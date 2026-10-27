"""Jev trade adviser — asks Jev every 15 minutes what it would do with each open trade, and NEVER acts on it.

Why (Oct 21 2026): Sam manages winners and losers by judgement — cut a trade going against the plan early, hold/add/trail
one that is working. Mechanical versions of that all made C10 worse on 2021–2026 (cut after 30 min: +0.258R → +0.123R;
breakeven, half off at 1R and trailing: −0.05R each). Discretion uses more than a clock, so this measures whether Jev's
judgement beats doing nothing, on the paper book, before it is ever allowed to touch a trade.

Each call (at every 15-minute close while a trade is open, from 15 minutes after entry) asks two questions
(jev.manage_trade): p_worse = will the trade finish worse than it stands now?  p_extend = will it run another 1R first?
The advice: CUT if p_worse >= cut_at; else ADD if p_extend >= add_at and the trade is in profit; else HOLD.
Logged on the trade's timeline and in the journal's `jev_advice` table. When the trade closes, every call is scored:
  value_cut = R if closed at that moment − R the trade really finished with    (> 0: cutting then would have helped)
  value_add = R a second, same-size unit bought at that moment would have made to the real exit, after the spread
              (> 0: adding then would have helped)
The scorecard compares CUT calls (should have value_cut > 0) with HOLD calls (should have value_cut < 0), and ADD calls
(value_add > 0). Only answers from Jev itself count (source = jev); heuristic fallbacks are kept but marked.
Config: jev_advisor: {books: [c10_afternoon], every_min: 15, cut_at: 0.6, add_at: 0.6}.
"""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from .core import Agent
from .trading import half_spread

PARTNER = {"NDQ": "US30", "US30": "NDQ"}
THESIS = {
    "c10_afternoon": ("Morning-to-afternoon continuation: the index moved one way from yesterday's close to 10:00 and still "
                      "held that direction at 13:00, at least 1 ATR from the 09:30 open with a steady (efficient) move. "
                      "Entered at 13:00 in that direction; stop 1.25 × 15-minute ATR, target 2R, out at 15:45. "
                      "Backtest: most of the profit comes from trades held to 15:45."),
}
TIME_EXIT = {"c10_afternoon": "15:45"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jev_advice(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, pos_id TEXT, symbol TEXT, strategy TEXT, source TEXT, action TEXT,
  p_worse REAL, conf_worse REAL, p_extend REAL, conf_extend REAL, r_now REAL, r_if_exit REAL, price REAL, mfe REAL,
  held_min REAL);
CREATE TABLE IF NOT EXISTS jev_advice_outcome(
  advice_id INTEGER PRIMARY KEY, pos_id TEXT, strategy TEXT, source TEXT, action TEXT, r_if_exit REAL, final_r REAL,
  value_cut REAL, value_add REAL);
CREATE INDEX IF NOT EXISTS ix_jev_advice_pos ON jev_advice(pos_id);
"""


def ensure_schema(journal) -> None:
    journal.db.executescript(SCHEMA)
    journal.db.commit()


def action_of(a: dict, r_now: float, cut_at: float, add_at: float) -> str:
    if a["p_worse"] >= cut_at:
        return "cut"
    if a["p_extend"] >= add_at and r_now > 0:
        return "add"
    return "hold"


def candles(df: pd.DataFrame, n: int, tz: str) -> list:
    d = df.iloc[-n:]
    return [[t.tz_convert(tz).strftime("%H:%M"), round(float(r.open), 2), round(float(r.high), 2), round(float(r.low), 2),
             round(float(r.close), 2)] for t, r in d.iterrows()]


class JevAdvisorAgent(Agent):
    name = "jev_advisor"

    def start(self):
        super().start()
        c = self.cfg.get("jev_advisor") or {}
        self.books = set(c.get("books") or ["c10_afternoon"])
        self.every = int(c.get("every_min", 15))
        self.cut_at, self.add_at = float(c.get("cut_at", 0.6)), float(c.get("add_at", 0.6))
        self.on = bool(c.get("enabled", True)) and getattr(self.ctx, "book_key", None) in self.books \
            and getattr(self.ctx, "jev", None) is not None and self.ctx.journal is not None
        self._tasks: dict[str, asyncio.Task] = {}   # pos_id -> in-flight advice; also keeps references alive
        if not self.on:
            return
        ensure_schema(self.ctx.journal)
        self.bus.subscribe("bar_1m", self.on_bar)
        self.bus.subscribe("position_closed", self.on_closed)

    def r_if_exit(self, pos, price: float) -> float:
        mult = float(self.cfg["instruments"][pos.symbol].get("multiplier", 1))
        risk_ccy = pos.initial_qty * pos.risk_per_unit * mult
        px = price - pos.side * half_spread(self.cfg, pos.symbol)
        return float((pos.realized + pos.unrealized(px, mult)) / risk_ccy) if risk_ccy else 0.0

    async def on_bar(self, bar):
        self.beat()
        end = pd.Timestamp(bar.ts) + pd.Timedelta("1min")
        if end.minute % self.every:
            return
        for pos in [p for p in self.state.positions.values() if p.symbol == bar.symbol and p.status == "open"]:
            held = (end - pd.Timestamp(pos.opened_ts)).total_seconds() / 60
            if held < self.every - 0.5:
                continue
            if pos.id in self._tasks:       # one call in flight per position; this 15-minute mark is skipped
                continue
            try:
                snap = self.snapshot(pos, bar.close, end, held)
            except Exception as e:  # noqa: BLE001 — the adviser must never disturb trading
                self.log.warning("jev adviser %s: %s", pos.symbol, e)
                continue
            task = asyncio.ensure_future(self._advise_bg(pos, snap))
            self._tasks[pos.id] = task
            task.add_done_callback(lambda t, pid=pos.id: self._tasks.get(pid) is t and self._tasks.pop(pid, None))

    async def drain(self) -> None:
        """Wait for in-flight advice calls (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
            await asyncio.sleep(0)

    def deadline(self) -> float:
        """Hard limit for one Jev call: the Jev client's own timeout plus its 1 s wait_for margin, plus 1 s."""
        return float((self.cfg.get("jev") or {}).get("timeout_s", 6)) + 2

    async def _advise_bg(self, pos, snap: dict) -> None:
        """Run one advice call off the bar path (Oct 26 2026). Never raises; a reply about a trade that has since
        closed (or a different position) is obsolete and dropped."""
        try:
            a = await asyncio.wait_for(self.ctx.jev.manage_trade(snap["info"]), timeout=self.deadline())
            if pos.status != "open" or self.state.positions.get(pos.id) is not pos:
                self.log.info("jev adviser %s: dropped reply, position %s no longer open", pos.symbol, pos.id)
                return
            self.record(pos, snap, a)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — the adviser must never disturb trading (timeouts land here too)
            self.log.warning("jev adviser %s: %r", pos.symbol, e)

    def info_for(self, pos, price: float, now: pd.Timestamp, held: float) -> dict:
        tz, store, sym = self.cfg["timezone"], self.ctx.store, pos.symbol
        b15, b5 = store.tf(sym, "15min"), store.tf(sym, "5min")
        loc = now.tz_convert(tz)
        today = b15[b15.index.tz_convert(tz).normalize() == loc.normalize()]
        r_now = pos.r_now(price)
        info = {"symbol": sym, "strategy": pos.strategy, "side": "LONG" if pos.side > 0 else "SHORT",
                "thesis": THESIS.get(pos.strategy, pos.reason), "entry_reason": pos.reason,
                "time_ny": loc.strftime("%H:%M"), "time_exit_ny": TIME_EXIT.get(pos.strategy, "15:50"),
                "entry": round(pos.entry, 2), "stop": round(pos.stop, 2),
                "target": round(pos.meta["target"], 2) if pos.meta.get("target") else None,
                "price": round(price, 2), "r_now": round(r_now, 2), "best_r": round(pos.mfe_r, 2),
                "worst_r": round(pos.mae_r, 2), "minutes_held": round(held),
                "today_open_0930": round(float(today[today.index.tz_convert(tz).strftime("%H:%M") == "09:30"].open.iloc[0]), 2)
                if (today.index.tz_convert(tz).strftime("%H:%M") == "09:30").any() else None,
                "candles_15m_today": candles(today, 32, tz), "candles_5m_recent": candles(b5, 12, tz)}
        ps = PARTNER.get(sym)
        if ps:
            try:
                p15 = store.tf(ps, "15min")
                pt = p15[p15.index.tz_convert(tz).normalize() == loc.normalize()]
                info["other_index"] = {"symbol": ps, "candles_15m_today": candles(pt, 32, tz)}
            except Exception:  # noqa: BLE001
                pass
        nw = getattr(self.ctx, "news", None)
        if nw is not None:
            try:
                info["news_next_hour"] = [{"title": e.get("title"), "tier": e.get("tier"),
                                           "in_min": round((e["ts"] - now).total_seconds() / 60)} for e in nw.upcoming(now, 1)]
            except Exception:  # noqa: BLE001
                pass
        bias = self.state.bias.get(sym) or {}
        if bias:
            info["htf_bias"] = {k: bias.get(k) for k in ("label", "score", "d", "h4", "h1")}
        return info

    def snapshot(self, pos, price: float, now: pd.Timestamp, held: float) -> dict:
        """Everything advice needs as of the bar close, taken before the (slow) model call (Oct 26 2026)."""
        return {"info": self.info_for(pos, price, now, held), "price": price, "now": now, "held": held,
                "r_now": pos.r_now(price), "r_exit": self.r_if_exit(pos, price), "mfe": pos.mfe_r}

    def record(self, pos, snap: dict, a: dict) -> dict:
        """Journal + timeline the answer, using the snapshot values; the advice time is the bar end it was asked for."""
        now, price, held, r_now = snap["now"], snap["price"], snap["held"], snap["r_now"]
        act = action_of(a, r_now, self.cut_at, self.add_at)
        rec = (now.isoformat(), pos.id, pos.symbol, pos.strategy, a["source"], act, a["p_worse"], a["conf_worse"],
               a["p_extend"], a["conf_extend"], round(r_now, 3), round(snap["r_exit"], 3), price,
               round(snap["mfe"], 3), round(held, 1))
        j = self.ctx.journal
        j.db.execute("INSERT INTO jev_advice(ts,pos_id,symbol,strategy,source,action,p_worse,conf_worse,p_extend,conf_extend,"
                     "r_now,r_if_exit,price,mfe,held_min) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rec)
        j.db.commit()
        prev = pos.meta.get("jev_advice")
        if act != prev:
            pos.log(now, "jev_advice", action=act, p_worse=a["p_worse"], p_extend=a["p_extend"], r=round(r_now, 2),
                    source=a["source"], shadow=True)
        pos.meta["jev_advice"] = act
        return {"action": act, **a}

    async def advise(self, pos, price: float, now: pd.Timestamp, held: float) -> dict:
        """Ask and record in one await (kept for direct callers; on_bar uses the background path)."""
        snap = self.snapshot(pos, price, now, held)
        return self.record(pos, snap, await self.ctx.jev.manage_trade(snap["info"]))

    async def on_closed(self, ev):
        pos, px = ev["position"], float(ev.get("price") or pos.last_price or 0)
        j = self.ctx.journal
        rows = [dict(r) for r in j.db.execute("SELECT * FROM jev_advice WHERE pos_id=?", (pos.id,))]
        if not rows:
            return
        mult = float(self.cfg["instruments"][pos.symbol].get("multiplier", 1))
        risk_ccy = pos.initial_qty * pos.risk_per_unit * mult
        if not risk_ccy or not pos.risk_per_unit:
            return
        final = pos.realized / risk_ccy
        sp = 2 * half_spread(self.cfg, pos.symbol)
        for r in rows:
            v_add = (pos.side * (px - r["price"]) - sp) / pos.risk_per_unit
            j.db.execute("INSERT OR REPLACE INTO jev_advice_outcome VALUES(?,?,?,?,?,?,?,?,?)",
                         (r["id"], pos.id, pos.strategy, r["source"], r["action"], r["r_if_exit"], round(final, 3),
                          round(r["r_if_exit"] - final, 3), round(v_add, 3)))
        j.db.commit()


def _ci(v: np.ndarray, rng) -> tuple[float, float]:
    if len(v) < 2:
        return (float(v[0]), float(v[0])) if len(v) else (float("nan"), float("nan"))
    b = v[rng.integers(0, len(v), (2000, len(v)))].mean(1)
    return float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))


def scorecard(journal, seed: int = 11) -> dict:
    """Per advice type (Jev answers only): how often, and the average value of following it with a 95% range.
    Plus the 'follow the first CUT' policy: average final R if every trade had been closed at its first CUT call,
    against what the trades really did (the bar Jev has to beat)."""
    ensure_schema(journal)
    rows = [dict(r) for r in journal.db.execute("SELECT * FROM jev_advice_outcome")]
    rng = np.random.default_rng(seed)
    jev = [r for r in rows if r["source"] == "jev"]
    out = {"n_trades": len({r["pos_id"] for r in jev}), "n_calls": len(jev),
           "n_heuristic": len(rows) - len(jev), "actions": []}
    # "helped" = share of calls where the advice was right: CUT value_cut > 0, HOLD value_cut < 0, ADD value_add > 0
    # (HOLD was inverted before; Oct 26 2026).
    for act, key, meaning in (("cut", "value_cut", "closing then vs holding to the real exit"),
                              ("hold", "value_cut", "closing then vs holding (negative = holding was right)"),
                              ("add", "value_add", "a second unit added then, to the real exit")):
        v = np.array([r[key] for r in jev if r["action"] == act], float)
        if not len(v):
            continue
        lo, hi = _ci(v, rng)
        out["actions"].append({"action": act, "n": int(len(v)), "avg_value_r": round(float(v.mean()), 3),
                               "lo": round(lo, 3), "hi": round(hi, 3), "helped": round(float(((v < 0) if act == "hold" else (v > 0)).mean()), 3),
                               "meaning": meaning})
    by_pos: dict[str, dict] = {}
    for r in sorted(jev, key=lambda x: x["advice_id"]):
        d = by_pos.setdefault(r["pos_id"], {"final": r["final_r"], "cut": None})
        if r["action"] == "cut" and d["cut"] is None:
            d["cut"] = r["r_if_exit"]
    if by_pos:
        real = np.array([d["final"] for d in by_pos.values()], float)
        pol = np.array([d["final"] if d["cut"] is None else d["cut"] for d in by_pos.values()], float)
        lo, hi = _ci(pol - real, rng)
        out["policy"] = {"trades": len(real), "actual_avg_r": round(float(real.mean()), 3),
                         "follow_first_cut_avg_r": round(float(pol.mean()), 3),
                         "difference": round(float((pol - real).mean()), 3), "lo": round(lo, 3), "hi": round(hi, 3)}
    out["recent"] = [dict(r) for r in journal.db.execute(
        "SELECT ts,pos_id,symbol,strategy,source,action,p_worse,p_extend,r_now FROM jev_advice ORDER BY id DESC LIMIT 30")]
    return out
