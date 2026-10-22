"""PS-1 (NDQ 1-minute pullback reclaim) port: rules on synthetic data, the engine's post-exit cooldown, look-ahead."""
import numpy as np
import pandas as pd

from fxagents.bt import data, engine
from fxagents.bt.run import load_plugin

NY = "America/New_York"


def _market(days=12, seed=5, spread=0.4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(pd.Timestamp("2026-02-02 08:00", tz=NY), periods=days * 1440, freq="1min")
    drift = np.where((np.arange(len(idx)) // 240) % 2 == 0, 0.6, -0.6)          # 4-hour trend legs
    mid = 20000 + np.cumsum(drift + rng.normal(0, 4, len(idx)))
    o = np.r_[mid[0], mid[:-1]]
    h = np.maximum(o, mid) + rng.uniform(0, 3, len(idx))
    l = np.minimum(o, mid) - rng.uniform(0, 3, len(idx))
    d = pd.DataFrame(index=idx.tz_convert("UTC"))
    for f, a in zip("ohlc", (o, h, l, mid)):
        d[f"bid_{f}"], d[f"ask_{f}"] = a - spread / 2, a + spread / 2
    keep = idx.dayofweek < 5
    return data.from_frame(d[keep])


def test_ps1_signals_follow_the_rules_and_trade():
    S, _ = load_plugin("btplugins/ps1_pullback_reclaim.py")
    s = S()
    m = _market()
    sig = s.signals(m)
    assert len(sig) > 20
    for x in sig:
        t = pd.Timestamp(x.t, tz="UTC").tz_convert(NY)
        mins = t.hour * 60 + t.minute
        assert 575 <= mins < 690 or 780 <= mins < 915
        assert round(x.stop * 10) == x.stop * 10 or abs(x.stop * 10 - round(x.stop * 10)) < 1e-6   # on the 0.1 grid
    res = engine.simulate(s, m)
    T = res["trades"]
    assert T and all(t["hold_min"] <= 12 + 1e-9 for t in T)
    assert set(t["exit_reason"] for t in T) <= {"target", "stop", "max_hold", "stop_same_bar", "flat", "data_gap"}
    # three minutes between an exit and the next fill, at most six a day
    T = sorted(T, key=lambda t: t["entry_time"])
    for a, b in zip(T, T[1:]):
        assert (b["entry_time"] - a["exit_time"]).total_seconds() >= 180 - 1e-6
    per_day = pd.Series([t["entry_time"].tz_convert(NY).date() for t in T]).value_counts()
    assert per_day.max() <= 6
    nc = S(context=False).signals(m)
    assert len(nc) > len(sig)                                  # the control drops the 5-minute filter


def test_ps1_lookahead_audit():
    S, _ = load_plugin("btplugins/ps1_pullback_reclaim.py")
    s = S()
    m = _market()
    a = engine.lookahead_audit(s, m, s.signals(m), 8, warm_days=5)
    assert a["checked"] == 8 and a["failed"] == 0, a
