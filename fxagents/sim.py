"""Backtesting core shared by the Evaluator agent, the Selector's statistics and backtest.py.

`simulate_outcome` replays the exact management the live Position Manager uses:
1R first target → bank a partial, stop to +lock R → pyramid adds on each further step with a trailing
stop → flatten at session end / max hold. Results are in R (multiples of the initial risk).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .indicators import in_windows
from .strategies import Strategy


@dataclass
class Mgmt:
    rr: float = 1.0
    partial: float = 0.5
    lock_r: float = 0.1
    trail_step_r: float = 1.0
    trail_gap_r: float = 0.0          # >0: once the first target is hit, the stop also follows the best price this far behind (R)
    # runner management (after the first target):
    #   structure: the stop follows each new confirmed higher low (lower high for shorts) on 1m pivots of
    #              half-width `struct_k` (default = the entry timeframe in minutes), so pullbacks that keep the
    #              trend's structure don't stop the trade
    #   stall:     if no new best price for `stall_minutes`, the stop tightens to `stall_gap_r` behind the best
    trail_struct: bool = False
    struct_k: int = 0
    struct_buf_r: float = 0.1
    stall_minutes: float = 0.0
    stall_gap_r: float = 0.5
    # adds: "step" = at each +1R step (default); "structure" = after a confirmed higher low, when price makes a new high
    add_mode: str = "step"
    add_from_step: int = 1            # step adds start at this target step (1 = already at the first target)
    pyramid: bool = True
    max_adds: int = 2
    add_frac: float = 0.5
    max_hold_bars: int = 48
    min_stop_atr: float = 0.5
    max_stop_pct: float = 0.10

    @classmethod
    def from_cfg(cls, cfg, rr: float | None = None, bar_minutes: int = 5) -> "Mgmt":
        m, r = cfg["management"], cfg["risk"]
        return cls(rr=rr or m["rr_initial"], partial=m["partial_at_target"], lock_r=m["lock_r"],
                   trail_step_r=m["trail_step_r"], trail_gap_r=float(m.get("trail_gap_r", 0) or 0),
                   trail_struct=(m.get("runner") or {}).get("structure_trail", False),
                   struct_k=int((m.get("runner") or {}).get("struct_k", 0) or bar_minutes),
                   struct_buf_r=float((m.get("runner") or {}).get("struct_buf_r") or 0.1),
                   stall_minutes=float((m.get("runner") or {}).get("stall_minutes", 0) or 0),
                   stall_gap_r=float((m.get("runner") or {}).get("stall_gap_r") or 0.5),
                   add_mode=(m.get("runner") or {}).get("add_mode", "step"),
                   add_from_step=int(m["pyramid"].get("from_step", 1)), pyramid=m["pyramid"]["enabled"],
                   max_adds=m["pyramid"]["max_adds"], add_frac=m["pyramid"]["add_size_frac"],
                   max_hold_bars=int(cfg["sessions"]["max_hold_minutes"] / bar_minutes),
                   min_stop_atr=r["min_stop_atr"], max_stop_pct=r["max_stop_pct_of_trade_value"])


def level_r(step: int, m: Mgmt) -> float:
    """R-multiple of the k-th target step (step 1 = first target)."""
    return m.rr + (step - 1) * m.trail_step_r


def stop_r_after(step: int, m: Mgmt) -> float:
    """Where the stop sits (in R from entry) once `step` targets have been reached."""
    return m.lock_r if step == 1 else level_r(step - 1, m) + m.lock_r


def worst_case_after_add(units: list[tuple[float, float]], realized_r: float, new_stop_r: float) -> float:
    """Total R if everything is stopped at new_stop_r. units = [(entry_r, frac)]"""
    return realized_r + sum((new_stop_r - e) * f for e, f in units)


def simulate_outcome(O, H, L, C, i0: int, side: int, entry: float, stop: float, m: Mgmt,
                     flat_mask: np.ndarray, cont_ok: np.ndarray | None = None) -> dict:
    R = abs(entry - stop)
    to_r = lambda px: (px - entry) * side / R  # noqa: E731
    units = [(0.0, 1.0)]              # (entry in R, fraction of initial size)
    realized, step, stop_r = 0.0, 0, -1.0
    mfe = mae = 0.0
    n = len(C)
    for j in range(i0 + 1, min(n, i0 + 1 + m.max_hold_bars)):
        o, hi, lo, c = (to_r(O[j]), to_r(H[j] if side > 0 else L[j]),
                        to_r(L[j] if side > 0 else H[j]), to_r(C[j]))
        # stop first (conservative)
        if lo <= stop_r:
            px = min(stop_r, o)
            return _close(realized, units, px, "stop" if step == 0 else "trail_stop", j - i0, mfe, mae, step)
        mfe, mae = max(mfe, hi), min(mae, lo)
        while hi >= level_r(step + 1, m):
            step += 1
            lvl = level_r(step, m)
            if step == 1:
                if not m.pyramid:
                    return _close(realized, units, lvl, "target", j - i0, mfe, mae, step)
                take = m.partial
                units[0] = (0.0, 1.0 - take)
                realized += lvl * take
            stop_r = stop_r_after(step, m)
            adds = len(units) - 1
            if m.pyramid and adds < m.max_adds and (cont_ok is None or cont_ok[j]):
                trial = units + [(lvl, m.add_frac)]
                if worst_case_after_add(trial, realized, stop_r) >= 0:
                    units = trial
        if m.trail_gap_r > 0 and step >= 1 and mfe - m.trail_gap_r - stop_r >= 0.1:
            if c <= mfe - m.trail_gap_r:
                return _close(realized, units, c, "trail_stop", j - i0, mfe, mae, step)
            stop_r = mfe - m.trail_gap_r
        if flat_mask[j]:
            return _close(realized, units, c, "session_flat", j - i0, mfe, mae, step)
    j = min(n - 1, i0 + m.max_hold_bars)
    return _close(realized, units, to_r(C[j]), "time", j - i0, mfe, mae, step)


def _close(realized, units, px_r, reason, bars, mfe, mae, step) -> dict:
    total = realized + sum((px_r - e) * f for e, f in units)
    return {"r": float(total), "exit_reason": reason, "bars": int(bars), "mfe": float(mfe),
            "mae": float(mae), "steps": step, "adds": len(units) - 1}


def backtest(strat: Strategy, df: pd.DataFrame, ctx: dict, m: Mgmt, entry_windows, flatten_at: str,
             start_i: int = 0, bias_score: np.ndarray | None = None, min_align: float = 0.25) -> list[dict]:
    """bias_score (aligned to df rows, known at each bar close) applies the live HARD bias rule:
    only signals with side × score ≥ min_align are taken — so stats reflect what can really trade."""
    O, H, L, C = (df[c].to_numpy() for c in ("open", "high", "low", "close"))
    close_ts = ctx["close_ts"]
    fh, fm = map(int, flatten_at.split(":"))
    mins = close_ts.hour * 60 + close_ts.minute
    flat_mask = np.asarray((mins >= fh * 60 + fm) & (mins < 17 * 60), dtype=bool)
    ema50, hist = ctx["ema50"], ctx["macd_hist"]
    trades, busy = [], -1
    a = ctx["atr"]
    for s in strat.scan(df, ctx):
        if s.i <= busy or s.i < start_i or not in_windows(close_ts[s.i], entry_windows) or flat_mask[s.i]:
            continue
        if bias_score is not None and s.side * bias_score[s.i] < min_align:
            continue
        entry, stop = s.entry, s.stop
        if abs(entry - stop) < m.min_stop_atr * a[s.i]:
            stop = entry - s.side * m.min_stop_atr * a[s.i]
        if abs(entry - stop) / entry > m.max_stop_pct:
            continue
        cont = (np.sign(C - ema50) == s.side) & (np.sign(hist) == s.side)
        res = simulate_outcome(O, H, L, C, s.i, s.side, entry, stop, m, flat_mask, cont)
        busy = s.i + res["bars"]
        ts = close_ts[s.i]
        trades.append({"ts": ts, "hour": ts.hour, "side": s.side, "entry": entry, "stop": stop,
                       "reason": s.reason, "bias": float(bias_score[s.i]) if bias_score is not None else None, **res})
    return trades


def stats(trades: list[dict], now: pd.Timestamp | None = None) -> dict:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "expectancy": 0.0, "pf": 0.0, "sum_r": 0.0, "avg_mfe": 0.0,
                "max_dd_r": 0.0, "by_hour": {}, "recent_exp": 0.0, "recent_n": 0, "reach": {}}
    r = np.array([t["r"] for t in trades])
    mfe = np.array([t["mfe"] for t in trades])
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]        # start from flat equity: an opening losing streak is drawdown too
    dd = float((np.maximum.accumulate(eq) - eq).max())
    by_hour: dict[int, dict] = {}
    for t in trades:
        b = by_hour.setdefault(int(t["hour"]), {"n": 0, "sum": 0.0, "w": 0})
        b["n"] += 1; b["sum"] += t["r"]; b["w"] += t["r"] > 0
    by_hour = {h: {"n": b["n"], "exp": round(b["sum"] / b["n"], 3), "win": round(b["w"] / b["n"], 3)}
               for h, b in sorted(by_hour.items())}
    recent = [t["r"] for t in trades if now is not None and (now - t["ts"]) <= pd.Timedelta("36h")]
    return {"n": int(len(r)), "win_rate": round(float((r > 0).mean()), 3),
            "expectancy": round(float(r.mean()), 3), "pf": round(float(wins / losses), 2) if losses else 99.0,
            "sum_r": round(float(r.sum()), 2), "avg_mfe": round(float(mfe.mean()), 2), "max_dd_r": round(dd, 2),
            "by_hour": by_hour, "recent_exp": round(float(np.mean(recent)), 3) if recent else 0.0,
            "recent_n": len(recent),
            "reach": {x: round(float((mfe >= x).mean()), 3) for x in (1.0, 1.5, 2.0, 3.0)}}


# ── synthetic market (sim mode + tests) ───────────────────────────────────────
def synth_1m(start_price: float, daily_vol: float, start: pd.Timestamp, days: int, seed: int,
             tz: str = "America/New_York") -> pd.DataFrame:
    """Regime-switching random walk with an intraday volatility profile and the CME daily break.
    Not a market model — just enough structure (trends, ranges, sweeps) to exercise every agent."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, start + pd.Timedelta(days=days), freq="1min", tz=tz, inclusive="left")
    idx = idx[(idx.dayofweek < 5) & ~((idx.hour == 17))]
    n = len(idx)
    hour = idx.hour + idx.minute / 60
    prof = np.full(n, 0.6)
    prof[(hour >= 2) & (hour < 5)] = 1.1
    prof[(hour >= 8.5) & (hour < 11.5)] = 1.6
    prof[(hour >= 13.5) & (hour < 16)] = 1.2
    sig = daily_vol / np.sqrt(1380) * prof
    drift = np.zeros(n)
    k = 0
    while k < n:
        span = int(rng.integers(40, 260))
        regime = rng.choice([-1, 0, 1], p=[0.3, 0.4, 0.3])
        drift[k:k + span] = regime * 0.12
        k += span
    shocks = rng.standard_t(5, size=(n, 4)) / np.sqrt(5 / 3)
    logp = np.log(start_price)
    rows = np.empty((n, 4))
    anchor = logp
    for t in range(n):
        path = []
        x = logp
        mr = -0.02 * (x - anchor) / max(sig[t], 1e-9) if drift[t] == 0 else 0.0
        for s in range(4):
            x += sig[t] / 2 * (shocks[t, s] + drift[t] + mr * 0.1)
            path.append(x)
        o = logp
        rows[t] = (o, max(o, *path), min(o, *path), path[-1])
        logp = path[-1]
        if drift[t] != 0:
            anchor = logp
    px = np.exp(rows)
    return pd.DataFrame(px, index=idx, columns=["open", "high", "low", "close"]).assign(
        volume=rng.integers(50, 500, n).astype(float))
