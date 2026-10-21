"""gpt_c01_zone_rejection — ChatGPT round 2, C01: confirmed horizontal-zone rejection (Gold H1).

Two confirmed swing lows (2 bars each side) in the last 48 bars, at least 4 bars apart and within 0.25 ATR of each other
→ zone = their mean ± 0.25 ATR (ATR at the second swing's confirmation), dropped after a close 0.10 ATR below it. Long when
the previous close is above the zone, this candle's low touches its top and it closes bullish back above it. Stop below
min(zone bottom, candle low) − 0.10 ATR. Needs room for 2R before the nearest confirmed swing high above (if any). Mirror
for shorts. Fills 08:00–12:00 NY, target 2R, out after 6h or 15:00.

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


class GptC01ZoneRejection(Strategy):
    name = "gpt_c01_zone_rejection"
    symbol = "XAUUSD"
    description = "H1: double-swing zone, rejection candle back out of it; 2R, 6h, fills 08–12 NY."
    params = {"look": 48, "k": 2, "min_sep": 4, "tol_atr": 0.25, "half_atr": 0.25, "kill_atr": 0.10, "buf_atr": 0.10,
              "target_r": 2.0}
    exits = Exits(target_r=2.0, max_hold_min=360, flat_at=900)
    entry_windows = [(480, 721)]
    max_per_day = 2
    news_block = None

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, "1h")
        a = ind.atr(b, 14)
        k, n = P["k"], len(b)
        sw = {1: [], -1: []}            # side → list of (bar index, price, known-at index); 1 = swing lows (support)
        out = []
        for i in range(100, n):
            j = i - 1 - k               # a swing at j is confirmed when bar j + k closes (before this candle)
            if j - k >= 0:
                if l[j] < min(l[j - k:j].min(), l[j + 1:j + k + 1].min()):
                    sw[1].append((j, l[j], j + k))
                if h[j] > max(h[j - k:j].max(), h[j + 1:j + k + 1].max()):
                    sw[-1].append((j, h[j], j + k))
            if not np.isfinite(a[i]):
                continue
            for side in (1, -1):
                pts = [p for p in sw[side] if p[0] >= i - P["look"]]
                if len(pts) < 2:
                    continue
                s2 = pts[-1]
                af = a[s2[2]]
                s1 = next((p for p in reversed(pts[:-1]) if s2[0] - p[0] >= P["min_sep"] and abs(p[1] - s2[1]) <= P["tol_atr"] * af), None)
                if s1 is None or not np.isfinite(af):
                    continue
                mid = (s1[1] + s2[1]) / 2
                near, far = mid + side * P["half_atr"] * af, mid - side * P["half_atr"] * af    # near = the edge price returns to
                seg = c[s2[2] + 1:i]
                if len(seg) and (side * (seg - (far - side * P["kill_atr"] * af)) < 0).any():
                    continue                                                 # zone broken by a close beyond it
                if not (side * (c[i - 1] - near) > 0 and side * (near - (l[i] if side > 0 else h[i])) >= 0
                        and side * (c[i] - near) > 0 and side * (c[i] - o[i]) > 0):
                    continue
                stop = (min(far, l[i]) if side > 0 else max(far, h[i])) - side * P["buf_atr"] * a[i]
                risk = abs(c[i] - stop)
                opp = [p[1] for p in sw[-side] if side * (p[1] - c[i]) > 0]
                if opp:
                    nearest = min(opp) if side > 0 else max(opp)
                    if abs(nearest - c[i]) < P["target_r"] * risk:
                        continue
                s = _sig(m, end[i], side, c[i], stop, a[i], "long" if side > 0 else "short")
                if s:
                    out.append(s)
        return out
