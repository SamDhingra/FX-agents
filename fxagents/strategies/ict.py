"""ICT models written as explicit, testable rules: 2022 model, Silver Bullet, Turtle Soup, AMD (power of
three) and SMT divergence. Long side only; shorts run the same code on the mirrored series
(structure.views), so both sides are symmetric by construction. All O(n) — safe on 1-minute history."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import structure as sx
from .base import RawSignal, Strategy

KILLZONES = [["02:00", "05:00"], ["08:30", "11:00"], ["13:30", "15:00"]]
SB_WINDOWS = {"all": [["03:00", "04:00"], ["10:00", "11:00"], ["14:00", "15:00"]],
              "am": [["10:00", "11:00"]], "am_pm": [["10:00", "11:00"], ["14:00", "15:00"]]}
MANIP = {"london": [["01:00", "05:00"]], "ny": [["07:00", "10:30"]], "both": [["01:00", "05:00"], ["07:00", "10:30"]]}


def _mask(ctx: dict, windows) -> np.ndarray:
    key = ("_win", str(windows))
    if key not in ctx:
        ctx[key] = sx.window_mask(ctx["close_ts"], windows)
    return ctx[key]


def _bar_minutes(ctx: dict) -> float:
    if "_bar_min" not in ctx:
        ts = ctx["close_ts"]
        ctx["_bar_min"] = float(pd.Series(ts).diff().median().total_seconds() / 60) if len(ts) > 2 else 5.0
    return ctx["_bar_min"]


def _tday(df: pd.DataFrame, ctx: dict) -> np.ndarray:
    if "_tday" not in ctx:
        ctx["_tday"] = ((df.index + pd.Timedelta(hours=7)).normalize().asi8 // 86_400_000_000_000).astype(np.int64)
    return ctx["_tday"]


class _Fast(Strategy):
    """Marker: linear-time scan, can run on a whole history frame (no windowing needed).
    Every fast setup also takes an optional `vol` parameter (structure.vol_ok: impulse / dry / climax);
    the research grid tries each as a separate variant."""
    fast = True
    vol_grid = ("impulse", "dry", "climax")

    def _scan_full(self, df, ctx=None):
        out = super()._scan_full(df, ctx)
        mode = self.params.get("vol", "any")
        if mode in (None, "any") or not out:
            return out
        ctx = ctx if ctx is not None else self.context(df)
        rv = ctx.get("rvol")
        if rv is None or len(rv) != len(df):
            rv = ctx["rvol"] = sx.rvol_tod(df)
        O, C = df["open"].to_numpy(float), df["close"].to_numpy(float)
        keep = []
        for s in out:
            if sx.vol_ok(mode, s.i, s.side, O, C, rv):
                s.features["rvol"] = float(rv[s.i]) if np.isfinite(rv[s.i]) else None
                keep.append(s)
        return keep


# ─────────────────────────────────────────────────────────────────────────────
class ICT2022(_Fast):
    name = "ict_2022"
    family = "ict2022"
    description = ("ICT 2022 model: inside a killzone, price raids sell-side liquidity (a swing low, or the "
                   "Asia/London/prior-day low), then shifts structure with displacement (close above the last "
                   "swing high with a ≥1 ATR body) leaving a fair value gap. Entry on the retrace into that FVG, "
                   "optionally only in the discount half of the dealing range; stop beyond the raid low or the FVG.")
    default_params = dict(swing=2, liq="swing", disp_k=1.0, fvg_min=0.1, max_wait=15, fvg_age=10,
                          discount=True, stop="sweep", stop_buf_atr=0.1, windows=KILLZONES)
    param_grid = {"swing": [2, 3], "liq": ["swing", "session"], "discount": [True, False],
                  "stop": ["sweep", "fvg"], "max_wait": [10, 20]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms, lv = v.O, v.H, v.L, v.C, v.ms, v.lv
            disp = sx.displacement_up(O, H, L, C, a, p["disp_k"])
            fok, ftop, fbot = sx.fvg_up(H, L, a, p["fvg_min"])
            st = pend = zone = None
            swept_idx, swept_lv = -1, set()
            for i in range(3, len(C)):
                # 1) liquidity raid
                hit = None
                if p["liq"] == "swing":
                    if ms["lo_i"][i] >= 0 and ms["lo_i"][i] != swept_idx and L[i] < ms["lo"][i]:
                        swept_idx, hit = ms["lo_i"][i], True
                else:
                    for k in ("asia_lo", "lon_lo", "pdl"):
                        x = lv[k][i]
                        if np.isfinite(x) and L[i] < x and (k, round(float(x), 5)) not in swept_lv:
                            swept_lv.add((k, round(float(x), 5))); hit = True
                if hit and np.isfinite(ms["hi"][i]):
                    if st is None or L[i] < st["low"]:
                        st = {"i": i, "low": L[i], "mss": ms["hi"][i]}
                if st is not None:
                    st["low"] = min(st["low"], L[i])
                    if i - st["i"] > p["max_wait"]:
                        st = None
                    elif C[i] > st["mss"] and disp[st["i"]:i + 1].any():          # 2) MSS with displacement
                        pend = {"lo": st["low"], "start": st["i"], "mss_i": i}
                        st = None
                # 3) the FVG left by the displacement leg (may confirm up to 2 bars after the MSS close)
                if pend is not None:
                    ks = [k for k in range(i, pend["start"] + 1, -1) if fok[k] and fbot[k] > pend["lo"]]
                    if ks:
                        k = ks[0]
                        zone = {"top": ftop[k], "bot": fbot[k], "created": i, "lo": pend["lo"],
                                "start": pend["start"]}
                        pend = None
                    elif i - pend["mss_i"] >= 2:
                        pend = None
                # 4) retrace into the FVG
                if zone is not None and i > zone["created"]:
                    if i - zone["created"] > p["fvg_age"] or C[i] < zone["bot"]:
                        zone = None
                    elif L[i] <= zone["top"] and C[i] >= zone["bot"] and win[i]:
                        hi = H[zone["start"]:i + 1].max()
                        if not p["discount"] or C[i] <= zone["lo"] + 0.5 * (hi - zone["lo"]):
                            ref = zone["lo"] if p["stop"] == "sweep" else zone["bot"]
                            out.append(RawSignal(i, v.side, v.px(C[i]), v.px(ref - p["stop_buf_atr"] * a[i]),
                                                 "ICT 2022: raid → MSS w/ displacement → FVG",
                                                 structural_target=v.px(hi),
                                                 features={"fvg_atr": float((zone["top"] - zone["bot"]) / a[i])}))
                            zone = None
        return out


# ─────────────────────────────────────────────────────────────────────────────
class ICTSilverBullet(_Fast):
    name = "ict_silver_bullet"
    family = "silver_bullet"
    description = ("ICT Silver Bullet: only inside 03–04, 10–11 or 14–15 NY. A displacement candle inside the "
                   "hour leaves a fair value gap (optionally after a raid on nearby sell-side liquidity); entry on "
                   "the first retrace into the FVG before the hour ends, stop below the FVG's first candle or the raid.")
    default_params = dict(sb="all", require_sweep=True, sweep_minutes=60, disp_k=0.8, fvg_min=0.1,
                          stop="fvg", stop_buf_atr=0.1, swing=2)
    param_grid = {"sb": ["all", "am", "am_pm"], "require_sweep": [True, False], "stop": ["fvg", "sweep"]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, SB_WINDOWS[p["sb"]])
        look = max(1, int(round(p["sweep_minutes"] / _bar_minutes(ctx))))
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms, lv = v.O, v.H, v.L, v.C, v.ms, v.lv
            disp = sx.displacement_up(O, H, L, C, a, p["disp_k"])
            fok, ftop, fbot = sx.fvg_up(H, L, a, p["fvg_min"])
            sweep_i, sweep_low, swept_idx, zone = -10 ** 9, np.nan, -1, None
            for i in range(3, len(C)):
                lvls = [ms["lo"][i] if ms["lo_i"][i] != swept_idx else np.nan, lv["asia_lo"][i], lv["lon_lo"][i], lv["pdl"][i]]
                for j, x in enumerate(lvls):
                    if np.isfinite(x) and L[i] < x:
                        if j == 0:
                            swept_idx = ms["lo_i"][i]
                        sweep_low = L[i] if i - sweep_i > look else min(sweep_low, L[i])
                        sweep_i = i
                        break
                if fok[i] and win[i] and win[i - 1] and disp[i - 1]:
                    if not p["require_sweep"] or i - sweep_i <= look:
                        zone = {"top": ftop[i], "bot": fbot[i], "c1": L[i - 2], "created": i,
                                "sweep": sweep_low if i - sweep_i <= look else L[i - 2]}
                if zone is None or i <= zone["created"]:
                    continue
                if not win[i] or C[i] < zone["bot"]:
                    zone = None
                elif L[i] <= zone["top"] and C[i] >= zone["bot"]:
                    ref = zone["c1"] if p["stop"] == "fvg" else min(zone["sweep"], zone["c1"])
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(ref - p["stop_buf_atr"] * a[i]),
                                         f"Silver Bullet ({p['sb']}): displacement FVG retrace"))
                    zone = None
        return out


# ─────────────────────────────────────────────────────────────────────────────
class ICTTurtleSoup(_Fast):
    name = "ict_turtle_soup"
    family = "turtle_soup"
    description = ("ICT Turtle Soup: price runs an old low (prior 20/40-bar low, prior-day low or Asia/London "
                   "low) to take the stops below it, then fails: entry on the close back above the level (within "
                   "3 bars) or on the change of character that follows. Stop beyond the raid's extreme.")
    default_params = dict(level="n20", min_pierce_atr=0.1, confirm="close_back", max_back=3, choch_window=10,
                          swing=2, stop_buf_atr=0.1, windows=KILLZONES)
    param_grid = {"level": ["n20", "n40", "pd", "session"], "confirm": ["close_back", "choch"]}

    def _levels(self, v: sx.View) -> np.ndarray:
        lvl = self.params["level"]
        if lvl in ("n20", "n40"):
            n = int(lvl[1:])
            s = pd.Series(v.L).shift(3).rolling(n - 2, min_periods=n - 2).min()     # an OLD low: ≥3 bars back
            return s.to_numpy()
        if lvl == "pd":
            return v.lv["pdl"]
        return np.fmin(v.lv["asia_lo"], v.lv["lon_lo"])

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms = v.O, v.H, v.L, v.C, v.ms
            level = self._levels(v)
            st, used = None, set()
            wait = p["max_back"] if p["confirm"] == "close_back" else p["choch_window"]
            for i in range(3, len(C)):
                x = level[i]
                if np.isfinite(x) and L[i] < x - p["min_pierce_atr"] * a[i] and round(float(x), 5) not in used:
                    used.add(round(float(x), 5))
                    st = {"i": i, "lvl": x, "low": L[i], "choch": ms["hi"][i]}
                if st is None:
                    continue
                st["low"] = min(st["low"], L[i])
                if i - st["i"] > wait:
                    st = None
                    continue
                if p["confirm"] == "close_back":
                    ok = C[i] > st["lvl"] and C[i] > O[i]
                else:
                    ok = np.isfinite(st["choch"]) and C[i] > st["choch"]
                if ok and win[i]:
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(st["low"] - p["stop_buf_atr"] * a[i]),
                                         f"Turtle Soup ({p['level']}, {p['confirm']})",
                                         features={"pierce_atr": float((st["lvl"] - st["low"]) / a[i])}))
                    st = None
        return out


# ─────────────────────────────────────────────────────────────────────────────
class ICTAMD(_Fast):
    name = "ict_amd"
    family = "amd"
    description = ("ICT AMD / power of three: Accumulation (the Asia range, or price around the midnight open), "
                   "Manipulation (a Judas swing below the Asia low / midnight open during London or the NY "
                   "open), Distribution (price reclaims it and shifts structure). Entry on the reclaim/CHoCH, "
                   "stop below the manipulation low. One trade per side per day.")
    default_params = dict(model="asia", manip="both", min_pierce_atr=0.1, disp_k=0.8, swing=2,
                          stop_buf_atr=0.1, windows=KILLZONES)
    param_grid = {"model": ["asia", "midnight"], "manip": ["london", "ny", "both"]}

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win, man = _mask(ctx, p["windows"]), _mask(ctx, MANIP[p["manip"]])
        day = _tday(df, ctx)
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            O, H, L, C, ms, lv = v.O, v.H, v.L, v.C, v.ms, v.lv
            ref = lv["asia_lo"] if p["model"] == "asia" else lv["mid_open"]
            disp = sx.displacement_up(O, H, L, C, a, p["disp_k"])
            st, done = None, set()
            for i in range(3, len(C)):
                if st is not None and st["day"] != day[i]:
                    st = None
                x = ref[i]
                if not np.isfinite(x) or day[i] in done:
                    continue
                if man[i] and L[i] < x - p["min_pierce_atr"] * a[i]:
                    if st is None:
                        st = {"day": day[i], "low": L[i], "choch": ms["hi"][i]}
                    st["low"] = min(st["low"], L[i])
                if st is None or not win[i]:
                    continue
                if p["model"] == "asia":
                    ok = C[i] > x and np.isfinite(st["choch"]) and C[i] > st["choch"]
                else:
                    ok = C[i] > x and disp[i]
                if ok:
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(st["low"] - p["stop_buf_atr"] * a[i]),
                                         f"AMD ({p['model']}): manipulation → distribution",
                                         structural_target=v.px(lv["asia_hi"][i]) if p["model"] == "asia" else None))
                    done.add(day[i]); st = None
        return out


# ─────────────────────────────────────────────────────────────────────────────
class SMTDivergence(_Fast):
    name = "smt_divergence"
    family = "smt"
    needs_peers = True
    description = ("ICT SMT divergence across correlated indices (NDQ / US30 — the MNQ/MYM of the "
                   "futures world): this index takes its last swing low while a correlated index does NOT take "
                   "its equivalent low. That crack in correlation marks the raid; entry on the change of "
                   "character (or the reclaim of the swept low), stop below the raid.")
    default_params = dict(swing=2, confirm="choch", confirm_window=10, match_bars=6, stop_buf_atr=0.1,
                          windows=KILLZONES)
    param_grid = {"swing": [2, 3], "confirm": ["choch", "reclaim"]}

    def _peer_views(self, ctx: dict, side: int) -> list[dict]:
        key = ("_smt_peers", self.params["swing"], side)
        if key in ctx:
            return ctx[key]
        res = []
        for b in ctx.get("peers") or []:
            Hb, Lb = b["high"].to_numpy(dtype=float), b["low"].to_numpy(dtype=float)
            h, l = (Hb, Lb) if side > 0 else (-Lb, -Hb)
            piv = sx.pivots_arr(h, l, self.params["swing"], self.params["swing"], reduce=False)
            res.append({"L": l, **sx.swing_levels(piv, len(l))})
        ctx[key] = res
        return res

    def _scan(self, df, ctx):
        p, a = self.params, ctx["atr"]
        win = _mask(ctx, p["windows"])
        out = []
        for v in sx.views(df, ctx, p["swing"]):
            peers = self._peer_views(ctx, v.side)
            if not peers:
                continue
            O, H, L, C, ms = v.O, v.H, v.L, v.C, v.ms
            st, used = None, -1
            for i in range(3, len(C)):
                li = ms["lo_i"][i]
                if li >= 0 and li != used and L[i] < ms["lo"][i]:
                    used = li
                    for b in peers:                          # does any peer hold its equivalent low?
                        bi = b["lo_i"][i]
                        if bi < 0 or abs(bi - li) > p["match_bars"]:
                            continue
                        after = b["L"][bi + 1:i + 1]                      # peer's lows since its swing low
                        if len(after) and np.nanmin(after) > b["lo"][i]:
                            st = {"i": i, "low": L[i], "lvl": ms["lo"][i], "choch": ms["hi"][i]}
                            break
                if st is None:
                    continue
                st["low"] = min(st["low"], L[i])
                if i - st["i"] > p["confirm_window"]:
                    st = None
                    continue
                ok = (np.isfinite(st["choch"]) and C[i] > st["choch"]) if p["confirm"] == "choch" \
                    else (C[i] > st["lvl"] and C[i] > O[i])
                if ok and win[i]:
                    out.append(RawSignal(i, v.side, v.px(C[i]), v.px(st["low"] - p["stop_buf_atr"] * a[i]),
                                         f"SMT divergence → {p['confirm']}"))
                    st = None
        return out
