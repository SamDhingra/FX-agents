"""Replay backtest pieces: the signal oracle, the replay feed's period, and the report maths."""
from __future__ import annotations

import copy
import sqlite3

import pandas as pd
import pytest

from fxagents.backtest_report import book_report
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.journal import Journal
from fxagents.replay import ReplayFeed, SignalOracle
from fxagents.setup_map import save_history
from fxagents.sim import synth_1m
from fxagents.state import LiveState
from fxagents.strategies import Strategy, build_strategy, default_specs

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


def test_oracle_matches_a_live_style_window_scan_on_the_last_bar():
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-05-01", tz=TZ), 20, 9, TZ)
    orc = SignalOracle({"NDQ": m1}, ["5min"], m1.index[0])
    df_all = resample_ohlc(m1, "5min")
    strats = [build_strategy(s) for s in default_specs(tfs=("5min",))]
    checked = same = 0
    for st in strats:
        for i in range(700, len(df_all), 97):
            w = df_all.iloc[i - 699:i + 1]
            a = {(r.side, round(r.entry, 3)) for r in st._scan_full(w, Strategy._context(w)) if r.i == len(w) - 1}
            b = {(r.side, round(r.entry, 3)) for r in orc.at(st, "NDQ", "5min", df_all.index[i])}
            checked += 1; same += a == b
    assert same / checked > 0.98
    c = orc.ctx_at("NDQ", "5min", df_all.index[800])
    assert len(c["rsi"]) == 801                                      # nothing after the bar is visible
    assert orc.at(strats[0], "NDQ", "5min", pd.Timestamp("2030-01-01", tz=TZ)) is None


def test_replay_feed_splits_warmup_and_period(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    for j, sym in enumerate(cfg["instruments"]):
        m1 = synth_1m(1000 + j, 0.01, pd.Timestamp("2026-06-01", tz=TZ), 30, j, TZ)
        save_history(cfg, sym, m1, resample_ohlc(m1, "1h"))
    f = ReplayFeed(cfg, Bus(), LiveState(), tmp_path, days=10)
    sym = next(iter(cfg["instruments"]))
    assert f.days == 10 and f.history(sym).index[-1] < f.split <= f.frames[sym].index[-1]
    assert f.history(sym).index[0] >= f.warm_start
    big = ReplayFeed(cfg, Bus(), LiveState(), tmp_path, days=400)    # asks for more than the cache holds
    assert big.days < 30


def test_report_metrics(tmp_path):
    p = tmp_path / "journal.sqlite"
    Journal(str(p))
    db = sqlite3.connect(str(p))
    rows = [("a", "NDQ", "smc_ifvg:5m@v1", "2026-09-01T09:00", "2026-09-01T09:40", 9, 1.0, 500.0, "target"),
            ("b", "SPX", "ict_ote:5m@v1", "2026-09-01T10:00", "2026-09-01T10:30", 10, -1.0, -500.0, "stop"),
            ("c", "NDQ", "smc_ifvg:5m@v1", "2026-09-02T09:00", "2026-09-02T10:00", 9, 2.0, 1000.0, "trail_stop"),
            ("d", "NDQ", "smc_ifvg:5m@v1", "2026-09-03T09:00", "2026-09-03T09:20", 9, -1.0, -500.0, "stop")]
    db.executemany("INSERT INTO trades(id,symbol,strategy,opened,closed,hour,r_multiple,realized,exit_reason,status) "
                   "VALUES(?,?,?,?,?,?,?,?,?,'closed')", rows)
    eq = [("2026-09-01T08:00-04:00", 100000), ("2026-09-01T09:40-04:00", 100500), ("2026-09-01T10:30-04:00", 100000),
          ("2026-09-02T10:00-04:00", 101000), ("2026-09-03T09:20-04:00", 100500)]
    db.executemany("INSERT INTO equity VALUES(?,?,0)", eq)
    db.commit()
    r = book_report(p, 100000)
    s = r["summary"]
    assert s["trades"] == 4 and s["win_rate"] == 0.5 and s["sum_r"] == 1.0
    assert s["profit_factor"] == pytest.approx(1.5) and s["pnl"] == 500.0 and s["return_pct"] == 0.005
    assert s["max_dd"] == -500.0 and s["max_losing_streak"] == 1
    assert {x["key"]: x["n"] for x in r["by_setup"]} == {"smc_ifvg": 3, "ict_ote": 1}
    assert [d["date"] for d in r["days"]] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert r["months"][0]["key"] == "2026-09" and r["trades"][0]["id"] == "d"


def test_whatif_simulates_blocked_signals_by_reason(tmp_path):
    from fxagents.backtest_report import filter_whatif
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    m1 = synth_1m(25000, 0.012, pd.Timestamp("2026-06-01", tz=TZ), 10, 3, TZ)
    save_history(cfg, "NDQ", m1, resample_ohlc(m1, "1h"))
    df = resample_ohlc(m1, "5min")
    Journal(cfg["storage"]["db_path"])
    db = sqlite3.connect(cfg["storage"]["db_path"])
    rows = []
    for k, i in enumerate(range(300, 1500, 100)):
        c = float(df["close"].iloc[i]); ts = (df.index[i] + pd.Timedelta("5min")).isoformat()
        act, why, q, cf = [("taken", "qty 1", 0.7, 0.6), ("filtered", "counter to BEARISH bias", None, None),
                           ("skipped", "Jev grade 0.62 below gate", 0.62, 0.3)][k % 3]
        rows.append((ts, "NDQ", "smc_ifvg:5m@v1", "LONG", c, c - 20, act, why, q, cf))
    db.executemany("INSERT INTO signals(ts,symbol,strategy,side,entry,stop,action,why,quality,confidence) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    w = {x["key"]: x for x in filter_whatif(cfg["storage"]["db_path"], cfg)}
    assert w["taken"]["n"] == 4 and w["blocked: counter to bias"]["n"] == 4
    assert w["blocked: Jev confidence"]["n"] == 4                      # quality passed, confidence failed
    assert all(x["avg_r"] >= -1.01 for x in w.values())                # never worse than a full stop (no slippage)
