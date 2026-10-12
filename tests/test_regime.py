"""Chop/trend regime: the Choppiness Index, the routing rule, no look-ahead, and the playbook_regime book."""
import numpy as np
import pandas as pd

from fxagents import regime as rx


def frame(close):
    c = pd.Series(close, index=pd.date_range("2026-03-02", periods=len(close), freq="15min", tz="UTC"))
    return pd.DataFrame({"high": c + 0.5, "low": c - 0.5, "close": c})


def test_chop_index_separates_trend_from_range():
    trend = rx.chop_index(frame(np.arange(200.0))).iloc[-1]
    rng = rx.chop_index(frame(100 + 3 * np.sin(np.arange(200) * 1.3))).iloc[-1]
    assert trend < rx.CHOP_LO < rx.CHOP_HI < rng
    assert rx.classify(trend) == "trend" and rx.classify(rng) == "chop" and rx.classify(50) == "mixed"


def test_routing_rule():
    assert rx.allowed("chop", "scalp") and not rx.allowed("chop", "std") and not rx.allowed("chop", "trend")
    assert not rx.allowed("trend", "scalp") and rx.allowed("trend", "std") and rx.allowed("trend", "tp2")
    assert all(rx.allowed(r, m) for r in ("mixed", "unknown") for m in ("scalp", "std", "trend"))


def test_chop_asof_uses_only_completed_candles():
    idx = pd.date_range("2026-03-02 00:00", periods=15 * 120, freq="1min", tz="UTC")
    p = 100 + np.cumsum(np.random.default_rng(2).normal(0, 0.1, len(idx)))
    m1 = pd.DataFrame({"high": p + 0.05, "low": p - 0.05, "close": p}, index=idx)
    ts = pd.DatetimeIndex([idx[15 * 60 + 7]])                 # 7 minutes into a candle
    a = rx.chop_asof(m1, ts)
    later = m1.copy()
    later.iloc[15 * 60:15 * 60 + 15, :] *= 1.5                # change the candle still forming at ts
    assert np.allclose(a, rx.chop_asof(later, ts), equal_nan=True)
