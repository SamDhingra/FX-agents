"""gpt_c03_orb_acceptance — ChatGPT round 2, C03: opening-range acceptance breakout (NAS100 M15).

Range = high/low of the 09:30 and 09:45 candles; ATR frozen at 10:00. Two consecutive closes more than 0.10 ATR above the
range high (the close before them not above) → buy next open, stop at the range midpoint. Mirror for shorts. One trade
a day, fills 10:30–12:00 NY, target 2R, out after 4h or 15:45.

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


class GptC03OrbAcceptance(Strategy):
    name = "gpt_c03_orb_acceptance"
    symbol = "NDQ"
    description = "M15: two closes beyond the 09:30–10:00 range; stop at its midpoint; 2R, 4h, fills 10:30–12:00 NY."
    params = {"brk_atr": 0.10}
    exits = Exits(target_r=2.0, max_hold_min=240, flat_at=945)
    entry_windows = [(630, 721)]
    max_per_day = 1
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        out = []
        pos = {(d, t): i for i, (d, t) in enumerate(zip(day, mod))}
        for d in np.unique(day):
            i0, i1 = pos.get((d, 570)), pos.get((d, 585))
            if i0 is None or i1 is None or i1 != i0 + 1 or i0 < 100 or not np.isfinite(a[i1]):
                continue
            hi, lo, at = max(h[i0], h[i1]), min(l[i0], l[i1]), a[i1]
            midp = (hi + lo) / 2
            done = False
            for i in range(i1 + 2, len(b)):
                if day[i] != d or mod[i] > 705 or done:
                    break
                for side in (1, -1):
                    thr = (hi if side > 0 else lo) + side * P["brk_atr"] * at
                    if side * (c[i] - thr) > 0 and side * (c[i - 1] - thr) > 0 and side * (c[i - 2] - thr) <= 0 \
                            and day[i - 1] == d:
                        s = _sig(m, end[i], side, c[i], midp, at, "long" if side > 0 else "short")
                        if s:
                            out.append(s)
                        done = True
                        break
        return out
