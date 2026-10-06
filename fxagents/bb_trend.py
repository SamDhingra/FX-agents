"""Bollinger trend-continuation (as posted for NQ), backtested exactly as written.

    python -m fxagents.bb_trend NDQ                 # on the ~90-day cache
    python -m fxagents.bb_trend NDQ --days 365      # on data/history_365d (./fx.sh yeartest fetches it)
    ./fx.sh bbtest NDQ XAUUSD                       # on the server, 365 days, report published to GitHub

Rules:
  • Bollinger Bands (20, 2) on 5m, 15m and 1h, taken from the LAST CLOSED candle of each (no repainting)
  • a 1m candle that CLOSES above ≥2 of the 3 upper bands → long; below ≥2 of the 3 lower bands → short
  • stop at the 5m basis (the 20-period mean of the last closed 5m candle), target 1R, nothing else
  • entries only 08:00–12:00 New York; 10 one-minute candles of cooldown after every exit
Execution (OANDA-style, on 1m mid candles): entry at the signal candle's close on the far side of the
spread, stop and target trigger on the bid (longs) / ask (shorts); a candle that touches both counts as a
stop (the conservative read); anything still open at 15:50 is closed at market. One position at a time.
Costs: the full spread is paid per round trip (`--spread`, default the OANDA estimate in research.py;
`--costs raw` uses research.RAW_SPREAD). The posted 71% / PF 3.24 almost certainly had no costs, so the
report shows both.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .research import DEFAULT_SPREAD, RAW_SPREAD, history_dir


def bands_closed(m1: pd.DataFrame, rule: str, n: int = 20, k: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Upper / basis / lower of the last CLOSED `rule` candle, aligned to each 1m candle's close."""
    c = m1["close"].resample(rule, label="left", closed="left").last().dropna()
    mid = c.rolling(n, min_periods=n).mean()
    sd = c.rolling(n, min_periods=n).std(ddof=0)            # TradingView's BB uses the population stdev
    known = pd.DataFrame({"u": mid + k * sd, "m": mid, "l": mid - k * sd})
    known.index = known.index + pd.Timedelta(rule)           # usable once that candle has closed
    close_ts = m1.index + pd.Timedelta("1min")
    u = known.index.union(close_ts)
    x = known.reindex(u).ffill().reindex(close_ts)
    return x["u"].to_numpy(), x["m"].to_numpy(), x["l"].to_numpy()


def backtest(m1: pd.DataFrame, spread: float, start="08:00", end="12:00", need=2, cooldown=10, rr=1.0,
             flatten="15:50", tfs=("5min", "15min", "1h"), trail_basis: bool = False) -> pd.DataFrame:
    """trail_basis=True: the stop follows the 5m basis as each 5m candle closes (only toward profit) —
    the other reading of "stop at the 5m basis"; the 1R target stays where it was set."""
    O, H, L, C = (m1[c].to_numpy(float) for c in ("open", "high", "low", "close"))
    B = [bands_closed(m1, tf) for tf in tfs]
    up = sum((C > b[0]).astype(int) for b in B)
    dn = sum((C < b[2]).astype(int) for b in B)
    basis5 = B[0][1]
    ct = m1.index + pd.Timedelta("1min")
    mins = np.asarray(ct.hour * 60 + ct.minute)
    sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":")); fh, fm = map(int, flatten.split(":"))
    in_win = (mins > sh * 60 + sm) & (mins <= eh * 60 + em)
    flat = (mins >= fh * 60 + fm) & (mins < 17 * 60)
    hs = spread / 2
    rows, i, n = [], 0, len(C)
    free_from = 0
    while i < n - 1:
        if i < free_from or not in_win[i] or not np.isfinite(basis5[i]):
            i += 1
            continue
        side = 1 if up[i] >= need else -1 if dn[i] >= need else 0
        if side == 0:
            i += 1
            continue
        entry = C[i] + side * hs
        stop = basis5[i]
        risk = (entry - stop) * side
        if risk <= 0:
            i += 1
            continue
        tgt = entry + side * rr * risk
        j, out, why = i + 1, None, None
        while j < n:
            if trail_basis and np.isfinite(basis5[j - 1]) and (basis5[j - 1] - stop) * side > 0:
                stop = basis5[j - 1]
            lo_b = (L[j] - hs) if side > 0 else (H[j] + hs)     # bid low (long) / ask high (short)
            hi_b = (H[j] - hs) if side > 0 else (L[j] + hs)     # bid high (long) / ask low (short)
            if (lo_b - stop) * side <= 0:
                op = O[j] - side * hs
                out, why = (op if (op - stop) * side < 0 else stop), "stop"
                break
            if (hi_b - tgt) * side >= 0:
                op = O[j] - side * hs
                out, why = (op if (op - tgt) * side > 0 else tgt), "target"
                break
            if flat[j]:
                out, why = C[j] - side * hs, "flatten"
                break
            j += 1
        if out is None:
            break
        r = (out - entry) * side / risk
        r_gross = ((out + side * hs) - (entry - side * hs)) * side / risk      # same trade with no spread
        rows.append({"ts": ct[i], "side": side, "entry": entry, "stop": stop, "target": tgt, "exit": out,
                     "exit_ts": ct[j], "why": why, "r": r, "r_no_cost": r_gross, "risk_pts": risk,
                     "bands": int(up[i] if side > 0 else dn[i])})
        free_from = j + 1 + cooldown
        i = j + 1
    return pd.DataFrame(rows)


def stats(t: pd.DataFrame, col: str = "r") -> dict:
    if not len(t):
        return {"trades": 0}
    r = t[col].to_numpy(float)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    sd = r.std(ddof=1) if len(r) > 1 else 0
    return {"trades": len(r), "win": round(float((r > 0).mean()), 3), "pf": round(float(wins / losses), 2) if losses else None,
            "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1), "max_dd_r": round(dd, 1),
            "t": round(float(r.mean() / (sd / np.sqrt(len(r)))), 2) if sd else None}


def report(sym: str, t: pd.DataFrame, spread: float) -> list[str]:
    L = [f"## {sym}  (spread {spread:g} per round trip)\n"]
    if not len(t):
        return L + ["No trades.\n"]
    t = t.copy()
    a, b = stats(t), stats(t, "r_no_cost")
    L.append(f"- with spread: **{a['trades']} trades, {a['win']:.0%} win, PF {a['pf']}, avg {a['avg_r']:+.3f}R, "
             f"total {a['sum_r']:+.1f}R**, worst drawdown {a['max_dd_r']}R, t {a['t']}")
    L.append(f"- no costs (how such posts are usually measured): {b['win']:.0%} win, PF {b['pf']}, avg {b['avg_r']:+.3f}R, total {b['sum_r']:+.1f}R")
    L.append(f"- median risk {t['risk_pts'].median():.2f} points → the spread is {spread / t['risk_pts'].median():.0%} of 1R on a typical trade")
    t["month"] = pd.to_datetime(t["ts"]).dt.strftime("%Y-%m")
    m = t.groupby("month")["r"].agg(["size", "sum"])
    L.append("- by month (R): " + " · ".join(f"{k} {v['sum']:+.1f} ({int(v['size'])})" for k, v in m.iterrows()))
    q = np.array_split(np.arange(len(t)), 4)
    L.append("- quarters (avg R): " + " · ".join(f"{t['r'].iloc[ix].mean():+.3f}" for ix in q if len(ix)))
    for nb in (2, 3):
        x = t[t["bands"] == nb]
        if len(x):
            s = stats(x)
            L.append(f"- closed beyond {nb} of 3 bands: {s['trades']} trades, {s['win']:.0%} win, avg {s['avg_r']:+.3f}R")
    for side, nm in ((1, "longs"), (-1, "shorts")):
        x = t[t["side"] == side]
        if len(x):
            s = stats(x)
            L.append(f"- {nm}: {s['trades']} trades, {s['win']:.0%} win, avg {s['avg_r']:+.3f}R")
    L.append(f"- exits: " + ", ".join(f"{k} {v}" for k, v in t["why"].value_counts().items()))
    return L + [""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*", default=["NDQ"])
    ap.add_argument("--days", type=int, help="use data/history_<days>d (fetched by ./fx.sh yeartest / setup-test --days)")
    ap.add_argument("--costs", choices=["oanda", "raw"], default="oanda")
    ap.add_argument("--spread", type=float, help="override the round-trip spread (price units)")
    ap.add_argument("--out", help="write report.md / trades.csv here")
    ap.add_argument("--trail-basis", action="store_true", help="stop follows the 5m basis as it moves")
    a = ap.parse_args()
    cfg = load_config()
    base = history_dir(cfg)
    hd = base.parent / f"history_{a.days}d" if a.days else base
    lines = [f"# Bollinger trend continuation — {a.days or 'cache'} days · costs {a.costs}\n",
             "1m close beyond ≥2 of the 5m/15m/1h BB(20,2) from closed candles, stop at the 5m basis, 1R target, "
             "08:00–12:00 NY entries, 10-candle cooldown.\n"]
    allt = []
    for sym in a.symbols:
        p = hd / f"{sym}.pkl"
        if not p.exists():
            lines.append(f"## {sym}\n\nno history at {p}\n")
            continue
        m1, _ = pd.read_pickle(p)
        tbl = RAW_SPREAD if a.costs == "raw" else DEFAULT_SPREAD
        spread = a.spread if a.spread is not None else float(((cfg.get("shadow") or {}).get("spread") or {}).get(sym, tbl.get(sym, 0))
                                                             if a.costs == "oanda" else tbl.get(sym, 0))
        t = backtest(m1, spread, trail_basis=a.trail_basis)
        lines.append(f"History {m1.index[0]:%Y-%m-%d} → {m1.index[-1]:%Y-%m-%d}\n")
        lines += report(sym, t, spread)
        t["sym"] = sym
        allt.append(t)
    txt = "\n".join(lines)
    print(txt)
    if a.out:
        o = Path(a.out)
        o.mkdir(parents=True, exist_ok=True)
        (o / "report.md").write_text(txt)
        if allt:
            pd.concat(allt).to_csv(o / "trades.csv", index=False)
        (o / "status.json").write_text(json.dumps({"stage": "done", "symbols": a.symbols, "days": a.days, "costs": a.costs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
