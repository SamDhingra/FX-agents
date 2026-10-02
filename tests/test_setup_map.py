"""90-day setup map: aggregation, shrunk priors, grid, and a real compute pass."""
from __future__ import annotations

import pandas as pd
import pytest

from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.setup_map import MIN_N, SetupMap, SetupMapHolder, compute
from fxagents.sim import synth_1m
from fxagents.strategies import build_strategy, default_specs

CFG = load_config("config.yaml")


def rows(sym, sid, hour, wd, rs, tf="5m"):
    return [[sym, sid, tf, hour, wd, r] for r in rs]


def test_prior_shrinks_thin_cells_toward_hour_and_overall():
    data = {"built_at": "x", "rows":
            rows("NDQ", "smc_ifvg:5m@v1", 9, 1, [2.0, 2.0])                  # 2 lucky Tuesday trades
            + rows("NDQ", "smc_ifvg:5m@v1", 9, 2, [-1.0] * 20)               # 20 losing Wednesdays at 9
            + rows("NDQ", "smc_ifvg:5m@v1", 14, 3, [0.2] * 40)}
    m = SetupMap(data)
    tue = m.prior("NDQ", "smc_ifvg:5m@v1", 9, 1)
    assert tue["n"] == 2 and tue["exp"] == 2.0
    assert tue["shrunk_exp"] < 0.5                                            # 2 trades can't make it a star
    wed = m.prior("NDQ", "smc_ifvg:5m@v1", 9, 2)
    assert wed["shrunk_exp"] < tue["shrunk_exp"] < 2.0
    # a tuned version with no history of its own falls back to its family
    v7 = m.prior("NDQ", "smc_ifvg:5m@v7", 14, 3)
    assert v7["level"] == "family" and v7["shrunk_exp"] > 0
    assert m.prior("SPX", "smc_ifvg:5m@v1", 9, 1)["level"] == "none"


def test_grid_filters_and_marks_thin_cells():
    data = {"rows": rows("NDQ", "ict_ote:5m@v1", 10, 0, [1.0] * 6) + rows("SPX", "ict_ote:15m@v1", 10, 1, [-1.0] * 2, "15m")}
    m = SetupMap(data)
    g = m.grid()
    c = g["rows"][0]["cells"]["10"]
    assert c["n"] == 8 and g["min_n"] == MIN_N
    assert m.grid(symbol="NDQ")["rows"][0]["cells"]["10"] == {"n": 6, "w": 1.0, "r": 1.0}
    assert m.grid(tf="15m")["rows"][0]["cells"]["10"]["n"] == 2
    assert m.grid(weekday="1")["rows"][0]["cells"]["10"]["n"] == 2


def test_compute_backtests_every_strategy_with_the_bias_rule(tmp_path):
    tz = CFG["timezone"]
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-06-01", tz=tz), 40, 3, tz)
    h1 = resample_ohlc(m1, "1h")
    strategies = [build_strategy(s) for s in default_specs(tfs=tuple(CFG["timeframes"]["entry"]))]
    res = compute(CFG, strategies, {"NDQ": (m1, h1)}, "test")
    assert res["trades"] == len(res["rows"]) > 20
    assert {r[2] for r in res["rows"]} <= {"5m", "15m"}
    assert all(0 <= r[3] < 24 and 0 <= r[4] < 7 for r in res["rows"])
    h = SetupMapHolder(str(tmp_path / "setup_map.json"))
    h.save(res)
    h2 = SetupMapHolder(str(tmp_path / "setup_map.json"))
    assert h2.load() and h2.status["state"] == "ready" and h2.map.grid()["rows"]


def test_best_now_pools_timeframes_by_family_and_ranks_by_shrunk_expectancy():
    data = {"rows": rows("NDQ", "smc_ifvg:5m@v1", 9, 1, [1.0, 1.0]) + rows("NDQ", "smc_ifvg:15m@v1", 9, 2, [1.0, 0.5])
            + rows("NDQ", "ict_ote:5m@v1", 9, 1, [-1.0] * 4) + rows("NDQ", "ict_ote:5m@v1", 10, 1, [1.0])}
    m = SetupMap(data)
    best = m.best_now(["smc_ifvg:5m@v1", "ict_ote:5m@v1"], ["NDQ"], 9, 1)
    assert [b["setup"] for b in best] == ["smc_ifvg", "ict_ote"]
    assert best[0]["hour_n"] == 4                                   # 5m + 15m pooled
