import numpy as np
import pandas as pd

from fxagents.astra_cfd import Costs, execute, gap_fail, h1_trend, orb, wilder_atr

C0 = Costs(s=1.0, slip=0.25, q=0.1)


def arr(*rows):
    return [np.array(x, float) for x in zip(*rows)]


def test_wilder_atr_seed_is_mean_of_first_n_true_ranges():
    H, L, C = np.array([10, 12, 11.]), np.array([9, 10, 8.]), np.array([9.5, 11, 9.])
    a = wilder_atr(H, L, C, n=2)
    assert np.isnan(a[0]) and a[1] == (1 + 2.5) / 2 and a[2] == (a[1] + 3) / 2


def test_long_entry_pays_half_spread_and_slip_and_stop_wins_same_bar():
    O, H, L, C = arr((100, 100, 100, 100), (100, 103, 97, 100))   # bar 1 touches both stop 98 and target 102
    r = execute(O, H, L, C, 0, 1, 98.0, 2, C0, target=102.0)
    assert r["fill"] == 100.75 and r["why"] == "stop" and r["exit"] == 98 - 0.25


def test_adverse_gap_fills_at_open_and_time_exit_at_open():
    O, H, L, C = arr((100, 100, 100, 100), (95, 96, 94, 95))
    assert execute(O, H, L, C, 0, 1, 98.0, 2, C0)["exit"] == 95 - 0.5 - 0.25
    O, H, L, C = arr((100, 100, 100, 100), (101, 101, 101, 101), (102, 102, 102, 102))
    r = execute(O, H, L, C, 0, -1, 103.0, 2, C0)
    assert r["why"] == "time" and r["exit"] == 102 + 0.5 + 0.25


def test_trail_through_market_closes_at_next_open():
    O, H, L, C = arr((100, 101, 100, 101), (110, 111, 109, 110), (110, 111, 109, 110))
    r = execute(O, H, L, C, 0, 1, 98.0, 3, C0, trail=lambda k, s, f, R: 120.0 if k == 2 else None)
    assert r["why"] == "trail_through" and r["k_exit"] == 2


def _m1(days=70, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 09:00", periods=60 * 24 * days, freq="1min", tz="America/New_York")
    idx = idx[idx.dayofweek < 5]
    c = 20000 + np.cumsum(rng.normal(0, 12, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.random(len(idx)) * 8,
                         "low": np.minimum(o, c) - rng.random(len(idx)) * 8, "close": c, "volume": 1.0}, index=idx)


def test_strategies_are_causal_on_a_prefix():
    m1 = _m1()
    cut = m1.index[len(m1) * 3 // 4].normalize()
    pre = m1[m1.index < cut]
    c = Costs(1.5, 0.375, 0.1)
    for fn, kw in ((orb, {}), (gap_fail, {"control": True}), (h1_trend, {})):
        full = [t for t in fn(m1, c, **kw) if pd.Timestamp(t["day"], tz="America/New_York") < cut - pd.Timedelta("1D")]
        part = [t for t in fn(pre, c, **kw) if pd.Timestamp(t["day"], tz="America/New_York") < cut - pd.Timedelta("1D")]
        assert len(full) > 0, fn.__name__
        assert [(t["day"], t["side"], round(t["r"], 9)) for t in full] == [(t["day"], t["side"], round(t["r"], 9)) for t in part]


def test_incomplete_last_session_is_skipped_not_crashing():
    m1 = _m1()
    cut = m1.index[-1].normalize() + pd.Timedelta(hours=12)       # the data ends at noon on the last day
    part = m1[m1.index < cut]
    c = Costs(1.5, 0.375, 0.1)
    for fn in (orb, h1_trend):
        last = part.index[-1].strftime("%Y-%m-%d")
        assert all(t["day"] != last for t in fn(part, c))
