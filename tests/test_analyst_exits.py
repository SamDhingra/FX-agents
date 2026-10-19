"""Trade-analyst exits in the simulator (analyst check): off by default, causal event arrays, and each exit fires."""
import dataclasses

import numpy as np
import pandas as pd

from fxagents.research import analyst_arrays, simulate_live
from fxagents.sim import Mgmt, synth_1m
from tests.test_exit_rules import BASE, path, run


def test_off_by_default_changes_nothing():
    assert run(BASE) == run(dataclasses.replace(BASE, an_flip=False, an_break=False, an_stall_min=0))


def test_stall_exit_cuts_a_trade_that_goes_nowhere():
    flat = np.r_[np.full(90, 100.4), np.linspace(100.4, 85, 30)]        # drifts, then falls through the stop
    c = np.r_[100.0, flat]
    o = np.r_[c[0], c[:-1]]
    O, H, L, C = o, np.maximum(o, c) + 0.05, np.minimum(o, c) - 0.05, c
    r = run(dataclasses.replace(BASE, an_stall_min=60, an_stall_max_r=0.5), (O, H, L, C))
    assert r["exit_reason"] == "analyst_stall" and r["r"] > -0.2


def test_flip_and_break_exits_fire_on_their_event_minutes():
    O, H, L, C = path()
    n = len(C)
    an = {"flip": np.zeros(n, bool), "brk": np.zeros(n, bool)}
    an["flip"][40] = True
    m = dataclasses.replace(BASE, an_flip=True)
    r = simulate_live(O, H, L, C, np.arange(n), 0, 1, 90.0, m, 0.0, np.zeros(n, bool), None, 1e9, False, an=an)
    assert r["exit_reason"] == "analyst_trend_flip" and r["j_exit"] == 40
    an["flip"][40], an["brk"][35] = False, True
    r = simulate_live(O, H, L, C, np.arange(n), 0, 1, 90.0, dataclasses.replace(BASE, an_break=True), 0.0,
                      np.zeros(n, bool), None, 1e9, False, an=an)
    assert r["exit_reason"] == "analyst_structure_break" and r["j_exit"] == 35


def test_event_arrays_only_fire_at_candle_closes():
    m1 = synth_1m(3000, 0.012, pd.Timestamp("2026-03-02", tz="America/New_York"), 20, seed=3)
    close1 = m1.index + pd.Timedelta("1min")
    a = analyst_arrays(m1, close1)
    for sd in (1, -1):
        f, b = a[sd]["flip"], a[sd]["brk"]
        assert f.any() and b.any()
        assert (close1[f].minute % 15 == 0).all() and (close1[b].minute % 5 == 0).all()
    assert not (a[1]["flip"] & a[-1]["flip"]).any()
