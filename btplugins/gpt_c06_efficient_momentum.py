"""gpt_c06_efficient_momentum — ChatGPT round 2, C06: efficient six-bar momentum (US30 H1).

M = (close − close 6 bars ago) / ATR. Buy on the first cross from M < 1.5 to M >= 1.5 with efficiency ratio ER(6) >= 0.60
and the candle's range <= 1.5 ATR; sell the mirror. Stop 1 ATR, target 2R. Fills 10:00–12:00 NY, out after 6h or 15:00.

Common rules (GPT's, kept): completed mid candles on the named timeframe, Wilder ATR14, next-candle-open entry, stop
0.5–2.5 ATR and at least the friction minimum (gold 9.1, NDQ 32.5, US30 39 points), max 2 entries a day, one at a time,
no breakeven/trailing/partials, H1 out by 15:00 NY and M15 by 15:45. No news blackout (GPT had none).
Differences: real 1-minute bid/ask fills (stops/targets checked minute by minute instead of "stop first" inside a candle);
ATR stops are placed from the signal close rather than the fill; GPT's 0.25-ATR opening-gap skip is not applied.
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind

MIN_STOP = {"XAUUSD": 9.1, "NDQ": 32.5, "US30": 39.0}     # GPT's "round-trip friction <= 10% of the stop" at its spreads


def _bars(m, tf):
    b = m.bars(tf)
    t = b.index
    return (b, b.o.to_numpy(), b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy(), b.end.to_numpy(),
            (t.hour * 60 + t.minute).to_numpy(), np.asarray([d.toordinal() for d in t.date]), t.dayofweek.to_numpy())


def _sig(m, t, side, ref, stop, atr, tag, **kw):
    """GPT's risk filters: stop 0.5–2.5 ATR, at least the friction minimum, at most 10% of price (checked at the fill)."""
    lo = max(0.5 * atr, MIN_STOP.get(m.symbol, 0.0))
    hi = min(2.5 * atr, 0.10 * ref)
    if not (np.isfinite(stop) and np.isfinite(atr)) or lo > hi:
        return None
    return Signal(t=int(t), side=side, stop=float(stop), risk_min=float(lo), risk_max=float(hi), tag=tag, **kw)


class GptC06EfficientMomentum(Strategy):
    name = "gpt_c06_efficient_momentum"
    symbol = "US30"
    description = "H1: 6-bar move crosses 1.5 ATR with efficiency >= 0.6; 1 ATR stop, 2R, fills 10–12 NY."
    params = {"n": 6, "m_thr": 1.5, "er_min": 0.60, "max_range_atr": 1.5, "stop_atr": 1.0}
    exits = Exits(target_r=2.0, max_hold_min=360, flat_at=900)
    entry_windows = [(600, 721)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, "1h")
        a = ind.atr(b, 14)
        n = P["n"]
        mom = np.full(len(b), np.nan)
        mom[n:] = (c[n:] - c[:-n]) / a[n:]
        er = ind.efficiency_ratio(c, n)
        out = []
        for i in range(100, len(b)):
            if not (np.isfinite(mom[i]) and np.isfinite(mom[i - 1]) and np.isfinite(er[i])):
                continue
            if er[i] < P["er_min"] or h[i] - l[i] > P["max_range_atr"] * a[i]:
                continue
            for side in (1, -1):
                if side * mom[i] >= P["m_thr"] and side * mom[i - 1] < P["m_thr"]:
                    s = _sig(m, end[i], side, c[i], c[i] - side * P["stop_atr"] * a[i], a[i], "long" if side > 0 else "short")
                    if s:
                        out.append(s)
        return out
