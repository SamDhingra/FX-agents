"""Journal tables for the shadow review gate (Oct 26 2026): one row per candidate entry, one row per (candidate,
provider, prompt version). The candidate id is the position id, so a review joins to `trades` (r_multiple, status) when
the trade closes. `called` = 1 when an API call was actually made (what the daily budget counts)."""
from __future__ import annotations

import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS dyn_candidates(
  candidate_id TEXT PRIMARY KEY, book TEXT, symbol TEXT, side TEXT, strategy TEXT, ts TEXT, packet_hash TEXT,
  packet TEXT, status TEXT, prompt_version TEXT, exchange_status TEXT, exchange_ms REAL, exchange_decision TEXT);
CREATE TABLE IF NOT EXISTS dyn_reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT, provider TEXT, model TEXT, prompt_version TEXT,
  packet_hash TEXT, action TEXT, trigger_id TEXT, invalidation_id TEXT, evidence TEXT, conflicting TEXT, missing TEXT,
  latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, error TEXT, called INTEGER, day TEXT,
  response TEXT, ts TEXT, round INTEGER DEFAULT 1, changed INTEGER, why_changed TEXT,
  UNIQUE(candidate_id, provider, prompt_version, round));
CREATE INDEX IF NOT EXISTS ix_dyn_reviews_cand ON dyn_reviews(candidate_id);
CREATE INDEX IF NOT EXISTS ix_dyn_reviews_day ON dyn_reviews(provider, day);
"""


MIGRATIONS = (   # milestone 1b (Oct 27 2026): columns added to tables created by milestone 1; existing reviews are round 1
    ("dyn_reviews", "round", "INTEGER DEFAULT 1"), ("dyn_reviews", "changed", "INTEGER"), ("dyn_reviews", "why_changed", "TEXT"),
    ("dyn_candidates", "exchange_status", "TEXT"), ("dyn_candidates", "exchange_ms", "REAL"),
    ("dyn_candidates", "exchange_decision", "TEXT"))


def ensure_schema(journal) -> None:
    journal.db.executescript(SCHEMA)
    for table, col, decl in MIGRATIONS:
        if col not in {r[1] for r in journal.db.execute(f"PRAGMA table_info({table})")}:
            journal.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    journal.db.commit()   # (an old table keeps its milestone-1 unique key; round 2 rows differ in prompt_version, so it still holds)


def add_candidate(journal, packet: dict, status: str, prompt_version: str) -> None:
    c = packet["candidate"]
    journal.db.execute(
        "INSERT OR REPLACE INTO dyn_candidates(candidate_id,book,symbol,side,strategy,ts,packet_hash,packet,status,"
        "prompt_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (c["id"], c["book"], c["symbol"], c["side"], c["strategy"], c["entry_time_utc"], packet["packet_hash"],
         json.dumps(packet, sort_keys=True), status, prompt_version))
    journal.db.commit()


def set_status(journal, candidate_id: str, status: str) -> None:
    journal.db.execute("UPDATE dyn_candidates SET status=? WHERE candidate_id=?", (status, candidate_id))
    journal.db.commit()


def set_exchange(journal, candidate_id: str, status: str, ms: float | None = None, decision: str | None = None) -> None:
    """How the exchange went: status `done` or `skipped: <reason>`, the full exchange latency (round-1 hand-over to
    round-2 end), and the decision rule's verdict (enter / wait / cancel) when it ran."""
    journal.db.execute("UPDATE dyn_candidates SET exchange_status=?, exchange_ms=?, exchange_decision=? WHERE candidate_id=?",
                       (status, None if ms is None else round(float(ms), 1), decision, candidate_id))
    journal.db.commit()


def add_review(journal, candidate_id: str, provider: str, model: str, prompt_version: str, packet_hash: str, res: dict,
               called: bool, day: str, ts: str, round_no: int = 1) -> None:
    journal.db.execute(
        "INSERT OR REPLACE INTO dyn_reviews(candidate_id,provider,model,prompt_version,packet_hash,action,trigger_id,"
        "invalidation_id,evidence,conflicting,missing,latency_ms,tokens_in,tokens_out,cost_usd,error,called,day,response,ts,"
        "round,changed,why_changed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (candidate_id, provider, model, prompt_version, packet_hash, res["action"], res.get("trigger_id"),
         res.get("invalidation_id"), res.get("evidence"), res.get("conflicting"), json.dumps(res.get("missing") or []),
         None if res.get("latency_ms") is None else round(float(res["latency_ms"]), 1), res.get("tokens_in"),
         res.get("tokens_out"), res.get("cost_usd"), res.get("error"), int(bool(called)), day, res.get("response"), ts,
         int(round_no), None if res.get("changed") is None else int(bool(res["changed"])), res.get("why_changed")))
    journal.db.commit()


def calls_on(journal, provider: str, day: str) -> int:
    """API calls already made for this provider on this NY trading day (the daily budget's count)."""
    r = journal.db.execute("SELECT COALESCE(SUM(called),0) FROM dyn_reviews WHERE provider=? AND day=?", (provider, day)).fetchone()
    return int(r[0] or 0)


def reviews_for(journal, trade_id: str) -> list[dict]:
    """The reviews of one trade (round 1 then round 2 per provider); [] when the tables don't exist or hold nothing.
    Milestone-1 databases without the round columns read as round 1."""
    try:
        have = {r[1] for r in journal.db.execute("PRAGMA table_info(dyn_reviews)")}
        extra = "round, changed, why_changed, " if "round" in have else ""
        rows = [dict(r) for r in journal.db.execute(
            "SELECT provider, model, prompt_version, action, trigger_id, invalidation_id, evidence, conflicting, missing, "
            f"latency_ms, tokens_in, tokens_out, cost_usd, error, {extra}ts FROM dyn_reviews WHERE candidate_id=? "
            "ORDER BY prompt_version, provider", (trade_id,))]
    except Exception:  # noqa: BLE001 — no table yet
        return []
    for r in rows:
        r.setdefault("round", 1)
        r.setdefault("changed", None)
        r.setdefault("why_changed", None)
        try:
            r["missing"] = json.loads(r["missing"] or "[]")
        except ValueError:
            r["missing"] = []
    return rows


def exchange_for(journal, trade_id: str) -> dict | None:
    """{status, ms, decision} of the exchange on one candidate, or None when nothing was recorded."""
    try:
        r = journal.db.execute("SELECT exchange_status, exchange_ms, exchange_decision FROM dyn_candidates WHERE candidate_id=?",
                               (trade_id,)).fetchone()
    except Exception:  # noqa: BLE001 — no table / old columns
        return None
    if r is None or r[0] is None:
        return None
    return {"status": r[0], "ms": r[1], "decision": r[2]}
