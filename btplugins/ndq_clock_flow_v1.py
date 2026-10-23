"""Exploratory hypothesis, not a validated strategy. One frozen NDQ candidate.

At 10:30 NY, follow the mean of the previous 20 complete 10:30-11:00
midpoint returns. Stop = their median fractional range times current price.
Exit at 11:00, with no profit target or discretionary management.
The previous_half_hour variant changes only the predictor to 10:00-10:30.
"""
from collections import deque

import numpy as np

from fxagents.bt import Costs, Exits, Signal, Strategy

MIN = 60_000_000_000


def _window(m, a, b, start, length):
    """Only accept every expected minute; never fill holes by resampling."""
    mods = m.mod[a:b]
    lo = a + int(np.searchsorted(mods, start))
    hi = lo + length
    if hi > b or not np.array_equal(m.mod[lo:hi], np.arange(start, start + length)):
        return None
    if length > 1 and not np.all(np.diff(m.ns[lo:hi]) == MIN):
        return None
    values = np.concatenate((m.o[lo:hi], m.h[lo:hi], m.l[lo:hi], m.c[lo:hi]))
    if not np.all(np.isfinite(values)) or np.any(values <= 0):
        return None
    opening = float(m.o[lo])
    ret = float(m.c[hi - 1] / opening - 1.0)
    span = float((np.max(m.h[lo:hi]) - np.min(m.l[lo:hi])) / opening)
    return ret, span, int(m.ns[hi - 1] + MIN)


class NdqClockFlowV1(Strategy):
    name = "ndq_clock_flow_v1"
    symbol = "NDQ"
    description = "Prior-day same-clock return persistence; 10:30-11:00 NY, NDQ only."
    params = {
        "lookback_sessions": 20,
        "history_days": 45,
        "warmup_days": 60,
        "entry_min": 630,
        "hold_min": 30,
        "control_shift_min": -30,
        "use_previous_slot": False,
        "stop_range": 1.0,
        "risk_min_ratio": 0.9,
        "risk_max_ratio": 1.1,
        "max_spread_frac": 0.04,
        "expire_min": 0.5,
        "max_per_day": 1,
        "target_r": None,
    }
    one_at_a_time = True
    news_block = None  # The supplied 08:30 / 14:00 releases cannot overlap this fill.
    variants = {"previous_half_hour": {"use_previous_slot": True}}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        p = self.params
        self.warmup_days = int(p["warmup_days"])
        if not 0 < p["history_days"] < self.warmup_days:
            raise ValueError("history_days must be positive and below warmup_days")
        self.entry_windows = [(p["entry_min"], p["entry_min"] + 1)]
        self.max_per_day = p["max_per_day"]
        self.exits = Exits(target_r=p["target_r"], max_hold_min=p["hold_min"],
                           flat_at=p["entry_min"] + p["hold_min"])
        self.costs = Costs(max_spread_frac=p["max_spread_frac"])

    def signals(self, m):
        if m.symbol != self.symbol:
            raise ValueError("This registration is NDQ only; another symbol is a new proposal")
        if not len(m):
            return []
        p, out, history = self.params, [], deque()
        n, entry, hold = int(p["lookback_sessions"]), int(p["entry_min"]), int(p["hold_min"])
        starts = np.r_[0, np.flatnonzero(np.diff(m.day)) + 1]
        ends = np.r_[starts[1:], len(m)]
        for a, b in zip(starts, ends):
            if m.dow[a] >= 5:
                continue
            j = int(a + np.searchsorted(m.mod[a:b], entry - 1))
            if j < b and m.mod[j] == entry - 1:
                t = int(m.ns[j] + MIN)
                cutoff = t - int(p["history_days"] * 1440 * MIN)
                while history and history[0][0] < cutoff:
                    history.popleft()
                if len(history) >= n:
                    prior = list(history)[-n:]
                    column = 2 if p["use_previous_slot"] else 1
                    forecast = float(np.mean([row[column] for row in prior]))
                    ref = float(m.c[j])
                    risk = ref * p["stop_range"] * float(np.median([row[3] for row in prior]))
                    if np.isfinite(ref + risk + forecast) and ref > 0 and risk > 0 and forecast != 0:
                        side = 1 if forecast > 0 else -1
                        stop = ref - side * risk
                        if stop > 0:
                            out.append(Signal(
                                t=t, side=side, stop=float(stop),
                                expire_min=p["expire_min"],
                                risk_min=float(p["risk_min_ratio"] * risk),
                                risk_max=float(p["risk_max_ratio"] * risk),
                                tag="previous_half_hour" if p["use_previous_slot"] else "same_clock",
                                info={"forecast": forecast, "history_end": prior[-1][0], "sessions": n},
                            ))
            # Today's returns become usable only for later days. Missing future
            # bars here cannot alter the signal already emitted for this day.
            same = _window(m, a, b, entry, hold)
            previous = _window(m, a, b, entry + p["control_shift_min"], hold)
            if same is not None and previous is not None and same[1] > 0:
                history.append((same[2], same[0], previous[0], same[1]))
        return out
