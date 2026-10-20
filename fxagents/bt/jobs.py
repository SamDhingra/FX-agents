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
        out = stats.summarize(res, m)
        stage("look-ahead audit", 78)
        out["audit"] = engine.lookahead_audit(strat, m, sigs, audit, warm_days=strat.warmup_days) if audit else None
        out["variants"] = {}
        for i, (name, ov) in enumerate(strat.variants.items()):
            stage(f"control: {name}", 85 + 10 * i / max(len(strat.variants), 1))
            out["variants"][name] = stats.summarize(engine.simulate(strat.with_params(**ov), m, controls=False), m)["stats"]
        stats.add_variant_gate(out)
        if out["audit"] and out["audit"]["failed"]:
            out["gates"]["no look-ahead"] = False
            out["gates"]["PASS"] = False
        out["run"] = {k: r[k] for k in ("id", "plugin", "name", "code_sha", "params", "symbol", "dataset", "role")}
        title = f"{r['name']} ({r['symbol']}, code {r['code_sha']}, run {rid})"
        (d / "summary.json").write_text(json.dumps(out, default=str))
        with gzip.open(d / "trades.json.gz", "wt") as fh:
            json.dump([_jsonable(t) for t in res["trades"]], fh, default=str)
        (d / "report.md").write_text(stats.text(title, r["dataset"], out, out["audit"]) + "\n")
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


def worker(poll: float = 3.0, once: bool = False):
    # a run left "running" by a crash/restart can't still be running (one worker): mark it so it can be re-queued
    con = ledger.db()
    try:
        con.execute("UPDATE runs SET status='error', stage='error', error='worker restarted mid-run' "
                    "WHERE status IN ('running','cancel')")
    finally:
        con.close()
    print("bt worker: waiting for jobs", flush=True)
    while True:
        r = ledger.claim()
        if r:
            print(f"bt worker: {r['id']} {r['plugin']} {r['symbol']} {r['dataset']}", flush=True)
            try:
                execute(r["id"])
                print(f"bt worker: {r['id']} done", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"bt worker: {r['id']} {type(e).__name__}: {e}", flush=True)
        elif once:
            return
        else:
            time.sleep(poll)
