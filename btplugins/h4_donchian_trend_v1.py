"""h4_donchian_trend_v1 — gold 4H 20-bar Donchian breakout with the rising 4H EMA200 and a 4H chandelier trail (the
quant's spec, frozen 2026-10-19; fxagents/h4_donchian.py ran it and failed step 1). Ported as the engine's parity check."""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


class H4DonchianTrendV1(Strategy):
    name = "h4_donchian_trend_v1"
    symbol = "XAUUSD"
    description = "4H close above the prior 20 bars' high, rising EMA200, chandelier trail; held overnight."
    params = {"entry_mods": (60, 300, 540, 780), "atr_bps": 0.0025, "ema": 200, "don": 20, "ch_max": 6.0,
              "bar_max": 2.2, "top": 0.35, "stop_buf": 0.20, "risk_atr": (1.2, 2.2), "use_bias": True}
    exits = Exits(trail={"kind": "chandelier", "tf": "4h", "atr": 14, "k": 2.2, "src": "close"},
                  max_hold_min=7200, friday_flat_at=990, hold_overnight=True)
    news_block = (15, 15)
    variants = {"no_bias": {"use_bias": False}}

    def signals(self, m):
        P = self.params
        b = m.bars("4h")
        end = b.end.to_numpy()
        emod = ((b.index.hour * 60 + b.index.minute + 240) % 1440).to_numpy()
        a4, e200 = ind.atr(b), ind.ema(b.c, P["ema"])
        o4, h4, l4, c4 = (b[k].to_numpy() for k in "ohlc")
        n = P["don"]
        out = []
        for k in range(P["ema"] + n, len(b)):
            if int(emod[k]) not in P["entry_mods"]:
                continue
            a = float(a4[k])
            if not np.isfinite(a) or a < P["atr_bps"] * c4[k]:
                continue
            for side in (1, -1):
                if side > 0:
                    hh, ll, o, h, l, c, e, e6 = h4[k - n:k], l4[k - n:k], o4[k], h4[k], l4[k], c4[k], e200[k], e200[k - 6]
                else:
                    hh, ll, o, h, l, c, e, e6 = (-l4[k - n:k], -h4[k - n:k], -o4[k], -l4[k], -h4[k], -c4[k],
                                                 -e200[k], -e200[k - 6])
                if P["use_bias"] and not (c > e and e > e6):
                    continue
                dh, dl = float(hh.max()), float(ll.min())
                if dh - dl > P["ch_max"] * a:
                    continue
                rng = h - l
                if rng <= 0 or rng > P["bar_max"] * a or c <= dh or c < h - P["top"] * rng:
                    continue
                stop_m = min(l, c - P["risk_atr"][0] * a) - P["stop_buf"] * a
                lvl = dh if side > 0 else -dh
                out.append(Signal(t=int(end[k]), side=side, stop=side * float(stop_m), expire_min=10,
                                  risk_min=P["risk_atr"][0] * a, risk_max=P["risk_atr"][1] * a,
                                  tag="h4_trend" if P["use_bias"] else "no_bias",
                                  draw=[{"k": "line", "t0": int(b.start.iloc[k - n]), "t1": int(end[k]), "px": lvl,
                                         "label": "20-bar channel"}]))
        return out
