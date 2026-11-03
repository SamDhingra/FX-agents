"""Paper book balances survive a restart (Nov 3 2026): rebuilt from the book's own journal, not reset to the practice
account's equity."""
import types

import pandas as pd

from fxagents.agents.setup_first import rebuild_balance
from fxagents.journal import Journal


def _book(tmp_path, eq_rows, trades):
    j = Journal(str(tmp_path / "journal_x.sqlite"))
    for ts, e in eq_rows:
        j.add_equity(ts, e, 0.0)
    for i, (opened, closed, realized, status) in enumerate(trades):
        j.db.execute("INSERT INTO trades(id, symbol, opened, closed, realized, status) VALUES(?,?,?,?,?,?)",
                     (f"t{i}", "XAUUSD", opened, closed, realized, status))
    j.db.commit()
    st = types.SimpleNamespace(equity=70_489.30, equity_peak=70_489.30, day_start_equity=70_489.30, last_prices={})
    broker = types.SimpleNamespace(cash=70_489.30, open_positions={}, mult=lambda s: 1.0)
    return types.SimpleNamespace(journal=j, state=st, broker=broker, cfg={"timezone": "America/New_York"}, book_key="x")


def test_balance_is_start_plus_realized(tmp_path):
    now = pd.Timestamp("2026-11-03 16:20", tz="America/New_York")
    b = _book(tmp_path, [("2026-10-20T09:00-04:00", 70_000.0), ("2026-11-03T16:00-05:00", 70_489.30)], [
        ("2026-10-21T10:00-04:00", "2026-10-21T11:00-04:00", 500.0, "closed"),
        ("2026-10-22T10:00-04:00", "2026-10-22T12:00-04:00", -300.0, "closed"),
        ("2026-11-03T09:00-05:00", "2026-11-03T10:00-05:00", 694.0, "closed"),     # closed today
        ("2026-11-03T15:00-05:00", None, 50.0, "open"),                             # partial taken on an open trade
        ("2026-10-01T10:00-04:00", "2026-10-01T11:00-04:00", 9_999.0, "closed"),   # before the book started: ignored
    ])
    cash = rebuild_balance(b, now)
    assert cash == 70_000 + 500 - 300 + 694 + 50
    assert b.broker.cash == cash and b.state.equity == cash
    assert b.state.day_start_equity == cash - 694
    assert b.state.equity_peak == 70_000 + 500 - 300 + 694 + 50


def test_two_books_no_longer_share_a_balance(tmp_path):
    now = pd.Timestamp("2026-11-03 16:20", tz="America/New_York")
    a = _book(tmp_path / "a" if (tmp_path / "a").mkdir() is None else None, [("2026-10-20T09:00-04:00", 70_000.0)],
              [("2026-10-21T10:00-04:00", "2026-10-21T11:00-04:00", 1_000.0, "closed")])
    b = _book(tmp_path / "b" if (tmp_path / "b").mkdir() is None else None, [("2026-10-20T09:00-04:00", 70_000.0)],
              [("2026-10-21T10:00-04:00", "2026-10-21T11:00-04:00", -400.0, "closed")])
    assert rebuild_balance(a, now) == 71_000 and rebuild_balance(b, now) == 69_600


def test_fresh_book_keeps_its_starting_equity(tmp_path):
    b = _book(tmp_path, [], [])
    assert rebuild_balance(b, pd.Timestamp("2026-11-03 16:20", tz="America/New_York")) is None
    assert b.broker.cash == 70_489.30
