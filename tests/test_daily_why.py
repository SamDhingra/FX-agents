"""Nov 9 2026: the daily RSI2/ADX2 diagnostic rebuilds the book's daily closes with the book's own code."""
import numpy as np
import pandas as pd

from fxagents.agents.daily_rule_trader import daily_frame, rule_state
from fxagents.daily_why import report, table

NY = "America/New_York"


def hourly(trend):
    idx = pd.date_range("2026-05-01 00:00", "2026-11-06 17:00", freq="1h", tz=NY)
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(3)
    px = 4000 + np.cumsum(rng.normal(trend, 2.0, len(idx)))
    return pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px}, index=idx)


def test_rows_match_the_books_own_rule():
    h1 = hourly(0.3)
    t = table(h1, pd.Timestamp("2026-10-20"), pd.Timestamp("2026-11-06 18:00", tz=NY))
    assert len(t) == 14 and (t.note == "").all()
    r = t.iloc[-1]
    st = rule_state(daily_frame(h1, r.close_at))
    assert r.entry == st["entry"] and r.above_sma50 == (st["c"] > st["sma50"]) and r.bot_window_days >= 60
    assert t.above_sma50.all()                                   # a steady uptrend sits above its 50-day average


def test_a_downtrend_blocks_the_long_only_rule():
    t = table(hourly(-0.3), pd.Timestamp("2026-10-20"), pd.Timestamp("2026-11-06 18:00", tz=NY))
    assert not t.entry.any() and not t.above_sma50.any()
    md = report(t, "XAUUSD")
    assert "0 entry signal(s) in 14 daily closes" in md and "above SMA50 0" in md


def test_the_command_finds_oandas_instrument_name_in_sim_mode():
    from fxagents.config import load_config
    from fxagents.oanda import _inst
    from fxagents.trade_atlas import journal_cfg
    cfg = load_config("config.yaml")
    cfg["mode"] = "sim"                                     # how ./fx.sh runs read-only commands
    c = journal_cfg(cfg)
    assert _inst(c, "XAUUSD") == "XAU_USD" and cfg["mode"] == "sim"   # the caller's config is left alone
