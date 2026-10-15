"""Dashboard insight endpoints: Mission Control flow, now/weather, evidence meters, courtroom story, replay bars."""
from __future__ import annotations

import asyncio
import copy
import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.agents.core import Ctx
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.dashboard import insights
from fxagents.dashboard.server import build_app
from fxagents.data import BarStore
from fxagents.journal import Journal
from fxagents.models import Bar
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


class Jev:
    live = False


def make_ctx(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["dashboard"]["token"] = ""
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 70000.0
    st.now = pd.Timestamp("2026-10-14 10:30", tz=TZ)
    bus = Bus()
    store = BarStore(TZ, max_days=5)
    idx = pd.date_range("2026-10-13 08:00", "2026-10-14 10:29", freq="1min", tz=TZ)
    p = 2650 + np.cumsum(np.random.default_rng(1).normal(0, 0.4, len(idx)))
    for ts, x in zip(idx, p):
        store.append(Bar("XAUUSD", ts, x, x + 0.3, x - 0.3, x, 1.0))
    j = Journal(str(tmp_path / "j.sqlite"))
    rng = np.random.default_rng(2)
    for i in range(40):
        o = pd.Timestamp("2026-09-01 09:30", tz=TZ) + pd.Timedelta(days=i // 2, hours=i % 2)
        r = float(rng.normal(0.1, 1))
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,events) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)", (f"t{i}", "XAUUSD", "LONG", "trend_breakout:15m@pb-x", "closed",
                                                     o.isoformat(), (o + pd.Timedelta(minutes=40)).isoformat(), r, r * 100,
                                                     json.dumps([{"ts": o.isoformat(), "kind": "entry", "price": 2650}])))
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,events) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 ("recent", "XAUUSD", "LONG", "trend_breakout:15m@pb-x", "closed", "2026-10-14T09:00:00-04:00",
                  "2026-10-14T09:40:00-04:00", 0.5, 50, "[]"))
    j.add_signal({"ts": "2026-10-14T08:59:00-04:00", "symbol": "XAUUSD", "strategy": "trend_breakout:15m@pb-x", "side": 1,
                  "entry": 2650.0, "stop": 2640.0, "action": "taken", "why": "qty 2"})
    j.add_decision({"ts": "2026-10-14T08:59:30-04:00", "kind": "signal_rating", "source": "jev", "symbol": "XAUUSD",
                    "strategy": "trend_breakout", "inputs": {"question": "q?", "htf_bias": 1}, "outputs": {"quality": 0.7}})
    j.db.commit()
    ctx = Ctx(cfg, bus, st, store, PaperBroker(cfg, st, bus), j, Jev(), None)
    ctx.shadows = {}
    return ctx


def test_flow_tap_records_bus_messages(tmp_path):
    ctx = make_ctx(tmp_path)
    insights.install_tap(ctx)
    insights.install_tap(ctx)                                   # idempotent: one subscription
    asyncio.run(ctx.bus.publish("entry_request", {"symbol": "XAUUSD"}))
    f = insights.flow(ctx)
    assert [e["topic"] for e in f["events"]] == ["entry_request"] and f["events"][0]["symbol"] == "XAUUSD"


def test_endpoints(tmp_path):
    ctx = make_ctx(tmp_path)
    c = TestClient(build_app(ctx))
    ev = c.get("/api/evidence").json()["books"][0]
    assert ev["n"] == 41 and ev["ci"] and ev["ci"][0] < ev["avg_r"] < ev["ci"][1]
    assert ev["verdict"] in ("unproven", "failing", "passing") and ev["strategies"][0]["name"] == "trend_breakout"
    st = c.get("/api/story/recent").json()
    assert st["signal"]["action"] == "taken" and st["jev"]["outputs"]["quality"] == 0.7 and st["jev"]["question"] == "q?"
    assert c.get("/api/story/nope").status_code == 404
    b = c.get("/api/bars", params={"symbol": "XAUUSD", "start": "2026-10-14T09:00:00-04:00",
                                   "end": "2026-10-14T09:40:00-04:00"}).json()
    assert len(b["bars"]) == 41
    old = c.get("/api/bars", params={"symbol": "XAUUSD", "start": "2026-01-01T09:00:00-05:00",
                                     "end": "2026-01-01T10:00:00-05:00"}).json()
    assert old["bars"] == [] and "older" in old["note"]
    n = c.get("/api/now").json()
    assert n["items"] and all("at" in i for i in n["items"]) and n["fuel"]["budget"] == 1400.0
    w = {x["symbol"]: x for x in n["weather"]}
    assert w["XAUUSD"]["sky"] in ("chop", "trend", "mixed") and w["XAUUSD"]["chop"] is not None
    assert "flow" in c.get("/api/state").json()
