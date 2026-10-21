"""gpt_c09_shock_reversal — ChatGPT round 2, C09: volatility-shock exhaustion reversal (Gold H1).

Shock candle: range >= 2 × the ATR before it, body <= 35% of the range, lower wick >= half the range (for a long). The next
candle closes bullish and more than 0.10 ATR above the shock close → buy next open; stop below the lower of the two lows
− 0.10 ATR. Mirror for shorts. Fills 08:00–12:00 NY, target 2R, out after 4h or 15:00.

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


class GptC09ShockReversal(Strategy):
    name = "gpt_c09_shock_reversal"
    symbol = "XAUUSD"
    description = "H1: 2-ATR rejection candle (long wick, small body) confirmed by the next candle; 2R, 4h."
    params = {"shock_atr": 2.0, "body_max": 0.35, "wick_min": 0.5, "conf_atr": 0.10, "buf_atr": 0.10}
    exits = Exits(target_r=2.0, max_hold_min=240, flat_at=900)
    entry_windows = [(480, 721)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, "1h")
        a = ind.atr(b, 14)
        out = []
        for i in range(101, len(b)):
            s_ = i - 1
            if not (np.isfinite(a[s_ - 1]) and np.isfinite(a[i])):
                continue
            rng = h[s_] - l[s_]
            if rng < P["shock_atr"] * a[s_ - 1] or rng <= 0 or abs(c[s_] - o[s_]) > P["body_max"] * rng:
                continue
            lower, upper = min(o[s_], c[s_]) - l[s_], h[s_] - max(o[s_], c[s_])
            for side in (1, -1):
                wick = lower if side > 0 else upper
                if wick >= P["wick_min"] * rng and side * (c[i] - o[i]) > 0 and side * (c[i] - c[s_]) > P["conf_atr"] * a[i]:
                    ext = min(l[s_], l[i]) if side > 0 else max(h[s_], h[i])
                    s = _sig(m, end[i], side, c[i], ext - side * P["buf_atr"] * a[i], a[i], "long" if side > 0 else "short")
                    if s:
                        out.append(s)
        return out
