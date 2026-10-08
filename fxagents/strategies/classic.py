"""Classic technical strategies: support/resistance rejection, RSI, MACD."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import RawSignal, Strategy


class SRRejection(Strategy):
    name = "sr_rejection"
    family = "sr"
    description = ("Support/resistance: horizontal levels built from clustered swing points (≥2 touches). "
                   "Enter on a rejection candle at the level, stop beyond the wick.")
    default_params = dict(swing=3, lookback=240, cluster_atr=0.3, min_touches=2, wick_frac=0.4,
                          stop_buf_atr=0.15, refresh=12)
    param_grid = {"swing": [3, 5], "cluster_atr": [0.2, 0.3, 0.5], "min_touches": [2, 3],
                  "wick_frac": [0.3, 0.4, 0.5]}

    def _levels(self, piv, i, a_i):
        p = self.params
        pts = sorted(q.price for q in piv if q.known_at <= i < q.until and q.idx >= i - p["lookback"])
        levels, cluster = [], []
        for x in pts:
            if cluster and x - cluster[-1] > p["cluster_atr"] * a_i:
                if len(cluster) >= p["min_touches"]:
                    levels.append(float(np.mean(cluster)))
                cluster = []
            cluster.append(x)
        if len(cluster) >= p["min_touches"]:
            levels.append(float(np.mean(cluster)))
        return levels

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        O, H, L, C = (df[c].to_numpy() for c in ("open", "high", "low", "close"))
        piv = self.pivots(df, ctx, p["swing"], p["swing"])
        out, levels, last_i = [], [], -999
        for i in range(p["swing"] * 2, len(C)):
            if i % p["refresh"] == 0 or not levels:
                levels = self._levels(piv, i, a[i])
            rng = H[i] - L[i]
            if rng <= 0 or i - last_i < 3:
                continue
            tol = 0.15 * a[i]
            for lvl in levels:
                # support: wick into level, close back above, lower wick dominant
                if L[i] <= lvl + tol and C[i] > lvl and (min(O[i], C[i]) - L[i]) / rng >= p["wick_frac"] and C[i] > O[i]:
                    out.append(RawSignal(i, 1, C[i], min(L[i], lvl) - p["stop_buf_atr"] * a[i],
                                         f"Support rejection @ {lvl:.2f}", features={"level": lvl}))
                    last_i = i; break
                if H[i] >= lvl - tol and C[i] < lvl and (H[i] - max(O[i], C[i])) / rng >= p["wick_frac"] and C[i] < O[i]:
                    out.append(RawSignal(i, -1, C[i], max(H[i], lvl) + p["stop_buf_atr"] * a[i],
                                         f"Resistance rejection @ {lvl:.2f}", features={"level": lvl}))
                    last_i = i; break
        return out


class RSIReversion(Strategy):
    name = "rsi_pullback"
    family = "rsi"
    description = ("RSI: with the trend (EMA200), buy when RSI recovers from the pullback threshold "
                   "(sell the mirror), stop beyond the recent swing.")
    default_params = dict(low=35, trend_filter=True, swing_bars=6, stop_buf_atr=0.15)
    param_grid = {"low": [25, 30, 35, 40], "trend_filter": [True, False], "swing_bars": [4, 6, 10]}

    def _scan(self, df, ctx):
        p, a, r, e = self.params, ctx["atr"], ctx["rsi"], ctx["ema200"]
        H, L, C = (df[c].to_numpy() for c in ("high", "low", "close"))
        lo, n = p["low"], p["swing_bars"]
        hi = 100 - lo  # symmetric thresholds keep long/short behaviour mirrored
        out = []
        for i in range(max(n, 200), len(C)):
            up = C[i] > e[i]
            if r[i - 1] < lo <= r[i] and (up or not p["trend_filter"]):
                out.append(RawSignal(i, 1, C[i], L[i - n:i + 1].min() - p["stop_buf_atr"] * a[i],
                                     f"RSI recovered above {lo}", features={"rsi": float(r[i])}))
            elif r[i - 1] > hi >= r[i] and (not up or not p["trend_filter"]):
                out.append(RawSignal(i, -1, C[i], H[i - n:i + 1].max() + p["stop_buf_atr"] * a[i],
                                     f"RSI rolled below {hi}", features={"rsi": float(r[i])}))
        return out

    def bias(self, df, ctx):
        return pd.Series(np.sign(ctx["rsi"] - 50), index=df.index)


class MACDCross(Strategy):
    name = "macd_cross"
    family = "macd"
    description = ("MACD: signal-line cross on the correct side of zero, aligned with EMA50 trend, "
                   "stop beyond the recent swing.")
    default_params = dict(zero_filter=True, trend_filter=True, swing_bars=6, stop_buf_atr=0.15)
    param_grid = {"zero_filter": [True, False], "trend_filter": [True, False], "swing_bars": [4, 6, 10]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        m, s, e = ctx["macd"], ctx["macd_sig"], ctx["ema50"]
        H, L, C = (df[c].to_numpy() for c in ("high", "low", "close"))
        n, out = p["swing_bars"], []
        for i in range(max(n, 50), len(C)):
            if m[i - 1] <= s[i - 1] and m[i] > s[i] and (not p["zero_filter"] or m[i] < 0) \
                    and (not p["trend_filter"] or C[i] > e[i]):
                out.append(RawSignal(i, 1, C[i], L[i - n:i + 1].min() - p["stop_buf_atr"] * a[i],
                                     "MACD bull cross", features={"hist": float(m[i] - s[i])}))
            elif m[i - 1] >= s[i - 1] and m[i] < s[i] and (not p["zero_filter"] or m[i] > 0) \
                    and (not p["trend_filter"] or C[i] < e[i]):
                out.append(RawSignal(i, -1, C[i], H[i - n:i + 1].max() + p["stop_buf_atr"] * a[i],
                                     "MACD bear cross", features={"hist": float(m[i] - s[i])}))
        return out

    def bias(self, df, ctx):
        return pd.Series(np.sign(ctx["macd_hist"]), index=df.index)
