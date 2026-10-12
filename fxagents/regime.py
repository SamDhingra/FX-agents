"""Market regime: choppy / consolidating vs trending, from completed 15-minute candles.

Measure: the Choppiness Index (E. W. Dreiss), CHOP(14) on 15m candles = 3.5 hours of price action:
    CHOP = 100 · log10( Σ TR over 14 candles / (highest high − lowest low over 14) ) / log10(14)
Near 100 = price wandered a lot but went nowhere (chop, consolidation); near 0 = it went one way (trend).
The conventional thresholds are used as they are, not fitted to our data:
    CHOP ≥ 61.8 → "chop"     scalps only (quick in and out)
    CHOP ≤ 38.2 → "trend"    longer exits only (no scalps)
    in between  → "mixed"    every exit allowed
Jev is asked the same question on live signals (jev.JevScorer.market_regime); when it answers with
confidence it decides, otherwise the measured CHOP decides.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TF = "15min"
N = 14
CHOP_HI = 61.8
CHOP_LO = 38.2


def chop_index(df: pd.DataFrame, n: int = N) -> pd.Series:
    """CHOP(n) on a frame with high/low/close columns (any timeframe), aligned to its index."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    rng = h.rolling(n).max() - l.rolling(n).min()
    x = 100 * np.log10(tr.rolling(n).sum() / rng.replace(0, np.nan)) / np.log10(n)
    return x.clip(0, 100)


def classify(chop: float, hi: float = CHOP_HI, lo: float = CHOP_LO) -> str:
    if chop is None or not np.isfinite(chop):
        return "unknown"
    return "chop" if chop >= hi else "trend" if chop <= lo else "mixed"


def allowed(regime: str, mgmt: str) -> bool:
    """The routing rule: chop → scalp exits only; trend → no scalps; mixed/unknown → anything."""
    scalp = str(mgmt).startswith("scalp")
    if regime == "chop":
        return scalp
    if regime == "trend":
        return not scalp
    return True


def resample15(m1: pd.DataFrame) -> pd.DataFrame:
    """15m candles from 1m bars, indexed by candle START (the bar store's convention)."""
    r = m1.resample(TF, label="left", closed="left")
    return pd.DataFrame({"high": r["high"].max(), "low": r["low"].min(), "close": r["close"].last()}).dropna()


def chop_asof(m1: pd.DataFrame, ts: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """CHOP of the last 15m candle COMPLETED at or before each timestamp (no look-ahead)."""
    b = resample15(m1)
    ch = chop_index(b)
    done = (b.index + pd.Timedelta(TF)).as_unit("ns").asi8      # candle close times
    t = pd.DatetimeIndex(ts).tz_convert(b.index.tz).as_unit("ns").asi8
    k = np.searchsorted(done, t, side="right") - 1
    out = np.full(len(t), np.nan)
    ok = k >= 0
    out[ok] = ch.to_numpy()[k[ok]]
    return out
