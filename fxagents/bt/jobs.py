"""Run ledger jobs: one at a time, in the `fxbt` worker container (its own memory cap, so a big backtest can never
starve the live bot), or inline from the CLI."""
from __future__ import annotations

import gzip
import json
import time
import traceback

import pandas as pd

from . import data, engine, ledger, stats
from .run import load_plugin


class Cancelled(Exception):
    pass


def _jsonable(t: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, pd.Timestamp) else v) for k, v in t.items() if k not in ("j", "jx")}


def execute(rid: str, audit: int = 10) -> dict:
    r = ledger.get(rid)
    d = ledger.run_dir(rid)
    last = [0.0]

    def stage(name, pct):
        now = time.time()
        if now - last[0] < 2 and pct not in (0, 100):
            return
        last[0] = now
        cur = ledger.get(rid)
        if cur and cur["status"] == "cancel":
            raise Cancelled()
        ledger.update(rid, stage=name, pct=round(float(pct), 1))

    try:
        cls, sha = load_plugin(d / "code.py")
        if sha != r["code_sha"]:
            raise RuntimeError("code changed after the run was queued")
        if r["role"] == "vault":                                   # re-checked at run time (two queued at once)
            con = ledger.db()
            try:
                n = con.execute("SELECT COUNT(*) FROM runs WHERE plugin=? AND code_sha=? AND params=? AND symbol=? "
                                "AND role='vault' AND status IN ('running','done') AND id<>?",
                                (r["plugin"], r["code_sha"], r["params"], r["symbol"], rid)).fetchone()[0]
            finally:
                con.close()
            if n:
                raise PermissionError("vault already opened for this exact strategy")
        strat = cls(**json.loads(r["params"]))
        stage("loading data", 2)
        m = data.load(r["dataset"], r["symbol"])
        stage("finding signals", 10)
        sigs = sorted(strat.signals(m), key=lambda s: s.t)
        stage(f"simulating {len(sigs)} signals", 30)
        res = engine.simulate(strat, m, sigs, progress=lambda i, n: stage(f"simulating {i}/{n}", 30 + 45 * i / max(n, 1)))
        diag = getattr(strat, "diag", None)          # the full-data diagnostics (the audit re-runs signals on slices)
        out = stats.summarize(res, m)
        stage("look-ahead audit", 78)
        out["audit"] = engine.lookahead_audit(strat, m, sigs, audit, warm_days=strat.warmup_days) if audit else None
        out["variants"] = {}
        vtrades = {}
        for i, (name, ov) in enumerate(strat.variants.items()):
            stage(f"control: {name}", 85 + 10 * i / max(len(strat.variants), 1))
            vr = engine.simulate(strat.with_params(**ov), m, controls=False)
            vtrades[name] = vr["trades"]
            out["variants"][name] = stats.summarize(vr, m)["stats"]
        extra = []
        if hasattr(strat, "compare"):                # optional strategy-specific report section
            if diag is not None:
                strat.diag = diag
            try:
                extra = list(strat.compare(m, res["trades"], vtrades) or [])
            except Exception as e:  # noqa: BLE001 — a report extra never fails the run
                extra = ["", f"(strategy comparison failed: {e})"]
        stats.add_variant_gate(out)
        if out["audit"] and out["audit"]["failed"]:
            out["gates"]["no look-ahead"] = False
            out["gates"]["PASS"] = False
        out["run"] = {k: r[k] for k in ("id", "plugin", "name", "code_sha", "params", "symbol", "dataset", "role")}
        title = f"{r['name']} ({r['symbol']}, code {r['code_sha']}, run {rid})"
        (d / "summary.json").write_text(json.dumps(out, default=str))
        with gzip.open(d / "trades.json.gz", "wt") as fh:
            json.dump([_jsonable(t) for t in res["trades"]], fh, default=str)
        out["extra"] = extra
        (d / "report.md").write_text(stats.text(title, r["dataset"], out, out["audit"]) + "\n" +
                                     ("\n".join(extra) + "\n" if extra else ""))
        s = out["stats"]
        ledger.update(rid, status="done", stage="done", pct=100, finished=time.time(), trades=s.get("trades", 0),
                      avg_r=s.get("avg_R"), ci_lo=s.get("ci_lo"), passed=int(bool(out["gates"]["PASS"])))
        return out
    except Cancelled:
        ledger.update(rid, status="cancelled", stage="cancelled", finished=time.time())
        raise
    except Exception as e:  # noqa: BLE001
        ledger.update(rid, status="error", stage="error", finished=time.time(),
                      error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
        raise


def _child(rid: str):
    try:
        execute(rid)
    except Exception:  # noqa: BLE001 — execute() already recorded it in the ledger
        pass


def run_job(rid: str, poll: float = 1.0) -> str:
    """Run one job in its own process, so a cancel stops it at once (not at its next progress step) and everything it
    loaded is freed when it ends. Returns the final status."""
    import multiprocessing as mp
    p = mp.get_context("fork").Process(target=_child, args=(rid,), daemon=True)
    p.start()
    while p.is_alive():
        p.join(poll)
        r = ledger.get(rid)
        if r and r["status"] == "cancel" and p.is_alive():
            p.terminate()
            p.join(10)
            ledger.update(rid, status="cancelled", stage="cancelled", finished=time.time())
    r = ledger.get(rid) or {}
    if r.get("status") in ("running", "cancel"):              # the process died without recording an outcome
        ledger.update(rid, status="cancelled" if r["status"] == "cancel" else "error", stage="error",
                      finished=time.time(), error=f"job process ended unexpectedly (exit {p.exitcode}; out of memory?)")
    return (ledger.get(rid) or {}).get("status", "?")


def worker(poll: float = 3.0, once: bool = False):
    # a run left running by a crash/restart can't still be running (one worker): record what happened to it
    con = ledger.db()
    try:
        con.execute("UPDATE runs SET status='cancelled', stage='cancelled' WHERE status='cancel'")
        con.execute("UPDATE runs SET status='error', stage='error', error='worker restarted mid-run' "
                    "WHERE status='running'")
    finally:
        con.close()
    print("bt worker: waiting for jobs", flush=True)
    while True:
        r = ledger.claim()
        if r:
            print(f"bt worker: {r['id']} {r['plugin']} {r['symbol']} {r['dataset']}", flush=True)
            print(f"bt worker: {r['id']} {run_job(r['id'])}", flush=True)
        elif once:
            return
        else:
            time.sleep(poll)
