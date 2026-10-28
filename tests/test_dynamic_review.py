"""Shadow review gate (Oct 26 2026, docs/dynamic_controller.md, milestone 1): the as-of packet, the two providers, the
background reviewer and its hook, the budget, the scorecard arms and the dashboard. No network: httpx is stubbed."""
import asyncio
import copy
import json
import time

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fxagents.agents.core import Ctx
from fxagents.agents.dynamic_review import DynamicReviewAgent
from fxagents.agents.trading import RiskAgent
from fxagents.bus import Bus
from fxagents.dashboard import ask
from fxagents.dashboard.server import build_app
from fxagents.data import BarStore
from fxagents.dynamic import packet as P
from fxagents.dynamic import providers as PR
from fxagents.dynamic import score as S
from fxagents.dynamic import store as DS
from fxagents.journal import Journal
from fxagents.models import Bar, Leg, Signal
from fxagents.state import LiveState
from tests.test_core import CFG, TZ
from tests.test_dashboard_insights import make_ctx

TS = pd.Timestamp("2026-10-26 09:38", tz=TZ)


def run(c):
    return asyncio.run(c)


def minutes(start="2026-10-25 06:00", end="2026-10-26 09:45", base=2650.0):
    idx = pd.date_range(start, end, freq="1min", tz=TZ)
    rng = np.random.default_rng(3)
    px = base + np.cumsum(rng.normal(0, 0.3, len(idx)))
    return idx, px


def fill_store(store, sym="XAUUSD", **kw):
    idx, px = minutes(**kw)
    for ts, c in zip(idx, px):
        store.append(Bar(sym, ts, c, c + 0.4, c - 0.4, c + 0.1234, 1.0))


# ── 1. the packet ──────────────────────────────────────────────────────────────────────────────────────────────
def mk_packet(ts=TS, store=None, **kw):
    store = store or BarStore(TZ, max_days=5)
    if not len(store.m1("XAUUSD")):
        fill_store(store)
    args = dict(candidate_id="abc123", book="live", symbol="XAUUSD", side=1, strategy="macd_cross:5m@pb-x", ts=ts, entry=2650.126,
                stop=2648.0, target_r=2.0, spread=0.31, cost_r=0.14, instrument={"tick_size": 0.01}, m1=store.m1("XAUUSD"),
                h1=store.h1("XAUUSD"), bias={"label": "BULLISH", "score": 0.7, "d": 1, "h4": 1, "h1": np.int64(1), "updated": "2026-10-26T09:00-04:00",
                                             "h1_minutes": 60, "h1_complete": True, "pdh": 2660.5, "pdl": 2630.25, "asia_hi": float("nan"),
                                             "asia_lo": 2645.0, "h4_swing_hi": 2655.0, "h4_swing_lo": 2640.0},
                record={"trades": 12, "avg_r": 0.2}, m15_live=False)
    args.update(kw)
    return P.build_packet(**args), store


def test_packet_holds_only_what_was_known_at_the_entry():
    p, store = mk_packet()
    c = p["candles"]
    starts = [r[0] for k in ("m5_closed", "m15_closed", "h1_closed") for r in c[k]]
    assert all(pd.Timestamp(s, tz=TZ) < TS for s in starts)
    last5 = pd.Timestamp(c["m5_closed"][-1][0], tz=TZ)
    assert last5 + pd.Timedelta("5min") <= TS and len(c["m5_closed"]) == 24 and len(c["m15_closed"]) == 16
    last15 = pd.Timestamp(c["m15_closed"][-1][0], tz=TZ)
    assert last15 + pd.Timedelta("15min") <= TS
    # the 15m candle in progress is separate and labelled partial; it holds only the minutes closed before 09:38
    f = c["m15_forming"]
    assert f["partial"] is True and f["start"] == "2026-10-26 09:30" and f["minutes_in"] == 8
    m1 = store.m1("XAUUSD")
    seg = m1[(m1.index >= "2026-10-26 09:30") & (m1.index <= "2026-10-26 09:37")]
    assert f["ohlc"][1] == round(float(seg.high.max()), 2) and f["ohlc"][2] == round(float(seg.low.min()), 2)
    assert f["start"] not in [r[0] for r in c["m15_closed"]]
    # nothing at or after the entry minute appears anywhere, however much later data the store holds
    later = BarStore(TZ, max_days=5)
    fill_store(later, end="2026-10-26 10:30")
    p2, _ = mk_packet(store=later)
    assert p2["packet_hash"] == p["packet_hash"] and p2 == p
    assert "2026-10-26 09:38" not in json.dumps(p["candles"]) and "2026-10-26 10:" not in json.dumps(p["candles"])


def test_packet_keeps_precision_and_is_deterministic():
    p, _ = mk_packet()
    assert p["order"]["entry"] == 2650.13 and p["order"]["price_decimals"] == 2 and p["order"]["tick_size"] == 0.01
    assert p["order"]["stop_distance"] == 2.13 and p["order"]["cost_r"] == 0.14
    for row in p["candles"]["m5_closed"]:
        for v in row[1:]:
            assert round(v, 2) == v
    assert p["bias"]["h1"] == 1 and p["bias"]["minutes_since_update"] == 38 and p["bias"]["h1_complete"] is True
    assert p["levels"]["asia_hi"] is None and p["levels"]["pdh"] == 2660.5       # NaN level → null, not "nan"
    assert p["candidate"]["entry_time_utc"] == "2026-10-26 13:38" and p["candidate"]["timeframe"] == "5m"
    assert p["setup_record"] == {"trades": 12, "avg_r": 0.2} and p["candles"]["m15_live_against_entry"] is False
    p2, _ = mk_packet()
    assert P.canonical(p) == P.canonical(p2)
    body = {k: v for k, v in p.items() if k != "packet_hash"}
    import hashlib
    assert p["packet_hash"] == hashlib.sha256(P.canonical(body).encode()).hexdigest()
    p3, _ = mk_packet(entry=2650.5)
    assert p3["packet_hash"] != p["packet_hash"]
    assert P.decimals_for({"tick_size": 0.25}, "NDQ") == 2 and P.decimals_for({"tick_size": 1.0}, "US30") == 0
    assert P.decimals_for({}, "US30") == 1 and P.decimals_for(None, "EURUSD") == 5


def test_packet_survives_missing_data_and_names_the_next_release():
    p, _ = mk_packet(m1=pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), h1=None, bias=None, record=None)
    assert p["candles"]["m5_closed"] == [] and p["candles"]["m15_forming"] is None and p["setup_record"] is None
    assert p["bias"]["label"] is None and p["bias"]["minutes_since_update"] is None
    q, _ = mk_packet(ts=pd.Timestamp("2026-10-28 13:30", tz=TZ))                  # FOMC statement day, 14:00 NY
    assert q["session"]["next_release"] == {"name": "FOMC", "time_ny": "2026-10-28 14:00", "minutes_to": 30}
    assert q["session"]["weekday"] == "Wednesday"


# ── 2. providers ───────────────────────────────────────────────────────────────────────────────────────────────
GOOD = {"candidate_id": "abc123", "action": "WAIT", "trigger_id": "retest_of_entry", "invalidation_id": "expiry_30m",
        "decisive_evidence": "Price is 1.2 below the Asia low retest.", "conflicting_evidence": "Bias is bullish.",
        "missing_data": ["order flow"]}


def claude_reply(obj=GOOD, **kw):
    return {"content": [{"type": "text", "text": json.dumps(obj)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 2000, "output_tokens": 100}, **kw}


def assert_claude_schema(sch):
    """Anthropic structured outputs: no length/number keywords, minItems 0/1 only, additionalProperties false on every object."""
    txt = json.dumps(sch)
    for kw in ("maxLength", "minLength", "maxItems", "minimum", "maximum", "multipleOf"):
        assert kw not in txt
    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "object":
                assert n.get("additionalProperties") is False
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(sch)
    assert set(sch["required"]) == set(sch["properties"])


def openai_reply(obj=GOOD, **kw):
    ch = {"message": {"content": json.dumps(obj)}, "finish_reason": "stop", **kw}
    return {"choices": [ch], "usage": {"prompt_tokens": 2100, "completion_tokens": 90}}


def provider(kind, handler, prices=None, monkeypatch=None):
    cls = PR.ClaudeProvider if kind == "claude" else PR.OpenAIProvider
    return cls("m-1", prices if prices is not None else {"m-1": {"in_per_mtok": 3.0, "out_per_mtok": 15.0}}, 5, httpx.MockTransport(handler))


def keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-SECRET")


def test_claude_and_openai_parse_valid_replies_and_price_the_tokens(monkeypatch):
    keys(monkeypatch)
    seen = {}

    def hc(req):
        seen["claude"] = (req.url, dict(req.headers), json.loads(req.content))
        return httpx.Response(200, json=claude_reply())

    def ho(req):
        seen["openai"] = (req.url, dict(req.headers), json.loads(req.content))
        return httpx.Response(200, json=openai_reply())
    for kind, h in (("claude", hc), ("openai", ho)):
        r = run(provider(kind, h).review('{"p":1}', "abc123"))
        assert r["action"] == "WAIT" and r["error"] is None and r["trigger_id"] == "retest_of_entry"
        assert r["invalidation_id"] == "expiry_30m" and r["missing"] == ["order flow"]
        assert r["tokens_in"] in (2000, 2100) and r["tokens_out"] in (100, 90)
        assert r["cost_usd"] == pytest.approx((r["tokens_in"] * 3.0 + r["tokens_out"] * 15.0) / 1e6)
    url, hd, body = seen["claude"]
    assert str(url) == "https://api.anthropic.com/v1/messages" and hd["x-api-key"] == "sk-ant-SECRET"
    assert hd["anthropic-version"] == "2023-06-01"
    assert "tools" not in body and "tool_choice" not in body and "betas" not in body and "anthropic-beta" not in hd
    assert body["output_config"]["format"]["type"] == "json_schema" and set(body["output_config"]) == {"format"}
    assert_claude_schema(body["output_config"]["format"]["schema"])
    assert body["messages"][-1]["role"] == "user" and body["max_tokens"] == 2048
    assert body["system"] == PR.SYSTEM_PROMPT and "PROMPT" not in body["messages"][0]["content"]
    url, hd, body = seen["openai"]
    assert str(url) == "https://api.openai.com/v1/chat/completions" and hd["authorization"] == "Bearer sk-oai-SECRET"
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True and rf["json_schema"]["name"] == "review"
    sch = rf["json_schema"]["schema"]
    assert sch["additionalProperties"] is False and set(sch["required"]) == set(sch["properties"])
    assert body["messages"][0]["content"] == PR.SYSTEM_PROMPT
    for secret in ("sk-ant-SECRET", "sk-oai-SECRET"):                    # a key is only ever in the header
        assert secret not in json.dumps(body)


def test_no_price_means_no_cost_and_the_tokens_are_still_kept(monkeypatch):
    keys(monkeypatch)
    r = run(provider("claude", lambda q: httpx.Response(200, json=claude_reply()), prices={}).review("{}", "abc123"))
    assert r["cost_usd"] is None and r["tokens_in"] == 2000 and r["action"] == "WAIT"


def _boom(req):
    raise httpx.ReadTimeout("slow", request=req)


BAD = [
    ("openai", lambda q: httpx.Response(200, json={"choices": [{"message": {"content": "not json {"}, "finish_reason": "stop"}]}), "not valid JSON"),
    ("openai", lambda q: httpx.Response(200, json=openai_reply({**GOOD, "candidate_id": "other"})), "does not match"),
    ("claude", lambda q: httpx.Response(200, json=claude_reply({**GOOD, "candidate_id": "other"})), "does not match"),
    ("openai", lambda q: httpx.Response(200, json=openai_reply({**GOOD, "action": "BUY"})), "action"),
    ("claude", lambda q: httpx.Response(200, json=claude_reply({**GOOD, "trigger_id": "vibes"})), "trigger_id"),
    ("claude", lambda q: httpx.Response(200, json=claude_reply({k: v for k, v in GOOD.items() if k != "decisive_evidence"})), "decisive_evidence"),
    ("openai", lambda q: httpx.Response(500, text="upstream sk-oai-SECRET exploded"), "HTTP 500"),
    ("claude", lambda q: httpx.Response(529, text="overloaded"), "HTTP 529"),
    ("claude", lambda q: httpx.Response(200, json={"content": [{"type": "text", "text": '{"action": "WAIT"'}], "stop_reason": "end_turn",
                                                    "usage": {"input_tokens": 5, "output_tokens": 5}}), "not valid JSON"),
    ("claude", lambda q: httpx.Response(200, json={"content": [], "stop_reason": "end_turn"}), "no text block"),
    ("claude", lambda q: httpx.Response(200, json={"content": [{"type": "text", "text": '{"action": "WAIT"'}], "stop_reason": "max_tokens",
                                                    "usage": {"input_tokens": 5, "output_tokens": 1024}}), "cut off (max_tokens)"),
    ("claude", _boom, "ReadTimeout"),
    ("openai", _boom, "ReadTimeout"),
    ("claude", lambda q: httpx.Response(200, json={"content": [{"type": "text", "text": "I refuse"}], "stop_reason": "refusal",
                                                    "usage": {"input_tokens": 5, "output_tokens": 5}}), "refused"),
    ("openai", lambda q: httpx.Response(200, json={"choices": [{"message": {"refusal": "no", "content": None}, "finish_reason": "stop"}]}), "refused"),
    ("openai", lambda q: httpx.Response(200, json={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}), "cut off"),
    ("claude", lambda q: httpx.Response(200, text="<html>"), "not JSON"),
]


@pytest.mark.parametrize("kind, handler, why", BAD)
def test_every_failure_is_an_abstain_with_a_reason(kind, handler, why, monkeypatch):
    keys(monkeypatch)
    r = run(provider(kind, handler).review("{}", "abc123"))
    assert r["action"] == "ABSTAIN" and why in r["error"]
    assert "SECRET" not in (r["error"] or "") and "SECRET" not in (r["response"] or "")


def test_a_missing_key_abstains_without_any_request(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def never(req):
        raise AssertionError("no request without a key")
    for kind in ("claude", "openai"):
        r = run(provider(kind, never).review("{}", "abc123"))
        assert r["action"] == "ABSTAIN" and r["error"] == f"no {'ANTHROPIC' if kind == 'claude' else 'OPENAI'}_API_KEY in the environment"


def test_long_text_is_cut_not_rejected(monkeypatch):
    keys(monkeypatch)
    r = run(provider("openai", lambda q: httpx.Response(200, json=openai_reply({**GOOD, "decisive_evidence": "x" * 900}))).review("{}", "abc123"))
    assert r["action"] == "WAIT" and len(r["evidence"]) == 300


# ── 3. the reviewer agent and the hook ─────────────────────────────────────────────────────────────────────────
class Stub(PR.Provider):
    """A provider with no HTTP: says `action` after `delay` seconds and keeps what it was shown."""
    def __init__(self, name, action="ENTER", delay=0.0, marker="", model="stub", key=True):
        self.name, self.env_key, self.model = name, name.upper() + "_KEY", model
        self.action, self.delay, self.marker, self.has_key = action, delay, marker, key
        self.seen: list[str] = []
        self.seen2: list[tuple] = []         # round 2 calls: (packet text, candidate id, the other's round-1 answer)
        self.action2, self.delay2, self.changed2, self.trigger2 = None, None, None, None     # changed2: what the model REPORTS     # round 2 defaults to the round-1 behaviour
        self.prices = {}

    def available(self):
        return self.has_key

    async def review(self, packet_json, candidate_id):
        self.seen.append(packet_json)
        await asyncio.sleep(self.delay)
        return PR.result(self.action, None, evidence=f"{self.marker} evidence", conflicting="c", tokens_in=1000, tokens_out=50,
                         cost_usd=0.01, latency_ms=5.0)


    async def review_exchange(self, packet_json, candidate_id, other_answer, own_answer=None):
        self.seen2.append((packet_json, candidate_id, other_answer, own_answer))
        await asyncio.sleep(self.delay if self.delay2 is None else self.delay2)
        act = self.action2 or self.action
        ch = (act != self.action) if self.changed2 is None else self.changed2
        return PR.result(act, None, evidence=f"{self.marker} round2", conflicting="c2", tokens_in=1500, tokens_out=60, cost_usd=0.02,
                         latency_ms=7.0, changed=ch, why_changed=f"{self.marker} why", trigger_id=self.trigger2, invalidation_id=None)


def dyn_cfg(**kw):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = "paper"
    cfg["risk"]["cost_cap_enforce"] = False
    cfg["instruments"]["XAUUSD"].update(multiplier=1, tick_size=0.01, qty_step=1, min_units=1, max_units=1e6, margin_rate=0)
    cfg["dynamic"] = {"enabled": True, "books": ["live", "playbook"], "claude_model": "c-1", "openai_model": "o-1", "deadline_s": 2,
                      "max_concurrency": 4, "daily_call_budget": 120, "prices": {}, **kw}
    return cfg


class Broker:
    price_bound = False

    async def quote(self, sym):
        return None

    async def equity(self):
        return 100000.0

    async def open(self, p, qty, ref):
        p.add_leg(Leg(qty, ref, p.opened_ts, "initial"))
        return ref


def entry_rig(tmp_path, stubs=None, with_agent=True, cfg=None, book_key="live", name="j"):
    cfg = cfg or dyn_cfg()
    st = LiveState(mode="paper"); st.now = TS; st.equity = 100000.0
    st.last_prices["XAUUSD"] = 2650.0
    st.bias["XAUUSD"] = {"suspended": False, "score": 1.0, "in_doubt": False, "label": "BULLISH", "d": 1, "h4": 1, "h1": 1,
                         "updated": "2026-10-26T09:00-04:00", "h1_minutes": 60, "h1_complete": True, "pdh": 2660.0, "pdl": 2630.0}
    store = BarStore(TZ, max_days=5)
    fill_store(store)
    j = Journal(str(tmp_path / f"{name}.sqlite"))
    ctx = Ctx(cfg, Bus(), st, store, Broker(), j, None, None)
    ctx.book_key = book_key
    ra = RiskAgent(ctx); ra.start()
    ag = None
    if with_agent:
        ag = DynamicReviewAgent(ctx); ag.start()
        if stubs is not None:
            ag.providers = {s.name: s for s in stubs}
    return ctx, ra, ag


async def enter(ra, ctx, price=2650.0, stop=2648.0):
    sig = Signal("XAUUSD", "macd_cross:5m@pb-x", 1, price, stop, TS)
    rec = {"ts": TS.isoformat(), "symbol": "XAUUSD", "strategy": sig.strategy, "side": "LONG", "entry": price, "stop": stop}
    await ra.on_request({"signal": sig, "grade": {"quality": 0.8, "confidence": 0.8, "source": "t"}, "record": rec})
    return list(ctx.state.positions.values())


def reviews(j, rnd=1):
    return [dict(r) for r in j.db.execute("SELECT * FROM dyn_reviews WHERE round=? ORDER BY provider", (rnd,))]


def test_the_hook_returns_at_once_records_in_the_background_and_the_trade_is_taken_whatever_they_say(tmp_path):
    slow = [Stub("openai", "CANCEL", delay=0.4, marker="OAI"), Stub("claude", "CANCEL", delay=0.4, marker="CLD")]
    ctx, ra, ag = entry_rig(tmp_path, slow, name="on")
    base_ctx, base_ra, _ = entry_rig(tmp_path, with_agent=False, name="off")

    async def go():
        t0 = time.monotonic()
        (pos,) = await enter(ra, ctx)
        took = time.monotonic() - t0
        assert took < 0.3                                      # the reviewers take 0.4 s: the entry did not wait
        assert pos.status == "open" and ctx.state.positions[pos.id] is pos
        assert reviews(ctx.journal) == []                      # nothing recorded yet, calls still in flight
        c = ctx.journal.db.execute("SELECT * FROM dyn_candidates").fetchall()
        assert len(c) == 1 and c[0]["candidate_id"] == pos.id and c[0]["status"] == "pending"
        await ag.drain()
        return pos
    pos = run(go())
    rows = reviews(ctx.journal)
    assert [r["provider"] for r in rows] == ["claude", "openai"] and {r["action"] for r in rows} == {"CANCEL"}
    assert all(r["candidate_id"] == pos.id and r["prompt_version"] == "dyn-v1" and r["called"] == 1 for r in rows)
    assert all(r["latency_ms"] >= 400 and r["tokens_in"] == 1000 for r in rows)
    assert ctx.journal.db.execute("SELECT status FROM dyn_candidates").fetchone()[0] == "reviewed"
    # the same entry with no reviewer attached: identical position, stop, size and entry event
    (b,) = run(enter(base_ra, base_ctx))
    assert (b.entry, b.stop, b.initial_stop, b.initial_qty, b.risk_mult, b.rr) == (pos.entry, pos.stop, pos.initial_stop, pos.initial_qty, pos.risk_mult, pos.rr)
    ev = lambda p: [{k: v for k, v in e.items() if k != "ts"} for e in p.events if e["kind"] == "entry"]
    assert ev(b) == ev(pos)


def test_sealed_reviews_get_the_identical_packet_and_never_the_others_answer(tmp_path):
    o, c = Stub("openai", "ENTER", marker="OPENAI-ANSWER"), Stub("claude", "CANCEL", marker="CLAUDE-ANSWER")
    ctx, ra, ag = entry_rig(tmp_path, [o, c])

    async def go():
        await enter(ra, ctx)
        await ag.drain()
    run(go())
    assert len(o.seen) == len(c.seen) == 1 and o.seen[0] == c.seen[0]
    assert "ANSWER" not in o.seen[0] and "ANSWER" not in c.seen[0]
    pk = json.loads(o.seen[0])
    assert pk["candidate"]["symbol"] == "XAUUSD" and pk["order"]["entry"] == 2650.0
    h = ctx.journal.db.execute("SELECT packet_hash, packet FROM dyn_candidates").fetchone()
    assert json.loads(h["packet"])["packet_hash"] == h["packet_hash"] == pk["packet_hash"]
    assert {r["packet_hash"] for r in reviews(ctx.journal)} == {h["packet_hash"]}
    assert {r["action"] for r in reviews(ctx.journal)} == {"ENTER", "CANCEL"}


def test_the_hook_can_never_raise_into_the_entry(tmp_path, monkeypatch):
    ctx, ra, ag = entry_rig(tmp_path, [Stub("openai"), Stub("claude")])
    import fxagents.agents.dynamic_review as dr

    def broken(**kw):
        raise RuntimeError("packet bug")
    monkeypatch.setattr(dr, "build_packet", broken)
    (pos,) = run(enter(ra, ctx))                                # the packet builder fails: the entry is still taken
    assert pos.status == "open" and reviews(ctx.journal) == []
    monkeypatch.undo()

    class Exploding:
        def submit_entry(self, **kw):
            raise ValueError("boom")
    ctx2, ra2, _ = entry_rig(tmp_path, with_agent=False, name="k2")
    ctx2.dyn_review = Exploding()
    (p2,) = run(enter(ra2, ctx2))
    assert p2.status == "open"


def test_budget_stops_the_calls_and_records_not_reviewed(tmp_path):
    o, c = Stub("openai", marker="o"), Stub("claude", marker="c")
    ctx, ra, ag = entry_rig(tmp_path, [o, c], cfg=dyn_cfg(daily_call_budget=2))

    async def go():
        for i in range(3):
            pk, _ = mk_packet(candidate_id=f"cand{i}")
            ag.submit(pk)
        await ag.drain()
    run(go())
    assert len(o.seen) == 2 and len(c.seen) == 2                # two calls per provider, then the budget is spent
    rows = [dict(r) for r in ctx.journal.db.execute("SELECT * FROM dyn_reviews WHERE candidate_id='cand2' ORDER BY provider")]
    assert [r["action"] for r in rows] == ["NOT_REVIEWED", "NOT_REVIEWED"] and all(r["called"] == 0 for r in rows)
    assert all(r["error"].startswith("not_reviewed: budget") for r in rows)
    assert DS.calls_on(ctx.journal, "openai", rows[0]["day"]) == 2
    # a restart does not reset the day's count: it is read back from the journal
    ag2 = DynamicReviewAgent(ctx); ag2.start()
    ag2.providers = {"openai": Stub("openai")}
    assert ag2._take_budget("openai", rows[0]["day"]) is False


def test_late_replies_and_missing_keys_abstain(tmp_path):
    slow, nokey = Stub("openai", delay=5.0), Stub("claude", key=False)
    ctx, ra, ag = entry_rig(tmp_path, [slow, nokey], cfg=dyn_cfg(deadline_s=0.1))
    t0 = time.monotonic()

    async def go():
        ag.submit(mk_packet()[0])
        await ag.drain()
    run(go())
    assert time.monotonic() - t0 < 2
    by = {r["provider"]: r for r in reviews(ctx.journal)}
    assert by["openai"]["action"] == "ABSTAIN" and by["openai"]["error"].startswith("timeout") and by["openai"]["called"] == 1
    assert by["claude"]["action"] == "ABSTAIN" and "environment" in by["claude"]["error"] and by["claude"]["called"] == 0


def test_concurrency_is_bounded(tmp_path):
    class Counting(Stub):
        live = peak = 0

        async def review(self, packet_json, candidate_id):
            Counting.live += 1; Counting.peak = max(Counting.peak, Counting.live)
            await asyncio.sleep(0.05)
            Counting.live -= 1
            return PR.result("ENTER", None, evidence="e", conflicting="c")
    ctx, ra, ag = entry_rig(tmp_path, [Counting("openai"), Counting("claude")], cfg=dyn_cfg(max_concurrency=2))

    async def go():
        for i in range(4):
            ag.submit(mk_packet(candidate_id=f"c{i}")[0])
        await ag.drain()
    run(go())
    assert Counting.peak == 2 and len(reviews(ctx.journal)) == 8


def test_switched_off_where_it_should_be(tmp_path):
    # a book that is not listed, sim mode, a replay and a disabled config all leave the hook unset
    for kw, tweak in (({"book_key": "setup_first"}, None), ({}, lambda c: c.update(mode="sim")),
                      ({}, lambda c: c.update(replay=True)), ({}, lambda c: c["dynamic"].update(enabled=False))):
        cfg = dyn_cfg()
        if tweak:
            tweak(cfg)
        ctx, ra, ag = entry_rig(tmp_path, cfg=cfg, name="off" + str(len(kw)), **kw)
        assert ag.on is False and getattr(ctx, "dyn_review", None) is None
        (pos,) = run(enter(ra, ctx))
        assert pos.status == "open"
        assert ctx.journal.db.execute("SELECT name FROM sqlite_master WHERE name='dyn_reviews'").fetchone() is None
    # the practice account has no book_key when its agents start: it counts as "live"
    ctx, ra, ag = entry_rig(tmp_path, name="live")
    del ctx.book_key
    ag2 = DynamicReviewAgent(ctx); ag2.start()
    assert ag2.on and ag2.book == "live"


def test_each_book_keeps_its_own_journal_and_state(tmp_path):
    a, b = Stub("claude", marker="a"), Stub("claude", marker="b")
    ca, ra, aa = entry_rig(tmp_path, [a], book_key="live", name="a")
    cb, rb, ab = entry_rig(tmp_path, [b], book_key="playbook", name="b")

    async def go():
        await enter(ra, ca); await enter(rb, cb)
        await aa.drain(); await ab.drain()
    run(go())
    assert len(a.seen) == len(b.seen) == 1
    for c, book in ((ca, "live"), (cb, "playbook")):
        (cand,) = c.journal.db.execute("SELECT book FROM dyn_candidates").fetchall()
        assert cand[0] == book and len(reviews(c.journal)) == 1


def test_config_has_the_documented_keys():
    d = CFG["dynamic"]
    assert d["enabled"] is True and d["books"] == ["live", "playbook"] and d["claude_model"] == "claude-sonnet-5-5"
    assert d["openai_model"] == "" and d["deadline_s"] == 25 and d["max_concurrency"] == 4
    assert d["daily_call_budget"] == 120 and d["prices"]["claude-sonnet-5-5"] == {"in_per_mtok": 2.0, "out_per_mtok": 10.0}
    assert list(PR.build_providers(d)) == ["claude"]            # empty openai_model: that arm is off
    assert list(PR.build_providers({**d, "openai_model": "x"})) == ["claude", "openai"]


# ── 4. the scorecard ───────────────────────────────────────────────────────────────────────────────────────────
SCFG = {"instruments": {"NDQ": {"multiplier": 1}, "US30": {"multiplier": 1}}}
#            id   sym    R     openai action   (latency s, cost)         claude action
TRADES = [("t1", "NDQ", 2.0, ("ENTER", 1, 0.5), ("ENTER", 1, 0.2)),
          ("t2", "NDQ", -1.0, ("CANCEL", 2, 0.5), ("ENTER", 2, 0.2)),
          ("t3", "NDQ", 1.0, ("WAIT", 3, 0.5), ("CANCEL", 3, 0.2)),
          ("t4", "NDQ", -1.0, ("ENTER", 40, 0.5), ("CANCEL", 4, 0.2)),
          ("t5", "US30", 0.5, ("ABSTAIN", 25, None), ("ENTER", 5, 0.2)),
          ("t6", "US30", -2.0, ("NOT_REVIEWED", None, None), ("ENTER", 6, 0.2))]


def scored_journal(tmp_path):
    j = Journal(str(tmp_path / "score.sqlite"))
    DS.ensure_schema(j)
    for i, (tid, sym, r, o, c) in enumerate(TRADES):
        opened = pd.Timestamp("2026-10-19 10:00", tz=TZ) + pd.Timedelta(days=i)
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (tid, sym, "LONG", "x:5m@y", "closed", opened.isoformat(),
                                                           (opened + pd.Timedelta(hours=1)).isoformat(), r, r * 100, 100, 100.0, 99.0, "[]"))
        pk = {"candidate": {"id": tid, "book": "live", "symbol": sym, "side": "LONG", "strategy": "x:5m@y",
                            "entry_time_utc": opened.tz_convert("UTC").strftime("%Y-%m-%d %H:%M")}, "packet_hash": "h" + tid}
        DS.add_candidate(j, pk, "reviewed", "dyn-v1")
        for prov, (act, lat, cost) in (("openai", o), ("claude", c)):
            called = act not in ("NOT_REVIEWED",)
            DS.add_review(j, tid, prov, "m", "dyn-v1", "h" + tid,
                          PR.result(act, "x" if act in ("ABSTAIN", "NOT_REVIEWED") else None, latency_ms=None if lat is None else lat * 1000,
                                    cost_usd=cost, tokens_in=10 if called else None, tokens_out=5 if called else None),
                          called, "2026-10-19", "2026-10-19T10:00")
    # an open trade and a review of an older prompt version must not be scored
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,qty_initial,entry,initial_stop,events) VALUES('open1','NDQ','LONG','x','open','2026-10-26T10:00',100,100,99,'[]')")
    DS.add_candidate(j, {"candidate": {"id": "open1", "book": "live", "symbol": "NDQ", "side": "LONG", "strategy": "x", "entry_time_utc": "2026-10-26 14:00"}, "packet_hash": "ho"}, "pending", "dyn-v1")
    j.db.commit()
    return j


def test_scorecard_arms_give_the_exact_expected_totals(tmp_path):
    j = scored_journal(tmp_path)
    sc = S.scorecard(j, SCFG, "live")
    assert sc["candidates"] == 6
    A, B, C, D = (sc["arms"][k] for k in "ABCD")
    assert (A["entered"], A["skipped"], A["total_r"], A["r_per_candidate"]) == (6, 0, -0.5, round(-0.5 / 6, 4))
    # B (OpenAI): ENTER on t1, t4 -> 2 - 1; CANCEL t2, WAIT t3 are skipped by review, ABSTAIN t5, not reviewed t6
    assert (B["entered"], B["skipped"], B["total_r"]) == (2, 4, 1.0)
    assert (B["skipped_by_review"], B["abstained"], B["not_reviewed"]) == (2, 1, 1)
    assert (B["avoided_losers"], B["avoided_r"], B["missed_winners"], B["missed_r"]) == (2, 3.0, 2, 1.5)
    # cost: 4 priced calls of $0.50 on a $100 risk each; the ABSTAIN call (t5) has tokens but no price
    assert B["cost"]["usd"] == 2.0 and B["cost"]["r"] == pytest.approx(0.02) and B["cost"]["unpriced_calls"] == 1
    assert B["cost"]["note"] == "1 call(s) without a price" and B["net_r"] == pytest.approx(0.98)
    # C (Claude): ENTER on t1, t2, t5, t6 -> 2 - 1 + 0.5 - 2; CANCEL t3, t4
    assert (C["entered"], C["skipped"], C["total_r"], C["skipped_by_review"]) == (4, 2, -0.5, 2)
    assert (C["avoided_losers"], C["avoided_r"], C["missed_winners"], C["missed_r"]) == (1, 1.0, 1, 1.0)
    assert C["cost"]["usd"] == pytest.approx(1.2) and C["cost"]["r"] == pytest.approx(0.012) and C["cost"]["note"] is None
    # D: only t1 has two ENTERs; t5 / t6 are skipped because OpenAI abstained / was not reviewed
    assert (D["entered"], D["skipped"], D["total_r"]) == (1, 5, 2.0)
    assert (D["skipped_by_review"], D["abstained"], D["not_reviewed"]) == (3, 1, 1)
    assert (D["avoided_losers"], D["avoided_r"], D["missed_winners"], D["missed_r"]) == (3, 4.0, 2, 1.5)
    assert D["cost"]["usd"] == pytest.approx(3.2) and D["net_r"] == pytest.approx(2.0 - 0.032)
    # latency: OpenAI's called reviews took 1, 2, 3, 40 and 25 s; only t1-t3 were answered within 30 s
    assert B["latency_ms"] == {"p50": 3000.0, "p95": 37000.0, "max": 40000.0, "n": 5}
    assert B["share_within_30s"] == 0.5 and C["share_within_30s"] == 1.0 and D["share_within_30s"] == pytest.approx(3 / 6)
    # paired difference to A, per candidate: B skipped +1, -1, -0.5 and +2 worth of R -> +1.5 in total; below 30 reviewed: no range
    assert B["vs_a"]["gross_per_candidate"] == round(1.5 / 6, 4) and B["vs_a"]["net_ci"] is None and "30" in B["vs_a"]["ci_note"]
    assert B["reviewed"] == 4 and B["rule"]["interim"] is True and B["rule"]["worth_live_trial"] is None
    # per symbol
    ndq, us = sc["by_symbol"]["NDQ"]["arms"], sc["by_symbol"]["US30"]["arms"]
    assert ndq["A"]["total_r"] == 1.0 and us["A"]["total_r"] == -1.5 and ndq["B"]["total_r"] == 1.0 and us["B"]["total_r"] == 0.0
    assert ndq["D"]["total_r"] == 2.0 and us["D"]["entered"] == 0
    # everything the reviewers did, including the trade that is still open
    assert sc["spend"]["openai"]["reviews"] == 6 and sc["spend"]["openai"]["calls"] == 5 and sc["spend"]["claude"]["ENTER"] == 4


def test_an_arm_with_no_reviews_is_off(tmp_path):
    j = scored_journal(tmp_path)
    j.db.execute("DELETE FROM dyn_reviews WHERE provider='openai'"); j.db.commit()
    sc = S.scorecard(j, SCFG, "live")
    assert sc["arms"]["B"]["on"] is False and sc["arms"]["D"]["on"] is False and sc["arms"]["C"]["on"] is True
    assert S.scorecard(Journal(str(tmp_path / "empty.sqlite")), SCFG, "live")["candidates"] == 0
    md = S.report_md({"All books": sc}, "dyn-v1", ["live"], [])
    assert "off: no reviews from this provider" in md and "Decision rule" in md


def test_prompt_versions_are_not_pooled(tmp_path):
    j = scored_journal(tmp_path)
    assert S.scorecard(j, SCFG, "live", "dyn-v2")["candidates"] == 0


def test_bootstrap_range_needs_30_reviewed_trades_and_is_reproducible():
    days = pd.bdate_range("2026-09-01", periods=60)
    rows = []
    for i, d in enumerate(days):
        r = 1.0 if i % 2 else -1.0
        act = "ENTER" if r > 0 else "CANCEL"                     # a reviewer that cancels every loser
        rows.append({"id": f"x{i}", "book": "live", "symbol": "NDQ", "strategy": "s", "day": str(d.date()), "r": r, "risk_usd": 100.0,
                     "reviews": {"claude": {"action": act, "latency_ms": 2000, "cost_usd": 0.1, "tokens_in": 1, "tokens_out": 1, "called": 1, "error": None}}})
    m = S.arm_metrics(rows, "C")
    assert m["reviewed"] == 60 and m["avoided_losers"] == 30 and m["missed_winners"] == 0 and m["total_r"] == 30.0
    lo, hi = m["vs_a"]["net_ci"]
    assert lo > 0 and hi >= lo and m["vs_a"]["net_per_candidate"] == pytest.approx(0.5 - 0.001)
    assert S.arm_metrics(rows, "C")["vs_a"]["net_ci"] == [lo, hi]
    assert m["rule"]["interim"] is True and m["rule"]["net_ci_above_0"] is True and m["rule"]["share_ok"] is True
    assert S.arm_metrics(rows[:20], "C")["vs_a"]["net_ci"] is None
    # a reviewer that cancels at random gains nothing: its range straddles 0
    rng = np.random.default_rng(5)
    for r in rows:
        r["reviews"]["claude"]["action"] = "ENTER" if rng.random() < 0.5 else "CANCEL"
    lo2, hi2 = S.arm_metrics(rows, "C")["vs_a"]["net_ci"]
    assert lo2 < 0 < hi2


def test_the_report_cli_writes_report_and_summary(tmp_path, monkeypatch):
    j = scored_journal(tmp_path)
    j.db.close()
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "score.sqlite")
    cfg["broker"] = "ibkr"
    import fxagents.config as fc
    monkeypatch.setattr(fc, "load_config", lambda p: cfg)
    for sym in ("NDQ", "US30"):
        cfg["instruments"][sym]["multiplier"] = 1
    out = tmp_path / "out"
    assert S.main(["--books", "live,playbook", "--out", str(out)]) == 0
    md = (out / "report.md").read_text()
    assert "playbook: no journal at" in md and "| **B** OpenAI |" in md and "1 call(s) without a price" in md.split("### By symbol")[0]
    summ = json.loads((out / "summary.json").read_text())
    assert summ["groups"]["All books"]["arms"]["B"]["total_r"] == 1.0


# ── 5. dashboard ───────────────────────────────────────────────────────────────────────────────────────────────
def test_api_story_and_ask_show_the_reviews(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.book_key = "live"
    c = TestClient(build_app(ctx))
    empty = c.get("/api/dynamic").json()
    assert empty["candidates"] == 0 and empty["recent"] == [] and empty["config"]["prompt_version"] == "dyn-v1"
    assert c.get("/api/story/recent").json()["shadow_reviews"] == []
    j = ctx.journal
    DS.ensure_schema(j)
    DS.add_candidate(j, {"candidate": {"id": "recent", "book": "live", "symbol": "XAUUSD", "side": "LONG", "strategy": "trend_breakout:15m@pb-x",
                                       "entry_time_utc": "2026-10-14 13:00"}, "packet_hash": "h"}, "reviewed", "dyn-v1")
    for prov, act in (("claude", "ENTER"), ("openai", "CANCEL")):
        DS.add_review(j, "recent", prov, "m", "dyn-v1", "h", PR.result(act, None, evidence=f"{prov} saw a retest", conflicting="bias",
                                                                       latency_ms=4200, cost_usd=0.01, tokens_in=1, tokens_out=1),
                      True, "2026-10-14", "2026-10-14T09:00:00-04:00")
    d = c.get("/api/dynamic").json()
    assert d["candidates"] == 1 and d["arms"]["A"]["total_r"] == 0.5 and d["arms"]["C"]["total_r"] == 0.5 and d["arms"]["B"]["total_r"] == 0.0
    assert d["arms"]["D"]["entered"] == 0 and len(d["recent"]) == 2 and d["recent"][0]["r_multiple"] == 0.5
    s = c.get("/api/story/recent").json()
    assert {r["provider"]: r["action"] for r in s["shadow_reviews"]} == {"claude": "ENTER", "openai": "CANCEL"}
    assert s["shadow_reviews"][0]["evidence"].endswith("saw a retest")
    facts = ask.gather(ctx, "how did the last XAUUSD trade go")["books"]["live"]["latest_trades"]
    got = [t for t in facts if t["id"] == "recent"][0]["shadow_reviews"]
    assert {x["provider"] for x in got} == {"claude", "openai"} and "shadow_reviews" in ask.SYSTEM
    html = (__import__("pathlib").Path(__file__).parents[1] / "fxagents/dashboard/static/index.html").read_text()
    assert "shadow review (not used for decisions)" in html and "api/dynamic" in html and 'id="dynBody"' in html


# ── 6. milestone 1b: one structured exchange (prompt dyn-x1) ────────────────────────────────────────────────────
def x_rig(tmp_path, o, c, **kw):
    ctx, ra, ag = entry_rig(tmp_path, [o, c], cfg=dyn_cfg(**kw))
    return ctx, ag


def drain_submit(ag, pk=None):
    async def go():
        ag.submit(pk or mk_packet()[0])
        await ag.drain()
    run(go())


def cand(j, cid="abc123"):
    return dict(j.db.execute("SELECT * FROM dyn_candidates WHERE candidate_id=?", (cid,)).fetchone())


def test_round_two_runs_only_when_both_round_one_answers_are_valid(tmp_path):
    for a1, a2, why in (("ENTER", "ABSTAIN", "round 1 not valid (openai: ABSTAIN)"), ("NOT_REVIEWED", "WAIT", "openai: NOT_REVIEWED")):
        o, c = Stub("openai", a1), Stub("claude", a2)
        if a1 == "NOT_REVIEWED":
            o.review = lambda t, i: asyncio.sleep(0, PR.result("NOT_REVIEWED", "not_reviewed: budget"))
        else:
            o.review, c.review = c.review, o.review          # openai says ENTER, claude abstains
            o.action, c.action = "ENTER", "ABSTAIN"
            async def abst(t, i):
                return PR.abstain("boom")
            c.review = abst
        ctx, ag = x_rig(tmp_path, o, c)
        drain_submit(ag)
        assert o.seen2 == [] and c.seen2 == []
        assert reviews(ctx.journal, 2) == []
        k = cand(ctx.journal)
        assert k["exchange_status"].startswith("skipped: round 1 not valid") and k["exchange_ms"] is None
        tmp_path = tmp_path / "b"; tmp_path.mkdir()
    # a valid CANCEL counts as valid: the exchange runs
    o, c = Stub("openai", "CANCEL"), Stub("claude", "ENTER")
    ctx, ag = x_rig(tmp_path / "c" if (tmp_path / "c").mkdir() is None else tmp_path, o, c)
    drain_submit(ag)
    assert len(o.seen2) == len(c.seen2) == 1 and cand(ctx.journal)["exchange_status"] == "done"
    # only one reviewer configured: no exchange, and the reason is recorded
    (tmp_path / "d").mkdir()
    ctx2, ra2, ag2 = entry_rig(tmp_path / "d", [Stub("claude", "ENTER")])
    drain_submit(ag2)
    assert cand(ctx2.journal)["exchange_status"] == "skipped: needs both reviewers (configured: claude)"
    assert reviews(ctx2.journal, 2) == []


def test_each_reviewer_gets_the_others_round_one_answer_and_the_same_packet(tmp_path):
    o, c = Stub("openai", "ENTER", marker="OAI1"), Stub("claude", "WAIT", marker="CLD1")
    o.action2, c.action2 = "WAIT", "ENTER"                       # they swap in round 2
    o.marker2 = c.marker2 = None
    ctx, ag = x_rig(tmp_path, o, c)
    drain_submit(ag)
    (po, ido, oth_o, own_o), (pc, idc, oth_c, own_c) = o.seen2[0], c.seen2[0]
    assert po == pc == o.seen[0] == c.seen[0] and ido == idc == "abc123"       # identical packet text in both rounds
    assert oth_o["action"] == "WAIT" and oth_o["decisive_evidence"] == "CLD1 evidence"       # OpenAI sees Claude's round 1
    assert oth_c["action"] == "ENTER" and oth_c["decisive_evidence"] == "OAI1 evidence"       # Claude sees OpenAI's round 1
    assert set(oth_o) == {"action", "trigger_id", "invalidation_id", "decisive_evidence", "conflicting_evidence", "missing_data"}
    blob = json.dumps([oth_o, oth_c])
    assert "round2" not in blob and "OAI1 round2" not in json.dumps(oth_c)        # nobody sees the other's round 2
    # each is also shown ITS OWN round-1 answer, separately from the other's (a fresh call has no memory of round 1)
    assert own_o["action"] == "ENTER" and own_o["decisive_evidence"] == "OAI1 evidence"
    assert own_c["action"] == "WAIT" and own_c["decisive_evidence"] == "CLD1 evidence"
    assert "OAI1" not in json.dumps(oth_o) and "CLD1" not in json.dumps(oth_c)
    r2 = {r["provider"]: r for r in reviews(ctx.journal, 2)}
    assert {k: v["action"] for k, v in r2.items()} == {"openai": "WAIT", "claude": "ENTER"}
    assert all(v["prompt_version"] == "dyn-x1" and v["round"] == 2 and v["called"] == 1 and v["changed"] == 1 for v in r2.values())
    assert r2["claude"]["why_changed"] == "CLD1 why"
    assert {r["prompt_version"] for r in reviews(ctx.journal, 1)} == {"dyn-v1"}
    k = cand(ctx.journal)
    assert k["exchange_status"] == "done" and k["exchange_ms"] >= 0 and k["exchange_decision"] == "cancel"


def test_the_provider_requests_carry_the_round_two_prompt_schema_and_only_the_others_fields(monkeypatch):
    keys(monkeypatch)
    other = PR.result("WAIT", None, trigger_id="retest_of_entry", evidence="e", conflicting="c", missing=["m"], tokens_in=9, latency_ms=3)
    other["model"] = "SECRET-MODEL-NAME"
    own = PR.result("ENTER", None, evidence="MY-OWN-EVIDENCE", conflicting="mc", missing=["mm"], tokens_in=7, latency_ms=2)
    seen = {}
    ex_obj = {**GOOD, "changed": False, "why_changed": "kept: 1.2 below the Asia low"}

    def handler(kind):
        def h(req):
            seen[kind] = json.loads(req.content)
            return httpx.Response(200, json=claude_reply(ex_obj) if kind == "claude" else openai_reply(ex_obj))
        return h
    for kind in ("claude", "openai"):
        res = run(provider(kind, handler(kind)).review_exchange('{"p":1}', "abc123", other, own))
        assert res["action"] == "WAIT" and res["changed"] is False and res["why_changed"].startswith("kept")
        assert res["tokens_in"] and res["error"] is None
        body = seen[kind]
        text = json.dumps(body)
        assert "ROUND 2" in text and "dyn-x1" in text and "SECRET-MODEL-NAME" not in text and "tokens_in" not in text
        user = body["messages"][0]["content"] if kind == "claude" else body["messages"][1]["content"]
        assert user.startswith('PACKET:\n{"p":1}') and "retest_of_entry" in user
        mine, theirs = user.index("YOUR ROUND-1 ANSWER:"), user.index("THE OTHER REVIEWER'S ROUND-1 ANSWER")
        assert mine < theirs and "MY-OWN-EVIDENCE" in user[mine:theirs] and "MY-OWN-EVIDENCE" not in user[theirs:]
        assert '"decisive_evidence": "e"' in user[theirs:] and '"missing_data": ["mm"]' in user[mine:theirs]
        assert "tokens_in" not in user and "latency" not in user
        schema = body["output_config"]["format"]["schema"] if kind == "claude" else body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["changed"] == {"type": "boolean"} and "why_changed" in schema["required"] and "changed" in schema["required"]
        assert "maxLength" not in json.dumps(schema)                      # strict mode: every field required, no length keywords
        assert set(schema["required"]) == set(schema["properties"])
        if kind == "claude":
            assert_claude_schema(schema)
    # round 1 keeps the dyn-v1 schema without the new fields
    assert "changed" not in PR.review_schema()["properties"] and PR.EXCHANGE_PROMPT_VERSION == "dyn-x1"
    # the same validation -> ABSTAIN-with-reason behaviour, and over-long why_changed is cut locally
    for bad, why in (({**GOOD, "why_changed": "x"}, "changed"), ({**GOOD, "changed": "yes", "why_changed": "x"}, "changed"),
                     ({**GOOD, "changed": True}, "why_changed"), ({**ex_obj, "action": "BUY"}, "action")):
        r = run(provider("claude", lambda req, b=bad: httpx.Response(200, json=claude_reply(b))).review_exchange("{}", "abc123", other))
        assert r["action"] == "ABSTAIN" and why in r["error"]
    long = run(provider("openai", lambda req: httpx.Response(200, json=openai_reply({**ex_obj, "why_changed": "w" * 900}))).review_exchange("{}", "abc123", other))
    assert len(long["why_changed"]) == 300
    wrong = run(provider("claude", lambda req: httpx.Response(200, json=claude_reply({**ex_obj, "candidate_id": "zzz"}))).review_exchange("{}", "abc123", other))
    assert wrong["action"] == "ABSTAIN" and "candidate_id" in wrong["error"]


def test_round_two_prompt_keeps_the_rules_and_adds_the_exchange_instructions():
    sp, xp = PR.SYSTEM_PROMPT, PR.EXCHANGE_SYSTEM_PROMPT
    assert "dyn-x1" in xp and "dyn-v1" not in xp and "Use ONLY the packet" in xp and "no authority over orders" in xp
    assert "differs from your round-1 answer shown below" in xp
    for phrase in ("other independent reviewer", "keep or change", "do not defer", "do not hold your", "why_changed", "packet numbers"):
        assert phrase in xp.replace("\n", " ").replace("  ", " ") or phrase.lower() in xp.lower(), phrase


def test_the_exchange_decision_rule_table():
    mk = lambda a, t=None: PR.result(a, None, trigger_id=t)
    table = [(("ENTER", None), ("ENTER", None), "enter"),
             (("WAIT", "retest_of_entry"), ("WAIT", "retest_of_entry"), "wait"),
             (("WAIT", "retest_of_entry"), ("WAIT", "m15_close_in_direction"), "cancel"),
             (("WAIT", None), ("WAIT", None), "cancel"),
             (("ENTER", None), ("CANCEL", None), "cancel"), (("CANCEL", None), ("CANCEL", None), "cancel"),
             (("ENTER", None), ("WAIT", "retest_of_entry"), "cancel"),
             (("ENTER", None), ("ABSTAIN", None), "cancel"), (("ABSTAIN", None), ("ABSTAIN", None), "cancel"),
             (("ENTER", None), ("NOT_REVIEWED", None), "cancel")]
    for a, b, want in table:
        assert PR.exchange_decision(mk(*a), mk(*b)) == want, (a, b)
    assert PR.exchange_decision(None, mk("ENTER")) == "cancel"


def test_the_stored_decision_follows_the_rule(tmp_path):
    for i, (a2, b2, t, want) in enumerate((("ENTER", "ENTER", None, "enter"), ("WAIT", "WAIT", "retest_of_entry", "wait"),
                                           ("WAIT", "WAIT", None, "cancel"), ("ENTER", "CANCEL", None, "cancel"))):
        o, c = Stub("openai", "ENTER"), Stub("claude", "ENTER")
        o.action2, c.action2 = a2, b2
        o.trigger2 = c.trigger2 = t
        (tmp_path / str(i)).mkdir()
        ctx, ag = x_rig(tmp_path / str(i), o, c)
        drain_submit(ag)
        assert cand(ctx.journal)["exchange_decision"] == want, (a2, b2)


def test_exchange_deadline_makes_a_late_round_two_an_abstain(tmp_path):
    o, c = Stub("openai", "ENTER"), Stub("claude", "ENTER", )
    o.delay2 = 5.0                                                  # OpenAI's round 2 is far too slow
    ctx, ag = x_rig(tmp_path, o, c, exchange_deadline_s=0.5, deadline_s=2)
    t0 = time.monotonic()
    drain_submit(ag)
    assert time.monotonic() - t0 < 3
    r2 = {r["provider"]: r for r in reviews(ctx.journal, 2)}
    assert r2["openai"]["action"] == "ABSTAIN" and r2["openai"]["error"].startswith("exchange deadline") and r2["openai"]["called"] == 1
    assert r2["claude"]["action"] == "ENTER"                       # the other reply was in time and is kept
    k = cand(ctx.journal)
    assert k["exchange_status"] == "done" and k["exchange_decision"] == "cancel" and 400 <= k["exchange_ms"] < 1500
    # round 1 used the whole window: round 2 is not even called and does not use the budget
    o2, c2 = Stub("openai", "ENTER", delay=0.4), Stub("claude", "ENTER", delay=0.4)
    (tmp_path / "w").mkdir()
    ctx2, ag2 = x_rig(tmp_path / "w", o2, c2, exchange_deadline_s=0.2, deadline_s=2)
    drain_submit(ag2)
    assert o2.seen2 == [] and c2.seen2 == []
    rows = reviews(ctx2.journal, 2)
    assert len(rows) == 2 and all(r["action"] == "ABSTAIN" and r["error"].startswith("exchange deadline") and r["called"] == 0 for r in rows)
    assert DS.calls_on(ctx2.journal, "openai", rows[0]["day"]) == 1


def test_round_two_calls_count_against_the_same_daily_budget(tmp_path):
    o, c = Stub("openai", "ENTER"), Stub("claude", "ENTER")
    ctx, ag = x_rig(tmp_path, o, c, daily_call_budget=3)
    drain_submit(ag)                                               # 1 + 1 calls each: within the budget of 3
    day = reviews(ctx.journal)[0]["day"]
    assert DS.calls_on(ctx.journal, "openai", day) == 2 and len(o.seen2) == 1
    drain_submit(ag, mk_packet(candidate_id="second")[0])         # round 1 takes the 3rd call, round 2 finds none left
    assert len(o.seen) == 2 and len(o.seen2) == 1 and len(c.seen2) == 1
    r2 = [dict(r) for r in ctx.journal.db.execute("SELECT * FROM dyn_reviews WHERE candidate_id='second' AND round=2")]
    assert {r["action"] for r in r2} == {"NOT_REVIEWED"} and all(r["called"] == 0 and r["error"].startswith("not_reviewed: budget") for r in r2)
    assert DS.calls_on(ctx.journal, "openai", day) == 3
    assert cand(ctx.journal, "second")["exchange_decision"] == "cancel"


def test_entry_is_taken_and_unchanged_with_a_slow_exchange(tmp_path):
    slow = [Stub("openai", "CANCEL", delay=0.2, marker="O"), Stub("claude", "CANCEL", delay=0.2, marker="C")]
    for s_ in slow:
        s_.delay2 = 0.6
    ctx, ra, ag = entry_rig(tmp_path, slow, name="slowx")
    base_ctx, base_ra, _ = entry_rig(tmp_path, with_agent=False, name="basex")

    async def go():
        t0 = time.monotonic()
        (pos,) = await enter(ra, ctx)
        assert time.monotonic() - t0 < 0.15 and pos.status == "open"
        await asyncio.sleep(0.3)                                   # still between round 1 and round 2
        assert pos.status == "open" and ctx.state.positions[pos.id] is pos
        await ag.drain()
        return pos
    pos = run(go())
    (b,) = run(enter(base_ra, base_ctx))
    assert (b.entry, b.stop, b.initial_stop, b.initial_qty, b.risk_mult, b.rr) == (pos.entry, pos.stop, pos.initial_stop, pos.initial_qty, pos.risk_mult, pos.rr)
    k = dict(ctx.journal.db.execute("SELECT * FROM dyn_candidates").fetchone())
    assert k["exchange_status"] == "done" and k["exchange_ms"] >= 750 and k["status"] == "reviewed"
    ev = lambda p: [{k_: v for k_, v in e.items() if k_ != "ts"} for e in p.events if e["kind"] == "entry"]
    assert ev(b) == ev(pos)


def test_old_milestone_one_tables_are_migrated_and_old_rows_are_round_one(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.sqlite")
    j = Journal(path)
    j.db.executescript("""
CREATE TABLE dyn_candidates(candidate_id TEXT PRIMARY KEY, book TEXT, symbol TEXT, side TEXT, strategy TEXT, ts TEXT, packet_hash TEXT,
  packet TEXT, status TEXT, prompt_version TEXT);
CREATE TABLE dyn_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT, provider TEXT, model TEXT, prompt_version TEXT,
  packet_hash TEXT, action TEXT, trigger_id TEXT, invalidation_id TEXT, evidence TEXT, conflicting TEXT, missing TEXT,
  latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, error TEXT, called INTEGER, day TEXT,
  response TEXT, ts TEXT, UNIQUE(candidate_id, provider, prompt_version));""")
    j.db.execute("INSERT INTO dyn_candidates(candidate_id,symbol,ts,prompt_version,status) VALUES('t1','NDQ','2026-10-19 14:00','dyn-v1','reviewed')")
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                 "VALUES('t1','NDQ','LONG','x','closed','2026-10-19T10:00','2026-10-19T11:00',2.0,200,100,100,99,'[]')")
    j.db.execute("INSERT INTO dyn_reviews(candidate_id,provider,model,prompt_version,action,called,day,cost_usd,latency_ms) VALUES('t1','openai','m','dyn-v1','ENTER',1,'2026-10-19',0.5,1000)")
    j.db.execute("INSERT INTO dyn_reviews(candidate_id,provider,model,prompt_version,action,called,day,cost_usd,latency_ms) VALUES('t1','claude','m','dyn-v1','ENTER',1,'2026-10-19',0.2,1000)")
    j.db.commit()
    # a read-only report on the old file works before any migration
    ro = S.ReadOnly(path)
    sc = S.scorecard(ro, SCFG, "live")
    assert sc["candidates"] == 1 and sc["arms"]["D"]["total_r"] == 2.0
    ex = sc["exchange"]
    assert ex["exchanged"] == 0 and ex["not_exchanged"] == 1 and ex["arms"]["E3"]["on"] is False
    assert "milestone-1 row" in list(ex["not_exchanged_reasons"])[0]
    assert S.report_md({"All books": sc}, "dyn-v1", ["live"], [])
    assert DS.reviews_for(ro, "t1")[0]["round"] == 1 and S.recent_reviews(ro)[0]["round"] == 1
    # the bot's ensure_schema adds the columns; old rows become round 1; round 2 rows can then be written beside them
    DS.ensure_schema(j)
    assert {r["round"] for r in j.db.execute("SELECT round FROM dyn_reviews")} == {1}
    DS.ensure_schema(j)                                            # idempotent
    DS.add_review(j, "t1", "openai", "m", "dyn-x1", "h", PR.result("WAIT", None, changed=True, why_changed="y"), True, "2026-10-19", "t", 2)
    got = [r for r in DS.reviews_for(j, "t1") if r["round"] == 2][0]
    assert got["changed"] == 1 and got["why_changed"] == "y"
    assert S.scorecard(j, SCFG, "live")["arms"]["D"]["total_r"] == 2.0       # round 2 rows never leak into arms A-D
    # a fresh table's unique key includes the round
    j2 = Journal(str(tmp_path / "new.sqlite")); DS.ensure_schema(j2)
    assert "round" in j2.db.execute("SELECT sql FROM sqlite_master WHERE name='dyn_reviews'").fetchone()[0].split("UNIQUE")[1]


# exchange scorecard on a hand-made set. Round 1 / round 2 (openai, claude), R, exchange seconds, status.
#   id  sym   R     openai r1 / r2           claude r1 / r2              exchange
XT = [("x1", "NDQ", 2.0, ("ENTER", "ENTER", 0), ("ENTER", "ENTER", 0), (20, "done")),            # both ENTER: E3 enters
      ("x2", "NDQ", -1.0, ("ENTER", "CANCEL", 1), ("CANCEL", "CANCEL", 0), (31, "done")),        # openai changed away from ENTER
      ("x3", "NDQ", 1.5, ("CANCEL", "ENTER", 1), ("ENTER", "ENTER", 0), (44, "done")),           # openai changed toward ENTER: E3 enters
      ("x4", "US30", -2.0, ("WAIT", "WAIT", 0), ("CANCEL", "ENTER", 1), (50, "done")),           # claude changed toward ENTER, E3 cancels
      ("x5", "US30", 1.0, ("ENTER", "ABSTAIN", 0), ("ENTER", "ENTER", 0), (46, "done")),         # round-2 abstain
      ("x6", "US30", 3.0, ("ENTER", None, 0), ("ABSTAIN", None, 0), (None, "skipped: round 1 not valid (claude: ABSTAIN)"))]


def exchange_journal(tmp_path):
    j = Journal(str(tmp_path / "x.sqlite"))
    DS.ensure_schema(j)
    for i, (tid, sym, r, o, c, (xs, st)) in enumerate(XT):
        opened = pd.Timestamp("2026-10-19 10:00", tz=TZ) + pd.Timedelta(days=i)
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (tid, sym, "LONG", "x:5m@y", "closed", opened.isoformat(),
                                                           (opened + pd.Timedelta(hours=1)).isoformat(), r, r * 100, 100, 100.0, 99.0, "[]"))
        pk = {"candidate": {"id": tid, "book": "live", "symbol": sym, "side": "LONG", "strategy": "x:5m@y",
                            "entry_time_utc": opened.tz_convert("UTC").strftime("%Y-%m-%d %H:%M")}, "packet_hash": "h" + tid}
        DS.add_candidate(j, pk, "reviewed", "dyn-v1")
        DS.set_exchange(j, tid, st, None if xs is None else xs * 1000)
        for prov, (a1, a2, ch) in (("openai", o), ("claude", c)):
            DS.add_review(j, tid, prov, "m", "dyn-v1", "h" + tid, PR.result(a1, "x" if a1 == "ABSTAIN" else None, latency_ms=1000,
                                                                            cost_usd=0.5 if prov == "openai" else 0.2, tokens_in=1, tokens_out=1),
                          True, "2026-10-19", "t")
            if a2 is not None:
                DS.add_review(j, tid, prov, "m", "dyn-x1", "h" + tid, PR.result(a2, "x" if a2 == "ABSTAIN" else None, latency_ms=2000,
                                                                                cost_usd=1.0 if prov == "openai" else 0.4, tokens_in=1, tokens_out=1,
                                                                                changed=bool(ch), why_changed="w"), True, "2026-10-19", "t", 2)
    return j


def test_exchange_arms_and_the_subset_comparison_with_d_match_the_hand_totals(tmp_path):
    j = exchange_journal(tmp_path)
    sc = S.scorecard(j, SCFG, "live")
    assert sc["candidates"] == 6 and sc["arms"]["D"]["total_r"] == 3.0       # D (round 1): both ENTER on x1 and x5 (x6: claude ABSTAIN)
    ex = sc["exchange"]
    assert (ex["candidates"], ex["exchanged"], ex["not_exchanged"]) == (6, 5, 1)
    assert ex["not_exchanged_reasons"] == {"skipped: round 1 not valid (claude: ABSTAIN)": 1}
    A, D, E1, E2, E3 = (ex["arms"][k] for k in ("A", "D", "E1", "E2", "E3"))
    assert (A["candidates"], A["total_r"]) == (5, 2.0 - 1.0 + 1.5 - 2.0 + 1.0)                  # 1.5: x6 is not in the subset
    # D on the exchanged subset: both round-1 ENTER on x1 and x5
    assert (D["entered"], D["total_r"]) == (2, 3.0)
    # E1 (Claude round 2): ENTER on x1, x3, x4, x5
    assert (E1["entered"], E1["total_r"], E1["skipped"]) == (4, 2.0 + 1.5 - 2.0 + 1.0, 1) and E1["total_r"] == 2.5
    # E2 (OpenAI round 2): ENTER x1, x3; CANCEL x2, WAIT x4, ABSTAIN x5
    assert (E2["entered"], E2["total_r"], E2["abstained"], E2["skipped_by_review"]) == (2, 3.5, 1, 2)
    # E3: both ENTER after round 2 -> x1 and x3 only (x4 WAIT/ENTER cancels, x5 has an abstain)
    assert (E3["entered"], E3["total_r"], E3["skipped"], E3["abstained"], E3["skipped_by_review"]) == (2, 3.5, 3, 1, 2)
    assert (E3["avoided_losers"], E3["avoided_r"], E3["missed_winners"], E3["missed_r"]) == (2, 3.0, 1, 1.0)
    # cost = whole exchange (round 1 + round 2, both reviewers) per candidate: 0.5+0.2+1.0+0.4 = 2.1 on a $100 risk; x5's openai
    # round 2 also cost 1.0 (an ABSTAIN call is still paid for)
    assert E3["cost"]["usd"] == pytest.approx(5 * 2.1) and E3["cost"]["r"] == pytest.approx(5 * 0.021)
    assert E1["cost"]["usd"] == pytest.approx(5 * 2.1)
    assert D["cost"]["usd"] == pytest.approx(5 * 0.7) and E3["net_r"] == pytest.approx(3.5 - 0.105)
    # E3 minus D, paired, net of each arm's own cost: D skips x2..x4, enters x1, x5 -> net gross diff vs A
    #   per candidate: E3 gross vs A = -(skipped R) ; D gross = -(-1 + 1.5 - 2.0) ; E3 gross = -(-1 -2 + 1) 
    d = ex["e3_minus_d"]
    gross_e3 = -(-1.0 - 2.0 + 1.0)            # skipped x2, x4, x5 -> +2.0
    gross_d = -(-1.0 + 1.5 - 2.0)             # skipped x2, x3, x4 -> +1.5
    cost_diff = 5 * (0.021 - 0.007)
    assert d["n"] == 5 and d["net_total_r"] == pytest.approx((gross_e3 - gross_d) - cost_diff, abs=1e-3)
    assert d["net_per_candidate"] == pytest.approx(d["net_total_r"] / 5, abs=1e-3) and d["net_ci"] is None and "30" in d["ci_note"]
    # latency of the full exchange over the 5 exchanged: 20, 31, 44, 50, 46 s
    lt = ex["latency"]
    assert (lt["p50_ms"], lt["max_ms"], lt["n"]) == (44000.0, 50000.0, 5)
    assert lt["share_le_30s"] == 0.2 and lt["share_le_45s"] == 0.6 and lt["share_le_30s_all_candidates"] == round(1 / 6, 4)
    assert lt["slower_than_30s_ge_5pct"] is True
    assert E3["share_within_30s"] == round(1 / 6, 4) and E3["latency_ms"]["p50"] == 44000.0     # share over ALL candidates
    # round-2 cost: 5 exchanged x (1.0 + 0.4)
    assert ex["round2_cost"]["usd"] == pytest.approx(7.0) and ex["round2_cost"]["r"] == pytest.approx(0.07)
    assert sc["spend_r2"]["openai"]["reviews"] == 5 and sc["spend_r2"]["claude"]["calls"] == 5
    # per symbol
    nd, us = sc["by_symbol"]["NDQ"]["exchange"], sc["by_symbol"]["US30"]["exchange"]
    assert (nd["exchanged"], nd["arms"]["E3"]["total_r"], nd["arms"]["E3"]["entered"]) == (3, 3.5, 2)
    assert (us["exchanged"], us["not_exchanged"], us["arms"]["E3"]["entered"]) == (2, 1, 0)
    # arms A-D are unchanged by the exchange rows
    assert sc["arms"]["D"]["entered"] == 2 and sc["arms"]["D"]["total_r"] == 3.0
    md = S.report_md({"All books": sc}, "dyn-v1", ["live"], [])
    assert "1 not exchanged" in md or "**1 not exchanged**" in md
    assert "slower (15m+) setups" in md and "E3 minus D" in md and "that is the case here" in md


def test_mind_change_stats(tmp_path):
    j = exchange_journal(tmp_path)
    mc = S.scorecard(j, SCFG, "live")["exchange"]["mind_change"]
    o, c = mc["openai"], mc["claude"]
    # openai changed on x2 (ENTER -> CANCEL, R -1) and x3 (CANCEL -> ENTER, R +1.5)
    assert (o["exchanged"], o["changed"], o["toward_enter"], o["away_from_enter"], o["other"]) == (5, 2, 1, 1, 0)
    assert (o["r_round1"], o["r_round2"], o["r_gain"]) == (-1.0, 1.5, 2.5)
    # claude changed on x4 only (CANCEL -> ENTER, R -2): its round-2 answer lost 2R that round 1 avoided
    assert (c["exchanged"], c["changed"], c["toward_enter"], c["away_from_enter"]) == (5, 1, 1, 0)
    assert (c["r_round1"], c["r_round2"], c["r_gain"]) == (0.0, -2.0, -2.0)
    assert o["flag_vs_action_mismatch"] == 0 and c["flag_vs_action_mismatch"] == 0


def test_dashboard_story_and_ask_show_round_two(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.book_key = "live"
    c = TestClient(build_app(ctx))
    j = ctx.journal
    DS.ensure_schema(j)
    DS.add_candidate(j, {"candidate": {"id": "recent", "book": "live", "symbol": "XAUUSD", "side": "LONG", "strategy": "trend_breakout:15m@pb-x",
                                       "entry_time_utc": "2026-10-14 13:00"}, "packet_hash": "h"}, "reviewed", "dyn-v1")
    DS.set_exchange(j, "recent", "done", 21500, "cancel")
    for prov, a1, a2 in (("claude", "ENTER", "WAIT"), ("openai", "CANCEL", "CANCEL")):
        DS.add_review(j, "recent", prov, "m", "dyn-v1", "h", PR.result(a1, None, evidence=f"{prov} r1", conflicting="b", latency_ms=4200, cost_usd=0.01,
                                                                      tokens_in=1, tokens_out=1), True, "2026-10-14", "2026-10-14T09:00:00-04:00")
        DS.add_review(j, "recent", prov, "m", "dyn-x1", "h", PR.result(a2, None, evidence=f"{prov} r2", conflicting="b", latency_ms=6000, cost_usd=0.02,
                                                                      tokens_in=1, tokens_out=1, changed=a1 != a2, why_changed=f"{prov} why"),
                      True, "2026-10-14", "2026-10-14T09:00:10-04:00", 2)
    s = c.get("/api/story/recent").json()
    by = {(r["provider"], r["round"]): r for r in s["shadow_reviews"]}
    assert by[("claude", 2)]["action"] == "WAIT" and by[("claude", 2)]["changed"] == 1 and by[("claude", 2)]["why_changed"] == "claude why"
    assert by[("claude", 1)]["action"] == "ENTER" and by[("openai", 2)]["changed"] == 0
    assert s["shadow_exchange"] == {"status": "done", "ms": 21500.0, "decision": "cancel"}
    d = c.get("/api/dynamic").json()
    assert d["exchange"]["candidates"] == 1 and d["exchange"]["exchanged"] == 1 and d["exchange"]["arms"]["E3"]["entered"] == 0
    assert d["exchange"]["arms"]["E1"]["skipped_by_review"] == 1 and d["exchange"]["mind_change"]["claude"]["changed"] == 1
    assert {r["round"] for r in d["recent"]} == {1, 2}
    facts = ask.gather(ctx, "how did the last XAUUSD trade go")["books"]["live"]["latest_trades"]
    t = [t for t in facts if t["id"] == "recent"][0]
    assert {(x["provider"], x["round"]) for x in t["shadow_reviews"]} == {("claude", 1), ("claude", 2), ("openai", 1), ("openai", 2)}
    assert t["shadow_exchange"]["decision"] == "cancel" and "round 2" in ask.SYSTEM
    html = (__import__("pathlib").Path(__file__).parents[1] / "fxagents/dashboard/static/index.html").read_text()
    assert "round 2" in html and "shadow_exchange" in html and "d.exchange" in html


def test_config_has_the_exchange_deadline():
    assert CFG["dynamic"]["exchange_deadline_s"] == 45
    assert CFG["dynamic"]["exchange"] is False                     # Oct 27 2026: switched off


def test_exchange_switched_off_runs_round_one_only(tmp_path):
    o, c = Stub("openai", "ENTER"), Stub("claude", "WAIT")
    ctx, ag = x_rig(tmp_path, o, c, exchange=False)
    drain_submit(ag)
    assert len(o.seen) == 1 and len(c.seen) == 1 and o.seen2 == [] and c.seen2 == []
    assert reviews(ctx.journal, 2) == []
    assert cand(ctx.journal)["exchange_status"].startswith("skipped: exchange switched off")


def test_changed_is_computed_locally_and_the_models_report_is_kept_apart(tmp_path):
    o, c = Stub("openai", "ENTER", marker="O"), Stub("claude", "WAIT", marker="C")
    c.trigger2 = None
    o.action2 = "CANCEL"; o.changed2 = False          # really changed, reports "no"
    c.action2 = "WAIT"; c.changed2 = True             # really identical (WAIT, no trigger either round), reports "yes"
    ctx, ag = x_rig(tmp_path, o, c)
    drain_submit(ag)
    r2 = {r["provider"]: r for r in reviews(ctx.journal, 2)}
    assert (r2["openai"]["changed"], r2["openai"]["changed_reported"]) == (1, 0)
    assert (r2["claude"]["changed"], r2["claude"]["changed_reported"]) == (0, 1)
    # a changed trigger alone counts as a change
    o2, c2 = Stub("openai", "WAIT"), Stub("claude", "WAIT")
    o2.trigger2 = "retest_of_entry"; o2.changed2 = False
    (tmp_path / "t").mkdir()
    ctx2, ag2 = x_rig(tmp_path / "t", o2, c2)
    drain_submit(ag2)
    r = {x["provider"]: x for x in reviews(ctx2.journal, 2)}
    assert r["openai"]["changed"] == 1 and r["claude"]["changed"] == 0
    # round-2 ABSTAIN has no changed value
    (tmp_path / "u").mkdir()
    o3, c3 = Stub("openai", "ENTER"), Stub("claude", "ENTER", delay=0.0)
    o3.delay2 = 5.0
    ctx3, ag3 = x_rig(tmp_path / "u", o3, c3, exchange_deadline_s=0.5, deadline_s=2)
    drain_submit(ag3)
    ab = [x for x in reviews(ctx3.journal, 2) if x["provider"] == "openai"][0]
    assert ab["action"] == "ABSTAIN" and ab["changed"] is None
    # the scorecard's stats use the local value and count the misreports
    DS.set_exchange(ctx.journal, "abc123", "done", 1000, "cancel")
    ctx.journal.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                           "VALUES('abc123','NDQ','LONG','x','closed','2026-10-26T10:00','2026-10-26T11:00',1.0,100,100,100,99,'[]')")
    ctx.journal.db.commit()
    mc = S.scorecard(ctx.journal, SCFG, "live")["exchange"]["mind_change"]
    assert mc["openai"]["changed"] == 1 and mc["openai"]["away_from_enter"] == 1 and mc["claude"]["changed"] == 0
    assert mc["openai"]["flag_vs_action_mismatch"] == 1 and mc["claude"]["flag_vs_action_mismatch"] == 1
