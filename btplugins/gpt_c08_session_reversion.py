"""gpt_c08_session_reversion — ChatGPT round 2, C08: session mean reversion in low efficiency (Gold M15).

Session mean = average typical price (h+l+c)/3 of the M15 candles since 08:00 NY (at least 8). With ER(12) < 0.30: buy when
the previous close was more than 2 ATR below the mean known then and this close rises but stays below the current mean;
stop below the lowest low of the last 3 candles − 0.10 ATR; target = the current mean, skipped if under 1.5R away. Mirror for
shorts. Fills 10:00–13:00 NY, out after 3h or 15:45.

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


class GptC08SessionReversion(Strategy):
    name = "gpt_c08_session_reversion"
    symbol = "XAUUSD"
    description = "M15: stretched 2 ATR from the session mean in a choppy session, turn back → target the mean (>=1.5R)."
    params = {"min_bars": 8, "er_n": 12, "er_max": 0.30, "stretch_atr": 2.0, "buf_atr": 0.10, "min_r": 1.5}
    exits = Exits(max_hold_min=180, flat_at=945)
    entry_windows = [(600, 781)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        er = ind.efficiency_ratio(c, P["er_n"])
        tp = (h + l + c) / 3
        out = []
        cur_day, s_sum, s_n, prev_mean = None, 0.0, 0, np.nan
        for i in range(len(b)):
            if day[i] != cur_day:
                cur_day, s_sum, s_n, prev_mean = day[i], 0.0, 0, np.nan
            if mod[i] < 480:
                continue
            s_sum += tp[i]
            s_n += 1
            mean = s_sum / s_n
            ok = i >= 100 and s_n >= P["min_bars"] and np.isfinite(prev_mean) and np.isfinite(er[i]) and er[i] < P["er_max"] \
                and np.isfinite(a[i]) and np.isfinite(a[i - 1])
            if ok:
                for side in (1, -1):
                    if side * (prev_mean - c[i - 1]) > P["stretch_atr"] * a[i - 1] and side * (c[i] - c[i - 1]) > 0 \
                            and side * (mean - c[i]) > 0:
                        ext = l[i - 2:i + 1].min() if side > 0 else h[i - 2:i + 1].max()
                        stop = ext - side * P["buf_atr"] * a[i]
                        if abs(mean - c[i]) < P["min_r"] * abs(c[i] - stop):
                            continue
                        s = _sig(m, end[i], side, c[i], stop, a[i], "long" if side > 0 else "short", target=float(mean))
                        if s:
                            out.append(s)
            prev_mean = mean
        return out
