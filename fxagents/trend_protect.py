"""Protection for the playbook's trend-profile trades (registered Nov 4 2026, research/trend_protect/PREREGISTRATION_2026-11-04.md,
before any run). Trend cells (15m+, first target 2R) have no protection before +2R; this replays their trades with
  lock1 (primary)  stop to +0.1R once +1R
  be05             stop to break-even once +0.5R
  half1            bank 50% at +1R, stop to +0.1R
on the playbook's own engine (research.simulate_live, real per-minute spread).

    python -m fxagents.trend_protect [--period seen|vault]     (./fx.sh trendprotect [seen|vault])
    → data/year_test/trend_protect_<period>/report.md
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import m15_timing as T
from . import mtf_whatif as W
from . import whatif_judge as J
from .research import full_exit, mgmt_profiles

SRC = {"vault": (Path("data/year_test/mtf_vault_trades"), Path("data/history_x/old_2016_2020"), "trades_old_"),
       "seen": (Path("data/year_test/playbook_test"), Path("data/history_x/seen_2021_2026"), "trades_seen_")}
OUT = {p: Path(f"data/year_test/trend_protect_{p}") for p in SRC}
RULES = {"lock1": {"early_be_r": 1.0, "early_lock_r": 0.1},
         "be05": {"early_be_r": 0.5, "early_lock_r": 0.0},
         "half1": {"early_partial_r": 1.0, "early_partial_frac": 0.5, "early_lock_r": 0.1}}
PRIMARY = "lock1"
NAMES = {"lock1": "stop to +0.1R at +1R (primary)", "be05": "stop to break-even at +0.5R",
         "half1": "50% off at +1R, stop to +0.1R"}


def tf_rule(tf: str) -> str:
    return f"{int(pd.Timedelta(str(tf)).total_seconds() // 60)}min"


def is_trend(mg) -> bool:
    return str(mg).split("|")[0] == "trend"


def replay(cfg, g: pd.DataFrame, m1: pd.DataFrame, rules: dict) -> pd.DataFrame:
    rows = []
    for tf, gt in g.groupby(g.tf.map(tf_rule)):
        A = T.Arrays(cfg, m1, tf)
        profiles = mgmt_profiles(cfg, tf)
        for r in gt.itertuples(index=False):
            out = {"kid": r.kid}
            loc = A.locate(r.ts)
            mg = str(getattr(r, "mgmt", "std"))
            if loc is None or mg not in profiles or not np.isfinite(r.risk_atr):
                rows.append({**out, "ok": False})
                continue
            i, j0 = loc
            m = profiles[mg]
            side = int(r.side)
            stop = A.C[j0] - side * float(r.risk_atr) * A.atr[i]
            tr = T.Trade(i, j0, side, stop, m, full_exit(cfg, mg), 480.0)
            out["ok"] = True
            for cost, hs in (("1x", A.hs), ("2x", A.hs * 2)):
                b = T.sim(A, tr, j0, stop, m, hs)
                out[f"base_{cost}"] = b["r"] if b else np.nan
                if cost == "1x":
                    out["mfe_rp"] = b.get("mfe", np.nan) if b else np.nan
                for name, ch in rules.items():
                    x = T.sim(A, tr, j0, stop, dataclasses.replace(m, **ch), hs)
                    out[f"{name}_{cost}"] = x["r"] if x else np.nan
            rows.append(out)
    return pd.DataFrame(rows)


def judge(a: pd.DataFrame, name: str, period: str) -> dict:
    d = (a[f"{name}_1x"] - a.base_1x).to_numpy(float)
    d2 = (a[f"{name}_2x"] - a.base_2x).to_numpy(float)
    first = (pd.to_datetime(a.ts) < J.split_of(period)).to_numpy()
    main = T.paired(a, d, period)
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    changed = int((np.abs(d) > 1e-9).sum())
    gates = {"changed ≥ 100": changed >= 100, "95% range above 0": main["lo"] > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2× costs > 0": float(np.mean(d2)) > 0}
    big = a[a.base_1x >= 2]
    return {"n": int(len(a)), "changed": changed, "base": float(a.base_1x.mean()), "rule": float(a[f"{name}_1x"].mean()),
            "win": float((a[f"{name}_1x"] > 0).mean()), "d": main, "halves": halves, "d_2x": float(np.mean(d2)),
            "big_n": int(len(big)), "big_base": float(big.base_1x.mean()) if len(big) else np.nan,
            "big_rule": float(big[f"{name}_1x"].mean()) if len(big) else np.nan, "gates": gates, "pass": all(gates.values())}


def run(period: str, cfg=None, out: Path | None = None, src: dict | None = None) -> dict:
    out = out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    rules = dict(RULES)
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not (seen.get(PRIMARY) or {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if lock1 passed on seen")
        rules = {PRIMARY: RULES[PRIMARY]}
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    s, hist, prefix = (src or SRC)[period]
    t = W.load(s, prefix)
    t = t[t.mgmt.map(is_trend)].reset_index(drop=True) if "mgmt" in t else t.iloc[0:0]
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True).assign(kid=lambda x: np.arange(len(x)))
    if not len(t):
        raise SystemExit("no trend-profile trades in the cohort")
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}: {len(g)} trades unavailable", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(replay(cfg, g, m1, rules))
        print(f"  {period} {sym}: {len(g)} trend trades", flush=True)
    rp = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"kid": [], "ok": []})
    a = t.merge(rp, on="kid", how="left")
    ok = a["ok"].fillna(False).astype(bool) & np.isfinite(a.get("base_1x", pd.Series(np.nan, index=a.index)).astype(float))
    mt = ok & (np.abs(a.get("base_1x", np.nan).astype(float) - a["r"].astype(float)) < T.MATCH_TOL)
    match = float(mt.sum() / max(1, len(t)))
    a = a[mt].reset_index(drop=True)
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades.csv.gz", index=False)
    res = {k: judge(a, k, period) for k in rules} if len(a) else {}
    for k in res:
        res[k]["gates"] = {"engine check ≥ 98%": match >= T.MATCH_MIN, **res[k]["gates"]}
        res[k]["pass"] = all(res[k]["gates"].values())
    md = [f"# Protection for trend-profile playbook trades ({period})", "",
          "Registered Nov 4 2026 before running (research/trend_protect/PREREGISTRATION_2026-11-04.md). Trend cells "
          "(15m+, first target 2R) have no protection before +2R. Each trade replayed on the playbook's own engine with "
          "the real spread; only what happens before the first target changes.", "",
          f"Cohort: {len(t):,} trend-profile trades; engine reproduces {match:.1%} of them ({len(a):,} judged).", ""]
    if len(a):
        gave = a[(a.mfe_rp >= 1) & (a.base_1x <= 0)]
        md += [f"Today: avg {a.base_1x.mean():+.3f}R, {float((a.base_1x > 0).mean()):.0%} win. "
               f"{len(gave):,} trades ({len(gave) / len(a):.0%}) reached +1R and still closed at or below 0 "
               f"(avg {gave.base_1x.mean() if len(gave) else float('nan'):+.2f}R) — the Nov 4 pattern.", "",
               "| rule | verdict | changed | win | avg R | change vs today (95% range) | halves | 2× costs | trades ≥ 2R today: today → rule |",
               "|---|---|---|---|---|---|---|---|---|"]
        for k, j in res.items():
            v = ("**PASS**" if j["pass"] else "**no** (" + ", ".join(g for g, ok in j["gates"].items() if not ok) + ")") \
                if k == PRIMARY else "info"
            md.append(f"| {NAMES[k]} | {v} | {j['changed']:,} of {j['n']:,} | {j['win']:.0%} | {j['rule']:+.3f} | "
                      f"{j['d']['mean']:+.3f} ({j['d']['lo']:+.3f} to {j['d']['hi']:+.3f}) | {j['halves'][0]:+.3f} / "
                      f"{j['halves'][1]:+.3f} | {j['d_2x']:+.3f} | {j['big_n']}: {j['big_base']:+.2f} → {j['big_rule']:+.2f} |")
        md += ["", "### By cell (avg R)", "", "| cell | trades | today | " + " | ".join(rules) + " |",
               "|---|---|---|" + "---|" * len(rules)]
        for cell, g in a.groupby("cell"):
            md.append(f"| {cell} | {len(g)} | {g.base_1x.mean():+.3f} | " + " | ".join(f"{g[f'{k}_1x'].mean():+.3f}" for k in rules) + " |")
        if period == "seen":
            md += ["", ("**lock1 passes → one judgement on 2016–2020: ./fx.sh trendprotect vault**" if res[PRIMARY]["pass"]
                        else "**lock1 does not pass → the vault is not touched; the trend profile stays as it is.**")]
        else:
            md += ["", f"**Verdict on 2016–2020: {'CONFIRMED → +0.1R stop at +1R on the trend profile, paper books first' if res[PRIMARY]['pass'] else 'NOT CONFIRMED → the trend profile stays as it is'}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "match": match}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Protection for trend-profile playbook trades (registered Nov 4 2026)")
    ap.add_argument("--period", choices=tuple(SRC), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
