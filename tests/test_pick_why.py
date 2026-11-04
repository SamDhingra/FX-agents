"""pick_why replays the hourly pick's arithmetic from journaled ratings (read-only)."""
import json

import pandas as pd

import fxagents.pick_why as PW
from fxagents.journal import Journal


def test_replays_rank_and_reason(tmp_path, monkeypatch, capsys):
    j = Journal(str(tmp_path / "journal.sqlite"))
    j.save_strategy({"id": "sr_rejection", "status": "live"}, "2026-10-01T00:00")
    cand = lambda name, tf, e: {"name": name, "timeframe": tf, "this_hour_exp_shrunk": e, "recent": {"exp": e},  # noqa: E731
                                "live_trades": {"n": 0, "expectancy": 0}, "overall": {"n": 40, "expectancy": e}}
    now = pd.Timestamp.now(tz="America/New_York")
    for i, (sr_e, other_e) in enumerate(((0.1, 0.4), (0.4, 0.1))):
        j.add_decision({"ts": (now - pd.Timedelta(hours=3 - i)).isoformat(), "kind": "strategy_rating", "source": "jev",
                        "symbol": "US30",
                        "inputs": {"hour_ny": 10 + i, "strategies": {"s0": cand("sr_rejection", "30m", sr_e),
                                                                     "s1": cand("smc_mss", "30m", other_e)}},
                        "outputs": {"s0": {"value": 0.9 if sr_e > other_e else 0.3, "confidence": 0.8},
                                    "s1": {"value": 0.9 if other_e > sr_e else 0.3, "confidence": 0.8},
                                    "trade_ok": {"value": 0.7, "confidence": 0.5}}})
    real = PW.load_config
    monkeypatch.setattr(PW, "load_config", lambda p: {**real(p), "storage": {"db_path": str(tmp_path / "journal.sqlite")}})
    PW.main(["sr_rejection", "--days", "1"])
    out = capsys.readouterr().out
    assert "sr_rejection: **live**" in out
    assert "rank 2 of 2 on 30m: smc_mss" in out and "→ PICKED" in out
    assert "rated 2 times, picked 1" in out
