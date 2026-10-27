"""Model reviewers for the shadow review gate: Claude (forced tool) and OpenAI (strict JSON schema), plain httpx.

Oct 26 2026, docs/dynamic_controller.md. Both get the same system prompt and the same packet text and never see each
other's answer. Whatever goes wrong (no key, HTTP error, timeout, refusal, unreadable or invalid reply, wrong candidate
id) comes back as an ABSTAIN with the reason, never as an exception, so a reviewer can't disturb anything. Tokens come
from the response's usage block; cost = tokens × the price configured in `dynamic.prices` (None when no price is set).
Keys are read from the environment at call time and never stored, logged or put in a prompt.
"""
from __future__ import annotations

import json
import os
import time

import httpx

PROMPT_VERSION = "dyn-v1"
ACTIONS = ("ENTER", "WAIT", "CANCEL")
TRIGGERS = ("m15_close_in_direction", "m5_close_beyond_entry_candle", "retest_of_entry")
INVALIDATIONS = ("stop_touched", "m15_close_against", "expiry_30m")
MAX_TEXT, MAX_MISSING = 300, 8

SYSTEM_PROMPT = f"""You are an independent second-opinion reviewer for an automated intraday trading bot (prompt {PROMPT_VERSION}).

The bot trades NAS100 (NDQ), US30 and gold (XAUUSD) on short timeframes on a practice account. A setup has JUST passed
every deterministic gate: the higher-timeframe bias agrees with the side, no news blackout is active, it is inside the
entry windows and the risk limits hold (the spread cost is shown to you as cost_r, not hidden). The position is being opened now. You are shown a frozen
PACKET JSON of what was known at that moment and nothing later: the order (entry, stop, spread, cost_r = spread / stop
distance), the structural bias (label, score, daily / 4H / 1H direction, how old the reading is), closed M5, M15 and H1
candles [start_ny, open, high, low, close], the still-forming M15 candle (labelled partial: do not treat it as closed),
levels known at the time (prior-day high/low, Asia high/low, the 4H swing high/low), the NY session clock, the next
scheduled USD release and minutes to it, and the setup's own track record if known.

Your single question: for THIS entry, right now, is it ENTER, WAIT or CANCEL?
  ENTER   take the entry as planned.
  WAIT    not now, but it may become valid; give the trigger that would make it valid (trigger_id) and what would kill
          it (invalidation_id).
  CANCEL  the setup is not worth taking; say what is decisive.
trigger_id must be one of: {", ".join(TRIGGERS)} (or null).
invalidation_id must be one of: {", ".join(INVALIDATIONS)} (or null).

Rules:
- Use ONLY the packet. Do not invent prices, levels, news or data that are not in it; if something you need is missing,
  list it in missing_data instead of guessing.
- The packet is a pattern of numbers, not advice: weigh trend structure, location against the listed levels, the
  forming candle, spread cost and event risk. Being cautious without a concrete reason in the packet is not a reason.
- You have no authority over orders. You cannot place, move or cancel anything, change risk or settings; your answer is
  recorded and scored later against what the trade really did.
- Echo the packet's candidate id exactly in candidate_id.
- decisive_evidence and conflicting_evidence: plain sentences, each at most {MAX_TEXT} characters, citing numbers from the packet.
Return your answer only through the structured output."""


def review_schema(strict_openai: bool = False) -> dict:
    """The answer schema (docs/dynamic_controller.md). OpenAI's strict mode gets the same shape without the length
    keywords, which it may reject; the limits are enforced locally in validate()."""
    def text(n):
        return {"type": "string"} if strict_openai else {"type": "string", "maxLength": n}
    arr = {"type": "array", "items": text(120)}
    if not strict_openai:
        arr["maxItems"] = MAX_MISSING
    return {"type": "object", "additionalProperties": False,
            "properties": {
                "candidate_id": {"type": "string"},
                "action": {"type": "string", "enum": list(ACTIONS)},
                "trigger_id": {"type": ["string", "null"], "enum": [*TRIGGERS, None]},
                "invalidation_id": {"type": ["string", "null"], "enum": [*INVALIDATIONS, None]},
                "decisive_evidence": text(MAX_TEXT),
                "conflicting_evidence": text(MAX_TEXT),
                "missing_data": arr},
            "required": ["candidate_id", "action", "trigger_id", "invalidation_id", "decisive_evidence",
                         "conflicting_evidence", "missing_data"]}


def validate(obj, candidate_id: str) -> tuple[dict | None, str | None]:
    """(clean answer, None) or (None, reason). Over-long text is cut, not rejected: it changes no decision."""
    if not isinstance(obj, dict):
        return None, "invalid: reply is not a JSON object"
    if obj.get("candidate_id") != candidate_id:
        return None, f"invalid: candidate_id {str(obj.get('candidate_id'))[:24]!r} does not match"
    if obj.get("action") not in ACTIONS:
        return None, f"invalid: action {str(obj.get('action'))[:24]!r} not in {'/'.join(ACTIONS)}"
    out = {"action": obj["action"]}
    for key, menu in (("trigger_id", TRIGGERS), ("invalidation_id", INVALIDATIONS)):
        v = obj.get(key)
        if v is not None and v not in menu:
            return None, f"invalid: {key} {str(v)[:30]!r} not in the menu"
        out[key] = v
    for key, name in (("decisive_evidence", "evidence"), ("conflicting_evidence", "conflicting")):
        v = obj.get(key)
        if not isinstance(v, str):
            return None, f"invalid: {key} missing or not text"
        out[name] = v[:MAX_TEXT]
    md = obj.get("missing_data")
    if not isinstance(md, list) or not all(isinstance(x, str) for x in md):
        return None, "invalid: missing_data is not a list of text"
    out["missing"] = [x[:120] for x in md[:MAX_MISSING]]
    return out, None


def result(action: str = "ABSTAIN", error: str | None = None, **kw) -> dict:
    return {"action": action, "trigger_id": None, "invalidation_id": None, "evidence": None, "conflicting": None,
            "missing": [], "error": error, "tokens_in": None, "tokens_out": None, "cost_usd": None, "latency_ms": None,
            "response": None, **kw}


def abstain(reason: str, **kw) -> dict:
    return result("ABSTAIN", reason, **kw)


class Provider:
    """Base: key check, one HTTP call, local validation, token + cost accounting. Subclasses build the request and
    pull the answer object and the usage out of the response."""
    name = ""
    env_key = ""

    def __init__(self, model: str, prices: dict | None = None, timeout_s: float = 25.0, transport=None) -> None:
        self.model, self.timeout_s, self.transport = model, float(timeout_s), transport
        self.prices = (prices or {}).get(model) or {}

    def key(self) -> str:
        return os.environ.get(self.env_key, "")

    def available(self) -> bool:
        return bool(self.key())

    def cost(self, tin, tout) -> float | None:
        pi, po = self.prices.get("in_per_mtok"), self.prices.get("out_per_mtok")
        if tin is None or tout is None or pi is None or po is None:
            return None
        return round((tin * float(pi) + tout * float(po)) / 1e6, 6)

    def request(self, system: str, packet_json: str, candidate_id: str) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def parse(self, body: dict) -> tuple[object, int | None, int | None, str | None]:
        """(answer object, tokens in, tokens out, error)"""
        raise NotImplementedError

    def clean(self, text: str) -> str:
        k = self.key()
        return text.replace(k, "***") if k else text

    async def review(self, packet_json: str, candidate_id: str) -> dict:
        if not self.available():
            return abstain(f"no {self.env_key} in the environment")
        t0 = time.monotonic()
        tin = tout = None
        try:
            url, headers, body = self.request(SYSTEM_PROMPT, packet_json, candidate_id)
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s), transport=self.transport) as cl:
                r = await cl.post(url, headers=headers, json=body)
            if r.status_code != 200:
                return abstain(self.clean(f"HTTP {r.status_code}: {r.text[:160]}"), latency_ms=(time.monotonic() - t0) * 1000)
            try:
                payload = r.json()
            except ValueError:
                return abstain("invalid: response is not JSON", latency_ms=(time.monotonic() - t0) * 1000)
            obj, tin, tout, err = self.parse(payload)
            lat = (time.monotonic() - t0) * 1000
            kw = {"tokens_in": tin, "tokens_out": tout, "cost_usd": self.cost(tin, tout), "latency_ms": lat,
                  "response": self.clean(json.dumps(obj, default=str)[:2000]) if obj is not None else None}
            if err:
                return abstain(err, **kw)
            clean, why = validate(obj, candidate_id)
            if clean is None:
                return abstain(why, **kw)
            return result(**{**clean, "error": None}, **kw)
        except Exception as e:  # noqa: BLE001 — a reviewer never raises (timeouts, network, bad payload shapes)
            return abstain(self.clean(f"{type(e).__name__}: {str(e)[:120]}"), tokens_in=tin, tokens_out=tout,
                           latency_ms=(time.monotonic() - t0) * 1000)


class ClaudeProvider(Provider):
    name, env_key = "claude", "ANTHROPIC_API_KEY"
    URL = "https://api.anthropic.com/v1/messages"

    def request(self, system, packet_json, candidate_id):
        headers = {"x-api-key": self.key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": 1024, "system": system,
                "tools": [{"name": "review", "description": "Record your review of this entry.",
                           "input_schema": review_schema()}],
                "tool_choice": {"type": "tool", "name": "review"},
                "messages": [{"role": "user", "content": "PACKET:\n" + packet_json}]}
        return self.URL, headers, body

    def parse(self, body):
        u = body.get("usage") or {}
        tin, tout = u.get("input_tokens"), u.get("output_tokens")
        if body.get("stop_reason") == "refusal":
            return None, tin, tout, "refused by the model"
        for b in body.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "review":
                return b.get("input"), tin, tout, None
        return None, tin, tout, f"invalid: no review tool call (stop_reason {body.get('stop_reason')})"


class OpenAIProvider(Provider):
    name, env_key = "openai", "OPENAI_API_KEY"
    URL = "https://api.openai.com/v1/chat/completions"

    def request(self, system, packet_json, candidate_id):
        headers = {"Authorization": "Bearer " + self.key(), "content-type": "application/json"}
        body = {"model": self.model, "max_completion_tokens": 2000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": "PACKET:\n" + packet_json}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "review", "strict": True, "schema": review_schema(True)}}}
        return self.URL, headers, body

    def parse(self, body):
        u = body.get("usage") or {}
        tin, tout = u.get("prompt_tokens"), u.get("completion_tokens")
        ch = (body.get("choices") or [None])[0]
        if not isinstance(ch, dict):
            return None, tin, tout, "invalid: no choices in the response"
        msg = ch.get("message") or {}
        if msg.get("refusal"):
            return None, tin, tout, "refused by the model"
        if ch.get("finish_reason") == "length":
            return None, tin, tout, "invalid: reply cut off (finish_reason length)"
        try:
            return json.loads(msg.get("content") or ""), tin, tout, None
        except ValueError:
            return None, tin, tout, "invalid: reply is not valid JSON"


def build_providers(dyn: dict, transport=None) -> dict[str, Provider]:
    """The arms that are switched on: a provider exists only when its model name is configured."""
    prices, tmo = dyn.get("prices") or {}, float(dyn.get("deadline_s", 25))
    out: dict[str, Provider] = {}
    if dyn.get("claude_model"):
        out["claude"] = ClaudeProvider(str(dyn["claude_model"]), prices, tmo, transport)
    if dyn.get("openai_model"):
        out["openai"] = OpenAIProvider(str(dyn["openai_model"]), prices, tmo, transport)
    return out
