"""Gold scalp: 15m trend → 5m breakout-and-retest → 3m confirmation (an outside suggestion, Sam 2026-10-19), coded as
specified and frozen before any result.

    python -m fxagents.gold_scalp --data dev_m1 --out data/year_test/gold_scalp_dev_m1        (./fx.sh scalp)
    python -m fxagents.gold_scalp --data holdout_m1 --frozen ...                               (only if it passed)

The spec, and how each open point is fixed here (Oct 19 2026, before testing):
  Direction 15m   trade with the EMA20/EMA50 trend: long only while EMA20 > EMA50 on the last CLOSED 15m mid candle,
                  short only while EMA20 < EMA50.
  Setup 5m        breakout = a 5m candle CLOSES beyond the high (low) of the 12 candles before it. Retest = within the
                  next 6 candles (30 min), a candle trades back to the broken level (low ≤ level + 0.1 ATR) and closes
                  on the breakout side; a close back through the level first kills the setup.
  Entry 3m        "a completed candle confirms continuation" = within 10 min of the retest candle's close, a 3m candle
                  closes beyond the retest candle's high (low). A 3m close beyond the retest extreme first cancels.
                  Fill: market at the next minute's open on the real bid/ask.
  Stop            beyond the retest extreme (lowest low from the candle after the breakout through the retest candle;
                  mirror for shorts) by 0.25 × ATR(14) of the 5m candles. Never moves.
  Target          2 × the chart stop distance D (from the 3m confirmation close to the stop). Kept only if, after the
                  entry spread c, (2D − c) / (D + c) ≥ 1.5.
  Cost filter     c ≤ 20% of D (c = spread at the fill minute). With this filter the 1.5:1 check always holds; both
                  are applied as written.
  Time exit       30 minutes after the fill, at that minute's price, if neither stop nor target was hit.
  Risk            0.25% per trade is sizing only — results are in R, so it doesn't change them. "Stop after two
                  consecutive losses" = no more trades that trading day (18:00 → 17:00 NY) after two losses in a row.
  Excluded        entries 16:00–18:30 NY (the 17:00 rollover), within 15 min of a scheduled USD release (FOMC, CPI,
                  NFP, PPI), and data gaps. One trade at a time.
  Controls        coin-flip (same minute, random side, same stop distance, target R and 30-min exit) and the same
                  rule WITHOUT the 15m trend filter (does the filter help?).

Gold only (XAUUSD). Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in
both halves of the period, better than the coin flip and better than the no-trend-filter version. Holdout only if it
passes (PASSED_DEV), unchanged.
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
from .simple_rules import NY, PIP, ema, load, pip_stats, stats, wilder

PASSED_DEV = False
LOOKBACK, RETEST_BARS, CONFIRM_MIN, HOLD_MIN = 12, 6, 10, 30
TOUCH, BUF = 0.1, 0.25
COST_FRAC, MIN_RR = 0.20, 1.5
NO_ENTRY = (960, 1110)               # NY minutes 16:00–18:30


def candles(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last(), "n": r["m_c"].count()}).dropna()
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    b["start"] = b.index.as_unit("ns").asi8
    return b


def setups(m1: pd.DataFrame, trend_filter: bool = True) -> list[dict]:
    """Causal entry decisions: {t_ns (confirmation 3m close time), side, stop, target, D}."""
    b5, b3 = candles(m1, 5), candles(m1, 3)
    c15 = m1["m_c"].resample("15min", label="right", closed="left").last().dropna()
    e20, e50 = ema(c15, 20).to_numpy(), ema(c15, 50).to_numpy()
    e15_end = c15.index.as_unit("ns").asi8
    pc = b5.c.shift()
    tr = pd.concat([b5.h - b5.l, (b5.h - pc).abs(), (b5.l - pc).abs()], axis=1).max(axis=1)
    atr = wilder(tr, 14).to_numpy()
    H5, L5, C5, S5, E5 = (b5[k].to_numpy() for k in ("h", "l", "c", "start", "end"))
    H3, L3, C3, S3, E3 = (b3[k].to_numpy() for k in ("h", "l", "c", "start", "end"))
    out = []
    for k in range(LOOKBACK + 14, len(b5) - 1):
        if S5[k] - S5[k - LOOKBACK] > (LOOKBACK + 6) * 5 * MIN:     # the 12 candles must be (nearly) continuous
            continue
        i15 = int(np.searchsorted(e15_end, E5[k], side="right")) - 1
        if i15 < 50 or not np.isfinite(e50[i15]):
            continue
        trend = 1 if e20[i15] > e50[i15] else -1 if e20[i15] < e50[i15] else 0
        for side in (1, -1):
            if trend_filter and side != trend:
                continue
            hi, lo, cl = (H5, L5, C5) if side > 0 else (-L5, -H5, -C5)  # mirrored: the long logic serves both
            level = hi[k - LOOKBACK:k].max()
            if cl[k] <= level:
                continue
            A = atr[k]
            r_found = None
            for r in range(k + 1, min(len(b5), k + 1 + RETEST_BARS)):
                if S5[r] - E5[r - 1] > 30 * MIN:
                    break
                if lo[r] <= level + TOUCH * A and cl[r] > level:
                    r_found = r
                    break
                if cl[r] < level:
                    break
            if r_found is None:
                continue
            r = r_found
            ext = lo[k + 1:r + 1].min()                                 # retest extreme (mirrored)
            j0 = int(np.searchsorted(S3, E5[r]))
            conf = None
            while j0 < len(b3) and E3[j0] <= E5[r] + CONFIRM_MIN * MIN:
                c3 = C3[j0] * side
                if c3 > hi[r]:
                    conf = j0
                    break
                if c3 < ext:
                    break
                j0 += 1
            if conf is None:
                continue
            stop_m = ext - BUF * atr[r]
            D = C3[conf] * side - stop_m
            if D <= 0:
                continue
            out.append({"t_ns": int(E3[conf]), "side": side, "stop": float(side * stop_m),
                        "target": float(side * (C3[conf] * side + 2 * D)), "D": float(D), "trend": trend})
    out.sort(key=lambda x: x["t_ns"])
    return out


def session_day(ts) -> object:
    return (ts.tz_convert(NY) + pd.Timedelta(hours=6)).date()          # 18:00 NY starts the next trading day


def execute(a: dict, sets: list[dict], blocked: np.ndarray, rng, two_loss_stop: bool = True):
    trades, ctl = [], []
    busy = -1
    gaps = np.nonzero(np.diff(a["ns"]) > 60 * MIN)[0] + 1
    streak: dict = {}
    for s in sets:
        j = int(np.searchsorted(a["ns"], s["t_ns"]))
        if j >= len(a["ns"]) or j <= busy or a["ns"][j] - s["t_ns"] > 5 * MIN:
            continue
        if NO_ENTRY[0] <= a["mod"][j] < NO_ENTRY[1] or blocked[j]:
            continue
        day = session_day(a["idx"][j])
        if two_loss_stop and streak.get(day, 0) >= 2:
            continue
        side = s["side"]
        px = a["ask_o"][j] if side > 0 else a["bid_o"][j]
        c = a["ask_o"][j] - a["bid_o"][j]
        D = s["D"]
        if c > COST_FRAC * D or (2 * D - c) / (D + c) < MIN_RR:
            continue
        risk = side * (px - s["stop"])
        if risk <= 0:
            continue
        tr = side * (s["target"] - px) / risk
        if tr <= 0:
            continue
        jf = int(np.searchsorted(a["ns"], a["ns"][j] + (HOLD_MIN + 1) * MIN))
        g = int(np.searchsorted(gaps, j, side="right"))
        if g < len(gaps) and gaps[g] <= jf:
            jf = gaps[g] + 1
        ex = Exits(target_r=tr, time_after_min=HOLD_MIN, time_min_r=1e9)
        jx, xp, why = manage(a, j, side, px, s["stop"], ex, min(jf, len(a["ns"])))
        row = trade_row(a, j, jx, side, px, xp, risk, c, why, D=D, target_r=round(tr, 3))
        trades.append(row)
        busy = jx
        streak[day] = streak.get(day, 0) + 1 if row["R"] <= 0 else 0
        cs = int(rng.choice([1, -1]))
        if j + 1 < jf:
            ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
            cjx, cpx, cwhy = manage(a, j + 1, cs, ce, ce - cs * risk, ex, min(jf, len(a["ns"])))
            ctl.append(trade_row(a, j, cjx, cs, ce, cpx, risk, c, cwhy))
    return trades, ctl


def judge(X: pd.DataFrame, days, mid) -> dict:
    st = stats(X, days) if len(X) else {"trades": 0}
    if len(X):
        et = pd.to_datetime(X.entry_time)
        a, b = X[et < mid], X[et >= mid]
        st |= {"h1": float(a.R.mean()) if len(a) else float("nan"), "h2": float(b.R.mean()) if len(b) else float("nan")}
        st |= pip_stats(X, PIP["XAUUSD"])
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dev_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--seed", type=int, default=31)
    a_ = ap.parse_args()
    if a_.frozen and not PASSED_DEV:
        raise SystemExit("the scalp did not pass on dev data — the holdout stays untouched")
    a_.out.mkdir(parents=True, exist_ok=True)
    m1 = load(Path("data/export") / a_.data / "XAUUSD_M1.csv.gz")
    a = prep(m1)
    blk = block_mask(a, 15, 15)
    rng = np.random.default_rng(a_.seed)
    tr, ctl = execute(a, setups(m1, True), blk, rng)
    nt, _ = execute(a, setups(m1, False), blk, rng)
    T, C, N = pd.DataFrame(tr), pd.DataFrame(ctl), pd.DataFrame(nt)
    if not len(T):
        raise SystemExit("no trades")
    for nm, X in (("trades", T), ("control", C), ("no_trend", N)):
        X.to_csv(a_.out / f"{nm}.csv.gz", index=False)
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    days = days[days.dayofweek < 5].tz_localize(NY)
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    res = {"rule": judge(T, days, mid), "coin-flip control": judge(C, days, mid),
           "no 15m trend filter": judge(N, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and r["avg_R"] > res["coin-flip control"].get("avg_R", -9)
              and r["avg_R"] > res["no 15m trend filter"].get("avg_R", -9))
    md = [f"# Gold scalp: 15m trend → 5m breakout + retest → 3m confirmation ({a_.data}) — **{'PASS' if ok else 'no pass'}**", "",
          f"{et.min():%Y-%m-%d} → {et.max():%Y-%m-%d}, XAUUSD. Rules as given (Oct 19 2026); open points fixed in "
          "fxagents/gold_scalp.py before this run. Real OANDA bid/ask fills; R includes the spread (\"2× costs\" pays "
          "one more spread). Stop beyond the retest extreme + 0.25 ATR(5m), target 2× the chart stop, 30-minute time exit, "
          "spread ≤ 20% of the stop, no trades after two straight losses in a day, no entries 16:00–18:30 NY or near "
          "USD releases.", "",
          "Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, "
          "better than the coin flip and than the same rule without the 15m trend filter.", "",
          "| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, s in res.items():
        if not s.get("trades"):
            md.append(f"| {nm} | 0 |" + " |" * 9)
            continue
        md.append(f"| {'**rule**' if nm == 'rule' else nm} | {s['trades']} | {s['win']:.0%} | {s['avg_R']:+.3f} | "
                  f"{s['ci_lo']:+.2f} to {s['ci_hi']:+.2f} | {s['avg_R_2x']:+.3f} | {s['h1']:+.3f} | {s['h2']:+.3f} | "
                  f"{s['total_R']:+.1f} | {s['pips_net']:+,.0f} | {s['hold_min_median']:.0f} min |")
    loc = et.dt.tz_convert(NY)
    hrs = loc.dt.hour
    sess = np.where((hrs >= 18) | (hrs < 2), "Asia 18–02", np.where(hrs < 8, "London 02–08",
                    np.where(hrs < 12, "NY morning 08–12", "NY afternoon 12–16")))
    md += ["", "## Where it trades", "", "| Session (NY time) | Trades | Win | Avg R |", "|---|---|---|---|"]
    for sname, x in T.groupby(sess):
        md.append(f"| {sname} | {len(x)} | {(x.R > 0).mean():.0%} | {x.R.mean():+.3f} |")
    md += ["", "| Side | Trades | Avg R |", "|---|---|---|"]
    for sd, x in T.groupby("side"):
        md.append(f"| {'long' if sd > 0 else 'short'} | {len(x)} | {x.R.mean():+.3f} |")
    why = ", ".join(f"{k} {v:.0%}" for k, v in T.exit_reason.value_counts(normalize=True).items())
    md += ["", f"Exits: {why}. Typical chart stop: {T.D.median():.2f} (median), {T.D.quantile(.25):.2f}–"
           f"{T.D.quantile(.75):.2f} (middle half); typical entry spread {(T.cost_R * T.atr).median():.2f}, "
           f"= {T.cost_R.median():.0%} of the stop.", ""]
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "pass": ok, "rows": res}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
