"""Operations agents: Journal, Notifier, Monitor."""
from __future__ import annotations

import asyncio
import os
import time

import httpx
import pandas as pd

from .core import Agent


def header_title(title: str) -> str:
    """HTTP header-safe title: emoji are dropped (ASCII only) and the result may not start or end
    with whitespace — a leading space (left behind when a title starts with an emoji) is an illegal header."""
    return " ".join(title.encode("ascii", "ignore").decode().split()) or "fx-agents"


class JournalAgent(Agent):
    """Writes every trade, management event, Jev decision and equity point to the SQLite journal."""
    name = "journal"

    def start(self):
        super().start()
        b = self.bus
        b.subscribe("position_opened", self.on_open)
        b.subscribe("position_updated", self.on_update)
        b.subscribe("position_closed", self.on_close)
        b.subscribe("decision", self.ctx.journal.add_decision)
        b.subscribe("clock", self.on_clock)
        self._last_eq_min = None

    def _mult(self, pos):
        return float(self.cfg["instruments"][pos.symbol]["multiplier"])

    async def on_open(self, pos):
        self.ctx.journal.upsert_trade(pos, self._mult(pos))

    async def on_update(self, ev):
        self.ctx.journal.upsert_trade(ev["position"], self._mult(ev["position"]))

    async def on_close(self, ev):
        self.ctx.journal.upsert_trade(ev["position"], self._mult(ev["position"]), ev["price"])

    async def on_clock(self, now):
        self.beat()
        eq = await self.ctx.broker.equity()
        st = self.state
        st.equity = eq
        st.equity_peak = max(st.equity_peak or eq, eq)
        if not st.day_start_equity:
            st.day_start_equity = eq
        key = now.floor("5min")
        if key != self._last_eq_min:
            self._last_eq_min = key
            st.equity_curve.append({"ts": now.isoformat(timespec="minutes"), "equity": round(eq, 2)})
            self.ctx.journal.add_equity(now.isoformat(timespec="minutes"), round(eq, 2), round(st.realized_today, 2))


class NotifierAgent(Agent):
    """Pushes to your phone via ntfy and/or Telegram. Silent (log only) when neither is configured."""
    name = "notifier"

    def start(self):
        super().start()
        n = self.cfg["notifications"]
        self.events = set(n.get("events", []))
        self.ntfy = n.get("ntfy_topic") or ""
        self.ntfy_server = n.get("ntfy_server", "https://ntfy.sh")
        self.tg_token = n.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.tg_chat = n.get("telegram_chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.ntfy or (self.tg_token and self.tg_chat)) and self.cfg["mode"] != "sim"
        self.sent: list[dict] = []
        b = self.bus
        b.subscribe("position_opened", self.on_open)
        b.subscribe("position_updated", self.on_update)
        b.subscribe("position_closed", self.on_close)
        b.subscribe("alert", self.on_alert)
        b.subscribe("promotion", lambda e: self.send("promotion", "🧠 Strategy promoted", e["msg"]))
        b.subscribe("daily_summary", lambda e: self.send("daily_summary", "📒 Daily summary", e["msg"]))

    async def send(self, event: str, title: str, body: str, priority: str = "default", record: bool = True):
        self.beat()
        if event not in self.events:
            return
        self.sent.append({"ts": str(self.now()), "event": event, "title": title, "body": body})
        if record:
            self.state.alert("info" if priority == "default" else "warn", f"{title} — {body}", event=event)
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                if self.ntfy:
                    await c.post(f"{self.ntfy_server}/{self.ntfy}", content=body.encode(),
                                 headers={"Title": header_title(title),
                                          "Priority": "high" if priority != "default" else "default",
                                          "Tags": event})
                if self.tg_token and self.tg_chat:
                    await c.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                 json={"chat_id": self.tg_chat, "text": f"*{title}*\n{body}", "parse_mode": "Markdown"})
        except Exception as e:
            self.log.warning("notify failed: %s", e)

    async def on_open(self, pos):
        side = "LONG" if pos.side > 0 else "SHORT"
        await self.send("entry", f"▶ {side} {pos.symbol}",
                        f"{pos.strategy}: {pos.initial_qty:g} @ {pos.entry} SL {pos.stop} "
                        f"(Jev {pos.jev_quality:.2f}/{pos.jev_confidence:.2f} {pos.jev_source})")

    async def on_update(self, ev):
        e = ev["event"]
        if e in ("stop_to_profit", "pyramid"):
            await self.send(e, f"{'🔒' if e == 'stop_to_profit' else '➕'} {ev['position'].symbol}", ev["msg"])

    async def on_close(self, ev):
        p = ev["position"]
        emoji = "✅" if p.realized > 0 else "❌"
        await self.send("exit", f"{emoji} {p.symbol} closed", f"{p.strategy} {p.exit_reason} @ {ev['price']}: "
                                                            f"${p.realized:,.2f} (adds {p.adds}, stage {p.stage})")

    async def on_alert(self, a):
        await self.send(a.get("event", "kill_switch"), a.get("title", "⚠ Alert"), a["msg"], priority="high", record=False)


# These agents only act when there is something to do (a request, a signal, a notification), so a quiet
# heartbeat is normal and not a sign they are down. Feed health is covered by the stale-data check.
EVENT_DRIVEN = {"selector", "risk", "trader", "notifier"}
ALERT_COOLDOWN = 1800.0


class MonitorAgent(Agent):
    """Watches everything: kill switch (daily loss / drawdown), unprotected broker positions,
    stale data, silent agents, day rollover and the daily summary."""
    name = "monitor"

    def start(self):
        super().start()
        self.bus.subscribe("clock", self.on_clock)
        self.day = None
        self.summary_sent = None
        self._last_check = 0.0
        self._orphan_seen: dict[str, int] = {}
        self._alerted: dict[str, float] = {}

    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        st, r = self.state, self.cfg["risk"]
        # trading day rolls at 17:00 NY (CME)
        tday = (now + pd.Timedelta(hours=7)).date()
        if self.day != tday:
            self.day = tday
            st.day_start_equity = st.equity or st.day_start_equity
            st.realized_today = 0.0
            if st.halt_reason.startswith("daily loss"):
                st.trading_enabled, st.halt_reason = True, ""
        if st.day_start_equity and st.trading_enabled:
            day_pnl = st.equity - st.day_start_equity
            if day_pnl <= -r["daily_loss_limit_pct"] * st.day_start_equity:
                await self.kill(f"daily loss limit hit (${day_pnl:,.0f})")
            elif st.equity_peak and st.equity <= st.equity_peak * (1 - r["max_drawdown_pct"]):
                await self.kill(f"max drawdown hit ({st.equity/st.equity_peak-1:.1%} from peak)")
        # daily summary after the NY close
        if now.hour == 16 and now.minute >= 5 and self.summary_sent != now.date():
            self.summary_sent = now.date()
            s = self.ctx.journal.summary(since=now.normalize().isoformat())
            await self.bus.publish("daily_summary", {"msg": f"{s['trades']} trades, P&L ${s['pnl']:,.2f}, "
                                                            f"win {s['win_rate']:.0%}, {s['sum_r']:+.2f}R"})
        # expensive checks at most every 30 s of wall time
        if time.time() - self._last_check < 30:
            return
        self._last_check = time.time()
        # positions at the broker that this process isn't managing (e.g. after a restart)
        known: dict[str, float] = {}
        for p in st.positions.values():
            if p.status == "open":
                known[p.symbol] = known.get(p.symbol, 0) + p.side * p.open_qty
        for sym, q in (await self.ctx.broker.broker_positions()).items():
            if q and abs(q - known.get(sym, 0)) > 1e-9:
                self._orphan_seen[sym] = self._orphan_seen.get(sym, 0) + 1
                if self._orphan_seen[sym] >= 2:          # seen on two checks 30 s apart → not a fill race
                    diff = q - known.get(sym, 0)
                    await self.alert(f"{sym}: {diff:+g} units at the broker not managed by the app — flattening them")
                    try:
                        await self.ctx.broker.flatten_orphan(sym, diff)
                    except Exception as e:  # noqa: BLE001
                        await self.alert(f"{sym}: could not flatten orphan position: {e}")
                    self._orphan_seen[sym] = 0
            else:
                self._orphan_seen.pop(sym, None)
        for sym in await self.ctx.broker.unprotected():
            await self.alert(f"{sym} position has NO working stop at the broker — flattening")
            await self.bus.publish("flatten_symbol", {"symbol": sym, "why": "unprotected"})
        if self.cfg["mode"] != "sim":
            for name, t in st.heartbeats.items():
                if time.time() - t > 300 and name not in EVENT_DRIVEN:
                    await self.alert(f"agent {name} silent for {int(time.time()-t)}s", event="agent_down",
                                     key=f"silent:{name}")
            for sym, ts in st.last_bar_ts.items():
                age = (now - pd.Timestamp(ts)).total_seconds()
                if age > 600 and now.dayofweek < 5 and now.hour != 17:
                    await self.alert(f"{sym} data stale ({int(age)}s)", event="agent_down", key=f"stale:{sym}")

    async def alert(self, msg: str, event: str = "kill_switch", key: str | None = None):
        """`key` de-duplicates a condition that stays true (re-alerts at most every 30 minutes)."""
        if key is not None:
            last = self._alerted.get(key)
            if last is not None and time.time() - last < ALERT_COOLDOWN:
                return
            self._alerted[key] = time.time()
        self.state.alert("error", msg)
        await self.bus.publish("alert", {"msg": msg, "event": event, "title": "⚠ FX-Agents"})

    async def kill(self, why: str):
        self.state.trading_enabled = False
        self.state.halt_reason = why
        await self.alert(f"KILL SWITCH: {why}. Flattening all positions; no new entries today.")
        await self.bus.publish("flatten_all", why)
