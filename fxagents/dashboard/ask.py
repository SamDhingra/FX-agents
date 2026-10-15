"""Ask the bot: a plain-language question about what the bot did, answered from its own records.

  1. gather()  pulls the FACTS that bear on the question from the journals and live state: setups seen around the
               time asked about (with why each was taken or passed), trades, open positions, bias, news, each book's
               evidence and filter scorecard, recent alerts. Times are New York time, like the rest of the app.
  2. answer()  with ANTHROPIC_API_KEY set, Claude writes the answer from those facts only (it is told to say when
               the facts don't cover the question); without a key, a plain summary of the facts is returned.
Read-only. Nothing here can place, change or close a trade. The facts sent are trading records only — no tokens,
account ids or keys.
"""
from __future__ import annotations

import json
import os
import re
import time

import pandas as pd

SYMS = {"XAUUSD": r"gold|xau", "NDQ": r"nasdaq|ndq|nq|nas100|us100", "US30": r"us30|dow|dji|ym"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SYSTEM = (
    "You are FX-Agents, Sam's automated trading bot, explaining your own decisions to him. Answer ONLY from the FACTS "
    "JSON (your journals and live state). If the facts don't cover the question, say so plainly and say what would. "
    "Be brief and concrete: lead with the answer in one or two sentences, then at most a few short bullet points with "
    "times (New York) and numbers. Explain jargon in plain words. Never give financial advice, never suggest changing "
    "risk or going live, and never invent trades, prices or reasons. R = profit or loss in units of the risk taken. "
    "A ghost trade is a setup the bot passed on, played out with a fixed yardstick exit (stop, 1.5R target or 4 hours).")


def when_of(q: str, now: pd.Timestamp) -> tuple[pd.Timestamp | None, pd.Timestamp, pd.Timestamp]:
    """(the moment asked about or None, window start, window end) in NY time."""
    ql = q.lower()
    day = now.normalize()
    if "yesterday" in ql:
        day -= pd.Timedelta(days=1)
    for i, d in enumerate(DAYS):
        if re.search(rf"\b{d}\b", ql):
            back = (now.dayofweek - i) % 7
            day = now.normalize() - pd.Timedelta(days=back or (7 if "last" in ql else 0))
    m = (re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", ql) or re.search(r"\b(\d{1,2})\s*(am|pm)\b", ql)
         or re.search(r"\b(?:at|around|near)\s+(\d{1,2})\b", ql))
    if m:
        g = [x for x in m.groups() if x is not None]
        h = int(g[0])
        mi = int(g[1]) if len(g) > 1 and g[1].isdigit() else 0
        ap = next((x for x in g[1:] if x in ("am", "pm")), None)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if h < 24 and mi < 60:
            t = day + pd.Timedelta(hours=h, minutes=mi)
            return t, t - pd.Timedelta(minutes=30), t + pd.Timedelta(minutes=30)
    if "morning" in ql:
        return None, day + pd.Timedelta(hours=2), day + pd.Timedelta(hours=12)
    if "afternoon" in ql:
        return None, day + pd.Timedelta(hours=12), day + pd.Timedelta(hours=17)
    if "week" in ql:
        return None, day - pd.Timedelta(days=6), now
    return None, day, max(now, day + pd.Timedelta(hours=23, minutes=59))


def symbols_of(q: str) -> list[str]:
    ql = q.lower()
    return [s for s, pat in SYMS.items() if re.search(rf"\b(?:{pat})\b", ql)]


def books_of(main) -> list[tuple[str, object]]:
    return [("live", main)] + list((getattr(main, "shadows", None) or {}).items())


def gather(main, question: str) -> dict:
    from . import ghosts, insights
    st = main.state
    now = pd.Timestamp(st.now) if st.now is not None else pd.Timestamp.now(tz=main.cfg["timezone"])
    if now.tzinfo is None:
        now = now.tz_localize(main.cfg["timezone"])
    at, a, b = when_of(question, now)
    syms = symbols_of(question)
    ql = question.lower()
    wanted = [k for k, _ in books_of(main) if k.replace("_", " ") in ql or k in ql] or None
    facts: dict = {"now_ny": now.isoformat(timespec="minutes"), "asked_about": {
        "moment": at.isoformat(timespec="minutes") if at is not None else None, "from": a.isoformat(timespec="minutes"),
        "to": b.isoformat(timespec="minutes"), "symbols": syms or "all", "books": wanted or "all"}}
    sa, sb = a.isoformat(), b.isoformat()
    per_book = {}
    for key, c in books_of(main):
        if wanted and key not in wanted:
            continue
        q = "SELECT ts, symbol, strategy, side, action, why, quality FROM signals WHERE ts >= ? AND ts <= ?"
        args: list = [sa, sb]
        if syms:
            q += f" AND symbol IN ({','.join('?' * len(syms))})"; args += syms
        sig = [dict(r) for r in c.journal.db.execute(q + " ORDER BY ts LIMIT 80", args)]
        q = "SELECT symbol, strategy, side, opened, closed, r_multiple, realized, exit_reason, jev_quality, reason FROM trades WHERE opened >= ? AND opened <= ?"
        args = [sa, sb]
        if syms:
            q += f" AND symbol IN ({','.join('?' * len(syms))})"; args += syms
        tr = [dict(r) for r in c.journal.db.execute(q + " ORDER BY opened LIMIT 40", args)]
        ev = insights.evidence_rows(c.journal, key)
        try:
            sc = ghosts.scorecard(c)
        except Exception:  # noqa: BLE001
            sc = None
        per_book[key] = {
            "mode": getattr(c, "selection_mode", key),
            "setups_in_window": sig, "trades_in_window": tr,
            "open_positions": [{"symbol": p.symbol, "side": "LONG" if p.side > 0 else "SHORT", "strategy": p.strategy,
                                "opened": str(p.opened_ts), "r_now": round(p.r_now(p.last_price or p.entry), 2)}
                               for p in c.state.positions.values() if p.status == "open"],
            "record": {k: ev[k] for k in ("n", "avg_r", "sum_r", "win", "ci", "verdict")},
            "strategies": ev["strategies"][:8],
            "filter_scorecard": ({"taken": sc["taken"], "filters": sc["filters"][:8]} if sc else None)}
    facts["books"] = per_book
    facts["live_state"] = {"entries_enabled": st.trading_enabled, "halt_reason": st.halt_reason or None,
                           "news_blackout": st.news_block, "bias": {s: {k: (st.bias.get(s) or {}).get(k) for k in ("state", "score", "d", "h4", "h1")}
                                                                     for s in (syms or list(main.cfg["instruments"]))},
                           "entry_windows_ny": main.cfg["sessions"].get("entry_windows"),
                           "flatten_ny": main.cfg["sessions"].get("flatten_at")}
    facts["news"] = [{"title": e.get("title"), "tier": e.get("tier"), "ts": str(e.get("ts")), "minutes_to": e.get("minutes_to")}
                     for e in (st.news or [])[:8]]
    facts["recent_alerts"] = [x.get("msg") for x in list(st.alerts)[:10]]
    return facts


def summarize(facts: dict) -> str:
    """No-LLM answer: the facts in a few plain lines."""
    out = []
    A = facts["asked_about"]
    out.append(f"From {A['from'][11:16]} to {A['to'][11:16]} NY ({A['from'][:10]}):")
    for k, b in facts["books"].items():
        sig = b["setups_in_window"]
        taken = [s for s in sig if s["action"] == "taken"]
        passed = [s for s in sig if s["action"] != "taken"]
        line = f"• {k}: {len(sig)} setup(s) seen, {len(taken)} taken"
        if passed:
            reasons: dict[str, int] = {}
            for s in passed:
                r = (s.get("why") or s["action"]).split("(")[0].strip()[:70]
                reasons[r] = reasons.get(r, 0) + 1
            line += "; passed because " + "; ".join(f"{r} ×{n}" for r, n in sorted(reasons.items(), key=lambda x: -x[1])[:4])
        if b["trades_in_window"]:
            line += "; trades: " + ", ".join(f"{t['symbol']} {t['side']} {t['r_multiple'] if t['r_multiple'] is not None else 'open'}R"
                                             for t in b["trades_in_window"][:5])
        out.append(line)
    if not facts["live_state"]["entries_enabled"]:
        out.append(f"Entries are paused: {facts['live_state']['halt_reason']}.")
    out.append("(Set ANTHROPIC_API_KEY in .env for full answers in plain language.)")
    return "\n".join(out)


class Asker:
    def __init__(self, main) -> None:
        self.main = main
        cfg = (main.cfg.get("dashboard") or {})
        self.model = cfg.get("ask_model") or "claude-sonnet-5-5"
        self.max_per_hour = int(cfg.get("ask_per_hour", 30))
        self.calls: list[float] = []
        self.busy = False

    @property
    def key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")

    async def answer(self, question: str, history: list[dict] | None = None) -> dict:
        question = (question or "").strip()[:500]
        if not question:
            return {"answer": "Ask me about a trade, a time, a book or a filter.", "source": "none", "facts": None}
        facts = gather(self.main, question)
        if not self.key:
            return {"answer": summarize(facts), "source": "facts", "facts": facts}
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 3600]
        if len(self.calls) >= self.max_per_hour or self.busy:
            return {"answer": "I'm answering too many questions right now — try again in a minute.\n\n" + summarize(facts),
                    "source": "facts", "facts": facts}
        self.calls.append(now)
        self.busy = True
        try:
            import httpx
            msgs = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in (history or [])[-6:]
                    if m.get("role") in ("user", "assistant")]
            msgs.append({"role": "user", "content": f"FACTS:\n{json.dumps(facts, default=str)[:60000]}\n\nQUESTION: {question}"})
            async with httpx.AsyncClient(timeout=45) as cl:
                r = await cl.post("https://api.anthropic.com/v1/messages",
                                  headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                  json={"model": self.model, "max_tokens": 700, "system": SYSTEM, "messages": msgs})
            if r.status_code != 200:
                return {"answer": f"I couldn't reach Claude ({r.status_code}). Here's what the records say:\n\n" + summarize(facts),
                        "source": "facts", "facts": facts}
            text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
            return {"answer": text or summarize(facts), "source": "claude", "facts": facts}
        except Exception as e:  # noqa: BLE001
            return {"answer": f"I couldn't reach Claude ({type(e).__name__}). Here's what the records say:\n\n" + summarize(facts),
                    "source": "facts", "facts": facts}
        finally:
            self.busy = False
