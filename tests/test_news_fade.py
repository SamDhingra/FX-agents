"""News fade (registered Oct 28 2026): direction, fills, stop, exit time, size-matched control, gates."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import news_fade as F
from fxagents.news_study import Prices

NY = "America/New_York"


def flat_m1(start="2024-03-01", days=10, px=100.0, spread=0.2):
    idx = pd.date_range(start, periods=days * 1440, freq="min", tz=NY)
    rng = np.random.default_rng(0)
    c = px + np.cumsum(rng.normal(0, 0.05, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.05, "low": np.minimum(o, c) - 0.05, "close": c, "spread": spread}, index=idx)


def shape(m1, T, path):
    """Overwrite closes from T-1 on with a piecewise path: list of (minute offset, price)."""
    m1 = m1.copy()
    for (a, pa), (b, pb) in zip(path, path[1:]):
        for k in range(a, b):
            t = T + pd.Timedelta(minutes=k - 1)                          # the bar starting at t gives the price at t+1
            v = pa + (pb - pa) * (k - a) / (b - a)
            m1.loc[t, ["open", "close"]] = v
            m1.loc[t, "high"], m1.loc[t, "low"] = v + 0.01, v - 0.01
    return m1


def test_fades_the_first_move_with_real_fills_and_exits_at_t150():
    T = pd.Timestamp("2024-03-06 08:30", tz=NY)
    m1 = shape(flat_m1(), T, [(-1, 100.0), (30, 103.0), (151, 101.0), (200, 101.0)])
    P = Prices(m1)
    x = F.trade(P, T)
    assert x["side"] == -1 and x["exit"] == "time" and x["hold_min"] == 120
    entry = P.mid(T + pd.Timedelta("30min")) - 0.1                      # short at the bid
    out = P.mid(T + pd.Timedelta("150min")) + 0.1                       # cover at the ask
    assert x["net"] == pytest.approx((entry - out) / x["atr15"])
    x2 = F.trade(P, T, cost_mult=2.0)
    assert x2["net"] == pytest.approx(x["net"] - 0.2 / x["atr15"])


def test_fomc_exits_at_1550_and_the_stop_fills_at_the_stop():
    T = pd.Timestamp("2024-03-06 14:00", tz=NY)
    m1 = shape(flat_m1(), T, [(-1, 100.0), (30, 99.0), (200, 99.0)])
    x = F.trade(Prices(m1), T)
    assert x["side"] == 1 and x["hold_min"] == 80
    T2 = pd.Timestamp("2024-03-07 08:30", tz=NY)
    base = flat_m1()
    u = Prices(base).atr15(T2 - pd.Timedelta("60min"))
    m2 = shape(base, T2, [(-1, 100.0), (30, 102.0), (40, 102.0 + 6 * u), (160, 102.0 + 6 * u)])   # keeps going: stop
    y = F.trade(Prices(m2), T2)
    assert y["exit"] == "stop" and y["net"] == pytest.approx(-F.STOP_ATR, abs=0.6)


def test_size_matched_control_keeps_only_big_first_moves():
    rel = pd.DataFrame({"sym": "NDQ", "group": "08:30", "first_move": [1.0, 2.0, 3.0], "net": 0.0, "day": ["a", "b", "c"]})
    ctl = pd.DataFrame({"sym": "NDQ", "group": "08:30", "first_move": [0.5, -2.5, 1.9, 2.0], "net": 0.0, "day": list("wxyz")})
    mc, thr = F.matched(rel, ctl)
    assert thr["NDQ 08:30"] == 2.0 and sorted(mc.first_move) == [-2.5, 2.0]


def test_run_end_to_end_and_vault_needs_a_pass(tmp_path, monkeypatch):
    hist = tmp_path / "h"; hist.mkdir()
    m1 = flat_m1(start="2023-11-10", days=60)
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    monkeypatch.setitem(F.PERIODS, "test", (pd.Timestamp("2023-11-17", tz=NY), pd.Timestamp("2024-01-05", tz=NY)))
    res = F.run("test", hist, tmp_path / "out", syms=("XAUUSD",))
    txt = (tmp_path / "out/report.md").read_text()
    assert res["n"] > 0 and "size-matched control" in txt and not res["pass"]          # far fewer than 100 trades
    t = pd.read_csv(tmp_path / "out/trades.csv.gz")
    assert (pd.to_datetime(t["T"], utc=True) >= pd.Timestamp("2023-11-17", tz=NY).tz_convert("UTC")).all()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        F.run("vault", hist, tmp_path / "v", syms=("XAUUSD",))


def test_nostop_variant_holds_to_the_time_exit_and_runs_once(tmp_path, monkeypatch):
    T = pd.Timestamp("2024-03-07 08:30", tz=NY)
    base = flat_m1()
    u = Prices(base).atr15(T - pd.Timedelta("60min"))
    m2 = shape(base, T, [(-1, 100.0), (30, 102.0), (40, 102.0 + 6 * u), (160, 102.0 + 6 * u)])
    y = F.trade(Prices(m2), T, stop_atr=None)
    assert y["exit"] == "time" and y["net"] < -F.STOP_ATR
    hist = tmp_path / "h"; hist.mkdir()
    pd.to_pickle((flat_m1(start="2017-02-01", days=40), None), hist / "XAUUSD.pkl")
    monkeypatch.setitem(F.PERIODS, "vault", (pd.Timestamp("2017-02-06", tz=NY), pd.Timestamp("2017-03-10", tz=NY)))
    with pytest.raises(SystemExit):
        F.run("test", hist, tmp_path / "x", syms=("XAUUSD",), nostop=True)              # 2016-2020 only
    res = F.run("vault", hist, tmp_path / "v", syms=("XAUUSD",), nostop=True)          # no test-period pass needed
    assert res["n"] > 0 and "No-stop variant" in (tmp_path / "v/report.md").read_text()
    with pytest.raises(SystemExit):
        F.run("vault", hist, tmp_path / "v", syms=("XAUUSD",), nostop=True)            # once
