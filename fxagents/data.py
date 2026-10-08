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
    """1-minute bars per symbol with cached higher-timeframe views.

    Cache identity (audit F14): `rev[symbol]` is a monotonically increasing data revision, bumped on
    every load/append — a re-sent bar with the same timestamp but corrected OHLCV changes neither the
    length nor the last timestamp, so those alone left stale views. A correction to a bar older than
    the newest marks every resampled view of that symbol dirty FROM that bar (incremental rebuild)."""

    def __init__(self, tz: str, max_days: int = 15) -> None:
        self.tz = tz
        self.max_rows = max_days * 1440
        self.frames: dict[str, pd.DataFrame] = {}
        self._buf: dict[str, list[dict]] = {}
        self._cache: dict[tuple[str, str], tuple[int, pd.DataFrame]] = {}
        self.rev: dict[str, int] = {}
        self._dirty: dict[tuple, pd.Timestamp] = {}     # resampled-cache key → earliest corrected 1m bar

    def load_history(self, symbol: str, df: pd.DataFrame) -> None:
        self.frames[symbol] = df[["open", "high", "low", "close", "volume"]].copy()
        self._buf[symbol] = []
        self.rev[symbol] = self.rev.get(symbol, 0) + 1
        for k in [k for k in self._cache if k[0] == "full" and k[1] == symbol]:
            del self._cache[k]                         # whole history replaced: rebuild from scratch

    def load_h1(self, symbol: str, df: pd.DataFrame) -> None:
        """Long hourly history for Daily/4H/1H structure."""
        self.h1_hist = getattr(self, "h1_hist", {})
        self.h1_hist[symbol] = df[["open", "high", "low", "close"]].copy()

    def h1(self, symbol: str) -> pd.DataFrame:
        """Hourly bars: long history + hours rebuilt from live 1m bars (incl. the forming hour,
        which the bias engine ignores until it closes)."""
        recent = self.tf(symbol, "1h", complete_only=False)[["open", "high", "low", "close"]]
        hist = getattr(self, "h1_hist", {}).get(symbol)
        if hist is None or not len(hist):
            return recent
        if len(recent):
            hist = hist[hist.index < recent.index[0]]
        return pd.concat([hist, recent])

    def append(self, bar: Bar) -> None:
        self._buf.setdefault(bar.symbol, []).append(
            {"ts": bar.ts, "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume})
        self.rev[bar.symbol] = self.rev.get(bar.symbol, 0) + 1

    def m1(self, symbol: str) -> pd.DataFrame:
        buf = self._buf.get(symbol)
        if buf:
            new = pd.DataFrame(buf).set_index("ts")
            base = self.frames.get(symbol)
            df = new if base is None else pd.concat([base, new])
            df = df[~df.index.duplicated(keep="last")]
            if base is not None and len(base) and new.index.min() <= base.index[-1]:   # correction / late bar
                t = new.index.min()
                df = df.sort_index()
                for k in [k for k in self._cache if k[0] == "full" and k[1] == symbol]:
                    self._dirty[k] = min(self._dirty.get(k, t), t)
            self.frames[symbol] = df.iloc[-self.max_rows:]
            self._buf[symbol] = []
        return self.frames.get(symbol, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    def _resampled(self, symbol: str, rule: str, m1: pd.DataFrame) -> pd.DataFrame:
        """All bars of `rule` incl. the forming one. Incremental: only the tail since the last cached
        bar is re-aggregated (a full resample of ~17k 1m rows on every new bar was the replay hot spot)."""
        key = ("full", symbol, rule)
        prev = self._cache.get(key)
        if prev is not None and len(m1) and len(prev[1]):
            p_first, full = prev[0], prev[1]
            last_start = full.index[-1]
            dirty = self._dirty.pop(key, None)
            if dirty is not None:                       # re-aggregate from the bin holding the corrected bar
                before = full.index[full.index <= dirty]
                last_start = before[-1] if len(before) else m1.index[0] - pd.Timedelta(rule)
            if m1.index[-1] >= last_start and m1.index[0] <= p_first + pd.Timedelta(rule):
                tail = resample_ohlc(m1[m1.index >= last_start], rule)
                full = pd.concat([full[full.index < last_start], tail])
                full = full[full.index >= m1.index[0].floor(rule)]
                self._cache[key] = (m1.index[0], full)
                return full
        full = resample_ohlc(m1, rule)
        self._cache[key] = (m1.index[0] if len(m1) else None, full)
        return full

    def tf(self, symbol: str, rule: str, complete_only: bool = True) -> pd.DataFrame:
        m1 = self.m1(symbol)
        key = (symbol, rule, complete_only)
        # revision: any load/append (incl. a corrected re-send of an existing bar) → new stamp;
        # length alone goes stale once the store is full, length + last ts misses corrections
        stamp = (self.rev.get(symbol, 0), len(m1), m1.index[-1] if len(m1) else None)
        if key in self._cache and self._cache[key][0] == stamp:
            return self._cache[key][1]
        df = self._resampled(symbol, rule, m1)
        if complete_only and len(df) and len(m1):
            # drop the still-forming bar
            last_close = df.index[-1] + pd.Timedelta(rule)
            if m1.index[-1] + pd.Timedelta("1min") < last_close:
                df = df.iloc[:-1]
        self._cache[key] = (stamp, df)
        return df


class SimFeed:
    """Synthetic multi-symbol market, replayed minute by minute through the bus."""

    def __init__(self, cfg, bus, state) -> None:
        self.cfg, self.bus, self.state = cfg, bus, state
        self.tz = cfg["timezone"]
        sim = cfg["sim"]
        warm = cfg["timeframes"]["history_days"]
        long = max(cfg["timeframes"].get("h1_history_days", 45), warm)
        start = pd.Timestamp.now(tz=self.tz).normalize() - pd.Timedelta(days=long + sim["days"] + 3)
        self.frames = {}
        for j, (sym, ic) in enumerate(cfg["instruments"].items()):
            df = synth_1m(ic["sim_start_price"], ic["sim_daily_vol"], start,
                          long + sim["days"] + 3, sim["seed"] + j, self.tz)
            self.frames[sym] = df
        first = next(iter(self.frames.values()))
        days = sorted(set(first.index.normalize()))
        split_day = days[-sim["days"]] if len(days) > sim["days"] else days[0]
        self.split = split_day
        self.warm_start = split_day - pd.Timedelta(days=warm)
        self.speed = float(sim.get("speed", 0))

    def history(self, symbol: str) -> pd.DataFrame:
        df = self.frames[symbol]
        return df[(df.index < self.split) & (df.index >= self.warm_start)]

    def h1_history(self, symbol: str) -> pd.DataFrame:
        df = self.frames[symbol]
        return resample_ohlc(df[df.index < self.warm_start], "1h")

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
        self._h1: dict[str, pd.DataFrame] = {}

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
            h1 = await self.ib.reqHistoricalDataAsync(
                c, endDateTime="", durationStr=f"{self.cfg['timeframes'].get('h1_history_days', 45)} D",
                barSizeSetting="1 hour", whatToShow=self._what(sym), useRTH=False, formatDate=2)
            hdf = pd.DataFrame([{"ts": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                                for b in h1])
            hdf["ts"] = pd.to_datetime(hdf["ts"], utc=True).dt.tz_convert(self.tz)
            self._h1[sym] = hdf.set_index("ts")
            bars.updateEvent += self._make_handler(sym)
            self._subs[sym] = bars
            log.info("%s: %d historical 1m bars", sym, len(df))

    def history(self, symbol: str) -> pd.DataFrame:
        return self._hist[symbol]

    def h1_history(self, symbol: str) -> pd.DataFrame:
        return self._h1[symbol]

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
