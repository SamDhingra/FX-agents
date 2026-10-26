"""Playbook two-step test: pieces/gates, and 2016–2020 is only opened for cells that pass step 1."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import fxagents.playbook_test as P
from tests.test_gemini_smc import frame, walk


def test_gates_and_pieces():
    ts = pd.date_range("2021-01-04 10:00", periods=600, freq="3D", tz="America/New_York")
    t = pd.DataFrame({"ts": ts, "day": ts.date, "r": np.where(np.arange(600) % 2, 1.3, -0.9), "cost_r": 0.05})
    st = P.judge(t, True)
    assert st["n"] == 600 and st["avg"] > 0 and st["pass"]
    assert set(st["pieces"]) == set(P.PIECES) and all(v[1] for v in st["pieces"].values())
    t2 = t.copy()
    t2.loc[pd.to_datetime(t2.ts).dt.tz_localize(None) < pd.Timestamp("2024-10-01"), "r"] = -0.2
    assert not P.judge(t2, True)["pass"]                       # a clean piece negative → no pass


def _export(root: Path, name: str, seed: int):
    d = root / "data/export" / name
    d.mkdir(parents=True)
    m = frame(walk(n_days=30, seed=seed))
    m = m[[c for c in m.columns if not c.startswith("m_")]]
    m.index.name = "time"
    m.to_csv(d / "XAUUSD_M1.csv.gz")


def test_old_data_only_opened_for_passers(tmp_path, monkeypatch):
    for n, s in (("holdout_m1", 1), ("dev_m1", 2)):
        _export(tmp_path, n, s)
    (tmp_path / "data").mkdir(exist_ok=True)
    shutil.copy("config.yaml", tmp_path / "config.yaml")
    cell = {"id": "smc_bos_retest:5m@t", "sym": "XAUUSD", "tf": "5min", "setup": "smc_bos_retest", "variant": "default",
            "params": {}, "mgmt": "std"}
    (tmp_path / "data/playbook.json").write_text(json.dumps({"asof": "x", "cells": [cell]}))
    monkeypatch.chdir(tmp_path)
    opened = []
    real_build = P.build_history
    monkeypatch.setattr(P, "build_history", lambda cfg, sets, syms, dest: (opened.append(sets), real_build(cfg, sets, syms, dest))[1])
    monkeypatch.setattr("sys.argv", ["x", "--out", "o1", "--workers", "1"])
    monkeypatch.setattr(P, "judge", lambda t, need: {"n": 0, "pass": False})
    P.main()
    assert opened == [["holdout_m1", "dev_m1"]] and "not opened" in Path("o1/report.md").read_text()
    _export(tmp_path, "old_m1", 3)
    st = {"n": 150, "pass": True, "win": .5, "avg": .1, "lo": .01, "hi": .2, "avg2x": .05, "h1": .1, "h2": .1, "cost": .05,
          "pieces": {k: (0.1, 50) for k in P.PIECES}}
    monkeypatch.setattr(P, "judge", lambda t, need: dict(st))
    monkeypatch.setattr("sys.argv", ["x", "--out", "o2", "--workers", "1"])
    P.main()
    assert opened[-1][0] == "old_m1" and "untouched 2016 → 2020" in Path("o2/report.md").read_text()


def test_judge_only_runs_the_frozen_cell_once_on_old_data(tmp_path, monkeypatch):
    _export(tmp_path, "old_m1", 4)
    shutil.copy("config.yaml", tmp_path / "config.yaml")
    cells = [{"id": "smc_bos_retest:5m@t", "sym": "XAUUSD", "tf": "5min", "setup": "smc_bos_retest", "variant": "default",
              "params": {}, "mgmt": "std"},
             {"id": "other", "sym": "XAUUSD", "tf": "5min", "setup": "smc_bos_retest", "variant": "default", "params": {},
              "mgmt": "std"}]
    (tmp_path / "frozen.json").write_text(json.dumps(cells))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no export expected")))
    monkeypatch.setattr("sys.argv", ["x", "--cells-file", "frozen.json", "--only", "smc_bos_retest:5m@t", "--judge-only",
                                     "--out", "o", "--workers", "1"])
    P.main()
    md = Path("o/report.md").read_text()
    assert "judged once on untouched 2016 → 2020" in md and "smc_bos_retest:5m@t" in md and "| other |" not in md


def test_cells_sharing_signals_run_once_and_each_is_saved_as_it_finishes(monkeypatch, tmp_path):
    calls = []

    def fake_job(job):
        cc, sym, tf, setups = job
        calls.append((sym, tf, setups[0]))
        ts = pd.date_range("2017-03-01 10:00", periods=4, freq="1D", tz="America/New_York")
        return pd.DataFrame({"tf": tf, "variant": P.vkey({}), "mgmt": ["standard", "scalp"] * 2, "ts": ts, "r": [1.0, -1.0, 0.5, 0.2],
                             "busy_self": False, "sym": sym, "setup": setups[0]})

    class Pool:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def map(self, f, jobs): return [f(j) for j in jobs]
    monkeypatch.setattr(P, "run_job_frame", fake_job)
    monkeypatch.setattr(P, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(P, "own_trades", lambda t: t)
    cells = [{"id": "x:3m@a", "sym": "XAUUSD", "tf": "3min", "setup": "x", "mgmt": "standard"},
             {"id": "x:3m@a-scalp", "sym": "XAUUSD", "tf": "3min", "setup": "x", "mgmt": "scalp"},
             {"id": "y:5m@b", "sym": "NDQ", "tf": "5min", "setup": "y", "mgmt": "standard"}]
    saved = []
    out = P.run_cells({"research": {}}, cells, tmp_path, 1, done=lambda c, t: saved.append((c["id"], len(t))))
    assert len(calls) == 2                                            # the scalp twin shares the x replay
    assert saved == [("x:3m@a", 2), ("x:3m@a-scalp", 2), ("y:5m@b", 2)] and set(out) == {c["id"] for c in cells}
