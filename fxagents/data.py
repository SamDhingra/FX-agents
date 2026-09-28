"""Market data: a rolling bar store plus two feeds — synthetic (sim) and Interactive Brokers."""
from __future__ import annotations

import asyncio
import logging

import pandas as pd

from .indicators import resample_ohlc
from .models import Bar
from .sim import synth_1m

log = logging.getLogger("data")


class BarStore:
    """1-minute bars per symbol with cached higher-timeframe views."""

    def __init__(self, tz: str, max_days: int = 15) -> None:
        self.tz = tz
        self.max_rows = max_days * 1440
        self.frames: dict[str, pd.DataFrame] = {}
        self._buf: dict[str, list[dict]] = {}
        self._cache: dict[tuple[str, str], tuple[int, pd.DataFrame]] = {}

    def load_history(self, symbol: str, df: pd.DataFrame) -> None:
        self.frames[symbol] = df[["open", "high", "low", "close", "volume"]].copy()
        self._buf[symbol] = []

    def append(self, bar: Bar) -> None:
        self._buf.setdefault(bar.symbol, []).append(
            {"ts": bar.ts, "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume})

    def m1(self, symbol: str) -> pd.DataFrame:
        buf = self._buf.get(symbol)
        if buf:
            new = pd.DataFrame(buf).set_index("ts")
            base = self.frames.get(symbol)
            df = new if base is None else pd.concat([base, new])
            self.frames[symbol] = df[~df.index.duplicated(keep="last")].iloc[-self.max_rows:]
            self._buf[symbol] = []
        return self.frames.get(symbol, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    def tf(self, symbol: str, rule: str, complete_only: bool = True) -> pd.DataFrame:
        m1 = self.m1(symbol)
        key = (symbol, rule)
        if key in self._cache and self._cache[key][0] == len(m1):
            return self._cache[key][1]
        df = resample_ohlc(m1, rule)
        if complete_only and len(df) and len(m1):
            # drop the still-forming bar
            last_close = df.index[-1] + pd.Timedelta(rule)
            if m1.index[-1] + pd.Timedelta("1min") < last_close:
                df = df.iloc[:-1]
        self._cache[key] = (len(m1), df)
        return df


class SimFeed:
    """Synthetic multi-symbol market, replayed minute by minute through the bus."""

    def __init__(self, cfg, bus, state) -> None:
        self.cfg, self.bus, self.state = cfg, bus, state
        self.tz = cfg["timezone"]
        sim = cfg["sim"]
        warm = cfg["timeframes"]["history_days"]
        start = pd.Timestamp.now(tz=self.tz).normalize() - pd.Timedelta(days=warm + sim["days"] + 3)
        self.frames = {}
        for j, (sym, ic) in enumerate(cfg["instruments"].items()):
            df = synth_1m(ic["sim_start_price"], ic["sim_daily_vol"], start,
                          warm + sim["days"] + 3, sim["seed"] + j, self.tz)
            self.frames[sym] = df
        first = next(iter(self.frames.values()))
        days = sorted(set(first.index.normalize()))
        split_day = days[-sim["days"]] if len(days) > sim["days"] else days[0]
        self.split = split_day
        self.speed = float(sim.get("speed", 0))

    def history(self, symbol: str) -> pd.DataFrame:
        df = self.frames[symbol]
        return df[df.index < self.split]

    async def run(self) -> None:
        live = {s: df[df.index >= self.split] for s, df in self.frames.items()}
        idx = sorted(set().union(*[set(d.index) for d in live.values()]))
        log.info("sim: replaying %d minutes across %d symbols", len(idx), len(live))
        for ts in idx:
            self.state.now = ts + pd.Timedelta("1min")      # bar has closed
            for sym, df in live.items():
                if ts in df.index:
                    r = df.loc[ts]
                    await self.bus.publish("bar", Bar(sym, ts, r.open, r.high, r.low, r.close, r.volume))
            await self.bus.publish("clock", self.state.now)
            if self.speed:
                await asyncio.sleep(self.speed)
            else:
                await asyncio.sleep(0)
        await self.bus.publish("feed_done", None)


def make_contract(spec: dict):
    from ib_async import CFD, Commodity, ContFuture, Contract, Forex, Future
    s = dict(spec)
    t = s.pop("secType")
    if t == "CONTFUT":
        return ContFuture(**s)
    if t == "FUT":
        return Future(**s)
    if t == "CMDTY":
        return Commodity(**s)
    if t == "CFD":
        return CFD(**s)
    if t == "CASH":
        return Forex(s["symbol"])
    return Contract(secType=t, **s)


class IBKRFeed:
    """1-minute bars from IBKR (reqHistoricalData keepUpToDate). Completed bars go on the bus."""

    def __init__(self, cfg, bus, state, ib) -> None:
        self.cfg, self.bus, self.state, self.ib = cfg, bus, state, ib
        self.tz = cfg["timezone"]
        self.contracts: dict = {}
        self.trade_contracts: dict = {}
        self._subs = {}
        self._hist: dict[str, pd.DataFrame] = {}

    async def qualify(self) -> None:
        from ib_async import Contract
        for sym, ic in self.cfg["instruments"].items():
            c = make_contract(ic["contract"])
            [q] = await self.ib.qualifyContractsAsync(c)
            self.contracts[sym] = q
            # continuous future → tradeable front-month contract
            self.trade_contracts[sym] = Contract(conId=q.conId, exchange=q.exchange) if ic["contract"]["secType"] == "CONTFUT" else q
            if ic["contract"]["secType"] == "CONTFUT":
                [self.trade_contracts[sym]] = await self.ib.qualifyContractsAsync(self.trade_contracts[sym])
            log.info("qualified %s → %s", sym, self.trade_contracts[sym])

    def _what(self, sym: str) -> str:
        t = self.cfg["instruments"][sym]["contract"]["secType"]
        return "MIDPOINT" if t in ("CMDTY", "CASH", "CFD") else "TRADES"

    async def start(self) -> None:
        self.ib.reqMarketDataType(self.cfg["ibkr"].get("market_data_type", 1))
        days = self.cfg["timeframes"]["history_days"]
        for sym, c in self.contracts.items():
            bars = await self.ib.reqHistoricalDataAsync(
                c, endDateTime="", durationStr=f"{days} D", barSizeSetting="1 min",
                whatToShow=self._what(sym), useRTH=False, formatDate=2, keepUpToDate=True)
            df = pd.DataFrame([{"ts": b.date, "open": b.open, "high": b.high, "low": b.low,
                                "close": b.close, "volume": float(b.volume or 0)} for b in bars[:-1]])
            df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(self.tz)
            self._hist[sym] = df.set_index("ts")
            bars.updateEvent += self._make_handler(sym)
            self._subs[sym] = bars
            log.info("%s: %d historical 1m bars", sym, len(df))

    def history(self, symbol: str) -> pd.DataFrame:
        return self._hist[symbol]

    def _make_handler(self, sym: str):
        def on_update(bars, has_new_bar):
            if not has_new_bar or len(bars) < 2:
                return
            b = bars[-2]  # the bar that just completed
            ts = pd.Timestamp(b.date).tz_convert(self.tz) if pd.Timestamp(b.date).tzinfo else pd.Timestamp(b.date, tz="UTC").tz_convert(self.tz)
            self.state.now = pd.Timestamp.now(tz=self.tz)
            asyncio.ensure_future(self.bus.publish("bar", Bar(sym, ts, b.open, b.high, b.low, b.close, float(b.volume or 0))))
        return on_update

    async def run(self) -> None:
        while True:  # clock tick for time-based agents
            self.state.now = pd.Timestamp.now(tz=self.tz)
            await self.bus.publish("clock", self.state.now)
            await asyncio.sleep(15)
