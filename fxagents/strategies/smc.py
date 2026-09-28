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
    description = ("Dave Teaches FX: trade with the break of structure. The leg that broke structure "
                   "becomes the zone (30/50/70% levels); enter on a confirmed rejection from the zone, "
                   "stop beyond the zone origin (100%).")
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
