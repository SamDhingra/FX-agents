"""Pure market-structure setups: displacement continuation, BOS retest, MSS, CHoCH retest.
They share structure.market_structure, so 'BOS', 'CHoCH' and 'MSS' mean exactly one thing each
(see the definitions at the top of fxagents/structure.py)."""
from __future__ import annotations

import pandas as pd

from .. import structure as sx
from ..structure import BULL_BOS, BULL_CHOCH
from .base import RawSignal
from .ict import KILLZONES, _Fast, _mask


class SMCDisplacement(_Fast):
    name = "smc_displacement"
    family = "displacement"
    description = ("Displacement continuation: a displacement candle (body ≥ k × ATR, ≥ 60% of its range) "
                   "that breaks structure and leaves a fair value gap. Entry on the first retrace to the gap "
                   "(its top, or its 50% 'consequent encroachment'), stop below the displacement candle.")
    default_params = dict(swing=2, disp_k=1.2, fvg_min=0.1, entry="ce", age=12, stop="disp_low",
                          stop_buf_atr=0.1, windows=None)
    param_grid = {"swing": [2, 3], "disp_k": [1.0, 1.5], "entry": ["top", "ce"], "stop": ["disp_low", "fvg_bot"]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ev = v.O, v.H, v.L, v.C, v.ms["event"]
            disp = sx.displacement_up(O, H, L, C, a, p["disp_k"])
            pend = zone = None
            for i in range(3, len(C)):
                if ev[i] in (BULL_BOS, BULL_CHOCH) and disp[i]:
                    pend = {"d": i, "low": min(L[i], L[i - 1])}
                elif pend is not None and i == pend["d"] + 1:
                    if L[i] > H[i - 2] and L[i] - H[i - 2] > p["fvg_min"] * a[i]:
                        zone = {"top": L[i], "bot": H[i - 2], "created": i, "low": pend["low"]}
                    pend = None
                if zone is None or i <= zone["created"]:
                    continue
                lvl = zone["top"] if p["entry"] == "top" else 0.5 * (zone["top"] + zone["bot"])
                if i - zone["created"] > p["age"] or C[i] < zone["bot"]:
                    zone = None
                elif L[i] <= lvl and win[i]:
                    ref = zone["low"] if p["stop"] == "disp_low" else zone["bot"]
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(min(ref, L[i]) - p["stop_buf_atr"] * a[i]),
                                         f"Displacement BOS → FVG {p['entry']}"))
                    zone = None
        return out


class _RetestBase(_Fast):
    """After a structure break, wait for price to move away and come back to retest the broken level."""
    kind = BULL_BOS
    label = "BOS"

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms = v.O, v.H, v.L, v.C, v.ms
            st = None
            for i in range(3, len(C)):
                if ms["event"][i] == self.kind:
                    src = int(ms["brk_src"][i])
                    st = {"lvl": ms["brk"][i], "origin": L[src:i + 1].min(), "i": i, "armed": False}
                    continue
                if ms["event"][i] < 0:
                    st = None
                if st is None:
                    continue
                if i - st["i"] > p["age"] or C[i] < st["origin"]:
                    st = None
                    continue
                if H[i] > st["lvl"] + p["away_atr"] * a[i]:
                    st["armed"] = True
                if st["armed"] and L[i] <= st["lvl"] + p["tol_atr"] * a[i] and C[i] >= st["lvl"] - p["tol_atr"] * a[i] \
                        and C[i] > O[i] and win[i]:
                    ref = st["origin"] if p["stop"] == "origin" else st["lvl"] - a[i]
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(min(ref, L[i]) - p["stop_buf_atr"] * a[i]),
                                         f"{self.label} → retest of the broken level"))
                    st = None
        return out


class SMCBosRetest(_RetestBase):
    name = "smc_bos_retest"
    family = "bos"
    kind, label = BULL_BOS, "BOS"
    description = ("Break of structure (continuation): in an up-trend, a close above the last swing high; after "
                   "price moves away, entry on the bullish retest of the broken level (old resistance → support). "
                   "Stop below the leg's origin low or 1 ATR below the level.")
    default_params = dict(swing=3, tol_atr=0.25, away_atr=0.5, age=24, stop="origin", stop_buf_atr=0.1, windows=None)
    param_grid = {"swing": [2, 3, 5], "stop": ["origin", "level"], "tol_atr": [0.15, 0.3]}


class SMCChochRetest(_RetestBase):
    name = "smc_choch"
    family = "choch"
    kind, label = BULL_CHOCH, "CHoCH"
    description = ("Change of character: the FIRST close above a swing high while the trend was down. After price "
                   "moves away, entry on the bullish retest of that level; stop below the low that made the CHoCH.")
    default_params = dict(swing=3, tol_atr=0.25, away_atr=0.5, age=24, stop="origin", stop_buf_atr=0.1, windows=None)
    param_grid = {"swing": [2, 3, 5], "stop": ["origin", "level"], "tol_atr": [0.15, 0.3]}


class SMCMss(_Fast):
    name = "smc_mss"
    family = "mss"
    description = ("Market structure shift (aggressive entry): sell-side liquidity is swept (a swing low is "
                   "taken), then a displacement candle closes above the last swing high — a CHoCH made with "
                   "displacement. Entry at that close, stop below the sweep low.")
    default_params = dict(swing=2, sweep_bars=20, disp_k=1.0, stop_buf_atr=0.1, windows=KILLZONES)
    param_grid = {"swing": [2, 3], "disp_k": [0.8, 1.2], "sweep_bars": [10, 20]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms = v.O, v.H, v.L, v.C, v.ms
            disp = sx.displacement_up(O, H, L, C, a, p["disp_k"])
            sweep, used = None, -1
            for i in range(3, len(C)):
                li = ms["lo_i"][i]
                if li >= 0 and li != used and L[i] < ms["lo"][i]:
                    used = li
                    sweep = {"i": i, "low": L[i]}
                if sweep is None:
                    continue
                sweep["low"] = min(sweep["low"], L[i])
                if i - sweep["i"] > p["sweep_bars"]:
                    sweep = None
                elif ms["event"][i] == BULL_CHOCH and disp[i] and win[i]:
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(sweep["low"] - p["stop_buf_atr"] * a[i]),
                                         "Sweep → MSS (displacement CHoCH)"))
                    sweep = None
        return out


class VWAPSetup(_Fast):
    name = "vwap"
    family = "vwap"
    description = ("Session VWAP (anchored at the 17:00 NY roll, weighted by tick volume). Three separate "
                   "definitions, never mixed: 'pullback' — price held above VWAP (≥6 of the last 8 closes), "
                   "dips to it and closes back above with a bullish candle; 'reclaim' — a close back above "
                   "VWAP from below with a ≥0.5 ATR body; 'band' — a dip to the −2σ VWAP band that closes back "
                   "inside it. Stop below the last 3 bars' low. The HTF bias rule decides the side, as for "
                   "every setup.")
    default_params = dict(mode="pullback", tol_atr=0.15, hold=6, stop_buf_atr=0.1, cooldown=6, windows=None)
    param_grid = {"mode": ["pullback", "reclaim", "band"], "tol_atr": [0.05, 0.3]}

    def _scan(self, df, ctx):
        import numpy as np
        p, a = self.params, ctx["atr"]
        if "_vwap" not in ctx:
            ctx["_vwap"] = sx.session_vwap(df)
        vw0, sd = ctx["_vwap"]
        win = _mask(ctx, p["windows"])
        O0, H0, L0, C0 = (df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
        day = ((df.index + pd.Timedelta(hours=7)).normalize().asi8)
        out = []
        for side in (1, -1):
            if side > 0:
                O, H, L, C, vw = O0, H0, L0, C0, vw0
            else:
                O, H, L, C, vw = -O0, -L0, -H0, -C0, -vw0
            above = C > vw
            last = -10**9
            for i in range(10, len(C)):
                if not (np.isfinite(vw[i]) and np.isfinite(a[i]) and win[i]) or i - last < p["cooldown"]:
                    continue
                if day[i] != day[i - 8]:            # need 8 bars of today's VWAP
                    continue
                m = p["mode"]
                if m == "pullback":
                    ok = (above[i - 8:i].sum() >= p["hold"] and L[i] <= vw[i] + p["tol_atr"] * a[i]
                          and C[i] > vw[i] and C[i] > O[i])
                elif m == "reclaim":
                    ok = (not above[i - 1] and above[i] and C[i] - O[i] >= 0.5 * a[i])
                else:                                # band: dip to −2σ, close back inside
                    band = vw[i] - 2 * sd[i]
                    ok = bool(np.isfinite(band) and sd[i] > 0 and L[i] <= band + p["tol_atr"] * a[i]
                              and C[i] > band and C[i] > O[i])
                if not ok:
                    continue
                stop = min(L[i - 2:i + 1]) - p["stop_buf_atr"] * a[i]
                if stop >= C[i]:
                    continue
                out.append(RawSignal(i, side, side * C[i], side * stop, f"VWAP {m}"))
                last = i
        return out
