"""Gold breakout trailing stop (registered Nov 3 2026): same entries as breakout_test, only the stop after entry moves."""
import numpy as np
import pandas as pd
import pytest

from fxagents import gold_trail as G
from fxagents.breakout_test import run as bt_run
from tests.test_breakout import frame, two_days


def _break_then(after):
    """Range 99.5–100.5 (00–07 broker), break up at 07:00 to 100.6, then the given minute prices."""
    return two_days([100.0] * 100 + [99.5] * 10 + [100.0] * 90 + [100.5] * 10 + [100.0] * 210 + list(after))


def test_baseline_matches_breakout_test_on_a_random_walk():
    rng = np.random.default_rng(5)
    px = 2000 + np.cumsum(rng.normal(0, 0.8, 1440 * 12))
    m1 = frame(px, start="2025-03-02 21:00", spread=0.3)
    m1 = m1[m1.index.dayofweek < 5]
    ref, _ = bt_run(m1, 20, "pct", np.random.default_rng(0))
    t = G.trades(m1)
    assert len(t) == len(ref) > 3
    for r, (_, g) in zip(ref, t.iterrows()):
        assert g.entry_time == r["entry_time"] and g.side == r["side"]
        assert abs(g.R_base - r["side"] * (r["exit"] - r["entry"]) / r["atr"]) < 1e-9


def test_trail_half_locks_profit_after_a_giveback():
    # entry ≈ 100.6 ask → 1R ≈ 1.006; rises to +0.8R, then falls back below entry
    fall = list(np.round(np.arange(101.4, 99.0, -0.02), 2))                   # a gradual giveback, no gaps
    t = G.trades(_break_then([100.6] * 5 + [101.4] * 30 + fall + [99.0] * 900))
    r = t.iloc[0]
    assert r.side == 1
    assert r.R_base < 0                                          # no trail: held to the close at a loss
    assert r.why_trail_half == "trail" and r.R_trail_half == pytest.approx((101.4 - 0.1 - 0.5 * r.risk - r.entry) / r.risk, abs=0.02)
    assert r.R_trail_half > 0          # a loss without the trail, a gain with it
    assert r.R_be_half == pytest.approx(0, abs=0.03)              # break-even: out at entry (one 0.02 step through)
    assert r.why_trail_1r != "trail"                             # never reached +1R: behaves as no trail


def test_trail_never_loosens_and_waits_for_threshold():
    t = G.trades(_break_then([100.6] * 5 + [100.9] * 30 + [100.55] * 900))     # only +0.25R at best
    r = t.iloc[0]
    assert r.R_trail_half == pytest.approx(r.R_base) and r.why_trail_half == "time"


def test_same_minute_high_does_not_protect_its_low():
    m1 = _break_then([100.6] * 5 + [101.4] * 1 + [100.6] * 900)
    i = m1.index.get_loc(m1.index[1440 + 420 + 5])
    m1.iloc[i, m1.columns.get_loc("bid_l")] = 100.2              # same minute: big high, and a dip below where the trail lands
    r = G.trades(m1).iloc[0]
    assert r.why_trail_half == "trail"                            # not out in that minute; the next minute opens (bid 100.5) below the trail → out there
    assert r.R_trail_half == pytest.approx((100.5 - r.entry) / r.risk, abs=1e-6)


def test_vault_refuses_without_a_seen_pass(tmp_path, monkeypatch):
    monkeypatch.setitem(G.OUT, "seen", tmp_path / "seen")
    with pytest.raises(SystemExit, match="only if trail_half passed"):
        G.run("vault", out=tmp_path / "vault", m1=two_days([100.0] * 1440))
