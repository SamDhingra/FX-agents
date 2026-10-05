"""DTFX (Dave Teaches FX) formalised.

DTFX is taught visually, and different sources draw some pieces differently. Where definitions
CONFLICT, each choice is its own strategy class with its own id, so they are tested and traded
separately. None of them is labelled "canonical DTFX" and none mixes two incompatible definitions.

Shared by every variant (the parts the sources agree on):
  • Swings: fractal swing highs/lows (`swing` bars each side), known only once confirmed.
  • Valid low (bullish case): the lowest low between the swing high that gets broken and the break.
    It is the low that "did the work". Once price breaks structure, that valid low is PROTECTED:
    bullish structure holds while it holds.
  • BOS: a break of the last swing high in the trend's direction. A flip/MSS is the first break
    against the trend. Both start a new bullish leg (valid low → break high) and a new zone.
  • Invalidation: price breaks the protected low (by the same rule used for BOS) → zone dead,
    structure flips.
  • Mitigation: a zone is used once. The first touch mitigates it, whether or not a trade was taken.
  • Stop: beyond the protected low (or the zone candle for the origin-zone definition) plus a buffer.
  • Target: the system manages exits (1R partial, trailing). The structural target is the leg high.
  • Session filter: killzones only, or any session window (parameter, not a definition).
  • Multi-timeframe: optionally require the 1-hour structure trend to agree (parameter).

Where sources conflict (→ separate classes):
  A. What counts as a break:      candle CLOSE beyond the swing    vs   any WICK beyond it
  B. What the zone is:            the leg's Fibonacci retracement   vs   the origin candle (last
                                  (30/50/70% of valid low → high)        opposing candle at the valid low)
  C. Fibonacci anchor (the high): the leg's EXTREME (keeps extending   vs   the high of the candle
                                  until the first retrace)                  that broke structure

  dtfx_close_fib      A=close  B=fib     C=extreme
  dtfx_wick_fib       A=wick   B=fib     C=extreme
  dtfx_close_fib_brk  A=close  B=fib     C=break-candle high
  dtfx_close_origin   A=close  B=origin-candle zone  (C not applicable)
"""
from __future__ import annotations

import numpy as np

from .. import structure as sx
from ..structure import BULL_BOS, BULL_CHOCH
from .base import RawSignal
from .ict import KILLZONES, _Fast, _mask


class _DTFX(_Fast):
    family = "dtfx_formal"
    rule = "close"          # A
    zone_kind = "fib"       # B
    anchor = "extreme"      # C
    default_params = dict(swing=3, level=0.5, confirm="rejection", sessions="all", mtf="none",
                          min_leg_atr=1.5, max_age=48, stop_buf_atr=0.1)
    param_grid = {"swing": [3, 5], "level": [0.3, 0.5, 0.7], "confirm": ["touch", "rejection"],
                  "mtf": ["none", "1h"], "sessions": ["all", "killzones"]}

    @classmethod
    def definition(cls) -> dict:
        return {"break": cls.rule, "zone": cls.zone_kind, "anchor": cls.anchor if cls.zone_kind == "fib" else None}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, KILLZONES if p["sessions"] == "killzones" else None)
        htf = sx.htf_trend(df, ctx, "1h") if p["mtf"] == "1h" else None
        out = []
        for v in sx.views(df, ctx, p["swing"], self.rule):
            O, H, L, C, ms = v.O, v.H, v.L, v.C, v.ms
            inval_px = C if self.rule == "close" else L
            zone = None
            for i in range(3, len(C)):
                ev = ms["event"][i]
                if ev in (BULL_BOS, BULL_CHOCH):                         # new bullish leg → new zone
                    src = int(ms["brk_src"][i])
                    oi = src + int(np.argmin(L[src:i + 1]))              # valid (protected) low
                    origin, hi = L[oi], H[i]
                    zone = None
                    if hi - origin < p["min_leg_atr"] * a[i]:
                        continue
                    z = {"start": i, "origin": origin, "ext": hi, "brk_hi": hi, "kind": "BOS" if ev == BULL_BOS else "flip"}
                    if self.zone_kind == "origin":
                        k = next((k for k in range(oi, max(src, oi - 3) - 1, -1) if C[k] < O[k]), oi)
                        z["zhi"], z["zlo"] = H[k], min(L[k], origin)
                    zone = z
                    continue
                if ev < 0:                                               # bearish break → bullish zone gone
                    zone = None
                    continue
                if zone is None:
                    continue
                floor = zone["zlo"] if self.zone_kind == "origin" else zone["origin"]
                if inval_px[i] < floor or i - zone["start"] > p["max_age"]:
                    zone = None
                    continue
                if self.zone_kind == "fib":
                    top = zone["ext"] if self.anchor == "extreme" else zone["brk_hi"]
                    lvl = top - p["level"] * (top - zone["origin"])
                else:
                    lvl = zone["zhi"]
                if L[i] > lvl:
                    if self.anchor == "extreme":
                        zone["ext"] = max(zone["ext"], H[i])             # the leg is still extending
                    continue
                # first touch → zone mitigated, trade or not
                ok = C[i] > floor if p["confirm"] == "touch" else (C[i] > lvl and C[i] > O[i])
                if ok and win[i] and (htf is None or htf[i] * v.side > 0):
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(floor - p["stop_buf_atr"] * a[i]),
                                         f"DTFX {self.name[5:]} {zone['kind']} → "
                                         + (f"{int(p['level'] * 100)}% " if self.zone_kind == "fib" else "origin zone ")
                                         + p["confirm"],
                                         structural_target=v.px(zone["ext"]),
                                         features={"leg_atr": float((zone["ext"] - zone["origin"]) / a[i])}))
                zone = None
        return out


class DTFXCloseFib(_DTFX):
    name = "dtfx_close_fib"
    rule, zone_kind, anchor = "close", "fib", "extreme"
    description = ("DTFX — close-based structure, Fibonacci zone anchored valid low → leg extreme; entry at the "
                   "30/50/70% level on first touch (or touch + rejection close), stop below the protected low.")


class DTFXWickFib(_DTFX):
    name = "dtfx_wick_fib"
    rule, zone_kind, anchor = "wick", "fib", "extreme"
    description = ("DTFX — wick-based structure (any trade through a swing counts as the break and as the "
                   "invalidation), Fibonacci zone valid low → leg extreme, first-touch entry, stop below the protected low.")


class DTFXCloseFibBreak(_DTFX):
    name = "dtfx_close_fib_brk"
    rule, zone_kind, anchor = "close", "fib", "break"
    description = ("DTFX — close-based structure, Fibonacci zone anchored valid low → the HIGH OF THE CANDLE "
                   "THAT BROKE STRUCTURE (not the later extreme); first-touch entry, stop below the protected low.")


class DTFXCloseOrigin(_DTFX):
    name = "dtfx_close_origin"
    rule, zone_kind, anchor = "close", "origin", "extreme"
    description = ("DTFX — close-based structure, zone = the origin candle (last opposing candle at the valid "
                   "low); entry on the first return to the zone, stop below the zone.")
    default_params = dict(_DTFX.default_params)
    param_grid = {"swing": [3, 5], "confirm": ["touch", "rejection"], "mtf": ["none", "1h"],
                  "sessions": ["all", "killzones"]}
