"""Strategy lab: candidates are tested and only promoted cells reach the playbook."""
import pandas as pd
import pytest

from fxagents import lab, playbook
from fxagents.config import load_config


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("FX_NO_LOCAL_CONFIG", "1")
    c = load_config()
    c["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    c["playbook"] = {}
    return c


def _trades(sym, tf, mg, rs, start="2026-07-01"):
    ts = pd.date_range(start, periods=len(rs), freq="6h", tz="America/New_York")
    return [{"sym": sym, "tf": tf, "mgmt": mg, "ts": t, "r": r} for t, r in zip(ts, rs)]


def test_verdict_needs_trades_both_halves_and_t():
    rows = _trades("XAUUSD", "15min", "std", [1.0, -1.0, 1.0, 1.0] * 15)             # 60 trades, +0.5R, steady
    rows += _trades("NDQ", "15min", "std", [-1.0] * 20 + [1.0, 1.0, 1.0, -1.0] * 10)   # second half only
    rows += _trades("US30", "15min", "std", [1.0, -1.0, 1.0] * 5)                       # too few trades
    v = {(r["sym"]): r for r in lab.verdict(pd.DataFrame(rows))}
    assert v["XAUUSD"]["pass"] and not v["NDQ"]["pass"] and not v["US30"]["pass"]


def test_add_validates_and_promote_pins_into_the_playbook(cfg):
    with pytest.raises(ValueError):
        lab.add(cfg, "no_such_setup")
    with pytest.raises(ValueError):
        lab.add(cfg, "trend_pullback", {"nope": 1})
    c = lab.add(cfg, "trend_pullback", {"ema": 50}, ["XAUUSD"], ["15min"], "test")
    with pytest.raises(ValueError):
        lab.promote(cfg, c["id"])                                                       # not tested yet
    cells = lab.verdict(pd.DataFrame(_trades("XAUUSD", "15min", "std", [1.0, -1.0, 1.0, 1.0] * 15)))
    lab.update(cfg, c["id"], status="passed", results={"cells": cells, "passed": True})
    assert lab.promote(cfg, c["id"])["status"] == "promoted"
    got = playbook.with_pinned(cfg, {"cells": []})["cells"]
    assert len(got) == 1 and got[0]["setup"] == "trend_pullback" and got[0]["params"] == {"ema": 50} \
        and got[0]["lab_id"] == c["id"] and got[0]["pinned"]
    lab.unpromote(cfg, c["id"])
    assert playbook.with_pinned(cfg, {"cells": []})["cells"] == []
