"""Smart-money strategies: ICT (FVG + liquidity sweep, OTE), Dave Teaches FX zones, Stoic Trader SBS.

Each strategy is written once for the LONG side and run a second time on a mirrored price series
(highs ↔ −lows) for shorts, so both sides are guaranteed symmetric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import Pivot
from .base import RawSignal, Strategy, in_window

KILLZONES = [["02:00", "05:00"], ["08:30", "11:00"], ["13:30", "15:00"]]


def _mirror(df: pd.DataFrame, piv: list[Pivot]):
    O, H, L, C = (df[c].to_numpy() for c in ("open", "high", "low", "close"))
    long_view = (O, H, L, C, piv)
    mp = [Pivot(p.idx, -p.price, "L" if p.kind == "H" else "H", p.known_at) for p in piv]
    short_view = (-O, -L, -H, -C, mp)
    return ((1, long_view), (-1, short_view))


def _known_iter(piv: list[Pivot]):
    """Yields pivots in the order they become known."""
    return sorted(piv, key=lambda p: (p.known_at, p.idx))


# ─────────────────────────────────────────────────────────────────────────────
class ICTFvgSweep(Strategy):
    name = "ict_fvg_sweep"
    family = "ict"
    description = ("ICT Silver-Bullet style: a swing low/high is swept for liquidity, price displaces "
                   "through structure (MSS) leaving a fair value gap, entry on the retrace into the FVG "
                   "inside a killzone, stop beyond the sweep extreme, filtered by 1H bias.")
    default_params = dict(swing=2, sweep_lookback=40, disp_window=20, min_fvg_atr=0.1,
                          fvg_max_age=12, stop_buf_atr=0.1, use_htf=True, killzones=KILLZONES)
    param_grid = {"swing": [2, 3, 5], "min_fvg_atr": [0.05, 0.1, 0.2], "disp_window": [10, 20, 30],
                  "fvg_max_age": [6, 12, 20], "use_htf": [True, False]}

    def _scan(self, df, ctx):
        p, a, htf = self.params, ctx["atr"], ctx["htf"]
        out: list[RawSignal] = []
        for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
            order = _known_iter(piv)
            ptr, known, swept = 0, [], set()
            sweep = None     # {"idx", "low", "mss"}
            active = []      # FVGs waiting for a retrace
            for i in range(2, len(C)):
                while ptr < len(order) and order[ptr].known_at <= i:
                    known.append(order[ptr]); ptr += 1
                lows = [q for q in known[-14:] if q.kind == "L" and q.idx >= i - p["sweep_lookback"]]
                highs = [q for q in known if q.kind == "H"]
                # 1) liquidity sweep: wick through a known swing low
                for q in lows:
                    if q.idx not in swept and L[i] < q.price:
                        swept.add(q.idx)
                        mss = highs[-1].price if highs else None
                        if sweep is None or L[i] < sweep["low"]:
                            sweep = {"idx": i, "low": L[i], "mss": mss}
                if sweep is not None:
                    sweep["low"] = min(sweep["low"], L[i])
                    if i - sweep["idx"] > p["disp_window"]:
                        sweep = None
                # 2) displacement through structure leaving an FVG
                if sweep is not None and sweep["mss"] is not None and C[i] > sweep["mss"]:
                    for k in range(i, max(sweep["idx"] + 1, 2) - 1, -1):
                        gap = L[k] - H[k - 2]
                        if gap > p["min_fvg_atr"] * a[k]:
                            active.append({"top": L[k], "bottom": H[k - 2], "created": i, "stop": sweep["low"]})
                            break
                    sweep = None
                # 3) retrace into an active FVG
                keep = []
                for f in active:
                    if i - f["created"] > p["fvg_max_age"] or C[i] < f["bottom"]:
                        continue
                    if i > f["created"] and L[i] <= f["top"] and C[i] >= f["bottom"] \
                            and in_window(ctx, i, p["killzones"]) \
                            and (not p["use_htf"] or htf[i] * side >= 0):
                        stop = min(f["stop"], L[f["created"]:i + 1].min()) - p["stop_buf_atr"] * a[i]
                        out.append(RawSignal(i, side, side * C[i], side * stop,
                                             "Sweep → MSS → FVG retrace",
                                             features={"fvg_atr": float((f["top"] - f["bottom"]) / a[i])}))
                        continue
                    keep.append(f)
                active = keep
        return out

    def bias(self, df, ctx):
        return pd.Series(ctx["htf"], index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
def _leg_retrace_scan(self: Strategy, df, ctx, fib_touch: float, fib_floor: float, confirm: bool,
                      windows, use_htf: bool, label: str) -> list[RawSignal]:
    """After a bullish break of structure, measure the impulse leg (origin low → high) and enter
    when price retraces to `fib_touch` of the leg without closing below `fib_floor`."""
    p, a, htf = self.params, ctx["atr"], ctx["htf"]
    out = []
    for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
        order = _known_iter(piv)
        ptr, known = 0, []
        leg = None
        broken = set()
        for i in range(1, len(C)):
            while ptr < len(order) and order[ptr].known_at <= i:
                known.append(order[ptr]); ptr += 1
            highs = [q for q in known if q.kind == "H"]
            lows = [q for q in known if q.kind == "L"]
            if highs and lows and highs[-1].idx not in broken and C[i] > highs[-1].price:
                broken.add(highs[-1].idx)
                origin = L[lows[-1].idx:i + 1].min()
                leg = {"low": origin, "high": H[i], "start": i}
                if (leg["high"] - leg["low"]) < p["min_leg_atr"] * a[i]:
                    leg = None
                continue
            if leg is None:
                continue
            if i - leg["start"] > p["max_age"] or L[i] < leg["low"]:
                leg = None
                continue
            rng = leg["high"] - leg["low"]
            touch_lvl = leg["high"] - fib_touch * rng
            floor_lvl = leg["high"] - fib_floor * rng
            if L[i] > touch_lvl:
                leg["high"] = max(leg["high"], H[i])  # still extending
                continue
            if C[i] < floor_lvl or (confirm and C[i] <= O[i]):
                continue
            if not in_window(ctx, i, windows) or (use_htf and htf[i] * side < 0):
                continue
            stop = leg["low"] - p["stop_buf_atr"] * a[i]
            out.append(RawSignal(i, side, side * C[i], side * stop, label,
                                 structural_target=side * leg["high"],
                                 features={"leg_atr": float(rng / a[i]),
                                           "retrace": float((leg["high"] - L[i]) / rng)}))
            leg = None
    return out


class ICTOte(Strategy):
    name = "ict_ote"
    family = "ict"
    description = ("ICT Optimal Trade Entry: after a market-structure break, enter the 62–79% "
                   "retracement of the impulse leg inside a killzone, stop beyond the leg origin.")
    default_params = dict(swing=3, fib_touch=0.62, fib_floor=0.79, max_age=24, stop_buf_atr=0.1,
                          min_leg_atr=1.5, use_htf=True, killzones=KILLZONES)
    param_grid = {"swing": [2, 3, 5], "fib_touch": [0.5, 0.62, 0.705], "min_leg_atr": [1.0, 1.5, 2.5]}

    def _scan(self, df, ctx):
        p = self.params
        return _leg_retrace_scan(self, df, ctx, p["fib_touch"], p["fib_floor"], confirm=False,
                                 windows=p["killzones"], use_htf=p["use_htf"], label="MSS → OTE retrace")

    def bias(self, df, ctx):
        return pd.Series(ctx["htf"], index=df.index)


class DTFXZone(Strategy):
    name = "dtfx_zone"
    family = "dtfx"
    description = ("DTFX-style, simplified (the original version here — not a formal DTFX definition; see the "
                   "dtfx_* setups for those): the leg that broke structure becomes the zone (30/50/70% levels); "
                   "enter on a confirmed rejection from the zone, stop beyond the zone origin (100%).")
    default_params = dict(swing=5, fib_touch=0.5, fib_floor=0.85, confirm=True, max_age=36,
                          stop_buf_atr=0.1, min_leg_atr=2.0, use_htf=False)
    param_grid = {"swing": [3, 5, 8], "fib_touch": [0.3, 0.5, 0.7], "min_leg_atr": [1.5, 2.0, 3.0],
                  "use_htf": [True, False]}

    def _scan(self, df, ctx):
        p = self.params
        return _leg_retrace_scan(self, df, ctx, p["fib_touch"], p["fib_floor"], confirm=p["confirm"],
                                 windows=None, use_htf=p["use_htf"],
                                 label=f"BOS → {int(p['fib_touch']*100)}% zone rejection")

    def bias(self, df, ctx):
        # structure bias: last broken swing direction
        piv = self.pivots(df, ctx, self.params["swing"], self.params["swing"])
        C = df["close"].to_numpy()
        b = np.zeros(len(C))
        order = _known_iter(piv)
        ptr, last_h, last_l, cur = 0, None, None, 0
        for i in range(len(C)):
            while ptr < len(order) and order[ptr].known_at <= i:
                q = order[ptr]; ptr += 1
                if q.kind == "H": last_h = q.price
                else: last_l = q.price
            if last_h is not None and C[i] > last_h: cur = 1
            if last_l is not None and C[i] < last_l: cur = -1
            b[i] = cur
        return pd.Series(b, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
class StoicSBS(Strategy):
    name = "stoic_sbs"
    family = "sbs"
    description = ("Stoic Trader Swing Breakout Sequence: breakout (HH) → first tap (HL) → quick scalp "
                   "(new HH) → return to liquidate the first tap → double-bottom reversal → target the "
                   "new swing high. Entry on the lower-timeframe break after the double bottom.")
    default_params = dict(swing=3, db_tol_atr=0.35, max_wait=24, stop_buf_atr=0.1, golden=False)
    param_grid = {"swing": [2, 3, 4], "db_tol_atr": [0.2, 0.35, 0.5], "golden": [False, True]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        out = []
        for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
            order = _known_iter(piv)
            ptr, known, used = 0, [], set()
            for i in range(1, len(C)):
                while ptr < len(order) and order[ptr].known_at <= i:
                    known.append(order[ptr]); ptr += 1
                if len(known) < 5:
                    continue
                p0, p1, p2, p3, p4 = known[-5:]
                if [q.kind for q in (p0, p1, p2, p3, p4)] != ["L", "H", "L", "H", "L"]:
                    continue
                if p4.idx in used or i - p4.known_at > p["max_wait"]:
                    continue
                if not (p2.price > p0.price and p3.price > p1.price and p0.price < p4.price < p2.price):
                    continue
                tol = p["db_tol_atr"] * a[i]
                # second bottom: a low near p4 after p4 was confirmed
                seg = slice(p4.idx + 2, i + 1)
                lows = L[seg]
                if len(lows) == 0:
                    continue
                j = int(np.argmin(lows)) + p4.idx + 2
                if abs(L[j] - p4.price) > tol or L[j] < p0.price or j == i:
                    continue
                trigger = H[j:i].max() if j < i else H[j]
                if C[i] <= trigger or C[i - 1] > trigger:
                    continue
                if p["golden"]:  # Golden SBS: require the entry to sit in the discount of p4→p3
                    if C[i] > p4.price + 0.618 * (p3.price - p4.price):
                        continue
                used.add(p4.idx)
                stop = min(p4.price, L[j]) - p["stop_buf_atr"] * a[i]
                out.append(RawSignal(i, side, side * C[i], side * stop, "SBS double bottom → break",
                                     structural_target=side * p3.price,
                                     features={"seq_range_atr": float((p3.price - p0.price) / a[i])}))
        return out


# ─────────────────────────────────────────────────────────────────────────────
#  Core SMC toolkit: order blocks, breaker blocks, inverse FVGs, liquidity sweeps
# ─────────────────────────────────────────────────────────────────────────────
def _levels(df, ctx) -> dict:
    """PDH/PDL and Asia high/low known at each bar close (cached per frame)."""
    if "_levels" not in ctx:
        from ..bias import bias_frame
        from ..indicators import resample_ohlc
        h1 = resample_ohlc(df, "1h")
        b = bias_frame(h1, ctx["close_ts"])
        ctx["_levels"] = {k: b[k].to_numpy() for k in ("pdh", "pdl", "asia_hi", "asia_lo")}
    return ctx["_levels"]


class SMCOrderBlock(Strategy):
    name = "smc_order_block"
    family = "smc"
    description = ("SMC order block: after a displacement leg breaks structure (BOS), the last opposing "
                   "candle before the leg is the order block. Enter on the first return into the block, "
                   "stop beyond it. Optional: the leg must leave an FVG.")
    default_params = dict(swing=3, disp_atr=1.2, require_fvg=True, max_age=30, stop_buf_atr=0.1)
    param_grid = {"swing": [2, 3, 5], "disp_atr": [0.8, 1.2, 1.8], "require_fvg": [True, False],
                  "max_age": [15, 30, 50]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        out = []
        for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
            order = _known_iter(piv)
            ptr, known, broken, blocks = 0, [], set(), []
            for i in range(3, len(C)):
                while ptr < len(order) and order[ptr].known_at <= i:
                    known.append(order[ptr]); ptr += 1
                highs = [q for q in known if q.kind == "H"]
                lows = [q for q in known if q.kind == "L"]
                if highs and lows and highs[-1].idx not in broken and C[i] > highs[-1].price:
                    broken.add(highs[-1].idx)
                    start = lows[-1].idx
                    leg = H[start:i + 1].max() - L[start:i + 1].min()
                    fvg = any(L[k] > H[k - 2] for k in range(max(start + 2, 2), i + 1))
                    if leg >= p["disp_atr"] * a[i] * 2 and (fvg or not p["require_fvg"]):
                        for k in range(i, start - 1, -1):        # last down-candle before the leg
                            if C[k] < O[k] and k <= start + max(1, (i - start) // 2):
                                blocks.append({"hi": H[k], "lo": L[k], "created": i})
                                break
                keep = []
                for b in blocks:
                    if i - b["created"] > p["max_age"] or C[i] < b["lo"]:
                        continue
                    if i > b["created"] and L[i] <= b["hi"] and C[i] >= b["lo"]:
                        out.append(RawSignal(i, side, side * C[i], side * (b["lo"] - p["stop_buf_atr"] * a[i]),
                                             "BOS → return to order block",
                                             features={"ob_atr": float((b["hi"] - b["lo"]) / a[i])}))
                        continue
                    keep.append(b)
                blocks = keep
        return out


class SMCBreaker(Strategy):
    name = "smc_breaker"
    family = "smc"
    description = ("SMC/ICT breaker block: price sweeps a swing low (liquidity), then breaks the swing high "
                   "(MSS). The last up-candle before the sweep leg is the breaker; enter on the retest, "
                   "stop below the sweep low.")
    default_params = dict(swing=3, max_wait=24, max_age=30, stop_buf_atr=0.1, stop_at="breaker")
    param_grid = {"swing": [2, 3, 5], "max_age": [15, 30, 50], "stop_at": ["breaker", "sweep"]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        out = []
        for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
            order = _known_iter(piv)
            ptr, known, used, zones = 0, [], set(), []
            for i in range(3, len(C)):
                while ptr < len(order) and order[ptr].known_at <= i:
                    known.append(order[ptr]); ptr += 1
                if len(known) >= 3:
                    l1, h1, l2 = known[-3:] if known[-1].kind == "L" else (None, None, None)
                    if l1 and [l1.kind, h1.kind] == ["L", "H"] and l2.price < l1.price and h1.idx not in used \
                            and i - l2.known_at <= p["max_wait"] and C[i] > h1.price:
                        used.add(h1.idx)
                        for k in range(l2.idx, h1.idx - 1, -1):   # last up-candle before the sweep leg
                            if C[k] > O[k]:
                                zones.append({"hi": H[k], "lo": L[k], "sweep": l2.price, "created": i})
                                break
                keep = []
                for z in zones:
                    if i - z["created"] > p["max_age"] or C[i] < z["sweep"]:
                        continue
                    if i > z["created"] and L[i] <= z["hi"] and C[i] >= z["lo"]:
                        ref = z["lo"] if p["stop_at"] == "breaker" else z["sweep"]
                        out.append(RawSignal(i, side, side * C[i], side * (min(ref, L[i]) - p["stop_buf_atr"] * a[i]),
                                             "Sweep → MSS → breaker retest"))
                        continue
                    keep.append(z)
                zones = keep
        return out


class SMCInverseFVG(Strategy):
    name = "smc_ifvg"
    family = "smc"
    description = ("Inverse FVG: an opposing fair value gap that price closes through flips polarity; "
                   "enter on the retest of the inverted gap, stop beyond it.")
    default_params = dict(min_fvg_atr=0.3, inv_body_atr=0.6, max_age=40, retest_age=20, stop_buf_atr=0.15)
    param_grid = {"min_fvg_atr": [0.2, 0.3, 0.5], "inv_body_atr": [0.4, 0.6, 1.0], "max_age": [20, 40, 80],
                  "retest_age": [10, 20, 30]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        out = []
        for side, (O, H, L, C, piv) in _mirror(df, []):
            gaps, inverted = [], []
            for i in range(2, len(C)):
                if L[i - 2] - H[i] > p["min_fvg_atr"] * a[i]:           # bearish gap (in this view)
                    gaps.append({"top": L[i - 2], "bot": H[i], "created": i})
                keep = []
                for g in gaps:
                    if i - g["created"] > p["max_age"]:
                        continue
                    if i > g["created"] and C[i] > g["top"] and C[i] - O[i] >= p["inv_body_atr"] * a[i]:
                        # displacement close through the gap → inverted
                        inverted.append(g | {"inv": i})
                        continue
                    keep.append(g)
                gaps = keep
                keep = []
                for g in inverted:
                    if i - g["inv"] > p["retest_age"] or C[i] < g["bot"]:
                        continue
                    if i > g["inv"] and L[i] <= g["top"] and C[i] >= g["top"]:
                        out.append(RawSignal(i, side, side * C[i], side * (g["bot"] - p["stop_buf_atr"] * a[i]),
                                             "Inverse FVG retest"))
                        continue
                    keep.append(g)
                inverted = keep
        return out


class SMCLiquiditySweep(Strategy):
    name = "smc_liquidity_sweep"
    family = "smc"
    description = ("Liquidity raid: price runs the previous day's low/high or the Asia range extreme, closes "
                   "back inside, then shifts structure (CHoCH) on the entry timeframe. Stop beyond the raid.")
    default_params = dict(swing=2, choch_window=12, stop_buf_atr=0.1, pools=["pd", "asia"])
    param_grid = {"swing": [2, 3], "choch_window": [6, 12, 24], "pools": [["pd", "asia"], ["pd"], ["asia"]]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        lv = _levels(df, ctx)
        out = []
        for side, (O, H, L, C, piv) in _mirror(df, self.pivots(df, ctx, p["swing"], p["swing"])):
            pools = []
            if "pd" in p["pools"]:
                pools.append(lv["pdl"] if side > 0 else -lv["pdh"])
            if "asia" in p["pools"]:
                pools.append(lv["asia_lo"] if side > 0 else -lv["asia_hi"])
            order = _known_iter(piv)
            ptr, known, raid, taken = 0, [], None, set()
            for i in range(1, len(C)):
                while ptr < len(order) and order[ptr].known_at <= i:
                    known.append(order[ptr]); ptr += 1
                for lvl in pools:
                    x = lvl[i]
                    if np.isfinite(x) and L[i] < x and C[i] > x and (round(float(x), 6)) not in taken:
                        taken.add(round(float(x), 6))
                        highs = [q for q in known if q.kind == "H" and q.idx < i]
                        raid = {"i": i, "low": L[i], "level": float(x),
                                "choch": highs[-1].price if highs else H[max(0, i - 6):i + 1].max()}
                if raid is not None:
                    raid["low"] = min(raid["low"], L[i])
                    if i - raid["i"] > p["choch_window"]:
                        raid = None
                    elif i > raid["i"] and C[i] > raid["choch"]:
                        out.append(RawSignal(i, side, side * C[i], side * (raid["low"] - p["stop_buf_atr"] * a[i]),
                                             "Liquidity raid → CHoCH", features={"pool": raid["level"] * side}))
                        raid = None
        return out
