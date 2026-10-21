"""mmxm_v1 — ICT Market Maker Model (MMXM) made mechanical: one fixed reading of a discretionary framework.

Buy model (sell model = the exact mirror):
  1. Draw on liquidity: the previous day's HIGH (daily candles close 17:00 New York).
  2. Engineering liquidity / smart-money reversal: in the NY AM killzone (08:30–11:00) price runs the overnight LOW
     (18:00 → 08:30 low = Asia + London sell-side).
  3. Discount: the sweep low is below the 50% of the previous day's range (`discount`).
  4. SMT divergence (`smt`, indices only): at the sweep, the partner index (NDQ ↔ US30) did NOT take its own overnight low.
  5. Market structure shift: within `max_wait` 5-minute candles of the sweep, a close above the last confirmed 5-minute swing
     high that formed before the sweep, the leg containing a displacement candle (body ≥ `disp_k` × 5m ATR) and a bullish
     fair value gap.
  6. Entry: limit at the top of the newest FVG in that leg (valid `fvg_wait` minutes; cancelled if price reaches the target
     first). Stop below the sweep low − `buf_atr` × ATR. Target the previous day's high; skipped if under `min_rr` × risk.
One trade a day, flat 15:50. Fills 08:30–12:00. This is ONE mechanical reading — MMXM teachers vary (HTF PD arrays, macro
times, which liquidity counts). Variants: no_smt, no_discount. Default NDQ (partner US30); on gold run with smt=false.
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, data, ind

PARTNER = {"NDQ": "US30", "US30": "NDQ"}
NS_MIN = 60 * 10 ** 9


class MmxmV1(Strategy):
    name = "mmxm_v1"
    symbol = "NDQ"
    description = "MMXM: overnight liquidity run in the NY killzone (discount/premium, SMT) → 5m MSS + FVG entry, target prior-day H/L."
    params = {"kz": (510, 660), "smt": True, "discount": True, "max_wait": 24, "disp_k": 1.0, "fvg_wait": 60,
              "buf_atr": 0.10, "min_rr": 2.0, "k": 2}
    exits = Exits(flat_at=950)
    entry_windows = [(510, 721)]
    max_per_day = 1
    news_block = (15, 15)
    variants = {"no_smt": {"smt": False}, "no_discount": {"discount": False}}

    def _partner(self, m):
        ps = PARTNER.get(m.symbol)
        if not (self.params["smt"] and ps and m.dataset):
            return None
        try:
            pm = data.load(m.dataset, ps)
        except Exception:  # noqa: BLE001 — no partner data: SMT can't be checked, so the setup can't qualify
            return False
        cut = int(np.searchsorted(pm.ns, m.ns[-1], side="right"))          # never let the partner see past our data
        if cut < len(pm.ns):
            from fxagents.bt.data import KEYS, Market
            pm = Market(ps, *(getattr(pm, k)[:cut] for k in KEYS), dataset=pm.dataset)
        b = pm.bars(5)
        return dict(zip(b.start.to_numpy(), zip(b.h.to_numpy(), b.l.to_numpy())))

    def signals(self, m):
        P = self.params
        b = m.bars(5)
        o, h, l, c, st, end = (b[x].to_numpy() for x in ("o", "h", "l", "c", "start", "end"))
        t = b.index
        mod = (t.hour * 60 + t.minute).to_numpy()
        sess = ((t.tz_localize(None).asi8 // NS_MIN + 6 * 60) // 1440).astype(np.int64)            # trading day (18:00 start)
        a = ind.atr(b, 14)
        sh, sl = ind.swings(h, l, P["k"])
        d = m.bars("1d")
        d_end, d_h, d_l = d.end.to_numpy(), d.h.to_numpy(), d.l.to_numpy()
        part = self._partner(m)
        if part is False:
            return []
        out = []
        starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
        for si, s0 in enumerate(starts):
            s1 = starts[si + 1] if si + 1 < len(starts) else len(b)
            idx = np.arange(s0, s1)
            on = idx[(mod[idx] >= 1080) | (mod[idx] < P["kz"][0])]
            kz = idx[(mod[idx] >= P["kz"][0]) & (mod[idx] < P["kz"][1])]
            if len(on) < 60 or not len(kz) or kz[0] < 300:
                continue
            k_d = int(np.searchsorted(d_end, st[kz[0]], side="right")) - 1                         # last completed day
            if k_d < 1:
                continue
            pdh, pdl = d_h[k_d], d_l[k_d]
            pmid = (pdh + pdl) / 2
            onh, onl = h[on].max(), l[on].min()
            if part:
                pon = [part.get(x) for x in st[on]]
                pon = [x for x in pon if x is not None]
                if len(pon) < 60:
                    continue
                p_onh, p_onl = max(x[0] for x in pon), min(x[1] for x in pon)
            done = False
            for side in (1, -1):
                if done:
                    break
                liq = onl if side > 0 else onh
                dol = pdh if side > 0 else pdl
                for ii, i in enumerate(kz):
                    ext_i = l[i] if side > 0 else h[i]
                    if side * (liq - ext_i) <= 0:
                        continue                                                  # 2) first run of the overnight extreme
                    mss = sh[i - 1] if side > 0 else sl[i - 1]                    #    last swing before the sweep
                    if not np.isfinite(mss):
                        break
                    sweep = ext_i
                    for j in range(i + 1, min(i + 1 + P["max_wait"], s1)):
                        e = l[j] if side > 0 else h[j]
                        if side * (e - sweep) < 0:
                            sweep = e                                             # a deeper run: same setup
                        if side * (c[j] - mss) <= 0:
                            continue
                        leg = np.arange(i, j + 1)                                  # 5) MSS at j
                        if not (np.abs(c[leg] - o[leg]) >= P["disp_k"] * a[leg]).any():
                            break
                        fvg = [x for x in leg[2:] if (side > 0 and l[x] > h[x - 2]) or (side < 0 and h[x] < l[x - 2])]
                        if not fvg:
                            break
                        x = fvg[-1]
                        px = l[x] if side > 0 else h[x]                            # 6) FVG edge nearest price
                        if P["discount"] and side * (pmid - sweep) <= 0:
                            break                                                  # 3) sweep must be in discount/premium
                        if part:
                            seg = [part.get(y) for y in st[kz[0]:j + 1]]
                            seg = [y for y in seg if y is not None]
                            if not seg:
                                break
                            took = (min(y[1] for y in seg) < p_onl) if side > 0 else (max(y[0] for y in seg) > p_onh)
                            if took:
                                break                                              # 4) no SMT: partner ran its liquidity too
                        stop = sweep - side * P["buf_atr"] * a[j]
                        risk = abs(px - stop)
                        if risk <= 0 or side * (dol - px) < P["min_rr"] * risk:
                            break
                        out.append(Signal(t=int(end[j]), side=side, stop=float(stop), entry="limit", price=float(px),
                                          expire_min=P["fvg_wait"], cancel=float(dol), target=float(dol),
                                          risk_max=0.1 * px, tag="buy_model" if side > 0 else "sell_model",
                                          info={"pdh": float(pdh), "pdl": float(pdl), "on_ext": float(liq)}))
                        done = True
                        break
                    break                                                          # one sweep evaluated per side per day
        return out
