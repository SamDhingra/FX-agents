"""Held trend rules / NDQ SuperTrend / SuperTrend in EMA21-RSI55 (registered Nov 2 2026)."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import supertrend_test as S
from fxagents import trend_hold_test as T

NY = "America/New_York"


def m1_week(weeks=6, seed=3, trend=0.02, spread=0.5):
    """Sun 18:00 → Fri 17:00 with a 17:00–18:00 daily break, like OANDA index CFDs."""
    rng = np.random.default_rng(seed)
    parts = []
    for w in range(weeks):
        sun = pd.Timestamp("2021-03-07 18:00", tz=NY) + pd.Timedelta(weeks=w)
        for d in range(5):
            start = sun + pd.Timedelta(days=d)
            parts.append(pd.date_range(start, start + pd.Timedelta(hours=23) - pd.Timedelta("1min"), freq="1min"))
    idx = parts[0].append(parts[1:])
    c = 15000 + np.cumsum(rng.normal(trend, 1.0, len(idx)))
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) + rng.random(len(c)), np.minimum(o, c) - rng.random(len(c))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0, "spread": spread}, index=idx)


def test_held_trades_cross_nights_and_pay_financing_fridays_three_times():
    mk = T.hold_market(m1_week(), "1h")
    t = mk.run2(S.PRIMARY, "st")
    assert len(t) > 3 and (t.nights > 0).any()
    assert ((t.r_nofin - t.r) >= -1e-12).all()                      # financing only ever costs
    held = t[t.nights > 0].iloc[0]
    assert held.r < held.r_nofin
    # a Friday 16:59 → Sunday 18:00 hold is three nights
    i = mk.m1.index
    j_fri = int(np.nonzero((i.dayofweek == 4) & (i.hour == 16) & (i.minute == 59))[0][0])
    assert mk.nights_cum[j_fri + 1] - mk.nights_cum[j_fri] == 3
    j_mon = int(np.nonzero((i.dayofweek == 0) & (i.hour == 18) & (i.minute == 0))[0][0])
    assert mk.nights_cum[j_mon] - mk.nights_cum[j_mon - 1] == 1


def test_er_rule_matches_the_paper_book_definition():
    mk = T.er_market(m1_week())
    t = mk.run2("er", "er")
    assert len(t) > 3 and set(t.exit) <= {"ema", "stop", "flat"}
    assert (abs(t.risk_atr - 3.0) < 1e-9).all()                     # 1R = 3 × ATR(14)
    hm = pd.to_datetime(t.ts).dt.hour * 60 + pd.to_datetime(t.ts).dt.minute
    assert ((hm >= 120) & (hm <= 930)).all()
    f = mk.run2("er", "er", st_filter=True)
    assert len(f) <= len(t)
    six = mk.run2("er", "er", only_hour=6)
    assert (six.hour == 6).all()


def test_seen_then_vault_flow(tmp_path, monkeypatch):
    data = {s: m1_week(weeks=4, seed=i + 5) for i, s in enumerate(S.SYMS)}
    out = tmp_path / "seen"
    s = T.run("seen", tmp_path, out, data=data)
    assert set(T.HOLD) <= set(s) and "er_st_filter" in s and "er_gold_06" in s and "ndq_st_15m" not in s
    rep = (out / "report.md").read_text()
    assert "financing" in rep and "entry hour" in rep
    with pytest.raises(SystemExit):
        T.run("seen", tmp_path, out, data=data)
    monkeypatch.setitem(T.OUT, "seen", out)
    j = json.loads((out / "summary.json").read_text())
    j["hold_st_4h"]["pass"] = True
    (out / "summary.json").write_text(json.dumps(j))
    v = T.run("vault", tmp_path, tmp_path / "vault", data=data)
    assert "ndq_st_15m" in v and "hold_st_4h" in v and "hold_er_1h" not in v
    with pytest.raises(SystemExit):
        T.run("vault", tmp_path, tmp_path / "vault", data=data)
