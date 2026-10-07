"""Learner context filters: hours / direction a strategy keeps losing in, and the generic scan filter."""
import numpy as np
import pandas as pd

from fxagents.agents.strategist import StrategistAgent
from fxagents.strategies import Strategy, build_strategy


def _agent(real=None):
    a = StrategistAgent.__new__(StrategistAgent)
    a.real_hours = lambda base: real or {}
    return a


def _trades(spec):
    out = []
    for hour, side, rs in spec:
        out += [{"hour": hour, "side": side, "r": r} for r in rs]
    return out


def test_losing_hour_is_blocked_and_good_hours_kept():
    st = build_strategy({"class": "smc_ifvg", "tf": "5min"})
    tr = _trades([(9, 1, [1.0, -1.0, 1.0, 1.0, -1.0] * 4), (10, 1, [1.0, 1.0, -1.0] * 4),
                  (14, 1, [-1.0] * 10)])
    ch = _agent().context_filter(st, tr)
    assert ch == {"block_hours": [14]}


def test_real_trades_overrule_and_back_up_the_backtest():
    st = build_strategy({"class": "smc_ifvg", "tf": "5min"})
    tr = _trades([(9, 1, [1.0, -1.0, 1.0] * 8), (14, 1, [-1.0, -1.0, 1.0] * 3)])
    assert _agent({14: [1.0] * 6}).context_filter(st, tr) is None            # real trades win at 14 → keep it
    tr2 = _trades([(9, 1, [1.0, -1.0, 1.0] * 8), (11, 1, [-1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])])
    ch = _agent({11: [-1.0] * 6}).context_filter(st, tr2)                     # real losses + a weak backtest → block
    assert ch == {"block_hours": [11]}


def test_losing_direction_is_dropped():
    st = build_strategy({"class": "smc_ifvg", "tf": "5min"})
    tr = _trades([(9, 1, [1.0, -1.0] * 10), (9, -1, [-1.0, -1.0, 1.0] * 7)])
    ch = _agent().context_filter(st, tr)
    assert ch.get("sides") == "long"


def test_scan_filters_apply_to_any_strategy():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2026-06-01", periods=3000, freq="5min", tz="America/New_York")
    c = 3650 + np.cumsum(rng.normal(0, 1.5, len(idx)))
    df = pd.DataFrame({"open": c, "high": c + 1.5, "low": c - 1.5, "close": c + rng.normal(0, .5, len(idx)),
                       "volume": 1.0}, index=idx)
    base = build_strategy({"class": "smc_choch", "tf": "5min"})
    ctx = Strategy._context(df)
    sig = base._scan_full(df, ctx)
    assert sig
    hours = {int(ctx["close_ts"][s.i].hour) for s in sig}
    h = sorted(hours)[0]
    f = build_strategy({"class": "smc_choch", "tf": "5min", "params": {"block_hours": [h], "sides": "long"}})
    got = f._scan_full(df, Strategy._context(df))
    assert all(int(ctx["close_ts"][s.i].hour) != h and s.side > 0 for s in got)
    assert {(s.i, s.side) for s in got} == {(s.i, s.side) for s in sig if s.side > 0 and int(ctx["close_ts"][s.i].hour) != h}
