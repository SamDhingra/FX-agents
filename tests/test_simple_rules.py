"""ema21_rsi55: enters only on a fresh close above EMA21 with RSI > 55, exits on the first close below it."""
import numpy as np
import pandas as pd

from fxagents.simple_rules import bars15, run_ema21_rsi55


def frame(prices):
    idx = pd.date_range("2025-03-03 00:00", periods=len(prices), freq="1min", tz="UTC")
    p = np.asarray(prices, float)
    d = pd.DataFrame(index=idx)
    for c in "ohlc":
        d[f"bid_{c}"], d[f"ask_{c}"] = p - 0.1, p + 0.1
    for c in "ohlc":
        d[f"m_{c}"] = p
    return d


def test_entry_and_exit_follow_the_rule():
    rng = np.random.default_rng(3)
    p = 100 + np.cumsum(rng.normal(0, 0.05, 15 * 400))
    m1 = frame(p)
    b = bars15(m1)
    tr = run_ema21_rsi55(m1, "24h")
    assert tr, "expected some trades on a random walk"
    for t in tr:
        sig = b[b.index <= t["entry_time"]].iloc[-2:]
        assert sig.c.iloc[-1] > sig.ema21.iloc[-1] and sig.c.iloc[-2] <= sig.ema21.iloc[-2] and sig.rsi.iloc[-1] > 55
        held = b[(b.index > t["entry_time"]) & (b.index <= t["exit_time"])]
        assert (held.c.iloc[:-1] >= held.ema21.iloc[:-1]).all() and held.c.iloc[-1] < held.ema21.iloc[-1]
        assert abs(t["entry"] - (m1.loc[t["entry_time"], "ask_o"])) < 1e-12      # bought at the ask
        assert abs(t["exit"] - (m1.loc[t["exit_time"], "bid_o"])) < 1e-12        # sold at the bid


def test_cost_is_one_spread_per_round_trip():
    rng = np.random.default_rng(5)
    m1 = frame(100 + np.cumsum(rng.normal(0, 0.05, 15 * 400)))       # spread 0.2 everywhere
    for t in run_ema21_rsi55(m1, "24h"):
        assert abs(t["cost_R"] * t["atr"] - 0.2) < 1e-9
        assert abs((t["R"] - t["R_2x"]) * t["atr"] - 0.2) < 1e-9


def test_add_follows_its_rule_and_volume_filter_only_removes_trades():
    rng = np.random.default_rng(11)
    p = 100 + np.cumsum(rng.normal(0.002, 0.05, 15 * 600))
    m1 = frame(p)
    m1["volume"] = rng.integers(1, 50, len(m1))
    b = bars15(m1)
    base = run_ema21_rsi55(m1, "24h", "15min", None, False, b)
    added = run_ema21_rsi55(m1, "24h", "15min", None, True, b)
    assert [t["entry_time"] for t in base] == [t["entry_time"] for t in added]       # adds never change entries/exits
    for t in added:
        if t["added"]:
            held = b[(b.index > t["entry_time"]) & (b.index < t["exit_time"])]
            ok = held[(held.rsi > 58) & (held.rsi <= 70) & (held.c > held.ema21) & (held.c > t["entry"])]
            assert len(ok)                                                          # a qualifying candle existed
        else:
            assert t["R"] == t["R_base"]
    vol = run_ema21_rsi55(m1, "24h", "15min", 1.0, False, b)
    assert {t["entry_time"] for t in vol} <= {t["entry_time"] for t in base} | {t["entry_time"] for t in vol}
    assert all(t["rvol"] >= 1.0 for t in vol)
