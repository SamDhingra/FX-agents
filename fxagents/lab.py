"""Strategy lab: new or enhanced strategies are tested here BEFORE they reach the playbook or the live book.

Stages:  new → testing → passed / failed → promoted (into the playbook as pinned cells) / rejected
Nothing in the lab trades or shows on the trading pages until it is promoted.

    ./fx.sh lab add trend_pullback --params '{"ema": 50}' --symbols XAUUSD NDQ --tfs 15min 30min --note "EMA50 pullbacks"
    ./fx.sh lab run <id>            # 90-day test (the cached history), ≈1–5 min
    ./fx.sh lab run <id> --days 365 # longer test (needs data/history_365d from ./fx.sh yeartest)
    ./fx.sh lab list
The dashboard's Backtests page shows the same candidates with Run / Promote / Reject buttons.

Verdict, per instrument × timeframe × exit: PASS when it has ≥ `min_n` trades, a positive average R after
spread, BOTH halves of the period positive, and t ≥ `min_t`. A candidate passes if any cell passes;
promotion pins the passing cells you choose into the playbook (data/lab/pinned.json), where the weekly
selection's caps still apply.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config

CRITERIA = {"min_n": 30, "min_t": 1.5}


def lab_dir(cfg) -> Path:
    d = Path(cfg["storage"]["db_path"]).parent / "lab"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(cfg) -> Path:
    return lab_dir(cfg) / "candidates.json"


def load(cfg) -> list[dict]:
    p = _path(cfg)
    try:
        return json.loads(p.read_text()) if p.exists() else []
    except ValueError:
        return []


def save(cfg, items: list[dict]) -> None:
    p = _path(cfg)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, default=str))
    os.replace(tmp, p)


def get(cfg, cid: str) -> dict | None:
    return next((c for c in load(cfg) if c["id"] == cid), None)


def update(cfg, cid: str, **kw) -> dict:
    items = load(cfg)
    for c in items:
        if c["id"] == cid:
            c.update(kw)
            save(cfg, items)
            return c
    raise KeyError(cid)


def add(cfg, setup: str, params: dict | None = None, symbols: list[str] | None = None, tfs: list[str] | None = None,
        note: str = "") -> dict:
    from .strategies import ALL
    if setup not in ALL:
        raise ValueError(f"unknown setup {setup!r}")
    params = dict(params or {})
    bad = [k for k in params if k not in ALL[setup].default_params and k not in ("block_hours", "sides")]
    if bad:
        raise ValueError(f"{setup} has no parameter(s) {', '.join(bad)} (has: {', '.join(ALL[setup].default_params)})")
    c = {"id": uuid.uuid4().hex[:8], "setup": setup, "params": params,
         "symbols": symbols or [s for s in cfg["instruments"]], "tfs": tfs or ["5min", "15min", "30min", "1h"],
         "note": note, "status": "new", "created": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"),
         "results": None}
    items = load(cfg)
    items.insert(0, c)
    save(cfg, items)
    return c


def verdict(t: pd.DataFrame, crit: dict = CRITERIA) -> list[dict]:
    rows = []
    if not len(t):
        return rows
    t = t.copy()
    t["ts"] = pd.to_datetime(t["ts"])
    mid = t["ts"].sort_values().iloc[len(t) // 2]
    for (sym, tf, mg), g in t.groupby(["sym", "tf", "mgmt"]):
        r = g["r"].to_numpy(float)
        sd = r.std(ddof=1) if len(r) > 1 else 0.0
        tt = float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else 0.0
        h1, h2 = g[g.ts < mid]["r"], g[g.ts >= mid]["r"]
        ok = (len(r) >= crit["min_n"] and r.mean() > 0 and len(h1) and len(h2) and h1.mean() > 0 and h2.mean() > 0
              and tt >= crit["min_t"])
        rows.append({"sym": sym, "tf": tf, "mgmt": mg, "n": int(len(r)), "win": round(float((r > 0).mean()), 3),
                     "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1), "t": round(tt, 2),
                     "h1": round(float(h1.mean()), 3) if len(h1) else None,
                     "h2": round(float(h2.mean()), 3) if len(h2) else None, "pass": bool(ok)})
    rows.sort(key=lambda x: (-x["pass"], -x["t"]))
    return rows


def run(cfg, cid: str, days: int | None = None) -> dict:
    """Backtest one candidate with the research engine (live rules, OANDA-style fills, spread)."""
    from . import research
    from .research import history_dir
    c = get(cfg, cid)
    if c is None:
        raise KeyError(cid)
    update(cfg, cid, status="testing", started=pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"))
    t0 = time.time()
    try:
        cfg = dict(cfg)
        base = history_dir(cfg)
        hd = base.parent / f"history_{days}d" if days else base
        if not hd.exists():
            raise FileNotFoundError(f"no history at {hd} (run ./fx.sh yeartest {days} first)")
        cfg["history_dir"] = str(hd)
        out = lab_dir(cfg) / c["id"]
        cfg["research_dir"] = str(out)
        cfg["research"] = {**(cfg.get("research") or {}), "only_params": {c["setup"]: c["params"]}}
        for s in c["symbols"]:
            if s in cfg["instruments"]:
                cfg["instruments"][s] = {**cfg["instruments"][s], "trade": True}
        syms = [s for s in c["symbols"] if (hd / f"{s}.pkl").exists()]
        t = research.run_all(cfg, syms, c["tfs"], [c["setup"]], workers=1)
        rows = verdict(t)
        span = [str(pd.to_datetime(t["ts"]).min().date()), str(pd.to_datetime(t["ts"]).max().date())] if len(t) else None
        res = {"days": days or "cache", "span": span, "trades": int(len(t)), "cells": rows,
               "passed": any(r["pass"] for r in rows), "criteria": CRITERIA, "minutes": round((time.time() - t0) / 60, 1)}
        hist = (c.get("history") or []) + [res]
        return update(cfg, cid, status="passed" if res["passed"] else "failed", results=res, history=hist[-5:],
                      finished=pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"))
    except Exception as e:  # noqa: BLE001
        return update(cfg, cid, status="error", error=str(e)[:300])


# ── promotion into the playbook ──────────────────────────────────────────────
def pinned_path(cfg) -> Path:
    return lab_dir(cfg) / "pinned.json"


def lab_pinned(cfg) -> list[dict]:
    p = pinned_path(cfg)
    try:
        return json.loads(p.read_text()) if p.exists() else []
    except ValueError:
        return []


def promote(cfg, cid: str, cells: list[dict] | None = None) -> dict:
    """Pin the candidate's passing cells (or the given sym/tf/mgmt cells) into the playbook."""
    c = get(cfg, cid)
    if c is None or not c.get("results"):
        raise ValueError("test the candidate first")
    rows = c["results"]["cells"]
    pick = cells or [r for r in rows if r["pass"]]
    if not pick:
        raise ValueError("no passing cell to promote (pick one explicitly to override)")
    pins = [p for p in lab_pinned(cfg) if p.get("lab_id") != cid]
    for r in pick:
        m = next((x for x in rows if x["sym"] == r["sym"] and x["tf"] == r["tf"] and x["mgmt"] == r["mgmt"]), r)
        pins.append({"setup": c["setup"], "sym": r["sym"], "tf": r["tf"], "mgmt": r["mgmt"], "params": c["params"],
                     "n": m.get("n", 0), "win_rate": m.get("win", 0.5), "exp_r": m.get("avg_r", 0.0), "lab_id": cid})
    tmp = pinned_path(cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(pins, indent=1))
    os.replace(tmp, pinned_path(cfg))
    return update(cfg, cid, status="promoted", promoted=[{k: r[k] for k in ("sym", "tf", "mgmt")} for r in pick])


def unpromote(cfg, cid: str) -> dict:
    pins = [p for p in lab_pinned(cfg) if p.get("lab_id") != cid]
    pinned_path(cfg).write_text(json.dumps(pins, indent=1))
    return update(cfg, cid, status="rejected")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("add")
    a1.add_argument("setup")
    a1.add_argument("--params", default="{}")
    a1.add_argument("--symbols", nargs="*")
    a1.add_argument("--tfs", nargs="*")
    a1.add_argument("--note", default="")
    a2 = sub.add_parser("run")
    a2.add_argument("id")
    a2.add_argument("--days", type=int)
    sub.add_parser("list")
    a4 = sub.add_parser("promote")
    a4.add_argument("id")
    a5 = sub.add_parser("reject")
    a5.add_argument("id")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "add":
        c = add(cfg, a.setup, json.loads(a.params), a.symbols, a.tfs, a.note)
        print(f"added {c['id']}: {c['setup']} {c['params']} on {', '.join(c['symbols'])} · {', '.join(c['tfs'])}")
    elif a.cmd == "run":
        c = run(cfg, a.id, a.days)
        print(f"{c['id']} {c['setup']}: {c['status']}" + (f" — {c.get('error')}" if c["status"] == "error" else ""))
        for r in (c.get("results") or {}).get("cells", [])[:12]:
            print(f"  {'PASS' if r['pass'] else '    '} {r['sym']:<7} {r['tf']:>5} {r['mgmt']:<6} {r['n']:>4} trades "
                  f"{r['win']:.0%} win {r['avg_r']:+.3f}R t {r['t']:+.2f} halves {r['h1']} / {r['h2']}")
    elif a.cmd == "list":
        for c in load(cfg):
            res = c.get("results") or {}
            best = (res.get("cells") or [{}])[0]
            print(f"{c['id']}  {c['status']:<9} {c['setup']:<18} {json.dumps(c['params'])[:40]:<40} "
                  + (f"best {best.get('sym')} {best.get('tf')} {best.get('avg_r', 0):+.3f}R t {best.get('t', 0):+.2f}" if best else ""))
    elif a.cmd == "promote":
        c = promote(cfg, a.id)
        print(f"promoted {c['id']}: {c['promoted']}")
    elif a.cmd == "reject":
        c = unpromote(cfg, a.id)
        print(f"rejected {c['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
