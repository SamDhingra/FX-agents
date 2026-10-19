"""Protection before the first target (exit study): a trade that runs to +0.6R and falls back to its stop."""
import dataclasses

import numpy as np

from fxagents.research import simulate_live
from fxagents.sim import Mgmt

BASE = Mgmt(rr=1.0, partial=0.5, lock_r=0.1, pyramid=False, max_adds=0)


def path(peak_r=0.6, after=None):
    """1m mid closes: entry 100 (risk 10 → stop 90), up to 100 + 10·peak_r, then down through the stop."""
    up = np.linspace(100, 100 + 10 * peak_r, 30)
    dn = np.linspace(100 + 10 * peak_r, 85, 60) if after is None else after
    c = np.r_[100.0, up, dn]
    o = np.r_[c[0], c[:-1]]
    return o, np.maximum(o, c) + 0.05, np.minimum(o, c) - 0.05, c


def run(m, c4=None, hs=0.0):
    O, H, L, C = c4 or path()
    n = len(C)
    return simulate_live(O, H, L, C, np.arange(n), 0, 1, 90.0, m, hs, np.zeros(n, bool), None, 1e9, full_exit=False)


def test_today_rules_give_it_all_back():
    r = run(BASE)
    assert r["exit_reason"] == "stop" and r["r"] < -0.99 and r["mfe"] > 0.55


def test_early_partial_banks_half_and_protects_the_rest():
    r = run(dataclasses.replace(BASE, early_partial_r=0.5))
    assert r["r"] > 0.2                                    # ~half banked near +0.5R, the rest out at break-even
    assert r["exit_reason"] in ("stop",)


def test_early_breakeven_cuts_the_loss_to_zero():
    r = run(dataclasses.replace(BASE, early_be_r=0.5))
    assert abs(r["r"]) < 0.02


def test_giveback_exits_after_half_the_open_profit_is_gone():
    r = run(dataclasses.replace(BASE, giveback_after_r=0.5))
    assert r["exit_reason"] == "giveback" and 0.25 <= r["r"] <= 0.35


def test_fixed_point_partial_uses_price_distance():
    m = dataclasses.replace(BASE, early_partial_pts=5.0)     # 5 points = 0.5R here
    assert run(m)["r"] > 0.2
    m = dataclasses.replace(BASE, early_partial_pts=8.0)     # never reached (peak +6 points)
    assert run(m)["r"] < -0.99


def test_early_partial_replaces_the_1r_partial_on_a_winner():
    rising = path(peak_r=0.6, after=np.linspace(106, 125, 60))   # keeps going past +2R
    a = run(BASE, rising)
    b = run(dataclasses.replace(BASE, early_partial_r=0.5), rising)
    assert a["r"] > b["r"] > 0                              # banking early costs some of a big runner
