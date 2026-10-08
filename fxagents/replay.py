"""Full-system replay backtest: real 1-minute history pushed bar by bar through the SAME agents the
live bot runs (selector + Jev, bias rule and safeguards, risk sizing and margin caps, position
management, kill switch, learner, and the shadow book running the other selection mode).

History comes from the cache the setup-map build saves (data/history/*.pkl, ~90 days of OANDA
1m + 135 days of 1h) — no network needed. Fills are virtual: live price ± half the configured spread.

Honest limits (also written into every report):
* no historical economic calendar → news blackouts and event-day sizing are not replayed;
* fills are simulated (bar prices + estimated spread), not real OANDA fills;
* Jev is the local heuristic unless the run asked for live Jev;
* the setup-map prior is off (the map is built on recent history that overlaps the replay).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import pandas as pd

from .models import Bar
from .setup_map import history_dir, load_history

log = logging.getLogger("replay")


def backtests_dir(cfg) -> Path:
    return Path(cfg["storage"]["db_path"]).parent / "backtests"


class SignalOracle:
    """Replay speed-up: each strategy scans the WHOLE replay period once per (symbol, timeframe);
    the agents then look up what fired on the bar that just closed. Strategies are causal (each signal
    uses only bars up to its own — enforced by a test), so this equals rescanning a window every bar,
    without the cost. Versions the learner creates mid-replay are scanned on first use.
    Pivot-based setups are prefix-exact since indicators.pivots became causal (audit F07: a swing is
    superseded only from its successor's confirmation, never erased retroactively), tested at many cuts
    in tests/test_data_parity.py. Residual live difference: the live window starts later, so EMA/ATR
    warm-up and swings near the window's first bars can differ — a start effect, not look-ahead."""

    CTX_KEYS = ("atr", "ema50", "ema200", "rsi", "macd", "macd_sig", "macd_hist", "adx", "htf")

    def __init__(self, frames: dict[str, pd.DataFrame], tfs: list[str], start) -> None:
        from .indicators import resample_ohlc
        from .strategies import Strategy
        self.df, self.ctx, self.pos, self.hits = {}, {}, {}, {}
        for sym, m1 in frames.items():
            for tf in tfs:
                df = resample_ohlc(m1[m1.index >= start], tf)
                self.df[(sym, tf)] = df
                self.ctx[(sym, tf)] = Strategy._context(df)
                self.pos[(sym, tf)] = {ts: i for i, ts in enumerate(df.index)}
        peers = {"NDQ": ["US30"], "US30": ["NDQ"]}
        for (sym, tf), df in self.df.items():       # correlated indices for SMT divergence
            self.ctx[(sym, tf)]["peers"] = [self.df[(p, tf)].reindex(df.index).ffill()
                                            for p in peers.get(sym, []) if (p, tf) in self.df]

    def _signals(self, st, sym: str, tf: str) -> dict:
        key = (st.id, sym, tf)
        if key not in self.hits:
            by_i: dict[int, list] = {}
            for rs in st._scan_full(self.df[(sym, tf)], self.ctx[(sym, tf)]):
                by_i.setdefault(rs.i, []).append(rs)
            self.hits[key] = by_i
        return self.hits[key]

    def at(self, st, sym: str, tf: str, bar_ts) -> list | None:
        i = self.pos.get((sym, tf), {}).get(bar_ts)
        if i is None:
            return None
        return self._signals(st, sym, tf).get(i, [])

    def ctx_at(self, sym: str, tf: str, bar_ts) -> dict | None:
        i = self.pos.get((sym, tf), {}).get(bar_ts)
        if i is None:
            return None
        c = self.ctx[(sym, tf)]
        return {k: c[k][: i + 1] for k in self.CTX_KEYS if k in c}


class ReplayFeed:
    """Same interface as SimFeed: history()/h1_history() for warm-up, run() replays minute by minute."""

    def __init__(self, cfg, bus, state, out_dir: Path, days: int, journal=None) -> None:
        self.cfg, self.bus, self.state, self.out, self.journal = cfg, bus, state, Path(out_dir), journal
        self.tz = cfg["timezone"]
        warm = int(cfg["timeframes"]["history_days"])
        self.frames, self.h1 = {}, {}
        for sym in cfg["instruments"]:
            h = load_history(cfg, sym)
            if h is None:
                raise SystemExit(f"no history cache for {sym} in {history_dir(cfg)} — let the app build the setup "
                                 f"map first (it downloads ~90 days from OANDA), then run the backtest")
            self.frames[sym], self.h1[sym] = h
        last = min(df.index[-1] for df in self.frames.values())
        first = max(df.index[0] for df in self.frames.values())
        avail = (last - first).days - warm - 1
        if avail < 1:
            raise SystemExit("not enough cached history for a replay")
        self.days = min(int(days), avail)
        self.end = last
        self.split = (last - pd.Timedelta(days=self.days)).normalize()
        self.warm_start = self.split - pd.Timedelta(days=warm)
        self.speed = 0.0
        from .agents.trading import signal_tfs
        self.oracle = SignalOracle(self.frames, signal_tfs(cfg), self.warm_start)
        if self.days < days:
            log.warning("only %d days of history available after warm-up (asked for %d)", self.days, days)

    def history(self, symbol: str) -> pd.DataFrame:
        df = self.frames[symbol]
        return df[(df.index < self.split) & (df.index >= self.warm_start)]

    def h1_history(self, symbol: str) -> pd.DataFrame:
        h = self.h1[symbol]
        return h[h.index < self.warm_start]

    def progress(self, ts, started: float, done: bool = False) -> None:
        total = (self.end - self.split).total_seconds()
        frac = 1.0 if done else max(0.0, min(1.0, (ts - self.split).total_seconds() / total)) if total else 1.0
        el = time.time() - started
        s = self.journal.summary() if self.journal is not None else {}
        (self.out / "progress.json").write_text(json.dumps({
            "state": "done" if done else "running", "sim_now": str(ts), "fraction": round(frac, 4),
            "elapsed_s": round(el), "eta_s": round(el / frac - el) if 0.02 < frac < 1 else None,
            "trades": s.get("trades"), "sum_r": s.get("sum_r"),
            "from": str(self.split), "to": str(self.end), "days": self.days}))

    async def run(self) -> None:
        live = {s: df[df.index >= self.split] for s, df in self.frames.items()}
        idx = sorted(set().union(*[set(d.index) for d in live.values()]))
        log.info("replay: %d minutes, %s → %s, %d symbols", len(idx), idx[0] if idx else "-", idx[-1] if idx else "-", len(live))
        started, last_p = time.time(), 0.0
        rows = {s: df.to_dict("index") for s, df in live.items()}
        for ts in idx:
            self.state.now = ts + pd.Timedelta("1min")
            for sym, rr in rows.items():
                r = rr.get(ts)
                if r is not None:
                    await self.bus.publish("bar", Bar(sym, ts, r["open"], r["high"], r["low"], r["close"],
                                                      float(r.get("volume", 0))))
            await self.bus.publish("clock", self.state.now)
            if time.time() - last_p > 10:
                last_p = time.time()
                self.progress(ts, started)
                await asyncio.sleep(0)
        self.progress(idx[-1] if idx else self.end, started, done=True)
        await self.bus.publish("feed_done", None)
