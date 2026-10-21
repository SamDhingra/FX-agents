"""AFR-1 (NDQ afternoon failed reversal): the rules on a hand-built trend day, its admission checks, early closes,
the report's per-eligible-day comparison, and the look-ahead audit."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from fxagents.bt import data, engine
from fxagents.bt.run import load_plugin

NY = "America/New_York"


def _day_market(sweep=True, spread=0.4, fill_mid=20105.0):
    idx = pd.date_range(pd.Timestamp("2026-03-02 18:00", tz=NY), pd.Timestamp("2026-03-05 15:59", tz=NY), freq="1min")
    rows = []
    for ts in idx:
        p = 20000.0
        if ts.date() == date(2026, 3, 5):
            mins = ts.hour * 60 + ts.minute
            if 570 <= mins < 750:
                p = 20000 + 100 * (mins - 570) / 180
            elif mins >= 750:
                p = 20100.0 if mins < 790 else 20105.0
        bar = (p, p + 5, p - 5, p)
        if sweep and ts.date() == date(2026, 3, 5):
            mins = ts.hour * 60 + ts.minute
            if mins == 785:
                bar = (20100, 20102, 20091, 20092)
            elif 786 <= mins <= 788:
                bar = (20093, 20096, 20092, 20093)
            elif mins == 789:
                bar = (20095, 20106, 20094, 20105)
            elif mins == 790:
                bar = (fill_mid, fill_mid + 5, fill_mid - 5, fill_mid)
        rows.append(bar)
    a = np.array(rows, float)
    d = pd.DataFrame(index=idx.tz_convert("UTC"))
    for i, f in enumerate("ohlc"):
        d[f"bid_{f}"], d[f"ask_{f}"] = a[:, i] - spread / 2, a[:, i] + spread / 2
    return data.from_frame(d)


def _plugin(**kw):
    S, _ = load_plugin("btplugins/afr1.py")
    return S(**kw)


def test_early_close_calendar():
    from importlib import import_module
    S, _ = load_plugin("btplugins/afr1.py")
    mod = import_module(S.__module__)
    assert mod.early_close(date(2025, 11, 28)) and mod.early_close(date(2024, 12, 24)) and mod.early_close(date(2025, 7, 3))
    assert not mod.early_close(date(2025, 11, 27)) and not mod.early_close(date(2022, 12, 24))   # Thanksgiving / Saturday


def test_failed_reversal_long_after_a_bullish_morning():
    s = _plugin()
    m = _day_market()
    sig = s.signals(m)
    assert len(sig) == 1 and sig[0].side == 1 and sig[0].tag == "afr_long"
    t = pd.Timestamp(sig[0].t, tz="UTC").tz_convert(NY)
    assert (t.hour, t.minute) == (13, 10)                      # the 13:05 candle's close
    b = sig[0].info["b"]
    assert 1.0 < b < 1.3                                       # b = 0.1 × ATR(14) of the 5-minute candles (~11)
    assert sig[0].stop == pytest.approx(20091 - 0.2 - b, abs=0.01)    # lowest BID of the candle − b
    assert s.diag["eligible_days"] == [date(2026, 3, 5).toordinal()]


def test_no_sweep_no_trade_and_the_reclaim_must_hold_at_the_fill():
    assert _plugin().signals(_day_market(sweep=False)) == []
    s = _plugin()
    assert s.signals(_day_market(fill_mid=20093.0)) == []      # next quote back below the reference
    assert any("wrong side" in k for k in s.diag["rejections"])


def test_friction_gate_skips_instead_of_widening():
    s = _plugin()
    assert s.signals(_day_market(spread=1.2)) == []            # (1.2 + 2 × 0.3) / 16.6 > 10%
    assert any("friction" in k for k in s.diag["rejections"])


def test_attribution_variants():
    m = _day_market()
    c10s = _plugin(mode="afr_c10stop").signals(m)
    assert len(c10s) == 1                                      # C10's 1.25 × ATR15 stop from the trigger close (20105)
    assert c10s[0].stop == pytest.approx(20105 - 1.25 * c10s[0].info["a15"], abs=0.02)
    mt = _plugin(mode="c10_matched").signals(m)
    t = pd.Timestamp(mt[0].t, tz="UTC").tz_convert(NY)
    assert len(mt) == 1 and (t.hour, t.minute) == (13, 0)


def test_engine_report_extra_and_lookahead():
    s = _plugin()
    m = _day_market()
    res = engine.simulate(s, m)
    assert len(res["trades"]) == 1
    v = {k: engine.simulate(s.with_params(**ov), m, controls=False)["trades"] for k, ov in s.variants.items()}
    s.signals(m)
    lines = "\n".join(s.compare(m, res["trades"], v))
    assert "Per eligible day" in lines and "AFR − matched C10" in lines
    a = engine.lookahead_audit(s, m, s.signals(m), 5, warm_days=2.5)
    assert a["checked"] == 1 and a["failed"] == 0
