"""Time machine, edge atlas, recap, trade notes per book, home-screen app files."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.dashboard import extras
from fxagents.dashboard.server import build_app
from tests.test_dashboard_insights import make_ctx

TZ = "America/New_York"


def test_timeline_and_recap(tmp_path):
    ctx = make_ctx(tmp_path)
    c = TestClient(build_app(ctx))
    tl = c.get("/api/timeline", params={"day": "2026-10-14"}).json()
    assert tl["day"] == "2026-10-14" and [t["id"] for t in tl["trades"]] == ["recent"]
    assert tl["signals"][0]["action"] == "taken" and tl["decisions"][0]["kind"] == "signal_rating"
    assert len(tl["bars"]["XAUUSD"]) > 100                       # 5-minute candles 00:00–10:29
    rc = c.get("/api/recap", params={"day": "2026-10-14"}).json()
    live = rc["books"][0]
    assert live["trades"] == 1 and live["sum_r"] == 0.5 and "closed 1 trade" in rc["script"] and rc["source"] == "facts"


def test_atlas_counts_luck_peaks(tmp_path):
    ctx = make_ctx(tmp_path)
    rng = np.random.default_rng(3)
    rows = [("XAUUSD", f"s{k}:5m@v1", "5m", h, 1, float(rng.normal(0, 1))) for k in range(5) for h in range(24) for _ in range(20)]
    ctx.setup_map = SimpleNamespace(map=SimpleNamespace(rows=rows), status={"state": "ready", "built": "x"})
    a = extras.atlas(ctx)
    assert a["state"] == "ready" and a["tested"] == 120 and abs(a["luck_peaks"] - 5.5) < .1
    cell = a["cells"][0]
    assert {"symbol", "setup", "hour", "n", "shrunk", "fog", "t"} <= set(cell) and cell["n"] == 20
    assert TestClient(build_app(ctx)).get("/api/atlas").json()["tested"] == 120


def test_notes_go_to_the_selected_book_and_app_files_are_public(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.cfg["dashboard"]["token"] = "tok"
    sh = make_ctx(tmp_path / "sh")
    ctx.shadows = {"playbook": sh}
    c = TestClient(build_app(ctx), base_url="https://x")
    r = c.post("/api/trades/recent/note?book=playbook", json={"note": "late entry #fomo"}, headers={"x-token": "tok"})
    assert r.status_code == 200
    assert sh.journal.db.execute("SELECT notes FROM trades WHERE id='recent'").fetchone()[0] == "late entry #fomo"
    assert ctx.journal.db.execute("SELECT notes FROM trades WHERE id='recent'").fetchone()[0] is None
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    assert c.get("/sw.js").status_code == 200 and c.get("/icon-192.png").status_code == 200
    assert c.get("/secret.png").status_code == 404 and c.get("/api/atlas").status_code == 401
