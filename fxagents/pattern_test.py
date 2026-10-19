"""Chart patterns, stage 2: do the classic patterns (fxagents/patterns.py) make money as entry signals? Frozen Oct 19 2026,
before any result.

    python -m fxagents.pattern_test --data dev_m1 --out data/year_test/patterns_dev_m1          (./fx.sh pattest)
    python -m fxagents.pattern_test --data holdout_m1 --frozen ...                                (passers only)

Instruments XAUUSD, NDQ, US30; 15m and 1h clock bars built from mid prices ((bid+ask)/2). Pattern definitions are the
overlay's, unchanged (ATR zigzag, ZZ_K = 1.5). What makes them tradable — and causal:

  • A pivot is only known at its confirmation bar (price has moved 1.5 ATR away from it). A pattern can trigger only
    at a bar ≥ the confirmation bar of its LAST pivot, and only on that bar's close. A close beyond the "failed" side
    first (same levels as the overlay) kills it. Deadline: 30 bars after the last pivot.
  • Entry: market at the next minute's open on the real bid/ask (buy at the ask, sell at the bid).
  • Stops and targets are fixed at entry and never move:
      double top / bottom   stop 0.1 ATR beyond the higher top (lower bottom); target = the measured move
                            (neckline ∓ height) or 1R, whichever is further (entry is past the neckline, so the
                            measured move alone is usually < 1R).
      head & shoulders      stop 0.1 ATR beyond the right shoulder; target = measured move (neckline ∓ head-to-neckline).
      (and inverse)         Again at least 1R.
      triangles, wedges,    trigger = a close beyond the pattern's line in its direction (symmetrical triangle: either
      channels              way); stop 0.1 ATR beyond the OPPOSITE line at the trigger bar; target 2R.
      flags                 causal version: a pole (≥ 3 ATR in ≤ 8 bars), then ≥ 5 consolidation bars (range ≤ 50% of
                            the pole, retrace ≤ 50%), trigger = the first close beyond the consolidation's extreme within
                            20 bars; stop 0.1 ATR beyond the consolidation's other extreme; target 2R.
    Every stop is at least 0.5 ATR from the trigger close (widened if closer). ATR = ATR(14) of the pattern's bars.
  • Exits: stop, target, a maximum hold of 30 bars of the pattern's timeframe, or 15:50 New York — whichever is first.
    A data gap > 60 min (the daily 17:00 break, weekends) exits at the last price before it.
  • Skipped: fills between 15:20 and 18:00 NY (too close to the flat), fills within 15 min of a scheduled USD release
    (FOMC/CPI/NFP/PPI), fills where the spread is > 20% of the stop distance. One trade at a time per instrument ×
    timeframe × pattern family.
  • Control: a coin-flip trade for every trade (same fill minute, random side, same stop distance, target R and hold).

Judged per pattern family (double, head & shoulders, triangle, wedge, channel, flag), all 3 instruments × 2 timeframes
pooled. Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, avg R > 0 in each half of
the period, and better than its coin-flip control. Six families are tested at once, so one may pass by luck: anything
that passes still has to pass the untouched holdout (--frozen, PASSED_DEV only) before it is considered.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .breakout_test import trade_row
from .gemini_smc import block_mask
from .gemini_test import MIN, Exits, manage, prep
from .patterns import FLAT, TOL_TOP, _line, atr14, zigzag
from .simple_rules import NY, PIP, load, pip_stats, stats

PASSED_DEV: set[str] = set()          # filled in after the dev_m1 run; nothing else is scored on holdout data
SYMBOLS = ("XAUUSD", "NDQ", "US30")
TFS = (15, 60)
FAMILIES = ("double", "hs", "triangle", "wedge", "channel", "flag")
TITLE = {"double": "Double top / bottom", "hs": "Head & shoulders (and inverse)", "triangle": "Triangles",
         "wedge": "Wedges", "channel": "Channels", "flag": "Flags"}
HORIZON, FLAG_MAX, MAX_HOLD_BARS = 30, 20, 30
BUF, MIN_STOP, MAX_SPREAD_FRAC = 0.1, 0.5, 0.20
WARMUP = 30
NO_FILL = (920, 1080)                 # NY minutes 15:20–18:00


# ── bars ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def bars(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    """Clock bars on mid; `end` = UTC ns at which the bar is complete."""
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"open": r["m_o"].first(), "high": r["m_h"].max(), "low": r["m_l"].min(),
                      "close": r["m_c"].last()}).dropna()
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    return b


# ── causal signals ────────────────────────────────────────────────────────────────────────────────────────────────────
def _scan(c, start, stop_at, up, dn, want):
    """First close in [start, stop_at] beyond a level → (bar, side) or None. want: +1 long only, −1 short only, 0 either.
    A close beyond the other side first (for want ≠ 0) kills the pattern."""
    f = lambda v, i: v(i) if callable(v) else v       # noqa: E731
    for i in range(start, min(len(c) - 1, stop_at) + 1):
        if c[i] > f(up, i):
            return (i, 1) if want >= 0 else None
        if c[i] < f(dn, i):
            return (i, -1) if want <= 0 else None
    return None


def signals(df: pd.DataFrame) -> list[dict]:
    """Every causal pattern signal in a bar frame: {family, kind, i (trigger bar), side, stop, target (None = 2R), atr}."""
    if len(df) < 30:
        return []
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    a = atr14(h, l, c)
    P = zigzag(h, l, a, conf=True)
    out: list[dict] = []

    def add(fam, kind, i, side, stop, target=None):
        if i < WARMUP:                                             # ATR(14) not settled yet
            return
        A = a[i]
        if side * (c[i] - stop) < MIN_STOP * A:                    # minimum stop distance from the trigger close
            stop = c[i] - side * MIN_STOP * A
        out.append({"family": fam, "kind": kind, "i": int(i), "side": int(side), "stop": float(stop),
                    "target": None if target is None else float(target), "atr": float(A)})

    for j in range(len(P)):
        # double top / bottom
        if j + 2 < len(P):
            (ia, pa, ka, _), (ib, pb, _, _), (ic, pc, _, cc) = P[j], P[j + 1], P[j + 2]
            A = a[ic]
            if 5 <= ic - ia <= 80 and abs(pa - pc) <= TOL_TOP * A:
                if ka == "H" and min(pa, pc) - pb >= 1.0 * A:
                    top = max(pa, pc)
                    s = _scan(c, max(cc, ic + 1), ic + HORIZON, top + 0.2 * A, pb, -1)
                    if s:
                        add("double", "double_top", s[0], -1, top + BUF * a[s[0]], pb - (top - pb))
                if ka == "L" and pb - max(pa, pc) >= 1.0 * A:
                    bot = min(pa, pc)
                    s = _scan(c, max(cc, ic + 1), ic + HORIZON, pb, bot - 0.2 * A, +1)
                    if s:
                        add("double", "double_bottom", s[0], 1, bot - BUF * a[s[0]], pb + (pb - bot))
        # head and shoulders (and inverse)
        if j + 4 < len(P):
            (i1, p1, k1, _), (j1, q1, _, _), (i2, p2, _, _), (j2, q2, _, _), (i3, p3, _, c3) = P[j:j + 5]
            A = a[i3]
            sg = 1 if k1 == "H" else -1
            s1, s2, s3, n1, n2 = (sg * x for x in (p1, p2, p3, q1, q2))
            if s2 - max(s1, s3) >= 0.5 * A and abs(s1 - s3) <= 1.0 * A and abs(n2 - n1) <= 1.0 * A and i3 - i1 <= 120:
                neck, _ = _line(j1, q1, j2, q2)
                if sg > 0:
                    s = _scan(c, max(c3, i3 + 1), i3 + HORIZON, p2, neck, -1)
                else:
                    s = _scan(c, max(c3, i3 + 1), i3 + HORIZON, neck, p2, +1)
                if s:
                    i = s[0]
                    add("hs", "head_shoulders" if sg > 0 else "inverse_head_shoulders", i, -sg,
                        p3 + sg * BUF * a[i], neck(i) - sg * (sg * (p2 - neck(i2))))
        # triangles, wedges, channels on 4 alternating pivots
        if j + 3 < len(P):
            quad = P[j:j + 4]
            H = [p for p in quad if p[2] == "H"]
            L = [p for p in quad if p[2] == "L"]
            i0, i1_, cq = quad[0][0], quad[-1][0], quad[-1][3]
            if len(H) == 2 and len(L) == 2 and i1_ - i0 >= 10:
                A = a[i1_]
                up, su = _line(H[0][0], H[0][1], H[1][0], H[1][1])
                lo, sl = _line(L[0][0], L[0][1], L[1][0], L[1][1])
                su, sl = su / A, sl / A
                inside = np.mean([lo(i) - 0.25 * A <= c[i] <= up(i) + 0.25 * A for i in range(i0, i1_ + 1)])
                if up(i1_) - lo(i1_) >= 0.5 * A and inside >= 0.8:
                    fu, fl = abs(su) < FLAT, abs(sl) < FLAT
                    conv = su - sl < -FLAT
                    par = abs(su - sl) <= 0.3 * max(abs(su), abs(sl), FLAT)
                    kind = fam = None
                    if fu and sl > FLAT:
                        kind, fam, d = "ascending_triangle", "triangle", 1
                    elif fl and su < -FLAT:
                        kind, fam, d = "descending_triangle", "triangle", -1
                    elif su < -FLAT and sl > FLAT:
                        kind, fam, d = "symmetrical_triangle", "triangle", 0
                    elif su > FLAT and sl > FLAT and conv:
                        kind, fam, d = "rising_wedge", "wedge", -1
                    elif su < -FLAT and sl < -FLAT and conv:
                        kind, fam, d = "falling_wedge", "wedge", 1
                    elif su > FLAT and sl > FLAT and par:
                        kind, fam, d = "channel_up", "channel", 1
                    elif su < -FLAT and sl < -FLAT and par:
                        kind, fam, d = "channel_down", "channel", -1
                    if kind:
                        s = _scan(c, max(cq, i1_ + 1), i1_ + HORIZON, up, lo, d)
                        if s:
                            i, sd = s
                            add(fam, kind, i, sd, lo(i) - BUF * a[i] if sd > 0 else up(i) + BUF * a[i])
    # flags, causal: decided bar by bar
    for sg in (1, -1):
        Hm, Lm, Cm = (h, l, c) if sg > 0 else (-l, -h, -c)
        i = 8
        while i < len(c) - 1:
            k0 = int(np.argmin(Cm[i - 8:i + 1])) + i - 8
            pole = Cm[i] - Cm[k0]
            if k0 >= i or pole < 3.0 * a[i]:
                i += 1
                continue
            hit = None
            for e in range(i + 1, min(len(c), i + FLAG_MAX + 2)):
                n = e - i - 1                                          # consolidation bars before e
                if n >= 5 and Cm[e] > Hm[i + 1:e].max():
                    hit = e
                    break
                if n + 1 > FLAG_MAX:
                    break
                seg_h, seg_l = Hm[i + 1:e + 1].max(), Lm[i + 1:e + 1].min()
                if seg_h - seg_l > 0.5 * pole or Cm[i] - seg_l > 0.5 * pole:
                    break
            if hit is not None:
                low_m = Lm[i + 1:hit].min()
                add("flag", "bull_flag" if sg > 0 else "bear_flag", hit, sg, sg * (low_m - BUF * a[hit]))
                i = hit
            i += 1
    return out


# ── execution ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def flat_index(a: dict, j: int) -> int:
    loc = a["idx"][j].tz_convert(NY)
    t = (pd.Timestamp(loc.date()) + pd.Timedelta(minutes=950)).tz_localize(NY)
    if t <= loc:
        t = (pd.Timestamp(loc.date()) + pd.Timedelta(days=1, minutes=950)).tz_localize(NY)
    return int(np.searchsorted(a["ns"], t.value))


def execute(a: dict, b: pd.DataFrame, sigs: list[dict], tf: int, blocked: np.ndarray, rng, sym: str):
    trades, ctl = [], []
    busy: dict[str, int] = {}
    ends = b["end"].to_numpy()
    gaps = np.nonzero(np.diff(a["ns"]) > 60 * MIN)[0] + 1           # first minute after each data gap
    for s in sorted(sigs, key=lambda x: x["i"]):
        j = int(np.searchsorted(a["ns"], ends[s["i"]]))               # first minute after the trigger bar closed
        if j >= len(a["ns"]) or j <= busy.get(s["family"], -1) or a["ns"][j] - ends[s["i"]] > 60 * MIN:
            continue
        if NO_FILL[0] <= a["mod"][j] < NO_FILL[1] or blocked[j]:
            continue
        side = s["side"]
        px = a["ask_o"][j] if side > 0 else a["bid_o"][j]
        risk = side * (px - s["stop"])
        spread = a["ask_o"][j] - a["bid_o"][j]
        if risk <= 0 or spread > MAX_SPREAD_FRAC * risk:
            continue
        tr = 2.0 if s["target"] is None else max(1.0, side * (s["target"] - px) / risk)
        ex = Exits(target_r=tr, time_after_min=MAX_HOLD_BARS * tf, time_min_r=1e9)
        jf = flat_index(a, j)
        g = int(np.searchsorted(gaps, j, side="right"))
        if g < len(gaps) and gaps[g] <= jf:
            jf = gaps[g] + 1                                       # the gap minute itself → "closure" exit before it
        jx, xp, why = manage(a, j, side, px, s["stop"], ex, jf)
        trades.append(trade_row(a, j, jx, side, px, xp, risk, spread, why, symbol=sym, tf=tf, family=s["family"],
                                kind=s["kind"], target_r=round(tr, 2)))
        busy[s["family"]] = jx
        cs = int(rng.choice([1, -1]))
        if j + 1 < jf:
            ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
            cjx, cpx, cwhy = manage(a, j + 1, cs, ce, ce - cs * risk, ex, jf)
            ctl.append(trade_row(a, j, cjx, cs, ce, cpx, risk, spread, cwhy, symbol=sym, tf=tf, family=s["family"],
                                 kind=s["kind"], target_r=round(tr, 2)))
    return trades, ctl


def run_symbol(path: Path, sym: str, rng) -> tuple[list, list, pd.DatetimeIndex]:
    m1 = load(path)
    a = prep(m1)
    blk = block_mask(a, 15, 15)
    T, C = [], []
    for tf in TFS:
        b = bars(m1, tf)
        t, c = execute(a, b, signals(b), tf, blk, rng, sym)
        T += t
        C += c
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return T, C, days[days.dayofweek < 5].tz_localize(NY)


def judge(X: pd.DataFrame, Cx: pd.DataFrame, days, mid) -> dict:
    st = stats(X, days) if len(X) else {"trades": 0}
    if not len(X):
        return st
    et = pd.to_datetime(X.entry_time)
    h1, h2 = X[et < mid].R.mean(), X[et >= mid].R.mean()
    cst = stats(Cx, days) if len(Cx) else {"avg_R": float("nan")}
    st |= {"h1": float(h1) if len(X[et < mid]) else float("nan"), "h2": float(h2) if len(X[et >= mid]) else float("nan"),
           "ctl_avg_R": cst.get("avg_R", float("nan")), "ctl_trades": len(Cx)}
    st["passed"] = bool(st.get("pass") and st["h1"] > 0 and st["h2"] > 0 and st["avg_R"] > st["ctl_avg_R"])
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dev_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frozen", action="store_true", help="holdout: score only PASSED_DEV families")
    ap.add_argument("--seed", type=int, default=29)
    a_ = ap.parse_args()
    rng = np.random.default_rng(a_.seed)
    a_.out.mkdir(parents=True, exist_ok=True)
    src = Path("data/export") / a_.data
    T, C, days = [], [], pd.DatetimeIndex([], tz=NY)
    for sym in SYMBOLS:
        f = src / f"{sym}_M1.csv.gz"
        if not f.exists():
            print(f"  {sym}: no {f}", flush=True)
            continue
        t, c, d = run_symbol(f, sym, rng)
        T += t
        C += c
        days = days.union(d)
        print(f"  {sym}: {len(t)} trades", flush=True)
    T, C = pd.DataFrame(T), pd.DataFrame(C)
    if not len(T):
        raise SystemExit("no trades — is the export there?")
    T.to_csv(a_.out / "trades.csv.gz", index=False)
    C.to_csv(a_.out / "control.csv.gz", index=False)
    fams = [f for f in FAMILIES if not a_.frozen or f in PASSED_DEV]
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    md = [f"# Chart patterns as entry signals — stage 2 ({a_.data}{', frozen' if a_.frozen else ''})", "",
          f"{et.min():%Y-%m-%d} → {et.max():%Y-%m-%d}. XAUUSD, NDQ, US30 on 15m and 1h bars. Pattern definitions are the "
          "chart overlay's, unchanged; the signal is causal (the last pivot must be confirmed, entry on the next minute "
          "after the trigger bar's close), stops and targets fixed at entry, exit at the stop, the target, 30 bars or "
          "15:50 NY. Real OANDA bid/ask fills; R includes the spread. Rules frozen in fxagents/pattern_test.py before "
          "this run.", "",
          "Pass (per family, everything pooled) = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× "
          "costs, positive in both halves of the period, and better than the coin-flip control. Six families are tested "
          "at once, so a pass is only a candidate for the untouched holdout.", "",
          "| Family | Verdict | Trades | Win | Avg R | 95% range | Avg R 2× costs | 1st half | 2nd half | Coin-flip avg R | Total R |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    rows, detail = [], []
    for fam in fams:
        X, Cx = T[T.family == fam], C[C.family == fam] if len(C) else C
        st = judge(X, Cx, days, mid)
        rows.append({"family": fam, **{k: v for k, v in st.items() if not isinstance(v, (list, dict))}})
        if not st.get("trades"):
            md.append(f"| {TITLE[fam]} | — | 0 |" + " |" * 8)
            continue
        md.append(f"| {TITLE[fam]} | **{'PASS' if st['passed'] else 'no pass'}** | {st['trades']} | {st['win']:.0%} | "
                  f"{st['avg_R']:+.3f} | {st['ci_lo']:+.2f} to {st['ci_hi']:+.2f} | {st['avg_R_2x']:+.3f} | "
                  f"{st['h1']:+.3f} | {st['h2']:+.3f} | {st['ctl_avg_R']:+.3f} | {st['total_R']:+.1f} |")
    md += ["", "## By instrument × timeframe (avg R, trades)", "",
           "| Family | " + " | ".join(f"{s} {tf}m" for s in SYMBOLS for tf in TFS) + " |",
           "|---|" + "---|" * (len(SYMBOLS) * len(TFS))]
    for fam in fams:
        cells = []
        for s in SYMBOLS:
            for tf in TFS:
                x = T[(T.family == fam) & (T.symbol == s) & (T.tf == tf)]
                cells.append(f"{x.R.mean():+.3f} ({len(x)})" if len(x) else "— (0)")
        md.append(f"| {TITLE[fam]} | " + " | ".join(cells) + " |")
    md += ["", "## By pattern and direction (avg R, trades)", "", "| Pattern | Long | Short | Exit reasons |", "|---|---|---|---|"]
    for kind, x in T.groupby("kind"):
        lo_, sh_ = x[x.side > 0], x[x.side < 0]
        why = ", ".join(f"{k} {v:.0%}" for k, v in x.exit_reason.value_counts(normalize=True).items())
        md.append(f"| {kind.replace('_', ' ')} | {f'{lo_.R.mean():+.3f} ({len(lo_)})' if len(lo_) else '—'} | "
                  f"{f'{sh_.R.mean():+.3f} ({len(sh_)})' if len(sh_) else '—'} | {why} |")
    for sym in SYMBOLS:
        x = T[T.symbol == sym]
        if len(x):
            ps = pip_stats(x, PIP[sym])
            detail.append(f"{sym}: {len(x)} trades, net {ps['pips_net']:+,.0f} pips after spread")
    md += ["", "Pips (all families): " + "; ".join(detail) + ".", ""]
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
