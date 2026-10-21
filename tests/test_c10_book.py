"""c10_afternoon shadow book: the same 13:00 decisions as the backtest plugin, entry at 13:00, out at the target or
15:45, one trade a day."""
import asyncio
import copy

import numpy as np
import pandas as pd

from fxagents.agents.c10_trader import STRATEGY, C10Trader, c10_signal
from fxagents.broker import PaperBroker
from fxagents.bt import data, engine
from fxagents.bt.run import load_plugin
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.models import Bar
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


def ndq_minutes(days=90, seed=11):
    idx = pd.date_range("2025-03-03", periods=days * 1440, freq="1min", tz="UTC")
    idx = idx[idx.tz_convert(TZ).dayofweek < 5]
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 1.5, len(idx) // 600 + 1), 600)[:len(idx)]
    p = 29000 + np.cumsum(rng.normal(0, 6, len(idx)) + drift)
    o, c = np.r_[p[0], p[:-1]], p
    w = np.abs(rng.normal(0, 3, len(idx)))
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) + w, "low": np.minimum(o, c) - w, "close": c}, index=idx)
    for f, k in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
        d[f"bid_{f}"], d[f"ask_{f}"] = d[k] - 1.15, d[k] + 1.15
    d["volume"] = 1.0
    return d


def m15(m1):
    return m1[["open", "high", "low", "close"]].tz_convert(TZ).resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def test_signals_match_the_backtest_plugin():
    m1 = ndq_minutes()
    cls, _ = load_plugin("btplugins/gpt_c10_afternoon_continuation_v2.py")
    want = {(pd.Timestamp(s.t, tz="UTC").tz_convert(TZ).date(), s.side) for s in cls().signals(data.from_frame(m1, symbol="NDQ"))}
    b = m15(m1)
    got = set()
    for i in np.flatnonzero((b.index.hour == 12) & (b.index.minute == 45)):
        st = c10_signal(b.iloc[:i + 1], TZ)
        if st:
            got.add((b.index[i].date(), st["side"]))
    first = b.index[120].date()
    assert got and got == {x for x in want if x[0] >= first}


class FS:
    def __init__(self, b, st): self.b, self.st = b, st
    def tf(self, sym, rule): return self.b[self.b.index + pd.Timedelta("15min") <= self.st.now]


class J:
    def __init__(self): self.signals = []
    def add_signal(self, s): self.signals.append(s)
    def trades(self, limit=50, status=None): return []


def test_book_enters_at_13_and_exits_by_1545():
    from fxagents.agents.core import Ctx
    m1 = ndq_minutes()
    cfg = copy.deepcopy(CFG)
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 100000
    bus = Bus()
    closed = []
    bus.subscribe("position_closed", lambda ev: closed.append(ev["position"]))
    ctx = Ctx(cfg, bus, st, FS(m15(m1), st), PaperBroker(cfg, st, bus), J(), None, None)
    tr = C10Trader(ctx); tr.start()
    loc = m1.tz_convert(TZ)
    sel = loc[((loc.index.hour == 12) & (loc.index.minute == 59)) | ((loc.index.hour >= 13) & (loc.index.hour < 16))]

    async def go():
        for ts, r in sel.iterrows():
            st.now = ts + pd.Timedelta("1min"); st.last_prices["NDQ"] = r.close
            b = Bar("NDQ", ts, r.open, r.high, r.low, r.close, 1.0)
            await ctx.broker.on_bar(b)
            await tr.on_bar(b)
    asyncio.run(go())
    taken = [s for s in tr.ctx.journal.signals if s["action"] == "taken"]
    assert taken and closed
    for p in closed:
        o = p.opened_ts.tz_convert(TZ)
        assert (o.hour, o.minute) == (13, 0)
        c = p.closed_ts.tz_convert(TZ)
        assert c.hour * 60 + c.minute <= 945 and p.exit_reason in ("target", "time_1545", "stop")
    assert len({p.opened_ts.tz_convert(TZ).date() for p in closed}) == len(closed)          # one a day
    assert not any(p.status == "open" for p in st.positions.values() if p.strategy == STRATEGY)
