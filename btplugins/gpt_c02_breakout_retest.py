"""gpt_c02_breakout_retest — ChatGPT round 2, C02: swing-level breakout and retest (US30 H1).

A candle closes more than 0.10 ATR above the latest confirmed swing high (48-bar search; the previous close was not
already past that threshold). Within the next 3 candles a retest: low within 0.20 ATR above the level and close more than
0.10 ATR above it, all closes since the break staying above level − 0.25 ATR. Enter next open; stop below the lowest
post-breakout low − 0.10 ATR. Mirror for downside breaks. Fills 10:00–12:00 NY, target 2.5R, out after 6h or 15:00.

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


class GptC02BreakoutRetest(Strategy):
    name = "gpt_c02_breakout_retest"
    symbol = "US30"
    description = "H1: close beyond a confirmed swing, retest within 3 bars holds; 2.5R, 6h, fills 10–12 NY."
    params = {"look": 48, "k": 2, "brk_atr": 0.10, "touch_atr": 0.20, "hold_atr": 0.25, "buf_atr": 0.10, "within": 3}
    exits = Exits(target_r=2.5, max_hold_min=360, flat_at=900)
    entry_windows = [(600, 721)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, "1h")
        a = ind.atr(b, 14)
        k, n = P["k"], len(b)
        last = {1: None, -1: None}      # latest confirmed swing (index, price) for breaks up (highs) and down (lows)
        hist = {1: [], -1: []}
        out, used = [], set()
        for j in range(100, n - 1):
            q = j - 1 - k
            if q - k >= 0:
                if h[q] > max(h[q - k:q].max(), h[q + 1:q + k + 1].max()):
                    hist[1].append((q, h[q]))
                if l[q] < min(l[q - k:q].min(), l[q + 1:q + k + 1].min()):
                    hist[-1].append((q, l[q]))
            if not np.isfinite(a[j]):
                continue
            for side in (1, -1):
                pts = [p for p in hist[side] if p[0] >= j - P["look"]]
                if not pts:
                    continue
                lvl, ab = pts[-1][1], a[j]
                thr = lvl + side * P["brk_atr"] * ab
                if not (side * (c[j] - thr) > 0 and side * (c[j - 1] - thr) <= 0):
                    continue
                for r in range(j + 1, min(j + 1 + P["within"], n)):
                    if (side * (c[j:r + 1] - (lvl - side * P["hold_atr"] * ab)) < 0).any():
                        break
                    ext = l[r] if side > 0 else h[r]
                    if side * (ext - (lvl + side * P["touch_atr"] * ab)) <= 0 and side * (c[r] - (lvl + side * P["brk_atr"] * ab)) > 0:
                        key = (day[r], side, round(lvl, 2))
                        if key in used:
                            break
                        used.add(key)
                        stop = (l[j + 1:r + 1].min() if side > 0 else h[j + 1:r + 1].max()) - side * P["buf_atr"] * a[r]
                        s = _sig(m, end[r], side, c[r], stop, a[r], "long" if side > 0 else "short")
                        if s:
                            out.append(s)
                        break
        return out
