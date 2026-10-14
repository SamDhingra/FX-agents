"""Gold Breakout 15M rules: range 00–07 GMT+3, OCA stop entries, 1% / range stop, flat at the close hour."""
import numpy as np
import pandas as pd

from fxagents.breakout_test import run, to_broker


def frame(prices, start="2025-03-02 21:00", spread=0.2):
    """M1 bid/ask frame from a list of mid prices (one per minute, flat candles)."""
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz="UTC")
    m = np.asarray(prices, float)
    d = {}
    for side, sh in (("bid", -spread / 2), ("ask", spread / 2)):
        for f in "ohlc":
            d[f"{side}_{f}"] = m + sh
    df = pd.DataFrame(d, index=idx)
    for f in "ohlc":
        df[f"m_{f}"] = (df[f"bid_{f}"] + df[f"ask_{f}"]) / 2
    return df


def two_days(day2):
    """Day 1 (skipped as first day) = 1440 flat minutes from 2025-03-03 00:00 broker; day 2 = 2025-03-04 from 00:00
    broker (2025-03-03 21:00 UTC), given minute by minute."""
    return frame([100.0] * 1440 + list(day2))


def test_broker_clock_is_utc_plus_3():
    idx = pd.DatetimeIndex(["2025-03-02 21:00", "2025-03-03 03:59"], tz="UTC")
    day, mins = to_broker(idx)
    assert day[0] == day[1] and list(mins) == [0, 419]


def test_long_breakout_fills_at_range_high_and_exits_at_close():
    day2 = [100.0] * 100 + [99.5] * 10 + [100.0] * 90 + [100.5] * 10 + [100.0] * 240 + [101.0] * 900  # 99.5–100.5
    tr, _ = run(two_days(day2), 20, "pct", np.random.default_rng(0))
    assert len(tr) == 1
    t = tr[0]
    assert t["side"] == 1 and abs(t["entry"] - 101.1) < 1e-9          # gapped through: fills at the ask open
    assert t["entry_time"] == pd.Timestamp("2025-03-04 04:30", tz="UTC")
    assert t["exit_reason"] == "time"
    assert t["exit_time"] == pd.Timestamp("2025-03-04 17:00", tz="UTC")


def test_pct_stop_and_one_trade_per_day():
    day2 = [100.0] * 200 + [101.0] * 10 + [100.0] * 210 + [101.5] * 10 + [96.0] * 600   # up-break, then collapse
    tr, _ = run(two_days(day2), 20, "pct", np.random.default_rng(0))
    assert len(tr) == 1                                       # the sell stop was cancelled by the first fill
    t = tr[0]
    assert t["side"] == 1 and t["exit_reason"] == "stop"
    assert abs(t["atr"] - t["entry"] * 0.01) < 1e-9
    assert abs(t["exit"] - 95.9) < 1e-9                       # gapped through the stop: out at the bid open


def test_range_stop_uses_opposite_boundary_and_earlier_close():
    day2 = [100.0] * 200 + [102.0] * 220 + [99.0] * 900      # range 100–102; breaks down
    tr, _ = run(two_days(day2), 12, "range", np.random.default_rng(0))
    t = tr[0]
    assert t["side"] == -1 and t["exit_reason"] == "time"
    assert t["exit_time"] == pd.Timestamp("2025-03-04 09:00", tz="UTC")
    assert abs((t["entry"] + t["atr"]) - (102.0 + 0.1)) < 1e-9   # stop above the range high, on the ask
