"""Market Bias page data (/api/bias_grid): five timeframe cells per instrument and the eligibility line, which
follows the bot's own checks in order (open position, paused, news, warming up, suspended, window, no bias)."""
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.dashboard import biasgrid
from fxagents.dashboard.server import build_app
from fxagents.models import Leg, Position
from tests.test_dashboard_insights import TZ, make_ctx

B = {"score": 0.6, "d": 1, "h4": 1, "h1": -1, "label": "BULLISH", "state": "BULLISH", "suspended": False, "in_doubt": False}


def test_endpoint_shape(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.state.bias["XAUUSD"] = dict(B, price=2650.0)
    r = TestClient(build_app(ctx)).get("/api/bias_grid").json()
    assert [t["key"] for t in r["tfs"]] == ["d", "h4", "h1", "m15", "m5"]
    row = next(x for x in r["rows"] if x["symbol"] == "XAUUSD")
    assert row["cells"]["d"] == 1 and row["cells"]["h1"] == -1 and row["cells"]["m15"] in (-1, 0, 1)
    assert row["context"] == "Bullish" and row["eligibility"]["state"] == "ready"
    assert "longs only" in row["eligibility"]["why"]
    assert row["last_signal"]["action"] == "taken"


def test_eligibility_order(tmp_path):
    ctx = make_ctx(tmp_path)
    st, now = ctx.state, ctx.state.now                                     # 10:30 NY: inside 08:30–11:30
    e = lambda b=B: biasgrid.eligibility(ctx, "XAUUSD", b, st.now)        # noqa: E731
    assert e(None)["label"] == "Warming up"
    assert e(dict(B, label="NEUTRAL", state="NEUTRAL"))["label"] == "No clear bias"
    assert e(dict(B, suspended=True))["label"] == "Bias suspended"
    assert "half size" in e(dict(B, in_doubt=True))["why"]
    st.now = pd.Timestamp("2026-10-14 12:10", tz=TZ)
    w = e()
    assert w["label"] == "Outside entry window" and "13:30" in w["why"]
    st.news_block = {"title": "CPI", "tier": "tier1"}
    assert e()["label"] == "News blackout"
    st.trading_enabled = False
    assert e()["label"] == "Entries paused"
    p = Position("XAUUSD", -1, "c10_afternoon:5m@v2", 2660.0, 2660.0, 10.0, 2.0, now)
    p.add_leg(Leg(1.0, 2650.0, now, "initial")); p.last_price = 2645.0
    st.positions[p.id] = p
    o = e()
    assert o["state"] == "open" and o["why"].startswith("Short c10_afternoon") and "+0.50R" in o["why"]


def test_books_daily(tmp_path):
    ctx = make_ctx(tmp_path)
    r = TestClient(build_app(ctx)).get("/api/books_daily").json()
    live = r["books"][0]
    assert live["book"] == "live" and "2026-10-14" in live["days"] and live["days"]["2026-10-14"]["trades"] == 1
