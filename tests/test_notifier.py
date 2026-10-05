"""Notification grouping: trade updates fold into the exit, news/bias/promotion arrive as one digest,
and on Telegram the exit replies to its entry."""
import asyncio
from datetime import datetime

import pandas as pd

from fxagents.agents.core import Ctx
from fxagents.agents.ops import NotifierAgent
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.models import Leg, Position
from fxagents.state import LiveState

TZ = "America/New_York"


class FakeResp:
    def __init__(self, mid): self.mid = mid
    def json(self): return {"ok": True, "result": {"message_id": self.mid}}


class FakeClient:
    posts: list = []
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None, content=None, headers=None):
        FakeClient.posts.append({"url": url, "json": json})
        return FakeResp(100 + len(FakeClient.posts))


def make(monkeypatch, **grouping):
    import copy
    import fxagents.agents.ops as ops
    cfg = copy.deepcopy(load_config("config.yaml"))
    cfg["mode"] = "paper"
    n = cfg["notifications"]
    n.update(ntfy_topic="", telegram_bot_token="T", telegram_chat_id="42")
    n["grouping"] = {"fold_trade_updates": True, "digest_minutes": 60,
                     "digest_events": ["news", "bias", "promotion"], **grouping}
    FakeClient.posts = []
    monkeypatch.setattr(ops.httpx, "AsyncClient", FakeClient)
    st = LiveState(); st.now = pd.Timestamp("2026-10-05 09:00", tz=TZ)
    a = NotifierAgent(Ctx(cfg, Bus(), st, None, None, None, None, None)); a.start()
    return a, st


def pos():
    p = Position(symbol="XAUUSD", side=1, strategy="ict2022", stop=2390.0, initial_stop=2390.0,
                 risk_per_unit=10.0, rr=2.0, opened_ts=datetime(2026, 10, 5, 9))
    p.legs.append(Leg(ts=datetime(2026, 10, 5, 9), qty=5, price=2400.0, kind="initial"))
    return p


def test_trade_updates_fold_into_exit_and_exit_replies_to_entry(monkeypatch):
    a, _ = make(monkeypatch)
    p = pos()
    asyncio.run(a.on_open(p))
    for e, m in [("partial", "half off at +1R"), ("stop_to_profit", "SL → 2401"), ("pyramid", "added 2 @ 2412")]:
        asyncio.run(a.on_update({"event": e, "position": p, "msg": m}))
    assert len(FakeClient.posts) == 1                       # only the entry buzzed
    p.realized, p.exit_reason = 512.0, "target"
    asyncio.run(a.on_close({"position": p, "price": 2420.0}))
    assert len(FakeClient.posts) == 2
    exit_msg = FakeClient.posts[1]["json"]
    assert exit_msg["reply_parameters"]["message_id"] == 101          # threaded under the entry
    for m in ("half off at +1R", "SL → 2401", "added 2 @ 2412"):
        assert m in exit_msg["text"]
    assert exit_msg["parse_mode"] == "HTML"


def test_digest_groups_news_bias_promotion_hourly(monkeypatch):
    a, st = make(monkeypatch)
    t0 = st.now
    asyncio.run(a.on_clock(t0))
    asyncio.run(a.on_alert({"msg": "CPI 08:30", "event": "news", "title": "📰 News ahead"}))
    asyncio.run(a.on_alert({"msg": "NDQ bias suspended", "event": "bias", "title": "🧭 Bias suspended"}))
    asyncio.run(a.queue("promotion", "Playbook", "refreshed: 12 cells"))
    asyncio.run(a.on_clock(t0 + pd.Timedelta(minutes=30)))
    assert FakeClient.posts == []                           # nothing yet
    asyncio.run(a.on_clock(t0 + pd.Timedelta(minutes=61)))
    assert len(FakeClient.posts) == 1
    msg = FakeClient.posts[0]["json"]
    assert "3 updates" in msg["text"] and "CPI 08:30" in msg["text"] and "12 cells" in msg["text"]
    assert msg["disable_notification"] is True              # digest arrives silently


def test_kill_switch_is_immediate_and_html_is_escaped(monkeypatch):
    a, _ = make(monkeypatch)
    asyncio.run(a.on_alert({"msg": "daily loss <-3%> hit", "event": "kill_switch", "title": "⚠ FX-Agents"}))
    assert len(FakeClient.posts) == 1
    assert "&lt;-3%&gt;" in FakeClient.posts[0]["json"]["text"]


def test_digest_off_sends_each_at_once(monkeypatch):
    a, _ = make(monkeypatch, digest_minutes=0)
    asyncio.run(a.on_alert({"msg": "CPI 08:30", "event": "news", "title": "📰 News ahead"}))
    assert len(FakeClient.posts) == 1


def test_daily_summary_flushes_pending_digest_first(monkeypatch):
    a, _ = make(monkeypatch)
    asyncio.run(a.on_alert({"msg": "CPI 08:30", "event": "news", "title": "📰 News ahead"}))
    asyncio.run(a.on_daily({"msg": "+3.1R today"}))
    assert len(FakeClient.posts) == 2
    assert "CPI" in FakeClient.posts[0]["json"]["text"] and "+3.1R" in FakeClient.posts[1]["json"]["text"]
