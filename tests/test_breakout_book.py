"""gold_breakout shadow book: same entries as the backtest (fxagents/breakout_test.py), 1% stop, one trade per broker
day, flagged flat at 20:00 GMT+3, Jev logged but never gating, no chasing after a restart."""
import asyncio
import copy

import numpy as np
import pandas as pd

from fxagents.agents.breakout_trader import STRATEGY, BreakoutTrader
from fxagents.agents.core import Ctx
from fxagents.breakout_test import run
from fxagents.agents.setup_first import ShadowBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.data import BarStore
from fxagents.models import Bar
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]
SP = float(CFG["shadow"]["spread"]["XAUUSD"])


def mids(days=6, seed=3):
    idx = pd.date_range("2026-03-01 22:00", periods=days * 1440, freq="1min", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    p = 2900 + np.cumsum(np.random.default_rng(seed).normal(0, 0.5, len(idx)))
    o = np.r_[p[0], p[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, p) + 0.15, "low": np.minimum(o, p) - 0.15, "close": p,
                         "volume": 10.0}, index=idx)


def bidask(m):
    d = {f"{s}_{f}": m[{"o": "open", "h": "high", "l": "low", "c": "close"}[f]] + sh
         for s, sh in (("bid", -SP / 2), ("ask", SP / 2)) for f in "ohlc"}
    d.update({f"m_{f}": m[{"o": "open", "h": "high", "l": "low", "c": "close"}[f]] for f in "ohlc"})
    return pd.DataFrame(d, index=m.index)


class J:
    def __init__(self): self.signals = []
    def add_signal(self, s): self.signals.append(s)


class FakeJev:
    def __init__(self): self.calls = 0
    async def breakout_follow(self, info):
        self.calls += 1
        return {"prob": 0.1, "confidence": 0.9, "source": "test"}          # a bad read: must not block


def replay(m, start_at=0):
    cfg = copy.deepcopy(CFG)
    cfg["shadow"]["gold_breakout"]["risk_pct"] = 0.01          # futures multiplier 10 here: 1% stop ≈ $290/unit
    store = BarStore(TZ, max_days=10)
    st = LiveState(); st.equity = st.day_start_equity = st.equity_peak = 70000
    bus = Bus()
    jev = FakeJev()
    ctx = Ctx(cfg, bus, st, store, ShadowBroker(cfg, st, bus, {"XAUUSD": SP}), J(), jev, None)
    tr = BreakoutTrader(ctx); tr.start()
    ml = m.copy(); ml.index = ml.index.tz_convert(TZ)

    async def go():
        for i, (ts, r) in enumerate(ml.iterrows()):
            b = Bar("XAUUSD", ts, r.open, r.high, r.low, r.close, r.volume)
            store.append(b)
            st.now = ts + pd.Timedelta("1min"); st.last_prices["XAUUSD"] = r.close
            if i < start_at:
                continue
            for p in list(st.positions.values()):          # stand-in for the position manager: flagged → closed
                if p.status == "open" and p.meta.get("pending_close"):
                    p.status = "closed"; p.meta["closed_at"] = ts
            await tr.on_bar(b)
    asyncio.run(go())
    return [p for p in st.positions.values() if p.strategy == STRATEGY], ctx, jev


def test_book_entries_match_backtest():
    m = mids()
    ps, ctx, jev = replay(m)
    bt, _ = run(bidask(m), 20, "pct", np.random.default_rng(0))
    day0 = (m.index[0] + pd.Timedelta(hours=3)).normalize()
    ps = [p for p in ps if (pd.Timestamp(p.opened_ts).tz_convert("UTC") + pd.Timedelta(hours=3)).normalize() > day0]
    assert len(ps) == len(bt) >= 3                                     # the backtest skips the first day of history
    for p, t in zip(sorted(ps, key=lambda p: p.opened_ts), bt):
        assert p.side == t["side"]
        assert abs(p.legs[0].price - t["entry"]) <= 0.051              # same fill (rounded to the 0.1 tick)
        assert abs(p.initial_stop - t["entry"] * (1 - t["side"] * 0.01)) <= 0.051
    assert jev.calls >= len(ps) and all(p.jev_quality == 0.1 for p in ps)   # bad read logged, trade taken anyway


def test_one_trade_per_day_and_flat_at_20_gmt3():
    ps, _, _ = replay(mids())
    days = [(pd.Timestamp(p.opened_ts).tz_convert("UTC") + pd.Timedelta(hours=3)).normalize() for p in ps]
    assert len(days) == len(set(days))
    for p in ps:
        c = p.meta.get("closed_at")
        assert p.meta.get("pending_close") == "close_hour" and c is not None
        assert c.tz_convert("UTC").hour == 17 and c.tz_convert("UTC").minute == 0   # flagged on the 16:59 bar


def test_restart_after_breakout_does_not_chase():
    m = mids()
    ps_full, _, _ = replay(m)
    first = min(pd.Timestamp(p.opened_ts) for p in ps_full)
    k = int(np.searchsorted(m.index, first.tz_convert("UTC"))) + 30           # start 30 minutes after that fill
    ps, _, _ = replay(m, start_at=k)
    day = lambda t: (pd.Timestamp(t).tz_convert("UTC") + pd.Timedelta(hours=3)).normalize()
    assert day(first) not in {day(p.opened_ts) for p in ps}
