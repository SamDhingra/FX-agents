"""FX-Agents entry point.

    python main.py                       # sim mode: synthetic market, paper broker, dashboard on :8088
    python main.py --mode paper          # IBKR paper account (IB Gateway/TWS must be running)
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
from fxagents.agents.trading import (MarketDataAgent, PositionManagerAgent, RiskAgent, SelectorAgent,
                                     TraderAgent)
from fxagents.broker import IBKRBroker, PaperBroker
from fxagents.bus import Bus
from fxagents.config import load_config
from fxagents.data import BarStore, IBKRFeed, SimFeed
from fxagents.jev import JevScorer
from fxagents.journal import Journal
from fxagents.news import NewsCalendar
from fxagents.state import LiveState

log = logging.getLogger("main")


async def build(cfg, args):
    state = LiveState(mode=cfg["mode"])
    bus = Bus()
    journal = Journal(cfg["storage"]["db_path"])
    store = BarStore(cfg["timezone"], max_days=cfg["timeframes"]["history_days"] + 3)
    jev = JevScorer(cfg, state, bus)
    book = StrategyBook(journal, rr=cfg["management"]["rr_initial"], tfs=tuple(cfg["timeframes"]["entry"]))
    news = NewsCalendar(cfg)
    ib = None
    if cfg["mode"] == "sim":
        feed = SimFeed(cfg, bus, state)
        broker = PaperBroker(cfg, state, bus)
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
    if cfg["mode"] == "sim":
        news.load_sim(feed.split, cfg["sim"]["days"] + 2)
    else:
        await news.refresh(state.now)
    ctx = Ctx(cfg, bus, state, store, broker, journal, jev, book, news)
    agents = [MarketDataAgent(ctx), NewsAgent(ctx), BiasAgent(ctx), StrategistAgent(ctx), SelectorAgent(ctx),
              TraderAgent(ctx), RiskAgent(ctx), PositionManagerAgent(ctx), JournalAgent(ctx), NotifierAgent(ctx),
              MonitorAgent(ctx)]
    for a in agents:
        a.start()
    return ctx, feed, agents, ib


async def main(args):
    cfg = load_config(args.config)
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
    live_ok = args.i_understand_live_trading or os.environ.get("I_UNDERSTAND_LIVE_TRADING", "").lower() == "yes"
    if cfg["mode"] == "live" and not live_ok:
        sys.exit("Refusing to start LIVE trading without --i-understand-live-trading. Run paper first.")
    ctx, feed, agents, ib = await build(cfg, args)
    strategist = next(a for a in agents if a.name == "strategist")
    log.info("mode=%s  strategies=%s  jev=%s", cfg["mode"], [s.id for s in ctx.book.live()], ctx.jev.source)

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
    return exit_code


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FX-Agents multi-agent intraday trader")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--mode", choices=["sim", "paper", "live"])
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
