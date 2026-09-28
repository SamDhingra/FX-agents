"""Shared plumbing for agents + the strategy book (registry of strategy versions)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..strategies import Strategy, build_strategy, default_specs


@dataclass
class Ctx:
    """Everything an agent may touch. Agents still only *communicate* via the bus."""
    cfg: Any
    bus: Any
    state: Any
    store: Any
    broker: Any
    journal: Any
    jev: Any
    book: "StrategyBook"
    news: Any = None


class Agent:
    name = "agent"

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx
        self.cfg, self.bus, self.state = ctx.cfg, ctx.bus, ctx.state
        self.log = logging.getLogger(self.name)

    def beat(self) -> None:
        self.state.beat(self.name)

    def start(self) -> None:  # subscribe here
        self.beat()

    async def loop(self) -> None:  # optional long-running task
        return None

    def now(self) -> pd.Timestamp:
        return self.state.now or pd.Timestamp.now(tz=self.cfg["timezone"])


class StrategyBook:
    """All strategy versions: live (tradeable), shadow (evaluated, not traded), retired."""

    def __init__(self, journal, rr: float, tfs: tuple[str, ...] = ("5min", "15min")) -> None:
        self.journal = journal
        self.items: dict[str, Strategy] = {}
        specs = journal.load_strategies() or default_specs(rr, tfs)
        for s in specs:
            if s.get("status") != "retired":
                st = build_strategy(s)
                self.items[st.id] = st
        for st in self.items.values():
            journal.save_strategy(st.spec(), pd.Timestamp.now().isoformat(timespec="seconds"))

    def live(self) -> list[Strategy]:
        return [s for s in self.items.values() if s.status == "live"]

    def evaluated(self) -> list[Strategy]:
        return [s for s in self.items.values() if s.status in ("live", "shadow", "candidate")]

    def get(self, sid: str) -> Strategy | None:
        return self.items.get(sid)

    def add(self, st: Strategy, ts: str, note: str = "") -> None:
        self.items[st.id] = st
        self.journal.save_strategy(st.spec(), ts, note)

    def set_status(self, sid: str, status: str, ts: str, note: str = "") -> None:
        st = self.items[sid]
        st.status = status
        self.journal.save_strategy(st.spec(), ts, note)
        if status == "retired":
            self.items.pop(sid, None)

    def next_version(self, base_name: str) -> str:
        n = [int(s.version[1:]) for s in self.items.values()
             if s.name == base_name and s.version[1:].isdigit()]
        return f"v{max(n, default=1) + 1}"

    def registry(self) -> list[dict]:
        return [s.spec() | {"description": s.description} for s in self.items.values()]
