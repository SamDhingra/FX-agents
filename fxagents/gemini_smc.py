"""Gemini's rebuilt SMC / ICT / DTFX gold setups — REVISION 2 (Gemini's "post-diagnostic revision", Sam 2026-10-17).
The first rebuild (stacked filters) was replaced before it was ever run, so the holdout is used once, for these.

    python -m fxagents.gemini_smc --data dev_m1,holdout_m1 --out data/year_test/gemini_smc

  bos   #1 G-BOS-Retest-15M    15m close through the last unbroken 3-bar fractal swing, 3-bar leg ≥ 1 ATR;
                               limit at the 25% retracement of the leg for 4 bars
  wick  #2 G-DTFX-Wick-5M      5m wick-to-wick impulse after a close through the last 5-bar fractal swing;
                               limit at the 50% wick midpoint for 6 bars
  sbs   #3 G-SBS-Sweep-15M     15m sweep of the last unbroken 3-bar fractal swing (3–24 bars old) that closes back
                               inside; stop entry beyond the sweep bar for 3 bars

OUT-OF-SAMPLE DESIGN (Sam chose it, 2026-10-17). Gemini built these rules from our one-year setup table, whose
trades run 2025-10-08 → 2026-10-08 — inside dev_m1. That year is IN-SAMPLE: reported, never judged.
Judged ("clean") data: dev_m1 before 2025-10-08 (Oct 2024 – Oct 2025) and the whole holdout_m1 (2021 – Sep 2024).
Pass = on the clean data combined: ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs;
AND avg R > 0 in each clean piece on its own; AND better than both controls on the clean data.

Shared conventions (engine of fxagents/gemini_test.py): clock bars on mid prices; fills on real bid/ask (stop orders at
the level or a gap-through open; limit orders at the level or a better open — a limit already marketable when it goes
live fills at that minute's open); stops/targets on the exit side; R = actual fill to initial stop; flat 15:50 NY;
one open position at a time. Every rule: cancel at the fill minute if the spread > 0.80, and no fills from 15 min
before to 15 min after an FOMC/CPI/NFP/PPI release (fxagents/usd_calendar.py). Max 2 fills a day, 1 per half
(#1/#3: 02:00–07:30 / 07:30–13:00 NY; #2: 03:00–07:30 / 07:30–12:00 NY, by fill time). ATR(14) = Wilder on that
timeframe's mid bars; MedVol(20) = median volume of the same clock slot over the previous 20 days that have it; EMA(50)
on 1h clock-hour closes, read from the last closed hour. Shorts are the exact mirror: the detectors run on the negated
price series (high ↔ −low), so both sides use identical code.

Rules (Gemini's numbers), with the points the spec left open fixed here before testing:
  bos   3-bar fractal high: High_k > High_k-1 and High_k ≥ High_k+1; "unbroken" = no 15m close above it since; the most
        recent such with t−k ≥ 3. Base: Close_0 > that swing, and the 3-bar leg (max high − min low of B-2..B0) ≥ 1.00
        ATR read at B-1. Conditions: Close_0 > EMA(50)1h; (Close−Open) ≥ 0.35·range and volume ≥ 0.85·MedVol. Limit
        at H_imp − 0.25·leg, bars B1–B4. Stop distance max(0.60·leg, 1.15·ATR(B-1), 0.25% of fill). Exits: target 2R;
        at +1.2R stop to +0.15R and trail 15m closes by 1.5 ATR; 12-bar (180 min) time stop if < +0.25R.
        Control (Gemini's): the same signal bars with the limit at the deep 75% retracement, same stop and exits.
  wick  5m bars. 5-bar fractal swings (confirmed 2 bars later); the breakout bar is the first 5m close above the most
        recent unbroken swing high at least 4 bars old. B0 = the first later bar closing below the previous close
        (looked for within 12 bars). W_low = lowest wick from the last confirmed swing low before the breakout to the
        breakout bar; W_high = highest wick up to B0. Base: WickRange ≥ 1.80 ATR(5m) at B0, B0 closing 03:00–12:00.
        Conditions: Close_0 > EMA(50)1h; some bar from the W_low bar to the W_high bar has volume ≥ its slot's MedVol.
        Limit at the 50% midpoint, bars B1–B6, cancelled if price trades past W_high first. Stop distance
        max(0.55·WickRange, 2.00·ATR(5m), 0.20% of fill). Exits: target 1.8R; at +1R stop to +0.15R; 90-min time stop
        if < +0.20R. Control (Gemini's): close-to-close anchors AND the volume condition inverted (no bar ≥ MedVol).
  sbs   3-bar fractal low (Low_k < Low_k-1, Low_k ≤ Low_k+1), unbroken (no 15m close below it since), most recent with
        3 ≤ t−k ≤ 24. Base: Low_0 < it, Close_0 > it, bar range ≥ 0.70 ATR(B0), B0 closing 02:00–13:00. Conditions:
        Close_0 > EMA(50)1h and Low_0 > the 20-bar low of COMPLETED 1h bars; Close_0 ≥ bar midpoint and volume ≥ 0.85
        MedVol. Buy stop High_0 + 0.30 for bars B1–B3, cancelled if price trades below Low_0 first. Stop distance
        max(range_0 + 0.50, 1.15·ATR(B0), 0.25% of fill). Target = entry + min(2.5D, max(2D, HH24 − entry)), HH24 =
        highest high of the 24 bars before B0. At +1R stop to +0.15R; trail 15m closes by 1.5 ATR after +1.5R;
        150-min time stop if < +0.25R. Control (Gemini's): the trend half of condition 1 inverted (Close_0 < EMA for
        longs); everything else, including the 1h-low check, unchanged.
Every rule also has a coin-flip control (same fill minute, random side, same stop distance and R-based exits).
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
from .simple_rules import NY, PIP, load, pip_stats, stats, wilder
from .usd_calendar import events

IN_SAMPLE_FROM = pd.Timestamp("2025-10-08", tz=NY)       # first trade of the one-year table Gemini read
RULES = ("bos", "wick", "sbs")
TITLE = {"bos": "#1 G-BOS-Retest-15M", "wick": "#2 G-DTFX-Wick-5M", "sbs": "#3 G-SBS-Sweep-15M"}
CONTROL = {"bos": "deep 75% control", "wick": "close-anchor + low-volume control", "sbs": "counter-trend control"}
HALVES = {"bos": 450, "wick": 450, "sbs": 450}            # NY minute splitting the two half-day sessions (07:30)
FUNNEL: dict[str, dict[str, int]] = {}


def count(rule: str, stage: str) -> None:
    f = FUNNEL.setdefault(rule, {})
    f[stage] = f.get(stage, 0) + 1


# ── bars ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def build(m1: pd.DataFrame, a: dict, tf: int = 15) -> dict:
    """Clock bars of `tf` minutes on mid prices, with ATR(14), slot MedVol(20), EMA(50) 1h and the 20-bar 1h range."""
    bid = a["ns"] // (tf * MIN)
    starts = np.r_[0, np.nonzero(np.diff(bid))[0] + 1]
    ends = np.r_[starts[1:], len(bid)]
    b = {"tf": tf, "j0": starts, "j1": ends, "start": bid[starts] * tf * MIN}
    b["o"] = a["m_o"][starts]
    b["c"] = a["m_c"][ends - 1]
    b["h"] = np.maximum.reduceat(a["m_h"], starts)
    b["l"] = np.minimum.reduceat(a["m_l"], starts)
    b["vol"] = np.add.reduceat(a["vol"], starts)
    loc = pd.DatetimeIndex(b["start"]).tz_localize("UTC").tz_convert(NY)
    b["mod"] = (loc.hour * 60 + loc.minute).to_numpy()
    b["day"] = loc.tz_localize(None).normalize().to_numpy()
    b["dow"] = loc.dayofweek.to_numpy()
    b["end"] = b["start"] + tf * MIN
    pc = np.r_[np.nan, b["c"][:-1]]
    tr = np.nanmax(np.vstack([b["h"] - b["l"], np.abs(b["h"] - pc), np.abs(b["l"] - pc)]), axis=0)
    b["atr"] = wilder(pd.Series(tr), 14).to_numpy()
    v = pd.Series(b["vol"])
    b["medvol"] = v.groupby(b["mod"]).transform(lambda x: x.shift(1).rolling(20, min_periods=20).median()).to_numpy()
    b["ema1h"] = np.array([last_closed(a["h1_end"], a["ema1h"], t) for t in b["end"]])
    h1h = m1["m_h"].resample("1h", label="right", closed="left").max().dropna()
    h1l = m1["m_l"].resample("1h", label="right", closed="left").min().dropna()
    ends1 = h1h.index.as_unit("ns").asi8
    i1 = np.searchsorted(ends1, b["end"], side="right") - 1                 # last COMPLETED hour at the bar's close
    hh, ll = h1h.rolling(20).max().to_numpy(), h1l.rolling(20).min().to_numpy()
    b["hh1h"] = np.where(i1 >= 0, hh[np.maximum(i1, 0)], np.nan)
    b["ll1h"] = np.where(i1 >= 0, ll[np.maximum(i1, 0)], np.nan)
    b["n"] = len(starts)
    return b


def mirrored(b: dict, side: int) -> dict:
    """Price view for the detector: side 1 as is, side −1 negated (high ↔ −low) so one long-only detector serves both."""
    if side > 0:
        return b
    m = dict(b)
    m["o"], m["c"], m["h"], m["l"] = -b["o"], -b["c"], -b["l"], -b["h"]
    m["ema1h"] = -b["ema1h"]
    m["hh1h"], m["ll1h"] = -b["ll1h"], -b["hh1h"]
    return m


def frac3_high(h, k) -> bool:
    return h[k] > h[k - 1] and h[k] >= h[k + 1]


def frac5_high(h, k) -> bool:
    return h[k] > h[k - 1] and h[k] > h[k - 2] and h[k] >= h[k + 1] and h[k] >= h[k + 2]


def in_window(b, t, lo, hi) -> bool:
    """Bar t is a weekday bar that starts at/after `lo` and closes by `hi` (NY minutes)."""
    return b["dow"][t] < 5 and b["mod"][t] >= lo and b["mod"][t] + b["tf"] <= hi


# ── orders ────────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Order:
    rule: str
    side: int
    kind: str                  # "stop" | "limit"
    level: float               # real price
    j0: int                    # live from this minute index …
    j1: int                    # … to (excl.)
    stop_fixed: float          # structural minimum stop distance (points)
    atr: float
    k_atr: float
    pct: float
    exits: callable            # (entry, risk) → Exits
    cancel_hi: float | None = None    # cancel if a mid high reaches this before the fill
    cancel_lo: float | None = None    # cancel if a mid low reaches this before the fill
    main: bool = True          # counts toward the funnel (False for Gemini's control variants)


def real_cancel(side: int, level_mirrored: float, beyond: bool) -> dict:
    """A cancel level from mirrored space: `beyond` = price going further in the trade's direction (above for a long)."""
    real = side * level_mirrored
    if (side > 0) == beyond:
        return {"cancel_hi": real}
    return {"cancel_lo": real}


def block_mask(a: dict, before: int, after: int) -> np.ndarray:
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
            hit = a["ask_h"][k] >= o.level if o.side > 0 else a["bid_l"][k] <= o.level
        else:
            hit = a["ask_l"][k] <= o.level if o.side > 0 else a["bid_h"][k] >= o.level
        dead = (o.cancel_hi is not None and a["m_h"][k] >= o.cancel_hi) or \
               (o.cancel_lo is not None and a["m_l"][k] <= o.cancel_lo)
        if dead and not hit:
            return None
        if dead and hit:                                  # both in one minute: the cancel counts (conservative)
            return None
        if hit:
            if a["ask_o"][k] - a["bid_o"][k] > 0.80:
                return None
            if o.kind == "stop":
                return k, (max(o.level, a["ask_o"][k]) if o.side > 0 else min(o.level, a["bid_o"][k]))
            return k, (min(o.level, a["ask_o"][k]) if o.side > 0 else max(o.level, a["bid_o"][k]))
    return None


def execute(a: dict, orders: list[Order], rng, blocked: np.ndarray, half: int = 450):
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
        ses = "first" if loc.hour * 60 + loc.minute < half else "second"
        if n_day.get(day, 0) >= 2 or n_ses.get((day, ses), 0) >= 1:
            continue
        dist = max(o.stop_fixed, o.k_atr * o.atr, o.pct * px)
        stop = px - o.side * dist
        d = a["days"].get(int(pd.Timestamp(loc).tz_localize(None).normalize().value // (1440 * MIN)))
        if d is None:
            continue
        j_flat = at(a, d[0], d[1], 950)
        if j >= j_flat:
            continue
        ex = o.exits(px, dist)
        jx, ex_px, why = manage(a, j, o.side, px, stop, ex, j_flat)
        spread = a["ask_o"][j] - a["bid_o"][j]
        trades.append(trade_row(a, j, jx, o.side, px, ex_px, dist, spread, why))
        if o.main:
            count(o.rule, "filled (after caps)")
        n_day[day] = n_day.get(day, 0) + 1
        n_ses[(day, ses)] = n_ses.get((day, ses), 0) + 1
        busy = jx
        cs = int(rng.choice([1, -1]))                     # coin-flip control: same minute, random side
        if j + 1 < j_flat:
            ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
            cex = Exits(**{**ex.__dict__, "abort": None, "checks": []})
            cjx, cpx, cwhy = manage(a, j + 1, cs, ce, ce - cs * dist, cex, j_flat)
            ctl.append(trade_row(a, j, cjx, cs, ce, cpx, dist, spread, cwhy))
    return trades, ctl


def minute_span(b: dict, t0: int, t1: int) -> tuple[int, int]:
    """Minute indices covering bars t0 … t1-1."""
    t1 = min(t1, b["n"])
    if t0 >= t1:
        return 0, 0
    return int(b["j0"][t0]), int(b["j1"][t1 - 1])


# ── #1 BOS shallow limit retest (15m) ─────────────────────────────────────────────────────────────────────────────────
BOS_EXITS = dict(target_r=2.0, trail_mode="close", trail_trig=1.2, trail_k=1.5, be=(1.2, 0.15), time_after_min=180,
                 time_min_r=0.25)


def detect_bos(b: dict, side: int, deep: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    out, main = [], not deep
    for t in range(30, b["n"] - 1):
        if not in_window(b, t, 120, 780):
            continue
        atr = b["atr"][t - 1]
        if not np.isfinite(atr):
            continue
        sh = None
        for k in range(t - 3, max(t - 200, 1), -1):        # most recent unbroken 3-bar fractal high, ≥3 bars old
            if frac3_high(h, k) and c[k + 1:t].max(initial=-np.inf) <= h[k]:
                sh = h[k]
                break
        if sh is None or not c[t] > sh:
            continue
        hi_imp, lo_imp = h[t - 2:t + 1].max(), l[t - 2:t + 1].min()
        leg = hi_imp - lo_imp
        if not leg >= 1.00 * atr:
            continue
        if main:
            count("bos", "base: close through swing, leg ≥ 1 ATR")
        if not (np.isfinite(m["ema1h"][t]) and c[t] > m["ema1h"][t]):
            continue
        if main:
            count("bos", "1h EMA agrees")
        mv = b["medvol"][t]
        if not (c[t] - o[t] >= 0.35 * (h[t] - l[t]) and np.isfinite(mv) and b["vol"][t] >= 0.85 * mv):
            continue
        if main:
            count("bos", "body ≥ 0.35 and volume ≥ 0.85×")
        lvl = hi_imp - (0.75 if deep else 0.25) * leg
        j0, j1 = minute_span(b, t + 1, t + 5)
        out.append(Order("bos", side, "limit", side * lvl, j0, j1, 0.60 * leg, atr, 1.15, 0.0025,
                         lambda e, r: Exits(**BOS_EXITS), main=main))
    return out


# ── #2 DTFX wick-fib (5m) ─────────────────────────────────────────────────────────────────────────────────────────────
def detect_wick(b: dict, side: int, control: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    hi_a, lo_a = (c, c) if control else (h, l)          # control: candle-close anchors
    out, main = [], not control
    unbroken, last_low = [], None                         # confirmed 5-bar fractal highs with no close above since
    for x in range(4, b["n"] - 13):
        k = x - 2
        if frac5_high(h, k) and c[k + 1] <= h[k]:
            unbroken.append(k)
        if frac5_high(-l, k):
            last_low = k
        sh = next((kk for kk in reversed(unbroken) if x - kk >= 4), None)   # most recent unbroken, ≥ 4 bars old
        broke = sh is not None and c[x] > h[sh]
        unbroken = [kk for kk in unbroken if h[kk] >= c[x]]               # this close breaks every high below it
        if not broke:
            continue
        sl = last_low
        if sl is None or sl >= x:
            continue
        t0 = next((y for y in range(x + 1, x + 13) if c[y] < c[y - 1]), None)
        if t0 is None or not in_window(b, t0, 180, 720):
            continue
        i_low = min(range(sl, x + 1), key=lambda y: lo_a[y])
        i_high = max(range(i_low, t0 + 1), key=lambda y: hi_a[y])
        w_low, w_high = lo_a[i_low], hi_a[i_high]
        wr = w_high - w_low
        atr = b["atr"][t0]
        if not (np.isfinite(atr) and wr >= 1.80 * atr):
            continue
        if main:
            count("wick", "base: structure break, wick range ≥ 1.8 ATR(5m)")
        if not (np.isfinite(m["ema1h"][t0]) and c[t0] > m["ema1h"][t0]):
            continue
        if main:
            count("wick", "1h EMA agrees")
        mv = b["medvol"][i_low:i_high + 1]
        ok = np.isfinite(mv) & (b["vol"][i_low:i_high + 1] >= mv)
        if not (ok.any() if main else (np.isfinite(mv).any() and not ok.any())):
            continue
        if main:
            count("wick", "impulse volume ≥ MedVol")
        lvl = w_high - 0.500 * wr
        j0, j1 = minute_span(b, t0 + 1, t0 + 7)

        def ex(e, r):
            return Exits(target_r=1.8, be=(1.0, 0.15), time_after_min=90, time_min_r=0.20)
        out.append(Order("wick", side, "limit", side * lvl, j0, j1, 0.55 * wr, atr, 2.00, 0.0020, ex,
                         main=main, **real_cancel(side, w_high, beyond=True)))
    return out


# ── #3 internal sweep & reclaim (15m) ─────────────────────────────────────────────────────────────────────────────────
def detect_sbs(b: dict, side: int, control: bool = False) -> list[Order]:
    m = mirrored(b, side)
    o, h, l, c = m["o"], m["h"], m["l"], m["c"]
    out, main = [], not control
    for t in range(30, b["n"] - 1):
        if not in_window(b, t, 120, 780):
            continue
        atr = b["atr"][t]
        if not np.isfinite(atr):
            continue
        sw = None
        for k in range(t - 3, max(t - 25, 1), -1):          # most recent unbroken 3-bar fractal low, 3–24 bars old
            if l[k] < l[k - 1] and l[k] <= l[k + 1] and c[k + 1:t].min(initial=np.inf) >= l[k]:
                sw = l[k]
                break
        if sw is None or not (l[t] < sw < c[t] and h[t] - l[t] >= 0.70 * atr):
            continue
        if main:
            count("sbs", "base: sweep and close back, range ≥ 0.7 ATR")
        e1, ll = m["ema1h"][t], m["ll1h"][t]
        if not (np.isfinite(e1) and np.isfinite(ll)):
            continue
        trend = c[t] > e1 if main else c[t] < e1
        if not (trend and l[t] > ll):
            continue
        if main:
            count("sbs", "1h trend + inside the 20-hour range")
        mv = b["medvol"][t]
        if not (c[t] >= 0.5 * (h[t] + l[t]) and np.isfinite(mv) and b["vol"][t] >= 0.85 * mv):
            continue
        if main:
            count("sbs", "close in upper half and volume ≥ 0.85×")
        hh24 = h[max(t - 24, 0):t].max()
        j0, j1 = minute_span(b, t + 1, t + 4)

        def ex(e, r, hh24=hh24):
            tgt = min(2.5, max(2.0, (hh24 - side * e) / r))
            return Exits(target_r=tgt, be=(1.0, 0.15), trail_mode="close", trail_trig=1.5, trail_k=1.5,
                         time_after_min=150, time_min_r=0.25)
        out.append(Order("sbs", side, "stop", side * (h[t] + 0.30), j0, j1, h[t] - l[t] + 0.50, atr, 1.15, 0.0025, ex,
                         main=main, **real_cancel(side, l[t], beyond=False)))
    return out


# ── run ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def run_set(path: Path, want: list[str], rng) -> dict[str, dict[str, list]]:
    m1 = load(path)
    a = prep(m1)
    b15 = build(m1, a, 15)
    b5 = build(m1, a, 5) if "wick" in want else None
    del m1
    blk = block_mask(a, 15, 15)
    out = {}
    if "bos" in want:
        tr, ctl = execute(a, detect_bos(b15, 1) + detect_bos(b15, -1), rng, blk)
        dp, _ = execute(a, detect_bos(b15, 1, deep=True) + detect_bos(b15, -1, deep=True), rng, blk)
        out["bos"] = {"rule": tr, "coin-flip control": ctl, CONTROL["bos"]: dp}
    if "wick" in want:
        tr, ctl = execute(a, detect_wick(b5, 1) + detect_wick(b5, -1), rng, blk)
        cl, _ = execute(a, detect_wick(b5, 1, control=True) + detect_wick(b5, -1, control=True), rng, blk)
        out["wick"] = {"rule": tr, "coin-flip control": ctl, CONTROL["wick"]: cl}
    if "sbs" in want:
        tr, ctl = execute(a, detect_sbs(b15, 1) + detect_sbs(b15, -1), rng, blk)
        xt, _ = execute(a, detect_sbs(b15, 1, control=True) + detect_sbs(b15, -1, control=True), rng, blk)
        out["sbs"] = {"rule": tr, "coin-flip control": ctl, CONTROL["sbs"]: xt}
    days = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(b15["day"]))))
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
    md = [f"# Gemini's rebuilt SMC/ICT/DTFX gold setups (revision 2) — out-of-sample design ({a_.data})", "",
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
            md += ["", "Setups reaching each stage (both data sets, longs + shorts; the last step counts fills after the daily caps): " +
                   " → ".join(f"{k} {v:,}" for k, v in f.items()), ""]
        md.append("")
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
