"""Rebuilt SMC/ICT/DTFX rules: shorts are the exact mirror of longs, and the in-sample year is split off."""
import numpy as np
import pandas as pd

import fxagents.gemini_smc as S
from fxagents.gemini_test import prep
from fxagents.simple_rules import NY


def walk(n_days=70, seed=5, base=3000.0):
    idx = pd.date_range("2024-11-04", periods=n_days * 1440, freq="1min", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(seed)
    p = base + np.cumsum(rng.normal(0, 0.35, len(idx)))
    d = pd.DataFrame(index=idx)
    d["m_o"], d["m_c"] = np.r_[base, p[:-1]], p
    wig = np.abs(rng.normal(0, 0.35, len(idx)))
    d["m_h"], d["m_l"] = np.maximum(d.m_o, d.m_c) + wig, np.minimum(d.m_o, d.m_c) - wig[::-1]
    day = pd.Series(rng.lognormal(0, 0.4, n_days * 2))
    d["volume"] = rng.integers(20, 200, len(idx)) * day.iloc[(idx.dayofyear % (n_days * 2))].to_numpy()
    return d


def frame(mid, sp=0.3):
    d = pd.DataFrame(index=mid.index)
    for f in "ohlc":
        d[f"bid_{f}"], d[f"ask_{f}"] = mid[f"m_{f}"] - sp / 2, mid[f"m_{f}"] + sp / 2
        d[f"m_{f}"] = mid[f"m_{f}"]
    d["volume"] = mid.volume
    return d


def reflect(mid, c=6000.0):
    r = mid.copy()
    r["m_o"], r["m_c"], r["m_h"], r["m_l"] = c - mid.m_o, c - mid.m_c, c - mid.m_l, c - mid.m_h
    return r


def detect_all(m1, fn, **kw):
    a = prep(m1)
    b = S.build(m1, a, 5 if fn is S.detect_wick else 15)
    return [(o.j0, o.side, round(o.level, 6)) for sd in (1, -1) for o in fn(b, sd, **kw)]


def test_orders_follow_the_spec_geometry():
    mid = walk()
    m1 = frame(mid)
    a = prep(m1)
    b = S.build(m1, a, 15)
    for o in S.detect_bos(b, 1):
        assert o.kind == "limit" and o.j1 > o.j0 and o.k_atr == 1.15 and o.pct == 0.0025
    for o in S.detect_sbs(b, -1):
        assert o.kind == "stop" and o.cancel_hi is not None and o.cancel_lo is None   # short: cancel above the sweep high
    b5 = S.build(m1, a, 5)
    for o in S.detect_wick(b5, 1):
        assert o.kind == "limit" and o.cancel_hi is not None and o.k_atr == 2.0


def test_detectors_are_mirror_symmetric():
    mid = walk()
    up, dn = frame(mid), frame(reflect(mid))
    for fn in (S.detect_bos, S.detect_wick, S.detect_sbs):
        a_ = detect_all(up, fn)
        b_ = detect_all(dn, fn)
        assert a_, fn.__name__ + " found nothing on 70 days"
        mirrored = sorted((j, -s, round(6000.0 - lv, 6)) for j, s, lv in b_)
        assert sorted(a_) == mirrored, fn.__name__
        for ctl in ({"deep": True} if fn is S.detect_bos else {"control": True},):
            c1, c2 = detect_all(up, fn, **ctl), detect_all(dn, fn, **ctl)
            assert sorted(c1) == sorted((j, -s, round(6000.0 - lv, 6)) for j, s, lv in c2), fn.__name__ + " control"


def test_segments_split_at_the_table_start():
    t = pd.DataFrame({"entry_time": pd.to_datetime(["2025-10-07 15:00", "2025-10-08 15:00"]).tz_localize("UTC")})
    seg = S.segment(t, holdout=False).tolist()
    assert seg == ["dev Oct 2024–Oct 2025 (clean)", "Oct 2025–Sep 2026 (in-sample)"]
    assert set(S.segment(t, holdout=True)) == {"holdout 2021–Sep 2024 (clean)"}
