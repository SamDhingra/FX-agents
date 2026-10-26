"""The stricter judge for skip/what-if checks (Oct 26 2026, from ChatGPT's round-3 pre-registration, adopted BEFORE any
result it judges was seen — including the m15_live 2016–2020 confirmation, which was still running).

What it fixes in the earlier liquidity/mtf judge (fxagents/liquidity.judge):
  * halves: a FIXED calendar split (seen: 2023-11-17 00:00 NY; vault: the elapsed midpoint of 2016-01-01 → 2021-01-01),
    not the median trade time;
  * random skipping: the same number of trades skipped at random WITHIN each stratum (cell, side, hour, calendar half),
    so a check can't look useful just by dropping more of a bad setup or a bad hour;
    p = (1 + #random ≥ observed) / (draws + 1);
  * the confidence range: circular moving blocks of 5 consecutive New York weekdays over the whole period (zero-trade
    weekdays included), the same blocks for kept and flagged trades;
  * minimums: ≥ 30 flagged and ≥ 30 kept trades in each half; a missing group fails, it doesn't disappear;
  * coverage: the check must be computable for ≥ 90% of the intended trades, otherwise the result is inconclusive.

Pass = coverage ≥ 90% and kept − flagged 95% range above 0 and kept − flagged > 0 in both halves and stratified random
p < 0.05 (and ≥ 90% of bootstrap draws valid).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
PERIODS = {
    "seen": (pd.Timestamp("2021-01-01", tz=NY), pd.Timestamp("2026-10-01", tz=NY), pd.Timestamp("2023-11-17", tz=NY)),
    "vault": (pd.Timestamp("2016-01-01", tz=NY), pd.Timestamp("2021-01-01", tz=NY), None),
}
DRAWS, SEED_BOOT, SEED_PERM, BLOCK, MIN_N, COVER = 10_000, 20261026, 20261027, 5, 30, 0.90


def split_of(period: str) -> pd.Timestamp:
    a, b, s = PERIODS[period]
    return s if s is not None else a + (b - a) / 2


def _weekday_index(period: str) -> pd.DatetimeIndex:
    a, b, _ = PERIODS[period]
    d = pd.date_range(a.tz_localize(None), b.tz_localize(None), freq="D", inclusive="left")
    return d[d.dayofweek < 5]


def boot_diff(t: pd.DataFrame, flag: np.ndarray, period: str, draws: int = DRAWS, seed: int = SEED_BOOT):
    """Circular 5-weekday block bootstrap of mean(kept) − mean(flagged). Returns (lo, hi, valid share)."""
    wd = _weekday_index(period)
    day = pd.to_datetime(t["day"].astype(str)).to_numpy("datetime64[D]")
    pos = np.searchsorted(wd.to_numpy("datetime64[D]"), day)          # a weekend day joins the next weekday
    pos = np.clip(pos, 0, len(wd) - 1)
    r = t.r.to_numpy(float)
    W = len(wd)
    ks = np.bincount(pos[~flag], r[~flag], W); kc = np.bincount(pos[~flag], minlength=W).astype(float)
    fs = np.bincount(pos[flag], r[flag], W); fc = np.bincount(pos[flag], minlength=W).astype(float)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(W / BLOCK))
    out = []
    for c in range(0, draws, 500):
        n = min(500, draws - c)
        st = rng.integers(0, W, size=(n, nb))
        ix = ((st[:, :, None] + np.arange(BLOCK)) % W).reshape(n, -1)[:, :W]
        a, b = kc[ix].sum(1), fc[ix].sum(1)
        ok = (a > 0) & (b > 0)
        d = np.full(n, np.nan)
        d[ok] = ks[ix][ok].sum(1) / a[ok] - fs[ix][ok].sum(1) / b[ok]
        out.append(d)
    d = np.concatenate(out)
    valid = float(np.isfinite(d).mean())
    if valid < 0.90:
        return float("nan"), float("nan"), valid
    return float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5)), valid


def strata_of(t: pd.DataFrame, period: str) -> np.ndarray:
    half = (pd.to_datetime(t.ts) >= split_of(period)).astype(int).astype(str)
    hour = pd.to_datetime(t.ts).dt.hour.astype(str)
    key = t["cell"].astype(str) + "|" + t["side"].astype(str) + "|" + hour + "|" + half
    return pd.factorize(key)[0]


def perm_p(t: pd.DataFrame, flag: np.ndarray, period: str, draws: int = DRAWS, seed: int = SEED_PERM) -> float:
    """Stratified random skipping: within each stratum skip as many trades as the check did, at random; p = share of
    draws whose kept mean is at least the real one."""
    g = strata_of(t, period)
    r = t.r.to_numpy(float)
    order0 = np.argsort(g, kind="stable")
    gs = g[order0]
    starts = np.r_[0, np.flatnonzero(np.diff(gs)) + 1]
    sizes = np.diff(np.r_[starts, len(gs)])
    k = np.bincount(g, weights=flag.astype(float), minlength=g.max() + 1).astype(int)[gs[starts]]
    rank_cut = np.repeat(k, sizes)                                       # per sorted row: how many to skip in its group
    within = np.arange(len(gs)) - np.repeat(starts, sizes)
    obs = r[~flag].mean()
    n_keep = int((~flag).sum())
    rng = np.random.default_rng(seed)
    hits = 0
    rs = r[order0]
    for c in range(0, draws, 200):
        n = min(200, draws - c)
        u = rng.random((n, len(gs)))
        u += gs[None, :] * 2.0                                           # keep groups apart, random order within
        o = np.argsort(u, axis=1, kind="stable")
        skipped = within < rank_cut                                       # first k of each group (in random order)
        kept_sum = np.where(skipped[None, :], 0.0, rs[o]).sum(1)
        hits += int((kept_sum / n_keep >= obs - 1e-12).sum())
    return (1 + hits) / (draws + 1)


def judge(t: pd.DataFrame, flag_col: str, period: str, intended: int | None = None) -> dict:
    """t: the trades the check could be computed for (flag_col True/False). intended: trades in the cohort before
    dropping the unavailable ones (for coverage)."""
    f = t[flag_col].to_numpy(bool)
    n = len(t)
    cover = n / intended if intended else 1.0
    res = {"check": flag_col, "period": period, "n": n, "coverage": round(cover, 4), "flagged": int(f.sum()),
           "flagged_avg": round(float(t.r[f].mean()), 4) if f.any() else None,
           "kept_avg": round(float(t.r[~f].mean()), 4) if (~f).any() else None, "all_avg": round(float(t.r.mean()), 4)}
    split = split_of(period)
    first = (pd.to_datetime(t.ts) < split).to_numpy()
    halves, counts = [], []
    for part in (first, ~first):
        fk, kk = f & part, ~f & part
        counts.append((int(fk.sum()), int(kk.sum())))
        halves.append(round(float(t.r[kk].mean() - t.r[fk].mean()), 4) if fk.any() and kk.any() else None)
    res.update(halves=halves, half_counts=counts, split=str(split.date()))
    why = []
    if cover < COVER:
        why.append(f"coverage {cover:.0%} < 90% (inconclusive)")
    if any(a < MIN_N or b < MIN_N for a, b in counts):
        why.append("fewer than 30 flagged or kept trades in a half")
    if not f.any() or f.all():
        why.append("no flagged trades" if not f.any() else "every trade flagged")
    if why and ("coverage" in why[0] or len(t) == 0 or not f.any() or f.all()):
        return {**res, "pass": False, "why": "; ".join(why)}
    lo, hi, valid = boot_diff(t, f, period)
    p = perm_p(t, f, period)
    res.update(diff=round(float(t.r[~f].mean() - t.r[f].mean()), 4), diff_ci=[round(lo, 4), round(hi, 4)],
               boot_valid=round(valid, 4), strat_p=round(p, 5))
    ok = (not why) and np.isfinite(lo) and lo > 0 and all(h is not None and h > 0 for h in halves) and p < 0.05
    if not ok and not why:
        why.append("gates not met")
    return {**res, "pass": bool(ok), "why": "; ".join(why)}


def fmt(j: dict) -> str:
    h = " / ".join(f"{x:+.3f}" if x is not None else "—" for x in j["halves"])
    if "diff" not in j:
        return (f"| {j['check']} | {j['flagged']} of {j['n']} ({j['coverage']:.0%} coverage) | {j['flagged_avg']} | "
                f"{j['kept_avg']} | — | {h} | — | **no** ({j['why']}) |")
    lo, hi = j["diff_ci"]
    rng = f"{lo:+.3f} to {hi:+.3f}" if np.isfinite(lo) else "unavailable"
    return (f"| {j['check']} | {j['flagged']} of {j['n']} ({j['coverage']:.0%} coverage) | {j['flagged_avg']:+.3f} | "
            f"{j['kept_avg']:+.3f} | {j['diff']:+.3f} ({rng}) | {h} | {j['strat_p']:.4f} | "
            f"{'**yes**' if j['pass'] else '**no**'}{'' if j['pass'] else ' (' + j['why'] + ')'} |")


HEAD = ("| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | "
        "stratified random p | pass |\n|---|---|---|---|---|---|---|---|")
