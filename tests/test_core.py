"""Run: python -m pytest -q"""
import asyncio

import pandas as pd
import pytest

from fxagents.broker import OrderRejected, PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.jev import JevScorer
from fxagents.models import Bar, Position
from fxagents.sim import Mgmt, backtest, simulate_outcome, stats, synth_1m, worst_case_after_add
from fxagents.state import LiveState
from fxagents.strategies import BUILTIN, Strategy

CFG = load_config("config.yaml")
TZ = "America/New_York"


def _broker():
    st = LiveState(); st.now = pd.Timestamp("2026-09-28 09:35", tz=TZ)
    return PaperBroker(CFG, st, Bus()), st


def test_entry_without_stop_is_rejected():
    b, st = _broker()
    p = Position("NDQ", 1, "x", None, None, 10, 1.0, st.now)  # type: ignore[arg-type]
    with pytest.raises(OrderRejected):
        asyncio.run(b.open(p, 1, 25000))


def test_stop_wider_than_10pct_rejected():
    b, st = _broker()
    p = Position("NDQ", 1, "x", 22000, 22000, 3000, 1.0, st.now)
    with pytest.raises(OrderRejected):
        asyncio.run(b.open(p, 1, 25000))


def test_stop_wrong_side_rejected():
    b, st = _broker()
    p = Position("NDQ", -1, "x", 24900, 24900, 100, 1.0, st.now)
    with pytest.raises(OrderRejected):
        asyncio.run(b.open(p, 1, 25000))


def test_stop_can_only_move_toward_profit():
    b, st = _broker()
    p = Position("NDQ", 1, "x", 24950, 24950, 50, 1.0, st.now)
    asyncio.run(b.open(p, 2, 25000))
    asyncio.run(b.move_stop(p, 25010))
    with pytest.raises(OrderRejected):
        asyncio.run(b.move_stop(p, 24990))


def test_paper_stop_fill_books_loss():
    b, st = _broker()
    p = Position("SPX", 1, "x", 6590, 6590, 10, 1.0, st.now)
    asyncio.run(b.open(p, 2, 6600))
    asyncio.run(b.on_bar(Bar("SPX", st.now, 6598, 6599, 6585, 6588)))
    assert p.open_qty == 0 and p.realized < 0


def test_pyramid_never_risks_open_profit():
    m = Mgmt()
    # after first target: 50% banked at +1R, stop at +0.1R, add 0.5 at +1R
    assert worst_case_after_add([(0, 0.5), (1.0, 0.5)], 0.5, 0.1) >= 0


def test_simulated_management_matches_rules():
    import numpy as np
    m = Mgmt(rr=1.0)
    # price: entry 100, stop 99 → runs to 103 then collapses
    C = np.array([100, 100.5, 101.2, 102.1, 103.1, 101.0, 99.0])
    O = np.r_[C[0], C[:-1]]
    H, L = np.maximum(O, C) + 0.05, np.minimum(O, C) - 0.05
    flat = np.zeros(len(C), bool)
    r = simulate_outcome(O, H, L, C, 0, 1, 100.0, 99.0, m, flat)
    # 0.5 banked at 1R + runner stopped at +2.1R + adds at 1R/2R stopped at +2.1R
    assert r["steps"] == 3 and r["adds"] == 2 and r["exit_reason"] == "trail_stop"
    assert abs(r["r"] - (0.5 + 0.5 * 2.1 + 0.5 * 1.1 + 0.5 * 0.1)) < 1e-9


def test_strategies_scan_without_lookahead():
    """Signals found on a truncated frame must equal those found on the full frame up to that point."""
    d1 = synth_1m(24500, 0.013, pd.Timestamp("2026-09-07", tz=TZ), 8, 3)
    df = resample_ohlc(d1, "5min")
    cut = int(len(df) * 0.7)
    for cls in BUILTIN.values():
        s = cls()
        full = {(x.i, x.side, round(x.entry, 6), round(x.stop, 6)) for x in s.scan(df) if x.i < cut - 1}
        part = {(x.i, x.side, round(x.entry, 6), round(x.stop, 6)) for x in s.scan(df.iloc[:cut]) if x.i < cut - 1}
        assert full == part, cls.name


def test_backtest_stats_shape():
    d1 = synth_1m(3650, 0.012, pd.Timestamp("2026-09-07", tz=TZ), 8, 5)
    df = resample_ohlc(d1, "5min")
    ctx = Strategy.context(df)
    tr = backtest(BUILTIN["sr_rejection"](), df, ctx, Mgmt.from_cfg(CFG), CFG["sessions"]["entry_windows"], "15:50")
    s = stats(tr)
    assert s["n"] == len(tr) and set(s) >= {"expectancy", "by_hour", "reach"}


def test_jev_response_parsing_with_stub_client():
    from typesafe_sdk import SystemOneResponse

    class Stub:
        async def system_one(self, state, questions):
            answers = {}
            for k, q in questions.items():
                if q.type == "score":
                    answers[k] = {"type": "score", "score": 3.0, "confidence": 0.8,
                                  "legend": {i: c for i, c in enumerate(q.criteria)},
                                  "probabilities": {0: 0.0, 1: 0.05, 2: 0.15, 3: 0.6, 4: 0.2}}
                else:
                    answers[k] = {"type": "noul", "noul": 0.9}
            return SystemOneResponse.model_validate({"model": "jev-stub", "usage": {}, "answers": answers})

    st = LiveState(); st.now = pd.Timestamp("2026-09-28 09:00", tz=TZ)
    j = JevScorer(CFG, st, Bus())
    j.live, j.client = True, Stub()
    stats_ = {"n": 40, "win_rate": 0.5, "expectancy": 0.2, "pf": 1.4, "max_dd_r": 3}
    res = asyncio.run(j.rate_strategies("NDQ", 9, {"adx": 25}, {
        "ict_fvg_sweep@v1": {"name": "ict_fvg_sweep@v1", "overall": stats_, "this_hour": {}}}))
    r = res["by_strategy"]["ict_fvg_sweep@v1"]
    assert res["source"] == "jev" and abs(r["value"] - 0.7375) < 1e-6 and r["confidence"] == 0.8
    assert res["trade_ok"]["value"] == 0.9
    assert st.decisions[0]["kind"] == "strategy_rating"


# ── bias / news / 15m ─────────────────────────────────────────────────────────
def test_bias_frame_is_causal():
    from fxagents.bias import bias_frame
    import numpy as np
    d1 = synth_1m(24500, 0.013, pd.Timestamp("2026-08-03", tz=TZ), 35, 11)
    h1 = resample_ohlc(d1, "1h")
    when = resample_ohlc(d1, "5min").index + pd.Timedelta("5min")
    full = bias_frame(h1, when)["score"].to_numpy()
    cut = len(when) // 2
    part = bias_frame(h1[h1.index < when[cut]], when[:cut])["score"].to_numpy()
    assert np.allclose(full[:cut], part)


def test_bias_rule_labels():
    from fxagents.bias import rule_check
    assert rule_check(1, 0.6, 0.25) == "aligned"
    assert rule_check(-1, 0.6, 0.25) == "counter"
    assert rule_check(1, 0.1, 0.25) == "neutral"


def test_backtest_respects_hard_bias_rule():
    import numpy as np
    d1 = synth_1m(3650, 0.012, pd.Timestamp("2026-09-07", tz=TZ), 8, 5)
    df = resample_ohlc(d1, "5min")
    ctx = Strategy.context(df)
    bearish = np.full(len(df), -1.0)
    tr = backtest(BUILTIN["sr_rejection"](), df, ctx, Mgmt.from_cfg(CFG), CFG["sessions"]["entry_windows"], "15:50",
                  bias_score=bearish, min_align=0.25)
    assert all(t["side"] == -1 for t in tr)


def test_news_calendar_windows_and_event_day():
    from fxagents.news import NewsCalendar
    cal = NewsCalendar(CFG)
    cal.load([{"title": "Non-Farm Employment Change", "country": "USD", "date": "2026-10-02T08:30:00-04:00", "impact": "High"},
              {"title": "Final GDP q/q", "country": "USD", "date": "2026-09-30T08:30:00-04:00", "impact": "High"},
              {"title": "BoJ thing", "country": "JPY", "date": "2026-10-02T08:30:00-04:00", "impact": "High"}], "test")
    assert len(cal.events) == 2                                             # JPY filtered out
    nfp = pd.Timestamp("2026-10-02 08:30", tz=TZ)
    assert cal.blocked(nfp - pd.Timedelta("29min"))["tier"] == "tier1"      # 30-min pre window
    assert cal.blocked(nfp - pd.Timedelta("31min")) is None
    assert cal.blocked(pd.Timestamp("2026-09-30 08:40", tz=TZ))["tier"] == "high"   # 15-min post window
    assert cal.pre_actions(nfp - pd.Timedelta("3min"))[0]["action"] == "protect"
    assert cal.risk_mult(pd.Timestamp("2026-10-02 13:00", tz=TZ)) == 0.5 and cal.risk_mult(pd.Timestamp("2026-10-01 13:00", tz=TZ)) == 1.0


def test_strategies_exist_on_5m_and_15m():
    from fxagents.strategies import default_specs, build_strategy
    ids = {build_strategy(s).id for s in default_specs()}
    assert "smc_order_block:15m@v1" in ids and "stoic_sbs:5m@v1" in ids and len(ids) == 2 * len(BUILTIN)


def test_barstore_views_refresh_after_store_is_full():
    from fxagents.data import BarStore
    d1 = synth_1m(3650, 0.012, pd.Timestamp("2026-09-07", tz=TZ), 3, 2)
    st = BarStore(TZ, max_days=1)
    st.load_history("X", d1.iloc[:1440])
    before = st.tf("X", "5min").index[-1]
    for ts, r in d1.iloc[1440:1500].iterrows():
        st.append(Bar("X", ts, r.open, r.high, r.low, r.close))
    assert len(st.m1("X")) == 1440 and st.tf("X", "5min").index[-1] > before
