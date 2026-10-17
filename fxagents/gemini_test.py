"""Three gold strategies proposed by Gemini (Sam, 2026-10-17), coded exactly as specified, frozen before any result.

    python -m fxagents.gemini_test --data dev_m1 --out data/year_test/gemini_dev_m1 [--only lny,xeq,pmrd]

  lny   #2 London-to-NY intraday momentum (gold only)
  xeq   #3 cross-asset US cash open (gold traded; NAS100 and US30 read)
  pmrd  #1 post-macro-release drift (gold; fxagents/usd_calendar.py: FOMC, CPI, NFP, PPI)

Every time is New York local (DST handled per day). Signals use mid candles ((bid+ask)/2) of completed bars; fills use
the real bid/ask: a buy stop fills when the ASK reaches the level (at the minute's open if it gaps through), a sell stop
when the BID does. Stops and time exits fill on the exit side (bid for longs, ask for shorts). R = distance from the
actual fill to the initial stop, so the entry spread and any gap are in R; "2× costs" pays one more spread.

Decisions the spec left open, fixed here before testing (Oct 17 2026):
  • 15m bars are clock bars (:00/:15/:30/:45). ATR(14) is Wilder's on 15m mid bars, read from the last bar CLOSED at
    the moment named. EMA(50) on 1h mid closes (clock hours) and on 4h mid closes (bars 01/05/09/13/17/21 NY, OANDA's
    alignment), read from the last closed bar.
  • 20-day baselines use the previous 20 qualifying trading days only (never the current day); a day without 20
    earlier days is skipped.
  • "Unrealized profit reaches +xR" = the best exit-side price since the fill has reached entry + x·R. The break-even
    move takes effect from the next minute; trailing stops update at each 15m close after that and only tighten.
    Chandelier = highest mid high since entry − k·ATR (lowest low + k·ATR for shorts); "trail behind the 15m close"
    (lny) = that 15m mid close − k·ATR.
  • In a minute that touches both the stop and the target, the stop counts (conservative). A minute that touches
    both the entry level and the cancel level before the fill cancels the order.
  • Time stops and other "exit at market" checks exit at that minute's open on the exit side.
  • Holiday early closes / data gaps > 60 min: out at the last price before the gap. Flat at 15:50 NY.
  • lny: London window needs ≥250 of its 315 minutes (else the day is skipped). Condition 5 reads the 08:15–08:45 mid
    lows (highs for shorts). "Cancel if price first breaches the stop" = mid low ≤ stop (high ≥ stop) before the fill.
  • xeq: the 10:00-release rule never fires — the verified calendar has no 10:00 events (ISM is not in it), so the
    order is always placed at 10:00. NAS volume = summed tick volume of the 09:30–10:00 minutes.
  • pmrd: B0 = the 15m bar containing the release minute; with two release times on one day, the earlier is tried
    first and at most one trade fills. "Second release within 60 minutes" uses the same calendar.
  • Controls: every rule has a coin-flip control (same fill minute, random side, same stop distance and exits).
    Gemini's own controls: lny with the London filter inverted (dead London: efficiency < 0.25 and volume below its
    median; side = sign of London's move; condition 5 kept); xeq with NAS/US30 open returns and volume taken from a
    randomly shuffled other day; pmrd on weekdays with NO calendar event, B0 = the 08:30 and 10:00 bars.

Pass (per rule) = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, and better than its
controls. Holdout data (--frozen) scores only rules in PASSED_DEV, unchanged.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .breakout_test import trade_row
from .simple_rules import NY, PIP, ema, load, pip_stats, stats, wilder
from .usd_calendar import FOMC_DAYS, events

PASSED_DEV: set[str] = set()          # filled in after the dev_m1 run; nothing else is scored on holdout data
MIN = 60_000_000_000                  # ns per minute
RULES = ("lny", "xeq", "pmrd")
FUNNEL: dict[str, list[dict]] = {}    # rule → one {condition: bool} per evaluated day (diagnostics, rule runs only)


def note(rule: str, on: bool, **conds) -> None:
    if on:
        FUNNEL.setdefault(rule, []).append(conds)


# ── data ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def prep(m1: pd.DataFrame) -> dict:
    a = {k: m1[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
                                             "m_o", "m_h", "m_l", "m_c")}
    a["vol"] = m1["volume"].to_numpy(float) if "volume" in m1 else np.ones(len(m1))
    a["idx"], a["ns"] = m1.index, m1.index.as_unit("ns").asi8
    loc = m1.index.tz_convert(NY)
    lns = loc.tz_localize(None).as_unit("ns").asi8
    a["mod"] = ((lns // MIN) % 1440).astype(int)
    day = lns // (1440 * MIN)
    starts = np.r_[0, np.nonzero(np.diff(day))[0] + 1]
    ends = np.r_[starts[1:], len(day)]
    a["days"] = {int(day[s]): (int(s), int(e)) for s, e in zip(starts, ends)}
    a["date"] = {int(day[s]): str(loc[s].date()) for s in starts}
    a["dow"] = {int(day[s]): int(loc[s].dayofweek) for s in starts}
    # 15m clock bars on mid (label = bar end) → ATR(14), and 1h / 4h EMA(50)
    r = m1.resample("15min", label="right", closed="left")
    b = pd.DataFrame({"h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    a["b15_end"], a["atr15"] = b.index.as_unit("ns").asi8, wilder(tr, 14).to_numpy()
    h1 = m1["m_c"].resample("1h", label="right", closed="left").last().dropna()
    a["h1_end"], a["ema1h"] = h1.index.as_unit("ns").asi8, ema(h1, 50).to_numpy()
    h4 = m1["m_c"].tz_convert(NY).resample("4h", offset="1h", label="right", closed="left").last().dropna()
    a["h4_end"], a["ema4h"] = h4.index.tz_convert("UTC").as_unit("ns").asi8, ema(h4, 50).to_numpy()
    return a


def last_closed(ends: np.ndarray, vals: np.ndarray, t_ns: int) -> float:
    """Value of the last bar whose end ≤ t (NaN if none)."""
    i = int(np.searchsorted(ends, t_ns, side="right")) - 1
    return float(vals[i]) if i >= 0 else float("nan")


def at(a: dict, s: int, e: int, minute: int) -> int:
    """First index in [s, e) whose NY minute-of-day ≥ minute (e if none)."""
    return s + int(np.searchsorted(a["mod"][s:e], minute))


def day_ns(a: dict, d: int, minute: int) -> int:
    """UTC ns of NY local `minute` on day d (DST-correct)."""
    return (pd.Timestamp(a["date"][d]) + pd.Timedelta(minutes=minute)).tz_localize(NY).value


# ── execution ─────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Exits:
    target_r: float
    trail_mode: str | None = None          # "chandelier" | "close"
    trail_trig: float = 1.0
    trail_k: float = 1.5
    be: tuple[float, float] | None = None  # (trigger R, lock R)
    time_after_min: int | None = None      # relative time stop (minutes after the fill)
    time_min_r: float = 0.0
    checks: list = field(default_factory=list)   # absolute [(index, min R)]: exit at that minute's open if below


def fill_stop(a, j0: int, j1: int, side: int, level: float, cancel: float | None = None,
              spread_max: float | None = None):
    """Stop entry order live in minutes [j0, j1). → (index, fill price) or None."""
    for k in range(j0, j1):
        if side > 0:
            trig, dead = a["ask_h"][k] >= level, cancel is not None and a["m_l"][k] <= cancel
        else:
            trig, dead = a["bid_l"][k] <= level, cancel is not None and a["m_h"][k] >= cancel
        if dead:
            return None
        if trig:
            if spread_max is not None and a["ask_o"][k] - a["bid_o"][k] > spread_max:
                return None
            return k, (max(level, a["ask_o"][k]) if side > 0 else min(level, a["bid_o"][k]))
    return None


def manage(a, j: int, side: int, entry: float, stop: float, ex: Exits, j_flat: int, first_bar_stop: bool = True):
    """Walk from the fill minute j to the 15:50 flatten j_flat. → (exit index, price, reason)."""
    risk = side * (entry - stop)
    tgt = entry + side * ex.target_r * risk
    best = -np.inf                                         # best exit-side excursion (points)
    ext = -np.inf if side > 0 else np.inf                  # highest mid high (lowest low) since entry
    trail_on, be_done = False, False
    t_stop = None
    if ex.time_after_min is not None:
        t_stop = int(np.searchsorted(a["ns"], a["ns"][j] + ex.time_after_min * MIN))
    checks = dict(ex.checks)
    for k in range(j, j_flat):
        if k > j and a["ns"][k] - a["ns"][k - 1] > 60 * MIN:
            p = a["bid_c"][k - 1] if side > 0 else a["ask_c"][k - 1]
            return k - 1, p, "closure"
        if side > 0:
            if a["bid_l"][k] <= stop and (k > j or first_bar_stop):
                return k, (stop if k == j else min(stop, a["bid_o"][k])), "stop"
            if k > j and a["bid_h"][k] >= tgt:
                return k, max(tgt, a["bid_o"][k]), "target"
        else:
            if a["ask_h"][k] >= stop and (k > j or first_bar_stop):
                return k, (stop if k == j else max(stop, a["ask_o"][k])), "stop"
            if k > j and a["ask_l"][k] <= tgt:
                return k, min(tgt, a["ask_o"][k]), "target"
        if k > j:
            px_o = a["bid_o"][k] if side > 0 else a["ask_o"][k]
            if t_stop is not None and k == t_stop and side * (px_o - entry) < ex.time_min_r * risk:
                return k, px_o, "time_stop"
            if k in checks and side * (px_o - entry) < checks[k] * risk:
                return k, px_o, "check"
        best = max(best, (a["bid_h"][k] - entry) if side > 0 else (entry - a["ask_l"][k]))
        ext = max(ext, a["m_h"][k]) if side > 0 else min(ext, a["m_l"][k])
        if ex.be and not be_done and best >= ex.be[0] * risk:
            lock = entry + side * ex.be[1] * risk
            stop = max(stop, lock) if side > 0 else min(stop, lock)
            be_done = True
        if ex.trail_mode and best >= ex.trail_trig * risk:
            trail_on = True
        if trail_on and a["mod"][k] % 15 == 14:            # this minute closes a 15m bar
            atr = last_closed(a["b15_end"], a["atr15"], a["ns"][k] + MIN)
            if np.isfinite(atr):
                base = ext if ex.trail_mode == "chandelier" else a["m_c"][k]
                cand = base - side * ex.trail_k * atr
                stop = max(stop, cand) if side > 0 else min(stop, cand)
    if j_flat >= len(a["ns"]):
        k = len(a["ns"]) - 1
        return k, (a["bid_c"][k] if side > 0 else a["ask_c"][k]), "end"
    return j_flat, (a["bid_o"][j_flat] if side > 0 else a["ask_o"][j_flat]), "flat_1550"


def trade(a, j, side, entry, stop, ex, j_flat, rng, ctl: list, **extra) -> dict:
    """Run one trade and its coin-flip control (same minute, random side, same stop distance and exits)."""
    jx, px, why = manage(a, j, side, entry, stop, ex, j_flat)
    risk = side * (entry - stop)
    spread = a["ask_o"][j] - a["bid_o"][j]
    row = trade_row(a, j, jx, side, entry, px, risk, spread, why, **extra)
    cs = int(rng.choice([1, -1]))
    if j + 1 < j_flat:
        ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
        cx = Exits(**{**ex.__dict__, "checks": list(ex.checks)})
        cjx, cpx, cwhy = manage(a, j + 1, cs, ce, ce - cs * risk, cx, j_flat)
        ctl.append(trade_row(a, j, cjx, cs, ce, cpx, risk, spread, cwhy))
    return row


# ── #2 London-to-NY momentum ──────────────────────────────────────────────────────────────────────────────────────────
LNY_EXITS = dict(target_r=3.0, trail_mode="close", trail_trig=1.2, trail_k=2.0, be=(1.2, 0.1))


def london_days(a: dict) -> dict[int, dict]:
    out = {}
    for d, (s, e) in a["days"].items():
        if a["dow"][d] >= 5:
            continue
        i03, i0815 = at(a, s, e, 180), at(a, s, e, 495)
        if i0815 - i03 < 250:
            continue
        hi, lo = a["m_h"][i03:i0815].max(), a["m_l"][i03:i0815].min()
        o, c = a["m_o"][i03], a["m_c"][i0815 - 1]
        out[d] = dict(o=o, c=c, h=hi, l=lo, rng=hi - lo, disp=c - o,
                      eff=abs(c - o) / (hi - lo) if hi > lo else 0.0, vol=a["vol"][i03:i0815].sum())
    keys = sorted(out)
    for n, d in enumerate(keys):                     # baselines from the previous 20 qualifying days
        prev = keys[max(0, n - 20):n]
        out[d]["avg_rng"] = float(np.mean([out[p]["rng"] for p in prev])) if len(prev) == 20 else np.nan
        out[d]["med_vol"] = float(np.median([out[p]["vol"] for p in prev])) if len(prev) == 20 else np.nan
    return out


def run_lny(a: dict, rng, mode: str = "rule") -> tuple[list, list]:
    """mode 'rule' = the strategy; 'dead' = Gemini's control (dead London days, side = sign of London's move)."""
    trades, ctl = [], []
    for d, L in london_days(a).items():
        if not np.isfinite(L["avg_rng"]) or a["date"][d] in FOMC_DAYS:
            continue
        s, e = a["days"][d]
        i0815, i0845, i1130 = at(a, s, e, 495), at(a, s, e, 525), at(a, s, e, 690)
        i1330, i1550 = at(a, s, e, 810), at(a, s, e, 950)
        if i0845 - i0815 < 20 or i1130 <= i0845:
            continue
        i03 = at(a, s, e, 180)
        c845 = a["m_c"][i0845 - 1]
        e4 = last_closed(a["h4_end"], a["ema4h"], day_ns(a, d, 480))
        atr = last_closed(a["b15_end"], a["atr15"], a["ns"][i0845 - 1] + MIN)
        if not (np.isfinite(e4) and np.isfinite(atr)):
            continue
        lo_open, hi_open = a["m_l"][i0815:i0845].min(), a["m_h"][i0815:i0845].max()
        sg = 1 if L["disp"] > 0 else -1
        conds = dict(disp_ge_0_8=abs(L["disp"]) >= 0.80 * L["avg_rng"], range_le_2_2=L["rng"] <= 2.20 * L["avg_rng"],
                     eff_ge_0_55=L["eff"] >= 0.55, vol_ge_1_15=L["vol"] >= 1.15 * L["med_vol"],
                     ema4h_agrees=(c845 - e4) * sg > 0,
                     open_holds=(lo_open > L["o"] + 0.35 * L["rng"]) if sg > 0 else (hi_open < L["o"] - 0.35 * L["rng"]))
        side = 0
        if mode == "rule":
            base = (abs(L["disp"]) >= 0.80 * L["avg_rng"] and L["rng"] <= 2.20 * L["avg_rng"] and L["eff"] >= 0.55
                    and L["vol"] >= 1.15 * L["med_vol"])
        else:
            base = L["eff"] < 0.25 and L["vol"] < L["med_vol"] and L["disp"] != 0
        if base and L["disp"] > 0 and c845 > e4 and lo_open > L["o"] + 0.35 * L["rng"]:
            side = 1
        elif base and L["disp"] < 0 and c845 < e4 and hi_open < L["o"] - 0.35 * L["rng"]:
            side = -1
        if not side:
            note("lny", mode == "rule", **conds, filled=False)
            continue
        level = (a["m_h"][i03:i0845].max() + 0.5) if side > 0 else (a["m_l"][i03:i0845].min() - 0.5)
        dist = max(0.50 * L["rng"], 1.50 * atr, 0.0035 * c845)
        stop0 = level - side * dist
        f = fill_stop(a, i0845, i1130, side, level, cancel=stop0)
        note("lny", mode == "rule", **conds, filled=bool(f))
        if not f:
            continue
        j, px = f
        ex = Exits(**LNY_EXITS, checks=[(i1330, 0.30)])
        trades.append(trade(a, j, side, px, stop0, ex, i1550, rng, ctl, london_eff=L["eff"],
                            london_disp_rng=abs(L["disp"]) / L["avg_rng"]))
    return trades, ctl


# ── #3 cross-asset US cash open ───────────────────────────────────────────────────────────────────────────────────────
XEQ_EXITS = dict(target_r=2.2, trail_mode="chandelier", trail_trig=1.0, trail_k=1.5, time_after_min=150, time_min_r=0.25)


def open_moves(a: dict) -> dict[int, dict]:
    """09:30–10:00 NY return and summed tick volume per day, with the volume's previous-20-day median."""
    out = {}
    for d, (s, e) in a["days"].items():
        i0930, i1000 = at(a, s, e, 570), at(a, s, e, 600)
        if i1000 - i0930 < 25:
            continue
        o, c = a["m_o"][i0930], a["m_c"][i1000 - 1]
        out[d] = dict(r=c / o - 1, vol=a["vol"][i0930:i1000].sum())
    keys = sorted(out)
    for n, d in enumerate(keys):
        prev = keys[max(0, n - 20):n]
        out[d]["med_vol"] = float(np.median([out[p]["vol"] for p in prev])) if len(prev) == 20 else np.nan
    return out


def run_xeq(a: dict, nas: dict, dow: dict, rng, shuffle: bool = False) -> tuple[list, list]:
    """nas, dow = open_moves() of NAS100 and US30. shuffle = Gemini's control: equity data from a random other day."""
    trades, ctl = [], []
    cal = events()
    both = sorted(set(nas) & set(dow))
    remap = dict(zip(both, rng.permutation(both))) if shuffle else {d: d for d in both}
    for d, (s, e) in a["days"].items():
        if a["dow"][d] >= 5 or d not in remap or a["date"][d] in FOMC_DAYS:
            continue
        q = remap[d]
        N, U = nas[q], dow[q]
        if not np.isfinite(N["med_vol"]):
            continue
        i0930, i1000, i1130, i1550 = at(a, s, e, 570), at(a, s, e, 600), at(a, s, e, 690), at(a, s, e, 950)
        if i1000 - i0930 < 25 or i1130 <= i1000:
            continue
        o, c = a["m_o"][i0930], a["m_c"][i1000 - 1]
        hi, lo = a["m_h"][i0930:i1000].max(), a["m_l"][i0930:i1000].min()
        rg = hi - lo
        atr = last_closed(a["b15_end"], a["atr15"], a["ns"][i1000 - 1] + MIN)
        e1 = last_closed(a["h1_end"], a["ema1h"], a["ns"][i1000 - 1] + MIN)
        if not (np.isfinite(atr) and np.isfinite(e1)) or rg <= 0:
            continue
        rx, dur = c / o - 1, N["r"] - U["r"]
        common = N["vol"] >= 1.15 * N["med_vol"] and 0.80 * atr <= rg <= 2.50 * atr
        sg = 1 if rx > 0 else -1
        conds = dict(nas_vol_ge_1_15=N["vol"] >= 1.15 * N["med_vol"], range_0_8_to_2_5_atr=0.80 * atr <= rg <= 2.50 * atr,
                     close_in_range_third=(c >= lo + 0.65 * rg) if sg > 0 else (c <= lo + 0.35 * rg),
                     ema1h_agrees=(c - e1) * sg > 0,
                     equity_confirms=(dur >= 0.0015 or (N["r"] <= -0.003 and U["r"] <= -0.003)) if sg > 0
                     else (dur <= -0.0015 or (N["r"] >= 0.003 and U["r"] >= 0.003)))
        side = 0
        if common and rx > 0 and c >= lo + 0.65 * rg and c > e1 and (dur >= 0.0015 or (N["r"] <= -0.003 and U["r"] <= -0.003)):
            side = 1
        elif common and rx < 0 and c <= lo + 0.35 * rg and c < e1 and (dur <= -0.0015 or (N["r"] >= 0.003 and U["r"] >= 0.003)):
            side = -1
        if not side:
            note("xeq", not shuffle, **conds, filled=False)
            continue
        j0 = i1000
        if any(m == 600 for m, _ in cal.get(a["date"][d], [])):          # 10:00 release: wait for the 10:15 close
            j0 = at(a, s, e, 615)
            hi, lo = a["m_h"][i0930:j0].max(), a["m_l"][i0930:j0].min()
            rg = hi - lo
        level = hi + 0.5 if side > 0 else lo - 0.5
        dist = max(rg, 1.30 * atr, 0.0030 * c)
        stop0 = level - side * dist
        f = fill_stop(a, j0, i1130, side, level, cancel=stop0, spread_max=0.80)
        note("xeq", not shuffle, **conds, filled=bool(f))
        if not f:
            continue
        j, px = f
        trades.append(trade(a, j, side, px, stop0, Exits(**XEQ_EXITS), i1550, rng, ctl,
                            duration_spread=dur, nas_r=N["r"], us30_r=U["r"]))
    return trades, ctl


# ── #1 post-macro-release drift ───────────────────────────────────────────────────────────────────────────────────────
PMRD_EXITS = dict(target_r=2.5, trail_mode="chandelier", trail_trig=1.0, trail_k=1.5, time_after_min=180, time_min_r=0.5)


def slot_volume_median(a: dict, slots: set[int]) -> dict[tuple[int, int], float]:
    """Median 15m tick volume of each NY slot (bar start minute) over the previous 20 weekdays that have the bar."""
    per = {m: [] for m in slots}
    out = {}
    for d in sorted(a["days"]):
        s, e = a["days"][d]
        if a["dow"][d] >= 5:
            continue
        for m in slots:
            i0, i1 = at(a, s, e, m), at(a, s, e, m + 15)
            if i1 - i0 < 10:
                continue
            hist = per[m]
            out[(d, m)] = float(np.median(hist[-20:])) if len(hist) >= 20 else np.nan
            hist.append(a["vol"][i0:i1].sum())
    return out


def run_pmrd(a: dict, rng, control: bool = False) -> tuple[list, list]:
    """control = Gemini's: weekdays with NO calendar event, B0 = the 08:30 and 10:00 bars."""
    trades, ctl = [], []
    cal = events()
    slots = {m - m % 15 for v in cal.values() for m, _ in v} | {510, 600}
    medv = slot_volume_median(a, slots)
    for d, (s, e) in a["days"].items():
        if a["dow"][d] >= 5:
            continue
        evs = cal.get(a["date"][d], [])
        if control:
            if evs:
                continue
            cands = [510, 600]
        else:
            cands = sorted({m - m % 15 for m, _ in evs})
        i1550 = at(a, s, e, 950)
        for slot in cands:
            i0, i1 = at(a, s, e, slot), at(a, s, e, slot + 15)
            if i1 - i0 < 10 or i1 >= i1550:
                continue
            o, hi, lo, c = a["m_o"][i0], a["m_h"][i0:i1].max(), a["m_l"][i0:i1].min(), a["m_c"][i1 - 1]
            rg = hi - lo
            atr = last_closed(a["b15_end"], a["atr15"], a["ns"][i0])               # bar before B0
            e1 = last_closed(a["h1_end"], a["ema1h"], a["ns"][i1 - 1] + MIN)
            mv = medv.get((d, slot), np.nan)
            if not (np.isfinite(atr) and np.isfinite(e1) and np.isfinite(mv)) or rg <= 0:
                continue
            body = abs(c - o) / rg
            common = 1.35 * atr <= rg <= 3.50 * atr and a["vol"][i0:i1].sum() >= 1.40 * mv and body >= 0.55
            sg = 1 if c > o else -1
            conds = dict(range_1_35_to_3_5_atr=1.35 * atr <= rg <= 3.50 * atr, range_ge_1_35_atr=rg >= 1.35 * atr,
                         vol_ge_1_4=a["vol"][i0:i1].sum() >= 1.40 * mv, body_ge_0_55=body >= 0.55,
                         close_near_extreme=(hi - c <= 0.25 * rg) if sg > 0 else (c - lo <= 0.25 * rg),
                         ema1h_agrees=(c - e1) * sg > 0)
            side = 0
            if common and c > o and hi - c <= 0.25 * rg and c > e1:
                side = 1
            elif common and c < o and c - lo <= 0.25 * rg and c < e1:
                side = -1
            if not side:
                note("pmrd", not control, **conds, filled=False)
                continue
            level = hi + 0.5 if side > 0 else lo - 0.5
            dist = max(0.65 * rg, 1.10 * atr, 0.0030 * c)
            stop0 = level - side * dist
            f = fill_stop(a, i1, min(at(a, s, e, slot + 45), i1550), side, level, spread_max=0.80)
            note("pmrd", not control, **conds, filled=bool(f))
            if not f:
                continue
            j, px = f
            checks = []
            nxt = [m for m, _ in evs if 0 < (day_ns(a, d, m) - a["ns"][j]) <= 60 * MIN]
            if nxt:
                checks = [(at(a, s, e, min(nxt) - 2), 0.75)]
            trades.append(trade(a, j, side, px, stop0, Exits(**PMRD_EXITS, checks=checks), i1550, rng, ctl,
                                event=",".join(n for m, n in evs if m - m % 15 == slot) or "none",
                                b0_range_atr=rg / atr))
            break                                                                  # one trade per day
    return trades, ctl


# ── report ────────────────────────────────────────────────────────────────────────────────────────────────────────────
TITLE = {"lny": "#2 London-to-NY momentum", "xeq": "#3 Cross-asset US cash open", "pmrd": "#1 Post-release drift"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", default=",".join(RULES))
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--frozen", action="store_true")
    a_ = ap.parse_args()
    want = [r for r in a_.only.split(",") if r in RULES]
    if a_.data.startswith("holdout"):
        if not a_.frozen:
            raise SystemExit("holdout data is scored only with --frozen (rules that passed dev_m1, unchanged)")
        want = [r for r in want if r in PASSED_DEV]
        if not want:
            raise SystemExit("no rule passed dev_m1, so nothing goes to the holdout")
    src = Path("data/export") / a_.data
    a_.out.mkdir(parents=True, exist_ok=True)
    m1 = load(src / "XAUUSD_M1.csv.gz")
    days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).normalize())))
    days = days[days.dayofweek < 5]
    g = prep(m1)
    del m1
    rng = np.random.default_rng(a_.seed)
    runs = []
    if "lny" in want:
        tr, ctl = run_lny(g, rng)
        dead, _ = run_lny(g, rng, mode="dead")
        runs.append(("lny", [("rule", tr), ("coin-flip control", ctl), ("dead-London control", dead)]))
    if "xeq" in want:
        nas = open_moves(prep(load(src / "NDQ_M1.csv.gz")))
        dow = open_moves(prep(load(src / "US30_M1.csv.gz")))
        tr, ctl = run_xeq(g, nas, dow, rng)
        sh, _ = run_xeq(g, nas, dow, rng, shuffle=True)
        runs.append(("xeq", [("rule", tr), ("coin-flip control", ctl), ("shuffled-equity control", sh)]))
    if "pmrd" in want:
        tr, ctl = run_pmrd(g, rng)
        nn, _ = run_pmrd(g, rng, control=True)
        runs.append(("pmrd", [("rule", tr), ("coin-flip control", ctl), ("no-news-day control", nn)]))
    rows, allt = [], []
    for name, sets in runs:
        for lab, t in sets:
            T = pd.DataFrame(t)
            st = stats(T, days) if len(T) else {"trades": 0}
            if len(T):
                st |= pip_stats(T, PIP["XAUUSD"])
                for sd, nm in ((1, "long"), (-1, "short")):
                    x = T[T.side == sd]
                    st[nm] = f"{x.R.mean():+.3f} ({len(x)})" if len(x) else "— (0)"
                st["exits"] = ", ".join(f"{k} {v}" for k, v in T.exit_reason.value_counts().items())
                allt.append(T.assign(strategy=name, rule=lab))
            rows.append({"strategy": name, "rule": lab, **st})
            print(f"  {name:5s} {lab:24s} {st.get('trades', 0):4d} trades  avg {st.get('avg_R', float('nan')):+.3f}R  "
                  f"95% [{st.get('ci_lo', float('nan')):+.3f}, {st.get('ci_hi', float('nan')):+.3f}]  "
                  f"2× {st.get('avg_R_2x', float('nan')):+.3f}", flush=True)
    if allt:
        pd.concat(allt, ignore_index=True).to_csv(a_.out / "trades.csv.gz", index=False)
    span = f"{days.min():%Y-%m-%d} → {days.max():%Y-%m-%d}" if len(days) else "—"
    md = [f"# Gemini's gold strategies on {a_.data}" + (" — frozen dev passers only" if a_.frozen else ""), "",
          f"Data {span}. Rules exactly as specified by Gemini (2026-10-17), with the open points fixed in "
          "fxagents/gemini_test.py before any run. Real OANDA bid/ask fills; R includes the spread; 2× costs pays one more. "
          "Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs — and the rule must beat "
          "its controls. #1 uses the verified calendar (FOMC, CPI, NFP, PPI only).", ""]
    for name, _ in runs:
        rr = [r for r in rows if r["strategy"] == name]
        main_r = rr[0]
        verdict = "PASS" if main_r.get("pass") and all(main_r["avg_R"] > r.get("avg_R", -9) for r in rr[1:]) else "no pass"
        md += [f"## {TITLE[name]} — **{verdict}**", "",
               "| Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Long avg R (n) | "
               "Short avg R (n) | Thirds | Median hold | Net pips | Exits |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rr:
            if not r.get("trades"):
                md.append(f"| {r['rule']} | 0 |" + " |" * 12)
                continue
            md.append(f"| {r['rule']} | {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | {r['ci_lo']:+.2f} to "
                      f"{r['ci_hi']:+.2f} | {r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['cost_R']:.3f} | {r['long']} | "
                      f"{r['short']} | {' / '.join(f'{x:+.2f}' for x in r['thirds'])} | {r['hold_min_median']:.0f} min | "
                      f"{r['pips_net']:+,.0f} | {r['exits']} |")
        md.append("")
    md += ["## Why so few trades: how many days pass each condition", "",
           "Each evaluated day (or release bar for #1) counted once. *Alone* = share passing that condition by itself; "
           "*cumulative* = days still left after it and every condition above it (in the rule's order).", ""]
    for name in want:
        F = pd.DataFrame(FUNNEL.get(name, []))
        if not len(F):
            continue
        md += [f"**{TITLE[name]}** — {len(F)} days evaluated", "", "| Condition | Alone | Cumulative (days) |", "|---|---|---|"]
        cum = pd.Series(True, index=F.index)
        for col in F.columns:
            if col == "range_ge_1_35_atr":
                md.append(f"| {col} (lower bound only, info) | {F[col].mean():.0%} | — |")
                continue
            cum &= F[col].astype(bool)
            md.append(f"| {col} | {F[col].mean():.0%} | {int(cum.sum())} |")
        md.append("")
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
