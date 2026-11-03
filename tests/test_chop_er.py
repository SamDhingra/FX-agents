"""Efficiency-ratio chop filter (registered Nov 3 2026)."""
import numpy as np
import pandas as pd
import pytest

from fxagents import chop_er as C
from tests.test_round3_gemini import m1_walk

NY = "America/New_York"


def test_efficiency_ratio_and_adx():
    assert C.efficiency(np.arange(20.0)) == pytest.approx(1.0)                 # a straight line
    zig = np.array([0, 1] * 10, float)
    assert C.efficiency(zig) < 0.1                                             # back and forth: no progress
    assert np.isnan(C.efficiency(np.arange(5.0)))
    idx = pd.date_range("2025-02-03", periods=80, freq="15min", tz=NY)
    up = pd.DataFrame({"high": np.arange(80) + 1.0, "low": np.arange(80) - 1.0, "close": np.arange(80.0)}, index=idx)
    side = pd.DataFrame({"high": 1 + (np.arange(80) % 2), "low": -1 - (np.arange(80) % 2), "close": np.zeros(80)}, index=idx)
    assert C.adx(up) > 40 and C.adx(side) < 20


def test_measure_reads_only_before_the_entry_and_flags():
    m1 = m1_walk(days=10)
    ts = pd.Timestamp("2025-02-12 10:00", tz=NY)
    m = C.measure(ts, m1)
    assert set(m) == {"er15", "er1h", "chop15", "adx15"} and 0 <= m["er15"] <= 1
    m1b = m1.copy()
    m1b.loc[m1b.index >= ts, ["open", "high", "low", "close"]] = 1e6           # poison the future
    assert C.measure(ts, m1b) == m
    f = C.flags({"er15": 0.1, "er1h": 0.5, "chop15": 70.0, "adx15": 30.0})
    assert f == {"er15": 1.0, "er1h": 0.0, "chop15_skip": 1.0, "adx15": 0.0}
    assert np.isnan(C.flags(None)["er15"])
    assert C.measure(m1.index[30], m1) is None


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
    res = C.run("seen", src, hist, tmp_path / "out")
    assert set(res) == {"er15", "er1h"}
    txt = (tmp_path / "out/report.md").read_text()
    assert "For comparison" in txt and "chop15_skip" in txt and "efficiency ratio" in txt
    with pytest.raises(SystemExit):
        C.run("seen", src, hist, tmp_path / "out")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        C.run("vault", src, hist, tmp_path / "v")
