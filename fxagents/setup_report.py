"""Backtest ONE setup on the cached history and print a report.   ./fx.sh setup-test london_breakout XAUUSD

Same engine and rules as the weekly research (session windows, the bias rule, news blackouts, ATR stop
floor, OANDA-style fills on 1-minute bars, the standard and scalp exit profiles) — but written to its own
folder (data/research_one/<setup>), so the real research results and the playbook are untouched.

Prints, per instrument: every variant × timeframe × exit profile with trades, win rate, average R and the
two halves of the period separately (an edge should show in both), then the default variant's trades.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import time

import pandas as pd

from .config import load_config
from . import research
from .research import TFS, history_dir


def fetch_long(cfg, base, days: int, syms: list[str]):
    """Longer 1-minute history from OANDA into data/history_<days>d (re-used for a day)."""
    from .config import apply_broker
    from .oanda import OandaFeed, oanda_from_cfg
    d = base.parent / f"history_{days}d"
    d.mkdir(parents=True, exist_ok=True)
    if (base / "instruments.json").exists():
        shutil.copy(base / "instruments.json", d / "instruments.json")
    todo = [s for s in syms if not ((d / f"{s}.pkl").exists() and time.time() - (d / f"{s}.pkl").stat().st_mtime < 86400)]
    if not todo:
        return d
    c2 = {**cfg, "mode": "paper", "broker": "oanda", "instruments": {k: dict(v) for k, v in cfg["instruments"].items()}}
    apply_broker(c2)

    async def go():
        feed = OandaFeed(c2, None, None, oanda_from_cfg(c2))
        now = pd.Timestamp.now(tz="UTC")
        for s in todo:
            name = feed.syms[s]
            print(f"  pulling {days} days of {s} 1-minute candles from OANDA …", flush=True)
            m1 = feed._frame(await feed._paged(name, "M1", now - pd.Timedelta(days=days)))
            h1 = feed._frame(await feed._paged(name, "H1", now - pd.Timedelta(days=days + 45)), vol=False)
            print(f"    {len(m1):,} bars, {m1.index[0]:%Y-%m-%d} → {m1.index[-1]:%Y-%m-%d}", flush=True)
            pd.to_pickle((m1, h1), d / f"{s}.pkl")
    asyncio.run(go())
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("setup")
    ap.add_argument("symbols", nargs="*", help="default: every instrument with cached history")
    ap.add_argument("--tfs", nargs="*", default=None, help=f"default: {' '.join(TFS)}")
    ap.add_argument("--trades", type=int, default=25, help="how many of the default variant's trades to list")
    ap.add_argument("--days", type=int, default=None,
                    help="pull this many days of 1-minute history from OANDA first (e.g. 365); default: the ~90-day cache")
    a = ap.parse_args()
    from .strategies import ALL
    if a.setup not in ALL:
        sys.exit(f"unknown setup {a.setup!r}. Known: {', '.join(sorted(ALL))}")
    cfg = load_config()
    base = history_dir(cfg)
    syms = a.symbols or None
    if a.days:
        cfg["history_dir"] = str(fetch_long(cfg, base, a.days, syms or list(cfg["instruments"])))
    else:
        cfg["history_dir"] = str(base)
    out_dir = base.parent / "research_one" / (a.setup + (f"_{a.days}d" if a.days else ""))
    cfg["research_dir"] = str(out_dir)
    print(f"Backtesting {a.setup} on {', '.join(syms or ['all instruments'])} … (a few minutes)", flush=True)
    t = research.run_all(cfg, syms, a.tfs, [a.setup], workers=1)
    if not len(t):
        print("No trades: the setup never fired inside the entry windows on this history.")
        return 0
    t["ts"] = pd.to_datetime(t["ts"])
    days = t["day"].nunique()
    mid = t["ts"].sort_values().iloc[len(t) // 2]
    print(f"\nHistory: {t['day'].min()} → {t['day'].max()} ({days} trading days with trades) · halves split at {mid:%b %d}")
    print("R = result in units of the trade's risk, after spread. 'first'/'second' = average R in each half.\n")
    tf_order = {tf: i for i, tf in enumerate(TFS)}
    for sym, g in t.groupby("sym"):
        rows = []
        for (var, tf, mg), x in g.groupby(["variant", "tf", "mgmt"]):
            rows.append({"variant": var, "tf": tf, "exit": mg, "trades": len(x), "win": f"{(x.r > 0).mean():.0%}",
                         "avg R": round(x.r.mean(), 2), "total R": round(x.r.sum(), 1),
                         "first": round(x[x.ts < mid].r.mean(), 2) if (x.ts < mid).any() else None,
                         "second": round(x[x.ts >= mid].r.mean(), 2) if (x.ts >= mid).any() else None})
        rep = pd.DataFrame(rows)
        rep["_o"] = rep["tf"].map(tf_order)
        rep = rep.sort_values(["variant", "_o", "exit"]).drop(columns="_o")
        print(f"━━ {sym}")
        print(rep.to_string(index=False))
        d = g[(g.variant == "default") & (g.mgmt == "std")].sort_values("ts")
        if len(d):
            print(f"\n  default variant, standard exits — last {min(a.trades, len(d))} of {len(d)} trades:")
            for r in d.tail(a.trades).itertuples():
                print(f"    {r.ts:%a %b %d %H:%M}  {r.tf:>5}  {'LONG ' if r.side > 0 else 'SHORT'}  {r.r:+.2f}R  ({r.exit})")
        print()
    print(f"Saved: {out_dir}/trades.pkl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
