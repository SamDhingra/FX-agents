"""Oct 2026 audit, batch 1: strategy lifecycle (F1/F2), signal priority (F4), one-index cap for every book (F7),
Jev gate (no hidden ×0.8, a heuristic fallback never passes), cost-to-risk logging (F6)."""
from __future__ import annotations

import asyncio
import copy

import pandas as pd
import pytest

from fxagents.agents.core import Ctx
from fxagents.agents.trading import RiskAgent, jev_gate, jev_gate_why
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.models import Leg, Position, Signal
from fxagents.state import LiveState

from tests.test_learner import NOW, TZ, fwd, real, setup

CFG = load_config("config.yaml")


# ── F1 / F2: lifecycle ───────────────────────────────────────────────────
def test_f1_demoted_on_real_trades_is_not_switched_back_on_by_simulation(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    fwd(j, parent.id, [0.6] * 30)                          # simulated record looks great …
    real(j, parent.id, [-1.0] * 12 + [1.0] * 4)            # … but 16 real trades lose (−0.5R)
    ag.lc["auto_promote"] = True                           # even with auto-promote on
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(parent.id).status == "shadow"
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))   # and not on the next cycle either
    assert book.get(parent.id).status == "shadow"


def test_f1_reactivation_obeys_auto_promote_off(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    book.set_status(parent.id, "shadow", NOW.isoformat(), "test")
    fwd(j, parent.id, [0.6] * 30)
    ag.lc["auto_promote"] = False
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(parent.id).status == "shadow"
    assert any("would re-activate" in x["msg"] for x in ctx.state.learner_log)
    ag.lc["auto_promote"] = True
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert book.get(parent.id).status == "live"


def _only_two_live(book, a, b, ts):
    for s in list(book.items.values()):
        if s.id not in (a, b) and s.status == "live":
            book.set_status(s.id, "shadow", ts, "test")


def test_f2_last_strategies_can_be_demoted_but_the_best_stays_on_probation(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    other = next(s for s in book.items.values() if s.status == "live" and s.id != parent.id)
    _only_two_live(book, parent.id, other.id, NOW.isoformat())
    fwd(j, parent.id, [-0.2, -0.4] * 15)                   # −0.30R
    fwd(j, other.id, [-0.1, -0.1] * 15)                    # −0.10R : the less bad one
    ag.lc["min_live"] = 1
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    live = [s.id for s in book.items.values() if s.status == "live"]
    assert live == [other.id]                              # the account keeps trading with one strategy
    assert book.get(other.id).meta.get("probation") is True
    assert book.get(parent.id).status == "shadow"
    # zero live is allowed when the floor is 0
    ag.lc["min_live"] = 0
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert [s for s in book.items.values() if s.status == "live"] == []


def test_f2_probation_ends_when_enough_good_strategies_exist(tmp_path):
    ctx, ag, book, j, parent, child = setup(tmp_path)
    other = next(s for s in book.items.values() if s.status == "live" and s.id != parent.id)
    _only_two_live(book, parent.id, other.id, NOW.isoformat())
    other.meta = {"probation": True}
    fwd(j, parent.id, [0.3] * 30)                          # a good one live …
    fwd(j, other.id, [0.1] * 30)                           # … and the probation one recovered
    ag.lc["min_live"] = 1
    asyncio.run(ag.promote_demote(NOW, NOW.isoformat()))
    assert not book.get(other.id).meta.get("probation") and book.get(other.id).status == "live"


# ── F4: same priority in research and live ───────────────────────────────
def test_f4_portfolio_prefers_expectancy_over_win_rate():
    from fxagents import playbook as P
    t0 = pd.Timestamp("2026-08-03 09:40", tz=TZ)
    rows = [{"sym": "XAUUSD", "tf": "5min", "setup": s, "variant": "default", "mgmt": "std", "ts": t0, "side": 1,
             "day": t0.date(), "r": 1.0, "bars": 12, "p": p, "e": e}
            for s, p, e in (("high_win_low_e", 0.70, 0.05), ("low_win_high_e", 0.50, 0.30))]
    pf = P.portfolio(pd.DataFrame(rows), P.Policy())
    assert list(pf["setup"]) == ["low_win_high_e"]


# ── Jev gate ─────────────────────────────────────────────────────────────
def test_jev_gate_uses_the_configured_confidence_exactly():
    jc = {**CFG["jev"], "signal_gate": "enforce", "min_signal_quality": 0.5, "min_signal_confidence": 0.5}
    assert not jev_gate({"quality": 0.7, "confidence": 0.45}, jc)      # used to pass: 0.45 ≥ 0.5 × 0.8
    assert jev_gate({"quality": 0.7, "confidence": 0.50}, jc)
    assert "confidence 0.45 < 0.50" in jev_gate_why({"quality": 0.7, "confidence": 0.45}, jc)
    assert CFG["jev"]["min_signal_confidence"] == 0.4                    # the bar that was in force, now explicit


def test_a_heuristic_fallback_grade_never_passes_the_enforce_gate():
    jc = {**CFG["jev"], "signal_gate": "enforce"}
    g = {"quality": 0.95, "confidence": 0.95, "source": "heuristic", "fallback": True}
    assert not jev_gate(g, jc) and "unavailable" in jev_gate_why(g, jc)
    assert jev_gate({**g, "fallback": False}, jc)                        # no key at all (sim/replay) is a different thing
    adv = {**jc, "signal_gate": "advisory"}
    assert jev_gate(g, adv) and g["size_mult"] == 0.5                    # advisory: trades, but at the minimum size


def test_scorer_flags_a_fallback_only_when_jev_was_supposed_to_answer():
    from fxagents.jev import JevScorer
    cfg = copy.deepcopy(CFG); st = LiveState(); st.now = NOW
    sc = JevScorer(cfg, st, Bus())
    sig = {"strategy": "x", "side": "LONG", "symbol": "NDQ", "entry": 1, "stop": 0.9, "strategy_expectancy": 0.1,
           "strategy_win_rate": 0.5, "htf_bias": 1, "risk_atr": 1.0, "rsi": 50}
    sc.live = False                                                      # no key: the heuristic is the design
    assert asyncio.run(sc.rate_signal(dict(sig)))["fallback"] is False
    sc.live = True                                                       # a key, but the call fails
    class Boom:
        async def system_one(self, **kw): raise TimeoutError("slow")
    sc.client = Boom()
    out = asyncio.run(sc.rate_signal(dict(sig)))
    assert out["fallback"] is True and out["source"] == "heuristic"


# ── F7 / F6: Risk ─────────────────────────────────────────────────────────
class _Broker:
    price_bound = False
    def __init__(self, quote=None): self._q = quote; self.opened = []
    async def quote(self, sym): return self._q
    async def equity(self): return 100000.0
    async def open(self, p, qty, ref):
        self.opened.append(qty)
        p.add_leg(Leg(qty, ref, p.opened_ts, "initial"))
        return ref


def _risk(tmp_path, held=(), quote=None, **risk):
    cfg = copy.deepcopy(CFG); cfg["mode"] = "paper"; cfg["risk"].update(risk)
    for s in ("NDQ", "US30"):
        cfg["instruments"][s].update(margin_rate=0)
    st = LiveState(mode="paper"); st.now = pd.Timestamp("2026-10-08 09:00", tz=TZ); st.equity = 100000.0
    for s in ("NDQ", "US30"):
        st.last_prices[s] = 20000.0
        st.bias[s] = {"suspended": False, "score": 1.0, "in_doubt": False, "label": "BULLISH", "d": 1, "h4": 1, "h1": 1}
    for k, s in enumerate(held):
        p = Position(s, 1, f"held{k}", 19900.0, 19900.0, 100.0, 1.0, st.now)
        p.add_leg(Leg(1.0, 20000.0, st.now, "initial"))
        st.positions[p.id] = p

    class J:
        rows: list = []
        def add_signal(self, s): self.rows.append(s)
    br = _Broker(quote)
    ctx = Ctx(cfg, Bus(), st, None, br, J(), None, None)
    ra = RiskAgent(ctx); ra.start()
    return ra, st, br, ctx


def _ask(ra, st, sym, stop=19900.0):
    sig = Signal(sym, "plain:5m@v1", 1, 20000.0, stop, st.now)
    rec = {"ts": st.now.isoformat(), "symbol": sym, "strategy": sig.strategy, "side": "LONG", "entry": 20000.0, "stop": stop}
    asyncio.run(ra.on_request({"signal": sig, "grade": {"quality": 0.8, "confidence": 0.8, "source": "test"}, "record": rec}))
    return ra.ctx.journal.rows[-1]


def test_f7_one_index_position_at_a_time_for_every_book(tmp_path):
    ra, st, br, ctx = _risk(tmp_path, held=["NDQ"])
    row = _ask(ra, st, "US30")                                           # no playbook metadata on this request
    assert row["action"] == "rejected" and "index group full" in row["why"] and not br.opened


def test_f7_cap_does_not_touch_other_instruments(tmp_path):
    ra, st, br, ctx = _risk(tmp_path, held=["NDQ"])
    cfg_inst = ra.cfg["instruments"]
    if "XAUUSD" in cfg_inst:
        st.last_prices["XAUUSD"] = 4000.0
        st.bias["XAUUSD"] = st.bias["NDQ"]
        row = _ask(ra, st, "XAUUSD", stop=3980.0)
        assert "index group" not in row["why"]


def test_f6_entry_logs_its_cost_in_r_and_flags_the_cap(tmp_path):
    q = (19998.0, 20002.0)                                               # 4-point spread, 100-point stop → 0.04R
    ra, st, br, ctx = _risk(tmp_path, quote=q)
    row = _ask(ra, st, "NDQ")
    assert row["action"] == "taken" and "cost 0.04R" in row["why"] and "over the" not in row["why"]
    ra, st, br, ctx = _risk(tmp_path, quote=(19990.0, 20010.0))          # 20-point spread vs a 110-point stop from the ask → 0.18R, over the 0.10R cap
    row = _ask(ra, st, "NDQ")
    assert row["action"] == "taken" and "over the 0.10R cap — log only" in row["why"]
    ev = next(iter(st.positions.values())).events[-1]
    assert ev.get("over_cost_cap") is True and ev.get("cost_r") == pytest.approx(20 / 110, abs=0.002)   # the stop is 110 from the ask


def test_f6_enforce_blocks_when_switched_on(tmp_path):
    ra, st, br, ctx = _risk(tmp_path, quote=(19990.0, 20010.0), cost_cap_enforce=True)
    row = _ask(ra, st, "NDQ")
    assert row["action"] == "rejected" and "cap 0.10R" in row["why"] and not br.opened
