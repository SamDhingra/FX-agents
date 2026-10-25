"""xau_h1_adr_exhaustion_v1 — frozen round-two research hypothesis; NOT validated.
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


class XauH1AdrExhaustionV1(Strategy):
    name = "xau_h1_adr_exhaustion_v1"
    symbol = "XAUUSD"
    description = "13:00 H1 fade at an outer quarter after one prior ADR of daily travel."
    params = dict(entry_min=780, hold_hours=3, friday_exit_min=960,
                  daily_close_min=1020, adr_n=20, adr_used=1.0, outer_fraction=0.25,
                  atr_n=14, atr_seed=140, stop_atr=1.5, use_adr=True, fade=True,
                  history_days=60, warmup_days=90, max_spread_frac=0.04,
                  risk_low=0.9, risk_high=1.1, expiry_min=0.5,
                  gap_exit_min=7200, max_per_day=1)
    news_block = None
    one_at_a_time = True
    variants = {"no_adr_gate": {"use_adr": False}, "continue_extension": {"fade": False}}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        p = self.params
        self.warmup_days = p["warmup_days"]
        self.max_per_day = p["max_per_day"]
        self.entry_windows = [(p["entry_min"], p["entry_min"] + 1)]
        self.exits = Exits(hold_overnight=True, max_hold_min=p["hold_hours"] * 60,
                           friday_flat_at=p["friday_exit_min"])
        self.costs = Costs(gap_exit_min=p["gap_exit_min"], max_spread_frac=p["max_spread_frac"])

    def signals(self, m):
        _check_market(m, self.symbol)
        if not len(m):
            return []
        p, out = self.params, []
        h, daily = _bars(m, "1h"), _bars(m, "1d")
        daily = daily[pd.to_datetime(daily.end, utc=True).dt.tz_convert(NY).dt.dayofweek < 5].reset_index(drop=True)
        dend = daily.end.to_numpy()
        for i in range(len(h)):
            t = int(h.end.iloc[i])
            local = pd.Timestamp(t, tz="UTC").tz_convert(NY)
            if local.dayofweek >= 5 or local.hour * 60 + local.minute != p["entry_min"]:
                continue
            if _complete(m, t - 60 * MIN, t) is None:
                continue
            session_start = _wall(t, p["daily_close_min"], -1)
            dk = int(np.searchsorted(dend, session_start, side="right")) - 1
            days = _tail(daily, dk, p["adr_n"], t, p["history_days"])
            if days is None:
                continue
            adr = float(np.mean(days.h.to_numpy() - days.l.to_numpy()))
            # Only already completed minutes of THIS 17:00-to-17:00 session.
            a, b = np.searchsorted(m.ns, [session_start, t])
            if b <= a:
                continue
            high, low, ref = float(np.max(m.h[a:b])), float(np.min(m.l[a:b])), float(h.c.iloc[i])
            width = high - low
            if not np.isfinite(adr + width) or adr <= 0 or width <= 0:
                continue
            # Condition 1: range used, normalized by prior COMPLETE daily ranges.
            if p["use_adr"] and width < p["adr_used"] * adr:
                continue
            # Condition 2: close at the outer quarter; no wick or reversal pattern.
            where = (ref - low) / width
            if where >= 1.0 - p["outer_fraction"]:
                side = -1
            elif where <= p["outer_fraction"]:
                side = 1
            else:
                continue
            if not p["fade"]:
                side = -side
            atr = _atr(h, i, p["atr_n"], p["atr_seed"], t, p["history_days"])
            risk = p["stop_atr"] * atr
            if not np.isfinite(risk) or risk <= 0 or ref - side * risk <= 0:
                continue
            out.append(Signal(t=t, side=side, stop=float(ref - side * risk),
                              expire_min=p["expiry_min"],
                              risk_min=p["risk_low"] * risk, risk_max=p["risk_high"] * risk,
                              tag="adr_exhaustion", info={"adr_known_at": int(days.end.iloc[-1])}))
        return out
