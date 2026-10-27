"""The review coroutine shared by the live shadow gate and the retrospective backfill (Oct 27 2026).

One implementation of: round 1 for every provider concurrently (sealed), then the one exchange when both answers are
valid, same prompts, same validation, same daily budget counter, same deadlines. The live agent (agents/dynamic_review.py)
and the backfill (dynamic/backfill.py) subclass `ReviewRunner` and differ only in the small hooks below, so a
retrospective review is the live path run on a past packet, not a copy of it.

The host provides: `ctx.journal`, `cfg`, `log`, `providers`, `deadline`, `exchange_deadline`, `budget`, `sem`, `used`.
Hooks: `source` (stored on the candidate row), `now_iso()`, `budget_day(packet)`.
"""
from __future__ import annotations

import asyncio
import time

import pandas as pd

from . import store
from .packet import canonical
from .providers import ACTIONS, EXCHANGE_PROMPT_VERSION, PROMPT_VERSION, abstain, exchange_decision, other_view, result
from ..state import trading_day


class ReviewRunner:
    source = "live"

    def now_iso(self) -> str:
        return (self.state.now or pd.Timestamp.now(tz=self.cfg["timezone"])).isoformat(timespec="seconds")

    def budget_day(self, packet: dict) -> str:
        """The trading day whose call count this review uses: the entry's own day (the review runs right then)."""
        return trading_day(pd.Timestamp(packet["candidate"]["entry_time_ny"], tz=self.cfg["timezone"]))

    async def _review_all(self, cid: str, packet: dict) -> None:
        try:
            text = canonical(packet)               # one text, byte-identical for every provider and both rounds
            t_start = time.monotonic()             # the hand-over: round 1 starts, the exchange clock starts
            names = list(self.providers)
            r1 = await asyncio.gather(*[self._one(n, self.providers[n], cid, packet, text) for n in names])
            first = dict(zip(names, r1))
            await self._exchange(cid, packet, text, first, t_start)
            store.set_status(self.ctx.journal, cid, "reviewed")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self.log.warning("dynamic review %s: %r", cid, e)

    async def _exchange(self, cid: str, packet: dict, text: str, first: dict, t_start: float) -> None:
        """Milestone 1b: when both round-1 answers are valid, each reviewer sees the other's round-1 answer once and answers
        again, concurrently and sealed from the other's round 2. Records the exchange status, latency and decision."""
        j = self.ctx.journal
        try:
            if len(self.providers) < 2:
                have = ", ".join(self.providers) or "none"
                store.set_exchange(j, cid, f"skipped: needs both reviewers (configured: {have})")
                return
            bad = [f"{n}: {r['action']}" for n, r in first.items() if r["action"] not in ACTIONS]
            if bad:
                store.set_exchange(j, cid, "skipped: round 1 not valid (" + ", ".join(bad) + ")")
                return
            names = list(self.providers)
            others = {n: other_view(first[next(m for m in names if m != n)]) for n in names}      # each gets the OTHER's round 1
            r2 = await asyncio.gather(*[self._one(n, self.providers[n], cid, packet, text, round_no=2, other=others[n], t_start=t_start,
                                                  own=first[n])
                                        for n in names])
            second = dict(zip(names, r2))
            ms = (time.monotonic() - t_start) * 1000
            store.set_exchange(j, cid, "done", ms, exchange_decision(second.get("openai"), second.get("claude")))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self.log.warning("dynamic review %s: exchange failed (%r)", cid, e)
            try:
                store.set_exchange(j, cid, f"skipped: error {type(e).__name__}")
            except Exception:  # noqa: BLE001
                pass

    def _take_budget(self, name: str, day: str) -> bool:
        key = (name, day)
        if key not in self.used:
            self.used[key] = store.calls_on(self.ctx.journal, name, day)
        if self.used[key] >= self.budget:
            return False
        self.used[key] += 1
        return True

    async def _one(self, name: str, prov, cid: str, packet: dict, text: str, round_no: int = 1, other: dict | None = None,
                   t_start: float | None = None, own: dict | None = None) -> dict:
        """One reviewer call (round 1, or round 2 with the other's round-1 answer); journals it and returns the result."""
        j = self.ctx.journal
        day = self.budget_day(packet)
        t0 = time.monotonic()
        called = False
        version = PROMPT_VERSION if round_no == 1 else EXCHANGE_PROMPT_VERSION
        # round 1: its own deadline, from the hand-over. round 2: whatever is left of the exchange window.
        limit = self.deadline if round_no == 1 else self.exchange_deadline - (t0 - (t_start if t_start is not None else t0))
        res = abstain("review task failed")
        try:
            if not prov.available():
                res = abstain(f"no {prov.env_key} in the environment")
            elif round_no == 2 and limit <= 0:
                res = abstain(f"exchange deadline: round 1 used the whole {self.exchange_deadline:g}s window")
            elif not self._take_budget(name, day):
                res = result("NOT_REVIEWED", f"not_reviewed: budget ({self.budget} calls a day reached)")
            else:
                called = True
                try:
                    async def call():
                        async with self.sem:         # waiting for a slot counts against the deadline
                            if round_no == 1:
                                return await prov.review(text, cid)
                            return await prov.review_exchange(text, cid, other, other_view(own))
                    res = await asyncio.wait_for(call(), timeout=limit)
                except asyncio.TimeoutError:
                    res = abstain(f"timeout: no valid reply within {self.deadline:g}s" if round_no == 1 else
                                  f"exchange deadline: no valid round-2 reply within the {self.exchange_deadline:g}s exchange window")
            if round_no == 2 and res.get("action") in ACTIONS:
                # `changed` is computed here against the reviewer's own round-1 answer; what the model said is kept apart
                res["changed_reported"] = res.get("changed")
                res["changed"] = any(res.get(k) != (own or {}).get(k) for k in ("action", "trigger_id", "invalidation_id"))
            if called:
                # round 1: from the hand-over, what a live gate would wait. round 2: the round-2 call itself; the whole
                # exchange is on the candidate (exchange_ms)
                res["latency_ms"] = (time.monotonic() - t0) * 1000
            store.add_review(j, cid, name, prov.model, version, packet["packet_hash"], res, called, day,
                             self.now_iso(), round_no)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — never raise out of a review task
            self.log.warning("dynamic review %s/%s (round %s): %r", cid, name, round_no, e)
        return res
