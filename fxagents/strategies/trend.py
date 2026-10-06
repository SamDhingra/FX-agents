"""Trend-following day trades: the higher timeframe sets the direction, the entry timeframe times it.

"Go with the trend": only longs while the 1-hour (or 4-hour) trend is up, only shorts while it's down,
and the entry is either a pullback that holds or a breakout in the trend's direction. Meant for 15m and
1h entries with wider targets (the `trend` exit profile: first target 2R, half banked, the rest trailed,
held up to 8 hours or the 15:50 flatten), so the spread is a small share of each trade.

Higher-timeframe trend (`htf` = 1h, completed bars only; the live trader scans 700 entry bars, which at
15m+ covers the EMA50 warm-up — so these run on 15m, 30m and 1h only):
  ema        EMA20 above EMA50 and the close above EMA50 (mirror for down)
  structure  higher highs / higher lows by close (structure.htf_trend)

trend_pullback — price dips to the entry-timeframe EMA (`ema` 20 or 50) after being above it, and the
  bar closes back above it, bullish. Stop below the lowest low of the last `swing_bars` bars (+0.2 ATR).
trend_breakout — the close breaks the highest high of the previous `n` bars while the entry-TF EMA50 is
  rising under price. Stop `stop_atr` × ATR below the entry. At most one signal per `n` bars per side.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import structure as sx
from .base import RawSignal
from .ict import _Fast


def htf_ema_trend(df: pd.DataFrame, ctx: dict, rule: str = "1h", fast: int = 20, slow: int = 50) -> np.ndarray:
    """+1 / −1 / 0 from completed higher-timeframe bars (known only once that bar has closed)."""
    key = ("_htf_ema", rule, fast, slow)
    if key in ctx:
        return ctx[key]
    hb = df["close"].resample(rule, label="left", closed="left").last().dropna()
    ef, es = hb.ewm(span=fast, adjust=False).mean(), hb.ewm(span=slow, adjust=False).mean()
    tr = np.where((ef > es) & (hb > es), 1.0, np.where((ef < es) & (hb < es), -1.0, 0.0))
    tr[:slow] = 0.0                                   # EMA warm-up (same cut-off however much history follows)
    known = pd.Series(tr, index=hb.index + pd.Timedelta(rule))
    u = known.index.union(ctx["close_ts"])
    ctx[key] = known.reindex(u).ffill().reindex(ctx["close_ts"]).fillna(0).to_numpy()
    return ctx[key]


def _htf(df, ctx, p) -> np.ndarray:
    return htf_ema_trend(df, ctx, p["htf"]) if p["trend"] == "ema" else sx.htf_trend(df, ctx, p["htf"])


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


class TrendPullback(_Fast):
    name = "trend_pullback"
    family = "trend"
    description = ("Trend pullback: with the 1-hour trend (EMA20/50), buy the first dip to the entry-timeframe EMA "
                   "that closes back above it with a bullish candle (mirror for shorts); stop below the recent low.")
    default_params = dict(htf="1h", trend="ema", ema=20, swing_bars=5, stop_buf_atr=0.2)
    param_grid = {"trend": ["ema", "structure"], "ema": [20, 50], "swing_bars": [3, 8]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        ht = _htf(df, ctx, p)
        out = []
        for v in sx.views(df, ctx, 2):
            O, H, L, C = v.O, v.H, v.L, v.C
            e = _ema(C, p["ema"])
            e50 = _ema(C, 50)
            n = p["swing_bars"]
            for i in range(max(60, n + 1), len(C)):
                if ht[i] * v.side <= 0 or e[i] <= e50[i]:
                    continue
                if not (L[i - 1] > e[i - 1] and L[i] <= e[i] and C[i] > e[i] and C[i] > O[i]):
                    continue
                stop = L[i - n + 1:i + 1].min() - p["stop_buf_atr"] * a[i]
                out.append(RawSignal(i, v.side, v.px(C[i]), v.px(stop),
                                     f"Trend pullback to EMA{p['ema']} with the {p['htf']} trend ({p['trend']})"))
        return out


class TrendBreakout(_Fast):
    name = "trend_breakout"
    family = "trend"
    description = ("Trend breakout: with the 1-hour trend, buy a close above the previous 20 bars' high while price "
                   "is above a rising EMA50 (mirror for shorts); stop 1.5 ATR below the entry.")
    default_params = dict(htf="1h", trend="ema", n=20, stop_atr=1.5)
    param_grid = {"trend": ["ema", "structure"], "n": [10, 40], "stop_atr": [1.0, 2.0]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        ht = _htf(df, ctx, p)
        n = p["n"]
        out = []
        for v in sx.views(df, ctx, 2):
            H, C = v.H, v.C
            e50 = _ema(C, 50)
            hh = pd.Series(H).shift(1).rolling(n, min_periods=n).max().to_numpy()
            last = -10 ** 9
            for i in range(max(60, n + 1), len(C)):
                if ht[i] * v.side <= 0 or not np.isfinite(hh[i]) or i - last < n:
                    continue
                if C[i] > hh[i] and C[i] > e50[i] > e50[i - 5]:
                    last = i
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(C[i] - p["stop_atr"] * a[i]),
                                         f"Trend breakout of the {n}-bar high with the {p['htf']} trend ({p['trend']})"))
        return out
