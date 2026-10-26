"""Round 3: the stricter what-if judge and the ChatGPT checks (fxagents/whatif_judge, fxagents/round3)."""
import numpy as np
import pandas as pd

from fxagents import round3 as R
from fxagents import whatif_judge as J

NY = "America/New_York"


def trades(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2021-01-04", "2026-09-30")
    ts = pd.DatetimeIndex(rng.choice(days, n)).tz_localize(NY) + pd.to_timedelta(rng.integers(8 * 60, 15 * 60, n), "min")
    cell = rng.choice(["bad", "ok1", "ok2"], n)
    r = rng.normal(0, 1, n) + np.where(cell == "bad", -0.4, 0.05)
    return pd.DataFrame({"ts": ts, "day": ts.tz_localize(None).normalize().date.astype(str), "cell": cell,
                         "side": rng.choice([1, -1], n), "r": r})


def test_a_check_that_only_removes_a_bad_setup_fails_the_stratified_test():
    t = trades()
    t["f"] = t.cell == "bad"                       # composition only: no information inside any cell
    j = J.judge(t, "f", "seen", len(t))
    assert j["diff"] > 0.3 and j["strat_p"] > 0.5 and not j["pass"]


def test_a_check_that_finds_worse_trades_inside_each_setup_passes():
    t = trades(seed=1)
    rng = np.random.default_rng(5)
    t["f"] = rng.random(len(t)) < 0.3
    t.loc[t.f, "r"] -= 0.5                         # flagged trades really are worse, in every cell
    j = J.judge(t, "f", "seen", len(t))
    assert j["pass"] and j["diff_ci"][0] > 0 and j["strat_p"] < 0.01 and j["split"] == "2023-11-17"


def test_low_coverage_is_inconclusive():
    t = trades(seed=2)
    t["f"] = False
    j = J.judge(t, "f", "seen", int(len(t) / 0.8))
    assert not j["pass"] and "inconclusive" in j["why"]


def test_vault_split_is_the_elapsed_midpoint():
    assert J.split_of("vault") == pd.Timestamp("2018-07-02 13:00", tz=NY)        # elapsed time; DST moves the clock


def test_chatgpt_checks_flag_the_cases_they_describe():
    a1, a2 = R._load_flag("opposing_path_v1.py"), R._load_flag("two_way_chop_v1.py")
    idx = pd.date_range("2025-03-04 05:00", "2025-03-04 10:00", freq="min", tz=NY, inclusive="left")
    rng = np.random.default_rng(3)
    base = 100 + np.cumsum(rng.normal(0, 0.05, len(idx)))
    base[-15:] = base[-16] + np.linspace(0.3, 4.5, 15)            # a strong, clean 15-minute rise into 10:00
    o = np.r_[base[0], base[:-1]]
    m1 = pd.DataFrame({"open": o, "high": np.maximum(o, base) + 0.01, "low": np.minimum(o, base) - 0.01, "close": base},
                      index=idx)
    t = pd.Timestamp("2025-03-04 10:00", tz=NY)
    assert a1({"ts": t, "side": -1}, m1) and not a1({"ts": t, "side": 1}, m1)
    assert not a2({"ts": t, "side": 1}, m1)
    gap = m1.drop(m1.index[100])
    try:
        a1({"ts": t, "side": -1}, gap)
        raise AssertionError("a gap must make the check unavailable")
    except ValueError:
        pass
