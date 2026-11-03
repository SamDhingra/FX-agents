"""Wait one M15 candle before entering against a fresh M15 close (registered Nov 2 2026,
research/m15_wait/PREREGISTRATION_2026-11-02.md, before any run). Judged ONCE on 2016–2020; 2021–2026 shown only.

    python -m fxagents.m15_wait            (./fx.sh m15wait) → data/year_test/m15_wait/report.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import m15_timing as T
from . import mtf_whatif as W
from . import whatif_judge as J
from .research import full_exit, mgmt_profiles

OUT = Path("data/year_test/m15_wait")
SRC = {"vault": (Path("data/year_test/mtf_vault_trades"), Path("data/history_x/old_2016_2020"), "trades_old_"),
       "seen": (Path("data/year_test/playbook_test"), Path("data/history_x/seen_2021_2026"), "trades_seen_")}


def replay(cfg, g: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tf, gt in g.groupby(g.tf.map(lambda x: T.LOWTF[str(x)])):
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
            base = mg.split("|")[0]
            mh = 30.0 if base == "scalp" else 480.0 if base == "trend" else A.max_hold_cfg
            side = int(r.side)
            stop = A.C[j0] - side * float(r.risk_atr) * A.atr[i]
            tr = T.Trade(i, j0, side, stop, m, full_exit(cfg, mg), mh)
            q = A.ref15(j0)
            flag = bool(q >= 0 and (A.c15[q] - A.o15[q]) * side < 0)
            out.update(ok=True, flag=flag)
            for cost, hs in (("1x", A.hs), ("2x", A.hs * 2)):
                b = T.sim(A, tr, j0, stop, m, hs)
                out[f"base_{cost}"] = b["r"] if b else np.nan
                if flag:
                    rw, kw, why = T.late_entry(A, tr, hs, forced_k=1)
                    out[f"w_{cost}"] = rw
                    if cost == "1x":
                        out["why"] = why
                else:
                    out[f"w_{cost}"] = out[f"base_{cost}"]
            rows.append(out)
    return pd.DataFrame(rows)


def evaluate(period: str, cfg, src_override: dict | None = None) -> tuple[dict, pd.DataFrame, float]:
    src, hist, prefix = (src_override or SRC)[period]
    t = W.load(src, prefix)
    t = t[t.tf.astype(str).isin(list(T.LOWTF))].reset_index(drop=True)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True).assign(kid=lambda x: np.arange(len(x)))
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(replay(cfg, g, m1))
        print(f"  {period} {sym}: {len(g)} trades", flush=True)
    rp = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"kid": [], "ok": []})
    a = t.merge(rp, on="kid", how="left")
    ok = a["ok"].fillna(False).astype(bool) & np.isfinite(a.get("base_1x", pd.Series(np.nan, index=a.index)).astype(float))
    mt = ok & (np.abs(a.get("base_1x", np.nan).astype(float) - a["r"].astype(float)) < T.MATCH_TOL)
    match = float(mt.sum() / max(1, len(t)))
    a = a[mt].reset_index(drop=True)                    # judged on the trades the engine reproduces (as m15_timing)
    if not len(a):
        return {"n": 0, "flagged": 0, "changed": 0, "base": np.nan, "rule": np.nan, "d": {"mean": np.nan, "lo": np.nan, "hi": np.nan},
                "halves": (np.nan, np.nan), "d_2x": np.nan, "match": match, "why": {}, "gates": {"engine check ≥ 98%": False},
                "pass": False}, a, match
    d = (a.w_1x - a.base_1x).to_numpy(float)
    d2 = (a.w_2x - a.base_2x).to_numpy(float)
    split = J.split_of(period)
    first = (pd.to_datetime(a.ts) < split).to_numpy()
    main = T.paired(a, d, period) if len(a) else {"mean": np.nan, "lo": np.nan, "hi": np.nan}
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    changed = int((np.abs(d) > 1e-9).sum())
    gates = {"engine check ≥ 98%": match >= 0.98, "changed ≥ 100": changed >= 100, "95% range above 0": main["lo"] > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2× costs > 0": float(np.mean(d2)) > 0}
    res = {"n": int(len(a)), "flagged": int(a.flag.sum()), "changed": changed, "base": float(a.base_1x.mean()),
           "rule": float(a.w_1x.mean()), "d": main, "halves": halves, "d_2x": float(np.mean(d2)), "match": match,
           "why": a[a.flag].why.value_counts().to_dict() if "why" in a else {}, "gates": gates, "pass": all(gates.values())}
    return res, a, match


def line(name: str, r: dict, gate: bool) -> str:
    d = r["d"]
    v = ("**PASS**" if r["pass"] else "**no** (" + ", ".join(k for k, ok in r["gates"].items() if not ok) + ")") if gate else "info"
    return (f"| {name} | {v} | {r['changed']:,} of {r['n']:,} | {r['base']:+.3f} | {r['rule']:+.3f} | "
            f"{d['mean']:+.3f} ({d['lo']:+.3f} to {d['hi']:+.3f}) | {r['halves'][0]:+.3f} / {r['halves'][1]:+.3f} | {r['d_2x']:+.3f} |")


def run(out: Path = OUT, cfg=None, src: dict | None = None) -> dict:
    if (out / "summary.json").exists():
        raise SystemExit("registered: m15_wait1 is judged once on 2016–2020 and already has a result")
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    vault, va, _ = evaluate("vault", cfg, src)
    seen, _, _ = evaluate("seen", cfg, src)
    seen["pass"] = False
    out.mkdir(parents=True, exist_ok=True)
    va.to_csv(out / "trades_vault.csv.gz", index=False)
    head = "| period | verdict | trades changed | avg R as recorded | avg R with rule | mean d (95% range) | halves | d at 2× costs |"
    md = ["# Wait one M15 candle before entering against a fresh M15 close", "",
          "Registered Nov 2 2026 before running (research/m15_wait/PREREGISTRATION_2026-11-02.md). Playbook 3m/5m trades "
          "whose last completed M15 candle closed against them wait for the next M15 close and enter there (same stop; "
          "cancelled if the stop is touched first or the session ends). Replayed by the playbook's own engine with the real "
          "bid/ask spread. Judged once on 2016–2020; 2021–2026 (where the idea came from) shown only.", "",
          f"Engine check (plain replay reproduces the recorded R): 2016–2020 {vault['match']:.1%}, 2021–2026 {seen['match']:.1%} "
          "(98% required).", "", head, "|---|---|---|---|---|---|---|---|",
          line("2016–2020 (judged)", vault, True), line("2021–2026 (shown)", seen, False), "",
          "Flagged trades on 2016–2020: " + (", ".join(f"{k} {v}" for k, v in vault["why"].items()) or "none"), "",
          ("**m15_wait1 is CONFIRMED on 2016–2020 → shadow tag on the live playbook; any trading change is for the review.**"
           if vault["pass"] else "**m15_wait1 is not confirmed on 2016–2020 → the 'wait for M15' family is closed.**")]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({"vault": vault, "seen": seen}, indent=1, default=str))
    return {"vault": vault, "seen": seen}


def main():
    run()
    print((OUT / "report.md").read_text())


if __name__ == "__main__":
    main()
