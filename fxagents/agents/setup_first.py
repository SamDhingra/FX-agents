"""Setup-first selection, and the shadow book that runs it next to the real one.

Setup-first: at every 5m/15m close, scan EVERY live strategy (not just this hour's pick). Each setup
that forms becomes a candidate. Cheap hard gates first (entry window, news blackout, open positions,
HTF bias rule); only survivors are graded by Jev, with extra context: how this setup has done at this
hour historically (shrunk toward its overall record) and how it has done on today's bars so far.
The best-graded candidate that clears the gate is sent to Risk; if Risk refuses it, the next one is
tried. The hourly ranking is still passed to Jev as context, but it no longer decides what is seen.

Shadow book: a second, fully separate set of agents (own bus, state, journal, virtual broker) that
receives the same live bars and makes its own decisions with the OTHER selection mode. It never sends
orders: positions are virtual (filled at the live price ± an estimated half-spread) and are managed by
the same PositionManager rules. Its journal is a separate SQLite file, so the dashboard can show
Live vs Shadow side by side.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..bias import rule_check
from ..broker import PaperBroker
from ..indicators import in_windows
from ..journal import Journal
from ..models import Bar, Signal
from ..sim import Mgmt, backtest
from ..state import LiveState
from ..strategies import Strategy
from .core import Agent, Ctx
from .ops import JournalAgent, MonitorAgent
from .trading import PositionManagerAgent, RiskAgent, TraderAgent, _hm, jev_gate_why

log = logging.getLogger("shadow")


class SetupFirstTrader(TraderAgent):
    """Scans every live strategy on each entry-TF close and trades the best Jev-graded setup."""
    name = "trader"

    def start(self):
        super().start()
        sf = self.cfg.get("setup_first", {}) or {}
        self.max_graded = int(sf.get("max_graded_per_bar", 3))
        self.today_ctx = bool(sf.get("today_context", True))

    # --- cheap gates (no Jev call) -------------------------------------------------
    def precheck(self, sig: Signal) -> str | None:
        now = self.now()
        s, r = self.cfg["sessions"], self.cfg["risk"]
        if not self.state.trading_enabled:
            return f"trading halted: {self.state.halt_reason}"
        if not in_windows(now, s["entry_windows"]):
            return "outside entry windows"
        if now.hour * 60 + now.minute >= _hm(s["flatten_at"]) - 20 and now.hour < 17:
            return "too close to session flatten"
        nb = self.ctx.news.blocked(now) if self.ctx.news else None
        if nb:
            return f"news blackout: {nb['title']}"
        open_pos = [p for p in self.state.positions.values() if p.status == "open"]
        if len(open_pos) >= r["max_open_positions"]:
            return "max open positions"
        if sum(p.symbol == sig.symbol for p in open_pos) >= r["max_positions_per_symbol"]:
            return "already positioned in symbol"
        return self.bias_precheck(sig)

    def hour_prior(self, sym: str, sid: str, hour: int) -> dict:
        s = self.state.strategy_stats.get(sym, {}).get(sid)
        if not s:
            return {"n": 0, "exp": 0.0, "shrunk_exp": 0.0}
        h = s["by_hour"].get(hour, {"n": 0, "exp": 0.0, "win": 0.0})
        k = self.cfg["selector"]["hour_shrinkage_k"]
        shrunk = (h["n"] * h["exp"] + k * s["expectancy"]) / (h["n"] + k)
        return {"n": h["n"], "exp": round(h["exp"], 3), "win": round(h.get("win", 0.0), 3),
                "overall_n": s["n"], "overall_exp": round(s["expectancy"], 3), "shrunk_exp": round(shrunk, 3)}

    def history_prior(self, sym: str, sid: str, hour: int) -> dict | None:
        h = getattr(self.ctx, "setup_map", None)
        if h is None or h.map is None:
            return None
        return h.map.prior(sym, sid, hour, int(self.now().dayofweek))

    def today_form(self, st: Strategy, df: pd.DataFrame, ctx: dict, tf_min: int) -> dict:
        """How this setup has played out on today's bars so far (backtest of today only)."""
        try:
            now = self.now()
            day_start = (now - pd.Timedelta(hours=17)).normalize() + pd.Timedelta(hours=17)   # 17:00 NY roll
            idx = df.index + pd.Timedelta(minutes=tf_min)
            start_i = int((idx < day_start).sum())
            if start_i >= len(df) - 1:
                return {"n": 0}
            s = self.cfg["sessions"]
            tr = backtest(st, df, Strategy.context(df), Mgmt.from_cfg(self.cfg, rr=st.rr, bar_minutes=tf_min),
                          s["entry_windows"], s["flatten_at"], start_i=start_i)
            tr = [t for t in tr if t["ts"] < idx[-1]]
            if not tr:
                return {"n": 0}
            rs = [t["r"] for t in tr]
            return {"n": len(rs), "sum_r": round(sum(rs), 2), "wins": sum(1 for x in rs if x > 0)}
        except Exception as e:  # noqa: BLE001 — context only; never block trading on it
            self.log.debug("today_form %s: %s", st.id, e)
            return {"n": 0}

    async def on_signal_bar(self, ev):
        self.beat()
        sym, tf = ev["symbol"], ev["tf"]
        if self.cfg["mode"] != "sim" and self.now() is not None and self.now() - ev["ts"] > pd.Timedelta("5min"):
            return
        # nothing can trade now → don't scan (and don't count untradeable setups as "seen")
        if not self.state.trading_enabled or not in_windows(self.now(), self.cfg["sessions"]["entry_windows"]):
            return
        strategies = [s for s in self.ctx.book.live() if s.tf == tf]
        if not strategies:
            return
        df = self.ctx.store.tf(sym, tf).iloc[-self.window:]
        if len(df) < 120:
            return
        ctx = self.bar_context(sym, tf, df)
        tf_min = int(pd.Timedelta(tf).total_seconds() // 60)
        hour = self.now().hour
        ranking = {r["id"]: i + 1 for i, r in enumerate(self.state.selections.get(sym, []))}
        cands = []
        for st in strategies:
            for rs in self.last_bar_signals(st, sym, tf, df, ctx):
                sig = Signal(sym, st.id, rs.side, rs.entry, rs.stop, ev["ts"], rs.reason,
                             rs.features, rs.structural_target, rr=st.rr)
                why = self.precheck(sig)
                if why:
                    self.ctx.journal.add_signal(self._rec(sig) | {"action": "filtered", "why": why})
                    continue
                prior = self.hour_prior(sym, st.id, hour)
                hist = self.history_prior(sym, st.id, hour)
                key = hist["shrunk_exp"] if hist and hist.get("level") != "none" else prior["shrunk_exp"]
                cands.append((key, st, sig, prior, hist))
        if not cands:
            return
        cands.sort(key=lambda c: -c[0])
        graded = []
        for _, st, sig, prior, hist in cands[: self.max_graded]:
            extra = {"setup_this_hour_12d": prior, "hourly_rank": ranking.get(st.id),
                     "candidates_on_this_bar": len(cands)}
            if hist and hist.get("level") != "none":
                extra["setup_history_90d"] = hist   # same setup, same hour & weekday, last ~90 days (shrunk)
            if self.today_ctx:
                extra["setup_today"] = self.today_form(st, df, ctx, tf_min)
            g = await self.grade(sig, ctx, df, extra)
            graded.append((g, sig))
        for _, st, sig, _, _ in cands[self.max_graded:]:
            self.ctx.journal.add_signal(self._rec(sig) | {"action": "skipped",
                                                          "why": f"not in top {self.max_graded} setups on this bar"})
        jc = self.cfg["jev"]
        graded.sort(key=lambda x: -(x[0]["quality"] * (0.5 + 0.5 * x[0]["confidence"])))
        taken = False
        for g, sig in graded:
            rec = self._rec(sig) | {"quality": g["quality"], "confidence": g["confidence"]}
            if taken:
                self.ctx.journal.add_signal(rec | {"action": "skipped", "why": "a better setup was taken on this bar"})
                continue
            if g["quality"] < jc["min_signal_quality"] or g["confidence"] < jc["min_signal_confidence"] * 0.8:
                self.ctx.journal.add_signal(rec | {"action": "skipped",
                                                   "why": jev_gate_why(g, jc)})
                continue
            before = {p.id for p in self.state.positions.values()}
            await self.bus.publish("entry_request", {"signal": sig, "grade": g, "record": rec})
            taken = any(p.id not in before and p.symbol == sig.symbol for p in self.state.positions.values())

    @staticmethod
    def _rec(sig: Signal) -> dict:
        return {"ts": sig.ts.isoformat(), "symbol": sig.symbol, "strategy": sig.strategy,
                "side": "LONG" if sig.side > 0 else "SHORT", "entry": sig.entry, "stop": sig.stop}

    async def grade(self, sig: Signal, ctx: dict, df: pd.DataFrame, extra: dict) -> dict:
        stats = self.state.strategy_stats.get(sig.symbol, {}).get(sig.strategy, {})
        b = self.state.bias.get(sig.symbol, {})
        info = {"symbol": sig.symbol, "strategy": sig.strategy, "side": "LONG" if sig.side > 0 else "SHORT",
                "entry": sig.entry, "stop": sig.stop, "target_1r": sig.target, "structural_target": sig.structural_target,
                "reason": sig.reason, "risk_atr": sig.features.get("risk_atr"),
                "htf_bias": 1 if b.get("score", 0) > 0 else -1 if b.get("score", 0) < 0 else 0,
                "htf_detail": {k: b.get(k) for k in ("label", "score", "d", "h4", "h1", "pd_pos", "pdh", "pdl", "state")},
                "news_next_hours": self.ctx.news.brief(self.now(), 3) if self.ctx.news else [],
                "rsi": round(float(ctx["rsi"][-1]), 1) if ctx else None,
                "strategy_expectancy": stats.get("expectancy", 0.0), "strategy_win_rate": stats.get("win_rate"),
                "recent_bars": df.iloc[-12:][["open", "high", "low", "close"]].round(4).to_dict("split")["data"],
                "time_ny": str(sig.ts), **extra}
        return await self.ctx.jev.rate_signal(info)


# ─────────────────────────────────────────────────────────────────────────────
_SHARED = ("bias", "strategy_stats", "selections", "strategy_registry", "news", "news_source",
           "news_block", "last_prices", "last_bar_ts", "learner_log")


class ShadowState(LiveState):
    """Own positions/equity/alerts/decisions; market context (bias, stats, news, prices) read live
    from the real state, so both books always see exactly the same picture."""

    def __init__(self, main: LiveState, **kw):
        object.__setattr__(self, "_main", main)
        super().__init__(**kw)

    def __getattribute__(self, k):
        if k in _SHARED:
            return getattr(object.__getattribute__(self, "_main"), k)
        return object.__getattribute__(self, k)

    def __setattr__(self, k, v):
        if k in _SHARED:
            return          # context is owned by the real agents
        object.__setattr__(self, k, v)


class ShadowBroker(PaperBroker):
    """Virtual fills at the live price ± an estimated half-spread (OANDA charges the spread, not commission)."""

    def __init__(self, cfg, state, bus, spreads: dict[str, float]) -> None:
        super().__init__(cfg, state, bus)
        self.spreads = spreads

    def _slip(self, sym: str, side: int) -> float:
        sp = self.spreads.get(sym)
        if sp is None:
            return super()._slip(sym, side)
        return side * sp / 2


class ShadowFeedAgent(Agent):
    """Lives on the REAL bus. After the real MarketData agent has stored each live bar, replays it into
    the shadow book in the same order the real book uses: resting stops → management → entry signals."""
    name = "shadow_feed"

    def __init__(self, main_ctx: Ctx, shadow_ctx: Ctx):
        super().__init__(main_ctx)
        self.sh = shadow_ctx
        self.tfs = [(tf, int(pd.Timedelta(tf).total_seconds() // 60)) for tf in main_ctx.cfg["timeframes"]["entry"]]

    def start(self):
        super().start()
        self.bus.subscribe("bar", self.on_bar)
        self.bus.subscribe("clock", self.on_clock)
        self.bus.subscribe("pre_news", lambda ev: self.sh.bus.publish("pre_news", ev))

    async def on_bar(self, bar: Bar):
        self.beat()
        self.sh.state.now = self.state.now
        await self.sh.broker.on_bar(bar)
        await self.sh.bus.publish("bar_1m", bar)
        mins = bar.ts.hour * 60 + bar.ts.minute + 1
        for tf, n in self.tfs:
            if mins % n == 0:
                await self.sh.bus.publish("bar_signal", {"symbol": bar.symbol, "tf": tf,
                                                         "ts": bar.ts + pd.Timedelta("1min")})

    async def on_clock(self, now):
        self.sh.state.now = now
        await self.sh.bus.publish("clock", now)


def shadow_db_path(main_path: str) -> str:
    p = Path(main_path)
    return str(p.with_name(p.stem + "_shadow" + (p.suffix or ".sqlite")))


def build_shadow(main: Ctx, equity: float):
    """Create the shadow book. Returns (shadow_ctx, [agents]) — agents are started by the caller."""
    from ..bus import Bus
    cfg = main.cfg
    sc = cfg.get("shadow", {}) or {}
    bus = Bus()
    st = ShadowState(main.state, mode=cfg["mode"])
    st.now = main.state.now
    broker = ShadowBroker(cfg, st, bus, {k: float(v) for k, v in (sc.get("spread") or {}).items()})
    broker.cash = float(equity)
    st.equity = st.equity_peak = st.day_start_equity = float(equity)
    journal = Journal(sc.get("db_path") or shadow_db_path(cfg["storage"]["db_path"]))
    sctx = Ctx(cfg, bus, st, main.store, broker, journal, main.jev, main.book, main.news)
    mode = sc.get("mode", "setup_first")
    trader = SetupFirstTrader(sctx) if mode == "setup_first" else TraderAgent(sctx)
    agents = [trader, RiskAgent(sctx), PositionManagerAgent(sctx), JournalAgent(sctx), MonitorAgent(sctx)]
    feed = ShadowFeedAgent(main, sctx)
    sctx.selection_mode = mode
    return sctx, agents, feed
