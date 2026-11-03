"""SuperTrend + EMA + RSI test (registered Nov 2 2026): indicators, entries, fills, stops, gates, one-shot rules."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import supertrend_test as S

NY = "America/New_York"


def m1_frame(days=40, seed=1, trend=0.0, spread=0.5):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2021-03-01", periods=days):
        idx.append(pd.date_range(pd.Timestamp(d, tz=NY) + pd.Timedelta(hours=1), periods=15 * 60, freq="1min"))
    idx = idx[0].append(idx[1:])
    ret = rng.normal(trend, 1.0, len(idx))
    c = 15000 + np.cumsum(ret)
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) + rng.random(len(c)), np.minimum(o, c) - rng.random(len(c))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0, "spread": spread}, index=idx)


def test_supertrend_flips_with_the_trend_and_line_sits_on_the_right_side():
    c = np.r_[np.linspace(100, 130, 60), np.linspace(130, 95, 60)]
    h, l = c + 0.5, c - 0.5
    line, d, a = S.supertrend(h, l, c)
    assert d[55] == 1 and line[55] < c[55]
    assert d[-1] == -1 and line[-1] > c[-1]
    assert S.rsi(np.linspace(1, 50, 60))[-1] > 90 and S.rsi(np.linspace(50, 1, 60))[-1] < 10


def test_trades_are_causal_fill_at_ask_and_stop_at_the_line():
    mk = S.Market(m1_frame(trend=0.05), "15min")
    t = mk.run(S.PRIMARY)
    assert len(t) > 5
    assert (t.risk_atr >= S.MIN_RISK_ATR).all() and (t.risk_atr <= S.MAX_RISK_ATR).all()
    assert set(t.exit) <= {"stop", "flip", "flat"}
    hm = pd.to_datetime(t.ts).dt.hour * 60 + pd.to_datetime(t.ts).dt.minute
    assert ((hm >= S.ENTRY_FROM) & (hm < S.ENTRY_TO)).all()
    assert (pd.to_datetime(t.exit_ts) > pd.to_datetime(t.ts) - pd.Timedelta("1min")).all()
    assert (pd.to_datetime(t.exit_ts).dt.hour * 60 + pd.to_datetime(t.exit_ts).dt.minute <= S.FLAT).all()
    # entries never overlap
    ts, xs = pd.to_datetime(t.ts).to_numpy(), pd.to_datetime(t.exit_ts).to_numpy()
    assert all(ts[i + 1] >= xs[i] for i in range(len(t) - 1))
    # a wider spread makes every trade worse (paid on entry and exit)
    wide = S.Market(m1_frame(trend=0.05, spread=3.0), "15min").run(S.PRIMARY)
    assert wide.r.mean() < t.r.mean()
    # causality: cutting the future doesn't change earlier signals
    m1 = m1_frame(trend=0.05)
    full = S.Market(m1, "15min").entry_bars(S.PRIMARY)
    cut = S.Market(m1.iloc[: len(m1) // 2], "15min")
    n = len(cut.bars) - 1
    assert [x for x in cut.entry_bars(S.PRIMARY) if x[0] < n] == [x for x in full if x[0] < n]


def test_gates_and_one_shot(tmp_path, monkeypatch):
    data = {s: m1_frame(days=30, seed=i + 2) for i, s in enumerate(S.SYMS)}
    out = tmp_path / "seen"
    s = S.run("seen", tmp_path, out, data=data)
    assert set(s) >= {S.PRIMARY, "control"} and (out / "report.md").exists()
    rep = (out / "report.md").read_text()
    assert "Shown, not judged" in rep and "random-timing control" in rep
    with pytest.raises(SystemExit):
        S.run("seen", tmp_path, out, data=data)
    monkeypatch.setitem(S.OUT, "seen", out)
    if not s[S.PRIMARY]["pass"]:
        with pytest.raises(SystemExit):
            S.run("vault", tmp_path, tmp_path / "vault", data=data)
    (out / "summary.json").write_text(json.dumps({S.PRIMARY: {"pass": True}}))
    v = S.run("vault", tmp_path, tmp_path / "vault", data=data)
    assert "Verdict on 2016–2020" in (tmp_path / "vault" / "report.md").read_text() and S.PRIMARY in v


def test_judge_requires_beating_the_control():
    days = pd.bdate_range("2021-01-04", periods=300, tz=NY)
    t = pd.DataFrame({"ts": np.repeat(days, 1) + pd.Timedelta(hours=10), "r": 0.3, "cost_r": 0.05})
    t.loc[::7, "r"] = -0.2
    good = S.judge(t, "2021-07-01", pd.DataFrame({"r": [0.0, 0.1]}))
    bad = S.judge(t, "2021-07-01", pd.DataFrame({"r": [0.5, 0.6]}))
    assert good["pass"] and not bad["pass"]
