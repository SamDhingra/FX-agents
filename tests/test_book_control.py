"""Pause / resume a paper book from the dashboard (Nov 4 2026); a drawdown resume restarts the peak."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from fxagents.dashboard.server import build_app
from fxagents.state import LiveState
from tests.test_dashboard_insights import make_ctx


def test_resume_a_halted_paper_book(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.cfg["dashboard"]["token"] = "t0k"
    sh = SimpleNamespace(state=LiveState(), book_key="playbook", is_shadow=True, journal=ctx.journal, cfg=ctx.cfg)
    sh.state.equity, sh.state.equity_peak = 65_000.0, 70_000.0
    sh.state.trading_enabled, sh.state.halt_reason = False, "max drawdown hit (-7.1% from peak)"
    ctx.shadows, ctx.shadow = {"playbook": sh}, sh
    c = TestClient(build_app(ctx))
    r = c.post("/api/control/resume?book=playbook", headers={"x-fx": "1", "x-token": "t0k"})
    assert r.status_code == 200 and r.json()["trading_enabled"] is True
    assert sh.state.equity_peak == 65_000.0 and sh.state.halt_reason == ""
    assert ctx.state.trading_enabled is True                                   # the account untouched
    assert c.post("/api/control/pause?book=playbook", headers={"x-fx": "1", "x-token": "t0k"}).json()["trading_enabled"] is False
    assert c.post("/api/control/flatten?book=playbook", headers={"x-fx": "1", "x-token": "t0k"}).status_code == 400
