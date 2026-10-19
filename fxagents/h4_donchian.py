"""h4_donchian_trend_v1 — gold 4H 20-bar Donchian breakout with the 4H EMA200 trend and a 4H chandelier trail.
Pre-registered by the outside strategy author (spec "h4_donchian_trend_v1", frozen 2026-10-19). Their constants and
strategy functions are used VERBATIM (copied from their h4_donchian_trend_standalone.py) with ONE mechanical fix, below;
shared helpers (data loader, release calendar, statistics) are the project's identical versions.

    python -m fxagents.h4_donchian --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/h4_donchian_trend_v1
                                                                                                    (./fx.sh h4don)

Fix (recorded before any run, intent unchanged): the spec charges financing "every time a trade is held across 17:00
NY", but its code tests for a candle stamped exactly 17:00 (`mod[k] == 1020`). OANDA gold has a daily 17:00–18:00 NY
break with no candles, so that test would never fire and no financing would ever be charged. The check here is "the
previous candle was before 17:00 and this one is at/after it (or on the next day)", which charges every overnight hold
as the spec intends; the Wednesday triple is taken from the day the rollover happens (the candle before the break).
The report shows how many rollovers were charged.

Rules (theirs): signals on 4H NY-aligned bars (closing 01/05/09/13/17/21 NY); entries only at the 01:00, 05:00, 09:00
and 13:00 closes. Long when the 4H close is above a rising 4H EMA200 (higher than 6 bars ago), 4H ATR(14) ≥ 25 bps of
price, the bar closes above the prior 20 bars' high, the 20-bar channel is ≤ 6 ATR wide, the bar range ≤ 2.2 ATR and it
closes in its top 35%. Market fill the next minute on the real bid/ask. Stop = min(bar low, close − 1.2 ATR) − 0.2 ATR,
risk 1.2–2.2 ATR. No target: a chandelier trail (highest 4H close since entry − 2.2 ATR) at each 4H close; stop checks
use mid prices 16:55–18:05 NY; out after 5 days or Friday 16:30 NY. Financing 1.8 bps of price per rollover (×3 on
Wednesday), deducted from R and doubled in "2× costs". One position at a time; no fills within 15 min of FOMC/CPI/
NFP/PPI. Controls: coin flip (same minute, random side, same stop distance and management) and no EMA200 filter.

Protocol (theirs): Step 1 — 2021 → Sep 2026 (holdout_m1 + dev_m1) must clear every gate combined (≥ 100 trades,
avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than both controls) and
be positive in each set. Step 2 — only then is the untouched old_m1 (2016–2020) opened, once, and judged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN
from .simple_rules import NY, PIP, ema, load, pip_stats, stats, wilder

# ── Frozen constants for h4_donchian_trend_v1 ──
ENTRY_MODS = (60, 300, 540, 780)      # 01:00, 05:00, 09:00, 13:00 NY 4H bar closes
FRI_FLAT = 990                        # Friday 16:30 NY flat (no weekend gap risk)
ATR4_BPS = 0.0025                     # min 4H ATR = 25 bps of spot price
EMA_LEN = 200                         # 4H EMA(200) macro trend filter
DON_BARS = 20                         # 20 x 4H bars Donchian breakout channel
CH_MAX_ATR = 6.00                     # 20-bar channel width <= 6.0 * ATR4
BAR_MAX_ATR = 2.20                    # breakout bar range <= 2.2 * ATR4
TOP_CLOSE = 0.35                      # close in top 35% of 4H bar range
STOP_BUF_ATR = 0.20                   # buffer below 4H low
RISK_MIN_ATR, RISK_MAX_ATR = 1.20, 2.20
TRAIL_ATR = 2.20                      # Chandelier trail = peak_4h_close - 2.20 * ATR4
MAX_HOLD_MIN = 7200                   # max hold 120 hours (5 trading days)
SWAP_BPS = 0.00018                    # 1.8 bps per 17:00 NY rollover financing cost


def atr(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n).to_numpy()


def prepare(m1: pd.DataFrame) -> dict:
    a = {k: m1[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
                                             "m_o", "m_h", "m_l", "m_c")}
    a["idx"], a["ns"] = m1.index, m1.index.as_unit("ns").asi8
    loc = m1.index.tz_convert(NY)
    lns = loc.tz_localize(None).as_unit("ns").asi8
    a["mod"] = ((lns // MIN) % 1440).astype(int)
    a["dow_m1"] = loc.dayofweek.to_numpy(int)
    day = lns // (1440 * MIN)
    starts = np.r_[0, np.nonzero(np.diff(day))[0] + 1]
    a["date"] = {int(day[s]): str(loc[s].date()) for s in starts}

    # 4H NY-aligned bars (closing at 01:00, 05:00, 09:00, 13:00, 17:00, 21:00 NY)
    m_ny = m1.tz_convert(NY)
    r4 = m_ny.resample("4h", offset="1h", label="left", closed="left")
    b4 = pd.DataFrame({"o": r4["m_o"].first(), "h": r4["m_h"].max(), "l": r4["m_l"].min(), "c": r4["m_c"].last()}).dropna()
    b4_end_ny = b4.index + pd.Timedelta(hours=4)
    b4["end"] = b4_end_ny.tz_convert("UTC").as_unit("ns").asi8
    b4["end_mod"] = (b4_end_ny.hour * 60 + b4_end_ny.minute).to_numpy(int)
    b4["ema200"] = ema(b4.c, EMA_LEN).to_numpy()
    b4["atr"] = atr(b4, 14)
    a["b4"] = b4
    return a


def mirror(a: dict, side: int) -> dict:
    b4 = a["b4"]
    if side > 0:
        return {"o4": b4.o.to_numpy(), "h4": b4.h.to_numpy(), "l4": b4.l.to_numpy(), "c4": b4.c.to_numpy(),
                "e200": b4.ema200.to_numpy(), "in_o": a["ask_o"], "mid_l": a["m_l"],
                "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"], "ex_c": a["bid_c"]}
    return {"o4": -b4.o.to_numpy(), "h4": -b4.l.to_numpy(), "l4": -b4.h.to_numpy(), "c4": -b4.c.to_numpy(),
            "e200": -b4.ema200.to_numpy(), "in_o": -a["bid_o"], "mid_l": -a["m_h"],
            "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"], "ex_c": -a["ask_c"]}


def find_trades(a: dict, use_bias: bool = True) -> list[dict]:
    b4 = a["b4"]
    E4, END_MOD = b4.end.to_numpy(), b4.end_mod.to_numpy()
    atr4, raw_c4 = b4.atr.to_numpy(), b4.c.to_numpy()
    ns = a["ns"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    out = []
    for k in range(EMA_LEN + DON_BARS, len(b4)):
        if int(END_MOD[k]) not in ENTRY_MODS:
            continue
        a4 = float(atr4[k])
        if not np.isfinite(a4) or a4 < ATR4_BPS * raw_c4[k]:
            continue
        for side in (1, -1):
            M = MM[side]
            if use_bias:
                if not (M["c4"][k] > M["e200"][k] and M["e200"][k] > M["e200"][k - 6]):
                    continue
                mode = "h4_trend"
            else:
                mode = "no_bias"
            don_hi = float(M["h4"][k - DON_BARS:k].max())
            don_lo = float(M["l4"][k - DON_BARS:k].min())
            if (don_hi - don_lo) > CH_MAX_ATR * a4:
                continue
            o, h, l, c = M["o4"][k], M["h4"][k], M["l4"][k], M["c4"][k]
            rng = h - l
            if rng <= 0 or rng > BAR_MAX_ATR * a4:
                continue
            if c <= don_hi or c < h - TOP_CLOSE * rng:
                continue
            j = int(np.searchsorted(ns, E4[k]))
            if j >= len(ns) or ns[j] - E4[k] > 10 * MIN:
                continue
            stop_m = min(l, c - RISK_MIN_ATR * a4) - STOP_BUF_ATR * a4
            out.append({"j": j, "k4": k, "side": side, "stop_m": float(stop_m), "a4": a4, "mode": mode})
    out.sort(key=lambda x: x["j"])
    return out


def manage(a: dict, M: dict, j: int, k4_start: int, entry_m: float, stop_m: float):
    """4H Chandelier trailing stop, Friday 16:30 exit, and daily 17:00 rollover swap accounting."""
    ns, mod, dow = a["ns"], a["mod"], a["dow_m1"]
    b4 = a["b4"]
    E4, atr4 = b4.end.to_numpy(), b4.atr.to_numpy()
    stop = stop_m
    peak_c4 = M["c4"][k4_start]
    i4_cur = k4_start
    rollovers = 0
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 180 * MIN:                      # >3h non-weekend gap
            if dow[k - 1] != 4:
                swap_drag = rollovers * SWAP_BPS * abs(entry_m)
                return k - 1, (M["ex_c"][k - 1] - entry_m) - swap_drag, swap_drag, rollovers > 0, "closure"
        if k > j and mod[k - 1] < 1020 and (mod[k] >= 1020 or mod[k] < mod[k - 1]):   # crossed 17:00 NY (see note)
            rollovers += 3 if dow[k - 1] == 2 else 1                    # Wednesday triple swap
        if dow[k] == 4 and mod[k] >= FRI_FLAT and k > j:                # Friday 16:30 NY flat
            swap_drag = rollovers * SWAP_BPS * abs(entry_m)
            return k, (M["ex_o"][k] - entry_m) - swap_drag, swap_drag, rollovers > 0, "fri_flat"
        if (ns[k] - ns[j]) >= MAX_HOLD_MIN * MIN:
            swap_drag = rollovers * SWAP_BPS * abs(entry_m)
            return k, (M["ex_o"][k] - entry_m) - swap_drag, swap_drag, rollovers > 0, "max_hold"
        # Pause bid/ask stop trigger during 16:55–18:05 NY rollover spread spike unless mid breaches stop
        in_rollover = 1015 <= mod[k] <= 1085
        hit_stop = (M["mid_l"][k] <= stop) if in_rollover else (M["ex_l"][k] <= stop)
        if hit_stop:
            px = stop if k == j else min(stop, M["ex_o"][k])
            swap_drag = rollovers * SWAP_BPS * abs(entry_m)
            return k, (px - entry_m) - swap_drag, swap_drag, rollovers > 0, "stop" if stop == stop_m else "chandelier_trail"
        # Update 4H Chandelier trail whenever a new 4H bar closes
        if i4_cur + 1 < len(E4) and ns[k] + MIN >= E4[i4_cur + 1]:
            i4_cur += 1
            if np.isfinite(M["c4"][i4_cur]) and np.isfinite(atr4[i4_cur]):
                peak_c4 = max(peak_c4, float(M["c4"][i4_cur]))
                trail = peak_c4 - TRAIL_ATR * float(atr4[i4_cur])
                if trail < M["ex_c"][k]:
                    stop = max(stop, trail)
        k += 1
    k = len(ns) - 1
    swap_drag = rollovers * SWAP_BPS * abs(entry_m)
    return k, (M["ex_c"][k] - entry_m) - swap_drag, swap_drag, rollovers > 0, "end"


def row(a, j, jx, side, entry_m, pts, risk, total_cost, over, why, **extra) -> dict:
    return {"entry_time": a["idx"][j], "exit_time": a["idx"][jx], "side": side, "entry": side * entry_m,
            "atr": risk, "points": pts, "R": pts / risk, "R_2x": (pts - total_cost) / risk,
            "cost_R": total_cost / risk, "exit_reason": why,
            "hold_min": (a["ns"][jx] - a["ns"][j]) / 60e9, "overnight": over, **extra}


def execute(a: dict, ents: list[dict], blocked: np.ndarray, rng):
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    trades, ctl = [], []
    busy = -1
    for e in ents:
        j, side, k4 = e["j"], e["side"], e["k4"]
        if j <= busy or blocked[j]:
            continue
        M = MM[side]
        entry_m = M["in_o"][j]
        risk = entry_m - e["stop_m"]
        a4 = e.get("a4", risk)
        if not (RISK_MIN_ATR * a4 <= risk <= RISK_MAX_ATR * a4):
            continue
        spread = a["ask_o"][j] - a["bid_o"][j]
        jx, pts, swap_drag, over, why = manage(a, M, j, k4, entry_m, e["stop_m"])
        total_cost = spread + swap_drag
        trades.append(row(a, j, jx, side, entry_m, pts, risk, total_cost, over, why, mode=e["mode"], swap=swap_drag))
        busy = jx
        cs = int(rng.choice([1, -1]))
        if j + 1 < len(a["ns"]):
            C = MM[cs]
            ce = C["in_o"][j + 1]
            cjx, cpts, cswap, cover, cwhy = manage(a, C, j + 1, k4, ce, ce - risk)
            ctl.append(row(a, j + 1, cjx, cs, ce, cpts, risk, spread + cswap, cover, cwhy, mode="coin"))
    return trades, ctl


def judge(X, days, mid):
    st = stats(X, days) if len(X) else {"trades": 0}
    if len(X):
        et = pd.to_datetime(X.entry_time)
        a, b = X[et < mid], X[et >= mid]
        st |= {"h1": float(a.R.mean()) if len(a) else float("nan"), "h2": float(b.R.mean()) if len(b) else float("nan")}
        st |= pip_stats(X, PIP["XAUUSD"])
    return st


def run_set(ds: str, seed: int):
    a = prepare(load(Path("data/export") / ds / "XAUUSD_M1.csv.gz"))
    blk = block_mask(a, 15, 15)
    rng = np.random.default_rng(seed)
    tr, ctl = execute(a, find_trades(a, True), blk, rng)
    nb, _ = execute(a, find_trades(a, False), blk, rng)
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return (pd.DataFrame(tr), pd.DataFrame(ctl), pd.DataFrame(nb)), days[days.dayofweek < 5].tz_localize(NY)


def gates(T, C, N, days) -> tuple[dict, bool]:
    if not len(T):
        return {"rule": {"trades": 0}}, False
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    res = {"rule": judge(T, days, mid), "coin-flip control": judge(C, days, mid), "no 4H EMA200 bias": judge(N, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("coin-flip control", "no 4H EMA200 bias")))
    return res, ok


def table(name, role, res, ok) -> list[str]:
    md = [f"### {name} — {role}: **{'PASS' if ok else 'no pass'}**", "",
          "| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, s in res.items():
        if not s.get("trades"):
            md.append(f"| {nm} | 0 |" + " |" * 9)
            continue
        md.append(f"| {'**rule**' if nm == 'rule' else nm} | {s['trades']} | {s['win']:.0%} | {s['avg_R']:+.3f} | "
                  f"{s['ci_lo']:+.2f} to {s['ci_hi']:+.2f} | {s['avg_R_2x']:+.3f} | {s['h1']:+.3f} | {s['h2']:+.3f} | "
                  f"{s['total_R']:+.1f} | {s['pips_net']:+,.0f} | {s['hold_min_median']:.0f} min |")
    return md + [""]


def detail(T: pd.DataFrame) -> list[str]:
    if not len(T):
        return []
    why = ", ".join(f"{k} {v:.0%}" for k, v in T.exit_reason.value_counts(normalize=True).items())
    nroll = int(round((T.swap / (SWAP_BPS * T.entry.abs())).sum()))
    return [f"Exits: {why}. Held overnight: {T.overnight.mean():.0%}; rollovers charged: {nroll:,} (avg financing {(T.swap / T.atr).mean():.3f}R per trade). Long {T[T.side > 0].R.mean():+.3f} ({(T.side > 0).sum()}), short "
            f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}). Typical stop ${T.atr.median():.2f} (middle half "
            f"${T.atr.quantile(.25):.2f}–${T.atr.quantile(.75):.2f}); typical total cost (spread + financing) {T.cost_R.median():.1%} of it; median hold {T.hold_min.median() / 60:.1f} h.", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="dev_m1,holdout_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=37)
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    md = ["# h4_donchian_trend_v1 — gold 4H Donchian breakout + EMA200 trend + chandelier trail (author's pre-registered spec)", "",
          "Author's constants and strategy functions used verbatim (fxagents/h4_donchian.py; one recorded fix: overnight financing is charged on every "
          "17:00 NY crossing), frozen 2026-10-19 before any run. Real OANDA bid/ask fills; R after spread and overnight financing; 2× costs doubles both. **Step 1:** seen data "
          "2021 → Sep 2026 must clear every gate combined and be positive in each set. **Step 2:** only then is the "
          "untouched 2016–2020 export opened, once, and judged.", ""]
    sets, alldays, rows = {}, {}, {}
    for ds in a_.known.split(","):
        sets[ds], alldays[ds] = run_set(ds, a_.seed)
        sets[ds][0].to_csv(a_.out / f"trades_{ds}.csv.gz", index=False)
        res, ok = gates(*sets[ds], alldays[ds])
        rows[ds] = res
        md += table(ds, "seen (step 1)", res, ok) + detail(sets[ds][0])
        print(f"  {ds}: {len(sets[ds][0])} trades", flush=True)
    comb = [pd.concat([sets[ds][i] for ds in sets], ignore_index=True) for i in range(3)]
    cdays = pd.DatetimeIndex(sorted(set().union(*[set(d) for d in alldays.values()])))
    cres, cok = gates(*comb, cdays)
    rows["combined"] = cres
    step1 = cok and all(rows[ds]["rule"].get("avg_R", -1) > 0 for ds in sets)
    md += table("seen, combined", "step 1 gate", cres, cok)
    if not step1:
        md += [f"**Step 1 failed — {a_.judge} was NOT opened** and stays untouched.", ""]
    elif not (Path("data/export") / a_.judge / "XAUUSD_M1.csv.gz").exists():
        md += [f"**Step 1 passed** — export {a_.judge} (2016–2020) and rerun to judge it.", ""]
    else:
        s2, d2 = run_set(a_.judge, a_.seed)
        s2[0].to_csv(a_.out / f"trades_{a_.judge}.csv.gz", index=False)
        r2, ok2 = gates(*s2, d2)
        rows[a_.judge] = r2
        md += table(a_.judge, "UNTOUCHED — judged once", r2, ok2) + detail(s2[0])
        md += [f"**Verdict: {'PASS on untouched data — next is a forward paper record.' if ok2 else 'no pass on untouched data.'}**", ""]
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"step1": step1, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
