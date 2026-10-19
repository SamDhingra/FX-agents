"""Sweep + VWAP gold scalp: mirror symmetry, causal window, and the 70/30 management."""
import numpy as np
import pandas as pd

import fxagents.sweep_vwap as V
from fxagents.gemini_smc import block_mask
from tests.test_gemini_smc import frame, reflect, walk


def test_entries_are_mirror_symmetric():
    mid = walk(seed=12, n_days=90)
    A = {(e["j"], e["side"], e["mode"]) for e in V.find_trades(V.prepare(frame(mid)))}
    B = {(e["j"], -e["side"], e["mode"]) for e in V.find_trades(V.prepare(frame(reflect(mid))))}
    assert len(A) > 10 and len(A ^ B) <= 0.1 * len(A)


def test_trades_follow_the_window_and_management():
    a = V.prepare(frame(walk(seed=13, n_days=120)))
    tr, ctl = V.execute(a, V.find_trades(a), block_mask(a, 15, 15), np.random.default_rng(2))
    T = pd.DataFrame(tr)
    assert len(T) > 15 and len(ctl) == len(T)
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    m = loc.dt.hour * 60 + loc.dt.minute
    assert ((m >= V.WIN[0]) & (m < V.WIN[1])).all()
    assert (T[T.exit_reason == "stop"].R <= -0.99).all()                 # full stop before TP1
    run = T[T.exit_reason == "runner_stop"]                                # after TP1: 70% banked at 1.5R, rest ≥ BE+0.40
    assert (run.R >= V.TP1_FRAC * V.TP1_R - 1e-9).all()
    tgt = T[T.exit_reason == "runner_target"]
    assert np.allclose(tgt.R, V.TP1_FRAC * V.TP1_R + (1 - V.TP1_FRAC) * V.RUN_R, atol=0.05)
    ex = pd.to_datetime(T.exit_time).dt.tz_convert("America/New_York")
    assert ((ex.dt.hour * 60 + ex.dt.minute) <= V.FLAT).all()
    assert T.groupby(loc.dt.date).size().max() <= V.MAX_DAY
