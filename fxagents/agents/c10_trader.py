"""Shadow book `c10_afternoon`: ChatGPT's C10 v2 "morning-to-afternoon continuation" on NDQ, rules frozen (Oct 20 2026).

Backtest (btplugins/gpt_c10_afternoon_continuation_v2.py, real 1-minute bid/ask): 2021 → Sep 2026 NDQ 251 trades,
+0.258R per trade (95% +0.115 … +0.410), passed every gate; the untouched 2016–2020 vault: 141 trades, +0.082R
(95% −0.123 … +0.295) — positive in both halves and at 2× costs but NOT significant. So: a forward record on paper.

Rules (identical to the plugin; same indicator code, fxagents/bt/ind.py), 15-minute mid candles, New York time:
  • at 13:00: r10 = 10:00 close − previous trading day's 16:00 close (its 15:45 candle), r13 = 13:00 close − that
    same close. Same sign required. The move from today's 09:30 open to the 13:00 close is ≥ 1 ATR(14, 15m) that way,
    and the efficiency ratio ER(12) ≥ 0.40. All fourteen 09:30–12:45 candles must be there.
  • enter that way at the next price; stop 1.25 ATR from the 13:00 close; target 2R from the fill; out at 15:45.
  • skipped when 1.3 × spread > 10% of the stop (the configured spread), or the stop isn't 0.5–2.5 ATR / ≤ 10% of price.
  • one trade a day, no news blackout (the test had none), no adds, no breakeven, no trailing.
Config (shadow.c10_afternoon): symbols [NDQ], risk_pct 0.001.

On the practice account too (Oct 21 2026, `c10_account.enabled`): the same frozen rules send real OANDA orders, at
`c10_account.risk_pct` (0.25% — half the normal risk, because the 2016–2020 result was not significant). There it
also respects the account's limits: trading halted / entries blocked, max open positions, one position per symbol,
the one-index-per-direction cap and the margin budget. Its 2R target rests at OANDA (audit F5). The paper book keeps
running unchanged, so the frozen forward record continues. After a restart the account's runtime state restores the
position (the paper book re-adopts from its journal).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..broker import OrderRejected
from ..bt import ind
from ..models import Bar, Leg, Position
from .core import Agent
from .trading import floor_step, half_spread, margin_in_use, margin_per_unit, qty_rules

STRATEGY = "c10_afternoon"
P = {"move_atr": 1.0, "er_n": 12, "er_min": 0.40, "stop_atr": 1.25, "target_r": 2.0, "spread_frac": 0.10 / 1.3}
ENTRY_MOD, EXIT_MOD = 780, 945            # 13:00 entry, 15:45 exit (NY minutes)


def c10_signal(df15: pd.DataFrame, tz: str) -> dict | None:
    """The rule at the last candle of `df15` (completed 15m mid candles, index = candle start). That candle must be
    the 12:45 one. Returns {side, close, atr, er, ...} or None."""
    if len(df15) < 120:
        return None
    t = df15.index.tz_convert(tz)
    mod = t.hour * 60 + t.minute
    day = np.asarray([d.toordinal() for d in t.date])
    if mod[-1] != ENTRY_MOD - 15 or t[-1].dayofweek >= 5:
        return None
    b = pd.DataFrame({"h": df15["high"].to_numpy(float), "l": df15["low"].to_numpy(float),
                      "c": df15["close"].to_numpy(float)})
    o, c = df15["open"].to_numpy(float), b.c.to_numpy()
    a = ind.atr(b, 14)
    er = ind.efficiency_ratio(c, P["er_n"])
    today = day[-1]
    pos = {(d, x): i for i, (d, x) in enumerate(zip(day, mod))}
    prior = sorted({int(d) for d, w in zip(day, t.dayofweek) if w < 5 and d < today and (d, 945) in pos})
    if not prior:
        return None
    ip, i0, i10, i13 = pos[(prior[-1], 945)], pos.get((today, 570)), pos.get((today, 585)), len(df15) - 1
    if i0 is None or i10 is None or i13 - i0 != 13 or not (np.isfinite(a[i13]) and np.isfinite(er[i13])):
        return None
    r10, r13 = c[i10] - c[ip], c[i13] - c[ip]
    if r10 == 0 or np.sign(r10) != np.sign(r13):
        return None
    side = 1 if r13 > 0 else -1
    if side * (c[i13] - o[i0]) < P["move_atr"] * a[i13] or er[i13] < P["er_min"]:
        return None
    return {"side": side, "close": float(c[i13]), "atr": float(a[i13]), "er": float(er[i13]),
            "prev_close": float(c[ip]), "open_0930": float(o[i0]), "close_1000": float(c[i10])}


class C10Trader(Agent):
    name = "trader"

    def __init__(self, ctx, on_account: bool = False):
        super().__init__(ctx)
        self.on_account = on_account
        if on_account:
            self.name = "c10_trader"                  # the account already has a "trader"
            self.log = __import__("logging").getLogger(self.name)

    def start(self):
        super().start()
        c = (self.cfg.get("c10_account") if self.on_account else (self.cfg.get("shadow") or {}).get(STRATEGY)) or {}
        self.symbols = [s for s in (c.get("symbols") or ["NDQ"]) if s in self.cfg["instruments"]]
        self.risk_pct = float(c.get("risk_pct", 0.001))
        self.tz = self.cfg["timezone"]
        self.done: dict[str, object] = {}                 # NY date of the last 13:00 decision, per symbol
        self.bus.subscribe("bar_1m", self.on_bar)
        if not self.on_account:
            self.adopt()                                   # the account's runtime state restores its own positions

    def adopt(self):
        """Re-open today's still-open trade from the journal after a restart (shadow positions live in memory only)."""
        try:
            rows = [r for r in self.ctx.journal.trades(limit=20, status="open") if r.get("strategy") == STRATEGY]
        except Exception as e:  # noqa: BLE001
            self.log.warning("%s: could not read open trades: %s", STRATEGY, e)
            return
        for r in rows:
            if r["symbol"] not in self.symbols or any(p.id == r["id"] for p in self.state.positions.values()):
                continue
            side = 1 if r["side"] == "LONG" else -1
            opened = pd.Timestamp(r["opened"])
            entry, stop0 = float(r["entry"]), float(r["initial_stop"])
            pos = Position(r["symbol"], side, STRATEGY, float(r["final_stop"]), stop0, abs(entry - stop0), 99.0, opened,
                           id=r["id"], reason=r.get("reason") or "", bias_mode="n/a")
            pos.add_leg(Leg(float(r["qty_initial"]), entry, opened, "initial"))
            try:
                pos.events = json.loads(r.get("events") or "[]")
            except ValueError:
                pos.events = []
            pos.meta.update(external_mgmt=True, no_pyramid=True, max_hold=10 ** 6,
                            target=entry + side * P["target_r"] * abs(entry - stop0))
            pos.last_price = entry
            pos.log(self.now(), "readopted", why="bot restarted; trade restored from the journal")
            self.state.positions[pos.id] = pos
            getattr(self.ctx.broker, "open_positions", {})[pos.id] = pos
            self.log.info("%s: re-adopted open %s trade %s", STRATEGY, pos.symbol, pos.id)

    async def on_bar(self, bar: Bar):
        self.beat()
        sym = bar.symbol
        if sym not in self.symbols:
            return
        await self.manage(sym, bar)
        t = (bar.ts + pd.Timedelta("1min")).tz_convert(self.tz)                # this bar's close
        if t.hour * 60 + t.minute != ENTRY_MOD or t.dayofweek >= 5 or self.done.get(sym) == t.date():
            return
        self.done[sym] = t.date()
        df = self.ctx.store.tf(sym, "15min")
        df = df[df.index + pd.Timedelta("15min") <= t]
        st = c10_signal(df, self.tz)
        if st:
            await self.enter(sym, st, bar)

    async def manage(self, sym: str, bar: Bar):
        t = (bar.ts + pd.Timedelta("1min")).tz_convert(self.tz)
        for pos in [p for p in self.state.positions.values() if p.symbol == sym and p.status == "open"
                    and p.strategy == STRATEGY and not p.meta.get("pending_close")]:
            tgt = pos.meta.get("target")
            if tgt is not None and (bar.high >= tgt if pos.side > 0 else bar.low <= tgt):
                await self.close(pos, float(tgt), "target", limit=True)
            elif t.hour * 60 + t.minute >= EXIT_MOD and t.hour < 17:
                await self.close(pos, bar.close, "time_1545")

    async def close(self, pos: Position, price: float, reason: str, limit: bool = False):
        try:
            px = await self.ctx.broker.close(pos, price, limit=price if limit else None)
        except OrderRejected as e:
            pos.meta["pending_close"] = reason            # the position manager retries it every bar
            pos.log(self.now(), "close_failed", why=str(e)[:200], reason=reason)
            return
        if px is None:
            return                                         # resting target not filled yet (OANDA): checked next bar
        if limit and not any(e.get("kind") == "limit_exit" and e.get("resting") for e in pos.events[-3:]):
            pos.log(self.now(), "limit_exit", level=round(price, 6), price=px, reason=reason)
        pos.status, pos.exit_reason, pos.closed_ts, pos.last_price = "closed", reason, self.now(), px
        pos.log(pos.closed_ts, "exit", price=px, reason=reason, realized=round(pos.realized, 2))
        self.state.realized_today += pos.realized
        self.state.positions.pop(pos.id, None)
        await self.bus.publish("position_closed", {"position": pos, "price": px})

    async def enter(self, sym: str, st: dict, bar: Bar):
        side = st["side"]
        mid = self.state.last_prices.get(sym, bar.close)
        hs = half_spread(self.cfg, sym)
        ic = self.cfg["instruments"][sym]
        q = float(ic["tick_size"])
        e0 = mid + side * hs
        if self.on_account:                                # size from the side the order really fills on
            qt = await self.ctx.broker.quote(sym)
            if qt:
                e0 = qt[1] if side > 0 else qt[0]
        stop = round((st["close"] - side * P["stop_atr"] * st["atr"]) / q) * q
        rec = {"ts": self.now().isoformat(), "symbol": sym, "strategy": STRATEGY, "side": side, "entry": round(e0, 6),
               "stop": stop, "quality": None, "confidence": None}
        dist = (e0 - stop) * side
        if not self.state.trading_enabled:
            return self._reject(rec, f"trading halted: {self.state.halt_reason}")
        if self.on_account:
            why = self.account_block(sym, side)
            if why:
                return self._reject(rec, why)
        if dist <= 0 or not (0.5 * st["atr"] <= dist <= min(2.5 * st["atr"], 0.10 * e0)):
            return self._reject(rec, f"stop {dist:.2f} outside 0.5–2.5 ATR ({st['atr']:.2f})")
        if 2 * hs > P["spread_frac"] * dist:
            return self._reject(rec, f"spread {2 * hs:.2f} too wide for a {dist:.2f} stop")
        equity = self.state.equity or await self.ctx.broker.equity()
        if not equity or equity <= 0:
            return self._reject(rec, "equity unknown")
        mult = float(ic["multiplier"])
        step, min_u = qty_rules(ic)
        qty = min(floor_step(equity * self.risk_pct / (dist * mult), step), float(ic["max_units"]))
        if self.on_account:
            r = self.cfg["risk"]
            mpu = margin_per_unit(ic, e0)
            if mpu:
                room = min(r.get("max_margin_pct_per_position", 0.25) * equity,
                           r.get("max_margin_pct_total", 0.60) * equity - margin_in_use(self.cfg, self.state))
                qty = min(qty, max(0.0, floor_step(room / mpu, step)))
        if qty < min_u:
            return self._reject(rec, f"{min_u:g} unit(s) exceed the {self.risk_pct:.2%} risk budget or the margin room")
        word = "up" if side > 0 else "down"
        pos = Position(sym, side, STRATEGY, stop, stop, dist, 99.0, self.now(), jev_source="none", bias_mode="n/a",
                       reason=f"morning {word} held to 13:00: {st['close']:.1f} vs prior close {st['prev_close']:.1f}, "
                              f"{abs(st['close'] - st['open_0930']) / st['atr']:.1f} ATR from 09:30, ER {st['er']:.2f}")
        pos.meta.update(external_mgmt=True, no_pyramid=True, max_hold=10 ** 6, atr15=round(st["atr"], 2),
                        er12=round(st["er"], 3))
        try:
            px = await self.ctx.broker.open(pos, qty, mid)
        except OrderRejected as e:
            return self._reject(rec, f"broker guard: {e}")
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.meta["target"] = px + side * P["target_r"] * pos.risk_per_unit
        pos.last_price = px
        pos.log(self.now(), "entry", price=px, qty=qty, stop=stop, target=round(pos.meta["target"], 2),
                risk_ccy=round(qty * pos.risk_per_unit * mult, 2))
        self.state.positions[pos.id] = pos
        place = getattr(self.ctx.broker, "place_target", None)
        if place is not None:                              # OANDA: the 2R target rests at the broker (audit F5)
            try:
                await place(pos, pos.meta["target"], pos.open_qty, "full")
            except Exception as e:  # noqa: BLE001
                self.log.warning("%s: resting target not placed: %s", STRATEGY, e)
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}"})
        await self.bus.publish("position_opened", pos)

    def account_block(self, sym: str, side: int) -> str:
        """The practice account's limits (the RiskAgent's checks that apply to a frozen external rule)."""
        r = self.cfg["risk"]
        if getattr(self.state, "entries_blocked", ""):
            return f"entries blocked: {self.state.entries_blocked}"
        if self.cfg["instruments"].get(sym, {}).get("trade", True) is False:
            return f"instrument off: {sym} is watch-only (trade: false)"
        open_pos = [p for p in self.state.positions.values() if p.status == "open"]
        if len(open_pos) >= r["max_open_positions"]:
            return "max open positions"
        if sum(p.symbol == sym for p in open_pos) >= r["max_positions_per_symbol"]:
            return "already positioned in symbol"
        grp = list(r.get("index_group", ["NDQ", "US30"]))
        if sym in grp and sum(p.symbol in grp and p.side == side for p in open_pos) >= int(r.get("index_group_max", 1)):
            return "index group full (one index position per direction at a time)"
        return ""

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("%s: no trade %s: %s", STRATEGY, rec["symbol"], why)
