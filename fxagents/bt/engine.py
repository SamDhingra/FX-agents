"""The backtest engine: one execution model for every strategy.

Fills: market entries at the next minute's open on the ask (longs) / bid (shorts); limit and stop entries fill when the
ask/bid actually trades through the price (at the open if it gaps through). Exits on the other side. Every minute:
data gap → out at the last price; financing at each 17:00 NY crossing; flat time / Friday flat / max hold / time
stop; the stop FIRST (on the mid during the 16:55–18:05 spread spike), with slippage on intrabar stop fills; then
partials, the full target, the break-even move and trailing — and, if any of those moved the stop, a same-minute
check that the low didn't already take it. Results in R after spread, financing and (optionally) the 1% CAD
conversion; "2×" pays every transaction cost once more — both half-spreads (entry and exit minute) and all slippage —
and the financing once more (Oct 25 2026; it used to add only the entry spread). Control: an exact coin flip — a long AND a short at the
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
           target_m: float | None = None, adjust=None, exit_ns: int | None = None, at_open: bool = True) -> dict:
    """One trade from fill minute j, in mirrored prices (e = entry, st0 = initial stop). Returns the outcome.

    Order within a minute (Oct 22 2026 correction, from the PS-1 execution review):
      · the minute's OPEN is the first known price: a later minute that opens through the stop fills there; one that
        opens beyond a partial level / the target fills those resting orders there, before anything intrabar;
      · then intrabar: the stop first (the order of the high and the low inside a minute is unknown), then partials
        and the target;
      · the fill minute: for a fill at the minute's open (`at_open`: market entries and the controls) the whole minute
        is after the entry, so its high can reach partials / the target (stop still first). A limit / stop entry
        filled inside the minute keeps the cautious rule — its high and low may be from before the fill — so only
        the stop is checked there.
    MFE / MAE include the prices actually exited at (partials, target, stop)."""
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
    xcost = 0.0                                                     # exit costs paid vs the mid (half-spread + slip)
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

    def out(k, px, why, sl=0.0):
        nonlocal xcost
        xcost += frac * (0.5 * float(m.spread[k]) + sl)
        pts = banked + frac * (px - e)
        b_, w_ = max(best, (px - e) / R), min(worst, (px - e) / R)
        return {"jx": int(k), "pts": float(pts), "why": why, "rollovers": rollovers, "mfe_r": float(b_),
                "mae_r": float(w_), "events": events, "exit_px": float(px), "stop_final": float(stop), "xcost": float(xcost)}

    def msl(k):
        return costs.market_slip_frac * float(m.spread[k])

    def mkt(k):                                                     # a market exit at minute k's open
        return M["ex_o"][k] - msl(k)

    def take_part(k, i, px):
        nonlocal banked, frac, stop, moved, mover, best, xcost
        r, f, nsr = parts[i]
        take = min(f, frac)
        xcost += take * 0.5 * float(m.spread[k])                    # a resting limit: half the spread, no slip
        banked += take * (px - e)
        frac -= take
        done_parts[i] = True
        best = max(best, (px - e) / R)
        if take > 0:
            events.append({"k": int(k), "kind": "partial", "px": float(side * px), "r": r, "frac": take})
        if nsr is not None and e + nsr * R > stop:
            stop, moved, mover = e + nsr * R, True, "partial" if take > 0 else "step"
            if take <= 0:
                events.append({"k": int(k), "kind": "stop_moved", "px": float(side * stop)})

    def slip(k):
        return costs.stop_slip_frac * float(m.spread[k])

    moved = False
    k = j
    n = len(ns)
    while k < n:
        if k > j and ns[k] - ns[k - 1] > gap * MIN:
            return out(k - 1, M["ex_c"][k - 1], "data_gap")
        if k > j and (day[k] != day[k - 1] or (mod[k - 1] < 1020 <= mod[k])):
            rollovers += _rollovers(int(day[k - 1]), int(mod[k - 1]), int(day[k]), int(mod[k]), costs.triple_dow)
        if k > j and t_flat is not None and ns[k] >= t_flat:
            return out(k, mkt(k), "flat", msl(k))
        if k > j and ex.friday_flat_at is not None and dow[k] == 4 and mod[k] >= ex.friday_flat_at:
            return out(k, mkt(k), "friday_flat", msl(k))
        if k > j and ex.max_hold_min is not None and ns[k] - ns[j] >= ex.max_hold_min * MIN:
            return out(k, mkt(k), "max_hold", msl(k))
        if k > j and k >= k_exit:
            return out(k, mkt(k), "signal_exit", msl(k))
        if k == k_time and (M["ex_o"][k] - e) < ex.time_stop[1] * R:
            return out(k, mkt(k), "time_stop", msl(k))
        moved = False
        o_k = M["ex_o"][k]
        if k > j and o_k > stop:
            # 0) the open is known first: resting partials / the target it already traded through fill at the open
            for i, (r, f, nsr) in enumerate(parts):
                if not done_parts[i] and o_k >= e + r * R:
                    take_part(k, i, o_k)
            if frac <= 1e-12:
                return out(k, e, "partials_done")
            if o_k >= tgt:
                return out(k, o_k, "target")
        # 1) the stop (intrabar it comes first)
        in_shield = shield is not None and shield[0] <= mod[k] <= shield[1]
        hit = (M["mid_l"][k] <= stop) if in_shield else (M["ex_l"][k] <= stop)
        if hit:
            if k > j and M["ex_o"][k] <= stop:
                px, sl = M["ex_o"][k], 0.0                          # gapped through: fills at the open
            else:
                px, sl = stop - slip(k), slip(k)
            why = "stop" if stop == st0 else f"{mover}_stop"
            return out(k, px, why, sl)
        hi = M["ex_h"][k]
        if k > j or at_open:
            # 2) partials, then the full target
            for i, (r, f, nsr) in enumerate(parts):
                lvl = e + r * R
                if not done_parts[i] and hi >= lvl:
                    take_part(k, i, max(lvl, o_k) if k > j else lvl)
            if frac <= 1e-12:
                return out(k, e, "partials_done")
            if hi >= tgt:
                return out(k, max(tgt, o_k) if k > j else tgt, "target")
        best = max(best, (hi - e) / R)
        worst = min(worst, (M["ex_l"][k] - e) / R)
        # 3) break-even move
        if ex.be_at_r is not None and not be_done and (k > j or at_open) and hi >= e + ex.be_at_r * R:
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
            return out(k, stop - slip(k), "stop_same_bar", slip(k))
        k += 1
    k = n - 1
    return out(k, M["ex_c"][k], "end")


def _rollovers(d0: int, m0: int, d1: int, m1: int, triple_dow: int | None) -> int:
    """Financing charges for the 17:00 NY rollovers crossed between minute (d0, m0) and minute (d1, m1) (NY day
    numbers / minutes of day). Every weekday rollover counts, so a holiday gap of several days pays each of them
    (Oct 25 2026; it used to count one). With a triple day (Wednesday, the FX convention that books the weekend)
    Saturday and Sunday aren't charged and Wednesday is 3×; without one (crypto) every day counts."""
    n = 0
    for d in range(d0, d1 + 1):
        if (d == d0 and m0 >= 1020) or (d == d1 and m1 < 1020):
            continue
        wd = (d + 3) % 7                                              # NY day number 0 = 1970-01-01, a Thursday
        if triple_dow is None:
            n += 1
        elif wd < 5:
            n += 3 if wd == triple_dow else 1
    return n


def _entry_cost(spread: float, market: bool, costs: Costs) -> float:
    """What an entry pays vs the mid: half the spread, plus slippage for a market order."""
    return spread * (0.5 + (costs.market_slip_frac if market else 0.0))


def _r(pts: float, R: float, fin: float, tc: float, cad: bool) -> tuple[float, float]:
    """R after costs, and at 2× costs: `tc` = every transaction cost the trade paid vs the mid (both half-spreads and
    all slippage), charged once more, and the financing once more."""
    def conv(x):
        return (x * 0.99 if x >= 0 else x * 1.01) if cad else x
    return conv((pts - fin) / R), conv((pts - fin - tc - fin) / R)


def simulate(strat: Strategy, m: Market, signals: list[Signal] | None = None, controls: bool = True,
             progress=None, n_draw: int = 10) -> dict:
    """Run one strategy on one Market. Returns {"trades": [...], "coin": [...], "funnel": {...}}."""
    costs, n = costs_for(strat.costs, m.symbol), len(m)
    sigs = sorted(strat.signals(m) if signals is None else signals, key=lambda s: s.t)
    sigs_by_t = {(int(x.t), int(x.side)): x for x in sigs}
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
            j, e = j0, float(M["in_o"][j0]) + costs.market_slip_frac * float(m.spread[j0])
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
        tstate = {"side": side, "entry": side * e, "stop0": s.stop, "risk": R, "j": j, "signal": s}   # kept per trade
        adj = (lambda k, d=tstate: strat.adjust(d, m, k)) if adjust_defined else None
        at_open = s.entry == "market" or e == float(M["in_o"][j])         # filled at the minute's open
        o = manage(m, M, side, j, e, st_m, ex, costs, s.t, tgt_m, adj, s.exit_t, at_open=at_open)
        fin = o["rollovers"] * costs.financing_bps / 1e4 * abs(e)
        tc = _entry_cost(spread, s.entry == "market", costs) + o["xcost"]
        r1, r2 = _r(o["pts"], R, fin, tc, costs.cad)
        trades.append({
            "entry_time": m.idx[j], "exit_time": m.idx[o["jx"]], "side": side, "entry": side * e, "stop": s.stop,
            "target": s.target if s.target is not None else (side * (e + ex.target_r * R) if ex.target_r else None),
            "exit": side * o["exit_px"], "stop_final": side * o["stop_final"], "spread": spread, "risk": R, "atr": R, "points": o["pts"] - fin, "R": r1, "R_2x": r2,
            "cost_R": (tc + fin) / R, "tc_R": tc / R, "fin_R": fin / R, "exit_reason": o["why"],
            "hold_min": (m.ns[o["jx"]] - m.ns[j]) / 60e9, "overnight": o["rollovers"] > 0,
            "rollovers": o["rollovers"], "mfe_r": o["mfe_r"], "mae_r": o["mae_r"], "tag": s.tag, "draw": s.draw,
            "events": [{**ev, "ts": m.idx[ev["k"]].isoformat()} for ev in o["events"]],
            "signal_time": pd.Timestamp(s.t, tz="UTC"), "j": j, "jx": o["jx"]})
        f["taken"] += 1
        busy = o["jx"]
        if strat.cooldown_min:                       # no new fill until `cooldown_min` minutes after this exit
            busy = max(busy, int(np.searchsorted(m.ns, m.ns[o["jx"]] + strat.cooldown_min * MIN)) - 1)
        per_day[sd] = per_day.get(sd, 0) + 1
        if controls:
            dist = None if tgt_m is None else tgt_m - e
            rr, rr2 = [], []
            for cs in (1, -1):
                C = MS[cs]
                ce = float(C["in_o"][j]) + costs.market_slip_frac * spread
                co = manage(m, C, cs, j, ce, ce - R, ex, costs, s.t, None if dist is None else ce + dist,
                            exit_ns=s.exit_t)
                cfin = co["rollovers"] * costs.financing_bps / 1e4 * abs(ce)
                a, b = _r(co["pts"], R, cfin, _entry_cost(spread, True, costs) + co["xcost"], costs.cad)
                rr.append(a)
                rr2.append(b)
            coin.append({"entry_time": m.idx[j], "exit_time": m.idx[o["jx"]], "side": 0, "R": float(np.mean(rr)),
                         "R_2x": float(np.mean(rr2)), "cost_R": spread / R, "hold_min": trades[-1]["hold_min"],
                         "overnight": False, "points": 0.0, "atr": R, "exit_reason": "exact_coin"})
    rand = random_timing(m, MS, trades, sigs_by_t, strat, costs, n_draw, blocked=blocked) if controls and n_draw else []
    return {"trades": trades, "coin": coin, "rand": rand, "funnel": f, "controls": bool(controls and n_draw)}


def twin_ok(m: Market, k: int, risk: float, ex: Exits, strat: Strategy, costs: Costs, blocked) -> bool:
    """Could the strategy itself have entered at minute k? The random-timing twins obey the same entry rules as real
    fills (Oct 25 2026): entry window, news blackout, the spread cap, and no entry once the Friday-flat time has passed
    (that twin would be closed a minute later). Without this the twins landed on minutes the rule would have skipped
    (wide spreads, releases), which made them worse and the rule look better."""
    if risk <= 0:
        return False
    if strat.entry_windows and not any(a <= m.mod[k] < b for a, b in strat.entry_windows):
        return False
    if blocked is not None and blocked[k]:
        return False
    if costs.max_spread_frac is not None and float(m.spread[k]) > costs.max_spread_frac * risk:
        return False
    if ex.friday_flat_at is not None and m.dow[k] == 4 and m.mod[k] >= ex.friday_flat_at:
        return False
    return True


def random_timing(m: Market, MS: dict, trades: list[dict], sigs_by_t: dict, strat: Strategy, costs: Costs,
                  n_draw: int = 10, seed: int = 11, blocked=None) -> list[dict]:
    """The timing control: each real trade is repeated on `n_draw` randomly chosen OTHER days at the same NY time
    of day and on the same side, with the same stop distance as a share of price and the same exit rules (Oct 22 2026:
    no longer forced out at the real trade's realised holding time — that tied the control to the real outcome; only
    a strategy with its own signal exit keeps the real trade's planned exit delay). If the rule's entries can't beat these, its timing adds nothing beyond being long (or short) at that hour —
    e.g. a long-only rule in a rising market. Returns one row per real trade: the average of its random twins."""
    rng = np.random.default_rng(seed)
    starts = np.r_[0, np.flatnonzero(np.diff(m.day)) + 1]
    ends = np.r_[starts[1:], len(m)]
    out = []
    for t in trades:
        j, jx, side = t["j"], t["jx"], t["side"]
        s = sigs_by_t[(t["signal_time"].value, side)]
        M = MS[side]
        e, R = side * t["entry"], t["risk"]
        frac = R / abs(e)
        tgt = None if s.target is None else (side * s.target - e) / abs(e)
        ex = strat.exits_for(s)
        mod_j, day_j = int(m.mod[j]), int(m.day[j])
        rr, rr2 = [], []
        for d in rng.permutation(len(starts)):
            if len(rr) >= n_draw:
                break
            a, b = starts[d], ends[d]
            if m.day[a] == day_j:
                continue
            k = a + int(np.searchsorted(m.mod[a:b], mod_j))
            if k >= b or m.mod[k] - mod_j > 5 or k + 1 >= len(m):
                continue
            ce = float(M["in_o"][k]) + costs.market_slip_frac * float(m.spread[k])
            cR = frac * abs(ce)
            if not twin_ok(m, k, cR, ex, strat, costs, blocked):
                continue
            co = manage(m, M, side, k, ce, ce - cR, ex, costs, int(m.ns[k]), None if tgt is None else ce + tgt * abs(ce),
                        exit_ns=None if s.exit_t is None else int(m.ns[k]) + int(s.exit_t - m.ns[j]))
            fin = co["rollovers"] * costs.financing_bps / 1e4 * abs(ce)
            r1, r2 = _r(co["pts"], cR, fin, _entry_cost(float(m.spread[k]), True, costs) + co["xcost"], costs.cad)
            rr.append(r1)
            rr2.append(r2)
        if rr:
            out.append({"entry_time": t["entry_time"], "exit_time": t["exit_time"], "side": side,
                        "R": float(np.mean(rr)), "R_2x": float(np.mean(rr2)), "edge": t["R"] - float(np.mean(rr)),
                        "cost_R": t["cost_R"], "hold_min": t["hold_min"], "overnight": t["overnight"],
                        "exit_reason": "random_timing", "n": len(rr)})
    return out


def _same(a: Signal, b: Signal, ref: float) -> str | None:
    """Why two signals for the same time and side differ (None if they match). Prices within 2% of the signal's
    stop distance count as equal — indicators warmed up on a shorter slice can differ in the last digits; 2% of the
    risk is far too small to be worth cheating for. Everything that changes how the trade runs is compared."""
    tol = max(0.02 * ref, 1e-9)
    for f in ("stop", "target", "price", "cancel", "risk_max", "risk_min"):
        x, y = getattr(a, f), getattr(b, f)
        if (x is None) != (y is None) or (x is not None and abs(float(x) - float(y)) > tol):
            return f
    if a.entry != b.entry:
        return "entry"
    if abs(float(a.expire_min or 0) - float(b.expire_min or 0)) > 1e-9:
        return "expire_min"
    if (a.exits or {}) != (b.exits or {}):
        return "exits"
    return None                          # exit_t is decided after the signal by design, so it isn't compared


AUDIT_WINDOW_MIN = 24 * 60               # signals compared in the day before each cut (both directions)


def lookahead_audit(strat: Strategy, m: Market, sigs: list[Signal], n_check: int = 10, warm_days: int = 90) -> dict:
    """Re-run the strategy on data that ENDS at a cut time and compare everything it signals in the day before the
    cut with the full run, both ways (Oct 25 2026):
      · a full-run signal that disappears or changes (side, stop, target, entry, price, risk limits, expiry,
        per-signal exits) on the cut data used information from after its own time;
      · a signal the cut data produces but the full run doesn't means the full run used the future to SKIP it — a
        filter like "only if the next hour goes my way". The old audit checked only the first direction, and a rule
        that cheated this way passed it 30 of 30 at +0.71R.
    Cuts: n_check signal times, plus n_check evenly spaced times that aren't signal times. Each re-run gets
    warm_days of history before the compared day (or the data from its start, the same history the full run had),
    so every compared signal had its full warm-up."""
    if not len(m):
        return {"checked": 0, "failed": 0, "examples": [], "cuts": 0}
    sigs = sorted(sigs, key=lambda s: s.t)
    W = AUDIT_WINDOW_MIN * MIN
    start = m.ns[0] + warm_days * 1440 * MIN
    pool = [s for s in sigs if s.t > start]
    cuts = [int(pool[i].t) for i in np.linspace(0, len(pool) - 1, min(n_check, len(pool))).astype(int)] if pool else []
    if m.ns[-1] > start and n_check:
        grid = np.linspace(start, int(m.ns[-1]), n_check + 2)[1:-1].astype(np.int64)
        cuts += [int(m.ns[min(int(np.searchsorted(m.ns, g)), len(m) - 1)]) for g in grid]
    cuts = sorted(set(cuts))
    by_key: dict = {}
    for s in sigs:
        by_key.setdefault((int(s.t), int(s.side)), []).append(s)
    bad, checked = [], 0
    for cut in cuts:
        i1 = int(np.searchsorted(m.ns, cut))
        i0 = int(np.searchsorted(m.ns, cut - W - warm_days * 1440 * MIN))
        sub = m.slice(i0, i1)
        lo = cut - W
        again = [x for x in strat.signals(sub) if lo < x.t <= cut]
        full = [x for x in sigs if lo < x.t <= cut]
        checked += len(full)
        ref_px = float(m.c[max(i1 - 1, 0)])
        when = pd.Timestamp(cut, tz="UTC").tz_convert(NY).isoformat()
        for s in full:
            twins = [x for x in again if x.t == s.t and x.side == s.side]
            sw = pd.Timestamp(s.t, tz="UTC").tz_convert(NY).isoformat()
            if not twins:
                bad.append(f"{sw} (disappears on data cut at {when})")
                continue
            ref = abs(ref_px - float(s.stop)) or abs(float(s.stop)) * 1e-3
            diffs = [_same(s, x, ref) for x in twins]
            if all(d is not None for d in diffs):
                bad.append(f"{sw} ({diffs[0]} changed)")
        for x in again:
            if (int(x.t), int(x.side)) not in by_key:
                xw = pd.Timestamp(x.t, tz="UTC").tz_convert(NY).isoformat()
                bad.append(f"{xw} (signalled on data cut at {when}, skipped by the full run)")
    return {"checked": checked, "failed": len(bad), "examples": bad[:5], "cuts": len(cuts)}
