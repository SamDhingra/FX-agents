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


# ── F13 ───────────────────────────────────────────────────────────────────────
def _h1(start, end):
    idx = pd.date_range(start, end, freq="1h", tz=TZ, inclusive="left")
    c = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.3, len(idx)))
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c}, index=idx)


def test_daily_bar_always_starts_at_1700_ny():
    from fxagents.bias import wall_ohlc
    for a, b in (("2026-02-20", "2026-03-20"), ("2026-10-20", "2026-11-20")):    # spring + autumn switches
        d = wall_ohlc(_h1(a, b), "24h", offset="17h")
        assert set(d.index.hour) == {17}, (a, sorted(set(d.index.hour)))
        assert set(d["end"].dt.hour) == {17} and (d["end"].iloc[:-1].to_numpy() == d.index[1:].to_numpy()).all()
        assert {round(x / 3600) for x in (d["end"] - d.index).dt.total_seconds()} == {23, 24, 25} - ({25} if a < "2026-06" else {23})


def test_4h_bars_sit_on_the_ny_session_grid():
    from fxagents.bias import wall_ohlc
    for a, b in (("2026-02-20", "2026-03-20"), ("2026-10-20", "2026-11-20")):
        h4 = wall_ohlc(_h1(a, b), "4h", offset="1h")
        assert set(h4.index.hour) == {17, 21, 1, 5, 9, 13}, (a, sorted(set(h4.index.hour)))
        assert set(h4["end"].dt.hour) == {17, 21, 1, 5, 9, 13}


def test_trading_day_rolls_at_1700_wall_clock_across_dst():
    from fxagents.structure import trading_day
    for d in ("2026-03-07", "2026-03-08", "2026-10-31", "2026-11-01"):
        t = pd.Timestamp(f"{d} 17:00", tz=TZ)
        assert trading_day(t) == trading_day(t - pd.Timedelta("1min")) + pd.Timedelta("1D") \
            == pd.Timestamp(d) + pd.Timedelta("1D")


# ── F14 ───────────────────────────────────────────────────────────────────────
def _flat_bars(n, freq="5min"):
    idx = pd.date_range("2026-06-02 09:00", periods=n, freq=freq, tz=TZ)
    return pd.DataFrame({"open": 102.0, "high": 104.0, "low": 100.0, "close": 102.0, "volume": 10.0}, index=idx)


def test_context_cache_sees_a_corrected_high():
    from fxagents.strategies import Strategy
    from fxagents.strategies.base import frame_key
    df = _flat_bars(40)
    assert abs(Strategy.context(df)["atr"][-1] - 4.0) < 1e-9
    fixed = df.copy()
    fixed.iloc[-1, fixed.columns.get_loc("high")] = 204.0            # TR 104 → ATR 4·13/14 + 104/14
    assert abs(Strategy.context(fixed)["atr"][-1] - 11.142857) < 1e-6
    older = df.copy()
    older.iloc[5, older.columns.get_loc("volume")] = 99.0            # anywhere, any column → new identity
    assert frame_key(older) != frame_key(df)


def test_barstore_shows_a_corrected_bar():
    from fxagents.data import BarStore
    from fxagents.models import Bar
    st = BarStore(TZ)
    m1 = _flat_bars(30, "1min")
    st.load_history("NDQ", m1)
    assert st.tf("NDQ", "5min")["high"].iloc[1] == 104.0
    t = m1.index[7]                                                   # inside the 2nd 5m bar, not the newest
    st.append(Bar("NDQ", t, 102.0, 900.0, 100.0, 102.0, 10.0))
    st.append(Bar("NDQ", m1.index[-1] + pd.Timedelta("1min"), 102.0, 104.0, 100.0, 102.0, 10.0))  # + a new bar
    h5 = st.tf("NDQ", "5min")
    assert h5["high"].iloc[1] == 900.0                                # incremental rebuild used to keep 104
    assert h5.index.is_monotonic_increasing and len(h5) == 6
    assert st.m1("NDQ").index.is_monotonic_increasing and len(st.m1("NDQ")) == 31
    last = m1.index[-1] + pd.Timedelta("1min")                        # same ts + length: a re-sent newest bar
    st.append(Bar("NDQ", last, 102.0, 104.0, 1.0, 102.0, 10.0))
    assert st.tf("NDQ", "5min", complete_only=False)["low"].iloc[-1] == 1.0


# ── F23 ───────────────────────────────────────────────────────────────────────
def test_hourly_bias_waits_for_the_hours_last_bar():
    """The 09:59 bar is polled only after the 10:00 clock tick. The bias must not close the partial
    09:00 hour; it is computed once the bar arrives and reflects its close (which breaks 1H structure)."""
    import asyncio
    import copy

    from fxagents.agents.context import BiasAgent
    from fxagents.agents.core import Ctx
    from fxagents.bus import Bus
    from fxagents.config import load_config
    from fxagents.data import BarStore
    from fxagents.models import Bar
    from fxagents.state import LiveState

    cfg = copy.deepcopy(load_config("config.yaml"))
    sym = next(iter(cfg["instruments"]))
    cfg["instruments"] = {sym: cfg["instruments"][sym]}
    cfg["bias"]["safeguards"]["jev_audit"] = False
    h_idx = pd.date_range("2026-06-01 00:00", "2026-06-04 09:00", freq="1h", tz=TZ, inclusive="left")
    c = 100 + 0.3 * np.arange(len(h_idx)) + 2.0 * np.sin(np.arange(len(h_idx)) / 2.0)     # rising zig-zag
    store = BarStore(TZ)
    store.load_h1(sym, pd.DataFrame({"open": c, "high": c + 0.4, "low": c - 0.4, "close": c}, index=h_idx))
    m_idx = pd.date_range("2026-06-04 09:00", periods=59, freq="1min", tz=TZ)                # 09:00 … 09:58
    px = c[-1] + 0.5
    store.load_history(sym, pd.DataFrame({"open": px, "high": px + 0.1, "low": px - 0.1, "close": px,
                                          "volume": 1.0}, index=m_idx))
    st = LiveState()
    agent = BiasAgent(Ctx(cfg, Bus(), st, store, None, None, None, None))
    agent.start()
    partial = agent.compute(sym, pd.Timestamp("2026-06-04 10:00:05", tz=TZ))

    asyncio.run(agent.on_clock(pd.Timestamp("2026-06-04 10:00:05", tz=TZ)))
    assert sym not in st.bias                                        # hour incomplete → not computed yet
    crash = float(c.min() - 20)                                      # the 09:59 close breaks every swing low
    store.append(Bar(sym, pd.Timestamp("2026-06-04 09:59", tz=TZ), px, px, crash, crash, 1.0))
    asyncio.run(agent.on_clock(pd.Timestamp("2026-06-04 10:00:20", tz=TZ)))
    b = st.bias[sym]
    assert b["price"] == round(crash, 4) and b["h1"] == -1 and partial["h1"] != -1
    asyncio.run(agent.on_clock(pd.Timestamp("2026-06-04 10:00:35", tz=TZ)))      # final for the hour
    assert agent.done[sym] == (pd.Timestamp("2026-06-04 10:00", tz=TZ), True)


def test_ict_trading_day_is_unit_safe():
    """pandas 3 indexes default to microseconds: the trading-day bucket must not collapse to one day."""
    import numpy as np
    import pandas as pd
    from fxagents.strategies.ict import _tday
    idx = pd.date_range("2026-01-05", periods=3 * 1440, freq="1min", tz="America/New_York")
    for unit in ("ns", "us"):
        df = pd.DataFrame({"close": 1.0}, index=idx.as_unit(unit))
        assert np.unique(_tday(df, {})).size == 4
