"""Early exit when the pullback's own floor breaks (registered Nov 9 2026: research/floor_exit/PREREGISTRATION_2026-11-09.md).

ICT OTE and DTFX Zone enter a pullback that has not closed beyond its floor (79% / 85% of the impulse leg). Candidate:
before the first target, at the first completed entry-timeframe candle (started at or after the fill) that closes
beyond that floor while the trade is losing on its executable side, exit at the next minute's open. Baseline: the
unchanged standard profile (today's config). Placebo: the same rule at a permuted floor depth.

    python -m fxagents.floor_exit seen|vault [--workers 2]
"""
from __future__ import annotations

import argparse
import copy
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import whatif_judge as J
from .m15_timing import Arrays, Trade, sim
from .research import full_exit, mgmt_profiles, own_trades, run_job_frame

SETUPS = ("ict_ote", "dtfx_zone")
SYMS = ("XAUUSD", "NDQ", "US30")
TFS = ("5min", "15min")
STAGES = {"seen": (Path("data/history_x/seen_2021_2026"), ["holdout_m1", "dev_m1"], "2023-11-17"),
          "vault": (Path("data/history_x/old_2016_2020"), ["old_m1", "old_m1_idx"], "2018-07-01")}
N_PERM, SEED_PERM, DRAWS, SEED_BOOT = 10_000, 20261109, 10_000, 7
MATCH_TOL, MATCH_MIN, COVER_MIN = 1e-3, 0.98, 0.90
OUT = Path("data/year_test")


def out_dir(stage):
    return OUT / f"floor_exit_{stage}"


# ── the cohort ───────────────────────────────────────────────────────────────
def cohort_cfg(cfg, hist: Path) -> dict:
    c = copy.deepcopy(cfg)
    c["history_dir"] = str(hist)
    r = c.setdefault("research", {})
    r["only_params"] = {s: {} for s in SETUPS}            # default parameters
    r["profiles_only"] = ["std"]                          # the hourly pick's standard profile
    r.pop("ignore_bias_rule", None)                       # the live bias rule stays on
    r.pop("exit_study", None)
    r.pop("exit_profiles", None)
    return c


def cohort(cfg, hist: Path, a: pd.Timestamp, b: pd.Timestamp, workers: int = 2, syms=SYMS, tfs=TFS) -> pd.DataFrame:
    cc = cohort_cfg(cfg, hist)
    jobs = [(cc, s, tf, list(SETUPS)) for s in syms for tf in tfs if (hist / f"{s}.pkl").exists()]
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as ex:
        parts = [p for p in ex.map(run_job_frame, jobs) if len(p)]
    if not parts:
        return pd.DataFrame()
    t = own_trades(pd.concat(parts, ignore_index=True))
    t["ts"] = pd.to_datetime(t["ts"])
    return t[(t.ts >= a) & (t.ts < b)].reset_index(drop=True)


# ── per-trade replay ─────────────────────────────────────────────────────────
def floor_path(A: Arrays, i: int, j0: int, side: int, px_in: float, R: float, j_exit: int, j_t1: int, hs) -> dict:
    """Completed entry-tf candles after the fill and before the baseline exit / first target: their mid close, whether
    the trade was losing on its executable side at that close, and the R of exiting at the next minute's open."""
    j_end = min(j_exit, j_t1) if j_t1 >= 0 else j_exit
    cs, ok, rx, js = [], [], [], []
    k = i + 1
    while k < len(A.j_of):
        j = int(A.j_of[k])
        if j < 0 or j >= j_end or j + 1 >= len(A.O):
            break
        h, h1 = (hs[j], hs[j + 1]) if np.ndim(hs) else (hs, hs)
        cs.append(A.C_tf[k])
        ok.append((A.C[j] - side * h - px_in) * side < 0)
        rx.append((A.O[j + 1] - side * h1 - px_in) * side / R)
        js.append(j)
        k += 1
    return {"cs": np.asarray(cs, float), "ok": np.asarray(ok, bool), "rx": np.asarray(rx, float), "js": js}


def trigger(path: dict, side: int, F: float) -> int:
    """Index of the first qualifying candle for floor F, or -1."""
    if not len(path["cs"]):
        return -1
    hit = (side * (path["cs"] - F) < 0) & path["ok"]
    return int(np.argmax(hit)) if hit.any() else -1


def replay(cfg, t: pd.DataFrame, m1: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows, paths = [], {}
    for tf, g in t.groupby("tf"):
        A = Arrays(cfg, m1, str(tf))
        m = mgmt_profiles(cfg, str(tf))["std"]
        fx = full_exit(cfg, "std")
        mh = A.max_hold_cfg
        for r in g.itertuples():
            out = {"kid": r.kid, "ok": False}
            loc = A.locate(r.ts)
            if loc is None or not np.isfinite(r.risk_atr):
                rows.append(out)
                continue
            i, j0 = loc
            side = int(r.side)
            stop = A.C[j0] - side * float(r.risk_atr) * A.atr[i]
            tr = Trade(i, j0, side, stop, m, fx, mh)
            F = float(r.floor_px) if np.isfinite(r.floor_px) else np.nan
            for cost, hs in (("1x", A.hs), ("2x", A.hs * 2)):
                b = sim(A, tr, j0, stop, m, hs)
                if b is None:
                    break
                px_in, R = b["px_in"], b["R"]
                out[f"base_{cost}"] = b["r"]
                out[f"cand_{cost}"] = b["r"]
                if cost == "1x":
                    out.update(ok=True, base_exit=b["exit_reason"], px_in=px_in, R=R, stop=stop)
                    out["eligible"] = bool(np.isfinite(F) and side * (px_in - F) > 0 and side * (F - stop) > 0)
                    out["depth"] = side * (px_in - F) / R if out["eligible"] else np.nan
                if not out.get("eligible"):
                    continue
                p = floor_path(A, i, j0, side, px_in, R, b["j_exit"], b["j_t1"], hs)
                k = trigger(p, side, F)
                if k >= 0:
                    out[f"cand_{cost}"] = float(p["rx"][k])
                if cost == "1x":
                    out["fired"] = k >= 0
                    paths[r.kid] = {"cs": p["cs"], "ok": p["ok"], "gain": p["rx"] - b["r"], "side": side,
                                    "px_in": px_in, "R": R}
            rows.append(out)
    return pd.DataFrame(rows), paths


# ── statistics ───────────────────────────────────────────────────────────────
def paired(t: pd.DataFrame, d: np.ndarray, period: str, draws: int = DRAWS, seed: int = SEED_BOOT) -> dict:
    """Mean of d per entry, circular 5-weekday blocks over every weekday of the period (no-trade days kept)."""
    wd = J._weekday_index(period)
    day = pd.to_datetime(t["day"].astype(str)).to_numpy("datetime64[D]")
    pos = np.clip(np.searchsorted(wd.to_numpy("datetime64[D]"), day), 0, len(wd) - 1)
    S, N = np.zeros(len(wd)), np.zeros(len(wd))
    np.add.at(S, pos, d)
    np.add.at(N, pos, 1)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(wd) / 5))
    idx = (rng.integers(0, len(wd), size=(draws, nb))[:, :, None] + np.arange(5)).reshape(draws, -1)[:, :len(wd)] % len(wd)
    s, n = S[idx].sum(1), N[idx].sum(1)
    m = s[n > 0] / n[n > 0]
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(d.mean()), "lo": float(lo), "hi": float(hi)}


def placebo(v: pd.DataFrame, paths: dict, n_all: int, n_perm: int = N_PERM, seed: int = SEED_PERM) -> np.ndarray:
    """Mean d over all cohort entries for each permutation of floor depths within strata."""
    e = v[v.eligible.fillna(False).astype(bool)].copy()
    tot = np.zeros(n_perm)
    rng = np.random.default_rng(seed)
    for _, g in e.groupby(["setup", "sym", "side", "tf", "half"]):
        depths = g.depth.to_numpy(float)
        P = np.array([rng.permutation(depths) for _ in range(n_perm)]) if len(g) > 1 else np.tile(depths, (n_perm, 1))
        for c, kid in enumerate(g.kid.to_numpy()):
            p = paths.get(kid)
            if p is None or not len(p["cs"]):
                continue
            Fp = p["px_in"] - p["side"] * P[:, c] * p["R"]
            hit = (p["side"] * (p["cs"][None, :] - Fp[:, None]) < 0) & p["ok"][None, :]
            any_ = hit.any(1)
            first = hit.argmax(1)
            tot += np.where(any_, p["gain"][first], 0.0)
    return tot / max(1, n_all)


def judge(v: pd.DataFrame, period: str, split: pd.Timestamp, perm_means: np.ndarray, coverage: float) -> dict:
    d = (v.cand_1x - v.base_1x).to_numpy(float)
    d2 = (v.cand_2x - v.base_2x).to_numpy(float)
    first = (v.ts < split).to_numpy()
    ch = np.abs(d) > 1e-12
    main = paired(v, d, period)
    p = float((perm_means >= d.mean() - 1e-12).mean()) if len(perm_means) else 1.0
    full_b, full_c = float((v.base_1x <= -1 + 1e-9).mean()), float((v.cand_1x <= -1 + 1e-9).mean())
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    g = {"≥ 90% reconstructable": coverage >= COVER_MIN,
         "≥ 100 changed, ≥ 30 per half": ch.sum() >= 100 and (ch & first).sum() >= 30 and (ch & ~first).sum() >= 30,
         "95% range above 0": main["lo"] > 0, "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves),
         "2× spread > 0": float(d2.mean()) > 0, "beats the placebo (p < 0.05)": p < 0.05,
         "fewer entries at ≤ −1R": full_c < full_b}
    cut = v[ch]
    worst = lambda x: float(np.sort(x)[:max(1, len(x) // 20)].mean())                    # noqa: E731
    dd = lambda x: float((np.maximum.accumulate(np.cumsum(x)) - np.cumsum(x)).max())      # noqa: E731
    vs = v.sort_values("ts")
    return {"n": len(v), "eligible": int(v.eligible.fillna(False).sum()), "changed": int(ch.sum()),
            "changed_halves": [int((ch & first).sum()), int((ch & ~first).sum())],
            "base": float(v.base_1x.mean()), "cand": float(v.cand_1x.mean()), "d": main, "halves": halves,
            "d_2x": float(d2.mean()), "placebo_mean": float(perm_means.mean()) if len(perm_means) else np.nan, "p": p,
            "full_loss_share": [full_b, full_c], "worst5": [worst(v.base_1x.to_numpy()), worst(v.cand_1x.to_numpy())],
            "max_dd": [dd(vs.base_1x.to_numpy()), dd(vs.cand_1x.to_numpy())],
            "saved_on_stops": float((cut.cand_1x - cut.base_1x)[cut.base_exit == "stop"].sum()),
            "lost_on_recoveries": float((cut.cand_1x - cut.base_1x)[cut.base_exit != "stop"].sum()),
            "cut_were_stops": int((cut.base_exit == "stop").sum()), "cut_recovered": int((cut.base_exit != "stop").sum()),
            "gates": g, "pass": all(g.values())}


# ── run a stage ──────────────────────────────────────────────────────────────
def run(stage: str, cfg=None, workers: int = 2, out: Path | None = None, t: pd.DataFrame | None = None,
        m1s: dict | None = None, n_perm: int = N_PERM) -> dict:
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    hist, sets, split = STAGES[stage]
    split = pd.Timestamp(split, tz=J.NY)
    a, b, _ = J.PERIODS[stage]
    if stage == "vault":
        f = out_dir("seen") / "summary.json"
        if not f.exists() or not json.loads(f.read_text()).get("pass"):
            raise SystemExit("registered: the vault is judged only after a seen pass (no seen run, or it failed)")
    out = out or out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
    if t is None:
        if not all((hist / f"{s}.pkl").exists() for s in SYMS):
            from .playbook_test import build_history
            build_history(cfg, sets, set(SYMS), hist)
        t = cohort(cfg, hist, a, b, workers)
        print(f"cohort: {len(t):,} entries", flush=True)
    t = t.reset_index(drop=True).copy()
    t["kid"] = np.arange(len(t))
    t["ts"] = pd.to_datetime(t["ts"])
    parts, paths = [], {}
    for sym, g in t.groupby("sym"):
        m1 = m1s[sym] if m1s is not None else pd.read_pickle(hist / f"{sym}.pkl")[0]
        r, p = replay(cfg, g, m1)
        parts.append(r)
        paths.update(p)
        print(f"  {sym}: replayed", flush=True)
    v = t.merge(pd.concat(parts, ignore_index=True), on="kid", how="left")
    ok = v["ok"].fillna(False).astype(bool) & np.isfinite(v["base_1x"].astype(float))
    match = ok & (np.abs(v["base_1x"].astype(float) - v["r"].astype(float)) < MATCH_TOL)
    share = float(match.sum() / max(1, len(t)))
    has_floor = np.isfinite(v.floor_px.astype(float))
    coverage = float((match & has_floor).sum() / max(1, len(t)))
    v = v[match].reset_index(drop=True)
    for c in ("eligible", "fired"):
        v[c] = v[c].fillna(False).astype(bool) if c in v else False
    v["half"] = np.where(v.ts < split, 1, 2)
    res = {"stage": stage, "cohort": len(t), "engine_match": share, "coverage": coverage}
    if share < MATCH_MIN:
        res["pass"] = False
        res["note"] = "the replay does not reproduce the engine closely enough; nothing is judged"
    else:
        perms = placebo(v, paths, len(v), n_perm)
        res.update(judge(v, stage, split, perms, coverage))
        res["by"] = {f"{k[0]} {k[1]} {k[2]}": [int(len(g)), float(g.base_1x.mean()), float(g.cand_1x.mean()),
                                               int((np.abs(g.cand_1x - g.base_1x) > 1e-12).sum())]
                     for k, g in v.groupby(["setup", "sym", "tf"])}
    v.drop(columns=[c for c in v.columns if c in ("exit_ts",)], errors="ignore").to_csv(out / "trades.csv.gz", index=False)
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "report.md").write_text(report(res))
    return res


def f3(x):
    return "—" if x is None or not np.isfinite(x) else f"{x:+.3f}"


def report(r: dict) -> str:
    md = [f"# Floor exit for ICT OTE / DTFX Zone: {r['stage']}", "",
          "Registered Nov 9 2026 (research/floor_exit/PREREGISTRATION_2026-11-09.md). Before the first target, exit at the "
          "next minute's open when a completed 5m/15m candle closes beyond the setup's own floor (79% / 85% of the leg) "
          "while the trade is losing. Baseline: today's standard profile, same entries. Real bid/ask per minute.", "",
          f"Cohort {r['cohort']:,} entries (default parameters, live bias rule, entry windows, news). Engine check: the "
          f"replay reproduces {r['engine_match']:.1%} (required {MATCH_MIN:.0%}); reconstructable with a floor: "
          f"{r['coverage']:.1%} (required {COVER_MIN:.0%})."]
    if "gates" not in r:
        return "\n".join(md + ["", f"**{r.get('note', 'not judged')}.**"]) + "\n"
    d = r["d"]
    md += ["", "| entries | eligible | changed (halves) | avg R baseline | avg R floor exit | mean d (95% range) | halves | "
           "2× spread | placebo mean d | placebo p | at ≤ −1R: baseline → rule | result |", "|" + "---|" * 12,
           f"| {r['n']:,} | {r['eligible']:,} | {r['changed']:,} ({r['changed_halves'][0]} / {r['changed_halves'][1]}) | "
           f"{f3(r['base'])} | {f3(r['cand'])} | {f3(d['mean'])} ({f3(d['lo'])} to {f3(d['hi'])}) | "
           f"{f3(r['halves'][0])} / {f3(r['halves'][1])} | {f3(r['d_2x'])} | {f3(r['placebo_mean'])} | {r['p']:.3f} | "
           f"{r['full_loss_share'][0]:.1%} → {r['full_loss_share'][1]:.1%} | "
           + ("**PASS**" if r["pass"] else "fail: " + ", ".join(k for k, v in r["gates"].items() if not v)) + " |",
           "", "## Information", "",
           f"- trades cut that would have hit the stop: {r['cut_were_stops']:,}, R saved {r['saved_on_stops']:+.1f}; cut "
           f"that would have recovered: {r['cut_recovered']:,}, R lost {r['lost_on_recoveries']:+.1f}",
           f"- worst 5% of trades: {r['worst5'][0]:+.2f}R → {r['worst5'][1]:+.2f}R · max drawdown {r['max_dd'][0]:.1f}R → "
           f"{r['max_dd'][1]:.1f}R", "",
           "| setup · instrument · tf | entries | baseline R | floor-exit R | changed |", "|---|---|---|---|---|"]
    md += [f"| {k} | {n} | {f3(b)} | {f3(c)} | {ch} |" for k, (n, b, c, ch) in r["by"].items()]
    nxt = {"seen": ("**Passed: the 2016–2020 vault is next (`./fx.sh floorexit vault`), once.**" if r["pass"] else
                    "**Did not pass: per the registration the floor exit is closed; nothing else is tried on these results.**"),
           "vault": ("**Confirmed on 2016–2020: forward paired shadow logging on the practice account comes next.**"
                     if r["pass"] else "**Not confirmed on 2016–2020: closed.**")}[r["stage"]]
    md += ["", nxt, "", "A pass does not make a still-negative setup tradable."]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(STAGES))
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    r = run(a.stage, workers=a.workers)
    print("result:", "PASS" if r.get("pass") else "fail")


if __name__ == "__main__":
    sys.exit(main())
