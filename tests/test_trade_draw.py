"""The setup's drawing travels signal → position → journal → API, and old journals gain the column."""
import json
import sqlite3
from datetime import datetime, timezone

from fxagents.journal import Journal
from fxagents.models import Position


def test_old_journal_gets_the_draw_column_and_round_trips(tmp_path):
    p = tmp_path / "j.sqlite"
    Journal(str(p)).db.close()
    db = sqlite3.connect(p)
    db.execute("ALTER TABLE trades DROP COLUMN draw")                       # what a journal from before Oct 19 looks like
    db.commit(); db.close()
    j = Journal(str(p))
    assert "draw" in {r[1] for r in j.db.execute("PRAGMA table_info(trades)")}


def test_position_drawing_is_journaled(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    pos = Position("XAUUSD", 1, "dtfx_close_fib:15m@pb", 2990.0, 2990.0, 10.0, 1.0, datetime(2026, 10, 19, 14, tzinfo=timezone.utc))
    pos.meta["draw"] = [{"k": "line", "px": 2995.0, "t0": "2026-10-19T09:00:00-04:00", "label": "50% fib", "role": "level"}]
    j.upsert_trade(pos, 1.0)
    row = dict(j.db.execute("SELECT draw FROM trades WHERE id=?", (pos.id,)).fetchone())
    assert json.loads(row["draw"])[0]["label"] == "50% fib"
    assert pos.to_public(1.0)["draw"][0]["px"] == 2995.0
