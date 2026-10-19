"""Gold scalp #2: liquidity sweep + VWAP alignment (15m bias → 5m displacement → 3m pullback), an outside suggestion
(Sam 2026-10-19), coded as specified and frozen before any result.

    python -m fxagents.sweep_vwap --data dev_m1 --out data/year_test/sweep_vwap_dev_m1         (./fx.sh sweepvwap)

Times are New York. Mid candles ((bid+ask)/2) for every signal; fills on the real bid/ask (buy at the ask, sell at
the bid, exits on the other side, stops at the minute's open if price gaps through). Open points fixed here:

  Window        entries 08:00–11:30 only; everything flat by 16:30. At most 3 trades a day, one at a time.
  15m bias      a SWEEP takes precedence: since 08:00, a closed 15m candle traded below a liquidity level (Asian low
                18:00–02:00, London low 02:00–08:00, previous day's low; day = 18:00→17:00) and closed back above it
                with a lower wick ≥ 50% of its range → long bias for the rest of the window (mirror for highs → short;
                sweeps both ways → no trade). Without a sweep: long while the last closed 15m close > EMA50, short
                while below. 15m ATR(14) ≥ $2.50 required.
  5m            displacement = a candle in the bias direction with body ≥ 60% of its range and range ≥ 1 × ATR(14,5m),
                closing beyond the session VWAP (anchored 18:00, tick volume) — or, under a sweep bias, beyond the
                swept level.
  3m            within 30 min after the displacement close: price pulls back into the EMA9/EMA21 zone or to VWAP
                (low ≤ the higher of EMA9/EMA21, or ≤ VWAP), then the first 3m bullish engulfing or pin bar (lower wick
                ≥ 60% of range, close in the top third) at/after that touch that closes above EMA21 → enter at the
                next minute. A 3m close beyond the displacement candle's far end cancels.
  Room          skip if an opposing level (previous day's high, Asian high, London high) lies less than $3.50 beyond
                the entry (the "minimum $3.50 target" rule).
  Stop          $0.50 beyond the lowest low of the last five 3m candles (incl. the trigger). Fixed until TP1.
  Exits         TP1: 70% at +1.5R, then the stop goes to entry + $0.40. Runner (30%): trails behind confirmed 15m
                swing lows (2 candles each side), target 3R, out at 16:30 at the latest. No conversion to swing holds.
  Excluded      fills within 15 min of a scheduled USD release (FOMC/CPI/NFP/PPI); data gaps.
  Controls      coin flip (same minute, random side, same stop distance and management) and the same 5m/3m trigger
                WITHOUT the 15m bias (both directions).

Gold only. Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves,
better than both controls. Holdout only if it passes, unchanged. R is per whole position (70% + 30%), after spread.
OANDA Canada's 1% conversion fee on P&L in a CAD account is NOT included (≈ −0.01R per trade; a USD sub-account
avoids it).
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

PASSED_DEV = False
# Pre-registered follow-up, frozen Oct 19 2026 after the dev report and BEFORE any holdout data was read (Sam's call):
# "sweep-only" = exactly the rule above, minus the 50-EMA fallback — only days with a 15m sweep trade. Dev showed
# +0.09R on ~100 sweep trades (found by slicing), so the untouched holdout (2021 → Sep 2024) alone judges it.
WIN = (480, 690)                  # 08:00–11:30 entries
FLAT = 990                        # 16:30
MAX_DAY = 3
ATR15_MIN, BODY, DISP_ATR, WICK15 = 2.50, 0.60, 1.0, 0.50
PULL_MIN, PIN_WICK = 30, 0.60
STOP_BUF, ROOM, TP1_R, TP1_FRAC, BE_PLUS, RUN_R = 0.50, 3.50, 1.5, 0.70, 0.40, 3.0


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
    """VWAP anchored at 18:00 NY, as of each minute's close (typical price × tick volume)."""
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
    b15, b5, b3 = candles(m1, 15), candles(m1, 5), candles(m1, 3)
    b15["ema50"], b15["atr"] = ema(b15.c, 50).to_numpy(), atr(b15)
    b5["atr"] = atr(b5)
    b3["e9"], b3["e21"] = ema(b3.c, 9).to_numpy(), ema(b3.c, 21).to_numpy()
    a["b15"], a["b5"], a["b3"] = b15, b5, b3
    # liquidity levels per session day: Asia 18:00–02:00, London 02:00–08:00, previous day high/low
    mod = a["mod"]
    lv = {}
    df = pd.DataFrame({"s": a["sess"], "mod": mod, "h": a["m_h"], "l": a["m_l"]})
    asia = df[(df["mod"] >= 1080) | (df["mod"] < 120)].groupby("s").agg(h=("h", "max"), l=("l", "min"))
    lon = df[(df["mod"] >= 120) & (df["mod"] < 480)].groupby("s").agg(h=("h", "max"), l=("l", "min"))
    day = df.groupby("s").agg(h=("h", "max"), l=("l", "min"))
    prev = day.shift(1)
    for s in day.index:
        lv[s] = {"asia": tuple(asia.loc[s]) if s in asia.index else (np.nan, np.nan),
                 "london": tuple(lon.loc[s]) if s in lon.index else (np.nan, np.nan),
                 "prev": tuple(prev.loc[s]) if s in prev.index else (np.nan, np.nan)}
    a["levels"] = lv
    # 15m swing lows / highs confirmed two candles later (for the runner's trail)
    L, H = b15.l.to_numpy(), b15.h.to_numpy()
    sl = np.full(len(b15), np.nan)
    sh = np.full(len(b15), np.nan)
    for i in range(2, len(b15) - 2):
        if L[i] < min(L[i - 2], L[i - 1], L[i + 1], L[i + 2]):
            sl[i + 2] = L[i]                                       # known at the close of candle i+2
        if H[i] > max(H[i - 2], H[i - 1], H[i + 1], H[i + 2]):
            sh[i + 2] = H[i]
    a["swing_lo"], a["swing_hi"] = pd.Series(sl).ffill().to_numpy(), pd.Series(sh).ffill().to_numpy()
    return a


def mirror(a: dict, side: int) -> dict:
    """Arrays in the trade's own direction: for shorts every price is negated, so the long logic serves both."""
    s = side
    b15, b5, b3 = a["b15"], a["b5"], a["b3"]
    if s > 0:
        return {"o5": b5.o.to_numpy(), "h5": b5.h.to_numpy(), "l5": b5.l.to_numpy(), "c5": b5.c.to_numpy(),
                "o3": b3.o.to_numpy(), "h3": b3.h.to_numpy(), "l3": b3.l.to_numpy(), "c3": b3.c.to_numpy(),
                "e9": b3.e9.to_numpy(), "e21": b3.e21.to_numpy(), "vwap": a["vwap"],
                "c15": b15.c.to_numpy(), "e50": b15.ema50.to_numpy(), "h15": b15.h.to_numpy(), "l15": b15.l.to_numpy(),
                "o15": b15.o.to_numpy(), "swing": a["swing_lo"],
                "in_o": a["ask_o"], "ex_o": a["bid_o"], "ex_h": a["bid_h"], "ex_l": a["bid_l"], "ex_c": a["bid_c"]}
    return {"o5": -b5.o.to_numpy(), "h5": -b5.l.to_numpy(), "l5": -b5.h.to_numpy(), "c5": -b5.c.to_numpy(),
            "o3": -b3.o.to_numpy(), "h3": -b3.l.to_numpy(), "l3": -b3.h.to_numpy(), "c3": -b3.c.to_numpy(),
            "e9": -b3.e9.to_numpy(), "e21": -b3.e21.to_numpy(), "vwap": -a["vwap"],
            "c15": -b15.c.to_numpy(), "e50": -b15.ema50.to_numpy(), "h15": -b15.l.to_numpy(), "l15": -b15.h.to_numpy(),
            "o15": -b15.o.to_numpy(), "swing": -a["swing_hi"],
            "in_o": -a["bid_o"], "ex_o": -a["ask_o"], "ex_h": -a["ask_l"], "ex_l": -a["ask_h"], "ex_c": -a["ask_c"]}


def lows_of(a: dict, sess: int, side: int) -> tuple[list[float], list[float]]:
    """(levels a sweep can take for this side, opposing levels that cap the room), in mirrored prices."""
    lv = a["levels"].get(sess)
    if not lv:
        return [], []
    hi = [lv[k][0] for k in ("asia", "london", "prev")]
    lo = [lv[k][1] for k in ("asia", "london", "prev")]
    sweep, opp = (lo, hi) if side > 0 else ([-x for x in hi], [-x for x in lo])
    return [x for x in sweep if np.isfinite(x)], [x for x in opp if np.isfinite(x)]


def bias(a: dict, M: dict, other: dict, sess: int, side: int, i15_last: int, i15_from: int,
         sweep_only: bool = False) -> tuple[str | None, float | None]:
    """→ ('sweep', level) | ('ema', None) | (None, None) for `side` at the close of 15m candle i15_last."""
    def swept(MM, sd):
        lv, _ = lows_of(a, sess, sd)
        for i in range(i15_from, i15_last + 1):
            rng = MM["h15"][i] - MM["l15"][i]
            if rng <= 0:
                continue
            wick = min(MM["o15"][i], MM["c15"][i]) - MM["l15"][i]
            for L in lv:
                if MM["l15"][i] < L < MM["c15"][i] and wick >= WICK15 * rng:
                    return L
        return None
    mine, theirs = swept(M, side), swept(other, -side)
    if mine is not None and theirs is not None:
        return None, None
    if theirs is not None:
        return None, None
    if mine is not None:
        return "sweep", mine
    if sweep_only:
        return None, None
    return ("ema", None) if M["c15"][i15_last] > M["e50"][i15_last] else (None, None)


def find_trades(a: dict, use_bias: bool = True, sweep_only: bool = False) -> list[dict]:
    """Causal entries: {j (fill minute), side, stop (real price), mode}."""
    b15, b5, b3 = a["b15"], a["b5"], a["b3"]
    E15, E5, E3 = b15.end.to_numpy(), b5.end.to_numpy(), b3.end.to_numpy()
    S3 = b3.index.as_unit("ns").asi8
    atr5, atr15 = b5.atr.to_numpy(), b15.atr.to_numpy()
    ns, mod, sess = a["ns"], a["mod"], a["sess"]
    MM = {1: mirror(a, 1), -1: mirror(a, -1)}
    out = []
    for k in range(20, len(b5)):
        j_end = int(np.searchsorted(ns, E5[k])) - 1                    # last minute of candle k
        if j_end < 0 or not (WIN[0] <= mod[j_end] + 1 <= WIN[1]):
            continue
        sd_ = int(sess[j_end])
        i15 = int(np.searchsorted(E15, E5[k], side="right")) - 1
        if i15 < 60 or not np.isfinite(atr15[i15]) or atr15[i15] < ATR15_MIN:
            continue
        day0 = ns[j_end] - (mod[j_end] - WIN[0]) * MIN               # 08:00 today
        i15_from = int(np.searchsorted(E15, day0 + 15 * MIN))         # first 15m candle starting ≥ 08:00
        for side in (1, -1):
            M, O = MM[side], MM[-side]
            if use_bias:
                mode, lvl = bias(a, M, O, sd_, side, i15, i15_from, sweep_only)
                if mode is None:
                    continue
            else:
                mode, lvl = "none", None
            o, h, l, c = M["o5"][k], M["h5"][k], M["l5"][k], M["c5"][k]
            rng = h - l
            if rng <= 0 or c - o < BODY * rng or rng < DISP_ATR * atr5[k - 1]:
                continue
            vw = M["vwap"][j_end]
            if not (c > vw or (mode == "sweep" and c > lvl)):
                continue
            far = l                                                      # the displacement candle's far end
            m = int(np.searchsorted(S3, E5[k]))
            touched, trig = False, None
            while m < len(b3) and E3[m] <= E5[k] + PULL_MIN * MIN:
                jm = int(np.searchsorted(ns, E3[m])) - 1
                if M["c3"][m] < far:
                    break
                zone = max(M["e9"][m], M["e21"][m])
                if M["l3"][m] <= zone or M["l3"][m] <= M["vwap"][jm]:
                    touched = True
                if touched and m > 0 and M["c3"][m] > M["e21"][m]:
                    o3, h3, l3, c3 = M["o3"][m], M["h3"][m], M["l3"][m], M["c3"][m]
                    po, pc = M["o3"][m - 1], M["c3"][m - 1]
                    r3 = h3 - l3
                    engulf = c3 > o3 and pc < po and c3 >= po and o3 <= pc
                    pin = r3 > 0 and (min(o3, c3) - l3) >= PIN_WICK * r3 and c3 >= h3 - r3 / 3
                    if engulf or pin:
                        trig = m
                        break
                m += 1
            if trig is None:
                continue
            j = int(np.searchsorted(ns, E3[trig]))
            if j >= len(ns) or ns[j] - E3[trig] > 5 * MIN or mod[j] >= WIN[1]:
                continue
            stop_m = M["l3"][max(0, trig - 4):trig + 1].min() - STOP_BUF
            out.append({"j": j, "side": side, "stop_m": float(stop_m), "mode": mode, "sess": sd_})
    out.sort(key=lambda x: x["j"])
    return out


def manage(a: dict, M: dict, j: int, entry_m: float, stop_m: float):
    """Long-only management in mirrored prices from fill minute j. → (exit minute, points per unit, why)."""
    ns, mod = a["ns"], a["mod"]
    risk = entry_m - stop_m
    tp1, tp_run = entry_m + TP1_R * risk, entry_m + RUN_R * risk
    E15 = a["b15"].end.to_numpy()
    stop, done1, banked = stop_m, False, 0.0
    k = j
    while k < len(ns):
        if k > j and ns[k] - ns[k - 1] > 60 * MIN:                      # data gap: out at the last price before it
            px = M["ex_c"][k - 1]
            return k - 1, banked + (1 - TP1_FRAC * done1) * (px - entry_m), "closure"
        if mod[k] >= FLAT and k > j:
            px = M["ex_o"][k]
            return k, banked + (1 - TP1_FRAC * done1) * (px - entry_m), "flat_1630"
        if M["ex_l"][k] <= stop:
            px = stop if k == j else min(stop, M["ex_o"][k])
            return k, banked + (1 - TP1_FRAC * done1) * (px - entry_m), "stop" if not done1 else "runner_stop"
        if not done1 and k > j and M["ex_h"][k] >= tp1:
            banked += TP1_FRAC * (max(tp1, M["ex_o"][k]) - entry_m)
            done1 = True
            stop = max(stop, entry_m + BE_PLUS)
        if done1 and k > j and M["ex_h"][k] >= tp_run:
            return k, banked + (1 - TP1_FRAC) * (max(tp_run, M["ex_o"][k]) - entry_m), "runner_target"
        if done1 and (mod[k] + 1) % 15 == 0:                            # a 15m candle closed: trail the runner
            i15 = int(np.searchsorted(E15, ns[k] + MIN, side="right")) - 1
            sw = M["swing"][i15] if i15 >= 0 else np.nan
            if np.isfinite(sw) and sw < M["ex_c"][k]:
                stop = max(stop, sw)
        k += 1
    k = len(ns) - 1
    return k, banked + (1 - TP1_FRAC * done1) * (M["ex_c"][k] - entry_m), "end"


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
        if risk <= 0:
            continue
        _, opp = lows_of(a, e["sess"], side)
        if any(0 < x - entry_m < ROOM for x in opp):
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


def main_sweep_only(data: str, out: Path, seed: int):
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for ds in data.split(","):
        m1 = load(Path("data/export") / ds / "XAUUSD_M1.csv.gz")
        a = prepare(m1)
        del m1
        blk = block_mask(a, 15, 15)
        rng = np.random.default_rng(seed)
        tr, ctl = execute(a, find_trades(a, True, sweep_only=True), blk, rng)
        T, C = pd.DataFrame(tr), pd.DataFrame(ctl)
        T.to_csv(out / f"trades_{ds}.csv.gz", index=False)
        days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
        days = days[days.dayofweek < 5].tz_localize(NY)
        if len(T):
            et = pd.to_datetime(T.entry_time)
            mid = et.min() + (et.max() - et.min()) / 2
            st, cst = judge(T, days, mid), judge(C, days, mid)
            st["passed"] = bool(st.get("pass") and st["h1"] > 0 and st["h2"] > 0 and st["avg_R"] > cst.get("avg_R", -9))
        else:
            st, cst = {"trades": 0}, {"trades": 0}
        res[ds] = (T, st, cst)
        print(f"  {ds}: {len(T)} trades", flush=True)
    md = [f"# Pre-registered: gold sweep + VWAP, sweep-only ({data})", "",
          "Exactly the sweep + VWAP rule (fxagents/sweep_vwap.py) minus the 50-EMA fallback: only a 15m sweep of the "
          "Asian / London / previous-day high or low sets the direction. Frozen Oct 19 2026 after the dev report, before "
          "any holdout data was read. Dev = where the idea came from (shown only); **the holdout alone decides**. Pass = "
          "≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better "
          "than the coin flip. Real OANDA bid/ask fills; R for the whole position after spread.", "",
          "| Data | Role | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Coin flip | Total R |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ds, (T, st, cst) in res.items():
        hold = ds.startswith("holdout")
        if not st.get("trades"):
            md.append(f"| {ds} | {'judged' if hold else 'shown'} | — | 0 |" + " |" * 8)
            continue
        v = ("**PASS**" if st["passed"] else "**no pass**") if hold else "(in-sample)"
        md.append(f"| {ds} | {'judged' if hold else 'shown'} | {v} | {st['trades']} | {st['win']:.0%} | {st['avg_R']:+.3f} | "
                  f"{st['ci_lo']:+.2f} to {st['ci_hi']:+.2f} | {st['avg_R_2x']:+.3f} | {st['h1']:+.3f} | {st['h2']:+.3f} | "
                  f"{cst.get('avg_R', float('nan')):+.3f} | {st['total_R']:+.1f} |")
    md += ["", "| Data | Long avg R (n) | Short avg R (n) | Reached TP1 | Typical stop | Typical spread |", "|---|---|---|---|---|---|"]
    for ds, (T, st, _) in res.items():
        if not len(T):
            continue
        lo_, sh_ = T[T.side > 0], T[T.side < 0]
        reach = (T.exit_reason.isin(["runner_stop", "runner_target"]) | (T.R > 0.5)).mean()
        md.append(f"| {ds} | {lo_.R.mean():+.3f} ({len(lo_)}) | {sh_.R.mean():+.3f} ({len(sh_)}) | {reach:.0%} | "
                  f"${T.atr.median():.2f} | ${(T.cost_R * T.atr).median():.2f} |")
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "run.json").write_text(json.dumps({ds: st for ds, (_, st, _) in res.items()}, indent=2, default=str))
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dev_m1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--seed", type=int, default=37)
    ap.add_argument("--sweep-only", action="store_true", help="pre-registered sweep-only rule: dev shown, holdout judged")
    a_ = ap.parse_args()
    if a_.sweep_only:
        return main_sweep_only(a_.data, a_.out, a_.seed)
    if a_.frozen and not PASSED_DEV:
        raise SystemExit("did not pass on dev data — the holdout stays untouched")
    a_.out.mkdir(parents=True, exist_ok=True)
    m1 = load(Path("data/export") / a_.data / "XAUUSD_M1.csv.gz")
    a = prepare(m1)
    blk = block_mask(a, 15, 15)
    rng = np.random.default_rng(a_.seed)
    tr, ctl = execute(a, find_trades(a, True), blk, rng)
    nb, _ = execute(a, find_trades(a, False), blk, rng)
    T, C, N = pd.DataFrame(tr), pd.DataFrame(ctl), pd.DataFrame(nb)
    if not len(T):
        raise SystemExit("no trades")
    for nm, X in (("trades", T), ("control", C), ("no_bias", N)):
        X.to_csv(a_.out / f"{nm}.csv.gz", index=False)
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in a["date"].values()}))
    days = days[days.dayofweek < 5].tz_localize(NY)
    et = pd.to_datetime(T.entry_time)
    mid = et.min() + (et.max() - et.min()) / 2
    res = {"rule": judge(T, days, mid), "coin-flip control": judge(C, days, mid), "no 15m bias": judge(N, days, mid)}
    r = res["rule"]
    ok = bool(r.get("pass") and r["h1"] > 0 and r["h2"] > 0
              and all(r["avg_R"] > res[k].get("avg_R", -9) for k in ("coin-flip control", "no 15m bias")))
    md = [f"# Gold scalp #2: liquidity sweep + VWAP (15m → 5m → 3m) ({a_.data}) — **{'PASS' if ok else 'no pass'}**", "",
          f"{et.min():%Y-%m-%d} → {et.max():%Y-%m-%d}, XAUUSD, entries 08:00–11:30 NY. Rules as given (Oct 19 2026); open "
          "points fixed in fxagents/sweep_vwap.py before this run. Real OANDA bid/ask fills; R is for the whole position "
          "(70% at 1.5R, 30% runner to 3R), after spread; 2× costs pays one more spread. OANDA Canada's 1% conversion "
          "fee on CAD-account P&L is not included (≈ −0.01R/trade).", "",
          "Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, "
          "better than the coin flip and than the same trigger without the 15m bias.", "",
          "| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, s in res.items():
        if not s.get("trades"):
            md.append(f"| {nm} | 0 |" + " |" * 9)
            continue
        md.append(f"| {'**rule**' if nm == 'rule' else nm} | {s['trades']} | {s['win']:.0%} | {s['avg_R']:+.3f} | "
                  f"{s['ci_lo']:+.2f} to {s['ci_hi']:+.2f} | {s['avg_R_2x']:+.3f} | {s['h1']:+.3f} | {s['h2']:+.3f} | "
                  f"{s['total_R']:+.1f} | {s['pips_net']:+,.0f} | {s['hold_min_median']:.0f} min |")
    md += ["", "| Bias | Side | Trades | Win | Avg R |", "|---|---|---|---|---|"]
    for (mo, sd), x in T.groupby(["mode", "side"]):
        md.append(f"| {mo} | {'long' if sd > 0 else 'short'} | {len(x)} | {(x.R > 0).mean():.0%} | {x.R.mean():+.3f} |")
    why = ", ".join(f"{k} {v:.0%}" for k, v in T.exit_reason.value_counts(normalize=True).items())
    reach = (T.exit_reason.isin(["runner_stop", "runner_target"]) | (T.R > 0.5)).mean()
    md += ["", f"Exits: {why}. Reached TP1 (+1.5R): {reach:.0%}. Typical stop distance ${T.atr.median():.2f} "
           f"(middle half ${T.atr.quantile(.25):.2f}–${T.atr.quantile(.75):.2f}); typical spread "
           f"${(T.cost_R * T.atr).median():.2f} = {T.cost_R.median():.0%} of the stop.", ""]
    (a_.out / "report.md").write_text("\n".join(md) + "\n")
    (a_.out / "run.json").write_text(json.dumps({"data": a_.data, "pass": ok, "rows": res}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
