"""ema21_rsi55 shadow book: same signal as the backtest, takes every signal (Jev logged, never gating),
flags the exit on the first 15m close below EMA21."""
import asyncio
import copy

import numpy as np
import pandas as pd

from fxagents.agents.core import Ctx
from fxagents.agents.ema_rsi_trader import STRATEGY, EmaRsiTrader, entry_signal, frame
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.data import BarStore
from fxagents.models import Bar
from fxagents.simple_rules import bars
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


def m1_series(n=15 * 300, seed=4):
    idx = pd.date_range("2026-03-02 02:00", periods=n, freq="1min", tz=TZ)
    p = 46000 + np.cumsum(np.random.default_rng(seed).normal(0, 4, n))
    return pd.DataFrame({"open": p, "high": p + 2, "low": p - 2, "close": p, "volume": 10.0}, index=idx)


def test_signal_matches_backtest_frame():
    m1 = m1_series()
    bt = m1.rename(columns={"open": "m_o", "high": "m_h", "low": "m_l", "close": "m_c"})
    ref = bars(bt, "15min")                                      # backtest: index = candle END
    live = frame(m1.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}))
    live.index = live.index + pd.Timedelta("15min")
    hits_ref = [t for i, t in enumerate(ref.index[1:], 1)
                if ref.c.iloc[i - 1] <= ref.ema21.iloc[i - 1] and ref.c.iloc[i] > ref.ema21.iloc[i] and ref.rsi.iloc[i] > 55
                and i >= 59]
    hits_live = [live.index[i - 1] for i in range(60, len(live) + 1) if entry_signal(live.iloc[:i])]
    assert hits_ref and hits_live == [t for t in hits_ref if t <= live.index[-1]]


class J:
    def __init__(self): self.signals = []
    def add_signal(self, s): self.signals.append(s)


class FakeJev:
    def __init__(self): self.calls = 0
    async def rate_signal(self, info):
        self.calls += 1
        return {"quality": 0.1, "confidence": 0.9, "htf_aligned": 0.2, "source": "test"}   # a bad grade: must not block


def test_book_takes_signal_logs_jev_and_flags_exit():
    cfg = copy.deepcopy(CFG)
    cfg["shadow"]["ema21_rsi55"] = {"symbols": ["US30"], "risk_pct": 0.001, "stop_atr": 3.0}
    m1 = m1_series()
    store = BarStore(TZ, max_days=10)
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 70000
    bus = Bus()
    jev = FakeJev()
    ctx = Ctx(cfg, bus, st, store, PaperBroker(cfg, st, bus), J(), jev, None)
    tr = EmaRsiTrader(ctx); tr.start()

    async def go():
        for i, (ts, r) in enumerate(m1.iterrows()):
            store.append(Bar("US30", ts, r.open, r.high, r.low, r.close, r.volume))
            st.now = ts + pd.Timedelta("1min"); st.last_prices["US30"] = r.close
            await tr.on_bar(Bar("US30", ts, r.open, r.high, r.low, r.close, r.volume))
            for p in list(st.positions.values()):                # stand-in for the position manager's close
                if p.status == "open" and p.meta.get("pending_close"):
                    p.status = "closed"
    asyncio.run(go())
    taken = [s for s in ctx.journal.signals if s["action"] == "taken"]
    assert taken and jev.calls >= len(taken)
    ps = [p for p in st.positions.values() if p.strategy == STRATEGY]
    assert ps and all(p.meta["jev_quality"] == 0.1 for p in ps)        # bad grade logged, trade still taken
    assert all(p.side == 1 and p.initial_stop < p.entry for p in ps)
    exits = [p for p in ps if p.meta.get("pending_close") == "close_below_ema21"]
    assert exits                                                     # the exit rule fired on a close below EMA21
