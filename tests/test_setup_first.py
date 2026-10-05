"""Setup-first selection and the shadow book."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pandas as pd
import pytest

from fxagents.agents.core import Ctx
from fxagents.agents.setup_first import ShadowBroker, ShadowState, SetupFirstTrader, build_shadow
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.journal import Journal
from fxagents.models import Position
from fxagents.sim import synth_1m
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = "America/New_York"
NOW = pd.Timestamp("2026-09-30 09:00", tz=TZ)        # Wednesday, inside the 08:30–11:30 window


class FakeStrategy:
    def __init__(self, sid, side=1):
        self.id, self.tf, self.rr, self.side = sid, "5min", 1.0, side
        self.family, self.tf_label, self.description = sid.split(":")[0], "5m", ""

    def scan(self, df, ctx):
        last = len(df) - 1
        px = float(df["close"].iloc[-1])
        yield SimpleNamespace(i=last, side=self.side, entry=px, stop=px - self.side * px * 0.002,
                              reason="test", features={"risk_atr": 1.0}, structural_target=None)


class FakeBook:
    def __init__(self, strategies):
        self.s = {s.id: s for s in strategies}

    def live(self):
        return list(self.s.values())

    def get(self, sid):
        return self.s.get(sid)


class FakeStore:
    def __init__(self):
        m1 = synth_1m(25000, 0.01, NOW - pd.Timedelta(days=3), 3, 7, TZ)
        self.df = resample_ohlc(m1[m1.index < NOW], "5min")

    def tf(self, sym, tf, complete_only=True):
        return self.df


class FakeJev:
    live = False
    source = "stub"

    def __init__(self, grades):
        self.grades, self.asked = grades, []

    async def rate_signal(self, info):
        self.asked.append(info)
        q = self.grades[info["strategy"]]
        return {"quality": q, "confidence": 0.8, "htf_aligned": 0.8, "source": "stub"}


def make(tmp_path, grades, strategies, bias_score=1.0):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = "paper"
    cfg["jev"]["signal_gate"] = "enforce"          # these tests are about the gate; don't depend on the server's config
    st = LiveState(mode="paper")
    st.now = NOW
    st.bias["NDQ"] = {"score": bias_score, "suspended": False, "h1": 1, "label": "BULLISH", "in_doubt": False}
    bus = Bus()
    ctx = Ctx(cfg, bus, st, FakeStore(), None, Journal(str(tmp_path / "j.sqlite")), FakeJev(grades),
              FakeBook(strategies), None)
    t = SetupFirstTrader(ctx)
    t.start()
    requests = []

    async def risk(req):   # stand-in for Risk: open a position so "taken" is detected
        requests.append(req)
        sig = req["signal"]
        p = Position(sig.symbol, sig.side, sig.strategy, sig.stop, sig.stop, abs(sig.entry - sig.stop), 1.0, NOW)
        st.positions[p.id] = p
    bus.subscribe("entry_request", risk)
    return ctx, t, requests


def test_scans_every_strategy_and_takes_only_the_best_graded(tmp_path):
    strats = [FakeStrategy("smc_ifvg:5m@v1"), FakeStrategy("ict_ote:5m@v1"), FakeStrategy("sr_rejection:5m@v1")]
    ctx, t, req = make(tmp_path, {"smc_ifvg:5m@v1": 0.6, "ict_ote:5m@v1": 0.9, "sr_rejection:5m@v1": 0.7}, strats)
    asyncio.run(t.on_signal_bar({"symbol": "NDQ", "tf": "5min", "ts": NOW}))
    assert len(ctx.jev.asked) == 3                                  # all three setups were seen and graded
    assert [r["signal"].strategy for r in req] == ["ict_ote:5m@v1"]   # only the best one traded
    why = {r["strategy"]: r["why"] for r in ctx.journal.signals(10)}
    assert why["smc_ifvg:5m@v1"] == why["sr_rejection:5m@v1"] == "a better setup was taken on this bar"
    assert "setup_this_hour_12d" in ctx.jev.asked[0] and "setup_today" in ctx.jev.asked[0]


def test_hard_bias_rule_filters_before_any_jev_call(tmp_path):
    strats = [FakeStrategy("smc_ifvg:5m@v1", side=-1)]             # short against a bullish bias
    ctx, t, req = make(tmp_path, {"smc_ifvg:5m@v1": 0.95}, strats)
    asyncio.run(t.on_signal_bar({"symbol": "NDQ", "tf": "5min", "ts": NOW}))
    assert not ctx.jev.asked and not req
    assert ctx.journal.signals(1)[0]["action"] == "filtered"


def test_weak_grades_are_skipped_and_nothing_scans_outside_windows(tmp_path):
    strats = [FakeStrategy("smc_ifvg:5m@v1")]
    ctx, t, req = make(tmp_path, {"smc_ifvg:5m@v1": 0.2}, strats)
    asyncio.run(t.on_signal_bar({"symbol": "NDQ", "tf": "5min", "ts": NOW}))
    assert not req and ctx.journal.signals(1)[0]["action"] == "skipped"
    ctx.state.now = pd.Timestamp("2026-09-30 12:10", tz=TZ)         # between windows
    n = len(ctx.jev.asked)
    asyncio.run(t.on_signal_bar({"symbol": "NDQ", "tf": "5min",
                                 "ts": pd.Timestamp("2026-09-30 12:10", tz=TZ)}))
    assert len(ctx.jev.asked) == n


def test_shadow_state_shares_market_context_but_owns_positions():
    main = LiveState(mode="paper")
    main.bias["NDQ"] = {"score": 1.0}
    main.last_prices["NDQ"] = 25000.0
    sh = ShadowState(main, mode="paper")
    assert sh.bias["NDQ"]["score"] == 1.0 and sh.last_prices["NDQ"] == 25000.0
    main.news = [{"title": "CPI"}]                                  # reassigned on the real state → visible
    assert sh.news == [{"title": "CPI"}]
    sh.positions["x"] = "shadow-only"
    sh.equity = 123.0
    assert "x" not in main.positions and main.equity == 0.0


def test_shadow_fills_pay_half_the_spread_each_way():
    cfg = copy.deepcopy(CFG)
    st = LiveState()
    st.now = NOW
    b = ShadowBroker(cfg, st, Bus(), {"NDQ": 2.0})
    p = Position("NDQ", 1, "x", 24900.0, 24900.0, 100.0, 1.0, NOW)
    assert asyncio.run(b.open(p, 1, 25000.0)) == 25001.0            # long pays the ask side
    assert asyncio.run(b.close(p, 25100.0)) == 25099.0              # and the bid side on exit


def test_build_shadow_is_isolated_from_the_real_book(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = "paper"
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    cfg["shadow"].pop("db_path", None)               # the default path is what's under test
    st = LiveState(mode="paper")
    st.now = NOW
    real_broker = PaperBroker(cfg, st, Bus())
    main = Ctx(cfg, Bus(), st, FakeStore(), real_broker, Journal(cfg["storage"]["db_path"]), FakeJev({}), FakeBook([]), None)
    sctx, agents, feed = build_shadow(main, 70000.0)
    assert sctx.broker is not real_broker and isinstance(sctx.broker, ShadowBroker)
    assert sctx.bus is not main.bus and sctx.journal.path.endswith("journal_shadow.sqlite")
    assert asyncio.run(sctx.broker.equity()) == pytest.approx(70000.0)
    assert {a.name for a in agents} >= {"trader", "risk", "position_manager", "journal", "monitor"}


def test_watch_only_instrument_is_rejected_by_risk(tmp_path):
    from fxagents.agents.trading import RiskAgent
    from fxagents.models import Signal
    cfg = copy.deepcopy(CFG); cfg["mode"] = "paper"
    cfg["instruments"]["SPX"]["trade"] = False
    st = LiveState(mode="paper"); st.now = NOW; st.equity = 70000
    ctx = Ctx(cfg, Bus(), st, FakeStore(), None, Journal(str(tmp_path / "j.sqlite")), None, None, None)
    r = RiskAgent(ctx); r.start()
    sig = Signal("SPX", "smc_ifvg:5m@v1", 1, 6500.0, 6490.0, NOW, "test", {})
    rec = {"ts": NOW.isoformat(), "symbol": "SPX", "strategy": sig.strategy, "side": "LONG", "entry": 6500.0, "stop": 6490.0}
    asyncio.run(r.on_request({"signal": sig, "grade": {"quality": 0.9, "confidence": 0.9}, "record": rec}))
    s = ctx.journal.signals(1)[0]
    assert s["action"] == "rejected" and s["why"].startswith("instrument off") and not st.positions


def test_shadow_broker_fills_like_oanda():
    """Stops trigger on the bid (longs), limit exits fill at market on the far side of the spread."""
    cfg = copy.deepcopy(CFG); cfg["mode"] = "paper"
    st = LiveState(mode="paper"); st.now = NOW
    br = ShadowBroker(cfg, st, Bus(), {"XAUUSD": 0.4})
    br.round_px = lambda s, px: round(px, 3)
    br.mult = lambda s: 1.0; br.commission = lambda s, q: 0.0
    pos = Position("XAUUSD", 1, "t", 99.0, 99.0, 1.0, 1.0, NOW)
    st.last_prices["XAUUSD"] = 100.0
    asyncio.run(br.open(pos, 1.0, 100.0))
    assert pos.legs[0].price == 100.2                                  # ask
    from fxagents.models import Bar
    asyncio.run(br.on_bar(Bar("XAUUSD", NOW, 100.0, 100.5, 99.15, 100.1, 1)))   # mid low 99.15 > stop, bid 98.95 < stop
    assert pos.open_qty == 0 and abs(pos.realized - (99.0 - 100.2)) < 1e-9
    pos2 = Position("XAUUSD", 1, "t2", 99.0, 99.0, 1.0, 1.0, NOW)
    asyncio.run(br.open(pos2, 1.0, 100.0))
    st.last_prices["XAUUSD"] = 101.0
    px = asyncio.run(br.close(pos2, 101.2, limit=101.2))              # target level 101.2, market is 101.0
    assert px == 100.8                                                 # bid at market, not the limit
