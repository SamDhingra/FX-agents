"""Execution. Two brokers with one interface:

* PaperBroker — simulated fills; stops are checked against every 1-minute bar.
* IBKRBroker  — Interactive Brokers via ib_async. The protective stop is a real resting STP order at
  IBKR (GTC), attached as a child of the entry, so the position stays protected even if this app,
  your laptop or the network dies.

Both enforce the hard rules a second time (defence in depth): no stop → no order; stop on the wrong
side → no order; stop wider than the max % of trade value → no order; stops only ever move toward profit.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .models import Bar, Leg, Position

log = logging.getLogger("broker")


class OrderRejected(Exception):
    pass


class Broker:
    def __init__(self, cfg, state, bus) -> None:
        self.cfg, self.state, self.bus = cfg, state, bus
        self.inst = cfg["instruments"]
        self.max_stop_pct = cfg["risk"]["max_stop_pct_of_trade_value"]

    def mult(self, sym: str) -> float:
        return float(self.inst[sym]["multiplier"])

    def round_px(self, sym: str, px: float) -> float:
        t = float(self.inst[sym]["tick_size"])
        return round(round(px / t) * t, 10)

    def commission(self, sym: str, qty: float) -> float:
        return float(self.inst[sym].get("commission_per_unit", 0)) * abs(qty)

    def guard_entry(self, sym: str, side: int, price: float, stop: float | None) -> None:
        if stop is None:
            raise OrderRejected("every trade needs a stop loss")
        if (price - stop) * side <= 0:
            raise OrderRejected(f"stop {stop} is on the wrong side of entry {price}")
        if abs(price - stop) / price > self.max_stop_pct:
            raise OrderRejected(f"stop distance {abs(price-stop)/price:.2%} exceeds {self.max_stop_pct:.0%} of trade value")

    @staticmethod
    def guard_stop_move(pos: Position, new_stop: float) -> None:
        if (new_stop - pos.stop) * pos.side < 0:
            raise OrderRejected("stops may only move toward profit")

    # interface
    async def connect(self) -> None: ...
    async def equity(self) -> float: raise NotImplementedError
    async def open(self, pos: Position, qty: float, ref_price: float) -> float: raise NotImplementedError
    async def add(self, pos: Position, qty: float, ref_price: float) -> float: raise NotImplementedError
    async def reduce(self, pos: Position, qty: float, ref_price: float, limit: float | None = None) -> float | None: raise NotImplementedError   # None = nothing filled
    async def close(self, pos: Position, ref_price: float, limit: float | None = None) -> float: raise NotImplementedError
    async def move_stop(self, pos: Position, new_stop: float) -> None: raise NotImplementedError
    async def on_bar(self, bar: Bar) -> None: ...
    async def broker_positions(self) -> dict[str, float]: return {}
    async def unprotected(self) -> list[str]: return []
    async def flatten_orphan(self, sym: str, qty: float) -> None: ...
    async def quote(self, sym: str) -> tuple[float, float] | None: return None       # fresh (bid, ask) if the broker has one
    async def adopt(self, positions: list[Position]) -> bool: return False           # re-manage persisted positions after a restart


class PaperBroker(Broker):
    def __init__(self, cfg, state, bus, slippage_ticks: float = 1.0) -> None:
        super().__init__(cfg, state, bus)
        self.cash = float(cfg.get("starting_equity", 100000))
        self.slip = slippage_ticks
        self.open_positions: dict[str, Position] = {}
        self.on_stop: Callable | None = None

    def _slip(self, sym: str, side: int) -> float:
        return side * self.slip * float(self.inst[sym]["tick_size"])

    async def equity(self) -> float:
        u = sum(p.unrealized(self.state.last_prices.get(p.symbol, p.entry), self.mult(p.symbol))
                for p in self.open_positions.values())
        return self.cash + u

    def _book(self, pos: Position, qty: float, px: float) -> float:
        pnl = (px - pos.avg_entry) * pos.side * qty * self.mult(pos.symbol)
        fee = self.commission(pos.symbol, qty)
        pos.closed_qty += qty
        pos.realized += pnl - fee
        pos.commissions += fee
        self.cash += pnl - fee
        return pnl - fee

    async def open(self, pos, qty, ref_price):
        px = self.round_px(pos.symbol, ref_price + self._slip(pos.symbol, pos.side))
        self.guard_entry(pos.symbol, pos.side, px, pos.stop)
        pos.add_leg(Leg(qty, px, self.state.now, "initial"))
        fee = self.commission(pos.symbol, qty)
        pos.realized -= fee; pos.commissions += fee; self.cash -= fee
        self.open_positions[pos.id] = pos
        return px

    async def add(self, pos, qty, ref_price):
        px = self.round_px(pos.symbol, ref_price + self._slip(pos.symbol, pos.side))
        pos.add_leg(Leg(qty, px, self.state.now, "pyramid"))
        fee = self.commission(pos.symbol, qty)
        pos.realized -= fee; pos.commissions += fee; self.cash -= fee
        return px

    async def reduce(self, pos, qty, ref_price, limit=None):
        if pos.open_qty <= 0:
            return None                          # nothing left to reduce
        px = limit if limit is not None else ref_price - self._slip(pos.symbol, pos.side)
        px = self.round_px(pos.symbol, px)
        self._book(pos, min(qty, pos.open_qty), px)
        return px

    async def close(self, pos, ref_price, limit=None):
        px = self.round_px(pos.symbol, limit if limit is not None else ref_price - self._slip(pos.symbol, pos.side))
        if pos.open_qty > 0:
            self._book(pos, pos.open_qty, px)
        self.open_positions.pop(pos.id, None)
        return px

    async def move_stop(self, pos, new_stop):
        self.guard_stop_move(pos, new_stop)
        pos.stop = self.round_px(pos.symbol, new_stop)

    async def on_bar(self, bar: Bar) -> None:
        for pos in list(self.open_positions.values()):
            if pos.symbol != bar.symbol or pos.open_qty <= 0:
                continue
            hit = bar.low <= pos.stop if pos.side > 0 else bar.high >= pos.stop
            if hit:
                gap = bar.open if (bar.open - pos.stop) * pos.side < 0 else pos.stop
                px = self.round_px(pos.symbol, gap - self._slip(pos.symbol, pos.side))
                self._book(pos, pos.open_qty, px)
                self.open_positions.pop(pos.id, None)
                await self.bus.publish("stop_filled", {"position": pos, "price": px, "ts": bar.ts})

    async def broker_positions(self):
        out: dict[str, float] = {}
        for p in self.open_positions.values():
            out[p.symbol] = out.get(p.symbol, 0) + p.side * p.open_qty
        return out


class IBKRBroker(Broker):
    """Live/paper execution at Interactive Brokers."""

    def __init__(self, cfg, state, bus, ib, feed) -> None:
        super().__init__(cfg, state, bus)
        self.ib, self.feed = ib, feed
        self.account = cfg["ibkr"].get("account") or ""
        self._stop_ids: dict[int, Position] = {}

    async def connect(self) -> None:
        self.ib.execDetailsEvent += self._on_exec

    def _c(self, sym):
        return self.feed.trade_contracts[sym]

    async def equity(self) -> float:
        for v in self.ib.accountValues(self.account):
            if v.tag == "NetLiquidation" and v.currency in ("USD", "BASE"):
                return float(v.value)
        return self.state.equity

    async def _fill(self, trade, timeout: float = 20) -> float:
        for _ in range(int(timeout * 10)):
            if trade.orderStatus.status == "Filled":
                return float(trade.orderStatus.avgFillPrice)
            if trade.orderStatus.status in ("Cancelled", "ApiCancelled", "Inactive"):
                raise OrderRejected(f"order {trade.order.orderId} {trade.orderStatus.status}: {trade.log[-1].message if trade.log else ''}")
            await asyncio.sleep(0.1)
        raise OrderRejected("fill timeout")

    async def open(self, pos, qty, ref_price):
        from ib_async import MarketOrder, StopOrder
        sym = pos.symbol
        stop = self.round_px(sym, pos.stop)
        self.guard_entry(sym, pos.side, ref_price, stop)
        act, opp = ("BUY", "SELL") if pos.side > 0 else ("SELL", "BUY")
        parent = MarketOrder(act, qty, account=self.account, transmit=False)
        parent.orderId = self.ib.client.getReqId()
        child = StopOrder(opp, qty, stop, account=self.account, parentId=parent.orderId,
                          tif="GTC", outsideRth=True, transmit=True)
        t_parent = self.ib.placeOrder(self._c(sym), parent)
        t_stop = self.ib.placeOrder(self._c(sym), child)
        px = await self._fill(t_parent)
        pos.add_leg(Leg(qty, px, self.state.now, "initial"))
        pos.meta["stop_trade"] = t_stop
        self._stop_ids[t_stop.order.orderId] = pos
        return px

    async def _resize_stop(self, pos: Position, qty: float | None = None, price: float | None = None):
        t = pos.meta["stop_trade"]
        o = t.order
        if qty is not None:
            o.totalQuantity = qty
        if price is not None:
            o.auxPrice = self.round_px(pos.symbol, price)
        o.transmit = True
        self.ib.placeOrder(self._c(pos.symbol), o)

    async def add(self, pos, qty, ref_price):
        from ib_async import MarketOrder
        act = "BUY" if pos.side > 0 else "SELL"
        t = self.ib.placeOrder(self._c(pos.symbol), MarketOrder(act, qty, account=self.account))
        px = await self._fill(t)
        pos.add_leg(Leg(qty, px, self.state.now, "pyramid"))
        await self._resize_stop(pos, qty=pos.open_qty)
        return px

    async def reduce(self, pos, qty, ref_price, limit=None):
        from ib_async import MarketOrder
        act = "SELL" if pos.side > 0 else "BUY"
        qty = min(qty, pos.open_qty)
        await self._resize_stop(pos, qty=pos.open_qty - qty)  # shrink protection first
        t = self.ib.placeOrder(self._c(pos.symbol), MarketOrder(act, qty, account=self.account))
        px = await self._fill(t)
        self._book(pos, qty, px)
        return px

    def _book(self, pos, qty, px):
        pnl = (px - pos.avg_entry) * pos.side * qty * self.mult(pos.symbol)
        fee = self.commission(pos.symbol, qty)
        pos.closed_qty += qty
        pos.realized += pnl - fee
        pos.commissions += fee

    async def close(self, pos, ref_price, limit=None):
        from ib_async import MarketOrder  # at IBKR every exit is a market order (limit ignored)
        t_stop = pos.meta.get("stop_trade")
        if t_stop is not None:
            self.ib.cancelOrder(t_stop.order)
            self._stop_ids.pop(t_stop.order.orderId, None)
        act = "SELL" if pos.side > 0 else "BUY"
        qty = pos.open_qty
        if qty <= 0:
            return ref_price
        t = self.ib.placeOrder(self._c(pos.symbol), MarketOrder(act, qty, account=self.account))
        px = await self._fill(t)
        self._book(pos, qty, px)
        return px

    async def move_stop(self, pos, new_stop):
        self.guard_stop_move(pos, new_stop)
        await self._resize_stop(pos, price=new_stop)
        pos.stop = self.round_px(pos.symbol, new_stop)

    def _on_exec(self, trade, fill) -> None:
        pos = self._stop_ids.pop(trade.order.orderId, None)
        if pos is None:
            return
        qty = pos.open_qty
        self._book(pos, qty, fill.execution.avgPrice)
        asyncio.ensure_future(self.bus.publish("stop_filled", {"position": pos, "price": fill.execution.avgPrice,
                                                               "ts": self.state.now}))

    async def broker_positions(self):
        out: dict[str, float] = {}
        rev = {c.conId: s for s, c in self.feed.trade_contracts.items()}
        for p in self.ib.positions(self.account):
            s = rev.get(p.contract.conId)
            if s:
                out[s] = out.get(s, 0) + float(p.position)
        return out

    async def flatten_orphan(self, sym: str, qty: float) -> None:
        """Close a broker position this process doesn't know about (e.g. after a restart) and
        cancel its resting orders. Day-trading system: we never carry unknown exposure."""
        from ib_async import MarketOrder
        c = self._c(sym)
        for t in self.ib.openTrades():
            if t.contract.conId == c.conId:
                self.ib.cancelOrder(t.order)
        act = "SELL" if qty > 0 else "BUY"
        t = self.ib.placeOrder(c, MarketOrder(act, abs(qty), account=self.account))
        await self._fill(t)

    async def unprotected(self) -> list[str]:
        """Symbols with a broker position but no working stop order."""
        pos = await self.broker_positions()
        rev = {c.conId: s for s, c in self.feed.trade_contracts.items()}
        protected = set()
        for t in self.ib.openTrades():
            if t.order.orderType in ("STP", "STP LMT", "TRAIL") and t.orderStatus.status not in ("Cancelled", "Filled"):
                s = rev.get(t.contract.conId)
                if s:
                    protected.add(s)
        return [s for s, q in pos.items() if q != 0 and s not in protected]
