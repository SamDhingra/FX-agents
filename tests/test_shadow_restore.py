"""Shadow books (playbook, C10 paper, …) keep their open positions across an update/restart, and a stop reached
while the app was down is booked on the first bar after it."""
from __future__ import annotations

import asyncio
import copy
import os
import time

import pandas as pd
import pytest

from fxagents.agents.core import Ctx
from fxagents.agents.setup_first import build_shadow
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.journal import Journal
from fxagents.models import Bar, Leg, Position
from fxagents.state import LiveState
from tests.test_setup_first import FakeBook, FakeJev

CFG = load_config("config.yaml")
TZ = "America/New_York"
NOW = pd.Timestamp("2026-10-21 10:00", tz=TZ)


class M1Store:
    def __init__(self, rows=None):
        self.rows = rows or []

    def m1(self, sym):
        idx = pd.DatetimeIndex([r[0] for r in self.rows]) if self.rows else pd.DatetimeIndex([], tz=TZ)
        return pd.DataFrame([r[1:] for r in self.rows] or None, index=idx, columns=["open", "high", "low", "close"])

    def tf(self, *a, **k):
        return pd.DataFrame()


def _main(tmp_path, store=None):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = "paper"
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    cfg["shadow"].pop("db_path", None)
    st = LiveState(mode="paper"); st.now = NOW
    return Ctx(cfg, Bus(), st, store or M1Store(), PaperBroker(cfg, st, Bus()), Journal(cfg["storage"]["db_path"]),
               FakeJev({}), FakeBook([]), None)


def _open(sctx, stop=24900.0):
    p = Position("NDQ", 1, "playbook:NDQ/5min/x@v1", stop, stop, 100.0, 1.0, NOW)
    p.add_leg(Leg(2.0, 25000.0, NOW, "initial"))
    p.meta.update(t1=NOW.isoformat(), max_hold=480)
    p.stage, p.partial_done = 1, True
    sctx.state.positions[p.id] = p
    sctx.broker.open_positions[p.id] = p
    asyncio.run(sctx.bus.publish("position_opened", p))
    return p


def test_open_shadow_positions_survive_a_restart(tmp_path):
    sctx, agents, feed = build_shadow(_main(tmp_path), 70000.0, "playbook")
    p = _open(sctx)
    sctx2, _, _ = build_shadow(_main(tmp_path), 70000.0, "playbook")          # the app restarts
    q = sctx2.state.positions.get(p.id)
    assert q is not None and q.status == "open" and q.open_qty == pytest.approx(2.0)
    assert q.stage == 1 and q.partial_done and q.meta["max_hold"] == 480       # management state kept
    assert sctx2.broker.open_positions[p.id] is q                             # its stop is watched again
    assert any(e["kind"] == "readopted" for e in q.events)
    # closed positions are not brought back
    q.status = "closed"
    asyncio.run(sctx2.bus.publish("position_closed", {"position": q}))
    sctx2.state.positions.pop(q.id)
    asyncio.run(sctx2.bus.publish("clock", NOW))
    sctx3, _, _ = build_shadow(_main(tmp_path), 70000.0, "playbook")
    assert not sctx3.state.positions


def test_a_stop_reached_during_the_restart_is_booked(tmp_path):
    sctx, _, _ = build_shadow(_main(tmp_path), 70000.0, "playbook")
    p = _open(sctx)
    path = sctx.runtime_store.path
    t_save = time.time() - 120
    os.utime(path, (t_save, t_save))                                          # saved two minutes ago
    down = pd.Timestamp(t_save, unit="s", tz="UTC").tz_convert(TZ)
    rows = [(down + pd.Timedelta(seconds=30), 24950.0, 24960.0, 24880.0, 24890.0)]   # through the 24900 stop
    sctx2, _, _ = build_shadow(_main(tmp_path, M1Store(rows)), 70000.0, "playbook")
    seen = []
    sctx2.bus.subscribe("stop_filled", lambda ev: seen.append(ev))
    now = down + pd.Timedelta(minutes=2)
    asyncio.run(sctx2.broker.on_bar(Bar("NDQ", now, 24950, 24960, 24940, 24950, 1)))
    assert seen and seen[0]["position"].id == p.id
    assert seen[0]["price"] <= 24900.0                                        # filled at the stop (or a gap beyond)
    assert p.id not in sctx2.broker.open_positions


def test_not_in_sim_or_replay(tmp_path):
    m = _main(tmp_path)
    m.cfg["mode"] = "sim"
    sctx, _, _ = build_shadow(m, 70000.0, "playbook")
    assert not hasattr(sctx, "runtime_store") or sctx.__dict__.get("runtime_store") is None
