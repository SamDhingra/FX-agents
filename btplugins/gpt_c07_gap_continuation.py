"""gpt_c07_gap_continuation — ChatGPT round 2, C07: cash-session gap continuation (NAS100 M15).

Gap = today's 09:30 open − the previous weekday's 16:00 close (its 15:45 candle's close), 0.5–2.0 × the ATR known at 09:30.
For an up gap, the 09:30 and 09:45 candles both close above the 09:30 open and the second close is higher → buy at 10:00,
stop below the two candles' low − 0.10 ATR. Mirror for down gaps. Target 2R, out after 4h or 15:45. One a day.

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


class GptC07GapContinuation(Strategy):
    name = "gpt_c07_gap_continuation"
    symbol = "NDQ"
    description = "M15: 0.5–2 ATR gap from yesterday's 16:00, first two candles confirm → in at 10:00; 2R."
    params = {"gap_lo": 0.5, "gap_hi": 2.0, "buf_atr": 0.10}
    exits = Exits(target_r=2.0, max_hold_min=240, flat_at=945)
    entry_windows = [(600, 601)]
    max_per_day = 1
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        pos = {(d, t): i for i, (d, t) in enumerate(zip(day, mod))}
        days = sorted({int(d) for d, w in zip(day, dow) if w < 5})
        out = []
        for prev, d in zip(days, days[1:]):
            ip, i0, i1 = pos.get((prev, 945)), pos.get((d, 570)), pos.get((d, 585))
            if ip is None or i0 is None or i1 is None or i1 != i0 + 1 or i0 < 101 or not np.isfinite(a[i1]):
                continue
            atr0 = a[i0 - 1]
            gap = o[i0] - c[ip]
            side = 1 if gap > 0 else -1
            if not (P["gap_lo"] * atr0 <= abs(gap) <= P["gap_hi"] * atr0):
                continue
            if not (side * (c[i0] - o[i0]) > 0 and side * (c[i1] - o[i0]) > 0 and side * (c[i1] - c[i0]) > 0):
                continue
            ext = min(l[i0], l[i1]) if side > 0 else max(h[i0], h[i1])
            s = _sig(m, end[i1], side, c[i1], ext - side * P["buf_atr"] * a[i1], a[i1], "gap_up" if side > 0 else "gap_down")
            if s:
                out.append(s)
        return out
