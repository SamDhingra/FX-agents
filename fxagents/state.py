"""Shared, read-mostly live state. Agents write their slice; the dashboard reads a snapshot."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LiveState:
    mode: str = "sim"
    started: float = field(default_factory=time.time)
    now: datetime | None = None                 # market clock (sim time in sim mode)
    equity: float = 0.0
    equity_peak: float = 0.0
    day_start_equity: float = 0.0
    realized_today: float = 0.0
    trading_enabled: bool = True
    halt_reason: str = ""
    last_prices: dict[str, float] = field(default_factory=dict)
    last_bar_ts: dict[str, str] = field(default_factory=dict)
    positions: dict[str, Any] = field(default_factory=dict)          # id -> Position
    selections: dict[str, list[dict]] = field(default_factory=dict)  # symbol -> ranked picks this hour
    strategy_stats: dict[str, dict[str, dict]] = field(default_factory=dict)  # symbol -> version -> stats
    strategy_registry: list[dict] = field(default_factory=list)
    heartbeats: dict[str, float] = field(default_factory=dict)
    decisions: deque = field(default_factory=lambda: deque(maxlen=300))
    alerts: deque = field(default_factory=lambda: deque(maxlen=200))
    equity_curve: deque = field(default_factory=lambda: deque(maxlen=3000))
    learner_log: deque = field(default_factory=lambda: deque(maxlen=200))

    def beat(self, agent: str) -> None:
        self.heartbeats[agent] = time.time()

    def alert(self, level: str, msg: str, **extra: Any) -> dict:
        a = {"ts": (self.now or datetime.now()).isoformat(timespec="seconds"), "level": level, "msg": msg, **extra}
        self.alerts.appendleft(a)
        return a
