"""The friend's weekly/daily rule books: his script runs unchanged, and our controls are added (fxagents/weekly_rules)."""
import numpy as np
import pandas as pd

from fxagents import weekly_rules as W


def fake_daily(inst, start_utc, seed=0, drift=0.0006):
    rng = np.random.default_rng(abs(hash(inst)) % 1000 + seed)
    days = pd.bdate_range(pd.Timestamp(start_utc).tz_convert("America/New_York").normalize().tz_localize(None),
                          pd.Timestamp.now().normalize(), freq="C", weekmask="Sun Mon Tue Wed Thu")
    idx = pd.DatetimeIndex([pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(hours=17) for d in days])
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, len(idx))))
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
    sp = c * 2e-4
    df = pd.DataFrame({"bo": o - sp / 2, "bh": h - sp / 2, "bl": l - sp / 2, "bc": c - sp / 2,
                       "ao": o + sp / 2, "ah": h + sp / 2, "al": l + sp / 2, "ac": c + sp / 2}, index=idx)
    for k in "ohlc":
        df["m" + k] = (df["b" + k] + df["a" + k]) / 2
    return df


def test_friends_selftest_still_passes():
    assert W.friend().selftest()


def test_run_adds_swap_controls_and_keeps_his_tables(monkeypatch):
    mod = W.friend()
    monkeypatch.setattr(mod, "fetch_daily", fake_daily)
    txt, summ = W.run(5, ["XAUUSD", "EURUSD", "NDQ"], placebo=3, mod=mod)
    assert "## Our checks" in txt and "# His tables" in txt and "His placebo" in txt
    assert "Random-timing edge" in txt and "| PASS |" in txt and "Every trade of WK" in txt
    assert summ["trades"] > 0 and set(summ["by_variant"]) == set(W.VARIANTS)


def test_swap_charges_fx_less_than_cfds():
    idx = pd.DatetimeIndex([pd.Timestamp("2025-01-06 17:00", tz="America/New_York") + pd.Timedelta(days=d) for d in (0, 30)])
    X = {k: np.array([100.0, 100.0]) for k in ("ao", "bo", "mo")}
    X["ao"] = X["ao"] + 0.01
    fx, _ = W.costs("EURUSD", X, idx, 0, 1)
    cfd, sp = W.costs("NDQ", X, idx, 0, 1)
    assert abs(fx - 30 * 0.006) < 1e-12 and abs(cfd - 30 * 0.018) < 1e-12 and abs(sp - 0.02) < 1e-9


def test_exits_match_his_rule_from_any_entry():
    n = 10
    X = {"bo": np.full(n, 100.), "mc": np.array([100, 101, 102, 103, 99, 98, 97, 96, 95, 94.])}
    e18 = np.full(n, 100.)
    assert W.dy_exit(X, e18, 1, 1) == 5           # first close below the EMA18 is day 4 → out at day 5's open
    assert W.dy_exit(X, e18, 5, -1) is None       # short: never closes above again → still open
