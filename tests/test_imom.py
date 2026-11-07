"""Intraday momentum into the close (registered Nov 7 2026): signal, fills at the real bid/ask, the controls, the vault gate."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import imom as I
from tests.test_breakout import frame


def market(n_days=160, follow=True, seed=1, spread=0.2):
    """NY weekdays. Each 16:00→16:00 session drifts one random way; the last half-hour (15:30–16:00) continues that
    way (follow=True) or goes a random way (follow=False)."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2022-01-03 16:00", tz=I.NY)
    idx = pd.date_range(start, periods=1440 * n_days, freq="1min")
    sess = ((idx - start) // pd.Timedelta("1D")).to_numpy()
    s = rng.choice([-1, 1], sess.max() + 1)
    tod = idx.hour * 60 + idx.minute
    last = (tod >= 15 * 60 + 30) & (tod < 16 * 60)
    step = s[sess] * 0.02 + rng.normal(0, 0.05, len(idx))
    if not follow:
        step = np.where(last, rng.choice([-1, 1], sess.max() + 1)[sess] * 0.02 + rng.normal(0, 0.05, len(idx)), step)
    m1 = frame(10000 + np.cumsum(step), start=str(idx[0].tz_convert("UTC").tz_localize(None)), spread=spread)
    return m1[m1.index.tz_convert(I.NY).dayofweek < 5]


def test_fills_and_signal():
    m1 = market(30)
    d = I.day_table(m1)
    day = d.index[5]
    ny = lambda hm: (day + pd.Timedelta(hm)).tz_localize(I.NY).tz_convert("UTC")
    prev = d.index[4]
    sig = m1.loc[ny("15:29:00"), "m_c"]
    ref = m1.loc[(prev + pd.Timedelta("15:59:00")).tz_localize(I.NY).tz_convert("UTC"), "m_c"]
    assert d.loc[day, "r"] == pytest.approx(sig / ref - 1)
    assert d.loc[day, "ask_in"] == m1.loc[ny("15:30:00"), "ask_o"] and d.loc[day, "bid_out"] == m1.loc[ny("15:59:00"), "bid_c"]
    mid = (d.loc[day, "ask_in"] + d.loc[day, "bid_in"]) / 2
    assert d.loc[day, "long_bps"] == pytest.approx((d.loc[day, "bid_out"] - d.loc[day, "ask_in"]) / mid * 1e4)
    assert d.loc[day, "spread_bps"] == pytest.approx(0.2 / mid * 1e4)


def test_momentum_market_passes_its_controls_and_noise_does_not():
    split = pd.Timestamp("2022-05-01")
    good = I.judge(I.trades(I.day_table(market(160, follow=True))), split, 1.0)
    assert good["win"] > 0.8 and good["vs_long_lo"] > 0 and good["perm_p"] < 0.01 and good["pass"]
    bad = I.judge(I.trades(I.day_table(market(160, follow=False, seed=2))), split, 1.0)
    assert not bad["pass"] and bad["perm_p"] > 0.01


def test_skips_a_missing_minute():
    m1 = market(10)
    d0 = I.day_table(m1)
    day = d0.index[4]
    t0 = (day + pd.Timedelta("15:25:00")).tz_localize(I.NY).tz_convert("UTC")
    t1 = (day + pd.Timedelta("15:35:00")).tz_localize(I.NY).tz_convert("UTC")
    d = I.day_table(m1[(m1.index < t0) | (m1.index > t1)])             # a 10-minute hole around 15:30
    assert day not in d.index and len(d) == len(d0) - 1


def test_vault_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="needs the seen result"):
        I.allowed("vault")
    (tmp_path / "imom_seen").mkdir()
    (tmp_path / "imom_seen/summary.json").write_text(json.dumps({"rows": {"US30": {"pass": False}, "NDQ": {"pass": True}}}))
    with pytest.raises(SystemExit, match="US30 did not pass"):
        I.allowed("vault")


def test_seen_stage_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "OUT", tmp_path)
    for s in ("holdout_m1", "dev_m1"):
        (tmp_path / "exp" / s).mkdir(parents=True)
    m1 = market(170)
    cut = m1.index[len(m1) // 2]
    for s, part in (("holdout_m1", m1[m1.index < cut]), ("dev_m1", m1[m1.index >= cut])):
        part.reset_index(names="time").to_csv(tmp_path / "exp" / s / "US30_M1.csv.gz", index=False)
    s = I.run_stage("seen", root=tmp_path / "exp")
    assert s["rows"]["US30"]["trades"] > 100 and s["missing"] == ["NDQ", "XAUUSD"]
    rep = (tmp_path / "imom_seen/report.md").read_text()
    assert "vs always long" in rep and "exit 15:50" in rep and "By year" in rep
