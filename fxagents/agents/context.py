"""Market-context agents: Bias (multi-timeframe direction + safeguards) and News (economic calendar)."""
from __future__ import annotations

import logging
from collections import deque

import numpy as np
import pandas as pd

from ..bias import bias_frame, label
from ..indicators import in_windows
from ..structure import trading_day
from .core import Agent


log = logging.getLogger("bias")

GUARD_DEFAULT = {"aligned_losses": 0, "suspended": False, "suspended_h1": None}


class GuardMixin:
    """The bias loss circuit-breaker, one instance per BOOK (Oct 26 2026): N bias-aligned losses in a row on a symbol
    → suspended until the 1H structure prints a fresh break. State lives on the book's LiveState (guards,
    guard_day, guard_closed) so it is saved in the runtime file and survives a restart. The practice account's
    BiasAgent and every paper book's BookGuardAgent use this, each fed only by its own book's closed positions."""

    def _guard_init(self, defaults: dict) -> None:
        st = self.state
        for sym in self.cfg["instruments"]:
            g = st.guards.setdefault(sym, {})       # a restored file may have filled it already: keep those values
            for k, v in defaults.items():
                g.setdefault(k, v)
        self.guard = st.guards

    def _persist(self) -> None:
        store = getattr(self.ctx, "runtime_store", None)
        if store is not None:
            try:
                store.save(self.state)
            except Exception as e:  # noqa: BLE001 — a failed save must never stop the bot
                self.log.warning("could not save the loss guards: %s", e)

    def _roll(self, now: pd.Timestamp) -> bool:
        """New 17:00-NY trading day → every loss streak starts over (suspensions stay)."""
        tday = str(trading_day(now).date())
        if tday == self.state.guard_day:
            return False
        self.state.guard_day = tday
        for g in self.guard.values():
            g["aligned_losses"] = 0
        self._persist()
        return True

    def _release(self, sym: str, h1) -> bool:
        """Release rule (unchanged): the 1H structure sign differs from the one at suspension time."""
        g = self.guard[sym]
        if g["suspended"] and h1 != g["suspended_h1"]:
            g["suspended"], g["aligned_losses"] = False, 0
            self.state.alert("info", f"{sym}: bias suspension lifted — fresh 1H structure break ({'+' if h1 > 0 else '−'})")
            self._persist()
            return True
        return False

    async def _count_close(self, ev, notify: bool = True) -> str | None:
        """Book one closed position into this book's guard. Returns the symbol if it was counted, else None.
        A position id counts once however often its close is announced (replayed notification)."""
        pos = ev["position"]
        seen = self.state.guard_closed
        if pos.id in seen:
            return None
        seen.append(pos.id)
        del seen[:-200]
        g = self.guard.get(pos.symbol)
        if g is None or pos.bias_mode not in ("aligned", "in_doubt"):
            self._persist()
            return None
        if pos.realized < 0:
            g["aligned_losses"] += 1
            if g["aligned_losses"] >= self.sg["suspend_after_losses"] and not g["suspended"]:
                b = self.state.bias.get(pos.symbol, {})
                g["suspended"], g["suspended_h1"] = True, b.get("h1")
                msg = (f"{pos.symbol}: {g['aligned_losses']} bias-aligned losses in a row — bias SUSPENDED until "
                       f"the 1H structure breaks again")
                self.state.alert("warn", msg)
                if notify:
                    await self.bus.publish("alert", {"msg": msg, "event": "bias", "title": "🧭 Bias suspended"})
        else:
            g["aligned_losses"] = 0
        self._persist()
        return pos.symbol


class BookGuardAgent(GuardMixin, Agent):
    """A paper book's own loss guard (Oct 26 2026). The structural bias reading is shared with the practice account,
    but suspensions used to be too — a paper book was suspended by the PRACTICE account's losses. Now each book
    counts only its own closes; its Risk gate reads the result through LiveState.bias_for()."""
    name = "book_guard"

    def start(self):
        super().start()
        self.sg = self.cfg["bias"]["safeguards"]
        self._guard_init(GUARD_DEFAULT)
        self.bus.subscribe("clock", self.on_clock)
        self.bus.subscribe("position_closed", self.on_closed)

    async def on_clock(self, now: pd.Timestamp):
        self._roll(now)
        for sym, g in self.guard.items():
            if g.get("suspended"):
                b = self.state.bias.get(sym)             # the shared reading
                if b:
                    self._release(sym, b["h1"])

    async def on_closed(self, ev):
        await self._count_close(ev, notify=False)


class BiasAgent(GuardMixin, Agent):
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
        self._guard_init({**GUARD_DEFAULT, "in_doubt": False, "audit_p": None, "audit_hour": None,
                          "audit_label": None, "audit_req": None})
        self.samples: dict[str, deque] = {s: deque(maxlen=200) for s in self.cfg["instruments"]}
        self.bus.subscribe("clock", self.on_clock)
        self.bus.subscribe("hour_closed", self.on_hour_closed)
        self.bus.subscribe("position_closed", self.on_closed)
        self.warned_short: set[tuple] = set()

    async def on_hour_closed(self, ev: dict):
        """The market-data agent stored a symbol's final minute of an hour (Oct 26 2026). Refresh that symbol's bias
        NOW — it runs before the bar's stops, management and entry signals — so no entry on the first bar after the
        hour is judged on the previous hour's bias. The clock tick that follows sees the hour as done and skips it.
        Hours whose final bar never arrives still go through on_clock's grace period; a final minute that arrives
        after the clock already did the grace update comes through here and redoes it once."""
        sym, hour = ev["symbol"], pd.Timestamp(ev["hour"])
        if sym not in self.cfg["instruments"]:
            return
        d = self.done.get(sym)
        if d is not None and (d[0] > hour or (d[0] == hour and d[1])):
            return                                          # already final for this hour (or a later hour was done)
        self.done[sym] = (hour, True)
        await self.update(sym, max(pd.Timestamp(self.now()), hour))

    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        self._roll(now)                # 17:00 NY roll on the wall clock → loss streaks reset (saved with the guard)
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

    def hour_minutes(self, sym: str, now: pd.Timestamp) -> tuple[int | None, bool | None]:
        """(minutes present, complete) for the hour that closed last before `now` (Oct 26 2026). Recorded only — it
        gates nothing. complete = 60 of 60, or the hour's final minute present AND at least 55 minutes."""
        try:
            end = now.floor("h")
            start = end - pd.Timedelta("1h")
            idx = self.ctx.store.m1(sym).index
            win = idx[(idx >= start) & (idx < end)]
        except Exception:  # noqa: BLE001 — a store that can't say leaves the fields empty
            return None, None
        n = len(win)
        last = bool(n) and win[-1] == end - pd.Timedelta("1min")
        return n, bool(n == 60 or (last and n >= 55))

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
        n_min, full = self.hour_minutes(sym, now)
        if n_min is not None and 0 < n_min < 55 and (sym, now.floor("h")) not in self.warned_short:
            self.warned_short.add((sym, now.floor("h")))      # once per symbol-hour; an empty hour is a closed market
            self.log.warning("%s: the hour ending %s closed with only %d of 60 one-minute bars", sym,
                             now.floor("h").strftime("%H:%M"), n_min)
        g = self.guard[sym]
        # safeguard 3: lift suspension once the 1H structure prints a fresh break
        self._release(sym, b["h1"])
        # safeguard 4: Jev audit (only when entries are possible soon, to save calls). Oct 26 2026: an audit belongs
        # to the reading it judged (symbol + label + hour) and expires; one request per reading; a late answer for an
        # older reading never overwrites a newer one.
        self._expire_audit(sym, g, b, now)
        wins = self.cfg["sessions"]["entry_windows"]
        soon = any(in_windows(now + pd.Timedelta(minutes=m), wins) for m in range(0, 90, 15))
        key = f"{sym}|{b['label']}|{now.floor('h').isoformat()}"
        if self.sg.get("jev_audit", True) and b["label"] != "NEUTRAL" and soon and g.get("audit_req") != key:
            g["audit_req"] = key                       # asked once for this reading, whatever the answer
            h1 = self.ctx.store.h1(sym).iloc[-12:]
            res = await self.ctx.jev.bias_audit({
                "symbol": sym, **b, "recent_h1": h1.round(4).to_dict("split")["data"],
                "news": self.ctx.news.brief(now) if self.ctx.news else []})
            when = now.isoformat(timespec="minutes")
            if res.get("fallback"):
                g["audit_src"] = "jev unavailable"     # keep the last real audit; a stand-in doesn't change the call
            elif g.get("audit_req") != key or (g.get("audit_hour") and pd.Timestamp(g["audit_hour"]) > pd.Timestamp(when)):
                self.log.info("%s: late Jev audit for %s ignored (a newer reading has been asked/answered)", sym, key)
            else:
                g["audit_p"], g["audit_hour"], g["audit_label"] = round(res["prob"], 3), when, b["label"]
                g["in_doubt"] = res["prob"] < self.sg["audit_doubt_below"]
                g["audit_src"] = res.get("source")
        elif b["label"] == "NEUTRAL":
            g["in_doubt"] = False
        # safeguard 6: accuracy — did the bias call the next N hours? One sample per symbol per hour (Oct 26 2026)
        smp = self.samples[sym]
        if not smp or smp[-1]["ts"].floor("h") != now.floor("h"):
            smp.append({"ts": now, "score": b["score"], "price": b["price"]})
        hz = pd.Timedelta(hours=self.sg.get("accuracy_horizon_h", 4))
        judged = [(s, b["price"]) for s in smp if now - s["ts"] >= hz and abs(s["score"]) >= self.bc["min_align"]
                  and "hit" not in s]
        for s, p in judged:
            s["hit"] = (p - s["price"]) * np.sign(s["score"]) > 0
        hits = [s["hit"] for s in smp if "hit" in s][-30:]
        acc = round(sum(hits) / len(hits), 3) if hits else None
        state = "SUSPENDED" if g["suspended"] else ("IN DOUBT" if g["in_doubt"] else b["label"])
        prev = self.state.bias.get(sym) or {}
        if prev.get("updated") and pd.Timestamp(prev["updated"]) > now.floor("min"):
            self._persist()                             # an update started later already published a newer reading
            return
        self.state.bias[sym] = b | {"state": state, "suspended": g["suspended"], "in_doubt": g["in_doubt"],
                                    "audit_p": g["audit_p"], "audit_src": g.get("audit_src"), "aligned_losses": g["aligned_losses"],
                                    "accuracy": acc, "accuracy_n": len(hits),
                                    "h1_minutes": n_min, "h1_complete": full, "updated": now.isoformat(timespec="minutes")}
        self._persist()

    def _expire_audit(self, sym: str, g: dict, b: dict, now: pd.Timestamp) -> None:
        """An audit only counts while it is fresh (bias.audit_ttl_min) and the bias still reads as it did when Jev
        judged it. Otherwise it is dropped — in_doubt clears, as if there were no audit — and the reason is logged
        (a failed refresh used to keep the old 'in doubt' alive indefinitely)."""
        if g.get("audit_p") is None and not g.get("in_doubt"):
            return
        ttl = float(self.bc.get("audit_ttl_min", 180))
        why = None
        if g.get("audit_label") and g["audit_label"] != b["label"]:
            why = f"bias changed {g['audit_label']} -> {b['label']}"
        elif g.get("audit_hour"):
            age = (now - pd.Timestamp(g["audit_hour"])).total_seconds() / 60
            if age > ttl:
                why = f"audit is {age:.0f} min old (ttl {ttl:.0f})"
        elif g.get("in_doubt"):
            why = "audit has no timestamp"
        if why:
            self.log.info("%s: Jev audit dropped (%s)", sym, why)
            g.update(in_doubt=False, audit_p=None, audit_hour=None, audit_label=None, audit_src=None)

    async def on_closed(self, ev):
        sym = await self._count_close(ev)
        if sym:
            await self.update(sym, self.now())


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
