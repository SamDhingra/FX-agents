"""Trade analyst — watches every open trade and says what it would do: hold, tighten, or exit, and why.

SHADOW ONLY (Oct 2026): it never touches a position. Every verdict is written to the trade's timeline and to the
journal's `analyst` table; when the trade closes, each piece of advice is scored against what actually happened
(value = the R the whole position would have had if it had been closed at the advice, minus the R it really
finished with — positive means the advice would have helped). The scorecard decides whether the analyst ever gets
to act (that needs a positive, steady record AND the historical check, ./fx.sh analystcheck, to agree).

Checks, run at every 5-minute close for each open trade (the first three are the same rules the historical check
replays in research.simulate_live):
  trend_flip       EXIT     the last closed 15m candle crossed its EMA50 against the trade
  structure_break  EXIT     a closed 5m candle closed beyond the last confirmed 5m swing low (longs) / high (shorts)
  stall            EXIT     no new best price for 60 minutes while the trade is under +0.5R
  h1_against       TIGHTEN  the last closed 1H candle is on the wrong side of its EMA50
  giveback         TIGHTEN  the trade reached ≥ +1R and has given back half of its best open profit
  news_soon        TIGHTEN  a high-impact release is due within 20 minutes
A verdict is logged when it changes (or a new exit reason appears), not every 5 minutes.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .core import Agent
from .trading import half_spread

EXIT_CHECKS = ("trend_flip", "structure_break", "stall")
TIGHTEN_CHECKS = ("h1_against", "giveback", "news_soon")
LABEL = {"trend_flip": "15m trend flipped against the trade", "structure_break": "5m structure broke",
         "stall": "stalled: no new best for 60 min and under +0.5R", "h1_against": "1H trend is against the trade",
         "giveback": "gave back half of a ≥1R open profit", "news_soon": "high-impact news within 20 min"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyst(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, pos_id TEXT, symbol TEXT, strategy TEXT, verdict TEXT,
  checks TEXT, r_now REAL, r_if_exit REAL, mfe REAL, price REAL);
CREATE TABLE IF NOT EXISTS analyst_outcome(
  pos_id TEXT, check_name TEXT, ts TEXT, symbol TEXT, strategy TEXT, r_if_exit REAL, final_r REAL, value REAL,
  PRIMARY KEY(pos_id, check_name));
CREATE INDEX IF NOT EXISTS ix_analyst_pos ON analyst(pos_id);
"""


def ensure_schema(journal) -> None:
    journal.db.executescript(SCHEMA)
    journal.db.commit()


def swing_lows(h: np.ndarray, l: np.ndarray):
    """Last confirmed 2-candle swing low / high as of each candle's close (known 2 candles later)."""
    n = len(l)
    sl, sh = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(2, n - 2):
        if l[i] < min(l[i - 2], l[i - 1], l[i + 1], l[i + 2]):
            sl[i + 2] = l[i]
        if h[i] > max(h[i - 2], h[i - 1], h[i + 1], h[i + 2]):
            sh[i + 2] = h[i]
    return pd.Series(sl).ffill().to_numpy(), pd.Series(sh).ffill().to_numpy()


def checks_for(side: int, b5: pd.DataFrame, b15: pd.DataFrame, b60: pd.DataFrame, mfe: float, r_now: float,
               idle_min: float, news_in: float | None) -> list[str]:
    """Pure function: which checks fire for a trade of `side` given CLOSED 5m / 15m / 1H candles."""
    out = []
    if len(b15) >= 52:
        c = b15["close"].to_numpy(float)
        e = pd.Series(c).ewm(span=50, adjust=False, min_periods=50).mean().to_numpy()
        if side * (c[-1] - e[-1]) < 0 <= side * (c[-2] - e[-2]):
            out.append("trend_flip")
    if len(b5) >= 8:
        sl, sh = swing_lows(b5["high"].to_numpy(float), b5["low"].to_numpy(float))
        lvl = sl[-2] if side > 0 else sh[-2]                     # the last swing confirmed BEFORE this candle
        if np.isfinite(lvl) and side * (float(b5["close"].iloc[-1]) - lvl) < 0:
            out.append("structure_break")
    if idle_min >= 60 and r_now < 0.5:
        out.append("stall")
    if len(b60) >= 51:
        c = b60["close"].to_numpy(float)
        e = pd.Series(c).ewm(span=50, adjust=False, min_periods=50).mean().to_numpy()
        if side * (c[-1] - e[-1]) < 0:
            out.append("h1_against")
    if mfe >= 1.0 and r_now <= 0.5 * mfe:
        out.append("giveback")
    if news_in is not None and 0 <= news_in <= 20:
        out.append("news_soon")
    return out


def verdict_of(checks: list[str]) -> str:
    if any(c in EXIT_CHECKS for c in checks):
        return "exit"
    if any(c in TIGHTEN_CHECKS for c in checks):
        return "tighten"
    return "hold"


class TradeAnalystAgent(Agent):
    name = "trade_analyst"

    def start(self):
        super().start()
        self.bus.subscribe("bar_1m", self.on_bar)
        self.bus.subscribe("position_closed", self.on_closed)
        self.on = bool((self.cfg.get("analyst") or {}).get("enabled", True))
        if self.on and self.ctx.journal is not None:
            ensure_schema(self.ctx.journal)

    def r_if_exit(self, pos, price: float) -> float:
        """R of the WHOLE position (banked partials + open units) if it were closed now at market."""
        mult = float(self.cfg["instruments"][pos.symbol].get("multiplier", 1))
        risk_ccy = pos.initial_qty * pos.risk_per_unit * mult
        px = price - pos.side * half_spread(self.cfg, pos.symbol)
        return float((pos.realized + pos.unrealized(px, mult)) / risk_ccy) if risk_ccy else 0.0

    async def on_bar(self, bar):
        if not self.on:
            return
        self.beat()
        end = pd.Timestamp(bar.ts) + pd.Timedelta("1min")
        if end.minute % 5:
            return                                               # analyse at 5-minute closes only
        for pos in [p for p in self.state.positions.values() if p.symbol == bar.symbol and p.status == "open"]:
            try:
                self.analyse(pos, bar.close, end)
            except Exception as e:  # noqa: BLE001 — the analyst must never disturb trading
                self.log.warning("analyst %s: %s", pos.symbol, e)

    def analyse(self, pos, price: float, now: pd.Timestamp) -> dict:
        store = self.ctx.store
        b5, b15, b60 = (store.tf(pos.symbol, r) for r in ("5min", "15min", "1h"))
        opened = pd.Timestamp(pos.opened_ts)
        b5 = b5[b5.index >= opened - pd.Timedelta(hours=8)]
        best = pd.Timestamp(pos.meta.get("best_ts") or opened)
        idle = (now - best).total_seconds() / 60
        r_now = pos.r_now(price)
        news_in = None
        nw = getattr(self.ctx, "news", None)
        if nw is not None:
            try:
                ev = [e for e in nw.upcoming(now, 1) if e.get("tier") == "tier1"]
                if ev:
                    news_in = min((e["ts"] - now).total_seconds() / 60 for e in ev)
            except Exception:  # noqa: BLE001
                news_in = None
        checks = checks_for(pos.side, b5, b15, b60, pos.mfe_r, r_now, idle, news_in)
        v = verdict_of(checks)
        prev = pos.meta.get("analyst") or {}
        seen = set(prev.get("seen", []))
        new_exit = [c for c in checks if c in EXIT_CHECKS and c not in seen]
        rec = {"ts": now.isoformat(), "verdict": v, "checks": checks, "r_now": round(r_now, 3),
               "r_if_exit": round(self.r_if_exit(pos, price), 3), "mfe": round(pos.mfe_r, 3), "price": price}
        if v != prev.get("verdict") or new_exit:
            why = "; ".join(LABEL[c] for c in checks) or "trade on track"
            pos.log(now, "analyst", verdict=v, why=why, r=rec["r_now"], shadow=True)
            j = self.ctx.journal
            if j is not None:
                j.db.execute("INSERT INTO analyst(ts,pos_id,symbol,strategy,verdict,checks,r_now,r_if_exit,mfe,price) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?)", (rec["ts"], pos.id, pos.symbol, pos.strategy, v,
                                                             json.dumps(checks), rec["r_now"], rec["r_if_exit"],
                                                             rec["mfe"], price))
                j.db.commit()
        first = dict(prev.get("first", {}))
        for c in checks:
            first.setdefault(c, {"ts": rec["ts"], "r_if_exit": rec["r_if_exit"]})
        if v == "exit":
            first.setdefault("any_exit", {"ts": rec["ts"], "r_if_exit": rec["r_if_exit"]})
        pos.meta["analyst"] = {"verdict": v, "checks": checks, "seen": sorted(seen | set(checks)), "first": first,
                               "ts": rec["ts"]}
        return rec

    async def on_closed(self, ev):
        if not self.on:
            return
        pos = ev["position"]
        a = pos.meta.get("analyst") or {}
        j = self.ctx.journal
        if not a.get("first") or j is None:
            return
        mult = float(self.cfg["instruments"][pos.symbol].get("multiplier", 1))
        risk_ccy = pos.initial_qty * pos.risk_per_unit * mult
        if not risk_ccy:
            return
        final = pos.realized / risk_ccy
        for name, f in a["first"].items():
            j.db.execute("INSERT OR REPLACE INTO analyst_outcome VALUES(?,?,?,?,?,?,?,?)",
                         (pos.id, name, f["ts"], pos.symbol, pos.strategy, f["r_if_exit"], round(final, 3),
                          round(f["r_if_exit"] - final, 3)))
        j.db.commit()


def scorecard(journal, seed: int = 11) -> dict:
    """Per check: how many closed trades it fired on, the average value of following it (R), a 95% bootstrap range,
    and how often it would have helped. Positive = following the analyst would have beaten what the trade did."""
    ensure_schema(journal)
    rows = [dict(r) for r in journal.db.execute("SELECT * FROM analyst_outcome")]
    out = {"n_trades": len({r["pos_id"] for r in rows}), "checks": []}
    rng = np.random.default_rng(seed)
    for name in ("any_exit", *EXIT_CHECKS, *TIGHTEN_CHECKS):
        v = np.array([r["value"] for r in rows if r["check_name"] == name], float)
        if not len(v):
            continue
        boot = v[rng.integers(0, len(v), (2000, len(v)))].mean(1) if len(v) > 1 else v
        lo, hi = (np.quantile(boot, [0.025, 0.975]) if len(v) > 1 else (v[0], v[0]))
        out["checks"].append({"check": name, "label": LABEL.get(name, "any exit advice"),
                              "kind": "exit" if name in EXIT_CHECKS or name == "any_exit" else "tighten",
                              "n": int(len(v)), "avg_value_r": round(float(v.mean()), 3),
                              "lo": round(float(lo), 3), "hi": round(float(hi), 3),
                              "helped": round(float((v > 0).mean()), 3)})
    recent = [dict(r) for r in journal.db.execute(
        "SELECT ts,pos_id,symbol,strategy,verdict,checks,r_now,r_if_exit FROM analyst ORDER BY id DESC LIMIT 40")]
    for r in recent:
        r["checks"] = json.loads(r["checks"] or "[]")
        r["why"] = "; ".join(LABEL.get(c, c) for c in r["checks"]) or "trade on track"
    out["recent"] = recent
    return out
