"""Floor exit (registered Nov 9 2026): the trigger, the replay against the research engine, the placebo and the gates."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fxagents import floor_exit as FE
from fxagents import research
from tests.test_m15_timing import cfg, market  # noqa: F401


def test_trigger_needs_a_close_beyond_the_floor_while_losing():
    p = {"cs": np.array([100.5, 99.4, 99.3]), "ok": np.array([True, False, True]), "rx": np.array([-0.2, -0.5, -0.6])}
    assert FE.trigger(p, 1, 99.5) == 2              # 99.4 is beyond but the trade wasn't losing there → the next one
    assert FE.trigger(p, 1, 99.0) == -1             # never closes below 99
    assert FE.trigger(p, 1, 99.4) == 2              # equality doesn't count
    s = {"cs": np.array([100.2, 100.7]), "ok": np.array([True, True]), "rx": np.array([0.0, 0.0])}
    assert FE.trigger(s, -1, 100.5) == 1            # short: a close above the floor


def rows_with_floor(cfg, monkeypatch, m1, h1, depth=0.5, n=80, seed=2):  # noqa: F811
    rng = np.random.default_rng(seed)

    def fake_signals(st, df, ctx):
        out = []
        for i in sorted(rng.choice(np.arange(400, len(df) - 200), n, replace=False)):
            sd = int(rng.choice([1, -1]))
            c = float(df["close"].iloc[i])
            stop = c - sd * float(rng.uniform(2.0, 6.0))
            out.append(SimpleNamespace(i=int(i), side=sd, stop=stop, features={"floor": c - sd * depth * abs(c - stop)}))
        return out
    monkeypatch.setattr(research, "load", lambda cfg_, sym: (m1, h1))
    monkeypatch.setattr(research, "bias_frame", lambda h1_, when, close_at_when=None, weights=None:
                        pd.DataFrame({"score": np.full(len(when), 0.0)}, index=when))
    monkeypatch.setattr(research, "_signals", fake_signals)
    monkeypatch.setattr(research, "news_block", lambda ts: False)
    cfg["bias"]["min_align"] = -2.0
    cfg["research"] = {"only_params": {"ict_2022": {}}, "profiles_only": ["std"]}
    rows = research.own_trades(pd.DataFrame(research.run_job((cfg, "XAUUSD", "5min", ["ict_2022"]))))
    rows["setup"] = "ict_ote"
    return rows


def test_replay_matches_the_engine_and_fires_where_it_should(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1 = market(days=20)
    rows = rows_with_floor(cfg, monkeypatch, m1, h1)
    assert len(rows) > 30 and rows.floor_px.notna().all()
    r = FE.run("seen", cfg=cfg, t=rows, m1s={"XAUUSD": m1}, n_perm=200, out=tmp_path / "fe")
    assert r["engine_match"] >= 0.98 and r["coverage"] >= 0.98
    v = pd.read_csv(tmp_path / "fe/trades.csv.gz")
    fired = v[v.fired.astype(bool)]
    assert len(fired) > 3 and (np.abs(v.cand_1x - v.base_1x) > 1e-12).sum() == len(fired)
    # a fired trade exits at the next minute's open on the executable side, before its baseline exit
    t = fired.iloc[0]
    assert t.cand_1x != t.base_1x and t.cand_1x > -1.5
    assert not v[~v.eligible.astype(bool)].fired.astype(bool).any()
    rep = (tmp_path / "fe/report.md").read_text()
    assert "placebo p" in rep and "Engine check" in rep


def test_placebo_without_shuffling_equals_the_real_rule(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1 = market(days=20, seed=5)
    rows = rows_with_floor(cfg, monkeypatch, m1, h1, depth=0.4)

    class Same:                                     # "permutation" that leaves every depth where it was
        def __init__(self, seed=None): pass
        def permutation(self, x): return np.asarray(x)
        def integers(self, *a, **k): return np.random.default_rng(1).integers(*a, **k)
    real_rng = FE.np.random.default_rng
    monkeypatch.setattr(FE.np.random, "default_rng", lambda seed=None: Same() if seed == FE.SEED_PERM else real_rng(seed))
    r = FE.run("seen", cfg=cfg, t=rows, m1s={"XAUUSD": m1}, n_perm=20, out=tmp_path / "fe")
    assert r["changed"] > 3
    assert r["placebo_mean"] == pytest.approx(r["d"]["mean"], abs=1e-9) and r["p"] == 1.0


def test_vault_needs_a_seen_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(FE, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="only after a seen pass"):
        FE.run("vault", cfg={})
    (tmp_path / "floor_exit_seen").mkdir()
    (tmp_path / "floor_exit_seen/summary.json").write_text(json.dumps({"pass": False}))
    with pytest.raises(SystemExit, match="only after a seen pass"):
        FE.run("vault", cfg={})


def test_setups_record_their_floor():
    from fxagents.strategies import build_strategy
    from fxagents.strategies.base import Strategy
    from fxagents.indicators import resample_ohlc
    m1, _ = market(days=15, seed=9)
    df = resample_ohlc(m1, "15min")
    for name in FE.SETUPS:
        st = build_strategy({"class": name, "tf": "15min", "params": {}})
        sigs = research._signals(st, df, Strategy._context(df))
        for s in sigs[:20]:
            F = s.features["floor"]
            assert (s.entry - F) * s.side >= 0 and (F - s.stop) * s.side > 0     # between entry and stop
