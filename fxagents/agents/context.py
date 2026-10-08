"""Market-context agents: Bias (multi-timeframe direction + safeguards) and News (economic calendar)."""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from ..bias import bias_frame, label
from ..indicators import in_windows
from ..structure import trading_day
from .core import Agent


class BiasAgent(Agent):
    """Owns the higher-timeframe bias per symbol and the safeguards around it.

    Hard rule (enforced by Risk): trade only in the bias direction.
    Safeguards for when the bias is wrong:
      1. Timeframe disagreement → NEUTRAL → no trades (or reduced, per config).
      2. Fast invalidation: the 1H structure is part of the score, so a 1H break against D/4H cuts
         conviction immediately instead of waiting for the daily candle.
      3. Loss circuit-breaker: N bias-aligned losses in a row → bias SUSPENDED for that symbol until
         the 1H structure prints a fresh break.
      4. Jev audit (hourly): if Jev judges the bias stale → IN DOUBT → half size, A-grade setups only.
      5. Reversal exception (Risk agent): counter-bias only after a liquidity raid + 1H shift + Jev ≥ 0.7,
         at half size with no pyramiding.
      6. Accuracy tracking: how often the bias called the next 4 hours — visible on the dashboard.
    """
    name = "bias"

    def start(self):
        super().start()
        self.bc = self.cfg["bias"]
        self.sg = self.bc["safeguards"]
        self.last_hour: pd.Timestamp | None = None
        # F23: per symbol (hour, complete) of the last hourly update — the clock can tick past the hour
        # before that hour's final 1m bar was polled, which would close a PARTIAL hour into the bias.
        self.done: dict[str, tuple[pd.Timestamp, bool]] = {}
        self.grace = pd.Timedelta(minutes=float(self.bc.get("hour_complete_grace_min", 5)))
        self.guard: dict[str, dict] = {s: {"aligned_losses": 0, "suspended": False, "suspended_h1": None,
                                           "in_doubt": False, "audit_p": None, "audit_hour": None}
                                       for s in self.cfg["instruments"]}
        self.samples: dict[str, deque] = {s: deque(maxlen=200) for s in self.cfg["instruments"]}
        self.day = None
        self.bus.subscribe("clock", self.on_clock)
        self.bus.subscribe("position_closed", self.on_closed)

    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        tday = trading_day(now).date()     # 17:00 NY roll on the wall clock
        if tday != self.day:           # new trading day → reset loss streaks
            self.day = tday
            for g in self.guard.values():
                g["aligned_losses"] = 0
        hour = now.floor("h")
        self.last_hour = hour
        for sym in self.cfg["instruments"]:
            d = self.done.get(sym)
            if d is not None and d[0] == hour and d[1]:
                continue                                    # this hour's bias is final
            full = self.hour_complete(sym, hour)
            if d is not None and d[0] == hour and not full:
                continue                                    # grace update done; still waiting for the bar
            # wait for the hour's last bar; after `grace` (daily break, weekend, dead feed) update anyway
            # and redo it once the bar does arrive
            if full or now - hour >= self.grace:
                self.done[sym] = (hour, full)
                await self.update(sym, now)

    def hour_complete(self, sym: str, hour: pd.Timestamp) -> bool:
        """The store holds the bar that closes the previous hour (opened at hour − 1 min) or a later one."""
        m1 = self.ctx.store.m1(sym)
        return bool(len(m1)) and m1.index[-1] >= hour - pd.Timedelta("1min")

    async def update_all(self, now: pd.Timestamp):
        for sym in self.cfg["instruments"]:
            await self.update(sym, now)

    def compute(self, sym: str, now: pd.Timestamp) -> dict | None:
        h1 = self.ctx.store.h1(sym)
        if len(h1) < 48:
            return None
        px = self.state.last_prices.get(sym, float(h1["close"].iloc[-1]))
        b = bias_frame(h1, pd.DatetimeIndex([now]), np.array([px]), self.bc["weights"]).iloc[-1]
        f = lambda x: None if pd.isna(x) else round(float(x), 4)  # noqa: E731
        return {"score": round(float(b["score"]), 3), "d": int(b["d"]), "h4": int(b["h4"]), "h1": int(b["h1"]),
                "label": label(float(b["score"]), self.bc["min_align"]), "pd_pos": f(b.get("pd_pos")),
                "pdh": f(b["pdh"]), "pdl": f(b["pdl"]), "asia_hi": f(b["asia_hi"]), "asia_lo": f(b["asia_lo"]),
                "h4_swing_hi": f(b["h4_swing_hi"]), "h4_swing_lo": f(b["h4_swing_lo"]), "price": round(px, 4)}

    async def update(self, sym: str, now: pd.Timestamp):
        b = self.compute(sym, now)
        if b is None:
            return
        g = self.guard[sym]
        # safeguard 3: lift suspension once the 1H structure prints a fresh break
        if g["suspended"] and b["h1"] != g["suspended_h1"]:
            g["suspended"], g["aligned_losses"] = False, 0
            self.state.alert("info", f"{sym}: bias suspension lifted — fresh 1H structure break ({'+' if b['h1']>0 else '−'})")
        # safeguard 4: Jev audit (only when entries are possible soon, to save calls)
        wins = self.cfg["sessions"]["entry_windows"]
        soon = any(in_windows(now + pd.Timedelta(minutes=m), wins) for m in range(0, 90, 15))
        if self.sg.get("jev_audit", True) and b["label"] != "NEUTRAL" and soon:
            h1 = self.ctx.store.h1(sym).iloc[-12:]
            res = await self.ctx.jev.bias_audit({
                "symbol": sym, **b, "recent_h1": h1.round(4).to_dict("split")["data"],
                "news": self.ctx.news.brief(now) if self.ctx.news else []})
            g["audit_p"], g["audit_hour"] = round(res["prob"], 3), now.isoformat(timespec="minutes")
            g["in_doubt"] = res["prob"] < self.sg["audit_doubt_below"]
        elif b["label"] == "NEUTRAL":
            g["in_doubt"] = False
        # safeguard 6: accuracy — did the bias call the next N hours?
        smp = self.samples[sym]
        smp.append({"ts": now, "score": b["score"], "price": b["price"]})
        hz = pd.Timedelta(hours=self.sg.get("accuracy_horizon_h", 4))
        judged = [(s, b["price"]) for s in smp if now - s["ts"] >= hz and abs(s["score"]) >= self.bc["min_align"]
                  and "hit" not in s]
        for s, p in judged:
            s["hit"] = (p - s["price"]) * np.sign(s["score"]) > 0
        hits = [s["hit"] for s in smp if "hit" in s][-30:]
        acc = round(sum(hits) / len(hits), 3) if hits else None
        state = "SUSPENDED" if g["suspended"] else ("IN DOUBT" if g["in_doubt"] else b["label"])
        self.state.bias[sym] = b | {"state": state, "suspended": g["suspended"], "in_doubt": g["in_doubt"],
                                    "audit_p": g["audit_p"], "aligned_losses": g["aligned_losses"],
                                    "accuracy": acc, "accuracy_n": len(hits), "updated": now.isoformat(timespec="minutes")}

    async def on_closed(self, ev):
        pos = ev["position"]
        g = self.guard.get(pos.symbol)
        if g is None or pos.bias_mode not in ("aligned", "in_doubt"):
            return
        if pos.realized < 0:
            g["aligned_losses"] += 1
            if g["aligned_losses"] >= self.sg["suspend_after_losses"] and not g["suspended"]:
                b = self.state.bias.get(pos.symbol, {})
                g["suspended"], g["suspended_h1"] = True, b.get("h1")
                msg = (f"{pos.symbol}: {g['aligned_losses']} bias-aligned losses in a row — bias SUSPENDED until "
                       f"the 1H structure breaks again")
                self.state.alert("warn", msg)
                await self.bus.publish("alert", {"msg": msg, "event": "bias", "title": "🧭 Bias suspended"})
        else:
            g["aligned_losses"] = 0
        await self.update(pos.symbol, self.now())


class NewsAgent(Agent):
    """Keeps the economic calendar fresh, warns ahead of releases, protects open trades just before them."""
    name = "news"

    def start(self):
        super().start()
        self.nc = self.cfg["news"]
        self.warned: set[str] = set()
        self.protected: set[str] = set()
        self.bus.subscribe("clock", self.on_clock)

    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        cal = self.ctx.news
        if self.cfg["mode"] != "sim" and (cal.last_refresh is None or
                                          now - cal.last_refresh >= pd.Timedelta(minutes=self.nc["refresh_minutes"])):
            await cal.refresh(now)
        self.state.news = cal.public(now)
        self.state.news_source = cal.source
        blk = cal.blocked(now)
        self.state.news_block = ({"title": blk["title"], "tier": blk["tier"], "phase": blk["phase"],
                                  "ts": blk["ts"].isoformat()} if blk else None)
        for e in cal.upcoming(now, hours=self.nc["heads_up_minutes"] / 60):
            if e["id"] not in self.warned and e["tier"] in ("tier1", "high") and e["ts"] > now:
                self.warned.add(e["id"])
                b, a = cal._win(e["tier"])
                msg = (f"{e['title']} at {e['ts'].strftime('%H:%M')} NY ({e['tier']}). No new entries "
                       f"{b} min before → {a} min after." + (f" Forecast {e['forecast']}." if e["forecast"] else ""))
                self.state.alert("info", f"📰 {msg}", event="news")
                await self.bus.publish("alert", {"msg": msg, "event": "news", "title": "📰 News ahead"})
        for e in cal.pre_actions(now):
            if e["id"] in self.protected:
                continue
            self.protected.add(e["id"])
            await self.bus.publish("pre_news", {"event": e["title"], "tier": e["tier"], "action": e["action"]})
