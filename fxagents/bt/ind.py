"""Causal indicator helpers for backtest plugins. Every array is aligned to its candles: the value at candle i is known
at that candle's `end`. Use Market.last_closed(tf, t) to read the value that was known at time t."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(x, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def sma(x, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).rolling(n, min_periods=n).mean().to_numpy()


def wilder(x, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def atr(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    """Wilder ATR of a candle frame (columns h l c)."""
    pc = b["c"].shift()
    tr = pd.concat([b["h"] - b["l"], (b["h"] - pc).abs(), (b["l"] - pc).abs()], axis=1).max(axis=1)
    return wilder(tr.to_numpy(), n)


def adx(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    """Wilder ADX of a candle frame (columns h l c)."""
    h, l, c = (b[k].to_numpy(float) for k in "hlc")
    up, dn = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    pdm[0] = mdm[0] = np.nan
    atr_ = wilder(tr[1:], n)
    pdi = 100 * wilder(pdm[1:], n) / atr_
    mdi = 100 * wilder(mdm[1:], n) / atr_
    s = pdi + mdi
    dx = 100 * np.abs(pdi - mdi) / np.where(s == 0, np.nan, s)
    dx = pd.Series(dx).fillna(0.0).where(pd.Series(s).notna()).to_numpy()
    return np.r_[np.nan, wilder(dx, n)]


def rsi(c, n: int = 14) -> np.ndarray:
    d = np.diff(np.asarray(c, float), prepend=np.nan)
    up, dn = wilder(np.clip(d, 0, None), n), wilder(np.clip(-d, 0, None), n)
    return 100 - 100 / (1 + up / np.where(dn == 0, np.nan, dn))


def efficiency_ratio(c, n: int) -> np.ndarray:
    s = pd.Series(np.asarray(c, float))
    net = (s - s.shift(n)).abs()
    tot = s.diff().abs().rolling(n).sum()
    return np.where(tot > 0, net / tot, np.nan)


def swings(h, l, k: int = 2):
    """Fractal swing highs / lows (beating k candles each side). Returns, per candle, the LAST CONFIRMED swing high and
    swing low as of that candle's close (a swing at i is known at i + k) — safe to read without look-ahead."""
    h, l = np.asarray(h, float), np.asarray(l, float)
    n = len(h)
    sh, sl = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(k, n - k):
        win_h = np.r_[h[i - k:i], h[i + 1:i + k + 1]]
        win_l = np.r_[l[i - k:i], l[i + 1:i + k + 1]]
        if h[i] > win_h.max():
            sh[i + k] = h[i]
        if l[i] < win_l.min():
            sl[i + k] = l[i]
    return pd.Series(sh).ffill().to_numpy(), pd.Series(sl).ffill().to_numpy()


def vwap(m, anchor_mod: int = 1080) -> np.ndarray:
    """Per-minute VWAP (typical price × tick volume) of a Market, reset each day at NY minute `anchor_mod`
    (1080 = 18:00 trading-day anchor; 570 = 09:30 cash open — minutes before the anchor carry the previous VWAP
    when anchored at 18:00, or the plain typical price before 09:30)."""
    tp = (m.h + m.l + m.c) / 3
    v = np.clip(m.vol, 1, None)
    if anchor_mod == 1080:
        g = m.sess
        cv = pd.Series(tp * v).groupby(g).cumsum().to_numpy()
        cw = pd.Series(v).groupby(g).cumsum().to_numpy()
        return cv / cw
    on = m.mod >= anchor_mod
    vv = np.where(on, v, 0.0)
    cv = pd.Series(tp * vv).groupby(m.day).cumsum().to_numpy()
    cw = pd.Series(vv).groupby(m.day).cumsum().to_numpy()
    out = tp.copy()
    np.divide(cv, cw, out=out, where=cw > 0)
    return out


def day_range(m, start_mod: int, end_mod: int, use_sess: bool = False) -> dict[int, tuple[float, float, int]]:
    """High / low / minute-count of each day between NY minutes [start_mod, end_mod) — e.g. the Asian or opening range.
    Keys = NY calendar day (or trading day with use_sess). Known only once end_mod has passed."""
    key = m.sess if use_sess else m.day
    if start_mod < end_mod:
        sel = (m.mod >= start_mod) & (m.mod < end_mod)
    else:                                                  # wraps midnight, e.g. 18:00 → 02:00
        sel = (m.mod >= start_mod) | (m.mod < end_mod)
    df = pd.DataFrame({"k": key[sel], "h": m.h[sel], "l": m.l[sel]})
    g = df.groupby("k").agg(h=("h", "max"), l=("l", "min"), n=("h", "size"))
    return {int(k): (float(r.h), float(r.l), int(r.n)) for k, r in g.iterrows()}
