"""Jev (TypeSafe System One) as the decision layer — the same pattern as the custom harness:
code builds a compact *state*, Jev answers typed questions (Score / Noul) with a confidence,
and ordinary code combines the answers. Every call is logged as a decision (inputs → outputs)
so the dashboard can show the lineage of each trade.

If TYPESAFE_API_KEY is missing or the API errors/times out, a transparent local heuristic answers
instead and the decision is tagged source="heuristic" — trading never blocks on the network.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Any

log = logging.getLogger("jev")

try:
    from typesafe_sdk import AsyncTypeSafeClient, Noul, Score
    HAVE_SDK = True
except Exception:  # pragma: no cover
    HAVE_SDK = False

LEVELS_EDGE = ["Very poor: expect losses", "Poor: negative edge", "Neutral: no clear edge",
               "Good: positive edge", "Excellent: strong, consistent edge"]
LEVELS_SETUP = ["D: invalid or against structure", "C: weak, low-probability", "B: acceptable",
                "A: clean, textbook", "A+: high-conviction, multiple confluences"]


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def norm_score(ans: Any) -> float:
    """Map a ScoreAnswer to 0..1 using its probability distribution over the levels."""
    probs = getattr(ans, "probabilities", None) or {}
    if probs:
        k = max(int(x) for x in probs)
        return sum(int(i) * p for i, p in probs.items()) / k if k else 0.0
    return float(getattr(ans, "score", 0.0))


class JevScorer:
    def __init__(self, cfg, state, bus) -> None:
        self.cfg, self.state, self.bus = cfg["jev"], state, bus
        self.key = os.environ.get("TYPESAFE_API_KEY", "")
        self.live = bool(self.cfg.get("enabled", True) and self.key and HAVE_SDK)
        self.client = AsyncTypeSafeClient(api_key=self.key, model=self.cfg.get("model") or None,
                                          timeout=self.cfg.get("timeout_s", 6)) if self.live else None
        self.calls = self.failures = 0

    @property
    def source(self) -> str:
        return "jev" if self.live else "heuristic"

    async def _ask(self, kind: str, state: dict, questions: dict, fallback: dict, meta: dict) -> dict:
        t0 = time.perf_counter()
        out, source, usage = fallback, "heuristic", None
        if self.live:
            try:
                self.calls += 1
                resp = await asyncio.wait_for(self.client.system_one(state=state, questions=questions),
                                              timeout=self.cfg.get("timeout_s", 6) + 1)
                out = {}
                for k, ans in resp.answers.items():
                    if ans.type == "score":
                        out[k] = {"value": round(norm_score(ans), 4), "confidence": round(ans.confidence, 4)}
                    elif ans.type == "noul":
                        out[k] = {"value": round(ans.noul, 4), "confidence": round(abs(ans.noul - 0.5) * 2, 4)}
                    else:
                        out[k] = {"value": ans.choice, "confidence": round(ans.confidence, 4)}
                source = "jev"
                usage = getattr(resp, "usage", None)
                usage = usage.model_dump() if hasattr(usage, "model_dump") else None
            except Exception as e:  # network, auth, rate-limit… fall back, never block trading
                self.failures += 1
                log.warning("Jev %s failed (%s) — using heuristic", kind, e)
                meta = {**meta, "jev_error": str(e)[:160]}
        decision = {"ts": (self.state.now.isoformat(timespec="seconds") if self.state.now else None),
                    "kind": kind, "source": source, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "inputs": state, "outputs": out, "usage": usage, **meta}
        self.state.decisions.appendleft(decision)
        await self.bus.publish("decision", decision)
        return {"answers": out, "source": source}

    # ── 1. which strategy for this symbol, this hour ──────────────────────
    async def rate_strategies(self, symbol: str, hour: int, regime: dict, cands: dict[str, dict]) -> dict:
        keys = {f"s{j}": sid for j, sid in enumerate(cands)}
        state = {"symbol": symbol, "hour_ny": hour, "regime": regime,
                 "strategies": {k: cands[sid] for k, sid in keys.items()}}
        questions: dict[str, Any] = {}
        if self.live:
            for k, sid in keys.items():
                questions[k] = Score(instructions=(
                    f"How effective will strategy {k} ({cands[sid]['name']}) be for day-trading {symbol} "
                    f"in the coming hour ({hour}:00 New York time)? Weigh its record at this hour, its "
                    f"overall and recent expectancy in R, sample size, and whether the regime suits it."),
                    criteria=LEVELS_EDGE)
            questions["trade_ok"] = Noul(instructions=(
                f"Are conditions suitable for intraday trading {symbol} in the coming hour "
                f"(adequate volatility and liquidity, no imminent high-impact news, not the session close)?"))
        fb = {k: self._h_strategy(cands[sid]) for k, sid in keys.items()}
        # scheduled news only lowers the bar here; the Risk agent hard-blocks entries around the release itself
        fb["trade_ok"] = {"value": 0.55 if regime.get("news_soon") else 0.7, "confidence": 0.4}
        res = await self._ask("strategy_rating", state, questions, fb, {"symbol": symbol})
        ans = res["answers"]
        return {"by_strategy": {sid: ans.get(k, fb[k]) for k, sid in keys.items()},
                "trade_ok": ans.get("trade_ok", fb["trade_ok"]), "source": res["source"]}

    @staticmethod
    def _h_strategy(c: dict) -> dict:
        e = c.get("this_hour_exp_shrunk", c["overall"]["expectancy"])
        rec = c.get("recent", {}).get("exp", 0.0)
        v = _sig(3.0 * e + 1.0 * rec)
        n = c["overall"]["n"]
        return {"value": round(v, 4), "confidence": round(min(0.9, n / 80), 4)}

    # ── 2. is this particular setup worth taking ─────────────────────────
    async def rate_signal(self, sig_info: dict) -> dict:
        questions: dict[str, Any] = {}
        if self.live:
            questions["quality"] = Score(instructions=(
                f"Grade this {sig_info['strategy']} {sig_info['side']} setup on {sig_info['symbol']} "
                f"for an intraday trade with the given stop. Consider structure, liquidity taken, "
                f"location (premium/discount), higher-timeframe alignment and the recent bars."),
                criteria=LEVELS_SETUP)
            questions["htf_aligned"] = Noul(instructions="Is this trade aligned with the higher-timeframe trend and market structure?")
        fb = self._h_signal(sig_info)
        res = await self._ask("signal_rating", sig_info, questions, fb, {"symbol": sig_info["symbol"],
                                                                         "strategy": sig_info["strategy"]})
        a = res["answers"]
        q = a.get("quality", fb["quality"])
        return {"quality": q["value"], "confidence": q["confidence"],
                "htf_aligned": a.get("htf_aligned", fb["htf_aligned"])["value"], "source": res["source"]}

    @staticmethod
    def _h_signal(s: dict) -> dict:
        x = 0.0
        ra = s.get("risk_atr") or 1.0
        x += 0.5 if 0.6 <= ra <= 2.5 else -0.5
        x += 0.6 * (s.get("htf_bias", 0) * (1 if s["side"] == "LONG" else -1))
        x += 1.2 * math.tanh(s.get("strategy_expectancy", 0.0))  # bounded: one great backtest ≠ certainty
        return {"quality": {"value": round(_sig(x - 0.4), 4), "confidence": 0.55},
                "htf_aligned": {"value": 0.7 if s.get("htf_bias", 0) * (1 if s["side"] == "LONG" else -1) > 0 else 0.35,
                                "confidence": 0.4}}

    # ── 3. pyramid add: is continuation likely ────────────────────────────
    async def continuation(self, info: dict) -> dict:
        questions: dict[str, Any] = {}
        if self.live:
            questions["continue"] = Noul(instructions=(
                "Is price likely to extend at least another 1R in the trade's direction before "
                "pulling back to the (now in-profit) stop?"))
        mom = info.get("momentum_aligned", 0)
        fb = {"continue": {"value": 0.62 if mom > 0 else 0.4, "confidence": 0.3}}
        res = await self._ask("pyramid_continuation", info, questions, fb, {"symbol": info["symbol"]})
        return {"prob": res["answers"].get("continue", fb["continue"])["value"], "source": res["source"]}

    # ── 4. learner: is a candidate's improvement real ────────────────────
    async def rate_candidate(self, info: dict) -> dict:
        questions: dict[str, Any] = {}
        if self.live:
            questions["robust"] = Noul(instructions=(
                "Is this candidate strategy's out-of-sample improvement over the incumbent likely to be "
                "a real, persistent edge rather than overfitting or noise?"))
        oos, inc = info["candidate_oos"], info["incumbent_oos"]
        gain = oos["expectancy"] - inc["expectancy"]
        v = _sig(4 * gain) * min(1.0, oos["n"] / 40)
        fb = {"robust": {"value": round(v, 4), "confidence": 0.4}}
        res = await self._ask("candidate_review", info, questions, fb, {"symbol": info.get("symbol")})
        return {"prob": res["answers"].get("robust", fb["robust"])["value"], "source": res["source"]}

    async def aclose(self) -> None:
        if self.client is not None:
            try:
                await self.client.aclose()  # type: ignore[attr-defined]
            except Exception:
                pass
