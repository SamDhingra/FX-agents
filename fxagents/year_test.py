"""Test every strategy on a long history the same way, and write a report Claude (or you) can read.

    ./fx.sh yeartest            # 365 days, every setup, every instrument, in the background (≈1 hour)
    ./fx.sh yeartest 180        # another length

What runs (all with the live rules — session windows, the bias rule, news blackouts, ATR stop floor,
OANDA-style fills on 1-minute bars, standard and scalp exits):
  1. pull N days of 1-minute history from OANDA into data/history_<N>d (reused for a day)
  2. the research grid: every setup × variant × instrument × timeframe × exit profile
  3. the weekly playbook selection replayed over that year (pick cells from the trailing
     playbook.window_days OBSERVED TRADE DAYS, trade only the following unseen week, capacity rules
     applied) — on the instruments the config actually trades (trade: true); watch-only instruments are
     researched (cells.csv, sections 2–4) but never enter the walk-forward portfolio
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
from .research import history_dir, manifest, own_trades

MIN_N = 30          # cells with fewer trades are listed in cells.csv but not ranked in the report


def _fmt(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{d}f}" if isinstance(x, float) else str(x)


def cell_table(t: pd.DataFrame) -> pd.DataFrame:
    """One row per setup × variant × instrument × timeframe × exit, in plain R per trade (each cell's own
    one-at-a-time record: busy_self candidates dropped)."""
    t = own_trades(t).copy()
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


def write_report(out: Path, t: pd.DataFrame, cells: pd.DataFrame, summary: dict | None, days: int, cfg, label: str = "") -> str:
    L = []
    t = own_trades(t).copy()
    t["ts"] = pd.to_datetime(t["ts"])
    L.append(f"# Strategy test — {label or f'{days} days'}\n")
    L.append(f"Created {pd.Timestamp.now(tz=cfg['timezone']):%Y-%m-%d %H:%M} NY · trades {t['ts'].min():%Y-%m-%d} → "
             f"{t['ts'].max():%Y-%m-%d} · {len(t):,} simulated trades · {len(cells):,} cells\n")
    L.append("R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; "
             "an edge worth trading is positive in most quarters, not just on average. 1-minute cells are "
             "listed but the playbook doesn't trade 1m (spread is too large a share of the bar).\n")

    # 1 · the whole system, walk-forward
    if summary:
        wf = summary.get("walk_forward", {})
        s = wf.get("summary", {})
        pol, dat = summary.get("policy") or {}, summary.get("data") or {}
        units = wf.get("units") or s.get("units") or "r"
        traded = [k for k, v in (pol.get("instruments") or {}).items() if v.get("role") != "off"]
        L.append("## 1 · The playbook system, replayed week by week on unseen data\n")
        L.append(f"Each week: pick cells from the trailing **{pol.get('window_days')} observed trade days** (days on which "
                 f"the research recorded at least one trade — not calendar days), trade them the next week, capacity "
                 f"rules on. The replay starts {dat.get('walk_forward_from')}, so its first weeks select on fewer days. "
                 f"Portfolio instruments (config trade: true): {', '.join(traded) or '—'}. "
                 "This is the number that says whether the approach works.\n")
        L.append(f"All R figures in this section are **{units}** "
                 + ("(budget-weighted: each trade's R × the share of the full risk budget Risk could take)."
                    if units == "rw" else "(per unit of each trade's own risk).") + "\n")
        ci = s.get("avg_ci95")
        L.append(f"- trades **{s.get('trades')}**, win rate **{(s.get('win_rate') or 0):.0%}**, avg **{_fmt(s.get('avg_r'), 3)}R**, "
                 f"total **{_fmt(s.get('sum_r'))}R**, profit factor {s.get('pf')}, worst drawdown {_fmt(s.get('max_dd_r'))}R, "
                 f"t-stat {s.get('t_stat')}, 95% interval of the average R per trade (day-block bootstrap, trading days "
                 f"resampled; not selection-adjusted): " + (f"[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "—"))
        if s.get("sum_ex_top3") is not None:
            L.append(f"- without the 3 best trades: {_fmt(s.get('sum_ex_top3'))}R")
        for sym, x in (wf.get("by_symbol") or {}).items():
            L.append(f"- {sym}: {x.get('trades')} trades, {(x.get('win_rate') or 0):.0%} win, {_fmt(x.get('sum_r'))}R")
        wk = pd.DataFrame(wf.get("weekly") or [])
        if len(wk):
            wk["month"] = pd.to_datetime(wk["week"]).dt.strftime("%Y-%m")
            m = wk.groupby("month").agg(trades=("n", "sum"), r=("r", "sum")).round(2)
            L.append(f"\nBy month ({units}): " + " · ".join(f"{k} {v.r:+.1f} ({int(v.trades)})" for k, v in m.iterrows()))
            L.append(f"\nPositive weeks: {int((wk['r'] > 0).sum())} of {len(wk)} · weekly {units} sums to "
                     f"{wk['r'].sum():+.2f}R (= the total above)")
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
                 "will pass by luck alone; t here is a per-cell screen, not corrected for the number of cells tried.")
    else:
        L.append("None.")
    L.append("")

    # 3 · each setup, overall
    L.append("## 3 · Every setup, overall (default variant, all timeframes but 1m; std = 1R first target, "
             "trend = 2R first target, 15m+ only)\n")
    d = t[(t["variant"] == "default") & (t["mgmt"].isin(["std", "trend"])) & (t["tf"] != "1min")]
    if len(d):
        mid = d["ts"].sort_values().iloc[len(d) // 2]
        rows = []
        for (setup, sym, mg), g in d.groupby(["setup", "sym", "mgmt"]):
            rows.append((setup, sym, mg, len(g), (g.r > 0).mean(), g.r.mean(), g[g.ts < mid].r.mean(), g[g.ts >= mid].r.mean()))
        rows.sort(key=lambda x: (x[0], x[1], x[2]))
        L.append("| setup | sym | exit | trades | win | avg R | first half | second half |")
        L.append("|---|---|---|---|---|---|---|---|")
        for setup, sym, mg, n, w, a, h1, h2 in rows:
            L.append(f"| {setup} | {sym} | {mg} | {n} | {w:.0%} | {a:+.3f} | {_fmt(float(h1))} | {_fmt(float(h2))} |")
    L.append("")

    # 3b · exit management compared on the same signals
    ex = t[(t["variant"] == "default") & (t["tf"] != "1min")]
    if ex["mgmt"].nunique() > 1:
        L.append("## 3b · Exits compared (same signals, default variants, all instruments, 15m+ for trend)\n")
        L.append("std = 1R first target, half banked, runner trailed (the bot today) · scalp = all out at 1R, 30-min cap (≤5m) · "
                 "trend = 2R first target + runner · tpX = all out at X R, no runner\n")
        L.append("| exit | trades | win | avg R | total R | per symbol (avg R) |")
        L.append("|---|---|---|---|---|---|")
        for mg, g in ex.groupby("mgmt"):
            per = " · ".join(f"{s} {x.r.mean():+.3f}" for s, x in g.groupby("sym"))
            L.append(f"| {mg} | {len(g)} | {(g.r > 0).mean():.0%} | {g.r.mean():+.3f} | {g.r.sum():+.0f} | {per} |")
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


def execution_cfg(cfg, mandate: list[str]) -> dict:
    """The config as the bot trades it: only `mandate` instruments have trade: true (policy_from_cfg turns
    the rest off), whatever the research universe was."""
    return {**cfg, "instruments": {s: {**ic, "trade": s in mandate} for s, ic in cfg["instruments"].items()}}


def run_one(a, costs: str, tag: str) -> None:
    from . import playbook, research
    from .setup_report import fetch_long
    cfg = load_config()
    base = history_dir(cfg)
    out = base.parent / "year_test" / (f"{a.days}d" + (f"_{tag}" if tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    status = out / "status.json"
    t0 = time.time()

    def stage(s, **kw):
        status.write_text(json.dumps({"stage": s, "days": a.days, "elapsed_min": round((time.time() - t0) / 60, 1),
                                      "at": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"), **kw}))
        print(f"[{(time.time() - t0) / 60:5.1f} min] {s}", flush=True)

    syms = a.symbols or list(cfg["instruments"])
    # the execution mandate is the ORIGINAL config's trade flags: watch-only instruments are researched
    # (that's the point) but the walk-forward portfolio only trades what the bot really trades (F17)
    mandate = [s for s, ic in cfg["instruments"].items() if ic.get("trade", True) is not False]
    for s in syms:
        cfg["instruments"][s]["trade"] = True
    if costs == "raw":
        sc = cfg.setdefault("shadow", {})
        sc["spread"] = {**(sc.get("spread") or {}), **research.RAW_SPREAD}
    if a.exits:
        cfg.setdefault("research", {})["exit_profiles"] = list(a.exits)
    if a.window:
        cfg.setdefault("playbook", {})["window_days"] = int(a.window)
    if a.tfs:
        cfg.setdefault("playbook", {})["tfs"] = [t for t in a.tfs if t != "1min"] or a.tfs
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
        research.run_all(cfg, syms, a.tfs, a.classes, a.workers)
    t = pd.read_pickle(out / "trades.pkl")
    stage("playbook walk-forward", trades=len(t))
    summary = None
    try:
        summary = playbook.build(execution_cfg(cfg, mandate), robustness=False)
    except Exception as e:  # noqa: BLE001
        print("playbook walk-forward failed:", e)
    stage("report")
    cells = cell_table(t)
    cells.round(4).to_csv(out / "cells.csv", index=False)
    pol = (summary or {}).get("policy") or {}
    (out / "run.json").write_text(json.dumps({"days": a.days, "costs": costs, "tfs": a.tfs, "classes": a.classes,
                                              "exits": a.exits, "window": a.window,
                                              "window_days": pol.get("window_days"), "window_units": "observed trade days",
                                              "symbols": syms, "portfolio_instruments": mandate,
                                              "spreads": (cfg.get("shadow") or {}).get("spread"),
                                              "manifest": manifest(execution_cfg(cfg, mandate), t)}, indent=1, default=str))
    write_report(out, t, cells, summary, a.days, cfg, label=f"{a.days} days · costs {costs}"
                 + (f" · {' '.join(a.tfs)}" if a.tfs else "") + (f" · {tag}" if tag else ""))
    stage("done", trades=len(t), cells=len(cells))
    print((out / "report.md").read_text()[:3000])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("days", nargs="?", type=int, default=365)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--classes", nargs="*")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--tfs", nargs="*", help="entry timeframes (default: all)")
    ap.add_argument("--costs", choices=["oanda", "raw", "both"], default="oanda",
                    help="raw = an ECN account: 0.0–1 pip spreads + ~$7/lot commission (research.RAW_SPREAD); "
                         "both = run twice, folders <tag>_oanda and <tag>_raw")
    ap.add_argument("--tag", default="", help="name for this run's folder, e.g. trend_raw → data/year_test/365d_trend_raw")
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from an earlier run's trades")
    ap.add_argument("--exits", nargs="*", default=[],
                    help="extra fixed take-profit exits to compare with the runner management, e.g. tp1 tp1.5 tp2")
    ap.add_argument("--window", type=int, help="playbook selection window in OBSERVED TRADE DAYS (default: config "
                                               "playbook.window_days); use ~30 on a 90-day test")
    a = ap.parse_args()
    costs = ["oanda", "raw"] if a.costs == "both" else [a.costs]
    for c in costs:
        tag = "_".join(x for x in (a.tag, c if a.costs == "both" else "") if x)
        run_one(a, c, tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
