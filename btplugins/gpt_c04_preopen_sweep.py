"""gpt_c04_preopen_sweep — ChatGPT round 2, C04: pre-open range sweep and reclaim (Gold M15).

Range = all 32 candles 00:00–07:45 NY, frozen at 08:00. Buy after a candle trades at least 0.10 ATR below the range low and
closes bullish more than 0.10 ATR back above it; stop 0.10 ATR below its low; only if the range high leaves room for 2R.
Mirror for shorts. One attempt per side a day, fills 08:15–11:30 NY, target 2R, out after 4h or 15:45.

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


class GptC04PreopenSweep(Strategy):
    name = "gpt_c04_preopen_sweep"
    symbol = "XAUUSD"
    description = "M15: sweep of the 00:00–08:00 range and close back inside; room for 2R; fills 08:15–11:30 NY."
    params = {"sweep_atr": 0.10, "reclaim_atr": 0.10, "buf_atr": 0.10, "target_r": 2.0}
    exits = Exits(target_r=2.0, max_hold_min=240, flat_at=945)
    entry_windows = [(495, 691)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        out = []
        for d in np.unique(day):
            sel = np.flatnonzero((day == d) & (mod < 480))
            if len(sel) != 32 or sel[0] < 100:
                continue
            hi, lo = h[sel].max(), l[sel].min()
            seen = set()
            for i in range(sel[-1] + 1, len(b)):
                if day[i] != d or mod[i] > 675:
                    break
                if not np.isfinite(a[i]):
                    continue
                for side in (1, -1):
                    edge, far = (lo, hi) if side > 0 else (hi, lo)
                    ext = l[i] if side > 0 else h[i]
                    if side in seen or not (side * (edge - P["sweep_atr"] * a[i] * side - ext) >= 0
                                            and side * (c[i] - (edge + side * P["reclaim_atr"] * a[i])) > 0
                                            and side * (c[i] - o[i]) > 0):
                        continue
                    seen.add(side)
                    stop = ext - side * P["buf_atr"] * a[i]
                    if side * (far - c[i]) < P["target_r"] * abs(c[i] - stop):
                        continue
                    s = _sig(m, end[i], side, c[i], stop, a[i], "long" if side > 0 else "short")
                    if s:
                        out.append(s)
        return out
