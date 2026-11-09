"""Nov 9 2026: a runner target (management.runner.target_r) in live and research, and by-hand actions on one open
trade for the account or a paper book."""
import asyncio
import copy
import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.config import load_config
from fxagents.dashboard.server import build_app
from fxagents.research import simulate_live
from fxagents.sim import Mgmt
from fxagents.state import LiveState
from tests.test_dashboard_insights import make_ctx


def _path(prices):
    p = np.asarray(prices, float)
    return p, p + 0.05, p - 0.05, p, np.arange(len(p), dtype=float)


def _sim(m, prices, stop=99.0):
    O, H, L, C, t = _path(prices)
    return simulate_live(O, H, L, C, t, 0, 1, stop, m, 0.0, np.zeros(len(C), bool), None, 1e9, False)


def test_config_turns_it_on_at_2r():
    cfg = load_config("config.yaml")
    assert Mgmt.from_cfg(cfg).runner_target_r == 2.0


def test_runner_closes_at_the_target_in_research():
    up = list(np.linspace(100, 104, 200))                                # straight to +4R (R = 1)
    m = Mgmt(rr=1.0, partial=0.5, pyramid=False, max_adds=0, runner_target_r=2.0)
    r = _sim(m, up)
    assert r["exit_reason"] == "runner_target" and abs(r["r"] - (0.5 * 1.0 + 0.5 * 2.0)) < 0.06
    off = _sim(dataclasses.replace(m, runner_target_r=0.0), up)
    assert off["exit_reason"] != "runner_target"                          # 0 = today's runner, no target
    trend = _sim(dataclasses.replace(m, rr=2.0), up)                      # first target 2R → runner target 3R
    assert trend["exit_reason"] == "runner_target" and abs(trend["r"] - (0.5 * 2 + 0.5 * 3)) < 0.06


def test_live_manager_closes_the_runner_at_the_target():
    from fxagents.agents.core import Ctx
    from fxagents.agents.trading import PositionManagerAgent
    from tests.test_live import pos, run, setup
    cfg, fake, c, st, bus, feed, b = setup()
    cfg = copy.deepcopy(cfg)
    cfg["management"]["runner"]["target_r"] = 2.0
    cfg["management"]["pyramid"]["max_adds"] = 0
    ctx = Ctx(cfg, bus, st, None, b, None, None, None)
    pm = PositionManagerAgent(ctx)
    pm.start()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        st.positions[p.id] = p
        p.stage, p.partial_done = 1, True                                  # first target already banked
        tgt = p.entry + p.side * 2.0 * p.risk_per_unit
        bar = SimpleNamespace(symbol=p.symbol, ts=pd.Timestamp("2026-11-02 10:30", tz="America/New_York"),
                              open=tgt - 1, high=tgt + 1, low=tgt - 2, close=tgt)
        pm.now = lambda: bar.ts
        await pm.manage(p, bar)
        return p, tgt
    p, tgt = run(go())
    assert p.status == "closed" and p.exit_reason == "runner_target"
    assert abs(p.meta["runner_target"] - tgt) < 1e-9


def test_card_shows_the_target_still_ahead():
    from tests.test_live import pos
    p = pos()
    first = p.to_public(1.0)["target"]
    p.stage, p.meta["runner_target"] = 1, p.entry + p.side * 2 * p.risk_per_unit
    assert p.to_public(1.0)["target"] == round(p.meta["runner_target"], 4) != first
    p.meta["target"] = 123.0                                               # a rule book's own target wins
    assert p.to_public(1.0)["target"] == 123.0


class FakeBus:
    def __init__(self, answer):
        self.answer, self.got = answer, []

    def subscribe(self, *a, **k):
        pass

    async def publish(self, kind, ev):
        self.got.append((kind, dict(ev)))
        ev["result"] = dict(self.answer)


def test_manual_route_reaches_the_right_book(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.cfg["dashboard"]["token"] = "t0k"
    ctx.bus = FakeBus({"ok": True, "msg": "closed"})
    sh = SimpleNamespace(state=LiveState(), book_key="playbook", is_shadow=True, journal=ctx.journal, cfg=ctx.cfg,
                         bus=FakeBus({"ok": False, "msg": "no such open position"}))
    ctx.shadows, ctx.shadow = {"playbook": sh}, sh
    c = TestClient(build_app(ctx))
    h = {"x-fx": "1", "x-token": "t0k"}
    r = c.post("/api/positions/abc/manual", json={"action": "close"}, headers=h)
    assert r.json() == {"ok": True, "msg": "closed"} and ctx.bus.got == [("manual", {"action": "close", "id": "abc", "by": "dashboard"})]
    r = c.post("/api/positions/xyz/manual?book=playbook", json={"action": "partial", "frac": 0.5}, headers=h)
    assert r.json()["ok"] is False and sh.bus.got[0][1]["frac"] == 0.5 and len(ctx.bus.got) == 1
    assert c.post("/api/positions/abc/manual", json={"action": "nuke"}, headers=h).status_code == 400
    assert c.post("/api/positions/abc/manual", json={"action": "stop"}, headers=h).status_code == 400
    assert c.post("/api/positions/abc/manual", json={"action": "close"}).status_code in (401, 403)      # no token
