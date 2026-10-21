"""Books summary: a paper book added today must not hide the other books' earlier trades."""
from types import SimpleNamespace

import pandas as pd

from fxagents.dashboard.server import league
from fxagents.journal import Journal


def jrnl(tmp_path, name, closed_times, signal_ts=None):
    j = Journal(str(tmp_path / f"{name}.sqlite"))
    for i, t in enumerate(closed_times):
        j.db.execute("INSERT INTO trades (id, symbol, side, strategy, status, opened, closed, realized, r_multiple) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", (f"{name}{i}", "NDQ", "LONG", name, "closed", t, t, 10.0, 1.0))
    if signal_ts:
        j.db.execute("INSERT INTO signals (ts, symbol, strategy, action) VALUES (?,?,?,?)", (signal_ts, "NDQ", name, "taken"))
    j.db.commit()
    return j


def book(j, mode):
    return SimpleNamespace(journal=j, selection_mode=mode, state=SimpleNamespace(positions={}))


def test_new_book_does_not_blank_the_others(tmp_path):
    now = pd.Timestamp("2026-10-21 13:30", tz="America/New_York")
    old = jrnl(tmp_path, "playbook", ["2026-10-20T10:00:00-04:00", "2026-10-21T09:45:00-04:00", "2026-10-21T11:10:00-04:00"])
    new = jrnl(tmp_path, "c10_afternoon", [], signal_ts="2026-10-21T13:00:00-04:00")
    live = jrnl(tmp_path, "live", ["2026-10-21T10:30:00-04:00"])
    ctx = SimpleNamespace(state=SimpleNamespace(now=now, positions={}), journal=live,
                          shadows={"playbook": book(old, "playbook"), "c10_afternoon": book(new, "c10_afternoon")})
    lg = league(ctx, "today")
    rows = {r["book"]: r for r in lg["rows"]}
    assert rows["playbook"]["trades"] == 2 and rows["live"]["trades"] == 1      # this morning's trades still count
    assert rows["c10_afternoon"]["trades"] == 0 and rows["c10_afternoon"]["since"].startswith("2026-10-21T13:00")
    assert lg["since"].startswith("2026-10-21T00:00")
