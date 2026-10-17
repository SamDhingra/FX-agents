"""Test a simple user-specified rule on an OANDA bid/ask export (data/export/<name>/<SYM>_M1.csv.gz).

Rules are frozen in code before any result is seen; each is run once on development data, and goes to the
holdout export only if it passes there.

  python -m fxagents.simple_rules ema21_rsi55 --data dev_m1 --out data/year_test/ema21_rsi55_dev_m1

ema21_rsi55 (Sam, 2026-10-11), 15-minute candles, long (shorts, the mirror, in variant ema21_rsi55_short):
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


def bars(m1: pd.DataFrame, tf: str = "15min") -> pd.DataFrame:
    """Mid candles of `tf`; label = candle END (the moment it is complete); empty candles dropped.
    rvol = this candle's tick volume / median volume of the same time-of-day candle over the previous 20 days
    (earlier days only — no look-ahead); NaN until 10 earlier days exist."""
    r = m1.resample(tf, label="right", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last(),
                      "n": r["m_c"].count(), "vol": r["volume"].sum() if "volume" in m1 else r["m_c"].count()}).dropna()
    b = b[b.n > 0]
    b["ema21"] = ema(b.c, 21)
    d = b.c.diff()
    b["rsi"] = 100 - 100 / (1 + wilder(d.clip(lower=0), 14) / wilder((-d).clip(lower=0), 14))
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = wilder(tr, 14)
    slot = b.index.tz_convert(NY).strftime("%H:%M")
    med = b.groupby(slot).vol.transform(lambda x: x.shift(1).rolling(20, min_periods=10).median())
    b["rvol"] = b.vol / med.replace(0, np.nan)
    return b


def bars15(m1: pd.DataFrame) -> pd.DataFrame:
    return bars(m1, "15min")


def run_ema21_rsi55(m1: pd.DataFrame, version: str, tf: str = "15min", vol_min: float | None = None,
                    add: bool = False, b: pd.DataFrame | None = None, side: int = 1) -> list[dict]:
    """The rule (see module doc). vol_min: also require rvol ≥ vol_min on the signal candle. add: once per trade,
    on a later candle that closes above EMA21 with 58 < RSI ≤ 70 while that close is above the entry price, buy a
    second, equal unit at the ask on the next minute; both units exit together. R is per INITIAL unit (ATR at entry),
    so an added trade's R is the sum of both units.
    side -1: the exact mirror — close crosses below EMA21 with RSI < 45 → sell at the bid; exit at the ask after
    the first close above EMA21 (add: a close below EMA21 with 30 ≤ RSI < 42 while below the entry)."""
    b = bars(m1, tf) if b is None else b
    t1 = m1.index
    ns = t1.as_unit("ns").asi8
    ask_o, bid_o, bid_c, ask_c = m1.ask_o.to_numpy(), m1.bid_o.to_numpy(), m1.bid_c.to_numpy(), m1.ask_c.to_numpy()
    in_o, out_o, out_c = (ask_o, bid_o, bid_c) if side > 0 else (bid_o, ask_o, ask_c)   # buy at ask / sell at bid
    sp_o = (m1.ask_o - m1.bid_o).to_numpy()
    gap = np.r_[np.diff(ns), 0] > 60 * 60 * 1_000_000_000
    loc = b.index.tz_convert(NY)
    mins = loc.hour * 60 + loc.minute
    c, e, rsi, atr, rv = (b[x].to_numpy() for x in ("c", "ema21", "rsi", "atr", "rvol"))
    first_min = np.searchsorted(ns, b.index.as_unit("ns").asi8)       # first minute at/after each candle's end
    out, i, n = [], 1, len(b)
    while i < n:
        ok = np.isfinite(e[i]) and np.isfinite(e[i - 1]) and np.isfinite(rsi[i]) and np.isfinite(atr[i]) and atr[i] > 0
        cross = (c[i - 1] <= e[i - 1] and c[i] > e[i] and rsi[i] > 55) if side > 0 else \
            (c[i - 1] >= e[i - 1] and c[i] < e[i] and rsi[i] < 45)
        if not (ok and cross):
            i += 1
            continue
        if vol_min is not None and not (np.isfinite(rv[i]) and rv[i] >= vol_min):
            i += 1
            continue
        if version == "day" and not (120 <= mins[i] <= 930):           # entries 02:00–15:30 NY (candle close time)
            i += 1
            continue
        j0 = first_min[i]
        if j0 >= len(t1) or t1[j0] - b.index[i] > pd.Timedelta("5min"):  # no tradable minute right after the close
            i += 1
            continue
        entry, sp_in = in_o[j0], sp_o[j0]
        k, jx, why, ja = i + 1, None, None, None
        flat = None
        if version == "day":
            flat = (loc[i].normalize() + pd.Timedelta(hours=15, minutes=50)).tz_convert("UTC")
        nxt_gap = j0 + int(np.argmax(gap[j0:])) if gap[j0:].any() else None
        while k < n:
            jk = first_min[k] if first_min[k] < len(t1) else len(t1) - 1
            if nxt_gap is not None and jk > nxt_gap:                    # market closed before this candle: out at the last bid
                jx, why = nxt_gap, "closure"
                break
            if flat is not None and b.index[k] > flat:
                jx, why = int(np.searchsorted(ns, flat.value)), "flat_1550"
                break
            if (c[k] < e[k]) if side > 0 else (c[k] > e[k]):
                jx, why = jk, "close_below_ema" if side > 0 else "close_above_ema"
                break
            add_ok = (58 < rsi[k] <= 70 and c[k] > entry) if side > 0 else (30 <= rsi[k] < 42 and c[k] < entry)
            if add and ja is None and add_ok and first_min[k] < len(t1) \
                    and t1[first_min[k]] - b.index[k] <= pd.Timedelta("5min") \
                    and (flat is None or b.index[k] <= flat - pd.Timedelta("20min")):
                ja = first_min[k]
            k += 1
        if jx is None or jx >= len(t1):
            break                                                       # still open at the end of the data
        px = out_c[jx] if why == "closure" else out_o[jx]
        sp_out = sp_o[jx]
        pts = (px - entry) * side
        cost = (sp_in + sp_out) / 2                                    # vs mid: half a spread each side = one spread
        add_pts, add_cost = 0.0, 0.0
        if ja is not None and ja < jx:
            add_pts = (px - in_o[ja]) * side
            add_cost = (sp_o[ja] + sp_out) / 2
        tot = pts + add_pts
        out.append({"entry_time": t1[j0], "exit_time": t1[jx], "side": side, "entry": entry, "exit": px, "atr": atr[i],
                    "points": tot, "points_base": pts, "added": ja is not None and ja < jx, "add_points": add_pts,
                    "R": tot / atr[i], "R_base": pts / atr[i],
                    "R_2x": (tot - cost - add_cost) / atr[i], "cost_R": (cost + add_cost) / atr[i],
                    "rsi": rsi[i], "rvol": rv[i], "exit_reason": why,
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


VARIANTS = {
    # name: (symbols or None for every file, [(tf, version, vol_min, add), ...])
    "ema21_rsi55": (None, [("15min", v, None, False) for v in ("24h", "day")]),
    # refinement (Sam, 2026-10-11, after seeing ema21_rsi55): indices + gold only; 15m and 1h; volume filter
    # rvol ≥ 1.0 (signal candle at least as active as that time of day usually is); add one equal unit while in
    # profit on a close above EMA21 with 58 < RSI ≤ 70. 2 × 2 × 2 × 2 = 16 variants × 3 instruments, fixed here.
    "ema21_rsi55_v2": (["XAUUSD", "NDQ", "US30"],
                       [(tf, v, vm, ad) for tf in ("15min", "1h") for v in ("24h", "day")
                        for vm in (None, 1.0) for ad in (False, True)]),
}
# shorts (Sam, 2026-10-17): the exact mirror of the base rule, and long + short together as the shadow book now
# runs it. Same instruments as the shadow book (+ NDQ), 15m, both versions. side: 1 long, -1 short, 0 both.
VARIANTS["ema21_rsi55_short"] = (["XAUUSD", "US30", "NDQ"],
                                 [("15min", v, None, False, sd) for sd in (-1, 0) for v in ("24h", "day")])
RVOL_BUCKETS = [(0, 0.8, "< 0.8"), (0.8, 1.2, "0.8–1.2"), (1.2, 2.0, "1.2–2.0"), (2.0, np.inf, "≥ 2.0")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rule", choices=sorted(VARIANTS))
    ap.add_argument("--data", required=True, help="export name under data/export/")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    want, grid = VARIANTS[a.rule]
    src = Path("data/export") / a.data
    files = [f for f in sorted(src.glob("*_M1.csv.gz")) if want is None or f.name.split("_M1")[0] in want]
    a.out.mkdir(parents=True, exist_ok=True)
    rows, trades = [], []
    for f in files:
        sym = f.name.split("_M1")[0]
        m1 = load(f)
        days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).normalize())))
        days = days[days.dayofweek < 5]
        cache = {}
        for g in grid:
            tf, v, vm, ad = g[:4]
            sd = g[4] if len(g) > 4 else 1
            if tf not in cache:
                cache[tf] = bars(m1, tf)
            sides = (1, -1) if sd == 0 else (sd,)
            t = pd.DataFrame([x for s_ in sides for x in run_ema21_rsi55(m1, v, tf, vm, ad, cache[tf], s_)])
            if len(t):
                t = t.sort_values("entry_time", ignore_index=True)
            st = stats(t, days)
            if len(t):
                st |= pip_stats(t, PIP.get(sym, 1.0))
                st["added_share"] = float(t.added.mean())
                st["add_R_added"] = float((t.R - t.R_base)[t.added].mean()) if t.added.any() else None
            key = {"symbol": sym, "tf": tf, "version": v, "volume": "rvol≥1" if vm else "—", "add": "yes" if ad else "—",
                   "side": {1: "long", -1: "short", 0: "both"}[sd]}
            rows.append({**key, **st})
            if len(t):
                trades.append(t.assign(**key))
            print(f"  {sym:7s} {key['side']:5s} {tf:5s} {v:3s} vol={key['volume']:6s} add={key['add']:3s} {st.get('trades', 0):5d} trades  "
                  f"avg {st.get('avg_R', float('nan')):+.3f}R  95% [{st.get('ci_lo', float('nan')):+.3f}, "
                  f"{st.get('ci_hi', float('nan')):+.3f}]  2×cost {st.get('avg_R_2x', float('nan')):+.3f}", flush=True)
        del m1, cache
    T = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    if len(T):
        T.to_csv(a.out / "trades.csv.gz", index=False)
    span = f"{T.entry_time.min():%Y-%m-%d} → {T.exit_time.max():%Y-%m-%d}" if len(T) else "—"
    npass = sum(bool(r.get("pass")) for r in rows)
    md = [f"# Rule test: {a.rule} on {a.data}", "",
          "Base rule (frozen before testing): candle closes above EMA21 (previous close at/below it) with RSI(14) > 55 → buy "
          "at the ask on the next minute; exit at the bid on the next minute after the first close below EMA21. Short "
          "(mirror): close below EMA21 (previous at/above) with RSI(14) < 45 → sell at the bid; exit at the ask after the first "
          "close above EMA21. Side both = long and short trades together. No stop. R = ATR(14) of that timeframe at entry. Real OANDA bid/ask (one spread per round trip, already in every "
          "result); 2× costs pays that spread once more. Versions: 24h = as written (forced out before closures > 60 min); "
          "day = entries 02:00–15:30 NY, flat 15:50 NY. Volume rvol≥1 = the signal candle's tick volume at least the median of "
          "the same time-of-day candle over the previous 20 days. Add = one extra equal unit, once, on a later close above "
          "EMA21 with 58 < RSI ≤ 70 while above the entry price; R is per initial unit, so an added trade's R counts both units.",
          "", f"Trades span {span}. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. "
          f"**{npass} of {len(rows)} variants pass.** With {len(rows)} variants, about {len(rows) * 0.025:.0f} could pass by "
          "luck alone, so anything that passes here goes to the holdout once, unchanged, before it counts.", "",
          "| Symbol | Side | TF | Version | Volume | Add | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Thirds | Median hold | Pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        k = f"| {r['symbol']} | {r.get('side', 'long')} | {r['tf']} | {r['version']} | {r['volume']} | {r['add']} |"
        if not r.get("trades"):
            md.append(k + " 0 | | | | | | | | | no |")
            continue
        md.append(f"{k} {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | {r['ci_lo']:+.3f} to {r['ci_hi']:+.3f} | "
                  f"{r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['cost_R']:.3f} | "
                  f"{' / '.join(f'{x:+.2f}' for x in r['thirds'])} | {r['hold_min_median']:.0f} min | "
                  f"{'**PASS**' if r['pass'] else 'no'} |")
    md += ["", "## Pips (after the real spread)", "",
           "1 pip = 0.0001 for FX majors, 0.10 for gold, 1 point for NDQ/US30. With adds, pips count both units.", "",
           "| Symbol | Side | TF | Version | Volume | Add | Trades | Pips won | Pips lost | Net pips | Avg win | Avg loss | Spread per trade | Largest win / loss |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("trades"):
            md.append(f"| {r['symbol']} | {r.get('side', 'long')} | {r['tf']} | {r['version']} | {r['volume']} | {r['add']} | {r['trades']} | "
                      f"{r['pips_won']:+,.0f} | {r['pips_lost']:+,.0f} | **{r['pips_net']:+,.0f}** | {r['avg_win_pips']:+.1f} | "
                      f"{r['avg_loss_pips']:+.1f} | {r['spread_pips_avg']:.1f} | {r['largest_win_pips']:+.0f} / {r['largest_loss_pips']:+.0f} |")
    if len(T) and "rvol" in T:
        base = T[(T["volume"] == "—") & (T["add"] == "—")]
        md += ["", "## Volume: how the base rule did by the signal candle's relative volume", "",
               "Descriptive only (no add, no volume filter). Buckets were fixed before the run; reading the best bucket and "
               "filtering on it would be fitting to this data.", "",
               "| Symbol | Side | TF | Version | " + " | ".join(f"rvol {lab}: trades / win / avg R" for _, _, lab in RVOL_BUCKETS) + " |",
               "|---|---|---|---|" + "---|" * len(RVOL_BUCKETS)]
        for (sym, sd_, tf, v), g in base.groupby(["symbol", "side", "tf", "version"], sort=False):
            cells = []
            for lo, hi, _ in RVOL_BUCKETS:
                x = g[(g.rvol >= lo) & (g.rvol < hi)]
                cells.append(f"{len(x)} / {(x.R > 0).mean():.0%} / {x.R.mean():+.2f}" if len(x) else "0")
            md.append(f"| {sym} | {sd_} | {tf} | {v} | " + " | ".join(cells) + " |")
    adds = [r for r in rows if r.get("trades") and r["add"] == "yes"]
    if adds:
        md += ["", "## Adds: what the second unit contributed", "",
               "| Symbol | TF | Version | Volume | Trades | Share with an add | Avg R of the added unit (on trades that added) |",
               "|---|---|---|---|---|---|---|"]
        for r in adds:
            ar = r.get("add_R_added")
            md.append(f"| {r['symbol']} | {r['tf']} | {r['version']} | {r['volume']} | {r['trades']} | {r['added_share']:.0%} | "
                      f"{'—' if ar is None else f'{ar:+.3f}'} |")
    md += ["", "Jev (the bot's LLM grader) is not in this backtest: asking a model today to grade 2024–2026 candles is not a "
           "clean test (it may know what happened next). It can only be tested forward, by logging its grade on live signals."]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"rule": a.rule, "data": a.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
