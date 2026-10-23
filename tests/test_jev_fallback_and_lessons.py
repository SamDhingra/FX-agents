"""Oct 22 2026, from the TradingAgents review.

1. A Jev answer that can't be read (a question missing, a score with no level probabilities, a value that isn't a
   number in 0..1) is a flagged fallback, exactly like a timeout — it never passes as Jev's judgement, never opens a
   counter-bias trade or a pyramid add, and is recorded with its reason so Ask Claude can report it.
2. Each closed practice-account trade gets a short lesson, for reading only, quoting the strategy's record as it
   stood at that trade's close (nothing later)."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fxagents.agents.trading import RiskAgent, jev_gate, jev_gate_why
from fxagents.bus import Bus
from fxagents.dashboard import ask, lessons
from fxagents.dashboard.server import build_app
from fxagents.jev import JevScorer, Unreadable, read_answers
from fxagents.models import Signal
from fxagents.state import LiveState
from tests.test_core import CFG, TZ
from tests.test_dashboard_insights import make_ctx

NOW = pd.Timestamp("2026-10-14 10:00", tz=TZ)
SIG = {"strategy": "x", "side": "LONG", "symbol": "NDQ", "entry": 1, "stop": 0.9, "strategy_expectancy": 0.1,
       "strategy_win_rate": 0.5, "htf_bias": 1, "risk_atr": 1.0, "rsi": 50}
Q = {"quality": object(), "htf_aligned": object()}


def A(**kw):
    return SimpleNamespace(**kw)


def score(probs=None, conf=0.8):
    return A(type="score", probabilities=probs if probs is not None else {0: 0, 1: .1, 2: .2, 3: .5, 4: .2}, confidence=conf)


def resp(**answers):
    return A(answers=answers, model="jev-stub", usage=None)


# ── 1. reading Jev's answers ─────────────────────────────────────────────────
def test_read_answers_accepts_a_complete_reply():
    out = read_answers(resp(quality=score(), htf_aligned=A(type="noul", noul=0.9)), Q)
    assert out["quality"]["value"] == pytest.approx(0.70) and out["htf_aligned"]["confidence"] == pytest.approx(0.8)


@pytest.mark.parametrize("reply, why", [
    (resp(quality=score()), "htf_aligned missing"),
    (resp(quality=score(probs={}), htf_aligned=A(type="noul", noul=0.9)), "quality value unreadable"),
    (resp(quality=score(), htf_aligned=A(type="noul", noul=float("nan"))), "htf_aligned value unreadable"),
    (resp(quality=score(conf=None), htf_aligned=A(type="noul", noul=0.9)), "quality confidence unreadable"),
    (resp(quality=score(), htf_aligned=A(type="noul", noul=1.7)), "htf_aligned value unreadable"),
])
def test_read_answers_names_what_is_unreadable(reply, why):
    with pytest.raises(Unreadable, match=why):
        read_answers(reply, Q)


def _scorer(reply):
    cfg = copy.deepcopy(CFG); st = LiveState(); st.now = NOW
    sc = JevScorer(cfg, st, Bus())
    sc.live = True

    class Stub:
        async def system_one(self, **kw):
            return reply
    sc.client = Stub()
    return sc, st


def test_an_unreadable_reply_is_a_flagged_fallback_not_a_jev_grade():
    sc, st = _scorer(resp(quality=score()))                       # htf_aligned missing
    g = asyncio.run(sc.rate_signal(dict(SIG)))
    assert g["fallback"] is True and g["source"] == "heuristic" and g["error"].startswith("unreadable")
    assert st.decisions[0]["source"] == "heuristic" and "htf_aligned missing" in st.decisions[0]["jev_error"]
    assert sc.unreadable == 1 and sc.failures == 1
    jc = {**CFG["jev"], "signal_gate": "enforce"}
    assert not jev_gate(g, jc) and "unreadable" in jev_gate_why(g, jc)
    asyncio.run(sc.rate_signal(dict(SIG)))
    assert sum("Jev signal_rating" in a["msg"] for a in st.alerts) == 1   # one alert per kind per 30 minutes


def test_a_score_without_probabilities_is_no_longer_a_silent_zero():
    sc, _ = _scorer(resp(quality=score(probs={}), htf_aligned=A(type="noul", noul=0.9)))
    g = asyncio.run(sc.rate_signal(dict(SIG)))
    assert g["fallback"] is True and g["quality"] != 0.0


def test_a_complete_reply_still_counts_as_jev():
    sc, _ = _scorer(resp(quality=score(), htf_aligned=A(type="noul", noul=0.9)))
    g = asyncio.run(sc.rate_signal(dict(SIG)))
    assert g["fallback"] is False and g["source"] == "jev" and g["quality"] == pytest.approx(0.70)


def test_every_helper_reports_the_fallback():
    sc, _ = _scorer(resp())
    info = {"symbol": "NDQ", "side": "LONG", "strategy": "x", "bias_label": "BEARISH", "raided": "PDL", "h1_flipped": True,
            "label": "BULLISH", "score": 0.6, "h1": 1, "momentum_aligned": 1}
    for coro in (sc.reversal(info), sc.continuation(info), sc.bias_audit(info), sc.market_regime(info),
                 sc.breakout_follow(info), sc.manage_trade(info)):
        assert asyncio.run(coro)["fallback"] is True


class _J:
    def __init__(self, fallback): self.fallback = fallback
    async def reversal(self, info):
        return {"prob": 0.72, "source": "heuristic" if self.fallback else "jev", "fallback": self.fallback, "error": "x"}


def _risk(fallback):
    cfg = copy.deepcopy(CFG)
    st = LiveState(); st.now = NOW
    st.bias["NDQ"] = {"suspended": False, "score": -0.8, "in_doubt": False, "label": "BEARISH", "d": -1, "h4": -1, "h1": 1,
                      "pdl": 20000.0, "pdh": 20500.0, "asia_lo": 20100.0, "asia_hi": 20400.0, "aligned_losses": 0}
    idx = pd.date_range(NOW - pd.Timedelta(hours=2), periods=30, freq="5min")
    df = pd.DataFrame({"open": 20050.0, "high": 20060.0, "low": 19950.0, "close": 20050.0}, index=idx)
    me = SimpleNamespace(cfg=cfg, state=st, ctx=SimpleNamespace(store=SimpleNamespace(tf=lambda s, r: df), jev=_J(fallback)))
    sig = Signal("NDQ", "x", 1, 20050.0, 20000.0, NOW)
    return asyncio.run(RiskAgent.bias_gate(me, sig, {"quality": 0.8}, NOW))


def test_a_counter_bias_trade_needs_a_real_jev_answer():
    assert _risk(fallback=False)["mode"] == "reversal_exception"          # the stand-in's 0.72 used to be enough
    out = _risk(fallback=True)
    assert "reject" in out and "didn't answer" in out["reject"]


def test_the_fallback_reason_is_stored_and_reported(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.journal.add_decision({"ts": "2026-10-14T09:10:00-04:00", "kind": "signal_rating", "source": "heuristic",
                              "symbol": "XAUUSD", "inputs": {}, "outputs": {}, "jev_error": "unreadable: quality missing"})
    ctx.journal.add_decision({"ts": "2026-10-14T09:20:00-04:00", "kind": "signal_rating", "source": "heuristic",
                              "symbol": "XAUUSD", "inputs": {}, "outputs": {}, "jev_error": "TimeoutError: slow"})
    f = ask.gather(ctx, "why was the 9am gold setup skipped?")
    jf = {d["kind"]: d for d in f["jev_fallbacks"]}["signal_rating"]
    assert jf["count"] == 2 and jf["unreadable"] == 1 and jf["last_error"].startswith("TimeoutError")


# ── 2. lessons ─────────────────────────────────────────────────────────────
def test_record_at_close_ignores_later_trades(tmp_path):
    ctx = make_ctx(tmp_path)
    t0 = dict(ctx.journal.db.execute("SELECT * FROM trades WHERE id='t9'").fetchone())
    rec = lessons.record_at(ctx.journal, t0)
    assert rec["trades"] == 10                                           # t0…t9, not the 31 that closed later


def test_plain_lesson_reads_the_numbers():
    f = {"symbol": "NDQ", "side": "LONG", "r": -1.0, "mfe_r": 0.9, "mae_r": -1.0, "exit": "stop",
         "record_at_close": {"strategy": "sr_rejection", "trades": 46, "avg_r": 0.107}}
    s = lessons.plain(f)
    assert s.startswith("Long NDQ was stopped out at -1.00R") and "up 0.90R before giving it back" in s
    assert "46 trades at +0.107R" in s and "one trade doesn't change that" in s
    few = lessons.plain({**f, "mfe_r": 0.2, "record_at_close": {"strategy": "ote", "trades": 5, "avg_r": 0.1}})
    assert "too few" in few and "giving it back" not in few


def test_writer_fills_missing_lessons_once_and_they_reach_story_and_ask(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx = make_ctx(tmp_path)
    w = lessons.LessonWriter(ctx)
    n = asyncio.run(w.pass_once())
    assert n == 1                                                        # only the trade inside lesson_days (14)
    assert asyncio.run(w.pass_once()) == 0
    row = ctx.journal.db.execute("SELECT text, source, facts FROM lessons WHERE trade_id='recent'").fetchone()
    assert row["source"] == "rules" and "+0.50R" in row["text"]
    assert json.loads(row["facts"])["record_at_close"]["trades"] == 41
    st = TestClient(build_app(ctx)).get("/api/story/recent").json()
    assert st["lesson"]["text"] == row["text"]
    f = ask.gather(ctx, "how did today go?")
    t = next(x for x in f["books"]["live"]["trades_in_window"] if x["id"] == "recent")
    assert t["lesson"] == row["text"]


def test_lessons_never_reach_the_deciding_code():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "fxagents"
    users = [p.relative_to(root).as_posix() for p in root.rglob("*.py") if "lessons" in p.read_text(encoding="utf-8")
             and p.name != "lessons.py"]
    assert sorted(users) == ["dashboard/ask.py", "dashboard/insights.py", "dashboard/server.py"]


def test_any_closed_trade_gets_a_lesson_when_opened_and_paper_books_get_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    ctx = make_ctx(tmp_path)
    c = TestClient(build_app(ctx))
    st = c.get("/api/story/t3").json()                               # Sept trade: outside the 14-day back-fill
    assert st["lesson"]["source"] == "rules" and "R" in st["lesson"]["text"]
    assert c.get("/api/story/t3").json()["lesson"]["text"] == st["lesson"]["text"]      # stored once
    shadow = make_ctx(tmp_path / "sh")
    ctx.shadows = {"playbook": shadow}
    w = lessons.LessonWriter(ctx)

    async def stub(f):
        return "A Claude lesson."
    monkeypatch.setattr(w, "_claude", stub)
    assert asyncio.run(w.pass_once()) == 2                            # the recent trade in each book
    assert ctx.journal.db.execute("SELECT source FROM lessons WHERE trade_id='recent'").fetchone()["source"] == "claude"
    assert shadow.journal.db.execute("SELECT source FROM lessons WHERE trade_id='recent'").fetchone()["source"] == "rules"
    order = [t["id"] for t in w.missing(ctx.journal, limit=50)]
    assert order == sorted(order, key=lambda i: ctx.journal.db.execute("SELECT closed FROM trades WHERE id=?", (i,)).fetchone()[0], reverse=True)
