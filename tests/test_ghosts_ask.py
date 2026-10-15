"""Ghost trades (passed setups played out with one fixed exit rule), the filter scorecard, and Ask the bot's facts."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.dashboard import ask, ghosts
from fxagents.dashboard.server import build_app
from tests.test_dashboard_insights import make_ctx

TZ = "America/New_York"


def m1(prices, start="2026-10-14 09:00"):
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=TZ)
    p = np.asarray(prices, float)
    return pd.DataFrame({"open": p, "high": p + .1, "low": p - .1, "close": p}, index=idx)


def test_simulate_stop_target_time_and_no_lookahead():
    up = m1([100] * 16 + list(np.linspace(100, 110, 60)) + [110] * 300)
    r = ghosts.simulate(up, pd.Timestamp("2026-10-14 09:00", tz=TZ), 1, 98.0, 15, 0.0)
    assert r["outcome"] == "target" and r["r"] == 1.5 and r["entry_ts"] == pd.Timestamp("2026-10-14 09:15", tz=TZ)
    dn = m1([100] * 16 + list(np.linspace(100, 90, 60)) + [90] * 300)
    assert ghosts.simulate(dn, pd.Timestamp("2026-10-14 09:00", tz=TZ), 1, 98.0, 15, 0.0)["outcome"] == "stop"
    flat = m1([100] * 400)
    t = ghosts.simulate(flat, pd.Timestamp("2026-10-14 09:00", tz=TZ), -1, 102.0, 1, 0.0)
    assert t["outcome"] == "time" and (t["exit_ts"] - t["entry_ts"]) == pd.Timedelta(minutes=ghosts.MAX_HOLD_MIN)
    assert ghosts.simulate(flat.iloc[:30], pd.Timestamp("2026-10-14 09:00", tz=TZ), -1, 102.0, 1, 0.0) is None  # not done yet


def test_filter_labels():
    assert ghosts.filter_of("filtered", "counter to BULLISH bias") == "Bias rule"
    assert ghosts.filter_of("rejected", "news blackout: CPI (tier1, before)") == "News blackout"
    assert ghosts.filter_of("skipped", "Jev quality 0.31 below advisory floor 0.40") == "Jev gate"
    assert ghosts.filter_of("skipped", "regime chop (CHOP 66): scalps only") == "Chop filter"
    assert ghosts.filter_of("taken", "qty 2") == "Taken"
    assert ghosts.tf_minutes("trend_breakout:15m@pb-x") == 15 and ghosts.tf_minutes("x:1h@v") == 60


def test_resolve_dedupes_and_scores(tmp_path):
    ctx = make_ctx(tmp_path)
    j = ctx.journal
    for i, (act, why) in enumerate([("taken", "qty 2"), ("filtered", "counter to BULLISH bias"),
                                     ("filtered", "counter to BULLISH bias"), ("rejected", "news blackout: CPI")]):
        ts = (pd.Timestamp("2026-10-13 09:30", tz=TZ) + pd.Timedelta(minutes=[0, 20, 23, 60][i])).isoformat()
        j.add_signal({"ts": ts, "symbol": "XAUUSD", "strategy": "trend_breakout:5m@pb-x", "side": "LONG" if i != 3 else "SHORT",
                      "entry": 2650.0, "stop": 2600.0 if i != 3 else 2700.0, "action": act, "why": why})
    n = ghosts.resolve(ctx)
    rows = {r["why"] or r["action"]: r["outcome"] for r in map(dict, j.db.execute("SELECT * FROM ghosts"))}
    assert n >= 4 and "duplicate" in [dict(r)["outcome"] for r in j.db.execute("SELECT outcome FROM ghosts")]
    sc = ghosts.scorecard(ctx)
    names = {f["filter"] for f in sc["filters"]}
    assert "Bias rule" in names and sc["taken"] is not None
    assert all("saved_r" in f and f["verdict"] == "early" for f in sc["filters"])


def test_ask_window_parsing():
    now = pd.Timestamp("2026-10-15 14:00", tz=TZ)          # Thursday
    at, a, b = ask.when_of("why no gold trade at 9:30?", now)
    assert at == pd.Timestamp("2026-10-15 09:30", tz=TZ) and b - a == pd.Timedelta(hours=1)
    at, *_ = ask.when_of("what happened yesterday around 2pm", now)
    assert at == pd.Timestamp("2026-10-14 14:00", tz=TZ)
    at, *_ = ask.when_of("monday at 10:15 am", now)
    assert at == pd.Timestamp("2026-10-12 10:15", tz=TZ)
    assert ask.symbols_of("why didn't you buy gold or the dow") == ["XAUUSD", "US30"]


def test_ask_endpoint_without_key_returns_facts(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx = make_ctx(tmp_path)
    ctx.state.now = pd.Timestamp("2026-10-14 10:30", tz=TZ)
    c = TestClient(build_app(ctx))
    r = c.post("/api/ask", json={"question": "why did you trade gold at 9:00?"}).json()
    assert r["source"] == "facts" and "1 taken" in r["answer"]
    f = r["facts"]["books"]["live"]
    assert f["setups_in_window"][0]["action"] == "taken" and f["record"]["n"] == 41
    g = c.get("/api/ghosts").json()
    assert "scorecard" in g and "recent" in g
