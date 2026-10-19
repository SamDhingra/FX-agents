"""SMC inducement trap: 1H dealing range → 15m demand/supply + inducement → 5m CHoCH + FVG → 3m order-block limit entry.
Proposed by the outside strategy author (Oct 19 2026), coded from their description and frozen here before any run.

    python -m fxagents.smc_idm --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/smc_idm   (./fx.sh smcidm)

All signals on mid candles; fills on the real bid/ask (a buy limit fills when the ASK trades at or below it, a sell limit
when the BID trades at or above it; at the minute's open if price gaps through). Times New York. Long logic is
described; shorts are its mirror image except where the author made them asymmetric (marked).

Definitions — the author's exact scale-invariant spec (sent Oct 19 2026, before any run), plus the points it left
open, fixed here:
  Swings        2-candle fractals (a high/low beating the 2 candles each side), known 2 candles later; the 5m
                "lower high" uses a 1-candle fractal, known 1 candle later.
  1H bias +     bullish after a 1H close above the last confirmed 1H swing high (BOS); bearish after a close below the
  dealing range last confirmed swing low. Range = last confirmed swing low at the BOS → highest 1H high since;
                equilibrium = midpoint. Longs only while bullish and the 15m zone's top is below equilibrium.
  15m zone      base candle i_ob whose move left a 3-candle FVG (low[i_ob+2] > high[i_ob]); zone = its high–low,
                known at the close of i_ob+2. Lives 2 days; a 15m close below it kills it.
  Inducement    a confirmed 5m or 15m swing low formed after the zone, above the zone top, existing at the tap; the tap
                (a 5m low into the zone) sweeps it. A 5m close below the zone kills the setup.
  5m CHoCH      within 12 five-minute candles of the tap, a 5m close above the last 1-candle fractal high before the
                tap, with a 5m or 3m FVG formed after the tap (by that close or the next 5m candle).
  3m order      the last bearish 3m candle at or before the lowest 3m low since the tap (up to 5 candles back); the 3m
  block + FVG   FVG = the first 3m imbalance after it.
  Entry         limit at the 3m FVG midpoint (else the order block's top), valid 24 minutes; cancelled if price (mid)
                covers 75% of the way to TP1 first, or reaches the stop first. Symmetric for shorts.
  Stop          0.15 × ATR(14,15m) beyond the order block's far end, and at least 0.80 × ATR15 from the limit.
  Targets       TP1 (50%) = 1.8R, or the internal high price fell from into the zone if that is further; TP2 (50%) =
                3.0R, or the 1H dealing range's high if further. Fixed stop. Flat 16:30 NY.
  Not tested    the Unicorn / Judas variants, the discretionary failure-swing exit, the 20% long-term hold.
  Window        fills 02:00–12:00 NY, none within 15 min of a scheduled USD release; ≤ 3 trades a day, one at a time.
  Controls      coin flip (same minute, random side, market entry, same stop distance and R targets) and the same model
                without the 1H bias / premium-discount filter.

Gates: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better
than both controls. Protocol (author's): step 1 on the seen sets dev_m1 + holdout_m1 (2021 → Sep 2026) combined, each
also positive; only then is the untouched old_m1 (2016–2020) opened and judged once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN, prep
from .simple_rules import NY, PIP, load, pip_stats, stats, wilder

WIN = (120, 720)                 # fills 02:00–12:00 NY
FLAT = 990
MAX_DAY = 3
OB_LOOK, ZONE_LIFE_15 = 10, 192  # 15m candles: order-block look-back; zone lifetime (2 days)
CHOCH_BARS = 12
OB3_LOOK = 5
LIMIT_MIN, CANCEL_FRAC = 24, 0.75          # limit valid 24 min (eight 3m candles)
STOP_ATR_BUF, MIN_STOP_ATR = 0.15, 0.80    # stop 0.15 × ATR15 beyond the 3m OB; at least 0.80 × ATR15 from the entry
TP1_R, TP2_R = 1.8, 3.0                    # TP1 ≥ 1.8R (or the internal high if further), TP2 ≥ 3R (or the 1H range high)
FUNNEL: dict[str, int] = {}          # diagnostics: setups reaching each stage (rule run, both sides)


def count(stage: str, on: bool = True) -> None:
    if on:
        FUNNEL[stage] = FUNNEL.get(stage, 0) + 1


def candles(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    b["start"] = b.index.as_unit("ns").asi8
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    return b


def ohlc(b: pd.DataFrame, side: int):
    o, h, l, c = (b[k].to_numpy() for k in "ohlc")
    return (o, h, l, c) if side > 0 else (-o, -l, -h, -c)


def swings(H: np.ndarray, L: np.ndarray):
    """As of each candle's close: (last confirmed swing-high price, its index, last confirmed swing-low price, index)."""
    n = len(H)
    shp, shi, slp, sli = (np.full(n, np.nan), np.full(n, -1), np.full(n, np.nan), np.full(n, -1))
    cur = [np.nan, -1, np.nan, -1]
    for t in range(n):
        i = t - 2
        if i >= 2:
            if H[i] > max(H[i - 2], H[i - 1], H[i + 1], H[i + 2]):
                cur[0], cur[1] = H[i], i
            if L[i] < min(L[i - 2], L[i - 1], L[i + 1], L[i + 2]):
                cur[2], cur[3] = L[i], i
        shp[t], shi[t], slp[t], sli[t] = cur
    return shp, shi.astype(int), slp, sli.astype(int)


def h1_state(b60: pd.DataFrame, side: int):
    """Per 1H candle close, in the side's own direction: bullish flag, range low, range high."""
    _, H, L, C = ohlc(b60, side)
    shp, _, slp, _ = swings(H, L)
    n = len(C)
    bull, rlo, rhi = np.zeros(n, bool), np.full(n, np.nan), np.full(n, np.nan)
    state, lo, hi, broken_hi, broken_lo = 0, np.nan, np.nan, np.nan, np.nan
    for t in range(n):
        if np.isfinite(shp[t]) and C[t] > shp[t] and shp[t] != broken_hi:
            state, lo, hi, broken_hi = 1, slp[t], H[t], shp[t]
        elif np.isfinite(slp[t]) and C[t] < slp[t] and slp[t] != broken_lo:
            state, broken_lo = -1, slp[t]
        if state == 1:
            hi = max(hi, H[t])
        bull[t], rlo[t], rhi[t] = state == 1, lo, hi
    return bull, rlo, rhi


def zones15(b15: pd.DataFrame, side: int, atr15: np.ndarray) -> list[dict]:
    """Author's definition: base candle i_ob whose move left a 3-candle FVG (low[i_ob+2] > high[i_ob]); zone = its
    full range, known at the close of i_ob+2."""
    _, H, L, _ = ohlc(b15, side)
    E = b15.end.to_numpy()
    out = []
    for i in range(14, len(H) - 2):
        if L[i + 2] > H[i]:
            out.append({"top": float(H[i]), "bot": float(L[i]), "made": int(E[i + 2]), "i15": i + 2, "ob": i,
                        "atr": float(atr15[i + 2])})
    return out


def fractal1_highs(H: np.ndarray) -> np.ndarray:
    """Last confirmed 1-bar fractal high as of each candle's close (high above both neighbours, known one candle later)."""
    out, cur = np.full(len(H), np.nan), np.nan
    for t in range(len(H)):
        i = t - 1
        if i >= 1 and H[i] > H[i - 1] and H[i] > H[i + 1]:
            cur = H[i]
        out[t] = cur
    return out


def find_setups(a: dict, side: int, htf: bool = True) -> list[dict]:
    b60, b15, b5, b3 = a["b60"], a["b15"], a["b5"], a["b3"]
    _, H5, L5, C5 = ohlc(b5, side)
    O3, H3, L3, C3 = ohlc(b3, side)
    S5, E5, S3, E3 = b5.start.to_numpy(), b5.end.to_numpy(), b3.start.to_numpy(), b3.end.to_numpy()
    E15, E60 = b15.end.to_numpy(), b60.end.to_numpy()
    _, _, sl5, sl5i = swings(H5, L5)
    lh5 = fractal1_highs(H5)
    _, H15, L15, _ = ohlc(b15, side)
    _, _, sl15, sl15i = swings(H15, L15)
    S15 = b15.start.to_numpy()
    atr15 = a["atr15"]
    bull, rlo, rhi = a["h1"][side]
    _, _, _, C15 = ohlc(b15, side)
    zs = zones15(b15, side, a["atr15"])
    FUNNEL["15m zones (base + FVG)"] = FUNNEL.get("15m zones (base + FVG)", 0) + len(zs) * htf
    out = []
    zi = 0
    active: list[dict] = []
    for k in range(5, len(b5)):
        while zi < len(zs) and zs[zi]["made"] <= S5[k]:
            active.append(dict(zs[zi], state="armed"))
            zi += 1
        if not active:
            continue
        i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
        keep = []
        for z in active:
            if i15 - z["i15"] > ZONE_LIFE_15 or (i15 > z["i15"] and C15[i15] < z["bot"]) or z["state"] == "done":
                continue
            keep.append(z)
            if z["state"] == "armed":
                if L5[k] > z["top"]:
                    continue
                # tap: needs an inducement — a confirmed 5m or 15m swing low formed after the zone, above its top
                idm_i, idm_t = -1, None
                if sl5i[k - 1] >= 0 and S5[sl5i[k - 1]] >= z["made"] and sl5[k - 1] > z["top"]:
                    idm_i, idm_t = sl5i[k - 1], S5[sl5i[k - 1]]
                j15 = int(np.searchsorted(E15, S5[k], side="right")) - 1
                if j15 >= 0 and sl15i[j15] >= 0 and S15[sl15i[j15]] >= z["made"] and sl15[j15] > z["top"]:
                    if idm_t is None or S15[sl15i[j15]] > idm_t:
                        idm_t = S15[sl15i[j15]]
                ok = idm_t is not None
                count("zone tapped", htf)
                if not ok or C5[k] < z["bot"]:
                    z["state"] = "done"
                    continue
                count("with inducement swept", htf)
                if htf:
                    h = int(np.searchsorted(E60, E5[k], side="right")) - 1
                    if h < 0 or not bull[h] or not np.isfinite(rlo[h]) or z["top"] >= (rlo[h] + rhi[h]) / 2:
                        z["state"] = "done"
                        continue
                count("in 1H bias + discount", htf)
                z.update(state="tapped", tap=k, lh=lh5[k - 1],
                         dol=float(rhi[int(np.searchsorted(E60, E5[k], side="right")) - 1]) if htf else np.nan)
                continue
            if z["state"] == "tapped":
                if C5[k] < z["bot"] or k - z["tap"] > CHOCH_BARS or not np.isfinite(z["lh"]):
                    z["state"] = "done"
                    continue
                if C5[k] <= z["lh"]:
                    continue
                count("5m CHoCH", htf)
                conf = None
                m0_ = int(np.searchsorted(S3, S5[z["tap"]]))
                for n in (k, k + 1):
                    if n >= len(b5):
                        break
                    m1n = int(np.searchsorted(E3, E5[n], side="right"))
                    if any(L5[q] > H5[q - 2] for q in range(z["tap"] + 2, n + 1)) or \
                            any(L3[q] > H3[q - 2] for q in range(m0_ + 2, m1n)):
                        conf = n
                        break
                z["state"] = "done"
                if conf is None:
                    continue
                count("with 5m/3m FVG", htf)
                t_conf = int(E5[conf])
                m0 = int(np.searchsorted(S3, S5[z["tap"]]))
                m1_ = int(np.searchsorted(E3, t_conf, side="right"))
                if m1_ - m0 < 3:
                    continue
                m_lo = m0 + int(np.argmin(L3[m0:m1_]))
                ob = next((m for m in range(m_lo, max(m0 - 1, m_lo - OB3_LOOK - 1), -1) if C3[m] < O3[m]), None)
                if ob is None:
                    continue
                count("3m order block found", htf)
                fvg = next((n for n in range(ob + 2, m1_) if L3[n] > H3[n - 2]), None)
                i15c = int(np.searchsorted(E15, t_conf, side="right")) - 1
                A = float(atr15[i15c])
                if not np.isfinite(A) or A <= 0:
                    continue
                limit = (L3[fvg] + H3[fvg - 2]) / 2 if fvg is not None else H3[ob]
                stop = min(L3[ob] - STOP_ATR_BUF * A, limit - MIN_STOP_ATR * A)
                i_made = int(np.searchsorted(S5, z["made"]))       # internal liquidity: the swing high price fell
                tp1 = float(H5[i_made:z["tap"]].max()) if z["tap"] > i_made else np.nan   # from into the zone
                out.append({"t": t_conf, "side": side, "limit": float(limit), "stop": float(stop), "tp1": tp1,
                            "dol": z["dol"], "zone": (z["bot"], z["top"]), "atr15": A})
        active = keep
    return out


def mirrored_exec(a: dict, side: int) -> dict:
    if side > 0:
        return {"in_o": a["ask_o"], "in_l": a["ask_l"], "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"],
                "ex_c": a["bid_c"], "mid_h": a["m_h"], "mid_l": a["m_l"]}
    return {"in_o": -a["bid_o"], "in_l": -a["bid_h"], "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"],
            "ex_c": -a["ask_c"], "mid_h": -a["m_l"], "mid_l": -a["m_h"]}


def manage(a, X, j, entry, stop, tp1, tp2):
    """50% at TP1, 50% at TP2, fixed stop, out at 16:30 / data gaps. Mirrored prices. → (exit idx, points, why)."""
    ns, mod = a["ns"], a["mod"]
    half, banked, left = 0.5, 0.0, 1.0
    for k in range(j, len(ns)):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:
            return k - 1, banked + left * (X["ex_c"][k - 1] - entry), "closure"
        if k > j and mod[k] >= FLAT:
            return k, banked + left * (X["ex_o"][k] - entry), "flat_1630"
        if X["ex_l"][k] <= stop:
            px = stop if k == j else min(stop, X["ex_o"][k])
            return k, banked + left * (px - entry), "stop" if left == 1.0 else "stop_after_tp1"
        if k > j and left == 1.0 and X["ex_h"][k] >= tp1:
            banked += half * (max(tp1, X["ex_o"][k]) - entry)
            left = half
        if k > j and left < 1.0 and X["ex_h"][k] >= tp2:
            return k, banked + left * (max(tp2, X["ex_o"][k]) - entry), "tp2"
    k = len(ns) - 1
    return k, banked + left * (X["ex_c"][k] - entry), "end"


def row(a, j, jx, side, entry, pts, risk, spread, why, **extra):
    return {"entry_time": a["idx"][j], "exit_time": a["idx"][jx], "side": side, "entry": side * entry, "atr": risk,
            "points": pts, "R": pts / risk, "R_2x": (pts - spread) / risk, "cost_R": spread / risk, "exit_reason": why,
            "hold_min": (a["ns"][jx] - a["ns"][j]) / 60e9, "overnight": False, **extra}


def execute(a: dict, setups: list[dict], blocked: np.ndarray, rng):
    ns, mod = a["ns"], a["mod"]
    XX = {1: mirrored_exec(a, 1), -1: mirrored_exec(a, -1)}
    trades, ctl = [], []
    busy, per_day = -1, {}
    for s in sorted(setups, key=lambda x: x["t"]):
        X, side = XX[s["side"]], s["side"]
        j0 = int(np.searchsorted(ns, s["t"]))
        if j0 <= busy or j0 >= len(ns):
            continue
        risk_plan = s["limit"] - s["stop"]
        if risk_plan <= 0:
            continue
        tp1 = max(s["tp1"] if np.isfinite(s["tp1"]) else -np.inf, s["limit"] + TP1_R * risk_plan)
        cancel_at = s["limit"] + CANCEL_FRAC * (tp1 - s["limit"])
        fill = None
        for k in range(j0, min(len(ns), j0 + LIMIT_MIN)):
            if k > j0 and ns[k] - ns[k - 1] > 60 * MIN:
                break
            if X["in_l"][k] <= s["limit"]:
                fill = (k, min(s["limit"], X["in_o"][k]))
                break
            if X["mid_h"][k] >= cancel_at or X["mid_l"][k] <= s["stop"]:
                break
        if fill is None:
            continue
        j, entry = fill
        if not (WIN[0] <= mod[j] < WIN[1]) or blocked[j]:
            continue
        day = (a["idx"][j].tz_convert(NY) + pd.Timedelta(hours=6)).date()
        if per_day.get(day, 0) >= MAX_DAY:
            continue
        risk = entry - s["stop"]
        if risk <= 0:
            continue
        tp1 = max(s["tp1"] if np.isfinite(s["tp1"]) else -np.inf, entry + TP1_R * risk)
        dol = s["dol"] if np.isfinite(s["dol"]) else -np.inf
        tp2 = max(dol, entry + TP2_R * risk, tp1)
        spread = a["ask_o"][j] - a["bid_o"][j]
        jx, pts, why = manage(a, X, j, entry, s["stop"], tp1, tp2)
        trades.append(row(a, j, jx, side, entry, pts, risk, spread, why, tp1_R=(tp1 - entry) / risk,
                          tp2_R=(tp2 - entry) / risk))
        busy, per_day[day] = jx, per_day.get(day, 0) + 1
        cs = int(rng.choice([1, -1]))
        if j + 1 < len(ns):
            C = XX[cs]
            ce = C["in_o"][j + 1]
            cjx, cpts, cwhy = manage(a, C, j + 1, ce, ce - risk, ce + (tp1 - entry), ce + (tp2 - entry))
            ctl.append(row(a, j + 1, cjx, cs, ce, cpts, risk, spread, cwhy))
    return trades, ctl


def prepare(m1: pd.DataFrame) -> dict:
    a = prep(m1)
    a["b60"], a["b15"], a["b5"], a["b3"] = candles(m1, 60), candles(m1, 15), candles(m1, 5), candles(m1, 3)
    b = a["b15"]
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    a["atr15"] = wilder(tr, 14).to_numpy()
    a["h1"] = {s: h1_state(a["b60"], s) for s in (1, -1)}
    return a


def run_set(ds: str, seed: int):
    m1 = load(Path("data/export") / ds / "XAUUSD_M1.csv.gz")
    a = prepare(m1)
    del m1
    blk = block_mask(a, 15, 15)
    out = {}
    for name, htf in (("rule", True), ("no HTF filter", False)):
        ss = find_setups(a, 1, htf) + find_setups(a, -1, htf)
        out[name] = execute(a, ss, blk, np.random.default_rng(seed))
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return out, days[days.dayofweek < 5].tz_localize(NY)


def judge(T: pd.DataFrame, days) -> dict:
    if not len(T):
        return {"trades": 0}
    st = stats(T, days) | pip_stats(T, PIP["XAUUSD"])
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    st["h1"], st["h2"] = float(T[et < mid].R.mean()), float(T[et >= mid].R.mean())
    return st


def evaluate(out, days) -> tuple[dict, bool]:
    T, C = (pd.DataFrame(x) for x in out["rule"])
    N = pd.DataFrame(out["no HTF filter"][0])
    res = {"rule": judge(T, days), "coin-flip control": judge(C, days), "no HTF filter": judge(N, days)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("coin-flip control", "no HTF filter")))
    return res, ok


def table(ds, res, ok, role):
    md = [f"### {ds} — {role}: **{'PASS' if ok else 'no pass'}**", "",
          "| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, s in res.items():
        if not s.get("trades"):
            md.append(f"| {nm} | 0 |" + " |" * 9)
            continue
        md.append(f"| {'**rule**' if nm == 'rule' else nm} | {s['trades']} | {s['win']:.0%} | {s['avg_R']:+.3f} | "
                  f"{s['ci_lo']:+.2f} to {s['ci_hi']:+.2f} | {s['avg_R_2x']:+.3f} | {s['h1']:+.3f} | {s['h2']:+.3f} | "
                  f"{s['total_R']:+.1f} | {s['pips_net']:+,.0f} | {s['hold_min_median']:.0f} min |")
    return md


def detail(T: pd.DataFrame) -> list[str]:
    if not len(T):
        return []
    why = ", ".join(f"{k} {v:.0%}" for k, v in T.exit_reason.value_counts(normalize=True).items())
    return ["", f"Exits: {why}. Long {T[T.side > 0].R.mean():+.3f} ({(T.side > 0).sum()}), short "
            f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}). Typical stop ${T.atr.median():.2f} (middle half "
            f"${T.atr.quantile(.25):.2f}–${T.atr.quantile(.75):.2f}); typical spread {T.cost_R.median():.0%} of it; "
            f"median TP1 {T.tp1_R.median():.1f}R, TP2 {T.tp2_R.median():.1f}R; median hold {T.hold_min.median():.0f} min.", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="dev_m1,holdout_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=43)
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    md = ["# SMC inducement trap → 5m CHoCH → 3m order-block limit (gold), scale-invariant spec", "",
          "Author's model in the author's own exact definitions (Oct 19 2026), every open point fixed in "
          "fxagents/smc_idm.py before any run. Real OANDA bid/ask fills (a limit fills only when the ask/bid actually "
          "trades there); R per whole position (50% TP1, 50% TP2) after spread; 2× costs pays one more spread.", "",
          "Gates: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, "
          "better than the coin flip and than the same model without the 1H bias. **Step 1:** the seen sets "
          "(2021 → Sep 2026) must clear every gate combined and be positive in each. **Step 2:** only then is the "
          "untouched 2016–2020 export opened, once, and judged.", ""]
    outs, dayss, rows = {}, {}, {}
    for ds in a_.known.split(","):
        outs[ds], dayss[ds] = run_set(ds, a_.seed)
        res, ok = evaluate(outs[ds], dayss[ds])
        rows[ds] = res
        T = pd.DataFrame(outs[ds]["rule"][0])
        T.to_csv(a_.out / f"trades_{ds}.csv.gz", index=False)
        md += table(ds, res, ok, "seen (step 1)") + detail(T)
        print(f"  {ds}: {len(T)} trades", flush=True)
    comb = {k: tuple(sum((list(outs[ds][k][i]) for ds in outs), []) for i in range(2)) for k in ("rule", "no HTF filter")}
    cdays = pd.DatetimeIndex(sorted(set().union(*[set(d) for d in dayss.values()])))
    cres, cok = evaluate(comb, cdays)
    step1 = cok and all(rows[ds]["rule"].get("avg_R", -1) > 0 for ds in outs)
    md += table("seen, combined", cres, cok, "step 1 gate")
    rows["combined"] = cres
    if FUNNEL:
        md += ["Setups reaching each stage (rule, longs + shorts, seen sets): "
               + " → ".join(f"{k} {v:,}" for k, v in FUNNEL.items())
               + f" → limit filled and taken {cres['rule'].get('trades', 0):,}", ""]
        FUNNEL.clear()
    if not step1:
        md += [f"**Step 1 failed — {a_.judge} was NOT opened** and stays untouched.", ""]
    elif not (Path("data/export") / a_.judge / "XAUUSD_M1.csv.gz").exists():
        md += [f"**Step 1 passed** — export {a_.judge} (2016–2020) and rerun to judge it.", ""]
    else:
        o2, d2 = run_set(a_.judge, a_.seed)
        r2, ok2 = evaluate(o2, d2)
        pd.DataFrame(o2["rule"][0]).to_csv(a_.out / f"trades_{a_.judge}.csv.gz", index=False)
        md += table(a_.judge, r2, ok2, "UNTOUCHED — judged once") + detail(pd.DataFrame(o2["rule"][0]))
        rows[a_.judge] = r2
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"step1": step1, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
