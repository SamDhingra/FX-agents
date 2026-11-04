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
