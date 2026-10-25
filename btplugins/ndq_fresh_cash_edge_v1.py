"""ndq_fresh_cash_edge_v1 — frozen round-two research hypothesis; NOT validated.
Standalone plugin; helpers included so the plugin hash covers indicator definitions.
No historical backtest was run during preparation.
"""
import numpy as np
import pandas as pd
from fxagents.bt import Costs, Exits, Signal, Strategy

MIN = 60_000_000_000
NY = "America/New_York"


def _bars(m, tf):
    if not len(m):
        return m.bars(tf).iloc[:0]
    b = m.bars(tf)
    return b[(b.start >= m.ns[0]) & (b.end <= int(m.ns[-1]) + MIN)].reset_index(drop=True)


def _tail(b, k, count, t, days):
    if k < count - 1:
        return None
    w = b.iloc[k - count + 1:k + 1]
    if w.start.iloc[0] < t - days * 1440 * MIN or w.end.iloc[-1] > t:
        return None
    a = w[["o", "h", "l", "c"]].to_numpy(float)
    return w if np.isfinite(a).all() and (a > 0).all() else None


def _smooth(x, n, alpha):
    v = float(np.mean(x[:n]))
    for xj in x[n:]:
        v += alpha * (float(xj) - v)
    return v


def _ema(b, k, n, seed, t, days):
    w = _tail(b, k, seed, t, days)
    return np.nan if w is None else _smooth(w.c.to_numpy(), n, 2.0 / (n + 1))


def _atr(b, k, n, seed, t, days):
    w = _tail(b, k, seed + 1, t, days)
    if w is None:
        return np.nan
    h, l, c = (w[q].to_numpy(float) for q in ("h", "l", "c"))
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    return _smooth(tr, n, 1.0 / n)


def _rsi(b, k, n, seed, t, days):
    w = _tail(b, k, seed + 1, t, days)
    if w is None:
        return np.nan
    delta = np.diff(w.c.to_numpy(float))
    up = _smooth(np.maximum(delta, 0.0), n, 1.0 / n)
    down = _smooth(np.maximum(-delta, 0.0), n, 1.0 / n)
    return 50.0 if up + down == 0 else 100.0 * up / (up + down)


def _complete(m, start, end):
    a, b = np.searchsorted(m.ns, [int(start), int(end)])
    expected = (int(end) - int(start)) // MIN
    if b - a != expected or b == a:
        return None
    if m.ns[a] != start or m.ns[b - 1] + MIN != end or not np.all(np.diff(m.ns[a:b]) == MIN):
        return None
    return int(a), int(b)


def _wall(t, minute, shift_days=0):
    date = pd.Timestamp(int(t), tz="UTC").tz_convert(NY).tz_localize(None).normalize()
    return int((date + pd.Timedelta(days=shift_days, minutes=minute)).tz_localize(
        NY, ambiguous=True, nonexistent="shift_forward").value)


def _check_market(m, symbol):
    if m.symbol != symbol:
        raise ValueError(f"Frozen registration is {symbol} only; changing symbol is another candidate")
    if len(m) and (np.any(np.diff(m.ns) <= 0) or not np.all(m.ns % MIN == 0)):
        raise ValueError("Minute timestamps must be unique, increasing and minute-aligned")


class NdqFreshCashEdgeV1(Strategy):
    name = "ndq_fresh_cash_edge_v1"
    symbol = "NDQ"
    description = "First M15 contact with a fresh prior cash-session edge; market fade, neutral H1 RSI."
    params = dict(cash_start=570, cash_end=960, decision_min=570, decision_tf=15,
                  expiry_min=120, market_wait_min=0.5, flat_min=945, adr_n=20, stop_adr=0.25,
                  rsi_n=14, rsi_seed=140, rsi_low=40.0, rsi_high=60.0,
                  use_rsi=True, fresh_only=True, history_days=60, warmup_days=90,
                  max_spread_frac=0.04, risk_low=0.9, risk_high=1.1, max_per_day=1)
    news_block = None
    one_at_a_time = True
    variants = {"no_rsi_state": {"use_rsi": False}, "allow_used_edge": {"fresh_only": False}}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        p = self.params
        self.warmup_days = p["warmup_days"]
        self.max_per_day = p["max_per_day"]
        self.entry_windows = [(p["decision_min"] + p["decision_tf"],
                               p["decision_min"] + p["expiry_min"] + 1)]
        self.exits = Exits(flat_at=p["flat_min"])
        self.costs = Costs(max_spread_frac=p["max_spread_frac"])

    def signals(self, m):
        _check_market(m, self.symbol)
        if not len(m):
            return []
        p, out, records = self.params, [], []
        hourly = _bars(m, "1h")
        h_end = hourly.end.to_numpy()
        starts = np.r_[0, np.flatnonzero(np.diff(m.day)) + 1]
        ends = np.r_[starts[1:], len(m)]
        for a, z in zip(starts, ends):
            if m.dow[a] >= 5:
                continue
            t = _wall(m.ns[a], p["decision_min"])
            dwin = _complete(m, t - p["decision_tf"] * MIN, t)
            cutoff = t - p["history_days"] * 1440 * MIN
            records = [x for x in records if x[0] >= cutoff]
            good = [x for x in records if x[1] is not None]
            if dwin is not None and records and records[-1][1] is not None and len(good) >= p["adr_n"]:
                end_prior, high, low = records[-1]
                ref = float(m.c[dwin[1] - 1])
                # Condition 1: inside the prior range; choose its NEAREST edge.
                if low < ref < high and ref != (high + low) / 2:
                    side = 1 if ref < (high + low) / 2 else -1
                    level = low if side == 1 else high
                    left, right = np.searchsorted(m.ns, [end_prior, t])
                    # Condition 2: that edge has not traded since its formation.
                    fresh = left == right or (float(np.min(m.l[left:right])) > level if side == 1
                                              else float(np.max(m.h[left:right])) < level)
                    k = int(np.searchsorted(h_end, t, side="right")) - 1
                    rsi = _rsi(hourly, k, p["rsi_n"], p["rsi_seed"], t, p["history_days"])
                    # Condition 3: neutral H1 relative-strength state.
                    if (fresh or not p["fresh_only"]) and (not p["use_rsi"] or
                                                          p["rsi_low"] <= rsi <= p["rsi_high"]):
                        adr = float(np.mean([x[1] - x[2] for x in good[-p["adr_n"]:]]))
                        risk = p["stop_adr"] * adr
                        target = float((high + low) / 2)
                        for elapsed in range(p["decision_tf"], p["expiry_min"] + 1, p["decision_tf"]):
                            decision = t + elapsed * MIN
                            contact = _complete(m, decision - p["decision_tf"] * MIN, decision)
                            if contact is None:
                                break  # missing data makes the first-contact state unknowable
                            ca, cb = contact
                            touched = (float(np.min(m.l[ca:cb])) <= level if side == 1
                                       else float(np.max(m.h[ca:cb])) >= level)
                            if not touched:
                                continue
                            price = float(m.c[cb - 1])
                            stop = price - side * risk
                            if np.isfinite(risk) and risk > 0 and stop > 0 and side * (target - price) > 0:
                                out.append(Signal(t=decision, side=side, stop=float(stop), expire_min=p["market_wait_min"],
                                                  target=target, risk_min=p["risk_low"] * risk,
                                                  risk_max=p["risk_high"] * risk, tag="fresh_cash_edge",
                                                  info={"level_known_at": int(end_prior), "frozen_at": t}))
                            break  # first contact consumes the attempt, even if no trade is executable
            # Add today's cash range only AFTER today's decision. It can affect
            # later days only, even when the full input contains today's future.
            cs, ce = _wall(m.ns[a], p["cash_start"]), _wall(m.ns[a], p["cash_end"])
            if ce <= int(m.ns[-1]) + MIN:
                span = _complete(m, cs, ce)
                if span is None:
                    records.append((ce, None, None))
                else:
                    lo, hi = span
                    records.append((ce, float(np.max(m.h[lo:hi])), float(np.min(m.l[lo:hi]))))
        return out
