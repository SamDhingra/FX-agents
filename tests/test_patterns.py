"""Chart patterns on hand-built price paths: each shape is found, named, and its break read correctly."""
import numpy as np
import pandas as pd

from fxagents.patterns import detect, to_json, zigzag, atr14


def frame(closes, noise=0.15):
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range("2026-10-01 09:00", periods=len(c), freq="15min", tz="America/New_York")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + noise, "low": np.minimum(o, c) - noise, "close": c}, index=idx)


def path(*legs):
    """legs: (target, n_bars) from the previous level, linear."""
    pts = [legs[0][0]]
    for tgt, n in legs[1:]:
        pts += list(np.linspace(pts[-1], tgt, n + 1)[1:])
    return pts


def kinds(df):
    return {(p["kind"], p["status"]) for p in detect(df)}


def test_zigzag_alternates():
    df = frame(path((100, 1), (106, 12), (101, 12), (107, 12), (100, 12)))
    a = atr14(df.high.values, df.low.values, df.close.values)
    P = zigzag(df.high.values, df.low.values, a)
    assert len(P) >= 3 and all(P[i][2] != P[i + 1][2] for i in range(len(P) - 1))


def test_double_top_confirmed_on_neckline_break():
    df = frame(path((100, 1), (110, 15), (104, 10), (110.1, 10), (100, 15)))
    assert ("double_top", "confirmed") in kinds(df)


def test_double_bottom():
    df = frame(path((110, 1), (100, 15), (106, 10), (99.9, 10), (110, 15)))
    assert ("double_bottom", "confirmed") in kinds(df)


def test_head_and_shoulders():
    df = frame(path((100, 1), (106, 10), (102, 8), (111, 10), (102.2, 10), (106.2, 8), (96, 14)))
    assert any(k == "head_shoulders" for k, _ in kinds(df))


def test_ascending_triangle_breaks_up():
    df = frame(path((100, 1), (108, 10), (102, 8), (108, 8), (104.5, 8), (108, 8), (106, 6), (115, 10)))
    assert any(k == "ascending_triangle" for k, _ in kinds(df))


def test_bull_flag():
    df = frame(path((100, 1), (100, 10), (112, 6), (110, 8), (111, 4), (109.5, 5), (118, 8)), noise=0.1)
    assert any(k == "bull_flag" for k, _ in kinds(df))


def test_json_has_times_and_segments():
    df = frame(path((100, 1), (110, 15), (104, 10), (110.1, 10), (100, 15)))
    js = to_json(df, detect(df))
    p = next(x for x in js if x["kind"] == "double_top")
    assert p["t0"] < p["t1"] and len(p["segs"]) == 3 and p["dir"] == -1 and p["target"] < 104


def test_mirror_symmetry():
    """Upside-down prices give the mirror patterns at the same bars."""
    pts = path((100, 1), (110, 15), (104, 10), (110.1, 10), (100, 15), (106, 10), (102, 8), (111, 10), (102.2, 10), (106.2, 8), (96, 14))
    up, dn = frame(pts), frame(list(300 - np.asarray(pts)))
    flip = {"double_top": "double_bottom", "double_bottom": "double_top", "head_shoulders": "inverse_head_shoulders",
            "inverse_head_shoulders": "head_shoulders", "bull_flag": "bear_flag", "bear_flag": "bull_flag",
            "ascending_triangle": "descending_triangle", "descending_triangle": "ascending_triangle",
            "rising_wedge": "falling_wedge", "falling_wedge": "rising_wedge", "channel_up": "channel_down",
            "channel_down": "channel_up", "symmetrical_triangle": "symmetrical_triangle"}
    a = sorted((flip[p["kind"]], p["i0"], p["i1"], p["status"]) for p in detect(up))
    b = sorted((p["kind"], p["i0"], p["i1"], p["status"]) for p in detect(dn))
    assert a and a == b


def test_api_finds_patterns_on_the_trade_timeframe():
    from types import SimpleNamespace
    from fxagents.dashboard.insights import patterns
    pts = path((100, 1), (110, 15), (104, 10), (110.1, 10), (100, 15))
    m1 = frame(np.repeat(pts, 15), noise=0.05)                     # 1-minute candles of the same shape
    m1.index = pd.date_range("2026-10-01 05:00", periods=len(m1), freq="1min", tz="America/New_York")
    m1["volume"] = 1.0
    c = SimpleNamespace(store=SimpleNamespace(m1=lambda s: m1))
    r = patterns(c, "XAUUSD", m1.index[200].isoformat(), m1.index[-1].isoformat(), tf=15)
    assert r["tf"] == 15 and any(p["kind"] == "double_top" for p in r["patterns"])
