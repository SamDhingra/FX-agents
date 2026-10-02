"""The Strategist agent — evaluates, improves, learns and creates strategies. It never trades.

Every `refresh_minutes`  → rolling re-evaluation of every live/shadow version on each symbol
                            (stats overall, per hour-of-day, last 36h) → feeds the Selector.
Every `optimize_every_hours` (and daily at `optimize_at`) → learning cycle:
  1. Tune: random parameter variants + R:R progression (1:1 → 1.25 → 1.5 …, capped at rr_max),
     walk-forward on up to `learner.history_days` (90) of history: chosen on the first 2/3,
     validated on the last 1/3 it never saw, then reviewed by Jev for overfit.
  2. Create: confluence strategies (primary entry model + other strategies' bias as filters).
  3. New versions start in SHADOW. Every completed simulated trade of every version is stored
     permanently (forward_trades), so forward records accumulate over weeks. A shadow version is
     promoted to LIVE after `min_trades_promote` forward trades beating its parent — unless real
     results (paper account + shadow book) disagree. Losing versions are demoted on either record.
  4. In LIVE mode, learner-made versions trade only after you vet them (`learner.live_requires_vetting`).
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
        self.lc = {"history_days": 90, "is_frac": 0.67, "real_block_n": 5, "real_demote_n": 15,
                   **(self.cfg.get("learner") or {})}
        self.bus.subscribe("clock", self.on_clock)

    # ── scheduling ────────────────────────────────────────────────────────
    async def on_clock(self, now: pd.Timestamp):
        self.beat()
        if self.busy:
            return
        if self.last_eval is None or now - self.last_eval >= pd.Timedelta(minutes=self.ec["refresh_minutes"]):
            await self.evaluate_all()
        hh, mm = map(int, self.ec["optimize_at"].split(":"))
        if not self.ec.get("learn_enabled", True):
            return
        due_daily = self.ec.get("optimize_daily", True) and now.hour == hh and now.minute >= mm \
            and (self.last_learn is None or self.last_learn.date() != now.date())
        due_every = self.last_learn is None or now - self.last_learn >= pd.Timedelta(hours=self.ec["optimize_every_hours"])
        if due_daily or due_every:
            if self.cfg["mode"] == "sim":
                await self.learn()                     # replays/sims: the clock waits for the learner
            else:
                self.busy = True                       # live/paper: never hold up market data for minutes
                asyncio.create_task(self.learn())

    def long_m1(self, sym: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Up to `history_days` of 1m bars: the cached long history (saved by the setup-map build)
        joined with the live store's recent bars. Falls back to the store alone."""
        m1, h1 = self.ctx.store.m1(sym), self.ctx.store.h1(sym)
        try:
            from ..setup_map import load_history
            hist = load_history(self.cfg, sym)
        except Exception:  # noqa: BLE001
            hist = None
        if hist is not None:
            hm1, hh1 = hist
            m1 = pd.concat([hm1[hm1.index < m1.index[0]] if len(m1) else hm1, m1])
            h1 = pd.concat([hh1[hh1.index < h1.index[0]] if len(h1) else hh1, h1])
        now = self.now()                      # never look past "now" (a replay's history file holds the future)
        m1, h1 = m1[m1.index < now], h1[h1.index < now.floor("h")]
        cut = m1.index[-1] - pd.Timedelta(days=float(self.lc["history_days"])) if len(m1) else None
        if cut is not None:
            m1 = m1[m1.index >= cut]
        return m1, h1

    def frames(self, long: bool = False) -> dict[tuple[str, str], dict]:
        """(symbol, tf) → bars + the multi-TF bias score known at each bar close (hard rule in backtests).
        long=True: up to `learner.history_days` for the learning cycle; otherwise the recent window."""
        out = {}
        for s in self.cfg["instruments"]:
            if long:
                from ..indicators import resample_ohlc
                lm1, h1 = self.long_m1(s)
            else:
                h1 = self.ctx.store.h1(s)
            for tf in self.cfg["timeframes"]["entry"]:
                n = int(self.ec["lookback_days"] * 24 * 60 / (pd.Timedelta(tf).total_seconds() / 60))
                df = resample_ohlc(lm1, tf) if long else self.ctx.store.tf(s, tf).iloc[-n:].copy()
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
        split = int(len(df) * float(self.lc["is_frac"]))
        if part == "is":
            d = df.iloc[:split]
            if "ctx_is" not in item:
                item["ctx_is"] = Strategy.context(d)
            return backtest(st, d, item["ctx_is"], self.mgmt(st), s["entry_windows"], s["flatten_at"],
                            bias_score=bias[:split], **kw)
        if ctx is None:
            if "ctx_full" not in item:
                item["ctx_full"] = Strategy.context(df)
            ctx = item["ctx_full"]
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
            self.record_forward(trades, now)
            self.log.info("evaluated %d versions × %d symbols in %.1fs", len(self.ctx.book.evaluated()), len(out),
                          time.perf_counter() - t0)
            await self.bus.publish("stats_updated", {"ts": now.isoformat()})
        finally:
            self.busy = False

    def record_forward(self, trades: dict, now: pd.Timestamp) -> None:
        """Store every completed simulated trade permanently (a trade is complete once the max hold
        time has passed since its entry), so forward records outlive the rolling window."""
        done_before = now - pd.Timedelta(minutes=float(self.cfg["sessions"]["max_hold_minutes"]) + 5)
        rows = []
        for sym, per in trades.items():
            for sid, tr in per.items():
                rows += [(sid, sym, t["ts"].isoformat(), round(float(t["r"]), 4)) for t in tr if t["ts"] <= done_before]
        try:
            self.ctx.journal.add_forward(rows)
        except Exception as e:  # noqa: BLE001
            self.log.warning("forward record: %s", e)

    def real_stats(self, sid: str, since: str | None) -> dict:
        """Actual trades of this version: the account's journal + the shadow book's journal."""
        n, tot, w = 0, 0.0, 0.0
        books = [self.ctx.journal] + ([self.ctx.shadow.journal] if getattr(self.ctx, "shadow", None) else [])
        for j in books:
            s = j.live_stats(strategy=sid, since=since)
            n += s["n"]; tot += s["n"] * s["expectancy"]; w += s["n"] * s["win_rate"]
        return {"n": n, "expectancy": round(tot / n, 3) if n else 0.0, "win_rate": round(w / n, 3) if n else 0.0}

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
            frames = self.frames(True)     # reads the live bar store → stays on the event loop
            span = max((len(v["df"]) for v in frames.values()), default=0)
            self._note(ts, f"learning on {span} bars per symbol/TF (walk-forward {self.lc['is_frac']:.0%} fit / "
                           f"{1-float(self.lc['is_frac']):.0%} validate)")
            props = await asyncio.to_thread(self._search, frames, list(self.ctx.book.live()))
            created = 0
            seen = {self._sig(x.spec()) for x in self.ctx.book.items.values()}
            for r in self.ctx.journal.strategy_rows():            # retired ones too: never re-propose them
                try:
                    seen.add(self._sig(__import__("json").loads(r["spec"])))
                except Exception:  # noqa: BLE001
                    pass
            for pr in props:
                if self._sig(pr["spec"]) in seen:
                    continue
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
                                     "origin": f"learner:{pr['parent']}", "created": ts,
                                     "meta": {"kind": pr["kind"], "parent": pr["parent"], "change": pr["change"],
                                              "oos_gain_r": round(gain, 3), "oos_n": pr["oos"]["n"],
                                              "jev_robust": round(review["prob"], 2)}}
                st = build_strategy(spec)
                if st.id in self.ctx.book.items:
                    continue
                self.ctx.book.add(st, ts, f"{pr['kind']} {pr['change']} OOS +{gain:.2f}R")
                seen.add(self._sig(pr["spec"]))
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

    @staticmethod
    def _sig(spec: dict) -> str:
        """Identity of a version's behaviour (class, timeframe, parameters, R:R) — not its name."""
        import json
        return json.dumps([spec.get("class"), spec.get("tf"), spec.get("params"), float(spec.get("rr") or 1.0)],
                          sort_keys=True, default=str)

    def _forward(self, sid: str, since: str | None) -> dict:
        """Forward record from the permanent store (accumulates across evaluation windows/restarts)."""
        return self.ctx.journal.forward_stats(sid, since)

    async def promote_demote(self, now, ts):
        book, ec = self.ctx.book, self.ec
        # promote shadows that beat their parent on forward (post-creation) trades
        for st in [s for s in book.items.values() if s.status == "shadow" and s.origin.startswith("learner:")]:
            parent_id = st.origin.split(":", 1)[1]
            since = getattr(st, "created", None)
            fwd = self._forward(st.id, since)
            par = self._forward(parent_id, since)
            real = self.real_stats(st.id, since)
            real_veto = real["n"] >= int(self.lc["real_block_n"]) and real["expectancy"] < 0
            if real_veto and fwd["n"] >= ec["min_trades_promote"]:
                self._note(ts, f"held {st.id}: simulated forward {fwd['expectancy']:+.2f}R but real trades "
                               f"{real['expectancy']:+.2f}R over {real['n']}")
            if fwd["n"] >= ec["min_trades_promote"] and fwd["expectancy"] >= par["expectancy"] + ec["promote_margin_r"] \
                    and fwd["expectancy"] > 0 and not real_veto:
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
        live = [s for s in book.items.values() if s.status == "live"]
        for st in sorted(live, key=lambda s: pooled[s.id]["expectancy"]):
            p = pooled[st.id]
            if len([s for s in book.items.values() if s.status == "live"]) <= 2:
                break
            real = self.real_stats(st.id, None)
            if p["n"] >= 20 and p["expectancy"] < ec["demote_below_r"]:
                book.set_status(st.id, "shadow", ts, f"demoted: {p['expectancy']:+.2f}R over {p['n']}")
                self._note(ts, f"demoted {st.id} to shadow ({p['expectancy']:+.2f}R over {p['n']} simulated trades)")
            elif real["n"] >= int(self.lc["real_demote_n"]) and real["expectancy"] < ec["demote_below_r"]:
                book.set_status(st.id, "shadow", ts, f"demoted on real trades: {real['expectancy']:+.2f}R over {real['n']}")
                self._note(ts, f"demoted {st.id} to shadow ({real['expectancy']:+.2f}R over {real['n']} real trades)")
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
