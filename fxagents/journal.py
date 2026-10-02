"""Trade journal (SQLite). Every trade, every management event, every Jev decision, every signal
taken or skipped (with the reason), strategy versions, and the equity curve."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades(
  id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT, status TEXT,
  opened TEXT, closed TEXT, hour INTEGER, entry REAL, avg_entry REAL, exit_price REAL,
  initial_stop REAL, final_stop REAL, qty_initial REAL, qty_gross REAL, adds INTEGER, stage INTEGER,
  realized REAL, commissions REAL, r_multiple REAL, mfe_r REAL, mae_r REAL, exit_reason TEXT,
  jev_quality REAL, jev_confidence REAL, jev_source TEXT, reason TEXT, events TEXT, notes TEXT,
  bias_mode TEXT, tf TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, source TEXT, symbol TEXT, strategy TEXT,
  latency_ms REAL, inputs TEXT, outputs TEXT);
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, strategy TEXT, side TEXT,
  entry REAL, stop REAL, action TEXT, why TEXT, quality REAL, confidence REAL);
CREATE TABLE IF NOT EXISTS strategy_versions(
  id TEXT PRIMARY KEY, spec TEXT, status TEXT, created TEXT, updated TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS forward_trades(version TEXT, symbol TEXT, ts TEXT, r REAL, PRIMARY KEY(version, symbol, ts));
CREATE TABLE IF NOT EXISTS equity(ts TEXT, equity REAL, realized_today REAL);
CREATE TABLE IF NOT EXISTS learner_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, msg TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS ix_trades_closed ON trades(closed);
CREATE INDEX IF NOT EXISTS ix_dec_ts ON decisions(ts);
"""


class Journal:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ── writes ────────────────────────────────────────────────────────────
    def upsert_trade(self, pos, mult: float, exit_price: float | None = None) -> None:
        risk_ccy = pos.initial_qty * pos.risk_per_unit * mult
        r_mult = pos.realized / risk_ccy if risk_ccy and pos.status == "closed" else None
        row = dict(
            id=pos.id, symbol=pos.symbol, side="LONG" if pos.side > 0 else "SHORT", strategy=pos.strategy,
            status=pos.status, opened=pos.opened_ts.isoformat(), closed=pos.closed_ts.isoformat() if pos.closed_ts else None,
            hour=pos.opened_ts.hour, entry=pos.entry, avg_entry=pos.avg_entry, exit_price=exit_price,
            initial_stop=pos.initial_stop, final_stop=pos.stop, qty_initial=pos.initial_qty, qty_gross=pos.gross_qty,
            adds=pos.adds, stage=pos.stage, realized=round(pos.realized, 2), commissions=round(pos.commissions, 2),
            r_multiple=round(r_mult, 3) if r_mult is not None else None, mfe_r=round(pos.mfe_r, 2),
            mae_r=round(pos.mae_r, 2), exit_reason=pos.exit_reason, jev_quality=pos.jev_quality,
            jev_confidence=pos.jev_confidence, jev_source=pos.jev_source, reason=pos.reason,
            events=json.dumps(pos.events, default=str), notes=None, bias_mode=pos.bias_mode,
            tf=pos.strategy.split(":")[1].split("@")[0] if ":" in pos.strategy and "@" in pos.strategy else "")
        cols = ",".join(row)
        q = ",".join("?" * len(row))
        upd = ",".join(f"{k}=excluded.{k}" for k in row if k not in ("id", "notes"))
        self.db.execute(f"INSERT INTO trades({cols}) VALUES({q}) ON CONFLICT(id) DO UPDATE SET {upd}", list(row.values()))
        self.db.commit()

    def add_decision(self, d: dict) -> None:
        self.db.execute("INSERT INTO decisions(ts,kind,source,symbol,strategy,latency_ms,inputs,outputs) VALUES(?,?,?,?,?,?,?,?)",
                        (d.get("ts"), d.get("kind"), d.get("source"), d.get("symbol"), d.get("strategy"),
                         d.get("latency_ms"), json.dumps(d.get("inputs"), default=str), json.dumps(d.get("outputs"), default=str)))
        self.db.commit()

    def add_signal(self, s: dict) -> None:
        self.db.execute("INSERT INTO signals(ts,symbol,strategy,side,entry,stop,action,why,quality,confidence) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (s["ts"], s["symbol"], s["strategy"], s["side"], s["entry"], s["stop"], s["action"],
                         s.get("why"), s.get("quality"), s.get("confidence")))
        self.db.commit()

    def save_strategy(self, spec: dict, ts: str, notes: str = "") -> None:
        self.db.execute("INSERT INTO strategy_versions(id,spec,status,created,updated,notes) VALUES(?,?,?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET spec=excluded.spec,status=excluded.status,updated=excluded.updated,"
                        "notes=COALESCE(excluded.notes, strategy_versions.notes)",
                        (spec["id"], json.dumps(spec), spec["status"], ts, ts, notes or None))
        self.db.commit()

    def add_forward(self, rows: list[tuple]) -> int:
        """Completed simulated trades per version, kept permanently so forward records accumulate
        over weeks (the rolling evaluation window alone forgets them). rows = (version, symbol, ts, r)."""
        if not rows:
            return 0
        cur = self.db.executemany("INSERT OR IGNORE INTO forward_trades VALUES(?,?,?,?)", rows)
        self.db.commit()
        return cur.rowcount

    def forward_stats(self, version: str, since: str | None = None) -> dict:
        q = "SELECT COUNT(*), AVG(r), SUM(CASE WHEN r>0 THEN 1 ELSE 0 END) FROM forward_trades WHERE version=?"
        args: list = [version]
        if since:
            q += " AND ts>=?"; args.append(since)
        n, exp, w = self.db.execute(q, args).fetchone()
        return {"n": n or 0, "expectancy": round(exp or 0.0, 3), "win_rate": round((w or 0) / n, 3) if n else 0.0}

    def strategy_rows(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT id, spec, status, created, updated, notes FROM strategy_versions")]

    def load_strategies(self) -> list[dict]:
        return [json.loads(r["spec"]) for r in self.db.execute("SELECT spec FROM strategy_versions")]

    def add_equity(self, ts: str, equity: float, realized_today: float) -> None:
        self.db.execute("INSERT INTO equity VALUES(?,?,?)", (ts, equity, realized_today))
        self.db.commit()

    def learner(self, ts: str, msg: str, data: Any = None) -> None:
        self.db.execute("INSERT INTO learner_log(ts,msg,data) VALUES(?,?,?)", (ts, msg, json.dumps(data, default=str)))
        self.db.commit()

    def set_note(self, trade_id: str, note: str) -> None:
        self.db.execute("UPDATE trades SET notes=? WHERE id=?", (note, trade_id))
        self.db.commit()

    # ── reads ─────────────────────────────────────────────────────────────
    def trades(self, limit: int = 200, status: str | None = "closed") -> list[dict]:
        q = "SELECT * FROM trades" + (" WHERE status=?" if status else "") + " ORDER BY COALESCE(closed, opened) DESC LIMIT ?"
        args = (status, limit) if status else (limit,)
        return [dict(r) for r in self.db.execute(q, args)]

    def live_stats(self, symbol: str | None = None, strategy: str | None = None, since: str | None = None) -> dict:
        q = "SELECT r_multiple, hour FROM trades WHERE status='closed' AND r_multiple IS NOT NULL"
        args: list = []
        for col, v in (("symbol", symbol), ("strategy", strategy)):
            if v:
                q += f" AND {col}=?"; args.append(v)
        if since:
            q += " AND closed>=?"; args.append(since)
        rs = [r[0] for r in self.db.execute(q, args)]
        if not rs:
            return {"n": 0, "expectancy": 0.0, "win_rate": 0.0}
        return {"n": len(rs), "expectancy": round(sum(rs) / len(rs), 3),
                "win_rate": round(sum(1 for r in rs if r > 0) / len(rs), 3)}

    def summary(self, since: str | None = None) -> dict:
        q = "SELECT realized, r_multiple FROM trades WHERE status='closed'" + (" AND closed>=?" if since else "")
        rows = list(self.db.execute(q, (since,) if since else ()))
        n = len(rows)
        pnl = sum(r[0] or 0 for r in rows)
        rr = [r[1] for r in rows if r[1] is not None]
        wins = [x for x in rr if x > 0]
        return {"trades": n, "pnl": round(pnl, 2), "win_rate": round(len(wins) / n, 3) if n else 0.0,
                "avg_r": round(sum(rr) / len(rr), 3) if rr else 0.0, "sum_r": round(sum(rr), 2)}

    def daily(self, start: str | None = None, end: str | None = None) -> dict[str, dict]:
        """P&L per trading day (NY calendar date of the exit)."""
        q = ("SELECT substr(closed,1,10) d, COUNT(*) n, SUM(realized) pnl, SUM(r_multiple) r, "
             "SUM(CASE WHEN realized>0 THEN 1 ELSE 0 END) w, MAX(realized) best, MIN(realized) worst "
             "FROM trades WHERE status='closed'")
        args: list = []
        if start:
            q += " AND substr(closed,1,10)>=?"; args.append(start)
        if end:
            q += " AND substr(closed,1,10)<=?"; args.append(end)
        q += " GROUP BY d ORDER BY d"
        return {r["d"]: {"trades": r["n"], "pnl": round(r["pnl"] or 0, 2), "r": round(r["r"] or 0, 2),
                         "wins": r["w"], "best": round(r["best"] or 0, 2), "worst": round(r["worst"] or 0, 2)}
                for r in self.db.execute(q, args)}

    def day_trades(self, day: str) -> list[dict]:
        rows = [dict(r) for r in self.db.execute(
            "SELECT * FROM trades WHERE status='closed' AND substr(closed,1,10)=? ORDER BY closed", (day,))]
        for r in rows:
            r["events"] = json.loads(r["events"] or "[]")
        return rows

    def equity_series(self, limit: int = 2000) -> list[dict]:
        rows = self.db.execute("SELECT ts, equity FROM equity ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows][::-1]

    def decisions(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))]

    def signal_funnel(self, since: str | None = None) -> dict:
        """What happened to every setup seen: per setup type, per hour, and per action (taken / filtered /
        skipped / rejected), with the most common reasons."""
        q = "SELECT ts, strategy, action, why FROM signals" + (" WHERE ts>=?" if since else "")
        rows = list(self.db.execute(q, (since,) if since else ()))
        by_setup: dict[str, dict] = {}
        by_hour: dict[int, dict] = {}
        reasons: dict[str, int] = {}
        for ts, strat, action, why in rows:
            setup = (strat or "").split(":")[0].split("@")[0]
            d = by_setup.setdefault(setup, {"seen": 0, "taken": 0, "filtered": 0, "skipped": 0, "rejected": 0})
            d["seen"] += 1
            d[action if action in d else "skipped"] += 1
            try:
                h = int(ts[11:13])
            except (TypeError, ValueError):
                continue
            hh = by_hour.setdefault(h, {"seen": 0, "taken": 0})
            hh["seen"] += 1
            hh["taken"] += action == "taken"
            if action != "taken" and why:
                key = why.split("(")[0].split(":")[0].strip()[:60]
                reasons[key] = reasons.get(key, 0) + 1
        return {"by_setup": by_setup, "by_hour": {str(k): v for k, v in sorted(by_hour.items())},
                "reasons": sorted(reasons.items(), key=lambda x: -x[1])[:10], "total": len(rows)}

    def signals(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))]
