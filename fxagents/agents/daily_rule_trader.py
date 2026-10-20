"""Shadow book `daily_rsi2_adx2`: Sam's daily RSI(2)/ADX(2) trend rule on paper, rules frozen (Oct 20 2026).

Backtest (btplugins/daily_rsi2_adx2.py, 2021 → Sep 2026, real bid/ask): BTC +0.027R, gold +0.059R, NDQ +0.019R,
US30 −0.023R per trade; random-timing edge +0.012 … +0.057R on the first three, every 95% range including zero.
Not a pass — this book builds the FORWARD record on gold and BTC, unchanged, to be judged on new data.

Rules (identical to the plugin; same indicator code, fxagents/bt/ind.py):
  • daily mid candles closing 17:00 New York (built from the bot's hourly history on the NY wall clock)
  • long entry at a daily close where close > SMA(50), close > EMA(7) and RSI(2) > ADX(2) → bought at the first
    price after the close (gold: the 18:00 reopen; Friday's signal fills Sunday evening). Long only.
  • exit at the first later daily close where RSI(2) < ADX(2) → sold at the next price.
  • protective stop entry − 3 × ATR(14, daily): defines 1R for sizing (risk_pct of equity) and caps a disaster;
    the rule itself has no stop. Held overnight and over weekends (exempt from the 15:50 session flatten).
  • virtual fills pay the configured spread; overnight financing isn't booked by the virtual broker, so each trade
    records its rollovers (meta, events) for the evaluation to subtract (gold ×3 on Wednesdays, BTC every day).
  • restart-safe: open trades are re-adopted from this book's journal when the bot starts.
Config (shadow.daily_rsi2_adx2): symbols [XAUUSD, BTCUSD], risk_pct 0.001, stop_atr 3.0.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..bias import wall_ohlc
from ..broker import OrderRejected
from ..bt import ind
from ..models import Bar, Leg, Position
from .core import Agent
from .trading import floor_step, qty_rules

STRATEGY = "daily_rsi2_adx2"
CRYPTO = ("BTCUSD", "ETHUSD")


def daily_frame(h1: pd.DataFrame, boundary: pd.Timestamp) -> pd.DataFrame:
    """Completed 17:00-NY daily candles up to `boundary`, with the rule's indicators."""
    d = wall_ohlc(h1[["open", "high", "low", "close"]], "24h", offset="17h")
    d = d[d["end"] <= boundary]
    b = pd.DataFrame({"h": d["high"].to_numpy(float), "l": d["low"].to_numpy(float), "c": d["close"].to_numpy(float)},
                     index=d.index)
    b["end"] = d["end"].to_numpy()
    c = b.c.to_numpy()
    b["sma50"], b["ema7"] = ind.sma(c, 50), ind.ema(c, 7)
    b["rsi2"], b["adx2"], b["atr14"] = ind.rsi(c, 2), ind.adx(b, 2), ind.atr(b, 14)
    return b


def rule_state(b: pd.DataFrame) -> dict:
    """Entry / exit at the last completed daily candle."""
    x = b.iloc[-1]
    ok = bool(np.isfinite([x.c, x.sma50, x.ema7, x.rsi2, x.adx2, x.atr14]).all() and x.atr14 > 0)
    return {"ok": ok, "entry": ok and x.c > x.sma50 and x.c > x.ema7 and x.rsi2 > x.adx2,
            "exit": ok and x.rsi2 < x.adx2, "c": float(x.c), "sma50": float(x.sma50), "ema7": float(x.ema7),
            "rsi2": float(x.rsi2), "adx2": float(x.adx2), "atr14": float(x.atr14)}


class DailyRuleTrader(Agent):
    name = "trader"

    def start(self):
        super().start()
        c = (self.cfg.get("shadow") or {}).get(STRATEGY) or {}
        self.symbols = [s for s in (c.get("symbols") or ["XAUUSD", "BTCUSD"]) if s in self.cfg["instruments"]]
        self.risk_pct = float(c.get("risk_pct", 0.001))
        self.stop_atr = float(c.get("stop_atr", 3.0))
        self.min_days = 60
        self.done: dict[str, pd.Timestamp] = {}          # last daily close acted on, per symbol
        self.pending: dict[str, dict] = {}               # entries waiting for the first price after the close
        self.bus.subscribe("bar_1m", self.on_bar)
        self.adopt()

    # ── restart safety ──
    def adopt(self):
        """Re-open this book's still-open trades from its journal (shadow positions live in memory only)."""
        try:
            rows = [r for r in self.ctx.journal.trades(limit=50, status="open") if r.get("strategy") == STRATEGY]
        except Exception as e:  # noqa: BLE001
            self.log.warning("%s: could not read open trades: %s", STRATEGY, e)
            return
        for r in rows:
            if r["symbol"] not in self.symbols or any(p.id == r["id"] for p in self.state.positions.values()):
                continue
            side = 1 if r["side"] == "LONG" else -1
            opened = pd.Timestamp(r["opened"])
            pos = Position(r["symbol"], side, STRATEGY, float(r["final_stop"]), float(r["initial_stop"]),
                           abs(float(r["entry"]) - float(r["initial_stop"])), 99.0, opened, id=r["id"],
                           reason=r.get("reason") or "", bias_mode="n/a")
            pos.add_leg(Leg(float(r["qty_initial"]), float(r["entry"]), opened, "initial"))
            try:
                pos.events = json.loads(r.get("events") or "[]")
            except ValueError:
                pos.events = []
            pos.meta.update(external_mgmt=True, no_pyramid=True, hold_overnight=True, max_hold=10 ** 9,
                            rollovers=sum(e.get("n", 0) for e in pos.events if e.get("kind") == "rollover"))
            pos.mfe_r, pos.mae_r = float(r.get("mfe_r") or 0), float(r.get("mae_r") or 0)
            pos.last_price = float(r["entry"])
            pos.log(self.now(), "readopted", why="bot restarted; trade restored from the journal")
            self.state.positions[pos.id] = pos
            getattr(self.ctx.broker, "open_positions", {})[pos.id] = pos
            self.log.info("%s: re-adopted open %s trade %s from %s", STRATEGY, pos.symbol, pos.id, r["opened"])

    # ── the daily clock ──
    async def on_bar(self, bar: Bar):
        self.beat()
        sym = bar.symbol
        if sym not in self.symbols:
            return
        t = bar.ts + pd.Timedelta("1min")                                 # this bar's close
        if sym in self.pending and bar.ts >= self.pending[sym]["boundary"]:
            await self.enter(sym, self.pending.pop(sym), bar)
        loc = t.tz_convert(self.cfg["timezone"])
        boundary = loc.normalize() + pd.Timedelta(hours=17)
        if loc < boundary:
            boundary -= pd.Timedelta(days=1)
        if self.done.get(sym) is not None and boundary <= self.done[sym]:
            return
        if t - boundary > pd.Timedelta("150min"):                          # started (or came back) long after it
            self.done[sym] = boundary
            return
        if t < boundary:
            return
        self.done[sym] = boundary
        await self.on_daily_close(sym, boundary)

    async def on_daily_close(self, sym: str, boundary: pd.Timestamp):
        mine = [p for p in self.state.positions.values() if p.symbol == sym and p.status == "open" and p.strategy == STRATEGY]
        for p in mine:                                                    # a 17:00 crossing while held = one rollover
            n = 1 if sym in CRYPTO else (3 if boundary.dayofweek == 2 else 1)
            if boundary.dayofweek < 5 or sym in CRYPTO:
                p.meta["rollovers"] = p.meta.get("rollovers", 0) + n
                p.log(self.now(), "rollover", n=n, total=p.meta["rollovers"])
                await self.bus.publish("position_updated", {"position": p, "event": "rollover",
                                                            "msg": f"held over the 17:00 roll ({p.meta['rollovers']} so far)"})
        b = daily_frame(self.ctx.store.h1(sym), boundary)
        if len(b) < self.min_days or b["end"].iloc[-1] != boundary:
            if len(b) < self.min_days:
                self.log.warning("%s %s: only %d daily candles (need %d) — raise timeframes.h1_history_days",
                                 STRATEGY, sym, len(b), self.min_days)
            return
        st = rule_state(b)
        for p in mine:
            if st["exit"] and not p.meta.get("pending_close"):
                p.meta["pending_close"] = "rsi2_below_adx2"
                p.log(self.now(), "exit_signal", rsi2=round(st["rsi2"], 1), adx2=round(st["adx2"], 1), close=st["c"])
        if st["entry"] and not mine and sym not in self.pending:
            self.pending[sym] = {"boundary": boundary, **st}
            self.log.info("%s %s: entry signal at the %s close (RSI2 %.1f > ADX2 %.1f) — buying at the next price",
                          STRATEGY, sym, boundary.strftime("%a %d %b"), st["rsi2"], st["adx2"])

    async def enter(self, sym: str, st: dict, bar: Bar):
        rec = {"ts": self.now().isoformat(), "symbol": sym, "strategy": STRATEGY, "side": 1, "entry": round(bar.open, 6),
               "stop": None, "quality": None, "confidence": None}
        if not self.state.trading_enabled:
            return self._reject(rec, f"trading halted: {self.state.halt_reason}")
        ic = self.cfg["instruments"][sym]
        q = float(ic["tick_size"])
        stop = round((st["c"] - self.stop_atr * st["atr14"]) / q) * q
        rec["stop"] = stop
        equity = self.state.equity or await self.ctx.broker.equity()
        if not equity or equity <= 0:
            return self._reject(rec, "equity unknown")
        dist = bar.open - stop
        step, min_u = qty_rules(ic)
        qty = min(floor_step(equity * self.risk_pct / (dist * float(ic["multiplier"])), step), float(ic["max_units"])) \
            if dist > 0 else 0.0
        if qty < min_u:
            return self._reject(rec, f"{min_u:g} unit(s) exceed the {self.risk_pct:.2%} risk budget" if dist > 0
                                else "price already below the protective stop")
        pos = Position(sym, 1, STRATEGY, stop, stop, dist, 99.0, self.now(), jev_source="none", bias_mode="n/a",
                       reason=f"daily close {st['c']:.2f} > SMA50 {st['sma50']:.2f} and EMA7 {st['ema7']:.2f}, "
                              f"RSI(2) {st['rsi2']:.1f} > ADX(2) {st['adx2']:.1f}")
        pos.meta.update(external_mgmt=True, no_pyramid=True, hold_overnight=True, max_hold=10 ** 9, rollovers=0,
                        signal_close=st["c"], atr14=round(st["atr14"], 4))
        try:
            px = await self.ctx.broker.open(pos, qty, bar.open)
        except OrderRejected as e:                          # e.g. the 10%-of-price stop guard on a wild BTC day
            return self._reject(rec, f"broker guard: {e}")
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.last_price = px
        pos.log(self.now(), "entry", price=px, qty=qty, stop=stop,
                risk_ccy=round(qty * pos.risk_per_unit * float(ic["multiplier"]), 2))
        self.state.positions[pos.id] = pos
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}"})
        await self.bus.publish("position_opened", pos)

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("%s: no trade %s: %s", STRATEGY, rec["symbol"], why)
