"""Playbook selection mode: trade the research-selected cells (setup × instrument × timeframe × exit).

PlaybookHolder  the current playbook (cells → strategy objects), swapped atomically on refresh
PlaybookAgent   keeps it current: live → re-selects as of today and re-runs the research grid when the
                history cache is newer (weekly, low priority); replay → re-selects every Monday as of that
                day from trades strictly before it, so a replay never sees its own future
PlaybookTrader  on each bar close, scans the cells for that symbol/timeframe, applies the hard bias rule,
                instrument capacity (gold up to 2 positions; one index position at a time; SPX watch-only),
                picks the highest-probability cell, asks Jev for a grade (advisory → size) and hands the
                entry to Risk with the cell's exit profile.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from .. import structure as sx
from .. import playbook as pbk
from ..models import Signal
from ..strategies import build_strategy
from .core import Agent
from .trading import TraderAgent, jev_gate, jev_gate_why

log = logging.getLogger("playbook")
PEERS = {"NDQ": ["US30", "SPX"], "US30": ["NDQ", "SPX"], "SPX": ["NDQ", "US30"]}


class Cell:
    def __init__(self, d: dict) -> None:
        self.d = d
        self.sym, self.tf, self.mgmt = d["sym"], d["tf"], d.get("mgmt", "std")
        self.p, self.e = float(d.get("p", 0.5)), float(d.get("e", 0.0))
        self.st = build_strategy({"class": d["setup"], "tf": d["tf"], "params": d.get("params") or {},
                                  "version": d["id"].split("@", 1)[1], "origin": "playbook", "status": "live"})
        self.id = self.st.id


class PlaybookHolder:
    def __init__(self) -> None:
        self.data: dict = {"cells": []}
        self.cells: dict[tuple[str, str], list[Cell]] = {}
        self.policy: pbk.Policy = pbk.Policy()
        self.source = "none"

    def load(self, data: dict, policy: pbk.Policy, source: str) -> None:
        cells: dict[tuple[str, str], list[Cell]] = {}
        for c in data.get("cells", []):
            try:
                cell = Cell(c)
            except Exception as e:  # noqa: BLE001  a bad cell never takes the book down
                log.warning("playbook cell %s skipped: %s", c.get("id"), e)
                continue
            cells.setdefault((cell.sym, cell.tf), []).append(cell)
        self.data, self.cells, self.policy, self.source = data, cells, policy, source

    def for_bar(self, sym: str, tf: str) -> list[Cell]:
        return self.cells.get((sym, tf), [])

    def tfs(self) -> list[str]:
        return sorted({tf for _, tf in self.cells}, key=lambda t: pd.Timedelta(t))

    def summary(self) -> dict:
        return {"source": self.source, "asof": self.data.get("asof"), "created": self.data.get("created"),
                "cells": self.data.get("cells", []), "validation": self.data.get("validation"),
                "policy": self.policy.to_json()}


class PlaybookAgent(Agent):
    """Keeps ctx.playbook current."""
    name = "playbook"

    def __init__(self, ctx, holder: PlaybookHolder) -> None:
        super().__init__(ctx)
        self.holder = holder
        self.replay = bool(ctx.cfg.get("replay"))
        self.last_sel_day = None
        self.refreshing = False
        self.last_check = None
        self.loaded_mtime = None
        self.last_poll = None

    def start(self):
        super().start()
        self.bus.subscribe("clock", self.on_clock)
        self.select(self.now())

    def select(self, now) -> None:
        pol = pbk.policy_from_cfg(self.cfg)
        day = (now + pd.Timedelta(hours=7)).normalize().date() if now is not None else None
        if self.replay or not pbk.playbook_path(self.cfg).exists():
            data = pbk.select_asof(self.cfg, day, pol) if day is not None else {"cells": []}
            src = "as-of selection"
        else:
            path = pbk.playbook_path(self.cfg)
            self.loaded_mtime = path.stat().st_mtime
            data = json.loads(path.read_text())
            src = "playbook.json"
        self.holder.load(data, pol, src)
        self.last_sel_day = day
        log.info("playbook %s (%s): %d cells — %s", data.get("asof"), src, len(data.get("cells", [])),
                 ", ".join(c["id"] + "/" + c["sym"] for c in data.get("cells", [])) or "none")

    async def on_clock(self, now):
        self.beat()
        day = (now + pd.Timedelta(hours=7)).normalize().date()
        if self.replay:
            # weekly re-selection, Monday's session (the trading day that starts Sunday 17:00)
            if day != self.last_sel_day and pd.Timestamp(day).dayofweek == 0:
                self.select(now)
            return
        # live: a new playbook.json (./fx.sh research, or the refresh below) is picked up within ~5 minutes
        if self.last_poll is None or now - self.last_poll >= pd.Timedelta("5min"):
            self.last_poll = now
            path = pbk.playbook_path(self.cfg)
            if path.exists() and path.stat().st_mtime != self.loaded_mtime and not self.refreshing:
                self.select(now)
        # once a day after the CME open, rebuild if the history cache is newer than the research
        if now.hour == 17 and now.minute >= 30 and self.last_check != day and not self.refreshing:
            self.last_check = day
            if self.stale():
                asyncio.ensure_future(self.refresh())

    def stale(self) -> bool:
        from ..setup_map import history_dir
        t = pbk.trades_path(self.cfg)
        if not t.exists():
            return True
        hist = [p.stat().st_mtime for p in Path(history_dir(self.cfg)).glob("*.pkl")]
        return bool(hist) and max(hist) > t.stat().st_mtime

    async def refresh(self) -> None:
        """Re-run the research grid on the (newer) history cache in a low-priority subprocess, then
        reload. The live bot keeps trading the current playbook meanwhile."""
        self.refreshing = True
        try:
            tfs = [str(t) for t in pbk.policy_from_cfg(self.cfg).tfs]
            cmd = ["nice", "-n", "15", sys.executable, "run_research.py", "--workers", "1", "--tfs", *tfs]
            log.info("playbook refresh: %s", " ".join(cmd))
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.PIPE)
            _, err = await proc.communicate()
            if proc.returncode != 0:
                log.warning("playbook refresh failed: %s", (err or b"").decode()[-400:])
                return
            self.select(self.now())
            await self.bus.publish("alert", {"msg": f"Playbook refreshed: {len(self.holder.data.get('cells', []))} cells",
                                             "event": "promotion", "title": "Playbook"})
        finally:
            self.refreshing = False


class PlaybookTrader(TraderAgent):
    name = "trader"

    def start(self):
        super().start()
        self.window = 700

    @property
    def holder(self) -> PlaybookHolder:
        return getattr(self.ctx, "playbook", None) or PlaybookHolder()

    def capacity_block(self, sym: str, cell: Cell, side: int = 0) -> str | None:
        pol = self.holder.policy
        rule = pol.instruments.get(sym)
        if rule is None or rule.role == "off":
            return f"playbook: {sym} is off"
        open_pos = [p for p in self.state.positions.values() if p.status == "open"]
        if len(open_pos) >= min(pol.max_open, int(self.cfg["risk"]["max_open_positions"])):
            return "playbook: max open positions"
        if sum(p.symbol == sym for p in open_pos) >= rule.max_positions:
            return f"playbook: {sym} already has {rule.max_positions} position(s)"
        if any(p.strategy == cell.id for p in open_pos):
            return "playbook: this cell already has a position"
        if side and any(p.symbol == sym and p.side != side for p in open_pos):
            return f"playbook: {sym} has an opposite position (OANDA nets positions per instrument)"
        grp = set(pol.index_group)
        if sym in grp and sum(p.symbol in grp for p in open_pos) >= pol.index_group_max:
            return "playbook: one index position at a time"
        return None

    def peers(self, sym: str, tf: str, df: pd.DataFrame) -> list[pd.DataFrame]:
        """Correlated indices for SMT. Bars arrive one instrument at a time, so a peer whose bar for this
        minute isn't stored yet is left out rather than forward-filled from the previous bar."""
        out = []
        for p in PEERS.get(sym, []):
            if p in self.cfg["instruments"]:
                b = self.ctx.store.tf(p, tf)
                if len(b) and b.index[-1] >= df.index[-1]:
                    out.append(b.reindex(df.index).ffill())
        return out

    async def on_tradingview(self, payload: dict):
        return          # TradingView alerts belong to the strategy book, not the playbook

    async def on_signal_bar(self, ev):
        self.beat()
        sym, tf = ev["symbol"], ev["tf"]
        cells = self.holder.for_bar(sym, tf)
        if not cells:
            return
        if self.cfg["mode"] != "sim" and self.now() is not None and self.now() - ev["ts"] > pd.Timedelta("5min"):
            return
        df = self.ctx.store.tf(sym, tf).iloc[-self.window:]
        if len(df) < 120:
            return
        ctx = self.bar_context(sym, tf, df)
        if any(c.st.params.get("vol", "any") not in (None, "any") for c in cells) and \
                len(ctx.get("rvol", ())) != len(df):
            # relative volume needs ~5 prior days of the same time-of-day bars: use the whole stored history
            full = self.ctx.store.tf(sym, tf)
            ctx["rvol"] = sx.rvol_tod(full)[-len(df):]
        if any(c.st.needs_peers for c in cells) and getattr(self.ctx, "oracle", None) is None:
            ctx.setdefault("peers", self.peers(sym, tf, df))
        cands = []
        for cell in cells:
            for rs in self.last_bar_signals(cell.st, sym, tf, df, ctx):
                sig = Signal(sym, cell.id, rs.side, rs.entry, rs.stop, ev["ts"],
                             f"{rs.reason} · playbook {cell.d['variant']}/{cell.mgmt} p={cell.p:.2f}",
                             rs.features, rs.structural_target, rr=1.0)
                rec = {"ts": sig.ts.isoformat(), "symbol": sym, "strategy": cell.id,
                       "side": "LONG" if sig.side > 0 else "SHORT", "entry": sig.entry, "stop": sig.stop}
                why = self.bias_precheck(sig)
                if why:
                    self.ctx.journal.add_signal(rec | {"action": "filtered", "why": why})
                    continue
                cands.append((cell, sig, rec))
        if not cands:
            return
        cands.sort(key=lambda c: (-c[0].p, -c[0].e))
        taken = False
        for cell, sig, rec in cands:
            if taken:
                self.ctx.journal.add_signal(rec | {"action": "skipped", "why": "a higher-probability playbook cell fired on this bar"})
                continue
            why = self.capacity_block(sym, cell, sig.side)
            if why:
                self.ctx.journal.add_signal(rec | {"action": "skipped", "why": why})
                continue
            g = await self.grade(cell, sig, ctx, df)
            jc = self.cfg["jev"]
            rec = rec | {"quality": g["quality"], "confidence": g["confidence"]}
            if not jev_gate(g, jc):
                self.ctx.journal.add_signal(rec | {"action": "skipped", "why": jev_gate_why(g, jc)})
                continue
            pol = self.holder.policy
            rule = pol.instruments[sym]
            before = {p.id for p in self.state.positions.values()}
            await self.bus.publish("entry_request", {
                "signal": sig, "grade": g, "record": rec,
                "playbook": {"max_per_symbol": rule.max_positions, "mgmt": cell.mgmt,
                             "group": {"members": list(pol.index_group), "max": pol.index_group_max}}})
            taken = any(p.id not in before and p.symbol == sym for p in self.state.positions.values())

    async def grade(self, cell: Cell, sig: Signal, ctx: dict, df: pd.DataFrame) -> dict:
        b = self.state.bias.get(sig.symbol, {})
        info = {"symbol": sig.symbol, "strategy": cell.id, "side": "LONG" if sig.side > 0 else "SHORT",
                "entry": sig.entry, "stop": sig.stop, "target_1r": sig.target, "structural_target": sig.structural_target,
                "reason": sig.reason, "risk_atr": sig.features.get("risk_atr"),
                "htf_bias": 1 if b.get("score", 0) > 0 else -1 if b.get("score", 0) < 0 else 0,
                "htf_detail": {k: b.get(k) for k in ("label", "score", "d", "h4", "h1", "pd_pos", "pdh", "pdl", "state")},
                "news_next_hours": self.ctx.news.brief(self.now(), 3) if self.ctx.news else [],
                "rsi": round(float(ctx["rsi"][-1]), 1) if ctx and "rsi" in ctx else None,
                "strategy_expectancy": cell.d.get("exp_r"), "strategy_win_rate": cell.d.get("win_rate"),
                "playbook_cell": {k: cell.d.get(k) for k in ("n", "win_rate", "p", "exp_r", "mgmt", "variant")},
                "recent_bars": df.iloc[-12:][["open", "high", "low", "close"]].round(4).to_dict("split")["data"],
                "time_ny": str(sig.ts)}
        return await self.ctx.jev.rate_signal(info)
