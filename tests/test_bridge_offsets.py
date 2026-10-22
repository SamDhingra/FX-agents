"""Bot-setup bridge: candidate discovery unions 8 chunk offsets, so which live-valid signals a backtest finds no
longer depends on where its data starts (the sr_rejection look-ahead audit failure, Oct 22 2026)."""
import numpy as np
import pandas as pd

from fxagents.research import _signals, verify_live_window
from fxagents.strategies import Strategy, build_strategy


def _df(n=4200, seed=11):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 00:00", periods=n, freq="5min", tz="America/New_York")
    c = 40000 + np.cumsum(rng.normal(0, 12, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, 8, n),
                         "low": np.minimum(o, c) - rng.uniform(0, 8, n), "close": c, "volume": 1.0}, index=idx)


def test_more_offsets_find_a_superset_of_live_valid_signals():
    df = _df()
    st = build_strategy({"class": "sr_rejection", "tf": "5min", "params": {}})
    ctx = Strategy._context(df)
    one = {(s.i, s.side) for s in _signals(st, df, ctx, offsets=1) if verify_live_window(st, df, s.i, s.side)}
    eight = {(s.i, s.side) for s in _signals(st, df, ctx, offsets=8) if verify_live_window(st, df, s.i, s.side)}
    assert one <= eight
    assert len({(s.i, s.side) for s in _signals(st, df, ctx, offsets=8)}) == len(_signals(st, df, ctx, offsets=8))  # no dupes


def test_bridge_uses_eight_offsets():
    src = open("fxagents/bt/botsetups.py").read()
    assert "offsets=1 if getattr(cls, \"fast\", False) else 8" in src
