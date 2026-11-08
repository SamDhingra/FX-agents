"""US30 one-stock reversal (registered Nov 7 2026): Dow membership, the decision kernel, a synthetic day end to end,
the counts-first rule and the vault gate."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import dow_data as DD
from fxagents import dow_reversal as R
from tests.test_breakout import frame

NY = "America/New_York"


def test_membership():
    assert len(DD.members("2016-01-04")) == 30 and "GE" in DD.members("2018-06-25") and "WBA" in DD.members("2018-06-26")
    m = DD.members("2026-07-01")
    assert {"GOOGL", "NVDA", "SHW", "AMZN", "AMGN", "HON", "CRM"} <= set(m) and not {"VZ", "INTC", "DOW", "XOM"} & set(m)
    assert "UTX" in DD.members("2020-04-02") and "RTX" in DD.members("2020-04-03") and "RTX" not in DD.members("2020-08-31")
    p = DD.periods()
    assert p["DD"] == [(pd.Timestamp("2016-01-01"), pd.Timestamp("2017-08-31"))]
    assert p["AAPL"] == [(pd.Timestamp("2016-01-01"), pd.Timestamp("2026-09-30"))]


def test_kernel_matches_the_worked_example():
    # one stock +$8, gross $20 → 40%; then the leader −$0.20, 19 others down; US30 +70 then 57 retained
    f = [8.0] + [0.5] * 20 + [-0.25] * 9                    # gross = 8 + 10 + 2.25 = 20.25 → 39.5%
    g = [-0.2] + [-0.1] * 19 + [0.05] * 10
    side, info = R.side_of(f, g, 70, 57, 30)
    assert side == -1 and info["share"] == pytest.approx(8 / 20.25)
    assert R.side_of(f, g, 70, 35, 30)[0] == 0                # already gave back below 70%
    assert R.side_of([8.0] + [0.5] * 20 + [-0.25] * 9, [1.0] + [-0.1] * 19 + [0.05] * 10, 70, 57, 30)[1] == "leader kept going"
    assert R.side_of(f, [-0.2] + [-0.1] * 10 + [0.05] * 19, 70, 57, 30)[1] == "no breadth turn"
    broad = [0.6 + 0.01 * i for i in range(25)] + [-0.1] * 5   # nobody dominates, no tie
    assert R.side_of(broad, [0.0] + [-0.1] * 19 + [0.05] * 10, 70, 57, 30)[1] == "not concentrated"
    assert R.side_of(broad, [0.0] + [-0.1] * 19 + [0.05] * 10, 70, 57, 30, control=True)[0] == -1


DAY = pd.Timestamp("2025-03-04")


def _stocks(tmp_path, leader_jump=8.0):
    """Members flat at $100; from 10:10 to 10:25 the first member rises leader_jump, others +0.5 / −0.25;
    10:25 → 10:30 the leader holds, 19 others slip."""
    root = tmp_path / "dow"
    idx = pd.date_range(DAY.tz_localize(NY) + pd.Timedelta(hours=9, minutes=30), periods=390, freq="1min")
    mins = (idx - idx[0]) / pd.Timedelta("1min")
    for k, s in enumerate(DD.members(DAY)):
        f = leader_jump if k == 0 else 0.5 if k <= 20 else -0.25
        g = -0.2 if k == 0 else -0.1 if k <= 19 else 0.05
        px = 100 + np.clip((mins - 40) / 15, 0, 1) * f + np.clip((mins - 55) / 5, 0, 1) * g
        (root / s).mkdir(parents=True)
        pd.DataFrame({"ts": idx.tz_convert("UTC"), "c": px}).to_csv(root / s / f"{DAY.to_period('M')}.csv.gz", index=False)
    return root


def _us30():
    """US30 mid: quiet ±5 wiggle; +70 from 10:10 to 10:25, back to +57 at 10:30, then falls 40 over 20 min."""
    idx = pd.date_range(DAY.tz_localize(NY), periods=1440, freq="1min")
    mins = ((idx - idx[0]) / pd.Timedelta("1min")).to_numpy()
    t0 = 10 * 60 + 10
    px = 40000 + 5 * np.sin(mins / 3) + np.clip((mins - t0) / 15, 0, 1) * 70 - np.clip((mins - t0 - 15) / 5, 0, 1) * 13 \
        - np.clip((mins - t0 - 20) / 20, 0, 1) * 40
    m1 = frame(px, start=str(idx[0].tz_convert("UTC").tz_localize(None)), spread=1.5)
    for side in ("bid", "ask"):                                 # realistic bar ranges: 5-min ATR ≈ 25 points
        m1[f"{side}_h"] += 12; m1[f"{side}_l"] -= 12
    m1["m_h"] += 12; m1["m_l"] -= 12
    m1.index = m1.index.tz_convert(NY)
    return R.US30(m1)


def test_synthetic_day_end_to_end(tmp_path):
    root = _stocks(tmp_path)
    r = R.scan_day(DAY, _us30(), root)
    rule = r["rule"]
    assert rule is not None and rule["status"] == "filled" and rule["side"] == -1
    assert rule["T"] == DAY.tz_localize(NY) + pd.Timedelta(hours=10, minutes=30)
    assert rule["leader"] == DD.members(DAY)[0] and rule["R"] > 0 and rule["exit_reason"] == "time"
    assert rule["rest_continued"] in (True, False)


def test_no_signal_without_a_dominant_leader(tmp_path):
    r = R.scan_day(DAY, _us30(), _stocks(tmp_path, leader_jump=0.6))
    assert r["rule"] is None


def test_counts_first_and_vault_gate(tmp_path, monkeypatch):
    days = pd.bdate_range("2021-01-04", periods=300)
    few = pd.DataFrame({"day": days[:50], "R": 1.0, "R_2x": 0.9, "bps": 3.0, "d": 0.5, "ctrl_R": 0.5, "exit_reason": "time"})
    j = R.judge(few, days, pd.Timestamp("2021-06-01"))
    assert j["inconclusive"] and not j["pass"]
    assert "Inconclusive" in R.report({"stage": "seen", "period": ["a", "b"], "split": "x",
                                       "counts": {"days": 300, "scans": 1, "data_gaps": 0, "rule_signals": 50,
                                                  "rule_filled": 50, "ctrl_filled": 0, "refused": {}}, "result": j})
    monkeypatch.setattr(R, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="only after a seen pass"):
        R.run_stage("vault")
    (tmp_path / "dow_reversal_seen").mkdir()
    (tmp_path / "dow_reversal_seen/summary.json").write_text(json.dumps({"result": {"pass": False}}))
    with pytest.raises(SystemExit, match="only after a seen pass"):
        R.run_stage("vault")


def test_fetcher_never_needs_keys_in_code(tmp_path, monkeypatch):
    calls = []

    class S:
        def get(self, url, params, timeout):
            calls.append((url, dict(params)))
            class Resp:
                status_code = 200
                def json(self_):
                    ts = pd.Timestamp(params["start"]).tz_convert(NY).normalize() + pd.Timedelta(hours=10)
                    return {"bars": [{"t": ts.tz_convert("UTC").isoformat(), "c": 1.0}], "next_page_token": None}
            return Resp()
    monkeypatch.setattr(DD.time, "sleep", lambda s: None)
    man = DD.fetch("2020-03-15", "2020-04-10", root=tmp_path, session=S(), feed="sip")
    assert "UTX/2020-03" in man and "RTX/2020-04" in man and "UTX/2020-05" not in man
    utx = [p for u, p in calls if "/UTX/" in u]
    assert utx and all(p["asof"] == "2020-03-15" and p["adjustment"] == "raw" for p in utx)
    assert all(p["asof"] == "2020-04-03" for u, p in calls if "/RTX/" in u)
    n = len(calls)
    DD.fetch("2020-03-15", "2020-04-10", root=tmp_path, session=S(), feed="sip")
    assert len(calls) == n                                      # resumable: nothing re-fetched


def test_stage_run_is_inconclusive_on_a_tiny_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "OUT", tmp_path)
    monkeypatch.setitem(R.STAGES, "seen", (("holdout_m1", "dev_m1"), "2025-03-01", "2025-03-31", "2025-03-15"))
    us = _us30()
    m1 = us.m1.copy()
    m1.index = m1.index.tz_convert("UTC")
    exp = tmp_path / "exp"
    for s in ("holdout_m1", "dev_m1"):
        (exp / s).mkdir(parents=True)
    m1[[c for c in m1.columns if not c.startswith("m_")]].reset_index(names="time").to_csv(exp / "dev_m1" / "US30_M1.csv.gz", index=False)
    s = R.run_stage("seen", root_export=exp, stocks=_stocks(tmp_path))
    assert s["counts"]["rule_filled"] == 1 and s["result"]["inconclusive"]
    rep = (tmp_path / "dow_reversal_seen/report.md").read_text()
    assert "Counts (read first)" in rep and "Inconclusive" in rep and "avg R" not in rep
