"""Nov 9 2026: the gold breakout and gold H1 trend rules also trade the practice account, frozen, inside its limits."""
import asyncio
import copy

import pandas as pd

from fxagents.agents.breakout_trader import BreakoutTrader
from fxagents.agents.core import Ctx
from fxagents.agents.h1_trend_trader import H1VolTrendTrader
from fxagents.agents.trading import account_block
from fxagents.broker import OrderRejected
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.models import Bar, Leg, Position
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = CFG["timezone"]


class J:
    def __init__(self): self.signals = []
    def add_signal(self, s): self.signals.append(s)
    def trades(self, limit=50, status=None): return []


class Broker:
    def __init__(self, reject=False): self.reject, self.opened = reject, []
    async def open(self, pos, qty, ref):
        if self.reject:
            raise OrderRejected("OANDA said no")
        self.opened.append((pos, qty)); return ref
    async def equity(self): return 100000.0


def ctx(broker=None):
    st = LiveState(); st.equity = 100000.0
    st.now = pd.Timestamp("2026-11-03 02:00", tz=TZ)
    return Ctx(copy.deepcopy(CFG), Bus(), st, None, broker or Broker(), J(), None, None)


def test_config_turns_both_on_for_practice_only():
    for k in ("gold_breakout_account", "h1_trend_account"):
        assert CFG[k]["enabled"] and CFG[k]["allow_live"] is False and CFG[k]["risk_pct"] == 0.005
    src = open("main.py").read()
    assert '"gold_breakout_account", BreakoutTrader' in src and '"h1_trend_account", H1VolTrendTrader' in src


def test_account_copies_read_the_account_settings():
    c = ctx()
    b = BreakoutTrader(c, on_account=True); b.start()
    h = H1VolTrendTrader(c, on_account=True); h.start()
    assert b.name == "gold_breakout_trader" and b.risk_pct == 0.005 and b.sl_pct == CFG["shadow"]["gold_breakout"]["sl_pct"]
    assert h.name == "h1_trend_trader" and h.risk_pct == 0.005
    p = BreakoutTrader(ctx()); p.start()
    assert p.name == "trader" and p.risk_pct == CFG["shadow"]["gold_breakout"]["risk_pct"]   # the paper book unchanged


def _breakout_entry(c, on_account):
    b = BreakoutTrader(c, on_account=on_account); b.start()
    b.now = lambda: pd.Timestamp("2026-11-03 02:00", tz=TZ)
    d = {"rh": 4010.0, "rl": 3990.0, "done": False}
    bar = Bar("XAUUSD", pd.Timestamp("2026-11-03 01:59", tz=TZ), 4009.0, 4012.0, 4008.0, 4011.0, 1.0)
    asyncio.run(b.maybe_enter("XAUUSD", d, bar))
    return b, d


def test_account_limits_block_a_second_gold_position():
    c = ctx()
    t0 = pd.Timestamp("2026-11-03 01:00", tz=TZ)
    other = Position("XAUUSD", 1, "smc_mss:5m@pb", 3980.0, 3980.0, 20.0, 1.0, t0)
    other.add_leg(Leg(1.0, 4000.0, t0, "initial"))
    c.state.positions[other.id] = other
    assert account_block(c.cfg, c.state, "XAUUSD", 1) == "already positioned in symbol"
    b, d = _breakout_entry(c, on_account=True)
    assert d["done"] and not c.broker.opened
    assert c.journal.signals[-1]["action"] == "rejected" and "already positioned" in c.journal.signals[-1]["why"]


def test_account_entry_and_a_broker_rejection():
    c = ctx()
    _breakout_entry(c, on_account=True)
    pos, qty = c.broker.opened[0]
    assert pos.strategy == "gold_breakout" and pos.meta["external_mgmt"] and qty > 0
    c2 = ctx(Broker(reject=True))
    _breakout_entry(c2, on_account=True)
    assert not c2.state.positions and "broker guard" in c2.journal.signals[-1]["why"]
