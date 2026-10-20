"""vol_breakout_v1 — gold 5m volatility-compression breakout with the 15m + 1H trend (the quant's spec, frozen
2026-10-19; the old module fxagents/vol_breakout.py ran it and failed step 1). Ported as the engine's parity check."""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


class VolBreakoutV1(Strategy):
    name = "vol_breakout_v1"
    symbol = "XAUUSD"
    description = "5m close breaks a tight 60-min box with the 15m and 1H EMA50 trend, beyond session VWAP."
    params = {"win": (480, 690), "atr15_bps": 0.0007, "box_bars": 12, "box_atr": (0.80, 2.20), "brk_buf": 0.05,
              "bar_atr": (0.45, 1.50), "body": 0.60, "top": 0.25, "stop_buf": 0.15, "risk_atr": (0.90, 2.00),
              "use_bias": True}
    exits = Exits(target_r=2.5, be_at_r=1.2, be_lock_r=0.10, flat_at=990)
    max_per_day = 1
    news_block = (15, 15)
    variants = {"no_bias": {"use_bias": False}}

    def signals(self, m):
        P = self.params
        b5, b15, b1h = m.bars(5), m.bars(15), m.bars("1h")
        E5, E15, E1 = b5.end.to_numpy(), b15.end.to_numpy(), b1h.end.to_numpy()
        a15 = ind.atr(b15)
        e50, c15 = ind.ema(b15.c, 50), b15.c.to_numpy()
        e1h = ind.ema(b1h.c, 50)
        vw = ind.vwap(m)
        o5, h5, l5, c5 = (b5[k].to_numpy() for k in "ohlc")
        nb = P["box_bars"]
        out = []
        for k in range(max(20, nb + 1), len(b5)):
            j_end = int(np.searchsorted(m.ns, E5[k])) - 1
            if j_end < 0 or not (P["win"][0] <= m.mod[j_end] + 1 <= P["win"][1]):
                continue
            j = int(np.searchsorted(m.ns, E5[k]))
            if j >= len(m) or m.mod[j] >= P["win"][1]:
                continue
            i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
            i1 = int(np.searchsorted(E1, E5[k], side="right")) - 1
            if i15 < 60 or i1 < 50 or not np.isfinite(a15[i15]) or a15[i15] < P["atr15_bps"] * c15[i15]:
                continue
            a = float(a15[i15])
            for side in (1, -1):
                if P["use_bias"] and not (side * c15[i15] > side * e50[i15] and side * c15[i15] > side * e1h[i1]):
                    continue
                if side > 0:
                    hh, ll, o, h, l, c = h5[k - nb:k], l5[k - nb:k], o5[k], h5[k], l5[k], c5[k]
                else:
                    hh, ll, o, h, l, c = -l5[k - nb:k], -h5[k - nb:k], -o5[k], -l5[k], -h5[k], -c5[k]
                bh, bl = float(hh.max()), float(ll.min())
                if not (P["box_atr"][0] * a <= bh - bl <= P["box_atr"][1] * a):
                    continue
                rng = h - l
                if not (P["bar_atr"][0] * a <= rng <= P["bar_atr"][1] * a):
                    continue
                if (c - o) < P["body"] * rng or c < h - P["top"] * rng:
                    continue
                if c <= bh + P["brk_buf"] * a or c <= side * vw[j_end]:
                    continue
                stop_m = min(l, 0.5 * (bh + bl)) - P["stop_buf"] * a
                out.append(Signal(t=int(E5[k]), side=side, stop=side * float(stop_m),
                                  risk_min=P["risk_atr"][0] * a, risk_max=P["risk_atr"][1] * a,
                                  tag="trend_brk" if P["use_bias"] else "no_bias",
                                  draw=[{"k": "box", "t0": int(b5.start.iloc[k - nb]), "t1": int(E5[k - 1]),
                                         "hi": side * bh if side > 0 else -bl, "lo": side * bl if side > 0 else -bh,
                                         "label": "60-min box"}]))
        return out
