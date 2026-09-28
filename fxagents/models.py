from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Bar:
    symbol: str
    ts: datetime  # bar OPEN time, tz-aware (NY)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    symbol: str
    strategy: str          # version id, e.g. "ict_fvg_sweep@v1"
    side: int              # +1 long, -1 short
    entry: float
    stop: float
    ts: datetime
    reason: str = ""
    features: dict = field(default_factory=dict)
    structural_target: Optional[float] = None
    rr: float = 1.0

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def target(self) -> float:
        return self.entry + self.side * self.risk * self.rr


@dataclass
class Leg:
    qty: float
    price: float
    ts: datetime
    kind: str  # initial | pyramid


@dataclass
class Position:
    symbol: str
    side: int
    strategy: str
    stop: float
    initial_stop: float
    risk_per_unit: float           # |entry - initial stop| in price
    rr: float
    opened_ts: datetime
    legs: list[Leg] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    closed_qty: float = 0.0
    realized: float = 0.0          # currency, net of commissions
    commissions: float = 0.0
    stage: int = 0                 # number of +R steps reached
    adds: int = 0
    partial_done: bool = False
    mfe_r: float = 0.0
    mae_r: float = 0.0
    last_price: float = 0.0
    jev_quality: Optional[float] = None
    jev_confidence: Optional[float] = None
    jev_source: str = ""
    reason: str = ""
    bias_mode: str = ""            # aligned | in_doubt | neutral_reduced | reversal_exception
    risk_mult: float = 1.0
    status: str = "open"
    exit_reason: str = ""
    closed_ts: Optional[datetime] = None
    events: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # broker handles, never serialised

    @property
    def entry(self) -> float:
        return self.legs[0].price if self.legs else 0.0

    @property
    def gross_qty(self) -> float:
        return sum(l.qty for l in self.legs)

    @property
    def open_qty(self) -> float:
        return round(self.gross_qty - self.closed_qty, 6)

    @property
    def avg_entry(self) -> float:
        q = self.gross_qty
        return sum(l.qty * l.price for l in self.legs) / q if q else 0.0

    @property
    def initial_qty(self) -> float:
        return self.legs[0].qty if self.legs else 0.0

    def r_now(self, price: float) -> float:
        return (price - self.entry) * self.side / self.risk_per_unit if self.risk_per_unit else 0.0

    def unrealized(self, price: float, multiplier: float) -> float:
        return (price - self.avg_entry) * self.side * self.open_qty * multiplier

    def log(self, ts: datetime, kind: str, **data: Any) -> None:
        self.events.append({"ts": ts.isoformat(), "kind": kind, **data})

    def to_public(self, multiplier: float) -> dict:
        px = self.last_price or self.entry
        return {
            "id": self.id, "symbol": self.symbol, "side": "LONG" if self.side > 0 else "SHORT",
            "strategy": self.strategy, "qty": self.open_qty, "initial_qty": self.initial_qty,
            "entry": round(self.entry, 4), "avg_entry": round(self.avg_entry, 4),
            "stop": round(self.stop, 4), "initial_stop": round(self.initial_stop, 4),
            "target": round(self.entry + self.side * self.risk_per_unit * self.rr, 4),
            "price": round(px, 4), "r_now": round(self.r_now(px), 2), "stage": self.stage,
            "adds": self.adds, "partial_done": self.partial_done,
            "unrealized": round(self.unrealized(px, multiplier), 2), "realized": round(self.realized, 2),
            "stop_in_profit": (self.stop - self.entry) * self.side > 0,
            "jev_quality": self.jev_quality, "jev_confidence": self.jev_confidence,
            "jev_source": self.jev_source, "opened": self.opened_ts.isoformat(), "reason": self.reason,
            "bias_mode": self.bias_mode, "risk_mult": self.risk_mult,
        }
