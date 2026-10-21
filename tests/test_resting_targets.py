"""Audit F5: targets rest at OANDA as reduce-only LIMIT orders, so they fill at the level (not as a market order after
a candle touched it). And C10 trading on the practice account with the account's limits."""
from __future__ import annotations

import asyncio
import copy

import pandas as pd
import pytest

from fxagents.agents.core import Ctx
from fxagents.models import Bar
from tests.test_oanda import pos, run, setup


async def _boot(fake, feed, b):
    await feed.qualify(); await b.connect()


def test_partial_target_rests_and_fills_at_the_level():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await _boot(fake, feed, b)
        p = pos()                                                  # long NDQ, stop 24400, entry 24500 → 1R = 24600
        await b.open(p, 4, 24500)
        tp = await b.place_target(p, 24600.0, 2, "1")
        assert tp and fake.limits[tp["id"]]["units"] == "-2" and fake.limits[tp["id"]]["price"] == "24600.0"
        fake.prices["NAS100_USD"] = 24599.0
        assert await b.reduce(p, 2, 24599.0, limit=24600.0) is None          # mid touched, bid not: still resting
        assert p.open_qty == 4
        fake.touch("NAS100_USD", 24603.0)                                  # bid reaches it → fills AT 24600
        await bus.publish("clock", st.now)                                 # the clock check leaves it for the manager
        assert p.open_qty == 4 and p.meta["step_hit"] == 1
        px = await b.reduce(p, 2, 24603.0, limit=24600.0)
        return p, px
    p, px = run(go())
    assert px == pytest.approx(24600.0) and p.open_qty == pytest.approx(2)
    assert p.realized == pytest.approx(2 * 100)                          # booked at the level, not at 24603's market
    assert any(e["kind"] == "limit_exit" and e.get("resting") for e in p.events)


def test_full_target_fill_is_booked_as_a_target_and_targets_never_outlive_the_position():
    cfg, fake, c, st, bus, feed, b = setup()
    seen = []
    bus.subscribe("stop_filled", lambda ev: seen.append(ev))

    async def go():
        await _boot(fake, feed, b)
        p = pos()
        await b.open(p, 2, 24500)
        await b.place_target(p, 24700.0, 2, "full")
        fake.touch("NAS100_USD", 24700.0)
        await bus.publish("clock", st.now)
        q = pos()                                                    # a second trade: stopped, its target cancelled
        await b.open(q, 1, 24700)
        tq = await b.place_target(q, 24900.0, 1, "full")
        for t in [t for t in fake.open_trades()]:
            fake.hit_stop(t["id"])
        await bus.publish("clock", st.now)
        return p, q, tq
    p, q, tq = run(go())
    assert seen[0]["position"] is p and seen[0]["reason"] == "target" and seen[0]["price"] == pytest.approx(24700.0)
    assert seen[1]["position"] is q and "reason" not in seen[1]
    assert fake.limits[tq["id"]]["state"] == "CANCELLED"


def test_market_close_cancels_the_resting_target_first():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await _boot(fake, feed, b)
        p = pos()
        await b.open(p, 2, 24500)
        tp = await b.place_target(p, 24600.0, 1, "1")
        await b.close(p, 24510.0)                                    # flatten / time exit
        return tp
    tp = run(go())
    assert fake.limits[tp["id"]]["state"] == "CANCELLED"


def test_a_stale_target_from_an_old_position_is_swept_before_a_new_entry():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await _boot(fake, feed, b)
        old = pos()
        await b.open(old, 1, 24500)
        tp = await b.place_target(old, 24600.0, 1, "full")
        b.managed.clear()                                            # e.g. a crash lost track of it
        new = pos()
        await b.open(new, 1, 24500)
        return tp
    tp = run(go())
    assert fake.limits[tp["id"]]["state"] == "CANCELLED"


def test_resting_targets_off_keeps_the_old_exit():
    cfg, fake, c, st, bus, feed, b = setup()
    b.resting_targets = False

    async def go():
        await _boot(fake, feed, b)
        p = pos()
        await b.open(p, 2, 24500)
        assert await b.place_target(p, 24600.0, 1, "1") is None
        fake.prices["NAS100_USD"] = 24601.0
        return await b.reduce(p, 1, 24601.0, limit=24600.0)
    assert run(go()) == pytest.approx(24601.0)                           # market after the touch


def test_position_manager_places_the_first_target_on_open():
    from fxagents.agents.trading import PositionManagerAgent
    cfg, fake, c, st, bus, feed, b = setup()

    class J:
        def add_signal(self, s): pass
    ctx = Ctx(cfg, bus, st, None, b, J(), None, None)
    pm = PositionManagerAgent(ctx); pm.start()

    async def go():
        await _boot(fake, feed, b)
        p = pos()
        await b.open(p, 4, 24500)
        p.risk_per_unit = 100.0
        st.positions[p.id] = p
        await bus.publish("position_opened", p)
        return p
    p = run(go())
    tp = p.meta["tp"]["1"]
    part = cfg["management"]["partial_at_target"] * 4
    assert tp["level"] == pytest.approx(24600.0) and tp["qty"] == pytest.approx(part)


# ── C10 on the account ───────────────────────────────────────────────────
def _c10(held=(), **ca):
    from fxagents.agents.c10_trader import C10Trader
    cfg, fake, c, st, bus, feed, b = setup()
    cfg["c10_account"] = {"enabled": True, "symbols": ["NDQ"], "risk_pct": 0.0025, **ca}
    st.equity = 100000.0
    rows = []

    class J:
        def add_signal(self, s): rows.append(s)
        def trades(self, **kw): return []
    ctx = Ctx(cfg, bus, st, None, b, J(), None, None)
    tr = C10Trader(ctx, on_account=True)
    from fxagents.models import Position
    for k, (sym, side) in enumerate(held):
        p = Position(sym, side, f"h{k}", 1.0, 1.0, 1.0, 1.0, st.now)
        p.add_leg(__import__("fxagents.models", fromlist=["Leg"]).Leg(1.0, 2.0, st.now, "initial"))
        st.positions[p.id] = p
    return cfg, fake, b, st, tr, rows, feed


def test_c10_on_account_trades_real_orders_with_a_resting_target():
    cfg, fake, b, st, tr, rows, feed = _c10()
    tr.start()
    sig = {"side": 1, "close": 24500.0, "atr": 40.0, "er": 0.6, "prev_close": 24300.0, "open_0930": 24400.0,
           "close_1000": 24420.0}

    async def go():
        await _boot(fake, feed, b)
        st.last_prices["NDQ"] = 24500.0
        await tr.enter("NDQ", sig, Bar("NDQ", st.now, 24500, 24501, 24499, 24500, 1))
    run(go())
    assert tr.name == "c10_trader" and tr.risk_pct == 0.0025
    p = next(iter(st.positions.values()))
    assert p.strategy == "c10_afternoon" and len(fake.open_trades()) == 1
    risk = p.risk_per_unit * p.open_qty * float(cfg["instruments"]["NDQ"]["multiplier"])
    assert risk <= 100000 * 0.0025 + 1e-6
    tp = p.meta["tp"]["full"]
    assert tp["level"] == pytest.approx(p.meta["target"], abs=0.1) and fake.limits[tp["id"]]["state"] == "PENDING"


def test_c10_on_account_respects_the_index_cap():
    cfg, fake, b, st, tr, rows, feed = _c10(held=[("US30", 1)])
    tr.start()
    sig = {"side": 1, "close": 24500.0, "atr": 40.0, "er": 0.6, "prev_close": 24300.0, "open_0930": 24400.0,
           "close_1000": 24420.0}

    async def go():
        await _boot(fake, feed, b)
        st.last_prices["NDQ"] = 24500.0
        await tr.enter("NDQ", sig, Bar("NDQ", st.now, 24500, 24501, 24499, 24500, 1))
    run(go())
    assert rows[-1]["action"] == "rejected" and "index group" in rows[-1]["why"] and not fake.open_trades()


def test_c10_not_on_a_real_money_account_by_default(monkeypatch):
    import main as M
    src = open(M.__file__).read()
    assert 'cfg["mode"] == "live" and not ca.get("allow_live")' in src
