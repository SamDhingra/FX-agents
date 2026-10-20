"""Backtest data: OANDA 1-minute bid/ask exports → one Market per (dataset, symbol), cached as .npy files (memory-mappable) for fast reloads.

Datasets (data/bt/datasets.json overrides the defaults) name which export folders they combine and their ROLE:
  seen   data any test may use (2021 → Sep 2026: holdout_m1 + dev_m1)
  vault  untouched data (2016 → 2020) — the ledger only lets a frozen strategy that passed on `seen` open it, once.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
MIN = 60_000_000_000
EXPORT = Path("data/export")
ROOT = Path("data/bt")

DEFAULT_DATASETS = {
    "seen": {"role": "seen", "label": "2021 → Sep 2026", "sets": ["holdout_m1", "dev_m1"]},
    "vault": {"role": "vault", "label": "2016 → 2020 (untouched)",
              "sets": ["old_m1", "old_m1_idx_NDQ", "old_m1_idx_US30", "old_m1_idx_XAUUSD"]},
}


def datasets() -> dict:
    p = ROOT / "datasets.json"
    if p.exists():
        return {**DEFAULT_DATASETS, **json.loads(p.read_text())}
    return dict(DEFAULT_DATASETS)


def export_files(ds: str, symbol: str) -> list[Path]:
    d = datasets()[ds]
    return [f for f in (EXPORT / s / f"{symbol}_M1.csv.gz" for s in d["sets"]) if f.exists()]


def symbols(ds: str) -> list[str]:
    d = datasets()[ds]
    out = set()
    for s in d["sets"]:
        for f in (EXPORT / s).glob("*_M1.csv.gz"):
            out.add(f.name.split("_M1")[0])
    return sorted(out)


@dataclass
class Market:
    """Minute arrays of one instrument (NY-time helpers) + cached higher-timeframe candles. All candles are mid prices;
    `end` is the ns at which a candle is complete — a strategy may only use candles with end ≤ its decision time."""
    symbol: str
    ns: np.ndarray
    bid_o: np.ndarray
    bid_h: np.ndarray
    bid_l: np.ndarray
    bid_c: np.ndarray
    ask_o: np.ndarray
    ask_h: np.ndarray
    ask_l: np.ndarray
    ask_c: np.ndarray
    vol: np.ndarray
    dataset: str = ""
    _bars: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.o = (self.bid_o + self.ask_o) / 2
        self.h = (self.bid_h + self.ask_h) / 2
        self.l = (self.bid_l + self.ask_l) / 2
        self.c = (self.bid_c + self.ask_c) / 2
        self.spread = self.ask_o - self.bid_o
        self.idx = pd.DatetimeIndex(self.ns.astype("datetime64[ns]")).tz_localize("UTC")
        loc = self.idx.tz_convert(NY)
        lns = loc.tz_localize(None).as_unit("ns").asi8
        self.mod = ((lns // MIN) % 1440).astype(np.int32)                 # NY minute of day
        self.dow = loc.dayofweek.to_numpy(np.int8)
        self.day = (lns // (1440 * MIN)).astype(np.int64)                  # NY calendar day number
        self.sess = ((lns + 6 * 60 * MIN) // (1440 * MIN)).astype(np.int64)  # trading day: 18:00 NY starts the next

    def __len__(self):
        return len(self.ns)

    # ── candles ──
    def bars(self, tf) -> pd.DataFrame:
        """Mid candles: tf = minutes (int) or "1h", "4h" (NY 01/05/09/13/17/21 closes), "1d" (NY 17:00 close) — both on the New York wall clock all year.
        Columns o h l c v start end (ns). Cached."""
        key = str(tf)
        if key in self._bars:
            return self._bars[key]
        m = pd.DataFrame({"o": self.o, "h": self.h, "l": self.l, "c": self.c, "v": self.vol}, index=self.idx)
        if key in ("4h", "1d"):
            # New York WALL-CLOCK grid (closes 01/05/09/13/17/21 or 17:00 all year). Resampling the tz-aware index
            # in fixed steps is elapsed time and drifts an hour for the half of the year on the other side of DST.
            from ..bias import _localize
            rule, off = ("4h", "1h") if key == "4h" else ("24h", "17h")
            wall = m.set_axis(self.idx.tz_convert(NY).tz_localize(None))
            b = wall.resample(rule, offset=off, label="left", closed="left").agg(
                {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()
            b["start"] = _localize(b.index, NY).tz_convert("UTC").as_unit("ns").asi8
            b["end"] = _localize(b.index + pd.Timedelta(rule), NY).tz_convert("UTC").as_unit("ns").asi8
            b.index = _localize(b.index, NY)
            self._bars[key] = b
            return b
        else:
            mins = 60 if key == "1h" else int(tf)
            r = m.resample(f"{mins}min", label="left", closed="left")
            step = pd.Timedelta(minutes=mins)
        b = pd.DataFrame({"o": r["o"].first(), "h": r["h"].max(), "l": r["l"].min(), "c": r["c"].last(),
                          "v": r["v"].sum()}).dropna()
        b["start"] = b.index.tz_convert("UTC").as_unit("ns").asi8
        b["end"] = (b.index + step).tz_convert("UTC").as_unit("ns").asi8
        b.index = b.index.tz_convert(NY)
        self._bars[key] = b
        return b

    def last_closed(self, tf, t_ns) -> int:
        """Index of the last candle of `tf` complete at time t (−1 if none)."""
        return int(np.searchsorted(self.bars(tf)["end"].to_numpy(), t_ns, side="right")) - 1

    def minute_at(self, t_ns) -> int:
        """First minute index at/after t."""
        return int(np.searchsorted(self.ns, t_ns))

    def slice(self, i0: int, i1: int) -> "Market":
        """A sub-market (used by the look-ahead audit)."""
        return Market(self.symbol, self.ns[i0:i1], self.bid_o[i0:i1], self.bid_h[i0:i1], self.bid_l[i0:i1],
                      self.bid_c[i0:i1], self.ask_o[i0:i1], self.ask_h[i0:i1], self.ask_l[i0:i1], self.ask_c[i0:i1],
                      self.vol[i0:i1], self.dataset)


def _read_exports(files: list[Path]) -> pd.DataFrame:
    parts = []
    for f in files:
        d = pd.read_csv(f)
        d.index = pd.to_datetime(d.pop("time"), utc=True)
        parts.append(d)
    d = pd.concat(parts).sort_index()
    return d[~d.index.duplicated()]


def from_frame(d: pd.DataFrame, symbol: str = "XAUUSD", ds: str = "") -> Market:
    """A Market from a minute frame with bid_*/ask_* columns (UTC index) — tests and ad-hoc data."""
    arr = [d[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")]
    vol = d["volume"].to_numpy(float) if "volume" in d else np.ones(len(d))
    return Market(symbol, d.index.as_unit("ns").asi8, *arr, vol, dataset=ds)


KEYS = ("ns", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "vol")


def _cache_dir(ds: str, symbol: str) -> Path:
    return ROOT / "cache" / f"{ds}_{symbol}"


def _sig(files: list[Path]) -> str:
    return "|".join(f"{f}:{f.stat().st_mtime_ns}:{f.stat().st_size}" for f in files)


def build_cache(ds: str, symbol: str) -> Path:
    """Write (or refresh) the uncompressed .npy cache of one dataset/symbol; returns its folder."""
    files = export_files(ds, symbol)
    if not files:
        raise FileNotFoundError(f"no {symbol} data in dataset {ds!r} ({', '.join(datasets()[ds]['sets'])})")
    sig, cd = _sig(files), _cache_dir(ds, symbol)
    if (cd / "sig.txt").exists() and (cd / "sig.txt").read_text() == sig and all((cd / f"{k}.npy").exists() for k in KEYS):
        return cd
    d = _read_exports(files)
    arr = {k: d[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")}
    arr["vol"] = d["volume"].to_numpy(float) if "volume" in d else np.ones(len(d))
    arr["ns"] = d.index.as_unit("ns").asi8
    cd.mkdir(parents=True, exist_ok=True)
    for k, v in arr.items():
        np.save(cd / f"{k}.npy", v)
    (cd / "sig.txt").write_text(sig)
    return cd


def load(ds: str, symbol: str) -> Market:
    cd = build_cache(ds, symbol)
    return Market(symbol, *(np.load(cd / f"{k}.npy") for k in KEYS), dataset=ds)


def window(ds: str, symbol: str, t0_ns: int, t1_ns: int, max_minutes: int = 200_000) -> Market:
    """A small slice [t0, t1) read through memory maps (no full load) — for the dashboard's trade charts."""
    cd = _cache_dir(ds, symbol)
    if not (cd / "ns.npy").exists():
        cd = build_cache(ds, symbol)
    ns = np.load(cd / "ns.npy", mmap_mode="r")
    i0, i1 = (int(x) for x in np.searchsorted(ns, [t0_ns, t1_ns]))
    i1 = min(i1, i0 + max_minutes)
    return Market(symbol, *(np.array(np.load(cd / f"{k}.npy", mmap_mode="r")[i0:i1]) for k in KEYS), dataset=ds)
