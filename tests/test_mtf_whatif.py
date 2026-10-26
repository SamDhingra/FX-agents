"""What-if checks: higher timeframe moving against the trade at entry (fxagents/mtf_whatif)."""
import numpy as np
import pandas as pd

from fxagents import mtf_whatif as W

NY = "America/New_York"


def m1_from(prices, start="2025-03-04 09:00"):
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=NY)
    p = np.asarray(prices, float)
    o = np.r_[p[0], p[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, p), "low": np.minimum(o, p), "close": p}, index=idx)


def test_flags_follow_the_higher_timeframe_candles():
    # 09:00–10:00 falls 100 → 40, then 10:00–10:20 rises 40 → 60: a short at 10:12 is inside a rising 15m candle
    prices = list(np.linspace(100, 40, 60)) + list(np.linspace(40, 60, 21))[1:] + [60] * 20
    m1 = m1_from(prices)
    t = pd.DataFrame({"ts": [pd.Timestamp("2025-03-04 10:12", tz=NY), pd.Timestamp("2025-03-04 10:12", tz=NY)],
                      "side": [-1, 1], "r": [-1.0, 1.0]})
    a = W.annotate(t, m1)
    short, long_ = a.iloc[0], a.iloc[1]
    assert short.ok and short.m15_live and not long_.m15_live          # 10:00 candle rising: against the short
    assert not short.m15_closed and long_.m15_closed                     # 09:45 candle closed red: against the long
    assert not short.m15_trend and long_.m15_trend                       # 15m EMA still falling
    assert short.h1_live and not long_.h1_live                            # the 10:00 hour is rising too


def test_entry_on_a_15m_boundary_uses_the_candle_that_just_closed():
    prices = [100] * 15 + list(np.linspace(100, 110, 16))[1:] + [110] * 30
    m1 = m1_from(prices)
    t = pd.DataFrame({"ts": [pd.Timestamp("2025-03-04 09:30", tz=NY)], "side": [-1], "r": [0.0]})
    a = W.annotate(t, m1).iloc[0]
    assert a.m15_live and a.m15_closed                                   # the 09:15 candle rose: against a short


def test_run_writes_a_report(tmp_path):
    rng = np.random.default_rng(1)
    n = 60 * 24 * 40
    m1 = m1_from(1000 + np.cumsum(rng.normal(0, 1, n)), start="2025-01-02 00:00")
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    src = tmp_path / "src"; src.mkdir()
    ts = m1.index[rng.choice(np.arange(2000, n - 10), 600, replace=False)]
    for tf in ("3m", "15m"):
        tr = pd.DataFrame({"sym": "XAUUSD", "tf": tf, "ts": ts.astype(str), "side": rng.choice([1, -1], len(ts)),
                           "r": rng.normal(-0.05, 1, len(ts)), "day": ts.date.astype(str)})
        tr.to_csv(src / f"trades_seen_x_{tf}.csv.gz", index=False)
    res = W.run(src, hist, tmp_path / "out")
    assert set(res["low_tf"]) == set(W.CHECKS) and (tmp_path / "out/report.md").exists()
    assert "Sam's case" in (tmp_path / "out/report.md").read_text()


def test_confirmation_judges_only_m15_live_and_shows_it_without_macd(tmp_path):
    rng = np.random.default_rng(2)
    n = 60 * 24 * 40
    m1 = m1_from(1000 + np.cumsum(rng.normal(0, 1, n)), start="2017-01-02 00:00")
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    src = tmp_path / "src"; src.mkdir()
    for cell in ("smc_displacement_3m_pb-xau-d", "macd_cross_5m_pb-ndq-d"):
        ts = m1.index[rng.choice(np.arange(2000, n - 10), 400, replace=False)]
        pd.DataFrame({"sym": "XAUUSD", "tf": cell.split("_")[-2], "ts": ts.astype(str), "side": rng.choice([1, -1], len(ts)),
                      "r": rng.normal(-0.05, 1, len(ts)), "day": ts.date.astype(str)}).to_csv(
            src / f"trades_old_{cell}.csv.gz", index=False)
    res = W.run(src, hist, tmp_path / "out", pattern="trades_old_", confirm=True)
    assert res["m15_live"]["check"] == "m15_live" and res["m15_live_without_macd"]["n"] == 400
    txt = (tmp_path / "out/report.md").read_text()
    assert "Verdict:" in txt and "For information only" in txt and "macd_cross_5m_pb-ndq-d" in txt
