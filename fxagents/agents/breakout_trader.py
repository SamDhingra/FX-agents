"""Shadow book `gold_breakout`: Gold Breakout 15M (WillyAlgoTrader) on paper, rules frozen (Oct 2026).

Tested on OANDA bid/ask (fxagents/breakout_test.py): passed on Oct 2024 – Sep 2026 (+0.116R over 500 trades,
95% +0.04 to +0.19) but NOT on the 2021 – Sep 2024 holdout (+0.022R over 960, 95% −0.02 to +0.07). So this book is a
forward record, not a live candidate: does the small effect hold in today's gold market? Virtual fills, no orders.

Rules (the author's defaults, same as the backtest):
  • broker clock fixed GMT+3; range = highest high / lowest low of the 1m mid bars 00:00–06:59 broker time
  • from 07:00 broker: buy stop at the range high, sell stop at the range low, one cancels the other, one trade per
    broker day; a long fills when the ask reaches the range high (at the minute's open if it gaps through)
  • stop 1% of the fill price; no target; flat at 20:00 broker time (17:00 UTC) — the position manager closes it
    on the next bar. No entries at or after 20:00.
  • if the book starts after the day's breakout already happened (restart), that day is skipped, not chased.

Jev (advisory, never gates): at every fill Jev is asked one question — will this breakout follow through in its
direction into the NY afternoon rather than fall back into the range? The answer is stored as the trade's Jev
quality, so `./fx.sh jevcheck` scores it like the other books. Fixed now, before any data: after ≥100 trades a Jev
gate (follow-through ≥ 0.5) is considered only if the trades Jev rated ≥ 0.5 beat the ones below 0.5 with a 95%
day-block range above zero; even then the gated version starts its own forward record.
Config (shadow.gold_breakout): symbols [XAUUSD], risk_pct 0.001, sl_pct 1.0, range_end_hour 7, close_hour 20,
broker_utc_offset 3.
"""
from __future__ import annotations

import pandas as pd

from ..models import Bar, Position
from .core import Agent
from .trading import floor_step, half_spread, qty_rules

STRATEGY = "gold_breakout"


class BreakoutTrader(Agent):
    name = "trader"

    def start(self):
        super().start()
        c = (self.cfg.get("shadow") or {}).get("gold_breakout") or {}
        self.symbols = [s for s in (c.get("symbols") or ["XAUUSD"]) if s in self.cfg["instruments"]]
        self.risk_pct = float(c.get("risk_pct", 0.001))
        self.sl_pct = float(c.get("sl_pct", 1.0))
        self.range_end = int(c.get("range_end_hour", 7)) * 60
        self.close_min = int(c.get("close_hour", 20)) * 60
        self.offset = pd.Timedelta(hours=float(c.get("broker_utc_offset", 3)))
        self.day: dict[str, dict] = {}            # per symbol: broker day, range, done flag
        self.bus.subscribe("bar_1m", self.on_bar)

    # broker clock -----------------------------------------------------------------------------------------------
    def broker(self, ts: pd.Timestamp) -> tuple[pd.Timestamp, int]:
        """Broker day (midnight GMT+3, as a naive date) and minute of that day for a timestamp."""
        b = ts.tz_convert("UTC").tz_localize(None) + self.offset
        return b.normalize(), b.hour * 60 + b.minute

    def day_start_utc(self, bday: pd.Timestamp) -> pd.Timestamp:
        return (bday - self.offset).tz_localize("UTC")

    # main loop --------------------------------------------------------------------------------------------------
    async def on_bar(self, bar: Bar):
        self.beat()
        sym = bar.symbol
        if sym not in self.symbols:
            return
        bday, bmin = self.broker(bar.ts)
        _, end_min = self.broker(bar.ts + pd.Timedelta("1min"))
        self.manage(sym, end_min if end_min > bmin else 24 * 60)
        if bmin < self.range_end or bmin >= self.close_min:
            return
        d = self.day.get(sym)
        if d is None or d["bday"] != bday:
            d = self.day[sym] = self.new_day(sym, bday, bar)
        if d["done"]:
            return
        await self.maybe_enter(sym, d, bar)

    def new_day(self, sym: str, bday: pd.Timestamp, bar: Bar) -> dict:
        """The day's range from the store; marks the day done if there is no usable range, the day was already
        traded (restart), or price already broke out before this bar (restart after the move: don't chase)."""
        d = {"bday": bday, "done": True, "rh": None, "rl": None}
        m1 = self.ctx.store.m1(sym)
        if not len(m1):
            return d
        t0 = self.day_start_utc(bday)
        idx = m1.index.tz_convert("UTC")
        rng = m1[(idx >= t0) & (idx < t0 + pd.Timedelta(minutes=self.range_end))]
        if len(rng) < 60:
            return d
        d["rh"], d["rl"] = float(rng["high"].max()), float(rng["low"].min())
        hs = half_spread(self.cfg, sym)
        before = m1[(idx >= t0 + pd.Timedelta(minutes=self.range_end)) & (m1.index < bar.ts)]
        if len(before) and ((before["high"] + hs >= d["rh"]).any() or (before["low"] - hs <= d["rl"]).any()):
            return d                                            # broke out before we were watching
        if self.traded(sym, t0):
            return d
        d["done"] = False
        return d

    def traded(self, sym: str, since_utc: pd.Timestamp) -> bool:
        if any(p.symbol == sym and p.strategy == STRATEGY and pd.Timestamp(p.opened_ts) >= since_utc
               for p in self.state.positions.values()):
            return True
        rows = getattr(self.ctx.journal, "trades", None)
        if rows is None:
            return False
        try:
            for r in rows(limit=50, status=None):
                if r.get("strategy") == STRATEGY and r.get("symbol") == sym and r.get("opened") \
                        and pd.Timestamp(r["opened"]).tz_convert("UTC") >= since_utc:
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def manage(self, sym: str, end_min: int):
        """Time exit: once the bar ending at/after the close hour is in, the manager closes on the next bar."""
        if end_min < self.close_min:
            return
        for pos in [p for p in self.state.positions.values()
                    if p.symbol == sym and p.status == "open" and p.strategy == STRATEGY]:
            if not pos.meta.get("pending_close"):
                pos.meta["pending_close"] = "close_hour"
                pos.log(self.now(), "exit_signal", why="20:00 broker time (no target)")

    async def maybe_enter(self, sym: str, d: dict, bar: Bar):
        hs = half_spread(self.cfg, sym)
        rh, rl = d["rh"], d["rl"]
        up, dn = bar.high + hs >= rh, bar.low - hs <= rl
        if not (up or dn):
            return
        d["done"] = True                                        # one-cancels-other: the first touch decides the day
        if up and dn:
            side = 1 if (rh - bar.open) <= (bar.open - rl) else -1   # both inside one minute: nearer the open
        else:
            side = 1 if up else -1
        if side > 0:
            fill = max(rh, bar.open + hs)                       # resting buy stop: the ask at the level, or the gap
        else:
            fill = min(rl, bar.open - hs)
        q = float(self.cfg["instruments"][sym]["tick_size"])
        stop = round(fill * (1 - side * self.sl_pct / 100) / q) * q
        rec = {"ts": self.now().isoformat(), "symbol": sym, "strategy": STRATEGY, "side": side, "entry": round(fill, 6),
               "stop": stop, "quality": None, "confidence": None}
        g = await self.jev_follow(sym, side, fill, stop, rh, rl)       # logged only — never gates the trade
        if g:
            rec.update(quality=g.get("prob"), confidence=g.get("confidence"))
        if not self.state.trading_enabled:
            return self._reject(rec, f"trading halted: {self.state.halt_reason}")
        nb = self.ctx.news.blocked(self.now()) if self.ctx.news else None
        if nb:
            return self._reject(rec, f"news blackout: {nb['title']}")
        ic = self.cfg["instruments"][sym]
        mult = float(ic["multiplier"])
        equity = self.state.equity or await self.ctx.broker.equity()
        if not equity or equity <= 0:
            return self._reject(rec, "equity unknown")
        dist = side * (fill - stop)
        step, min_u = qty_rules(ic)
        qty = min(floor_step(equity * self.risk_pct / (dist * mult), step), float(ic["max_units"])) if dist > 0 else 0
        if dist <= 0 or qty < min_u:
            return self._reject(rec, f"{min_u:g} unit(s) exceed the {self.risk_pct:.2%} risk budget")
        pos = Position(sym, side, STRATEGY, stop, stop, dist, 99.0, self.now(),
                       jev_quality=(g or {}).get("prob"), jev_confidence=(g or {}).get("confidence"),
                       jev_source=(g or {}).get("source", "none"),
                       reason=f"Breakout {'above' if side > 0 else 'below'} the 00–07 GMT+3 range "
                              f"{rl:.2f}–{rh:.2f}; stop {self.sl_pct:g}%, flat 20:00 GMT+3",
                       bias_mode="n/a")
        pos.meta.update(external_mgmt=True, no_pyramid=True, max_hold=10 ** 6, range_high=round(rh, 4),
                        range_low=round(rl, 4), trigger=round(rh if side > 0 else rl, 4),
                        jev_follow=(g or {}).get("prob"))
        px = await self.ctx.broker.open(pos, qty, fill - side * hs)     # the broker adds the half-spread back
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.last_price = px
        pos.log(self.now(), "entry", price=px, qty=qty, stop=stop, risk_ccy=round(qty * pos.risk_per_unit * mult, 2),
                jev=(g or {}).get("prob"))
        self.state.positions[pos.id] = pos
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}, jev follow {(g or {}).get('prob')}"})
        await self.bus.publish("position_opened", pos)

    async def jev_follow(self, sym, side, entry, stop, rh, rl) -> dict | None:
        """Jev's read of follow-through, for the record. Any failure → None; the trade goes ahead regardless."""
        jev = getattr(self.ctx, "jev", None)
        if jev is None or not hasattr(jev, "breakout_follow"):
            return None
        bias = self.state.bias.get(sym, {})
        try:
            b15 = self.ctx.store.tf(sym, "15min").iloc[-40:]
            bars = b15[["open", "high", "low", "close"]].round(2).values.tolist()
        except Exception:  # noqa: BLE001
            bars = []
        info = {"symbol": sym, "strategy": STRATEGY, "side": "LONG" if side > 0 else "SHORT", "entry": round(entry, 4),
                "stop": stop, "range_high": round(rh, 4), "range_low": round(rl, 4),
                "range_width": round(rh - rl, 4), "time_ny": str(self.now()),
                "htf_bias": 1 if bias.get("score", 0) > 0 else -1 if bias.get("score", 0) < 0 else 0,
                "htf_detail": {k: bias.get(k) for k in ("label", "score", "d", "h4", "h1", "pd_pos", "pdh", "pdl")},
                "recent_15m_ohlc": bars,
                "plan": "no target; held until 20:00 GMT+3 (17:00 UTC) unless the 1% stop is hit"}
        try:
            return await jev.breakout_follow(info)
        except Exception as e:  # noqa: BLE001
            self.log.warning("gold_breakout: Jev read failed for %s: %s", sym, e)
            return None

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("gold_breakout: no trade %s: %s", rec["symbol"], why)
