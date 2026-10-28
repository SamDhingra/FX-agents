"""M15 timing (registered Oct 28 2026): replay parity with research.run_job, the two rules, look-ahead, the judge."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fxagents import m15_timing as T
from fxagents import research
from fxagents.config import load_config

TZ = "America/New_York"


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("FX_NO_LOCAL_CONFIG", "1")
    c = load_config()
    c["history_dir"] = str(tmp_path / "history")
    c["playbook"] = {}
    return c


def market(seed=3, start="2025-03-03 00:00", days=12):
    idx = pd.date_range(start, periods=days * 1440, freq="1min", tz=TZ)
    idx = idx[(idx.dayofweek < 5) & (idx.hour != 17)]
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 0.4, len(idx)))
    o = np.r_[c[0], c[:-1]]
    m1 = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.15, "low": np.minimum(o, c) - 0.15, "close": c,
                       "volume": 1.0, "spread": 0.3}, index=idx)
    h1 = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return m1, h1


def recorded(cfg, monkeypatch, m1, h1, tf="5min", n=60, seed=1):
    """Trades written by research.run_job itself (fake signals, everything else real)."""
    rng = np.random.default_rng(seed)

    def fake_signals(st, df, ctx):
        ix = sorted(rng.choice(np.arange(400, len(df) - 200), n, replace=False))
        out = []
        for i in ix:
            sd = int(rng.choice([1, -1]))
            out.append(SimpleNamespace(i=int(i), side=sd, stop=float(df["close"].iloc[i]) - sd * float(rng.uniform(1.5, 6))))
        return out
    monkeypatch.setattr(research, "load", lambda cfg_, sym: (m1, h1))
    monkeypatch.setattr(research, "bias_frame", lambda h1_, when, close_at_when=None, weights=None:
                        pd.DataFrame({"score": np.where(np.arange(len(when)) % 2, 0.9, -0.9)}, index=when))
    monkeypatch.setattr(research, "_signals", fake_signals)
    monkeypatch.setattr(research, "news_block", lambda ts: False)
    cfg["bias"]["min_align"] = -2.0                                    # let both sides through
    cfg["research"] = {"only_params": {"ict_2022": {}}}
    rows = pd.DataFrame(research.run_job((cfg, "XAUUSD", tf, ["ict_2022"])))
    rows = research.own_trades(rows)
    rows["day"] = rows["day"].astype(str)
    return rows


def test_plain_replay_reproduces_run_job(cfg, monkeypatch):
    m1, h1 = market()
    rows = recorded(cfg, monkeypatch, m1, h1)
    assert len(rows) > 20
    rows = rows.reset_index(drop=True).assign(kid=lambda x: np.arange(len(x)))
    out = T.replay_symbol(cfg, rows, m1, None, None, None)
    a = rows.merge(out, on="kid")
    assert a.ok.all()
    assert (np.abs(a.base_1x - a.r) < 1e-9).mean() == 1.0
    assert a.base_2x.mean() < a.base_1x.mean()                        # twice the spread costs on average


def test_late_entry_waits_for_the_turn_and_cancels_on_the_stop(cfg):
    m1, _ = market(days=6)
    A = T.Arrays(cfg, m1, "5min")
    m = research.mgmt_profiles(cfg, "5min")["std"]
    hits = {"entered": 0, "stop_first": 0}
    for i in range(300, len(A.close_ts) - 300, 7):
        j0 = int(A.j_of[i])
        if j0 < 0:
            continue
        for side in (1, -1):
            q = A.ref15(j0)
            assert A.lab15[q] <= A.c1ns[j0] and (q + 1 >= len(A.lab15) or A.lab15[q + 1] > A.c1ns[j0])
            tr = T.Trade(i, j0, side, A.C[j0] - side * 2.0, m, False, 240.0)
            r, k, why = T.late_entry(A, tr, A.hs)
            if why == "entered":
                qk = q + k
                jk = A.g15[qk]
                assert jk > j0 and (A.c15[qk] - A.o15[qk]) * side > 0
                prev = A.l15[qk - 1] if side < 0 else A.h15[qk - 1]
                assert (A.c15[qk] - prev) * side > 0
            hits[why] = hits.get(why, 0) + 1
    assert hits["entered"] > 0 and hits["stop_first"] > 0


def test_decisions_never_read_after_the_decision_minute(cfg):
    m1, _ = market(days=6)
    A = T.Arrays(cfg, m1, "5min")
    m = research.mgmt_profiles(cfg, "5min")["std"]
    i = 700
    j0 = int(A.j_of[i])
    tr = T.Trade(i, j0, -1, A.C[j0] + 2.0, m, False, 240.0)
    q = A.ref15(j0)
    fires = T.inval_minutes(A, tr)
    k1 = fires[0][1] if fires else None
    # poison everything after the first decision minute: the reference candle and the first firing can't change
    cut = (k1 if k1 is not None else j0 + 200) + 1
    m2 = m1.copy()
    m2.iloc[cut:, :4] = 9e9
    B = T.Arrays(cfg, m2, "5min")
    assert B.ref15(j0) == q and B.h15[q] == A.h15[q] and B.l15[q] == A.l15[q]
    fb = T.inval_minutes(B, T.Trade(i, j0, -1, A.C[j0] + 2.0, m, False, 240.0))
    if k1 is not None:
        assert fb[0][1] == k1                                          # the same first M15 close fires


def test_inval_exit_only_before_the_first_target(cfg):
    O = np.array([100, 100, 100.5, 101, 102, 101.8, 101.5, 101.2, 101.0, 100.8], float)
    C, H, L = O.copy(), O + 0.05, O - 0.05
    n = len(C)
    m = dataclasses.replace(research.mgmt_profiles(cfg, "15min")["std"], inval_exit=True)
    fire = T.Fire([6])
    r = research.simulate_live(O, H, L, C, np.arange(n), 0, 1, 99.0, m, 0.0, np.zeros(n, bool), None, 480.0, False, an={"inval": fire})
    assert r["exit_reason"] != "m15_invalidation"                    # +1R reached at bar 3, after it the runner rules
    m0 = dataclasses.replace(m, rr=5.0)
    r = research.simulate_live(O, H, L, C, np.arange(n), 0, 1, 99.0, m0, 0.0, np.zeros(n, bool), None, 480.0, False, an={"inval": fire})
    assert r["exit_reason"] == "m15_invalidation" and r["j_exit"] == 6
    assert research.Mgmt().inval_exit is False if hasattr(research, "Mgmt") else True


def test_run_seen_end_to_end_and_vault_needs_a_pass(cfg, monkeypatch, tmp_path):
    m1, h1 = market(start="2021-03-01 00:00", days=40)
    rows = recorded(cfg, monkeypatch, m1, h1, n=400)
    src = tmp_path / "src"; src.mkdir()
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, h1), hist / "XAUUSD.pkl")
    rows.assign(ts=rows.ts.astype(str), exit_ts=rows.exit_ts.astype(str)).to_csv(src / "trades_seen_x_5m.csv.gz", index=False)
    res = T.run("seen", src, hist, tmp_path / "out", cfg=cfg)
    assert set(res) == set(T.CHECKS)
    txt = (tmp_path / "out/report.md").read_text()
    assert "Engine check" in txt and "100.0%" in txt and "A m15_turn_entry" in txt and "B m15_inval_exit" in txt
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        T.run("vault", src, hist, tmp_path / "v", cfg=cfg)


def test_replay_mismatch_refuses_to_judge(cfg, monkeypatch, tmp_path):
    m1, h1 = market(start="2021-03-01 00:00", days=20)
    rows = recorded(cfg, monkeypatch, m1, h1, n=100)
    rows["r"] = rows["r"] + 0.5                                        # as if the exit settings changed since
    src = tmp_path / "src"; src.mkdir()
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, h1), hist / "XAUUSD.pkl")
    rows.assign(ts=rows.ts.astype(str)).to_csv(src / "trades_seen_x_5m.csv.gz", index=False)
    res = T.run("seen", src, hist, tmp_path / "out", cfg=cfg)
    assert res["engine_match"] < 0.98 and "nothing is judged" in (tmp_path / "out/report.md").read_text()
