"""Data / structure parity regressions from the 2026-10-08 audit (docs/astra_audit_2026-10-08.md §2):
F07 causal pivots · F13 DST session grid · F14 cache identity · F23 hourly completeness · F26 drawdown."""
import numpy as np
import pandas as pd

from fxagents.indicators import known_pivots, pivots, resample_ohlc
from fxagents.sim import stats, synth_1m
from fxagents.strategies import BUILTIN

TZ = "America/New_York"


def _frame(highs, lows=None):
    h = np.asarray(highs, float)
    l = np.asarray(lows, float) if lows is not None else 90 + 0.1 * np.arange(len(h))   # rising lows: no L fractal
    idx = pd.date_range("2026-06-02 09:00", periods=len(h), freq="5min", tz=TZ)
    return pd.DataFrame({"open": l, "high": h, "low": l, "close": (h + l) / 2, "volume": 1.0}, index=idx)


# ── F07 ───────────────────────────────────────────────────────────────────────
def test_known_pivot_prefix_invariance():
    """H@5 (110) is confirmed at bar 8; a higher H@10 (120) with no low between is confirmed at 13. A live
    prefix ending at bar 9..12 has the 110 high; the whole-history reduction used to report NO high then."""
    df = _frame([100, 101, 102, 103, 104, 110, 105, 104, 103, 106, 120, 108, 107, 106, 105, 104])
    full = pivots(df, 3, 3)
    for i in range(3, len(df)):
        part = pivots(df.iloc[:i + 1], 3, 3)
        alive = [(p.idx, p.kind, p.price) for p in part if getattr(p, "until", 1 << 62) > i]
        assert [(p.idx, p.kind, p.price) for p in known_pivots(full, i)] == alive, i
    assert [(p.idx, p.price) for p in known_pivots(full, 10)] == [(5, 110.0)]
    assert [(p.idx, p.price) for p in known_pivots(full, 13)] == [(10, 120.0)]


def test_pivot_strategies_are_prefix_invariant_at_many_cuts():
    """Every pivot-based strategy: signals up to each cut equal those from scanning only that prefix."""
    d1 = synth_1m(24500, 0.013, pd.Timestamp("2026-09-07", tz=TZ), 4, 4)   # seed 4: order block + DTFX hit it
    df = resample_ohlc(d1, "5min")
    names = [n for n, c in BUILTIN.items() if c.__module__.endswith((".smc", ".classic"))]
    for name in names:
        full = [(x.i, x.side, round(x.entry, 6), round(x.stop, 6)) for x in BUILTIN[name]().scan(df)]
        for cut in range(300, len(df), 23):
            part = [(x.i, x.side, round(x.entry, 6), round(x.stop, 6)) for x in BUILTIN[name]().scan(df.iloc[:cut])
                    if x.i < cut - 1]
            assert [s for s in full if s[0] < cut - 1] == part, (name, cut)


# ── F26 ───────────────────────────────────────────────────────────────────────
def test_single_losing_trade_is_one_r_drawdown():
    t = {"r": -1.0, "mfe": 0.0, "hour": 9, "ts": pd.Timestamp("2026-06-02 09:30", tz=TZ)}
    assert stats([t])["max_dd_r"] == 1.0
