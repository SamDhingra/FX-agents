"""Does the chop/trend routing rule help? Checked on a year test's research trades, before anyone trusts it.

    python -m fxagents.regime_check --run 365d_p2 --days 365 --out data/year_test/regime_365d_p2

For every research trade (all setups × variants × instruments × timeframes except 1m, each cell's own
one-at-a-time record) it looks up the Choppiness Index of the last 15m candle completed before the signal
(fxagents/regime.py) and reports average R by exit style × regime, and what the routing rule would keep
and drop. The thresholds are the conventional 61.8 / 38.2, fixed before this check.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .regime import CHOP_HI, CHOP_LO, allowed, chop_asof, classify
from .research import own_trades

BUCKETS = [(0, CHOP_LO, f"trend (≤{CHOP_LO})"), (CHOP_LO, 50, f"{CHOP_LO}–50"), (50, CHOP_HI, f"50–{CHOP_HI}"),
           (CHOP_HI, 101, f"chop (≥{CHOP_HI})")]


def row(g: pd.DataFrame, val: str) -> dict:
    if not len(g):
        return {"n": 0}
    r = g[val].to_numpy()
    return {"n": int(len(r)), "win": float((r > 0).mean()), "avg": float(r.mean()), "total": float(r.sum())}


def fmt(d: dict) -> str:
    return "—" if not d.get("n") else f"{d['n']:,} · {d['win']:.0%} · {d['avg']:+.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="365d_p2", help="year-test folder under data/year_test (holds trades.pkl)")
    ap.add_argument("--days", type=int, default=365, help="history cache data/history_<days>d")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    t = pd.read_pickle(Path("data/year_test") / a.run / "trades.pkl")
    t = own_trades(t)
    t = t[t["tf"] != "1min"]
    val = "rw" if "rw" in t.columns else "r"
    t = t[["sym", "tf", "setup", "mgmt", "ts", "r"] + (["rw"] if val == "rw" else [])].copy()
    hd = Path("data") / f"history_{a.days}d"
    parts = []
    for sym, g in t.groupby("sym"):
        p = hd / f"{sym}.pkl"
        if not p.exists():
            continue
        m1 = pd.read_pickle(p)[0]
        g = g.assign(chop=chop_asof(m1, pd.to_datetime(g["ts"])))
        parts.append(g)
        del m1
    t = pd.concat(parts, ignore_index=True)
    t = t[np.isfinite(t["chop"])]
    t["regime"] = [classify(x) for x in t["chop"]]
    t["mg"] = np.where(t["mgmt"].astype(str).str.startswith("scalp"), "scalp",
                       np.where(t["mgmt"].astype(str).str.startswith("trend"), "trend", "std / tp"))
    t["keep"] = [allowed(rg, m) for rg, m in zip(t["regime"], t["mgmt"])]
    a.out.mkdir(parents=True, exist_ok=True)

    md = [f"# Chop / trend routing check on {a.run}", "",
          f"Every research trade except 1m ({len(t):,} trades, each cell's own record), R as sized by Risk. Regime = "
          f"Choppiness Index (14) of the last completed 15m candle before the signal. Rule fixed beforehand: CHOP ≥ "
          f"{CHOP_HI} → scalps only; CHOP ≤ {CHOP_LO} → no scalps; between → anything.", "",
          "## 1 · What the rule would keep and drop", "",
          "| | Trades · win · avg R | Total R |", "|---|---|---|"]
    k, d, al = row(t[t.keep], val), row(t[~t.keep], val), row(t, val)
    for lab, x in (("All trades", al), ("Kept by the rule", k), ("Dropped by the rule", d)):
        md.append(f"| {lab} | {fmt(x)} | {x.get('total', 0):+,.0f} |")
    verdict = ("the rule helps: the trades it drops are worse than the ones it keeps" if k.get("avg", 0) > d.get("avg", 0)
               else "the rule does not help: the trades it drops are no worse than the ones it keeps")
    md += ["", f"**{verdict}** (avg {k.get('avg', 0):+.3f}R kept vs {d.get('avg', 0):+.3f}R dropped). "
           "A real effect should also show up per instrument in section 3.", "",
           "## 2 · Exit style × regime (trades · win · avg R)", "",
           "| Exit | " + " | ".join(b[2] for b in BUCKETS) + " |", "|---|" + "---|" * len(BUCKETS)]
    for mg in ("scalp", "std / tp", "trend"):
        g = t[t.mg == mg]
        md.append(f"| {mg} | " + " | ".join(fmt(row(g[(g.chop >= lo) & (g.chop < hi)], val)) for lo, hi, _ in BUCKETS) + " |")
    md += ["", "If the idea is right, scalps should do relatively better on the right (chop) and std/trend exits "
           "relatively better on the left (trend).", "",
           "## 3 · Per instrument: avg R kept vs dropped", "",
           "| Instrument | Kept | Dropped |", "|---|---|---|"]
    for sym, g in t.groupby("sym"):
        md.append(f"| {sym} | {fmt(row(g[g.keep], val))} | {fmt(row(g[~g.keep], val))} |")
    share = t["regime"].value_counts(normalize=True)
    md += ["", "Time in each regime (share of trades): " + ", ".join(f"{k} {v:.0%}" for k, v in share.items()) + "."]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"run": a.run, "kept": k, "dropped": d, "all": al}, indent=2))
    print("\n".join(md[:14]))


if __name__ == "__main__":
    main()
