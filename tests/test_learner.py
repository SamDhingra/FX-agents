"""Learner fixes: permanent forward records, real-results veto/demotion, live vetting gate."""
from __future__ import annotations

import asyncio
import copy

import pandas as pd

from fxagents.agents.core import Ctx, StrategyBook
from fxagents.agents.strategist import StrategistAgent
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.journal import Journal
from fxagents.state import LiveState
from fxagents.strategies import build_strategy

CFG = load_config("config.yaml")
TZ = "America/New_York"
NOW = pd.Timestamp("2026-10-20 17:05", tz=TZ)
CREATED = "2026-10-01T17:05:00-04:00"


def setup(tmp_path, mode="paper"):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = mode
    j = Journal(str(tmp_path / "j.sqlite"))
    book = StrategyBook(j, rr=1.0)
    parent = book.get("smc_ifvg:5m@v1")
    child = build_strategy(parent.spec() | {"version": "v2", "status": "shadow", "origin": f"learner:{parent.id}",
                                            "created": CREATED, "params": {**parent.params}})
    book.add(child, CREATED, "test")
    st = LiveState(mode=mode); st.now = NOW
    ctx = Ctx(cfg, Bus(), st, None, None, j, None, book, None)
    ag = StrategistAgent(ctx); ag.start()
    return ctx, ag, book, j, parent, child


def fwd(j, sid, rs, start="2026-10-02 09:00"):
    t0 = pd.Timestamp(start, tz=TZ)
    j.add_forward([(sid, "NDQ", (t0 + pd.Timedelta(hours=6 * i)).isoformat(), r) for i, r in enumerate(rs)])


def real(j, sid, rs):
    for i, r in enumerate(rs):
        j.db.execute("INSERT INTO trades(id, symbol, strategy, status, closed, r_multiple, hour) VALUES(?,?,?,?,?,?,?)",
                     (f"{sid}-{i}", "NDQ", sid, "closed", f"2026-10-1{i % 9}T10:00:00-04:00", r, 10))
    j.db.commit()


def test_forward_records_accumulate_and_dedupe(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    fwd(j, "x:5m@v2", [1.0, -1.0, 1.0])
    fwd(j, "x:5m@v2", [1.0, -1.0, 1.0])                      # same trades seen again next hour → ignored
    s = j.forward_stats("x:5m@v2")
    assert s["n"] == 3 and abs(s["expectancy"] - 1 / 3) < 1e-3
    assert j.forward_stats("x:5m@v2", since="2026-10-02T14:00:00-04:00")["n"] == 2


def test_only_completed_simulated_trades_are_recorded(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    trades = {"NDQ": {child.id: [{"ts": NOW - pd.Timedelta(hours=6), "r": 1.0},
                                 {"ts": NOW - pd.Timedelta(minutes=30), "r": -1.0}]}}   # still inside max hold
    ag.record_forward(trades, NOW)
    assert j.forward_stats(child.id)["n"] == 1


def test_promotion_builds_up_over_weeks_beyond_the_rolling_window(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    fwd(j, child.id, [0.6] * 30)                              # 30 forward trades spread over ~8 days
    fwd(j, parent.id, [0.1] * 30)
    ag.lc["auto_promote"] = True
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(child.id).status == "live" and book.get(parent.id).status == "shadow"


def test_auto_promote_off_only_reports(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    fwd(j, child.id, [0.6] * 30)
    fwd(j, parent.id, [0.1] * 30)
    ag.lc["auto_promote"] = False
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(child.id).status == "shadow" and book.get(parent.id).status != "shadow"


def test_negative_real_trades_veto_promotion(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    fwd(j, child.id, [0.6] * 30)
    fwd(j, parent.id, [0.1] * 30)
    real(j, child.id, [-1.0] * 6)
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(child.id).status == "shadow"
    assert any("held" in x["msg"] for x in ctx.state.learner_log)


def test_live_version_is_demoted_when_real_trades_lose(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    real(j, parent.id, [-1.0] * 10 + [1.0] * 6)                # 16 real trades, −0.25R
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(parent.id).status == "shadow"


def test_live_mode_trades_only_vetted_learner_versions(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path, mode="live")
    book.set_status(child.id, "live", NOW.isoformat())        # promoted on paper …
    book.set_status(parent.id, "shadow", NOW.isoformat())     # … replacing its parent
    book.require_vetting = True
    ids = {s.id for s in book.live()}
    assert child.id not in ids and parent.id in ids           # unvetted → parent keeps trading
    book.set_vetted(child.id, True, NOW.isoformat())
    ids = {s.id for s in book.live()}
    assert child.id in ids and parent.id not in ids
    book.require_vetting = False                              # paper: promotion applies immediately
    book.set_vetted(child.id, False, NOW.isoformat())
    assert child.id in {s.id for s in book.live()}
    # vetting survives a restart
    book.set_vetted(child.id, True, NOW.isoformat())
    assert StrategyBook(j, rr=1.0).get(child.id).vetted is True


def test_learner_never_recreates_an_existing_or_retired_version():
    sig = StrategistAgent._sig
    a = {"class": "smc_ifvg", "tf": "5min", "params": {"x": 1, "y": 2}, "rr": 1}
    b = {"class": "smc_ifvg", "tf": "5min", "params": {"y": 2, "x": 1}, "rr": 1.0, "version": "v9"}
    assert sig(a) == sig(b)
    assert sig(a) != sig(a | {"rr": 1.25}) != sig(a | {"tf": "15min"})
