"""Gold scalp rule: mirror-symmetric, causal timing, and trades follow the frozen exits and filters."""
import numpy as np
import pandas as pd

import fxagents.gold_scalp as G
from fxagents.gemini_smc import block_mask
from fxagents.gemini_test import prep
from tests.test_gemini_smc import frame, reflect, walk


def test_setups_are_mirror_symmetric():
    mid = walk(seed=4)
    A = {(s["t_ns"], s["side"], round(s["stop"], 6)) for s in G.setups(frame(mid), True)}
    B = {(s["t_ns"], -s["side"], round(6000.0 - s["stop"], 6)) for s in G.setups(frame(reflect(mid)), True)}
    assert len(A) > 20 and len(A ^ B) <= 0.05 * len(A)


def test_setups_follow_the_geometry_and_time_order():
    m1 = frame(walk(seed=6))
    for s in G.setups(m1, True):
        assert s["side"] == s["trend"]                                  # with the 15m trend only
        assert np.isclose(s["side"] * (s["target"] - s["stop"]), 3 * s["D"])   # target = 2D beyond the 3m close
    t = [s["t_ns"] for s in G.setups(m1, False)]
    assert t == sorted(t)


def test_trades_respect_exits_costs_and_the_two_loss_stop():
    m1 = frame(walk(seed=7, n_days=90))
    a = prep(m1)
    tr, ctl = G.execute(a, G.setups(m1, True), block_mask(a, 15, 15), np.random.default_rng(1))
    T = pd.DataFrame(tr)
    assert len(T) > 30 and len(ctl) >= len(T) - 2
    assert (T.hold_min <= G.HOLD_MIN + 1).all()
    assert (T[T.exit_reason == "stop"].R <= -0.99).all()
    assert (T.cost_R * T.atr <= G.COST_FRAC * T.D + 1e-9).all()        # spread ≤ 20% of the chart stop
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    m = loc.dt.hour * 60 + loc.dt.minute
    assert not ((m >= G.NO_ENTRY[0]) & (m < G.NO_ENTRY[1])).any()
    for day, x in T.groupby(pd.to_datetime(T.entry_time).map(G.session_day)):
        r = x.sort_values("entry_time").R.to_numpy()
        for i in range(2, len(r)):
            assert not (r[i - 1] <= 0 and r[i - 2] <= 0), "traded after two straight losses"
