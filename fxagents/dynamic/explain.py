"""Why did the reviewers say what they said? (Oct 27 2026, Sam: "I would like the reasoning as to why they said wait.")

Reads the journal only (no API call, no network) and writes, for every reviewed trade of a book (live and past/backfill
reviews, labelled), each reviewer's answer in full: action, the trigger it was waiting for, what would invalidate the
entry, its decisive evidence, the conflicting evidence and the data it said was missing — next to what the trade then
did. Then a summary: per reviewer, how often it said ENTER / WAIT / CANCEL, the WAIT triggers with counts, and what the
WAITs and ENTERs were worth (R of the trades). When post-mortems exist (./fx.sh dynpostmortem) they are added per trade
and summarised (alternative per reviewer, rules proposed) — labelled hindsight: hypotheses to test, not evidence.

    python -m fxagents.dynamic.explain --book live
    ./fx.sh dynexplain [book=live]   → data/year_test/dynamic_explain/report.md
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from . import store
from .providers import PROMPT_VERSION

OUT = Path("data/year_test/dynamic_explain")
NAMES = {"claude": "Claude", "openai": "OpenAI"}


def _has(journal, table: str) -> bool:
    return journal.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def trades(journal) -> list[dict]:
    """Reviewed trades (a dyn_candidates row), closed or still open, newest entry first."""
    if not _has(journal, "dyn_candidates"):
        return []
    rows = [dict(r) for r in journal.db.execute(
        "SELECT t.id, t.symbol, t.side, t.strategy, t.status, t.opened, t.closed, t.entry, t.initial_stop, t.exit_price, "
        "t.exit_reason, t.r_multiple, t.mfe_r, t.mae_r, c.source, c.status AS review_status, c.exchange_status, "
        "c.exchange_decision FROM dyn_candidates c JOIN trades t ON t.id = c.candidate_id")]
    rows.sort(key=lambda r: pd.Timestamp(r["opened"]).tz_convert("UTC") if r["opened"] else pd.Timestamp(0, tz="UTC"), reverse=True)
    return rows


def postmortems(journal) -> dict[str, dict[str, dict]]:
    if not _has(journal, "dyn_postmortems"):
        return {}
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in journal.db.execute("SELECT * FROM dyn_postmortems ORDER BY id"):
        out[r["candidate_id"]][r["provider"]] = dict(r)
    return out


def _r(x) -> str:
    return "open" if x is None else f"{x:+.2f}R"


def _ny(ts, tz) -> str:
    return pd.Timestamp(ts).tz_convert(tz).strftime("%Y-%m-%d %H:%M") if ts else "?"


def _line(text) -> str:
    return " ".join(str(text or "—").split())


def answer_md(rv: dict) -> list[str]:
    who = NAMES.get(rv["provider"], rv["provider"])
    rnd = "" if (rv.get("round") or 1) == 1 else " (after the exchange)"
    if rv["action"] not in ("ENTER", "WAIT", "CANCEL"):
        return [f"- **{who}{rnd}: no answer** ({rv['action']}: {_line(rv.get('error'))[:200]})"]
    out = [f"- **{who}{rnd}: {rv['action']}**"]
    if rv["action"] == "WAIT":
        out.append(f"  - waiting for: `{rv.get('trigger_id') or 'no trigger named'}`; gives up if: `{rv.get('invalidation_id') or '—'}`")
    elif rv.get("trigger_id") or rv.get("invalidation_id"):
        out.append(f"  - trigger `{rv.get('trigger_id') or '—'}`, invalidation `{rv.get('invalidation_id') or '—'}`")
    out.append(f"  - decisive evidence: {_line(rv.get('evidence'))}")
    out.append(f"  - against it: {_line(rv.get('conflicting'))}")
    if rv.get("missing"):
        out.append(f"  - missing data: {'; '.join(_line(m) for m in rv['missing'])}")
    if (rv.get("round") or 1) == 2 and rv.get("changed"):
        out.append(f"  - changed its answer because: {_line(rv.get('why_changed'))}")
    return out


def pm_md(pm: dict) -> list[str]:
    who = NAMES.get(pm["provider"], pm["provider"])
    if pm.get("error"):
        return [f"- {who}: no post-mortem ({_line(pm['error'])[:200]})"]
    vis = "yes — " + _line(pm["visible_evidence"]) if pm["visible_at_entry"] else "no (only visible afterwards)"
    return [f"- **{who}** — verdict on the entry: `{pm['entry_review_verdict']}`; alternative: `{pm['alternative_action']}`",
            f"  - why it lost: {_line(pm['why_lost'])}",
            f"  - warning sign in the packet at entry: {vis}",
            f"  - rule it would test: {_line(pm['alternative_rule'])}",
            f"  - lesson: {_line(pm['lesson'])}"]


def summary(rows: list[dict], revs: dict[str, list[dict]]) -> list[str]:
    acts: dict[str, Counter] = defaultdict(Counter)
    trig: dict[str, Counter] = defaultdict(Counter)
    inval: dict[str, Counter] = defaultdict(Counter)
    r_by: dict[tuple, list] = defaultdict(list)
    losers_enter: Counter = Counter()
    n_losers = sum(1 for t in rows if t["r_multiple"] is not None and t["r_multiple"] < 0)
    for t in rows:
        for rv in revs[t["id"]]:
            if (rv.get("round") or 1) != 1:
                continue
            p, a = rv["provider"], rv["action"]
            a = a if a in ("ENTER", "WAIT", "CANCEL") else "no answer"
            acts[p][a] += 1
            if a == "WAIT":
                trig[p][rv.get("trigger_id") or "(none named)"] += 1
                inval[p][rv.get("invalidation_id") or "(none named)"] += 1
            if t["r_multiple"] is not None:
                r_by[(p, a)].append(t["r_multiple"])
                if a == "ENTER" and t["r_multiple"] < 0:
                    losers_enter[p] += 1
    out = ["## Summary (round 1, the sealed answers)", "",
           "| reviewer | ENTER | WAIT | CANCEL | no answer | R of the trades it said ENTER on | R of its WAIT trades (what waiting skipped) | R of its CANCEL trades | losers it said ENTER on |",
           "|---|---|---|---|---|---|---|---|---|"]
    for p in sorted(acts):
        c = acts[p]
        s = {a: r_by[(p, a)] for a in ("ENTER", "WAIT", "CANCEL")}
        cell = lambda v: f"{sum(v):+.2f}R on {len(v)} ({sum(1 for x in v if x > 0)} won)" if v else "—"  # noqa: E731
        out.append(f"| {NAMES.get(p, p)} | {c['ENTER']} | {c['WAIT']} | {c['CANCEL']} | {c['no answer']} | {cell(s['ENTER'])} | "
                   f"{cell(s['WAIT'])} | {cell(s['CANCEL'])} | {losers_enter[p]} of {n_losers} |")
    out += ["", "A WAIT trade's R is what the trade did when the bot entered anyway: positive means waiting would have skipped a winner "
            "(milestone 1 scores WAIT as a skip; it does not yet simulate entering on the trigger).", ""]
    for p in sorted(trig):
        out.append(f"**{NAMES.get(p, p)} — what its WAITs were waiting for:** "
                   + ", ".join(f"`{k}` × {v}" for k, v in trig[p].most_common())
                   + "; gave up if: " + ", ".join(f"`{k}` × {v}" for k, v in inval[p].most_common()))
        out.append("")
    return out


def pm_summary(rows: list[dict], pms: dict) -> list[str]:
    have = [(t, pms[t["id"]]) for t in rows if t["id"] in pms]
    if not have:
        return []
    alt: dict[str, Counter] = defaultdict(Counter)
    ver: dict[str, Counter] = defaultdict(Counter)
    vis: dict[str, Counter] = defaultdict(Counter)
    rules = []
    for t, by in have:
        for p, pm in by.items():
            if pm.get("error"):
                continue
            alt[p][pm["alternative_action"]] += 1
            ver[p][pm["entry_review_verdict"]] += 1
            vis[p]["visible at entry" if pm["visible_at_entry"] else "only afterwards"] += 1
            rules.append((p, t, pm))
    out = ["## Post-mortems of the losing trades — HINDSIGHT, hypotheses only", "",
           f"{len(have)} losing trade(s) have a post-mortem. The reviewers saw how the trade ended, so this is not evidence: a rule from here",
           "is a candidate for the research loop and must pass the usual tests (>= 100 trades, 95% range above 0, both halves, 2x costs,",
           "controls, look-ahead audit) on data it was not drawn from before it can touch trading.", "",
           "| reviewer | alternative it would use | verdict on the entry | warning sign at entry? |", "|---|---|---|---|"]
    for p in sorted(alt):
        f = lambda c: ", ".join(f"{k} × {v}" for k, v in c.most_common())  # noqa: E731
        out.append(f"| {NAMES.get(p, p)} | {f(alt[p])} | {f(ver[p])} | {f(vis[p])} |")
    out += ["", "### Rules they proposed (one per trade per reviewer)", ""]
    for p, t, pm in sorted(rules, key=lambda x: (x[0], x[2]["alternative_action"])):
        out.append(f"- {NAMES.get(p, p)}, `{pm['alternative_action']}` ({t['symbol']} {t['side']} {_r(t['r_multiple'])}): {_line(pm['alternative_rule'])}")
    return out + [""]


def report(journal, cfg, book: str, only: str | None = None) -> str:
    tz = cfg["timezone"]
    store.ensure_schema(journal)
    rows = trades(journal)
    if only:
        rows = [t for t in rows if t["source"] == only]
    revs = {t["id"]: store.reviews_for(journal, t["id"]) for t in rows}
    pms = postmortems(journal)
    n_live = sum(1 for t in rows if t["source"] == "live")
    out = [f"# Why the reviewers said what they said — book {book}", "",
           f"{len(rows)} reviewed trade(s): {n_live} live, {len(rows) - n_live} past trades reviewed afterwards (backfill). "
           f"Prompt {PROMPT_VERSION}. Read from the journal only; no model was called to make this report.", "",
           "The reasons are the reviewers' own words at the entry minute, from the packet they were shown (closed candles, bias, levels, "
           "spread, next release). They are explanations a model gave, not proof of why price moved.", ""]
    if not rows:
        return "\n".join(out + ["Nothing reviewed yet."]) + "\n"
    out += summary(rows, revs)
    out += pm_summary(rows, pms)
    out += ["## Trade by trade (newest entry first)", ""]
    for t in rows:
        src = "live review" if t["source"] == "live" else "past trade, reviewed afterwards"
        out.append(f"### {t['symbol']} {t['side']} {t['strategy']} — opened {_ny(t['opened'], tz)} NY — {_r(t['r_multiple'])} ({src})")
        out.append("")
        if t["r_multiple"] is not None:
            mfe = f"{t['mfe_r']:+.2f}R" if t["mfe_r"] is not None else "?"
            mae = f"{t['mae_r']:+.2f}R" if t["mae_r"] is not None else "?"
            out.append(f"Outcome: exit `{t['exit_reason'] or '?'}` at {_ny(t['closed'], tz)} NY; best {mfe}, worst {mae}. "
                       f"Entry {t['entry']}, stop {t['initial_stop']}, exit {t['exit_price']}.")
        if t.get("exchange_status"):
            out.append(f"Exchange: {t['exchange_status']}" + (f" → {t['exchange_decision']}" if t.get("exchange_decision") else ""))
        out.append("")
        rv = sorted(revs[t["id"]], key=lambda r: ((r.get("round") or 1), r["provider"]))
        out += [x for r in rv for x in answer_md(r)] or ["- no review rows"]
        if t["id"] in pms:
            out += ["", "Post-mortem (hindsight):"] + [x for p in sorted(pms[t["id"]]) for x in pm_md(pms[t["id"]][p])]
        out.append("")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The reviewers' reasons, trade by trade, from the journal (no API calls)")
    ap.add_argument("--book", default="live")
    ap.add_argument("--source", choices=["live", "backfill"], default=None, help="only live or only past-trade reviews")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    from ..config import load_config
    from ..journal import Journal
    from . import score
    cfg = load_config(a.config)
    path = score.journal_path(cfg, a.book)
    if not Path(path).exists():
        print(f"no journal for book {a.book!r} at {path}")
        return 1
    txt = report(Journal(path), cfg, a.book, a.source)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(txt)
    print(txt[:4000])
    print(f"... wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
