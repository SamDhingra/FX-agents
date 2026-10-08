"""Three research hypotheses from the Oct 2026 audit (docs/astra_audit_2026-10-08.md §4), coded as
specified, each with the control the spec names. Unmeasured ideas, v0.1.0 — frozen before testing:
nothing here was tuned on our data, and nothing may be tuned after reading the results.

  ASTRA-ORB-EXP-CFD-001    NDQ, US30   cash opening range 09:30–09:45, first 5m close-break 09:50–11:00,
                                       stop at the range midpoint, no target, 2×ATR5 trail after +1.5R
  ASTRA-GAP-FAIL-CFD-001   NDQ, US30   small overnight gap (0.10–0.35 daily ATR) that fails by 09:45 →
                                       fade to yesterday's 16:00 close, stop beyond the opening extreme
  ASTRA-H1-VOL-TREND-CFD-001 XAUUSD, NDQ  1h breakout of 12 bars with EMA32>EMA128, efficiency ratio ≥ 0.30,
                                       normal volatility; 2×ATR stop, 2×ATR trail after +1R

    python -m fxagents.astra_cfd --days 365 --out data/year_test/astra_cfd
    ./fx.sh newstrats            # on the server, 365 days, report published to GitHub

Execution on 1-minute MID candles with a synthetic spread (bid = mid − s/2, ask = mid + s/2):
  • decision at a bar's close; market entry at the NEXT 1m open on the far side + slippage max(q, s/4)
  • stops trigger on the bid (longs) / ask (shorts); an adverse gap fills at the open; + slippage
  • a resting target fills at its price (no improvement); stop and target in the same minute → stop
  • trailing stops update only on completed 5m / 1h closes and take effect from the next minute;
    a new stop already through the market closes the trade at the next open
  • time exits at the first quote of the exit minute (15:50, or 11:00 for the gap trade)
  • R = |actual fill − initial stop|; results are net of spread and slippage
Cost gate (spec): (s + 2·slip) / stop distance ≤ 0.10. Stress: costs ×1.5 and ×2 on the SAME trades
the baseline admitted (the gate stays at baseline costs).
Calendar: skip US cash holidays, early closes and FOMC days. CPI/PPI/NFP/GDP/PCE come out at 08:30 ET,
outside every entry and holding window here, so their ±15-min blackout never binds (nonstandard-time
releases are not modelled). Warm-up: the spec asks for 500 bars of the longest indicator timeframe;
365 days can't give 500 daily bars, so the gap test needs 20 daily bars and the others 150 bars (noted
in the report). Each instrument is evaluated on its own; the one-index-position rule is not applied.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config

TICK = {"XAUUSD": 0.001, "NDQ": 0.1, "US30": 0.1}
SPREAD = {"XAUUSD": 0.40, "NDQ": 1.50, "US30": 2.50}          # the spec's baseline full spreads (price points)
COST_GATE = 0.10

HOLIDAYS = {  # US cash-market holidays
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25"}
EARLY_CLOSE = {"2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24"}
FOMC = {"2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"}
SKIP = HOLIDAYS | EARLY_CLOSE | FOMC


# ── indicators (spec definitions) ─────────────────────────────────────────────
def wilder_atr(H, L, C, n: int = 14) -> np.ndarray:
    """TR = max(H−L, |H−Cprev|, |L−Cprev|), first TR = H−L; seed = mean of the first n TRs; then Wilder."""
    H, L, C = (np.asarray(x, float) for x in (H, L, C))
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(H - L, np.fmax(np.abs(H - pc), np.abs(L - pc)))
    tr[0] = H[0] - L[0]
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        out[i] = ((n - 1) * out[i - 1] + tr[i]) / n
    return out


def ema(x, n: int) -> np.ndarray:
    """SMA of the first n values, then alpha = 2/(n+1)."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = x[:n].mean()
    a = 2 / (n + 1)
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Clock-aligned bars [t, t+rule) in New York time (labelled by their start); empty bars dropped."""
    return m1.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


# ── the 1-minute executor ─────────────────────────────────────────────────────
@dataclass
class Costs:
    s: float      # full spread
    slip: float   # adverse slippage per market / stop fill
    q: float

    def scaled(self, k: float) -> "Costs":
        return Costs(self.s * k, self.slip * k, self.q)

    @property
    def round_trip(self) -> float:
        return self.s + 2 * self.slip


def execute(O, H, L, C, j: int, side: int, stop: float, j_end: int, c: Costs, target: float | None = None,
            trail=None) -> dict:
    """Run one trade from the open of minute j to (at the latest) the open of minute j_end.
    trail(k, stop, fill, R) → new stop or None; called at the start of minute k when an HTF bar has
    just completed (the caller decides which k)."""
    hs = c.s / 2
    fill = O[j] + side * (hs + c.slip)
    R = abs(fill - stop)
    if R <= 0:
        return {}
    k = j
    while k < j_end:
        if trail is not None and k > j:
            ns = trail(k, stop, fill, R)
            if ns is not None and (ns - stop) * side > 0:
                if (O[k] - side * hs - ns) * side <= 0:            # new stop already through the market
                    return _done(O[k] - side * (hs + c.slip), "trail_through", k, fill, stop, R, side)
                stop = ns
        bid_lo = (L[k] - hs) if side > 0 else (H[k] + hs)          # adverse extreme on the exit side
        bid_hi = (H[k] - hs) if side > 0 else (L[k] + hs)          # favourable extreme on the exit side
        if (bid_lo - stop) * side <= 0:
            op = O[k] - side * hs
            px = op if (op - stop) * side < 0 else stop
            return _done(px - side * c.slip, "stop", k, fill, stop, R, side)
        if target is not None and (bid_hi - target) * side >= 0:
            return _done(target, "target", k, fill, stop, R, side)
        k += 1
    if j_end >= len(O):
        return {}                                                  # exit minute not in the data
    return _done(O[j_end] - side * (hs + c.slip), "time", j_end, fill, stop, R, side)


def _done(px, why, k, fill, stop, R, side) -> dict:
    return {"exit": float(px), "why": why, "k_exit": int(k), "fill": float(fill), "R": float(R),
            "r": float((px - fill) * side / R), "final_stop": float(stop)}


# ── session helpers ───────────────────────────────────────────────────────────
class Day:
    """Index helpers for one symbol's 1-minute frame."""

    def __init__(self, m1: pd.DataFrame):
        self.m1 = m1
        self.idx = m1.index
        self.O, self.H, self.L, self.C = (m1[c].to_numpy(float) for c in ("open", "high", "low", "close"))
        self.pos = {t: i for i, t in enumerate(self.idx)}

    def at(self, ts) -> int | None:
        return self.pos.get(ts)

    def first_at_or_after(self, ts) -> int:
        """Index of the first minute at or after ts ON THE SAME DAY; len(idx) (= not available) otherwise."""
        k = int(self.idx.searchsorted(ts))
        if k < len(self.idx) and self.idx[k].normalize() != ts.normalize():
            return len(self.idx)
        return k


def sessions(m1: pd.DataFrame) -> list[pd.Timestamp]:
    """Regular cash sessions present in the data (09:30 bar exists), excluding holidays / early closes."""
    t = m1.index[(m1.index.hour == 9) & (m1.index.minute == 30)]
    return [x for x in t if x.strftime("%Y-%m-%d") not in HOLIDAYS | EARLY_CLOSE]


def _t(day: pd.Timestamp, hm: str) -> pd.Timestamp:
    h, m = map(int, hm.split(":"))
    return day.normalize() + pd.Timedelta(hours=h, minutes=m)


# ── ASTRA-ORB-EXP-CFD-001 ─────────────────────────────────────────────────────
def orb(m1: pd.DataFrame, c: Costs, control: bool = False, k_cost: float = 1.0, admitted: set | None = None) -> list[dict]:
    d = Day(m1)
    b5 = resample(m1, "5min")
    A5 = wilder_atr(b5.high, b5.low, b5.close)
    b5_close_t = b5.index + pd.Timedelta("5min")
    b5_pos = {t: i for i, t in enumerate(b5.index)}
    first_k = np.asarray(d.idx.searchsorted(b5_close_t))     # minute index at which each 5m bar is known
    k_to_b5 = {}
    for bi, k in enumerate(first_k):
        k_to_b5.setdefault(int(k), bi)
    cx = c.scaled(k_cost)
    widths: list[float] = []
    out = []
    for day in sessions(m1):
        ds = day.strftime("%Y-%m-%d")
        orng = m1[(m1.index >= day) & (m1.index < _t(day, "09:45"))]
        if len(orng) < 14:
            continue
        hor, lor = orng.high.max(), orng.low.min()
        W = hor - lor
        M = float(np.median(widths[-20:])) if len(widths) >= 20 else None
        widths.append(W)
        if ds in FOMC or M is None or not np.isfinite(A5[min(len(A5) - 1, b5_pos.get(_t(day, "09:40"), 0))]):
            continue
        if b5_pos.get(_t(day, "09:40"), 0) < 150:
            continue
        if not control and not (M > 0 and 0.80 <= W / M <= 1.80):
            continue
        q = c.q
        for st in pd.date_range(_t(day, "09:45"), _t(day, "10:55"), freq="5min"):
            bi = b5_pos.get(st)
            if bi is None:
                continue
            o5, h5, l5, c5 = b5.iloc[bi][["open", "high", "low", "close"]]
            side = 1 if c5 >= hor + q else -1 if c5 <= lor - q else 0
            if side == 0:
                continue
            rng = h5 - l5
            if not control:
                ok = rng > 0 and ((c5 > o5 and (c5 - l5) / rng >= 0.75) if side > 0 else (c5 < o5 and (h5 - c5) / rng >= 0.75))
                if not ok:
                    break                                          # the first break failed → done for the day
            j = d.at(st + pd.Timedelta("5min"))
            if j is None:
                break
            mid_or = (hor + lor) / 2
            S = math.floor(mid_or / q) * q if side > 0 else math.ceil(mid_or / q) * q
            E = d.O[j] + side * c.s / 2
            dist, A = abs(E - S), A5[bi]
            if (E - S) * side <= 0 or not (0.5 * A <= dist <= 2.0 * A):
                break
            key = (ds, side)
            if admitted is None and c.round_trip / dist > COST_GATE:
                break
            if admitted is not None and key not in admitted:
                break
            j_end = d.first_at_or_after(_t(day, "15:50"))
            if j_end >= len(d.idx):
                break                                              # session incomplete in the data (e.g. today)

            best = {"c": None}

            def trail(k, stop, fill, R, side=side, j=j):
                b = k_to_b5.get(k)
                if b is None or b5.index[b] < d.idx[j]:
                    return None                                    # only 5m bars that started after entry
                cl = b5.close.iloc[b]
                best["c"] = cl if best["c"] is None else (max(best["c"], cl) if side > 0 else min(best["c"], cl))
                if (best["c"] - (fill + side * 1.5 * R)) * side < 0:
                    return None
                ns = best["c"] - side * 2 * A5[b]
                return math.floor(ns / q) * q if side > 0 else math.ceil(ns / q) * q

            res = execute(d.O, d.H, d.L, d.C, j, side, S, j_end, cx, trail=trail)
            if res:
                out.append({"day": ds, "ts": d.idx[j], "side": side, "stop": S, "W_M": round(W / M, 2), **res, "key": key})
            break
    return out


# ── ASTRA-GAP-FAIL-CFD-001 ────────────────────────────────────────────────────
def gap_fail(m1: pd.DataFrame, c: Costs, control: bool = False, k_cost: float = 1.0, admitted: set | None = None) -> list[dict]:
    d = Day(m1)
    cx = c.scaled(k_cost)
    q = c.q
    cash = m1.between_time("09:30", "15:59")
    daily = cash.groupby(cash.index.normalize()).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "size"})
    daily = daily[(daily["volume"] >= 380) & ~daily.index.strftime("%Y-%m-%d").isin(list(HOLIDAYS | EARLY_CLOSE))]
    D_atr = pd.Series(wilder_atr(daily.high, daily.low, daily.close), index=daily.index)
    out = []
    days = list(daily.index)
    for n, dn in enumerate(days):
        if n < 21:
            continue
        ds = dn.strftime("%Y-%m-%d")
        if ds in FOMC:
            continue
        prev = days[n - 1]
        jp, jo = d.at(_t(prev, "15:59")), d.at(_t(dn, "09:30"))
        D = D_atr.iloc[n - 1]                                      # known before today
        if jp is None or jo is None or not np.isfinite(D):
            continue
        P, O = d.C[jp], d.O[jo]
        G = O - P
        if not (0.10 * D <= abs(G) <= 0.35 * D):
            continue
        orng = m1[(m1.index >= dn) & (m1.index < _t(dn, "09:45"))]
        if len(orng) < 14:
            continue
        H, L, Cl = orng.high.max(), orng.low.min(), orng.close.iloc[-1]
        g = abs(G)
        if G > 0:
            side = -1
            ok = control or (P < Cl <= O - 0.25 * G and H <= O + 0.25 * G)
            S, T = math.ceil((H + 0.05 * D) / q) * q, math.ceil(P / q) * q
        else:
            side = 1
            ok = control or (O + 0.25 * g <= Cl < P and L >= O - 0.25 * g)
            S, T = math.floor((L - 0.05 * D) / q) * q, math.floor(P / q) * q
        if not ok:
            continue
        j = d.at(_t(dn, "09:45"))
        if j is None:
            continue
        E = d.O[j] + side * c.s / 2
        if (T - E) * side <= 0 or (E - S) * side <= 0:
            continue                                               # target already reached / stop not behind
        dist = abs(E - S)
        if abs(T - E) / dist < 1.25:
            continue
        key = (ds, side)
        if admitted is None and c.round_trip / dist > COST_GATE:
            continue
        if admitted is not None and key not in admitted:
            continue
        j_end = d.first_at_or_after(_t(dn, "11:00"))
        if j_end >= len(d.idx):
            continue                                               # session incomplete in the data
        res = execute(d.O, d.H, d.L, d.C, j, side, S, j_end, cx, target=T)
        if res:
            out.append({"day": ds, "ts": d.idx[j], "side": side, "stop": S, "target": T, "gap_D": round(G / D, 3), **res, "key": key})
    return out


# ── ASTRA-H1-VOL-TREND-CFD-001 ────────────────────────────────────────────────
def h1_trend(m1: pd.DataFrame, c: Costs, control: str | None = None, k_cost: float = 1.0, admitted: set | None = None) -> list[dict]:
    """control: None (the spec), 'plain' (12-bar breakout, no EMA/ER/vol filters), 'trend10' (10:00 entry
    in the EMA32/EMA128 direction, no breakout)."""
    d = Day(m1)
    cx = c.scaled(k_cost)
    q = c.q
    h1 = resample(m1, "1h")
    Hh, Lh, Ch = (h1[x].to_numpy(float) for x in ("high", "low", "close"))
    A = wilder_atr(Hh, Lh, Ch)
    e32, e128 = ema(Ch, 32), ema(Ch, 128)
    absd = np.abs(np.diff(Ch, prepend=np.nan))
    h_close_t = h1.index + pd.Timedelta("1h")
    first_k = np.asarray(d.idx.searchsorted(h_close_t))
    k_to_h = {}
    for bi, k in enumerate(first_k):
        k_to_h.setdefault(int(k), bi)
    by_close = {t: i for i, t in enumerate(h_close_t)}
    out = []
    for day in sessions(m1):
        ds = day.strftime("%Y-%m-%d")
        if ds in FOMC:
            continue
        hours = ["10:00"] if control == "trend10" else ["09:00", "10:00", "11:00", "12:00", "13:00"]
        for hm in hours:
            t = by_close.get(_t(day, hm))
            if t is None or t < 150:
                continue
            if control == "trend10":
                side = 1 if e32[t] > e128[t] else -1 if e32[t] < e128[t] else 0
            else:
                hi12, lo12 = Hh[t - 12:t].max(), Lh[t - 12:t].min()
                up, dn = Ch[t] >= hi12 + q, Ch[t] <= lo12 - q
                if control != "plain":
                    den = absd[t - 23:t + 1].sum()
                    er = abs(Ch[t] - Ch[t - 24]) / den if den > 0 else 0.0
                    med = np.median(A[t - 120:t])
                    if not (er >= 0.30 and np.isfinite(med) and med > 0 and 0.75 <= A[t] / med <= 1.75):
                        continue
                    up = up and e32[t] > e128[t] and e32[t] > e32[t - 3]
                    dn = dn and e32[t] < e128[t] and e32[t] < e32[t - 3]
                side = 1 if up else -1 if dn else 0
            if side == 0:
                continue
            j = d.at(_t(day, hm))
            if j is None:
                break
            E0 = d.O[j] + side * c.s / 2
            raw = E0 - side * 2 * A[t]
            S = math.floor(raw / q) * q if side > 0 else math.ceil(raw / q) * q
            dist = abs(E0 - S)
            key = (ds, side)
            if admitted is None and c.round_trip / dist > COST_GATE:
                break
            if admitted is not None and key not in admitted:
                break
            j_end = d.first_at_or_after(_t(day, "15:50"))
            if j_end >= len(d.idx):
                break                                              # session incomplete in the data (e.g. today)
            best = {"c": None, "armed": False}

            def trail(k, stop, fill, R, side=side, j=j):
                b = k_to_h.get(k)
                if b is None or h1.index[b] < d.idx[j]:
                    return None
                cl = Ch[b]
                best["c"] = cl if best["c"] is None else (max(best["c"], cl) if side > 0 else min(best["c"], cl))
                if not best["armed"]:
                    if (cl - (fill + side * R)) * side < 0:
                        return None
                    best["armed"] = True
                ns = best["c"] - side * 2 * A[b]
                return math.floor(ns / q) * q if side > 0 else math.ceil(ns / q) * q

            res = execute(d.O, d.H, d.L, d.C, j, side, S, j_end, cx, trail=trail)
            if res:
                out.append({"day": ds, "ts": d.idx[j], "side": side, "stop": S, "hour": hm, **res, "key": key})
            break                                                  # the first qualifying hour is the only one
    return out


# ── evaluation ────────────────────────────────────────────────────────────────
TESTS = [  # (name, kind, function, kwargs, symbols)
    ("ORB-EXP", "spec", orb, {}, ["NDQ", "US30"]),
    ("ORB-EXP", "control: no W/M or close-location filter", orb, {"control": True}, ["NDQ", "US30"]),
    ("GAP-FAIL", "spec", gap_fail, {}, ["NDQ", "US30"]),
    ("GAP-FAIL", "control: unconditional small-gap fade", gap_fail, {"control": True}, ["NDQ", "US30"]),
    ("H1-VOL-TREND", "spec", h1_trend, {}, ["XAUUSD", "NDQ"]),
    ("H1-VOL-TREND", "control: plain 12-bar breakout", h1_trend, {"control": "plain"}, ["XAUUSD", "NDQ"]),
    ("H1-VOL-TREND", "control: 10:00 entry with the EMA trend", h1_trend, {"control": "trend10"}, ["XAUUSD", "NDQ"]),
]


def stats(r: np.ndarray, seed: int = 7) -> dict:
    if not len(r):
        return {"n": 0}
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min())
    rng = np.random.default_rng(seed)
    bs = rng.choice(r, (4000, len(r)), replace=True).mean(axis=1) if len(r) > 1 else np.array([r.mean()])
    return {"n": int(len(r)), "win": float((r > 0).mean()), "avg": float(r.mean()), "sum": float(r.sum()),
            "pf": float(w / l) if l > 0 else None, "t": float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else 0.0,
            "lo95": float(np.percentile(bs, 2.5)), "hi95": float(np.percentile(bs, 97.5)), "dd": dd}


def run(hd: Path, symbols: list[str] | None = None, until: str | None = None) -> tuple[list[dict], pd.DataFrame]:
    rows, trades = [], []
    cache: dict[str, pd.DataFrame] = {}
    for name, kind, fn, kw, syms in TESTS:
        for sym in syms:
            if symbols and sym not in symbols:
                continue
            p = hd / f"{sym}.pkl"
            if not p.exists():
                continue
            if sym not in cache:
                m = pd.read_pickle(p)[0]
                if until:                                          # out-of-sample: only data up to this date
                    m = m[m.index < pd.Timestamp(until, tz=m.index.tz) + pd.Timedelta("1D")]
                cache[sym] = m
            m1 = cache[sym]
            c = Costs(SPREAD[sym], max(TICK[sym], 0.25 * SPREAD[sym]), TICK[sym])
            base = fn(m1, c, **kw)
            adm = {t["key"] for t in base}
            row = {"strategy": name, "kind": kind, "sym": sym, "span": [str(m1.index[0].date()), str(m1.index[-1].date())]}
            r = np.array([t["r"] for t in base])
            row["base"] = stats(r)
            for k in (1.5, 2.0):
                row[f"x{k:g}"] = stats(np.array([t["r"] for t in fn(m1, c, k_cost=k, admitted=adm, **kw)]))
            if len(base):
                tdf = pd.DataFrame(base)
                tdf["ts"] = pd.to_datetime(tdf["ts"])
                mid = tdf["ts"].sort_values().iloc[len(tdf) // 2]
                row["h1"], row["h2"] = float(tdf[tdf.ts < mid].r.mean()), float(tdf[tdf.ts >= mid].r.mean())
                qs = np.array_split(np.arange(len(tdf)), 4)
                row["quarters"] = [float(tdf.r.iloc[ix].mean()) for ix in qs if len(ix)]
                row["months"] = {k: (int(len(g)), round(float(g.r.sum()), 2)) for k, g in tdf.groupby(tdf.ts.dt.strftime("%Y-%m"))}
                row["sides"] = {("long" if s > 0 else "short"): (int(len(g)), round(float(g.r.mean()), 3)) for s, g in tdf.groupby("side")}
                row["exits"] = tdf["why"].value_counts().to_dict()
                tdf["strategy"], tdf["kind"], tdf["sym"] = name, kind, sym
                trades.append(tdf.drop(columns=["key"]))
            rows.append(row)
    return rows, (pd.concat(trades, ignore_index=True) if trades else pd.DataFrame())


def verdict(row: dict, control: dict | None) -> str:
    b, s2 = row["base"], row.get("x2", {})
    if b.get("n", 0) < 30:
        return f"too few trades ({b.get('n', 0)}) to judge"
    ok = b["avg"] > 0 and b["lo95"] > 0 and s2.get("avg", -1) > 0 and (control is None or b["avg"] > control["base"].get("avg", -9))
    if ok:
        return "**PROMISING** — positive, CI above zero, survives 2× costs and beats its control"
    why = []
    if b["avg"] <= 0:
        why.append("average R ≤ 0")
    elif b["lo95"] <= 0:
        why.append("95% interval includes zero (unproven)")
    if s2.get("avg", -1) <= 0:
        why.append("2× costs turn it negative")
    if control is not None and b["avg"] <= control["base"].get("avg", -9):
        why.append("no better than its control")
    return "fail — " + "; ".join(why)


def report(rows: list[dict], days, hd: Path) -> str:
    def f(x, fmt="+.3f"):
        return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else format(x, fmt)
    L = [f"# Audit strategies (ASTRA-*-CFD-001 v0.1.0) — {days or 'cache'} days\n",
         f"History: {hd}. Rules exactly as in docs/astra_audit_2026-10-08.md §4; nothing tuned. R per trade after spread + "
         "slippage (spread NDQ 1.50 / US30 2.50 / XAUUSD 0.40, slippage max(tick, ¼ spread) per market/stop fill). "
         "95% = bootstrap interval of the average R (at most one trade per day, so trades are day blocks). "
         "×1.5 / ×2 = the same trades with costs scaled.\n",
         "Warm-up deviation: the spec asks for 500 bars of the longest indicator timeframe; with 365 days the gap test "
         "uses ≥ 20 prior daily bars and the others ≥ 150 bars. Instruments are tested separately (no one-index-position rule).\n",
         "## Summary\n",
         "| strategy | test | sym | trades | win | avg R | 95% | total R | PF | t | ×1.5 avg | ×2 avg | halves | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    spec = {(r["strategy"], r["sym"]): r for r in rows if r["kind"] == "spec"}
    for r in rows:
        b = r["base"]
        if not b.get("n"):
            L.append(f"| {r['strategy']} | {r['kind']} | {r['sym']} | 0 | | | | | | | | | | no trades |")
            continue
        ctl = None
        if r["kind"] == "spec":
            ctls = [x for x in rows if x["strategy"] == r["strategy"] and x["sym"] == r["sym"] and x["kind"] != "spec" and x["base"].get("n")]
            ctl = max(ctls, key=lambda x: x["base"]["avg"]) if ctls else None
        v = verdict(r, ctl) if r["kind"] == "spec" else ("better than spec" if (sp := spec.get((r["strategy"], r["sym"]))) and sp["base"].get("n") and b["avg"] > sp["base"]["avg"] else "")
        L.append(f"| {r['strategy']} | {r['kind']} | {r['sym']} | {b['n']} | {b['win']:.0%} | {b['avg']:+.3f} | "
                 f"{b['lo95']:+.2f} … {b['hi95']:+.2f} | {b['sum']:+.1f} | {f(b['pf'], '.2f')} | {b['t']:+.2f} | "
                 f"{f(r['x1.5'].get('avg'))} | {f(r['x2'].get('avg'))} | {f(r.get('h1'), '+.2f')} / {f(r.get('h2'), '+.2f')} | {v} |")
    L.append("\nVerdict rule (frozen before the run): PROMISING needs ≥ 30 trades, average R > 0, the 95% interval above "
             "zero, average R > 0 at 2× costs, and a better average than its best control. Anything else fails; a "
             "positive average with an interval spanning zero is 'unproven', not a pass.\n")
    L.append("## Detail\n")
    for r in rows:
        b = r["base"]
        if not b.get("n"):
            continue
        L.append(f"### {r['strategy']} · {r['sym']} · {r['kind']}\n")
        L.append(f"- {b['n']} trades {r['span'][0]} → {r['span'][1]}, worst drawdown {b['dd']:.1f}R")
        L.append("- quarters (avg R): " + " · ".join(f"{x:+.3f}" for x in r.get("quarters", [])))
        L.append("- by month (trades, R): " + " · ".join(f"{k} {v[1]:+.1f} ({v[0]})" for k, v in r.get("months", {}).items()))
        L.append("- sides: " + ", ".join(f"{k} {v[0]} trades {v[1]:+.3f}R" for k, v in r.get("sides", {}).items()))
        L.append("- exits: " + ", ".join(f"{k} {v}" for k, v in r.get("exits", {}).items()) + "\n")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, help="use data/history_<days>d (fetched if missing or a day old)")
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--out", help="folder for report.md / trades.csv / summary.json")
    ap.add_argument("--until", help="use only data up to this date (YYYY-MM-DD), e.g. the year before an earlier test")
    a = ap.parse_args()
    cfg = load_config()
    from .research import history_dir
    base = history_dir(cfg)
    hd = base
    if a.days:
        from .setup_report import fetch_long
        hd = fetch_long(cfg, base, a.days, a.symbols or ["XAUUSD", "NDQ", "US30"])
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "status.json").write_text(json.dumps({"stage": "running", "days": a.days}))
    rows, trades = run(hd, a.symbols, a.until)
    txt = report(rows, a.days, hd)
    if a.until:
        txt = txt.replace("\n", f"\n\n**Data only up to {a.until}** (out-of-sample check).\n", 1)
    print(txt)
    if out:
        (out / "report.md").write_text(txt)
        if len(trades):
            trades.to_csv(out / "trades.csv", index=False)
        (out / "summary.json").write_text(json.dumps(rows, indent=1, default=str))
        (out / "status.json").write_text(json.dumps({"stage": "done", "days": a.days, "trades": int(len(trades)),
                                                     "at": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
