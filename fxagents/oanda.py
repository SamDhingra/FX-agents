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
  disappeared or shrank was closed by its stop (or by you, manually) → the units the bot hasn't booked
  yet are booked at their own price, derived from OANDA's lifetime averageClosePrice.
* Orders and closes are never blindly re-sent: after a lost response the account is read back and
  whatever actually happened is booked (entries are found again by their client id).

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
LIVE_WINDOW = pd.Timedelta("10min")   # bars older than this are back-filled, never treated as live


class OandaError(Exception):
    def __init__(self, status: int, body: dict | str):
        self.status, self.body = status, body
        msg = body.get("errorMessage") if isinstance(body, dict) else str(body)
        code = body.get("errorCode") if isinstance(body, dict) else None
        rej = (body.get("orderRejectTransaction") or {}).get("rejectReason") if isinstance(body, dict) else None
        super().__init__(f"OANDA {status}: {code or ''} {rej or ''} {msg or ''}".strip())


class OandaClient:
    """Thin async v20 REST client. GETs retry on 429/5xx/network errors; POST/PUT retry only on 429."""

    def __init__(self, token: str, account_id: str, environment: str = "practice",
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 15.0) -> None:
        if not token or not account_id:
            raise SystemExit("OANDA needs OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env")
        if environment not in HOSTS:
            raise SystemExit(f"OANDA environment must be practice or live, not {environment!r}")
        self.account_id, self.environment = account_id, environment
        self.backoff = 1.5                       # seconds × attempt between retries (tests set 0)
        self.http = httpx.AsyncClient(
            base_url=HOSTS[environment], transport=transport, timeout=timeout,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept-Datetime-Format": "RFC3339"})

    def acct(self, path: str = "") -> str:
        return f"/v3/accounts/{self.account_id}{path}"

    async def req(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
                  retries: int = 3) -> dict:
        """A mutating request (POST order, PUT close/stop) is never re-sent after a network error or a 5xx:
        the first attempt may have executed and only its response was lost. It raises (status 0 or ≥500,
        see `ambiguous`) and the caller reads the account to find out what happened. 429 = not executed →
        retried for every method."""
        safe = method.upper() == "GET"
        for attempt in range(retries + 1):
            try:
                r = await self.http.request(method, path, params=params, json=json)
            except httpx.TransportError as e:
                if attempt == retries or not safe:
                    raise OandaError(0, str(e)) from e
                await asyncio.sleep(self.backoff * (attempt + 1))
                continue
            if r.status_code == 429 or (r.status_code >= 500 and safe):
                if attempt == retries:
                    raise OandaError(r.status_code, _body(r))
                await asyncio.sleep(self.backoff * (attempt + 1))
                continue
            body = _body(r)
            if r.status_code >= 400:
                raise OandaError(r.status_code, body)
            return body
        raise OandaError(0, "unreachable")

    async def aclose(self) -> None:
        await self.http.aclose()


def ambiguous(e: OandaError) -> bool:
    """A mutating request whose outcome is unknown: no response (network) or a server error."""
    return e.status == 0 or e.status >= 500


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
        self.clock = lambda: pd.Timestamp.now(tz=self.tz)     # injectable for tests

    async def qualify(self) -> None:
        """Read precision/min size per instrument and write them into the instrument config so
        sizing and price rounding match what OANDA accepts."""
        names = ",".join(self.syms.values())
        res = await self.c.req("GET", self.c.acct("/instruments"), params={"instruments": names})
        by = {i["name"]: i for i in res.get("instruments", [])}
        for sym, name in list(self.syms.items()):
            i = by.get(name)
            if i is None and self.cfg["instruments"][sym].get("trade", True) is False:
                log.warning("%s: %s isn't offered on this OANDA account — dropped (it was watch-only)", sym, name)
                self.cfg["instruments"].pop(sym, None)
                self.syms.pop(sym, None)
                continue
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
        """All candles from `start` to now. Pages until the newest candle reaches the present: OANDA
        may return fewer than `count` candles per page, so a short page does NOT mean "done"."""
        out: list[dict] = []
        cur = start
        step = pd.Timedelta("1h" if gran == "H1" else "1min")
        for _ in range(200):
            cs = await self.candles(name, gran, start=cur, count=5000)
            if not cs:
                break
            out += cs
            nxt = pd.Timestamp(cs[-1]["time"])
            if nxt <= cur or nxt >= pd.Timestamp.now(tz="UTC") - 2 * step:
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
            age = (pd.Timestamp.now(tz=self.tz) - m1.index[-1]).total_seconds() / 60 if len(m1) else float("nan")
            log.info("%s: %d historical 1m bars, %d hourly bars, newest 1m bar %.0f min old", sym, len(m1), len(h1), age)

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
            if not len(df):
                continue
            now = self.clock()
            old = df[df.index < now - LIVE_WINDOW]
            if len(old):
                # gap after an outage/restart: store these bars, but don't trade or manage on them
                await self.bus.publish("backfill", [Bar(sym, ts, r.open, r.high, r.low, r.close, float(r.volume))
                                                    for ts, r in old.iterrows()])
                log.info("%s: back-filled %d bars (%s → %s)", sym, len(old), old.index[0], old.index[-1])
            for ts, r in df[df.index >= now - LIVE_WINDOW].iterrows():
                self.state.now = pd.Timestamp.now(tz=self.tz)
                await self.bus.publish("bar", Bar(sym, ts, r.open, r.high, r.low, r.close, float(r.volume)))
            self.last_ts[sym] = df.index[-1]
            n += len(df)
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
    """Practice/live execution at OANDA (CFDs: XAU_USD, SPX500_USD, NAS100_USD, US30_USD …).

    Accounting per broker trade (pos.meta["trades"] entries): `units` still open as far as the bot knows,
    `init` units filled, `booked_units`/`booked_value` = what the bot has already booked from closes of that
    trade. Anything OANDA closed beyond that (stop, manual close, a close whose response was lost) is booked
    from the trade's lifetime averageClosePrice minus what was already booked (`_settle`)."""
    price_bound = True                           # entries carry a priceBound (RiskAgent sizes for it)

    def __init__(self, cfg, state, bus, client: OandaClient, feed: OandaFeed | None = None) -> None:
        super().__init__(cfg, state, bus)
        self.c, self.feed = client, feed
        self.names = {s: _inst(cfg, s) for s in cfg["instruments"]}
        self.rev = {v: k for k, v in self.names.items()}
        oc = cfg.get("oanda") or {}
        self.position_fill = oc.get("position_fill", "DEFAULT")
        self.client_ext = bool(oc.get("client_extensions", True))
        self.managed: dict[str, Position] = {}        # trade id → position
        self.unresolved: dict[str, str] = {}          # symbol → client id of an entry whose outcome is unknown
        self._pending: dict[str, dict] = {}           # symbol → {cid, pos, kind, tries} for those entries
        self._locks: dict[str, asyncio.Lock] = {}     # position id → one close / reconciliation at a time
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

    def _lock(self, pos: Position) -> asyncio.Lock:
        return self._locks.setdefault(pos.id, asyncio.Lock())

    # ── formatting ──
    def _px(self, sym: str, px: float) -> str:
        t = Decimal(str(self.inst[sym]["tick_size"]))
        return str((Decimal(str(px)) / t).quantize(Decimal(1)) * t)

    def _units(self, sym: str, qty: float) -> str:
        step = Decimal(str(self.inst[sym].get("qty_step", 1)))
        q = (Decimal(str(abs(qty))) / step).to_integral_value(rounding=ROUND_DOWN) * step
        return format(q.normalize(), "f")

    # ── account ──
    async def _usd_rate(self) -> float | None:
        """Account currency → USD (sizing and P&L are in USD, the instruments' quote currency).
        None when it can't be looked up: callers must not size new exposure on a guessed rate."""
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
        log.warning("no %s→USD rate — new exposure blocked until it is available", self.currency)
        return None

    async def equity(self) -> float | None:
        """Account NAV in USD, or None when it can't be known right now (summary or FX rate unavailable).
        Callers keep their last known value and skip anything that compares equity (kill switch)."""
        try:
            s = (await self.c.req("GET", self.c.acct("/summary")))["account"]
        except OandaError as e:
            log.warning("summary: %s", e)
            return None
        rate = await self._usd_rate()
        if rate is None:
            return None                          # never NAV × a guessed 1.0
        return _f(s["NAV"]) * rate

    async def quote(self, sym: str) -> tuple[float, float] | None:
        """Fresh (bid, ask) for sizing; None if pricing is unavailable."""
        try:
            p = (await self.c.req("GET", self.c.acct("/pricing"), params={"instruments": self.names[sym]}))["prices"][0]
            bid = _f((p.get("bids") or [{}])[0].get("price") or p.get("closeoutBid"))
            ask = _f((p.get("asks") or [{}])[0].get("price") or p.get("closeoutAsk"))
        except (OandaError, KeyError, IndexError):
            return None
        return (bid, ask) if 0 < bid <= ask else None

    # ── orders ──
    async def _find_entry(self, sym: str, cid: str, signed: str) -> dict | None:
        """The open trade an entry with client id `cid` created, if any (raises OandaError if OANDA can't be read).
        Without client extensions: an unmanaged trade on the instrument with exactly these units."""
        for t in await self._open_trades():
            if t.get("instrument") != self.names[sym] or str(t["id"]) in self.managed:
                continue
            if self.client_ext:
                if (t.get("clientExtensions") or {}).get("id") == cid:
                    return t
            elif _f(t.get("initialUnits")) == _f(signed):
                return t
        return None

    async def _entry_order(self, cid: str) -> tuple[str, str | None]:
        """State of our order by client id (GET /orders/@{clientID}): ('FILLED', tradeOpenedID),
        ('CANCELLED', None) or ('UNKNOWN', None) when OANDA doesn't know it (yet) or it is still pending.
        Raises OandaError if OANDA can't be read."""
        try:
            o = (await self.c.req("GET", self.c.acct(f"/orders/@{cid}")))["order"]
        except OandaError as e:
            if e.status == 404:
                return "UNKNOWN", None
            raise
        state = o.get("state")
        if state == "FILLED":
            return "FILLED", (str(o["tradeOpenedID"]) if o.get("tradeOpenedID") else None)
        return ("CANCELLED", None) if state == "CANCELLED" else ("UNKNOWN", None)

    async def _market(self, pos: Position, qty: float, kind: str) -> tuple[float, str, float]:
        sym = pos.symbol
        if sym in self.unresolved:
            raise OrderRejected(f"{sym}: outcome of entry {self.unresolved[sym]} still unknown — no new entries until reconciled")
        if await self._usd_rate() is None:
            raise OrderRejected(f"no {self.currency}→USD rate: risk can't be sized, new exposure blocked")
        units = self._units(sym, qty)
        if Decimal(units) <= 0 or float(units) < float(self.inst[sym].get("min_units", 0)):
            raise OrderRejected(f"{qty:g} units is below OANDA's minimum for {self.names[sym]}")
        stop = self._px(sym, pos.stop)
        signed = units if pos.side > 0 else f"-{units}"
        order = {"type": "MARKET", "instrument": self.names[sym], "units": signed,
                 "timeInForce": "FOK", "positionFill": self.position_fill,
                 "stopLossOnFill": {"price": stop, "timeInForce": "GTC"}}
        if pos.meta.get("price_bound"):          # worst acceptable fill (RiskAgent: entry ± slippage allowance)
            order["priceBound"] = self._px(sym, pos.meta["price_bound"])
        cid = f"fxa-{pos.id}-{kind}{len(pos.meta.get('trades', []))}"   # deterministic per position and leg
        if self.client_ext:   # MT4-linked accounts reject client extensions → oanda.client_extensions: false
            ext = {"id": cid, "tag": "fxagents", "comment": f"{pos.id} {kind}"[:120]}
            order["clientExtensions"], order["tradeClientExtensions"] = ext, dict(ext)
        self.unresolved[sym] = cid               # cleared below once the outcome is known
        known = False
        try:
            tr = None
            try:
                res = await self.c.req("POST", self.c.acct("/orders"), json={"order": order}, retries=0)
            except OandaError as e:
                if not ambiguous(e):
                    known = True
                    raise OrderRejected(str(e)) from e
                # timeout / 5xx: the order may have filled (now or a moment later). Ask OANDA for the order by its
                # client id; only FILLED or CANCELLED is an answer. Anything else stays unresolved: the symbol is
                # blocked and on_clock asks again (resolve_entries), adopting the trade if it did fill.
                if self.client_ext:
                    state, otid = await self._entry_order(cid)
                    if state == "CANCELLED":
                        known = True
                        raise OrderRejected(f"entry cancelled at OANDA after a lost response ({e})") from e
                    if state != "FILLED" or not otid:
                        self._pending[sym] = {"cid": cid, "pos": pos, "kind": kind, "tries": 0}
                        raise OrderRejected(f"entry outcome unknown ({e}); {sym} blocked until reconciled") from e
                    tr = (await self.c.req("GET", self.c.acct(f"/trades/{otid}")))["trade"]
                else:                            # no client ids on this account: match an unmanaged trade by units
                    tr = await self._find_entry(sym, cid, signed)
                    if tr is None:
                        known = True
                        raise OrderRejected(f"entry not filled ({e})") from e
                known = True
                log.warning("%s: entry response lost (%s) but trade %s exists — registering it", sym, e, tr["id"])
                tid, px, filled = str(tr["id"]), _f(tr.get("price")), abs(_f(tr.get("initialUnits")))
            else:
                known = True
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
        except OandaError as e:
            # the order may have filled and we couldn't look: keep the symbol blocked until on_clock finds out
            self._pending[sym] = {"cid": cid, "pos": pos, "kind": kind, "tries": 0}
            raise OrderRejected(f"entry outcome unknown ({e}); {sym} blocked until reconciled") from e
        finally:
            if known:
                self.unresolved.pop(sym, None)
        # belt and braces: the stop must exist at OANDA, otherwise get out immediately
        if tr is None:
            try:
                tr = (await self.c.req("GET", self.c.acct(f"/trades/{tid}")))["trade"]
            except OandaError as e:
                # the trade is real: keep it managed. stopLossOnFill was part of the order; if it is really
                # missing the monitor's unprotected-position check flattens it
                log.warning("trade %s filled but could not be re-read (%s) — managing it, stop unverified", tid, e)
                pos.meta["stop_unverified"] = True
                return px, tid, filled
        if not (tr.get("stopLossOrder") or tr.get("guaranteedStopLossOrder")):
            await self.c.req("PUT", self.c.acct(f"/trades/{tid}/close"), json={"units": "ALL"})
            raise OrderRejected(f"trade {tid} had no stop at OANDA — closed it immediately")
        return px, tid, filled

    def _register(self, pos: Position, tid: str, filled: float) -> None:
        pos.meta.setdefault("trades", []).append({"id": tid, "units": filled, "init": filled,
                                                  "booked_units": 0.0, "booked_value": 0.0})
        self.managed[tid] = pos

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
        pos.add_leg(Leg(filled, px, self.state.now, "initial"))
        pos.meta["trades"] = []
        self._register(pos, tid, filled)
        return px

    async def add(self, pos, qty, ref_price):
        px, tid, filled = await self._market(pos, qty, "pyramid")
        pos.add_leg(Leg(filled, px, self.state.now, "pyramid"))
        self._register(pos, tid, filled)
        return px

    @staticmethod
    def _mark(t: dict, n: float, px: float) -> None:
        t["booked_units"] = t.get("booked_units", 0.0) + n
        t["booked_value"] = t.get("booked_value", 0.0) + px * n
        t["units"] = round(max(0.0, t["units"] - n), 9)

    def _settle(self, t: dict, tr: dict, fallback: float) -> tuple[float, float]:
        """Units of broker trade `tr` that OANDA has closed but the bot hasn't booked yet, and their price.
        OANDA's averageClosePrice averages EVERY close of the trade, including partials the bot already
        booked, so the unbooked units' price is the rest of the total close value:
        (averageClosePrice × closed_units − booked_value) / unbooked_units, closed = |initial| − |current|."""
        init = abs(_f(tr.get("initialUnits"))) or t.get("init") or t["units"]
        closed = init - abs(_f(tr.get("currentUnits")))
        new = round(closed - t.get("booked_units", init - t["units"]), 9)   # older state: booked = init − open
        new = min(new, t["units"])
        if new <= 1e-9:
            return 0.0, 0.0
        avg = _f(tr.get("averageClosePrice"))
        px = (avg * closed - t.get("booked_value", 0.0)) / new if avg else fallback
        if px <= 0:
            px = avg or fallback
        self._mark(t, new, px)
        return px, new

    def _done(self, t: dict) -> None:
        if t["units"] <= 1e-9:
            self.managed.pop(t["id"], None)

    async def _close_trade(self, pos: Position, t: dict, units: str) -> tuple[float, float]:
        """Close `units` ('ALL' or a number) of one trade. Returns (price, units closed and booked here).
        Never re-sends a close whose outcome is unknown: it reads the trade and books what OANDA shows."""
        try:
            res = await self.c.req("PUT", self.c.acct(f"/trades/{t['id']}/close"), json={"units": units})
        except OandaError as e:
            gone = e.status == 404 or "TRADE_DOESNT_EXIST" in str(e) or "NOT_FOUND" in str(e)
            if not (gone or ambiguous(e)):
                raise OrderRejected(str(e)) from e
            # 404: already closed (its stop was hit a moment ago). timeout/5xx: may or may not have executed.
            try:
                tr = (await self.c.req("GET", self.c.acct(f"/trades/{t['id']}")))["trade"]
            except OandaError as e2:
                raise OrderRejected(f"close of trade {t['id']} unconfirmed ({e}); re-check failed: {e2}") from e2
            px, n = self._settle(t, tr, self.state.last_prices.get(pos.symbol, pos.entry))
            self._done(t)
            if n <= 0 and not gone:
                raise OrderRejected(f"close of trade {t['id']} did not execute ({e})")
            return px, n
        fill = res.get("orderFillTransaction")
        if not fill:
            why = (res.get("orderCancelTransaction") or {}).get("reason", "not filled")
            raise OrderRejected(f"OANDA close cancelled: {why}")
        closed_all = any(str(x.get("tradeID")) == str(t["id"]) for x in (fill.get("tradesClosed") or []))
        n = sum(abs(_f(x.get("units"))) for x in (fill.get("tradesClosed") or []))
        tr = fill.get("tradeReduced")
        if tr:
            n += abs(_f(tr.get("units")))
        n = min(n or (t["units"] if units == "ALL" else float(units)), t["units"])
        px = _f(fill.get("price"))
        self._mark(t, n, px)
        if closed_all and t["units"] > 1e-9:
            # the trade is gone but some units were closed earlier outside the bot (manual partial): book them
            try:
                rest = (await self.c.req("GET", self.c.acct(f"/trades/{t['id']}")))["trade"]
                p2, n2 = self._settle(t, rest, px)
                px, n = (px * n + p2 * n2) / (n + n2) if n2 else px, n + n2
            except OandaError as e:
                log.warning("trade %s: could not read back earlier closes (%s); check_stops will", t["id"], e)
        self._done(t)
        return px, n

    def _book(self, pos: Position, qty: float, px: float) -> float:
        pnl = (px - pos.avg_entry) * pos.side * qty * self.mult(pos.symbol)
        fee = self.commission(pos.symbol, qty)
        pos.closed_qty += qty
        pos.realized += pnl - fee
        pos.commissions += fee
        return pnl - fee

    async def reduce(self, pos, qty, ref_price, limit=None):
        """Oldest trade first. Each leg is booked as soon as OANDA confirms it, so if a later leg fails
        (OrderRejected) the earlier ones are not lost."""
        async with self._lock(pos):
            left = float(self._units(pos.symbol, min(qty, pos.open_qty)))
            got, value = 0.0, 0.0
            for t in [t for t in pos.meta.get("trades", []) if t["units"] > 0]:   # oldest first
                if left <= 1e-9:
                    break
                take = min(left, t["units"])
                px, n = await self._close_trade(pos, t, "ALL" if take >= t["units"] - 1e-9 else self._units(pos.symbol, take))
                if n > 0:
                    self._book(pos, min(n, pos.open_qty), px)
                    got, value, left = got + n, value + px * n, left - n
            return value / got if got > 0 else None      # None: nothing was reduced (e.g. already closed)

    async def close(self, pos, ref_price, limit=None):
        async with self._lock(pos):
            got, value = 0.0, 0.0
            for t in [t for t in pos.meta.get("trades", []) if t["units"] > 0]:
                px, n = await self._close_trade(pos, t, "ALL")
                if n > 0:
                    self._book(pos, min(n, pos.open_qty), px)
                    got, value = got + n, value + px * n
            return value / got if got > 0 else ref_price

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
        if self._checking or not (self.managed or self.unresolved):
            return
        self._checking = True
        try:
            await self.resolve_entries()
            if self.managed:
                await self.check_stops()
        except OandaError as e:
            log.warning("stop check: %s", e)
        finally:
            self._checking = False

    RESOLVE_TRIES = 2       # clock ticks an order OANDA doesn't know yet is re-checked before giving up

    async def resolve_entries(self) -> None:
        """Entries whose outcome was unknown: ask OANDA for the order by client id each clock tick. FILLED →
        the trade is adopted and managed like any entry (position_opened); CANCELLED, or still unknown to
        OANDA after RESOLVE_TRIES ticks → the symbol is unblocked. Not readable → keep asking."""
        for sym, p in list(self._pending.items()):
            p["tries"] += 1
            try:
                state, tid = await self._entry_order(p["cid"]) if self.client_ext else ("UNKNOWN", None)
                if state == "FILLED" and tid:
                    tr = (await self.c.req("GET", self.c.acct(f"/trades/{tid}")))["trade"]
                    await self._adopt_entry(p, tr)
                elif state != "CANCELLED" and p["tries"] < self.RESOLVE_TRIES:
                    continue
            except OandaError as e:
                log.warning("%s: entry %s still unresolved: %s", sym, p["cid"], e)
                continue
            self._pending.pop(sym, None)
            self.unresolved.pop(sym, None)
        for sym in [s for s in self.unresolved if s not in self._pending]:
            self.unresolved.pop(sym, None)

    async def _adopt_entry(self, p: dict, tr: dict) -> None:
        """An entry reported unknown did fill: manage it (stop verified first, as for any entry)."""
        pos, tid = p["pos"], str(tr["id"])
        px, filled = _f(tr.get("price")), abs(_f(tr.get("initialUnits")))
        if not (tr.get("stopLossOrder") or tr.get("guaranteedStopLossOrder")):
            await self.c.req("PUT", self.c.acct(f"/trades/{tid}/close"), json={"units": "ALL"})
            log.warning("late-filled trade %s had no stop at OANDA — closed it", tid)
            return
        now = self.state.now
        pos.add_leg(Leg(filled, px, now, p["kind"]))
        if p["kind"] == "initial":
            pos.meta["trades"] = []
        self._register(pos, tid, filled)
        log.warning("%s: entry %s filled after a lost response — adopted trade %s", pos.symbol, p["cid"], tid)
        if p["kind"] == "initial":
            pos.risk_per_unit = abs(px - pos.initial_stop) or pos.risk_per_unit
            pos.last_price = px
            pos.log(now, "entry", price=px, qty=filled, stop=pos.stop, late=True)
            self.state.positions[pos.id] = pos
            await self.bus.publish("position_opened", pos)

    async def check_stops(self) -> None:
        """Book what OANDA closed without us: stop hit, manual (partial) close, margin closeout. A trade that
        is still open but holds fewer units than the bot thinks gets the difference booked too."""
        open_tr = {str(t["id"]): t for t in await self._open_trades()}
        seen: dict[str, list] = {}
        for tid, pos in list(self.managed.items()):
            lock = self._lock(pos)
            if lock.locked():
                continue          # a close of ours is in flight; it books its own fills
            t = next((x for x in pos.meta.get("trades", []) if x["id"] == tid), None)
            if t is None:
                self.managed.pop(tid, None)
                continue
            tr = open_tr.get(tid)
            if tr is not None and abs(_f(tr.get("currentUnits"))) >= t["units"] - 1e-9:
                continue          # untouched
            async with lock:
                tr = (await self.c.req("GET", self.c.acct(f"/trades/{tid}")))["trade"]
                px, n = self._settle(t, tr, pos.stop)
                self._done(t)
                if n > 0:
                    self._book(pos, min(n, pos.open_qty), px)
                    a = seen.setdefault(pos.id, [pos, 0.0, 0.0])
                    a[1], a[2] = a[1] + n, a[2] + px * n
        for pos, got, value in seen.values():
            px = round(value / got, 6)
            if not any(t["units"] > 1e-9 for t in pos.meta.get("trades", [])):
                await self.bus.publish("stop_filled", {"position": pos, "price": px, "ts": self.state.now})
            else:
                pos.log(self.state.now, "broker_reduced", qty=got, price=px)
                await self.bus.publish("position_updated", {"position": pos, "event": "broker_reduced",
                                                            "msg": f"{got:g} units closed at OANDA @ {px}"})

    async def adopt(self, positions: list[Position]) -> bool:
        """After a restart: take persisted positions back under management. Trades OANDA still holds are
        re-registered; whatever OANDA closed while the app was down is booked by check_stops
        (stop_filled → the position manager finalizes and journals it)."""
        for pos in positions:
            for t in pos.meta.get("trades", []):
                if t["units"] > 1e-9:
                    self.managed[t["id"]] = pos
        if self.managed:
            await self.check_stops()
        return True

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
        """Close trades on this instrument that this process doesn't manage (e.g. a manual trade) and
        journal each as a closed trade with exit reason orphan_close."""
        name = self.names[sym]
        for t in await self._open_trades():
            if t["instrument"] == name and str(t["id"]) not in self.managed:
                res = await self.c.req("PUT", self.c.acct(f"/trades/{t['id']}/close"), json={"units": "ALL"})
                log.warning("closed unmanaged OANDA trade %s (%s %s units)", t["id"], name, t.get("currentUnits"))
                fill = res.get("orderFillTransaction") or {}
                await self._journal_orphan(sym, t, _f(fill.get("price")) or self.state.last_prices.get(sym, _f(t.get("price"))))

    async def _journal_orphan(self, sym: str, t: dict, px: float) -> None:
        u = _f(t.get("currentUnits"))
        side, entry = (1 if u > 0 else -1), _f(t.get("price"))
        stop = _f((t.get("stopLossOrder") or {}).get("price")) or entry
        now = self.state.now or pd.Timestamp.now(tz=self.cfg["timezone"])
        opened = pd.Timestamp(t["openTime"]).tz_convert(self.cfg["timezone"]) if t.get("openTime") else now
        p = Position(sym, side, "orphan:unmanaged", stop, stop, abs(entry - stop), 1.0, opened,
                     reason=f"OANDA trade {t['id']} not managed by this process")
        p.add_leg(Leg(abs(u), entry, opened, "initial"))
        self._book(p, abs(u), px)
        p.status, p.exit_reason, p.closed_ts, p.last_price = "closed", "orphan_close", now, px
        p.log(now, "exit", price=px, reason="orphan_close", realized=round(p.realized, 2))
        await self.bus.publish("position_closed", {"position": p, "price": px})
