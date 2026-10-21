"""london_ifvg — "London Liquidity / IFVG by Shujat" (a friend's RQ strategy, Oct 21 2026), ported line by line.
Defaults = his MNQ 5-minute showcase preset; run it on NDQ (OANDA's Nasdaq 100 CFD stands in for MNQ).

Rules, all on 5-minute mid candles, New York time; everything resets at New York midnight:
  1. London box: high/low of the candles 03:30–09:25. When the first candle at/after 09:25 arrives the box closes
     and its high/low become the levels.
  2. Liquidity sweep (LS), only on candles 09:25–13:15, once a day:
       bearish: a candle CLOSES above the London high; later (or the same flag carried) a candle closes back ≤ the high
                with a body > 50% of its range → short bias, ls_price = that candle's high;
       bullish: mirror at the London low. The high is checked first on a bar.
  3. Fair value gaps are collected while the box is open (03:30–09:25) and after the LS candle (not in between):
       bullish FVG: high two candles back < this low; bearish: low two back > this high. Dropped after
       `max_age_h` hours or at midnight.
  4. Entry, 09:25–13:15, after the LS (the LS candle itself counts): a candle CLOSES through an FVG the opposite
     way — an inverse FVG (IFVG) — in the sweep's direction: below a bullish FVG's bottom → short after a high sweep;
     above a bearish FVG's top → long after a low sweep. Short IFVGs need the FVG bottom ≤ ls_price, longs the FVG top
     ≥ ls_price. The newest FVG is checked first. One setup a day (the first IFVG ends the day, traded or not).
  5. Stop = close ∓ `sl_atr` × ATR(14) (sl="atr") or the 5-candle extreme (sl="swing"). Target = close ±
     `tp_atr` × ATR (tp="atr"), `rr` × risk (tp="rr"), or the opposite London level (tp="range").
     His code enters AT the signal candle's close; here the fill is the next minute's open (real bid/ask) with the
     stop and target levels unchanged.
Preset: 2.0 ATR stop, 0.2 ATR target — risk 10 to make 1. Breakeven before costs needs ~91% winners, and a random
entry with the same 2 ATR / 0.2 ATR bracket also wins ~91% of the time, so the random-timing control is the real test.
Not in his code but in ours: out at 15:50 (the bot never holds index trades overnight). No news blackout (his has none).
Variants (his own options, not tuned): tp_rr2 (2R target), tp_range (opposite London level), sl_swing.
"""
import numpy as np

from fxagents.bt import Exits, Signal, Strategy, ind


def _hm(x: int) -> int:                       # hhmm → minutes
    return (x // 100) * 60 + x % 100


class LondonIfvg(Strategy):
    name = "london_ifvg"
    symbol = "NDQ"
    description = "London 03:30–09:25 box; NY sweep + large-body close back inside → inverse FVG entry, 2 ATR stop / 0.2 ATR target."
    params = {"box": (330, 925), "ls": (925, 1315), "max_age_h": 10, "atr": 14, "sl": "atr", "sl_atr": 2.0,
              "swing_n": 5, "tp": "atr", "tp_atr": 0.2, "rr": 2.0}
    exits = Exits(flat_at=950)
    entry_windows = [(565, 800)]               # fills right after a 09:25–13:15 candle closes
    max_per_day = 1
    news_block = None
    variants = {"tp_rr2": {"tp": "rr", "rr": 2.0}, "tp_range": {"tp": "range"}, "sl_swing": {"sl": "swing"}}

    def signals(self, m):
        P = self.params
        b = m.bars(5)
        o, h, l, c, st, end = (b[x].to_numpy() for x in ("o", "h", "l", "c", "start", "end"))
        t = b.index
        mod = (t.hour * 60 + t.minute).to_numpy()
        day = np.asarray([d.toordinal() for d in t.date])
        a = ind.atr(b, P["atr"])
        b0, b1 = _hm(P["box"][0]), _hm(P["box"][1])
        s0, s1 = _hm(P["ls"][0]), _hm(P["ls"][1])
        max_age = P["max_age_h"] * 3600 * 10 ** 9
        out = []

        sess = False; shi = slo = np.nan; hi_lvl = lo_lvl = np.nan
        lines = hs = ls_ = made = marked = False
        ls_t = -1; ls_dir = 0; ls_px = np.nan; last_day = None
        fvgs: list = []                                   # [start_ns, lower, upper, bullish, day]
        for i in range(len(b)):
            d = day[i]
            if last_day is not None and d != last_day:     # New York midnight: reset the day
                sess = False; hs = ls_ = lines = made = marked = False
                ls_t = -1; ls_dir = 0; ls_px = np.nan
            last_day = d
            in_box = b0 <= mod[i] < b1
            if sess and st[i] - sess_t > 20 * 3600 * 10 ** 9:
                sess = False                               # a data gap straight into the next box
            if in_box and not sess:
                sess, shi, slo, sess_t = True, h[i], l[i], st[i]
                lines = made = marked = False; ls_t = -1; ls_dir = 0; ls_px = np.nan
            elif in_box:
                shi, slo = max(shi, h[i]), min(slo, l[i])
            elif sess:
                hi_lvl, lo_lvl, sess, lines = shi, slo, False, True
            ls_ok = s0 <= mod[i] < s1
            rng = h[i] - l[i]
            big = rng > 0 and abs(o[i] - c[i]) * 100 / rng > 50
            if lines and not made and ls_ok and np.isfinite(hi_lvl):
                if c[i] > hi_lvl:
                    hs = True
                if hs and c[i] <= hi_lvl and big:
                    made, ls_t, ls_dir, ls_px, hs = True, st[i], -1, h[i], False
            if lines and not made and ls_ok and np.isfinite(lo_lvl):
                if c[i] < lo_lvl:
                    ls_ = True
                if ls_ and c[i] >= lo_lvl and big:
                    made, ls_t, ls_dir, ls_px, ls_ = True, st[i], 1, l[i], False
            if i >= 2:
                track = (in_box and not marked) or (made and not marked and st[i] > ls_t)
                if track and h[i - 2] < l[i] and len(fvgs) < 64:
                    fvgs.append([st[i - 2], h[i - 2], l[i], True, d])
                if track and l[i - 2] > h[i] and len(fvgs) < 64:
                    fvgs.append([st[i - 2], h[i], l[i - 2], False, d])
            if not fvgs or not np.isfinite(a[i]):
                continue
            k = len(fvgs)
            while k > 0:
                k -= 1
                f0, lower, upper, bull, fd = fvgs[k]
                if st[i] - f0 > max_age or fd != d or marked:
                    fvgs.pop(k); continue
                inverted = c[i] < lower if bull else c[i] > upper
                bear_ifvg = bull
                match = (ls_dir == -1 and bear_ifvg) or (ls_dir == 1 and not bear_ifvg)
                pos_ok = (lower <= ls_px) if bear_ifvg else (upper >= ls_px)
                if not (inverted and made and not in_box and ls_ok and match and pos_ok):
                    continue
                side = -1 if bear_ifvg else 1
                lo_ = max(0, i - P["swing_n"] + 1)
                stop = (c[i] - side * P["sl_atr"] * a[i]) if P["sl"] == "atr" else \
                    (h[lo_:i + 1].max() if side < 0 else l[lo_:i + 1].min())
                risk = abs(c[i] - stop)
                tgt = {"rr": c[i] + side * risk * P["rr"], "atr": c[i] + side * P["tp_atr"] * a[i]}.get(
                    P["tp"], lo_lvl if side < 0 else hi_lvl)
                marked = True
                fvgs.pop(k)
                if side * (c[i] - stop) > 0 and side * (tgt - c[i]) > 0:
                    out.append(Signal(t=int(end[i]), side=side, stop=float(stop), target=float(tgt),
                                      risk_max=0.1 * c[i], tag="short_after_high_sweep" if side < 0 else "long_after_low_sweep",
                                      info={"london_hi": float(hi_lvl), "london_lo": float(lo_lvl), "fvg": [float(lower), float(upper)]}))
        return out
