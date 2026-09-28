"""Trading-path agents: MarketData → Selector (hourly) → Trader → Risk → PositionManager."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..broker import OrderRejected
from ..indicators import in_windows
from ..models import Bar, Position, Signal
from ..strategies import Strategy
from .core import Agent


def _hm(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def news_blackout(cfg, ts: pd.Timestamp, lookahead_min: int = 0) -> str | None:
    nb = cfg["risk"]["news_blackout"]
    w = nb.get("window_min", 5)
    mins = ts.hour * 60 + ts.minute
    if ts.dayofweek < 5:
        for t in nb.get("recurring_weekdays", []):
            if _hm(t) - w - lookahead_min <= mins <= _hm(t) + w:
                return f"news window {t}"
    for ev in nb.get("events", []) or []:
        if str(ev["date"]) == ts.strftime("%Y-%m-%d"):
            ew = ev.get("window_min", w)
            if _hm(ev["time"]) - ew - lookahead_min <= mins <= _hm(ev["time"]) + ew:
                return ev.get("label", "news")
    return None


# ─────────────────────────────────────────────────────────────────────────────
class MarketDataAgent(Agent):
    """Stores bars, lets the broker check resting stops, then fans out 1m and 5m events."""
    name = "market_data"

    def start(self):
        super().start()
        self.bus.subscribe("bar", self.on_bar)
        self.sig_minutes = int(pd.Timedelta(self.cfg["timeframes"]["signal"]).total_seconds() // 60)

    async def on_bar(self, bar: Bar):
        self.beat()
        self.ctx.store.append(bar)
        self.state.last_prices[bar.symbol] = bar.close
        self.state.last_bar_ts[bar.symbol] = bar.ts.isoformat()
        await self.ctx.broker.on_bar(bar)                 # 1) resting stops
        await self.bus.publish("bar_1m", bar)              # 2) trade management
        if (bar.ts.minute + 1) % self.sig_minutes == 0:    # 3) new entries on signal-TF close
            await self.bus.publish("bar_signal", {"symbol": bar.symbol, "ts": bar.ts + pd.Timedelta("1min")})


# ─────────────────────────────────────────────────────────────────────────────
class SelectorAgent(Agent):
    """Each hour, per symbol: rank live strategies by (Jev rating × confidence) blended with
    hour-of-day statistics, and activate the best one(s). A symbol can also sit the hour out."""
    name = "selector"

    def start(self):
        super().start()
        self.last_hour: dict[str, pd.Timestamp] = {}
        self.bus.subscribe("clock", self.on_clock)
        self.bus.subscribe("stats_updated", self.on_stats)

    async def on_stats(self, _):
        await self.select_all()  # only symbols without a decision for this hour yet

    async def on_clock(self, now):
        self.beat()
        # select a few minutes before the hour so the hour starts with a decision
        nxt = (now + pd.Timedelta("3min")).floor("h")
        if any(self.last_hour.get(s) != nxt for s in self.cfg["instruments"]):
            await self.select_all()

    def regime(self, symbol: str, now: pd.Timestamp) -> dict:
        df = self.ctx.store.tf(symbol, self.cfg["timeframes"]["signal"])
        if len(df) < 60:
            return {}
        ctx = Strategy.context(df.iloc[-600:])
        a = ctx["atr"]
        pct = float((a[-1] > a[-288:]).mean()) if len(a) > 20 else 0.5
        wins = self.cfg["sessions"]["entry_windows"]
        nxt = now + pd.Timedelta("30min")
        return {"atr_percentile": round(pct, 2), "adx": round(float(ctx["adx"][-1]), 1),
                "htf_bias": int(ctx["htf"][-1]), "rsi": round(float(ctx["rsi"][-1]), 1),
                "in_entry_window": in_windows(nxt, wins),
                "news_soon": news_blackout(self.cfg, now, lookahead_min=60),
                "trend": "up" if df["close"].iloc[-1] > ctx["ema200"][-1] else "down"}

    async def select_all(self, force: bool = False):
        now = self.now()
        hour_ts = (now + pd.Timedelta("3min")).floor("h")
        for sym in self.cfg["instruments"]:
            if not force and self.last_hour.get(sym) == hour_ts:
                continue
            self.last_hour[sym] = hour_ts
            await self.select(sym, hour_ts)

    async def select(self, sym: str, hour_ts: pd.Timestamp):
        sel_cfg, jcfg = self.cfg["selector"], self.cfg["jev"]
        stats = self.state.strategy_stats.get(sym, {})
        live = [s for s in self.ctx.book.live() if s.id in stats]
        if not live:
            return
        wins = self.cfg["sessions"]["entry_windows"]
        if not any(in_windows(hour_ts + pd.Timedelta(minutes=m), wins) for m in range(0, 60, 5)):
            # no entries possible this hour → don't spend Jev calls
            self.state.selections[sym] = []
            return
        hour = hour_ts.hour
        k = sel_cfg["hour_shrinkage_k"]
        cands, quant = {}, {}
        for st in live:
            s = stats[st.id]
            h = s["by_hour"].get(hour, {"n": 0, "exp": 0.0, "win": 0.0})
            shrunk = (h["n"] * h["exp"] + k * s["expectancy"]) / (h["n"] + k)
            live_rec = self.ctx.journal.live_stats(sym, st.id)
            cands[st.id] = {
                "name": st.id, "family": st.family, "description": st.description[:220],
                "overall": {k2: s[k2] for k2 in ("n", "win_rate", "expectancy", "pf", "max_dd_r")},
                "this_hour": h, "this_hour_exp_shrunk": round(shrunk, 3),
                "recent": {"n": s["recent_n"], "exp": s["recent_exp"]},
                "live_trades": live_rec, "rr": st.rr}
            q = 1 / (1 + math.exp(-(3.0 * shrunk + 1.0 * s["recent_exp"]
                                    + (0.5 * live_rec["expectancy"] if live_rec["n"] >= 5 else 0))))
            if s["n"] < sel_cfg["min_trades_for_stats"]:
                q *= 0.6
            quant[st.id] = q
        regime = self.regime(sym, hour_ts)
        rating = await self.ctx.jev.rate_strategies(sym, hour, regime, cands)
        w = jcfg["weight"]
        ranked = []
        for sid, r in rating["by_strategy"].items():
            conf, jv = r["confidence"], r["value"]
            combined = w * (conf * jv + (1 - conf) * quant[sid]) + (1 - w) * quant[sid]
            ranked.append({"id": sid, "combined": round(combined, 3), "jev": round(jv, 3),
                           "jev_conf": round(conf, 3), "quant": round(quant[sid], 3),
                           "hour_exp": cands[sid]["this_hour_exp_shrunk"], "n": cands[sid]["overall"]["n"],
                           "source": rating["source"]})
        ranked.sort(key=lambda x: -x["combined"])
        trade_ok = rating["trade_ok"]["value"]
        for j, r in enumerate(ranked):
            r["selected"] = j < sel_cfg["top_n_per_symbol"] and r["combined"] >= jcfg["min_select_score"] and trade_ok >= 0.4
        self.state.selections[sym] = ranked
        picked = [r["id"] for r in ranked if r["selected"]]
        await self.bus.publish("selection", {"symbol": sym, "hour": hour, "picked": picked,
                                             "trade_ok": trade_ok, "ranked": ranked})
        self.log.info("%s %02d:00 → %s (trade_ok %.2f, %s)", sym, hour, picked or "sit out", trade_ok, rating["source"])


# ─────────────────────────────────────────────────────────────────────────────
class TraderAgent(Agent):
    """Runs this hour's selected strategy per symbol on each signal-TF close; Jev grades each setup."""
    name = "trader"

    def start(self):
        super().start()
        self.bus.subscribe("bar_signal", self.on_signal_bar)
        self.bus.subscribe("tv_signal", self.on_tradingview)
        self.window = 700

    async def on_signal_bar(self, ev):
        self.beat()
        sym = ev["symbol"]
        picks = [r["id"] for r in self.state.selections.get(sym, []) if r.get("selected")]
        if not picks:
            return
        df = self.ctx.store.tf(sym, self.cfg["timeframes"]["signal"]).iloc[-self.window:]
        if len(df) < 250:
            return
        ctx = Strategy.context(df)
        last = len(df) - 1
        for sid in picks:
            st = self.ctx.book.get(sid)
            if st is None:
                continue
            for rs in st.scan(df, ctx):
                if rs.i != last:
                    continue
                sig = Signal(sym, st.id, rs.side, rs.entry, rs.stop, ev["ts"], rs.reason,
                             rs.features, rs.structural_target, rr=st.rr)
                await self.evaluate(sig, ctx, df)

    async def evaluate(self, sig: Signal, ctx: dict | None, df: pd.DataFrame):
        stats = self.state.strategy_stats.get(sig.symbol, {}).get(sig.strategy, {})
        recent = df.iloc[-12:][["open", "high", "low", "close"]].round(4)
        info = {"symbol": sig.symbol, "strategy": sig.strategy, "side": "LONG" if sig.side > 0 else "SHORT",
                "entry": sig.entry, "stop": sig.stop, "target_1r": sig.target, "structural_target": sig.structural_target,
                "reason": sig.reason, "risk_atr": sig.features.get("risk_atr"),
                "htf_bias": int(ctx["htf"][-1]) if ctx else 0,
                "rsi": round(float(ctx["rsi"][-1]), 1) if ctx else None,
                "strategy_expectancy": stats.get("expectancy", 0.0), "strategy_win_rate": stats.get("win_rate"),
                "recent_bars_5m": recent.to_dict("split")["data"], "time_ny": str(sig.ts)}
        g = await self.ctx.jev.rate_signal(info)
        jc = self.cfg["jev"]
        ok = g["quality"] >= jc["min_signal_quality"] and g["confidence"] >= jc["min_signal_confidence"] * 0.8
        rec = {"ts": sig.ts.isoformat(), "symbol": sig.symbol, "strategy": sig.strategy, "side": info["side"],
               "entry": sig.entry, "stop": sig.stop, "quality": g["quality"], "confidence": g["confidence"]}
        if not ok:
            self.ctx.journal.add_signal(rec | {"action": "skipped", "why": f"Jev grade {g['quality']:.2f} below gate"})
            return
        await self.bus.publish("entry_request", {"signal": sig, "grade": g, "record": rec})

    async def on_tradingview(self, payload: dict):
        """TradingView alert → treated as one more strategy: graded by Jev, sized and checked by Risk."""
        sym = payload["symbol"]
        side = 1 if str(payload["side"]).lower() in ("buy", "long") else -1
        price = float(payload.get("price") or self.state.last_prices.get(sym, 0))
        stop = payload.get("stop")
        if stop is None:  # no stop in alert → derive 1 ATR stop (a trade never goes without one)
            df = self.ctx.store.tf(sym, self.cfg["timeframes"]["signal"]).iloc[-300:]
            a = float(Strategy.context(df)["atr"][-1]) if len(df) > 20 else price * 0.002
            stop = price - side * a
        sig = Signal(sym, f"tradingview:{payload.get('strategy', 'alert')}", side, price, float(stop),
                     self.now(), payload.get("comment", "TradingView alert"), {}, rr=float(payload.get("rr", 1.0)))
        df = self.ctx.store.tf(sym, self.cfg["timeframes"]["signal"]).iloc[-self.window:]
        await self.evaluate(sig, Strategy.context(df) if len(df) > 60 else None, df)


# ─────────────────────────────────────────────────────────────────────────────
class RiskAgent(Agent):
    """Final gate before the broker: stop mandatory, ≤10% of trade value, risk-%-of-equity sizing,
    exposure limits, entry windows, news blackouts, kill switch."""
    name = "risk"

    def start(self):
        super().start()
        self.bus.subscribe("entry_request", self.on_request)

    def _reject(self, rec: dict, why: str):
        self.ctx.journal.add_signal(rec | {"action": "rejected", "why": why})
        self.log.info("rejected %s %s: %s", rec["symbol"], rec["strategy"], why)

    async def on_request(self, req):
        self.beat()
        sig: Signal = req["signal"]
        rec = req["record"]
        r, s = self.cfg["risk"], self.cfg["sessions"]
        now = self.now()
        if not self.state.trading_enabled:
            return self._reject(rec, f"trading halted: {self.state.halt_reason}")
        if not in_windows(now, s["entry_windows"]):
            return self._reject(rec, "outside entry windows")
        if now.hour * 60 + now.minute >= _hm(s["flatten_at"]) - 20 and now.hour < 17:
            return self._reject(rec, "too close to session flatten")
        nb = news_blackout(self.cfg, now)
        if nb:
            return self._reject(rec, f"news blackout ({nb})")
        open_pos = [p for p in self.state.positions.values() if p.status == "open"]
        if len(open_pos) >= r["max_open_positions"]:
            return self._reject(rec, "max open positions")
        if sum(p.symbol == sig.symbol for p in open_pos) >= r["max_positions_per_symbol"]:
            return self._reject(rec, "already positioned in symbol")
        if sig.stop is None:
            return self._reject(rec, "no stop loss")

        ic = self.cfg["instruments"][sig.symbol]
        mult, tick = float(ic["multiplier"]), float(ic["tick_size"])
        price = self.state.last_prices.get(sig.symbol, sig.entry)
        stop = sig.stop
        # enforce minimum stop (noise) using ATR
        a = sig.features.get("atr")
        if a and abs(price - stop) < r["min_stop_atr"] * a:
            stop = price - sig.side * r["min_stop_atr"] * a
        stop = round(round(stop / tick) * tick, 10)
        if (price - stop) * sig.side <= 0:
            return self._reject(rec, "stop on wrong side of price")
        dist = abs(price - stop)
        if dist / price > r["max_stop_pct_of_trade_value"]:
            return self._reject(rec, f"stop {dist/price:.2%} of trade value > {r['max_stop_pct_of_trade_value']:.0%}")
        equity = self.state.equity or await self.ctx.broker.equity()
        risk_ccy = equity * r["risk_per_trade_pct"]
        qty = math.floor(risk_ccy / (dist * mult))
        qty = min(qty, int(ic["max_units"]))
        if qty < 1:
            return self._reject(rec, f"1 unit risks ${dist*mult:,.0f} > budget ${risk_ccy:,.0f}")

        pos = Position(sig.symbol, sig.side, sig.strategy, stop, stop, dist, sig.rr, now,
                       jev_quality=req["grade"]["quality"], jev_confidence=req["grade"]["confidence"],
                       jev_source=req["grade"]["source"], reason=sig.reason)
        try:
            px = await self.ctx.broker.open(pos, qty, price)
        except OrderRejected as e:
            return self._reject(rec, f"broker: {e}")
        pos.risk_per_unit = abs(px - pos.initial_stop)
        pos.last_price = px
        pos.log(now, "entry", price=px, qty=qty, stop=stop, risk_ccy=round(qty * pos.risk_per_unit * mult, 2))
        self.state.positions[pos.id] = pos
        self.ctx.journal.add_signal(rec | {"action": "taken", "why": f"qty {qty}, risk ${qty*pos.risk_per_unit*mult:,.0f}"})
        await self.bus.publish("position_opened", pos)


# ─────────────────────────────────────────────────────────────────────────────
class PositionManagerAgent(Agent):
    """1:1 first target → bank a partial and move the stop into profit → pyramid adds (Jev-confirmed,
    never risking open profit) with a stepped trailing stop → flatten at session end."""
    name = "position_manager"

    def start(self):
        super().start()
        self.bus.subscribe("bar_1m", self.on_bar)
        self.bus.subscribe("stop_filled", self.on_stop)
        self.bus.subscribe("flatten_all", self.on_flatten_all)
        self.bus.subscribe("flatten_symbol", self.on_flatten_symbol)
        self.m = self.cfg["management"]

    def lvl(self, pos: Position, step: int) -> float:
        r = pos.rr + (step - 1) * self.m["trail_step_r"]
        return pos.entry + pos.side * r * pos.risk_per_unit

    def stop_after(self, pos: Position, step: int) -> float:
        base = 0.0 if step == 1 else pos.rr + (step - 2) * self.m["trail_step_r"]
        return pos.entry + pos.side * (base + self.m["lock_r"]) * pos.risk_per_unit

    async def on_bar(self, bar: Bar):
        self.beat()
        for pos in [p for p in self.state.positions.values() if p.symbol == bar.symbol and p.status == "open"]:
            await self.manage(pos, bar)

    async def manage(self, pos: Position, bar: Bar):
        broker, now = self.ctx.broker, self.now()
        mult = float(self.cfg["instruments"][pos.symbol]["multiplier"])
        hi = bar.high if pos.side > 0 else bar.low
        lo = bar.low if pos.side > 0 else bar.high
        pos.last_price = bar.close
        pos.mfe_r = max(pos.mfe_r, pos.r_now(hi))
        pos.mae_r = min(pos.mae_r, pos.r_now(lo))

        # 1) time exits (day trading)
        s = self.cfg["sessions"]
        mins = now.hour * 60 + now.minute
        held = (now - pos.opened_ts).total_seconds() / 60
        if (_hm(s["flatten_at"]) <= mins < 17 * 60) or held >= s["max_hold_minutes"]:
            return await self.close(pos, bar.close, "session_flat" if held < s["max_hold_minutes"] else "max_hold")

        # 2) target steps
        while (hi - self.lvl(pos, pos.stage + 1)) * pos.side >= 0:
            pos.stage += 1
            level = self.lvl(pos, pos.stage)
            if pos.stage == 1:
                if not self.m["pyramid"]["enabled"]:
                    return await self.close(pos, level, "target", limit=True)
                part = math.floor(pos.initial_qty * self.m["partial_at_target"])
                if part >= 1 and not pos.partial_done:
                    px = await broker.reduce(pos, part, bar.close, limit=level)
                    pos.partial_done = True
                    pos.log(now, "partial", price=px, qty=part, r=pos.rr)
                    await self.bus.publish("position_updated", {"position": pos, "event": "partial",
                                                                "msg": f"banked {part} @ {px} (+{pos.rr:g}R)"})
            new_stop = self.stop_after(pos, pos.stage)
            if (new_stop - pos.stop) * pos.side > 0:
                await broker.move_stop(pos, new_stop)
                pos.log(now, "stop_moved", stop=pos.stop, stage=pos.stage)
                await self.bus.publish("position_updated", {"position": pos, "event": "stop_to_profit",
                                                            "msg": f"stop → {pos.stop} (locks +{pos.r_now(pos.stop):.2f}R)"})
            await self.maybe_pyramid(pos, level, mult, bar)

    async def maybe_pyramid(self, pos: Position, level: float, mult: float, bar: Bar):
        pc = self.m["pyramid"]
        if not pc["enabled"] or pos.adds >= pc["max_adds"] or not self.state.trading_enabled:
            return
        add_qty = max(1, round(pos.initial_qty * pc["add_size_frac"]))
        # hard ceiling on units
        if pos.open_qty + add_qty > float(self.cfg["instruments"][pos.symbol]["max_units"]):
            return
        # worst case if stopped right after adding must stay ≥ 0 (never turn a winner into a loser)
        new_avg = (pos.avg_entry * pos.gross_qty + level * add_qty) / (pos.gross_qty + add_qty)
        open_after = pos.open_qty + add_qty
        worst = pos.realized + (pos.stop - new_avg) * pos.side * open_after * mult \
            - self.ctx.broker.commission(pos.symbol, add_qty + open_after)
        if pc.get("never_risk_open_profit", True) and worst < 0:
            pos.log(self.now(), "pyramid_skipped", why="would risk open profit", worst=round(worst, 2))
            return
        if pc["require_continuation"]:
            df = self.ctx.store.tf(pos.symbol, self.cfg["timeframes"]["signal"]).iloc[-300:]
            c = Strategy.context(df) if len(df) > 60 else None
            mom = 0
            if c is not None:
                mom = int(np.sign(df["close"].iloc[-1] - c["ema50"][-1]) == pos.side and np.sign(c["macd_hist"][-1]) == pos.side)
            res = await self.ctx.jev.continuation({
                "symbol": pos.symbol, "side": "LONG" if pos.side > 0 else "SHORT", "strategy": pos.strategy,
                "r_now": round(pos.r_now(bar.close), 2), "stage": pos.stage, "stop_locked_r": round(pos.r_now(pos.stop), 2),
                "momentum_aligned": mom, "adx": round(float(c["adx"][-1]), 1) if c is not None else None,
                "recent_bars_5m": df.iloc[-8:][["open", "high", "low", "close"]].round(4).to_dict("split")["data"]})
            if res["prob"] < pc["min_continuation_prob"]:
                pos.log(self.now(), "pyramid_skipped", why=f"continuation {res['prob']:.2f}")
                return
        px = await self.ctx.broker.add(pos, add_qty, bar.close)
        pos.adds += 1
        pos.log(self.now(), "pyramid", price=px, qty=add_qty, stop=pos.stop, worst_case=round(worst, 2))
        await self.bus.publish("position_updated", {"position": pos, "event": "pyramid",
                                                    "msg": f"added {add_qty} @ {px}; worst case +${worst:,.0f}"})

    async def close(self, pos: Position, price: float, reason: str, limit: bool = False):
        px = await self.ctx.broker.close(pos, price, limit=price if limit else None)
        await self.finalize(pos, px, reason)

    async def finalize(self, pos: Position, px: float, reason: str):
        if pos.status == "closed":
            return
        pos.status, pos.exit_reason, pos.closed_ts = "closed", reason, self.now()
        pos.last_price = px
        pos.log(pos.closed_ts, "exit", price=px, reason=reason, realized=round(pos.realized, 2))
        self.state.realized_today += pos.realized
        self.state.positions.pop(pos.id, None)
        await self.bus.publish("position_closed", {"position": pos, "price": px})

    async def on_stop(self, ev):
        pos: Position = ev["position"]
        reason = "stop" if pos.stage == 0 else ("breakeven_plus_stop" if pos.stage == 1 else "trail_stop")
        await self.finalize(pos, ev["price"], reason)

    async def on_flatten_all(self, why):
        for pos in list(self.state.positions.values()):
            await self.close(pos, self.state.last_prices.get(pos.symbol, pos.entry), f"flatten: {why}")

    async def on_flatten_symbol(self, ev):
        for pos in [p for p in list(self.state.positions.values()) if p.symbol == ev["symbol"]]:
            await self.close(pos, self.state.last_prices.get(pos.symbol, pos.entry), f"flatten: {ev.get('why')}")
