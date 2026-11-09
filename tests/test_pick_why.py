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


def test_new_strategy_with_a_good_record_can_be_picked_but_luck_cannot_dominate():
    from fxagents.agents.trading import quant_score
    m, none = 8, {"n": 0, "expectancy": 0.0}
    old = quant_score(0.4, 5, 0.4, 5, none, m, old_penalty=True)
    new = quant_score(0.4, 5, 0.4, 5, none, m)
    assert old < 0.55 < new                                         # before: shut out by ×0.6; now: pickable
    assert quant_score(0.0, 0, 0.0, 0, none, m) == 0.5             # no record = no edge, not picked at 0.55
    assert quant_score(-0.3, 5, -0.3, 5, none, m) < 0.5            # a new LOSING strategy still isn't
    lucky = quant_score(1.5, 3, 1.5, 3, none, m)                    # 3 trades at +1.5R
    proven = quant_score(0.5, 200, 0.5, 60, none, m)                # 200 trades at +0.5R
    assert proven > lucky
    assert abs(quant_score(0.3, 400, 0.3, 100, none, m) - quant_score(0.3, 400, 0.3, 100, none, m, True)) < 0.03


def test_compare_counts_picks_before_and_after(tmp_path, monkeypatch):
    j = Journal(str(tmp_path / "journal.sqlite"))
    cand = lambda name, tf, e, n: {"name": name, "timeframe": tf, "this_hour_exp_shrunk": e,  # noqa: E731
                                   "recent": {"exp": e, "n": n}, "live_trades": {"n": 0, "expectancy": 0},
                                   "overall": {"n": n, "expectancy": e}}
    now = pd.Timestamp.now(tz="America/New_York")
    rows = [  # (good-new, proven, Jev value for proven, trade_ok)
        ({"s0": cand("new_good", "5m", 0.4, 5), "s1": cand("proven", "15m", 0.2, 100)}, 0.9, 0.2),   # Jev sat it out
        ({"s0": cand("new_good", "5m", 0.4, 5), "s1": cand("proven", "15m", 0.2, 100)}, 0.1, 0.8),   # Jev disliked it
    ]
    for i, (st, jv, tok) in enumerate(rows):
        j.add_decision({"ts": (now - pd.Timedelta(hours=2 - i)).isoformat(), "kind": "strategy_rating", "source": "jev",
                        "symbol": "NDQ", "inputs": {"hour_ny": 9 + i, "strategies": st},
                        "outputs": {"s0": {"value": 0.5, "confidence": 0.5}, "s1": {"value": jv, "confidence": 0.9},
                                    "trade_ok": {"value": tok, "confidence": 0.5}}})
    real = PW.load_config
    cfg = {**real("config.yaml"), "storage": {"db_path": str(tmp_path / "journal.sqlite")}}
    md = PW.compare(1, cfg)
    assert "| **all** | 2 | **0** | **4** |" in md
    assert "trade_ok < 0.4) | 1 | 0 |" in md
