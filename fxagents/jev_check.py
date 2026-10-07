"""Does Jev's grade predict how a trade turns out — and would a different gate have done better?

    ./fx.sh jevcheck            # reads every book's journal on the server, report published to GitHub

For every closed trade that carries a Jev grade (real book and each shadow book):
  • results by Jev quality and by Jev confidence bucket (trades, win rate, average R, total R)
  • the rank correlation between the grade and the result, and top-half vs bottom-half average R
  • "what if": the trades a stricter gate (quality ≥ x, confidence ≥ y) would have kept, and their result
In advisory mode Jev never blocks, so trades of every grade were taken — exactly what this needs. A grade
that predicts nothing shows flat buckets and a correlation near zero; then a higher gate only cuts trades.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config

Q_EDGES = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.01]


def load_trades(path: str) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    t = pd.read_sql("SELECT symbol, strategy, opened, r_multiple, realized, jev_quality, jev_confidence, jev_source, "
                    "bias_mode FROM trades WHERE status='closed' AND r_multiple IS NOT NULL", db)
    return t.dropna(subset=["jev_quality"])


def _row(g: pd.DataFrame) -> str:
    r = g["r_multiple"]
    return f"{len(g)} | {(r > 0).mean():.0%} | {r.mean():+.3f} | {r.sum():+.1f}"


def section(name: str, t: pd.DataFrame) -> list[str]:
    L = [f"## {name}\n"]
    if len(t) < 5:
        return L + [f"{len(t)} graded closed trades — not enough to say anything yet.\n"]
    r = t["r_multiple"]
    L.append(f"{len(t)} closed trades with a Jev grade · {(r > 0).mean():.0%} win · avg {r.mean():+.3f}R · total {r.sum():+.1f}R · "
             f"sources: " + ", ".join(f"{k} {v}" for k, v in t["jev_source"].fillna("?").value_counts().items()) + "\n")
    for col, label in (("jev_quality", "quality"), ("jev_confidence", "confidence")):
        x = t.dropna(subset=[col])
        if not len(x):
            continue
        rho = x[col].rank().corr(x["r_multiple"].rank())
        med = x[col].median()
        hi, lo = x[x[col] > med], x[x[col] <= med]
        L.append(f"**By {label}** — rank correlation with the result: {rho:+.2f} "
                 f"(top half {hi['r_multiple'].mean():+.3f}R over {len(hi)}, bottom half {lo['r_multiple'].mean():+.3f}R over {len(lo)})\n")
        L.append(f"| {label} | trades | win | avg R | total R |")
        L.append("|---|---|---|---|---|")
        for k, g in x.groupby(pd.cut(x[col], Q_EDGES, right=False), observed=True):
            L.append(f"| {k.left:.1f}–{min(k.right, 1.0):.1f} | {_row(g)} |")
        L.append("")
    L.append("**What if the gate had been stricter** (keep only trades at or above both thresholds)\n")
    L.append("| quality ≥ | confidence ≥ | trades kept | win | avg R | total R |")
    L.append("|---|---|---|---|---|---|")
    for qmin in (0.0, 0.3, 0.4, 0.5, 0.6, 0.7):
        for cmin in (0.0, 0.4, 0.5, 0.6):
            k = t[(t["jev_quality"] >= qmin) & (t["jev_confidence"].fillna(0) >= cmin)]
            if len(k):
                L.append(f"| {qmin:.1f} | {cmin:.1f} | {_row(k)} |")
    L.append("")
    if t["symbol"].nunique() > 1:
        L.append("**By instrument** (quality top half vs bottom half, avg R)\n")
        for sym, g in t.groupby("symbol"):
            if len(g) >= 6:
                m = g["jev_quality"].median()
                L.append(f"- {sym}: {len(g)} trades · top {g[g.jev_quality > m].r_multiple.mean():+.3f}R · "
                         f"bottom {g[g.jev_quality <= m].r_multiple.mean():+.3f}R")
        L.append("")
    return L


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="folder for report.md (default data/year_test/jev_check)")
    a = ap.parse_args()
    cfg = load_config()
    from .agents.setup_first import shadow_db_for, shadow_modes
    books = [("Real book (" + cfg["selector"].get("mode", "hourly_pick") + ")", cfg["storage"]["db_path"])]
    books += [(f"Shadow book ({m})", shadow_db_for(cfg, m, i == 0)) for i, m in enumerate(shadow_modes(cfg))]
    jc = cfg["jev"]
    L = ["# Jev grade vs trade results\n",
         f"Gate now: {jc.get('signal_gate', 'enforce')} · min quality {jc.get('min_signal_quality')} · "
         f"min confidence {jc.get('min_signal_confidence')} · advisory floor {jc.get('advisory_floor')}\n",
         "R per trade in units of its own risk. Buckets with a handful of trades are noise.\n"]
    allt = []
    for name, path in books:
        t = load_trades(path)
        L += section(name, t)
        allt.append(t)
    both = pd.concat([x for x in allt if len(x)], ignore_index=True) if any(len(x) for x in allt) else pd.DataFrame()
    if len(both) and len(allt) > 1:
        L += section("All books together", both)
    txt = "\n".join(L)
    out = Path(a.out) if a.out else Path(cfg["storage"]["db_path"]).parent / "year_test" / "jev_check"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(txt)
    (out / "status.json").write_text(json.dumps({"stage": "done", "trades": int(len(both)),
                                                 "at": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds")}))
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
