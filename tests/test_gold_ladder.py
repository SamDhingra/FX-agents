"""Gold breakout ladder (registered Nov 3 2026): half ratchet, half runner, one re-entry, setup-broken rule."""
import numpy as np
import pandas as pd
import pytest

from fxagents import gold_ladder as L
from fxagents import gold_trail as GT
from fxagents.breakout_test import to_broker
from tests.test_breakout import two_days


def _day(after):
    """Range 99.5–100.5 (00–07 broker); price sits at 100.6 from 07:00 (long break), then `after`; padded past 20:00."""
    pre = [100.0] * 100 + [99.5] * 10 + [100.0] * 90 + [100.5] * 10 + [100.0] * 210
    body = list(after)
    return two_days(pre + body + [body[-1]] * max(0, 1000 - len(body)))


def _go(m1, mode="ladder"):
    a = GT.arrays(m1)
    _, bmin = to_broker(a["idx"])
    end15 = (bmin % 15) == 14
    (j, side, entry, stop, risk, spread, t1, rh, rl), = GT.entries(a)
    base = GT.walk(a, j, t1, side, entry, stop, risk, "base")
    m = L.manage(a, end15, j, t1, side, entry, stop, risk, rh, rl, mode)
    return m, side * (base[1] - entry) / risk, entry, risk


def ramp(a, b, step=0.01):
    n = int(round(abs(b - a) / step))
    return list(np.round(np.linspace(a, b, n + 1), 4))[1:]


def test_quiet_day_equals_no_management():
    m, base, *_ = _go(_day([100.6] * 10 + [100.7] * 50))
    assert m["R"] == pytest.approx(base) and not m["reentry"]


def test_ratchet_takes_partial_and_runner_keeps_going():
    # entry ≈100.5..; step 0.25R ≈ 0.25; ride up 1R, pull back 0.4R, then run to +3R by the close
    m1 = _day(ramp(100.6, 101.6) + ramp(101.6, 100.95) + ramp(100.95, 103.6))
    m, base, entry, risk = _go(m1, "ladder_nobreak")
    assert base > 2.5
    assert m["reentry"]                                       # P was ratcheted out on the pullback, then re-entered
    assert 0.5 * base < m["R"] < 1.5 * base


def test_setup_broken_cuts_losing_legs():
    # break up, fall back inside the range and keep falling to the stop
    m1 = _day([100.6] * 20 + ramp(100.6, 99.0))
    m, base, entry, risk = _go(m1, "ladder")
    assert base == pytest.approx(-1, abs=0.05)
    assert m["R"] > base + 0.3                               # out at the first 15m close back inside the range
    assert not m["reentry"]


def test_vault_refuses_without_a_seen_pass(tmp_path, monkeypatch):
    monkeypatch.setitem(L.OUT, "seen", tmp_path / "seen")
    with pytest.raises(SystemExit, match="only if ladder passed"):
        L.run("vault", out=tmp_path / "vault", m1=two_days([100.0] * 1440))


def test_full_report_runs(tmp_path):
    rng = np.random.default_rng(3)
    px = 2000 + np.cumsum(rng.normal(0, 0.8, 1440 * 15))
    from tests.test_breakout import frame
    m1 = frame(px, start="2021-03-01 21:00", spread=0.3)
    m1 = m1[m1.index.dayofweek < 5]
    res = L.run("seen", out=tmp_path / "s", m1=m1)
    assert set(res) == set(L.MODES)
    assert (tmp_path / "s" / "report.md").read_text().startswith("# Gold overnight breakout: ladder")
