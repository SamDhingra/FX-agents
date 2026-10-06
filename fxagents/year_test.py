"""Test every strategy on a long history the same way, and write a report Claude (or you) can read.

    ./fx.sh yeartest            # 365 days, every setup, every instrument, in the background (≈1 hour)
    ./fx.sh yeartest 180        # another length

What runs (all with the live rules — session windows, the bias rule, news blackouts, ATR stop floor,
OANDA-style fills on 1-minute bars, standard and scalp exits):
  1. pull N days of 1-minute history from OANDA into data/history_<N>d (reused for a day)
  2. the research grid: every setup × variant × instrument × timeframe × exit profile
  3. the weekly playbook selection replayed over that year (pick cells from the trailing 60 days, trade
     only the following unseen week, capacity rules applied) — the honest test of the whole system
  4. report.md (read this), cells.csv (every cell), summary.json (the playbook build output)

Everything lands in data/year_test/<N>d/; the live research, playbook and journals are untouched.
`./fx.sh yeartest` then publishes the report to the `results` branch on GitHub (see fx.sh publish).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .research import history_dir

MIN_N = 30          # cells with fewer trades are listed in cells.csv but not ranked in the report


def _fmt(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{d}f}" if isinstance(x, float) else str(x)


def cell_table(t: pd.DataFrame) -> pd.DataFrame:
    """One row per setup × variant × instrument × timeframe × exit, in plain R per trade."""
    t = t.copy()
    t["ts"] = pd.to_datetime(t["ts"])
    ns = t["ts"].astype("int64").to_numpy() if t["ts"].dt.tz is None else t["ts"].dt.tz_convert("UTC").astype("int64").to_numpy()
    edges = np.linspace(ns.min(), ns.max(), 5)[1:-1]
    t["q"] = np.clip(np.searchsorted(edges, ns, side="right"), 0, 3)
    rows = []
    for key, g in t.groupby(["setup", "variant", "sym", "tf", "mgmt"]):
        r = g["r"].to_numpy(float)
        sd = r.std(ddof=1) if len(r) > 1 else 0.0
        qs = [g.loc[g["q"] == k, "r"].mean() if (g["q"] == k).any() else np.nan for k in range(4)]
        rows.append(dict(zip(["setup", "variant", "sym", "tf", "mgmt"], key),
                         n=len(r), win=float((r > 0).mean()), avg_r=float(r.mean()), sum_r=float(r.sum()),
                         t=float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else np.nan,
                         h1=float(g.loc[g["q"] <= 1, "r"].mean()) if (g["q"] <= 1).any() else np.nan,
                         h2=float(g.loc[g["q"] >= 2, "r"].mean()) if (g["q"] >= 2).any() else np.nan,
                         q1=qs[0], q2=qs[1], q3=qs[2], q4=qs[3],
                         q_pos=int(sum(1 for x in qs if np.isfinite(x) and x > 0))))
    return pd.DataFrame(rows)


def write_report(out: Path, t: pd.DataFrame, cells: pd.DataFrame, summary: dict | None, days: int, cfg) -> str:
    L = []
    t = t.copy()
    t["ts"] = pd.to_datetime(t["ts"])
    L.append(f"# Strategy test — {days} days\n")
    L.append(f"Created {pd.Timestamp.now(tz=cfg['timezone']):%Y-%m-%d %H:%M} NY · trades {t['ts'].min():%Y-%m-%d} → "
             f"{t['ts'].max():%Y-%m-%d} · {len(t):,} simulated trades · {len(cells):,} cells\n")
    L.append("R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; "
             "an edge worth trading is positive in most quarters, not just on average. 1-minute cells are "
             "listed but the playbook doesn't trade 1m (spread is too large a share of the bar).\n")

    # 1 · the whole system, walk-forward
    if summary:
        wf = summary.get("walk_forward", {})
        s = wf.get("summary", {})
        L.append("## 1 · The playbook system, replayed week by week on unseen data\n")
        L.append("Each week: pick cells from the trailing 60 days, trade them the next week, capacity rules on. "
                 "This is the number that says whether the approach works.\n")
        L.append(f"- trades **{s.get('trades')}**, win rate **{(s.get('win_rate') or 0):.0%}**, avg **{_fmt(s.get('avg_r'), 3)}R**, "
                 f"total **{_fmt(s.get('sum_r'))}R**, profit factor {s.get('pf')}, worst drawdown {_fmt(s.get('max_dd_r'))}R, "
                 f"t-stat {s.get('t_stat')}, chance it's really ≤0: {s.get('p_boot')}")
        if s.get("sum_ex_top3") is not None:
            L.append(f"- without the 3 best trades: {_fmt(s.get('sum_ex_top3'))}R")
        for sym, x in (wf.get("by_symbol") or {}).items():
            L.append(f"- {sym}: {x.get('trades')} trades, {(x.get('win_rate') or 0):.0%} win, {_fmt(x.get('sum_r'))}R")
        wk = pd.DataFrame(wf.get("weekly") or [])
        if len(wk):
            wk["month"] = pd.to_datetime(wk["week"]).dt.strftime("%Y-%m")
            m = wk.groupby("month").agg(trades=("n", "sum"), r=("r", "sum")).round(2)
            L.append("\nBy month (R): " + " · ".join(f"{k} {v.r:+.1f} ({int(v.trades)})" for k, v in m.iterrows()))
            L.append(f"\nPositive weeks: {int((wk['r'] > 0).sum())} of {len(wk)}")
        L.append("")

    c = cells[(cells["n"] >= MIN_N)]
    # 2 · cells that held up
    L.append(f"## 2 · Cells that held up (≥{MIN_N} trades, positive in both halves and ≥3 of 4 quarters)\n")
    good = c[(c["avg_r"] > 0) & (c["h1"] > 0) & (c["h2"] > 0) & (c["q_pos"] >= 3)].sort_values("t", ascending=False)
    if len(good):
        L.append("| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in good.head(40).itertuples():
            L.append(f"| {r.setup} | {r.variant} | {r.sym} | {r.tf} | {r.mgmt} | {r.n} | {r.win:.0%} | {r.avg_r:+.3f} | {r.t:.1f} | "
                     f"{r.h1:+.2f} | {r.h2:+.2f} | {r.q1:+.2f} | {r.q2:+.2f} | {r.q3:+.2f} | {r.q4:+.2f} |")
        L.append(f"\n{len(good)} cells qualify out of {len(c)} with ≥{MIN_N} trades. With this many cells, a few "
                 "will pass by luck alone — a t above ~3 is the bar for 'probably real'.")
    else:
        L.append("None.")
    L.append("")

    # 3 · each setup, overall
    L.append("## 3 · Every setup, overall (default variant, standard exits, all timeframes but 1m)\n")
    d = t[(t["variant"] == "default") & (t["mgmt"] == "std") & (t["tf"] != "1min")]
    if len(d):
        mid = d["ts"].sort_values().iloc[len(d) // 2]
        rows = []
        for (setup, sym), g in d.groupby(["setup", "sym"]):
            rows.append((setup, sym, len(g), (g.r > 0).mean(), g.r.mean(), g[g.ts < mid].r.mean(), g[g.ts >= mid].r.mean()))
        rows.sort(key=lambda x: (x[0], x[1]))
        L.append("| setup | sym | trades | win | avg R | first half | second half |")
        L.append("|---|---|---|---|---|---|---|")
        for setup, sym, n, w, a, h1, h2 in rows:
            L.append(f"| {setup} | {sym} | {n} | {w:.0%} | {a:+.3f} | {_fmt(float(h1))} | {_fmt(float(h2))} |")
    L.append("")

    # 4 · best per setup
    L.append(f"## 4 · Best cell per setup (≥{MIN_N} trades, by t-stat)\n")
    if len(c):
        best = c.sort_values("t", ascending=False).drop_duplicates("setup")
        L.append("| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in best.itertuples():
            L.append(f"| {r.setup} | {r.variant} | {r.sym} | {r.tf} | {r.mgmt} | {r.n} | {r.win:.0%} | {r.avg_r:+.3f} | {r.t:.1f} | {r.q_pos}/4 |")
    txt = "\n".join(L) + "\n"
    (out / "report.md").write_text(txt)
    return txt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("days", nargs="?", type=int, default=365)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--classes", nargs="*")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from an earlier run's trades")
    a = ap.parse_args()
    from . import playbook, research
    from .setup_report import fetch_long
    cfg = load_config()
    base = history_dir(cfg)
    out = base.parent / "year_test" / f"{a.days}d"
    out.mkdir(parents=True, exist_ok=True)
    status = out / "status.json"
    t0 = time.time()

    def stage(s, **kw):
        status.write_text(json.dumps({"stage": s, "days": a.days, "elapsed_min": round((time.time() - t0) / 60, 1),
                                      "at": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"), **kw}))
        print(f"[{(time.time() - t0) / 60:5.1f} min] {s}", flush=True)

    syms = a.symbols or list(cfg["instruments"])
    cfg["history_dir"] = str(base)
    if not a.report_only:
        stage("fetching history")
        cfg["history_dir"] = str(fetch_long(cfg, base, a.days, syms))
    else:
        cfg["history_dir"] = str(base.parent / f"history_{a.days}d")
    cfg["research_dir"] = str(out)
    cfg["storage"] = {**cfg["storage"], "db_path": str(out / "journal.sqlite")}   # playbook.json goes here, not live
    if not a.report_only:
        stage("research grid (every setup × variant × instrument × timeframe)")
        research.run_all(cfg, syms, None, a.classes, a.workers)
    t = pd.read_pickle(out / "trades.pkl")
    stage("playbook walk-forward", trades=len(t))
    summary = None
    try:
        summary = playbook.build(cfg, robustness=False)
    except Exception as e:  # noqa: BLE001
        print("playbook walk-forward failed:", e)
    stage("report")
    cells = cell_table(t)
    cells.round(4).to_csv(out / "cells.csv", index=False)
    write_report(out, t, cells, summary, a.days, cfg)
    stage("done", trades=len(t), cells=len(cells))
    print((out / "report.md").read_text()[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
