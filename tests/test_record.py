import sqlite3

from fxagents.record import table


def test_record_groups_by_book_and_strategy(tmp_path):
    for name, rows in {"journal.sqlite": [("a", 100.0, 1.0), ("a", -50.0, -0.5)],
                       "journal_gold_breakout.sqlite": [("b", -10.0, -1.0)]}.items():
        db = sqlite3.connect(tmp_path / name)
        db.execute("CREATE TABLE trades(symbol, strategy, status, realized, r_multiple, opened)")
        db.executemany("INSERT INTO trades VALUES('XAUUSD', ?, 'closed', ?, ?, '2026-10-10T10:00')", rows)
        db.commit()
    t = table("XAUUSD", str(tmp_path))
    assert "| live | a | 2 | 50% | +0.250 | +0.50 | +50 |" in t
    assert "| gold_breakout | b | 1 | 0% | -1.000 |" in t
    assert table("NDQ", str(tmp_path)).startswith("No closed NDQ")
