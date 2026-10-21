"""gpt_c05_channel_expansion — ChatGPT round 2, C05: twenty-bar channel expansion (NAS100 H1). GPT's pick (15 trades).

Buy when an H1 candle closes more than 0.10 ATR above the highest high of the previous 20 candles and in the top 25% of
its own range; sell the mirror. Stop 1.25 ATR, target 2.5R. Fills 10:00–12:00 NY, out after 6h or 15:00.

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


class GptC05ChannelExpansion(Strategy):
    name = "gpt_c05_channel_expansion"
    symbol = "NDQ"
    description = "H1: close beyond the 20-bar channel, in the top/bottom quarter of its range; 1.25 ATR stop, 2.5R."
    params = {"n": 20, "brk_atr": 0.10, "close_q": 0.25, "stop_atr": 1.25}
    exits = Exits(target_r=2.5, max_hold_min=360, flat_at=900)
    entry_windows = [(600, 721)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, "1h")
        a = ind.atr(b, 14)
        n = P["n"]
        hh = b.h.shift(1).rolling(n).max().to_numpy()
        ll = b.l.shift(1).rolling(n).min().to_numpy()
        out = []
        for i in range(100, len(b)):
            if not np.isfinite(a[i]) or not np.isfinite(hh[i]):
                continue
            rng = h[i] - l[i]
            if rng <= 0:
                continue
            for side in (1, -1):
                lvl = hh[i] if side > 0 else ll[i]
                pos = (c[i] - l[i]) / rng if side > 0 else (h[i] - c[i]) / rng
                if side * (c[i] - lvl) > P["brk_atr"] * a[i] and pos >= 1 - P["close_q"]:
                    s = _sig(m, end[i], side, c[i], c[i] - side * P["stop_atr"] * a[i], a[i], "long" if side > 0 else "short")
                    if s:
                        out.append(s)
        return out
