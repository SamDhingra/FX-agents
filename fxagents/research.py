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
  • one trade at a time per setup/instrument/timeframe

Output: one row per simulated trade (data/research/trades.pkl) for the selection step."""
from __future__ import annotations

import itertools
import json
import logging
import time
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
DEFAULT_SPREAD = {"XAUUSD": 0.40, "SPX": 0.50, "NDQ": 1.50, "US30": 2.50}
NOT_ON = {"ict_silver_bullet": {"30min", "1h"}, "smt_divergence": set()}   # SB needs bars inside one hour


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
    bm = int(pd.Timedelta(tf).total_seconds() // 60)
    std = Mgmt.from_cfg(cfg, bar_minutes=bm)
    out = {"std": std}
    if tf in SCALP_TFS:
        out["scalp"] = Mgmt(rr=1.0, partial=1.0, lock_r=std.lock_r, trail_step_r=std.trail_step_r, trail_gap_r=std.trail_gap_r, pyramid=False,
                            max_adds=0, add_frac=0.0, max_hold_bars=max(2, int(30 / bm)),
                            min_stop_atr=std.min_stop_atr, max_stop_pct=std.max_stop_pct)
    return out


# ── live-style execution on 1-minute bars ─────────────────────────────────────
def simulate_live(O, H, L, C, tmin, j0: int, side: int, stop: float, m: Mgmt, hs: float, flat: np.ndarray,
                  cont: np.ndarray | None, max_hold: float, full_exit: bool) -> dict | None:
    """One trade managed the way the live agents and OANDA execute it, on 1-minute MID bars:
      entry at market at the close of 1m bar j0 (ask for longs: mid + half-spread); the resting stop
      triggers when the bid (longs) / ask (shorts) reaches it and fills there, or at the gapped open;
      the position manager notices target steps on the 1m mid high/low and acts at that bar's close —
      partials, full exits and adds all fill AT MARKET (OANDA ignores limit prices); the add's safety
      check uses the level (as live does) but the add fills at the close; time exits at the close.
    Runner rules (Mgmt): gap trail, structure trail (confirmed 1m pivots), stall tightening, structure adds.
    Every stop change is decided at a bar's close and protects from the next bar on.
    Accounting is average-cost. Returns R in units of the filled entry's risk."""
    px_in = C[j0] + side * hs
    R = abs(px_in - stop)
    if R <= 0:
        return None
    lvl = lambda k: px_in + side * (m.rr + (k - 1) * m.trail_step_r) * R                 # noqa: E731
    stop_after = lambda k: px_in + side * ((0.0 if k == 1 else m.rr + (k - 2) * m.trail_step_r) + m.lock_r) * R  # noqa: E731
    stop_px, step, adds = stop, 0, 0
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
            fill = C[j] + side * hs
            avg, open_q, adds = (avg * open_q + fill * q) / (open_q + q), open_q + q, adds + 1

    def move(ns, j, why):
        """Ratchet the stop to ns (only toward profit, ≥0.1R better); out at market if price is already through."""
        nonlocal stop_px
        if (ns - stop_px) * side < 0.1 * R:
            return None
        if ((C[j] - side * hs) - ns) * side <= 0:
            return done(C[j] - side * hs, why, j)
        stop_px = ns
        return None

    j = j0
    for j in range(j0 + 1, n):
        # 1) resting stop (the broker checks stops before the manager runs)
        far_lo = (L[j] - hs) if side > 0 else (H[j] + hs)
        if (far_lo - stop_px) * side <= 0:
            far_open = (O[j] - hs) if side > 0 else (O[j] + hs)
            fill = far_open if (far_open - stop_px) * side < 0 else stop_px
            return done(fill, "stop" if step == 0 else ("breakeven_plus_stop" if step == 1 else "trail_stop"), j)
        mkt = C[j] - side * hs                                                   # exit at market
        prev_best = px_in + side * mfe * R
        new_best = ((H[j] if side > 0 else L[j]) - px_in) * side / R
        if new_best > mfe:
            mfe, best_j = new_best, j
        # 2) time exits
        if flat[j]:
            return done(mkt, "session_flat", j)
        if tmin[j] - tmin[j0] >= max_hold:
            return done(mkt, "max_hold", j)
        # 3) target steps on the mid high/low
        hi = H[j] if side > 0 else L[j]
        while (hi - lvl(step + 1)) * side >= 0:
            step += 1
            if step == 1:
                if full_exit or not m.pyramid:
                    return done(mkt, "target", j)
                q = min(m.partial, open_q)
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
                    r = move(piv - side * (hs + m.struct_buf_r * R), j, "trail_stop")
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
    return done(C[j] - side * hs, "end", j)


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


def news_block(ts: pd.Timestamp) -> bool:
    """No historical calendar is cached, so approximate the live blackouts: the 08:30 release window
    every weekday (±15 min), NFP Fridays (first Friday, 08:00–09:00), the 10:00 releases (±5 min) and
    FOMC days (13:30–15:00: statement 14:00, press conference 14:30)."""
    hm = ts.hour * 60 + ts.minute
    if 8 * 60 + 15 <= hm < 8 * 60 + 45 or 9 * 60 + 55 <= hm < 10 * 60 + 5:
        return True
    if ts.dayofweek == 4 and ts.day <= 7 and 8 * 60 <= hm < 9 * 60:
        return True
    return ts.strftime("%Y-%m-%d") in FOMC_2026 and 13 * 60 + 30 <= hm < 15 * 60


def verify_live_window(st: Strategy, df: pd.DataFrame, i: int, side: int, window: int = 700) -> bool:
    """Legacy setups aren't strictly causal on a whole frame: re-scan the exact window the live trader
    would have (the last `window` bars) and keep the signal only if it fires on that last bar."""
    sub = df.iloc[max(0, i - window + 1):i + 1]
    return any(r.i == len(sub) - 1 and r.side == side for r in st._scan_full(sub, Strategy._context(sub)))


def load(cfg, sym: str):
    m1, h1 = pd.read_pickle(history_dir(cfg) / f"{sym}.pkl")
    return m1, h1


def _signals(st: Strategy, df: pd.DataFrame, ctx: dict) -> list:
    if getattr(st, "fast", False):
        return st._scan_full(df, ctx)
    # legacy setups are O(n × swings): scan in overlapping 1400-bar chunks, keep each chunk's second half
    W, out = 700, []
    for start in range(0, len(df), W):
        lo, hi = max(0, start - W), min(len(df), start + W)
        sub = df.iloc[lo:hi]
        for s in st._scan_full(sub, Strategy._context(sub)):
            if start <= lo + s.i < start + W:
                s.i += lo
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
    bias = bias_frame(h1, close_ts)["score"].to_numpy()
    s_cfg = cfg["sessions"]
    fh, fm = map(int, s_cfg["flatten_at"].split(":"))
    mins = close_ts.hour * 60 + close_ts.minute
    late = np.asarray((mins >= fh * 60 + fm - 20) & (mins < 17 * 60), bool)
    entry_ok = window_mask(close_ts, s_cfg["entry_windows"]) & ~late
    news = np.array([news_block(t) for t in close_ts], bool)
    min_align = float(cfg["bias"]["min_align"])
    spread = float(((cfg.get("shadow") or {}).get("spread") or {}).get(sym, DEFAULT_SPREAD.get(sym, 0.0)))
    hs = spread / 2
    a = ctx["atr"]
    # 1-minute execution arrays (the position manager and the broker work on 1m bars)
    O1, H1, L1, C1 = (m1[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    close1 = m1.index + pd.Timedelta("1min")
    tmin = (m1.index.asi8 // 60_000_000_000).astype(np.int64)
    m1min = close1.hour * 60 + close1.minute
    flat1 = np.asarray((m1min >= fh * 60 + fm) & (m1min < 17 * 60), bool)
    # live continuation check for adds: 5-minute momentum, known at each 5m close
    d5 = resample_ohlc(m1, "5min")
    c5 = Strategy._context(d5)
    cont5 = {sd: pd.Series(((np.sign(d5["close"].to_numpy() - c5["ema50"]) == sd) & (np.sign(c5["macd_hist"]) == sd)).astype(float),
                           index=d5.index + pd.Timedelta("5min")) for sd in (1, -1)}
    cont1 = {sd: cont5[sd].reindex(cont5[sd].index.union(close1)).ffill().reindex(close1).fillna(0).to_numpy() > 0.5
             for sd in (1, -1)}
    j_of = np.searchsorted(m1.index.asi8, (close_ts - pd.Timedelta("1min")).asi8, side="right") - 1
    ic = {**cfg["instruments"].get(sym, {}), **((load_specs_cached(cfg) or {}).get(sym, {}))}
    equity = float((cfg.get("playbook") or {}).get("equity_usd", 70000))
    profiles = mgmt_profiles(cfg, tf)
    rows = []
    for cname in classes:
        cls = {**BUILTIN, **SETUPS}[cname]
        if tf in NOT_ON.get(cname, set()) or (cls.needs_peers and not peers):
            continue
        if not getattr(cls, "fast", False) and tf == "1min":
            continue          # legacy setups need a live-window re-check per signal; 1m isn't traded anyway
        for change in variants(cls):
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
                max_hold = 30.0 if pname == "scalp" else float(s_cfg["max_hold_minutes"])
                for s, j0 in keep:
                    if j0 <= busy_until:
                        continue
                    i, price = s.i, C1[j0]
                    stop = s.stop
                    if abs(price - stop) < m.min_stop_atr * a[i]:
                        stop = price - s.side * m.min_stop_atr * a[i]
                    dist = abs(price - stop)
                    if dist <= 0 or (price - stop) * s.side <= 0 or dist / price > m.max_stop_pct:
                        continue
                    res = simulate_live(O1, H1, L1, C1, tmin, j0, s.side, stop, m, hs, flat1, cont1[s.side],
                                        max_hold, full_exit=(pname == "scalp"))
                    if res is None:
                        continue
                    busy_until = res["j_exit"]
                    w = margin_weight(cfg, ic, price, dist, equity)
                    ts = close_ts[i]
                    rows.append({"sym": sym, "tf": tf, "setup": cname, "family": cls.family, "variant": vkey(change),
                                 "mgmt": pname, "ts": ts, "exit_ts": close1[res["j_exit"]],
                                 "day": (ts + pd.Timedelta(hours=7)).normalize().date(),
                                 "hour": ts.hour, "wd": ts.dayofweek, "side": s.side, "bias": float(sc),
                                 "risk_atr": float(dist / a[i]) if a[i] else np.nan,
                                 "r": res["r"], "w": w, "rw": res["r"] * w * res["R"] / dist,
                                 "cost_r": spread * (1 + m.add_frac * res["adds"]) / res["R"],
                                 "exit": res["exit_reason"], "bars": int((res["j_exit"] - j0)), "adds": res["adds"],
                                 "mfe": res["mfe"]})
    log.info("%s %s: %d trades (%.0fs)", sym, tf, len(rows), time.time() - t0)
    return rows


_SPECS: dict = {}


def load_specs_cached(cfg):
    from .setup_map import load_specs
    if "v" not in _SPECS:
        _SPECS["v"] = load_specs(cfg)
    return _SPECS["v"]


def run_all(cfg, symbols=None, tfs=None, classes=None, workers: int = 2) -> pd.DataFrame:
    symbols = symbols or [s for s in cfg["instruments"] if (history_dir(cfg) / f"{s}.pkl").exists()]
    tfs = tfs or TFS
    classes = classes or list(SETUPS) + list(BUILTIN)
    # biggest jobs first so the two workers finish together
    jobs = sorted(((cfg, s, tf, classes) for s, tf in itertools.product(symbols, tfs)),
                  key=lambda j: pd.Timedelta(j[2]))
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for part in ex.map(run_job, jobs):
            rows.extend(part)
    df = pd.DataFrame(rows)
    out = research_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    df.to_pickle(out / "trades.pkl")
    (out / "trades_meta.json").write_text(json.dumps({
        "created": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"),
        "symbols": symbols, "tfs": tfs, "classes": classes, "n": len(df)}, indent=1))
    return df
