"""Backtest data: OANDA 1-minute bid/ask exports → one Market per (dataset, symbol), cached as .npz for fast reloads.

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
        """Mid candles: tf = minutes (int) or "1h", "4h" (NY 01/05/09/13/17/21 closes), "1d" (NY 17:00 close).
        Columns o h l c v start end (ns). Cached."""
        key = str(tf)
        if key in self._bars:
            return self._bars[key]
        m = pd.DataFrame({"o": self.o, "h": self.h, "l": self.l, "c": self.c, "v": self.vol}, index=self.idx)
        if key == "4h":
            r = m.tz_convert(NY).resample("4h", offset="1h", label="left", closed="left")
            step = pd.Timedelta(hours=4)
        elif key == "1d":
            r = m.tz_convert(NY).resample("1D", offset="17h", label="left", closed="left")
            step = pd.Timedelta(days=1)
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


def load(ds: str, symbol: str, cache: bool = True) -> Market:
    files = export_files(ds, symbol)
    if not files:
        raise FileNotFoundError(f"no {symbol} data in dataset {ds!r} ({', '.join(datasets()[ds]['sets'])})")
    sig = "|".join(f"{f}:{f.stat().st_mtime_ns}:{f.stat().st_size}" for f in files)
    cp = ROOT / "cache" / f"{ds}_{symbol}.npz"
    if cache and cp.exists():
        z = np.load(cp, allow_pickle=False)
        if str(z["sig"]) == sig:
            return Market(symbol, *(z[k] for k in ("ns", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l",
                                                   "ask_c", "vol")), dataset=ds)
    d = _read_exports(files)
    arr = {k: d[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")}
    arr["vol"] = d["volume"].to_numpy(float) if "volume" in d else np.ones(len(d))
    arr["ns"] = d.index.as_unit("ns").asi8
    if cache:
        cp.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cp, sig=np.array(sig), **arr)
    return Market(symbol, arr["ns"], arr["bid_o"], arr["bid_h"], arr["bid_l"], arr["bid_c"], arr["ask_o"],
                  arr["ask_h"], arr["ask_l"], arr["ask_c"], arr["vol"], dataset=ds)
