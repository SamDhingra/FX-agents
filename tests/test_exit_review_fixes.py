"""Nov 9 2026 (Astra exit review): C10's 15:45 deadline comes before a target touch, the H1-trend trail survives a
restart, and frozen rule paper books hold through the pre-news exit."""
import asyncio
import copy

import pandas as pd

from fxagents.agents.c10_trader import STRATEGY, C10Trader
from fxagents.agents.core import Ctx
from fxagents.agents.trading import PositionManagerAgent
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.models import Bar, Leg, Position
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


class FakeBroker:
    """close(limit=…) on a resting full target: `filled` decides whether OANDA already filled it."""
    def __init__(self, filled=False):
        self.filled, self.calls = filled, []

    async def close(self, pos, price, limit=None):
        self.calls.append(("limit" if limit is not None else "market", price))
        if limit is not None and (pos.meta.get("tp") or {}).get("full") and not self.filled:
            return None                                   # resting target not filled: pending
        return price


def c10_pos(target=25100.0):
    t0 = pd.Timestamp("2026-11-03 13:00", tz=TZ)
    p = Position("NDQ", 1, STRATEGY, 24950.0, 24950.0, 50.0, 2.0, t0, reason="t")
    p.add_leg(Leg(1.0, 25000.0, t0, "initial"))
    p.meta.update(external_mgmt=True, target=target, tp={"full": "oid1"})
    return p


def c10_run(bar_time, high, filled=False):
    st = LiveState()
    broker = FakeBroker(filled)
    ctx = Ctx(copy.deepcopy(CFG), Bus(), st, None, broker, None, None, None)
    tr = C10Trader.__new__(C10Trader)
    tr.ctx, tr.cfg, tr.state, tr.bus, tr.tz = ctx, ctx.cfg, st, ctx.bus, TZ
    tr.now = lambda: pd.Timestamp(bar_time, tz=TZ) + pd.Timedelta("1min")
    p = c10_pos()
    st.positions[p.id] = p
    bar = Bar("NDQ", pd.Timestamp(bar_time, tz=TZ), 25090.0, high, 25080.0, 25085.0, 1.0)
    asyncio.run(tr.manage("NDQ", bar))
    return p, broker


def test_deadline_wins_over_an_unfilled_target_touch():
    p, b = c10_run("2026-11-03 15:44", high=25101.0)            # the 15:44 bar closes at 15:45; mid touches target
    assert b.calls == [("limit", 25100.0), ("market", 25085.0)]
    assert p.status == "closed" and p.exit_reason == "time_1545"


def test_deadline_books_a_target_that_already_filled():
    p, b = c10_run("2026-11-03 15:44", high=25101.0, filled=True)
    assert b.calls == [("limit", 25100.0)] and p.exit_reason == "target"


def test_before_the_deadline_a_touch_only_tries_the_target():
    p, b = c10_run("2026-11-03 14:10", high=25101.0)
    assert b.calls == [("limit", 25100.0)] and p.status == "open"


def test_h1_trail_state_lives_on_the_position():
    from fxagents.agents import h1_trend_trader as H
    src = open(H.__file__).read()
    assert 'pos.meta.setdefault("h1_trail", {})' in src and "self.trail" not in src
    st = {}
    from fxagents.astra_cfd import h1_trail
    h1_trail(st, 102.0, 1.0, 100.0, 1.0, 1, 0.01)              # +2R close → armed
    restored = dict(st)                                         # what the runtime file round-trips (JSON-safe)
    assert restored == {"best": 102.0, "armed": True}
    assert h1_trail(restored, 101.5, 1.0, 100.0, 1.0, 1, 0.01) == 100.0   # same trail as an uninterrupted run


def _pm(book_key=None):
    st = LiveState()
    ctx = Ctx(copy.deepcopy(CFG), Bus(), st, None, None, None, None, None)
    if book_key:
        ctx.book_key = book_key
    pm = PositionManagerAgent(ctx); pm.start()
    closed = []

    async def close(pos, price, reason, limit=False):
        closed.append((pos.strategy, reason))
        return True
    pm.close = close
    pm.now = lambda: pd.Timestamp("2026-11-06 08:28", tz=TZ)
    for strat, ext in (("c10_afternoon", True), ("smc_mss:5m@pb", False)):
        p = c10_pos()
        p.strategy = strat
        if not ext:
            p.meta.pop("external_mgmt")
        st.positions[p.id] = p
        st.last_prices["NDQ"] = 24990.0                        # under water: the close branch
    asyncio.run(pm.on_pre_news({"event": "NFP", "action": "close"}))
    return closed, st


def test_pre_news_leaves_frozen_rule_paper_books_alone():
    closed, st = _pm("c10_afternoon")
    assert closed == [("smc_mss:5m@pb", "pre-news: NFP")]
    skipped = [p for p in st.positions.values() if p.strategy == "c10_afternoon"][0]
    assert skipped.events[-1]["kind"] == "pre_news_skipped"


def test_pre_news_still_protects_the_practice_account():
    closed, _ = _pm(None)
    assert sorted(closed) == [("c10_afternoon", "pre-news: NFP"), ("smc_mss:5m@pb", "pre-news: NFP")]
