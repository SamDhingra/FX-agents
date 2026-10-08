"""Shared, read-mostly live state. Agents write their slice; the dashboard reads a snapshot."""
from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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
    trading_day: str = ""                       # NY trading date (rolls at 17:00) that day_start_equity belongs to
    entries_blocked: str = ""                   # set by the flatten supervisor near the session end
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
    bias: dict[str, dict] = field(default_factory=dict)              # symbol -> multi-TF bias + safeguards
    news: list[dict] = field(default_factory=list)                   # upcoming events
    news_source: str = ""
    news_block: dict | None = None

    def beat(self, agent: str) -> None:
        self.heartbeats[agent] = time.time()

    def alert(self, level: str, msg: str, **extra: Any) -> dict:
        a = {"ts": (self.now or datetime.now()).isoformat(timespec="seconds"), "level": level, "msg": msg, **extra}
        self.alerts.appendleft(a)
        return a


# ── restart persistence (paper/live) ─────────────────────────────────────────
RUNTIME_FILE = "runtime_state.json"
STARTUP_HALT = "startup: reconciling with the broker"


def trading_day(ts) -> str:
    """NY trading date; the day rolls at 17:00 New York."""
    import pandas as pd
    return str((pd.Timestamp(ts) + pd.Timedelta(hours=7)).date())


def pos_to_dict(p) -> dict:
    from dataclasses import fields
    d = {f.name: getattr(p, f.name) for f in fields(p) if f.name not in ("legs", "meta", "events")}
    d["legs"] = [{"qty": l.qty, "price": l.price, "ts": l.ts, "kind": l.kind} for l in p.legs]
    meta = {}
    for k, v in p.meta.items():          # broker handles that aren't plain data (IBKR order objects) are skipped
        try:
            json.dumps(v)
            meta[k] = v
        except (TypeError, ValueError):
            pass
    d["meta"], d["events"] = meta, p.events[-100:]
    return json.loads(json.dumps(d, default=lambda x: x.isoformat() if hasattr(x, "isoformat") else str(x)))


def pos_from_dict(d: dict):
    import pandas as pd
    from .models import Leg, Position
    d = dict(d)
    legs = [Leg(l["qty"], l["price"], pd.Timestamp(l["ts"]), l["kind"]) for l in d.pop("legs", [])]
    for k in ("opened_ts", "closed_ts"):
        d[k] = pd.Timestamp(d[k]) if d.get(k) else None
    p = Position(**d)
    p.legs = legs
    return p


class RuntimeStore:
    """runtime_state.json next to the journal DB: what a restart must not forget — the halt flag and reason,
    the day's starting equity (with its trading date), the equity peak, today's realized P&L, and every open
    position with its broker trade ids and booked quantities."""

    def __init__(self, path) -> None:
        self.path = Path(path)

    @classmethod
    def for_cfg(cls, cfg) -> "RuntimeStore":
        return cls(Path(cfg["storage"]["db_path"]).parent / RUNTIME_FILE)

    def save(self, st: LiveState) -> None:
        enabled, reason = st.trading_enabled, st.halt_reason
        if reason == STARTUP_HALT:       # never persist the transient startup gate as a real halt
            enabled, reason = True, ""
        d = {"saved": datetime.now().isoformat(timespec="seconds"), "trading_enabled": enabled, "halt_reason": reason,
             "trading_day": st.trading_day, "day_start_equity": st.day_start_equity, "equity_peak": st.equity_peak,
             "realized_today": st.realized_today,
             "positions": [pos_to_dict(p) for p in st.positions.values() if p.status == "open"]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.path)

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    def restore(self, st: LiveState, now) -> tuple[str, list]:
        """Put the saved risk baseline back into `st`. Returns (halt reason to keep, saved open positions).
        A halt is kept if it was set on the same trading day; a max-drawdown halt is kept whatever the day
        (it waits for you, as it would have without the restart)."""
        d = self.load()
        if not d:
            return "", []
        today = trading_day(now)
        st.equity_peak = max(st.equity_peak or 0.0, float(d.get("equity_peak") or 0.0))
        if d.get("trading_day") == today:
            st.trading_day = today
            st.day_start_equity = float(d.get("day_start_equity") or st.day_start_equity)
            st.realized_today = float(d.get("realized_today") or 0.0)
        halt = "" if d.get("trading_enabled", True) else (d.get("halt_reason") or "halted before the restart")
        if halt and not (d.get("trading_day") == today or halt.startswith("max drawdown")):
            halt = ""
        return halt, [pos_from_dict(x) for x in d.get("positions", [])]


async def startup_reconcile(st: LiveState, broker, store: RuntimeStore, now) -> dict:
    """Run once at startup with every agent subscribed. Entries stay disabled (STARTUP_HALT) until this has
    finished: saved positions whose broker trades are still open are managed again, anything the broker
    closed meanwhile is booked and journaled (stop_filled → position manager), and a same-day halt is restored."""
    halt, saved = store.restore(st, now)
    for p in saved:
        st.positions[p.id] = p
    adopted = bool(saved) and await broker.adopt(saved)
    if saved and not adopted:          # this broker can't re-attach (IBKR): the monitor's orphan check takes over
        for p in saved:
            st.positions.pop(p.id, None)
    st.trading_enabled, st.halt_reason = (False, halt) if halt else (True, "")
    store.save(st)
    return {"halt": halt, "saved": len(saved), "adopted": adopted,
            "open": [p.id for p in st.positions.values() if p.status == "open"]}
