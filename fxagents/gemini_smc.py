"""Gemini's rebuilt SMC / ICT / DTFX gold setups (Sam, 2026-10-17), coded as specified and frozen before any result.

    python -m fxagents.gemini_smc --data dev_m1,holdout_m1 --out data/year_test/gemini_smc

  bos   #1 G-BOS-iFVG-15M     break of a 5-bar swing with displacement + FVG/iFVG, shallow 38.2–50% retest
  wick  #2 G-DTFX-Wick-15M    wick-to-wick impulse after a structure shift, limit at the 38.2% wick retracement
  sbs   #3 G-SBS-Sweep-15M    sweep of an internal 15m swing inside the 4h trend, displacement + FVG, limit at the FVG

OUT-OF-SAMPLE DESIGN (Sam chose it, 2026-10-17). Gemini built these rules from our one-year setup table, whose
trades run 2025-10-08 → 2026-10-08 — inside dev_m1. So that year is IN-SAMPLE and is only reported, never judged.
Judged ("clean") data: dev_m1 before 2025-10-08 (Oct 2024 – Oct 2025) and the whole holdout_m1 (2021 – Sep 2024).
Pass = on the clean data combined: ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs;
AND avg R > 0 in each clean piece on its own; AND better than both controls on the clean data. The holdout is used
here once for these three rules.

Shared conventions (same engine as fxagents/gemini_test.py): 15m clock bars on mid prices; fills on real bid/ask
(stop orders at the level or a gap-through open; limit orders at the level or a better open); stops/targets on the
exit side; R = actual fill to initial stop; flat 15:50 NY; one open position at a time (the bot's one-per-symbol rule).
ATR(14) = Wilder on 15m mid bars through the decision bar. MedVol(20) = median volume of the same 15m clock slot over
the previous 20 days that have it. EMA(50) 1h on clock hours, 4h on bars ending 01/05/09/13/17/21 NY.
Shorts are the exact mirror: the detector runs on the negated price series (high ↔ −low), so both sides use
identical code. News blocks use the verified calendar (fxagents/usd_calendar.py: FOMC, CPI, NFP, PPI).

Open points fixed here before testing:
  bos   "unbroken" swing high = no 15m close above it since it formed; most recent such, ≥4 bars old. iFVG = a bearish
        FVG (High_m < Low_m-2) formed in the 20 bars before B0, with B0 closing above its top (Low_m-2). The buy stop
        after the confirmation bar lives for 2 bars on BOTH sides (the spec said "next bar" for longs, 2 bars for
        shorts). Session cap by entry time (London < 08:00 NY ≤ NY). B0 must close by 13:00 NY.
  wick  structure shift = first 15m close above the last confirmed 5-bar swing high, close above the 4h EMA, shift bar
        closing 03:00–12:30. W_low = lowest low from the prior confirmed swing low to the shift bar. W_high = highest
        high from the shift bar through the first bar that closes below the previous close (looked for within 12 bars).
        The limit is placed after that bar closes and lives from 2 to 8 bars after the W_high bar; if price already
        reached the 38.2% level before then, the leg is skipped (the "falling knife" / missed entry). Impulse volume =
        any bullish bar from the W_low bar to the W_high bar with volume ≥ 1.35× MedVol. Break-even trigger = price
        back at W_high (R multiple computed per trade). Deep-close abort = a 15m mid close below the 61.8% level.
  sbs   internal swing = 3-bar fractal (Low_k < Low_k-1 and Low_k ≤ Low_k+1) confirmed before the sweep bar, within
        the last 24 bars, above the 20-bar 4h low + 1.5 ATR; most recent such. Sweep bar inside a killzone (03:00–05:45,
        08:15–10:15 NY). Displacement = the first of the next 2 bars that qualifies. Target = 2R, or the 24-bar 15m high
        (through the displacement bar) when that is more than 2R away, capped at 2.5R.
Controls: coin-flip on every rule (same fill minute, random side, same stop distance and R-based exits). Gemini's:
  bos   the same impulse legs entered with a limit at the deep 70.5% retracement (middle of 62–79%), live 6 bars,
        stop beyond the leg low (same formula), same exits.
  wick  candle-CLOSE anchors instead of wicks, no volume filter, everything else identical.
  sbs   EXTERNAL sweeps: the 20-bar 4h low/high instead of the internal swing, no trend filter.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .breakout_test import trade_row
from .gemini_test import MIN, Exits, at, last_closed, manage, prep
from .simple_rules import NY, PIP, ema, load, pip_stats, stats, wilder
from .usd_calendar import events

IN_SAMPLE_FROM = pd.Timestamp("2025-10-08", tz=NY)       # first trade of the one-year table Gemini read
RULES = ("bos", "wick", "sbs")
TITLE = {"bos": "#1 G-BOS-iFVG-15M", "wick": "#2 G-DTFX-Wick-15M", "sbs": "#3 G-SBS-Sweep-15M"}
FUNNEL: dict[str, dict[str, int]] = {}
CONTROL = {"bos": "deep 70.5% control", "wick": "close-anchor control", "sbs": "external-sweep control"}


def count(rule: str, stage: str) -> None:
    f = FUNNEL.setdefault(rule, {})
    f[stage] = f.get(stage, 0) + 1


# ── 15m bars ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def build(m1: pd.DataFrame, a: dict) -> dict:
    bid = a["ns"] // (15 * MIN)
    starts = np.r_[0, np.nonzero(np.diff(bid))[0] + 1]
    ends = np.r_[starts[1:], len(bid)]
    b = {"j0": starts, "j1": ends, "start": bid[starts] * 15 * MIN}
    b["o"] = a["m_o"][starts]
    b["c"] = a["m_c"][ends - 1]
    b["h"] = np.maximum.reduceat(a["m_h"], starts)
    b["l"] = np.minimum.reduceat(a["m_l"], starts)
    b["vol"] = np.add.reduceat(a["vol"], starts)
    loc = pd.DatetimeIndex(b["start"]).tz_localize("UTC").tz_convert(NY)
    b["mod"] = (loc.hour * 60 + loc.minute).to_numpy()
    b["day"] = loc.tz_localize(None).normalize().to_numpy()
    b["dow"] = loc.dayofweek.to_numpy()
    b["end"] = b["start"] + 15 * MIN
    tr = np.maximum.reduce([b["h"] - b["l"], np.abs(b["h"] - np.r_[np.nan, b["c"][:-1]]),
                            np.abs(b["l"] - np.r_[np.nan, b["c"][:-1]])])
    tr[0] = b["h"][0] - b["l"][0]
    b["atr"] = wilder(pd.Series(tr), 14).to_numpy()
    v = pd.Series(b["vol"])
    b["medvol"] = v.groupby(b["mod"]).transform(lambda x: x.shift(1).rolling(20, min_periods=20).median()).to_numpy()
    h4h = m1["m_h"].tz_convert(NY).resample("4h", offset="1h", label="right", closed="left").max().dropna()
    h4l = m1["m_l"].tz_convert(NY).resample("4h", offset="1h", label="right", closed="left").min().dropna()
    b["h4_end"] = h4h.index.tz_convert("UTC").as_unit("ns").asi8
    b["hh4"] = h4h.rolling(20).max().to_numpy()
    b["ll4"] = h4l.rolling(20).min().to_numpy()
    n = len(starts)
    b["ema1h"] = np.array([last_closed(a["h1_end"], a["ema1h"], t) for t in b["end"]])
    i1 = np.searchsorted(a["h1_end"], b["end"], side="right") - 1
    b["ema1h_4ago"] = np.where(i1 >= 4, a["ema1h"][np.maximum(i1 - 4, 0)], np.nan)
    b["ema4h"] = np.array([last_closed(a["h4_end"], a["ema4h"], t) for t in b["end"]])
    i4 = np.searchsorted(b["h4_end"], b["end"], side="right") - 1
    b["hh4_now"] = np.where(i4 >= 0, b["hh4"][np.maximum(i4, 0)], np.nan)
    b["ll4_now"] = np.where(i4 >= 0, b["ll4"][np.maximum(i4, 0)], np.nan)
    b["n"] = n
    return b


def mirrored(b: dict, side: int) -> dict:
    """Price view for the detector: side 1 as is, side −1 negated (high ↔ −low) so one long-only detector serves both."""
    if side > 0:
        return b
    m = dict(b)
    m["o"], m["c"], m["h"], m["l"] = -b["o"], -b["c"], -b["l"], -b["h"]
    m["ema1h"], m["ema1h_4ago"], m["ema4h"] = -b["ema1h"], -b["ema1h_4ago"], -b["ema4h"]
    m["hh4_now"], m["ll4_now"] = -b["ll4_now"], -b["hh4_now"]
    return m


def swings5(h: np.ndarray, k: int) -> bool:
    return h[k] > h[k - 1] and h[k] > h[k - 2] and h[k] >= h[k + 1] and h[k] >= h[k + 2]


# ── orders ────────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Order:
    rule: str
    side: int
    kind: str                 # "stop" | "limit"
    level: float              # real price
    j0: int                   # live from this minute index …
    j1: int                   # … to (excl.)
    stop_anchor: float | None  # real price the stop must clear (None: no structural anchor)
    stop_fixed: float          # minimum stop distance in points from structure (e.g. 0.30 × WickRange)
    atr: float
    k_atr: float
    pct: float
    exits: callable           # (entry, risk) → Exits
    session: str
    tag: str = ""


def block_mask(a: dict, before: int, after: int) -> np.ndarray:
    """True on minutes from `before` min ahead of a release to `after` min after it (NY times from the calendar)."""
    mask = np.zeros(len(a["ns"]), bool)
    for d, evs in events().items():
        for m, _ in evs:
            t = (pd.Timestamp(d) + pd.Timedelta(minutes=m)).tz_localize(NY).value
            i0, i1 = np.searchsorted(a["ns"], [t - before * MIN, t + after * MIN])
            mask[i0:i1] = True
    return mask


def fill(a, o: Order, j0: int, blocked: np.ndarray):
    for k in range(j0, min(o.j1, len(a["ns"]))):
        if blocked[k]:
            return None                                   # pending order cancelled around the release
        if o.kind == "stop":
            if o.side > 0 and a["ask_h"][k] >= o.level:
                return k, max(o.level, a["ask_o"][k])
            if o.side < 0 and a["bid_l"][k] <= o.level:
                return k, min(o.level, a["bid_o"][k])
        else:
            if o.side > 0 and a["ask_l"][k] <= o.level:
                return k, min(o.level, a["ask_o"][k])
            if o.side < 0 and a["bid_h"][k] >= o.level:
                return k, max(o.level, a["bid_o"][k])
    return None


def execute(a: dict, orders: list[Order], rng, blocked: np.ndarray, per_day: int = 2, per_session: int = 1):
    trades, ctl = [], []
    busy = -1
    n_day: dict = {}
    n_ses: dict = {}
    for o in sorted(orders, key=lambda x: x.j0):
        j0 = max(o.j0, busy + 1)
        if j0 >= o.j1:
            continue
        f = fill(a, o, j0, blocked)
        if not f:
            continue
        j, px = f
        loc = a["idx"][j].tz_convert(NY)
        day = loc.date()
        ses = o.session if o.session else ("london" if loc.hour < 8 else "ny")
        if n_day.get(day, 0) >= per_day or n_ses.get((day, ses), 0) >= per_session:
            continue
        dist = max(o.side * (px - o.stop_anchor) if o.stop_anchor is not None else 0.0, o.stop_fixed,
                   o.k_atr * o.atr, o.pct * px)
        stop = px - o.side * dist
        risk = dist
        d = a["days"].get(int((pd.Timestamp(loc).tz_localize(None).normalize().value) // (1440 * MIN)))
        if d is None:
            continue
        j_flat = at(a, d[0], d[1], 950)
        if j >= j_flat:
            continue
        ex = o.exits(px, risk)
        jx, ex_px, why = manage(a, j, o.side, px, stop, ex, j_flat)
        spread = a["ask_o"][j] - a["bid_o"][j]
        trades.append(trade_row(a, j, jx, o.side, px, ex_px, risk, spread, why, tag=o.tag))
        n_day[day] = n_day.get(day, 0) + 1
        n_ses[(day, ses)] = n_ses.get((day, ses), 0) + 1
        busy = jx
        # coin-flip control: same minute, random side, same stop distance, R-based exits (no price-level abort)
        cs = int(rng.choice([1, -1]))
        if j + 1 < j_flat:
            ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
            cex = Exits(**{**ex.__dict__, "abort": None, "checks": []})
            cjx, cpx, cwhy = manage(a, j + 1, cs, ce, ce - cs * risk, cex, j_flat)
            ctl.append(trade_row(a, j, cjx, cs, ce, cpx, risk, spread, cwhy))
    return trades, ctl


def minute_span(b: dict, t0: int, t1: int) -> tuple[int, int]:
    """Minute indices covering 15m bars t0 … t1-1."""
    t1 = min(t1, b["n"])
    if t0 >= t1:
        return 0, 0
    return int(b["j0"][t0]), int(b["j1"][t1 - 1])


# ── #1 BOS + FVG/iFVG shallow retest ──────────────────────────────────────────────────────────────────────────────────
BOS_EXITS = dict(target_r=2.2, trail_mode="close", trail_trig=1.2, trail_k=1.5, be=(1.2, 0.15), time_after_min=180,
                 time_min_r=0.40)


def detect_bos(b: dict, side: int, deep: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    rule = "bos"
    out = []
    for t in range(30, b["n"] - 1):
        if b["dow"][t] >= 5 or not (180 <= b["mod"][t] and b["mod"][t] + 15 <= 780):
            continue
        atr, e1, e1o = b["atr"][t], m["ema1h"][t], m["ema1h_4ago"][t]
        if not (np.isfinite(atr) and np.isfinite(e1) and np.isfinite(e1o) and np.isfinite(b["medvol"][t])):
            continue
        sh = None
        for k in range(t - 4, max(t - 100, 2), -1):        # most recent unbroken confirmed 5-bar swing high, ≥4 bars old
            if swings5(h, k) and c[k + 1:t].max(initial=-np.inf) <= h[k]:
                sh = h[k]
                break
        if sh is None:
            continue
        if not (c[t] > sh + 0.15 * atr):
            continue
        if not (c[t] > e1 and e1 > e1o):
            continue
        if not deep:
            count(rule, "break of an unbroken swing + 1h trend")
        lo_imp, hi_imp = min(l[t], l[t - 1], l[t - 2]), h[t]
        leg = hi_imp - lo_imp
        if not (leg >= 1.40 * atr and b["vol"][t] >= 1.30 * b["medvol"][t]):
            continue
        if not deep:
            count(rule, "leg ≥ 1.4 ATR and volume ≥ 1.3×")
        fvg = l[t] > h[t - 2]
        ifvg = any(h[mm] < l[mm - 2] and c[t] > l[mm - 2] for mm in range(max(t - 20, 2), t))
        if not (fvg or ifvg):
            continue
        if not deep:
            count(rule, "FVG or iFVG")
        if deep:                                         # Gemini's control: the same leg at the deep 70.5% level
            lvl = hi_imp - 0.705 * leg
            j0, j1 = minute_span(b, t + 1, t + 7)
            out.append(Order(rule, side, "limit", side * lvl, j0, j1, side * (lo_imp - 0.25 * atr), 0.0, atr, 1.15,
                             0.0028, lambda e, r: Exits(**BOS_EXITS), ""))
            continue
        z_top, z_bot = max(sh, hi_imp - 0.382 * leg), hi_imp - 0.500 * leg
        cancel = hi_imp - 0.618 * leg
        for r in range(t + 1, min(t + 7, b["n"] - 1)):
            if c[r] < cancel:
                break
            if l[r] <= z_top and c[r] > o[r] and c[r] >= z_bot:
                count(rule, "shallow retest confirmed")
                j0, j1 = minute_span(b, r + 1, r + 3)
                atr_r = b["atr"][r]
                out.append(Order(rule, side, "stop", side * (h[r] + 0.30), j0, j1, side * (l[r] - 0.25 * atr_r), 0.0,
                                 atr_r, 1.15, 0.0028, lambda e, rk: Exits(**BOS_EXITS), ""))
                break
    return out


# ── #2 DTFX wick-fib shallow pullback ─────────────────────────────────────────────────────────────────────────────────
def detect_wick(b: dict, side: int, closes: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    hi_a, lo_a = (c, c) if closes else (h, l)            # control: candle-close anchors
    rule = "wick"
    out = []
    last_sh = last_sl = None                              # (index) of the latest confirmed 5-bar swing high / low
    for t in range(4, b["n"] - 13):
        k = t - 2                                         # a swing at k is confirmed once bar t (= k+2) has closed
        if swings5(h, k):
            last_sh = k
        if swings5(-l, k):
            last_sl = k
        if last_sh is None or last_sl is None:
            continue
        if b["dow"][t] >= 5 or not (180 <= b["mod"][t] and b["mod"][t] + 15 <= 750):
            continue
        sh = h[last_sh]
        if not (c[t] > sh and c[t - 1] <= sh and c[t] > m["ema4h"][t]):
            continue
        if not closes:
            count(rule, "structure shift above the 4h EMA")
        u = next((x for x in range(t + 1, t + 13) if c[x] < c[x - 1]), None)
        if u is None:
            continue
        seg_lo = range(last_sl, t + 1)
        i_low = min(seg_lo, key=lambda x: lo_a[x])
        w_low = lo_a[i_low]
        i_high = max(range(t, u + 1), key=lambda x: hi_a[x])
        w_high = hi_a[i_high]
        wr = w_high - w_low
        atr = b["atr"][u]
        if not (np.isfinite(atr) and 1.60 * atr <= wr <= 3.50 * atr):
            continue
        if not closes:
            count(rule, "wick range 1.6–3.5 ATR")
            mv = b["medvol"]
            if not any(c[x] > o[x] and np.isfinite(mv[x]) and b["vol"][x] >= 1.35 * mv[x] for x in range(i_low, i_high + 1)):
                continue
            count(rule, "impulse volume ≥ 1.35×")
        lvl = w_high - 0.382 * wr
        if any(l[x] <= lvl for x in range(i_high + 1, u + 1)):
            continue                                       # reached 38.2% before the order could be live
        if not closes:
            count(rule, "pullback not yet at 38.2%")
        first = max(u + 1, i_high + 2)
        j0, j1 = minute_span(b, first, i_high + 9)
        if j1 <= j0:
            continue
        be_lvl, abort = w_high, w_high - 0.618 * wr

        def ex(e, r, be_lvl=be_lvl, abort=abort):
            return Exits(target_r=2.0, be=(max(side * (side * be_lvl - e), 0.0) / r, 0.20), time_after_min=150,
                         time_min_r=0.30, abort=side * abort)
        out.append(Order(rule, side, "limit", side * lvl, j0, j1, None, 0.30 * wr, atr, 1.15, 0.0028, ex, "x"))
    return out


# ── #3 internal sweep + displacement ──────────────────────────────────────────────────────────────────────────────────
KZ = ((180, 345, "kz1"), (495, 615, "kz2"))


def detect_sbs(b: dict, side: int, external: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    rule = "sbs"
    out = []
    for t in range(30, b["n"] - 3):
        if b["dow"][t] >= 5:
            continue
        kz = next((z for s0, s1, z in KZ if s0 <= b["mod"][t] and b["mod"][t] + 15 <= s1), None)
        if kz is None:
            continue
        atr, ll4 = b["atr"][t], m["ll4_now"][t]
        if not (np.isfinite(atr) and np.isfinite(ll4)):
            continue
        if external:
            lvl_sw = ll4
        else:
            if not c[t] > m["ema4h"][t]:
                continue
            lvl_sw = None
            for k in range(t - 2, max(t - 25, 1), -1):       # 3-bar fractal low confirmed by bar k+1 ≤ t-1
                if l[k] < l[k - 1] and l[k] <= l[k + 1]:
                    if l[k] > ll4 + 1.50 * atr:
                        lvl_sw = l[k]
                    break
            if lvl_sw is None:
                continue
            count(rule, "internal swing low in the 4h uptrend")
        if not (lvl_sw - 0.85 * atr <= l[t] <= lvl_sw - 0.10 * atr and (c[t] > lvl_sw or c[t + 1] > lvl_sw)):
            continue
        if not external:
            count(rule, "sweep 0.10–0.85 ATR and close back")
        d = None
        for x in (t + 1, t + 2):
            mv = b["medvol"][x]
            if (c[x] > o[x] and c[x] > max(h[x - 3:x]) and l[x] > h[x - 2] and np.isfinite(mv)
                    and b["vol"][x] >= 1.25 * mv):
                d = x
                break
        if d is None:
            continue
        if not external:
            count(rule, "displacement + FVG + volume")
        lvl = l[d]
        hh24 = h[max(d - 23, 0):d + 1].max()
        j0, j1 = minute_span(b, d + 1, d + 5)

        def ex(e, r, hh24=hh24):
            need = (hh24 - side * e) / r
            tgt = min(need, 2.5) if need > 2.0 else 2.0
            return Exits(target_r=tgt, be=(1.0, 0.10), trail_mode="close", trail_trig=1.5, trail_k=1.5,
                         time_after_min=150, time_min_r=0.25)
        out.append(Order(rule, side, "limit", side * lvl, j0, j1, side * (l[t] - 0.20 * atr), 0.0, atr, 1.10, 0.0028,
                         ex, kz))
    return out


# ── run + report ──────────────────────────────────────────────────────────────────────────────────────────────────────
def run_set(path: Path, want: list[str], rng) -> dict[str, dict[str, list]]:
    m1 = load(path)
    a = prep(m1)
    b = build(m1, a)
    del m1
    blk15, blk10 = block_mask(a, 15, 15), block_mask(a, 10, 0)
    out = {}
    if "bos" in want:
        tr, ctl = execute(a, detect_bos(b, 1) + detect_bos(b, -1), rng, blk15)
        dp, _ = execute(a, detect_bos(b, 1, deep=True) + detect_bos(b, -1, deep=True), rng, blk15)
        out["bos"] = {"rule": tr, "coin-flip control": ctl, "deep 70.5% control": dp}
    if "wick" in want:
        tr, ctl = execute(a, detect_wick(b, 1) + detect_wick(b, -1), rng, blk10, per_session=2)
        cl, _ = execute(a, detect_wick(b, 1, closes=True) + detect_wick(b, -1, closes=True), rng, blk10, per_session=2)
        out["wick"] = {"rule": tr, "coin-flip control": ctl, "close-anchor control": cl}
    if "sbs" in want:
        tr, ctl = execute(a, detect_sbs(b, 1) + detect_sbs(b, -1), rng, blk15)
        xt, _ = execute(a, detect_sbs(b, 1, external=True) + detect_sbs(b, -1, external=True), rng, blk15)
        out["sbs"] = {"rule": tr, "coin-flip control": ctl, "external-sweep control": xt}
    days = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(b["day"]))))
    out["_days"] = days[days.dayofweek < 5].tz_localize(NY)
    return out


def segment(t: pd.DataFrame, holdout: bool) -> pd.Series:
    if holdout:
        return pd.Series("holdout 2021–Sep 2024 (clean)", index=t.index)
    et = pd.to_datetime(t.entry_time).dt.tz_convert(NY)
    return pd.Series(np.where(et < IN_SAMPLE_FROM, "dev Oct 2024–Oct 2025 (clean)", "Oct 2025–Sep 2026 (in-sample)"),
                     index=t.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dev_m1,holdout_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", default=",".join(RULES))
    ap.add_argument("--seed", type=int, default=23)
    a_ = ap.parse_args()
    want = [r for r in a_.only.split(",") if r in RULES]
    rng = np.random.default_rng(a_.seed)
    a_.out.mkdir(parents=True, exist_ok=True)
    frames, day_sets = [], {}
    for ds in a_.data.split(","):
        res = run_set(Path("data/export") / ds / "XAUUSD_M1.csv.gz", want, rng)
        hold = ds.startswith("holdout")
        days = res.pop("_days")
        if hold:
            day_sets["holdout 2021–Sep 2024 (clean)"] = days
        else:
            day_sets["dev Oct 2024–Oct 2025 (clean)"] = days[days < IN_SAMPLE_FROM]
            day_sets["Oct 2025–Sep 2026 (in-sample)"] = days[days >= IN_SAMPLE_FROM]
        for rule, sets in res.items():
            for lab, t in sets.items():
                T = pd.DataFrame(t)
                if len(T):
                    frames.append(T.assign(strategy=rule, test=lab, segment=segment(T, hold).values))
        print(f"  {ds}: done", flush=True)
    T = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(T):
        T.to_csv(a_.out / "trades.csv.gz", index=False)
    clean_keys = [k for k in day_sets if "clean" in k]
    clean_days = pd.DatetimeIndex(sorted(set().union(*[set(day_sets[k]) for k in clean_keys]))) if clean_keys else None
    md = [f"# Gemini's rebuilt SMC/ICT/DTFX gold setups — out-of-sample design ({a_.data})", "",
          "Rules exactly as Gemini specified (2026-10-17); open points fixed in fxagents/gemini_smc.py before any run. "
          "Gemini built them from our one-year setup table (trades 2025-10-08 → 2026-10-08), so that year is **in-sample: "
          "shown, not judged**. Judged = clean data only: Oct 2024–Oct 2025 + 2021–Sep 2024. Pass = on the clean data "
          "together ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs; avg R > 0 in each clean "
          "piece; and better than both controls. Real OANDA bid/ask fills; R includes the spread.", ""]
    rows = []
    for rule in want:
        segs = [("clean, combined", clean_keys)] + [(k, [k]) for k in clean_keys] + \
               [(k, [k]) for k in day_sets if "in-sample" in k]
        tests = ["rule", "coin-flip control", CONTROL[rule]]
        res = {}
        for lab in tests:
            for sname, keys in segs:
                X = T[(T.strategy == rule) & (T.test == lab) & (T.segment.isin(keys))] if len(T) else pd.DataFrame()
                dd = clean_days if sname == "clean, combined" else day_sets[keys[0]]
                st = stats(X, dd) if len(X) else {"trades": 0}
                if len(X):
                    st |= pip_stats(X, PIP["XAUUSD"])
                    for sd, nm in ((1, "long"), (-1, "short")):
                        x = X[X.side == sd]
                        st[nm] = f"{x.R.mean():+.3f} ({len(x)})" if len(x) else "— (0)"
                res[(lab, sname)] = st
                rows.append({"strategy": rule, "test": lab, "segment": sname, **st})
        cc = res[("rule", "clean, combined")]
        pieces_ok = all(res[("rule", k)].get("avg_R", -1) > 0 for k in clean_keys)
        beats = all(cc.get("avg_R", -9) > res[(lab, "clean, combined")].get("avg_R", -9) for lab in tests[1:])
        ok = bool(cc.get("pass")) and pieces_ok and beats
        md += [f"## {TITLE[rule]} — **{'PASS' if ok else 'no pass'}**", "",
               f"Clean combined: {cc.get('trades', 0)} trades" +
               (f", avg {cc['avg_R']:+.3f}R (95% {cc['ci_lo']:+.2f} to {cc['ci_hi']:+.2f}), 2× costs {cc['avg_R_2x']:+.3f}R; "
                f"each clean piece positive: {'yes' if pieces_ok else 'no'}; beats both controls: {'yes' if beats else 'no'}."
                if cc.get("trades") else "."), "",
               "| Test | Data | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Long avg R (n) | Short avg R (n) | Median hold |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for lab in tests:
            for sname, _ in segs:
                r = res[(lab, sname)]
                nm = f"**{lab}**" if lab == "rule" else lab
                if not r.get("trades"):
                    md.append(f"| {nm} | {sname} | 0 |" + " |" * 8)
                    continue
                md.append(f"| {nm} | {sname} | {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | {r['ci_lo']:+.2f} to "
                          f"{r['ci_hi']:+.2f} | {r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['long']} | {r['short']} | "
                          f"{r['hold_min_median']:.0f} min |")
        f = FUNNEL.get(rule, {})
        if f:
            md += ["", "Setups reaching each stage (all data, longs + shorts, before fills and daily caps): " +
                   " → ".join(f"{k} {v:,}" for k, v in f.items()), ""]
        md.append("")
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
