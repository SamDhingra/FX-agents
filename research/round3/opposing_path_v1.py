"""Round 3, A1. Frozen 2026-10-26. Research flag; no trading or outcome reads."""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
MINUTE = pd.Timedelta(minutes=1)


def _window(trade: dict, m1: pd.DataFrame):
    """Past-only, complete minute data; errors mean UNAVAILABLE, never 'keep'."""
    t = pd.Timestamp(trade["ts"])
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("ts must be timezone-aware")
    t = t.tz_convert(NY)
    if t != t.tz_convert("UTC").floor("min").tz_convert(NY):
        raise ValueError("ts must be a minute boundary")
    side = float(trade["side"])
    if side not in (-1.0, 1.0):
        raise ValueError("side must be +1 or -1")
    if not isinstance(m1.index, pd.DatetimeIndex) or m1.index.tz is None:
        raise ValueError("m1 needs a timezone-aware DatetimeIndex")

    # Last 15m boundary at/before t-30m. UTC flooring avoids DST ambiguity;
    # NY's UTC offsets are whole hours, so its 15m boundaries are identical.
    end = (t - 30 * MINUTE).tz_convert("UTC").floor("15min").tz_convert(NY)
    start = end - 15 * pd.Timedelta(minutes=15)  # 14 TRs + preceding close
    cols = ["open", "high", "low", "close"]
    x = m1.loc[(m1.index >= start) & (m1.index < t), cols].copy()
    x.index = x.index.tz_convert(NY)
    expected = pd.date_range(start, t - MINUTE, freq="min")
    if not x.index.equals(expected):
        raise ValueError("missing, duplicate, unordered or non-minute history")
    a = x.to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError("OHLC must be finite and positive")
    if ((x.high < x[["open", "close", "low"]].max(axis=1)).any()
            or (x.low > x[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("invalid OHLC geometry")

    b = x.loc[x.index < end].resample(
        "15min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    if len(b) != 15 or (b.index + pd.Timedelta(minutes=15) > end).any():
        raise ValueError("incomplete baseline")
    pc = b.close.shift(1)
    tr = pd.concat(
        [b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1
    ).max(axis=1).iloc[1:]
    scale = float(tr.mean())  # exactly 14 TRs; SMA, not Wilder ATR
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("non-positive baseline range")
    return side, x.close.to_numpy(dtype=float), scale


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flag a material, efficient 15-minute move AGAINST the intended side."""
    side, close, scale = _window(trade, m1)
    p = close[-16:]  # prices at t-15m,...,t (minute-ending prices)
    signed_move = side * float(p[-1] - p[0])
    path = float(np.abs(np.diff(p)).sum())
    return bool(
        path > 0.0
        and signed_move <= -0.50 * scale
        and -signed_move >= 0.70 * path
    )
