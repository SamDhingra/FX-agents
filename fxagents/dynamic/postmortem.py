"""Post-mortems of losing trades by both reviewers (Oct 27 2026, Sam: "why did they say WAIT, and what other strategy
would they use for the losing trades?").

For each reviewed trade that closed with a loss (r_multiple < 0) and has no post-mortem yet, both models get:
  * the PACKET they reviewed at entry (exactly what was known then; stored in dyn_candidates),
  * THEIR OWN entry review (action, trigger, invalidation, decisive / conflicting evidence, missing data),
  * WHAT HAPPENED: exit reason, R, how far it went for and against (mfe_r / mae_r), hold time, and the 15-minute
    candles from the entry to 30 minutes after the exit (OANDA mid prices).
and answer, structured: why it lost; whether a warning sign was visible in the packet AT ENTRY (with the numbers) or
only afterwards; whether entering was reasonable on the packet alone; ONE alternative from a fixed menu; ONE concrete,
testable rule that decides with information available at the moment of decision (never the outcome); one lesson.

This is HINDSIGHT. It is a source of hypotheses for the research loop, never evidence: a rule that comes out of it
still has to pass the usual tests on data it wasn't drawn from. Nothing here touches trading.

    python -m fxagents.dynamic.postmortem --book live --last 10 [--dry-run]
    ./fx.sh dynpostmortem [book=live] [n=10] [dry]   → data/year_test/dynamic_postmortem/report.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

from . import store
from .backfill import entry_minute, fetch_candles
from .providers import build_providers

PM_VERSION = "pm-v1"
MAX_TRADES = 50
MAX_TEXT = 600
PATH_BARS = 40                      # 15m candles after entry shown (10 hours); longer trades are cut, and the cut is stated
OUT = Path("data/year_test/dynamic_postmortem")
ALTERNATIVES = ["skip", "wait_for_m15_turn", "enter_on_retest", "wider_stop", "closer_target", "opposite_direction",
                "higher_timeframe_entry", "other"]
VERDICTS = ["entry_was_reasonable", "should_have_waited", "should_have_cancelled"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dyn_postmortems(
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT, provider TEXT, model TEXT, pm_version TEXT,
  why_lost TEXT, visible_at_entry INTEGER, visible_evidence TEXT, entry_review_verdict TEXT, alternative_action TEXT,
  alternative_rule TEXT, lesson TEXT, error TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, latency_ms REAL,
  ts TEXT, UNIQUE(candidate_id, provider, pm_version));
"""

SYSTEM = f"""You are reviewing a CLOSED, LOSING trade of an automated intraday trading bot after the fact (post-mortem {PM_VERSION}).
The bot trades NAS100 (NDQ), US30 and gold (XAUUSD) on a practice account. You are given three things:
  PACKET: exactly what was known at the entry minute (order, spread cost, higher-timeframe bias, closed M5/M15/H1 candles,
          the forming M15 candle labelled partial, levels, session, next scheduled release, the setup's record).
  YOUR ENTRY REVIEW: what you answered at the entry (ENTER / WAIT / CANCEL and your reasons), or that you gave none.
  WHAT HAPPENED: how the trade ended (exit reason, R, how far it went for and against it, hold time) and the 15-minute
          candles from the entry until 30 minutes after the exit.
Answer honestly and keep hindsight apart from foresight (candidate_id: the CANDIDATE_ID given):
1. why_lost: the mechanism of the loss in plain words, citing numbers (what price did relative to the entry, the stop and
   the levels in the packet).
2. visible_at_entry: true ONLY if a warning sign was in the PACKET at the entry minute. visible_evidence: the packet numbers
   that showed it ('' when false). Something you can see only in WHAT HAPPENED does not count as visible.
3. entry_review_verdict: judging the PACKET alone (not the outcome), was entering reasonable even though it lost (losses
   happen to good entries), or should the bot have waited or cancelled?
4. alternative_action (one of the menu) and alternative_rule: ONE concrete, testable rule, with numbers, that decides using
   only information available at the moment of the decision (at the entry, or later as it happens — never the trade's
   outcome), e.g. "skip shorts when the last two closed M15 candles closed above their open and price is within 0.3 x
   the M15 range of the Asia low". Generic advice ("be careful", "manage risk better") is not acceptable. Prefer a rule
   that would apply to many trades, not one tailored to this loss; one losing trade is not evidence.
5. lesson: one sentence.
Use only the numbers given; do not invent prices or news. Each text field at most {MAX_TEXT} characters.
Return your answer only through the structured output."""


def schema() -> dict:
    """Strict-mode friendly for both providers: all fields required, no length keywords, enums never with a type list."""
    s = {"type": "string"}
    return {"type": "object", "additionalProperties": False,
            "properties": {"candidate_id": s, "why_lost": s, "visible_at_entry": {"type": "boolean"}, "visible_evidence": s,
                           "entry_review_verdict": {"type": "string", "enum": VERDICTS},
                           "alternative_action": {"type": "string", "enum": ALTERNATIVES},
                           "alternative_rule": s, "lesson": s},
            "required": ["candidate_id", "why_lost", "visible_at_entry", "visible_evidence", "entry_review_verdict",
                         "alternative_action", "alternative_rule", "lesson"]}


def ensure(journal) -> None:
    store.ensure_schema(journal)
    journal.db.executescript(SCHEMA_SQL)
    journal.db.commit()


def validate(obj: dict, cid: str) -> tuple[dict | None, str | None]:
    if str(obj.get("candidate_id")) != cid:
        return None, "invalid: candidate_id does not match"
    if obj.get("entry_review_verdict") not in VERDICTS:
        return None, "invalid: entry_review_verdict"
    if obj.get("alternative_action") not in ALTERNATIVES:
        return None, "invalid: alternative_action"
    if not isinstance(obj.get("visible_at_entry"), bool):
        return None, "invalid: visible_at_entry not a boolean"
    out = {k: str(obj.get(k) or "")[:MAX_TEXT] for k in ("why_lost", "visible_evidence", "alternative_rule", "lesson")}
    if not out["why_lost"] or not out["alternative_rule"]:
        return None, "invalid: why_lost or alternative_rule empty"
    return {**out, "visible_at_entry": obj["visible_at_entry"], "entry_review_verdict": obj["entry_review_verdict"],
            "alternative_action": obj["alternative_action"]}, None


def pick(journal, n: int) -> list[dict]:
    """Reviewed (live or backfill), closed, losing trades with a stored packet and no post-mortem yet; newest first."""
    rows = [dict(r) for r in journal.db.execute(
        "SELECT t.*, c.packet AS packet, c.source AS source FROM trades t JOIN dyn_candidates c ON c.candidate_id = t.id "
        "WHERE t.status='closed' AND t.closed IS NOT NULL AND t.r_multiple IS NOT NULL AND t.r_multiple < 0 AND c.packet IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM dyn_postmortems p WHERE p.candidate_id = t.id AND p.pm_version = ? AND p.error IS NULL)",
        (PM_VERSION,))]
    rows.sort(key=lambda r: pd.Timestamp(r["closed"]).tz_convert("UTC"), reverse=True)
    return rows[:n]


def own_review(journal, cid: str, provider: str) -> dict | None:
    r = journal.db.execute("SELECT action, trigger_id, invalidation_id, evidence, conflicting, missing, error FROM dyn_reviews "
                           "WHERE candidate_id=? AND provider=? AND COALESCE(round,1)=1 ORDER BY id DESC LIMIT 1",
                           (cid, provider)).fetchone()
    if r is None:
        return None
    d = dict(r)
    try:
        d["missing"] = json.loads(d["missing"] or "[]")
    except ValueError:
        d["missing"] = []
    return d


def review_text(rv: dict | None) -> str:
    if rv is None:
        return "You gave no review of this entry."
    if rv["action"] not in ("ENTER", "WAIT", "CANCEL"):
        return f"You gave no answer at the entry ({rv['action']}: {rv.get('error') or 'unknown'})."
    return json.dumps({"action": rv["action"], "trigger_id": rv["trigger_id"], "invalidation_id": rv["invalidation_id"],
                       "decisive_evidence": rv["evidence"], "conflicting_evidence": rv["conflicting"],
                       "missing_data": rv["missing"]}, sort_keys=True)


def outcome_block(t: dict, path15: pd.DataFrame, decimals: int, tz: str) -> dict:
    """What happened after the entry. path15: 15m mid candles from the entry to 30 min after the exit."""
    op, cl = pd.Timestamp(t["opened"]), pd.Timestamp(t["closed"])
    rows = [[ts.tz_convert(tz).strftime("%Y-%m-%d %H:%M"), *[round(float(r[k]), decimals) for k in ("open", "high", "low", "close")]]
            for ts, r in path15.iterrows()]
    cut = len(rows) > PATH_BARS
    return {"side": t["side"], "entry": t["entry"], "initial_stop": t.get("initial_stop"), "exit_price": t.get("exit_price"),
            "exit_reason": t.get("exit_reason"), "r_multiple": t["r_multiple"], "mfe_r": t.get("mfe_r"), "mae_r": t.get("mae_r"),
            "opened_ny": op.tz_convert(tz).strftime("%Y-%m-%d %H:%M") if op.tzinfo else str(op),
            "closed_ny": cl.tz_convert(tz).strftime("%Y-%m-%d %H:%M") if cl.tzinfo else str(cl),
            "hold_minutes": round((cl - op).total_seconds() / 60, 1) if op.tzinfo and cl.tzinfo else None,
            "m15_after_entry [start_ny, open, high, low, close]": rows[:PATH_BARS],
            "note": (f"only the first {PATH_BARS} of {len(rows)} 15m candles are shown" if cut else "")}


async def path_after(client, cfg, t: dict) -> pd.DataFrame:
    from ..oanda import _inst
    tz = cfg["timezone"]
    start = entry_minute(t["opened"], tz)
    end = min(pd.Timestamp(t["closed"]).tz_convert(tz) + pd.Timedelta(minutes=30), start + pd.Timedelta(days=2))
    m1 = await fetch_candles(client, _inst(cfg, t["symbol"]), "M1", "M", start, end, tz)
    if not len(m1):
        return m1
    return m1.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def decimals_of(packet: dict) -> int:
    try:
        return int((packet.get("order") or {}).get("price_decimals") or packet.get("price_decimals") or 2)
    except (TypeError, ValueError):
        return 2


async def run(cfg, book: str, n: int, out: Path, dry_run: bool = False, client=None, journal=None, providers=None) -> int:
    from . import score
    if not (1 <= n <= MAX_TRADES):
        print(f"refused: --last must be 1 to {MAX_TRADES}")
        return 2
    dyn = cfg.get("dynamic") or {}
    if journal is None:
        from ..journal import Journal
        path = score.journal_path(cfg, book)
        if not Path(path).exists():
            print(f"no journal for book {book!r} at {path}")
            return 1
        journal = Journal(path)
    ensure(journal)
    providers = providers if providers is not None else build_providers(dyn)
    providers = {k: p for k, p in providers.items() if p.available()}
    if not providers:
        print("no provider configured with its key")
        return 1
    trades = pick(journal, n)
    print(f"Book {book}: {len(trades)} reviewed losing trade(s) without a post-mortem (newest first).")
    for t in trades:
        print(f"  {t['id']}  {t['symbol']:7} {t['side']:5} opened {t['opened']}  R {t['r_multiple']:+.2f}  ({t['source']})")
    est = len(trades) * len(providers) * (5000 * 2.0 + 700 * 10.0) / 1e6
    print(f"Estimated cost: about ${est:.2f} ({len(trades)} trades x {len(providers)} models).")
    if dry_run or not trades:
        print("--dry-run: nothing was called or stored." if dry_run else "nothing to do.")
        return 0
    if client is None:
        from ..oanda import oanda_from_cfg
        from ..reconcile import broker_cfg
        client = oanda_from_cfg(broker_cfg(cfg))
    tz = cfg["timezone"]
    done = []
    try:
        for t in trades:
            packet = json.loads(t["packet"])
            try:
                p15 = await path_after(client, cfg, t)
            except Exception as e:  # noqa: BLE001
                print(f"  {t['id']}: could not fetch the path after entry ({type(e).__name__}: {e}); skipped")
                continue
            what = outcome_block(t, p15, decimals_of(packet), tz)

            async def one(name, prov, t=t, packet=packet, what=what):
                user = (f"CANDIDATE_ID: {t['id']}\n\nPACKET:\n" + json.dumps(packet, sort_keys=True) + "\n\nYOUR ENTRY REVIEW:\n"
                        + review_text(own_review(journal, t["id"], name)) + "\n\nWHAT HAPPENED:\n" + json.dumps(what, default=str))
                res = await prov.ask_json(SYSTEM, user, schema(), name="postmortem", max_tokens=3000)
                clean, err = (validate(res["obj"], t["id"]) if res["obj"] is not None else (None, res["error"]))
                cols = ("why_lost", "visible_at_entry", "visible_evidence", "entry_review_verdict", "alternative_action",
                        "alternative_rule", "lesson")
                vals = [int(clean[k]) if k == "visible_at_entry" else clean[k] for k in cols] if clean else [None] * len(cols)
                journal.db.execute(
                    "INSERT OR REPLACE INTO dyn_postmortems(candidate_id,provider,model,pm_version," + ",".join(cols)
                    + ",error,tokens_in,tokens_out,cost_usd,latency_ms,ts) VALUES(" + ",".join("?" * (len(cols) + 10)) + ")",
                    (t["id"], name, prov.model, PM_VERSION, *vals, None if clean else (err or "no answer"), res["tokens_in"],
                     res["tokens_out"], res["cost_usd"], res["latency_ms"], pd.Timestamp.now(tz).isoformat(timespec="seconds")))
                journal.db.commit()
            await asyncio.gather(*[one(n_, p_) for n_, p_ in providers.items()])
            done.append(t["id"])
            print(f"  {t['id']}: post-mortem done")
    finally:
        aclose = getattr(client, "aclose", None)
        if aclose:
            await aclose()
    from .explain import report
    txt = report(journal, cfg, book, only=None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(txt)
    cost = sum(r[0] or 0 for r in journal.db.execute("SELECT cost_usd FROM dyn_postmortems WHERE candidate_id IN (%s)"
                                                    % ",".join("?" * len(done)), done)) if done else 0.0
    print(f"\n{len(done)} post-mortem(s) written, cost ${cost:.4f}. Wrote {out / 'report.md'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Post-mortems of reviewed losing trades by both reviewers (hindsight; hypotheses only)")
    ap.add_argument("--book", default="live")
    ap.add_argument("--last", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    from ..config import load_config
    cfg = load_config(a.config)
    if cfg.get("broker") == "oanda":
        from ..reconcile import broker_cfg
        cfg = broker_cfg(cfg)
    return asyncio.run(run(cfg, a.book, a.last, Path(a.out), a.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
