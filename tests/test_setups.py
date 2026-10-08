"""Structure primitives and the playbook setups: definitions, no look-ahead, long/short symmetry."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fxagents import structure as sx
from fxagents.indicators import pivots, resample_ohlc
from fxagents.sim import synth_1m
from fxagents.strategies import SETUPS, Strategy, build_strategy
from fxagents.strategies.dtfx import DTFXCloseFib, DTFXCloseOrigin, DTFXWickFib, DTFXCloseFibBreak

TZ = "America/New_York"


def frame(seed=3, days=12, tf="5min", px=25000.0):
    m1 = synth_1m(px, 0.012, pd.Timestamp("2026-06-01", tz=TZ), days, seed, TZ)
    return resample_ohlc(m1, tf)


def peers_for(df, seed=11):
    """A correlated index: the same moves ×1.85 plus an independent wobble (like US30 vs NDQ)."""
    n = frame(seed, tf="5min", px=1000.0).reindex(df.index).ffill().bfill()
    dev = (n["close"] - n["close"].rolling(48, min_periods=1).mean()) * 6
    out = pd.DataFrame({c: df[c] * 1.85 + dev for c in ("open", "high", "low", "close")}, index=df.index)
    return [out]


def test_vectorised_pivots_match_the_reference():
    df = frame(5)
    for left in (2, 3, 5):
        a = [p for p in pivots(df, left, left) if p.until > len(df)]   # alive at the end = whole-history reduction
        b = sx.pivots_arr(df["high"].to_numpy(), df["low"].to_numpy(), left, left)
        assert [(p.idx, p.kind, p.price, p.known_at) for p in a] == [(p.idx, p.kind, p.price, p.known_at) for p in b]


def _bars(closes, spread=0.5):
    idx = pd.date_range("2026-06-02 09:00", periods=len(closes), freq="5min", tz=TZ)
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c + spread), "low": np.minimum(o, c - spread),
                         "close": c, "volume": 1.0}, index=idx)


def test_bos_vs_choch_definitions():
    # down-leg, swing high at 106, CHoCH up through it, pull back, then BOS through the next high
    seq = [110, 108, 106, 104, 102, 100, 102, 104, 106, 104, 102, 101, 103, 105, 107, 109, 111,
           109, 107, 105, 107, 109, 111, 113, 115, 117]
    df = _bars(seq)
    H, L, C = (df[c].to_numpy() for c in ("high", "low", "close"))
    ms = sx.market_structure(H, L, C, sx.pivots_arr(H, L, 2, 2, reduce=False))
    ev = [(i, int(e)) for i, e in enumerate(ms["event"]) if e]
    kinds = [e for _, e in ev]
    assert sx.BULL_CHOCH in kinds or sx.BULL_BOS in kinds
    first_up = next(e for e in kinds if e > 0)
    later_up = [e for e in kinds[kinds.index(first_up) + 1:] if e > 0]
    assert later_up and all(e == sx.BULL_BOS for e in later_up)          # once the trend is up, breaks are BOS
    assert ms["trend"][-1] == 1


def test_session_levels_are_only_known_after_their_window():
    m1 = synth_1m(4000, 0.01, pd.Timestamp("2026-06-01", tz=TZ), 4, 2, TZ)
    df = resample_ohlc(m1, "15min")
    ct = df.index + pd.Timedelta("15min")
    lv = sx.session_levels(df.index, ct, *(df[c].to_numpy() for c in ("open", "high", "low")))
    h = df.index.hour
    assert np.isnan(lv["asia_hi"][(h >= 17)]).all()                       # forming / not started
    assert np.isnan(lv["lon_hi"][(h < 5)]).all()
    day = df[(df.index >= "2026-06-02 00:00") & (df.index < "2026-06-02 17:00")]
    asia = df[(df.index >= "2026-06-01 20:00") & (df.index < "2026-06-02 00:00")]
    j = df.index.get_loc(day.index[0])
    assert lv["asia_hi"][j] == asia["high"].max() and lv["asia_lo"][j] == asia["low"].min()


ALL_NEW = sorted(SETUPS)


@pytest.mark.parametrize("name", ALL_NEW)
def test_no_look_ahead(name):
    """Signals up to bar k are identical whether or not the future bars exist."""
    df = frame(7, days=10)
    st = build_strategy({"class": name, "tf": "5min"})
    full_ctx = Strategy._context(df)
    if st.needs_peers:
        full_ctx["peers"] = peers_for(df)
    full = st._scan_full(df, full_ctx)
    for cut in (500, 900, 1300, 1700, 2100, len(df) - 300, len(df) - 7):
        part = df.iloc[:cut + 1]
        ctx = Strategy._context(part)
        if st.needs_peers:
            ctx["peers"] = [p.iloc[:cut + 1] for p in full_ctx["peers"]]
        a = {(s.i, s.side, round(s.entry, 6), round(s.stop, 6)) for s in full if s.i <= cut}
        b = {(s.i, s.side, round(s.entry, 6), round(s.stop, 6)) for s in st._scan_full(part, ctx)}
        assert a == b, f"{name}: look-ahead around bar {cut}"


@pytest.mark.parametrize("name", ALL_NEW)
def test_long_short_symmetry(name):
    """Flip the chart upside down → the same trades on the same bars, opposite direction."""
    df = frame(9, days=10)
    k = 2 * float(df["high"].max())
    flip = pd.DataFrame({"open": k - df["open"], "high": k - df["low"], "low": k - df["high"],
                         "close": k - df["close"], "volume": df["volume"]}, index=df.index)
    st = build_strategy({"class": name, "tf": "5min"})
    c1, c2 = Strategy._context(df), Strategy._context(flip)
    if st.needs_peers:
        pr = peers_for(df)
        c1["peers"] = pr
        c2["peers"] = [pd.DataFrame({"open": k - p["open"], "high": k - p["low"], "low": k - p["high"],
                                     "close": k - p["close"]}, index=p.index) for p in pr]
    a = {(s.i, s.side) for s in st._scan_full(df, c1)}
    b = {(s.i, -s.side) for s in st._scan_full(flip, c2)}
    assert a == b


def test_every_setup_fires_with_stops_on_the_right_side():
    df = frame(4, days=20)
    for name in ALL_NEW:
        st = build_strategy({"class": name, "tf": "5min",
                             "params": {"windows": None} if "windows" in SETUPS[name].default_params else {}})
        ctx = Strategy._context(df)
        if st.needs_peers:
            ctx["peers"] = peers_for(df)
        sig = st._scan_full(df, ctx)
        assert sig, f"{name} never fired on 20 days of synthetic data"
        assert all((s.entry - s.stop) * s.side > 0 for s in sig), name     # (sides: see the symmetry test)


def test_dtfx_definitions_are_separate_and_never_called_canonical():
    defs = {c.name: c.definition() for c in (DTFXCloseFib, DTFXWickFib, DTFXCloseFibBreak, DTFXCloseOrigin)}
    assert len({tuple(sorted(d.items())) for d in defs.values()}) == 4    # four distinct definitions
    for c in (DTFXCloseFib, DTFXWickFib, DTFXCloseFibBreak, DTFXCloseOrigin):
        assert "canonical" not in c.description.lower()
    df = frame(6, days=15)
    ids = [{(s.i, s.side) for s in build_strategy({"class": n, "tf": "5min"}).scan(df)} for n in defs]
    assert len({frozenset(x) for x in ids}) == 4                          # they really trade differently


def test_new_setups_are_fast_enough_for_minute_history():
    import time
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-06-01", tz=TZ), 30, 1, TZ)
    t0 = time.time()
    for name in ("ict_2022", "dtfx_close_fib", "smc_bos_retest"):
        build_strategy({"class": name, "tf": "1min"}).scan(m1)
    assert time.time() - t0 < 60          # ~40k 1m bars each, both sides


def _with_volume(df, seed=5):
    rng = np.random.default_rng(seed)
    out = df.copy()
    out["volume"] = rng.lognormal(4, 0.6, len(df)).round()
    return out


@pytest.mark.parametrize("mode", ["impulse", "dry", "climax"])
def test_volume_variants_have_no_look_ahead(mode):
    df = _with_volume(frame(7, days=14))
    st = build_strategy({"class": "ict_turtle_soup", "tf": "5min", "params": {"vol": mode}})
    full = st._scan_full(df, Strategy._context(df))
    base = st.__class__({}, tf="5min")._scan_full(df, Strategy._context(df))
    assert full and len(full) < len(base)                     # the filter really filters
    for cut in (1500, 2500, len(df) - 5):
        part = df.iloc[:cut + 1]
        a = {(s.i, s.side) for s in full if s.i <= cut}
        b = {(s.i, s.side) for s in st._scan_full(part, Strategy._context(part))}
        assert a == b, f"vol={mode}: look-ahead around bar {cut}"


def test_rvol_and_vwap_are_causal():
    from fxagents import structure as sx
    df = _with_volume(frame(3, days=10))
    rv, (vw, sd) = sx.rvol_tod(df), sx.session_vwap(df)
    cut = len(df) - 400
    rv2, (vw2, sd2) = sx.rvol_tod(df.iloc[:cut]), sx.session_vwap(df.iloc[:cut])
    np.testing.assert_allclose(rv[:cut], rv2, equal_nan=True)
    np.testing.assert_allclose(vw[:cut], vw2, equal_nan=True)


@pytest.mark.parametrize("name", ["dtfx_close_fib", "dtfx_wick_fib", "dtfx_close_fib_brk"])
def test_dtfx_pullback_zone_variant(name):
    """level='50-70': causal, symmetric, fires, and only enters between the 50% and 70% levels."""
    df = frame(4, days=20)
    st = build_strategy({"class": name, "tf": "5min", "params": {"level": "50-70"}})
    ctx = Strategy._context(df)
    full = st._scan_full(df, ctx)
    assert full and all((s.entry - s.stop) * s.side > 0 for s in full)
    for cut in (900, 1700, len(df) - 50):
        part = df.iloc[:cut + 1]
        a = {(s.i, s.side, round(s.stop, 6)) for s in full if s.i <= cut}
        assert a == {(s.i, s.side, round(s.stop, 6)) for s in st._scan_full(part, Strategy._context(part))}
    k = 2 * float(df["high"].max())
    flip = pd.DataFrame({"open": k - df["open"], "high": k - df["low"], "low": k - df["high"],
                         "close": k - df["close"], "volume": df["volume"]}, index=df.index)
    assert {(s.i, s.side) for s in full} == {(s.i, -s.side) for s in st._scan_full(flip, Strategy._context(flip))}
