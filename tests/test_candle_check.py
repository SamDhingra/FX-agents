"""Entry vs the close of the setup candle (Oct 29 2026)."""
import json

from fxagents import candle_check as CC
from fxagents.journal import Journal


def _trade(j, tid, strategy, start, opened):
    draw = json.dumps([{"k": "mark", "px": 1.0, "t0": start, "label": "signal bar", "role": "signal"}])
    j.db.execute("INSERT INTO trades(id, symbol, side, strategy, status, opened, draw) VALUES (?,?,?,?,?,?,?)",
                 (tid, "XAUUSD", "LONG", strategy, "closed", opened, draw))
    j.db.commit()


def test_flags_only_entries_before_their_own_candle_closed(tmp_path):
    main = tmp_path / "journal.sqlite"
    j = Journal(str(main))
    _trade(j, "ok", "dtfx_close_origin:5m@v1", "2026-10-28T10:00:00-04:00", "2026-10-28T10:05:03-04:00")
    _trade(j, "bad", "dtfx_close_origin:5m@v1", "2026-10-28T10:00:00-04:00", "2026-10-28T10:03:00-04:00")
    _trade(j, "h", "smc_ifvg:15m@v1", "2026-10-28T11:00:00-04:00", "2026-10-28T11:15:01-04:00")
    j.db.execute("INSERT INTO trades(id, symbol, strategy, opened) VALUES ('old','NDQ','x:5m@v1','2026-10-01T10:00:00-04:00')")
    j.db.commit()
    s = Journal(str(tmp_path / "journal_playbook_allhours.sqlite"))
    _trade(s, "s1", "sr_rejection:3m@v1", "2026-10-28T10:03:00-04:00", "2026-10-28T10:06:01-04:00")
    summ = CC.run(main, tmp_path / "out")
    assert summ["live"] == {"checked": 3, "early": 1}
    assert summ["playbook_allhours"] == {"checked": 1, "early": 0}
    rep = (tmp_path / "out" / "report.md").read_text()
    assert "this is a bug to fix" in rep and "| live | XAUUSD | dtfx_close_origin:5m@v1 | 10:00 (5m) | 10:05 | 10:03:00 | 120 s |" in rep


def test_timeframe_parsing():
    assert CC.tf_minutes("smc_ifvg:15m@v1") == 15 and CC.tf_minutes("x:1h@v2") == 60
    assert CC.tf_minutes("gold_breakout", "5min") == 5 and CC.tf_minutes("gold_breakout") is None


def test_by_symbol_groups_closed_trades_per_instrument(tmp_path):
    """Oct 30 2026: the instrument × book table on Compare."""
    from fxagents.dashboard.server import by_symbol
    j = Journal(str(tmp_path / "j.sqlite"))
    rows = [("a", "XAUUSD", "closed", "2026-10-29T10:00:00-04:00", 1.0, 100.0), ("b", "XAUUSD", "closed", "2026-10-30T10:00:00-04:00", -1.0, -90.0),
            ("c", "NDQ", "closed", "2026-10-30T11:00:00-04:00", 0.5, 40.0), ("d", "NDQ", "open", None, None, None)]
    for r in rows:
        j.db.execute("INSERT INTO trades(id, symbol, status, closed, r_multiple, realized) VALUES (?,?,?,?,?,?)", r)
    j.db.commit()
    assert by_symbol(j, None) == {"XAUUSD": {"trades": 2, "wins": 1, "sum_r": 0.0, "pnl": 10.0},
                                  "NDQ": {"trades": 1, "wins": 1, "sum_r": 0.5, "pnl": 40.0}}
    assert by_symbol(j, "2026-10-30T00:00:00-04:00")["XAUUSD"]["trades"] == 1
