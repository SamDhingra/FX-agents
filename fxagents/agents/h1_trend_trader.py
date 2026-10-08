"""Shadow book `h1_vol_trend`: ASTRA-H1-VOL-TREND-CFD-001 v0.1.0 traded on paper, rules frozen.

The only idea from the Oct 2026 audit tests that was positive in both the year it was designed against
and the unseen year before (+0.07R/trade over 103 trades, not significant). It runs as its own shadow
book to build a forward record — virtual fills, no orders sent, nothing tuned.

Same decision code as the backtest (fxagents/astra_cfd.py: H1Ind, h1_initial_stop, h1_trail):
  • decisions on completed hourly bars closing 09:00, 10:00, 11:00, 12:00, 13:00 New York; the FIRST
    qualifying hour is the day's only opportunity (taken or not); no trades on FOMC days / holidays
  • entry at the next price; stop 2×ATR14(1h) from entry; cost gate (spread + 2·slippage) ≤ 10% of the stop
  • no target; after a completed hourly close ≥ +1R the stop trails 2×ATR behind the best hourly close,
    updated only on hourly closes; a new stop already through the market closes the trade
  • flat at the session flatten (the position manager's time exit); constant risk (`risk_pct` of equity),
    no Jev, no bias rule, no adds
Config (shadow.h1_vol_trend): symbols [XAUUSD], risk_pct 0.001.
"""
from __future__ import annotations

import pandas as pd

from ..astra_cfd import COST_GATE, FOMC, HOLIDAYS, EARLY_CLOSE, H1Ind, h1_initial_stop, h1_trail
from ..models import Bar, Position
from .core import Agent
from .trading import floor_step, half_spread, qty_rules

STRATEGY = "astra_h1_vol_trend"
DECISION_HOURS = (9, 10, 11, 12, 13)


class H1VolTrendTrader(Agent):
    name = "trader"

    def start(self):
        super().start()
        c = (self.cfg.get("shadow") or {}).get("h1_vol_trend") or {}
        self.symbols = [s for s in (c.get("symbols") or ["XAUUSD"]) if s in self.cfg["instruments"]]
        self.risk_pct = float(c.get("risk_pct", 0.001))
        self.done_day: dict[str, str] = {}          # symbol → trading date whose opportunity is used up
        self.last_hour: dict[str, pd.Timestamp] = {}
        self.trail: dict[str, dict] = {}            # position id → trailing state (best close, armed)
        self.bus.subscribe("bar_1m", self.on_bar)

    def _h1(self, sym: str, upto: pd.Timestamp) -> pd.DataFrame:
        """Completed hourly bars ending at or before `upto`."""
        h1 = self.ctx.store.h1(sym)
        return h1[h1.index + pd.Timedelta("1h") <= upto]

    async def on_bar(self, bar: Bar):
        self.beat()
        sym = bar.symbol
        if sym not in self.symbols:
            return
        boundary = (bar.ts + pd.Timedelta("1min")).floor("h")
        if self.last_hour.get(sym) is not None and boundary <= self.last_hour[sym]:
            return
        if bar.ts + pd.Timedelta("1min") - boundary > pd.Timedelta("5min"):
            self.last_hour[sym] = boundary           # too late after the hour (outage): skip, don't act on stale bars
            return
        self.last_hour[sym] = boundary
        h1 = self._h1(sym, boundary)
        if len(h1) < 151 or h1.index[-1] + pd.Timedelta("1h") != boundary:
            return
        ind = H1Ind(h1)
        await self.manage(sym, ind, bar)
        await self.maybe_enter(sym, ind, boundary, bar)

    async def manage(self, sym: str, ind: H1Ind, bar: Bar):
        q = float(self.cfg["instruments"][sym]["tick_size"])
        for pos in [p for p in self.state.positions.values() if p.symbol == sym and p.status == "open" and p.strategy == STRATEGY]:
            st = self.trail.setdefault(pos.id, {})
            t = len(ind.C) - 1
            if pd.Timestamp(pos.opened_ts).floor("min") > self.last_hour[sym] - pd.Timedelta("1h"):
                continue                              # this hourly bar began before the entry minute
            ns = h1_trail(st, ind.C[t], ind.A[t], pos.entry, pos.risk_per_unit, pos.side, q)
            if ns is None or (ns - pos.stop) * pos.side <= 0:
                continue
            px = self.state.last_prices.get(sym, bar.close) - pos.side * half_spread(self.cfg, sym)
            if (px - ns) * pos.side <= 0:
                pos.meta["pending_close"] = "trail_through"   # the manager closes it on the next bar
                pos.log(self.now(), "trail_through", stop=ns)
                continue
            await self.ctx.broker.move_stop(pos, ns)
            pos.log(self.now(), "stop_moved", stop=pos.stop, why="2×ATR trail on hourly close")
            await self.bus.publish("position_updated", {"position": pos, "event": "stop_to_profit",
                                                        "msg": f"trail → {pos.stop} (locks {pos.r_now(pos.stop):+.2f}R)"})

    async def maybe_enter(self, sym: str, ind: H1Ind, boundary: pd.Timestamp, bar: Bar):
        day = boundary.strftime("%Y-%m-%d")
        if boundary.hour not in DECISION_HOURS or boundary.minute or boundary.dayofweek >= 5:
            return
        if day in FOMC or day in HOLIDAYS or day in EARLY_CLOSE or self.done_day.get(sym) == day:
            return
        if any(p.symbol == sym and p.status == "open" and p.strategy == STRATEGY for p in self.state.positions.values()):
            return
        q = float(self.cfg["instruments"][sym]["tick_size"])
        t = len(ind.C) - 1
        side = ind.side(t, q)
        if side == 0:
            return
        self.done_day[sym] = day                      # first qualifying hour = the day's only opportunity
        rec = {"ts": self.now().isoformat(), "symbol": sym, "strategy": STRATEGY, "side": side,
               "entry": bar.close, "stop": None, "quality": None, "confidence": None}
        if not self.state.trading_enabled:
            return self._reject(rec, f"trading halted: {self.state.halt_reason}")
        nb = self.ctx.news.blocked(self.now()) if self.ctx.news else None
        if nb:
            return self._reject(rec, f"news blackout: {nb['title']}")
        mid = self.state.last_prices.get(sym, bar.close)
        hs = half_spread(self.cfg, sym)
        E0 = mid + side * hs
        stop = h1_initial_stop(E0, float(ind.A[t]), side, q)
        dist = abs(E0 - stop)
        rec.update(entry=round(E0, 6), stop=stop)
        slip = max(q, 0.5 * hs)                       # the spec's slippage, max(tick, ¼ spread)
        if dist <= 0 or (2 * hs + 2 * slip) / dist > COST_GATE:
            return self._reject(rec, f"cost gate: costs {(2*hs+2*slip)/max(dist,1e-9):.0%} of the stop > {COST_GATE:.0%}")
        ic = self.cfg["instruments"][sym]
        mult = float(ic["multiplier"])
        equity = self.state.equity or await self.ctx.broker.equity()
        if not equity or equity <= 0:
            return self._reject(rec, "equity unknown")
        step, min_u = qty_rules(ic)
        qty = min(floor_step(equity * self.risk_pct / (dist * mult), step), float(ic["max_units"]))
        if qty < min_u:
            return self._reject(rec, f"{min_u:g} unit(s) exceed the {self.risk_pct:.2%} risk budget")
        pos = Position(sym, side, STRATEGY, stop, stop, dist, 99.0, self.now(), jev_source="none",
                       reason=f"H1-VOL-TREND {'long' if side > 0 else 'short'}: 12-bar breakout, EMA32/128 trend, "
                              f"ER24 ≥ 0.30, normal ATR", bias_mode="n/a")
        pos.meta.update(external_mgmt=True, no_pyramid=True, max_hold=10 ** 6)
        px = await self.ctx.broker.open(pos, qty, mid)
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.last_price = px
        pos.log(self.now(), "entry", price=px, qty=qty, stop=stop, risk_ccy=round(qty * pos.risk_per_unit * mult, 2))
        self.state.positions[pos.id] = pos
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}, risk ${qty * pos.risk_per_unit * mult:,.0f}"})
        await self.bus.publish("position_opened", pos)

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("h1_vol_trend: no trade %s: %s", rec["symbol"], why)

