"""Strategy research on cached OANDA history: every setup × variant × instrument × timeframe, run
through the bot's own rules so the numbers mean what live trading would mean:

  • entries only inside the session windows, nothing in the last 20 minutes before the 15:50 flatten
  • the hard bias rule (Daily/4H/1H composite, side × score ≥ min_align; neutral skipped)
  • stops widened to ≥ 0.5 ATR, trades refused if the stop is > 10% of trade value
  • executed like the live agents + OANDA on 1-MINUTE bars (simulate_live): entries at the ask/bid,
    stops triggered on the far side of the spread, partials / full exits / adds at market at the 1m
    close, average-cost accounting; exits: 1R partial → stop to +0.1R → trail per R with adds (or the
    scalp profile: all out at 1R, no adds, 30-minute max hold), flat at 15:50, 4-hour max hold
  • each trade weighted by the size Risk can really take (margin cap, unit ceiling) → `rw`, in units of
    the full 0.5% budget — what the money actually does; `r` is per unit of the trade's own risk
  • an approximation of the news blackouts (no historical calendar is cached; see news_block)
  • legacy setups re-checked on the exact 700-bar window the live trader scans
  • one trade at a time per setup/instrument/timeframe for the CELL's own statistics — but every signal is
    simulated and kept: rows the cell would have skipped (its own earlier trade still open) carry
    `busy_self=True`. Cell stats drop them (own_trades); the playbook's portfolio replay uses all of them
    and applies occupancy only to positions it actually ACCEPTED (a rejected trade blocks nothing)

Output: one row per simulated trade (data/research/trades.pkl) for the selection step."""
from __future__ import annotations

import dataclasses
import itertools
import json
import logging
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .bias import bias_frame
from .indicators import resample_ohlc
from .setup_map import history_dir
from .sim import Mgmt
from .strategies import BUILTIN, SETUPS, Strategy, build_strategy
from .structure import window_mask

log = logging.getLogger("research")

TFS = ["1min", "3min", "5min", "15min", "30min", "1h"]
SCALP_TFS = {"1min", "3min", "5min"}
PEERS = {"NDQ": ["US30"], "US30": ["NDQ"], "XAUUSD": []}
DEFAULT_SPREAD = {"XAUUSD": 0.62, "SPX": 0.50, "NDQ": 2.30, "US30": 3.00,   # OANDA 1m bid/ask medians, Oct 2024–Sep 2026
                  "EURUSD": 0.00014, "GBPUSD": 0.00020, "AUDUSD": 0.00016}
# A raw-spread ECN account (0.0–1 pip + ~$7 per lot round turn), as an all-in spread per round trip:
# FX 0.2–0.3 pip raw + 0.7 pip commission; gold 0.12 + 0.07; indices typically commission-free.
RAW_SPREAD = {"XAUUSD": 0.20, "NDQ": 1.00, "US30": 1.60, "EURUSD": 0.00009, "GBPUSD": 0.00010, "AUDUSD": 0.00010}
NOT_ON = {"ict_silver_bullet": {"30min", "1h"}, "smt_divergence": set(),
          "trend_pullback": {"1min", "3min", "5min"}, "trend_breakout": {"1min", "3min", "5min"}}   # SB needs bars inside one hour


def research_dir(cfg) -> Path:
    """Next to the history cache (data/research), so replays — whose journal lives in the run folder —
    still read the same research trades."""
    if cfg.get("research_dir"):
        return Path(cfg["research_dir"])
    return Path(history_dir(cfg)).parent / "research"


def variants(cls) -> list[dict]:
    """Default parameters + one-factor-at-a-time changes from the grid (new setups); legacy setups
    run as they are (the learner already tunes those live)."""
    base = dict(cls.default_params)
    out = [{}]
    if cls.name in SETUPS:
        for k, vals in cls.param_grid.items():
            for v in vals:
                if base.get(k) != v:
                    out.append({k: v})
        out += [{"vol": v} for v in getattr(cls, "vol_grid", ()) if base.get("vol", "any") != v]
    return out


def vkey(change: dict) -> str:
    return "default" if not change else ",".join(f"{k}={v}" for k, v in sorted(change.items()))


def mgmt_profiles(cfg, tf: str) -> dict[str, Mgmt]:
    """Exit profiles as live runs them. `pyramid` here means only "adds allowed" — whether the first
    target closes everything is `full_exit()` (live: no_pyramid ≠ full_exit). std takes its adds from the
    config (pyramid.enabled AND max_adds; max_adds 0 = no adds, as live)."""
    bm = int(pd.Timedelta(tf).total_seconds() // 60)
    std = Mgmt.from_cfg(cfg, bar_minutes=bm)
    std.pyramid = bool(std.pyramid and std.max_adds > 0)
    out = {"std": std}
    if tf in SCALP_TFS:
        out["scalp"] = Mgmt(rr=1.0, partial=1.0, lock_r=std.lock_r, trail_step_r=std.trail_step_r, trail_gap_r=std.trail_gap_r, pyramid=False,
                            max_adds=0, add_frac=0.0, max_hold_bars=max(2, int(30 / bm)),
                            min_stop_atr=std.min_stop_atr, max_stop_pct=std.max_stop_pct)
    # fixed take-profit profiles (opt-in: research.exit_profiles: [tp1, tp1.5, tp2]): all out at the target, no runner,
    # no adds — to compare a hard TP against the runner management
    for name in ((cfg.get("research") or {}).get("exit_profiles") or []):
        if str(name).startswith("tp"):
            out[str(name)] = Mgmt(rr=float(str(name)[2:]), partial=1.0, lock_r=std.lock_r, trail_step_r=std.trail_step_r,
                                  trail_gap_r=0.0, pyramid=False, max_adds=0, add_frac=0.0, max_hold_bars=std.max_hold_bars,
                                  min_stop_atr=std.min_stop_atr, max_stop_pct=std.max_stop_pct)
    if bm >= 15:
        # trend profile = live RiskAgent mgmt "trend": first target ≥2R, the configured partial banked, the runner
        # managed by the same runner rules as std (trail, stall), NO adds, held up to 8 h. (Until Oct 2026 this
        # was simulated as all-out at 2R — audit F08.)
        out["trend"] = dataclasses.replace(std, rr=max(std.rr, 2.0), pyramid=False, max_adds=0, add_frac=0.0,
                                           max_hold_bars=max(2, int(480 / bm)))
    study = (cfg.get("research") or {}).get("exit_study")
    if study:                                  # each base profile × the early-protection variants ("std|B", …)
        out = {f"{name}|{v}": dataclasses.replace(m, **ch) for name, m in out.items() for v, ch in study.items()}
    return out


def full_exit(cfg, pname: str) -> bool:
    """Does the first target close the whole position? Live (PositionManager): yes when the profile sets
    meta.full_exit (scalp, tpX) or pyramiding is globally disabled; trend/std bank a partial and run the rest."""
    pname = pname.split("|")[0]
    return pname == "scalp" or pname.startswith("tp") or not cfg["management"]["pyramid"]["enabled"]


def own_trades(t: pd.DataFrame) -> pd.DataFrame:
    """The cell's own one-at-a-time record: drop the candidates it would have skipped while its own trade
    was open (busy_self). Every per-cell statistic uses this; the portfolio replay uses all rows."""
    return t[~t["busy_self"].astype(bool)] if "busy_self" in t.columns else t


# ── live-style execution on 1-minute bars ─────────────────────────────────────
def analyst_arrays(m1: pd.DataFrame, close1: pd.DatetimeIndex) -> dict:
    """Per side, boolean arrays on the 1-minute grid (true at the minute a closed candle shows the event):
    flip = a 15m close crossing the 15m EMA50 against that side; brk = a 5m close beyond the last confirmed 5m swing
    low (for longs; swing high for shorts), swings being 2-candle fractals known 2 candles later."""
    out = {1: {}, -1: {}}
    r15 = m1.resample("15min", label="right", closed="left")
    c15 = r15["close"].last().dropna()
    e50 = c15.ewm(span=50, adjust=False, min_periods=50).mean()
    above = (c15 > e50)
    below = (c15 < e50)
    flip = {1: below & above.shift(1, fill_value=False), -1: above & below.shift(1, fill_value=False)}
    r5 = m1.resample("5min", label="right", closed="left")
    b5 = pd.DataFrame({"h": r5["high"].max(), "l": r5["low"].min(), "c": r5["close"].last()}).dropna()
    hh, ll, cc = b5.h.to_numpy(), b5.l.to_numpy(), b5.c.to_numpy()
    n = len(cc)
    sl, sh = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(2, n - 2):
        if ll[i] < min(ll[i - 2], ll[i - 1], ll[i + 1], ll[i + 2]):
            sl[i + 2] = ll[i]
        if hh[i] > max(hh[i - 2], hh[i - 1], hh[i + 1], hh[i + 2]):
            sh[i + 2] = hh[i]
    sl_k = pd.Series(sl).ffill().shift(1).to_numpy()            # last swing confirmed BEFORE this candle
    sh_k = pd.Series(sh).ffill().shift(1).to_numpy()
    brk = {1: pd.Series(cc < sl_k, index=b5.index), -1: pd.Series(cc > sh_k, index=b5.index)}
    for sd in (1, -1):
        out[sd]["flip"] = flip[sd].reindex(close1).fillna(False).to_numpy(bool)
        out[sd]["brk"] = brk[sd].reindex(close1).fillna(False).to_numpy(bool)
    return out


def simulate_live(O, H, L, C, tmin, j0: int, side: int, stop: float, m: Mgmt, hs: float, flat: np.ndarray,
                  cont: np.ndarray | None, max_hold: float, full_exit: bool, an: dict | None = None) -> dict | None:
    """One trade managed the way the live agents and OANDA execute it, on 1-minute MID bars:
      entry at market at the close of 1m bar j0 (ask for longs: mid + half-spread); the resting stop
      triggers when the bid (longs) / ask (shorts) reaches it and fills there, or at the gapped open;
      the position manager notices target steps on the 1m mid high/low and acts at that bar's close —
      partials, full exits and adds all fill AT MARKET (OANDA ignores limit prices); the add's safety
      check uses the level (as live does) but the add fills at the close; time exits at the close.
    Runner rules (Mgmt): gap trail, structure trail (confirmed 1m pivots), stall tightening, structure adds.
    Every stop change is decided at a bar's close and protects from the next bar on.
    Accounting is average-cost. Returns R in units of the filled entry's risk.
    `hs` = half the bid/ask spread: one number, or an array per 1m bar (the real spread of a bid/ask export)."""
    HS = hs if np.ndim(hs) else None
    hsj = (lambda j: HS[j]) if HS is not None else (lambda j: hs)          # noqa: E731
    px_in = C[j0] + side * hsj(j0)
    R = abs(px_in - stop)
    if R <= 0:
        return None
    lvl = lambda k: px_in + side * (m.rr + (k - 1) * m.trail_step_r) * R                 # noqa: E731
    stop_after = lambda k: px_in + side * ((0.0 if k == 1 else m.rr + (k - 2) * m.trail_step_r) + m.lock_r) * R  # noqa: E731
    stop_px, step, adds = stop, 0, 0
    early_done = False
    open_q, avg, realized = 1.0, px_in, 0.0          # realized in price × qty (initial qty = 1)
    mfe, best_j = 0.0, j0
    k = int(m.struct_k)
    use_struct = (m.trail_struct or m.add_mode in ("structure", "both")) and k > 0
    last_pivot = None                                 # price of the last confirmed higher low (longs) / lower high
    armed = False                                     # structure add: a fresh higher low is in, waiting for a new high
    n = len(C)

    def done(px, reason, j):
        tot = realized + (px - avg) * side * open_q
        return {"r": float(tot / R), "exit_reason": reason, "j_exit": int(j), "adds": adds, "steps": step,
                "mfe": float(mfe), "R": float(R), "px_in": float(px_in)}

    def try_add(j, worst_stop, ref):
        """Add at market (fills at the ask/bid). The never-risk-open-profit check uses `ref` exactly as live
        does: the step level for step adds, the bar's mid close for structure adds."""
        nonlocal avg, open_q, adds
        if not (m.pyramid and adds < m.max_adds and (cont is None or cont[j])):
            return
        q = m.add_frac
        chk = (avg * open_q + ref * q) / (open_q + q)
        if realized + (worst_stop - chk) * side * (open_q + q) >= 0:          # never risk open profit
            fill = C[j] + side * hsj(j)
            avg, open_q, adds = (avg * open_q + fill * q) / (open_q + q), open_q + q, adds + 1

    def move(ns, j, why):
        """Ratchet the stop to ns (only toward profit, ≥0.1R better); out at market if price is already through."""
        nonlocal stop_px
        if (ns - stop_px) * side < 0.1 * R:
            return None
        if ((C[j] - side * hsj(j)) - ns) * side <= 0:
            return done(C[j] - side * hsj(j), why, j)
        stop_px = ns
        return None

    j = j0
    for j in range(j0 + 1, n):
        # 1) resting stop (the broker checks stops before the manager runs)
        h_ = hsj(j)
        far_lo = (L[j] - h_) if side > 0 else (H[j] + h_)
        if (far_lo - stop_px) * side <= 0:
            far_open = (O[j] - h_) if side > 0 else (O[j] + h_)
            fill = far_open if (far_open - stop_px) * side < 0 else stop_px
            return done(fill, "stop" if step == 0 else ("breakeven_plus_stop" if step == 1 else "trail_stop"), j)
        mkt = C[j] - side * h_                                                   # exit at market
        prev_best = px_in + side * mfe * R
        new_best = ((H[j] if side > 0 else L[j]) - px_in) * side / R
        if new_best > mfe:
            mfe, best_j = new_best, j
        # 2) time exits
        if flat[j]:
            return done(mkt, "session_flat", j)
        if tmin[j] - tmin[j0] >= max_hold:
            return done(mkt, "max_hold", j)
        # 2b) protection before the first target (exit study; all off by default)
        if step == 0:
            if not early_done and ((m.early_partial_r > 0 and mfe >= m.early_partial_r)
                                   or (m.early_partial_pts > 0 and mfe * R >= m.early_partial_pts)):
                early_done = True
                q = min(m.early_partial_frac, open_q)
                realized += (mkt - avg) * side * q
                open_q -= q
                r = move(px_in + side * m.early_lock_r * R, j, "early_lock_stop")
                if r:
                    return r
            if m.early_be_r > 0 and mfe >= m.early_be_r:
                r = move(px_in + side * m.early_lock_r * R, j, "early_lock_stop")
                if r:
                    return r
        if m.giveback_after_r > 0 and mfe >= m.giveback_after_r and (mkt - px_in) * side / R <= mfe * (1 - m.giveback_frac):
            return done(mkt, "giveback", j)
        # 2c) trade-analyst exits (analyst check; all off by default)
        if an is not None:
            if m.an_flip and an["flip"][j]:
                return done(mkt, "analyst_trend_flip", j)
            if m.an_break and an["brk"][j]:
                return done(mkt, "analyst_structure_break", j)
        if m.an_stall_min > 0 and tmin[j] - tmin[best_j] >= m.an_stall_min and (mkt - px_in) * side / R < m.an_stall_max_r:
            return done(mkt, "analyst_stall", j)
        # 3) target steps on the mid high/low
        hi = H[j] if side > 0 else L[j]
        while (hi - lvl(step + 1)) * side >= 0:
            step += 1
            if step == 1:
                if full_exit:                         # scalp / tpX (or adds globally off): all out
                    return done(mkt, "target", j)
                q = 0.0 if early_done else min(m.partial, open_q)     # an early partial replaces the 1R one
                realized += (mkt - avg) * side * q
                open_q -= q
            ns = stop_after(step)
            if (ns - stop_px) * side > 0:
                stop_px = ns
            if m.add_mode in ("step", "both") and step >= m.add_from_step:
                try_add(j, stop_px, lvl(step))
        if step < 1:
            continue
        # 4) runner rules (after the first target)
        if use_struct and j - k > j0 + k:
            p = j - k
            win = L[p - k:j + 1] if side > 0 else H[p - k:j + 1]
            piv = L[p] if side > 0 else H[p]
            if (piv <= win.min() if side > 0 else piv >= win.max()) and (last_pivot is None or (piv - last_pivot) * side > 0):
                last_pivot = piv
                armed = True
                if m.trail_struct:
                    r = move(piv - side * (h_ + m.struct_buf_r * R), j, "trail_stop")
                    if r:
                        return r
        if m.add_mode in ("structure", "both") and armed and ((H[j] if side > 0 else L[j]) - prev_best) * side > 0:
            armed = False
            try_add(j, stop_px, C[j])
        if m.trail_gap_r > 0:
            r = move(px_in + side * (mfe - m.trail_gap_r) * R, j, "trail_stop")
            if r:
                return r
        if m.stall_minutes > 0 and tmin[j] - tmin[best_j] >= m.stall_minutes:
            r = move(px_in + side * (mfe - m.stall_gap_r) * R, j, "trail_stop")
            if r:
                return r
    return done(C[j] - side * hsj(j), "end", j)


def margin_weight(cfg, ic: dict, price: float, dist: float, equity: float) -> float:
    """Share of the full risk budget Risk can actually take: the per-position margin cap and the unit
    ceiling cut size when the stop is tight (e.g. gold at 22% margin: stops under ~18 points)."""
    r = cfg["risk"]
    budget_units = equity * r["risk_per_trade_pct"] / (dist * float(ic.get("multiplier", 1)))
    caps = [float(ic.get("max_units", 1e12))]
    mr = float(ic.get("margin_rate") or 0)
    if mr:
        caps.append(r.get("max_margin_pct_per_position", 0.25) * equity / (price * float(ic.get("multiplier", 1)) * mr))
    return float(min(1.0, min(caps) / budget_units)) if budget_units > 0 else 0.0


FOMC_2026 = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"}
# FOMC decision days (statement day) — the year tests reach back into 2024/2025 (audit F22)
FOMC = FOMC_2026 | {"2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07",
                    "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17",
                    "2025-10-29", "2025-12-10"}


def news_block(ts: pd.Timestamp) -> bool:
    """No historical calendar is cached, so approximate the live blackouts: the 08:30 release window
    every weekday (±15 min), NFP Fridays (first Friday, 08:00–09:00), the 10:00 releases (±5 min) and
    FOMC days (13:30–15:00: statement 14:00, press conference 14:30)."""
    hm = ts.hour * 60 + ts.minute
    if 8 * 60 + 15 <= hm < 8 * 60 + 45 or 9 * 60 + 55 <= hm < 10 * 60 + 5:
        return True
    # NFP ≈ the first Friday — an approximation: BLS sometimes moves it (e.g. to the second Friday when the 1st
    # is early in the week / holidays, or a Thursday), and shutdowns delay it; no point-in-time calendar is cached
    if ts.dayofweek == 4 and ts.day <= 7 and 8 * 60 <= hm < 9 * 60:
        return True
    return ts.strftime("%Y-%m-%d") in FOMC and 13 * 60 + 30 <= hm < 15 * 60


def verify_live_window(st: Strategy, df: pd.DataFrame, i: int, side: int, window: int = 700) -> bool:
    """Legacy setups aren't strictly causal on a whole frame: re-scan the exact window the live trader
    would have (the last `window` bars) and keep the signal only if it fires on that last bar."""
    sub = df.iloc[max(0, i - window + 1):i + 1]
    return any(r.i == len(sub) - 1 and r.side == side for r in st._scan_full(sub, Strategy._context(sub)))


def load(cfg, sym: str):
    m1, h1 = pd.read_pickle(history_dir(cfg) / f"{sym}.pkl")
    return m1, h1


def _signals(st: Strategy, df: pd.DataFrame, ctx: dict, offsets: int = 1) -> list:
    """Candidate signals of a setup over a whole frame. Legacy setups are O(n × swings), so they are scanned in
    overlapping 1400-bar chunks (each chunk keeps its second half). They are not strictly causal on a frame, so a
    chunk can miss a signal the live trader (last 700 bars, every bar) would see, and which ones depends on where
    the chunks fall — shifting the data's start changed ~7% of US30 sr_rejection signals (Oct 22 2026).
    `offsets` > 1 unions chunkings shifted by 700/offsets bars: on 3 months of US30 5m, 1 → 8.3% of live signals
    missed, 4 → 0.7%, 8 → 0.2%. Callers that need live fidelity verify each candidate with verify_live_window."""
    if getattr(st, "fast", False):
        return st._scan_full(df, ctx)
    W, out, seen = 700, [], set()
    for k in range(max(1, int(offsets))):
        off = k * W // max(1, int(offsets))
        for start in range(-off, len(df), W):
            lo, hi = max(0, start - W), min(len(df), start + W)
            if hi <= lo:
                continue
            sub = df.iloc[lo:hi]
            for s in st._scan_full(sub, Strategy._context(sub)):
                gi = lo + s.i
                if max(start, 0) <= gi < start + W and (gi, s.side) not in seen:
                    seen.add((gi, s.side))
                    s.i = gi
                    out.append(s)
    return out


def run_job(args) -> list[dict]:
    """All setups × variants × exit profiles for one instrument and timeframe, executed live-style."""
    cfg, sym, tf, classes = args
    t0 = time.time()
    m1, h1 = load(cfg, sym)
    df = resample_ohlc(m1, tf)
    ctx = Strategy._context(df)
    peers = []
    for p in PEERS.get(sym, []):
        try:
            pm1, _ = load(cfg, p)
            peers.append(resample_ohlc(pm1, tf).reindex(df.index).ffill())
        except FileNotFoundError:
            pass
    ctx["peers"] = peers
    close_ts = ctx["close_ts"]
    C_tf = df["close"].to_numpy(dtype=float)
    bias = bias_frame(h1, close_ts, weights=(cfg.get("bias") or {}).get("weights"))["score"].to_numpy()
    s_cfg = cfg["sessions"]
    fh, fm = map(int, s_cfg["flatten_at"].split(":"))
    mins = close_ts.hour * 60 + close_ts.minute
    late = np.asarray((mins >= fh * 60 + fm - 20) & (mins < 17 * 60), bool)
    entry_ok = window_mask(close_ts, s_cfg["entry_windows"]) & ~late
    news = np.array([news_block(t) for t in close_ts], bool)
    min_align = float(cfg["bias"]["min_align"])
    spread = float(((cfg.get("shadow") or {}).get("spread") or {}).get(sym, DEFAULT_SPREAD.get(sym, 0.0)))
    hs = spread / 2
    if "spread" in m1.columns:                      # a bid/ask export: the real spread of every minute (playbook test)
        hs = (m1["spread"].to_numpy(dtype=float) / 2)
        spread = float(np.nanmedian(m1["spread"].to_numpy(dtype=float)))
    a = ctx["atr"]
    # 1-minute execution arrays (the position manager and the broker work on 1m bars)
    O1, H1, L1, C1 = (m1[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    close1 = m1.index + pd.Timedelta("1min")
    # minutes since epoch — via a ns view: pandas 3 indexes are often us/s, and raw asi8 // 6e10 then breaks max_hold
    tmin = (m1.index.as_unit("ns").asi8 // 60_000_000_000).astype(np.int64)
    m1min = close1.hour * 60 + close1.minute
    flat1 = np.asarray((m1min >= fh * 60 + fm) & (m1min < 17 * 60), bool)
    # live continuation check for adds: 5-minute momentum, known at each 5m close
    d5 = resample_ohlc(m1, "5min")
    c5 = Strategy._context(d5)
    cont5 = {sd: pd.Series(((np.sign(d5["close"].to_numpy() - c5["ema50"]) == sd) & (np.sign(c5["macd_hist"]) == sd)).astype(float),
                           index=d5.index + pd.Timedelta("5min")) for sd in (1, -1)}
    cont1 = {sd: cont5[sd].reindex(cont5[sd].index.union(close1)).ffill().reindex(close1).fillna(0).to_numpy() > 0.5
             for sd in (1, -1)}
    j_of = np.searchsorted(m1.index.as_unit("ns").asi8, (close_ts - pd.Timedelta("1min")).as_unit("ns").asi8, side="right") - 1
    ic = {**cfg["instruments"].get(sym, {}), **((load_specs_cached(cfg) or {}).get(sym, {}))}
    equity = float((cfg.get("playbook") or {}).get("equity_usd", 70000))
    profiles = mgmt_profiles(cfg, tf)
    AN = analyst_arrays(m1, close1) if any(m.an_flip or m.an_break for m in profiles.values()) else None
    rows = []
    for cname in classes:
        cls = {**BUILTIN, **SETUPS}[cname]
        if tf in NOT_ON.get(cname, set()) or (cls.needs_peers and not peers):
            continue
        if not getattr(cls, "fast", False) and tf == "1min":
            continue          # legacy setups need a live-window re-check per signal; 1m isn't traded anyway
        only = ((cfg.get("research") or {}).get("only_params") or {})
        for change in ([only[cname]] if cname in only else variants(cls)):
            st = build_strategy({"class": cname, "tf": tf, "params": change})
            try:
                sigs = sorted(_signals(st, df, ctx), key=lambda s: s.i)
            except Exception as e:  # noqa: BLE001
                log.warning("%s %s %s %s failed: %s", sym, tf, cname, vkey(change), e)
                continue
            # the live filters, then (legacy only) the exact live-window check
            keep = []
            for s in sigs:
                i = s.i
                if i >= len(C_tf) - 1 or not entry_ok[i] or news[i]:
                    continue
                sc = bias[i]
                if not np.isfinite(sc) or s.side * sc < min_align:
                    continue                                     # hard bias rule (neutral / counter skipped)
                j0 = int(j_of[i])
                if j0 < 0 or m1.index[j0] < df.index[i] or abs(C1[j0] - C_tf[i]) > 1e-9 * max(1.0, abs(C_tf[i])):
                    continue
                keep.append((s, j0))
            if not getattr(cls, "fast", False):
                keep = [(s, j0) for s, j0 in keep if verify_live_window(st, df, s.i, s.side)]
            for pname, m in profiles.items():
                busy_until = -1
                base = pname.split("|")[0]
                max_hold = 30.0 if base == "scalp" else 480.0 if base == "trend" else float(s_cfg["max_hold_minutes"])
                fx = full_exit(cfg, pname)
                for s, j0 in keep:
                    # the cell's own trade still open → keep the candidate, flagged (the portfolio may have
                    # rejected that earlier trade, in which case live would take this one — audit F16)
                    busy = j0 <= busy_until
                    i, price = s.i, C1[j0]
                    stop = s.stop
                    if abs(price - stop) < m.min_stop_atr * a[i]:
                        stop = price - s.side * m.min_stop_atr * a[i]
                    dist = abs(price - stop)
                    if dist <= 0 or (price - stop) * s.side <= 0 or dist / price > m.max_stop_pct:
                        continue
                    res = simulate_live(O1, H1, L1, C1, tmin, j0, s.side, stop, m, hs, flat1, cont1[s.side],
                                        max_hold, full_exit=fx, an=AN[s.side] if AN else None)
                    if res is None:
                        continue
                    if not busy:
                        busy_until = res["j_exit"]
                    w = margin_weight(cfg, ic, price, dist, equity)
                    ts = close_ts[i]
                    rows.append({"sym": sym, "tf": tf, "setup": cname, "family": cls.family, "variant": vkey(change),
                                 "mgmt": pname, "ts": ts, "exit_ts": close1[res["j_exit"]],
                                 "day": (ts + pd.Timedelta(hours=7)).normalize().date(),
                                 "hour": ts.hour, "wd": ts.dayofweek, "side": s.side, "bias": float(bias[i]),
                                 "risk_atr": float(dist / a[i]) if a[i] else np.nan,
                                 "r": res["r"], "w": w, "rw": res["r"] * w * res["R"] / dist,
                                 "cost_r": spread * (1 + m.add_frac * res["adds"]) / res["R"],
                                 "exit": res["exit_reason"], "bars": int((res["j_exit"] - j0)), "adds": res["adds"],
                                 "mfe": res["mfe"], "busy_self": busy})
    log.info("%s %s: %d trades (%.0fs)", sym, tf, len(rows), time.time() - t0)
    return rows


_SPECS: dict = {}


def load_specs_cached(cfg):
    from .setup_map import load_specs
    if "v" not in _SPECS:
        _SPECS["v"] = load_specs(cfg)
    return _SPECS["v"]


# ── run manifest: which code, which settings, which data produced a result ─
MANIFEST_KEYS = ("instruments", "management", "risk", "sessions", "bias", "playbook", "research")


def git_sha() -> str:
    """The commit this code runs at: `git rev-parse HEAD`, else $FX_GIT_SHA (set it in images without .git)."""
    import os
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.environ.get("FX_GIT_SHA") or "unknown"


def config_hash(cfg) -> str:
    """Short sha256 of the settings that shape research results — only MANIFEST_KEYS + shadow.spread are
    hashed (never broker credentials or other secrets)."""
    import hashlib
    eff = {k: cfg.get(k) for k in MANIFEST_KEYS}
    eff["shadow.spread"] = (cfg.get("shadow") or {}).get("spread")
    return hashlib.sha256(json.dumps(eff, sort_keys=True, default=str).encode()).hexdigest()[:16]


def manifest(cfg, t: pd.DataFrame | None = None, **extra) -> dict:
    """git commit + config hash + the data span (first/last trade entry, trading days) of a run."""
    span = None
    if t is not None and len(t):
        ts = pd.to_datetime(t["ts"])
        span = {"from": str(ts.min()), "to": str(ts.max()),
                "trade_days": int(t["day"].nunique()) if "day" in t.columns else None}
    return {"git_sha": git_sha(), "config_sha256": config_hash(cfg), "config_hashed": [*MANIFEST_KEYS, "shadow.spread"],
            "history_dir": str(history_dir(cfg)), "data_span": span, **extra}


def run_job_frame(args) -> pd.DataFrame:
    """run_job's trades as one DataFrame — far smaller to pickle back and to hold than a list of dicts."""
    return pd.DataFrame(run_job(args))


def run_all(cfg, symbols=None, tfs=None, classes=None, workers: int = 2) -> pd.DataFrame:
    symbols = symbols or [s for s in cfg["instruments"] if (history_dir(cfg) / f"{s}.pkl").exists()]
    tfs = tfs or TFS
    classes = classes or list(SETUPS) + list(BUILTIN)
    # biggest jobs first so the two workers finish together
    jobs = sorted(((cfg, s, tf, classes) for s, tf in itertools.product(symbols, tfs)),
                  key=lambda j: pd.Timedelta(j[2]))
    # Memory (the 365-day grid was OOM-killed twice at 1.1–1.5 GB): each worker hands back its job as a
    # DataFrame (~0.2 KB a trade) instead of a list of dicts (~1.5 KB), and every worker process is
    # replaced after one job, so nothing a job built stays resident while the next one runs.
    parts = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                             max_tasks_per_child=1) as ex:
        for part in ex.map(run_job_frame, jobs):
            if len(part):
                parts.append(part)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    del parts
    out = research_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    df.to_pickle(out / "trades.pkl")
    (out / "trades_meta.json").write_text(json.dumps({
        "created": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"),
        "symbols": symbols, "tfs": tfs, "classes": classes, "n": len(df)}, indent=1))
    return df
