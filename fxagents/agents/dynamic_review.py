"""Shadow review gate (Oct 26 2026, docs/dynamic_controller.md, milestone 1): for every entry Risk approves, freeze what
was known at that moment and ask a Claude and an OpenAI reviewer, sealed from each other, ENTER / WAIT / CANCEL.
Their answers are journaled and scored later against what the trade really did, net of the API cost. They change NO
trade: the hook in RiskAgent runs after the position exists and only hands over a packet; the model calls are
background tasks with a hard deadline (same approach as the Jev adviser), so the bar path never waits and never sees an
exception. Config `dynamic:` in config.yaml; books not in `dynamic.books` (and sim / replay runs) switch it off.
"""
from __future__ import annotations

import asyncio
import time

import pandas as pd

from ..dynamic import store
from ..dynamic.packet import build_packet, canonical
from ..dynamic.providers import PROMPT_VERSION, abstain, build_providers, result
from ..state import trading_day
from .core import Agent


class DynamicReviewAgent(Agent):
    name = "dynamic_review"

    def start(self):
        super().start()
        c = self.cfg.get("dynamic") or {}
        # the practice account's context has no book_key yet when its agents start (main.py sets it afterwards)
        self.book = getattr(self.ctx, "book_key", None) or "live"
        self.on = (bool(c.get("enabled", False)) and self.book in set(c.get("books") or ["live", "playbook"])
                   and self.cfg.get("mode") in ("paper", "live") and not self.cfg.get("replay")
                   and self.ctx.journal is not None)
        self._tasks: dict[str, asyncio.Task] = {}   # candidate id -> in-flight reviews; also keeps references alive
        self.providers: dict = {}
        if not self.on:
            return
        self.deadline = float(c.get("deadline_s", 25))
        self.budget = int(c.get("daily_call_budget", 120))
        self.sem = asyncio.Semaphore(max(1, int(c.get("max_concurrency", 4))))
        self.used: dict[tuple[str, str], int] = {}  # (provider, trading day) -> calls reserved, seeded from the journal
        store.ensure_schema(self.ctx.journal)
        self.providers = build_providers(c)
        for name, p in self.providers.items():
            if not p.available():
                self.log.warning("dynamic review (%s): no %s in the environment, so the %s arm is off and records ABSTAIN",
                                 self.book, p.env_key, name)
        if not c.get("openai_model"):
            self.log.info("dynamic review (%s): dynamic.openai_model is empty, the OpenAI arm is off", self.book)
        self.ctx.dyn_review = self          # RiskAgent looks this up; absent = no hook
        self.bus.subscribe("clock", self.on_clock)

    async def on_clock(self, now):
        self.beat()                          # alive, not busy: it only works when an entry happens

    # ── the hook (called synchronously by RiskAgent after the position is open) ──────────────────────
    def submit_entry(self, *, sig, pos, price: float, spread: float | None, cost_r: float | None) -> None:
        """Build the frozen packet and start the reviews in the background. Never raises, never waits."""
        if not self.on:
            return
        try:
            ts = pd.Timestamp(sig.ts)
            sym = pos.symbol
            store_ = self.ctx.store
            rec = None
            try:
                st = self.ctx.journal.live_stats(strategy=pos.strategy)
                rec = {"trades": st["n"], "avg_r": st["expectancy"]} if st["n"] else None
            except Exception:  # noqa: BLE001 — the record is optional context
                rec = None
            packet = build_packet(
                candidate_id=pos.id, book=self.book, symbol=sym, side=pos.side, strategy=pos.strategy, ts=ts, entry=price,
                stop=pos.initial_stop, target_r=pos.rr, spread=spread, cost_r=cost_r, instrument=self.cfg["instruments"].get(sym),
                m1=store_.m1(sym), h1=store_.h1(sym), bias=self.state.bias_for(sym), record=rec,
                m15_live=pos.meta.get("m15_live"))
            self.submit(packet)
        except Exception as e:  # noqa: BLE001 — a review must never disturb an entry
            self.log.warning("dynamic review %s: packet not built (%s: %s)", getattr(pos, "symbol", "?"), type(e).__name__, e)

    def submit(self, packet: dict) -> None:
        """Record the candidate and start its reviews. Never raises."""
        if not self.on:
            return
        try:
            cid = packet["candidate"]["id"]
            store.add_candidate(self.ctx.journal, packet, "pending", PROMPT_VERSION)
            task = asyncio.ensure_future(self._review_all(cid, packet))
            self._tasks[cid] = task
            task.add_done_callback(lambda t, c=cid: self._tasks.get(c) is t and self._tasks.pop(c, None))
        except Exception as e:  # noqa: BLE001
            self.log.warning("dynamic review: not started (%s: %s)", type(e).__name__, e)

    async def drain(self) -> None:
        """Wait for in-flight reviews (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
            await asyncio.sleep(0)

    # ── background work ───────────────────────────────────────────────────────────────────────────
    async def _review_all(self, cid: str, packet: dict) -> None:
        try:
            text = canonical(packet)               # one text, byte-identical for every provider
            await asyncio.gather(*[self._one(name, p, cid, packet, text) for name, p in self.providers.items()])
            store.set_status(self.ctx.journal, cid, "reviewed")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self.log.warning("dynamic review %s: %r", cid, e)

    def _take_budget(self, name: str, day: str) -> bool:
        key = (name, day)
        if key not in self.used:
            self.used[key] = store.calls_on(self.ctx.journal, name, day)
        if self.used[key] >= self.budget:
            return False
        self.used[key] += 1
        return True

    async def _one(self, name: str, prov, cid: str, packet: dict, text: str) -> None:
        j = self.ctx.journal
        ts = packet["candidate"]["entry_time_ny"]
        day = trading_day(pd.Timestamp(ts, tz=self.cfg["timezone"]))
        t0 = time.monotonic()
        called = False
        try:
            if not prov.available():
                res = abstain(f"no {prov.env_key} in the environment")
            elif not self._take_budget(name, day):
                res = result("NOT_REVIEWED", f"not_reviewed: budget ({self.budget} calls a day reached)")
            else:
                called = True
                try:
                    async def call():
                        async with self.sem:         # waiting for a slot counts against the deadline
                            return await prov.review(text, cid)
                    res = await asyncio.wait_for(call(), timeout=self.deadline)
                except asyncio.TimeoutError:
                    res = abstain(f"timeout: no valid reply within {self.deadline:g}s")
            if called:
                res["latency_ms"] = (time.monotonic() - t0) * 1000     # from the hand-over: what a live gate would wait
            store.add_review(j, cid, name, prov.model, PROMPT_VERSION, packet["packet_hash"], res, called, day,
                             (self.state.now or pd.Timestamp.now(tz=self.cfg["timezone"])).isoformat(timespec="seconds"))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — never raise out of a review task
            self.log.warning("dynamic review %s/%s: %r", cid, name, e)
