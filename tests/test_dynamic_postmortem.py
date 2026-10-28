"""Reasons report (explain) and post-mortems of losing trades (Oct 27 2026). Stubbed OANDA and providers; no network."""
import asyncio
import json

import httpx
import pandas as pd

from fxagents.dynamic import explain as X
from fxagents.dynamic import postmortem as PM
from fxagents.dynamic import providers as PR
from tests.test_core import TZ
from tests.test_dynamic_backfill import FakeOanda, bf_cfg, go
from tests.test_dynamic_review import Stub, keys


def run(c):
    return asyncio.run(c)


class PathOanda(FakeOanda):
    """Adds M1 'M' (mid) candles: the post-entry path."""

    async def req(self, method, path, *, params=None, json=None, retries=3):
        if params["granularity"] == "M1" and params["price"] == "M":
            self.requests.append(dict(params, path=path))
            a, b = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
            ix = self.mid.index[(self.mid.index >= a) & (self.mid.index < b)]
            return {"candles": [{"time": t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "complete": True, "volume": 1,
                                 "mid": {k: str(self.mid[t]) for k in "ohlc"}} for t in ix]}
        return await super().req(method, path, params=params, json=json, retries=retries)


class PMStub:
    def __init__(self, name, action="skip", fail=False):
        self.name, self.model, self.env_key = name, f"{name}-m", "X"
        self.action, self.fail, self.users = action, fail, []

    def available(self):
        return True

    async def ask_json(self, system, user, schema, name="answer", max_tokens=3000, timeout_s=None):
        self.users.append(user)
        base = {"tokens_in": 5000, "tokens_out": 600, "cost_usd": 0.016, "latency_ms": 900.0}
        if self.fail:
            return {**base, "obj": None, "error": "HTTP 500: boom"}
        cid = user.split("CANDIDATE_ID: ")[1].split("\n")[0]
        return {**base, "error": None, "obj": {
            "candidate_id": cid, "why_lost": "price reversed off the Asia high " + "x" * 900, "visible_at_entry": True,
            "visible_evidence": "last two M15 closed against", "entry_review_verdict": "should_have_waited",
            "alternative_action": self.action, "alternative_rule": "skip longs when the last 2 closed M15 candles closed below open",
            "lesson": "respect the M15 turn"}}


def backfilled(tmp_path, **kw):
    stubs = {"openai": Stub("openai", "WAIT", marker="O"), "claude": Stub("claude", "ENTER", marker="C")}
    code, j, cl, _ = go(tmp_path, stubs=stubs, **kw)
    assert code == 0
    return j


def test_schema_suits_both_strict_modes():
    s = PM.schema()
    assert set(s["required"]) == set(s["properties"]) and s["additionalProperties"] is False
    assert "maxLength" not in json.dumps(s)


def test_postmortem_only_losers_stores_both_and_cuts_text(tmp_path):
    j = backfilled(tmp_path)
    provs = {"claude": PMStub("claude"), "openai": PMStub("openai", "wait_for_m15_turn")}
    cl = PathOanda()
    code = run(PM.run(bf_cfg(), "live", 10, tmp_path / "pm", client=cl, journal=j, providers=provs))
    assert code == 0
    rows = [dict(r) for r in j.db.execute("SELECT * FROM dyn_postmortems")]
    assert {r["candidate_id"] for r in rows} == {"t2", "t4"}                      # the two losers only
    assert len(rows) == 4 and all(r["error"] is None and len(r["why_lost"]) == PM.MAX_TEXT for r in rows)
    u = provs["openai"].users[0]
    assert "PACKET:" in u and "YOUR ENTRY REVIEW:" in u and '"action": "WAIT"' in u and "WHAT HAPPENED:" in u
    assert '"action": "ENTER"' in provs["claude"].users[0]                        # each sees its own entry review
    # the path starts at the entry and stops 30 minutes after the exit
    t4 = [r for r in cl.requests if r["price"] == "M" and r["granularity"] == "M1"]
    assert t4 and max(pd.Timestamp(r["to"]) for r in t4) <= pd.Timestamp("2026-10-23T15:30:00-04:00").tz_convert("UTC")
    rep = (tmp_path / "pm" / "report.md").read_text()
    assert "HINDSIGHT" in rep and "wait_for_m15_turn" in rep and "skip longs when" in rep
    # run again: nothing left to do, no calls
    n = len(provs["claude"].users)
    assert run(PM.run(bf_cfg(), "live", 10, tmp_path / "pm", client=cl, journal=j, providers=provs)) == 0
    assert len(provs["claude"].users) == n


def test_failed_postmortem_is_stored_with_error_and_retried(tmp_path):
    j = backfilled(tmp_path)
    run(PM.run(bf_cfg(), "live", 10, tmp_path / "pm", client=PathOanda(), journal=j,
               providers={"claude": PMStub("claude", fail=True)}))
    assert {r[0] for r in j.db.execute("SELECT error FROM dyn_postmortems")} == {"HTTP 500: boom"}
    assert len(PM.pick(j, 10)) == 2                                               # errors don't count as done


def test_validate_rejects_wrong_id_and_bad_enum():
    good = {"candidate_id": "t2", "why_lost": "a", "visible_at_entry": False, "visible_evidence": "", "entry_review_verdict":
            "entry_was_reasonable", "alternative_action": "skip", "alternative_rule": "r", "lesson": "l"}
    assert PM.validate(good, "t2")[1] is None
    assert PM.validate(good, "t9")[1].startswith("invalid")
    assert PM.validate({**good, "alternative_action": "pray"}, "t2")[1].startswith("invalid")


def test_n_is_capped(tmp_path):
    assert run(PM.run(bf_cfg(), "live", 51, tmp_path, client=PathOanda(), journal=None, providers={})) == 2


def test_explain_shows_wait_reasons_summary_and_labels(tmp_path):
    j = backfilled(tmp_path)
    txt = X.report(j, bf_cfg(), "live")
    assert "past trade, reviewed afterwards" in txt and "OpenAI: WAIT" in txt and "waiting for:" in txt
    assert "## Summary" in txt and "what its WAITs were waiting for" in txt
    assert "decisive evidence:" in txt and "no model was called" in txt
    assert "Post-mortems" not in txt                                              # none yet


def test_ask_json_both_providers(monkeypatch):
    keys(monkeypatch)
    seen = {}

    def h(req):
        seen[req.url.host] = json.loads(req.content)
        if "anthropic" in req.url.host:
            return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps({"a": 1})}], "stop_reason": "end_turn",
                                             "usage": {"input_tokens": 1000, "output_tokens": 100}})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"a": 2})}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 1000, "completion_tokens": 100}})
    p = {"m-1": {"in_per_mtok": 2.0, "out_per_mtok": 10.0}}
    c = run(PR.ClaudeProvider("m-1", p, 5, httpx.MockTransport(h)).ask_json("s", "u", PM.schema(), "pm"))
    o = run(PR.OpenAIProvider("m-1", p, 5, httpx.MockTransport(h)).ask_json("s", "u", PM.schema(), "pm"))
    assert c["obj"] == {"a": 1} and o["obj"] == {"a": 2} and c["error"] is None
    assert abs(c["cost_usd"] - 0.003) < 1e-9
    assert seen["api.anthropic.com"]["output_config"]["format"]["schema"] == PM.schema()
    assert seen["api.openai.com"]["response_format"]["json_schema"]["strict"] is True
    assert "SECRET" not in json.dumps(seen)

    def bad(req):
        return httpx.Response(529, text="overloaded")
    e = run(PR.ClaudeProvider("m-1", p, 5, httpx.MockTransport(bad)).ask_json("s", "u", PM.schema()))
    assert e["obj"] is None and "529" in e["error"]
