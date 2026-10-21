"""crt_daily — Candle Range Theory on daily candles (17:00 New York close).

Candle 1 = yesterday's daily candle (its high/low/50%). Candle 2 = today's: a bullish CRT trades below candle 1's low and
closes back inside the range; bearish is the mirror at the high. Entry at the next open (the 18:00 reopen; Friday → Sunday
evening). Stop beyond candle 2's extreme (+ `buf_atr` × daily ATR). Target candle 1's opposite extreme (`target` "far") or
its 50% ("mid"); skipped if under `min_rr` × risk. Out at the close of candle 3 (the next daily close) if neither is hit.
Held overnight: financing is charged per 17:00 crossing.
"""
import numpy as np

from fxagents.bt import Costs, Exits, Signal, Strategy, ind


class CrtDaily(Strategy):
    name = "crt_daily"
    symbol = "XAUUSD"
    description = "Daily CRT: today sweeps yesterday's high/low and closes back inside → target the other side, out next close."
    params = {"target": "far", "buf_atr": 0.10, "min_rr": 1.0}
    exits = Exits(hold_overnight=True)
    costs = Costs(gap_exit_min=5 * 1440)
    news_block = None
    warmup_days = 60
    variants = {"target_mid": {"target": "mid"}}

    def signals(self, m):
        P = self.params
        b = m.bars("1d")
        h, l, c, end = (b[k].to_numpy() for k in ("h", "l", "c", "end"))
        a = ind.atr(b, 14)
        out = []
        for j in range(15, len(b)):
            i = j - 1
            if not np.isfinite(a[j]):
                continue
            hi, lo = h[i], l[i]
            for side in (1, -1):
                if not (((l[j] < lo) if side > 0 else (h[j] > hi)) and lo < c[j] < hi):
                    continue
                stop = (l[j] if side > 0 else h[j]) - side * P["buf_atr"] * a[j]
                tgt = (hi if side > 0 else lo) if P["target"] == "far" else (hi + lo) / 2
                risk = abs(c[j] - stop)
                if risk <= 0 or side * (tgt - c[j]) < P["min_rr"] * risk:
                    continue
                out.append(Signal(t=int(end[j]), side=side, stop=float(stop), target=float(tgt), exit_t=self._next_close(end, j),
                                  expire_min=3 * 1440, tag="bull_crt" if side > 0 else "bear_crt"))
        return out

    @staticmethod
    def _next_close(end, j):
        """Candle 3's close: the next daily close (computed from the calendar, so it doesn't need future candles)."""
        import pandas as pd
        t = pd.Timestamp(int(end[j]), tz="UTC").tz_convert("America/New_York")
        nxt = t + pd.Timedelta(days=3 if t.dayofweek == 4 else 1)
        return int(nxt.tz_convert("UTC").value)
