"""TradingView export: valid-looking Pine v6 with one entry per trade, and the right OANDA ticker."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fxagents.config import load_config
from fxagents.dashboard.extras import pine_script, tv_symbol
from fxagents.journal import Journal
from fxagents.models import Leg, Position

CFG = load_config("config.yaml")


def test_pine_marks_each_trade(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    now = datetime.now(timezone.utc)
    for k, (side, closed) in enumerate([(1, True), (-1, True), (1, False)]):
        p = Position("XAUUSD", side, 'dtfx"q:15m@pb', 4090.0, 4090.0, 10, 1.0, now - timedelta(hours=5 - k))
        p.add_leg(Leg(1.0, 4100.0, p.opened_ts, "initial"))
        if closed:
            p.status, p.closed_ts, p.realized = "closed", now - timedelta(hours=4 - k), 12.0 * side
        j.upsert_trade(p, 1.0, 4112.0 if closed else None)
    s = pine_script(CFG, SimpleNamespace(journal=j), "XAUUSD")
    assert s.splitlines()[3] == "//@version=6" and "(3 trades)" in s
    assert "var sides = array.from(1, -1, 1)" in s
    assert "float(na)" in s and ", 0)" in s                       # the open trade: no exit
    assert 'var names = array.from("dtfx\'q:15m"' in s               # a quote in a name can't break the Pine string
    assert "isOpen" in s and "\n        open =" not in s            # never shadow Pine's built-in `open`
    assert tv_symbol(CFG, "NDQ") == "OANDA:NAS100USD" and tv_symbol(CFG, "US30") == "OANDA:US30USD"


def test_pine_without_trades_says_so(tmp_path):
    s = pine_script(CFG, SimpleNamespace(journal=Journal(str(tmp_path / "j.sqlite"))), "NDQ")
    assert "No NDQ trades" in s and "array.from(" not in s
