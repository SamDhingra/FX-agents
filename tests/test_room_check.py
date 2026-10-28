"""Room-to-the-next-M15-level check (registered Oct 28 2026)."""
import numpy as np
import pandas as pd
import pytest

from fxagents import room_check as R
from tests.test_round3_gemini import m1_walk

NY = "America/New_York"


def bars(lows, highs):
    idx = pd.date_range("2025-02-03 09:00", periods=len(lows), freq="15min", tz=NY)
    return pd.DataFrame({"open": 0.0, "high": highs, "low": lows, "close": 0.0}, index=idx)


def test_swing_level_is_the_nearest_confirmed_swing_on_the_target_side():
    lows = [10, 8, 9, 7, 9, 9.5, 6]            # swings at 8 (i=1) and 7 (i=3); the last candle can't be a swing
    b = bars(lows, [x + 1 for x in lows])
    assert R.swing_level(b, -1, 9.0) == 8      # short at 9: nearest swing low below
    assert R.swing_level(b, -1, 7.5) == 7
    assert R.swing_level(b, -1, 6.5) is None   # nothing below → open room
    highs = [5, 7, 6, 8, 6, 5, 9]
    assert R.swing_level(bars([0] * 7, highs), +1, 6.5) == 7


def test_measure_reads_only_before_the_entry_and_flags():
    m1 = m1_walk(days=10)
    ts = pd.Timestamp("2025-02-12 10:00", tz=NY)
    m = R.measure({"ts": ts, "side": -1, "tf": "5m", "risk_atr": 1.0}, m1)
    assert m["entry"] == float(m1.loc[m1.index < ts, "close"].iloc[-1])
    m1b = m1.copy()
    m1b.loc[m1b.index >= ts, ["open", "high", "low", "close"]] = 1e6            # poison the future
    assert R.measure({"ts": ts, "side": -1, "tf": "5m", "risk_atr": 1.0}, m1b) == m
    f = R.flags({**m, "room_swing": 0.5 * m["stop"], "room_last2": -1.0})
    assert f["room_swing"] == 1.0 and f["room_last2"] == 0.0 and f["room_swing_x0.75"] == 1.0
    f = R.flags({**m, "room_swing": None, "room_last2": 0.3 * m["stop"]})
    assert f["room_swing"] == 0.0 and f["room_last2"] == 1.0
    assert np.isnan(R.flags(None)["room_swing"])
    assert R.measure({"ts": m1.index[50], "side": 1, "tf": "3m", "risk_atr": 1.0}, m1) is None   # too little history


def test_run_seen_and_vault_needs_a_seen_pass(tmp_path, monkeypatch):
    rng = np.random.default_rng(4)
    m1 = m1_walk(days=60, seed=2, start="2021-03-01 00:00")
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    src = tmp_path / "src"; src.mkdir()
    ts = m1.index[rng.choice(np.arange(8 * 1440, len(m1) - 10), 300, replace=False)]
    pd.DataFrame({"sym": "XAUUSD", "tf": "3min", "ts": ts.astype(str), "side": rng.choice([1, -1], len(ts)),
                  "r": rng.normal(-0.05, 1, len(ts)), "risk_atr": rng.uniform(0.3, 2.0, len(ts)),
                  "day": ts.date.astype(str)}).to_csv(src / "trades_seen_x_3m.csv.gz", index=False)
    res = R.run("seen", src, hist, tmp_path / "out")
    assert set(res) == {"room_swing", "room_last2"}
    txt = (tmp_path / "out/report.md").read_text()
    assert "Sensitivity" in txt and "room_swing" in txt and "no_room" in txt
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        R.run("vault", src, hist, tmp_path / "v")
