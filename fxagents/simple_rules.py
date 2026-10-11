"""Test a simple user-specified rule on an OANDA bid/ask export (data/export/<name>/<SYM>_M1.csv.gz).

Rules are frozen in code before any result is seen; each is run once on development data, and goes to the
holdout export only if it passes there.

  python -m fxagents.simple_rules ema21_rsi55 --data dev_m1 --out data/year_test/ema21_rsi55_dev_m1

ema21_rsi55 (Sam, 2026-10-11), 15-minute candles, long only:
  entry  a completed 15m candle closes above EMA21 (the previous candle closed at or below it) and RSI(14) > 55
         on that candle → buy at the ASK on the next minute's open
  exit   the first completed 15m candle that closes below EMA21 → sell at the BID on the next minute's open
  no stop loss (the rule has none). Results in units of ATR(14, 15m) at entry ("R"), and in price points.
  versions:  24h — as written; also exits at the last price before a closure gap > 60 min (weekends, breaks)
             day — the bot's day-trading constraints: entries 02:00–15:30 NY, flat at 15:50 NY
Signals use mid prices ((bid+ask)/2) of completed candles only; fills use the real bid/ask of that minute.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
# one pip in price units: FX majors 0.0001; gold 0.10 (the common retail convention); indices 1 point
PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
       "USDJPY": 0.01, "XAUUSD": 0.10, "XAGUSD": 0.01, "NDQ": 1.0, "US30": 1.0, "SPX": 1.0}


def pip_stats(t: pd.DataFrame, pip: float) -> dict:
    """Net pips after the real spread: winners vs losers, totals and averages, plus the spread paid."""
    p = t.points / pip
    w, l = p[p > 0], p[p <= 0]
    sp = t.cost_R * t.atr / pip
    return {"pips_won": float(w.sum()), "pips_lost": float(l.sum()), "pips_net": float(p.sum()),
            "avg_win_pips": float(w.mean()) if len(w) else 0.0, "avg_loss_pips": float(l.mean()) if len(l) else 0.0,
            "avg_pips": float(p.mean()), "spread_pips_avg": float(sp.mean()), "spread_pips_total": float(sp.sum()),
            "largest_win_pips": float(p.max()), "largest_loss_pips": float(p.min())}


def load(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d.index = pd.to_datetime(d.pop("time"), utc=True)
    d = d[~d.index.duplicated()].sort_index()
    for s in ("o", "h", "l", "c"):
        d[f"m_{s}"] = (d[f"bid_{s}"] + d[f"ask_{s}"]) / 2
    return d


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def bars15(m1: pd.DataFrame) -> pd.DataFrame:
    """15-minute mid candles; label = candle END (the moment it is complete); empty quarters dropped."""
    r = m1.resample("15min", label="right", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last(),
                      "n": r["m_c"].count()}).dropna()
    b = b[b.n > 0]
    b["ema21"] = ema(b.c, 21)
    d = b.c.diff()
    b["rsi"] = 100 - 100 / (1 + wilder(d.clip(lower=0), 14) / wilder((-d).clip(lower=0), 14))
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = wilder(tr, 14)
    return b


def run_ema21_rsi55(m1: pd.DataFrame, version: str) -> list[dict]:
    b = bars15(m1)
    t1 = m1.index
    ask_o, bid_o, bid_c = m1.ask_o.to_numpy(), m1.bid_o.to_numpy(), m1.bid_c.to_numpy()
    sp_o = (m1.ask_o - m1.bid_o).to_numpy()
    gap = np.r_[np.diff(t1.as_unit("ns").asi8), 0] > 60 * 60 * 1_000_000_000
    loc = b.index.tz_convert(NY)
    mins = loc.hour * 60 + loc.minute
    c, e, rsi, atr = b.c.to_numpy(), b.ema21.to_numpy(), b.rsi.to_numpy(), b.atr.to_numpy()
    first_min = np.searchsorted(t1.as_unit("ns").asi8, b.index.as_unit("ns").asi8)   # first minute at/after each bar end
    out, i, n = [], 1, len(b)
    while i < n:
        ok = np.isfinite(e[i]) and np.isfinite(e[i - 1]) and np.isfinite(rsi[i]) and np.isfinite(atr[i]) and atr[i] > 0
        if not (ok and c[i - 1] <= e[i - 1] and c[i] > e[i] and rsi[i] > 55):
            i += 1
            continue
        if version == "day" and not (120 <= mins[i] <= 930):           # entries 02:00–15:30 NY (bar close time)
            i += 1
            continue
        j0 = first_min[i]
        if j0 >= len(t1) or t1[j0] - b.index[i] > pd.Timedelta("5min"):  # no tradable minute right after the close
            i += 1
            continue
        entry, sp_in = ask_o[j0], sp_o[j0]
        # exit: first later bar closing below EMA21 → next minute's bid open; or forced exits
        k, jx, why = i + 1, None, None
        flat = None
        if version == "day":
            day = loc[i].normalize()
            flat = (day + pd.Timedelta(hours=15, minutes=50)).tz_convert("UTC")
        nxt_gap = j0 + int(np.argmax(gap[j0:])) if gap[j0:].any() else None
        while k < n:
            jk = first_min[k] if first_min[k] < len(t1) else len(t1) - 1
            if nxt_gap is not None and jk > nxt_gap:                    # market closed before this bar: out at the last bid
                jx, why = nxt_gap, "closure"
                break
            if flat is not None and b.index[k] > flat:
                jx, why = int(np.searchsorted(t1.as_unit("ns").asi8, flat.value)), "flat_1550"
                break
            if c[k] < e[k]:
                jx, why = jk, "close_below_ema"
                break
            k += 1
        if jx is None or jx >= len(t1):
            break                                                       # still open at the end of the data
        px = bid_c[jx] if why == "closure" else bid_o[jx]
        sp_out = sp_o[jx]
        pts = px - entry
        out.append({"entry_time": t1[j0], "exit_time": t1[jx], "entry": entry, "exit": px, "atr": atr[i],
                    "points": pts, "R": pts / atr[i],
                    # vs mid, buying at the ask and selling at the bid costs half a spread on each side = one spread
                    # per round trip (already inside `points`); 2× costs pays that again
                    "R_2x": (pts - (sp_in + sp_out) / 2) / atr[i], "cost_R": (sp_in + sp_out) / 2 / atr[i], "rsi": rsi[i], "exit_reason": why,
                    "hold_min": (t1[jx] - t1[j0]).total_seconds() / 60,
                    "overnight": t1[jx].tz_convert(NY).date() != t1[j0].tz_convert(NY).date()})
        i = max(k, i + 1)
    return out


def stats(t: pd.DataFrame, days: pd.DatetimeIndex, seed: int = 7) -> dict:
    if not len(t):
        return {"trades": 0}
    r = t.R.to_numpy()
    daily = t.groupby(t.entry_time.dt.tz_convert(NY).dt.normalize()).R.agg(["sum", "count"]).reindex(days, fill_value=0)
    s, k = daily["sum"].to_numpy(), daily["count"].to_numpy()
    rng, B, blk, nd = np.random.default_rng(seed), 4000, 5, len(s)
    ix = (rng.integers(0, nd, (B, -(-nd // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :nd] % nd
    den = k[ix].sum(1)
    boot = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    lo, hi = np.nanquantile(boot, [0.025, 0.975])
    thirds = np.array_split(np.arange(len(t)), 3)
    return {"trades": len(t), "win": float((r > 0).mean()), "avg_R": float(r.mean()), "total_R": float(r.sum()),
            "ci_lo": float(lo), "ci_hi": float(hi), "avg_R_2x": float(t.R_2x.mean()), "cost_R": float(t.cost_R.mean()),
            "thirds": [float(t.R.iloc[x].mean()) for x in thirds if len(x)],
            "hold_min_median": float(t.hold_min.median()), "overnight": float(t.overnight.mean()),
            "pass": bool(len(t) >= 100 and r.mean() > 0 and lo > 0 and t.R_2x.mean() > 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rule", choices=["ema21_rsi55"])
    ap.add_argument("--data", required=True, help="export name under data/export/")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    src = Path("data/export") / a.data
    files = sorted(src.glob("*_M1.csv.gz"))
    a.out.mkdir(parents=True, exist_ok=True)
    rows, trades = [], []
    for f in files:
        sym = f.name.split("_M1")[0]
        m1 = load(f)
        days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).normalize())))
        days = days[days.dayofweek < 5]
        for v in ("24h", "day"):
            t = pd.DataFrame(run_ema21_rsi55(m1, v))
            st = stats(t, days)
            if len(t):
                st |= pip_stats(t, PIP.get(sym, 1.0))
            rows.append({"symbol": sym, "version": v, **st})
            if len(t):
                trades.append(t.assign(symbol=sym, version=v))
            print(f"  {sym:7s} {v:3s} {st.get('trades', 0):5d} trades  avg {st.get('avg_R', float('nan')):+.3f}R  "
                  f"95% [{st.get('ci_lo', float('nan')):+.3f}, {st.get('ci_hi', float('nan')):+.3f}]  "
                  f"2×cost {st.get('avg_R_2x', float('nan')):+.3f}  spread {st.get('cost_R', float('nan')):.3f}R", flush=True)
        del m1
    T = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    if len(T):
        T.to_csv(a.out / "trades.csv.gz", index=False)
    span = f"{T.entry_time.min():%Y-%m-%d} → {T.exit_time.max():%Y-%m-%d}" if len(T) else "—"
    md = [f"# Rule test: {a.rule} on {a.data}", "",
          "Rule (frozen before testing): 15m candle closes above EMA21 (previous close at/below it) with RSI(14) > 55 → buy "
          "at the ask on the next minute; exit at the bid on the next minute after the first 15m close below EMA21. Long only, "
          "no stop. R = ATR(14) of 15m candles at entry. Real OANDA bid/ask (one spread per round trip, already in every result); 2× costs pays that spread once more. "
          "Versions: 24h = as written (forced out before closures > 60 min); day = entries 02:00–15:30 NY, flat 15:50 NY.",
          "", f"Trades span {span}. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs.", "",
          "| Symbol | Version | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread paid (R) | Thirds | Median hold | Overnight | Pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("trades"):
            md.append(f"| {r['symbol']} | {r['version']} | 0 | | | | | | | | | | no |")
            continue
        md.append(f"| {r['symbol']} | {r['version']} | {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | "
                  f"{r['ci_lo']:+.3f} to {r['ci_hi']:+.3f} | {r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['cost_R']:.3f} | "
                  f"{' / '.join(f'{x:+.2f}' for x in r['thirds'])} | {r['hold_min_median']:.0f} min | {r['overnight']:.0%} | "
                  f"{'**PASS**' if r['pass'] else 'no'} |")
    md += ["", "## Pips (after the real spread)", "",
           "1 pip = 0.0001 for FX majors, 0.10 for gold, 1 point for NDQ/US30. Pips won = sum over winning trades; pips lost = "
           "sum over losing trades; the spread is already inside both (it is shown separately so you can see its weight).", "",
           "| Symbol | Version | Trades | Pips won | Pips lost | Net pips | Avg win | Avg loss | Avg per trade | Spread per trade | Spread total | Largest win / loss |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("trades"):
            md.append(f"| {r['symbol']} | {r['version']} | {r['trades']} | {r['pips_won']:+,.0f} | {r['pips_lost']:+,.0f} | "
                      f"**{r['pips_net']:+,.0f}** | {r['avg_win_pips']:+.1f} | {r['avg_loss_pips']:+.1f} | {r['avg_pips']:+.1f} | "
                      f"{r['spread_pips_avg']:.1f} | {r['spread_pips_total']:,.0f} | {r['largest_win_pips']:+.0f} / {r['largest_loss_pips']:+.0f} |")
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"rule": a.rule, "data": a.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
