"""News event study, step 1 — EXPLORE (Oct 28 2026). Descriptive only: what XAUUSD / NDQ / US30 did before and after the
scheduled USD releases the bot blacks out (FOMC 14:00, CPI / NFP / PPI 08:30 NY; fxagents/usd_calendar.py), by release type
and instrument, against the same clock time on days with no release.

Three-step plan (docs/news_study.md):
  1. explore  2021-01-01 -> 2023-11-17 (the first half of the seen period) — this module. The M1 data is CUT at the split
              before anything is computed, so the second half and 2016-2020 are not read at all.
  2. register at most a few fixed rules from what step 1 shows, then judge them once on 2023-11-17 -> 2026-10-01.
  3. a rule that passes step 2 is judged once on 2016-2020.

What it measures per event (moves in units of ATR15 = mean true range of the 20 M15 candles closed by T-60):
  * volatility and cost: |move| and range in windows around T vs the same windows on no-release days; spread / ATR15 per minute
  * pre-release drift: signed moves T-240..T-60, T-120..T-35, T-60..T-5, T-30..T-1
  * does the pre-move predict the reaction (sign agreement of T-60..T-5 with T-1..T+5)
  * after the first k minutes (k = 5, 15, 30): trade in the direction of the move T-1..T+k (continuation) or against it (fade),
    held h = 30 / 60 / 120 minutes, entered and exited at the real bid / ask of those minutes (net of the spread)
Event days are the unit of resampling (95% ranges: bootstrap over release days). Many cells are shown; at 95% about 1 in
20 looks "significant" by luck — the report counts how many do vs that expectation. Nothing here is a trading rule.

    python -m fxagents.news_study   (./fx.sh newsstudy)  -> data/year_test/news_study_explore/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import usd_calendar as cal

NY = "America/New_York"
START, SPLIT = pd.Timestamp("2021-01-01", tz=NY), pd.Timestamp("2023-11-17", tz=NY)
SYMS = ("XAUUSD", "NDQ", "US30")
TYPES = ("FOMC", "CPI", "NFP", "PPI")
PRE = [(-240, -60), (-120, -35), (-60, -5), (-30, -1)]
REACT = [(-1, 1), (-1, 5), (-1, 15), (-1, 30)]
KS, HS = (5, 15, 30), (30, 60, 120)
RANGES = [(-60, -1), (0, 30), (30, 90)]
SPREAD_AT = (-1, 0, 1, 5, 30)
MAX_GAP = 3                                   # minutes: a price at t is the close of the last bar starting in [t-1-MAX_GAP, t-1]
DRAWS, SEED = 5000, 3
OUT = Path("data/year_test/news_study_explore")


def release_times(start=START, end=SPLIT) -> pd.DataFrame:
    rows = []
    for typ, (dates, minute) in cal.SOURCES.items():
        for d in dates:
            t = pd.Timestamp(d, tz=NY) + pd.Timedelta(minutes=minute)
            if start <= t < end:
                rows.append({"type": typ, "T": t, "day": d})
    return pd.DataFrame(rows).sort_values("T").reset_index(drop=True)


def control_times(ev: pd.DataFrame, start=START, end=SPLIT) -> pd.DataFrame:
    """No-release weekdays at the same clock minutes (08:30 for CPI/NFP/PPI, 14:00 for FOMC); excludes any release day."""
    busy = set(ev["day"])
    days = pd.date_range(start.tz_localize(None), (end - pd.Timedelta(days=1)).tz_localize(None), freq="B")
    rows = []
    for d in days:
        ds = d.strftime("%Y-%m-%d")
        if ds in busy:
            continue
        for typ, minute in (("ctl_0830", 8 * 60 + 30), ("ctl_1400", 14 * 60)):
            rows.append({"type": typ, "T": pd.Timestamp(ds, tz=NY) + pd.Timedelta(minutes=minute), "day": ds})
    return pd.DataFrame(rows)


class Prices:
    """Mid / bid / ask at a moment t (the close of the minute bar that starts at t-1), from one symbol's M1 frame."""

    def __init__(self, m1: pd.DataFrame):
        self.ns = m1.index.as_unit("ns").asi8
        self.c = m1["close"].to_numpy(float)
        self.h = m1["high"].to_numpy(float)
        self.l = m1["low"].to_numpy(float)
        self.o = m1["open"].to_numpy(float)
        self.sp = m1["spread"].to_numpy(float) if "spread" in m1.columns else np.zeros(len(m1))
        self.m1 = m1

    def pos(self, t: pd.Timestamp) -> int:
        """Index of the last bar starting at or before t-1min, within MAX_GAP minutes; -1 if none."""
        x = (t - pd.Timedelta(minutes=1)).as_unit("ns").value
        i = int(np.searchsorted(self.ns, x, side="right") - 1)
        if i < 0 or x - self.ns[i] > MAX_GAP * 60_000_000_000:
            return -1
        return i

    def mid(self, t):
        i = self.pos(t)
        return np.nan if i < 0 else self.c[i]

    def spread(self, t):
        i = self.pos(t)
        return np.nan if i < 0 else self.sp[i]

    def rng(self, a: pd.Timestamp, b: pd.Timestamp):
        i, j = int(np.searchsorted(self.ns, a.as_unit("ns").value)), int(np.searchsorted(self.ns, b.as_unit("ns").value))
        if j - i < 3:
            return np.nan
        return float(self.h[i:j].max() - self.l[i:j].min())

    def atr15(self, t: pd.Timestamp) -> float:
        """Mean true range of the 20 M15 candles closed by t (from the 3 days of M1 before t)."""
        a = int(np.searchsorted(self.ns, (t - pd.Timedelta(days=3)).as_unit("ns").value))
        b = int(np.searchsorted(self.ns, t.as_unit("ns").value))
        seg = self.m1.iloc[a:b]
        if len(seg) < 300:
            return np.nan
        r = seg.resample("15min", label="left", closed="left").agg({"high": "max", "low": "min", "close": "last"}).dropna()
        r = r[r.index + pd.Timedelta("15min") <= t].iloc[-21:]
        if len(r) < 21:
            return np.nan
        pc = r["close"].shift(1)
        tr = np.maximum(r["high"] - r["low"], np.maximum((r["high"] - pc).abs(), (r["low"] - pc).abs())).iloc[1:]
        v = float(tr.mean())
        return v if v > 0 else np.nan


def measure(P: Prices, T: pd.Timestamp) -> dict | None:
    u = P.atr15(T - pd.Timedelta(minutes=60))
    if not np.isfinite(u):
        return None
    at = lambda k: T + pd.Timedelta(minutes=k)          # noqa: E731
    out = {"atr15": u}
    for a, b in PRE + REACT:
        out[f"mv_{a}_{b}"] = (P.mid(at(b)) - P.mid(at(a))) / u
    for a, b in RANGES:
        out[f"rg_{a}_{b}"] = P.rng(at(a), at(b)) / u
    for k in SPREAD_AT:
        out[f"sp_{k}"] = P.spread(at(k)) / u
    for k in KS:
        d = np.sign(P.mid(at(k)) - P.mid(at(-1)))
        out[f"dir_{k}"] = d
        for h in HS:
            e, x = at(k), at(k + h)
            pe, px = P.mid(e), P.mid(x)
            se, sx = P.spread(e) / 2, P.spread(x) / 2
            gross = d * (px - pe) / u
            cost = (se + sx) / u
            out[f"cont_{k}_{h}"] = gross - cost if d != 0 else np.nan     # trade with the first move, pay the spread both ways
            out[f"fade_{k}_{h}"] = -gross - cost if d != 0 else np.nan
            out[f"gross_{k}_{h}"] = gross if d != 0 else np.nan
    return out


def collect(m1s: dict[str, pd.DataFrame], ev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, m1 in m1s.items():
        P = Prices(m1)
        for r in ev.itertuples(index=False):
            m = measure(P, r.T)
            if m is not None:
                rows.append({"sym": sym, "type": r.type, "T": r.T, "day": r.day, **m})
    return pd.DataFrame(rows)


def boot(v: np.ndarray, days: np.ndarray, draws: int = DRAWS, seed: int = SEED) -> tuple[float, float, float, int]:
    """Mean and a 95% range from resampling release DAYS (instruments on the same day move together)."""
    ok = np.isfinite(v)
    v, days = v[ok], days[ok]
    if len(v) < 8:
        return (float(np.mean(v)) if len(v) else np.nan, np.nan, np.nan, len(v))
    u, inv = np.unique(days, return_inverse=True)
    S, N = np.zeros(len(u)), np.zeros(len(u))
    np.add.at(S, inv, v)
    np.add.at(N, inv, 1)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(u), size=(draws, len(u)))
    m = S[pick].sum(1) / N[pick].sum(1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(v.mean()), float(lo), float(hi), len(v)


def cell(v, days, sig=True) -> str:
    m, lo, hi, n = boot(np.asarray(v, float), np.asarray(days))
    if not np.isfinite(m):
        return "—"
    if not np.isfinite(lo):
        return f"{m:+.2f} (n {n})"
    star = " **\\***" if sig and (lo > 0 or hi < 0) else ""
    return f"{m:+.2f} ({lo:+.2f}..{hi:+.2f}){star}"


def report(a: pd.DataFrame, ctl: pd.DataFrame, n_ev: pd.DataFrame) -> tuple[str, dict]:
    sig_cells, all_cells = 0, 0
    L = ["# News event study — step 1, EXPLORE (2021-01-01 → 2023-11-17 only)", "",
         "Descriptive. What gold, NDQ and US30 did around the scheduled USD releases the bot currently blacks out (no entries "
         "30 min before and after): FOMC 14:00, CPI / NFP / PPI 08:30 NY. **The data after 2023-11-17 and all of 2016–2020 were "
         "not read**, so they are still clean for the registered test (step 2) and its confirmation (step 3).", "",
         "Units: moves in **ATR15** (the average 15-minute candle range just before the window), so instruments and years compare. "
         "Ranges are a bootstrap over release days (instruments on the same day count together). **\\*** marks a 95% range that "
         "excludes 0 — with this many cells, about 1 in 20 does that by luck alone; the count is at the end.", "",
         "Not available: the released numbers and forecasts (the surprise). The historical calendar has dates and times only, and "
         "the live feed has no real-time actual at release, so a rule here can only use prices.", "",
         "## Releases covered", "", "| type | " + " | ".join(SYMS) + " |", "|---|" + "---|" * len(SYMS)]
    for t in TYPES:
        L.append(f"| {t} | " + " | ".join(str(int(((a.type == t) & (a.sym == s)).sum())) for s in SYMS) + " |")
    L += ["", f"Controls: the same clock minutes on {ctl.day.nunique():,} weekdays with no release (08:30 for CPI/NFP/PPI, 14:00 for FOMC).", ""]

    # 1. volatility and cost
    L += ["## 1. How much it moves, and what it costs", "",
          "Median range in ATR15 units, release vs the same window on no-release days; median spread at the minute (in ATR15).", "",
          "| type | sym | range T−60..T | range T..T+30 | range T+30..T+90 | spread T−1 | spread at T | T+1 | T+5 | T+30 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for t in TYPES:
        cname = "ctl_1400" if t == "FOMC" else "ctl_0830"
        for s in SYMS:
            g, c = a[(a.type == t) & (a.sym == s)], ctl[(ctl.type == cname) & (ctl.sym == s)]
            if not len(g):
                continue
            rg = lambda k: f"{g[k].median():.1f} vs {c[k].median():.1f}" if len(c) else f"{g[k].median():.1f}"  # noqa: E731
            sp = lambda k: f"{g[k].median():.3f}" + (f" ({g[k].median() / c[k].median():.1f}×)" if len(c) and c[k].median() > 0 else "")  # noqa: E731
            L.append(f"| {t} | {s} | {rg('rg_-60_-1')} | {rg('rg_0_30')} | {rg('rg_30_90')} | {sp('sp_-1')} | {sp('sp_0')} | "
                     f"{sp('sp_1')} | {sp('sp_5')} | {sp('sp_30')} |")

    # 2. pre-release drift
    L += ["", "## 2. Before the release: does price drift one way?", "",
          "Mean signed move (ATR15), 95% range. Positive = up. Controls on the right show what that clock time does without a release.", "",
          "| type | sym | " + " | ".join(f"T{a_:+d}..T{b_:+d}" for a_, b_ in PRE) + " | control T−60..T−5 |", "|---|---|" + "---|" * (len(PRE) + 1)]
    for t in TYPES:
        cname = "ctl_1400" if t == "FOMC" else "ctl_0830"
        for s in SYMS:
            g, c = a[(a.type == t) & (a.sym == s)], ctl[(ctl.type == cname) & (ctl.sym == s)]
            if not len(g):
                continue
            cs = []
            for a_, b_ in PRE:
                k = f"mv_{a_}_{b_}"
                cs.append(cell(g[k], g.day))
                all_cells += 1
                sig_cells += cs[-1].endswith("**\\***")
            L.append(f"| {t} | {s} | " + " | ".join(cs) + f" | {cell(c['mv_-60_-5'], c.day, sig=False)} |")

    # 3. pre-move vs reaction
    L += ["", "## 3. Does the move before the release predict the first reaction?", "",
          "Share of releases where the sign of T−60..T−5 matches the sign of T−1..T+5 (0.50 = no relation), and the mean reaction "
          "in the pre-move's direction (ATR15).", "", "| type | sym | n | same sign | reaction in the pre-move's direction |", "|---|---|---|---|---|"]
    for t in TYPES:
        for s in SYMS:
            g = a[(a.type == t) & (a.sym == s)].copy()
            if not len(g):
                continue
            sgn = np.sign(g["mv_-60_-5"])                                # the pre-move T-60..T-5
            agree = (np.sign(g["mv_-1_5"]) == sgn) & (sgn != 0)
            c = cell(sgn * g["mv_-1_5"], g.day)
            all_cells += 1
            sig_cells += c.endswith("**\\***")
            L.append(f"| {t} | {s} | {len(g)} | {agree.mean():.2f} | {c} |")

    # 4. continuation vs fade
    L += ["", "## 4. After the first k minutes: go with the move or against it?", "",
          "Enter at T+k in the direction of the move T−1..T+k (**continuation**), hold h minutes, at the real bid/ask of those minutes "
          "(net of the spread, ATR15). The fade is the mirror image and pays the spread too, so both can be negative. Gross shown "
          "for reference. k = 30 is the first entry the current blackout allows.", ""]
    for t in TYPES:
        L += [f"### {t}", "", "| sym | k | " + " | ".join(f"continue h={h}" for h in HS) + " | " + " | ".join(f"fade h={h}" for h in HS)
              + " | gross h=60 |", "|---|---|" + "---|" * (2 * len(HS) + 1)]
        for s in SYMS:
            g = a[(a.type == t) & (a.sym == s)]
            if not len(g):
                continue
            for k in KS:
                cs = []
                for kind in ("cont", "fade"):
                    for h in HS:
                        c = cell(g[f"{kind}_{k}_{h}"], g.day)
                        cs.append(c)
                        all_cells += 1
                        sig_cells += c.endswith("**\\***")
                L.append(f"| {s} | {k} | " + " | ".join(cs) + f" | {cell(g[f'gross_{k}_60'], g.day, sig=False)} |")
        L.append("")
    L += ["### All releases pooled (each instrument and type together)", "",
          "| k | " + " | ".join(f"continue h={h}" for h in HS) + " | " + " | ".join(f"fade h={h}" for h in HS) + " |",
          "|---|" + "---|" * (2 * len(HS))]
    for k in KS:
        cs = []
        for kind in ("cont", "fade"):
            for h in HS:
                c = cell(a[f"{kind}_{k}_{h}"], a.day)
                cs.append(c)
                all_cells += 1
                sig_cells += c.endswith("**\\***")
        L.append(f"| {k} | " + " | ".join(cs) + " |")
    exp = 0.05 * all_cells
    L += ["", "## How many cells look significant, vs luck", "",
          f"{sig_cells} of {all_cells} directional cells have a 95% range that excludes 0; about {exp:.0f} would by luck alone "
          "(they are also correlated with each other). A cell is a lead for step 2 only if it is large enough to pay the spread, "
          "consistent across instruments or types, and makes sense — not because it has a star.", "",
          "## Next", "", "Step 2: register at most a few fixed rules from this (entry, direction, hold, stop, which releases and "
          "instruments), then judge them once on 2023-11-17 → 2026-10-01 with the usual gates. Step 3: a passer is judged once "
          "on 2016–2020."]
    return "\n".join(L) + "\n", {"sig_cells": sig_cells, "cells": all_cells}


def run(hist: Path, out: Path, syms=SYMS) -> dict:
    ev = release_times()
    ctl = control_times(ev)
    m1s = {}
    for s in syms:
        f = hist / f"{s}.pkl"
        if not f.exists():
            print(f"  no history for {s}", flush=True)
            continue
        m1 = pd.read_pickle(f)[0]
        m1 = m1[(m1.index >= START - pd.Timedelta(days=5)) & (m1.index < SPLIT)]     # the explore half ONLY; nothing later is kept
        m1s[s] = m1
        print(f"  {s}: {len(m1):,} minutes up to {m1.index.max() if len(m1) else '-'}", flush=True)
    a = collect(m1s, ev)
    c = collect(m1s, ctl)
    md, meta = report(a, c, ev)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(md)
    a.to_csv(out / "events.csv.gz", index=False)
    (out / "summary.json").write_text(json.dumps({**meta, "events": len(a), "controls": len(c), "explore_end": str(SPLIT)}, indent=1))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="News event study, step 1 (explore 2021 → Nov 2023, descriptive)")
    ap.add_argument("--hist", default="data/history_x/seen_2021_2026")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    run(Path(a.hist), Path(a.out))
    print((Path(a.out) / "report.md").read_text())


if __name__ == "__main__":
    main()
