"""The backtest engine: one execution model for every strategy.

Fills: market entries at the next minute's open on the ask (longs) / bid (shorts); limit and stop entries fill when the
ask/bid actually trades through the price (at the open if it gaps through). Exits on the other side. Every minute:
data gap → out at the last price; financing at each 17:00 NY crossing; flat time / Friday flat / max hold / time
stop; the stop FIRST (on the mid during the 16:55–18:05 spread spike), with slippage on intrabar stop fills; then
partials, the full target, the break-even move and trailing — and, if any of those moved the stop, a same-minute
check that the low didn't already take it. Results in R after spread, financing and (optionally) the 1% CAD
conversion; "2×" pays the spread and financing once more. Control: an exact coin flip — a long AND a short at the
same minute, same stop distance and exits, averaged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..usd_calendar import events
from . import ind
from .api import Costs, Exits, Signal, Strategy, costs_for
from .data import MIN, NY, Market

INF = float("inf")


def news_mask(m: Market, before: int, after: int, ten_am: bool = False) -> np.ndarray:
    mask = np.zeros(len(m), bool)
    for d, evs in events().items():
        for minute, _ in evs:
            t = (pd.Timestamp(d) + pd.Timedelta(minutes=minute)).tz_localize(NY).value
            i0, i1 = np.searchsorted(m.ns, [t - before * MIN, t + after * MIN])
            mask[i0:i1] = True
    if ten_am:
        mask |= (m.mod >= 595) & (m.mod < 605) & (m.dow < 5)
    return mask


def sides(m: Market) -> dict:
    """Mirrored execution arrays: for shorts every price is negated, so one long-only loop handles both sides."""
    return {1: {"in_o": m.ask_o, "in_h": m.ask_h, "in_l": m.ask_l, "ex_o": m.bid_o, "ex_h": m.bid_h, "ex_l": m.bid_l,
                "ex_c": m.bid_c, "mid_h": m.h, "mid_l": m.l, "mid_c": m.c},
            -1: {"in_o": -m.bid_o, "in_h": -m.bid_l, "in_l": -m.bid_h, "ex_o": -m.ask_o, "ex_h": -m.ask_l,
                 "ex_l": -m.ask_h, "ex_c": -m.ask_c, "mid_h": -m.l, "mid_l": -m.h, "mid_c": -m.c}}


class _Trail:
    """Trailing-stop state for one trade (mirrored prices)."""

    def __init__(self, m: Market, spec: dict, side: int, t_sig: int):
        self.spec, self.kind = spec, spec["kind"]
        self.ok = True
        if self.kind in ("chandelier", "swing"):
            b = m.bars(spec["tf"])
            self.end = b["end"].to_numpy()
            if self.kind == "chandelier":
                src = b["h"] if (spec.get("src", "close") == "high" and side > 0) else \
                    b["l"] if (spec.get("src", "close") == "high") else b["c"]
                self.src = side * src.to_numpy(float)
                self.atr = ind.atr(b, int(spec.get("atr", 14)))
            else:
                sh, sl = ind.swings(b["h"].to_numpy(), b["l"].to_numpy(), int(spec.get("k", 2)))
                self.sw = sl if side > 0 else -sh
            self.i = int(np.searchsorted(self.end, t_sig, side="right")) - 1     # the signal's candle
            self.peak = self.src[self.i] if self.kind == "chandelier" and self.i >= 0 else -INF

    def update(self, ns_k: int, ex_c: float, best_r: float, e: float, R: float, stop: float, close_r_ok: bool):
        """Called every minute; returns a candidate stop (mirrored) or None. Candle-based trails move only on the
        minute that completes a candle."""
        if self.kind == "gap_r":
            cand = e + (best_r - float(self.spec["gap"])) * R
            return cand if cand < ex_c else None
        if self.i + 1 >= len(self.end) or ns_k + MIN < self.end[self.i + 1]:
            return None
        self.i += 1
        if not close_r_ok:
            return None
        if self.kind == "chandelier":
            if np.isfinite(self.src[self.i]):
                self.peak = max(self.peak, self.src[self.i])
            a = self.atr[self.i]
            if not np.isfinite(a):
                return None
            cand = self.peak - float(self.spec.get("k", 2.0)) * a
        else:
            sw = self.sw[self.i]
            if not np.isfinite(sw):
                return None
            cand = sw - float(self.spec.get("buf_r", 0.0)) * R
        return cand if cand < ex_c else None


def manage(m: Market, M: dict, side: int, j: int, e: float, st0: float, ex: Exits, costs: Costs, t_sig: int,
           target_m: float | None = None, adjust=None, exit_ns: int | None = None) -> dict:
    """One trade from fill minute j, in mirrored prices (e = entry, st0 = initial stop). Returns the outcome."""
    ns, mod, dow, day = m.ns, m.mod, m.dow, m.day
    R = e - st0
    tgt = target_m if target_m is not None else (e + ex.target_r * R if ex.target_r else INF)
    parts = sorted([(float(r), float(f), (None if nsr is None else float(nsr))) for r, f, *rest in ex.partials
                    for nsr in [(rest[0] if rest else None)]])
    done_parts = [False] * len(parts)
    stop, frac, banked, best, worst = st0, 1.0, 0.0, 0.0, 0.0
    be_done = False
    mover = "stop"                                                  # which rule last moved the stop (exit label)
    rollovers = 0
    events = []
    trail = _Trail(m, ex.trail, side, t_sig) if ex.trail else None
    t_flat = None
    if ex.flat_at is not None:
        loc = pd.Timestamp(int(ns[j]), tz="UTC").tz_convert(NY)
        f = (pd.Timestamp(loc.date()) + pd.Timedelta(minutes=int(ex.flat_at))).tz_localize(NY)
        if f <= loc:
            f = (pd.Timestamp(loc.date()) + pd.Timedelta(days=1, minutes=int(ex.flat_at))).tz_localize(NY)
        t_flat = f.value
    k_time = int(np.searchsorted(ns, ns[j] + ex.time_stop[0] * MIN)) if ex.time_stop else -1
    k_exit = int(np.searchsorted(ns, exit_ns)) if exit_ns is not None else len(ns) + 1   # the strategy's own exit
    gap = costs.gap_exit_min if not ex.hold_overnight else max(costs.gap_exit_min, 180.0)
    shield = costs.rollover_shield
    close_after = (ex.trail or {}).get("after_close_r")
    close_ok = close_after is None

    def out(k, px, why):
        pts = banked + frac * (px - e)
        return {"jx": int(k), "pts": float(pts), "why": why, "rollovers": rollovers, "mfe_r": float(best),
                "mae_r": float(worst), "events": events, "exit_px": float(px), "stop_final": float(stop)}

    def slip(k):
        return costs.stop_slip_frac * float(m.spread[k])

    k = j
    n = len(ns)
    while k < n:
        if k > j and ns[k] - ns[k - 1] > gap * MIN:
            return out(k - 1, M["ex_c"][k - 1], "data_gap")
        if k > j and mod[k - 1] < 1020 and (mod[k] >= 1020 or day[k] != day[k - 1]):
            rollovers += 3 if dow[k - 1] == costs.triple_dow else 1
        if k > j and t_flat is not None and ns[k] >= t_flat:
            return out(k, M["ex_o"][k], "flat")
        if k > j and ex.friday_flat_at is not None and dow[k] == 4 and mod[k] >= ex.friday_flat_at:
            return out(k, M["ex_o"][k], "friday_flat")
        if k > j and ex.max_hold_min is not None and ns[k] - ns[j] >= ex.max_hold_min * MIN:
            return out(k, M["ex_o"][k], "max_hold")
        if k > j and k >= k_exit:
            return out(k, M["ex_o"][k], "signal_exit")
        if k == k_time and (M["ex_o"][k] - e) < ex.time_stop[1] * R:
            return out(k, M["ex_o"][k], "time_stop")
        # 1) the stop first
        in_shield = shield is not None and shield[0] <= mod[k] <= shield[1]
        hit = (M["mid_l"][k] <= stop) if in_shield else (M["ex_l"][k] <= stop)
        if hit:
            if k == j:
                px = stop - slip(k)
            elif M["ex_o"][k] <= stop:
                px = M["ex_o"][k]                                   # gapped through: fills at the open
            else:
                px = stop - slip(k)
            why = "stop" if stop == st0 else f"{mover}_stop"
            return out(k, px, why)
        hi = M["ex_h"][k]
        moved = False
        if k > j:
            # 2) partials, then the full target
            for i, (r, f, nsr) in enumerate(parts):
                lvl = e + r * R
                if not done_parts[i] and hi >= lvl:
                    px = max(lvl, M["ex_o"][k])
                    take = min(f, frac)
                    banked += take * (px - e)
                    frac -= take
                    done_parts[i] = True
                    events.append({"k": int(k), "kind": "partial", "px": float(side * px), "r": r, "frac": take})
                    if nsr is not None and e + nsr * R > stop:
                        stop, moved, mover = e + nsr * R, True, "partial"
            if frac <= 1e-12:
                return out(k, e, "partials_done")
            if hi >= tgt:
                return out(k, max(tgt, M["ex_o"][k]), "target")
        best = max(best, (hi - e) / R)
        worst = min(worst, (M["ex_l"][k] - e) / R)
        # 3) break-even move
        if ex.be_at_r is not None and not be_done and k > j and hi >= e + ex.be_at_r * R:
            be_done = True
            if e + ex.be_lock_r * R > stop:
                stop, moved, mover = e + ex.be_lock_r * R, True, "be"
                events.append({"k": int(k), "kind": "stop_moved", "px": float(side * stop)})
        # 4) trailing
        if trail is not None and best >= ex.trail_after_r:
            if not close_ok and trail.kind != "gap_r":
                # activation on a candle CLOSE ≥ after_close_r (checked on the minute that completes the candle)
                if trail.i + 1 < len(trail.end) and ns[k] + MIN >= trail.end[trail.i + 1]:
                    b = m.bars(ex.trail["tf"])
                    c_close = side * float(b["c"].iloc[trail.i + 1])
                    if c_close >= e + float(close_after) * R:
                        close_ok = True
                        lock = (ex.trail or {}).get("lock_r")
                        if lock is not None and e + float(lock) * R > stop:
                            stop, moved, mover = e + float(lock) * R, True, "trail"
            cand = trail.update(int(ns[k]), M["ex_c"][k], best, e, R, stop, close_ok)
            if cand is not None and cand > stop:
                stop, moved, mover = cand, True, "trail"
                events.append({"k": int(k), "kind": "stop_moved", "px": float(side * stop)})
        # 5) the strategy's own stop adjustment
        if adjust is not None:
            ns_ = adjust(k)
            if ns_ is not None and side * ns_ > stop and side * ns_ < M["ex_c"][k]:
                stop, moved, mover = side * ns_, True, "adjust"
                events.append({"k": int(k), "kind": "stop_moved", "px": float(ns_)})
        if moved and costs.same_bar_check and M["ex_l"][k] <= stop:
            return out(k, stop - slip(k), "stop_same_bar")
        k += 1
    k = n - 1
    return out(k, M["ex_c"][k], "end")


def _r(pts: float, R: float, fin: float, spread: float, cad: bool) -> tuple[float, float]:
    def conv(x):
        return (x * 0.99 if x >= 0 else x * 1.01) if cad else x
    return conv((pts - fin) / R), conv((pts - fin - spread - fin) / R)


def simulate(strat: Strategy, m: Market, signals: list[Signal] | None = None, controls: bool = True,
             progress=None) -> dict:
    """Run one strategy on one Market. Returns {"trades": [...], "coin": [...], "funnel": {...}}."""
    costs, n = costs_for(strat.costs, m.symbol), len(m)
    sigs = sorted(strat.signals(m) if signals is None else signals, key=lambda s: s.t)
    blocked = news_mask(m, *strat.news_block, ten_am=strat.news_10am) if strat.news_block else \
        (news_mask(m, 0, 0, ten_am=True) if strat.news_10am else np.zeros(n, bool))
    MS = sides(m)
    f = {"signals": len(sigs), "not busy": 0, "filled": 0, "in window": 0, "no news": 0, "under daily cap": 0,
         "risk ok": 0, "taken": 0}
    trades, coin = [], []
    busy, per_day = -1, {}
    adjust_defined = type(strat).adjust is not Strategy.adjust
    for i_s, s in enumerate(sigs):
        if progress is not None and i_s % 50 == 0:
            progress(i_s, len(sigs))
        side = int(s.side)
        M = MS[side]
        j0 = int(np.searchsorted(m.ns, s.t))
        if j0 >= n or (strat.one_at_a_time and j0 <= busy):
            continue
        f["not busy"] += 1
        st_m = side * s.stop
        # fill
        if s.entry == "market":
            if m.ns[j0] - s.t > (s.expire_min or 5) * MIN:
                continue
            j, e = j0, float(M["in_o"][j0])
        else:
            pm = side * float(s.price)
            cm = None if s.cancel is None else s.cancel
            j = e = None
            k_end = int(np.searchsorted(m.ns, s.t + max(s.expire_min, 1) * MIN))
            for k in range(j0, min(k_end, n)):
                if k > j0 and m.ns[k] - m.ns[k - 1] > costs.gap_exit_min * MIN:
                    break
                if cm is not None and m.l[k] <= cm <= m.h[k]:
                    break
                if M["mid_l"][k] <= st_m:
                    break
                if s.entry == "limit" and M["in_l"][k] <= pm:
                    j, e = k, min(pm, float(M["in_o"][k]))
                    break
                if s.entry == "stop" and M["in_h"][k] >= pm:
                    j, e = k, max(pm, float(M["in_o"][k]))
                    break
            if j is None or (strat.one_at_a_time and j <= busy):
                continue
        f["filled"] += 1
        if strat.entry_windows and not any(a <= m.mod[j] < b for a, b in strat.entry_windows):
            continue
        f["in window"] += 1
        if blocked[j]:
            continue
        f["no news"] += 1
        sd = int(m.sess[j])
        if strat.max_per_day is not None and per_day.get(sd, 0) >= strat.max_per_day:
            continue
        f["under daily cap"] += 1
        R = e - st_m
        spread = float(m.spread[j])
        if R <= 0 or (s.risk_min is not None and R < s.risk_min) or (s.risk_max is not None and R > s.risk_max) \
                or (costs.max_spread_frac is not None and spread > costs.max_spread_frac * R):
            continue
        f["risk ok"] += 1
        ex = strat.exits_for(s)
        tgt_m = None if s.target is None else side * float(s.target)
        if tgt_m is not None and tgt_m <= e:
            continue
        adj = (lambda k, s=s, side=side: strat.adjust({"side": side, "entry": side * e, "stop0": s.stop,
                                                       "signal": s}, m, k)) if adjust_defined else None
        o = manage(m, M, side, j, e, st_m, ex, costs, s.t, tgt_m, adj, s.exit_t)
        fin = o["rollovers"] * costs.financing_bps / 1e4 * abs(e)
        r1, r2 = _r(o["pts"], R, fin, spread, costs.cad)
        trades.append({
            "entry_time": m.idx[j], "exit_time": m.idx[o["jx"]], "side": side, "entry": side * e, "stop": s.stop,
            "target": s.target if s.target is not None else (side * (e + ex.target_r * R) if ex.target_r else None),
            "exit": side * o["exit_px"], "stop_final": side * o["stop_final"], "spread": spread, "risk": R, "atr": R, "points": o["pts"] - fin, "R": r1, "R_2x": r2,
            "cost_R": (spread + fin) / R, "fin_R": fin / R, "exit_reason": o["why"],
            "hold_min": (m.ns[o["jx"]] - m.ns[j]) / 60e9, "overnight": o["rollovers"] > 0,
            "rollovers": o["rollovers"], "mfe_r": o["mfe_r"], "mae_r": o["mae_r"], "tag": s.tag, "draw": s.draw,
            "events": [{**ev, "ts": m.idx[ev["k"]].isoformat()} for ev in o["events"]],
            "signal_time": pd.Timestamp(s.t, tz="UTC"), "j": j, "jx": o["jx"]})
        f["taken"] += 1
        busy = o["jx"]
        per_day[sd] = per_day.get(sd, 0) + 1
        if controls:
            dist = None if tgt_m is None else tgt_m - e
            rr, rr2 = [], []
            for cs in (1, -1):
                C = MS[cs]
                ce = float(C["in_o"][j])
                co = manage(m, C, cs, j, ce, ce - R, ex, costs, s.t, None if dist is None else ce + dist,
                            exit_ns=s.exit_t)
                cfin = co["rollovers"] * costs.financing_bps / 1e4 * abs(ce)
                a, b = _r(co["pts"], R, cfin, spread, costs.cad)
                rr.append(a)
                rr2.append(b)
            coin.append({"entry_time": m.idx[j], "exit_time": m.idx[o["jx"]], "side": 0, "R": float(np.mean(rr)),
                         "R_2x": float(np.mean(rr2)), "cost_R": spread / R, "hold_min": trades[-1]["hold_min"],
                         "overnight": False, "points": 0.0, "atr": R, "exit_reason": "exact_coin"})
    return {"trades": trades, "coin": coin, "funnel": f}


def lookahead_audit(strat: Strategy, m: Market, sigs: list[Signal], n_check: int = 10, warm_days: int = 90) -> dict:
    """Re-run the strategy on data that ENDS at each sampled signal's time; a signal that disappears or changes side
    there used information from after its own time."""
    if not sigs:
        return {"checked": 0, "failed": 0, "examples": []}
    sigs = sorted(sigs, key=lambda s: s.t)
    start = m.ns[0] + warm_days * 1440 * MIN
    pool = [s for s in sigs if s.t > start]
    pick = [pool[i] for i in np.linspace(0, len(pool) - 1, min(n_check, len(pool))).astype(int)] if pool else []
    bad = []
    for s in pick:
        i1 = int(np.searchsorted(m.ns, s.t))
        i0 = int(np.searchsorted(m.ns, s.t - warm_days * 1440 * MIN))
        sub = m.slice(i0, i1)
        again = [x for x in strat.signals(sub) if x.t == s.t and x.side == s.side]
        if not again:
            bad.append(pd.Timestamp(s.t, tz="UTC").tz_convert(NY).isoformat())
    return {"checked": len(pick), "failed": len(bad), "examples": bad[:5]}
