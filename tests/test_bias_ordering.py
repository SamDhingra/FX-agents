"""Oct 26 2026 — the bias is refreshed before the first entry after an hour closes; the hour's minute count is
recorded; stale bias is dropped before Jev is asked; the 15m-candle shadow tag is recorded and decides nothing."""
import asyncio
import copy
import logging
from types import SimpleNamespace

import numpy as np
import pandas as pd

from fxagents.agents.context import BiasAgent
from fxagents.agents.core import Ctx
from fxagents.agents.trading import MarketDataAgent, RiskAgent, TraderAgent
from fxagents.bus import Bus
from fxagents.data import BarStore
from fxagents.journal import Journal
from fxagents.models import Bar, Leg, Signal
from fxagents.mtf_whatif import live_m15_against
from fxagents.state import LiveState
from tests.test_core import CFG, TZ


def run(c):
    return asyncio.run(c)


H = pd.Timestamp("2026-10-26 10:00", tz=TZ)          # the hour boundary under test (09:00–10:00 closes)


class StubJev:
    def __init__(self):
        self.calls = 0

    async def bias_audit(self, info):
        self.calls += 1
        return {"prob": 0.9, "source": "jev", "fallback": False, "error": ""}


class NullBroker:
    async def on_bar(self, bar):
        pass


def rig(last_closes_until=None):
    """Real MarketData + Bias agents on one bus. The bias reading is a function of the newest stored minute
    (> 100 = BULLISH), so it can only be right if the bar was stored first. `seen` records the bias a trader sees on
    each bar_signal (5m close)."""
    cfg = copy.deepcopy(CFG)
    cfg["instruments"] = {"NDQ": cfg["instruments"]["NDQ"]}
    st = LiveState(mode="paper")
    store = BarStore(TZ, max_days=5)
    for ts in pd.date_range("2026-10-26 08:00", "2026-10-26 08:59", freq="1min", tz=TZ):
        store.append(Bar("NDQ", ts, 90, 90, 90, 90, 1.0))
    bus, jev = Bus(), StubJev()
    ctx = Ctx(cfg, bus, st, store, NullBroker(), None, jev, None)
    md, bias = MarketDataAgent(ctx), BiasAgent(ctx)
    md.start(); bias.start()
    bias.updates = []

    def compute(sym, now):
        c = float(store.m1(sym)["close"].iloc[-1])
        lab = "BULLISH" if c > 100 else "BEARISH"
        return {"score": 0.8 if c > 100 else -0.8, "d": 1, "h4": 1, "h1": 1 if c > 100 else -1, "label": lab,
                "pd_pos": 0.5, "pdh": 1.0, "pdl": 0.0, "asia_hi": 1.0, "asia_lo": 0.0, "h4_swing_hi": 1.0,
                "h4_swing_lo": 0.0, "price": c}
    bias.compute = compute
    orig = bias.update

    async def counted(sym, now):
        bias.updates.append(now)
        return await orig(sym, now)
    bias.update = counted
    seen = []

    async def trader(ev):                                           # runs after MarketData (subscription order)
        seen.append((ev["ts"], st.bias["NDQ"]["label"]))
    bus.subscribe("bar_signal", trader)
    return SimpleNamespace(cfg=cfg, st=st, store=store, bus=bus, jev=jev, bias=bias, seen=seen)


def feed(r, start, end, close, mode):
    """Publish minutes start..end (inclusive) the way the live loop (clock a few seconds after) or the replay
    (state.now = bar end, clock right after the bar) does."""
    for ts in pd.date_range(start, end, freq="1min", tz=TZ):
        c = close(ts)
        r.st.now = ts + pd.Timedelta("1min") + (pd.Timedelta("20s") if mode == "live" else pd.Timedelta(0))
        run(r.bus.publish("bar", Bar("NDQ", ts, c, c, c, c, 1.0)))
        run(r.bus.publish("clock", r.st.now + (pd.Timedelta("5s") if mode == "live" else pd.Timedelta(0))))


def flip(ts):
    return 110 if ts >= H - pd.Timedelta("1min") else 90         # the hour's final minute closes above 100


def bar_before(ts):
    return 90


def test_the_first_entry_after_the_hour_sees_the_new_bias_live_and_replay():
    for mode in ("live", "replay"):
        r = rig()
        feed(r, "2026-10-26 09:00", "2026-10-26 09:58", bar_before, mode)
        assert r.st.bias["NDQ"]["label"] == "BEARISH"
        n = len(r.bias.updates)
        feed(r, "2026-10-26 09:59", "2026-10-26 09:59", flip, mode)
        sig_at_hour = [lab for ts, lab in r.seen if ts == H]
        assert sig_at_hour and set(sig_at_hour) == {"BULLISH"}, mode                   # the 10:00 signal bar saw the completed hour
        assert r.st.bias["NDQ"]["updated"].startswith("2026-10-26T10:00")
        # the clock tick that followed did not update again (and so did not ask Jev again)
        assert len(r.bias.updates) == n + 1, mode
        asked = r.jev.calls                                       # one audit per reading: BEARISH 09:xx, BULLISH 10:00
        feed(r, "2026-10-26 10:00", "2026-10-26 10:03", lambda ts: 110, mode)
        assert len(r.bias.updates) == n + 1 and r.jev.calls == asked, mode


def test_a_late_final_minute_still_updates_once_when_it_arrives():
    r = rig()
    feed(r, "2026-10-26 09:00", "2026-10-26 09:58", bar_before, "replay")
    n = len(r.bias.updates)
    for m in range(0, 7):                                         # the clock passes the hour, the 09:59 bar is missing
        r.st.now = H + pd.Timedelta(minutes=m)
        run(r.bus.publish("clock", r.st.now))
    assert len(r.bias.updates) == n + 1                           # one grace update at 10:05
    assert r.st.bias["NDQ"]["label"] == "BEARISH" and r.st.bias["NDQ"]["h1_complete"] is False
    r.st.now = H + pd.Timedelta("7min")
    run(r.bus.publish("bar", Bar("NDQ", H - pd.Timedelta("1min"), 110, 110, 110, 110, 1.0)))   # it finally arrives
    assert len(r.bias.updates) == n + 2 and r.st.bias["NDQ"]["label"] == "BULLISH"
    run(r.bus.publish("clock", H + pd.Timedelta("8min")))
    assert len(r.bias.updates) == n + 2                           # and the hour is final: no further update


def test_a_late_final_minute_by_backfill_is_picked_up_by_the_clock():
    r = rig()
    feed(r, "2026-10-26 09:00", "2026-10-26 09:58", bar_before, "replay")
    for m in range(0, 7):
        r.st.now = H + pd.Timedelta(minutes=m)
        run(r.bus.publish("clock", r.st.now))
    run(r.bus.publish("backfill", [Bar("NDQ", H - pd.Timedelta("1min"), 110, 110, 110, 110, 1.0)]))
    r.st.now = H + pd.Timedelta("8min")
    run(r.bus.publish("clock", r.st.now))
    assert r.st.bias["NDQ"]["label"] == "BULLISH"


def test_an_hour_without_its_final_bar_still_updates_after_the_grace_period():
    r = rig()                                                     # nothing ever arrives for 09:xx (daily break style)
    for m in range(0, 6):
        r.st.now = H + pd.Timedelta(minutes=m)
        run(r.bus.publish("clock", r.st.now))
    assert len(r.bias.updates) == 1 and r.bias.updates[0] == H + pd.Timedelta("5min")


# ── 2. minute counts ─────────────────────────────────────────────────────────────────────────────────────
def count_rig(drop):
    r = rig()
    store = BarStore(TZ, max_days=5)
    for ts in pd.date_range("2026-10-26 09:00", "2026-10-26 09:59", freq="1min", tz=TZ):
        if ts.strftime("%H:%M") not in drop:
            store.append(Bar("NDQ", ts, 100, 100, 100, 100, 1.0))
    r.bias.ctx.store = store
    return r


def test_minute_counts_and_completeness(caplog):
    cases = [([], 60, True), (["09:30"], 59, True), (["09:59"], 59, False),
             ([f"09:{m}" for m in range(10, 15)], 55, True), ([f"09:{m}" for m in range(10, 16)], 54, False)]
    for drop, n, full in cases:
        r = count_rig(drop)
        assert r.bias.hour_minutes("NDQ", H + pd.Timedelta("3min")) == (n, full), drop
    r = count_rig(["09:30"])
    run(r.bias.update("NDQ", H))
    assert r.st.bias["NDQ"]["h1_minutes"] == 59 and r.st.bias["NDQ"]["h1_complete"] is True
    r = count_rig([f"09:{m}" for m in range(10, 20)])
    with caplog.at_level(logging.WARNING, logger="bias"):
        run(r.bias.update("NDQ", H)); run(r.bias.update("NDQ", H + pd.Timedelta("1min")))
    assert r.st.bias["NDQ"]["h1_minutes"] == 50 and r.st.bias["NDQ"]["h1_complete"] is False
    assert len([x for x in caplog.records if "only 50 of 60" in x.message]) == 1       # warned once for the hour


def test_a_short_hour_does_not_block_anything():
    r = count_rig([f"09:{m}" for m in range(10, 20)])
    run(r.bias.update("NDQ", H))
    assert r.st.bias["NDQ"]["state"] == "BEARISH" or r.st.bias["NDQ"]["state"] in ("BULLISH", "IN DOUBT")
    assert r.st.bias["NDQ"]["h1_complete"] is False and r.st.bias["NDQ"]["label"] != "NEUTRAL"


# ── 3. stale bias in the precheck ────────────────────────────────────────────────────────────────────────
def test_a_stale_bias_is_dropped_before_jev_is_asked():
    cfg = copy.deepcopy(CFG)
    st = LiveState(); st.now = H
    old = (H - pd.Timedelta(minutes=151)).isoformat(timespec="minutes")
    st.bias["NDQ"] = {"suspended": False, "in_doubt": False, "aligned_losses": 0, "score": 0.8, "label": "BULLISH",
                      "d": 1, "h4": 1, "h1": 1, "updated": old}
    rows = []

    class J:
        def add_signal(self, s): rows.append(s)

    class NoJev:
        calls = 0
        async def rate_signal(self, info):
            self.calls += 1
            return {"quality": 0.9, "confidence": 0.9, "source": "jev"}
    jev = NoJev()
    me = SimpleNamespace(cfg=cfg, state=st, now=lambda: H, ctx=SimpleNamespace(journal=J(), jev=jev, news=None))
    me.bias_precheck = lambda s: TraderAgent.bias_precheck(me, s)
    sig = Signal("NDQ", "x:5m@v1", 1, 100.0, 99.0, H)
    run(TraderAgent.evaluate(me, sig, None, pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})))
    assert jev.calls == 0 and rows[0]["action"] == "filtered" and rows[0]["why"].startswith("bias stale: last updated 2h31m ago")
    risk = SimpleNamespace(cfg=cfg, state=st, ctx=SimpleNamespace(store=None, jev=None))
    assert run(RiskAgent.bias_gate(risk, sig, {"quality": 0.8}, H))["reject"] == rows[0]["why"]      # the same text
    st.bias["NDQ"]["updated"] = (H - pd.Timedelta(minutes=149)).isoformat(timespec="minutes")
    assert me.bias_precheck(sig) is None


# ── 4. shadow tag: 15m candle in progress against the entry ──────────────────────────────────────────────
def m1_path(prices, start="2026-10-26 09:30"):
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=TZ)
    p = np.asarray(prices, float)
    o = np.r_[p[0], p[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, p), "low": np.minimum(o, p), "close": p, "volume": 1.0}, index=idx)


def test_the_tag_on_a_rising_and_a_falling_15m_candle():
    rising = m1_path(np.linspace(100, 104, 8))                     # 09:30..09:37, entry at 09:38 (candle opens at 100)
    ts = pd.Timestamp("2026-10-26 09:38", tz=TZ)
    assert live_m15_against(rising, ts, -1, 104.0) is True         # short into a rising candle
    assert live_m15_against(rising, ts, 1, 104.0) is False
    falling = m1_path(np.linspace(100, 96, 8))
    assert live_m15_against(falling, ts, 1, 96.0) is True
    assert live_m15_against(falling, ts, -1, 96.0) is False
    # at a 15m boundary it is the candle that just closed
    three = m1_path(np.linspace(100, 108, 15))                     # 09:30..09:44
    assert live_m15_against(three, pd.Timestamp("2026-10-26 09:45", tz=TZ), -1, 108.0) is True
    # missing data → None
    assert live_m15_against(rising, pd.Timestamp("2026-10-26 09:50", tz=TZ), -1, 104.0) is None
    assert live_m15_against(rising.iloc[0:0], ts, -1, 104.0) is None


def entry_rig(tmp_path, strategy, closes):
    cfg = copy.deepcopy(CFG); cfg["mode"] = "paper"
    cfg["risk"]["cost_cap_enforce"] = False
    cfg["instruments"]["XAUUSD"].update(multiplier=1, tick_size=0.01, qty_step=1, min_units=1, max_units=1e6, margin_rate=0)
    st = LiveState(mode="paper"); st.now = pd.Timestamp("2026-10-26 09:38", tz=TZ); st.equity = 100000.0
    st.last_prices["XAUUSD"] = 100.0
    st.bias["XAUUSD"] = {"suspended": False, "score": 1.0, "in_doubt": False, "label": "BULLISH", "d": 1, "h4": 1, "h1": 1}
    store = BarStore(TZ, max_days=5)
    for ts, c in zip(pd.date_range("2026-10-26 09:30", periods=len(closes), freq="1min", tz=TZ), closes):
        store.append(Bar("XAUUSD", ts, c, c, c, c, 1.0))

    class B:
        price_bound = False
        async def quote(self, sym): return None
        async def equity(self): return 100000.0
        async def open(self, p, qty, ref):
            p.add_leg(Leg(qty, ref, p.opened_ts, "initial")); return ref
    j = Journal(str(tmp_path / "j.sqlite"))
    ra = RiskAgent(Ctx(cfg, Bus(), st, store, B(), j, None, None)); ra.start()
    sig = Signal("XAUUSD", strategy, 1, 100.0, 99.0, st.now)
    rec = {"ts": st.now.isoformat(), "symbol": "XAUUSD", "strategy": strategy, "side": "LONG", "entry": 100.0, "stop": 99.0}
    run(ra.on_request({"signal": sig, "grade": {"quality": 0.8, "confidence": 0.8, "source": "t"}, "record": rec}))
    return st, j


def test_the_tag_is_stored_on_the_trade_and_the_entry_is_still_taken(tmp_path):
    # a long at 100 inside a 15m candle that opened at 102 (fell 2): the candle is against the trade
    st, j = entry_rig(tmp_path, "macd_cross:5m@pb-x", [102] * 7 + [100])
    (pos,) = st.positions.values()                                 # still taken: the tag decides nothing
    assert pos.meta["m15_live"] is True and [e for e in pos.events if e["kind"] == "entry"][0]["m15_live"] is True
    j.upsert_trade(pos, 1.0)
    assert j.db.execute("SELECT m15_live FROM trades WHERE id=?", (pos.id,)).fetchone()[0] == 1
    (tmp_path / "b").mkdir()
    st2, j2 = entry_rig(tmp_path / "b", "macd_cross:3m@pb-x", [98] * 7 + [100])
    (p2,) = st2.positions.values()
    assert p2.meta["m15_live"] is False
    j2.upsert_trade(p2, 1.0)
    assert j2.db.execute("SELECT m15_live FROM trades WHERE id=?", (p2.id,)).fetchone()[0] == 0


def test_no_tag_for_other_timeframes_or_missing_data(tmp_path):
    (tmp_path / "c").mkdir(); (tmp_path / "d").mkdir()
    st, j = entry_rig(tmp_path / "c", "macd_cross:15m@pb-x", [102] * 7 + [100])
    (pos,) = st.positions.values()
    assert pos.meta["m15_live"] is None
    j.upsert_trade(pos, 1.0)
    assert j.db.execute("SELECT m15_live FROM trades WHERE id=?", (pos.id,)).fetchone()[0] is None
    st2, _ = entry_rig(tmp_path / "d", "macd_cross:5m@pb-x", [])      # no minute bars at all
    (p2,) = st2.positions.values()
    assert p2.meta["m15_live"] is None


def test_the_journal_migrates_an_old_database(tmp_path):
    Journal(str(tmp_path / "old.sqlite")).db.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "old.sqlite")
    db.execute("ALTER TABLE trades DROP COLUMN m15_live"); db.commit(); db.close()      # a journal from before this change
    j = Journal(str(tmp_path / "old.sqlite"))
    assert "m15_live" in {r[1] for r in j.db.execute("PRAGMA table_info(trades)")}


def test_the_story_and_ask_carry_the_tag(tmp_path):
    from fastapi.testclient import TestClient
    from fxagents.dashboard import ask
    from fxagents.dashboard.server import build_app
    from tests.test_dashboard_insights import make_ctx
    ctx = make_ctx(tmp_path)
    c = TestClient(build_app(ctx))
    assert c.get("/api/story/recent").json()["shadow_tags"] == []        # not recorded: nothing shown
    ctx.journal.db.execute("UPDATE trades SET m15_live=1 WHERE id='recent'"); ctx.journal.db.commit()
    s = c.get("/api/story/recent").json()
    assert s["trade"]["m15_live"] is True
    assert s["shadow_tags"][0]["text"] == "15m candle against the entry: yes (shadow tag, not used for decisions)"
    ctx.journal.db.execute("UPDATE trades SET m15_live=0 WHERE id='recent'"); ctx.journal.db.commit()
    assert c.get("/api/story/recent").json()["shadow_tags"][0]["text"].startswith("15m candle against the entry: no")
    ctx.journal.db.execute("UPDATE trades SET m15_live=1 WHERE id='recent'"); ctx.journal.db.commit()
    rows = ask.gather(ctx, "how did the last XAUUSD trade go")["books"]["live"]["latest_trades"]
    assert any(t.get("m15_candle_against_entry") == 1 for t in rows)
