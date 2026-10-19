"""sweep_reclaim_v2 — gold 15m sweep → 5m reclaim, ATR-scaled. Proposed by the outside strategy author (Oct 19 2026)
after seeing the sweep + VWAP results; their code, used as given, frozen here before any run.

    python -m fxagents.sweep_reclaim_v2 --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/sweep_reclaim_v2
                                                                                            (./fx.sh reclaimv2)

The rule (their constants, unchanged):
  Window     entries 08:00–11:30 NY, flat 16:30, at most 1 trade per session day (18:00→17:00), one at a time.
  Volatility 15m ATR(14) ≥ 8 bps of the 15m close (scale-free version of the old $2.50 floor).
  Sweep      within the last six 15m candles (and from 06:00 NY), a 15m candle traded through a liquidity level (Asian /
             London / previous-day low for longs, highs for shorts), closed back beyond it, lower wick ≥ 40% of its
             range, excursion past the level ≤ 1.5 × ATR15. Fresh sweeps in both directions → no trade.
  Entry      a 5m candle in the trade's direction (body ≥ 50% of range) that tests the swept level (low ≤ level +
             0.25 × ATR15), closes back beyond it, and is still on the far side of the session VWAP (long: close < VWAP)
             → market at the next minute on the real bid/ask.
  Stop       0.15 × ATR15 beyond the lower of the sweep low and the 5m low. Skipped unless risk is 0.6–2.2 × ATR15.
  Room       skipped if an opposing level (Asian / London / previous-day high) is less than 1.5R away.
  Exit       one target at +1.8R, the stop, or 16:30 NY. No partials, no break-even move.
  Controls   coin flip (same minute, random side, same stop distance and exits).

Note on the code as given (not changed, recorded): London levels (02:00–08:00) are only complete at 08:00, and a candle
inside that window can never close beyond them, so before 08:00 only the Asian and previous-day levels can be swept.
This uses no future data.

Protocol (agreed with the author, fixed before running):
  1. KNOWN data — dev_m1 (Oct 2024–Sep 2026) and holdout_m1 (2021–Sep 2024), both already seen, shown only. The rule
     must clear every gate on the two combined: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2×
     costs, positive in both halves, better than the coin flip — and be positive in each of the two sets.
  2. Only if step 1 passes, the UNTOUCHED old_m1 export (2016–2020, never opened by any test) is read once and judged
     with the same gates. If step 1 fails, old_m1 is not opened and stays clean for future ideas.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN
from .simple_rules import NY, load
from .sweep_vwap import judge, lows_of, mirror, prepare, row

# ── Frozen constants for sweep_reclaim_v2 (as given) ──
WIN = (480, 690)                  # 08:00–11:30 NY entries
FLAT = 990                        # 16:30 NY flat
MAX_DAY = 1                       # at most 1 trade per session day
ATR15_BPS = 0.0008                # min 15m ATR = 8 bps of spot price (scale-invariant)
WICK15, SWEEP_MAX_ATR = 0.40, 1.5 # 15m sweep wick >= 40% range; excursion <= 1.5 * ATR15
RECLAIM_TOUCH_ATR = 0.25          # 5m low must test within 0.25 * ATR15 of swept level
BODY5 = 0.50                      # 5m reclaim candle body >= 50% of its range
STOP_ATR_BUF = 0.15               # stop buffer = 0.15 * ATR15 beyond sweep/trigger low
RISK_MIN_ATR, RISK_MAX_ATR = 0.60, 2.20
ROOM_R, TP_R = 1.5, 1.8           # opposing level >= 1.5R away; full exit at +1.8R


def bias_v2(a: dict, M: dict, other: dict, sess: int, side: int, i15_last: int,
            i15_from: int, atr15: np.ndarray) -> tuple[float | None, float | None]:
    """→ (swept_level, sweep_extreme_low) for `side` if a fresh 15m sweep occurred in [i15_from, i15_last]."""
    def swept(MM, sd):
        lv, _ = lows_of(a, sess, sd)
        best_lvl, best_lo = None, None
        for i in range(i15_from, i15_last + 1):
            rng = MM["h15"][i] - MM["l15"][i]
            a15 = atr15[i]
            if rng <= 0 or not np.isfinite(a15) or a15 <= 0:
                continue
            wick = min(MM["o15"][i], MM["c15"][i]) - MM["l15"][i]
            if wick < WICK15 * rng:
                continue
            for L in lv:
                if MM["l15"][i] < L < MM["c15"][i] and (L - MM["l15"][i]) <= SWEEP_MAX_ATR * a15:
                    best_lvl, best_lo = L, MM["l15"][i]
        return best_lvl, best_lo

    mine_lvl, mine_lo = swept(M, side)
    theirs_lvl, _ = swept(other, -side)
    if mine_lvl is None or theirs_lvl is not None:
        return None, None
    return mine_lvl, mine_lo


def find_trades(a: dict, use_bias: bool = True, sweep_only: bool = True) -> list[dict]:
    """Causal 5m sweep-reclaim entries (scale-invariant across 2016–2026 gold prices)."""
    b15, b5 = a["b15"], a["b5"]
    E15, E5 = b15.end.to_numpy(), b5.end.to_numpy()
    atr15 = b15.atr.to_numpy()
    raw_c15 = b15.c.to_numpy()
    ns, mod, sess = a["ns"], a["mod"], a["sess"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    out = []
    for k in range(20, len(b5)):
        j_end = int(np.searchsorted(ns, E5[k])) - 1
        if j_end < 0 or not (WIN[0] <= mod[j_end] + 1 <= WIN[1]):
            continue
        sd_ = int(sess[j_end])
        i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
        if i15 < 60 or not np.isfinite(atr15[i15]) or atr15[i15] < ATR15_BPS * raw_c15[i15]:
            continue
        a15 = float(atr15[i15])
        day0 = ns[j_end] - (mod[j_end] - WIN[0]) * MIN               # 08:00 NY today
        i15_0600 = int(np.searchsorted(E15, day0 - 105 * MIN))        # 06:00 NY pre-market onward
        i15_from = max(i15_0600, i15 - 5)                             # fresh sweep within last 6 x 15m bars (90m)
        for side in (1, -1):
            M, O = MM[side], MM[-side]
            if use_bias:
                lvl, sw_lo = bias_v2(a, M, O, sd_, side, i15, i15_from, atr15)
                if lvl is None:
                    continue
                mode = "sweep"
            else:
                lvl, sw_lo, mode = M["o5"][k], M["l5"][k], "none"
            o, h, l, c = M["o5"][k], M["h5"][k], M["l5"][k], M["c5"][k]
            rng = h - l
            if rng <= 0 or (c - o) < BODY5 * rng:
                continue
            vw = M["vwap"][j_end]
            # Reclaim check: 5m candle tests near swept level, closes back above it, while still below VWAP
            if use_bias and not (l <= lvl + RECLAIM_TOUCH_ATR * a15 and c > lvl and c < vw):
                continue
            j = int(np.searchsorted(ns, E5[k]))
            if j >= len(ns) or ns[j] - E5[k] > 5 * MIN or mod[j] >= WIN[1]:
                continue
            base_lo = min(sw_lo, l) if use_bias else l
            stop_m = base_lo - STOP_ATR_BUF * a15
            out.append({"j": j, "side": side, "stop_m": float(stop_m), "a15": a15, "mode": mode, "sess": sd_})
    out.sort(key=lambda x: x["j"])
    return out


def manage(a: dict, M: dict, j: int, entry_m: float, stop_m: float):
    """Single full target at +1.8R, structural stop, flat at 16:30 NY."""
    ns, mod = a["ns"], a["mod"]
    risk = entry_m - stop_m
    tp = entry_m + TP_R * risk
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:
            return k - 1, M["ex_c"][k - 1] - entry_m, "closure"
        if mod[k] >= FLAT and k > j:
            return k, M["ex_o"][k] - entry_m, "flat_1630"
        if M["ex_l"][k] <= stop_m:
            px = stop_m if k == j else min(stop_m, M["ex_o"][k])
            return k, px - entry_m, "stop"
        if k > j and M["ex_h"][k] >= tp:
            return k, max(tp, M["ex_o"][k]) - entry_m, "target"
        k += 1
    k = len(ns) - 1
    return k, M["ex_c"][k] - entry_m, "end"


def execute(a: dict, ents: list[dict], blocked: np.ndarray, rng):
    """The harness's execute() with the author's risk / room replacement and MAX_DAY = 1."""
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    trades, ctl = [], []
    busy, per_day = -1, {}
    for e in ents:
        j, side = e["j"], e["side"]
        if j <= busy or blocked[j] or per_day.get(e["sess"], 0) >= MAX_DAY:
            continue
        M = MM[side]
        entry_m = M["in_o"][j]
        risk = entry_m - e["stop_m"]
        a15 = e.get("a15", risk)
        if not (RISK_MIN_ATR * a15 <= risk <= RISK_MAX_ATR * a15):
            continue
        _, opp = lows_of(a, e["sess"], side)
        if any(0 < x - entry_m < ROOM_R * risk for x in opp):
            continue
        spread = a["ask_o"][j] - a["bid_o"][j]
        jx, pts, why = manage(a, M, j, entry_m, e["stop_m"])
        trades.append(row(a, j, jx, side, entry_m, pts, risk, spread, why, mode=e["mode"]))
        busy = jx
        per_day[e["sess"]] = per_day.get(e["sess"], 0) + 1
        cs = int(rng.choice([1, -1]))
        if j + 1 < len(a["ns"]):
            C = MM[cs]
            ce = C["in_o"][j + 1]
            cjx, cpts, cwhy = manage(a, C, j + 1, ce, ce - risk)
            ctl.append(row(a, j + 1, cjx, cs, ce, cpts, risk, spread, cwhy, mode="coin"))
    return trades, ctl


def run_set(ds: str, seed: int):
    m1 = load(Path("data/export") / ds / "XAUUSD_M1.csv.gz")
    a = prepare(m1)
    del m1
    tr, ctl = execute(a, find_trades(a), block_mask(a, 15, 15), np.random.default_rng(seed))
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return pd.DataFrame(tr), pd.DataFrame(ctl), days[days.dayofweek < 5].tz_localize(NY), \
        float(np.nanmedian(a["m_c"]))


def gates(T: pd.DataFrame, C: pd.DataFrame, days) -> dict:
    if not len(T):
        return {"trades": 0, "passed": False}
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    st, cst = judge(T, days, mid), judge(C, days, mid)
    st["ctl_avg_R"] = cst.get("avg_R", float("nan"))
    st["passed"] = bool(st.get("pass") and st["h1"] > 0 and st["h2"] > 0 and st["avg_R"] > st["ctl_avg_R"])
    return st


def line(name, role, st, px=None):
    if not st.get("trades"):
        return f"| {name} | {role} | — | 0 |" + " |" * 9
    v = "**PASS**" if st["passed"] else "**no pass**"
    return (f"| {name} | {role} | {v} | {st['trades']} | {st['win']:.0%} | {st['avg_R']:+.3f} | {st['ci_lo']:+.2f} to "
            f"{st['ci_hi']:+.2f} | {st['avg_R_2x']:+.3f} | {st['h1']:+.3f} | {st['h2']:+.3f} | {st['ctl_avg_R']:+.3f} | "
            + (f"${px:,.0f} |" if px else " |"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="dev_m1,holdout_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=41)
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    known = {}
    for ds in a_.known.split(","):
        known[ds] = run_set(ds, a_.seed)
        known[ds][0].to_csv(a_.out / f"trades_{ds}.csv.gz", index=False)
        print(f"  {ds}: {len(known[ds][0])} trades", flush=True)
    KT = pd.concat([v[0] for v in known.values()], ignore_index=True)
    KC = pd.concat([v[1] for v in known.values()], ignore_index=True)
    kdays = pd.DatetimeIndex(sorted(set().union(*[set(v[2]) for v in known.values()])))
    each = {ds: gates(v[0], v[1], v[2]) for ds, v in known.items()}
    comb = gates(KT, KC, kdays)
    step1 = bool(comb["passed"] and all(s.get("avg_R", -1) > 0 for s in each.values()))
    md = ["# sweep_reclaim_v2 — gold 15m sweep → 5m reclaim, ATR-scaled (author's code, frozen Oct 19 2026)", "",
          "Rules exactly as supplied (fxagents/sweep_reclaim_v2.py). Real OANDA bid/ask fills; R after spread; 2× costs "
          "pays one more spread. Gates: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, "
          "positive in both halves, better than the coin flip.", "",
          "**Protocol (fixed before running):** step 1 — the two already-seen sets must clear every gate combined and be "
          "positive in each. Step 2 — only then is the untouched 2016–2020 export opened, once, and judged.", "",
          "| Data | Role | Gates | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Coin flip | Median gold |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ds, v in known.items():
        md.append(line(ds, "seen (step 1)", each[ds], v[3]))
    md.append(line("**seen, combined**", "step 1 gate", comb))
    if not step1:
        md += ["", f"**Step 1 failed — {a_.judge} was NOT opened** and stays untouched for future ideas.", ""]
    else:
        T, C, days, px = run_set(a_.judge, a_.seed)
        T.to_csv(a_.out / f"trades_{a_.judge}.csv.gz", index=False)
        fin = gates(T, C, days)
        md.append(line(f"**{a_.judge}**", "UNTOUCHED — judged", fin, px))
        md += ["", "**Verdict: " + ("PASS on untouched data — next is a forward paper record.**" if fin["passed"] else
                                     "no pass on untouched data.**"), ""]
    for ds, v in known.items():
        T = v[0]
        if len(T):
            why = ", ".join(f"{k} {x:.0%}" for k, x in T.exit_reason.value_counts(normalize=True).items())
            md.append(f"- {ds}: exits {why}; long {T[T.side > 0].R.mean():+.3f} ({(T.side > 0).sum()}), short "
                      f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}); typical stop ${T.atr.median():.2f}, "
                      f"spread {T.cost_R.median():.0%} of it.")
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"step1": step1, "each": each, "combined": comb}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
