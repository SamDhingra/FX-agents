"""EMA21 round 3 (registered Nov 7 2026): same rule code as simple_rules, the live-book 3×ATR stop, the two judged
configurations, the random-timing control and the stage gates."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import ema_v3 as V
from fxagents.simple_rules import run_ema21_rsi55
from tests.test_breakout import frame


def walk(n_days=25, seed=3, start="2025-03-03 00:00", vol=0.6):
    rng = np.random.default_rng(seed)
    px = 2000 + np.cumsum(rng.normal(0, vol, 1440 * n_days))
    m1 = frame(px, start=start, spread=0.3)
    m1 = m1[m1.index.dayofweek < 5].copy()
    m1["bid_l"] -= np.abs(rng.normal(0, 0.3, len(m1)))          # some intrabar range so stops can be touched
    m1["volume"] = 100
    return m1


def test_ref_without_stop_is_the_original_rule():
    m1 = walk()
    mk = V.Market(m1)
    mine = mk.run("ref", stop=False)
    orig = pd.DataFrame(run_ema21_rsi55(m1, "day", b=mk.b))
    assert len(mine) == len(orig) > 10
    assert (mine.entry_time.values == orig.entry_time.values).all()
    assert np.allclose(mine.R.to_numpy(), orig.R.to_numpy())


def test_configs_nest_and_the_stop_only_cuts_losses():
    mk = V.Market(walk(seed=4))
    ref, a, b = (mk.run(c) for c in ("ref", "A_norsi", "B_h1"))
    sig = lambda c: {i for i in range(1, len(mk.b)) if mk.ok(i) and mk.signal(i, c)}
    assert sig("ref") <= sig("A_norsi") and sig("B_h1") <= sig("ref") and len(sig("A_norsi")) > len(sig("ref"))
    stopped = ref[ref.exit_reason == "stop"]
    assert (stopped.R >= -V.STOP_ATR - 1).all()                     # at most a gap beyond 3 ATR
    assert np.allclose(ref.R_stop_units, ref.R / 3)


def test_stop_fills_at_the_level():
    m1 = walk(seed=4)
    mk = V.Market(m1)
    r = mk.run("A_norsi", stop=False).iloc[3]                   # a real trade: crash a minute inside it
    j = m1.index.get_loc(r.entry_time) + 2
    assert m1.index[j] < r.exit_time
    m1.iloc[j, m1.columns.get_loc("bid_l")] = r.entry - 5 * r.atr
    t = V.Market(m1).run("A_norsi")
    s = t[t.entry_time == r.entry_time].iloc[0]
    assert s.exit_reason == "stop" and s.exit_time == m1.index[j]
    assert s.exit == pytest.approx(r.entry - 3 * r.atr) and s.R == pytest.approx(-3)


def test_random_control_same_hour_and_half():
    mk = V.Market(walk(seed=5))
    t = mk.run("A_norsi")
    split = pd.Timestamp("2025-03-17", tz="UTC")
    c = mk.random_control(t, split)
    assert len(c) == len(t) and np.isfinite(c).mean() > 0.9
    assert (c == mk.random_control(t, split)).all()                  # seeded


def test_stage_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="needs the dev result"):
        V.allowed("holdout")
    d = tmp_path / "ema_v3_dev"; d.mkdir()
    rows = [{"symbol": "NDQ", "config": "A_norsi", "pass": False, "lo": 0.1}, {"symbol": "NDQ", "config": "ref", "pass": None}]
    (d / "summary.json").write_text(json.dumps({"rows": rows}))
    with pytest.raises(SystemExit, match="nothing passed dev"):
        V.allowed("holdout")
    rows[0]["pass"] = True
    (d / "summary.json").write_text(json.dumps({"rows": rows}))
    assert V.allowed("holdout") == [("NDQ", "A_norsi")]
    h = tmp_path / "ema_v3_holdout"; h.mkdir()
    hr = [{"symbol": "NDQ", "config": "A_norsi", "pass": True, "lo": 0.02}, {"symbol": "US30", "config": "B_h1", "pass": True, "lo": 0.05}]
    (h / "summary.json").write_text(json.dumps({"rows": hr}))
    assert V.allowed("vault") == [("US30", "B_h1")]                   # one nominee: highest holdout lower bound


def test_dev_stage_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "OUT", tmp_path)
    src = tmp_path / "exp"; src.mkdir()
    walk(n_days=30, seed=6).reset_index(names="time").to_csv(src / "NDQ_M1.csv.gz", index=False)
    s = V.run_stage("dev", src=src, out=tmp_path / "ema_v3_dev", syms=("NDQ",))
    assert {r["config"] for r in s["rows"]} == {"ref", "A_norsi", "B_h1"}
    rep = (tmp_path / "ema_v3_dev/report.md").read_text()
    assert "vs random" in rep and "Code check" in rep and ("Passed: none" in rep or "PASS" in rep)
