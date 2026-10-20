"""Failed-breakout reversal (gold) — the outside strategy author's "XAUUSD_Failed_Breakout_Reversal_Strategy.md"
v1.0 (Oct 19 2026). Their constants and strategy functions are used VERBATIM (copied from their
failed_breakout_reversal_standalone.py); shared helpers (data loader, statistics, release calendar — checked identical
to their copy) are the project's.

    python -m fxagents.failed_breakout --known holdout_m1,dev_m1 --judge old_m1 --out data/year_test/failed_breakout_v1
                                                                                                    (./fx.sh fbr)

Rules (theirs): reference range = 06:00–08:00 NY (≥ 30 minutes of data). Between 08:05 and 11:00 NY a 5m candle trades
below the range low (above the high for shorts) and closes back inside the range but below (above) its midpoint, the
previous 5m candle having closed inside the range; the last closed 15m efficiency ratio ER(8) ≤ 0.30 (choppy). Entry at
the next 3-minute boundary on the real bid/ask, unless price touched the midpoint or the stop first. Stop = the signal
candle's low − max(spread, 0.2 ATR14 5m); target = the range midpoint; out at 11:30 NY. Taken only if estimated cost
(spread + 0.05 ATR5 slippage) ≤ 20% of the stop distance and the net reward:risk after cost and OANDA Canada's 1%
conversion ≥ 1.5. One trade a day; none within 15 min of FOMC/CPI/NFP/PPI. R includes the 1% CAD conversion
(wins × 0.99, losses × 1.01). Controls: coin flip (same moment, random side, same stop and target distances) and the
author's boundary control (a simple touch of the range edge, without the close back inside).

Protocol (same as every frozen test): Step 1 — 2021 → Sep 2026 (holdout_m1 + dev_m1): ≥ 100 trades, avg R > 0, 95%
day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than both controls — combined, and
positive in each set. Step 2 — only then is the untouched old_m1 (2016–2020) opened, once, and judged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN
from .simple_rules import NY, PIP, load, pip_stats, wilder
from .simple_rules import stats as _stats

# ── Frozen constants from XAUUSD_Failed_Breakout_Reversal_Strategy.md ──
REF_START, REF_END = 360, 480         # 06:00 inclusive to 08:00 exclusive NY (minutes from 00:00 NY)
WIN = (480, 660)                      # 08:00–11:00 NY entry window; no entries after 11:00
FLAT = 690                            # 11:30 NY hard time exit
MAX_DAY = 1                           # First qualifying trade only; max 1 trade per day
ER_LEN = 8                            # 8 completed 15m intervals (9 closes)
ER_MAX = 0.30                         # Efficiency Ratio <= 0.30
BUF_ATR5 = 0.20                       # buffer = max(current_spread, 0.20 * ATR14_5m)
COST_STOP_MAX = 0.20                  # execution_cost / D <= 0.20
NET_RR_MIN = 1.50                     # ((T - C) * 0.99) / ((D + C) * 1.01) >= 1.50
CAD_WIN, CAD_LOSS = 0.99, 1.01        # OANDA Canada 1% FX conversion markup/markdown on USD P&L
FIXED_SPREAD, FIXED_SLIP = 0.54, 0.15 # Section 7 illustrative starting assumptions ($0.69 total)
DYN_SLIP_ATR5 = 0.05                  # Scale-invariant slippage allowance (~$0.15 at $3,850 gold)



def stats(t: pd.DataFrame, days: pd.DatetimeIndex, seed: int = 7) -> dict:
    """The project's statistics plus the author's 1.5× cost column."""
    st = _stats(t, days, seed)
    if len(t):
        st["avg_R_15x"] = float(t.R_15x.mean())
    return st


def candles(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    return b


def atr(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n).to_numpy()


def efficiency_ratio(c: pd.Series, n: int = 8) -> np.ndarray:
    """Section 4: ER = abs(C[t] - C[t-8]) / sum(abs(C[i] - C[i-1]), i=t-7..t)."""
    net = (c - c.shift(n)).abs()
    tot = c.diff().abs().rolling(n).sum()
    er = np.where(tot > 0, net / tot, np.nan)
    return er


def prepare(m1: pd.DataFrame) -> dict:
    a = {k: m1[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
                                             "m_o", "m_h", "m_l", "m_c")}
    a["idx"], a["ns"] = m1.index, m1.index.as_unit("ns").asi8
    loc = m1.index.tz_convert(NY)
    lns = loc.tz_localize(None).as_unit("ns").asi8
    a["mod"] = ((lns // MIN) % 1440).astype(int)
    day = lns // (1440 * MIN)
    starts = np.r_[0, np.nonzero(np.diff(day))[0] + 1]
    a["date"] = {int(day[s]): str(loc[s].date()) for s in starts}
    a["sess"] = np.array([d.toordinal() for d in loc.date])

    b15, b5 = candles(m1, 15), candles(m1, 5)
    b15["er"] = efficiency_ratio(b15.c, ER_LEN)
    b5["atr"] = atr(b5, 14)
    a["b15"], a["b5"] = b15, b5

    # Section 2: Reference range from 06:00 inclusive to 08:00 exclusive NY time
    df = pd.DataFrame({"s": a["sess"], "mod": a["mod"], "h": a["m_h"], "l": a["m_l"]})
    ref = df[(df["mod"] >= REF_START) & (df["mod"] < REF_END)].groupby("s").agg(h=("h", "max"), l=("l", "min"), n=("h", "count"))
    ranges = {}
    for s, row_ in ref.iterrows():
        if row_["n"] >= 30 and np.isfinite(row_["h"]) and np.isfinite(row_["l"]) and row_["h"] > row_["l"]:
            ranges[int(s)] = (float(row_["h"]), float(row_["l"]))
    a["ranges"] = ranges
    return a


def mirror(a: dict, side: int) -> dict:
    b5 = a["b5"]
    if side > 0:
        return {"o5": b5.o.to_numpy(), "h5": b5.h.to_numpy(), "l5": b5.l.to_numpy(), "c5": b5.c.to_numpy(),
                "m_o": a["m_o"], "m_h": a["m_h"], "m_l": a["m_l"],
                "in_o": a["ask_o"], "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"], "ex_c": a["bid_c"]}
    return {"o5": -b5.o.to_numpy(), "h5": -b5.l.to_numpy(), "l5": -b5.h.to_numpy(), "c5": -b5.c.to_numpy(),
            "m_o": -a["m_o"], "m_h": -a["m_l"], "m_l": -a["m_h"],
            "in_o": -a["bid_o"], "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"], "ex_c": -a["ask_c"]}


def next_3m_open(ns: np.ndarray, mod: np.ndarray, t_sig_end: int) -> int | None:
    """Section 2 & 5: First available quote at the next 3-minute bar opening after the 5m signal closes."""
    j0 = int(np.searchsorted(ns, t_sig_end))
    for j in range(j0, min(j0 + 5, len(ns))):
        if ns[j] - t_sig_end > 5 * MIN:
            return None
        if mod[j] % 3 == 0:
            return j
    return None


def find_signals(a: dict, blocked: np.ndarray, cost_mode: str = "dynamic",
                 boundary_control: bool = False) -> tuple[list[dict], dict]:
    """Scan 5m candles for failed-breakout signals and record the exact filter funnel."""
    b15, b5 = a["b15"], a["b5"]
    E15, E5 = b15.end.to_numpy(), b5.end.to_numpy()
    er15, atr5 = b15.er.to_numpy(), b5.atr.to_numpy()
    ns, mod, sess = a["ns"], a["mod"], a["sess"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}

    funnel = {
        "1_days_with_0600_0800_range": len(a["ranges"]),
        "2_5m_breach_and_close_inside_below_mid": 0,
        "3_prev_5m_closed_inside_range": 0,
        "4_er15_le_030": 0,
        "5_news_and_3m_open_valid": 0,
        "6_not_invalidated_before_3m_open": 0,
        "7_pass_cost_to_stop_le_020": 0,
        "8_pass_net_rr_ge_150": 0,
        "9_first_qualifying_trade_of_day": 0,
    }

    out = []
    taken_days = set()

    for k in range(20, len(b5)):
        j_sig = int(np.searchsorted(ns, E5[k])) - 1                    # last minute of 5m signal candle k
        if j_sig < 0:
            continue
        end_min = mod[j_sig] + 1                                       # NY minute of 5m close
        if not (WIN[0] < end_min <= WIN[1]):                           # 5m signal closes in (08:00, 11:00] NY
            continue
        sd_ = int(sess[j_sig])
        if sd_ not in a["ranges"]:
            continue
        r_hi, r_lo = a["ranges"][sd_]
        r_mid = 0.5 * (r_hi + r_lo)

        i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
        if i15 < ER_LEN or not np.isfinite(atr5[k]):
            continue
        a5 = float(atr5[k])

        for side in (1, -1):
            M = MM[side]
            # Mirrored range boundaries: for longs (+1), range_low = r_lo, range_high = r_hi, mid = r_mid
            # For shorts (-1), range_low (the upper boundary breached) = -r_hi, range_high = -r_lo, mid = -r_mid
            bnd_near = r_lo if side > 0 else -r_hi
            bnd_far = r_hi if side > 0 else -r_lo
            mid_m = r_mid if side > 0 else -r_mid

            l_k, c_k, h_k = M["l5"][k], M["c5"][k], M["h5"][k]
            c_prev = M["c5"][k - 1]

            if not boundary_control:
                # Section 5.2 & 5.3: Signal low is below frozen range low, and closes back inside range & below midpoint
                if not (l_k < bnd_near and bnd_near <= c_k < mid_m):
                    continue
                funnel["2_5m_breach_and_close_inside_below_mid"] += 1

                # Section 5.1: Preceding completed 5m candle closed inside the frozen range
                if not (bnd_near <= c_prev <= bnd_far):
                    continue
                funnel["3_prev_5m_closed_inside_range"] += 1
            else:
                # Section 10.4 Control: simpler range-boundary touch while inside range without requiring close back inside
                if not (l_k <= bnd_near and c_k < mid_m and bnd_near <= c_prev <= bnd_far):
                    continue

            # Section 4: Latest completed 15m efficiency ratio <= 0.30
            if not np.isfinite(er15[i15]) or er15[i15] > ER_MAX:
                continue
            if not boundary_control:
                funnel["4_er15_le_030"] += 1

            # Section 2 & 5.6: Next scheduled 3-minute bar opening
            j_exec = next_3m_open(ns, mod, int(E5[k]))
            if j_exec is None or mod[j_exec] > WIN[1] or blocked[j_exec]:
                continue
            if not boundary_control:
                funnel["5_news_and_3m_open_valid"] += 1

            spread = float(a["ask_o"][j_exec] - a["bid_o"][j_exec])
            if spread <= 0:
                continue
            buf = max(spread, BUF_ATR5 * a5)
            stop_mid = float(l_k - buf)

            # Check if midpoint or stop was already breached between 5m close and 3m open
            j_after_5m = int(np.searchsorted(ns, E5[k]))
            if j_exec > j_after_5m:
                if M["m_h"][j_after_5m:j_exec].max() >= mid_m or M["m_l"][j_after_5m:j_exec].min() <= stop_mid:
                    continue
            if M["m_o"][j_exec] >= mid_m or M["m_o"][j_exec] <= stop_mid:
                continue
            if not boundary_control:
                funnel["6_not_invalidated_before_3m_open"] += 1

            # Section 7: Cost and reward-to-risk eligibility checks at the 3m opening
            D = float(M["m_o"][j_exec] - stop_mid)
            T = float(mid_m - M["m_o"][j_exec])
            if D <= 0 or T <= 0:
                continue

            if cost_mode == "fixed":
                C = FIXED_SPREAD + FIXED_SLIP
            else:
                C = spread + DYN_SLIP_ATR5 * a5

            if (C / D) > COST_STOP_MAX:
                continue
            if not boundary_control:
                funnel["7_pass_cost_to_stop_le_020"] += 1

            net_rr = ((T - C) * CAD_WIN) / ((D + C) * CAD_LOSS)
            if net_rr < NET_RR_MIN:
                continue
            if not boundary_control:
                funnel["8_pass_net_rr_ge_150"] += 1

            if sd_ in taken_days:
                continue
            taken_days.add(sd_)
            if not boundary_control:
                funnel["9_first_qualifying_trade_of_day"] += 1

            out.append({
                "j": j_exec, "side": side, "stop_m": stop_mid, "target_m": float(mid_m),
                "D_mid": D, "T_mid": T, "C_est": C, "net_rr_plan": net_rr,
                "sess": sd_, "mode": "boundary_ctl" if boundary_control else "failed_brk"
            })
    out.sort(key=lambda x: x["j"])
    return out, funnel


def manage(a: dict, M: dict, j: int, entry_m: float, stop_m: float, target_m: float):
    """Section 2 & 9: Exit at frozen range midpoint, protective stop, or 11:30 NY time (conservative stop-first)."""
    ns, mod = a["ns"], a["mod"]
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:
            return k - 1, M["ex_c"][k - 1] - entry_m, "closure"
        if mod[k] >= FLAT and k > j:
            return k, M["ex_o"][k] - entry_m, "flat_1130"
        # Section 10.3: Conservative stop-first resolution if a 1m bar touches both stop and target
        if M["ex_l"][k] <= stop_m:
            px = stop_m if k == j else min(stop_m, M["ex_o"][k])
            return k, px - entry_m, "stop"
        if M["ex_h"][k] >= target_m:
            px = target_m if k == j else max(target_m, M["ex_o"][k])
            return k, px - entry_m, "midpoint_target"
        k += 1
    k = len(ns) - 1
    return k, M["ex_c"][k] - entry_m, "end"


def apply_cad_fx(pts: float) -> float:
    """Section 7: OANDA Canada 1% conversion markup/markdown reduces USD wins by 1% and increases losses by 1%."""
    return pts * CAD_WIN if pts >= 0 else pts * CAD_LOSS


def row(a, j, jx, side, entry_m, raw_pts, risk, spread, why, **extra) -> dict:
    pts_cad = apply_cad_fx(raw_pts)
    pts_15x = apply_cad_fx(raw_pts - 0.5 * spread)
    pts_2x = apply_cad_fx(raw_pts - spread)
    risk_cad = risk * CAD_LOSS
    return {"entry_time": a["idx"][j], "exit_time": a["idx"][jx], "side": side, "entry": side * entry_m,
            "atr": risk_cad, "points": pts_cad, "R": pts_cad / risk_cad,
            "R_15x": pts_15x / risk_cad, "R_2x": pts_2x / risk_cad,
            "cost_R": (spread * CAD_LOSS) / risk_cad, "exit_reason": why,
            "hold_min": (a["ns"][jx] - a["ns"][j]) / 60e9, "overnight": False, **extra}


def execute(a: dict, ents: list[dict], rng):
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    trades, ctl = [], []
    busy = -1
    for e in ents:
        j, side = e["j"], e["side"]
        if j <= busy:
            continue
        M = MM[side]
        entry_m = float(M["in_o"][j])                                  # actual executable Ask (long) or Bid (short)
        stop_m, target_m = e["stop_m"], e["target_m"]
        risk = entry_m - stop_m
        if risk <= 0 or target_m <= entry_m:
            continue
        spread = float(a["ask_o"][j] - a["bid_o"][j])
        jx, raw_pts, why = manage(a, M, j, entry_m, stop_m, target_m)
        trades.append(row(a, j, jx, side, entry_m, raw_pts, risk, spread, why, mode=e["mode"]))
        busy = jx

        # Coin-flip control at the exact same moment with identical stop & target distance
        cs = int(rng.choice([1, -1]))
        if j + 1 < len(a["ns"]):
            C = MM[cs]
            ce = float(C["in_o"][j + 1])
            t_dist = target_m - entry_m
            cjx, cpts, cwhy = manage(a, C, j + 1, ce, ce - risk, ce + t_dist)
            ctl.append(row(a, j + 1, cjx, cs, ce, cpts, risk, spread, cwhy, mode="coin"))
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
    ents, funnel = find_signals(a, blk, cost_mode="dynamic", boundary_control=False)
    b_ents, _ = find_signals(a, blk, cost_mode="dynamic", boundary_control=True)
    tr, ctl = execute(a, ents, rng)
    b_tr, _ = execute(a, b_ents, rng)
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return (pd.DataFrame(tr), pd.DataFrame(ctl), pd.DataFrame(b_tr)), days[days.dayofweek < 5].tz_localize(NY), funnel


def gates(T, C, B, days) -> tuple[dict, bool]:
    if not len(T):
        return {"rule": {"trades": 0}}, False
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    res = {"rule": judge(T, days, mid), "coin-flip control": judge(C, days, mid),
           "boundary control": judge(B, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("coin-flip control", "boundary control")))
    return res, ok


def table(name, role, res, ok) -> list[str]:
    md = [f"### {name} — {role}: **{'PASS' if ok else 'no pass'}**", "",
          "| Test | Trades | Win | Avg R | 95% range | 1.5× costs | 2× costs | 1st half | 2nd half | Total R | Median hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, s in res.items():
        if not s.get("trades"):
            md.append(f"| {nm} | 0 |" + " |" * 9)
            continue
        md.append(f"| {'**rule**' if nm == 'rule' else nm} | {s['trades']} | {s['win']:.0%} | {s['avg_R']:+.3f} | "
                  f"{s['ci_lo']:+.2f} to {s['ci_hi']:+.2f} | {s['avg_R_15x']:+.3f} | {s['avg_R_2x']:+.3f} | "
                  f"{s['h1']:+.3f} | {s['h2']:+.3f} | {s['total_R']:+.1f} | {s['hold_min_median']:.0f} min |")
    return md + [""]


def detail(T: pd.DataFrame, funnel: dict | None) -> list[str]:
    md = []
    if funnel:
        md.append("Signal funnel: " + " → ".join(f"{k.split('_', 1)[1].replace('_', ' ')} {v:,}" for k, v in funnel.items()))
    if len(T):
        why = ", ".join(f"{k} {v:.0%}" for k, v in T.exit_reason.value_counts(normalize=True).items())
        md.append(f"Exits: {why}. Long {T[T.side > 0].R.mean():+.3f} ({(T.side > 0).sum()}), short "
                  f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}). Typical stop ${T.atr.median():.2f} (middle half "
                  f"${T.atr.quantile(.25):.2f}–${T.atr.quantile(.75):.2f}); spread {T.cost_R.median():.0%} of it.")
    return md + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="holdout_m1,dev_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=37)
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    md = ["# Failed-breakout reversal (gold) — author's v1.0 spec, functions verbatim", "",
          "06:00–08:00 NY range, 5m failed break back inside below the midpoint in a choppy 15m market (ER ≤ 0.30), "
          "entry at the next 3-minute boundary, target the range midpoint, stop beyond the signal candle, out 11:30 NY. "
          "Real OANDA bid/ask; R after spread and OANDA Canada's 1% CAD conversion. **Step 1:** 2021 → Sep 2026 must clear "
          "every gate combined and be positive in each set. **Step 2:** only then is untouched 2016–2020 opened, once.", ""]
    sets, alldays, rows = {}, {}, {}
    for ds in a_.known.split(","):
        sets[ds], alldays[ds], funnel = run_set(ds, a_.seed)
        sets[ds][0].to_csv(a_.out / f"trades_{ds}.csv.gz", index=False)
        res, ok = gates(*sets[ds], alldays[ds])
        rows[ds] = res
        md += table(ds, "seen (step 1)", res, ok) + detail(sets[ds][0], funnel)
        print(f"  {ds}: {len(sets[ds][0])} trades", flush=True)
    comb = [pd.concat([sets[ds][i] for ds in sets], ignore_index=True) for i in range(3)]
    cdays = pd.DatetimeIndex(sorted(set().union(*[set(d) for d in alldays.values()])))
    cres, cok = gates(*comb, cdays)
    rows["combined"] = cres
    step1 = cok and all(rows[ds]["rule"].get("avg_R", -1) > 0 for ds in sets)
    md += table("seen, combined", "step 1 gate", cres, cok)
    if not step1:
        md += [f"**Step 1 failed — {a_.judge} was NOT opened** and stays untouched.", ""]
    else:
        s2, d2, f2 = run_set(a_.judge, a_.seed)
        s2[0].to_csv(a_.out / f"trades_{a_.judge}.csv.gz", index=False)
        r2, ok2 = gates(*s2, d2)
        rows[a_.judge] = r2
        md += table(a_.judge, "UNTOUCHED — judged once", r2, ok2) + detail(s2[0], f2)
        md += [f"**Verdict: {'PASS on untouched data — next is a forward paper record.' if ok2 else 'no pass on untouched data.'}**", ""]
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"step1": step1, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
