"""Jev trade adviser: asks at 15-minute closes while a c10_afternoon trade is open, logs hold/cut/add, never touches
the trade, and scores every call when the trade closes."""
import asyncio
import copy

import pandas as pd

from fxagents.agents import jev_advisor as ja
from fxagents.agents.c10_trader import C10Trader
from fxagents.agents.core import Ctx
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.journal import Journal
from fxagents.models import Bar
from fxagents.state import LiveState
from tests.test_c10_book import CFG, TZ, m15, ndq_minutes


class FS:
    def __init__(self, m1, st):
        self.st, self.f = st, {r: m1[["open", "high", "low", "close"]].tz_convert(TZ).resample(r, label="left", closed="left")
                               .agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                               for r in ("5min", "15min")}
    def tf(self, sym, rule):
        b = self.f[rule]
        return b[b.index + pd.Timedelta(rule) <= self.st.now]


class FakeJev:
    """Says CUT when the trade is under water, ADD when it is above +0.5R, otherwise HOLD."""
    def __init__(self): self.calls = []
    async def manage_trade(self, info):
        self.calls.append(info)
        r = info["r_now"]
        return {"p_worse": 0.8 if r < 0 else 0.3, "conf_worse": 0.6, "p_extend": 0.7 if r > 0.5 else 0.4,
                "conf_extend": 0.6, "source": "jev"}


def run(tmp_path, with_adviser: bool):
    m1 = ndq_minutes()
    cfg = copy.deepcopy(CFG)
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 100000
    bus, jev = Bus(), FakeJev()
    closed = []
    bus.subscribe("position_closed", lambda ev: closed.append(ev["position"]))
    j = Journal(str(tmp_path / f"j{int(with_adviser)}.sqlite"))
    ctx = Ctx(cfg, bus, st, FS(m1, st), PaperBroker(cfg, st, bus), j, jev, None)
    ctx.book_key = "c10_afternoon"
    tr = C10Trader(ctx); tr.start()
    ad = None
    if with_adviser:
        ad = ja.JevAdvisorAgent(ctx); ad.start(); assert ad.on
    loc = m1.tz_convert(TZ)
    sel = loc[((loc.index.hour == 12) & (loc.index.minute == 59)) | ((loc.index.hour >= 13) & (loc.index.hour < 16))]

    async def go():
        for ts, r in sel.iterrows():
            st.now = ts + pd.Timedelta("1min"); st.last_prices["NDQ"] = r.close
            b = Bar("NDQ", ts, r.open, r.high, r.low, r.close, 1.0)
            await ctx.broker.on_bar(b)
            await tr.on_bar(b)
            if ad:
                await ad.on_bar(b)
                await ad.drain()          # advice runs in the background; settle it before the next bar
    asyncio.run(go())
    return closed, j, jev


def test_adviser_logs_and_scores_but_never_changes_a_trade(tmp_path):
    base, _, _ = run(tmp_path, False)
    closed, j, jev = run(tmp_path, True)
    key = lambda ps: [(str(p.opened_ts), p.exit_reason, round(p.realized, 6)) for p in ps]
    assert key(base) == key(closed) and closed                      # identical trades: advice is never acted on
    rows = [dict(r) for r in j.db.execute("SELECT * FROM jev_advice")]
    assert rows and jev.calls
    for r in rows:
        t = pd.Timestamp(r["ts"]).tz_convert(TZ)
        assert t.minute % 15 == 0 and r["held_min"] >= 14.5                # 15-minute closes, from 15 min after entry
        assert r["action"] == ("cut" if r["r_now"] < 0 else "add" if r["r_now"] > 0.5 and r["p_extend"] >= 0.6 else "hold")
    info = jev.calls[0]
    assert info["thesis"] and info["time_exit_ny"] == "15:45" and info["candles_15m_today"] and info["side"] in ("LONG", "SHORT")
    out = [dict(r) for r in j.db.execute("SELECT * FROM jev_advice_outcome")]
    assert len(out) == len(rows)
    finals = {p.id: p.realized / (p.initial_qty * p.risk_per_unit * float(CFG["instruments"]["NDQ"]["multiplier"])) for p in closed}
    for o in out:
        assert abs(o["final_r"] - finals[o["pos_id"]]) < 1e-3 and abs(o["value_cut"] - (o["r_if_exit"] - o["final_r"])) < 1e-3
    sc = ja.scorecard(j)
    assert sc["n_trades"] >= 1 and sc["n_calls"] == len(rows) and {a["action"] for a in sc["actions"]} <= {"cut", "hold", "add"}
    assert "policy" in sc and sc["policy"]["trades"] == sc["n_trades"]


def test_adviser_stays_off_for_other_books(tmp_path):
    ctx = Ctx(copy.deepcopy(CFG), Bus(), LiveState(), None, None, Journal(str(tmp_path / "x.sqlite")), FakeJev(), None)
    ctx.book_key = "playbook"
    a = ja.JevAdvisorAgent(ctx); a.start()
    assert not a.on


def _agent(tmp_path, jev):
    st = LiveState()
    ctx = Ctx(copy.deepcopy(CFG), Bus(), st, None, None, Journal(str(tmp_path / "bg.sqlite")), jev, None)
    ctx.book_key = "c10_afternoon"
    ad = ja.JevAdvisorAgent(ctx); ad.start(); assert ad.on
    return ad, st


class _Pos:
    id, symbol, strategy, side, status = "p1", "NDQ", "c10_afternoon", 1, "open"
    opened_ts = pd.Timestamp("2026-10-26 17:00", tz="UTC")
    meta: dict = {}
    mfe_r = 0.2
    def __init__(self): self.meta, self.events = {}, []
    def log(self, ts, kind, **d): self.events.append(kind)
    def r_now(self, price): return 0.1


class SlowJev:
    def __init__(self, delay=0.2): self.calls, self.delay = 0, delay
    async def manage_trade(self, info):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return {"p_worse": 0.3, "conf_worse": 0.6, "p_extend": 0.4, "conf_extend": 0.6, "source": "jev"}


def _bg(tmp_path, jev, scenario):
    ad, st = _agent(tmp_path, jev)
    pos = _Pos(); st.positions[pos.id] = pos
    ad.info_for = lambda *a: {"r_now": 0.1}
    ad.r_if_exit = lambda p, px: 0.05
    bar = lambda m: Bar("NDQ", pd.Timestamp("2026-10-26 17:00", tz="UTC") + pd.Timedelta(minutes=m), 1, 1, 1, 100.0, 1.0)

    async def go():
        await scenario(ad, st, pos, bar)
    asyncio.run(go())
    return ad, pos, [dict(r) for r in ad.ctx.journal.db.execute("SELECT * FROM jev_advice")]


def test_on_bar_returns_before_slow_jev_and_records_after(tmp_path):
    jev, seen = SlowJev(0.3), {}
    async def sc(ad, st, pos, bar):
        await ad.on_bar(bar(14))                      # bar end 17:15 -> held 15 min
        seen["before"] = len(list(ad.ctx.journal.db.execute("SELECT * FROM jev_advice")))
        seen["pending"] = len(ad._tasks)
        await ad.drain()
    ad, pos, rows = _bg(tmp_path, jev, sc)
    assert seen == {"before": 0, "pending": 1}
    assert len(rows) == 1 and rows[0]["ts"].startswith("2026-10-26T17:15") and rows[0]["held_min"] == 15.0
    assert pos.events == ["jev_advice"] and not ad._tasks


def test_reply_for_closed_position_is_dropped(tmp_path):
    async def sc(ad, st, pos, bar):
        await ad.on_bar(bar(14))
        pos.status = "closed"
        await ad.drain()
    _, pos, rows = _bg(tmp_path, SlowJev(0.05), sc)
    assert rows == [] and pos.events == []


def test_one_call_in_flight_per_position(tmp_path):
    jev = SlowJev(0.2)
    async def sc(ad, st, pos, bar):
        await ad.on_bar(bar(14)); await ad.on_bar(bar(29))   # second 15-min mark while the first is running
        await ad.drain()
        await ad.on_bar(bar(44)); await ad.drain()           # free again afterwards
    _, _, rows = _bg(tmp_path, jev, sc)
    assert jev.calls == 2 and len(rows) == 2


def test_jev_error_and_timeout_are_contained(tmp_path):
    class Boom:
        async def manage_trade(self, info): raise RuntimeError("x")
    async def sc(ad, st, pos, bar):
        await ad.on_bar(bar(14)); await ad.drain()
    _, _, rows = _bg(tmp_path, Boom(), sc)
    assert rows == []


def test_scorecard_helped_is_action_specific(tmp_path):
    j = Journal(str(tmp_path / "sc.sqlite")); ja.ensure_schema(j)
    # trade finished better (-0.5 at advice, +1 final): value_cut = -1.5 -> HOLD right, CUT wrong; ADD value 0.4 -> right
    for i, (act, vc, va) in enumerate([("hold", -1.5, 0.0), ("cut", -1.5, 0.0), ("add", -1.5, 0.4)], 1):
        j.db.execute("INSERT INTO jev_advice_outcome VALUES(?,?,?,?,?,?,?,?,?)", (i, "p", "s", "jev", act, -0.5, 1.0, vc, va))
    j.db.commit()
    h = {a["action"]: a["helped"] for a in ja.scorecard(j)["actions"]}
    assert h == {"hold": 1.0, "cut": 0.0, "add": 1.0}
