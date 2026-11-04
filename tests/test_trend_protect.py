"""Trend-profile protection (registered Nov 4 2026): the plain replay reproduces run_job, rules only act before 2R."""
import numpy as np
import pandas as pd
import pytest

from fxagents import trend_protect as TP
from tests.test_m15_timing import cfg, market, recorded  # noqa: F401  (fixture)


def _trend_rows(cfg, monkeypatch, days=30, n=200):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=days)
    rows = recorded(cfg, monkeypatch, m1, h1, tf="15min", n=n)
    rows = rows[rows.mgmt.map(TP.is_trend)].reset_index(drop=True)
    return m1, h1, rows


def test_replay_matches_and_rules_only_touch_trades_that_ran(cfg, monkeypatch):  # noqa: F811
    m1, _, rows = _trend_rows(cfg, monkeypatch)
    assert len(rows) > 10
    rows = rows.assign(kid=np.arange(len(rows)), tf=rows.tf.astype(str))
    out = TP.replay(cfg, rows, m1, TP.RULES)
    a = rows.merge(out, on="kid")
    assert a.ok.all() and (np.abs(a.base_1x - a.r) < 1e-9).mean() == 1.0
    never = a[a.mfe_rp < 0.5]
    assert np.allclose(never.lock1_1x, never.base_1x) and np.allclose(never.be05_1x, never.base_1x)
    ran = a[(a.mfe_rp >= 1.05) & (a.base_1x <= 0)]
    if len(ran):
        assert (ran.lock1_1x > ran.base_1x).all()                       # +1R then a loss → saved by the lock


def test_run_and_vault_gate(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1, rows = _trend_rows(cfg, monkeypatch, days=40, n=300)
    src = tmp_path / "src"; src.mkdir()
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, h1), hist / "XAUUSD.pkl")
    x = rows.assign(ts=rows.ts.astype(str), exit_ts=rows.exit_ts.astype(str))
    x.to_csv(src / "trades_seen_x_15m.csv.gz", index=False)
    srcs = {"seen": (src, hist, "trades_seen_"), "vault": (src, hist, "trades_old_")}
    res = TP.run("seen", cfg=cfg, out=tmp_path / "s", src=srcs)
    assert set(res) == set(TP.RULES)
    assert "Protection for trend-profile" in (tmp_path / "s/report.md").read_text()
    monkeypatch.setitem(TP.OUT, "seen", tmp_path / "nope")
    with pytest.raises(SystemExit, match="only if lock1 passed"):
        TP.run("vault", cfg=cfg, out=tmp_path / "v", src=srcs)
