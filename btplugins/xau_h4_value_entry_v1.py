"""xau_h4_value_entry_v1 — frozen round-two research hypothesis; NOT validated.
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


class XauH4ValueEntryV1(Strategy):
    name = "xau_h4_value_entry_v1"
    symbol = "XAUUSD"
    description = "H4 counter-move across EMA20 in the direction of the EMA50 slope; 48h maximum."
    params = dict(fast=20, fast_seed=100, slow=50, slow_seed=250, slope_bars=6,
                  atr_n=14, atr_seed=140, stop_atr=1.5, hold_hours=48,
                  entry_minutes=[60, 300, 540, 780, 1260], friday_exit_min=780,
                  use_regime=True, history_days=90, warmup_days=140,
                  max_spread_frac=0.03, risk_low=0.9, risk_high=1.1,
                  expiry_min=0.5, gap_exit_min=7200, max_per_day=1)
    news_block = None
    one_at_a_time = True
    variants = {"no_slow_regime": {"use_regime": False}}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        p = self.params
        self.warmup_days = p["warmup_days"]
        self.max_per_day = p["max_per_day"]
        self.entry_windows = [(x, x + 1) for x in p["entry_minutes"]]
        self.exits = Exits(hold_overnight=True, max_hold_min=p["hold_hours"] * 60,
                           friday_flat_at=p["friday_exit_min"])
        self.costs = Costs(gap_exit_min=p["gap_exit_min"], max_spread_frac=p["max_spread_frac"])

    def signals(self, m):
        _check_market(m, self.symbol)
        if not len(m):
            return []
        p, out, b = self.params, [], _bars(m, "4h")
        for i in range(1, len(b)):
            t = int(b.end.iloc[i])
            local = pd.Timestamp(t, tz="UTC").tz_convert(NY)
            minute = local.hour * 60 + local.minute
            if local.dayofweek >= 5 or minute not in p["entry_minutes"]:
                continue
            if local.dayofweek == 4 and minute >= p["friday_exit_min"]:
                continue
            # The decision bar must have its final minute, not a stale last quote.
            if _complete(m, t - MIN, t) is None:
                continue
            fast = _ema(b, i, p["fast"], p["fast_seed"], t, p["history_days"])
            previous = _ema(b, i - 1, p["fast"], p["fast_seed"], t, p["history_days"])
            slow = _ema(b, i, p["slow"], p["slow_seed"], t, p["history_days"])
            old_slow = _ema(b, i - p["slope_bars"], p["slow"], p["slow_seed"], t, p["history_days"])
            if not np.isfinite(fast + previous + slow + old_slow):
                continue
            ref, prev = float(b.c.iloc[i]), float(b.c.iloc[i - 1])
            # Condition 1: first close across EMA20 AGAINST the entry direction.
            if prev >= previous and ref < fast:
                side = 1
            elif prev <= previous and ref > fast:
                side = -1
            else:
                continue
            # Condition 2: the slower EMA's one-day slope supports that direction.
            if p["use_regime"] and side * (slow - old_slow) <= 0:
                continue
            risk = p["stop_atr"] * _atr(b, i, p["atr_n"], p["atr_seed"], t, p["history_days"])
            if not np.isfinite(risk) or risk <= 0 or ref - side * risk <= 0:
                continue
            out.append(Signal(t=t, side=side, stop=float(ref - side * risk),
                              expire_min=p["expiry_min"],
                              risk_min=p["risk_low"] * risk, risk_max=p["risk_high"] * risk,
                              tag="h4_value_entry"))
        return out
