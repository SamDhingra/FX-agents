"""Ghost trades and the filter scorecard. Read-only: nothing here changes trading.

Every setup a book saw is in its journal's `signals` table — taken, or passed with a reason (news blackout, bias
rule, Jev gate, risk, capacity, chop filter …). For each one this module plays out what WOULD have happened, on the
1-minute bars, with one fixed exit rule for all of them, and stores the result in a `ghosts` table in the same
journal (so results outlive the in-memory bar store).

The rule, fixed here and identical for passed and taken setups (so they compare like for like):
  • entry   the open of the first 1-minute bar after the signal candle has closed (no look-ahead), paying half
            the configured spread; the setup's own stop
  • exit    the stop, a 1.5R target, or 4 hours / the 15:50 NY flatten, whichever comes first (stops win ties)
  • the R of a ghost is NOT the R the bot would have made with its own management (partials, trailing stops);
    it is a common yardstick. The scorecard compares each filter's ghosts with the TAKEN setups under the same rule:
    a filter helps if the setups it blocked do worse than the ones it let through.
Repeats of the same setup (symbol + strategy + side) within 15 minutes are counted once.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

TARGET_R = 1.5
MAX_HOLD_MIN = 240
DEDUPE_MIN = 15
SCHEMA = """CREATE TABLE IF NOT EXISTS ghosts(
  signal_id INTEGER PRIMARY KEY, ts TEXT, symbol TEXT, strategy TEXT, side INTEGER, action TEXT, filter TEXT, why TEXT,
  entry_ts TEXT, entry REAL, stop REAL, exit_ts TEXT, exit REAL, r REAL, outcome TEXT, jev REAL);"""

FILTERS = [  # (label, pattern on the reason) — first match wins
    ("News blackout", r"news|pre-news"), ("Bias rule", r"bias|counter to"), ("Chop filter", r"regime|chop|scalps"),
    ("Jev gate", r"jev"), ("Better setup same bar", r"better setup|higher-expectancy"),
    ("Position limits", r"already has|opposite position|max.?open|positions? per|capacity"),
    ("Risk sizing", r"risk budget|unit\(s\)|margin|stop .* of trade value"), ("Trading paused", r"halted|paused|entries blocked"),
    ("Session window", r"window|session|outside"), ("Instrument off", r"instrument off|is off|watch-only"),
    ("Equity unknown", r"equity unknown"), ("Broker", r"broker")]


def filter_of(action: str, why: str | None) -> str:
    if action == "taken":
        return "Taken"
    w = (why or "").lower()
    for label, pat in FILTERS:
        if re.search(pat, w):
            return label
    return (why or "Other").split(":")[0].strip()[:40] or "Other"


def tf_minutes(strategy: str) -> int:
    m = re.search(r":(\d+)(m|min|h)\b", strategy or "")
    if not m:
        return 1
    n = int(m.group(1))
    return n * 60 if m.group(2) == "h" else n


def side_of(v) -> int:
    if isinstance(v, str):
        return 1 if v.upper().startswith(("L", "B", "1")) else -1
    return 1 if (v or 0) > 0 else -1


def ensure(journal) -> None:
    journal.db.executescript(SCHEMA)


def simulate(m1: pd.DataFrame, ts: pd.Timestamp, side: int, stop: float, tf_min: int, hs: float, flat_hm=(15, 50)):
    """Play one setup out on mid 1-minute bars. Returns dict or None when the bars don't cover it yet / any more."""
    if not len(m1):
        return None
    start = ts + pd.Timedelta(minutes=tf_min)
    if start < m1.index[0]:
        return {"outcome": "no data"}
    j0 = int(m1.index.searchsorted(start))
    if j0 >= len(m1) or (m1.index[j0] - start) > pd.Timedelta("30min"):
        return None if j0 >= len(m1) else {"outcome": "no data"}
    entry = float(m1["open"].iat[j0]) + side * hs
    risk = side * (entry - stop)
    if not risk > 0:
        return {"outcome": "invalid", "entry_ts": m1.index[j0], "entry": entry}
    target = entry + side * TARGET_R * risk
    loc = m1.index[j0].tz_convert("America/New_York")
    flat = loc.normalize() + pd.Timedelta(hours=flat_hm[0], minutes=flat_hm[1])
    if flat <= loc:
        flat += pd.Timedelta(days=1)
    end_t = min(m1.index[j0] + pd.Timedelta(minutes=MAX_HOLD_MIN), flat)
    j1 = int(m1.index.searchsorted(end_t))
    seg = m1.iloc[j0:j1]
    lo = seg["low"].to_numpy() - (hs if side > 0 else -hs)      # exit side: bid for longs, ask for shorts
    hi = seg["high"].to_numpy() - (hs if side > 0 else -hs)
    if side > 0:
        hit_s, hit_t = lo <= stop, hi >= target
    else:
        hit_s, hit_t = hi >= stop, lo <= target
    s_i = int(np.argmax(hit_s)) if hit_s.any() else None
    t_i = int(np.argmax(hit_t)) if hit_t.any() else None
    if s_i is not None and (t_i is None or s_i <= t_i):
        return {"outcome": "stop", "entry_ts": m1.index[j0], "entry": entry, "exit_ts": seg.index[s_i], "exit": stop, "r": -1.0}
    if t_i is not None:
        return {"outcome": "target", "entry_ts": m1.index[j0], "entry": entry, "exit_ts": seg.index[t_i], "exit": target, "r": TARGET_R}
    if j1 >= len(m1):
        return None                                                 # not finished yet
    px = float(m1["open"].iat[j1]) - side * hs
    return {"outcome": "time", "entry_ts": m1.index[j0], "entry": entry, "exit_ts": m1.index[j1], "exit": px,
            "r": round(side * (px - entry) / risk, 4)}


def resolve(c, limit: int = 400) -> int:
    """Play out the signals of one book that have no ghost yet. Returns how many were stored."""
    j = c.journal
    ensure(j)
    rows = j.db.execute("SELECT s.* FROM signals s LEFT JOIN ghosts g ON g.signal_id = s.id WHERE g.signal_id IS NULL "
                        "AND s.stop IS NOT NULL ORDER BY s.id LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    spread = ((c.cfg.get("shadow") or {}).get("spread") or {})
    last_seen: dict[tuple, pd.Timestamp] = {}
    prev = j.db.execute("SELECT symbol, strategy, side, MAX(ts) FROM ghosts WHERE outcome != 'duplicate' "
                        "GROUP BY symbol, strategy, side").fetchall()
    for sym, strat, sd, t in prev:
        if t:
            last_seen[(sym, strat, sd)] = pd.Timestamp(t)
    frames: dict[str, pd.DataFrame] = {}
    n = 0
    for r in rows:
        r = dict(r)
        sym, side = r["symbol"], side_of(r["side"])
        if sym not in frames:
            try:
                frames[sym] = c.store.m1(sym)
            except Exception:  # noqa: BLE001
                frames[sym] = pd.DataFrame()
        ts = pd.Timestamp(r["ts"])
        key = (sym, r["strategy"], side)
        filt = filter_of(r["action"], r.get("why"))
        base = {"signal_id": r["id"], "ts": r["ts"], "symbol": sym, "strategy": r["strategy"], "side": side,
                "action": r["action"], "filter": filt, "why": r.get("why"), "stop": r["stop"], "jev": r.get("quality")}
        if r["action"] != "taken" and key in last_seen and ts - last_seen[key] < pd.Timedelta(minutes=DEDUPE_MIN):
            _store(j, base | {"outcome": "duplicate"})
            n += 1
            continue
        res = simulate(frames[sym], ts, side, float(r["stop"]), tf_minutes(r["strategy"]), float(spread.get(sym, 0.0)) / 2)
        if res is None:
            continue                                                # wait for more bars
        last_seen[key] = ts
        _store(j, base | res)
        n += 1
    j.db.commit()
    return n


def _store(j, g: dict) -> None:
    cols = ["signal_id", "ts", "symbol", "strategy", "side", "action", "filter", "why", "entry_ts", "entry", "stop",
            "exit_ts", "exit", "r", "outcome", "jev"]
    vals = [str(g[k]) if isinstance(g.get(k), pd.Timestamp) else g.get(k) for k in cols]
    j.db.execute(f"INSERT OR REPLACE INTO ghosts({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)


def scorecard(c, since: str | None = None) -> dict:
    """Per filter: how many setups it blocked, their ghost R, against the taken setups under the same exit rule."""
    from .insights import boot_ci
    j = c.journal
    ensure(j)
    q = "SELECT * FROM ghosts WHERE r IS NOT NULL" + (" AND ts >= ?" if since else "")
    rows = [dict(x) for x in j.db.execute(q, (since,) if since else ())]
    pend = j.db.execute("SELECT COUNT(*) FROM signals s LEFT JOIN ghosts g ON g.signal_id = s.id "
                        "WHERE g.signal_id IS NULL AND s.stop IS NOT NULL").fetchone()[0]
    df = pd.DataFrame(rows)
    out = {"rule": {"target_r": TARGET_R, "max_hold_min": MAX_HOLD_MIN}, "pending": int(pend), "filters": [], "taken": None}
    if not len(df):
        return out
    df["day"] = df["ts"].str[:10]

    def pack(g):
        r = g["r"].to_numpy(float)
        ci = boot_ci(r, g["day"].to_numpy())
        return {"n": int(len(r)), "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 2),
                "win": round(float((r > 0).mean()), 3), "ci": [round(ci[0], 3), round(ci[1], 3)] if ci else None}
    tk = df[df.action == "taken"]
    out["taken"] = pack(tk) if len(tk) else None
    base = out["taken"]["avg_r"] if out["taken"] else 0.0
    for f, g in df[df.action != "taken"].groupby("filter"):
        p = pack(g)
        p["filter"] = f
        p["saved_r"] = round(-p["sum_r"], 2)            # what not taking them was worth, under the common exit rule
        ci = p["ci"]
        p["verdict"] = ("early" if p["n"] < 30 or not ci else "helping" if ci[1] < base else "hurting" if ci[0] > base else "unclear")
        out["filters"].append(p)
    out["filters"].sort(key=lambda x: -x["n"])
    return out


def recent(c, symbol: str | None = None, start: str | None = None, end: str | None = None, limit: int = 60) -> list[dict]:
    ensure(c.journal)
    q, a = "SELECT * FROM ghosts WHERE outcome NOT IN ('duplicate','no data')", []
    if symbol:
        q += " AND symbol = ?"; a.append(symbol)
    if start:
        q += " AND ts >= ?"; a.append(start)
    if end:
        q += " AND ts <= ?"; a.append(end)
    q += " ORDER BY ts DESC LIMIT ?"; a.append(limit)
    return [dict(x) for x in c.journal.db.execute(q, a)]
