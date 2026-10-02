"""Turn a replay's journals into a report: headline metrics, equity, monthly and per-day P&L,
breakdowns (symbol, setup, hour, weekday, exit reason), trade list and learner activity."""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pandas as pd

LEARNER_KEYS = ("new shadow", "PROMOTED", "demoted", "retired", "held", "re-activated", "learning on")


def _rows(db: sqlite3.Connection, q: str, args=()) -> list[dict]:
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(q, args)]


def _group(trades: list[dict], key) -> list[dict]:
    g: dict = {}
    for t in trades:
        k = key(t)
        d = g.setdefault(k, {"key": k, "n": 0, "wins": 0, "sum_r": 0.0, "pnl": 0.0})
        d["n"] += 1; d["wins"] += (t["r_multiple"] or 0) > 0
        d["sum_r"] += t["r_multiple"] or 0; d["pnl"] += t["realized"] or 0
    out = []
    for d in g.values():
        out.append({**d, "win_rate": round(d["wins"] / d["n"], 3), "avg_r": round(d["sum_r"] / d["n"], 3),
                    "sum_r": round(d["sum_r"], 2), "pnl": round(d["pnl"], 2)})
    return out


def book_report(path: str | Path, start_equity: float) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    db = sqlite3.connect(str(path))
    trades = _rows(db, "SELECT id, symbol, side, strategy, tf, opened, closed, hour, r_multiple, realized, exit_reason, "
                       "adds, stage, jev_quality, bias_mode FROM trades WHERE status='closed' ORDER BY closed")
    eq = _rows(db, "SELECT ts, equity FROM equity ORDER BY ts")
    learner = [r for r in _rows(db, "SELECT ts, msg FROM learner_log ORDER BY id")
               if any(k in r["msg"] for k in LEARNER_KEYS)]
    db.close()
    rs = [t["r_multiple"] or 0.0 for t in trades]
    n = len(trades)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    pnl = sum(t["realized"] or 0 for t in trades)
    # equity / drawdown
    eq_daily, max_dd, max_dd_pct = [], 0.0, 0.0
    if eq:
        e = pd.Series([x["equity"] for x in eq], index=pd.to_datetime([x["ts"] for x in eq], utc=True))
        peak = e.cummax()
        dd = e - peak
        max_dd = float(dd.min())
        max_dd_pct = float((dd / peak).min())
        daily = e.groupby(e.index.tz_convert("America/New_York").date).last()
        eq_daily = [{"date": str(d), "equity": round(float(v), 2)} for d, v in daily.items()]
    # per day
    days: dict[str, dict] = {}
    for t in trades:
        d = (t["closed"] or "")[:10]
        x = days.setdefault(d, {"date": d, "n": 0, "pnl": 0.0, "r": 0.0})
        x["n"] += 1; x["pnl"] += t["realized"] or 0; x["r"] += t["r_multiple"] or 0
    day_list = [{**v, "pnl": round(v["pnl"], 2), "r": round(v["r"], 2)} for v in sorted(days.values(), key=lambda v: v["date"])]
    dp = [v["pnl"] for v in day_list]
    sharpe = None
    if len(eq_daily) > 5:
        rets = pd.Series([x["equity"] for x in eq_daily]).pct_change().dropna()
        if rets.std() > 0:
            sharpe = round(float(rets.mean() / rets.std() * math.sqrt(252)), 2)
    streak = cur = 0
    for r in rs:
        cur = cur + 1 if r < 0 else 0
        streak = max(streak, cur)
    holds = []
    for t in trades:
        try:
            holds.append((pd.Timestamp(t["closed"]) - pd.Timestamp(t["opened"])).total_seconds() / 60)
        except Exception:  # noqa: BLE001
            pass
    months = _group(trades, lambda t: (t["closed"] or "")[:7])
    summary = {
        "trades": n, "win_rate": round(len(wins) / n, 3) if n else 0.0, "sum_r": round(sum(rs), 2),
        "avg_r": round(sum(rs) / n, 3) if n else 0.0,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
        "pnl": round(pnl, 2), "return_pct": round(pnl / start_equity, 4) if start_equity else None,
        "max_dd": round(max_dd, 2), "max_dd_pct": round(max_dd_pct, 4), "sharpe": sharpe,
        "best_day": round(max(dp), 2) if dp else 0.0, "worst_day": round(min(dp), 2) if dp else 0.0,
        "green_days": sum(1 for x in dp if x > 0), "red_days": sum(1 for x in dp if x < 0),
        "max_losing_streak": streak, "avg_hold_min": round(sum(holds) / len(holds)) if holds else None,
        "pyramided": sum(1 for t in trades if (t["adds"] or 0) > 0),
    }
    return {
        "summary": summary, "equity_daily": eq_daily, "days": day_list,
        "months": sorted(months, key=lambda x: x["key"]),
        "by_symbol": sorted(_group(trades, lambda t: t["symbol"]), key=lambda x: -x["sum_r"]),
        "by_setup": sorted(_group(trades, lambda t: (t["strategy"] or "").split(":")[0]), key=lambda x: -x["sum_r"]),
        "by_hour": sorted(_group(trades, lambda t: t["hour"]), key=lambda x: x["key"] if x["key"] is not None else -1),
        "by_weekday": sorted(_group(trades, lambda t: pd.Timestamp(t["opened"]).dayofweek if t["opened"] else -1),
                             key=lambda x: x["key"]),
        "by_exit": sorted(_group(trades, lambda t: (t["exit_reason"] or "").split(":")[0]), key=lambda x: -x["n"]),
        "trades": trades[-400:][::-1],
        "learner": learner[-80:][::-1],
    }


def build(out_dir: str | Path, meta: dict) -> dict:
    out = Path(out_dir)
    eq0 = float(meta.get("equity") or 100000)
    rep = {"meta": meta,
           "books": {"main": book_report(out / "journal.sqlite", eq0),
                     "shadow": book_report(out / "journal_shadow.sqlite", eq0)},
           "caveats": [
               "No historical economic calendar: news blackouts and event-day half size were NOT applied.",
               "Fills are simulated at bar prices plus an estimated half-spread; real fills will differ.",
               ("Jev was the live API." if meta.get("jev") == "live" else
                "Jev was replaced by the local heuristic (fast and free, but only an approximation of Jev)."),
               "The setup-map prior was off (the map is built on history that overlaps this period).",
               "For speed, each strategy scans the whole period once instead of a 700-bar window per bar; in testing "
               "the two agreed on 99.9% of bars, with a few percent of individual signals differing at window edges.",
               "Strategies were partly designed and tuned on recent markets — past results flatter future ones.",
           ]}
    (out / "report.json").write_text(json.dumps(rep, default=str))
    return rep
