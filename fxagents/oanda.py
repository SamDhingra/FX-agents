"""OANDA v20 REST: market data feed + broker.

Same interface as the IBKR pair, so the agents don't know which broker they run on.

* Paper  → https://api-fxpractice.oanda.com   (practice account)
* Live   → https://api-fxtrade.oanda.com
* Auth   → OANDA_API_TOKEN + OANDA_ACCOUNT_ID (from .env)

How protection works at OANDA:
* Every entry is a MARKET order with `stopLossOnFill`: the stop is created by OANDA in the same
  transaction as the fill, so there is never an unprotected moment. After the fill we re-read the
  trade and, if the stop is somehow missing, close it immediately.
* A pyramid add is a new OANDA trade with its own stop at the position's current stop. Moving the
  stop moves it on every trade of the position. Partial exits close units oldest-trade-first.
* Stops rest at OANDA (GTC), so the position stays protected if this app or the server dies.
* Stop fills are detected by polling open trades every clock tick (≈15 s): a managed trade that
  disappeared was closed by its stop (or by you, manually) → booked at OANDA's close price.

Hard rules are enforced again here (defence in depth): no stop → no order; stop on the wrong side
→ no order; stop wider than the max % of trade value → no order; stops only move toward profit.
"""
from __future__ import annotations

import asyncio
import logging
import os
from decimal import ROUND_DOWN, Decimal

import httpx
import pandas as pd

from .broker import Broker, OrderRejected
from .models import Bar, Leg, Position

log = logging.getLogger("oanda")

HOSTS = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}


class OandaError(Exception):
    def __init__(self, status: int, body: dict | str):
        self.status, self.body = status, body
        msg = body.get("errorMessage") if isinstance(body, dict) else str(body)
        code = body.get("errorCode") if isinstance(body, dict) else None
        rej = (body.get("orderRejectTransaction") or {}).get("rejectReason") if isinstance(body, dict) else None
        super().__init__(f"OANDA {status}: {code or ''} {rej or ''} {msg or ''}".strip())


class OandaClient:
    """Thin async v20 REST client with retries on 429/5xx/network errors."""

    def __init__(self, token: str, account_id: str, environment: str = "practice",
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 15.0) -> None:
        if not token or not account_id:
            raise SystemExit("OANDA needs OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env")
        if environment not in HOSTS:
            raise SystemExit(f"OANDA environment must be practice or live, not {environment!r}")
        self.account_id, self.environment = account_id, environment
        self.http = httpx.AsyncClient(
            base_url=HOSTS[environment], transport=transport, timeout=timeout,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept-Datetime-Format": "RFC3339"})

    def acct(self, path: str = "") -> str:
        return f"/v3/accounts/{self.account_id}{path}"

    async def req(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
                  retries: int = 3) -> dict:
        for attempt in range(retries + 1):
            try:
                r = await self.http.request(method, path, params=params, json=json)
            except httpx.TransportError as e:
                if attempt == retries:
                    raise OandaError(0, str(e)) from e
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == retries:
                    raise OandaError(r.status_code, _body(r))
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            body = _body(r)
            if r.status_code >= 400:
                raise OandaError(r.status_code, body)
            return body
        raise OandaError(0, "unreachable")

    async def aclose(self) -> None:
        await self.http.aclose()


def _body(r: httpx.Response) -> dict:
    try:
        return r.json()
    except ValueError:
        return {"errorMessage": r.text[:300]}


def oanda_from_cfg(cfg, transport=None) -> OandaClient:
    oc = cfg.get("oanda", {}) or {}
    env = oc.get("environment") or ("live" if cfg["mode"] == "live" else "practice")
    if cfg["mode"] == "paper" and env == "live":
        raise SystemExit("mode=paper but oanda.environment=live — refusing (use the practice account for paper)")
    return OandaClient(os.environ.get("OANDA_API_TOKEN", "") or oc.get("token", ""),
                       os.environ.get("OANDA_ACCOUNT_ID", "") or oc.get("account_id", ""),
                       env, transport=transport)


def _inst(cfg, sym: str) -> str:
    ic = cfg["instruments"][sym]
    name = ic.get("oanda_instrument") or ic.get("contract", {}).get("instrument")
    if not name:
        raise SystemExit(f"{sym}: set oanda.instrument in config.yaml (e.g. XAU_USD)")
    return name


def _f(x) -> float:
    return float(x) if x not in (None, "") else 0.0


# ─────────────────────────────────────────────────────────────────────────────
class OandaFeed:
    """1-minute mid candles from OANDA. Polls just after each minute closes and publishes every
    completed candle in order (gaps are back-filled from the last bar seen)."""

    def __init__(self, cfg, bus, state, client: OandaClient) -> None:
        self.cfg, self.bus, self.state, self.c = cfg, bus, state, client
        self.tz = cfg["timezone"]
        self.syms = {s: _inst(cfg, s) for s in cfg["instruments"]}
        self.specs: dict[str, dict] = {}
        self._hist: dict[str, pd.DataFrame] = {}
        self._h1: dict[str, pd.DataFrame] = {}
        self.last_ts: dict[str, pd.Timestamp] = {}
        self.poll_seconds = float((cfg.get("oanda") or {}).get("poll_seconds", 5))

    async def qualify(self) -> None:
        """Read precision/min size per instrument and write them into the instrument config so
        sizing and price rounding match what OANDA accepts."""
        names = ",".join(self.syms.values())
        res = await self.c.req("GET", self.c.acct("/instruments"), params={"instruments": names})
        by = {i["name"]: i for i in res.get("instruments", [])}
        for sym, name in self.syms.items():
            i = by.get(name)
            if i is None:
                raise SystemExit(f"{sym}: instrument {name} is not tradeable on this OANDA account "
                                 f"(available here: {', '.join(sorted(by)) or 'none'})")
            ic = self.cfg["instruments"][sym]
            dp, up = int(i.get("displayPrecision", 2)), int(i.get("tradeUnitsPrecision", 0))
            ic["tick_size"] = 10 ** -dp
            ic["qty_step"] = 10 ** -up
            ic["min_units"] = max(_f(i.get("minimumTradeSize", 1)), ic["qty_step"])
            ic["margin_rate"] = _f(i.get("marginRate"))
            self.specs[sym] = i
            log.info("%s → %s  price dp=%d  units step=%g  min=%g  margin=%.1f%%", sym, name, dp,
                     ic["qty_step"], ic["min_units"], 100 * ic["margin_rate"])

    async def candles(self, name: str, gran: str, *, start: pd.Timestamp | None = None,
                      count: int = 500) -> list[dict]:
        p = {"granularity": gran, "price": "M", "count": str(count)}
        if start is not None:
            p["from"] = start.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
            p["includeFirst"] = "false"
        res = await self.c.req("GET", f"/v3/instruments/{name}/candles", params=p)
        return res.get("candles", [])

    def _frame(self, cs: list[dict], vol: bool = True) -> pd.DataFrame:
        rows = [{"ts": c["time"], "open": _f(c["mid"]["o"]), "high": _f(c["mid"]["h"]), "low": _f(c["mid"]["l"]),
                 "close": _f(c["mid"]["c"]), "volume": float(c.get("volume", 0))} for c in cs if c.get("complete")]
        cols = ["open", "high", "low", "close"] + (["volume"] if vol else [])
        if not rows:
            return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz=self.tz, name="ts"))
        df = pd.DataFrame(rows)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(self.tz)
        df = df.set_index("ts")[cols]
        return df[~df.index.duplicated(keep="last")].sort_index()

    async def _paged(self, name: str, gran: str, start: pd.Timestamp) -> list[dict]:
        out: list[dict] = []
        cur = start
        for _ in range(60):  # 60 × 5000 bars is far more than we ever ask for
            cs = await self.candles(name, gran, start=cur, count=5000)
            if not cs:
                break
            out += cs
            nxt = pd.Timestamp(cs[-1]["time"])
            if len(cs) < 5000 or nxt <= cur:
                break
            cur = nxt
        return out

    async def start(self) -> None:
        now = pd.Timestamp.now(tz="UTC")
        days = int(self.cfg["timeframes"]["history_days"])
        h1d = int(self.cfg["timeframes"].get("h1_history_days", 45))
        for sym, name in self.syms.items():
            m1 = self._frame(await self._paged(name, "M1", now - pd.Timedelta(days=days)))
            h1 = self._frame(await self._paged(name, "H1", now - pd.Timedelta(days=h1d)), vol=False)
            self._hist[sym], self._h1[sym] = m1, h1
            if len(m1):
                self.last_ts[sym] = m1.index[-1]
            log.info("%s: %d historical 1m bars, %d hourly bars", sym, len(m1), len(h1))

    def history(self, symbol: str) -> pd.DataFrame:
        return self._hist[symbol]

    def h1_history(self, symbol: str) -> pd.DataFrame:
        return self._h1[symbol]

    async def poll_once(self) -> int:
        """Publish every newly completed 1m candle. Returns how many were published."""
        n = 0
        for sym, name in self.syms.items():
            since = self.last_ts.get(sym)
            try:
                cs = await self.candles(name, "M1", start=since, count=500 if since is not None else 3)
            except OandaError as e:
                log.warning("%s candles: %s", sym, e)
                continue
            df = self._frame(cs)
            if since is not None:
                df = df[df.index > since]
            for ts, r in df.iterrows():
                self.state.now = pd.Timestamp.now(tz=self.tz)
                await self.bus.publish("bar", Bar(sym, ts, r.open, r.high, r.low, r.close, float(r.volume)))
                self.last_ts[sym] = ts
                n += 1
        return n

    async def run(self) -> None:
        last_clock = 0.0
        next_poll = 0.0
        loop = asyncio.get_running_loop()
        while True:
            now = pd.Timestamp.now(tz=self.tz)
            # candles complete on the minute; poll a couple of seconds after, then every few seconds
            # until every symbol has its bar. When nothing new arrives (weekend, daily break) back off.
            if (now.second >= 2 or not self.last_ts) and loop.time() >= next_poll:
                want = (now.floor("min") - pd.Timedelta("1min"))
                if any(self.last_ts.get(s) is None or self.last_ts[s] < want for s in self.syms):
                    got = await self.poll_once()
                    next_poll = loop.time() + (0 if got else 30)
            if loop.time() - last_clock >= 15:
                last_clock = loop.time()
                self.state.now = pd.Timestamp.now(tz=self.tz)
                await self.bus.publish("clock", self.state.now)
            await asyncio.sleep(self.poll_seconds)


# ─────────────────────────────────────────────────────────────────────────────
class OandaBroker(Broker):
    """Practice/live execution at OANDA (CFDs: XAU_USD, SPX500_USD, NAS100_USD, US30_USD …)."""

    def __init__(self, cfg, state, bus, client: OandaClient, feed: OandaFeed | None = None) -> None:
        super().__init__(cfg, state, bus)
        self.c, self.feed = client, feed
        self.names = {s: _inst(cfg, s) for s in cfg["instruments"]}
        self.rev = {v: k for k, v in self.names.items()}
        oc = cfg.get("oanda") or {}
        self.position_fill = oc.get("position_fill", "DEFAULT")
        self.client_ext = bool(oc.get("client_extensions", True))
        self.managed: dict[str, Position] = {}        # trade id → position
        self.currency = "USD"
        self._fx_cache: tuple[float, float] | None = None   # (rate, loop time)
        self._checking = False

    async def connect(self) -> None:
        s = (await self.c.req("GET", self.c.acct("/summary")))["account"]
        self.currency = s.get("currency", "USD")
        if s.get("hedgingEnabled") is False and self.position_fill == "OPEN_ONLY":
            log.info("account is not hedging-enabled; OPEN_ONLY still prevents an entry from closing another trade")
        self.bus.subscribe("clock", self.on_clock)
        log.info("OANDA %s account %s (%s), NAV %s %s", self.c.environment, self.c.account_id,
                 s.get("alias") or "", s.get("NAV"), self.currency)

    # ── formatting ──
    def _px(self, sym: str, px: float) -> str:
        t = Decimal(str(self.inst[sym]["tick_size"]))
        return str((Decimal(str(px)) / t).quantize(Decimal(1)) * t)

    def _units(self, sym: str, qty: float) -> str:
        step = Decimal(str(self.inst[sym].get("qty_step", 1)))
        q = (Decimal(str(abs(qty))) / step).to_integral_value(rounding=ROUND_DOWN) * step
        return format(q.normalize(), "f")

    # ── account ──
    async def _usd_rate(self) -> float:
        """Account currency → USD (sizing and P&L are in USD, the instruments' quote currency)."""
        if self.currency == "USD":
            return 1.0
        loop = asyncio.get_running_loop()
        if self._fx_cache and loop.time() - self._fx_cache[1] < 300:
            return self._fx_cache[0]
        for name, invert in ((f"USD_{self.currency}", True), (f"{self.currency}_USD", False)):
            try:
                p = (await self.c.req("GET", self.c.acct("/pricing"), params={"instruments": name}))["prices"][0]
                mid = (_f(p["closeoutBid"]) + _f(p["closeoutAsk"])) / 2
                rate = 1 / mid if invert else mid
                self._fx_cache = (rate, loop.time())
                return rate
            except (OandaError, KeyError, IndexError, ZeroDivisionError):
                continue
        log.warning("no %s→USD rate; treating equity as USD", self.currency)
        return 1.0

    async def equity(self) -> float:
        try:
            s = (await self.c.req("GET", self.c.acct("/summary")))["account"]
        except OandaError as e:
            log.warning("summary: %s", e)
            return self.state.equity
        return _f(s["NAV"]) * await self._usd_rate()

    # ── orders ──
    async def _market(self, pos: Position, qty: float, kind: str) -> tuple[float, str, float]:
        sym = pos.symbol
        units = self._units(sym, qty)
        if Decimal(units) <= 0 or float(units) < float(self.inst[sym].get("min_units", 0)):
            raise OrderRejected(f"{qty:g} units is below OANDA's minimum for {self.names[sym]}")
        stop = self._px(sym, pos.stop)
        body = {"order": {"type": "MARKET", "instrument": self.names[sym],
                          "units": units if pos.side > 0 else f"-{units}",
                          "timeInForce": "FOK", "positionFill": self.position_fill,
                          "stopLossOnFill": {"price": stop, "timeInForce": "GTC"}}}
        if self.client_ext:   # MT4-linked accounts reject client extensions → oanda.client_extensions: false
            body["order"]["tradeClientExtensions"] = {"tag": "fxagents", "comment": f"{pos.id} {kind}"[:120]}
        try:
            res = await self.c.req("POST", self.c.acct("/orders"), json=body, retries=0)
        except OandaError as e:
            raise OrderRejected(str(e)) from e
        fill = res.get("orderFillTransaction")
        if not fill:
            why = (res.get("orderCancelTransaction") or {}).get("reason", "not filled")
            raise OrderRejected(f"OANDA cancelled the order: {why}")
        opened = fill.get("tradeOpened")
        if not opened:
            # the fill reduced/closed something else instead of opening a trade → never acceptable
            raise OrderRejected("OANDA fill did not open a new trade (it offset an existing one) — check the account")
        tid = str(opened["tradeID"])
        px = _f(opened.get("price") or fill.get("price"))
        filled = abs(_f(opened.get("units")))
        # belt and braces: the stop must exist at OANDA, otherwise get out immediately
        tr = (await self.c.req("GET", self.c.acct(f"/trades/{tid}")))["trade"]
        if not (tr.get("stopLossOrder") or tr.get("guaranteedStopLossOrder")):
            await self.c.req("PUT", self.c.acct(f"/trades/{tid}/close"), json={"units": "ALL"})
            raise OrderRejected(f"trade {tid} had no stop at OANDA — closed it immediately")
        return px, tid, filled

    async def open(self, pos, qty, ref_price):
        sym = pos.symbol
        self.guard_entry(sym, pos.side, ref_price, pos.stop)      # no stop → rejected before anything else
        stop = float(self._px(sym, pos.stop))
        self.guard_entry(sym, pos.side, ref_price, stop)          # and again after rounding to OANDA precision
        for p in self.managed.values():
            if p.symbol == sym and p.side != pos.side and p.status == "open":
                raise OrderRejected(f"already {('long' if p.side > 0 else 'short')} {sym}; no opposite-side entry")
        pos.stop = stop
        px, tid, filled = await self._market(pos, qty, "initial")
        pos.legs.append(Leg(filled, px, self.state.now, "initial"))
        pos.meta["trades"] = [{"id": tid, "units": filled}]
        self.managed[tid] = pos
        return px

    async def add(self, pos, qty, ref_price):
        px, tid, filled = await self._market(pos, qty, "pyramid")
        pos.legs.append(Leg(filled, px, self.state.now, "pyramid"))
        pos.meta.setdefault("trades", []).append({"id": tid, "units": filled})
        self.managed[tid] = pos
        return px

    async def _close_trade(self, pos: Position, t: dict, units: str) -> tuple[float, float]:
        """Close `units` ('ALL' or a number) of one trade. Returns (price, units closed)."""
        try:
            res = await self.c.req("PUT", self.c.acct(f"/trades/{t['id']}/close"), json={"units": units})
        except OandaError as e:
            if e.status == 404 or "TRADE_DOESNT_EXIST" in str(e) or "NOT_FOUND" in str(e):
                # already closed (its stop was hit a moment ago) → book it at OANDA's price
                tr = (await self.c.req("GET", self.c.acct(f"/trades/{t['id']}")))["trade"]
                n = t["units"]
                t["units"] = 0
                self.managed.pop(t["id"], None)
                return _f(tr.get("averageClosePrice")) or self.state.last_prices.get(pos.symbol, pos.entry), n
            raise OrderRejected(str(e)) from e
        fill = res.get("orderFillTransaction")
        if not fill:
            why = (res.get("orderCancelTransaction") or {}).get("reason", "not filled")
            raise OrderRejected(f"OANDA close cancelled: {why}")
        n = sum(abs(_f(x.get("units"))) for x in (fill.get("tradesClosed") or []))
        tr = fill.get("tradeReduced")
        if tr:
            n += abs(_f(tr.get("units")))
        n = n or (t["units"] if units == "ALL" else float(units))
        t["units"] = round(t["units"] - n, 9)
        if t["units"] <= 1e-9:
            self.managed.pop(t["id"], None)
        return _f(fill.get("price")), n

    def _book(self, pos: Position, qty: float, px: float) -> float:
        pnl = (px - pos.avg_entry) * pos.side * qty * self.mult(pos.symbol)
        fee = self.commission(pos.symbol, qty)
        pos.closed_qty += qty
        pos.realized += pnl - fee
        pos.commissions += fee
        return pnl - fee

    async def reduce(self, pos, qty, ref_price, limit=None):
        left = float(self._units(pos.symbol, min(qty, pos.open_qty)))
        got, value = 0.0, 0.0
        for t in [t for t in pos.meta.get("trades", []) if t["units"] > 0]:   # oldest first
            if left <= 1e-9:
                break
            take = min(left, t["units"])
            px, n = await self._close_trade(pos, t, "ALL" if take >= t["units"] - 1e-9 else self._units(pos.symbol, take))
            got += n
            value += px * n
            left -= n
        if got <= 0:
            return ref_price
        px = value / got
        self._book(pos, got, px)
        return px

    async def close(self, pos, ref_price, limit=None):
        got, value = 0.0, 0.0
        for t in [t for t in pos.meta.get("trades", []) if t["units"] > 0]:
            px, n = await self._close_trade(pos, t, "ALL")
            got += n
            value += px * n
        if got <= 0:
            return ref_price
        px = value / got
        self._book(pos, min(got, pos.open_qty), px)
        return px

    async def move_stop(self, pos, new_stop):
        self.guard_stop_move(pos, new_stop)
        price = self._px(pos.symbol, new_stop)
        for t in [t for t in pos.meta.get("trades", []) if t["units"] > 0]:
            try:
                await self.c.req("PUT", self.c.acct(f"/trades/{t['id']}/orders"),
                                 json={"stopLoss": {"price": price, "timeInForce": "GTC"}})
            except OandaError as e:
                if e.status == 404:
                    continue   # trade already closed; the clock check books it
                raise OrderRejected(f"could not move stop on trade {t['id']}: {e}") from e
        pos.stop = float(price)

    # ── reconciliation ──
    async def _open_trades(self) -> list[dict]:
        return (await self.c.req("GET", self.c.acct("/openTrades"))).get("trades", [])

    async def on_clock(self, now) -> None:
        if self._checking or not self.managed:
            return
        self._checking = True
        try:
            await self.check_stops()
        except OandaError as e:
            log.warning("stop check: %s", e)
        finally:
            self._checking = False

    async def check_stops(self) -> None:
        """Book trades that OANDA closed (stop hit, manual close, margin closeout)."""
        open_ids = {str(t["id"]) for t in await self._open_trades()}
        gone: dict[str, list[str]] = {}
        for tid, pos in list(self.managed.items()):
            if tid not in open_ids:
                gone.setdefault(pos.id, []).append(tid)
        for pid, tids in gone.items():
            pos = self.managed[tids[0]]
            got, value = 0.0, 0.0
            for tid in tids:
                t = next((x for x in pos.meta.get("trades", []) if x["id"] == tid), None)
                tr = (await self.c.req("GET", self.c.acct(f"/trades/{tid}")))["trade"]
                n = t["units"] if t else abs(_f(tr.get("initialUnits")))
                px = _f(tr.get("averageClosePrice")) or pos.stop
                if t:
                    t["units"] = 0
                self.managed.pop(tid, None)
                got += n
                value += px * n
            if got > 0:
                px = value / got
                self._book(pos, min(got, pos.open_qty), px)
                if not any(t["units"] > 0 for t in pos.meta.get("trades", [])):
                    await self.bus.publish("stop_filled", {"position": pos, "price": round(px, 6),
                                                           "ts": self.state.now})

    async def broker_positions(self) -> dict[str, float]:
        res = await self.c.req("GET", self.c.acct("/openPositions"))
        out: dict[str, float] = {}
        for p in res.get("positions", []):
            sym = self.rev.get(p["instrument"])
            if sym:
                q = _f(p.get("long", {}).get("units")) + _f(p.get("short", {}).get("units"))
                if q:
                    out[sym] = out.get(sym, 0) + q
        return out

    async def unprotected(self) -> list[str]:
        bad = set()
        for t in await self._open_trades():
            sym = self.rev.get(t["instrument"])
            if sym and not (t.get("stopLossOrder") or t.get("guaranteedStopLossOrder")
                            or t.get("trailingStopLossOrder")):
                bad.add(sym)
        return sorted(bad)

    async def flatten_orphan(self, sym: str, qty: float) -> None:
        """Close trades on this instrument that this process doesn't manage (e.g. after a restart)."""
        name = self.names[sym]
        for t in await self._open_trades():
            if t["instrument"] == name and str(t["id"]) not in self.managed:
                await self.c.req("PUT", self.c.acct(f"/trades/{t['id']}/close"), json={"units": "ALL"})
                log.warning("closed unmanaged OANDA trade %s (%s %s units)", t["id"], name, t.get("currentUnits"))
