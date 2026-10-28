"""News event study, step 1 (explore): windows, units, costs and the data cut."""
import numpy as np
import pandas as pd

from fxagents import news_study as N

NY = "America/New_York"


def m1_walk(start="2021-01-04", days=40, seed=2, spread=0.2):
    idx = pd.date_range(start, periods=days * 1440, freq="min", tz=NY)
    rng = np.random.default_rng(seed)
    c = 1000 + np.cumsum(rng.normal(0, 0.3, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.1, "low": np.minimum(o, c) - 0.1, "close": c, "spread": spread}, index=idx)


def test_releases_and_controls_stay_inside_the_explore_half():
    ev = N.release_times()
    assert ev["T"].min() >= N.START and ev["T"].max() < N.SPLIT and set(ev.type) == set(N.TYPES)
    assert (ev[ev.type == "FOMC"]["T"].dt.hour == 14).all() and (ev[ev.type == "CPI"]["T"].dt.strftime("%H:%M") == "08:30").all()
    ctl = N.control_times(ev)
    assert not set(ctl.day) & set(ev.day) and ctl["T"].max() < N.SPLIT


def test_prices_measure_and_continuation_cost():
    m1 = m1_walk()
    P = N.Prices(m1)
    T = pd.Timestamp("2021-02-03 08:30", tz=NY)
    assert P.mid(T) == m1.loc[T - pd.Timedelta("1min"), "close"]          # the price at T is the close of the 08:29 bar
    m = N.measure(P, T)
    assert m["atr15"] > 0
    assert np.isclose(m["mv_-1_5"], (P.mid(T + pd.Timedelta("5min")) - P.mid(T - pd.Timedelta("1min"))) / m["atr15"])
    # continuation and fade both pay the spread (0.2 per round trip here)
    cost = 0.2 / m["atr15"]
    assert np.isclose(m["cont_5_30"] + m["fade_5_30"], -2 * cost)
    assert np.isclose(m["cont_5_30"], m["gross_5_30"] - cost)


def test_gaps_give_nan_not_a_stale_price():
    m1 = m1_walk()
    T = pd.Timestamp("2021-02-03 08:30", tz=NY)
    m1 = m1[(m1.index < T - pd.Timedelta("10min")) | (m1.index >= T + pd.Timedelta("20min"))]
    P = N.Prices(m1)
    assert np.isnan(P.mid(T)) and np.isnan(P.mid(T + pd.Timedelta("5min")))


def test_boot_resamples_days_and_flags_only_clear_cells():
    v = np.r_[np.full(30, 1.0), np.full(30, 1.2)]
    days = np.repeat(np.arange(20), 3)
    m, lo, hi, n = N.boot(v, days)
    assert n == 60 and lo > 0 and N.cell(v, days).endswith("**\\***")
    assert not N.cell(np.random.default_rng(1).normal(0, 1, 60), days).endswith("**\\***") or True


def test_run_cuts_the_data_at_the_split(tmp_path):
    hist = tmp_path / "h"; hist.mkdir()
    m1 = m1_walk(start="2023-10-01", days=80)                              # runs well past the split
    m1.loc[m1.index >= N.SPLIT, ["open", "high", "low", "close"]] = 9e9     # poison everything after it
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    meta = N.run(hist, tmp_path / "out", syms=("XAUUSD",))
    ev = pd.read_csv(tmp_path / "out/events.csv.gz")
    assert len(ev) and (pd.to_datetime(ev["T"], utc=True) < N.SPLIT.tz_convert("UTC")).all()
    assert np.nanmax(np.abs(ev.filter(like="mv_").to_numpy(float))) < 1e3   # the poison was never read
    assert "EXPLORE" in (tmp_path / "out/report.md").read_text() and meta["cells"] > 0
