"""Regression tests for the Oct 2026 audit's execution/accounting findings (F01–F06, F11, F27).
Mocked HTTP only (tests/fake_oanda.py) and synthetic data."""
from __future__ import annotations

import asyncio
import copy

import pandas as pd
import pytest

from fxagents.agents.core import Ctx
from fxagents.broker import OrderRejected, PaperBroker
from fxagents.bus import Bus
from fxagents.config import apply_broker, load_config
from fxagents.models import Bar, Leg, Position, Signal
from fxagents.oanda import OandaBroker, OandaClient, OandaFeed
from fxagents.state import LiveState
from tests.fake_oanda import ACCT, TOKEN, FakeOanda

BASE = load_config("config.yaml")
TZ = "America/New_York"


def setup(**kw):
    cfg = copy.deepcopy(BASE)
    cfg["mode"], cfg["broker"] = "paper", "oanda"
    cfg.pop("_broker_applied", None)
    apply_broker(cfg)
    fake = FakeOanda(**kw)
    client = OandaClient(TOKEN, ACCT, "practice", transport=fake.transport())
    client.backoff = 0
    st, bus = LiveState(mode="paper"), Bus()
    st.now = pd.Timestamp("2026-10-08 10:00", tz=TZ)
    feed = OandaFeed(cfg, bus, st, client)
    broker = OandaBroker(cfg, st, bus, client, feed)
    return cfg, fake, client, st, bus, feed, broker


def pos(sym="NDQ", side=1, stop=24400.0, rpu=100.0):
    return Position(sym, side, "smc_ifvg:5m@v1", stop, stop, rpu, 1.0, pd.Timestamp("2026-10-08 10:00", tz=TZ))


def run(coro):
    return asyncio.run(coro)


def puts(fake, suffix="/close"):
    return [r for r in fake.requests if r[0] == "PUT" and r[1].endswith(suffix)]


def posts(fake):
    return [r for r in fake.requests if r[0] == "POST"]


# ── F01 broker P&L / quantity reconciliation ────────────────────────────────
def test_F01_partial_then_stop_books_residual_at_its_own_price():
    """Entry 100-equivalent: 10 @ 24500, bank 5 @ 24600, the other 5 stopped @ 24400 → OANDA's lifetime
    averageClosePrice is 24500; the residual must be booked at 24400 (total 0), not 24500 (+500)."""
    cfg, fake, c, st, bus, feed, b = setup()
    seen = []
    bus.subscribe("stop_filled", lambda ev: seen.append(ev))

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 10, 24500)
        fake.prices["NAS100_USD"] = 24600.0
        await b.reduce(p, 5, 24600)
        tid = p.meta["trades"][0]["id"]
        fake.hit_stop(tid)
        assert float(fake.trades[tid]["averageClosePrice"]) == pytest.approx(24500.0)
        await b.check_stops()
        return p
    p = run(go())
    assert p.open_qty == 0
    assert p.realized == pytest.approx(0.0)
    assert seen and seen[0]["price"] == pytest.approx(24400.0)


def test_F01_manual_partial_close_is_reconciled():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 10, 24500)
        tid = p.meta["trades"][0]["id"]
        fake.prices["NAS100_USD"] = 24550.0
        fake.close(fake.trades[tid], "4")                       # closed by hand in the OANDA app
        await b.check_stops()
        mid = (p.open_qty, p.realized, tid in b.managed)
        fake.hit_stop(tid)                                      # rest stopped at 24400
        await b.check_stops()
        return p, mid
    p, (q, real, managed) = run(go())
    assert q == pytest.approx(6) and real == pytest.approx(4 * 50) and managed
    assert p.open_qty == 0 and p.realized == pytest.approx(4 * 50 - 6 * 100)


# ── F02 ambiguous close retry ──────────────────────────────────────────────
def test_F02_partial_close_not_resent_after_lost_response():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 10, 24500)
        fake.prices["NAS100_USD"] = 24600.0
        fake.faults.append(["PUT", "/close", "timeout_after", 1])     # executed, response lost
        px = await b.reduce(p, 5, 24600)
        return p, px
    p, px = run(go())
    assert len(puts(fake)) == 1                                 # never sent twice
    assert float(fake.open_trades()[0]["currentUnits"]) == 5
    assert p.open_qty == pytest.approx(5) and px == pytest.approx(24600)
    assert p.realized == pytest.approx(5 * 100)


def test_F02_close_that_never_executed_is_reported_not_resent():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 10, 24500)
        fake.faults.append(["PUT", "/close", "timeout_before", 1])    # never reached OANDA
        with pytest.raises(OrderRejected, match="did not execute"):
            await b.reduce(p, 5, 24500)
        fake.faults.append(["GET", "/summary", 503, 2])               # reads are still retried
        await b.equity()
        return p
    p = run(go())
    assert len(puts(fake)) == 1 and p.open_qty == pytest.approx(10)
    assert float(fake.open_trades()[0]["currentUnits"]) == 10


# ── F03 non-atomic execution state ─────────────────────────────────────────
def test_F03_first_leg_booked_when_second_leg_fails():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 4, 24500)
        fake.prices["NAS100_USD"] = 24600.0
        await b.add(p, 2, 24600)
        first, second = (t["id"] for t in p.meta["trades"])
        avg = p.avg_entry
        fake.faults.append(["PUT", f"/trades/{second}/close", 400, 1])
        with pytest.raises(OrderRejected):
            await b.close(p, 24600)
        mid = (p.open_qty, p.realized, first in b.managed, second in b.managed)
        await b.close(p, 24600)                                     # next attempt closes the rest
        return p, avg, mid
    p, avg, (q, real, m1, m2) = run(go())
    assert q == pytest.approx(2) and real == pytest.approx(4 * (24600 - avg))
    assert not m1 and m2
    assert p.open_qty == 0 and p.realized == pytest.approx(6 * (24600 - avg)) and not fake.open_trades()


def test_F03_manager_retries_failed_partial_and_stop_move():
    from fxagents.agents.trading import PositionManagerAgent
    cfg = copy.deepcopy(BASE)
    cfg["mode"] = "sim"
    m = cfg["management"]
    m["pyramid"]["enabled"], m["pyramid"]["max_adds"], m["runner"], m["trail_gap_r"] = True, 0, {}, 0

    class Flaky(PaperBroker):
        fail_reduce = fail_move = 1

        async def reduce(self, p, qty, ref, limit=None):
            if self.fail_reduce:
                self.fail_reduce -= 1
                raise OrderRejected("timeout")
            return await super().reduce(p, qty, ref, limit)

        async def move_stop(self, p, new_stop):
            if self.fail_move:
                self.fail_move -= 1
                raise OrderRejected("timeout")
            return await super().move_stop(p, new_stop)

    st = LiveState(); st.now = pd.Timestamp("2026-10-08 10:00", tz=TZ)
    br = Flaky(cfg, st, Bus()); br._slip = lambda s, side: 0.0
    ctx = Ctx(cfg, br.bus, st, None, br, None, None, None)
    pm = PositionManagerAgent(ctx); pm.start()
    p = Position("NDQ", 1, "t", 24900.0, 24900.0, 100.0, 1.0, st.now)
    run(br.open(p, 2, 25000.0)); st.positions[p.id] = p

    def bar(hi, minute):
        st.now = pd.Timestamp(f"2026-10-08 10:{minute:02d}", tz=TZ)
        return Bar("NDQ", st.now, 25040, hi, 25030, 25040)
    run(pm.on_bar(bar(25110, 1)))            # target hit, partial fails → nothing counted
    assert (p.stage, p.partial_done, p.open_qty) == (0, False, 2)
    run(pm.on_bar(bar(25050, 2)))            # back below the level: partial retried and done, stop move fails
    assert (p.stage, p.partial_done, p.open_qty) == (0, True, 1) and p.stop == 24900
    run(pm.on_bar(bar(25050, 3)))            # stop move retried
    assert p.stage == 1 and p.stop == pytest.approx(25010)


# ── F04 restart recovery ───────────────────────────────────────────────────
def test_F04_restart_restores_halt_baseline_and_positions(tmp_path):
    from fxagents.agents.ops import MonitorAgent
    from fxagents.agents.trading import PositionManagerAgent
    from fxagents.state import RuntimeStore, startup_reconcile, trading_day
    cfg, fake, c, st, bus, feed, b = setup()
    store = RuntimeStore(tmp_path / "runtime_state.json")
    now = st.now

    async def before_restart():
        await feed.qualify(); await b.connect()
        a, g = pos(), pos("XAUUSD", stop=3600.0, rpu=50.0)
        await b.open(a, 10, 24500); await b.open(g, 5, 3650)
        st.positions = {a.id: a, g.id: g}
        st.trading_enabled, st.halt_reason = False, "daily loss limit hit (-$300)"
        st.trading_day, st.day_start_equity, st.equity_peak = trading_day(now), 12345.0, 20000.0
        store.save(st)
        return a, g
    a, g = run(before_restart())
    fake.hit_stop(g.meta["trades"][0]["id"])                     # gold stopped out while the app was down

    # a fresh process: new state, client, broker and agents on the same account
    c2 = OandaClient(TOKEN, ACCT, "practice", transport=fake.transport())
    st2, bus2 = LiveState(mode="paper"), Bus()
    st2.now, st2.equity = now, 12345.0
    st2.equity_peak = st2.day_start_equity = 15000.0             # what a cold start would have used
    b2 = OandaBroker(cfg, st2, bus2, c2)
    closed = []
    bus2.subscribe("position_closed", lambda ev: closed.append(ev["position"]))
    ctx = Ctx(cfg, bus2, st2, None, b2, None, None, None)
    PositionManagerAgent(ctx).start()

    async def after_restart():
        await b2.connect()
        res = await startup_reconcile(st2, b2, store, now)
        mon = MonitorAgent(ctx); mon.start()
        await mon.on_clock(now)                                  # same trading day → no baseline reset
        return res
    res = run(after_restart())
    assert not st2.trading_enabled and st2.halt_reason.startswith("daily loss")
    assert st2.day_start_equity == 12345.0 and st2.equity_peak == 20000.0
    assert list(st2.positions) == [a.id]
    a2 = st2.positions[a.id]
    assert a2.open_qty == pytest.approx(10) and a2.meta["trades"][0]["id"] in b2.managed
    assert [p.id for p in closed] == [g.id] and closed[0].exit_reason == "stop"
    assert closed[0].realized == pytest.approx(5 * (3600 - 3650))
    assert res["adopted"] and store.load()["positions"][0]["id"] == a.id


def test_F04_startup_failure_is_not_persisted_as_a_halt(tmp_path):
    from fxagents.state import STARTUP_FAILED, STARTUP_HALT, RuntimeStore, trading_day
    store = RuntimeStore(tmp_path / "rt.json")
    st = LiveState(); st.now = pd.Timestamp("2026-10-08 10:00", tz=TZ); st.trading_day = trading_day(st.now)
    st.trading_enabled, st.halt_reason = False, f"{STARTUP_FAILED} (timeout) — retrying every minute"
    store.save(st)
    assert store.load()["trading_enabled"] and store.load()["halt_reason"] == ""
    st.trading_enabled, st.halt_reason = False, "daily loss limit hit"
    store.save(st)
    for transient in (STARTUP_HALT, f"{STARTUP_FAILED} (x)"):   # a real halt already on file survives
        st.halt_reason = transient
        store.save(st)
        assert store.load()["halt_reason"] == "daily loss limit hit" and not store.load()["trading_enabled"]


def test_F04_new_day_clears_daily_halt_and_orphans_are_journaled(tmp_path):
    from fxagents.agents.ops import JournalAgent
    from fxagents.journal import Journal
    from fxagents.state import STARTUP_HALT, RuntimeStore, startup_reconcile
    cfg, fake, c, st, bus, feed, b = setup()
    store = RuntimeStore(tmp_path / "rt.json")
    st.trading_enabled, st.halt_reason, st.trading_day = False, "daily loss limit hit", "2026-10-07"
    store.save(st)
    st2 = LiveState(mode="paper"); st2.trading_enabled, st2.halt_reason = False, STARTUP_HALT
    run(startup_reconcile(st2, b, store, pd.Timestamp("2026-10-08 10:00", tz=TZ)))
    assert st2.trading_enabled and st2.halt_reason == ""
    j = Journal(str(tmp_path / "j.sqlite"))
    JournalAgent(Ctx(cfg, bus, st, None, b, j, None, None)).start()

    async def go():
        await feed.qualify(); await b.connect()
        fake.trades["999"] = {"id": "999", "instrument": "NAS100_USD", "price": "24400.0", "state": "OPEN",
                              "currentUnits": "2", "initialUnits": "2"}
        await b.flatten_orphan("NDQ", 2)
    run(go())
    rows = j.trades()
    assert len(rows) == 1 and rows[0]["exit_reason"] == "orphan_close" and rows[0]["status"] == "closed"
    assert rows[0]["realized"] == pytest.approx(2 * 100)


# ── F05 unknown entry outcome ──────────────────────────────────────────────
def test_F05_lost_entry_response_registers_the_filled_trade():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        fake.faults.append(["POST", "/orders", "timeout_after", 1])
        px = await b.open(p, 2, 24500)
        return p, px
    p, px = run(go())
    o = posts(fake)[0][2]["order"]
    assert len(posts(fake)) == 1 and o["clientExtensions"]["id"] == o["tradeClientExtensions"]["id"]
    assert o["clientExtensions"]["id"].startswith(f"fxa-{p.id}-")
    tid = fake.open_trades()[0]["id"]
    assert tid in b.managed and p.open_qty == pytest.approx(2) and px == pytest.approx(24500)
    assert not b.unresolved


def test_F05_entry_not_filled_after_timeout_is_rejected_and_unblocked():
    """OANDA never got the order: it stays unresolved for RESOLVE_TRIES clock ticks, then the symbol is freed."""
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        fake.faults.append(["POST", "/orders", "timeout_before", 1])
        with pytest.raises(OrderRejected, match="unknown"):
            await b.open(pos(), 2, 24500)
        await b.on_clock(st.now)
        assert b.unresolved                                     # first re-check: OANDA doesn't know it (yet)
        await b.on_clock(st.now)
        assert not b.unresolved and not fake.open_trades() and not st.positions
        await b.open(pos(), 2, 24500)                           # the symbol is free again
    run(go())
    assert len(fake.open_trades()) == 1


def test_F05_unknown_outcome_blocks_symbol_until_reconciled():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        fake.faults += [["POST", "/orders", "timeout_after", 1], ["GET", "/orders/@", 503, 4]]
        p = pos()
        with pytest.raises(OrderRejected, match="unknown"):
            await b.open(p, 2, 24500)
        n = len(posts(fake))
        with pytest.raises(OrderRejected, match="still unknown"):
            await b.open(pos(), 2, 24500)
        assert len(posts(fake)) == n                            # nothing sent while unresolved
        await b.on_clock(st.now)                                # OANDA readable again → FILLED → adopted
        assert not b.unresolved and st.positions.get(p.id) is p
        assert p.open_qty == 2 and p.meta["trades"][0]["id"] in b.managed
    run(go())


def test_F05_order_filling_after_the_first_lookup_is_adopted_not_orphaned():
    from fxagents.agents.ops import MonitorAgent
    cfg, fake, c, st, bus, feed, b = setup()
    opened = []
    bus.subscribe("position_opened", lambda p: opened.append(p))

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        fake.faults.append(["POST", "/orders", "defer", 1])     # reaches OANDA only after the lookup
        with pytest.raises(OrderRejected, match="unknown"):
            await b.open(p, 2, 24500)
        fake.flush_deferred()                                   # ...now it fills
        st.equity = st.day_start_equity = st.equity_peak = 10000.0
        mon = MonitorAgent(Ctx(cfg, bus, st, None, b, None, None, None)); mon.start()
        for _ in range(2):                                      # orphan check runs while it's unresolved
            mon._last_check = 0
            await mon.on_clock(st.now)
        await b.on_clock(st.now)                                # first re-check → FILLED → adopted
        return p
    p = run(go())
    assert opened == [p] and st.positions[p.id] is p and p.open_qty == 2
    assert len(fake.open_trades()) == 1 and not b.unresolved   # managed, never orphan-closed
    assert p.risk_per_unit == pytest.approx(100.0)


def test_F05_failed_post_fill_check_still_registers_trade():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        fake.faults.append(["GET", "/trades/", 503, 4])
        await b.open(p, 2, 24500)
        return p
    p = run(go())
    assert p.meta["stop_unverified"] and p.meta["trades"][0]["id"] in b.managed and p.open_qty == 2


# ── F06 wall-clock flatten supervisor ──────────────────────────────────────
def _supervised():
    from fxagents.agents.trading import FlattenSupervisor, PositionManagerAgent
    cfg, fake, c, st, bus, feed, b = setup()
    ctx = Ctx(cfg, bus, st, None, b, None, None, None)
    pm = PositionManagerAgent(ctx); pm.start()
    return cfg, fake, st, bus, feed, b, FlattenSupervisor(ctx, pm)


def test_F06_supervisor_flattens_on_wall_clock_while_bus_is_blocked():
    cfg, fake, st, bus, feed, b, sup = _supervised()
    t = pd.Timestamp("2026-10-08 15:49:05", tz=TZ)              # within the 60 s buffer, no new bars

    async def go():
        await feed.qualify(); await b.connect()
        gate = asyncio.Event()

        async def slow_grader(_):
            await gate.wait()                                   # e.g. a Jev call that never returns
        bus.subscribe("bar_signal", slow_grader)
        blocked = asyncio.create_task(bus.publish("bar_signal", {}))
        await asyncio.sleep(0)
        p = pos()
        await b.open(p, 2, 24500)
        st.positions[p.id], st.last_prices["NDQ"] = p, 24500.0
        fake.trades["999"] = {"id": "999", "instrument": "NAS100_USD", "price": "24500.0", "state": "OPEN",
                              "currentUnits": "1", "initialUnits": "1"}       # not ours
        assert await sup.tick(t - pd.Timedelta("5min")) is None and not st.entries_blocked
        ok = await sup.tick(t)
        still_blocked = not blocked.done()
        gate.set(); await blocked
        return p, ok, still_blocked
    p, ok, still_blocked = run(go())
    assert ok and still_blocked
    assert not fake.open_trades() and p.status == "closed" and p.exit_reason == "session_flat"
    assert st.entries_blocked.startswith("session flatten")
    assert run(sup.tick(pd.Timestamp("2026-10-08 17:05", tz=TZ))) is None and not st.entries_blocked


def test_F06_not_flat_at_deadline_is_alerted_and_retried():
    cfg, fake, st, bus, feed, b, sup = _supervised()
    alerts = []
    bus.subscribe("alert", lambda a: alerts.append(a["msg"]))

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        st.positions[p.id] = p
        fake.faults.append(["PUT", "/close", 503, 99])          # broker refuses closes
        r1 = await sup.tick(pd.Timestamp("2026-10-08 15:49:30", tz=TZ))
        n1 = len(alerts)
        r2 = await sup.tick(pd.Timestamp("2026-10-08 15:50:10", tz=TZ))
        fake.faults.clear()
        r3 = await sup.tick(pd.Timestamp("2026-10-08 15:50:20", tz=TZ))
        return r1, n1, r2, r3, p
    r1, n1, r2, r3, p = run(go())
    assert r1 is False and n1 == 0
    assert r2 is False and len(alerts) == 1 and "NOT FLAT" in alerts[0]
    assert any("NOT FLAT" in a["msg"] for a in st.alerts)
    assert r3 is True and p.status == "closed" and not fake.open_trades()


def test_F06_manager_does_not_act_on_a_position_the_supervisor_closed():
    """Supervisor flattens while the manager is mid-way through banking a partial on the same position:
    no fake 'banked' partial, no stop move, no add."""
    cfg, fake, st, bus, feed, b, sup = _supervised()
    pm = sup.pm
    updates = []
    bus.subscribe("position_updated", lambda ev: updates.append(ev["event"]))
    real_close_trade = b._close_trade

    async def slow_close_trade(p, t, units):
        await asyncio.sleep(0.01)                               # the supervisor's close is in flight…
        return await real_close_trade(p, t, units)
    b._close_trade = slow_close_trade

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        st.positions[p.id], st.last_prices["NDQ"] = p, 24500.0
        st.now = pd.Timestamp("2026-10-08 15:40", tz=TZ)        # market clock: before flatten_at for the manager
        p.opened_ts = st.now - pd.Timedelta("10min")            # (no max-hold exit either)
        bar = Bar("NDQ", st.now, 24550, 24610, 24540, 24600)    # first target (24600) hit → partial
        sup_t = asyncio.create_task(sup.tick(pd.Timestamp("2026-10-08 15:49:30", tz=TZ)))
        await asyncio.sleep(0)                                  # supervisor takes the position lock first
        assert p.status == "open"
        await pm.manage(p, bar)                                 # the manager's bar pass runs meanwhile
        return p, await sup_t
    p, flat = run(go())
    assert flat and p.status == "closed" and p.exit_reason == "session_flat"
    assert not p.partial_done and "partial" not in updates and "stop_to_profit" not in updates
    assert not [e for e in p.events if e["kind"] in ("partial", "stop_moved", "pyramid")]
    assert len(puts(fake)) == 1 and p.adds == 0


def test_F06_failed_flatten_all_close_is_retried_on_the_next_bar():
    from fxagents.agents.trading import PositionManagerAgent
    cfg = copy.deepcopy(BASE); cfg["mode"] = "sim"

    class Flaky(PaperBroker):
        fails = 1

        async def close(self, p, ref, limit=None):
            if self.fails:
                self.fails -= 1
                raise OrderRejected("timeout")
            return await super().close(p, ref, limit)
    st = LiveState(); st.now = pd.Timestamp("2026-10-08 10:00", tz=TZ)
    br = Flaky(cfg, st, Bus()); br._slip = lambda s, side: 0.0
    pm = PositionManagerAgent(Ctx(cfg, br.bus, st, None, br, None, None, None)); pm.start()
    p = Position("NDQ", 1, "t", 24900.0, 24900.0, 100.0, 1.0, st.now)
    run(br.open(p, 2, 25000.0)); st.positions[p.id] = p
    run(br.bus.publish("flatten_all", "kill switch"))
    assert p.status == "open" and p.meta["pending_close"] == "flatten: kill switch"
    st.now += pd.Timedelta("1min")
    run(pm.on_bar(Bar("NDQ", st.now, 25000, 25010, 24990, 25000)))      # an ordinary bar: no time exit
    assert p.status == "closed" and p.exit_reason == "flatten: kill switch" and "pending_close" not in p.meta


def test_F06_supervisor_runs_only_on_a_real_clock():
    from fxagents.agents.trading import FlattenSupervisor, PositionManagerAgent

    async def go(mode, replay=None):
        cfg = copy.deepcopy(BASE); cfg["mode"] = mode
        if replay:
            cfg["replay"] = replay
        ctx = Ctx(cfg, Bus(), LiveState(), None, None, None, None, None)
        sup = FlattenSupervisor(ctx, PositionManagerAgent(ctx))
        sup.clock = lambda: pd.Timestamp("2026-10-08 12:00", tz=TZ)
        sup.start()
        has = sup.task is not None
        if has:
            sup.task.cancel()
        return has
    assert run(go("paper")) and not run(go("sim")) and not run(go("paper", {"days": 5}))


# ── F11 sizing from the executable price ───────────────────────────────────
class _QuoteBroker:
    def __init__(self, fill: float, bound: bool):
        self.fill, self.price_bound, self.opened, self.reduced = fill, bound, None, []

    async def quote(self, sym):
        return (99.0, 101.0)

    async def equity(self):
        return 100000.0

    async def open(self, p, qty, ref):
        self.opened = (qty, ref, p.meta.get("price_bound"))
        p.add_leg(Leg(qty, self.fill, p.opened_ts, "initial"))
        return self.fill

    async def reduce(self, p, qty, ref, limit=None):
        self.reduced.append(qty)
        p.closed_qty += qty
        return ref


def _risk(broker):
    from fxagents.agents.trading import RiskAgent
    cfg = copy.deepcopy(BASE); cfg["mode"] = "paper"
    cfg["instruments"]["XAUUSD"].update(multiplier=1, tick_size=0.01, qty_step=1, min_units=1, max_units=1e6, margin_rate=0)
    st = LiveState(mode="paper"); st.now = pd.Timestamp("2026-10-08 09:00", tz=TZ)
    st.equity = 100000.0
    st.last_prices["XAUUSD"] = 100.0                             # the mid
    st.bias["XAUUSD"] = {"suspended": False, "score": 1.0, "in_doubt": False, "label": "BULLISH", "d": 1, "h4": 1, "h1": 1}

    class J:
        rows: list = []
        def add_signal(self, s): self.rows.append(s)
    ra = RiskAgent(Ctx(cfg, Bus(), st, None, broker, J(), None, None)); ra.start()
    sig = Signal("XAUUSD", "t", 1, 100.0, 99.0, st.now)
    rec = {"ts": st.now.isoformat(), "symbol": "XAUUSD", "strategy": "t", "side": "LONG", "entry": 100.0, "stop": 99.0}
    run(ra.on_request({"signal": sig, "grade": {"quality": 0.8, "confidence": 0.8, "source": "test"}, "record": rec}))
    return st


def test_F11_sizes_from_ask_with_slippage_allowance_and_price_bound():
    """Mid 100, ask 101, stop 99: the real distance is 2 (+0.2 allowance), not 1 → 227 units, not 500."""
    br = _QuoteBroker(fill=101.0, bound=True)
    st = _risk(br)
    qty, ref, bound = br.opened
    assert ref == pytest.approx(101.0) and qty == 227 and bound == pytest.approx(101.2)
    p = next(iter(st.positions.values()))
    assert p.open_qty * p.risk_per_unit <= 500 + 1e-9


def test_F11_post_fill_risk_overrun_is_trimmed():
    br = _QuoteBroker(fill=103.0, bound=False)                  # no price bound, fill 2 worse than the ask
    st = _risk(br)
    assert br.opened[0] == 250 and br.reduced == [125]          # risk 250×4 = 1000 > 550 → keep 500/4
    p = next(iter(st.positions.values()))
    assert p.open_qty == 125 and p.open_qty * p.risk_per_unit == pytest.approx(500)
    assert p.initial_qty == 125 and p.closed_qty == 0          # partial size and journal R use the trimmed size


def test_F11_shadow_fill_pays_half_spread_once():
    """No live quote (paper/shadow): size from mid + s/2, but the broker gets the mid and adds s/2 itself."""
    from fxagents.agents.setup_first import ShadowBroker
    holder = {}

    class SB(ShadowBroker):
        def __init__(self):
            cfg = copy.deepcopy(BASE)
            super().__init__(cfg, LiveState(), Bus(), {"XAUUSD": 0.40})
            self.commission = lambda s, q: 0.0

        async def open(self, p, qty, ref):
            holder["ref"] = ref
            return await super().open(p, qty, ref)
    br = SB()
    st = _risk(br)
    p = next(iter(st.positions.values()))
    assert holder["ref"] == pytest.approx(100.0) and p.entry == pytest.approx(100.2)   # mid 100 + 0.40/2


def test_F11_oanda_market_order_carries_price_bound():
    cfg, fake, c, st, bus, feed, b = setup()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos(); p.meta["price_bound"] = 24510.04
        await b.open(p, 1, 24500)
        q = pos(); q.meta["price_bound"] = 24510.0
        fake.spread["NAS100_USD"] = 30.0                        # ask 24515 is beyond the bound
        with pytest.raises(OrderRejected, match="BOUNDS_VIOLATION"):
            await b.open(q, 1, 24500)
        return await b.quote("NDQ")
    quote = run(go())
    assert posts(fake)[0][2]["order"]["priceBound"] == "24510.0"
    assert quote == (24485.0, 24515.0)


# ── F27 non-USD conversion fallback ────────────────────────────────────────
def test_F27_failed_conversion_blocks_new_exposure():
    cfg, fake, c, st, bus, feed, b = setup(nav=13700.0, currency="CAD")
    fake.fx_down = True

    async def go():
        await feed.qualify(); await b.connect()
        eq = await b.equity()
        with pytest.raises(OrderRejected, match="rate"):
            await b.open(pos(), 1, 24500)
        return eq
    eq = run(go())
    assert eq is None                                           # unknown — never NAV × a guessed 1.0
    assert not posts(fake)


def test_F27_restart_with_rate_unavailable_does_not_halt_or_close(tmp_path):
    """Same-day restart while the CAD→USD rate is down: equity unknown must not look like a −100% day."""
    from fxagents.agents.ops import JournalAgent, MonitorAgent
    from fxagents.journal import Journal
    from fxagents.state import RuntimeStore, startup_reconcile, trading_day
    cfg, fake, c, st, bus, feed, b = setup(nav=13700.0, currency="CAD")
    store = RuntimeStore(tmp_path / "rt.json")
    st.trading_day, st.day_start_equity, st.equity_peak = trading_day(st.now), 10000.0, 10000.0
    store.save(st)
    fake.fx_down = True
    flat = []
    bus.subscribe("flatten_all", lambda why: flat.append(why))

    async def go():
        await feed.qualify(); await b.connect()
        p = pos(); fake.fx_down = False
        await b.open(p, 1, 24500)                               # a position from before the restart
        fake.fx_down, b._fx_cache = True, None
        st2 = st
        st2.positions = {p.id: p}
        st2.equity = st2.day_start_equity = st2.equity_peak = (await b.equity()) or 0.0   # boot: unknown → 0
        await startup_reconcile(st2, b, store, st2.now)
        ctx = Ctx(cfg, bus, st2, None, b, Journal(str(tmp_path / "j.sqlite")), None, None)
        JournalAgent(ctx).start(); MonitorAgent(ctx).start()
        for _ in range(3):
            await bus.publish("clock", st2.now)
        return st2, p
    st2, p = run(go())
    assert st2.trading_enabled and not flat and p.status == "open" and len(fake.open_trades()) == 1
    assert st2.day_start_equity == 10000.0 and store.load()["trading_enabled"]
