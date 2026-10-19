"""sweep_reclaim_v2: frozen constants, the author's risk/room gates, and the two-step protocol."""
import numpy as np
import pandas as pd

import fxagents.sweep_reclaim_v2 as R
from fxagents.gemini_smc import block_mask
from fxagents.sweep_vwap import prepare
from tests.test_gemini_smc import frame, walk


def test_trades_respect_the_authors_bounds():
    a = prepare(frame(walk(seed=21, n_days=120)))
    ents = R.find_trades(a)
    assert ents and {e["mode"] for e in ents} == {"sweep"}
    tr, ctl = R.execute(a, ents, block_mask(a, 15, 15), np.random.default_rng(3))
    T = pd.DataFrame(tr)
    assert len(T) > 5 and len(ctl) == len(T)
    assert set(T.exit_reason) <= {"stop", "target", "flat_1630", "closure", "end"}
    assert np.allclose(T[T.exit_reason == "target"].R, R.TP_R, atol=0.05)
    assert (T[T.exit_reason == "stop"].R <= -0.99).all()
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    assert T.groupby((loc + pd.Timedelta(hours=6)).dt.date).size().max() == 1   # one trade per session day


def _export(tmp, names):
    for ds in names:
        d = tmp / "data/export" / ds
        d.mkdir(parents=True)
        m = frame(walk(n_days=60, seed=5))
        m = m[[c for c in m.columns if not c.startswith("m_")]]
        m.index.name = "time"
        m.to_csv(d / "XAUUSD_M1.csv.gz")


def test_untouched_set_is_only_opened_after_step_one(tmp_path, monkeypatch):
    _export(tmp_path, ["dev_m1", "holdout_m1"])                      # old_m1 deliberately missing
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["x", "--out", str(tmp_path / "o1")])
    fail = {"trades": 0, "passed": False, "avg_R": -0.1}
    monkeypatch.setattr(R, "gates", lambda T, C, d: dict(fail))
    R.main()                                                          # would crash if it tried to open old_m1
    assert "NOT opened" in (tmp_path / "o1/report.md").read_text()
    _export(tmp_path, ["old_m1"])
    stat = {"trades": 120, "passed": True, "avg_R": 0.1, "win": .5, "ci_lo": .01, "ci_hi": .2, "avg_R_2x": .05,
            "h1": .1, "h2": .1, "ctl_avg_R": 0.0}
    monkeypatch.setattr(R, "gates", lambda T, C, d: dict(stat))
    monkeypatch.setattr("sys.argv", ["x", "--out", str(tmp_path / "o2")])
    R.main()
    assert "UNTOUCHED — judged" in (tmp_path / "o2/report.md").read_text()
