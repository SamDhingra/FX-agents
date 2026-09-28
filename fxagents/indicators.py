"""Indicators and market-structure helpers. Everything here is causal (no look-ahead):
swing pivots carry the index at which they become *known* (pivot index + right bars)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().bfill()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


@dataclass
class Pivot:
    idx: int        # bar index of the swing point
    price: float
    kind: str       # "H" or "L"
    known_at: int   # first bar index at which the pivot is confirmed


def pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[Pivot]:
    """Fractal swing highs/lows, reduced to an alternating H/L sequence (keeps the extreme)."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    raw: list[Pivot] = []
    for i in range(left, n - right):
        wh = h[i - left:i + right + 1]
        wl = l[i - left:i + right + 1]
        if h[i] == wh.max() and (wh == h[i]).sum() == 1:
            raw.append(Pivot(i, float(h[i]), "H", i + right))
        if l[i] == wl.min() and (wl == l[i]).sum() == 1:
            raw.append(Pivot(i, float(l[i]), "L", i + right))
    raw.sort(key=lambda p: (p.idx, p.kind))
    out: list[Pivot] = []
    for p in raw:
        if out and out[-1].kind == p.kind:
            better = p.price > out[-1].price if p.kind == "H" else p.price < out[-1].price
            if better:
                out[-1] = Pivot(p.idx, p.price, p.kind, max(p.known_at, out[-1].known_at))
            continue
        out.append(p)
    return out


def known_pivots(pvts: list[Pivot], i: int) -> list[Pivot]:
    return [p for p in pvts if p.known_at <= i]


def htf_bias(df: pd.DataFrame, rule: str = "60min", n: int = 50) -> pd.Series:
    """+1 / -1 bias from completed higher-timeframe bars (close vs EMA), aligned to df without look-ahead."""
    htf = df.resample(rule, label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    e = ema(htf["close"], n)
    b = np.sign(htf["close"] - e)
    # a completed HTF bar labelled T is usable from T onward
    return b.reindex(df.index.union(b.index)).ffill().reindex(df.index).fillna(0)


def resample_ohlc(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df1m.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()


def in_windows(ts: pd.Timestamp, windows: list[list[str]]) -> bool:
    hm = ts.hour * 60 + ts.minute
    for a, b in windows:
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        if ah * 60 + am <= hm < bh * 60 + bm:
            return True
    return False
