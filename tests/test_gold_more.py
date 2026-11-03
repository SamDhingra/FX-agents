"""Gold breakout no-progress exit and add-on-resume (registered Nov 3 2026)."""
import numpy as np
import pandas as pd
import pytest

from fxagents import gold_more as G
from fxagents import gold_trail as GT
from tests.test_breakout import frame, two_days
from tests.test_gold_ladder import _day, ramp


def _one(m1):
    a = GT.arrays(m1)
    (j, side, entry, stop, risk, spread, t1, rh, rl), = GT.entries(a)
    base = GT.walk(a, j, t1, side, entry, stop, risk, "base")
    return a, G.bars15(m1), (j, side, entry, stop, risk, t1), side * (base[1] - entry) / risk


def test_noprog_cuts_a_flat_trade_at_three_hours():
    a, b, (j, side, entry, stop, risk, t1), base = _one(_day([100.6] * 300 + [99.9] * 600))
    r = G.noprog(a, j, t1, side, entry, stop, risk, 3, "prog")
    assert r == pytest.approx((100.5 - entry) / risk)          # out at the 3h open (bid 100.5), not the later 99.8
    assert r > base


def test_noprog_keeps_a_trade_that_made_progress():
    a, b, (j, side, entry, stop, risk, t1), base = _one(_day(ramp(100.6, 101.3) + [101.0] * 900))
    assert G.noprog(a, j, t1, side, entry, stop, risk, 3, "prog") == pytest.approx(base)


def test_add_fires_on_resumption_after_a_pullback():
    # up to +1.5R, pull back 0.7R, then a strong 15m candle up and a run higher
    path = ramp(100.6, 102.2, 0.02) + ramp(102.2, 101.5, 0.02) + [101.5] * 20 + ramp(101.5, 103.5, 0.02)
    a, b, (j, side, entry, stop, risk, t1), base = _one(_day(path))
    x = G.add_on(a, b, j, t1, side, entry, stop, risk, 1.0, "ext")
    assert x is not None and x["R"] > 0
    assert x["dist"] >= 0.25 * risk - 1e-9


def test_no_add_without_a_pullback():
    a, b, (j, side, entry, stop, risk, t1), base = _one(_day(ramp(100.6, 103.0, 0.005)))
    assert G.add_on(a, b, j, t1, side, entry, stop, risk, 1.0, "ext") is None


def test_full_report_runs(tmp_path):
    rng = np.random.default_rng(4)
    px = 2000 + np.cumsum(rng.normal(0, 0.8, 1440 * 15))
    m1 = frame(px, start="2021-03-01 21:00", spread=0.3)
    m1 = m1[m1.index.dayofweek < 5]
    res = G.run("seen", out=tmp_path / "s", m1=m1)
    assert set(res) == set(G.A_MODES) | set(G.B_MODES)
    assert "## B." in (tmp_path / "s" / "report.md").read_text()


def test_vault_refuses_without_a_seen_pass(tmp_path, monkeypatch):
    monkeypatch.setitem(G.OUT, "seen", tmp_path / "seen")
    with pytest.raises(SystemExit, match="only for a primary that passed"):
        G.run("vault", out=tmp_path / "vault", m1=two_days([100.0] * 1440))
