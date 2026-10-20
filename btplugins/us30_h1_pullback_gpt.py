"""us30_h1_pullback_gpt — ChatGPT's "US30 H1 trend pullback" (OANDA_H1_Strategy_Research, 2026-10-20), ported as written.

GPT found it on 2 months of H1 candles: 4 training + 5 validation trades. Here it gets 2021 → Sep 2026 with real 1-minute
bid/ask fills. Rules, unchanged:
  • H1 mid candles. EMA20, EMA50 on closes; Wilder ATR14.
  • Long at an H1 close: EMA20 > EMA50, EMA20 above its value 3 bars earlier, previous close ≤ previous EMA20 and this
    close > this EMA20 (a pullback that closes back above the EMA20). Shorts mirror every inequality.
  • Filled at the next H1 open, only the 10:00, 11:00, 12:00 or 13:00 New York opens. Max 2 entries a day, one at a time.
  • Stop 1 × ATR14 (of the signal candle) from the signal close; target 1.5R; no breakeven / trailing / partials.
    (GPT measures the ATR from the fill; at the next minute's open the difference is a few points.)
  • Out after 3 hours or at 15:00 NY, whichever comes first.
  • Skipped when the stop is under 39 points (GPT's "friction ≤ 10% of the stop" rule at a 3-point spread).
  • No news blackout (GPT's test had none).
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


class Us30H1PullbackGpt(Strategy):
    name = "us30_h1_pullback_gpt"
    symbol = "US30"
    description = "H1: EMA20>EMA50 rising, close crosses back over EMA20 → next 10–13h NY open; 1 ATR stop, 1.5R, out 3h/15:00."
    params = {"fast": 20, "slow": 50, "slope_bars": 3, "atr": 14, "stop_atr": 1.0, "min_stop": 39.0, "use_trend": True}
    exits = Exits(target_r=1.5, max_hold_min=180, flat_at=900)
    entry_windows = [(600, 781)]          # fills at the 10:00 … 13:00 NY H1 opens
    max_per_day = 2
    news_block = None
    variants = {"no_trend_filter": {"use_trend": False}}

    def signals(self, m):
        P = self.params
        b = m.bars("1h")
        c = b.c.to_numpy()
        end = b.end.to_numpy()
        f, s = ind.ema(c, P["fast"]), ind.ema(c, P["slow"])
        a = ind.atr(b, P["atr"])
        k = P["slope_bars"]
        out = []
        for i in range(max(P["slow"], k) + 1, len(b)):
            if not (np.isfinite(f[i]) and np.isfinite(s[i]) and np.isfinite(a[i])) or a[i] * P["stop_atr"] < P["min_stop"]:
                continue
            for side in (1, -1):
                trend = side * (f[i] - s[i]) > 0 and side * (f[i] - f[i - k]) > 0
                cross = side * (c[i - 1] - f[i - 1]) <= 0 and side * (c[i] - f[i]) > 0
                if cross and (trend or not P["use_trend"]):
                    out.append(Signal(t=int(end[i]), side=side, stop=float(c[i] - side * P["stop_atr"] * a[i]),
                                      tag="long" if side > 0 else "short", info={"atr": round(float(a[i]), 1)}))
        return out
