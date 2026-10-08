"""Multi-timeframe bias: Daily + 4H + 1H market structure, premium/discount of the prior day's
range, and the liquidity pools ICT/SMC traders watch (PDH/PDL, Asia high/low).

Everything is causal: an HTF bar only counts once it has closed, and a swing only counts once it
is confirmed. The same `bias_frame()` powers the live hard rule and the backtests, so the rule the
Strategist evaluates is the rule the Risk agent enforces.

Structure state per timeframe:  +1 after a close above the last confirmed swing high (BOS/CHoCH up)
                                 −1 after a close below the last confirmed swing low
Composite score = Σ weight × state  ∈ [−1, 1]   (default D 0.40, 4H 0.35, 1H 0.25)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


DEFAULT_WEIGHTS = {"d": 0.40, "h4": 0.35, "h1": 0.25}


def _localize(naive: pd.DatetimeIndex, tz) -> pd.DatetimeIndex:
    """Wall-clock → tz-aware. An ambiguous fall-back label is its first (DST) occurrence; a label inside
    the spring-forward gap moves to the first real instant after it."""
    if tz is None:
        return naive
    return naive.tz_localize(tz, ambiguous=np.ones(len(naive), bool), nonexistent="shift_forward")


def wall_ohlc(df: pd.DataFrame, rule: str, offset: str | None = None) -> pd.DataFrame:
    """OHLC bars on a fixed NEW YORK WALL-CLOCK grid (audit F13): daily = 17:00 → 17:00 and 4H =
    17/21/01/05/09/13 on both sides of a DST switch. Resampling a tz-aware index in fixed 24h/4h steps
    is elapsed-time and drifts to 16:00/18:00 for half the year. Bins are built on the naive wall
    clock, then re-localised; column `end` is each bar's real close instant (23h/25h on switch days)."""
    tz = df.index.tz
    wall = df.set_axis(df.index.tz_localize(None) if tz is not None else df.index)
    kw = {"offset": offset} if offset else {}
    out = wall.resample(rule, label="left", closed="left", **kw).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    end = _localize(out.index + pd.Timedelta(rule), tz)
    out.index = _localize(out.index, tz)
    out["end"] = end
    return out


def structure_state(htf: pd.DataFrame, swing: int) -> pd.DataFrame:
    """Per completed HTF bar: structure state and the swing levels that would invalidate it.

    Swing levels come from structure.swing_levels (raw fractals, applied in the order they are
    confirmed), so the state at bar i is exactly what was knowable at bar i. The older version reduced
    the whole history first, which let a later swing erase an earlier one before it was confirmed."""
    from .structure import pivots_arr, swing_levels
    H, L = htf["high"].to_numpy(dtype=float), htf["low"].to_numpy(dtype=float)
    C = htf["close"].to_numpy(dtype=float)
    lv = swing_levels(pivots_arr(H, L, swing, swing, reduce=False), len(C))
    st = np.zeros(len(C))
    cur = 0
    for i in range(len(C)):
        h, l = lv["hi"][i], lv["lo"][i]
        if not np.isnan(h) and C[i] > h: cur = 1
        if not np.isnan(l) and C[i] < l: cur = -1
        st[i] = cur
    return pd.DataFrame({"state": st, "swing_hi": lv["hi"], "swing_lo": lv["lo"]}, index=htf.index)


def _known(frame: pd.DataFrame, ends) -> pd.DataFrame:
    """Re-index an HTF frame by the time each bar becomes known (its close): `ends` is either a fixed
    period or the per-bar close instants (wall_ohlc's `end`, which handles 23h/25h DST days)."""
    out = frame.copy()
    out.index = out.index + ends if isinstance(ends, pd.Timedelta) else pd.DatetimeIndex(ends)
    return out


def _align(frame: pd.DataFrame, when: pd.DatetimeIndex) -> pd.DataFrame:
    u = frame.index.union(when)
    return frame.reindex(u).ffill().reindex(when)


def bias_frame(h1: pd.DataFrame, when: pd.DatetimeIndex, close_at_when: np.ndarray | None = None,
               weights: dict | None = None) -> pd.DataFrame:
    """Bias at each timestamp in `when` (decision times), using only information known by then.
    h1 = hourly OHLC with a long history (≥ 20 trading days recommended)."""
    w = weights or DEFAULT_WEIGHTS
    d = wall_ohlc(h1, "24h", offset="17h")        # CME trading day: 17:00 → 17:00 NY wall clock
    h4 = wall_ohlc(h1, "4h", offset="1h")         # 17:00, 21:00, 01:00 … aligned to the 17:00 roll
    parts = {}
    for key, frame, swing, per in (("d", d, 1, d["end"]), ("h4", h4, 2, h4["end"]),
                                   ("h1", h1[["open", "high", "low", "close"]], 2, pd.Timedelta("1h"))):
        s = structure_state(frame, swing)
        parts[key] = _align(_known(s, per), when)
    out = pd.DataFrame(index=when)
    for k, p in parts.items():
        out[k] = p["state"].fillna(0).to_numpy()
    out["score"] = sum(w[k] * out[k] for k in w)
    out["h4_swing_hi"] = parts["h4"]["swing_hi"].to_numpy()
    out["h4_swing_lo"] = parts["h4"]["swing_lo"].to_numpy()
    # prior day range + premium/discount
    dk = _align(_known(d[["high", "low"]].rename(columns={"high": "pdh", "low": "pdl"}), d["end"]), when)
    out["pdh"], out["pdl"] = dk["pdh"].to_numpy(), dk["pdl"].to_numpy()
    # Asia range 20:00–00:00 NY, known from midnight until the next day's 17:00 roll
    asia = h1[(h1.index.hour >= 20)]
    if len(asia):
        a = asia.groupby(asia.index.normalize()).agg(asia_hi=("high", "max"), asia_lo=("low", "min"))
        a.index = a.index + pd.DateOffset(days=1)   # known at 00:00 (wall clock) the next calendar day
        ak = _align(a, when)
        out["asia_hi"], out["asia_lo"] = ak["asia_hi"].to_numpy(), ak["asia_lo"].to_numpy()
    else:
        out["asia_hi"] = out["asia_lo"] = np.nan
    if close_at_when is not None:
        rng = (out["pdh"] - out["pdl"]).replace(0, np.nan)
        out["pd_pos"] = ((close_at_when - out["pdl"]) / rng).clip(-0.5, 1.5)
    return out


def rule_check(side: int, score: float, min_align: float) -> str:
    """'aligned' | 'neutral' | 'counter'"""
    if score * side >= min_align:
        return "aligned"
    if abs(score) < min_align:
        return "neutral"
    return "counter"


def label(score: float, min_align: float) -> str:
    if score >= min_align: return "BULLISH"
    if score <= -min_align: return "BEARISH"
    return "NEUTRAL"
