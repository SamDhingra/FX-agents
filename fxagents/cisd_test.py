"""CISD (change in state of delivery) on OANDA bid/ask exports, rules fixed before testing (Oct 2026 research).

    python -m fxagents.cisd_test --data dev_m1 --out data/year_test/cisd_dev_m1

Times: America/New_York (DST-aware). Signals on mid = (bid+ask)/2 candles built from M1; longs fill at the ask,
shorts at the bid; stops/targets trigger on the side that would fill (bid for long exits, ask for short exits).

Set A — sweep → CISD → market entry (5m primary; 1m and 15m as robustness checks with identical parameters)
  levels:   previous trading day high/low (trading day 18:00→17:00), Asian range 20:00–00:00, and for the NY window
            also the London range 02:00–05:00. A level counts only if price has not traded through it since it formed
            ("first touch").
  windows:  London 02:00–05:00, NY AM 08:30–11:00 (signal candle close inside the window), reported separately.
  sweep:    a candle low < level − 1 tick (bullish; mirror for bearish). Sweep extreme = lowest low since, updated
            every candle until a CISD fires; X = the candle holding it.
  series:   from X backwards, the most recent down-close candle, extended back while candles are down-close; doji
            (close = open) are skipped (neither break nor join); the first up-close candle ends it.
            CISD level = open of the earliest candle of that series.
  trigger:  first candle after X (within 12 candles of X, inside the window) whose close > CISD level. A new lower low
            re-anchors X, the series and the level.
  entry:    market at the next candle's open (ask for longs). Stop = sweep extreme − 0.1 × ATR(14) of the signal
            timeframe (on the bid). Skip if stop distance < 4 × the entry spread. Target 2.0R. Time exit: 11:00 for
            London trades, 15:55 for NY trades. One trade per window per instrument. No bias filter, no news filter.
Set B — the same, plus bias = direction of the most recent 1h CISD (series rule, no sweep, completed 1h candles only),
  and entry by limit at the midpoint of the first FVG (≥ 0.1 ATR) whose middle candle lies between X and trigger+2;
  cancelled if unfilled after 12 candles, if price reaches 2R first, on a close beyond the sweep extreme, or at the
  window end. 5m only.
Control: for every Set A trade, the same entry time, stop distance and 2R target with the side chosen by a coin flip.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .simple_rules import NY, PIP, load, pip_stats, stats, wilder

SYMS = ["XAUUSD", "NDQ", "US30"]
TICK = {"XAUUSD": 0.01, "NDQ": 0.1, "US30": 0.1}
WINDOWS = {"London": (120, 300, 11 * 60), "NY": (510, 660, 15 * 60 + 55)}    # start, end (minutes NY), flat time
EXPIRY, BUF_ATR, FLOOR_SPREADS, TARGET_R, FVG_MIN_ATR = 12, 0.1, 4.0, 2.0, 0.1


def candles(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    r = m1.resample(tf, label="left", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = wilder(tr, 14)
    b["end"] = b.index + pd.Timedelta(tf)                         # the moment the candle is complete
    loc = b["end"].dt.tz_convert(NY)
    b["mins"] = loc.dt.hour * 60 + loc.dt.minute
    b["day"] = loc.dt.normalize()
    return b


def cisd_level(o, c, x: int, side: int):
    """Open of the earliest candle of the last unbroken delivery series ending at or before x.
    side +1 (bullish CISD): series of down-close candles; -1: up-close candles. Doji are skipped."""
    want = -side
    j = x
    while j >= 0 and np.sign(c[j] - o[j]) != want:              # most recent candle of the delivering colour
        j -= 1
    if j < 0:
        return None
    first = j
    k = j - 1
    while k >= 0:
        s = np.sign(c[k] - o[k])
        if s == want:
            first = k
        elif s == side:
            break
        k -= 1
    return o[first]


def htf_bias(m1: pd.DataFrame) -> pd.Series:
    """Direction (+1/−1) of the most recent 1h CISD (series rule, no sweep), indexed by the 1h candle's END time."""
    h = candles(m1, "1h")
    o, c = h.o.to_numpy(), h.c.to_numpy()
    out = np.zeros(len(h))
    cur = 0
    for k in range(1, len(h)):
        for side in (1, -1):
            lvl = cisd_level(o, c, k - 1, side)
            if lvl is not None and side * (c[k] - lvl) > 0:
                cur = side
        out[k] = cur
    return pd.Series(out, index=h["end"])


def levels_for_day(m1loc: pd.DataFrame, day: pd.Timestamp, window: str) -> list[tuple[str, float, int, pd.Timestamp]]:
    """(name, price, side it can be swept from (+1 = a low swept for a bullish setup), time it starts counting)."""
    out = []
    pd_start, pd_end = day - pd.Timedelta(days=2) + pd.Timedelta(hours=18), day - pd.Timedelta(days=1) + pd.Timedelta(hours=17)
    if day.dayofweek == 0:                                     # Monday: previous trading day is Friday
        pd_start, pd_end = day - pd.Timedelta(days=4) + pd.Timedelta(hours=18), day - pd.Timedelta(days=3) + pd.Timedelta(hours=17)
    seg = m1loc[(m1loc.index >= pd_start) & (m1loc.index < pd_end)]
    if len(seg):
        out += [("PDL", seg.m_l.min(), 1, pd_end), ("PDH", seg.m_h.max(), -1, pd_end)]
    a0 = day - pd.Timedelta(hours=4)
    seg = m1loc[(m1loc.index >= a0) & (m1loc.index < day)]
    if len(seg):
        out += [("Asia low", seg.m_l.min(), 1, day), ("Asia high", seg.m_h.max(), -1, day)]
    if window == "NY":
        seg = m1loc[(m1loc.index >= day + pd.Timedelta(hours=2)) & (m1loc.index < day + pd.Timedelta(hours=5))]
        if len(seg):
            t = day + pd.Timedelta(hours=5)
            out += [("London low", seg.m_l.min(), 1, t), ("London high", seg.m_h.max(), -1, t)]
    return out


def simulate(m1, j0: int, side: int, entry: float, stop: float, target: float, flat: pd.Timestamp):
    """Walk M1 from minute j0 (entry minute) to the first stop / target / flat. Stop wins inside one minute."""
    t = m1.index
    bl, bh, al, ah = (m1[x].to_numpy() for x in ("bid_l", "bid_h", "ask_l", "ask_h"))
    bo, ao, bc, ac = (m1[x].to_numpy() for x in ("bid_o", "ask_o", "bid_c", "ask_c"))
    n = len(t)
    for j in range(j0, n):
        if j > j0 and (t[j] - t[j - 1]) > pd.Timedelta("60min"):  # closure: out at the last price before it
            return j - 1, (bc[j - 1] if side > 0 else ac[j - 1]), "closure"
        if t[j] >= flat:
            return j, (bo[j] if side > 0 else ao[j]), "time"
        lo, hi, op = (bl[j], bh[j], bo[j]) if side > 0 else (al[j], ah[j], ao[j])
        if side > 0:
            if lo <= stop:
                return j, min(stop, op) if j > j0 else stop, "stop"
            if hi >= target:
                return j, target, "target"
        else:
            if hi >= stop:
                return j, max(stop, op) if j > j0 else stop, "stop"
            if lo <= target:
                return j, target, "target"
    return None


def run(m1: pd.DataFrame, sym: str, tf: str, window: str, variant: str, bias: pd.Series | None, rng) -> tuple[list, list]:
    b = candles(m1, tf)
    m1loc = m1.copy()
    m1loc.index = m1loc.index.tz_convert(NY)
    o, h, l, c, atr = (b[x].to_numpy() for x in ("o", "h", "l", "c", "atr"))
    end = b["end"].to_numpy()
    mins, day = b["mins"].to_numpy(), b["day"].to_numpy()
    ns1 = m1.index.as_unit("ns").asi8
    sp_o = (m1.ask_o - m1.bid_o).to_numpy()
    ask_o, bid_o = m1.ask_o.to_numpy(), m1.bid_o.to_numpy()
    tick = TICK[sym]
    w0, w1, flat_m = WINDOWS[window]
    trades, control = [], []
    days = pd.DatetimeIndex(sorted(set(b["day"]))).tz_convert(NY)
    idx_by_day = pd.Series(np.arange(len(b))).groupby(b["day"].to_numpy()).apply(list)
    for d in days:
        if d.dayofweek >= 5 or d not in idx_by_day.index:
            continue
        rows = [i for i in idx_by_day[d] if w0 < mins[i] <= w1]
        if not rows:
            continue
        lv = levels_for_day(m1loc, d, window)
        if not lv:
            continue
        flat = (d + pd.Timedelta(minutes=flat_m)).tz_convert("UTC")
        # freshness: a level is spent if traded through between its start time and the candle before the sweep
        fresh = []
        for name, px, s, since in lv:
            seg = m1loc[(m1loc.index >= since) & (m1loc.index < pd.Timestamp(end[rows[0]]).tz_convert(NY) - pd.Timedelta(tf))]
            touched = (seg.m_l.min() < px) if s > 0 else (seg.m_h.max() > px) if len(seg) else False
            if len(seg) and touched:
                continue
            fresh.append((name, px, s))
        state = {1: None, -1: None}                              # side → dict(x, ext, level_name)
        done = False
        for i in rows:
            if done:
                break
            for s in (1, -1):
                stt = state[s]
                lows = l if s > 0 else -h
                # 1) sweep / new extreme
                if stt is None:
                    for name, px, ss in fresh:
                        if ss == s and ((l[i] < px - tick) if s > 0 else (h[i] > px + tick)):
                            state[s] = stt = {"x": i, "ext": l[i] if s > 0 else h[i], "lvl": name}
                            break
                    continue
                if (l[i] < stt["ext"]) if s > 0 else (h[i] > stt["ext"]):
                    stt.update(x=i, ext=l[i] if s > 0 else h[i])
                    continue
                if i - stt["x"] > EXPIRY:
                    continue
                lvl = cisd_level(o, c, stt["x"], s)
                if lvl is None or not (s * (c[i] - lvl) > 0):
                    continue
                if variant == "B":
                    bt = bias[bias.index <= pd.Timestamp(end[i])] if bias is not None else None
                    if bt is None or not len(bt) or bt.iloc[-1] != s:
                        state[s] = None
                        continue
                # 2) CISD fired on candle i
                a = atr[i] if np.isfinite(atr[i]) else np.nan
                if not np.isfinite(a):
                    continue
                stop_mid = stt["ext"] - s * BUF_ATR * a
                if variant == "A":
                    j0 = int(np.searchsorted(ns1, pd.Timestamp(end[i]).value))
                    if j0 >= len(ns1) or ns1[j0] - pd.Timestamp(end[i]).value > 5 * 60 * 1_000_000_000:
                        continue
                    entry = ask_o[j0] if s > 0 else bid_o[j0]
                    spread = sp_o[j0]
                    lim_bar = i
                else:
                    gap = None
                    for m in range(max(stt["x"], 1), min(i + 3, len(b) - 1)):
                        lo_g, hi_g = (h[m - 1], l[m + 1]) if s > 0 else (h[m + 1], l[m - 1])
                        if hi_g - lo_g >= FVG_MIN_ATR * a:
                            gap = (m, (lo_g + hi_g) / 2)
                            break
                    if gap is None:
                        state[s] = None
                        continue
                    m, limit = gap
                    lim_bar = max(i, m + 1)
                    j_place = int(np.searchsorted(ns1, pd.Timestamp(end[lim_bar]).value))
                    if j_place >= len(ns1):
                        continue
                    spread = sp_o[j_place]
                    risk = s * (limit - stop_mid)
                    target_px = limit + s * TARGET_R * risk
                    j_end = int(np.searchsorted(ns1, pd.Timestamp(end[min(lim_bar + EXPIRY, len(b) - 1)]).value))
                    win_end = (d + pd.Timedelta(minutes=w1)).tz_convert("UTC").value
                    fill = None
                    for j in range(j_place, min(j_end, len(ns1))):
                        if ns1[j] >= win_end:
                            break
                        px_fill = m1.ask_l.iat[j] if s > 0 else m1.bid_h.iat[j]
                        far = m1.bid_h.iat[j] if s > 0 else m1.ask_l.iat[j]
                        if s * (far - target_px) >= 0:
                            break                                   # ran to 2R without us
                        if s * (m1.m_c.iat[j] - stt["ext"]) < 0:
                            break                                   # closed beyond the sweep extreme
                        if (px_fill <= limit) if s > 0 else (px_fill >= limit):
                            fill = j
                            break
                    if fill is None:
                        done = True
                        break
                    j0, entry = fill, limit
                stop = stop_mid - s * spread / 2                     # stop on the exit side (bid for longs)
                risk = s * (entry - stop)
                if risk <= 0 or risk < FLOOR_SPREADS * spread:
                    state[s] = None
                    continue
                target = entry + s * TARGET_R * risk
                res = simulate(m1, j0, s, entry, stop, target, flat)
                if res is None:
                    done = True
                    break
                jx, px, why = res
                pts = s * (px - entry)
                cost = spread
                trades.append({"entry_time": m1.index[j0], "exit_time": m1.index[jx], "side": s, "entry": entry,
                               "exit": px, "atr": risk, "points": pts, "R": pts / risk, "R_2x": (pts - cost) / risk,
                               "cost_R": cost / risk, "exit_reason": why, "level": stt["lvl"],
                               "hold_min": (m1.index[jx] - m1.index[j0]).total_seconds() / 60, "overnight": False})
                if variant == "A":                                   # coin-flip control: same time, distance, target
                    cs = int(rng.choice([1, -1]))
                    ce = ask_o[j0] if cs > 0 else bid_o[j0]
                    cst = ce - cs * risk
                    ctg = ce + cs * TARGET_R * risk
                    cr = simulate(m1, j0, cs, ce, cst, ctg, flat)
                    if cr is not None:
                        cpts = cs * (cr[1] - ce)
                        control.append({"entry_time": m1.index[j0], "exit_time": m1.index[cr[0]], "side": cs, "entry": ce,
                                        "exit": cr[1], "atr": risk, "points": cpts, "R": cpts / risk,
                                        "R_2x": (cpts - spread) / risk, "cost_R": spread / risk, "exit_reason": cr[2],
                                        "level": "control", "hold_min": 0.0, "overnight": False})
                done = True
                break
    return trades, control


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    src = Path("data/export") / a.data
    a.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    grid = [("A", "5min"), ("A", "1min"), ("A", "15min"), ("B", "5min")]
    rows, allt = [], []
    for sym in SYMS:
        f = src / f"{sym}_M1.csv.gz"
        if not f.exists():
            continue
        m1 = load(f)
        days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).normalize())))
        days = days[days.dayofweek < 5]
        bias = htf_bias(m1)
        for variant, tf in grid:
            for window in WINDOWS:
                tr, ctl = run(m1, sym, tf, window, variant, bias if variant == "B" else None, rng)
                for name, t in ((f"Set {variant}", tr), ("coin-flip control", ctl)):
                    if name.startswith("coin") and (variant != "A"):
                        continue
                    T = pd.DataFrame(t)
                    st = stats(T, days) if len(T) else {"trades": 0}
                    if len(T):
                        st |= pip_stats(T, PIP.get(sym, 1.0))
                        st["target_hits"] = float((T.exit_reason == "target").mean())
                    key = {"symbol": sym, "rule": name, "tf": tf, "window": window}
                    rows.append({**key, **st})
                    if len(T):
                        allt.append(T.assign(**key))
                    print(f"  {sym:6s} {name:18s} {tf:5s} {window:6s} {st.get('trades', 0):4d} trades  "
                          f"avg {st.get('avg_R', float('nan')):+.3f}R  95% [{st.get('ci_lo', float('nan')):+.3f}, "
                          f"{st.get('ci_hi', float('nan')):+.3f}]", flush=True)
        del m1
    if allt:
        pd.concat(allt, ignore_index=True).to_csv(a.out / "trades.csv.gz", index=False)
    main_rows = [r for r in rows if r["rule"] != "coin-flip control"]
    npass = sum(bool(r.get("pass")) for r in main_rows)
    md = [f"# CISD on {a.data}", "",
          "Rules fixed before testing (fxagents/cisd_test.py docstring): Set A = sweep of PDH/PDL, Asian range or (NY) London "
          "range → CISD (close beyond the open of the first candle of the last delivery series, within 12 candles) → market "
          "entry, stop beyond the sweep extreme + 0.1 ATR, 2R target, skip if stop < 4 spreads, one trade per window. "
          "Set B adds a 1h-CISD bias and an FVG-midpoint limit entry. Real OANDA bid/ask fills; R includes the spread.", "",
          f"Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. **{npass} of {len(main_rows)} "
          f"cells pass.** The coin-flip control takes the same trades with a random direction: CISD only adds something if "
          "it beats its control.", "",
          "| Symbol | Rule | TF | Window | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Hit 2R | Net pips | Pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("trades"):
            md.append(f"| {r['symbol']} | {r['rule']} | {r['tf']} | {r['window']} | 0 | | | | | | | | | |")
            continue
        md.append(f"| {r['symbol']} | {r['rule']} | {r['tf']} | {r['window']} | {r['trades']} | {r['win']:.0%} | {r['avg_R']:+.3f} | "
                  f"{r['ci_lo']:+.2f} to {r['ci_hi']:+.2f} | {r['total_R']:+.1f} | {r['avg_R_2x']:+.3f} | {r['cost_R']:.3f} | "
                  f"{r['target_hits']:.0%} | {r['pips_net']:+,.0f} | {'**PASS**' if r.get('pass') and r['rule'] != 'coin-flip control' else 'no'} |")
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"data": a.data, "rows": rows}, indent=2, default=str))
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
