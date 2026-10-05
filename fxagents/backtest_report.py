"""Turn a replay's journals into a report: headline metrics, equity, monthly and per-day P&L,
breakdowns (symbol, setup, hour, weekday, exit reason), trade list and learner activity."""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pandas as pd

LEARNER_KEYS = ("new shadow", "PROMOTED", "demoted", "retired", "held", "re-activated", "learning on", "KILL SWITCH")


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
    kills = [r for r in learner if r["msg"].startswith("KILL SWITCH")]
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
        "kill_switch": len(kills), "kill_dates": [str(k["ts"])[:10] for k in kills],
    }
    by_instrument = {}
    for sym in sorted({t["symbol"] for t in trades}):
        tt = [t for t in trades if t["symbol"] == sym]
        r_ = [t["r_multiple"] or 0.0 for t in tt]
        w_, l_ = [x for x in r_ if x > 0], [x for x in r_ if x < 0]
        cum, curve, peak, dd = 0.0, [], 0.0, 0.0
        for t in tt:
            cum += t["realized"] or 0.0
            peak = max(peak, cum); dd = min(dd, cum - peak)
            curve.append({"date": (t["closed"] or "")[:10], "pnl": round(cum, 2)})
        daily = {}
        for c in curve:
            daily[c["date"]] = c["pnl"]
        by_instrument[sym] = {
            "summary": {"trades": len(tt), "win_rate": round(len(w_) / len(tt), 3) if tt else 0.0,
                        "sum_r": round(sum(r_), 2), "avg_r": round(sum(r_) / len(tt), 3) if tt else 0.0,
                        "profit_factor": round(sum(w_) / -sum(l_), 2) if l_ else None,
                        "pnl": round(sum(t["realized"] or 0 for t in tt), 2), "max_dd": round(dd, 2),
                        "pyramided": sum(1 for t in tt if (t["adds"] or 0) > 0)},
            "pnl_daily": [{"date": d, "pnl": v} for d, v in sorted(daily.items())],
            "months": sorted(_group(tt, lambda t: (t["closed"] or "")[:7]), key=lambda x: x["key"]),
            "by_setup": sorted(_group(tt, lambda t: (t["strategy"] or "").split(":")[0]), key=lambda x: -x["sum_r"]),
            "by_tf": sorted(_group(tt, lambda t: (t["strategy"] or ":?").split(":")[1].split("@")[0] if ":" in (t["strategy"] or "") else "?"),
                            key=lambda x: -x["sum_r"]),
            "by_hour": sorted(_group(tt, lambda t: t["hour"]), key=lambda x: x["key"] if x["key"] is not None else -1),
            "by_exit": sorted(_group(tt, lambda t: (t["exit_reason"] or "").split(":")[0]), key=lambda x: -x["n"]),
            "trades": tt[-200:][::-1]}
    return {
        "summary": summary, "equity_daily": eq_daily, "days": day_list, "by_instrument": by_instrument,
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


def build(out_dir: str | Path, meta: dict, cfg: dict | None = None) -> dict:
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
               "Kill switch: a daily-loss halt resumes next day as live; a max-drawdown halt (which live waits for you "
               "to resume) also resumes next day from a new peak, so the run covers the whole period. Count and dates "
               "are in the summary.",
               "Strategies were partly designed and tuned on recent markets — past results flatter future ones.",
           ]}
    if cfg is not None:
        for k, f in (("main", "journal.sqlite"), ("shadow", "journal_shadow.sqlite")):
            if rep["books"][k]:
                try:
                    rep["books"][k]["whatif"] = filter_whatif(out / f, cfg)
                except Exception as e:  # noqa: BLE001  never lose the report over the extra section
                    rep["books"][k]["whatif_error"] = str(e)
    (out / "report.json").write_text(json.dumps(rep, default=str))
    return rep


# ── what-if: how would the signals the filters blocked have done? ─────────────
def _bucket(row: dict, jc: dict) -> str:
    a, why = row["action"], row["why"] or ""
    if a == "taken":
        return "taken"
    if why.startswith("counter to"):
        return "blocked: counter to bias"
    if why.startswith("bias neutral"):
        return "blocked: bias neutral"
    if why.startswith("Jev") and row["quality"] is not None:
        q_ok = row["quality"] >= jc["min_signal_quality"]
        c_ok = (row["confidence"] or 0) >= jc["min_signal_confidence"] * 0.8
        return ("blocked: Jev confidence" if q_ok and not c_ok else
                "blocked: Jev quality" if c_ok and not q_ok else "blocked: Jev quality + confidence")
    if why.startswith("instrument off"):
        return "blocked: instrument off"
    if a == "rejected":
        return "blocked: risk rules"
    return "skipped: other"


def filter_whatif(journal: str | Path, cfg: dict) -> list[dict] | None:
    """Simulate every logged signal with the bot's own trade management (stop, 1R partial, trailing,
    adds, session flat) on the cached history, grouped by why it was or wasn't taken. Approximate:
    first target 1R, no slippage, no Jev pyramid check — good for comparing groups, not for exact P&L."""
    import numpy as np
    from .indicators import resample_ohlc
    from .setup_map import load_history
    from .sim import Mgmt, simulate_outcome
    path = Path(journal)
    if not path.exists():
        return None
    db = sqlite3.connect(str(path))
    sigs = _rows(db, "SELECT ts, symbol, strategy, side, entry, stop, action, why, quality, confidence FROM signals")
    db.close()
    if not sigs:
        return []
    jc, frames, out = cfg["jev"], {}, {}
    fh, fm = map(int, cfg["sessions"]["flatten_at"].split(":"))
    seen = set()
    for s in sigs:
        key = (s["ts"], s["symbol"], s["strategy"], s["side"])
        if key in seen:
            continue
        seen.add(key)
        tf = "15min" if ":15m" in (s["strategy"] or "") else "5min"
        fk = (s["symbol"], tf)
        if fk not in frames:
            h = load_history(cfg, s["symbol"])
            if h is None:
                frames[fk] = None
            else:
                m1 = h[0] if isinstance(h, tuple) else h
                df = resample_ohlc(m1, tf)
                close_ts = df.index + pd.Timedelta(tf)
                mins = close_ts.hour * 60 + close_ts.minute
                tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                                (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
                frames[fk] = (df, np.asarray((mins >= fh * 60 + fm) & (mins < 17 * 60), dtype=bool),
                              tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy())
        fr = frames[fk]
        if fr is None or s["entry"] is None or s["stop"] is None:
            continue
        df, flat, atr = fr
        ts = pd.Timestamp(s["ts"])
        lo = df.index.searchsorted(ts - 3 * pd.Timedelta(tf))
        hi = df.index.searchsorted(ts, side="right")
        if hi <= lo:
            continue
        C = df["close"].to_numpy()
        i0 = lo + int(np.argmin(np.abs(C[lo:hi] - s["entry"])))
        side = 1 if s["side"] == "LONG" else -1
        entry, stop = float(s["entry"]), float(s["stop"])
        if (entry - stop) * side <= 0:
            continue
        if abs(entry - C[i0]) > 2 * atr[i0]:
            continue          # the history doesn't match this journal (e.g. a run made on other data) — don't guess
        m = Mgmt.from_cfg(cfg, bar_minutes=int(pd.Timedelta(tf).total_seconds() // 60))
        if abs(entry - stop) < m.min_stop_atr * atr[i0]:            # the live risk agent widens these
            stop = entry - side * m.min_stop_atr * atr[i0]
        if abs(entry - stop) / entry > m.max_stop_pct:
            continue
        O, H, L = (df[c].to_numpy() for c in ("open", "high", "low"))
        r = simulate_outcome(O, H, L, C, i0, side, entry, stop, m, flat)["r"]
        b = _bucket(s, jc)
        d = out.setdefault(b, {"key": b, "n": 0, "wins": 0, "sum_r": 0.0})
        d["n"] += 1; d["wins"] += r > 0; d["sum_r"] += r
    order = ["taken", "blocked: counter to bias", "blocked: bias neutral", "blocked: Jev quality",
             "blocked: Jev confidence", "blocked: Jev quality + confidence", "blocked: risk rules", "blocked: instrument off", "skipped: other"]
    res = [{**d, "sum_r": round(d["sum_r"], 2), "avg_r": round(d["sum_r"] / d["n"], 3),
            "win_rate": round(d["wins"] / d["n"], 3)} for d in out.values()]
    return sorted(res, key=lambda x: order.index(x["key"]) if x["key"] in order else 99)


def rebuild(run_dir: str | Path, config: str = "config.yaml") -> dict:
    """Re-make report.json for an existing run (adds sections introduced after it ran)."""
    from .config import load_config
    out = Path(run_dir)
    meta = json.loads((out / "meta.json").read_text())
    cfg = load_config(config)
    return build(out, meta, cfg)


if __name__ == "__main__":
    import sys
    for d in sys.argv[1:] or sorted(str(p) for p in (Path("data/backtests")).glob("*") if (p / "meta.json").exists()):
        try:
            rebuild(d)
            print("rebuilt", d)
        except Exception as e:  # noqa: BLE001
            print("skipped", d, e)
