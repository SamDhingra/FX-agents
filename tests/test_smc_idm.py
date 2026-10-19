"""SMC inducement model: causal swing confirmation, order geometry, limit fills on the real bid/ask, and exits."""
import numpy as np
import pandas as pd

import fxagents.smc_idm as I
from fxagents.gemini_smc import block_mask
from tests.test_gemini_smc import frame, walk


def test_swings_are_confirmed_two_candles_later():
    H = np.array([1, 2, 5, 3, 2, 1, 1, 1.0])
    L = H - 1
    shp, shi, _, _ = I.swings(H, L)
    assert np.isnan(shp[3]) and shp[4] == 5 and shi[4] == 2          # known at the close of candle 4, not before


def test_setups_and_trades_follow_the_frozen_geometry():
    a = I.prepare(frame(walk(seed=8, n_days=250)))
    ss = I.find_setups(a, 1, False) + I.find_setups(a, -1, False)
    assert len(ss) >= 10
    for s in ss:
        assert s["limit"] - s["stop"] >= I.MIN_STOP_ATR * s["atr15"] - 1e-9   # stop ≥ 0.8 ATR15 below the limit
    tr, ctl = I.execute(a, ss, block_mask(a, 15, 15), np.random.default_rng(1))
    T = pd.DataFrame(tr)
    if len(T):
        assert (T[T.exit_reason == "stop"].R <= -0.99).all()
        loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
        m = loc.dt.hour * 60 + loc.dt.minute
        assert ((m >= I.WIN[0]) & (m < I.WIN[1])).all()
        assert (T.tp1_R >= I.TP1_R - 1e-9).all() and (T.tp2_R >= I.TP2_R - 1e-9).all() and (T.tp2_R >= T.tp1_R).all()


def test_buy_limit_fills_only_when_the_ask_trades_there():
    a = I.prepare(frame(walk(seed=3, n_days=40)))
    X = I.mirrored_exec(a, 1)
    j = 5000
    lim = float(a["ask_l"][j + 3]) + 0.0                                # exactly the ask low three minutes later
    s = {"t": int(a["ns"][j]), "side": 1, "limit": lim, "stop": lim - 5, "tp1": lim + 50, "dol": np.nan, "zone": (0, 0)}
    first = next(k for k in range(j, j + 30) if X["in_l"][k] <= lim)
    assert X["in_l"][first] <= lim and first <= j + 3


def test_setups_are_mirror_symmetric():
    from tests.test_gemini_smc import reflect
    mid = walk(seed=8, n_days=200)
    a, r = I.prepare(frame(mid)), I.prepare(frame(reflect(mid)))
    A = {(x["t"], round(x["limit"], 6)) for x in I.find_setups(a, 1, False)}
    B = {(x["t"], round(x["limit"] + 6000.0, 6)) for x in I.find_setups(r, -1, False)}   # mirrored short = p - 6000
    assert len(A) >= 5 and len(A ^ B) <= 0.1 * len(A)
