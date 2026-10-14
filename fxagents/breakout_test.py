"""Gold Breakout 15M (WillyAlgoTrader, TradingView, open source) on OANDA bid/ask exports. Rules fixed before testing
(Sam asked for it 2026-10-14, plus earlier close times to shorten the hold).

    python -m fxagents.breakout_test --data dev_m1 --out data/year_test/breakout_dev_m1

The author's defaults, as published:
  broker time  fixed GMT+3 (no DST). Broker day = 00:00–24:00 GMT+3 (21:00 UTC → 21:00 UTC).
  range        highest high / lowest low of the bars opening 00:00–06:59 broker time (mid prices).
               The first day of the file is skipped.
  entry        from 07:00, a buy stop at the range high and a sell stop at the range low, one-cancels-other; one trade
               per broker day; no entries at or after the close hour. Longs fill at the ASK when it reaches the range
               high (at the minute's open if it gaps through), shorts at the BID.
  stop         "pct": 1.0% of the fill price (default) · "range": the opposite side of the range (option on the page).
  target       none. Exit at the stop or at the close hour (default 20:00 broker = 17:00 UTC), whichever is first.
Earlier close hours (Sam: "see if we can reduce the time"), fixed here before any result: 12:00, 14:00, 16:00 broker
(09:00, 11:00, 13:00 UTC). The default (20:00, pct stop, gold) is the primary result; the rest are extra looks, so a
lone pass among them is weaker evidence.

R = stop distance at entry. One spread per round trip is in R through the real fills; "2× costs" pays one more.
Holdout (--frozen): only the cells that passed on dev_m1 (2026-10-14) are scored, unchanged — gold, 1% stop at the 20:00
(primary) and 16:00 closes, and the range-boundary stop at 20:00 — each with its control. Nothing else runs on holdout data.

Control: at the same minute as each breakout fill, a coin-flip direction with the same stop distance and close.
If the breakout direction carries information, the rule beats its control.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .simple_rules import NY, PIP, load, pip_stats, stats

SYMS = ["XAUUSD", "NDQ", "US30"]
BROKER_UTC_OFFSET = 3                     # hours (fixed GMT+3)
RANGE_END = 7 * 60                        # range bars open 00:00–06:59 broker → minutes [0, 420)
SL_PCT = 1.0
CLOSE_HOURS = (20, 16, 14, 12)            # broker time; 20 = the author's default
FROZEN = [("XAUUSD", "pct", 20), ("XAUUSD", "pct", 16), ("XAUUSD", "range", 20)]   # dev_m1 passers, 2026-10-14
STOP_MODES = ("pct", "range")
MIN_RANGE_MIN = 60                        # need at least an hour of range data (Mondays open ~01:00 broker)


def to_broker(idx: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Broker-day number and minute of the broker day for every UTC timestamp."""
    ns = idx.as_unit("ns").asi8 + BROKER_UTC_OFFSET * 3_600_000_000_000
    mins = ns // 60_000_000_000
    return mins // 1440, mins % 1440


def exit_walk(a: dict, j0: int, j_end: int, side: int, stop: float) -> tuple[int, float, str]:
    """First stop hit from minute j0 up to (not including) j_end; else out at j_end's open (time) or at the last price
    before a closure gap > 60 min. Long exits on the bid, short exits on the ask; a gap through the stop fills at
    the open."""
    t = a["ns"]
    j_end = min(j_end, len(t))
    # include the step into j_end: a market closed before the close hour (holiday) must not exit next session
    gaps = np.nonzero(np.diff(t[j0:j_end + 1]) > 60 * 60_000_000_000)[0]
    stop_end = j0 + int(gaps[0]) + 1 if len(gaps) else j_end    # minutes before the first closure
    hit = (a["bid_l"][j0:stop_end] <= stop) if side > 0 else (a["ask_h"][j0:stop_end] >= stop)
    if hit.any():
        j = j0 + int(np.argmax(hit))
        op = a["bid_o"][j] if side > 0 else a["ask_o"][j]
        px = stop if j == j0 else (min(stop, op) if side > 0 else max(stop, op))
        return j, px, "stop"
    if len(gaps):
        j = stop_end - 1
        return j, (a["bid_c"][j] if side > 0 else a["ask_c"][j]), "closure"
    if j_end >= len(t):
        j = len(t) - 1
        return j, (a["bid_c"][j] if side > 0 else a["ask_c"][j]), "end"
    return j_end, (a["bid_o"][j_end] if side > 0 else a["ask_o"][j_end]), "time"


def trade_row(a, j0, jx, side, entry, px, risk, spread, why, **extra) -> dict:
    pts = side * (px - entry)
    return {"entry_time": a["idx"][j0], "exit_time": a["idx"][jx], "side": side, "entry": entry, "exit": px,
            "atr": risk, "points": pts, "R": pts / risk, "R_2x": (pts - spread) / risk, "cost_R": spread / risk,
            "exit_reason": why, "hold_min": (a["ns"][jx] - a["ns"][j0]) / 60e9, "overnight": False, **extra}


def run(m1: pd.DataFrame, close_hour: int, stop_mode: str, rng) -> tuple[list, list]:
    a = {k: m1[k].to_numpy() for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
                                        "m_h", "m_l")}
    a["idx"], a["ns"] = m1.index, m1.index.as_unit("ns").asi8
    bday, bmin = to_broker(m1.index)
    starts = np.r_[0, np.nonzero(np.diff(bday))[0] + 1]
    ends = np.r_[starts[1:], len(bday)]
    close_min = close_hour * 60
    trades, ctl = [], []
    for k, (s0, e0) in enumerate(zip(starts, ends)):
        if k == 0:
            continue                                            # first day of loaded history: range may be partial
        mins = bmin[s0:e0]
        rng_n = int(np.searchsorted(mins, RANGE_END))
        if rng_n < MIN_RANGE_MIN:
            continue
        rh, rl = a["m_h"][s0:s0 + rng_n].max(), a["m_l"][s0:s0 + rng_n].min()
        t0 = s0 + rng_n                                         # first minute at/after 07:00
        t1 = s0 + int(np.searchsorted(mins, close_min))         # first minute at/after the close hour
        if t1 <= t0:
            continue
        up = a["ask_h"][t0:t1] >= rh
        dn = a["bid_l"][t0:t1] <= rl
        iu = int(np.argmax(up)) if up.any() else None
        idn = int(np.argmax(dn)) if dn.any() else None
        if iu is None and idn is None:
            continue
        if idn is None or (iu is not None and iu < idn):
            side, j = 1, t0 + iu
        elif iu is None or idn < iu:
            side, j = -1, t0 + idn
        else:                                                   # both levels touched in the same minute
            o = (a["ask_o"][t0 + iu] + a["bid_o"][t0 + iu]) / 2  # take the side nearer the minute's open
            side, j = (1, t0 + iu) if (rh - o) <= (o - rl) else (-1, t0 + idn)
        if side > 0:
            entry = max(rh, a["ask_o"][j])
        else:
            entry = min(rl, a["bid_o"][j])
        spread = a["ask_o"][j] - a["bid_o"][j]
        if stop_mode == "pct":
            stop = entry * (1 - side * SL_PCT / 100)
        else:
            stop = (rl - spread / 2) if side > 0 else (rh + spread / 2)   # opposite boundary, on the exit side
        risk = side * (entry - stop)
        if not risk > 0:
            continue
        jx, px, why = exit_walk(a, j, t1, side, stop)
        trades.append(trade_row(a, j, jx, side, entry, px, risk, spread, why,
                                range_width=rh - rl, entry_bmin=int(bmin[j])))
        # coin-flip control: same minute (enters at that minute's close), same stop distance, same close hour
        cs = int(rng.choice([1, -1]))
        if j + 1 < t1:
            ce = a["ask_c"][j] if cs > 0 else a["bid_c"][j]
            cstop = ce - cs * risk
            jx, px, why = exit_walk(a, j + 1, t1, cs, cstop)
            ctl.append(trade_row(a, j, jx, cs, ce, px, risk, spread, why))
    return trades, ctl


def side_avg(T: pd.DataFrame, s: int) -> str:
    g = T[T.side == s]
    return f"{g.R.mean():+.3f} ({len(g)})" if len(g) else "— (0)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="export name under data/export/")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--frozen", action="store_true", help="score only the dev_m1 passers (required on holdout data)")
    a = ap.parse_args()
    if a.data.startswith("holdout") and not a.frozen:
        raise SystemExit("holdout data is scored only with --frozen (the dev_m1 passers, unchanged)")
    cells = FROZEN if a.frozen else [(s_, m_, h_) for s_ in SYMS for m_ in STOP_MODES for h_ in CLOSE_HOURS]
    src = Path("data/export") / a.data
    a.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    rows, allt = [], []
    for sym in SYMS:
        f = src / f"{sym}_M1.csv.gz"
        if not f.exists() or not any(c[0] == sym for c in cells):
            continue
        m1 = load(f)
        days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).normalize())))
        days = days[days.dayofweek < 5]
        for stop_mode in STOP_MODES:
            for ch in CLOSE_HOURS:
                if (sym, stop_mode, ch) not in cells:
                    continue
                tr, ctl = run(m1, ch, stop_mode, rng)
                for name, t in (("breakout", tr), ("coin-flip control", ctl)):
                    T = pd.DataFrame(t)
                    st = stats(T, days) if len(T) else {"trades": 0}
                    if len(T):
                        st |= pip_stats(T, PIP.get(sym, 1.0))
                        st["long"], st["short"] = side_avg(T, 1), side_avg(T, -1)
                        st["stopped"] = float((T.exit_reason == "stop").mean())
                    key = {"symbol": sym, "stop": "1% of entry" if stop_mode == "pct" else "range boundary",
                           "close": f"{ch:02d}:00", "rule": name,
                           "primary": sym == "XAUUSD" and stop_mode == "pct" and ch == 20 and name == "breakout"}
                    rows.append({**key, **st})
                    if len(T):
                        allt.append(T.assign(**{k: v for k, v in key.items() if k != "primary"}))
                    print(f"  {sym:6s} {key['stop']:14s} close {key['close']} {name:17s} {st.get('trades', 0):4d} trades  "
                          f"avg {st.get('avg_R', float('nan')):+.3f}R  95% [{st.get('ci_lo', float('nan')):+.3f}, "
                          f"{st.get('ci_hi', float('nan')):+.3f}]", flush=True)
        del m1
    if allt:
        pd.concat(allt, ignore_index=True).to_csv(a.out / "trades.csv.gz", index=False)
    main_rows = [r for r in rows if r["rule"] == "breakout"]
    npass = sum(bool(r.get("pass")) for r in main_rows)
    prim = next((r for r in rows if r["primary"]), {})
    pv = ("—" if not prim.get("trades") else
          f"{prim['trades']} trades, avg {prim['avg_R']:+.3f}R (95% {prim['ci_lo']:+.2f} to {prim['ci_hi']:+.2f}), "
          f"2× costs {prim['avg_R_2x']:+.3f}R → {'PASS' if prim.get('pass') else 'no pass'}")
    md = [f"# Gold Breakout 15M (WillyAlgoTrader) on {a.data}" + (" — frozen dev passers only" if a.frozen else ""), "",
          "Author's defaults (fxagents/breakout_test.py docstring): range = high/low 00:00–07:00 GMT+3; from 07:00 a buy stop "
          "at the range high and a sell stop at the range low (one cancels the other, one trade a day); stop 1% of entry "
          "(or the opposite side of the range); no target; flat at the close hour (default 20:00 GMT+3 = 17:00 UTC). "
          "Earlier closes (12/14/16:00 GMT+3) added to shorten the hold. Real OANDA bid/ask fills; R includes the spread.", "",
          f"**Primary (gold, 1% stop, 20:00 close): {pv}.**", "",
          f"Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. **{npass} of {len(main_rows)} "
          "cells pass.** The coin-flip control enters at the same minute in a random direction with the same stop and "
          "close: the breakout only adds something if it beats its control.", "",
          "| Symbol | Stop | Close (GMT+3) | Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) "
          "| Stopped | Median hold (h) | Long avg R (n) | Short avg R (n) | Thirds | Net pips | Pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lab = f"**{r['rule']}**" if r["primary"] else r["rule"]
        if not r.get("trades"):
            md.append(f"| {r['symbol']} | {r['stop']} | {r['close']} | {lab} | 0 |" + " |" * 13)
            continue
        th = " / ".join(f"{x:+.2f}" for x in r["thirds"])
        md.append(f"| {r['symbol']} | {r['stop']} | {r['close']} | {lab} | {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | "
                  f"{r['ci_lo']:+.2f} to {r['ci_hi']:+.2f} | {r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['cost_R']:.3f} | "
                  f"{r['stopped']:.0%} | {r['hold_min_median'] / 60:.1f} | {r['long']} | {r['short']} | {th} | "
                  f"{r['pips_net']:+,.0f} | {'**PASS**' if r.get('pass') and r['rule'] == 'breakout' else 'no'} |")
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"data": a.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md[:8]))


if __name__ == "__main__":
    main()
