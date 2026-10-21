"""gpt_c10_afternoon_continuation — ChatGPT round 2, C10: morning-to-afternoon continuation (US30 M15).

At 13:00 NY: the move from the previous weekday's 16:00 close to today's 10:00 close and to the 13:00 close have the same
sign, the move since the 09:30 open is at least 1 ATR that way, and ER(12) >= 0.40 → enter that way at 13:00 with a
1.25 ATR stop. Target 2R, out at 15:45. All 09:30–13:00 candles must be there. One a day.

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


class GptC10AfternoonContinuation(Strategy):
    name = "gpt_c10_afternoon_continuation"
    symbol = "US30"
    description = "M15: morning direction kept to 13:00 (>=1 ATR from the open, efficient) → in at 13:00; 2R, out 15:45."
    params = {"move_atr": 1.0, "er_n": 12, "er_min": 0.40, "stop_atr": 1.25}
    exits = Exits(target_r=2.0, flat_at=945)
    entry_windows = [(780, 781)]
    max_per_day = 1
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        er = ind.efficiency_ratio(c, P["er_n"])
        pos = {(d, t): i for i, (d, t) in enumerate(zip(day, mod))}
        days = sorted({int(d) for d, w in zip(day, dow) if w < 5})
        out = []
        for prev, d in zip(days, days[1:]):
            ip, i0, i10, i13 = pos.get((prev, 945)), pos.get((d, 570)), pos.get((d, 585)), pos.get((d, 765))
            if None in (ip, i0, i10, i13) or i13 - i0 != 13 or i0 < 100 or not (np.isfinite(a[i13]) and np.isfinite(er[i13])):
                continue
            r10, r13 = c[i10] - c[ip], c[i13] - c[ip]
            if r10 == 0 or np.sign(r10) != np.sign(r13):
                continue
            side = 1 if r13 > 0 else -1
            if side * (c[i13] - o[i0]) < P["move_atr"] * a[i13] or er[i13] < P["er_min"]:
                continue
            s = _sig(m, end[i13], side, c[i13], c[i13] - side * P["stop_atr"] * a[i13], a[i13], "long" if side > 0 else "short")
            if s:
                out.append(s)
        return out
