"""Copy engine: mirrors the live book's trades onto members' own OANDA accounts (live site only).

The live book is the master. Its own Risk agent and position manager decide everything. This engine only follows
their published events, and only for members who pass every switch in members.MemberStore.active():

  position_opened   → each member: size from THEIR equity × their risk % (× the master's risk multiplier, e.g. half
                      size on news days), capped by their max units and the instrument's; same stop. Skipped (and
                      recorded) when the master entry is more than 60 s old, the member's daily loss limit is hit, the
                      size rounds below OANDA's minimum, or the key fails.
  position_updated  partial → the same share of the member's position; stop moved → the member's stop moves to the
                      same price (only ever toward profit); pyramid adds are NOT copied.
  position_closed   → member closes at market.
  clock             → member stop fills are booked; anything a member still holds at the 15:50 flatten is closed.

Every member has their own OandaClient (their key, decrypted only in memory), their own OandaBroker, state and bus,
so a member's error never touches the master or another member. Member work runs in background tasks: the master's
bus handlers never wait on a member's network call. Open copies are saved (copies.state) and adopted again after a
restart, like the master's own positions. Tokens never reach a log line or an alert.
"""
from __future__ import annotations

import asyncio
import json
import logging

import pandas as pd

from ..agents.core import Agent
from ..agents.trading import _hm, floor_step, qty_rules
from ..broker import OrderRejected
from ..bus import Bus
from ..models import Position
from ..state import LiveState, pos_from_dict, pos_to_dict
from .members import MemberStore

log = logging.getLogger("copier")
MAX_AGE_S = 60


class _Member:
    def __init__(self, uid: int, broker, client, state: LiveState, bus: Bus, stamp) -> None:
        self.uid, self.broker, self.client, self.state, self.bus, self.stamp = uid, broker, client, state, bus, stamp
        self.positions: dict[str, tuple[int, Position]] = {}      # master id → (copy row id, member position)


class CopyEngine(Agent):
    name = "copier"

    def __init__(self, ctx, store: MemberStore, client_factory=None) -> None:
        super().__init__(ctx)
        self.store = store
        self.members: dict[int, _Member] = {}
        self.tasks: set[asyncio.Task] = set()
        self._client_factory = client_factory           # tests: (token, account, env) → OandaClient on a fake transport
        self._ready = False

    def start(self):
        super().start()
        for topic, fn in (("position_opened", self.on_opened), ("position_updated", self.on_updated),
                          ("position_closed", self.on_closed), ("clock", self.on_clock)):
            self.bus.subscribe(topic, fn)

    # ── plumbing ──
    def _spawn(self, coro) -> None:
        t = asyncio.ensure_future(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)

    async def drain(self) -> None:
        """Wait for every member task in flight (tests, shutdown)."""
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def _alert(self, msg: str) -> None:
        self.state.alert("warn", msg)
        try:
            await self.bus.publish("alert", {"msg": msg, "event": "copier", "title": "⚠ FX-Agents live — members"})
        except Exception:  # noqa: BLE001
            pass

    async def member(self, m: dict) -> _Member:
        """The member's own broker; rebuilt when their key changes."""
        from ..oanda import OandaBroker, OandaClient
        uid, stamp = int(m["user_id"]), (m.get("account_id"), m.get("verified"), m.get("environment"))
        cur = self.members.get(uid)
        if cur is not None and cur.stamp == stamp:
            return cur
        token = self.store.token(uid)
        if not token:
            raise OrderRejected("no key on file")
        env = m.get("environment") or "live"
        client = (self._client_factory or (lambda t, a, e: OandaClient(t, a, e)))(token, m["account_id"], env)
        del token
        st, bus = LiveState(mode=self.cfg["mode"]), Bus()
        st.now = self.state.now
        st.last_prices = self.state.last_prices                      # same live prices as the master
        broker = OandaBroker(self.cfg, st, bus, client, None)
        await broker.connect()
        mem = _Member(uid, broker, client, st, bus, stamp)
        bus.subscribe("stop_filled", lambda ev, mem=mem: self._member_stop(mem, ev))
        if cur is not None:                                          # key replaced: carry its open copies over
            mem.positions = cur.positions
            try:
                await cur.client.aclose()
            except Exception:  # noqa: BLE001
                pass
        self.members[uid] = mem
        return mem

    def _save(self, cid: int, mp: Position) -> None:
        self.store.db.execute("UPDATE copies SET state=? WHERE id=?", (json.dumps(pos_to_dict(mp)), cid))
        self.store.db.commit()

    async def restore(self) -> int:
        """After a restart: adopt every copy still open (its member broker books whatever closed meanwhile)."""
        cols = {r[1] for r in self.store.db.execute("PRAGMA table_info(copies)")}
        if "state" not in cols:
            self.store.db.execute("ALTER TABLE copies ADD COLUMN state TEXT")
            self.store.db.commit()
        n = 0
        for r in self.store.db.execute("SELECT id, user_id, master_id, state FROM copies WHERE status='open'").fetchall():
            try:
                m = self.store.get(int(r["user_id"]))
                mem = await self.member(m)
                mp = pos_from_dict(json.loads(r["state"]))
                mem.positions[r["master_id"]] = (int(r["id"]), mp)
                await mem.broker.adopt([mp])
                n += 1
            except Exception as e:  # noqa: BLE001
                self.store.set_error(int(r["user_id"]), f"restore after restart: {type(e).__name__}")
                await self._alert(f"member #{r['user_id']}: an open copy could not be re-attached after the restart — "
                                  "check their OANDA account")
        self._ready = True
        return n

    # ── master events ──
    async def on_opened(self, pos: Position):
        for m in self.store.active(pos.symbol):
            self._spawn(self._open(m, pos))

    async def _open(self, m: dict, pos: Position) -> None:
        uid = int(m["user_id"])
        now = self.state.now
        if now is not None and (now - pd.Timestamp(pos.opened_ts)).total_seconds() > MAX_AGE_S:
            self.store.add_copy(uid, pos.id, None, pos.symbol, pos.side, 0, None, pos.stop, "skipped", "master entry too old")
            return
        try:
            mem = await self.member(m)
            mem.state.now = now
            eq = await mem.broker.equity()
            if eq is None or eq <= 0:
                raise OrderRejected("account equity unavailable")
            day = (now + pd.Timedelta(hours=7)).normalize().date().isoformat() if now is not None else ""
            if mem.state.trading_day != day:
                mem.state.trading_day, mem.state.day_start_equity = day, eq
            if eq <= mem.state.day_start_equity * (1 - float(m["daily_loss_pct"])):
                self.store.add_copy(uid, pos.id, None, pos.symbol, pos.side, 0, None, pos.stop, "skipped",
                                    "member's daily loss limit reached")
                return
            ic = self.cfg["instruments"][pos.symbol]
            step, min_u = qty_rules(ic)
            per_unit = pos.risk_per_unit * float(ic["multiplier"])
            qty = eq * float(m["risk_pct"]) * float(pos.risk_mult or 1.0) / per_unit if per_unit > 0 else 0.0
            qty = floor_step(min(qty, float(m["max_units"]), float(ic.get("max_units", qty))), step)
            if qty < min_u:
                self.store.add_copy(uid, pos.id, None, pos.symbol, pos.side, qty, None, pos.stop, "skipped",
                                    f"size {qty:g} is below OANDA's minimum for this risk")
                return
            mp = Position(pos.symbol, pos.side, pos.strategy, pos.stop, pos.initial_stop, pos.risk_per_unit, pos.rr, now,
                          reason=f"copy of {pos.id}")
            mp.meta["master"] = pos.id
            ref = self.state.last_prices.get(pos.symbol, pos.entry)
            px = await mem.broker.open(mp, qty, ref)
            mp.last_price = px
            mp.log(now, "entry", price=px, qty=qty, stop=mp.stop, master=pos.id)
            cid = self.store.add_copy(uid, pos.id, mp.id, pos.symbol, pos.side, qty, px, mp.stop, "open")
            mem.positions[pos.id] = (cid, mp)
            self._save(cid, mp)
            self.store.set_error(uid, None)
        except Exception as e:  # noqa: BLE001 — a member's failure never reaches the master
            why = str(e) if isinstance(e, OrderRejected) else type(e).__name__
            self.store.add_copy(uid, pos.id, None, pos.symbol, pos.side, 0, None, pos.stop, "failed", why)
            self.store.set_error(uid, f"entry not copied: {why}")
            await self._alert(f"member #{uid}: {pos.symbol} entry not copied ({why[:120]})")

    async def on_updated(self, ev: dict):
        pos, kind = ev.get("position"), ev.get("event")
        if pos is None or kind not in ("partial", "manual_partial", "stop_to_profit", "manual_stop"):
            return
        for mem in list(self.members.values()):
            link = mem.positions.get(pos.id)
            if link:
                self._spawn(self._follow(mem, link, pos, kind, ev.get("frac")))

    async def _follow(self, mem: _Member, link, pos: Position, kind: str, frac=None) -> None:
        cid, mp = link
        if mp.status != "open":
            return
        mem.state.now = self.state.now
        try:
            if kind in ("partial", "manual_partial"):
                step, min_u = qty_rules(self.cfg["instruments"][mp.symbol])
                if kind == "manual_partial":            # the owner banked a share of the trade by hand: same share
                    part = floor_step(mp.open_qty * float(frac or 0), step)
                    ok = min_u <= part < mp.open_qty
                else:
                    part = floor_step(mp.initial_qty * float(self.cfg["management"]["partial_at_target"]), step)
                    ok = part >= min_u and not mp.partial_done
                if ok:
                    px = await mem.broker.reduce(mp, part, self.state.last_prices.get(mp.symbol, mp.entry))
                    if px is not None:
                        mp.partial_done = mp.partial_done or kind == "partial"
                        mp.log(self.state.now, "partial", price=px, qty=part)
                        self.store.copy_event(cid, "partial", price=px, qty=part)
            if (pos.stop - mp.stop) * mp.side > 0:
                await mem.broker.move_stop(mp, pos.stop)
                mp.log(self.state.now, "stop_moved", stop=mp.stop)
                self.store.copy_event(cid, "stop_moved", stop=mp.stop)
            self._save(cid, mp)
        except Exception as e:  # noqa: BLE001
            why = str(e) if isinstance(e, OrderRejected) else type(e).__name__
            self.store.copy_event(cid, "follow_failed", what=kind, why=why[:200])
            await self._alert(f"member #{mem.uid}: {mp.symbol} {kind} not copied ({why[:120]})")

    async def on_closed(self, ev: dict):
        pos = ev.get("position")
        if pos is None:
            return
        for mem in list(self.members.values()):
            link = mem.positions.get(pos.id)
            if link:
                self._spawn(self._close(mem, link, pos.id, ev.get("price"), f"master closed ({pos.exit_reason})"))

    async def _close(self, mem: _Member, link, master_id: str, price, why: str) -> None:
        cid, mp = link
        if mp.status != "open":
            mem.positions.pop(master_id, None)
            return
        mem.state.now = self.state.now
        try:
            px = await mem.broker.close(mp, self.state.last_prices.get(mp.symbol, price or mp.entry))
        except Exception as e:  # noqa: BLE001 — retried on the next clock tick
            mp.meta["pending_close"] = why
            self.store.copy_event(cid, "close_failed", why=(str(e) if isinstance(e, OrderRejected) else type(e).__name__)[:200])
            self._save(cid, mp)
            return
        self._finish(mem, master_id, cid, mp, px, why)

    def _finish(self, mem: _Member, master_id: str, cid: int, mp: Position, px: float, why: str) -> None:
        mp.status, mp.exit_reason, mp.closed_ts = "closed", why, self.state.now
        mult = float(self.cfg["instruments"][mp.symbol]["multiplier"])
        risk = mp.risk_per_unit * mult * (mp.initial_qty or 1)
        r = round(mp.realized / risk, 3) if risk else None
        self.store.close_copy(cid, px, round(mp.realized, 2), r)
        self._save(cid, mp)
        mem.positions.pop(master_id, None)

    async def _member_stop(self, mem: _Member, ev: dict) -> None:
        mp: Position = ev["position"]
        for mid, (cid, p) in list(mem.positions.items()):
            if p is mp:
                self._finish(mem, mid, cid, mp, ev["price"], ev.get("reason") or "stop")

    async def on_clock(self, now):
        if not self.members:
            return
        s = self.cfg["sessions"]
        mins = now.hour * 60 + now.minute
        flat = _hm(s["flatten_at"]) <= mins < 17 * 60
        for mem in list(self.members.values()):
            mem.state.now = now
            try:
                await mem.bus.publish("clock", now)          # the member broker books its own stop fills
            except Exception:  # noqa: BLE001
                pass
            for mid, link in list(mem.positions.items()):
                mp = link[1]
                if mp.status == "open" and (flat or mp.meta.get("pending_close")):
                    self._spawn(self._close(mem, link, mid, None, mp.meta.get("pending_close") or "session flat"))

    async def stop(self) -> None:
        await self.drain()
        for mem in self.members.values():
            try:
                await mem.client.aclose()
            except Exception:  # noqa: BLE001
                pass


def install(ctx, store: MemberStore) -> CopyEngine:
    """Wire the engine onto the live book (main.py, live site only)."""
    eng = CopyEngine(ctx, store)
    eng.start()
    ctx.copier = eng
    asyncio.ensure_future(eng.restore())
    log.info("copy engine on (members copy only when the owner's switch, their approval and their own switch are on)")
    return eng

