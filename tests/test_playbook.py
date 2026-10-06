"""Playbook strategy: selection rules, no leakage in the weekly re-selection, capacity rules, and the
trader → Risk → position-manager path (per-instrument caps, index group, scalp exits)."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import numpy as np
import pandas as pd

from fxagents import playbook as P
from fxagents.agents.core import Ctx
from fxagents.agents.playbook_trader import PlaybookHolder, PlaybookTrader
from fxagents.agents.trading import PositionManagerAgent, RiskAgent
from fxagents.broker import PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.journal import Journal
from fxagents.models import Bar, Position, Signal
from fxagents.sim import synth_1m
from fxagents.state import LiveState

CFG = load_config("config.yaml")
TZ = "America/New_York"
DAYS = [d.date() for d in pd.bdate_range("2026-07-06", periods=60)]


def trades_for(sym, tf, setup, wr_first, wr_second, n_per_day=1, mgmt="std", variant="default", win_r=1.0, days=DAYS):
    rows = []
    half = len(days) // 2
    seq = 0
    for k, d in enumerate(days):
        for j in range(n_per_day):
            wr = wr_first if k < half else wr_second
            win = int((seq + 1) * wr) > int(seq * wr)          # exact win rate, wins spread evenly
            seq += 1
            rows.append({"sym": sym, "tf": tf, "setup": setup, "variant": variant, "mgmt": mgmt,
                         "ts": pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=9, minutes=40 + j),
                         "day": d, "r": win_r if win else -1.0, "cost_r": 0.05, "bars": 6, "exit": "x",
                         "side": 1, "hour": 9})
    return rows


def frame(rows):
    return pd.DataFrame(rows)


def test_selection_respects_instrument_rules():
    rows = []
    rows += trades_for("XAUUSD", "5min", "smc_bos_retest", 0.62, 0.62)             # good gold cell
    rows += trades_for("XAUUSD", "5min", "ict_ote", 0.75, 0.20)                    # one good half only → out
    rows += trades_for("XAUUSD", "5min", "smc_mss", 0.40, 0.40)                    # pool filler (drags p0 down)
    rows += trades_for("NDQ", "5min", "ict_silver_bullet", 0.62, 0.62)             # 62% raw: not enough evidence
    rows += trades_for("NDQ", "5min", "smc_mss", 0.40, 0.40)
    rows += trades_for("US30", "5min", "dtfx_close_fib", 0.95, 0.95, n_per_day=2)  # overwhelming evidence → in
    rows += trades_for("US30", "5min", "smc_mss", 0.40, 0.40)
    rows += trades_for("SPX", "5min", "smc_bos_retest", 0.9, 0.9)                  # SPX is off
    rows += trades_for("XAUUSD", "1min", "smc_choch", 0.9, 0.9)                    # 1m not in the policy
    cube = P.CellCube(frame(rows))
    pol = P.Policy()
    sel = P.select(cube.window(0, len(cube.days)), pol)
    got = {(r.sym, r.setup) for r in sel.itertuples()}
    assert ("XAUUSD", "smc_bos_retest") in got
    assert ("XAUUSD", "ict_ote") not in got and ("XAUUSD", "smc_choch") not in got
    assert ("NDQ", "ict_silver_bullet") not in got
    assert ("US30", "dtfx_close_fib") in got
    assert not any(s == "SPX" for s, _ in got)
    assert (sel["p"][sel["sym"] != "XAUUSD"] >= 0.60).all()


def test_weekly_reselection_never_sees_the_week_it_trades():
    # a cell that is awful before mid-August and perfect after: a leaky selection would pick it up early
    days = DAYS
    flip = days.index(pd.Timestamp("2026-08-17").date())
    rows = trades_for("XAUUSD", "5min", "smc_bos_retest", 0.5, 0.5)
    for k, d in enumerate(days):
        win = k >= flip
        rows.append({"sym": "XAUUSD", "tf": "5min", "setup": "ict_2022", "variant": "default", "mgmt": "std",
                     "ts": pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=10), "day": d, "r": 1.0 if win else -1.0,
                     "cost_r": 0.05, "bars": 6, "exit": "x", "side": 1, "hour": 10})
    wf = P.walk_forward(frame(rows), P.Policy(), start_day=days[20])
    picked = wf[wf["setup"] == "ict_2022"]
    assert len(picked) == 0 or pd.Timestamp(picked["day"].min()) >= pd.Timestamp(days[flip]) + pd.Timedelta(days=7)
    # and select_asof's statistics only count trades strictly before the as-of day
    cube = P.CellCube(frame(rows))
    b = int(np.searchsorted(np.array(cube.days), days[30]))
    st = cube.window(b - 60, b)
    n_bos = st[(st["setup"] == "smc_bos_retest")]["n"].iloc[0]
    assert n_bos == 30


def test_portfolio_caps():
    t0 = pd.Timestamp("2026-08-03 09:40", tz=TZ)
    rows = []
    for k, (sym, setup, tf) in enumerate([("XAUUSD", "a", "5min"), ("XAUUSD", "a2", "5min"), ("XAUUSD", "b", "3min"),
                                         ("XAUUSD", "c", "15min"), ("NDQ", "d", "5min"), ("US30", "e", "5min"),
                                         ("SPX", "f", "5min")]):
        rows.append({"sym": sym, "tf": tf, "setup": setup, "variant": "default", "mgmt": "std", "ts": t0, "side": 1,
                     "day": t0.date(), "r": -1.0, "bars": 12, "p": 0.6 - k * 0.01, "e": 0.1})
    pf = P.portfolio(pd.DataFrame(rows), P.Policy())
    # one entry per instrument/TF bar (a2 out), gold ×2 (c out), then ONE index (US30 out), SPX off
    assert list(pf["setup"]) == ["a", "b", "d"]
    # no opposite positions on one instrument
    opp = [dict(rows[0]), dict(rows[2], side=-1)]
    assert list(P.portfolio(pd.DataFrame(opp), P.Policy())["setup"]) == ["a"]
    # daily loss stop: after −4R in a day nothing else is taken that day
    rows = [{"sym": "XAUUSD", "tf": "5min", "setup": f"s{k}", "variant": "default", "mgmt": "std", "side": 1,
             "ts": t0 + pd.Timedelta(minutes=70 * k), "day": t0.date(), "r": -1.0, "bars": 2, "p": 0.5, "e": 0.1}
            for k in range(7)]
    assert len(P.portfolio(pd.DataFrame(rows), P.Policy())) == 4          # −4R of CLOSED trades → stop for the day
    # a trade still open doesn't count toward the daily stop yet
    rows2 = [dict(rows[0], bars=600)] + [dict(r, setup=f"t{k}") for k, r in enumerate(rows[1:5])]
    rows2 = [dict(r, tf="3min") if k else r for k, r in enumerate(rows2)]
    assert len(P.portfolio(pd.DataFrame(rows2), P.Policy())) == 5


def test_policy_from_config_turns_watch_only_instruments_off():
    cfg = copy.deepcopy(CFG)
    cfg["instruments"]["NDQ"]["trade"] = False
    cfg["playbook"] = {"tfs": ["5min"], "instruments": {"XAUUSD": {"max_positions": 3}}}
    pol = P.policy_from_cfg(cfg)
    assert pol.instruments["NDQ"].role == "off" and pol.instruments["XAUUSD"].max_positions == 3
    assert pol.tfs == ("5min",) and "SPX" not in pol.instruments


# ── live path ────────────────────────────────────────────────────────────────
NOW = pd.Timestamp("2026-09-30 09:40", tz=TZ)


class Store:
    def __init__(self):
        m1 = synth_1m(4000, 0.01, NOW - pd.Timedelta(days=4), 4, 3, TZ)
        self.df = resample_ohlc(m1[m1.index < NOW], "5min")

    def tf(self, sym, tf, complete_only=True):
        return self.df


class Jev:
    live, source = False, "stub"

    async def rate_signal(self, info):
        return {"quality": 0.6, "confidence": 0.6, "htf_aligned": 0.8, "source": "stub"}

    async def continuation(self, info):
        return {"prob": 0.4, "source": "stub"}


def make_ctx(tmp_path, cells, bias=1.0):
    cfg = copy.deepcopy(CFG)
    cfg["mode"] = "paper"
    st = LiveState(mode="paper")
    st.now, st.equity = NOW, 70000.0
    for s in cfg["instruments"]:
        sgn = 1 if bias > 0 else -1
        st.bias[s] = {"score": bias, "suspended": False, "h1": sgn, "label": "BULLISH" if bias > 0 else "BEARISH",
                      "in_doubt": False, "d": sgn, "h4": sgn, "aligned_losses": 0}
    bus = Bus()
    store = Store()
    st.last_prices = {s: float(store.df["close"].iloc[-1]) for s in cfg["instruments"]}
    ctx = Ctx(cfg, bus, st, store, PaperBroker(cfg, st, bus), Journal(str(tmp_path / "j.sqlite")), Jev(), None, None)
    ctx.playbook = PlaybookHolder()
    ctx.playbook.load({"cells": cells}, P.Policy(), "test")
    return ctx


def cell(sym, setup="smc_bos_retest", mgmt="std", p=0.55):
    return {"id": P.cell_id(setup, "5min", "default", mgmt, sym), "sym": sym, "tf": "5min", "setup": setup,
            "variant": "default", "params": {}, "mgmt": mgmt, "n": 40, "win_rate": p, "p": p, "exp_r": 0.2, "e": 0.1}


def fire(ctx, trader, sym, side=1):
    px = float(ctx.store.df["close"].iloc[-1])
    sig = SimpleNamespace(i=len(ctx.store.df) - 1, side=side, entry=px, stop=px - side * px * 0.002,
                          reason="test", features={"risk_atr": 1.0, "atr": px * 0.001}, structural_target=None)
    trader.last_bar_signals = lambda st, s, tf, df, c: [copy.copy(sig)]
    asyncio.run(trader.on_signal_bar({"symbol": sym, "tf": "5min", "ts": NOW}))


def test_trader_sends_playbook_limits_and_respects_capacity(tmp_path):
    ctx = make_ctx(tmp_path, [cell("XAUUSD"), cell("XAUUSD", "ict_ote", p=0.6), cell("NDQ", "smc_mss", "scalp")])
    t = PlaybookTrader(ctx); t.start()
    reqs = []

    async def risk(r):           # stand-in for Risk: record and open a position so "taken" is detected
        reqs.append(r)
        sg = r["signal"]
        p = Position(sg.symbol, sg.side, sg.strategy, sg.stop, sg.stop, abs(sg.entry - sg.stop), 1.0, NOW)
        ctx.state.positions[p.id] = p
    ctx.bus.subscribe("entry_request", risk)
    fire(ctx, t, "XAUUSD")
    assert len(reqs) == 1 and reqs[0]["signal"].strategy.startswith("ict_ote")     # higher p first
    assert reqs[0]["playbook"]["max_per_symbol"] == 2 and reqs[0]["playbook"]["mgmt"] == "std"
    why = {r["strategy"].split(":")[0]: r["why"] for r in ctx.journal.signals(10)}
    assert why["smc_bos_retest"].startswith("a higher-probability")
    # two gold positions already open → the third is refused before Risk is even asked
    ctx.state.positions.clear()
    for k in range(2):
        p = Position("XAUUSD", 1, f"x{k}", 1.0, 1.0, 1.0, 1.0, NOW); ctx.state.positions[p.id] = p
    reqs.clear(); fire(ctx, t, "XAUUSD")
    assert not reqs and "already has 2" in ctx.journal.signals(1)[0]["why"]
    # an index position open → NDQ refused (one index at a time)
    ctx.state.positions.clear()
    p = Position("US30", 1, "y", 1.0, 1.0, 1.0, 1.0, NOW); ctx.state.positions[p.id] = p
    reqs.clear(); fire(ctx, t, "NDQ")
    assert not reqs and "one index position" in ctx.journal.signals(1)[0]["why"]


def test_bias_rule_still_applies(tmp_path):
    ctx = make_ctx(tmp_path, [cell("XAUUSD")], bias=-1.0)
    t = PlaybookTrader(ctx); t.start()
    reqs = []
    ctx.bus.subscribe("entry_request", lambda r: reqs.append(r))
    fire(ctx, t, "XAUUSD", side=1)
    assert not reqs and ctx.journal.signals(1)[0]["action"] == "filtered"


def test_risk_and_manager_apply_scalp_profile_and_symbol_cap(tmp_path):
    ctx = make_ctx(tmp_path, [])
    risk = RiskAgent(ctx); risk.start()
    pm = PositionManagerAgent(ctx); pm.start()
    px = float(ctx.store.df["close"].iloc[-1])
    ctx.state.now = pd.Timestamp("2026-09-30 09:45", tz=TZ)

    def req(strategy, mgmt="scalp", cap=2):
        sig = Signal("XAUUSD", strategy, 1, px, px - 5.0, NOW, "t", {"atr": 4.0}, None, rr=1.0)
        rec = {"ts": NOW.isoformat(), "symbol": "XAUUSD", "strategy": strategy, "side": "LONG", "entry": px, "stop": px - 5}
        return {"signal": sig, "grade": {"quality": 0.6, "confidence": 0.6, "source": "stub"}, "record": rec,
                "playbook": {"max_per_symbol": cap, "mgmt": mgmt, "group": {"members": ["NDQ", "US30", "SPX"], "max": 1}}}

    asyncio.run(risk.on_request(req("a:5m@pb-d-scalp")))
    asyncio.run(risk.on_request(req("b:5m@pb-d", "std")))
    asyncio.run(risk.on_request(req("c:5m@pb-d", "std")))           # third gold position → refused
    pos = list(ctx.state.positions.values())
    assert len(pos) == 2
    scalp = next(p for p in pos if p.strategy.endswith("scalp"))
    assert scalp.meta.get("full_exit") and scalp.meta.get("no_pyramid") and scalp.meta.get("max_hold") == 30
    # price reaches +1R → the scalp exits in full, the std position banks a partial and stays open
    lvl = scalp.entry + scalp.risk_per_unit * 1.05
    ctx.state.now = pd.Timestamp("2026-09-30 09:50", tz=TZ)
    asyncio.run(pm.on_bar(Bar("XAUUSD", ctx.state.now - pd.Timedelta("1min"), lvl - 1, lvl, lvl - 1, lvl, 1.0)))
    assert scalp.status == "closed" and scalp.exit_reason == "target"
    std = next(p for p in pos if not p.strategy.endswith("scalp"))
    assert std.status == "open" and std.partial_done
    # the scalp's 30-minute limit
    asyncio.run(risk.on_request(req("d:5m@pb-d-scalp")))
    s2 = next(p for p in ctx.state.positions.values() if p.strategy.startswith("d:"))
    ctx.state.now = s2.opened_ts + pd.Timedelta(minutes=31)
    c = float(ctx.store.df["close"].iloc[-1])
    asyncio.run(pm.on_bar(Bar("XAUUSD", ctx.state.now - pd.Timedelta("1min"), c, c + 0.1, c - 0.1, c, 1.0)))
    assert s2.status == "closed" and s2.exit_reason == "max_hold"


def test_stop_trails_between_steps_after_first_target(tmp_path):
    ctx = make_ctx(tmp_path, [])
    ctx.cfg["management"] = {**ctx.cfg["management"], "trail_gap_r": 0.75,
                             "pyramid": {**ctx.cfg["management"]["pyramid"], "max_adds": 0}}
    risk = RiskAgent(ctx); risk.start()
    pm = PositionManagerAgent(ctx); pm.start()
    px = float(ctx.store.df["close"].iloc[-1])
    ctx.state.now = pd.Timestamp("2026-09-30 09:45", tz=TZ)
    sig = Signal("XAUUSD", "b:5m@pb-d", 1, px, px - 5.0, NOW, "t", {"atr": 4.0}, None, rr=1.0)
    rec = {"ts": NOW.isoformat(), "symbol": "XAUUSD", "strategy": "b:5m@pb-d", "side": "LONG", "entry": px, "stop": px - 5}
    asyncio.run(risk.on_request({"signal": sig, "grade": {"quality": 0.6, "confidence": 0.6, "source": "stub"},
                                 "record": rec, "playbook": {"max_per_symbol": 2, "mgmt": "std"}}))
    pos = next(iter(ctx.state.positions.values()))
    R, e = pos.risk_per_unit, pos.entry

    def bar(hi, close, minute):
        ctx.state.now = pd.Timestamp(f"2026-09-30 09:{minute}", tz=TZ)
        asyncio.run(pm.on_bar(Bar("XAUUSD", ctx.state.now - pd.Timedelta("1min"), close, hi, close - 0.01, close, 1.0)))

    bar(e + 1.05 * R, e + 1.0 * R, 50)                       # first target: partial; best +1.05R → stop +0.30R
    assert pos.partial_done and abs(pos.r_now(pos.stop) - 0.30) < 0.02
    bar(e + 1.6 * R, e + 1.5 * R, 51)                        # best +1.6R → stop follows to +0.85R
    assert abs(pos.r_now(pos.stop) - 0.85) < 0.02
    bar(e + 1.65 * R, e + 1.6 * R, 52)                       # < 0.1R better → no new stop order
    assert abs(pos.r_now(pos.stop) - 0.85) < 0.02
    bar(e + 2.4 * R, e + 0.9 * R, 53)                        # spikes to +2.4R then closes below the trail → out
    assert pos.status == "closed" and pos.exit_reason == "trail_stop"


def test_stall_rule_leaves_runners_alone_and_tightens_when_price_stalls(tmp_path):
    ctx = make_ctx(tmp_path, [])
    ctx.cfg["management"] = {**ctx.cfg["management"], "trail_gap_r": 0,
                             "runner": {"stall_minutes": 30, "stall_gap_r": 0.5},
                             "pyramid": {**ctx.cfg["management"]["pyramid"], "max_adds": 0}}
    risk = RiskAgent(ctx); risk.start()
    pm = PositionManagerAgent(ctx); pm.start()
    px = float(ctx.store.df["close"].iloc[-1])
    ctx.state.now = pd.Timestamp("2026-09-30 09:45", tz=TZ)
    sig = Signal("XAUUSD", "b:5m@pb-d", 1, px, px - 5.0, NOW, "t", {"atr": 4.0}, None, rr=1.0)
    rec = {"ts": NOW.isoformat(), "symbol": "XAUUSD", "strategy": "b:5m@pb-d", "side": "LONG", "entry": px, "stop": px - 5}
    asyncio.run(risk.on_request({"signal": sig, "grade": {"quality": 0.6, "confidence": 0.6, "source": "stub"},
                                 "record": rec, "playbook": {"max_per_symbol": 2, "mgmt": "std"}}))
    pos = next(iter(ctx.state.positions.values()))
    R, e = pos.risk_per_unit, pos.entry

    def bar(hi, close, t):
        ctx.state.now = pd.Timestamp(f"2026-09-30 {t}", tz=TZ)
        asyncio.run(pm.on_bar(Bar("XAUUSD", ctx.state.now - pd.Timedelta("1min"), close, hi, close - 0.01, close, 1.0)))

    bar(e + 1.05 * R, e + 1.0 * R, "09:50")                   # first target → +0.1R
    for i, m in enumerate(range(51, 60)):                      # a runner: new highs every minute
        bar(e + (1.1 + 0.1 * i) * R, e + (1.05 + 0.1 * i) * R, f"09:{m}")
    assert abs(pos.r_now(pos.stop) - 0.1) < 0.02               # left alone while it keeps making new highs
    best = pos.mfe_r
    bar(e + (best - 0.2) * R, e + (best - 0.3) * R, "10:15")  # 20 min without a new high: still alone
    assert abs(pos.r_now(pos.stop) - 0.1) < 0.02
    bar(e + (best - 0.2) * R, e + (best - 0.3) * R, "10:30")  # 31 min stalled → stop to best − 0.5R
    assert abs(pos.r_now(pos.stop) - (best - 0.5)) < 0.02 and pos.status == "open"


def test_structure_add_waits_for_a_higher_low_then_a_new_high(tmp_path):
    ctx = make_ctx(tmp_path, [])
    ctx.cfg["management"] = {**ctx.cfg["management"], "trail_gap_r": 0,
                             "runner": {"stall_minutes": 0, "add_mode": "structure", "structure_trail": True},
                             "pyramid": {**ctx.cfg["management"]["pyramid"], "max_adds": 2, "require_continuation": False}}
    risk = RiskAgent(ctx); risk.start()
    pm = PositionManagerAgent(ctx); pm.start()
    px = float(ctx.store.df["close"].iloc[-1])
    ctx.state.now = pd.Timestamp("2026-09-30 09:45", tz=TZ)
    sig = Signal("XAUUSD", "b:5m@pb-d", 1, px, px - 5.0, NOW, "t", {"atr": 4.0}, None, rr=1.0)
    rec = {"ts": NOW.isoformat(), "symbol": "XAUUSD", "strategy": "b:5m@pb-d", "side": "LONG", "entry": px, "stop": px - 5}
    asyncio.run(risk.on_request({"signal": sig, "grade": {"quality": 0.6, "confidence": 0.6, "source": "stub"},
                                 "record": rec, "playbook": {"max_per_symbol": 2, "mgmt": "std"}}))
    pos = next(iter(ctx.state.positions.values()))
    R, e = pos.risk_per_unit, pos.entry
    piv = {"v": None}                                 # no swing confirmed since the first target yet
    pm.last_pivot = lambda p: piv["v"]

    def bar(hi, close, t):
        ctx.state.now = pd.Timestamp(f"2026-09-30 {t}", tz=TZ)
        asyncio.run(pm.on_bar(Bar("XAUUSD", ctx.state.now - pd.Timedelta("1min"), close, hi, close - 0.01, close, 1.0)))

    bar(e + 1.05 * R, e + 1.0 * R, "09:50")          # first target: partial, but NO immediate add any more
    assert pos.partial_done and pos.adds == 0
    bar(e + 1.4 * R, e + 1.35 * R, "09:55")          # new high, but no higher low since the target → no add
    assert pos.adds == 0
    piv["v"] = e + 1.1 * R                            # pullback held: a higher low is confirmed
    bar(e + 1.3 * R, e + 1.25 * R, "10:00")          # arms, not a new high
    assert pos.adds == 0
    bar(e + 1.6 * R, e + 1.55 * R, "10:05")          # resumes to a new high → add
    assert pos.adds == 1                             # (the stop sits under the higher low, so the add risks no profit)


def test_last_pivot_uses_only_swings_confirmed_after_the_first_target(tmp_path):
    ctx = make_ctx(tmp_path, [])
    pm = PositionManagerAgent(ctx); pm.start()
    t0 = pd.Timestamp("2026-09-30 10:00", tz=TZ)
    lows = [10, 9, 8, 9, 10, 11, 12, 11, 10.5, 11, 12, 13, 14, 13, 12.5, 13, 14, 15, 16]   # swing lows 8, 10.5, 12.5
    idx = pd.date_range(t0, periods=len(lows), freq="1min")
    df = pd.DataFrame({"open": lows, "high": [x + 1 for x in lows], "low": lows, "close": lows, "volume": 1.0}, index=idx)
    ctx.store.tf = lambda sym, tf, complete_only=True: df
    pos = Position("XAUUSD", 1, "x:2m@pb-d", 1.0, 1.0, 1.0, 1.0, t0)
    assert pm.last_pivot(pos) is None                                   # no first target yet
    pos.meta["t1"] = (t0 + pd.Timedelta(minutes=5)).isoformat()         # target hit after the 8-low was confirmed
    pm.m = {**pm.m, "runner": {"struct_k": 2}}
    assert pm.last_pivot(pos) == 12.5                                   # 10.5 then 12.5: the rising chain's top
    pos.meta["t1"] = (t0 + pd.Timedelta(minutes=12)).isoformat()        # 10.5 confirmed (min 10) before t1
    assert pm.last_pivot(pos) == 12.5
