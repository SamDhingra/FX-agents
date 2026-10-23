"""A short written lesson for each closed practice-account trade (Oct 2026, after TradingAgents' reflection log).

Once a trade closes, 2–3 sentences say what happened (R, how far it went for and against it, how it exited), whether
the exit or management changed the result, and the strategy's record AT THAT CLOSE — so a single trade is always
read against its sample size. Claude writes it when ANTHROPIC_API_KEY is set; otherwise a plain rule-based line does.

Reading only. Lessons are shown in the trade story and handed to Ask Claude; nothing that decides a trade (the
strategies, Risk, Jev prompts, the learner) ever reads them. Feeding one-trade lessons back into decisions would be
tuning on seen data, one trade at a time.

Point in time: the record quoted in a lesson counts only trades that had closed by the lesson's own trade, so a
lesson written late (after a restart) says what was known then, not what is known now.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import numpy as np

log = logging.getLogger("lessons")

SCHEMA = """CREATE TABLE IF NOT EXISTS lessons(trade_id TEXT PRIMARY KEY, ts TEXT, text TEXT, source TEXT, model TEXT,
facts TEXT)"""

SYSTEM = (
    "You review one closed intraday trade from Sam's trading bot, using ONLY the FACTS JSON. Write 2 or 3 sentences "
    "of plain prose, no bullets, no markdown, under 70 words. Cover in order: (1) what happened, citing the R result, "
    "how far it went in its favour (mfe_r) and against it (mae_r) and how it exited; (2) whether the exit or the "
    "management changed the result (for example it reached +0.9R and was then stopped, or the partial banked most "
    "of it); (3) the strategy's record at this close (record_at_close: trades and average R) and that one trade "
    "does not change it. Never suggest changing rules, parameters, risk or size, and never give financial advice. "
    "R = profit or loss in units of the risk taken.")

EXITS = {"stop": "was stopped out", "target": "hit its target", "partial_stop": "banked a partial, then the rest was stopped",
         "time": "was closed by the time exit", "flatten": "was flattened at the session end", "stall": "was closed by the stall rule",
         "manual": "was closed by hand", "news": "was closed ahead of news", "session_flat": "was flattened at the session end",
         "trail_stop": "was closed by the trailing stop", "max_hold": "was closed at its maximum hold time"}


def ensure(journal) -> None:
    journal.db.execute(SCHEMA)
    journal.db.commit()


def _fam(strategy: str) -> str:
    return (strategy or "").split(":")[0].split("@")[0] or "other"


def record_at(journal, trade: dict) -> dict:
    """The strategy family's closed-trade record up to and including this trade's close — nothing later."""
    fam = _fam(trade["strategy"])
    rs = [float(r) for s, r in journal.db.execute(
        "SELECT strategy, r_multiple FROM trades WHERE status='closed' AND r_multiple IS NOT NULL AND closed <= ? "
        "ORDER BY closed", (trade["closed"],)) if _fam(s) == fam]
    if not rs:
        return {"strategy": fam, "trades": 0}
    a = np.array(rs)
    return {"strategy": fam, "trades": len(a), "avg_r": round(float(a.mean()), 3), "win_rate": round(float((a > 0).mean()), 2),
            "total_r": round(float(a.sum()), 2)}


def facts_of(journal, trade: dict) -> dict:
    ev = json.loads(trade.get("events") or "[]")
    keep = [{"ts": str(e.get("ts", ""))[11:16], "what": e.get("kind") or e.get("event"),
             **{k: e[k] for k in ("price", "r", "why", "stop") if k in e}} for e in ev][:14]
    return {"symbol": trade["symbol"], "side": trade["side"], "strategy": trade["strategy"],
            "opened": trade["opened"], "closed": trade["closed"], "r": trade["r_multiple"],
            "mfe_r": trade.get("mfe_r"), "mae_r": trade.get("mae_r"), "exit": trade.get("exit_reason"),
            "adds": trade.get("adds"), "bias_mode": trade.get("bias_mode"), "setup": (trade.get("reason") or "")[:200],
            "jev_grade": trade.get("jev_quality"), "jev_source": trade.get("jev_source"), "events": keep,
            "record_at_close": record_at(journal, trade)}


def plain(f: dict) -> str:
    """The no-key lesson: the same three points, from the numbers alone."""
    r, mfe, mae = f["r"] or 0.0, f.get("mfe_r"), f.get("mae_r")
    how = EXITS.get(f.get("exit") or "", f"exited ({(f.get('exit') or 'unknown').replace('_', ' ')})")
    s1 = f"{f['side'].title()} {f['symbol']} {how} at {r:+.2f}R"
    if mfe is not None and mae is not None:
        s1 += f", after going {mfe:+.2f}R for it and {mae:+.2f}R against it"
    s1 += "."
    s2 = ""
    if mfe is not None and mfe >= 0.8 and r < 0.2:
        s2 = f" It was up {mfe:.2f}R before giving it back, so the exit, not the entry, decided this one."
    elif mae is not None and r > 0 and mae <= -0.7:
        s2 = f" It came within {abs(mae):.2f}R of the stop before working, so it was closer to a loss than the result shows."
    rec = f["record_at_close"]
    if rec.get("trades"):
        s3 = (f" {rec['strategy']} now has {rec['trades']} trades at {rec['avg_r']:+.3f}R on average; "
              + ("one trade doesn't change that." if rec["trades"] >= 30 else "still too few to say anything about its edge."))
    else:
        s3 = ""
    return (s1 + s2 + s3).strip()


class LessonWriter:
    """Writes the missing lessons for the practice account, a few at a time. Never blocks or touches trading."""

    def __init__(self, main) -> None:
        self.main = main
        cfg = main.cfg.get("dashboard") or {}
        self.on = bool(cfg.get("lessons", True)) and main.journal is not None
        self.model = cfg.get("lesson_model") or cfg.get("ask_model") or "claude-sonnet-5-5"
        self.days = int(cfg.get("lesson_days", 14))            # no back-fill of old history: cost, and it's old news
        self.per_hour = int(cfg.get("lessons_per_hour", 20))
        self.calls: list[float] = []
        if self.on:
            ensure(main.journal)

    @property
    def key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")

    def missing(self, limit: int = 5) -> list[dict]:
        j = self.main.journal
        now = self.main.state.now
        since = (now - __import__("pandas").Timedelta(days=self.days)).isoformat() if now is not None else ""
        rows = j.db.execute("SELECT t.* FROM trades t LEFT JOIN lessons l ON l.trade_id = t.id WHERE t.status='closed' "
                            "AND t.r_multiple IS NOT NULL AND t.closed >= ? AND l.trade_id IS NULL ORDER BY t.closed LIMIT ?",
                            (since, limit)).fetchall()
        return [dict(r) for r in rows]

    async def _claude(self, f: dict) -> str | None:
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 3600]
        if not self.key or len(self.calls) >= self.per_hour:
            return None
        self.calls.append(now)
        import httpx
        async with httpx.AsyncClient(timeout=45) as cl:
            r = await cl.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": self.model, "max_tokens": 1500, "system": SYSTEM,
                                    "messages": [{"role": "user", "content": "FACTS:\n" + json.dumps(f, default=str)}]})
        if r.status_code != 200:
            log.warning("lesson: Claude HTTP %s", r.status_code)
            return None
        body = r.json()
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text").strip()
        return text or None

    async def write(self, trade: dict) -> dict:
        j = self.main.journal
        f = facts_of(j, trade)
        text, source, model = None, "rules", None
        try:
            text = await self._claude(f)
            if text:
                source, model = "claude", self.model
        except Exception as e:  # noqa: BLE001 — a lesson is never worth an error anywhere else
            log.warning("lesson %s: %s", trade["id"], e)
        if not text:
            text = plain(f)
        ts = self.main.state.now.isoformat(timespec="seconds") if self.main.state.now is not None else None
        j.db.execute("INSERT OR IGNORE INTO lessons(trade_id, ts, text, source, model, facts) VALUES(?,?,?,?,?,?)",
                     (trade["id"], ts, text, source, model, json.dumps(f, default=str)))
        j.db.commit()
        return {"trade_id": trade["id"], "text": text, "source": source}

    async def pass_once(self) -> int:
        if not self.on:
            return 0
        n = 0
        for t in self.missing():
            await self.write(t)
            n += 1
        return n

    async def run(self, every_s: int = 120) -> None:
        while True:
            try:
                await self.pass_once()
            except Exception as e:  # noqa: BLE001
                log.warning("lessons pass: %s", e)
            await asyncio.sleep(every_s)


def lesson_of(journal, trade_id: str) -> dict | None:
    try:
        r = journal.db.execute("SELECT text, source, ts FROM lessons WHERE trade_id=?", (trade_id,)).fetchone()
    except Exception:  # noqa: BLE001 — no table yet (shadow books never get one)
        return None
    return dict(r) if r else None


def lessons_for(journal, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    try:
        q = f"SELECT trade_id, text FROM lessons WHERE trade_id IN ({','.join('?' * len(ids))})"
        return {r[0]: r[1] for r in journal.db.execute(q, ids)}
    except Exception:  # noqa: BLE001
        return {}
