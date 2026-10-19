"""Exit study: protection BEFORE the first target, on the entries the bot actually trades (Sam, 2026-10-19).

    python -m fxagents.exit_study [--days 365] [--workers 2]          (./fx.sh exitstudy)

Why: live trades reach +0.5R … +0.9R and fall back to a loss — the first partial and every stop move wait for +1R.
Every cell of the current playbook (data/playbook.json) is replayed on 1-minute bars with real spread, exactly as the
research grid and the live agents manage it, once per variant (same entries, only the exit changes):

  A  today: bank 50% at +1R, stop to +0.1R, runner rules after that
  B  bank 50% at +0.5R, stop to break-even (the 1R partial is then skipped)
  C  stop to break-even once the trade has been +0.5R (no partial)
  D  once +0.5R was reached, exit if the trade gives back half of its best open profit
  E  bank 50% at a fixed 100 pips (gold 10.0 points, NDQ/US30 100 points), stop to break-even

Reported: avg R per variant, the paired difference to A per entry with a 95% day-block bootstrap range, by
instrument and by half of the period, what each costs on big runners (A ≥ +2R), and how often today's rules turn a
+0.5R trade into a loss. A variant is worth switching to only if it beats A by more than noise in both halves.
"""
from __future__ import annotations

import argparse
import copy
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .research import history_dir, run_job_frame, vkey
from .simple_rules import PIP

VARIANTS = {
    "A": {},
    "B": {"early_partial_r": 0.5, "early_lock_r": 0.0},
    "C": {"early_be_r": 0.5, "early_lock_r": 0.0},
    "D": {"giveback_after_r": 0.5, "giveback_frac": 0.5},
    "E": {"early_partial_pts": None, "early_lock_r": 0.0},     # points filled per instrument (100 pips)
}
LABEL = {"A": "today (50% at +1R)", "B": "50% at +0.5R, stop to BE", "C": "stop to BE at +0.5R",
         "D": "give back half after +0.5R → out", "E": "50% at 100 pips, stop to BE"}
# trade-analyst check (Oct 19 2026, frozen before running): would a live analyst that exits when the trade's
# situation turns against it have helped? Same entries, today's rules plus one analyst exit each.
ANALYST = {
    "A": {},
    "F": {"an_flip": True},
    "G": {"an_break": True},
    "H": {"an_stall_min": 60.0, "an_stall_max_r": 0.5},
    "X": {"an_flip": True, "an_break": True, "an_stall_min": 60.0, "an_stall_max_r": 0.5},
}
ANALYST_LABEL = {"A": "today (no analyst)", "F": "out when the 15m trend flips (close crosses EMA50 against)",
                 "G": "out when 5m structure breaks (close beyond the last swing low/high)",
                 "H": "out after 60 min without a new best while under +0.5R", "X": "all three analyst exits"}
SETS = {"exit": (VARIANTS, LABEL, "Exit study — protection before the first target"),
        "analyst": (ANALYST, ANALYST_LABEL, "Analyst check — would a live trade analyst's exits have helped?")}


def cell_jobs(cfg, cells: list[dict], variants: dict | None = None) -> list[tuple]:
    variants = VARIANTS if variants is None else variants
    jobs = []
    for c in cells:
        cc = copy.deepcopy(cfg)
        r = cc.setdefault("research", {})
        r["only_params"] = {c["setup"]: c.get("params") or {}}
        vs = copy.deepcopy(variants)
        if "E" in vs:
            vs["E"]["early_partial_pts"] = 100 * PIP.get(c["sym"], 1.0)
        r["exit_study"] = vs
        jobs.append((cc, c["sym"], c["tf"], [c["setup"]]))
    return jobs


def boot_diff(d: pd.DataFrame, seed: int = 5, B: int = 3000, blk: int = 5) -> tuple[float, float]:
    """95% range of the mean per-entry difference, resampling 5-day blocks of trading days."""
    g = d.groupby("day").diff_r.agg(["sum", "count"])
    s, k = g["sum"].to_numpy(), g["count"].to_numpy()
    n = len(s)
    if n < 5:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (B, -(-n // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :n] % n
    m = s[ix].sum(1) / np.maximum(k[ix].sum(1), 1)
    lo, hi = np.quantile(m, [0.025, 0.975])
    return float(lo), float(hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--set", choices=sorted(SETS), default="exit")
    a = ap.parse_args()
    variants, label, title = SETS[a.set]
    a.out = a.out or Path("data/year_test/exit_study" if a.set == "exit" else "data/year_test/analyst_check")
    cfg = load_config("config.yaml")
    pb = json.loads(Path("data/playbook.json").read_text())
    cells = [c for c in pb["cells"] if c["sym"] in cfg["instruments"]]
    long_hist = Path(history_dir(cfg)).parent / f"history_{a.days}d"
    if long_hist.exists():
        cfg["history_dir"] = str(long_hist)
    a.out.mkdir(parents=True, exist_ok=True)
    cfg["research_dir"] = str(a.out / "research")
    print(f"{len(cells)} playbook cells (as of {pb.get('asof')}), history {cfg.get('history_dir', 'data/history')}", flush=True)
    parts = []
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=multiprocessing.get_context("spawn"),
                             max_tasks_per_child=1) as ex:
        for c, part in zip(cells, ex.map(run_job_frame, cell_jobs(cfg, cells, variants))):
            if not len(part):
                continue
            part = part[(part.tf == c["tf"]) & (part.variant == vkey(c.get("params") or {}))
                        & part.mgmt.str.startswith(c["mgmt"] + "|")]
            part = part.assign(cell=c["id"], var=part.mgmt.str.split("|").str[1])
            parts.append(part)
            print(f"  {c['id']}: {len(part) // len(variants)} entries", flush=True)
    T = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not len(T):
        raise SystemExit("no trades — is the history cache there?")
    T.to_pickle(a.out / "trades.pkl")
    key = ["cell", "ts", "side"]
    A = T[T["var"] == "A"].set_index(key)
    span = f"{pd.Timestamp(T.ts.min()):%Y-%m-%d} → {pd.Timestamp(T.ts.max()):%Y-%m-%d}"
    mid = pd.Timestamp(T.ts.min()) + (pd.Timestamp(T.ts.max()) - pd.Timestamp(T.ts.min())) / 2
    gave = A[(A.mfe >= 0.5) & (A.r <= 0)]
    md = [f"# {title}", "",
          f"{len(cells)} cells of the current playbook (as of {pb.get('asof')}), {span}, every candidate entry of each "
          "cell replayed on 1-minute bars with real spread under each exit rule. Same entries for every variant — only "
          "the exit changes, so the differences are paired. R per trade after spread.", "",
          f"**Today's rules turn a good start into a loss on {len(gave)} of {len(A)} entries "
          f"({len(gave) / len(A):.0%})**: they reached +0.5R or more and still closed at or below zero "
          f"(avg {gave.r.mean():+.2f}R on those). Entries reaching +0.5R at all: {(A.mfe >= 0.5).mean():.0%}; "
          f"reaching +1R: {(A.mfe >= 1).mean():.0%}.", "",
          "| Variant | Rule | Entries | Win | Avg R | vs today (per entry) | 95% range of the difference | 1st half | 2nd half | Big runners (today ≥ +2R) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for v in variants:
        X = T[T["var"] == v].set_index(key)
        J = X[["r"]].join(A[["r", "day"]], rsuffix="_a", how="inner")
        J["diff_r"] = J.r - J.r_a
        lo, hi = boot_diff(J.reset_index())
        ts = J.index.get_level_values("ts")
        h1, h2 = J[ts < mid].diff_r.mean(), J[ts >= mid].diff_r.mean()
        big = J[J.r_a >= 2]
        rows.append({"var": v, "n": len(X), "win": float((X.r > 0).mean()), "avg_r": float(X.r.mean()),
                     "diff": float(J.diff_r.mean()), "lo": lo, "hi": hi, "h1": float(h1), "h2": float(h2),
                     "big_n": len(big), "big_diff": float(big.diff_r.mean()) if len(big) else float("nan")})
        r = rows[-1]
        md.append(f"| **{v}** | {label[v]} | {r['n']} | {r['win']:.0%} | {r['avg_r']:+.3f} | "
                  + ("— |  — | — | — | — |" if v == "A" else
                     f"{r['diff']:+.3f} | {r['lo']:+.3f} to {r['hi']:+.3f} | {r['h1']:+.3f} | {r['h2']:+.3f} | "
                     f"{r['big_diff']:+.2f}R on {r['big_n']} |"))
    md += ["", "## By instrument (avg R per entry)", "",
           "| Instrument | Entries | " + " | ".join(f"{v}" for v in variants) + " |", "|---|---|" + "---|" * len(variants)]
    for sym, g in T.groupby("sym"):
        n = int((g["var"] == "A").sum())
        md.append(f"| {sym} | {n} | " + " | ".join(f"{g[g['var'] == v].r.mean():+.3f}" for v in variants) + " |")
    md += ["", "## By cell (avg R per entry)", "", "| Cell | Entries | " + " | ".join(variants) + " |",
           "|---|---|" + "---|" * len(variants)]
    for cell, g in T.groupby("cell"):
        md.append(f"| {cell} | {int((g['var'] == 'A').sum())} | "
                  + " | ".join(f"{g[g['var'] == v].r.mean():+.3f}" for v in variants) + " |")
    best = max((r for r in rows if r["var"] != "A"), key=lambda r: r["diff"])
    verdict = (f"**{best['var']} ({label[best['var']]}) beats today by {best['diff']:+.3f}R per entry, above noise and in "
               "both halves — worth switching to (after a forward check).**"
               if best["lo"] > 0 and best["h1"] > 0 and best["h2"] > 0 else
               f"**No variant beats today's rules by more than noise in both halves** (best: {best['var']}, "
               f"{best['diff']:+.3f}R per entry, 95% {best['lo']:+.3f} to {best['hi']:+.3f}).")
    md[6:6] = [verdict, ""]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"rows": rows, "cells": [c["id"] for c in cells]}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
