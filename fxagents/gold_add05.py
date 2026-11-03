"""Gold breakout add-on-resume armed at +0.5R (registered Nov 3 2026, research/gold_add05/PREREGISTRATION_2026-11-03.md):
judged ONCE on 2016–2020. Rule = gold_more.add_on(arm_r=0.5, stop_kind="ext").

    python -m fxagents.gold_add05      (./fx.sh goldadd05) → data/year_test/gold_add05_vault/report.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import gold_more as GM
from . import gold_trail as GT
from .simple_rules import load

OUT = Path("data/year_test/gold_add05_vault")


def run(out: Path = OUT, m1: pd.DataFrame | None = None) -> dict:
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    sets, a0, b0, split = GT.PERIODS["vault"]
    if m1 is None:
        parts = [load(Path("data/export") / s / "XAUUSD_M1.csv.gz") for s in sets
                 if (Path("data/export") / s / "XAUUSD_M1.csv.gz").exists()]
        if not parts:
            raise SystemExit(f"no XAUUSD bid/ask export in {sets}")
        m1 = pd.concat(parts).sort_index()
        m1 = m1[~m1.index.duplicated()]
    m1 = m1[(m1.index >= pd.Timestamp(a0, tz="UTC")) & (m1.index < pd.Timestamp(b0, tz="UTC"))]
    a, b = GT.arrays(m1), GM.bars15(m1)
    rows = []
    for j, side, entry, stop, risk, spread, t1, rh, rl in GT.entries(a):
        _, px, _ = GT.walk(a, j, t1, side, entry, stop, risk, "base")
        x = GM.add_on(a, b, j, t1, side, entry, stop, risk, 0.5, "ext")
        rows.append({"entry_time": a["idx"][j], "side": side, "R_base": side * (px - entry) / risk,
                     "has_add05": x is not None, "add_add05": x["R"] if x else 0.0,
                     "sp_add05": x["spread"] if x else 0.0, "dist_add05": x["dist"] if x else 1.0})
    t = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / "trades.csv.gz", index=False)
    j = GM.judge_add(t, "add05", split)
    per_day = float(t.add_add05.sum() / len(t)) if len(t) else float("nan")
    v = "CONFIRMED → paper book gold_breakout_add beside gold_breakout" if j["pass"] else \
        "NOT CONFIRMED → adding on the resumption is closed for this book"
    md = [f"# Gold breakout: add when a pullback resumes, armed at +0.5R (vault {a0} → {b0}, judged once)", "",
          "Registered Nov 3 2026 before this run (research/gold_add05/PREREGISTRATION_2026-11-03.md).", "",
          f"The book on these years: {len(t)} days, avg {t.R_base.mean():+.3f}R.", "",
          "| adds | add wins | avg per add (day R) | 95% range | halves | 2× costs | per day, all days |", "|---|---|---|---|---|---|---|",
          f"| {j['n']} | {j['win']:.0%} | {j['d']:+.3f} | {j['lo']:+.3f} to {j['hi']:+.3f} | "
          f"{j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['d_2x']:+.3f} | {per_day:+.3f} |", "",
          "Gates: " + ", ".join(f"{k} {'✓' if ok else '✗'}" for k, ok in j["gates"].items()), "",
          "For reference, 2021–Sep 2026 (where the idea came from): 406 adds, +0.051 per add, −0.023 to +0.126.", "",
          f"**Verdict: {v}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({"add05": j, "per_day": per_day}, indent=1, default=str))
    return j


def main(argv=None):
    run()
    print((OUT / "report.md").read_text())


if __name__ == "__main__":
    main()
