"""crt_h4_1am — Candle Range Theory, intraday 4H version (the "1 AM / 5 AM" model).

Candle 1 = the 01:00–05:00 New York 4H candle: its high and low are the range.
Candle 2 = the 05:00–09:00 4H candle. Bullish CRT: it trades below candle 1's low (takes the sell-side stops) and CLOSES
back inside the range (above candle 1's low, below its high). Bearish: the mirror at candle 1's high.
Entry (param `entry`):
  "c2_close" — market at 09:00, the moment candle 2 closes back inside.
  "m15_mss"  — wait (09:00–11:00) for a 15-minute close beyond the latest confirmed 15-minute swing high (low for shorts);
               cancelled if candle 2's extreme is broken first (the lower-timeframe "change in state of delivery").
Stop beyond candle 2's extreme (+ `buf_atr` × 4H ATR). Target candle 1's opposite extreme (`target` "far") or its 50% level
("mid"). Skipped if the target is under `min_rr` × the risk. Out at the close of candle 3 (13:00) or 15:50, whichever first.
Sources for the rules: LuxAlgo "Candle Range Theory" library page; the 1 AM range / 5 AM sweep pairing is the commonly
taught intraday variant. CRT teachers also want candle 2 to sweep INTO a higher-timeframe level — not modelled here.
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


class CrtH41am(Strategy):
    name = "crt_h4_1am"
    symbol = "XAUUSD"
    description = "4H CRT: 05:00 candle sweeps the 01:00 candle's high/low and closes back inside → target the other side."
    params = {"entry": "c2_close", "target": "far", "buf_atr": 0.10, "min_rr": 1.0, "ltf_wait_min": 120}
    exits = Exits(flat_at=950)
    entry_windows = [(540, 661)]
    max_per_day = 1
    news_block = None
    variants = {"m15_confirm": {"entry": "m15_mss"}, "target_mid": {"target": "mid"}}

    def signals(self, m):
        P = self.params
        b4 = m.bars("4h")
        o, h, l, c, end = (b4[k].to_numpy() for k in ("o", "h", "l", "c", "end"))
        hr = b4.index.hour.to_numpy()
        a4 = ind.atr(b4, 14)
        if P["entry"] == "m15_mss":
            b15 = m.bars(15)
            e15, c15, h15, l15 = b15.end.to_numpy(), b15.c.to_numpy(), b15.h.to_numpy(), b15.l.to_numpy()
            sh15, sl15 = ind.swings(h15, l15, 2)
        out = []
        for i in range(20, len(b4) - 1):
            if hr[i] != 1 or hr[i + 1] != 5 or not np.isfinite(a4[i + 1]):
                continue
            j = i + 1
            hi, lo, mid = h[i], l[i], (h[i] + l[i]) / 2
            for side in (1, -1):
                swept = (l[j] < lo) if side > 0 else (h[j] > hi)
                inside = lo < c[j] < hi
                if not (swept and inside):
                    continue
                ext = l[j] if side > 0 else h[j]
                stop = ext - side * P["buf_atr"] * a4[j]
                tgt = (hi if side > 0 else lo) if P["target"] == "far" else mid
                c3_end = int(end[j]) + 4 * 3600 * 10 ** 9
                if P["entry"] == "c2_close":
                    t, ref = int(end[j]), c[j]
                else:
                    k0 = int(np.searchsorted(e15, end[j], side="right"))
                    t = ref = None
                    for k in range(k0, len(b15)):
                        if e15[k] > end[j] + P["ltf_wait_min"] * 60 * 10 ** 9:
                            break
                        if (l15[k] <= ext) if side > 0 else (h15[k] >= ext):
                            break                                         # candle 2's extreme taken out: setup dead
                        lvl = sh15[k - 1] if side > 0 else sl15[k - 1]
                        if np.isfinite(lvl) and side * (c15[k] - lvl) > 0:
                            t, ref = int(e15[k]), c15[k]
                            break
                    if t is None:
                        continue
                risk = abs(ref - stop)
                if risk <= 0 or side * (tgt - ref) < P["min_rr"] * risk:
                    continue
                out.append(Signal(t=t, side=side, stop=float(stop), target=float(tgt), exit_t=c3_end,
                                  risk_max=0.1 * ref, tag="bull_crt" if side > 0 else "bear_crt",
                                  draw=[{"k": "box", "t0": int(b4.start.iloc[i]), "t1": int(end[j]), "hi": float(hi),
                                         "lo": float(lo), "label": "CRT range"}]))
        return out
