"""90-day historical setup map: how every setup has played out by symbol × hour × weekday.

Built from ~90 days of 1-minute history (OANDA, or whatever the bar store holds as a fallback): each
live strategy version is backtested on 5m and 15m bars with the SAME rules the bot trades with — the
hard HTF bias rule, entry windows, 1:1 → partial → stop-to-profit → pyramid management. Every
simulated trade is bucketed by (symbol, strategy, hour NY, weekday).

Used in two places:
* the Strategies page heatmap (what tends to work when), and
* setup-first's ranking and Jev context, as a *prior*: cell → hour → overall, each level shrunk toward
  the next (k trades of pseudo-weight), so a lucky Tuesday-10:00 with 3 trades can't dominate.

Rebuilt weekly (Sunday evening, before the week opens) and on demand from the dashboard.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .bias import bias_frame
from .indicators import resample_ohlc
from .sim import Mgmt, backtest
from .strategies import Strategy

log = logging.getLogger("setup_map")
DAYS = 90
SHRINK_K = 8.0
MIN_N = 5          # below this a cell is "thin" (shown faded)


def setup_name(sid: str) -> str:
    return sid.split(":")[0]


class SetupMap:
    """Aggregated cells + hierarchical priors. cells[(sym, sid, hour, wd)] = [n, wins, sum_r]."""

    def __init__(self, data: dict):
        self.meta = {k: v for k, v in data.items() if k != "rows"}
        self.cells: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        self.hours: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        self.overall: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        self.fam_hours: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        self.fam_overall: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        self.rows = data.get("rows", [])
        for sym, sid, tf, hour, wd, r in self.rows:
            win = 1 if r > 0 else 0
            fam = setup_name(sid)
            for d, k in ((self.cells, (sym, sid, hour, wd)), (self.hours, (sym, sid, hour)),
                         (self.overall, (sym, sid)), (self.fam_hours, (sym, fam, hour)),
                         (self.fam_overall, (sym, fam))):
                c = d[k]; c[0] += 1; c[1] += win; c[2] += r

    @staticmethod
    def _exp(c) -> float:
        return c[2] / c[0] if c[0] else 0.0

    def prior(self, sym: str, sid: str, hour: int, wd: int) -> dict:
        """Shrunk expectancy (R) for this setup at this hour and weekday. Falls back to the setup
        family when this exact version has no history (e.g. a freshly tuned learner version)."""
        o, h, c = self.overall.get((sym, sid)), self.hours.get((sym, sid, hour)), self.cells.get((sym, sid, hour, wd))
        level = "version"
        if not o or not o[0]:
            fam = setup_name(sid)
            o, h, c = self.fam_overall.get((sym, fam)), self.fam_hours.get((sym, fam, hour)), None
            level = "family"
        if not o or not o[0]:
            return {"n": 0, "shrunk_exp": 0.0, "level": "none"}
        eo = self._exp(o)
        h = h or [0, 0, 0.0]
        eh = (h[2] + SHRINK_K * eo) / (h[0] + SHRINK_K)
        c = c or [0, 0, 0.0]
        ec = (c[2] + SHRINK_K * eh) / (c[0] + SHRINK_K)
        return {"level": level, "n": c[0], "win": round(c[1] / c[0], 3) if c[0] else None,
                "exp": round(self._exp(c), 3) if c[0] else None, "hour_n": h[0],
                "hour_exp": round(self._exp(h), 3) if h[0] else None, "overall_n": o[0],
                "overall_exp": round(eo, 3), "shrunk_exp": round(ec, 3)}

    def grid(self, symbol: str = "ALL", tf: str = "all", weekday: str = "all") -> dict:
        """Heatmap: rows = setups, cols = hours 0–23 (NY), cell = {n, w, r}."""
        acc: dict[tuple, list] = defaultdict(lambda: [0, 0, 0.0])
        for sym, sid, tfl, hour, wd, r in self.rows:
            if symbol != "ALL" and sym != symbol:
                continue
            if tf != "all" and tfl != tf:
                continue
            if weekday != "all" and str(wd) != str(weekday):
                continue
            c = acc[(setup_name(sid), hour)]; c[0] += 1; c[1] += r > 0; c[2] += r
        names = sorted({k[0] for k in acc}, key=lambda n: -sum(v[0] for k, v in acc.items() if k[0] == n))
        rows = []
        for n in names:
            cells = {}
            for hr in range(24):
                c = acc.get((n, hr))
                if c and c[0]:
                    cells[str(hr)] = {"n": c[0], "w": round(c[1] / c[0], 3), "r": round(c[2] / c[0], 3)}
            tot = [sum(acc[(n, h)][i] for h in range(24) if (n, h) in acc) for i in range(3)]
            rows.append({"setup": n, "n": tot[0], "w": round(tot[1] / tot[0], 3) if tot[0] else 0,
                         "r": round(tot[2] / tot[0], 3) if tot[0] else 0, "cells": cells})
        return {"rows": rows, "min_n": MIN_N, "hours": sorted({k[1] for k in acc})}

    def best_now(self, live_ids: list[str], symbols: list[str], hour: int, wd: int, top: int = 6) -> list[dict]:
        """Best setup families for this hour (both timeframes pooled), shrunk toward the family's
        overall record. Needs at least 3 trades at this hour to be listed."""
        fams = {setup_name(i) for i in live_ids}
        out = []
        for sym in symbols:
            for fam in fams:
                o, h = self.fam_overall.get((sym, fam)), self.fam_hours.get((sym, fam, hour))
                if not o or not h or h[0] < 3:
                    continue
                eo = self._exp(o)
                shrunk = (h[2] + SHRINK_K * eo) / (h[0] + SHRINK_K)
                out.append({"symbol": sym, "setup": fam, "hour_n": h[0], "hour_exp": round(self._exp(h), 3),
                            "win": round(h[1] / h[0], 3), "overall_exp": round(eo, 3), "shrunk_exp": round(shrunk, 3)})
        return sorted(out, key=lambda x: -x["shrunk_exp"])[:top]


def compute(cfg, strategies: list, data: dict[str, tuple[pd.DataFrame, pd.DataFrame]], source: str) -> dict:
    """data[sym] = (1m bars, 1h bars). CPU-bound → run in a worker thread. `strategies` is a snapshot."""
    s = cfg["sessions"]
    rows, bars = [], {}
    for sym, (m1, h1) in data.items():
        if m1 is None or len(m1) < 1440:
            continue
        bars[sym] = len(m1)
        for tf in cfg["timeframes"]["entry"]:
            df = resample_ohlc(m1, tf)
            if len(df) < 200:
                continue
            tf_min = int(pd.Timedelta(tf).total_seconds() // 60)
            ctx = Strategy.context(df)
            bias = bias_frame(h1, df.index + pd.Timedelta(tf), weights=cfg["bias"]["weights"])["score"].to_numpy()
            for st in [x for x in strategies if x.tf == tf]:
                try:
                    trades = backtest(st, df, ctx, Mgmt.from_cfg(cfg, rr=st.rr, bar_minutes=tf_min),
                                      s["entry_windows"], s["flatten_at"], bias_score=bias,
                                      min_align=cfg["bias"]["min_align"])
                except Exception as e:  # noqa: BLE001
                    log.warning("setup map: %s %s failed: %s", sym, st.id, e)
                    continue
                for t in trades:
                    ts = t["ts"]
                    rows.append([sym, st.id, st.tf_label, int(ts.hour), int(ts.dayofweek), round(float(t["r"]), 3)])
    first = min((m1.index[0] for m1, _ in data.values() if m1 is not None and len(m1)), default=None)
    last = max((m1.index[-1] for m1, _ in data.values() if m1 is not None and len(m1)), default=None)
    return {"built_at": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="minutes"), "source": source,
            "from": first.isoformat(timespec="minutes") if first is not None else None,
            "to": last.isoformat(timespec="minutes") if last is not None else None,
            "days": round((last - first).total_seconds() / 86400, 1) if first is not None else 0,
            "bars": bars, "trades": len(rows), "rows": rows}


class SetupMapHolder:
    """Shared by the real and shadow books; the dashboard reads status from here."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.map: SetupMap | None = None
        self.status = {"state": "missing"}

    def load(self) -> bool:
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text())
            self.map = SetupMap(data)
            self.status = {"state": "ready", **self.map.meta}
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("setup map unreadable (%s) — will rebuild", e)
            return False

    def age_days(self) -> float:
        return (time.time() - self.path.stat().st_mtime) / 86400 if self.path.exists() else 1e9

    def save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")))
        tmp.replace(self.path)
        self.map = SetupMap(data)
        self.status = {"state": "ready", **self.map.meta}


def map_path(cfg) -> str:
    return str(Path(cfg["storage"]["db_path"]).with_name("setup_map.json"))


def history_dir(cfg) -> Path:
    return Path(cfg["storage"]["db_path"]).parent / "history"


def save_history(cfg, sym: str, m1: pd.DataFrame, h1: pd.DataFrame) -> None:
    """Cache the long history so the learner can walk-forward on it between weekly rebuilds."""
    d = history_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    pd.to_pickle((m1, h1), d / f"{sym}.pkl")


def load_history(cfg, sym: str):
    p = history_dir(cfg) / f"{sym}.pkl"
    return pd.read_pickle(p) if p.exists() else None


class SetupMapAgent:
    """Loads the map at start, builds it when missing/stale (in the background, never blocking trading),
    and rebuilds it each Sunday evening before the week opens."""
    name = "setup_map"

    def __init__(self, ctx, holder: SetupMapHolder, feed=None):
        self.ctx, self.holder, self.feed = ctx, holder, feed
        self.cfg = ctx.cfg
        self.task: asyncio.Task | None = None

    def start(self):
        self.holder.load()
        self.ctx.bus.subscribe("clock", self.on_clock)

    async def on_clock(self, now: pd.Timestamp):
        if self.task and not self.task.done():
            return
        sc = self.cfg.get("setup_map", {}) or {}
        if not sc.get("enabled", True):
            return
        stale = self.holder.age_days() > float(sc.get("max_age_days", 7))
        sunday_slot = now.dayofweek == 6 and now.hour >= 18 and self.holder.age_days() > 1
        if self.holder.map is None or stale or sunday_slot:
            self.rebuild()

    def rebuild(self) -> bool:
        if self.task and not self.task.done():
            return False
        self.task = asyncio.create_task(self._build())
        return True

    async def _fetch(self) -> tuple[dict, str]:
        days = int((self.cfg.get("setup_map", {}) or {}).get("days", DAYS))
        feed = self.feed
        if feed is not None and hasattr(feed, "_paged"):      # OANDA: pull real history
            now = pd.Timestamp.now(tz="UTC")
            out = {}
            for sym, name in feed.syms.items():
                m1 = feed._frame(await feed._paged(name, "M1", now - pd.Timedelta(days=days)))
                h1 = feed._frame(await feed._paged(name, "H1", now - pd.Timedelta(days=days + 45)), vol=False)
                out[sym] = (m1, h1)
                try:
                    save_history(self.cfg, sym, m1, h1)
                except Exception as e:  # noqa: BLE001
                    log.warning("history cache %s: %s", sym, e)
                await asyncio.sleep(0)
            return out, f"OANDA {days}-day 1-minute history"
        store = self.ctx.store                               # sim / IBKR: whatever the bar store holds
        return {sym: (store.m1(sym), store.h1(sym)) for sym in self.cfg["instruments"]}, "bar store (live history)"

    async def _build(self):
        t0 = time.time()
        self.holder.status = {**{k: v for k, v in self.holder.status.items() if k != "state"},
                              "state": "building", "started": pd.Timestamp.now(tz=self.cfg["timezone"]).isoformat(timespec="minutes")}
        try:
            data, source = await self._fetch()
            res = await asyncio.to_thread(compute, self.cfg, list(self.ctx.book.live()), data, source)
            del data
            self.holder.save(res)
            log.info("setup map built: %d trades over %.0f days in %.0fs (%s)", res["trades"], res["days"],
                     time.time() - t0, source)
        except Exception as e:  # noqa: BLE001
            log.exception("setup map build failed")
            self.holder.status = {**self.holder.status, "state": "error", "error": str(e)[:200]}
