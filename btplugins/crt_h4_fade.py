"""crt_h4_fade — the exact mirror of crt_h4_1am (Oct 21 2026), tested because crt_h4_1am lost reliably:
US30 −0.223R (95% −0.365 … −0.069) and −0.172R vs random timing on 2021–Sep 2026; NDQ −0.117R, gold −0.091R.
That makes this a data-mined idea (chosen AFTER seeing the loss) — one try, all three instruments, same gates and vault.

Setup: identical to crt_h4_1am. Candle 1 = 01:00–05:00 NY 4H candle; candle 2 = 05:00–09:00 sweeps candle 1's low (high)
and closes back inside its range.
Trade: the OPPOSITE of the CRT. Where CRT buys (swept low, closed back inside) this SELLS at 09:00, betting the sweep
continues. Stop = the CRT's target (candle 1's opposite extreme); target = the CRT's stop (beyond candle 2's extreme,
+ `buf_atr` × 4H ATR). So every price path that won for crt_h4_1am loses here and vice versa — before costs, which this
version pays again. Only setups where crt_h4_1am traded (its min_rr filter) are taken, so the trade set is the same.
Out at 13:00 (candle 3's close) or 15:50, whichever first.
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


class CrtH4Fade(Strategy):
    name = "crt_h4_fade"
    symbol = "US30"
    description = "Mirror of the 4H CRT: when the 05:00 candle sweeps the 01:00 range and closes back inside, trade WITH the sweep."
    params = {"buf_atr": 0.10, "min_rr": 1.0}
    exits = Exits(flat_at=950)
    entry_windows = [(540, 661)]
    max_per_day = 1
    news_block = None

    def signals(self, m):
        P = self.params
        b4 = m.bars("4h")
        h, l, c, end = (b4[k].to_numpy() for k in ("h", "l", "c", "end"))
        hr = b4.index.hour.to_numpy()
        a4 = ind.atr(b4, 14)
        out = []
        for i in range(20, len(b4) - 1):
            if hr[i] != 1 or hr[i + 1] != 5 or not np.isfinite(a4[i + 1]):
                continue
            j = i + 1
            hi, lo = h[i], l[i]
            for crt in (1, -1):                                   # the CRT's side; we trade the other one
                swept = (l[j] < lo) if crt > 0 else (h[j] > hi)
                if not (swept and lo < c[j] < hi):
                    continue
                crt_stop = (l[j] if crt > 0 else h[j]) - crt * P["buf_atr"] * a4[j]
                crt_tgt = hi if crt > 0 else lo
                ref = c[j]
                if abs(ref - crt_stop) <= 0 or crt * (crt_tgt - ref) < P["min_rr"] * abs(ref - crt_stop):
                    continue                                       # same trade set as crt_h4_1am
                side = -crt
                out.append(Signal(t=int(end[j]), side=side, stop=float(crt_tgt), target=float(crt_stop),
                                  exit_t=int(end[j]) + 4 * 3600 * 10 ** 9, risk_max=0.1 * ref,
                                  tag="fade_bull_crt" if crt > 0 else "fade_bear_crt"))
        return out
