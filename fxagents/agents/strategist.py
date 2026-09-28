"""The Strategist agent — evaluates, improves, learns and creates strategies. It never trades.

Every `refresh_minutes`  → rolling re-evaluation of every live/shadow version on each symbol
                            (stats overall, per hour-of-day, last 36h) → feeds the Selector.
Every `optimize_every_hours` (and daily at `optimize_at`) → learning cycle:
  1. Tune: random parameter variants + R:R progression (1:1 → 1.25 → 1.5 …, capped at rr_max),
     chosen in-sample (first 70%), validated out-of-sample (last 30%), reviewed by Jev for overfit.
  2. Create: confluence strategies (primary entry model + other strategies' bias as filters).
  3. New versions start in SHADOW; they are promoted to LIVE only after beating their parent on
     forward (post-creation) shadow trades. Losing live versions are demoted; stale candidates retired.
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import pandas as pd

from ..bias import bias_frame
from ..sim import Mgmt, backtest, stats
from ..strategies import BUILTIN, Confluence, Strategy, build_strategy
from .core import Agent

BIAS_FILTERS = ["dtfx_zone", "macd_cross", "rsi_pullback", "ict_ote"]


class StrategistAgent(Agent):
    name = "strategist"

    def start(self):
        super().start()
        self.ec = self.cfg["evaluator"]
        self.last_eval: pd.Timestamp | None = None
        self.last_learn: pd.Timestamp | None = None
        self.trades: dict[str, dict[str, list[dict]]] = {}
        self.busy = False
        self.rng = np.random.default_rng(self.cfg["sim"].get("seed", 7))
        self.bus.subscribe("clock", self.on_clock)

    # ── scheduling ────────────────────────────────────────────────────────
    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        if self.busy:
            return
        if self.last_eval is None or now - self.last_eval >= pd.Timedelta(minutes=self.ec["refresh_minutes"]):
            await self.evaluate_all()
        hh, mm = map(int, self.ec["optimize_at"].split(":"))
        due_daily = now.hour == hh and now.minute >= mm and (self.last_learn is None or self.last_learn.date() != now.date())
        due_every = self.last_learn is None or now - self.last_learn >= pd.Timedelta(hours=self.ec["optimize_every_hours"])
        if due_daily or due_every:
            await self.learn()

    def frames(self) -> dict[tuple[str, str], dict]:
        """(symbol, tf) → bars + the multi-TF bias score known at each bar close (hard rule in backtests)."""
        out = {}
        for s in self.cfg["instruments"]:
            h1 = self.ctx.store.h1(s)
            for tf in self.cfg["timeframes"]["entry"]:
                n = int(self.ec["lookback_days"] * 24 * 60 / (pd.Timedelta(tf).total_seconds() / 60))
                df = self.ctx.store.tf(s, tf).iloc[-n:].copy()
                if len(df) < 120 or len(h1) < 48:
                    continue
                b = bias_frame(h1, df.index + pd.Timedelta(tf), weights=self.cfg["bias"]["weights"])
                out[(s, tf)] = {"df": df, "bias": b["score"].to_numpy()}
        return out

    def mgmt(self, st: Strategy) -> Mgmt:
        return Mgmt.from_cfg(self.cfg, rr=st.rr, bar_minutes=int(pd.Timedelta(st.tf).total_seconds() // 60))

    def _bt(self, st: Strategy, item: dict, part: str = "full", ctx: dict | None = None) -> list[dict]:
        s = self.cfg["sessions"]
        df, bias = item["df"], item["bias"]
        kw = dict(min_align=self.cfg["bias"]["min_align"])
        split = int(len(df) * 0.7)
        if part == "is":
            d = df.iloc[:split]
            return backtest(st, d, Strategy.context(d), self.mgmt(st), s["entry_windows"], s["flatten_at"],
                            bias_score=bias[:split], **kw)
        ctx = ctx or Strategy.context(df)
        return backtest(st, df, ctx, self.mgmt(st), s["entry_windows"], s["flatten_at"],
                        start_i=split if part == "oos" else 0, bias_score=bias, **kw)

    # ── rolling evaluation ────────────────────────────────────────────────
    def _eval(self, frames, strategies, now):
        out, trades = {}, {}
        for (sym, tf), item in frames.items():
            ctx = Strategy.context(item["df"])
            out.setdefault(sym, {}); trades.setdefault(sym, {})
            for st in [x for x in strategies if x.tf == tf]:
                tr = self._bt(st, item, "full", ctx)
                trades[sym][st.id] = tr
                out[sym][st.id] = stats(tr, now) | {"status": st.status, "rr": st.rr, "tf": st.tf_label}
        return out, trades

    async def evaluate_all(self):
        self.busy = True
        try:
            t0 = time.perf_counter()
            now = self.now()
            out, trades = await asyncio.to_thread(self._eval, self.frames(), list(self.ctx.book.evaluated()), now)
            self.state.strategy_stats, self.trades = out, trades
            self.state.strategy_registry = self.ctx.book.registry()
            self.last_eval = now
            self.log.info("evaluated %d versions × %d symbols in %.1fs", len(self.ctx.book.evaluated()), len(out),
                          time.perf_counter() - t0)
            await self.bus.publish("stats_updated", {"ts": now.isoformat()})
        finally:
            self.busy = False

    # ── pooled helpers ────────────────────────────────────────────────────
    def _pooled(self, st: Strategy, frames, part: str) -> dict:
        tr = []
        for (sym, tf), item in frames.items():
            if tf == st.tf:
                tr += self._bt(st, item, part)
        return stats(tr)

    def _search(self, frames, live: list[Strategy]) -> list[dict]:
        """CPU-heavy part, runs in a worker thread. Returns proposals for the async review step."""
        props = []
        rr_max = self.cfg["management"]["rr_max"]
        for st in [x for x in live if not isinstance(x, Confluence)]:
            base_is = self._pooled(st, frames, "is")
            trials = [(p, st.rr) for p in st.variants(max_n=4, rng=self.rng)]
            full = self._pooled(st, frames, "full")
            for step in (0.25, 0.5):  # R:R progression, only if price actually travels that far
                rr = round(st.rr + step, 2)
                if rr <= rr_max and full["reach"].get(min((1.5, 2.0, 3.0), key=lambda x: abs(x - rr)), 0) >= 0.4:
                    trials.append(({}, rr))
            best, best_is = None, base_is
            for params, rr in trials:
                cand = build_strategy({"class": st.name, "params": {**st.params, **params}, "rr": rr, "tf": st.tf})
                r = self._pooled(cand, frames, "is")
                if r["n"] >= 10 and r["expectancy"] > best_is["expectancy"] + 0.02:
                    best, best_is = (cand, params, rr), r
            if best is None:
                continue
            cand, params, rr = best
            oos_c, oos_i = self._pooled(cand, frames, "oos"), self._pooled(st, frames, "oos")
            props.append({"kind": "tune", "parent": st.id,
                          "spec": {"class": st.name, "params": cand.params, "rr": rr, "tf": st.tf},
                          "change": {**params, **({"rr": rr} if rr != st.rr else {})},
                          "is": best_is, "oos": oos_c, "incumbent_oos": oos_i, "incumbent_is": base_is})
        # confluence creation
        ranked = sorted([x for x in live if not isinstance(x, Confluence)],
                        key=lambda x: -self._pooled(x, frames, "full")["expectancy"])[:3]
        combos = [(p, f) for p in ranked for f in BIAS_FILTERS if BUILTIN[f].family != p.family]
        if len(combos) > 5:
            combos = [combos[j] for j in self.rng.choice(len(combos), 5, replace=False)]
        existing = {s.id.split("@")[0] for s in self.ctx.book.items.values()}
        for p, f in combos:
            if f"{p.name}+{f}:{p.tf_label}" in existing:
                continue
            spec = {"class": "confluence", "rr": p.rr, "tf": p.tf,
                    "params": {"primary": p.spec(), "filters": [BUILTIN[f](tf=p.tf).spec()]}}
            cand = build_strategy(spec)
            oos_c, oos_i = self._pooled(cand, frames, "oos"), self._pooled(p, frames, "oos")
            is_c = self._pooled(cand, frames, "is")
            props.append({"kind": "confluence", "parent": p.id, "spec": spec, "change": {"filter": f},
                          "is": is_c, "oos": oos_c, "incumbent_oos": oos_i})
        return props

    # ── learning cycle ────────────────────────────────────────────────────
    async def learn(self):
        self.busy = True
        now = self.now()
        ts = now.isoformat(timespec="seconds")
        try:
            t0 = time.perf_counter()
            frames = self.frames()
            props = await asyncio.to_thread(self._search, frames, list(self.ctx.book.live()))
            created = 0
            for pr in props:
                gain = pr["oos"]["expectancy"] - pr["incumbent_oos"]["expectancy"]
                ok_stats = pr["oos"]["n"] >= 8 and gain >= self.ec["promote_margin_r"] and pr["is"]["expectancy"] > 0
                if not ok_stats:
                    continue
                review = await self.ctx.jev.rate_candidate({
                    "symbol": "ALL", "kind": pr["kind"], "parent": pr["parent"], "change": pr["change"],
                    "candidate_is": _slim(pr["is"]), "candidate_oos": _slim(pr["oos"]),
                    "incumbent_oos": _slim(pr["incumbent_oos"])})
                if review["prob"] < 0.55:
                    self._note(ts, f"rejected {pr['kind']} of {pr['parent']} (Jev robust {review['prob']:.2f})", pr["change"])
                    continue
                base = pr["spec"]["class"]
                spec = pr["spec"] | {"version": self.ctx.book.next_version(base), "status": "shadow",
                                     "origin": f"learner:{pr['parent']}", "created": ts}
                st = build_strategy(spec)
                if st.id in self.ctx.book.items:
                    continue
                self.ctx.book.add(st, ts, f"{pr['kind']} {pr['change']} OOS +{gain:.2f}R")
                created += 1
                self._note(ts, f"new shadow {st.id} ({pr['kind']} {pr['change']}): OOS {pr['oos']['expectancy']:+.2f}R "
                               f"vs {pr['incumbent_oos']['expectancy']:+.2f}R, Jev robust {review['prob']:.2f}", pr["change"])
            await self.promote_demote(now, ts)
            self.last_learn = now
            self._note(ts, f"learning cycle done: {len(props)} proposals, {created} new shadow versions "
                           f"({time.perf_counter()-t0:.1f}s)")
            self.state.strategy_registry = self.ctx.book.registry()
        finally:
            self.busy = False
        await self.evaluate_all()

    def _forward(self, sid: str, since: str | None) -> dict:
        tr = []
        for sym in self.trades.values():
            tr += [t for t in sym.get(sid, []) if since is None or t["ts"].isoformat() >= since]
        return stats(tr)

    async def promote_demote(self, now, ts):
        book, ec = self.ctx.book, self.ec
        # promote shadows that beat their parent on forward (post-creation) trades
        for st in [s for s in book.items.values() if s.status == "shadow" and s.origin.startswith("learner:")]:
            parent_id = st.origin.split(":", 1)[1]
            since = getattr(st, "created", None)
            fwd = self._forward(st.id, since)
            par = self._forward(parent_id, since)
            if fwd["n"] >= ec["min_trades_promote"] and fwd["expectancy"] >= par["expectancy"] + ec["promote_margin_r"] and fwd["expectancy"] > 0:
                book.set_status(st.id, "live", ts, "promoted on forward shadow results")
                if parent_id in book.items and not isinstance(st, Confluence):
                    book.set_status(parent_id, "shadow", ts, f"superseded by {st.id}")
                msg = f"PROMOTED {st.id}: forward {fwd['expectancy']:+.2f}R over {fwd['n']} vs parent {par['expectancy']:+.2f}R"
                self._note(ts, msg)
                await self.bus.publish("promotion", {"msg": msg, "id": st.id})
            elif fwd["n"] >= ec["min_trades_promote"] and fwd["expectancy"] < 0:
                book.set_status(st.id, "retired", ts, "negative forward expectancy")
                self._note(ts, f"retired {st.id}: forward {fwd['expectancy']:+.2f}R")
        # demote losing live versions (always keep at least 2 live)
        pooled = {sid: self._forward(sid, None) for sid in book.items}
        live = book.live()
        for st in sorted(live, key=lambda s: pooled[s.id]["expectancy"]):
            p = pooled[st.id]
            if len(book.live()) <= 2:
                break
            if p["n"] >= 20 and p["expectancy"] < ec["demote_below_r"]:
                book.set_status(st.id, "shadow", ts, f"demoted: {p['expectancy']:+.2f}R over {p['n']}")
                self._note(ts, f"demoted {st.id} to shadow ({p['expectancy']:+.2f}R over {p['n']} trades)")
        # re-activate recovered builtin shadows
        for st in [s for s in book.items.values() if s.status == "shadow" and s.origin == "builtin"]:
            p = pooled[st.id]
            if p["n"] >= 20 and p["expectancy"] > 0.1:
                book.set_status(st.id, "live", ts, "recovered")
                self._note(ts, f"re-activated {st.id} ({p['expectancy']:+.2f}R)")
        # cap candidate pool
        cands = [s for s in book.items.values() if s.status == "shadow" and s.origin.startswith("learner:")]
        if len(cands) > ec["max_candidates"]:
            for st in sorted(cands, key=lambda s: pooled[s.id]["expectancy"])[:len(cands) - ec["max_candidates"]]:
                book.set_status(st.id, "retired", ts, "candidate pool full")
                self._note(ts, f"retired {st.id} (pool full)")

    def _note(self, ts: str, msg: str, data=None):
        self.log.info(msg)
        self.state.learner_log.appendleft({"ts": ts, "msg": msg})
        self.ctx.journal.learner(ts, msg, data)


def _slim(s: dict) -> dict:
    return {k: s[k] for k in ("n", "win_rate", "expectancy", "pf", "max_dd_r")}
