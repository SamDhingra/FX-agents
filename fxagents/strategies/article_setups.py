"""Gold setups from ThinkMarkets' "Gold trading strategy 2026" (Feb 2026), formalised so they can be tested.

Only the two that fit an intraday, flat-by-15:50 bot are here; the article's EMA-cross trend trade (H4/daily,
held for days) and its daily-chart swing trade don't fit the holding rules, and its break-and-retest
price-action entry is already covered by smc_bos_retest / sr_rejection.

london_breakout — "London Open breakout":
  • Range: the Asian session box, 20:00 NY (prior evening) up to `range_end`. The article says "up to
    08:00 GMT", which is 03:00 NY in winter and 04:00 NY in summer, so both are tested.
  • Break: the first bar that CLOSES outside the box before `until` (08:00 NY), optionally only if its
    body is ≥ `min_body_atr` ATR ("decisive"). One trade per side per day.
  • Stop: `stop_atr` × ATR(14) beyond the breakout candle's low (longs) / high (shorts) — the article's
    1.5 × ATR — or the other side of the box.
  • Run it on 30m and 1h bars as the article does; the grid also tries 15m.

rsi_extreme_fade — the article's scalping fade:
  • RSI(14) spikes beyond `extreme` (80 / 20), then the trade is the bar where it comes back inside
    `reenter` (70 / 30) within `max_wait` bars: short after an overbought spike, long after oversold.
  • Stop beyond the spike's extreme plus a small ATR buffer (the article's fixed 30–50 pips is replaced
    by the bot's usual ATR floor). Target: the exit profile (the scalp profile = all out at 1R).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import structure as sx
from .base import RawSignal
from .ict import _Fast, _tday


class LondonBreakout(_Fast):
    name = "london_breakout"
    family = "breakout"
    description = ("London Open breakout of the Asian range: box from 20:00 NY to 03:00 NY; first candle that "
                   "closes outside it before 08:00 NY is the entry, stop 1.5 ATR beyond the breakout candle.")
    default_params = dict(range_end=3, until=8, min_body_atr=0.0, stop="atr", stop_atr=1.5)
    param_grid = {"range_end": [3, 4], "min_body_atr": [0.0, 0.5], "stop": ["atr", "box"], "until": [6, 8]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        td = _tday(df, ctx)
        idx = df.index
        hr = np.asarray(idx.hour)
        ct = ctx["close_ts"]
        ct_h = np.asarray(ct.hour + ct.minute / 60.0)
        in_box = (hr >= 20) | (hr < p["range_end"])
        out = []
        for v in sx.views(df, ctx, 2):
            O, H, L, C = v.O, v.H, v.L, v.C
            day, hi, lo, done = None, -np.inf, np.inf, False
            for i in range(len(C)):
                if td[i] != day:
                    day, hi, lo, done = td[i], -np.inf, np.inf, False
                if in_box[i]:
                    hi, lo = max(hi, H[i]), min(lo, L[i])      # the box is still forming (known up to this bar)
                    continue
                if done or not np.isfinite(hi) or not (p["range_end"] <= ct_h[i] <= p["until"]) or hr[i] >= 17:
                    continue
                if C[i] <= hi:
                    continue
                if C[i] - O[i] < p["min_body_atr"] * a[i]:
                    continue
                done = True
                stop = (L[i] - p["stop_atr"] * a[i]) if p["stop"] == "atr" else (lo - 0.1 * a[i])
                out.append(RawSignal(i, v.side, v.px(C[i]), v.px(stop),
                                     f"London breakout: close {'above' if v.side > 0 else 'below'} the Asian range",
                                     structural_target=v.px(C[i] + (hi - lo)),
                                     features={"box_atr": float((hi - lo) / a[i]) if a[i] else None}))
        return out


class RSIExtremeFade(_Fast):
    name = "rsi_extreme_fade"
    family = "rsi_fade"
    description = ("RSI fade: after RSI spikes past 80 (20), sell (buy) the bar it re-enters 70 (30); stop beyond "
                   "the spike extreme. Mean reversion for 1m–5m scalps.")
    default_params = dict(extreme=80, reenter=70, max_wait=6, stop_buf_atr=0.2)
    param_grid = {"extreme": [80, 90], "reenter": [70, 60], "max_wait": [3, 6, 12]}

    def _scan(self, df, ctx):
        p, a, r = self.params, ctx["atr"], ctx["rsi"]
        out = []
        for v in sx.views(df, ctx, 2):
            # view orientation: longs fade an OVERSOLD spike (RSI of real price < 100-extreme)
            rr = r if v.side > 0 else 100 - r
            lo_x, lo_re = 100 - p["extreme"], 100 - p["reenter"]
            L, C = v.L, v.C
            armed, low = None, np.inf
            for i in range(1, len(C)):
                if not np.isfinite(rr[i]):
                    continue
                if rr[i] < lo_x:
                    armed, low = i, min(low if armed is not None else np.inf, L[i])
                    continue
                if armed is None:
                    continue
                low = min(low, L[i])
                if i - armed > p["max_wait"]:
                    armed, low = None, np.inf
                    continue
                if rr[i] >= lo_re and rr[i - 1] < lo_re:
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(low - p["stop_buf_atr"] * a[i]),
                                         f"RSI fade: back inside {p['reenter']}/{100 - p['reenter']} after a "
                                         f"{p['extreme']}/{100 - p['extreme']} spike", features={"rsi": float(r[i])}))
                    armed, low = None, np.inf
        return out
