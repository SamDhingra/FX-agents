"""FX-Agents entry point.

    python main.py                       # sim mode: synthetic market, paper broker, dashboard on :8088
    python main.py --mode paper          # paper on the configured broker (OANDA practice by default)
    python main.py --mode paper --broker ibkr   # IBKR paper (IB Gateway/TWS must be running)
    python main.py --mode live --i-understand-live-trading
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

import pandas as pd

from fxagents.agents.context import BiasAgent, NewsAgent
from fxagents.agents.core import Ctx, StrategyBook
from fxagents.agents.ops import JournalAgent, MonitorAgent, NotifierAgent
from fxagents.agents.strategist import StrategistAgent
from fxagents.agents.trading import (FlattenSupervisor, MarketDataAgent, PositionManagerAgent, RiskAgent,
                                     SelectorAgent, TraderAgent)
from fxagents.broker import IBKRBroker, PaperBroker
from fxagents.bus import Bus
from fxagents.config import apply_broker, load_config
from fxagents.data import BarStore, IBKRFeed, SimFeed
from fxagents.jev import JevScorer
from fxagents.journal import Journal
from fxagents.news import NewsCalendar
from fxagents.state import STARTUP_HALT, LiveState, RuntimeStore, startup_reconcile

log = logging.getLogger("main")


async def build(cfg, args):
    state = LiveState(mode=cfg["mode"])
    real = cfg["mode"] in ("paper", "live") and not cfg.get("replay")
    if real:   # no entries until the broker has been reconciled with the saved runtime state (end of build)
        state.trading_enabled, state.halt_reason = False, STARTUP_HALT
    bus = Bus()
    journal = Journal(cfg["storage"]["db_path"])
    store = BarStore(cfg["timezone"], max_days=cfg["timeframes"]["history_days"] + 3)
    jev = JevScorer(cfg, state, bus)
    book = StrategyBook(journal, rr=cfg["management"]["rr_initial"], tfs=tuple(cfg["timeframes"]["entry"]))
    # live money: learner-made versions need your vetting first (they promote automatically on paper)
    book.require_vetting = cfg["mode"] == "live" and bool((cfg.get("learner") or {}).get("live_requires_vetting", True))
    news = NewsCalendar(cfg)
    ib = oanda = None
    if cfg.get("replay"):
        # full-system backtest on cached real history, virtual fills with the configured spread
        from fxagents.agents.setup_first import ShadowBroker
        from fxagents.replay import ReplayFeed
        rp = cfg["replay"]
        feed = ReplayFeed(cfg, bus, state, rp["dir"], rp["days"], journal)
        broker = ShadowBroker(cfg, state, bus, {k: float(v) for k, v in ((cfg.get("shadow") or {}).get("spread") or {}).items()})
    elif cfg["mode"] == "sim":
        feed = SimFeed(cfg, bus, state)
        broker = PaperBroker(cfg, state, bus)
    elif cfg["broker"] == "oanda":
        from fxagents.oanda import OandaBroker, OandaFeed, oanda_from_cfg
        oanda = oanda_from_cfg(cfg)
        for attempt in range(1, 31):   # network blips at boot → retry for ~5 minutes
            try:
                feed = OandaFeed(cfg, bus, state, oanda)
                await feed.qualify()
                broker = OandaBroker(cfg, state, bus, oanda, feed)
                await broker.connect()
                break
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                if getattr(e, "status", None) in (401, 403):
                    sys.exit(f"OANDA rejected the token/account ({e}). Check OANDA_API_TOKEN and OANDA_ACCOUNT_ID.")
                log.warning("OANDA not reachable (attempt %d/30): %s", attempt, e)
                await asyncio.sleep(10)
        else:
            sys.exit("Could not reach OANDA after 5 minutes")
        await feed.start()
    else:
        from ib_async import IB
        ib = IB()
        ic = cfg["ibkr"]
        # IB Gateway can take a minute or two to log in after a (re)start → keep trying
        for attempt in range(1, 61):
            try:
                await ib.connectAsync(ic["host"], int(ic["port"]), clientId=int(ic["client_id"]), timeout=20)
                break
            except Exception as e:  # noqa: BLE001
                log.warning("IBKR %s:%s not ready (attempt %d/60): %s", ic["host"], ic["port"], attempt, e)
                await asyncio.sleep(10)
        else:
            sys.exit("Could not connect to IB Gateway after 10 minutes")
        log.info("connected to IBKR %s:%s (accounts %s)", ic["host"], ic["port"], ib.managedAccounts())
        feed = IBKRFeed(cfg, bus, state, ib)
        await feed.qualify()
        await feed.start()
        broker = IBKRBroker(cfg, state, bus, ib, feed)
        await broker.connect()
    for sym in cfg["instruments"]:
        store.load_history(sym, feed.history(sym))
        store.load_h1(sym, feed.h1_history(sym))
    first = store.m1(next(iter(cfg["instruments"])))
    state.now = (first.index[-1] + pd.Timedelta("1min")) if len(first) else pd.Timestamp.now(tz=cfg["timezone"])
    state.equity = state.equity_peak = state.day_start_equity = await broker.equity()
    if cfg.get("replay"):
        news.source = "none (replay — no historical calendar)"
    elif cfg["mode"] == "sim":
        news.load_sim(feed.split, cfg["sim"]["days"] + 2)
    else:
        await news.refresh(state.now)
    ctx = Ctx(cfg, bus, state, store, broker, journal, jev, book, news)
    ctx.oracle = getattr(feed, "oracle", None)          # replays: precomputed per-bar signals
    from fxagents.agents.setup_first import SetupFirstTrader, build_shadow, shadow_modes
    from fxagents.agents.playbook_trader import PlaybookAgent, PlaybookHolder, PlaybookTrader
    sel_mode = cfg["selector"].get("mode", "hourly_pick")
    sh_modes = shadow_modes(cfg)
    ctx.playbook = PlaybookHolder()
    playbook_agent = None
    if "playbook" in (sel_mode, *sh_modes):
        playbook_agent = PlaybookAgent(ctx, ctx.playbook)
    if sel_mode == "playbook":
        trader = PlaybookTrader(ctx)
    else:
        trader = SetupFirstTrader(ctx) if sel_mode == "setup_first" else TraderAgent(ctx)
    ctx.selection_mode = sel_mode
    notifier = NotifierAgent(ctx)
    pm = PositionManagerAgent(ctx)
    agents = [MarketDataAgent(ctx), NewsAgent(ctx), BiasAgent(ctx), StrategistAgent(ctx), SelectorAgent(ctx),
              trader, RiskAgent(ctx), pm, JournalAgent(ctx), notifier,
              MonitorAgent(ctx)] + ([playbook_agent] if playbook_agent else [])
    # wall-clock session-end flatten, its own asyncio task (paper/live only; a no-op start in sim/replay)
    agents.append(FlattenSupervisor(ctx, pm))
    for a in agents:
        a.start()
    # 90-day setup map (heatmap + setup-first prior): loaded now, built/rebuilt in the background
    from fxagents.setup_map import SetupMapAgent, SetupMapHolder, map_path
    ctx.setup_map = SetupMapHolder(map_path(cfg))
    if cfg.get("replay"):
        ctx.setup_map.status = {"state": "off", "why": "replay"}     # map overlaps the replayed period → off
        ctx.setup_map_agent = None
    else:
        ctx.setup_map_agent = SetupMapAgent(ctx, ctx.setup_map, feed if cfg["mode"] != "sim" else None)
        ctx.setup_map_agent.start()
    # shadow books: same live bars, other selection modes, virtual fills only (never send orders)
    ctx.shadow, ctx.shadows = None, {}
    ctx.book_key = "live"
    ctx.shadow_info = {"enabled": False, "books": []}
    sc = cfg.get("shadow", {}) or {}
    for i, mode in enumerate(sh_modes):
        sctx, sagents, sfeed = build_shadow(ctx, state.equity, mode, first=(i == 0))
        sctx.oracle = ctx.oracle
        for a in sagents:
            a.start()
        sfeed.start()                      # after MarketData, so each bar is already stored
        ctx.shadows[mode] = sctx
        sctx.setup_map = ctx.setup_map
        sctx.is_shadow = True
        sctx.shadow, sctx.shadows = None, {}
        if sc.get("notify_trades"):
            def _hooks(sctx=sctx, mode=mode):
                tag = {"setup_first": "setup-first", "hourly_pick": "hourly pick"}.get(mode, mode)
                async def _sh_open(p):
                    await notifier.send("entry", f"Shadow ({tag}) {'LONG' if p.side > 0 else 'SHORT'} {p.symbol}",
                                        f"{p.strategy}: {p.initial_qty:g} @ {p.entry} SL {p.stop}", record=False)
                async def _sh_close(ev):
                    p = ev["position"]
                    await notifier.send("exit", f"Shadow ({tag}) {p.symbol} closed",
                                        f"{p.strategy} {p.exit_reason}: ${p.realized:,.2f}", record=False)
                sctx.bus.subscribe("position_opened", _sh_open)
                sctx.bus.subscribe("position_closed", _sh_close)
            _hooks()
        log.info("shadow book: %s (virtual fills, journal %s)", mode, getattr(sctx.journal, "path", ""))
    if ctx.shadows:
        ctx.shadow = next(iter(ctx.shadows.values()))      # the first one: what older code paths mean by "shadow"
        info = {"enabled": True, "mode": next(iter(ctx.shadows)), "books": list(ctx.shadows), "live_mode": sel_mode}
        ctx.shadow_info = info
        for sctx in ctx.shadows.values():
            sctx.shadow_info = info
    ctx.oanda = oanda
    if real:
        # restart safety: halt flag, day-start equity, peak and open positions (with broker trade ids) live in
        # runtime_state.json next to the journal; entries open only after the broker has been reconciled
        store = RuntimeStore.for_cfg(cfg)
        try:
            res = await startup_reconcile(state, broker, store, pd.Timestamp.now(tz=cfg["timezone"]))
            log.info("startup reconciliation: %s", res)
        except Exception as e:  # noqa: BLE001
            state.halt_reason = f"startup reconciliation failed ({e}) — check the broker, then resume from the dashboard"
            state.alert("error", state.halt_reason)
            log.error(state.halt_reason)
        for topic in ("position_opened", "position_updated", "position_closed", "stop_filled", "clock", "alert"):
            bus.subscribe(topic, lambda _ev, store=store: store.save(state))
        ctx.runtime_store = store
    return ctx, feed, agents, ib


async def main(args, cfg=None):
    cfg = cfg if cfg is not None else load_config(args.config)
    if args.mode:
        cfg["mode"] = args.mode
    if args.days:
        cfg["sim"]["days"] = args.days
    if args.db:
        cfg["storage"]["db_path"] = args.db
    if args.port:
        cfg["dashboard"]["port"] = args.port
    if args.speed is not None:
        cfg["sim"]["speed"] = args.speed
    if args.broker:
        cfg["broker"] = args.broker
    apply_broker(cfg)
    live_ok = args.i_understand_live_trading or os.environ.get("I_UNDERSTAND_LIVE_TRADING", "").lower() == "yes"
    if cfg["mode"] == "live" and not live_ok:
        sys.exit("Refusing to start LIVE trading without --i-understand-live-trading. Run paper first.")
    ctx, feed, agents, ib = await build(cfg, args)
    strategist = next(a for a in agents if a.name == "strategist")
    log.info("mode=%s  broker=%s  selection=%s  shadow=%s  strategies=%d  jev=%s", cfg["mode"],
             "paper-sim" if cfg["mode"] == "sim" else cfg["broker"], ctx.selection_mode,
             "+".join(ctx.shadows) or "off", len(ctx.book.live()), ctx.jev.source)

    bias_agent = next(a for a in agents if a.name == "bias")
    await bias_agent.update_all(ctx.state.now)   # HTF bias before anything can trade
    await strategist.evaluate_all()              # stats → selector picks for the current hour
    tasks = []
    server = None
    if not args.no_dashboard:
        import uvicorn
        from fxagents.dashboard.server import build_app
        d = cfg["dashboard"]
        server = uvicorn.Server(uvicorn.Config(build_app(ctx), host=d["host"], port=int(d["port"]),
                                               log_level="warning"))
        tasks.append(asyncio.create_task(server.serve()))
        log.info("dashboard → http://%s:%s", d["host"], d["port"])

    done = asyncio.Event()
    ctx.bus.subscribe("feed_done", lambda _: done.set())
    tasks.append(asyncio.create_task(feed.run()))
    tasks += [a.task for a in agents if getattr(a, "task", None) is not None]   # the flatten supervisor
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, done.set)
        except NotImplementedError:
            pass
    exit_code = 0
    if ib is not None:
        def on_disconnect():
            # Stops rest at IBKR, so nothing is unprotected. Exit non-zero and let the supervisor
            # (Docker restart policy / launchd) start a fresh process that reconnects cleanly.
            nonlocal exit_code
            exit_code = 3
            ctx.state.alert("error", "IBKR disconnected — restarting to reconnect; resting stops remain at the broker")
            asyncio.ensure_future(ctx.bus.publish("alert", {"msg": "IBKR disconnected — app restarting to reconnect",
                                                            "event": "agent_down", "title": "⚠ FX-Agents"}))
            loop.call_later(5, done.set)
        ib.disconnectedEvent += on_disconnect
    await done.wait()

    if cfg["mode"] == "sim":
        # close anything still open at the end of the replay
        await ctx.bus.publish("flatten_all", "end of simulation")
        s = ctx.journal.summary()
        log.info("SIM DONE: %s | equity $%.2f", s, await ctx.broker.equity())
        for sh in ctx.shadows.values():
            await sh.bus.publish("flatten_all", "end of simulation")
            log.info("SHADOW (%s): %s | equity $%.2f", sh.selection_mode, sh.journal.summary(),
                     await sh.broker.equity())
        if server is not None and not args.exit_after_sim:
            log.info("replay finished — dashboard still serving (Ctrl-C to exit)")
            stop = asyncio.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass
            await stop.wait()
    if server is not None:
        server.should_exit = True
    for t in tasks:
        t.cancel()
    await ctx.jev.aclose()
    if ib is not None:
        ib.disconnect()
    if getattr(ctx, "oanda", None) is not None:
        await ctx.oanda.aclose()
    return exit_code


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FX-Agents multi-agent intraday trader")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--mode", choices=["sim", "paper", "live"])
    ap.add_argument("--broker", choices=["oanda", "ibkr"], help="paper/live broker (default: config.yaml)")
    ap.add_argument("--days", type=int, help="sim: trading days to replay")
    ap.add_argument("--db", help="override journal path")
    ap.add_argument("--port", type=int, help="dashboard port")
    ap.add_argument("--speed", type=float, help="sim: seconds per simulated minute")
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--exit-after-sim", action="store_true")
    ap.add_argument("--i-understand-live-trading", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-5s %(name)-16s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main(a)) or 0)
