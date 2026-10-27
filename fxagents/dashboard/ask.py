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

import logging

import pandas as pd

log = logging.getLogger("ask")

SYMS = {"XAUUSD": r"gold|xau", "NDQ": r"nasdaq|ndq|nq|nas100|us100", "US30": r"us30|dow|dji|ym"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SYSTEM = (
    "You are FX-Agents, Sam's automated trading bot, explaining your own decisions to him. Answer ONLY from the FACTS "
    "JSON (your journals and live state). If the facts don't cover the question, say so plainly and say what would. "
    "Be brief and concrete: lead with the answer in one or two sentences, then at most a few short bullet points with "
    "times (New York) and numbers. Explain jargon in plain words. Never give financial advice, never suggest changing "
    "risk or going live, and never invent trades, prices or reasons. R = profit or loss in units of the risk taken. "
    "A ghost trade is a setup the bot passed on, played out with a fixed yardstick exit (stop, 1.5R target or 4 hours). "
    "For 'best/worst so far' questions use record_by_instrument_and_strategy, and say how many trades stand behind a "
    "number: under ~30 trades a result is mostly luck. A trade's 'lesson' is a short note written after it closed; "
    "quote it when asked why a trade went as it did, but one trade never proves a rule. 'jev_fallbacks' lists Jev "
    "calls that failed or came back unreadable: those were answered by a rule-based stand-in, which never passes a Jev "
    "gate — mention them when asked about Jev or about a skipped setup. 'm15_candle_against_entry' (1 yes, 0 no, null unknown) "
    "is a shadow tag only: it was not confirmed and never decides a trade. 'shadow_reviews' on a trade are what a Claude "
    "and an OpenAI reviewer said (ENTER / WAIT / CANCEL, or ABSTAIN when they failed) about the entry from the data known "
    "then; they decide nothing and are being scored, so report them as opinions, never as the reason a trade was taken. Each reviewer has a round 1 (alone) and, when both answered, a round 2 "
    "after seeing the other's round-1 answer ('round', 'changed', 'why_changed'; 'shadow_exchange' has the decision rule's verdict: "
    "enter / wait / cancel, and the exchange time in ms, or why no exchange ran). "
    "Keep the whole answer under 180 words.")


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


def by_sym_strat(journal, syms: list[str]) -> list[dict]:
    """Every closed trade of a book, grouped by instrument × strategy family (all time): trades, win rate, avg/total R."""
    q = "SELECT symbol, strategy, r_multiple FROM trades WHERE status='closed' AND r_multiple IS NOT NULL"
    args: list = []
    if syms:
        q += f" AND symbol IN ({','.join('?' * len(syms))})"; args += syms
    acc: dict[tuple, list] = {}
    for sym, strat, r in journal.db.execute(q, args):
        fam = (strat or "").split(":")[0].split("@")[0]
        tf = (strat or "").split(":")[1].split("@")[0] if ":" in (strat or "") else ""
        acc.setdefault((sym, fam, tf), []).append(float(r))
    out = [{"symbol": k[0], "strategy": k[1], "timeframe": k[2], "trades": len(v), "win_rate": round(sum(x > 0 for x in v) / len(v), 2),
            "avg_r": round(sum(v) / len(v), 3), "total_r": round(sum(v), 2)} for k, v in acc.items()]
    return sorted(out, key=lambda x: -x["total_r"])[:40]


def jev_fallbacks(journal, a: str, b: str) -> list[dict]:
    """Jev calls in the window that fell back (failure or unreadable answer), by kind: count and the latest reason."""
    try:
        rows = journal.db.execute("SELECT kind, symbol, ts, error FROM decisions WHERE ts >= ? AND ts <= ? AND error IS NOT NULL "
                                  "ORDER BY ts", (a, b)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    out: dict[str, dict] = {}
    for kind, sym, ts, err in rows:
        d = out.setdefault(kind, {"kind": kind, "count": 0, "unreadable": 0})
        d["count"] += 1
        d["unreadable"] += str(err).startswith("unreadable")
        d.update(last_ts=ts, last_symbol=sym, last_error=err)
    return list(out.values())


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
        q = "SELECT id, symbol, strategy, side, opened, closed, r_multiple, realized, exit_reason, jev_quality, reason, m15_live AS m15_candle_against_entry FROM trades WHERE opened >= ? AND opened <= ?"
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
            "filter_scorecard": ({"taken": sc["taken"], "filters": sc["filters"][:8]} if sc else None),
            # always there, whatever the window: "the last NDQ trade", "how did this week go"
            "latest_trades": [dict(r) for r in c.journal.db.execute(
                "SELECT id, symbol, side, strategy, opened, closed, r_multiple, realized, exit_reason, jev_quality, reason, notes, "
                "m15_live AS m15_candle_against_entry "
                "FROM trades WHERE status='closed'" + (f" AND symbol IN ({','.join('?' * len(syms))})" if syms else "")
                + " ORDER BY closed DESC LIMIT 8", syms or [])],
            "last_7_days": [{"date": d, **v} for d, v in list(c.journal.daily().items())[-7:]],
            "record_by_instrument_and_strategy": by_sym_strat(c.journal, syms)}
    if "live" in per_book:                   # lessons exist for the practice account only
        from .lessons import lessons_for
        L = per_book["live"]
        ids = [t["id"] for t in L["trades_in_window"] + L["latest_trades"] if t.get("id")]
        got = lessons_for(main.journal, ids)
        for t in L["trades_in_window"] + L["latest_trades"]:
            if t.get("id") in got:
                t["lesson"] = got[t["id"]]
    from ..dynamic.store import exchange_for, reviews_for
    for key, c in books_of(main):               # shadow reviews of the trades listed (reading only)
        b = per_book.get(key)
        if not b:
            continue
        for t in b["trades_in_window"] + b["latest_trades"]:
            if t.get("id"):
                rv = reviews_for(c.journal, t["id"])
                if rv:
                    t["shadow_reviews"] = [{k: x.get(k) for k in ("provider", "round", "action", "trigger_id", "evidence", "conflicting", "changed", "why_changed", "latency_ms", "error")}
                                           for x in rv]
                    xc = exchange_for(c.journal, t["id"])
                    if xc:
                        t["shadow_exchange"] = xc
    facts["books"] = per_book
    facts["jev_fallbacks"] = jev_fallbacks(main.journal, sa, sb)
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
    return "\n".join(out)


def _err(r) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:160] or r.reason_phrase
    except Exception:  # noqa: BLE001
        return getattr(r, "reason_phrase", "")


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
            return {"answer": summarize(facts) + "\n(No ANTHROPIC_API_KEY in the bot's environment, so this is the raw record.)",
                    "source": "facts", "facts": facts}
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
                                  json={"model": self.model, "max_tokens": 4000, "system": SYSTEM, "messages": msgs})
            if r.status_code != 200:
                log.warning("ask: Claude HTTP %s: %s", r.status_code, r.text[:300])
                return {"answer": f"I couldn't reach Claude (HTTP {r.status_code}: {_err(r)}). Here's what the records say:\n\n"
                        + summarize(facts), "source": "facts", "facts": facts}
            body = r.json()
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text").strip()
            stop = body.get("stop_reason")
            if not text:
                log.warning("ask: Claude returned no text (stop_reason=%s)", stop)
                return {"answer": f"Claude returned no answer (stop reason: {stop}). Here's what the records say:\n\n"
                        + summarize(facts), "source": "facts", "facts": facts}
            if stop == "max_tokens":
                text += " …"
            return {"answer": text, "source": "claude", "facts": facts}
        except Exception as e:  # noqa: BLE001
            return {"answer": f"I couldn't reach Claude ({type(e).__name__}). Here's what the records say:\n\n" + summarize(facts),
                    "source": "facts", "facts": facts}
        finally:
            self.busy = False

    async def narrate(self, rc: dict) -> dict:
        """Evening recap: Claude rewrites the day's numbers as a ~60-second spoken script (facts only). Falls back
        to the plain script when there is no key, the hourly cap is reached, or the call fails."""
        if not self.key:
            return {"script": rc["script"], "source": "facts"}
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 3600]
        if len(self.calls) >= self.max_per_hour:
            return {"script": rc["script"], "source": "facts"}
        self.calls.append(now)
        sysmsg = ("You are FX-Agents, Sam's trading bot, giving him a spoken end-of-day recap. Use ONLY the FACTS. "
                  "About 120-150 words, plain spoken English, no bullet points, no markdown, no advice. Numbers rounded "
                  "for speech (say 'plus one point four R'). Lead with the practice account, then anything notable in "
                  "the paper books and the filters (ghost results are a yardstick, not real trades). End with what's "
                  "still open, if anything.")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=45) as cl:
                r = await cl.post("https://api.anthropic.com/v1/messages",
                                  headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                  json={"model": self.model, "max_tokens": 2500, "system": sysmsg,
                                        "messages": [{"role": "user", "content": "FACTS:\n" + json.dumps(rc, default=str)[:30000]}]})
            if r.status_code == 200:
                text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
                if text:
                    return {"script": text, "source": "claude"}
        except Exception:  # noqa: BLE001
            pass
        return {"script": rc["script"], "source": "facts"}
