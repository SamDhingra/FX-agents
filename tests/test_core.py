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
    p = Position("US30", 1, "x", 6590, 6590, 10, 1.0, st.now)
    asyncio.run(b.open(p, 2, 6600))
    asyncio.run(b.on_bar(Bar("US30", st.now, 6598, 6599, 6585, 6588)))
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


# ── cloud / container behaviour ───────────────────────────────────────────────
def test_env_overrides_for_containers(monkeypatch):
    monkeypatch.setenv("IB_HOST", "ib-gateway")
    monkeypatch.setenv("IB_PORT", "4004")
    monkeypatch.setenv("FX_MODE", "paper")
    c = load_config("config.yaml")
    assert c["ibkr"]["host"] == "ib-gateway" and int(c["ibkr"]["port"]) == 4004 and c["mode"] == "paper"


def test_monitor_flattens_orphan_broker_positions():
    import time
    from fxagents.agents.core import Ctx
    from fxagents.agents.ops import MonitorAgent

    class FakeBroker:
        def __init__(self): self.flattened = []
        async def broker_positions(self): return {"NDQ": 2.0}
        async def unprotected(self): return []
        async def flatten_orphan(self, sym, qty): self.flattened.append((sym, qty))

    st = LiveState(); st.now = pd.Timestamp("2026-09-28 10:00", tz=TZ)
    st.equity = st.day_start_equity = st.equity_peak = 100000
    fb = FakeBroker()
    ctx = Ctx(CFG, Bus(), st, None, fb, None, None, None)
    m = MonitorAgent(ctx); m.start()
    asyncio.run(m.on_clock(st.now))          # first sighting: could be a fill race → no action
    assert fb.flattened == []
    m._last_check = time.time() - 31
    asyncio.run(m.on_clock(st.now))          # second sighting → flatten
    assert fb.flattened == [("NDQ", 2.0)]


def test_notification_title_is_a_legal_http_header():
    from fxagents.agents.ops import header_title
    assert header_title("⚠ FX-Agents") == "FX-Agents"
    assert header_title("▶ LONG NDQ") == "LONG NDQ"
    assert header_title("✅ NDQ closed") == "NDQ closed"
    assert header_title("🔒 NDQ") == "NDQ" and header_title("🧠") == "fx-agents"
    import httpx
    httpx.Headers({"Title": header_title("⚠ FX-Agents")}).raw       # would raise on a leading space


def test_monitor_ignores_event_driven_agents_and_does_not_repeat_alerts():
    import time
    from fxagents.agents.core import Ctx
    from fxagents.agents.ops import MonitorAgent

    class FakeBroker:
        async def broker_positions(self): return {}
        async def unprotected(self): return []

    cfg = dict(CFG); cfg["mode"] = "paper"
    st = LiveState(); st.now = pd.Timestamp("2026-09-30 10:00", tz=TZ)          # a Wednesday
    st.equity = st.day_start_equity = st.equity_peak = 100000
    ctx = Ctx(cfg, Bus(), st, None, FakeBroker(), None, None, None)
    m = MonitorAgent(ctx); m.start()
    sent = []
    ctx.bus.subscribe("alert", lambda a: sent.append(a["msg"]))
    old = time.time() - 900
    for name in ("risk", "trader", "notifier", "selector"):
        st.heartbeats[name] = old                    # quiet on purpose → no alert
    st.heartbeats["bias"] = old                      # clock-driven agent that went quiet → alert
    for _ in range(3):                               # three checks 30 s apart: only one alert
        m._last_check = time.time() - 31
        asyncio.run(m.on_clock(st.now))
    assert [x for x in sent if "silent" in x] == [x for x in sent if "agent bias silent" in x]
    assert len([x for x in sent if "agent bias silent" in x]) == 1
    assert not [x for x in sent if any(n in x for n in ("risk", "trader", "notifier", "selector"))]


def test_replay_resumes_after_max_drawdown_halt_but_live_does_not():
    from fxagents.agents.core import Ctx
    from fxagents.agents.ops import MonitorAgent

    class FakeBroker:
        async def broker_positions(self): return {}
        async def unprotected(self): return []

    class J:
        def __init__(self): self.log = []
        def learner(self, ts, msg, data=None): self.log.append(msg)

    for replay in (True, False):
        cfg = dict(CFG); cfg["mode"] = "sim"
        if replay:
            cfg["replay"] = {"days": 5}
        st = LiveState(); t = pd.Timestamp("2026-09-29 10:00", tz=TZ)
        st.equity_peak = 100000; st.equity = st.day_start_equity = 93000   # 7% under the peak
        ctx = Ctx(cfg, Bus(), st, None, FakeBroker(), J(), None, None)
        m = MonitorAgent(ctx); m.start()
        asyncio.run(m.on_clock(t))
        assert not st.trading_enabled and st.halt_reason.startswith("max drawdown")
        asyncio.run(m.on_clock(t + pd.Timedelta(days=1)))                  # next trading day
        assert st.trading_enabled is replay
        if replay:
            assert st.equity_peak == 93000 and ctx.journal.log[0].startswith("KILL SWITCH")


def test_jev_advisory_gate_sizes_instead_of_blocking():
    from fxagents.agents.trading import jev_gate, jev_gate_why
    jc = dict(CFG["jev"]); jc["signal_gate"] = "enforce"
    assert not jev_gate({"quality": 0.62, "confidence": 0.3}, dict(jc))        # confidence blocks
    assert "confidence 0.30" in jev_gate_why({"quality": 0.62, "confidence": 0.3}, jc)
    jc["signal_gate"] = "advisory"
    lo, mid, hi = ({"quality": q, "confidence": 0.2} for q in (0.1, 0.5, 0.9))
    assert jev_gate(lo, jc) and jev_gate(mid, jc) and jev_gate(hi, jc)       # nothing blocked
    assert lo["size_mult"] == 0.5 and mid["size_mult"] == 0.75 and hi["size_mult"] == 1.0
    jc["advisory_floor"] = 0.2
    assert not jev_gate({"quality": 0.1, "confidence": 0.9}, jc)


def test_pnl_after_partial_then_add_is_not_overbooked():
    """Long 1 @100, bank half @110, add 0.5 @110, close all @110 → +10 (5 from the partial, 5 on the rest)."""
    from fxagents.broker import PaperBroker
    from fxagents.models import Position
    cfg = dict(CFG); cfg["mode"] = "sim"
    st = LiveState(); st.now = pd.Timestamp("2026-09-30 10:00", tz=TZ)
    br = PaperBroker(cfg, st, Bus()); br._slip = lambda s, side: 0.0; br.commission = lambda s, q: 0.0
    br.mult = lambda s: 1.0; br.round_px = lambda s, px: px; br.guard_entry = lambda *a: None
    pos = Position("XAUUSD", 1, "t", 90.0, 90.0, 10.0, 1.0, st.now)
    asyncio.run(br.open(pos, 1.0, 100.0))
    asyncio.run(br.reduce(pos, 0.5, 110.0))
    asyncio.run(br.add(pos, 0.5, 110.0))
    assert pos.avg_entry == 105.0 and pos.open_qty == 1.0
    asyncio.run(br.close(pos, 110.0))
    assert abs(pos.realized - 10.0) < 1e-9


def test_bias_frame_has_no_look_ahead():
    """The bias at a decision time is the same whether or not later hours exist."""
    from fxagents.bias import bias_frame
    from fxagents.indicators import resample_ohlc
    for seed in (1, 4):                       # price paths where the old whole-history swing reduction leaked
        m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-05-01", tz=TZ), 45, seed, TZ)
        h1 = resample_ohlc(m1, "1h")
        when = h1.index[150:] + pd.Timedelta("1h")
        full = bias_frame(h1, when)
        for t in when[::3]:
            part = bias_frame(h1[h1.index + pd.Timedelta("1h") <= t], pd.DatetimeIndex([t]))
            assert part["score"].iloc[0] == full.loc[t, "score"], (seed, t)
