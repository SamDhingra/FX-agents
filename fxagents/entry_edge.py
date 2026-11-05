"""Do the playbook's entries beat random timing? (registered Nov 5 2026, research/entry_edge/PREREGISTRATION_2026-11-05.md,
before any run). Each recorded playbook trade is replayed on the playbook's own engine, then against
  rand_time (primary)  same day, same timeframe, same side, same stop in ATR, same exit, random entry candle (5 draws)
  opposite             same moment, the other side
    python -m fxagents.entry_edge [--period seen|vault]      (./fx.sh entryedge [seen|vault])
    → data/year_test/entry_edge_<period>/report.md
"""
from __future__ import annotations

import argparse
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
OUT = {p: Path(f"data/year_test/entry_edge_{p}") for p in SRC}
DRAWS, SEED = 5, 20261105
PRIMARY = "rand_time"


def tf_rule(tf: str) -> str:
    return f"{int(pd.Timedelta(str(tf)).total_seconds() // 60)}min"


def max_hold(A, mg: str) -> float:
    base = mg.split("|")[0]
    return 30.0 if base == "scalp" else 480.0 if base == "trend" else A.max_hold_cfg


def day_bars(A) -> dict:
    """Trading day (17:00 NY roll, as research.run_job) → indices of tf candles whose close minute allows an entry."""
    days = (A.close_ts + pd.Timedelta(hours=7)).normalize().date
    j = A.j_of
    ok = (j >= 0) & A.entry_ok[np.clip(j, 0, len(A.entry_ok) - 1)] & np.isfinite(A.atr) & (A.atr > 0)
    out: dict = {}
    for i in np.nonzero(ok)[0]:
        out.setdefault(str(days[i]), []).append(int(i))
    return out


def replay(cfg, g: pd.DataFrame, m1: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for tf, gt in g.groupby(g.tf.map(tf_rule)):
        A = T.Arrays(cfg, m1, tf)
        profiles = mgmt_profiles(cfg, tf)
        pool = day_bars(A)
        for r in gt.itertuples(index=False):
            out = {"kid": r.kid}
            loc = A.locate(r.ts)
            mg = str(getattr(r, "mgmt", "std"))
            if loc is None or mg not in profiles or not np.isfinite(r.risk_atr):
                rows.append({**out, "ok": False})
                continue
            i, j0 = loc
            m, fx, mh, side, ra = profiles[mg], full_exit(cfg, mg), max_hold(A, mg), int(r.side), float(r.risk_atr)
            cands = [k for k in pool.get(str(r.day), []) if k != i]
            picks = [int(x) for x in rng.choice(cands, size=DRAWS, replace=len(cands) < DRAWS)] if cands else []
            out["ok"], out["n_cands"] = True, len(cands)
            for cost, hs in (("1x", A.hs), ("2x", A.hs * 2)):
                stop = A.C[j0] - side * ra * A.atr[i]
                b = T.sim(A, T.Trade(i, j0, side, stop, m, fx, mh), j0, stop, m, hs)
                out[f"base_{cost}"] = b["r"] if b else np.nan
                ostop = A.C[j0] + side * ra * A.atr[i]
                o = T.sim(A, T.Trade(i, j0, -side, ostop, m, fx, mh), j0, ostop, m, hs)
                out[f"opposite_{cost}"] = o["r"] if o else np.nan
                vals = []
                for k in picks:
                    jk = int(A.j_of[k])
                    sk = A.C[jk] - side * ra * A.atr[k]
                    x = T.sim(A, T.Trade(k, jk, side, sk, m, fx, mh), jk, sk, m, hs)
                    if x:
                        vals.append(x["r"])
                out[f"rand_time_{cost}"] = float(np.mean(vals)) if vals else np.nan
            rows.append(out)
    return pd.DataFrame(rows)


def judge(a: pd.DataFrame, name: str, period: str) -> dict:
    s = a[np.isfinite(a[f"{name}_1x"].astype(float))].reset_index(drop=True)
    if len(s) < 2:
        return {"n": int(len(s)), "pass": False, "gates": {"compared ≥ 100": False}}
    d = (s.base_1x - s[f"{name}_1x"]).to_numpy(float)
    d2 = (s.base_2x - s[f"{name}_2x"]).to_numpy(float)
    first = (pd.to_datetime(s.ts) < J.split_of(period)).to_numpy()
    main = T.paired(s, d, period)
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    gates = {"compared ≥ 100": len(s) >= 100, "95% range above 0": main["lo"] > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2× costs > 0": float(np.mean(d2)) > 0}
    return {"n": int(len(s)), "real": float(s.base_1x.mean()), "control": float(s[f"{name}_1x"].mean()), "d": main,
            "halves": halves, "d_2x": float(np.mean(d2)), "gates": gates, "pass": all(gates.values())}


def by(a: pd.DataFrame, key: str, top: int | None = None) -> list[str]:
    rows = []
    for k, g in a.groupby(key):
        g = g[np.isfinite(g.rand_time_1x.astype(float))]
        if len(g) < 20:
            continue
        rows.append((k, len(g), g.base_1x.mean(), g.rand_time_1x.mean(), g.opposite_1x.mean()))
    rows.sort(key=lambda x: -(x[2] - x[3]))
    if top:
        rows = rows[:top] + (rows[-top:] if len(rows) > 2 * top else rows[top:])
    return [f"| {k} | {n:,} | {r:+.3f} | {c:+.3f} | {r - c:+.3f} | {o:+.3f} |" for k, n, r, c, o in rows]


def run(period: str, cfg=None, out: Path | None = None, src: dict | None = None) -> dict:
    out = out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not (seen.get(PRIMARY) or {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if the entries beat random timing on seen")
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    s, hist, prefix = (src or SRC)[period]
    t = W.load(s, prefix)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True).assign(kid=lambda x: np.arange(len(x)))
    if not len(t):
        raise SystemExit("no playbook trades in the cohort")
    rng = np.random.default_rng(SEED)
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}: {len(g)} trades unavailable", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(replay(cfg, g, m1, rng))
        print(f"  {period} {sym}: {len(g):,} trades", flush=True)
    rp = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"kid": [], "ok": []})
    a = t.merge(rp, on="kid", how="left")
    ok = a["ok"].fillna(False).astype(bool) & np.isfinite(a.get("base_1x", pd.Series(np.nan, index=a.index)).astype(float))
    mt = ok & (np.abs(a.get("base_1x", np.nan).astype(float) - a["r"].astype(float)) < T.MATCH_TOL)
    match = float(mt.sum() / max(1, len(t)))
    a = a[mt].reset_index(drop=True)
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades.csv.gz", index=False)
    res = {k: judge(a, k, period) for k in (PRIMARY, "opposite")} if len(a) else {}
    for k in res:
        res[k]["gates"] = {"engine check ≥ 98%": match >= T.MATCH_MIN, **res[k]["gates"]}
        res[k]["pass"] = all(res[k]["gates"].values())
    md = [f"# Do the playbook's entries beat random timing? ({period})", "",
          "Registered Nov 5 2026 before running (research/entry_edge/PREREGISTRATION_2026-11-05.md). Each playbook trade "
          "replayed on the playbook's own engine with the real spread, against the same trade entered at a random candle "
          f"of the same day ({DRAWS} draws, same side, stop, exit) and against the opposite side at the same moment.", "",
          f"Cohort: {len(t):,} trades; the engine reproduces {match:.1%} ({len(a):,} judged)."]
    if len(a):
        md += ["", "| comparison | verdict | trades | real avg R | control avg R | real − control (95% range) | halves | 2× costs |",
               "|---|---|---|---|---|---|---|---|"]
        for k, label in ((PRIMARY, "vs random timing (primary)"), ("opposite", "vs the opposite side")):
            j = res[k]
            if "d" not in j:
                continue
            v = ("**EDGE**" if j["pass"] else "**no edge** (" + ", ".join(g for g, ok in j["gates"].items() if not ok) + ")") \
                if k == PRIMARY else "info"
            md.append(f"| {label} | {v} | {j['n']:,} | {j['real']:+.3f} | {j['control']:+.3f} | {j['d']['mean']:+.3f} "
                      f"({j['d']['lo']:+.3f} to {j['d']['hi']:+.3f}) | {j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['d_2x']:+.3f} |")
        head = "| {} | trades | real | random timing | real − random | opposite side |\n|---|---|---|---|---|---|"
        md += ["", "### By instrument", "", head.format("instrument")] + by(a, "sym")
        md += ["", "### By timeframe", "", head.format("timeframe")] + by(a, "tf")
        md += ["", "### By exit profile", "", head.format("exit")] + by(a, "mgmt")
        md += ["", "### By setup (best and worst 8 by real − random, at least 20 trades)", "", head.format("setup")] + by(a, "setup", 8)
        if period == "seen":
            md += ["", ("**The entries beat random timing → one judgement on 2016–2020: ./fx.sh entryedge vault**" if res[PRIMARY]["pass"]
                        else "**The entries do not beat random timing: the setups' timing adds nothing over a random entry with "
                             "the same stop and exit. Filters and exits on top cannot make the playbook pay.**")]
        else:
            md += ["", f"**Verdict on 2016–2020: {'CONFIRMED — the entries have a timing edge' if res[PRIMARY]['pass'] else 'NOT CONFIRMED'}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "match": match}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Do the playbook's entries beat random timing? (registered Nov 5 2026)")
    ap.add_argument("--period", choices=tuple(SRC), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
