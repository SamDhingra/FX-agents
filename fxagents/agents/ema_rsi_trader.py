"""Shadow book `ema21_rsi55`: Sam's EMA21 + RSI 55 rule on paper, rules frozen (Oct 2026).

Tested on OANDA bid/ask Oct 2024 – Sep 2026 (fxagents/simple_rules.py, report year_test/ema21_rsi55_v2_dev_m1):
positive on gold and US30 15m (+0.08 / +0.29 ATR per trade, day version) but no 95% range above zero. This book
builds the forward record — virtual fills, no orders — and logs Jev's grade on every signal WITHOUT acting on it,
so after ~100 trades the grade can be checked against the outcomes.

Rules (the "day" version that was tested; same code as the backtest: simple_rules.ema / wilder):
  • 15-minute mid candles; long and short (shorts added Oct 17 2026: the exact mirror of the long rule)
  • long entry: a completed candle closes above EMA21, the previous candle closed at or below it, and RSI(14) > 55
    → buy at the next price.  short entry: closes below EMA21, the previous closed at or above it, RSI(14) < 45
    → sell at the next price.  Candle close between 02:00 and 15:30 New York.
  • exit: long — the first completed 15m candle that closes below EMA21; short — the first that closes above it
    (the position manager closes it on the next bar). A candle that exits one side can enter the other.
    Flat at the session flatten (15:50 NY) like every book
  • the rule has no stop: a protective stop 3 × ATR(14, 15m) beyond entry exists only so the position has a
    defined risk for sizing (risk_pct of equity at that stop) and a cap on a gap; if it is ever hit, the journal
    says so. No adds, no target, no bias rule, no Jev gate.
Config (shadow.ema21_rsi55): symbols [XAUUSD, US30], risk_pct 0.001, stop_atr 3.0, sides [long, short].
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import Bar, Position
from ..simple_rules import ema, wilder
from .core import Agent
from .trading import floor_step, half_spread, qty_rules

STRATEGY = "ema21_rsi55"
TF = "15min"


def frame(df: pd.DataFrame) -> pd.DataFrame:
    """EMA21, RSI(14) and ATR(14) on 15m candles (index = candle start, columns open/high/low/close)."""
    b = pd.DataFrame({"c": df["close"], "h": df["high"], "l": df["low"]})
    b["ema21"] = ema(b.c, 21)
    d = b.c.diff()
    b["rsi"] = 100 - 100 / (1 + wilder(d.clip(lower=0), 14) / wilder((-d).clip(lower=0), 14))
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = wilder(tr, 14)
    return b


def entry_signal(b: pd.DataFrame, side: int = 1) -> bool:
    """side 1: close crosses above EMA21 with RSI > 55. side -1 (mirror): close crosses below EMA21 with RSI < 45."""
    if len(b) < 60:
        return False
    c, e, r, a = b.c.iloc[-1], b.ema21.iloc[-1], b.rsi.iloc[-1], b.atr.iloc[-1]
    c0, e0 = b.c.iloc[-2], b.ema21.iloc[-2]
    if not (np.isfinite([c, e, r, a, c0, e0]).all() and a > 0):
        return False
    if side > 0:
        return bool(c0 <= e0 and c > e and r > 55)
    return bool(c0 >= e0 and c < e and r < 45)


def signal_side(b: pd.DataFrame, sides=(1, -1)) -> int:
    for sd in sides:
        if entry_signal(b, sd):
            return sd
    return 0


class EmaRsiTrader(Agent):
    name = "trader"

    def start(self):
        super().start()
        c = (self.cfg.get("shadow") or {}).get("ema21_rsi55") or {}
        self.symbols = [s for s in (c.get("symbols") or ["XAUUSD", "US30"]) if s in self.cfg["instruments"]]
        self.risk_pct = float(c.get("risk_pct", 0.001))
        self.stop_atr = float(c.get("stop_atr", 3.0))
        self.sides = tuple({"long": 1, "short": -1}[str(x).lower()] for x in (c.get("sides") or ["long", "short"]))
        self.last: dict[str, pd.Timestamp] = {}
        self.bus.subscribe("bar_1m", self.on_bar)

    async def on_bar(self, bar: Bar):
        self.beat()
        sym = bar.symbol
        if sym not in self.symbols:
            return
        boundary = (bar.ts + pd.Timedelta("1min")).floor(TF)
        if self.last.get(sym) is not None and boundary <= self.last[sym]:
            return
        if bar.ts + pd.Timedelta("1min") - boundary > pd.Timedelta("5min"):
            self.last[sym] = boundary                    # too late after the candle closed (outage): skip it
            return
        self.last[sym] = boundary
        df = self.ctx.store.tf(sym, TF)
        df = df[df.index + pd.Timedelta(TF) <= boundary]
        if not len(df) or df.index[-1] + pd.Timedelta(TF) != boundary:
            return
        b = frame(df)
        self.manage(sym, b)
        await self.maybe_enter(sym, b, boundary, bar)

    def manage(self, sym: str, b: pd.DataFrame):
        for pos in [p for p in self.state.positions.values() if p.symbol == sym and p.status == "open" and p.strategy == STRATEGY]:
            if pd.Timestamp(pos.opened_ts) >= b.index[-1] + pd.Timedelta(TF):
                continue                                  # this candle closed before the entry
            c, e = b.c.iloc[-1], b.ema21.iloc[-1]
            if (c < e if pos.side > 0 else c > e) and not pos.meta.get("pending_close"):
                pos.meta["pending_close"] = "close_below_ema21" if pos.side > 0 else "close_above_ema21"
                pos.log(self.now(), "exit_signal", close=round(float(b.c.iloc[-1]), 4), ema21=round(float(b.ema21.iloc[-1]), 4))

    async def maybe_enter(self, sym: str, b: pd.DataFrame, boundary: pd.Timestamp, bar: Bar):
        loc = boundary.tz_convert(self.cfg["timezone"]) if boundary.tzinfo else boundary
        mins = loc.hour * 60 + loc.minute
        if loc.dayofweek >= 5 or not (120 <= mins <= 930):
            return
        side = signal_side(b, self.sides)
        if not side:
            return
        # one position per symbol; a position already flagged to close on this candle doesn't block the reverse
        if any(p.symbol == sym and p.status == "open" and p.strategy == STRATEGY and not p.meta.get("pending_close")
               for p in self.state.positions.values()):
            return
        mid = self.state.last_prices.get(sym, bar.close)
        hs = half_spread(self.cfg, sym)
        q = float(self.cfg["instruments"][sym]["tick_size"])
        atr = float(b.atr.iloc[-1])
        e0 = mid + side * hs                                       # ask for a buy, bid for a sell
        stop = round((e0 - side * self.stop_atr * atr) / q) * q
        rec = {"ts": self.now().isoformat(), "symbol": sym, "strategy": STRATEGY, "side": side, "entry": round(e0, 6),
               "stop": stop, "quality": None, "confidence": None}
        g = await self.jev_grade(sym, b, e0, stop, atr, side)             # logged only — never gates the trade
        if g:
            rec.update(quality=g.get("quality"), confidence=g.get("confidence"))
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
        dist = (e0 - stop) * side
        step, min_u = qty_rules(ic)
        qty = min(floor_step(equity * self.risk_pct / (dist * mult), step), float(ic["max_units"]))
        if dist <= 0 or qty < min_u:
            return self._reject(rec, f"{min_u:g} unit(s) exceed the {self.risk_pct:.2%} risk budget")
        rule = "EMA21+RSI55" if side > 0 else "EMA21+RSI45 short"
        pos = Position(sym, side, STRATEGY, stop, stop, dist, 99.0, self.now(), jev_source=(g or {}).get("source", "none"),
                       reason=f"{rule}: 15m close {b.c.iloc[-1]:.2f} {'>' if side > 0 else '<'} EMA21 {b.ema21.iloc[-1]:.2f}, RSI {b.rsi.iloc[-1]:.1f}",
                       bias_mode="n/a")
        pos.meta.update(external_mgmt=True, no_pyramid=True, max_hold=10 ** 6, atr15=round(atr, 4),
                        rsi=round(float(b.rsi.iloc[-1]), 2),
                        jev_quality=(g or {}).get("quality"), jev_confidence=(g or {}).get("confidence"),
                        jev_htf_aligned=(g or {}).get("htf_aligned"))
        px = await self.ctx.broker.open(pos, qty, mid)
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.last_price = px
        pos.log(self.now(), "entry", price=px, qty=qty, stop=stop, risk_ccy=round(qty * pos.risk_per_unit * mult, 2),
                jev=(g or {}).get("quality"))
        self.state.positions[pos.id] = pos
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}, jev {(g or {}).get('quality')}"})
        await self.bus.publish("position_opened", pos)

    async def jev_grade(self, sym: str, b: pd.DataFrame, entry: float, stop: float, atr: float, side: int = 1) -> dict | None:
        """Jev's opinion of this signal, for the record. Any failure → None; the trade goes ahead regardless."""
        jev = getattr(self.ctx, "jev", None)
        if jev is None:
            return None
        bias = self.state.bias.get(sym, {})
        long_ = side > 0
        info = {"symbol": sym, "strategy": STRATEGY, "side": "LONG" if long_ else "SHORT", "entry": round(entry, 4), "stop": stop,
                "reason": "15m close crossed above EMA21 with RSI(14) > 55; exit on the first 15m close below EMA21" if long_
                else "15m close crossed below EMA21 with RSI(14) < 45; exit on the first 15m close above EMA21",
                "risk_atr": round(abs(entry - stop) / atr, 2) if atr else None,
                "htf_bias": 1 if bias.get("score", 0) > 0 else -1 if bias.get("score", 0) < 0 else 0,
                "htf_detail": {k: bias.get(k) for k in ("label", "score", "d", "h4", "h1", "pd_pos", "pdh", "pdl")},
                "rsi": round(float(b.rsi.iloc[-1]), 1), "ema21": round(float(b.ema21.iloc[-1]), 4),
                "recent_bars": b[["c"]].iloc[-12:].round(4).c.tolist(), "time_ny": str(self.now()),
                "question": f"Is the trend likely to continue {'up' if long_ else 'down'} from here?"}
        try:
            return await jev.rate_signal(info)
        except Exception as e:  # noqa: BLE001
            self.log.warning("ema21_rsi55: Jev grade failed for %s: %s", sym, e)
            return None

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("ema21_rsi55: no trade %s: %s", rec["symbol"], why)
