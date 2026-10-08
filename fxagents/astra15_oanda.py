"""Astra's frozen 15-strategy screen (ASTRA-INTRADAY-15-v0.2.0-simple) run unchanged on our OANDA history.

fxagents/astra15/backtest.py and strategies.json are byte-identical copies of the files Astra delivered on
2026-10-08 (sha256 of backtest.py starts 697e407e3b50c2ed). Nothing here changes a rule, a cost or a threshold:
this wrapper only turns data/history_<N>d/<SYM>.pkl (OANDA 1-minute mid candles + tick volume) into the CSV
input that code expects, cut to a date window, and writes a short report.

Astra designed and revised these rules on vendor data from 2026-03-26 to 2026-09-25. OANDA data before
2026-03-26 was never looked at, so `--until 2026-03-25` is a genuine out-of-sample test of frozen rules.

  python -m fxagents.astra15_oanda --days 730 --until 2026-03-25 --out data/year_test/astra15_unseen
  python -m fxagents.astra15_oanda --days 730 --from 2026-02-01 --until 2026-09-25 \
      --splits 2026-06-30 2026-07-31 2026-09-25 --out data/year_test/astra15_overlap   # same dates as Astra's
"""
from __future__ import annotations

import argparse
import json
import resource
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .astra15 import backtest as bt

SYMS = ["XAUUSD", "NDQ", "US30"]
# Astra's vendor-data results (simple revision, base costs, volume filter on), from its report §4, for comparison.
ASTRA_VENDOR = {"G-S1": (21, -0.244), "G-S2": (58, 0.097), "G-S3": (18, -0.137), "G-H1": (0, None), "G-H2": (34, 0.009),
                "N-S1": (20, 0.345), "N-S2": (46, 0.211), "N-S3": (14, -0.478), "N-H1": (3, -0.512), "N-H2": (25, -0.189),
                "U-S1": (10, -0.300), "U-S2": (40, 0.212), "U-S3": (21, -0.167), "U-H1": (1, 0.398), "U-H2": (17, -0.065)}
SHORTLIST = ["U-S2", "G-S2", "N-S1", "N-S2"]


def export(hd: Path, dst: Path, start: str | None, until: str | None) -> dict:
    """OANDA cache → Astra's CSV format (UTC bar-open timestamps, mid OHLC, tick volume). Our own trusted pickles only."""
    dst.mkdir(parents=True, exist_ok=True)
    span = {}
    for s in SYMS:
        m1 = pd.read_pickle(hd / f"{s}.pkl")[0]
        m1 = m1[["open", "high", "low", "close", "volume"]].astype(float)
        m1.index = pd.DatetimeIndex(m1.index).tz_convert("UTC")
        if start:
            m1 = m1[m1.index >= pd.Timestamp(start, tz="UTC")]
        if until:
            m1 = m1[m1.index < pd.Timestamp(until, tz="UTC") + pd.Timedelta("1D")]
        m1 = m1[~m1.index.duplicated()].sort_index()
        m1.index.name = "datetime"
        m1.to_csv(dst / f"{s}.csv")
        span[s] = [str(m1.index[0].date()), str(m1.index[-1].date()), len(m1)]
        print(f"  {s}: {len(m1):,} bars {span[s][0]} → {span[s][1]}", flush=True)
    return span


def _f(x, nd=3, sign=True):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}")


def report(summary: pd.DataFrame, span: dict, splits: dict, label: str) -> tuple[str, list[dict]]:
    def cell(i, seg="all", cost=1.0, vol=True):
        r = summary[(summary.id == i) & (summary.segment == seg) & (summary.cost_mult == cost) & (summary.volume_filter == vol)]
        return r.iloc[0] if len(r) else None

    rows, verdicts = [], []
    for i in ASTRA_VENDOR:
        b, x2, vo = cell(i), cell(i, cost=2.0), cell(i, vol=False)
        d, v, e = cell(i, "development"), cell(i, "validation"), cell(i, "evaluation")
        n = int(b.trades)
        ok = (n >= 100 and (b.avg_R or 0) > 0 and pd.notna(b.ci_low) and b.ci_low > 0 and (x2.avg_R or 0) > 0)
        why = ("PASS" if ok else "too few trades" if n < 100 else "avg R ≤ 0" if not (b.avg_R or 0) > 0
               else "95% range includes 0" if not (pd.notna(b.ci_low) and b.ci_low > 0) else "fails at 2× costs")
        verdicts.append({"id": i, "trades": n, "avg_R": None if n == 0 else float(b.avg_R), "ci_low": None if pd.isna(b.ci_low) else float(b.ci_low),
                         "ci_high": None if pd.isna(b.ci_high) else float(b.ci_high), "avg_R_2x": None if not x2.trades else float(x2.avg_R),
                         "q_primary_15": None if pd.isna(b.q_primary_15) else float(b.q_primary_15), "verdict": why})
        an, aa = ASTRA_VENDOR[i]
        ci = "—" if pd.isna(b.ci_low) else f"{b.ci_low:+.2f} to {b.ci_high:+.2f}"
        rows.append(f"| {i}{' ★' if i in SHORTLIST else ''} | {n} | {_f(b.avg_R if n else None)} | {ci} | {_f(b.total_R, 1)} | "
                    f"{_f(x2.avg_R if x2.trades else None)} | {_f(vo.avg_R if vo.trades else None)} ({int(vo.trades)}) | "
                    f"{_f(d.avg_R if d.trades else None, 2)} / {_f(v.avg_R if v.trades else None, 2)} / {_f(e.avg_R if e.trades else None, 2)} | "
                    f"{an} / {_f(aa)} | {why} |")
    passes = [v["id"] for v in verdicts if v["verdict"] == "PASS"]
    short = [v for v in verdicts if v["id"] in SHORTLIST]
    head = (f"# Astra 15 strategies on OANDA data — {label}\n\n"
            f"Rules: ASTRA-INTRADAY-15-v0.2.0-simple, Astra's own code run unchanged (fxagents/astra15). "
            f"Costs: Astra's (spread 0.40 / 1.50 / 2.50, slippage 0.10 / 0.375 / 0.625 per fill).\n"
            f"Data: {', '.join(f'{s} {a} → {b} ({n:,} bars)' for s, (a, b, n) in span.items())}. "
            f"Slices: development ≤ {splits['development_end']}, validation ≤ {splits['validation_end']}, evaluation ≤ {splits['evaluation_end']}.\n\n"
            f"## Headline\n\n"
            f"**{'PASS: ' + ', '.join(passes) if passes else 'Nothing passes'}** "
            f"(pass = ≥100 trades, avg R > 0, 5-session-block 95% range above 0, avg R > 0 at 2× costs).\n\n"
            "Astra's shortlist: " + "; ".join(f"{v['id']} {v['trades']} trades, avg {_f(v['avg_R'])}R, 95% "
                                              f"{_f(v['ci_low'], 2)} to {_f(v['ci_high'], 2)}, 2× costs {_f(v['avg_R_2x'])}"
                                              for v in short) + ".\n\n"
            "## All 15 (base costs, volume filter on)\n\n"
            "| ID | Trades | Avg R | 95% range | Total R | Avg R 2× costs | Avg R volume off (N) | Avg R dev / val / eval | Astra vendor N / avg R | Verdict |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n")
    return head + "\n".join(rows) + "\n", verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=730, help="read data/history_<days>d (as left by yeartest/newstrats)")
    ap.add_argument("--history", type=Path, help="history folder (overrides --days)")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--until", default="2026-03-25")
    ap.add_argument("--splits", nargs=3, metavar=("DEV_END", "VAL_END", "EVAL_END"),
                    help="default: thirds of the window, last = --until")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    hd = a.history or Path("data") / f"history_{a.days}d"
    a.out.mkdir(parents=True, exist_ok=True)
    tmp = a.out / "_csv"
    print(f"exporting {hd} → CSV", flush=True)
    span = export(hd, tmp, a.start, a.until)
    if a.splits:
        splits = dict(zip(["development_end", "validation_end", "evaluation_end"], a.splits))
    else:
        first = max(pd.Timestamp(v[0]) for v in span.values()) + pd.Timedelta(days=45)   # ≈ the 500-H1-bar warmup
        last = pd.Timestamp(a.until)
        step = (last - first) / 3
        splits = {"development_end": str((first + step).date()), "validation_end": str((first + 2 * step).date()),
                  "evaluation_end": str(last.date())}
    raw = a.out / "raw"
    bt.run(tmp, raw, "simple", splits)
    shutil.rmtree(tmp, ignore_errors=True)
    summary = pd.read_csv(raw / "summary.csv")
    label = a.label or (f"{a.start or 'start'} → {a.until}")
    md, verdicts = report(summary, span, splits, label)
    (a.out / "report.md").write_text(md)
    summary.to_csv(a.out / "cells.csv", index=False)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    (a.out / "run.json").write_text(json.dumps({"rules": "ASTRA-INTRADAY-15-v0.2.0-simple", "history": str(hd), "span": span,
                                                "splits": splits, "verdicts": verdicts, "peak_rss_mb": round(peak)}, indent=2))
    print(md.split("## All 15")[0], flush=True)
    print(f"peak memory {peak:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
