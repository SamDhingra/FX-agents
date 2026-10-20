"""ndq_orb_vwap_v1 — NAS100 09:30–09:45 NY opening-range breakout with the cash-session VWAP. Pre-registered by the
outside strategy author (spec "ndq_orb_vwap_v1", frozen 2026-10-20). Their constants and strategy functions are used
verbatim (from their ndq_orb_vwap_standalone.py) with the fixes below, recorded before any run; shared helpers (data
loader, statistics, release calendar — checked identical to their copy) are the project's.

    python -m fxagents.ndq_orb --known holdout_m1,dev_m1 --judge old_m1_idx_NDQ --out data/year_test/ndq_orb_vwap_v1
                                                                                                        (./fx.sh ndqorb)

Fixes, each bringing the code in line with the written spec (intent unchanged):
  1. execute(): the coin-flip block was mis-indented — the file as sent does not run (IndentationError).
  2. spec 1.2: "at 09:45 NY (close of the 09:30–09:45 bar i15_or), a15 = ATR(14)_15m[i15_or]" and the 12 bps floor on
     close_15m[i15_or] — the code read the LATEST closed 15m bar at each 3m candle instead. Now read at i15_or.
  3. spec 1.3: "the last closed 1H close is above e50_1h" — the code compared the latest 15m close with the 1H EMA. Now
     the 1H close.
  4. spec 1.3: "… or above e50_15m" refers to the opening-range close c15[i15_or] — follows from fix 2.
  The spec's prose for the stop says "l3[m] − 0.25 a15" but its formula, table and code say 0.15 — 0.15 is used.
Cost accounting: OANDA Canada's 1% CAD conversion is ON (Sam's account is CAD; the spec makes it optional); the
spec's 0.15 × spread stop slippage and exact long-and-short coin-flip control are the author's own.

Rules (theirs): opening range = 09:30–09:45 NY; its width must be 0.6–2.4 × ATR15 and ATR15 ≥ 12 bps of price. A 3m
candle closing 09:48–11:15 beyond the range (by 0.05–0.6 ATR15, body ≥ 50%, close in its top 30%, range ≤ 1.2 ATR15)
and beyond the 09:30-anchored cash VWAP, in the direction of the 1H trend (1H close vs 1H EMA50) with the opening range
closing in the trade's half or beyond the 15m EMA50 → market fill the next minute on the real bid/ask. Stop =
min(range midpoint, candle low − 0.15 ATR15) − 0.10 ATR15, risk 0.6–1.8 ATR15. Target +3R; after a 15m close ≥ +1.5R
the stop locks +0.25R and trails 15m swing lows; out 15:55 NY. One trade a day; none within 15 min of FOMC/CPI/NFP/PPI.
Controls: exact coin flip (average of a long and a short at the same minute) and no 1H/15m bias.

Protocol (theirs): Step 1 — 2021 → Sep 2026 (holdout_m1 + dev_m1 NAS100): every gate combined (≥ 100 trades, avg R > 0,
95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than both controls) and positive in
each set. Step 2 — only then is untouched 2016–2020 NAS100 opened, once, and judged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN
from .simple_rules import NY, ema, load, pip_stats, stats, wilder

PIP = {"NAS100": 1.0}
SYM = "NDQ"
CAD = True
# ── Frozen constants for ndq_orb_vwap_v1 (100% ATR / relative scaled, zero point constants) ──
OR_START, OR_END = 570, 585           # 09:30–09:45 NY Cash Opening Range
WIN = (588, 675)                      # 3m bar closes from 09:48 to 11:15 NY
FLAT = 955                            # 15:55 NY cash session exit (no overnight holds)
MAX_DAY = 1                           # max 1 trade per day
ATR15_BPS = 0.0012                    # min 15m ATR = 12 bps of NDQ index price
OR_MIN_ATR, OR_MAX_ATR = 0.60, 2.40   # Opening Range width bounds in ATR15 units
BRK_BUF_ATR, BRK_MAX_EXT = 0.05, 0.60 # close >= or_hi + 0.05*ATR15 and <= or_hi + 0.60*ATR15
BAR3_MAX_ATR = 1.20                   # max 3m breakout bar range = 1.20 * ATR15
BODY3, TOP_CLOSE3 = 0.50, 0.30        # 3m body >= 50% range, close in top 30%
RISK_MIN_ATR, RISK_MAX_ATR = 0.60, 1.80
TRAIL_ACT_R, TRAIL_LOCK_R = 1.50, 0.25 # only activate trail after a 15m close >= +1.50R
TP_R = 3.00                           # ceiling target at +3.00R
STOP_SLIP_FRAC = 0.15                 # realistic intrabar stop slippage = 15% of spread


def candles(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    return b


def atr(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n).to_numpy()


def cash_session_vwap(m1: pd.DataFrame, mod: np.ndarray, sess: np.ndarray) -> np.ndarray:
    """Cash VWAP anchored specifically at 09:30 NY (mod >= 570) so overnight pre-market chop is excluded."""
    tp = ((m1.m_h + m1.m_l + m1.m_c) / 3).to_numpy(float)
    v = (m1["volume"].to_numpy(float) if "volume" in m1 else np.ones(len(m1))).clip(min=1.0)
    in_cash = mod >= OR_START
    v_cash = np.where(in_cash, v, 0.0)
    tp_v = tp * v_cash
    df = pd.DataFrame({"s": sess, "tpv": tp_v, "v": v_cash})
    cs_tpv = df.groupby("s")["tpv"].cumsum().to_numpy()
    cs_v = df.groupby("s")["v"].cumsum().to_numpy()
    return np.where(cs_v > 0, cs_tpv / cs_v, tp)


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

    a["vwap"] = cash_session_vwap(m1, a["mod"], a["sess"])
    h1 = m1["m_c"].resample("1h", label="right", closed="left").last().dropna()
    a["h1_end"], a["ema1h"] = h1.index.as_unit("ns").asi8, ema(h1, 50).to_numpy()
    a["h1c"] = h1.to_numpy()                                  # [spec 1.3] the last closed 1H CLOSE

    b15, b3 = candles(m1, 15), candles(m1, 3)
    b15["ema50"], b15["atr"] = ema(b15.c, 50).to_numpy(), atr(b15, 14)
    a["b15"], a["b3"] = b15, b3
    # [spec 1.2] the 09:30–09:45 NY 15m bar of each session day (i15_or)
    s15 = b15.index.tz_convert(NY)
    st15 = s15.hour * 60 + s15.minute
    a["i15_or"] = {int(d.toordinal()): int(i) for i, (d, m_) in enumerate(zip(s15.date, st15)) if m_ == OR_START}

    # 09:30–09:45 NY Opening Range per calendar session day
    df = pd.DataFrame({"s": a["sess"], "mod": a["mod"], "o": a["m_o"], "h": a["m_h"], "l": a["m_l"], "c": a["m_c"]})
    orb = df[(df["mod"] >= OR_START) & (df["mod"] < OR_END)].groupby("s").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("h", "count")
    )
    or_map = {}
    for s, r_ in orb.iterrows():
        if r_["n"] >= 10 and np.isfinite(r_["h"]) and np.isfinite(r_["l"]) and r_["h"] > r_["l"]:
            or_map[int(s)] = (float(r_["o"]), float(r_["h"]), float(r_["l"]), float(r_["c"]))
    a["or_map"] = or_map

    # 15m confirmed swing lows/highs (2 bars each side) for trailing after +1.5R
    L, H = b15.l.to_numpy(), b15.h.to_numpy()
    sl, sh = np.full(len(b15), np.nan), np.full(len(b15), np.nan)
    for i in range(2, len(b15) - 2):
        if L[i] < min(L[i - 2], L[i - 1], L[i + 1], L[i + 2]):
            sl[i + 2] = L[i]
        if H[i] > max(H[i - 2], H[i - 1], H[i + 1], H[i + 2]):
            sh[i + 2] = H[i]
    a["swing_lo"], a["swing_hi"] = pd.Series(sl).ffill().to_numpy(), pd.Series(sh).ffill().to_numpy()
    return a


def mirror(a: dict, side: int) -> dict:
    b15, b3 = a["b15"], a["b3"]
    if side > 0:
        return {"o3": b3.o.to_numpy(), "h3": b3.h.to_numpy(), "l3": b3.l.to_numpy(), "c3": b3.c.to_numpy(),
                "vwap": a["vwap"], "c15": b15.c.to_numpy(), "e50": b15.ema50.to_numpy(),
                "ema1h": a["ema1h"], "h1c": a["h1c"], "swing": a["swing_lo"],
                "in_o": a["ask_o"], "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"], "ex_c": a["bid_c"]}
    return {"o3": -b3.o.to_numpy(), "h3": -b3.l.to_numpy(), "l3": -b3.h.to_numpy(), "c3": -b3.c.to_numpy(),
            "vwap": -a["vwap"], "c15": -b15.c.to_numpy(), "e50": -b15.ema50.to_numpy(),
            "ema1h": -a["ema1h"], "h1c": -a["h1c"], "swing": -a["swing_hi"],
            "in_o": -a["bid_o"], "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"], "ex_c": -a["ask_c"]}


def find_trades(a: dict, use_bias: bool = True) -> list[dict]:
    b15, b3 = a["b15"], a["b3"]
    E15, E3, H1_END = b15.end.to_numpy(), b3.end.to_numpy(), a["h1_end"]
    atr15, raw_c15 = b15.atr.to_numpy(), b15.c.to_numpy()
    ns, mod, sess = a["ns"], a["mod"], a["sess"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    out = []
    for m in range(50, len(b3)):
        j_end = int(np.searchsorted(ns, E3[m])) - 1
        if j_end < 0:
            continue
        close_mod = mod[j_end] + 1
        if not (WIN[0] <= close_mod <= WIN[1]):
            continue
        sd_ = int(sess[j_end])
        if sd_ not in a["or_map"]:
            continue
        or_o, or_h, or_l, or_c = a["or_map"][sd_]
        or_w = or_h - or_l
        or_mid = 0.5 * (or_h + or_l)

        i15 = a["i15_or"].get(sd_)                             # [spec 1.2] read at 09:45 (close of the OR bar)
        i1h = int(np.searchsorted(H1_END, E3[m], side="right")) - 1
        if i15 is None or i15 < 60 or i1h < 50 or not np.isfinite(atr15[i15]):
            continue
        a15 = float(atr15[i15])
        if a15 < ATR15_BPS * raw_c15[i15]:
            continue
        if not (OR_MIN_ATR * a15 <= or_w <= OR_MAX_ATR * a15):
            continue

        for side in (1, -1):
            M = MM[side]
            or_hi_m = or_h if side > 0 else -or_l
            or_mid_m = or_mid if side > 0 else -or_mid
            or_c_m = or_c if side > 0 else -or_c

            if use_bias:
                if not (M["h1c"][i1h] > M["ema1h"][i1h] and (or_c_m >= or_mid_m or M["c15"][i15] > M["e50"][i15])):
                    continue
                mode = "orb_trend"
            else:
                mode = "no_bias"

            o, h, l, c = M["o3"][m], M["h3"][m], M["l3"][m], M["c3"][m]
            rng = h - l
            if rng <= 0 or rng > BAR3_MAX_ATR * a15:
                continue
            if (c - o) < BODY3 * rng or c < h - TOP_CLOSE3 * rng:
                continue
            if not (or_hi_m + BRK_BUF_ATR * a15 <= c <= or_hi_m + BRK_MAX_EXT * a15):
                continue
            if c <= M["vwap"][j_end]:
                continue

            j = int(np.searchsorted(ns, E3[m]))
            if j >= len(ns) or ns[j] - E3[m] > 5 * MIN or mod[j] > WIN[1]:
                continue

            stop_m = min(or_mid_m, l - 0.15 * a15) - 0.10 * a15
            out.append({"j": j, "side": side, "stop_m": float(stop_m), "a15": a15, "mode": mode, "sess": sd_})
    out.sort(key=lambda x: x["j"])
    return out


def manage(a: dict, M: dict, j: int, entry_m: float, stop_m: float, spread: float):
    """Strict stop-first 1m management with intrabar stop slippage, 15m close trail activation, and 15:55 flat."""
    ns, mod = a["ns"], a["mod"]
    E15 = a["b15"].end.to_numpy()
    risk = entry_m - stop_m
    tp = entry_m + TP_R * risk
    act_lvl = entry_m + TRAIL_ACT_R * risk
    lock_stop = entry_m + TRAIL_LOCK_R * risk
    slip = STOP_SLIP_FRAC * spread
    stop = stop_m
    trail_on = False
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:
            return k - 1, M["ex_c"][k - 1] - entry_m, "closure"
        if mod[k] >= FLAT and k > j:
            return k, M["ex_o"][k] - entry_m, "flat_1555"
        # Strict stop-first check on every minute (with intrabar stop slippage unless gap-open beyond stop)
        if M["ex_l"][k] <= stop:
            if k == j:
                px = stop - slip
            else:
                px = M["ex_o"][k] if M["ex_o"][k] <= stop else (stop - slip)
            return k, px - entry_m, "stop" if stop == stop_m else "trail_stop"
        # Target check
        if M["ex_h"][k] >= tp:
            px = tp if k == j else max(tp, M["ex_o"][k])
            return k, px - entry_m, "target"
        # Check 15m bar close for trail activation and swing trailing (only at 15m boundaries)
        if k > j and (mod[k] + 1) % 15 == 0:
            i15 = int(np.searchsorted(E15, ns[k] + MIN, side="right")) - 1
            if i15 >= 0:
                if not trail_on and M["c15"][i15] >= act_lvl:
                    trail_on = True
                    stop = max(stop, lock_stop)
                if trail_on:
                    sw = M["swing"][i15]
                    if np.isfinite(sw) and sw < M["ex_c"][k]:
                        stop = max(stop, sw)
        k += 1
    k = len(ns) - 1
    return k, M["ex_c"][k] - entry_m, "end"


def row(a, j, jx, side, entry_m, pts, risk, spread, why, cad_fx: bool = False, **extra) -> dict:
    if cad_fx:
        pts_adj = pts * 0.99 if pts >= 0 else pts * 1.01
        pts_2x = (pts - spread) * 0.99 if (pts - spread) >= 0 else (pts - spread) * 1.01
        risk_adj = risk * 1.01
    else:
        pts_adj, pts_2x, risk_adj = pts, pts - spread, risk
    return {"entry_time": a["idx"][j], "exit_time": a["idx"][jx], "side": side, "entry": side * entry_m,
            "atr": risk_adj, "points": pts_adj, "R": pts_adj / risk_adj, "R_2x": pts_2x / risk_adj,
            "cost_R": spread / risk_adj, "exit_reason": why,
            "hold_min": (a["ns"][jx] - a["ns"][j]) / 60e9, "overnight": False, **extra}


def execute(a: dict, ents: list[dict], blocked: np.ndarray, cad_fx: bool = False):
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    trades, ctl = [], []
    busy, per_day = -1, {}
    for e in ents:
        j, side = e["j"], e["side"]
        if j <= busy or blocked[j] or per_day.get(e["sess"], 0) >= MAX_DAY:
            continue
        M = MM[side]
        entry_m = float(M["in_o"][j])
        risk = entry_m - e["stop_m"]
        a15 = e.get("a15", risk)
        if not (RISK_MIN_ATR * a15 <= risk <= RISK_MAX_ATR * a15):
            continue
        spread = float(a["ask_o"][j] - a["bid_o"][j])
        jx, pts, why = manage(a, M, j, entry_m, e["stop_m"], spread)
        trades.append(row(a, j, jx, side, entry_m, pts, risk, spread, why, cad_fx=cad_fx, mode=e["mode"]))
        busy = jx
        per_day[e["sess"]] = per_day.get(e["sess"], 0) + 1

        # Deterministic Exact Coin-Flip Control: average of +1 and -1 at the exact same moment j
        if j < len(a["ns"]):
            _, pts_l, _ = manage(a, MM[1], j, float(MM[1]["in_o"][j]), float(MM[1]["in_o"][j]) - risk, spread)
            _, pts_s, _ = manage(a, MM[-1], j, float(MM[-1]["in_o"][j]), float(MM[-1]["in_o"][j]) - risk, spread)
            avg_pts = 0.5 * (pts_l + pts_s)
            ctl.append(row(a, j, jx, side, entry_m, avg_pts, risk, spread, "exact_coin", cad_fx=cad_fx, mode="coin"))
    return trades, ctl


def judge(X, days, mid):
    st = stats(X, days) if len(X) else {"trades": 0}
    if len(X):
        et = pd.to_datetime(X.entry_time)
        a, b = X[et < mid], X[et >= mid]
        st |= {"h1": float(a.R.mean()) if len(a) else float("nan"), "h2": float(b.R.mean()) if len(b) else float("nan")}
        st |= pip_stats(X, PIP["NAS100"])
    return st


def run_set(ds: str, seed: int):
    a = prepare(load(Path("data/export") / ds / f"{SYM}_M1.csv.gz"))
    blk = block_mask(a, 15, 15)
    tr, ctl = execute(a, find_trades(a, True), blk, cad_fx=CAD)
    nb, _ = execute(a, find_trades(a, False), blk, cad_fx=CAD)
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    return (pd.DataFrame(tr), pd.DataFrame(ctl), pd.DataFrame(nb)), days[days.dayofweek < 5].tz_localize(NY)


def gates(T, C, N, days) -> tuple[dict, bool]:
    if not len(T):
        return {"rule": {"trades": 0}}, False
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    res = {"rule": judge(T, days, mid), "exact coin-flip control": judge(C, days, mid), "no 1H/15m bias": judge(N, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("exact coin-flip control", "no 1H/15m bias")))
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
    return [f"Exits: {why}. Long {T[T.side > 0].R.mean():+.3f} ({(T.side > 0).sum()}), short "
            f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}). Typical stop {T.atr.median():.1f} pts (middle half "
            f"{T.atr.quantile(.25):.1f}–{T.atr.quantile(.75):.1f} pts); typical spread {T.cost_R.median():.0%} of it.", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="dev_m1,holdout_m1")
    ap.add_argument("--judge", default="old_m1_idx_NDQ")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=37)  # unused: the coin-flip control is exact
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    md = ["# ndq_orb_vwap_v1 — NAS100 09:30–09:45 opening-range breakout + cash VWAP (author's pre-registered spec)", "",
          "Author's constants and strategy functions used verbatim (fxagents/ndq_orb.py) with four recorded fixes that "
          "bring the code in line with the written spec, frozen 2026-10-20 before any run. Real OANDA bid/ask fills, "
          "0.15 × spread stop slippage, OANDA Canada 1% CAD conversion; R after costs; 2× costs pays one more spread; "
          "exact coin-flip control (long and short averaged at the same minute). **Step 1:** seen data "
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
    elif not (Path("data/export") / a_.judge / f"{SYM}_M1.csv.gz").exists():
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
