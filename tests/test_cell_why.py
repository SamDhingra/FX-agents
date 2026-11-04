"""cell_why: explains why a setup's cells are or aren't selected (read-only)."""
import numpy as np
import pandas as pd

from fxagents import cell_why as CW
from fxagents import playbook as pbk


def _trades():
    rng = np.random.default_rng(0)
    days = [str(d.date()) for d in pd.bdate_range("2026-07-01", periods=90)]
    rows = []
    for setup, sym, mu in (("sr_rejection", "NDQ", 0.15), ("sr_rejection", "US30", -0.2), ("smc_mss", "NDQ", 0.3)):
        for d in days:
            for _ in range(2):
                r = float(rng.normal(mu, 1.0))
                rows.append({"setup": setup, "sym": sym, "tf": "30min", "variant": "default", "mgmt": "std", "day": d,
                             "r": r, "ts": pd.Timestamp(d + " 10:00", tz="America/New_York"), "busy_self": False})
    return pd.DataFrame(rows)


def test_reasons_and_report(monkeypatch, tmp_path, capsys):
    cube = pbk.CellCube(_trades())
    monkeypatch.setattr(pbk, "load_cube", lambda cfg: cube)
    monkeypatch.setattr(pbk, "playbook_path", lambda cfg: tmp_path / "none.json")
    CW.main(["sr_rejection", "--days", "3"])
    out = capsys.readouterr().out
    assert "Why isn't sr_rejection trading?" in out and "## Its cells now" in out
    assert "US30" in out and ("shrunk expectancy" in out or "half of the window" in out)


def test_old_index_rules_flag(monkeypatch, tmp_path, capsys):
    cube = pbk.CellCube(_trades())
    monkeypatch.setattr(pbk, "load_cube", lambda cfg: cube)
    monkeypatch.setattr(pbk, "playbook_path", lambda cfg: tmp_path / "none.json")
    CW.main(["sr_rejection", "--days", "2", "--old-index-rules"])
    assert "max_cells=4" in capsys.readouterr().out


def test_signals_section(monkeypatch, tmp_path, capsys):
    from fxagents.journal import Journal
    cube = pbk.CellCube(_trades())
    monkeypatch.setattr(pbk, "load_cube", lambda cfg: cube)
    monkeypatch.setattr(pbk, "playbook_path", lambda cfg: tmp_path / "none.json")
    j = Journal(str(tmp_path / "journal_playbook.sqlite"))
    j.add_signal({"ts": "2026-11-02T10:30", "symbol": "US30", "strategy": "sr_rejection:30m@pb-us30-d-trend", "side": "long",
                  "entry": 1.0, "stop": 0.9, "action": "skipped", "why": "bias: counter-trend"})
    import fxagents.cell_why as m
    real = m.load_config
    monkeypatch.setattr(m, "load_config", lambda p: {**real(p), "storage": {"db_path": str(tmp_path / "journal.sqlite")}})
    CW.main(["sr_rejection", "--days", "1"])
    out = capsys.readouterr().out
    assert "journal_playbook.sqlite" in out and "bias: counter-trend" in out
