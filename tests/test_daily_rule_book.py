"""daily_rsi2_adx2 shadow book: the same entries and exits as the backtest plugin, fills after the daily close,
held overnight (not flattened), rollovers recorded, open trades re-adopted after a restart."""
import asyncio
import copy

import numpy as np
import pandas as pd

from fxagents.agents.core import Ctx
from fxagents.agents.daily_rule_trader import STRATEGY, DailyRuleTrader, daily_frame, rule_state
from fxagents.broker import PaperBroker
from fxagents.bt import data, engine
from fxagents.bt.run import load_plugin
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.journal import Journal
from fxagents.models import Bar
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


def btc_minutes(days=260, seed=3):
    """24/7 synthetic BTC-like minutes with trending stretches; mid OHLC + bid/ask (spread 10)."""
    idx = pd.date_range("2025-01-01 00:00", periods=days * 1440, freq="1min", tz="UTC")
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.5, len(idx) // 4000 + 1), 4000)[:len(idx)]
    p = 60000 + np.cumsum(rng.normal(0, 25, len(idx)) + drift)
    o, c = np.r_[p[0], p[:-1]], p
    w = np.abs(rng.normal(0, 15, len(idx)))
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) + w, "low": np.minimum(o, c) - w, "close": c}, index=idx)
    for f, k in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
        d[f"bid_{f}"], d[f"ask_{f}"] = d[k] - 5, d[k] + 5
    d["volume"] = 1.0
    return d


def h1_of(m1):
    return m1[["open", "high", "low", "close"]].tz_convert(TZ).resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def test_daily_candles_and_rule_match_the_backtest_plugin():
    m1 = btc_minutes()
    m = data.from_frame(m1, symbol="BTCUSD")
    cls, _ = load_plugin("btplugins/daily_rsi2_adx2.py")
    want = {int(s.t) for s in cls().signals(m)}
    b = daily_frame(h1_of(m1), pd.Timestamp("2030-01-01", tz=TZ))
    got = {int(pd.Timestamp(b["end"].iloc[i]).value) for i in range(60, len(b)) if rule_state(b.iloc[:i + 1])["entry"]}
    first = int(pd.Timestamp(b["end"].iloc[60]).value)
    assert got and got == {t for t in want if t >= first}


class FS:
    """Stand-in bar store: the hourly history known at the current time."""
    def __init__(self, h1, st): self.H, self.st = h1, st
    def h1(self, sym): return self.H[self.H.index + pd.Timedelta("1h") <= self.st.now]


class J:
    def __init__(self): self.signals = []
    def add_signal(self, s): self.signals.append(s)
    def trades(self, limit=50, status=None): return []


def run_book(m1, journal=None, days=None):
    cfg = copy.deepcopy(CFG)
    cfg["instruments"]["BTCUSD"] = {**cfg["instruments"]["XAUUSD"], "tick_size": 0.01, "qty_step": 0.0001,
                                    "min_units": 0.0001, "multiplier": 1, "max_units": 100}
    cfg["shadow"][STRATEGY] = {"symbols": ["BTCUSD"], "risk_pct": 0.001, "stop_atr": 3.0}
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 70000
    bus = Bus()
    ctx = Ctx(cfg, bus, st, FS(h1_of(m1), st), PaperBroker(cfg, st, bus), journal or J(), None, None)
    tr = DailyRuleTrader(ctx); tr.start()
    loc = m1.tz_convert(TZ)
    sel = loc[(loc.index.hour == 16) & (loc.index.minute == 59) | (loc.index.hour == 17) & (loc.index.minute == 0)]
    if days:
        sel = sel[sel.index >= sel.index[-1] - pd.Timedelta(days=days)]
    closed = []

    async def go():
        for ts, r in sel.iterrows():
            st.now = ts + pd.Timedelta("1min"); st.last_prices["BTCUSD"] = r.close
            await tr.on_bar(Bar("BTCUSD", ts, r.open, r.high, r.low, r.close, 1.0))
            for p in list(st.positions.values()):                # stand-in for the position manager's close
                if p.status == "open" and p.meta.get("pending_close") and ts.hour == 17:
                    p.status = "closed"; closed.append(p)
    asyncio.run(go())
    return tr, st, closed


def test_book_enters_after_the_close_holds_and_counts_rollovers():
    m1 = btc_minutes()
    tr, st, closed = run_book(m1)
    ps = [p for p in st.positions.values() if p.strategy == STRATEGY]
    assert len(ps) > 3 and closed
    for p in ps:
        assert p.opened_ts.tz_convert(TZ).hour == 17 and p.opened_ts.tz_convert(TZ).minute == 1   # filled after the close
        assert p.meta["hold_overnight"] and p.initial_stop < p.entry
    assert any(p.meta["rollovers"] >= 1 for p in closed)
    m = data.from_frame(m1, symbol="BTCUSD")
    cls, _ = load_plugin("btplugins/daily_rsi2_adx2.py")
    bt = engine.simulate(cls(), m, controls=False)["trades"]
    days_bt = {pd.Timestamp(t["entry_time"]).tz_convert(TZ).date() for t in bt}
    days_book = {p.opened_ts.tz_convert(TZ).date() for p in ps}
    assert len(days_book & days_bt) >= 0.8 * len(days_book)         # same trades (the book needs 60 days to warm up)


def test_open_trade_survives_a_restart(tmp_path):
    m1 = btc_minutes()
    j = Journal(str(tmp_path / "j.sqlite"))
    tr, st, _ = run_book(m1, journal=j)
    open_ = [p for p in st.positions.values() if p.status == "open" and p.strategy == STRATEGY]
    for p in st.positions.values():
        j.upsert_trade(p, 1.0)
    tr2, st2, _ = run_book(m1, journal=j, days=0)
    again = [p for p in st2.positions.values() if p.strategy == STRATEGY and any(e.get("kind") == "readopted" for e in p.events)]
    assert {p.id for p in again} == {p.id for p in open_}


def test_position_manager_doesnt_flatten_a_held_overnight_trade():
    import inspect
    from fxagents.agents import trading
    src = inspect.getsource(trading.PositionManagerAgent)
    assert 'if not pos.meta.get("hold_overnight") and ((_hm(s["flatten_at"])' in src
