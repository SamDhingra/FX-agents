"""Trade-management replay: a real trade's entry/stop replayed under each rule on bid/ask minutes."""
import sqlite3

import numpy as np
import pandas as pd

from fxagents import mgmt_replay as mr


def path_frame(start, prices, half=0.5):
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz="UTC")
    p = np.asarray(prices, float)
    o, c = np.r_[p[0], p[:-1]], p
    d = pd.DataFrame(index=idx)
    for f, v in (("o", o), ("h", np.maximum(o, c)), ("l", np.minimum(o, c)), ("c", c)):
        d[f"bid_{f}"], d[f"ask_{f}"] = v - half, v + half
    d["volume"] = 1.0
    return d


def test_rules_on_a_trade_that_runs_to_1_5R_then_reverses_to_the_stop():
    # long at ~100.5 (ask), stop 90.5 → R = 10. Up to 115.5 (+1.5R) over 60 min, then down through the stop.
    up = np.linspace(100, 115.5, 61)
    down = np.linspace(115.5, 85, 61)[1:]
    f = path_frame("2026-10-15 14:00", np.r_[up, down, np.full(30, 85)])
    tr = {"symbol": "NDQ", "side": "LONG", "initial_stop": 90.5, "opened": pd.Timestamp("2026-10-15 14:00", tz="UTC"),
          "closed": pd.Timestamp("2026-10-15 14:40", tz="UTC")}
    r = mr.replay(tr, f)
    assert -1.1 < r["stop_only"] < -0.95                       # rode it back to the stop
    assert 0.9 < r["target_1r"] < 1.05                         # banked at +1R
    assert 0.0 < r["be1"] < 0.15                               # breakeven + 0.1R
    assert 0.45 < r["part1_2r"] < 0.6                          # half at +1R, rest at +0.1R
    assert r["target_2r"] < -0.9 and r["target_3r"] < -0.9     # targets never reached
    assert 0.0 < r["trail1"] < 0.6                             # trailed 1R behind the +1.5R best
    assert 0.5 < r["actual_exit"] < 1.0                        # out at 14:40 (about +1R)
    assert r["cut15"] == r["target_2r"]                        # in profit after 15 min → no cut


def test_cut15_cuts_a_trade_that_is_under_water():
    f = path_frame("2026-10-15 14:00", np.r_[np.linspace(100, 97, 20), np.full(30, 97), np.linspace(97, 125, 60)])
    tr = {"symbol": "NDQ", "side": "LONG", "initial_stop": 90.5, "opened": pd.Timestamp("2026-10-15 14:00", tz="UTC"),
          "closed": pd.Timestamp("2026-10-15 15:30", tz="UTC")}
    r = mr.replay(tr, f)
    assert -0.6 < r["cut15"] < 0 and r["target_2r"] > 1.5          # the cut lost the eventual winner


def test_loads_only_intraday_closed_trades(tmp_path):
    p = tmp_path / "j.sqlite"
    from fxagents.journal import Journal
    j = Journal(str(p))
    for i, (o, c) in enumerate([("2026-10-19T10:00:00-04:00", "2026-10-19T11:00:00-04:00"),
                                ("2026-10-10T10:00:00-04:00", "2026-10-10T11:00:00-04:00"),       # too old
                                ("2026-10-19T17:00:00-04:00", "2026-10-21T17:00:00-04:00")]):     # held overnight
        j.db.execute("INSERT INTO trades (id,symbol,side,strategy,status,opened,closed,entry,initial_stop,r_multiple) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)", (f"t{i}", "NDQ", "LONG", "x", "closed", o, c, 100, 90, 0.5))
    j.db.commit()
    rows = mr.load_trades({"live": str(p)}, pd.Timestamp("2026-10-14", tz="America/New_York"))
    assert [r["id"] for r in rows] == ["t0"]
