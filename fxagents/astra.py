"""ASTRA research strategies (spec: Astra_Strategy_Research v0.1.0), implemented exactly as specified
and executed with the spec's conservative OHLC fill rules:

  ASTRA-ICT-MRSF-001  morning-range (08:00–09:29) sweep & reclaim in the 5m trend → displacement that
                      closes beyond the 3-bar structure → FVG on the very next bar → buy/sell limit at the
                      gap midpoint, stop beyond the sweep, fixed 2R target inside the range.
  ASTRA-DTFX-PF-SR-001 1m confirmed-pivot close-break (BOS/flip) with displacement in the 5m trend → frozen
                      zone protected-extreme → break bar, limit at the 50% level, stop beyond the zone, 2R.

Shared: signals 09:35–10:55 (bar closes), no new exposure from 11:00, unfilled orders cancelled at 11:00 or
after 5 bars, positions closed at the 30-minute holding limit or 11:30; one pending/open trade per
instrument; 5m features lagged (strictly earlier completed 5m bar); ATR14 Wilder on 1m.
Fills (OHLC approximation, §10): limits activate on the bar after the proposal and need one tick of
penetration on the ask (buys) / bid (sells); entry at the limit; entry+stop reachable in one bar → stop;
stop+target in one bar → stop; stop gaps fill at the adverse open; exits on the bid (longs) / ask (shorts).
Shorts run the long code on the mirrored series (prices negated; floor/ceil rounding mirrors exactly).
Controls (§11): sweep-reclaim market entry, morning-range breakout, trend-only at 09:45, random-in-trend."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .research import FOMC_2026, news_block

TICK = {"XAUUSD": 0.001, "NDQ": 0.1, "US30": 0.1, "SPX": 0.1}    # OANDA price increments
SPREAD = {"XAUUSD": 0.40, "SPX": 0.50, "NDQ": 1.50, "US30": 2.50}


def _ema_sma_seed(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = x[:n].mean()
    a = 2 / (n + 1)
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _wilder_atr(H, L, C, n=14) -> np.ndarray:
    pc = np.r_[np.nan, C[:-1]]
    tr = np.nanmax(np.vstack([H - L, np.abs(H - pc), np.abs(L - pc)]), axis=0)
    tr[0] = H[0] - L[0]
    out = np.full(len(tr), np.nan)
    if len(tr) <= n:
        return out
    out[n] = tr[1:n + 1].mean()
    for i in range(n + 1, len(tr)):
        out[i] = (13 * out[i - 1] + tr[i]) / 14
    return out


def features(m1: pd.DataFrame) -> dict:
    """1m arrays plus the lagged 5m regime (+1 up / −1 down / 0) and Wilder ATR14."""
    O, H, L, C = (m1[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    t_close = m1.index + pd.Timedelta("1min")
    b5 = m1.resample("5min", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min",
                                                               "close": "last"}).dropna()
    c5 = b5["close"].to_numpy()
    e20, e50 = _ema_sma_seed(c5, 20), _ema_sma_seed(c5, 50)
    e20_3 = np.r_[np.full(3, np.nan), e20[:-3]]
    up = (c5 > e20) & (e20 > e50) & (e20 > e20_3)
    dn = (c5 < e20) & (e20 < e50) & (e20 < e20_3)
    reg5 = np.where(up, 1, np.where(dn, -1, 0))
    reg5[:250] = 0                                                   # 250 completed 5m bars of warm-up
    end5 = (b5.index + pd.Timedelta("5min")).asi8
    # decision at a 1m close t uses the latest 5m bar whose END is strictly before t
    k = np.searchsorted(end5, t_close.asi8, side="left") - 1
    reg = np.where(k >= 0, reg5[np.clip(k, 0, None)], 0)
    hm = (t_close.hour * 60 + t_close.minute).to_numpy()
    lab_hm = (m1.index.hour * 60 + m1.index.minute).to_numpy()
    day = (m1.index.tz_convert("America/New_York").normalize()).asi8
    return {"O": O, "H": H, "L": L, "C": C, "A": _wilder_atr(H, L, C), "reg": reg, "hm": hm, "lab_hm": lab_hm,
            "day": day, "t_close": t_close, "index": m1.index}


def _fl(x, q):
    return np.floor(x / q + 1e-9) * q


def _cl(x, q):
    return np.ceil(x / q - 1e-9) * q


# ── execution of one frozen proposal (long view) ─────────────────────────────
def _execute(f, view, j_first, j_expire, E, S, T, cancel, hs, q, side) -> dict | None:
    """Limit at E active on bars j_first..j_expire (bar labels < 11:00). Returns trade or None (no fill).
    `cancel(j)` → reason string for close-based pre-entry cancellation evaluated at the close of bar j."""
    O, H, L, C = view
    hm, lab = f["hm"], f["lab_hm"]
    n = len(C)
    for j in range(j_first, min(j_expire, n - 1) + 1):
        if lab[j] >= 11 * 60 or news_block(f["t_close"][j]):
            return {"filled": False, "why": "deadline/blackout"}
        ask_lo = L[j] + hs                                   # buy limit fills when the ask trades through E by a tick
        if ask_lo <= E - q:
            entry_j = j
            # entry and stop reachable in the same bar → stopped
            if L[j] - hs <= S:
                return _trade(f, entry_j, entry_j, E, min(S, O[j] - hs) if O[j] - hs < S else S, "stop_same_bar", E - S, side)
            return _manage(f, view, entry_j, E, S, T, hs, side)
        if H[j] - hs >= T:
            return {"filled": False, "why": "target before entry"}
        why = cancel(j)
        if why:
            return {"filled": False, "why": why}
    return {"filled": False, "why": "expired"}


def _manage(f, view, j_in, E, S, T, hs, side) -> dict:
    O, H, L, C = view
    hm = f["hm"]
    t_in = f["t_close"][j_in]
    for j in range(j_in + 1, len(C)):
        bid_lo, bid_hi, bid_open = L[j] - hs, H[j] - hs, O[j] - hs
        stop_hit, tgt_hit = bid_lo <= S, bid_hi >= T
        if stop_hit:
            return _trade(f, j_in, j, E, bid_open if bid_open < S else S, "stop", E - S, side)
        if tgt_hit:
            return _trade(f, j_in, j, E, T, "target", E - S, side)
        if (f["t_close"][j] - t_in) >= pd.Timedelta("30min"):
            return _trade(f, j_in, j, E, C[j] - hs, "time_30m", E - S, side)
        if hm[j] >= 11 * 60 + 30:
            return _trade(f, j_in, j, E, C[j] - hs, "liquidate_1130", E - S, side)
        if news_block(f["t_close"][j]):
            return _trade(f, j_in, j, E, C[j] - hs, "blackout", E - S, side)
    return _trade(f, j_in, len(C) - 1, E, C[-1] - hs, "end", E - S, side)


def _trade(f, j_in, j_out, E, X, why, R, side) -> dict:
    return {"filled": True, "j_in": j_in, "j_out": j_out, "r": (X - E) / R if R > 0 else 0.0, "exit": why,
            "side": side}


# ── strategies ───────────────────────────────────────────────────────────────
def _views(f):
    O, H, L, C = f["O"], f["H"], f["L"], f["C"]
    return {1: (O, H, L, C), -1: (-O, -L, -H, -C)}


def _days(f):
    d = f["day"]
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    ends = np.r_[starts[1:], len(d)]
    return list(zip(starts, ends))


def mrsf(f, sym, params=None) -> list[dict]:
    """ASTRA-ICT-MRSF-001 v0.1.0 (both sides, one pending/open at a time, each side once a day)."""
    p = {"disp_k": 1.0, "gap_k": 0.10, "expiry": 5, "target_r": 2.0, **(params or {})}
    q, hs = TICK[sym], SPREAD[sym] / 2
    A_all, reg_all, hm, lab = f["A"], f["reg"], f["hm"], f["lab_hm"]
    out = []
    for a, b in _days(f):
        ts0 = f["index"][a]
        if ts0.strftime("%Y-%m-%d") in FOMC_2026 or ts0.dayofweek >= 5:
            continue
        rng = np.flatnonzero((lab[a:b] >= 8 * 60) & (lab[a:b] < 9 * 60 + 30)) + a
        if len(rng) != 90:
            continue                                                    # incomplete reference window
        busy_until = -1
        used = set()
        for s in range(a, b):
            if hm[s] < 9 * 60 + 35 or hm[s] > 10 * 60 + 55 or s <= busy_until or s < 4:
                continue
            for side in (1, -1):
                if side in used or s <= busy_until:
                    continue
                O, H, L, C = _views(f)[side]
                RL, RH = (f["L"][rng].min(), f["H"][rng].max()) if side > 0 else (-f["H"][rng].max(), -f["L"][rng].min())
                reg = reg_all * side
                A = A_all[s - 1]
                if not (A > 0) or reg[s] != 1:
                    continue
                if not (L[s] <= RL - q and RL < C[s] < RH and C[s - 1] > RL and H[s] < RH + q):
                    continue
                if not (4 * A <= RH - RL <= 30 * A):
                    continue
                used.add(side)                                           # consume the side
                bbuf = max(2 * q, _cl(0.10 * A, q))
                B = max(H[s - 3], H[s - 2], H[s - 1])
                d = None
                for j in range(s + 1, min(s + 6, b)):
                    if C[j] <= RL or reg[j] != 1:
                        break
                    body, r_ = C[j] - O[j], H[j] - L[j]
                    if C[j] > O[j] and body >= p["disp_k"] * A and r_ > 0 and body / r_ >= 0.6 and C[j] >= B + q:
                        d = j
                        break
                if d is None or d + 1 >= b:
                    busy_until = max(busy_until, min(s + 5, b - 1))
                    continue
                k = d + 1
                gap_lo, gap_hi = H[d - 1], L[k]
                if not (gap_hi - gap_lo >= max(q, _cl(p["gap_k"] * A, q)) and C[k] > B and reg[k] == 1):
                    busy_until = k
                    continue
                E = _fl((gap_lo + gap_hi) / 2, q)
                S = _fl(L[s:k + 1].min() - bbuf, q)
                R = E - S
                T = E + p["target_r"] * R
                if not (gap_lo < E < gap_hi and RL < E < RH and E < C[k] and 0.5 * A <= R <= 3 * A and T <= RH - q):
                    busy_until = k
                    continue

                def cancel(j, C=C, RL=RL, gap_lo=gap_lo, reg=reg):
                    if C[j] <= RL:
                        return "close through range"
                    if C[j] < gap_lo:
                        return "close beyond gap"
                    if reg[j] != 1:
                        return "regime lost"
                    return None
                res = _execute(f, (O, H, L, C), k + 1, k + p["expiry"], E, S, T, cancel, hs, q, side)
                rec = {"sym": sym, "strategy": "ASTRA-ICT-MRSF-001", "side": side, "setup_ts": f["t_close"][s],
                       "day": ts0.date(), "risk_atr": R / A, **res}
                out.append(rec)
                busy_until = res["j_out"] if res.get("filled") else k + p["expiry"]
    return out


def dtfx(f, sym, params=None) -> list[dict]:
    """ASTRA-DTFX-PF-SR-001 v0.1.0."""
    p = {"disp_k": 1.0, "expiry": 5, "target_r": 2.0, "level": 0.5, **(params or {})}
    q, hs = TICK[sym], SPREAD[sym] / 2
    A_all, reg_all, hm, lab = f["A"], f["reg"], f["hm"], f["lab_hm"]
    out = []
    for a, b in _days(f):
        ts0 = f["index"][a]
        if ts0.strftime("%Y-%m-%d") in FOMC_2026 or ts0.dayofweek >= 5:
            continue
        busy_until, proposals = -1, 0
        state = {1: {"consumed": set()}, -1: {"consumed": set()}}
        lo_s = max(a, a + 2)
        for t in range(lo_s + 2, b):
            if proposals >= 2:
                break
            for side in (1, -1):
                O, H, L, C = _views(f)[side]
                # latest valid high confirmed strictly before t: pivot i with i+2 <= t-1
                piv = None
                for i in range(t - 3, max(a + 2, t - 61) - 1, -1):
                    if i + 2 < b and H[i] > max(H[i - 2], H[i - 1], H[i + 1], H[i + 2]):
                        piv = i
                        break
                if piv is None or piv in state[side]["consumed"]:
                    continue
                if not (C[t] >= H[piv] + q and C[t - 1] <= H[piv]):
                    continue
                state[side]["consumed"].add(piv)                         # consumed on first close-break
                if t <= busy_until or hm[t] < 9 * 60 + 35 or hm[t] > 10 * 60 + 55:
                    continue
                reg = reg_all * side
                A = A_all[t - 1]
                body, r_ = C[t] - O[t], H[t] - L[t]
                if not (A > 0 and reg[t] == 1 and C[t] > O[t] and body >= p["disp_k"] * A and r_ > 0 and body / r_ >= 0.6):
                    continue
                ZL, ZH = L[piv:t + 1].min(), H[t]
                E = _fl(ZL + p["level"] * (ZH - ZL), q)
                bbuf = max(2 * q, _cl(0.10 * A, q))
                S = _fl(ZL - bbuf, q)
                R = E - S
                T = E + p["target_r"] * R
                proposals += 1
                if not (E < C[t] and 0.5 * A <= R <= 3 * A):
                    continue

                def cancel(j, C=C, ZL=ZL, reg=reg, side=side, t=t):
                    if C[j] < ZL:
                        return "close through protected low"
                    if reg[j] != 1:
                        return "regime lost"
                    Oo, Ho, Lo, Co = _views(f)[-side]               # opposite confirmed break
                    for i in range(j - 3, max(t, j - 61) - 1, -1):
                        if Ho[i] > max(Ho[i - 2], Ho[i - 1], Ho[i + 1], Ho[i + 2]):
                            if Co[j] >= Ho[i] + q and Co[j - 1] <= Ho[i]:
                                return "opposite break"
                            break
                    return None
                res = _execute(f, (O, H, L, C), t + 1, t + p["expiry"], E, S, T, cancel, hs, q, side)
                out.append({"sym": sym, "strategy": "ASTRA-DTFX-PF-SR-001", "side": side, "setup_ts": f["t_close"][t],
                            "day": ts0.date(), "risk_atr": R / A, **res})
                busy_until = res["j_out"] if res.get("filled") else t + p["expiry"]
                break
    return out


# ── controls (same window, exits, 2R, costs) ─────────────────────────────────
def _market_trade(f, view, j, side, stop, hs, target_r=2.0):
    O, H, L, C = view
    E = C[j] + hs                                            # market entry at the close (ask)
    R = E - stop
    if R <= 0:
        return None
    return _manage(f, view, j, E, stop, E + target_r * R, hs, side)


def controls(f, sym, seed=0) -> list[dict]:
    q, hs = TICK[sym], SPREAD[sym] / 2
    A_all, reg_all, hm, lab = f["A"], f["reg"], f["hm"], f["lab_hm"]
    rng_ = np.random.default_rng(seed)
    out = []
    for a, b in _days(f):
        ts0 = f["index"][a]
        if ts0.strftime("%Y-%m-%d") in FOMC_2026 or ts0.dayofweek >= 5:
            continue
        rng = np.flatnonzero((lab[a:b] >= 8 * 60) & (lab[a:b] < 9 * 60 + 30)) + a
        if len(rng) != 90:
            continue
        win = [s for s in range(a, b) if 9 * 60 + 35 <= hm[s] <= 10 * 60 + 55 and not news_block(f["t_close"][s])]
        for side in (1, -1):
            O, H, L, C = _views(f)[side]
            view = (O, H, L, C)
            RL, RH = (f["L"][rng].min(), f["H"][rng].max()) if side > 0 else (-f["H"][rng].max(), -f["L"][rng].min())
            reg = reg_all * side
            # 1) simple sweep-reclaim, market entry (no displacement/FVG)
            for s in win:
                A = A_all[s - 1]
                if A > 0 and reg[s] == 1 and L[s] <= RL - q and RL < C[s] < RH and C[s - 1] > RL:
                    st = _fl(L[s] - max(2 * q, _cl(0.1 * A, q)), q)
                    res = _market_trade(f, view, s, side, st, hs)
                    if res and 0.5 * A <= (C[s] + hs - st) <= 3 * A:
                        out.append({"sym": sym, "strategy": "control: sweep-reclaim market", "side": side, "day": ts0.date(), **res})
                    break
            # 2) morning-range breakout with trend
            for s in win:
                A = A_all[s - 1]
                if A > 0 and reg[s] == 1 and C[s] >= RH + q and C[s - 1] < RH + q:
                    res = _market_trade(f, view, s, side, C[s] - 1.5 * A, hs)
                    if res:
                        out.append({"sym": sym, "strategy": "control: range breakout", "side": side, "day": ts0.date(), **res})
                    break
            # 3) trend only, fixed 09:45 decision
            s = next((s for s in win if hm[s] >= 9 * 60 + 45), None)
            if s is not None and A_all[s - 1] > 0 and reg[s] == 1:
                res = _market_trade(f, view, s, side, C[s] - 1.5 * A_all[s - 1], hs)
                if res:
                    out.append({"sym": sym, "strategy": "control: trend at 09:45", "side": side, "day": ts0.date(), **res})
            # 4) random entry in the trend direction (one per side per day, when in trend)
            cand = [s for s in win if reg[s] == 1 and A_all[s - 1] > 0]
            if cand:
                s = int(rng_.choice(cand))
                res = _market_trade(f, view, s, side, C[s] - 1.5 * A_all[s - 1], hs)
                if res:
                    out.append({"sym": sym, "strategy": "control: random in trend", "side": side, "day": ts0.date(), **res})
    return out
