"""ASTRA research strategies: run end to end, respect the session clock, and use a lagged 5m regime."""
import pandas as pd

from fxagents import astra as A
from fxagents.sim import synth_1m

TZ = "America/New_York"


def test_astra_runs_and_respects_the_clock():
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-06-01", tz=TZ), 15, 3, TZ)
    f = A.features(m1)
    rows = A.mrsf(f, "NDQ") + A.dtfx(f, "NDQ") + A.controls(f, "NDQ")
    for r in rows:
        if r.get("setup_ts") is not None:
            hm = r["setup_ts"].hour * 60 + r["setup_ts"].minute
            assert 9 * 60 + 35 <= hm <= 10 * 60 + 55
        if r.get("filled"):
            assert r["exit"] in {"stop", "stop_same_bar", "target", "time_30m", "liquidate_1130", "blackout", "end"}
            assert r["r"] >= -3.0


def test_regime_uses_only_strictly_earlier_5m_bars():
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-06-01", tz=TZ), 6, 5, TZ)
    full = A.features(m1)["reg"]
    cut = len(m1) - 37
    part = A.features(m1.iloc[:cut])["reg"]
    assert (full[:cut] == part).all()
