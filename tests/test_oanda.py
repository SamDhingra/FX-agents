"""OANDA adapter against an in-memory fake of the v20 API (no network)."""
from __future__ import annotations

import asyncio
import copy

import pandas as pd
import pytest

from fxagents.agents.trading import floor_step, qty_rules, round_step
from fxagents.broker import OrderRejected
from fxagents.bus import Bus
from fxagents.config import apply_broker, load_config
from fxagents.models import Position
from fxagents.oanda import OandaBroker, OandaClient, OandaFeed
from fxagents.state import LiveState
from tests.fake_oanda import ACCT, TOKEN, FakeOanda

BASE = load_config("config.yaml")


def setup(**kw):
    cfg = copy.deepcopy(BASE)
    cfg["mode"], cfg["broker"] = "paper", "oanda"
    cfg.pop("_broker_applied", None)
    apply_broker(cfg)
    fake = FakeOanda(**kw)
    client = OandaClient(TOKEN, ACCT, "practice", transport=fake.transport())
    st, bus = LiveState(mode="paper"), Bus()
    st.now = pd.Timestamp.now(tz="America/New_York")
    feed = OandaFeed(cfg, bus, st, client)
    broker = OandaBroker(cfg, st, bus, client, feed)
    return cfg, fake, client, st, bus, feed, broker


def pos(sym="NDQ", side=1, stop=24400.0):
    return Position(sym, side, "smc_ifvg:5m@v1", stop, stop, abs(24500 - stop), 1.0, pd.Timestamp.now(tz="America/New_York"))


def run(coro):
    return asyncio.run(coro)


def test_apply_broker_swaps_instruments_only_for_paper_live():
    cfg = copy.deepcopy(BASE)
    cfg["mode"], cfg["broker"] = "sim", "oanda"
    apply_broker(cfg)
    assert cfg["instruments"]["NDQ"]["multiplier"] == 2            # sim keeps the futures spec
    cfg["mode"] = "paper"
    apply_broker(cfg)
    ndq = cfg["instruments"]["NDQ"]
    assert ndq["multiplier"] == 1 and ndq["oanda_instrument"] == "NAS100_USD" and ndq["commission_per_unit"] == 0
    with pytest.raises(SystemExit):
        bad = copy.deepcopy(BASE); bad["broker"] = "etrade"; apply_broker(bad)


def test_qty_helpers_support_fractional_units():
    assert qty_rules({}) == (1.0, 1.0)
    assert qty_rules({"qty_step": 0.1, "min_units": 0.1}) == (0.1, 0.1)
    assert floor_step(2.37, 0.1) == 2.3 and floor_step(2.0, 1) == 2 and floor_step(0.3, 0.1) == 0.3
    assert round_step(1.25, 0.1) in (1.2, 1.3)


def test_qualify_reads_precision_and_history_pages():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify()
        await feed.start()
        await c.aclose()
    run(go())
    ndq = cfg["instruments"]["NDQ"]
    assert ndq["tick_size"] == pytest.approx(0.1) and ndq["qty_step"] == pytest.approx(0.1)
    assert cfg["instruments"]["XAUUSD"]["qty_step"] == 1 and cfg["instruments"]["XAUUSD"]["tick_size"] == pytest.approx(0.001)
    m1 = feed.history("NDQ")
    assert len(m1) > 5000                                     # 12 days needed several 5000-candle pages
    assert m1.index.is_monotonic_increasing and not m1.index.has_duplicates
    assert str(m1.index.tz) == "America/New_York"
    assert m1.index[-1] < fake.now.tz_convert("America/New_York")    # forming candle excluded
    assert len(feed.h1_history("NDQ")) > 24 * 30


def test_unknown_instrument_is_a_clear_error():
    cfg, fake, c, *_ = setup()
    cfg["instruments"]["NDQ"]["oanda_instrument"] = "NAS100_XYZ"
    feed = OandaFeed(cfg, Bus(), LiveState(), c)
    with pytest.raises(SystemExit, match="not tradeable"):
        run(feed.qualify())


def test_entry_carries_stop_on_fill_with_correct_precision():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos(stop=24400.04)                                  # rounds to OANDA's 0.1 precision
        px = await b.open(p, 2.35, 24500)                       # units floor to the 0.1 step
        return p, px
    p, px = run(go())
    method, path, body = next(r for r in fake.requests if r[0] == "POST")
    o = body["order"]
    assert o["type"] == "MARKET" and o["timeInForce"] == "FOK"
    assert o["stopLossOnFill"] == {"price": "24400.0", "timeInForce": "GTC"}
    assert o["units"] == "2.3"
    assert px == 24500.0 and p.open_qty == pytest.approx(2.3) and len(p.meta["trades"]) == 1


def test_short_entry_sends_negative_units():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        await b.open(pos(side=-1, stop=24600), 1, 24500)
    run(go())
    assert next(r for r in fake.requests if r[0] == "POST")[2]["order"]["units"] == "-1"


def test_hard_rules_block_orders_before_they_reach_oanda():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        with pytest.raises(OrderRejected, match="wrong side"):
            await b.open(pos(stop=24600), 1, 24500)
        with pytest.raises(OrderRejected, match="exceeds"):
            await b.open(pos(stop=20000), 1, 24500)
        p = pos(); p.stop = None
        with pytest.raises(OrderRejected, match="needs a stop"):
            await b.open(p, 1, 24500)
    run(go())
    assert not [r for r in fake.requests if r[0] == "POST"]


def test_cancelled_order_and_missing_stop_are_rejected():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        fake.cancel_next = "MARKET_HALTED"
        with pytest.raises(OrderRejected, match="MARKET_HALTED"):
            await b.open(pos(), 1, 24500)
        fake.drop_stop_next = True
        with pytest.raises(OrderRejected, match="no stop"):
            await b.open(pos(), 1, 24500)
    run(go())
    assert not fake.open_trades()                               # the naked trade was closed at once


def test_no_opposite_side_entry_on_same_symbol():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        await b.open(pos(), 1, 24500)
        with pytest.raises(OrderRejected, match="opposite"):
            await b.open(pos(side=-1, stop=24600), 1, 24500)
    run(go())


def test_pyramid_partial_and_stop_moves_across_trades():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 4, 24500)
        fake.prices["NAS100_USD"] = 24600.0
        await b.move_stop(p, 24510)
        await b.add(p, 2, 24600)
        assert len(fake.open_trades()) == 2
        assert all(t["stopLossOrder"]["price"] == "24510.0" for t in fake.open_trades())   # add got current stop
        await b.move_stop(p, 24550)
        assert all(t["stopLossOrder"]["price"] == "24550.0" for t in fake.open_trades())
        with pytest.raises(OrderRejected, match="toward profit"):
            await b.move_stop(p, 24520)
        px = await b.reduce(p, 3, 24600)                        # oldest trade first
        units = sorted(float(t["currentUnits"]) for t in fake.open_trades())
        return p, px, units
    p, px, units = run(go())
    assert units == [1.0, 2.0]
    assert px == 24600.0 and p.open_qty == pytest.approx(3)
    # booked against the position's average entry (24533.33), like every broker in the app
    assert p.realized == pytest.approx(3 * (24600 - (4 * 24500 + 2 * 24600) / 6))


def test_stop_fill_is_detected_and_booked():
    cfg, fake, c, st, bus, feed, b = setup()
    seen = []
    bus.subscribe("stop_filled", lambda ev: seen.append(ev))

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        await b.add(p, 1, 24500)
        for t in list(fake.open_trades()):
            fake.hit_stop(t["id"])
        await bus.publish("clock", st.now)
        return p
    p = run(go())
    assert len(seen) == 1 and seen[0]["position"] is p
    assert seen[0]["price"] == pytest.approx(24400.0)
    assert p.open_qty == 0 and p.realized == pytest.approx(-100 * 3)
    assert not b.managed


def test_close_tolerates_trade_already_stopped_out():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 1, 24500)
        fake.hit_stop(p.meta["trades"][0]["id"])
        return p, await b.close(p, 24450)
    p, px = run(go())
    assert px == pytest.approx(24400.0) and p.open_qty == 0


def test_equity_in_cad_is_converted_to_usd():
    cfg, fake, c, st, bus, feed, b = setup(nav=13700.0, currency="CAD", usdcad=1.37)

    async def go():
        await b.connect()
        return await b.equity()
    assert run(go()) == pytest.approx(10000.0, rel=1e-3)


def test_reconciliation_views_and_orphans():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        # a trade opened by hand on the OANDA app (unknown to the bot), and one without a stop
        fake.trades["999"] = {"id": "999", "instrument": "NAS100_USD", "price": "24500.0", "state": "OPEN",
                              "currentUnits": "1", "initialUnits": "1"}
        bp = await b.broker_positions()
        un = await b.unprotected()
        await b.flatten_orphan("NDQ", 1)
        return bp, un
    bp, un = run(go())
    assert bp == {"NDQ": 3.0} and un == ["NDQ"]
    assert fake.trades["999"]["state"] == "CLOSED"
    assert len(fake.open_trades()) == 1                         # the bot's own trade is untouched


def test_poll_publishes_only_new_completed_bars_in_order():
    cfg, fake, c, st, bus, feed, b = setup()
    bars = []
    bus.subscribe("bar", lambda bar: bars.append(bar))

    async def go():
        await feed.qualify()
        await feed.start()
        assert await feed.poll_once() == 0                       # nothing new yet
        fake.now += pd.Timedelta("3min")
        n = await feed.poll_once()
        return n
    n = run(go())
    assert n == 3 * len(BASE["instruments"])                    # 3 new minutes × every symbol
    ndq = [x.ts for x in bars if x.symbol == "NDQ"]
    assert ndq == sorted(ndq) and len(set(ndq)) == 3


def test_bad_token_is_reported():
    from fxagents.oanda import OandaError
    fake = FakeOanda()
    c = OandaClient("wrong", ACCT, "practice", transport=fake.transport())
    with pytest.raises(OandaError) as e:
        run(c.req("GET", "/v3/accounts"))
    assert e.value.status == 401


def test_margin_helpers_and_budget_math():
    from fxagents.agents.trading import floor_step, margin_in_use, margin_per_unit
    cfg, fake, c, st, bus, feed, b = setup()
    ic = cfg["instruments"]["NDQ"]
    assert margin_per_unit(ic, 30000) == 0                       # unknown margin rate (before qualify) → no cap
    ic["margin_rate"] = 0.12
    assert margin_per_unit(ic, 30000) == pytest.approx(3600)     # 1 unit = $30,000 notional × 12%
    p = pos()
    p.legs.append(__import__("fxagents.models", fromlist=["Leg"]).Leg(2.0, 30000, st.now, "initial"))
    p.last_price = 30000
    st.positions[p.id] = p
    assert margin_in_use(cfg, st) == pytest.approx(7200)
    equity = 73000.0
    room = min(0.25 * equity, 0.60 * equity - margin_in_use(cfg, st))
    assert floor_step(room / margin_per_unit(ic, 30000), 0.01) == pytest.approx(5.06)   # 25% of equity ÷ margin per unit; not the 12 units the stop distance alone would give


def test_history_reaches_now_even_when_pages_come_back_short():
    """Regression: real OANDA returned < count candles per page; the loader stopped after page 1
    and the app then replayed a week of old bars as if they were live."""
    cfg, fake, c, st, bus, feed, b = setup()
    fake.page_cap = 4999

    async def go():
        await feed.qualify()
        await feed.start()
    run(go())
    newest = feed.history("NDQ").index[-1]
    assert fake.now.tz_convert("America/New_York") - newest <= pd.Timedelta("2min")
    assert len(feed.history("NDQ")) > 12000


def test_catch_up_bars_are_backfilled_not_published_as_live():
    cfg, fake, c, st, bus, feed, b = setup()
    live, back = [], []
    bus.subscribe("bar", lambda x: live.append(x))
    bus.subscribe("backfill", lambda xs: back.extend(xs))

    async def go():
        await feed.qualify()
        await feed.start()
        fake.now += pd.Timedelta("90min")          # e.g. the network was down for 90 minutes
        feed.clock = lambda: fake.now.tz_convert("America/New_York")
        await feed.poll_once()
    run(go())
    assert back and all((fake.now.tz_convert("America/New_York") - x.ts) > pd.Timedelta("10min") for x in back)
    assert live and all((fake.now.tz_convert("America/New_York") - x.ts) <= pd.Timedelta("10min") for x in live)
    assert len(live) <= 10 * len(BASE["instruments"])
