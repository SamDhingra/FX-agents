"""Entry edge vs random timing (registered Nov 5 2026): the replay matches run_job; controls keep side, stop and exit."""
import numpy as np
import pandas as pd
import pytest

from fxagents import entry_edge as E
from fxagents import m15_timing as T
from tests.test_m15_timing import cfg, market, recorded  # noqa: F401  (fixture)


def test_day_pool_matches_research_days(cfg, monkeypatch):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=10)
    rows = recorded(cfg, monkeypatch, m1, h1, tf="5min", n=60)
    A = T.Arrays(cfg, m1, "5min")
    pool = E.day_bars(A)
    for r in rows.itertuples():
        i, _ = A.locate(r.ts)
        assert i in pool[str(r.day)]                         # the real entry is a valid candle of its own day


def test_replay_and_controls(cfg, monkeypatch):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=20)
    rows = recorded(cfg, monkeypatch, m1, h1, tf="5min", n=120)
    rows = rows.reset_index(drop=True).assign(kid=lambda x: np.arange(len(x)), tf="5m")
    out = E.replay(cfg, rows, m1, np.random.default_rng(1))
    a = rows.merge(out, on="kid")
    assert a.ok.all() and (np.abs(a.base_1x - a.r) < 1e-9).mean() == 1.0
    assert a.rand_time_1x.notna().mean() > 0.95 and a.opposite_1x.notna().all()
    assert not np.allclose(a.rand_time_1x, a.base_1x)
    assert a.base_2x.mean() < a.base_1x.mean() and a.opposite_2x.mean() < a.opposite_1x.mean()


def test_run_and_vault_gate(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=30)
    rows = recorded(cfg, monkeypatch, m1, h1, tf="5min", n=200)
    src = tmp_path / "src"; src.mkdir()
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, h1), hist / "XAUUSD.pkl")
    x = rows.assign(ts=rows.ts.astype(str), exit_ts=rows.exit_ts.astype(str), tf="5m")
    x.to_csv(src / "trades_seen_x_5m.csv.gz", index=False)
    srcs = {"seen": (src, hist, "trades_seen_"), "vault": (src, hist, "trades_old_")}
    res = E.run("seen", cfg=cfg, out=tmp_path / "s", src=srcs)
    assert set(res) == {"rand_time", "opposite"} and res["rand_time"]["n"] > 100
    rep = (tmp_path / "s/report.md").read_text()
    assert "vs random timing (primary)" in rep and "### By setup" in rep
    with pytest.raises(SystemExit, match="judged once"):
        E.run("seen", cfg=cfg, out=tmp_path / "s", src=srcs)
    monkeypatch.setitem(E.OUT, "seen", tmp_path / "nope")
    with pytest.raises(SystemExit, match="only if the entries beat random"):
        E.run("vault", cfg=cfg, out=tmp_path / "v", src=srcs)
