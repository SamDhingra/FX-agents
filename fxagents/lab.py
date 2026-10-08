"""Strategy lab: new or enhanced strategies are tested here BEFORE they reach the playbook or the live book.

Stages:  new → testing → screened / failed → promoted (into the playbook as pinned cells) / rejected
Nothing in the lab trades or shows on the trading pages until it is promoted.

    ./fx.sh lab add trend_pullback --params '{"ema": 50}' --symbols XAUUSD NDQ --tfs 15min 30min --note "EMA50 pullbacks"
    ./fx.sh lab run <id>            # 90-day test (the cached history), ≈1–5 min
    ./fx.sh lab run <id> --days 365 # longer test (needs data/history_365d from ./fx.sh yeartest)
    ./fx.sh lab run <id> --days 365 --until 2026-06-30   # only history up to that day (keep the rest unseen)
    ./fx.sh lab run <id> --days 365 --from 2026-07-01    # only trades from that day on (earlier bars = warm-up)
    ./fx.sh lab list
    ./fx.sh lab promote <id> [--force]
The dashboard's Backtests page shows the same candidates with Run / Promote / Reject buttons.

Two levels, per instrument × timeframe × exit (audit §3.4):
  SCREENED (exploratory, was "PASS"): ≥ `min_n` trades, positive average R after spread, BOTH halves of the
    period positive, t ≥ `min_t`. A screen, not evidence: the halves are the same selected history.
  PROMOTABLE (the gate `promote` enforces): ≥ `promote_n` trades, average R > 0, the 95% day-block bootstrap
    lower bound of the average > 0 (trading days resampled), and average R > 0 at 2× spread (one extra
    spread per trade, cost_r). Still not proof — run it on a window the candidate was not designed on
    (--from/--until), and remember how many candidates were tried.
`promote` pins only promotable cells unless force=True (recorded in the pin and the candidate). Each pin
carries `effective_from` (the promotion time): replays/walk-forwards before that date don't trade it.
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

CRITERIA = {"min_n": 30, "min_t": 1.5, "promote_n": 100, "promote_lb": 0.0, "cost_mult": 2.0}


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


def screened(r: dict) -> bool:
    """A result row's screen verdict (results written before Oct 2026 call it "pass")."""
    return bool(r.get("screened", r.get("pass", False)))


def verdict(t: pd.DataFrame, crit: dict = CRITERIA) -> list[dict]:
    from .playbook import day_block_ci, days_of
    from .research import own_trades
    rows = []
    t = own_trades(t)
    if not len(t):
        return rows
    t = t.copy()
    t["ts"] = pd.to_datetime(t["ts"])
    t["_day"] = days_of(t)
    mid = t["ts"].sort_values().iloc[len(t) // 2]
    for (sym, tf, mg), g in t.groupby(["sym", "tf", "mgmt"]):
        r = g["r"].to_numpy(float)
        sd = r.std(ddof=1) if len(r) > 1 else 0.0
        tt = float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else 0.0
        h1, h2 = g[g.ts < mid]["r"], g[g.ts >= mid]["r"]
        ok = (len(r) >= crit["min_n"] and r.mean() > 0 and len(h1) and len(h2) and h1.mean() > 0 and h2.mean() > 0
              and tt >= crit["min_t"])
        # promotion gate: enough trades, a day-block 95% lower bound above zero, positive at 2× spread
        ci = day_block_ci(r, g["_day"])
        avg_2x = float((r - (crit["cost_mult"] - 1) * g["cost_r"].to_numpy(float)).mean()) if "cost_r" in g.columns else None
        prom = bool(len(r) >= crit["promote_n"] and r.mean() > 0 and ci is not None and ci["lo"] > crit["promote_lb"]
                    and avg_2x is not None and avg_2x > 0)
        rows.append({"sym": sym, "tf": tf, "mgmt": mg, "n": int(len(r)), "win": round(float((r > 0).mean()), 3),
                     "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1), "t": round(tt, 2),
                     "h1": round(float(h1.mean()), 3) if len(h1) else None,
                     "h2": round(float(h2.mean()), 3) if len(h2) else None, "screened": bool(ok),
                     "ci95": [ci["lo"], ci["hi"]] if ci else None,
                     "avg_r_2x_cost": round(avg_2x, 3) if avg_2x is not None else None, "promotable": prom})
    rows.sort(key=lambda x: (-x["promotable"], -x["screened"], -x["t"]))
    return rows


def window_history(src: Path, dst: Path, until: str | None, tz: str) -> Path:
    """Copy the history pickles (m1, h1) to `dst`, cut after `until` (a date: its whole NY day is kept), so
    nothing later can reach the test. instruments.json is copied as is."""
    import shutil
    dst.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp(until, tz=tz) + pd.Timedelta(days=1) if until else None
    for p in src.glob("*.pkl"):
        m1, h1 = pd.read_pickle(p)
        if end is not None:
            m1, h1 = m1[m1.index < end], h1[h1.index < end]
        pd.to_pickle((m1, h1), dst / p.name)
    if (src / "instruments.json").exists():
        shutil.copy(src / "instruments.json", dst / "instruments.json")
    return dst


def run(cfg, cid: str, days: int | None = None, since: str | None = None, until: str | None = None) -> dict:
    """Backtest one candidate with the research engine (live rules, OANDA-style fills, spread).
    until: use history only up to that date (inclusive); since: keep only trades entered from that date on —
    the earlier bars still warm up indicators and the bias, as live would have had them."""
    from . import research
    from .research import history_dir
    c = get(cfg, cid)
    if c is None:
        raise KeyError(cid)
    update(cfg, cid, status="testing", started=pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"))
    t0 = time.time()
    try:
        cfg = {**cfg, "instruments": dict(cfg["instruments"])}     # the trade:true flips below stay local
        base = history_dir(cfg)
        hd = base.parent / f"history_{days}d" if days else base
        if not hd.exists():
            raise FileNotFoundError(f"no history at {hd} (run ./fx.sh yeartest {days} first)")
        out = lab_dir(cfg) / c["id"]
        if until:
            hd = window_history(hd, out / "history_window", until, cfg["timezone"])
        cfg["history_dir"] = str(hd)
        cfg["research_dir"] = str(out)
        cfg["research"] = {**(cfg.get("research") or {}), "only_params": {c["setup"]: c["params"]}}
        for s in c["symbols"]:
            if s in cfg["instruments"]:
                cfg["instruments"][s] = {**cfg["instruments"][s], "trade": True}
        syms = [s for s in c["symbols"] if (hd / f"{s}.pkl").exists()]
        t = research.run_all(cfg, syms, c["tfs"], [c["setup"]], workers=1)
        if since and len(t):
            t = t[pd.to_datetime(t["ts"]) >= pd.Timestamp(since, tz=cfg["timezone"])].reset_index(drop=True)
            out.mkdir(parents=True, exist_ok=True)
            t.to_pickle(out / "trades.pkl")
        rows = verdict(t)
        own = research.own_trades(t)
        span = [str(pd.to_datetime(own["ts"]).min().date()), str(pd.to_datetime(own["ts"]).max().date())] if len(own) else None
        res = {"days": days or "cache", "span": span, "window": {"from": since, "until": until}, "trades": int(len(own)),
               "cells": rows, "screened": any(screened(r) for r in rows), "promotable": any(r["promotable"] for r in rows),
               "criteria": CRITERIA, "minutes": round((time.time() - t0) / 60, 1),
               "manifest": research.manifest(cfg, own, window={"from": since, "until": until})}
        hist = (c.get("history") or []) + [res]
        return update(cfg, cid, status="screened" if res["screened"] else "failed", results=res, history=hist[-5:],
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


def promote(cfg, cid: str, cells: list[dict] | None = None, force: bool = False) -> dict:
    """Pin the candidate's PROMOTABLE cells (or the given sym/tf/mgmt cells, each of which must be a tested,
    promotable cell) into the playbook. force=True overrides the gate — explicitly, and it is recorded in the
    pin and the candidate. Every pin is effective from now on (`effective_from`), never retroactively."""
    c = get(cfg, cid)
    if c is None or not c.get("results"):
        raise ValueError("test the candidate first")
    rows = c["results"]["cells"]
    pick = cells or [r for r in rows if r.get("promotable")] or ([r for r in rows if screened(r)] if force else [])
    if not pick:
        raise ValueError("no promotable cell (≥{promote_n} trades, day-block 95% lower bound > 0, positive at 2× spread)"
                         .format(**CRITERIA) + " — use force=True / --force to override on the record")
    now = pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds")
    pins = [p for p in lab_pinned(cfg) if p.get("lab_id") != cid]
    for r in pick:
        m = next((x for x in rows if x["sym"] == r["sym"] and x["tf"] == r["tf"] and x["mgmt"] == r["mgmt"]), None)
        if not force and (m is None or not m.get("promotable")):
            raise ValueError(f"{r['sym']} {r['tf']} {r['mgmt']}: " + ("not among the tested cells" if m is None else
                             "did not pass the promotion gate") + " — use force=True / --force to override on the record")
        m = m or r
        pins.append({"setup": c["setup"], "sym": r["sym"], "tf": r["tf"], "mgmt": r["mgmt"], "params": c["params"],
                     "n": m.get("n", 0), "win_rate": m.get("win", 0.5), "exp_r": m.get("avg_r", 0.0), "lab_id": cid,
                     "effective_from": now, "forced": bool(force and not m.get("promotable")),
                     "evidence": {k: m.get(k) for k in ("n", "avg_r", "ci95", "avg_r_2x_cost", "screened", "promotable")}
                     | {"span": c["results"].get("span"), "window": c["results"].get("window")}})
    tmp = pinned_path(cfg).with_suffix(".tmp")
    tmp.write_text(json.dumps(pins, indent=1))
    os.replace(tmp, pinned_path(cfg))
    return update(cfg, cid, status="promoted", promoted_at=now, forced=bool(force),
                  promoted=[{k: r[k] for k in ("sym", "tf", "mgmt")} for r in pick])


def unpromote(cfg, cid: str) -> dict:
    pins = [p for p in lab_pinned(cfg) if p.get("lab_id") != cid]
    pinned_path(cfg).write_text(json.dumps(pins, indent=1))
    return update(cfg, cid, status="rejected")


def _date(s: str) -> str:
    """YYYY-MM-DD, validated."""
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""):
        raise argparse.ArgumentTypeError(f"{s!r}: use YYYY-MM-DD")
    pd.Timestamp(s)
    return s


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
    a2.add_argument("--from", dest="since", type=_date, help="keep only trades entered from this date (YYYY-MM-DD)")
    a2.add_argument("--until", type=_date, help="use history only up to this date, inclusive (YYYY-MM-DD)")
    sub.add_parser("list")
    a4 = sub.add_parser("promote")
    a4.add_argument("id")
    a4.add_argument("--force", action="store_true", help="promote even though the gate failed (recorded in the pin)")
    a5 = sub.add_parser("reject")
    a5.add_argument("id")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "add":
        c = add(cfg, a.setup, json.loads(a.params), a.symbols, a.tfs, a.note)
        print(f"added {c['id']}: {c['setup']} {c['params']} on {', '.join(c['symbols'])} · {', '.join(c['tfs'])}")
    elif a.cmd == "run":
        c = run(cfg, a.id, a.days, a.since, a.until)
        print(f"{c['id']} {c['setup']}: {c['status']}" + (f" — {c.get('error')}" if c["status"] == "error" else ""))
        for r in (c.get("results") or {}).get("cells", [])[:12]:
            tag = "PROMOTABLE" if r.get("promotable") else "screened  " if screened(r) else "          "
            print(f"  {tag} {r['sym']:<7} {r['tf']:>5} {r['mgmt']:<6} {r['n']:>4} trades "
                  f"{r['win']:.0%} win {r['avg_r']:+.3f}R t {r['t']:+.2f} halves {r['h1']} / {r['h2']} "
                  f"95% {r.get('ci95')} 2×cost {r.get('avg_r_2x_cost')}")
    elif a.cmd == "list":
        for c in load(cfg):
            res = c.get("results") or {}
            best = (res.get("cells") or [{}])[0]
            print(f"{c['id']}  {c['status']:<9} {c['setup']:<18} {json.dumps(c['params'])[:40]:<40} "
                  + (f"best {best.get('sym')} {best.get('tf')} {best.get('avg_r', 0):+.3f}R t {best.get('t', 0):+.2f}" if best else ""))
    elif a.cmd == "promote":
        c = promote(cfg, a.id, force=a.force)
        print(f"promoted {c['id']}: {c['promoted']}" + (" (FORCED past the gate)" if c.get("forced") else ""))
    elif a.cmd == "reject":
        c = unpromote(cfg, a.id)
        print(f"rejected {c['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
