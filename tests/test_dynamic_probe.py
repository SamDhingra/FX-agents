"""Claude's structured-output schema (no enum next to a type list; OpenAI's body unchanged) and the live probe (httpx stubbed)."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from fxagents.dynamic import probe as PB
from fxagents.dynamic import providers as PR
from tests.test_dynamic_review import GOOD, claude_reply, openai_reply


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


# the schema OpenAI was sent before this change, frozen
OPENAI_ROUND1 = json.dumps(PR.review_schema(True, False), sort_keys=False)
OPENAI_ROUND2 = json.dumps(PR.review_schema(True, True), sort_keys=False)


@pytest.mark.parametrize("exchange", [False, True])
def test_claude_schema_has_no_enum_next_to_a_type_list_and_nullable_enums_are_anyof(exchange):
    sc = PR.review_schema_claude(exchange)
    for n in walk(sc):
        assert not (isinstance(n.get("type"), list)), n
        assert not ("enum" in n and isinstance(n.get("type"), list))
        for banned in ("maxLength", "minLength", "maxItems", "minItems", "minimum", "maximum"):
            assert banned not in n
    assert sc["additionalProperties"] is False and set(sc["required"]) == set(sc["properties"])
    for key, names in (("trigger_id", PR.TRIGGERS), ("invalidation_id", PR.INVALIDATIONS)):
        assert sc["properties"][key] == {"anyOf": [{"type": "string", "enum": list(names)}, {"type": "null"}]}
    assert ("changed" in sc["properties"]) == exchange


def test_the_anyof_rewrite_also_handles_plain_nullable_types_and_nested_nodes():
    out = PR._anyof({"type": "object", "properties": {"a": {"type": ["string", "null"]}, "b": {"type": "array", "items": {"type": ["integer", "null"], "enum": [1, None]}}}})
    assert out["properties"]["a"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert out["properties"]["b"]["items"] == {"anyOf": [{"type": "integer", "enum": [1]}, {"type": "null"}]}


def request_body(cls, exchange):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=claude_reply() if cls is PR.ClaudeProvider else openai_reply())
    p = cls("m-1", {}, 5, httpx.MockTransport(handler))
    import os
    os.environ[p.env_key] = "k"
    coro = p.review_exchange("{}", "abc123", {"action": "ENTER"}, {"action": "ENTER"}) if exchange else p.review("{}", "abc123")
    asyncio.run(coro)
    return seen["body"]


@pytest.mark.parametrize("exchange", [False, True])
def test_requests_carry_the_right_schema_per_provider(exchange, monkeypatch):
    c = request_body(PR.ClaudeProvider, exchange)
    assert c["output_config"]["format"]["schema"] == PR.review_schema_claude(exchange)
    o = request_body(PR.OpenAIProvider, exchange)
    sent = o["response_format"]["json_schema"]["schema"]
    assert json.dumps(sent) == (OPENAI_ROUND2 if exchange else OPENAI_ROUND1)          # byte-identical to before
    assert sent["properties"]["trigger_id"] == {"type": ["string", "null"], "enum": [*PR.TRIGGERS, None]}


# ── the probe ──────────────────────────────────────────────────────────────────────────────────────────────────
def prov(cls, handler, monkeypatch, prices=True):
    monkeypatch.setenv(cls.env_key, "secret-key-123")
    return cls("m-1", {"m-1": {"in_per_mtok": 3.0, "out_per_mtok": 15.0}} if prices else {}, 5, httpx.MockTransport(handler))


def ok_reply(cid):
    return {**GOOD, "candidate_id": cid}


def test_probe_reports_each_provider_and_exits_0_when_all_answer(monkeypatch, capsys):
    def claude(req):
        body = json.loads(req.content)
        cid = json.loads(body["messages"][0]["content"].split("PACKET:\n", 1)[1])["candidate"]["id"]
        assert cid.startswith("probe-") and "XAUUSD" in body["messages"][0]["content"]
        return httpx.Response(200, json=claude_reply(ok_reply(cid)))

    def openai(req):
        body = json.loads(req.content)
        cid = json.loads(body["messages"][1]["content"].split("PACKET:\n", 1)[1])["candidate"]["id"]
        return httpx.Response(200, json=openai_reply(ok_reply(cid)))
    provs = {"claude": prov(PR.ClaudeProvider, claude, monkeypatch), "openai": prov(PR.OpenAIProvider, openai, monkeypatch)}
    assert asyncio.run(PB.run({}, provs)) == 0
    out = capsys.readouterr().out
    assert "probe-" in out and "claude" in out and "openai" in out and "m-1" in out and "latency" in out and "tokens" in out and "cost $" in out
    assert "ALL PROVIDERS ANSWERED" in out and "secret-key-123" not in out


def test_probe_prints_the_full_error_text_and_exits_1_on_any_failure(monkeypatch, capsys):
    msg = "output_config.format.schema: Invalid schema: Enum value 'm15_close_in_direction' does not match the declared type " + "y" * 300
    provs = {"claude": prov(PR.ClaudeProvider, lambda r: httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": msg}}), monkeypatch),
             "openai": prov(PR.OpenAIProvider, lambda r: httpx.Response(200, json=openai_reply(ok_reply(json.loads(json.loads(r.content)["messages"][1]["content"].split("PACKET:\n", 1)[1])["candidate"]["id"]))), monkeypatch)}
    assert asyncio.run(PB.run({}, provs)) == 1
    out = capsys.readouterr().out
    assert "FAIL ABSTAIN" in out and msg in out and "NOT ANSWERED: claude" in out and "OK " in out


def test_probe_with_no_provider_or_no_key_exits_1(monkeypatch, capsys):
    assert asyncio.run(PB.run({"dynamic": {}})) == 1
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert asyncio.run(PB.run({}, {"claude": PR.ClaudeProvider("m-1")})) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_probe_stores_nothing_and_opens_no_journal(monkeypatch):
    import fxagents.journal as J
    monkeypatch.setattr(J.Journal, "__init__", lambda *a, **k: (_ for _ in ()).throw(AssertionError("journal opened")))
    p = prov(PR.ClaudeProvider, lambda r: httpx.Response(529, text="overloaded"), monkeypatch)
    assert asyncio.run(PB.run({}, {"claude": p})) == 1


def test_fx_sh_has_dynprobe():
    sh = (Path(__file__).parents[1] / "fx.sh").read_text()
    assert "dynprobe)" in sh and "python -m fxagents.dynamic.probe" in sh and "dynprobe |" in sh
