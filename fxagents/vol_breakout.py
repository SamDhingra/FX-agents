"""vol_breakout_v1 — gold 5m volatility-compression breakout with the 15m + 1H trend (momentum continuation).
Pre-registered by the outside strategy author (spec "vol_breakout_v1", frozen 2026-10-19). Their constants and strategy
functions are used VERBATIM (copied from their vol_breakout_standalone.py); shared helpers (data loader, minute
preparation, release calendar, statistics) are the project's identical versions.

    python -m fxagents.vol_breakout --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/vol_breakout_v1
                                                                                                (./fx.sh volbrk)

Rules (theirs): entries 08:00–11:30 NY on a 5m close that breaks a 60-minute box (12 × 5m, width 0.8–2.2 × ATR15) by
≥ 0.05 ATR15, with range 0.45–1.5 ATR15, body ≥ 60%, close in the top quarter, beyond the session VWAP, in the direction
of BOTH the 15m EMA50 and the 1H EMA50 (15m close vs each). 15m ATR ≥ 7 bps of price. Market fill the next minute on
the real bid/ask. Stop = min(breakout candle low, box midpoint) − 0.15 ATR15; risk must be 0.9–2.0 ATR15. Exit 100% at
+2.5R; at +1.2R the stop moves to +0.1R; flat 16:30 NY. One trade per session day; none within 15 min of FOMC/CPI/
NFP/PPI. Controls: coin flip (same minute, random side, same stop distance and exits) and the same trigger without the
trend filter.

Protocol (theirs): Step 1 — already-seen 2021 → Sep 2026 (holdout_m1 + dev_m1): every gate on the two combined
(≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than
both controls) and positive in each set. Step 2 — only then is the untouched old_m1 (2016–2020) opened, once, and
judged with the same gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .gemini_smc import block_mask
from .gemini_test import MIN, prep
from .simple_rules import NY, PIP, ema, load, pip_stats, stats, wilder

# ── Frozen constants for vol_breakout_v1 ──
WIN = (480, 690)                   # 08:00–11:30 NY entries
FLAT = 990                         # 16:30 NY flat
MAX_DAY = 1                        # at most 1 trade per session day
ATR15_BPS = 0.0007                 # min 15m ATR = 7 bps of spot price
BOX_BARS = 12                      # 12 x 5m bars = 60-minute compression lookback
BOX_MIN_ATR, BOX_MAX_ATR = 0.80, 2.20
BRK_BUF_ATR = 0.05                 # close must clear box high by >= 0.05 * ATR15
BAR_MIN_ATR, BAR_MAX_ATR = 0.45, 1.50
BODY5, TOP_CLOSE = 0.60, 0.25      # body >= 60% of 5m range; close in top 25% of range
STOP_BUF_ATR = 0.15                # stop buffer below min(l5[k], box_mid)
RISK_MIN_ATR, RISK_MAX_ATR = 0.90, 2.00
BE_TRIG_R, BE_LOCK_R = 1.20, 0.10  # at +1.2R move stop to +0.10R
TP_R = 2.50                        # full target at +2.5R


def candles(m1: pd.DataFrame, tf: int) -> pd.DataFrame:
    r = m1.resample(f"{tf}min", label="left", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    b["end"] = (b.index + pd.Timedelta(minutes=tf)).as_unit("ns").asi8
    return b


def atr(b: pd.DataFrame, n: int = 14) -> np.ndarray:
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n).to_numpy()


def session_vwap(m1: pd.DataFrame) -> np.ndarray:
    loc = m1.index.tz_convert(NY)
    sess = (loc + pd.Timedelta(hours=6)).date
    tp = (m1.m_h + m1.m_l + m1.m_c) / 3
    v = (m1["volume"] if "volume" in m1 else pd.Series(1.0, index=m1.index)).clip(lower=1)
    g = pd.Series(sess, index=m1.index)
    return ((tp * v).groupby(g).cumsum() / v.groupby(g).cumsum()).to_numpy()


def prepare(m1: pd.DataFrame) -> dict:
    a = prep(m1)
    a["vwap"] = session_vwap(m1)
    loc = m1.index.tz_convert(NY)
    a["sess"] = np.array([d.toordinal() for d in (loc + pd.Timedelta(hours=6)).date])
    b15, b5 = candles(m1, 15), candles(m1, 5)
    b15["ema50"], b15["atr"] = ema(b15.c, 50).to_numpy(), atr(b15)
    a["b15"], a["b5"] = b15, b5
    return a


def mirror(a: dict, side: int) -> dict:
    b15, b5 = a["b15"], a["b5"]
    if side > 0:
        return {"o5": b5.o.to_numpy(), "h5": b5.h.to_numpy(), "l5": b5.l.to_numpy(), "c5": b5.c.to_numpy(),
                "vwap": a["vwap"], "c15": b15.c.to_numpy(), "e50": b15.ema50.to_numpy(),
                "ema1h": a["ema1h"], "in_o": a["ask_o"],
                "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"], "ex_c": a["bid_c"]}
    return {"o5": -b5.o.to_numpy(), "h5": -b5.l.to_numpy(), "l5": -b5.h.to_numpy(), "c5": -b5.c.to_numpy(),
            "vwap": -a["vwap"], "c15": -b15.c.to_numpy(), "e50": -b15.ema50.to_numpy(),
            "ema1h": -a["ema1h"], "in_o": -a["bid_o"],
            "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"], "ex_c": -a["ask_c"]}


def find_trades(a: dict, use_bias: bool = True) -> list[dict]:
    b15, b5 = a["b15"], a["b5"]
    E15, E5, H1_END = b15.end.to_numpy(), b5.end.to_numpy(), a["h1_end"]
    atr15 = b15.atr.to_numpy()
    raw_c15 = b15.c.to_numpy()
    ns, mod, sess = a["ns"], a["mod"], a["sess"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    out = []
    for k in range(max(20, BOX_BARS + 1), len(b5)):
        j_end = int(np.searchsorted(ns, E5[k])) - 1
        if j_end < 0 or not (WIN[0] <= mod[j_end] + 1 <= WIN[1]):
            continue
        sd_ = int(sess[j_end])
        i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
        i1h = int(np.searchsorted(H1_END, E5[k], side="right")) - 1
        if i15 < 60 or i1h < 50 or not np.isfinite(atr15[i15]) or atr15[i15] < ATR15_BPS * raw_c15[i15]:
            continue
        a15 = float(atr15[i15])
        for side in (1, -1):
            M = MM[side]
            if use_bias:
                if not (M["c15"][i15] > M["e50"][i15] and M["c15"][i15] > M["ema1h"][i1h]):
                    continue
                mode = "trend_brk"
            else:
                mode = "no_bias"
            box_hi = float(M["h5"][k - BOX_BARS:k].max())
            box_lo = float(M["l5"][k - BOX_BARS:k].min())
            box_w = box_hi - box_lo
            if not (BOX_MIN_ATR * a15 <= box_w <= BOX_MAX_ATR * a15):
                continue
            o, h, l, c = M["o5"][k], M["h5"][k], M["l5"][k], M["c5"][k]
            rng = h - l
            if not (BAR_MIN_ATR * a15 <= rng <= BAR_MAX_ATR * a15):
                continue
            if (c - o) < BODY5 * rng or c < h - TOP_CLOSE * rng:
                continue
            if c <= box_hi + BRK_BUF_ATR * a15 or c <= M["vwap"][j_end]:
                continue
            j = int(np.searchsorted(ns, E5[k]))
            if j >= len(ns) or ns[j] - E5[k] > 5 * MIN or mod[j] >= WIN[1]:
                continue
            box_mid = 0.5 * (box_hi + box_lo)
            stop_m = min(l, box_mid) - STOP_BUF_ATR * a15
            out.append({"j": j, "side": side, "stop_m": float(stop_m), "a15": a15, "mode": mode, "sess": sd_})
    out.sort(key=lambda x: x["j"])
    return out


def manage(a: dict, M: dict, j: int, entry_m: float, stop_m: float):
    ns, mod = a["ns"], a["mod"]
    risk = entry_m - stop_m
    tp = entry_m + TP_R * risk
    be_trig = entry_m + BE_TRIG_R * risk
    be_stop = entry_m + BE_LOCK_R * risk
    stop = stop_m
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:
            return k - 1, M["ex_c"][k - 1] - entry_m, "closure"
        if mod[k] >= FLAT and k > j:
            return k, M["ex_o"][k] - entry_m, "flat_1630"
        if M["ex_l"][k] <= stop:
            px = stop if k == j else min(stop, M["ex_o"][k])
            return k, px - entry_m, "stop" if stop == stop_m else "be_stop"
        if k > j and M["ex_h"][k] >= tp:
            return k, max(tp, M["ex_o"][k]) - entry_m, "target"
        if k > j and stop < be_stop and M["ex_h"][k] >= be_trig:
            stop = be_stop
        k += 1
    k = len(ns) - 1
    return k, M["ex_c"][k] - entry_m, "end"


def row(a, j, jx, side, entry_m, pts, risk, spread, why, **extra) -> dict:
    return {"entry_time": a["idx"][j], "exit_time": a["idx"][jx], "side": side, "entry": side * entry_m,
            "atr": risk, "points": pts, "R": pts / risk, "R_2x": (pts - spread) / risk, "cost_R": spread / risk,
            "exit_reason": why, "hold_min": (a["ns"][jx] - a["ns"][j]) / 60e9, "overnight": False, **extra}


def execute(a: dict, ents: list[dict], blocked: np.ndarray, rng):
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
    res = {"rule": judge(T, days, mid), "coin-flip control": judge(C, days, mid), "no HTF bias": judge(N, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("coin-flip control", "no HTF bias")))
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
            f"{T[T.side < 0].R.mean():+.3f} ({(T.side < 0).sum()}). Typical stop ${T.atr.median():.2f} (middle half "
            f"${T.atr.quantile(.25):.2f}–${T.atr.quantile(.75):.2f}); typical spread {T.cost_R.median():.0%} of it.", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", default="dev_m1,holdout_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=37)
    a_ = ap.parse_args()
    a_.out.mkdir(parents=True, exist_ok=True)
    md = ["# vol_breakout_v1 — gold 5m compression breakout with the 15m + 1H trend (author's pre-registered spec)", "",
          "Author's constants and strategy functions used verbatim (fxagents/vol_breakout.py), frozen 2026-10-19 before "
          "any run. Real OANDA bid/ask fills; R after spread; 2× costs pays one more spread. **Step 1:** seen data "
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
