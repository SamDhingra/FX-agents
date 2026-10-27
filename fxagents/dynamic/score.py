"""Scorecard for the shadow review gate (Oct 26 2026, docs/dynamic_controller.md, "Scoring" and "Decision rule").

Milestone 1 policy: a review is a SKIP gate. Per closed trade the arms are
  A  every entry taken (the trade's actual R)             B  actual R if OpenAI said ENTER, else 0
  C  actual R if Claude said ENTER, else 0                D  actual R if both said ENTER, else 0
WAIT and CANCEL both mean "skipped" here (WAIT's trigger is logged for milestone 2); ABSTAIN (late, invalid, refused,
no key, HTTP error) and `not_reviewed: budget` are skipped too and counted separately. Only closed trades are scored.
Reported per arm: candidates, entered, skipped, total R, R per candidate, avoided losers / missed winners, API cost
(USD, and in R using each trade's own risk in USD: the bot books everything in USD), latency p50 / p95 / max and the
share of candidates with a valid answer within 30 s; per symbol; and the paired difference to A (net of the API cost)
with a circular 5-weekday block bootstrap once an arm has >= 30 reviewed closed trades (the blocks of
fxagents/whatif_judge.py). The decision rule is only reported, never applied: >= 100 reviewed closed trades, the 95%
range of the net improvement above 0, and >= 95% of candidates answered within 30 s. Rows are separated by prompt
version: results are never pooled across versions.

    python -m fxagents.dynamic.score [--books live,playbook]   ->  data/year_test/dynamic_review/{report.md,summary.json}
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .providers import PROMPT_VERSION

NY = "America/New_York"
ARMS = {"A": (), "B": ("openai",), "C": ("claude",), "D": ("openai", "claude")}
ARM_NAME = {"A": "every entry taken", "B": "OpenAI", "C": "Claude", "D": "both say ENTER"}
ANSWERS = ("ENTER", "WAIT", "CANCEL")
DRAWS, SEED, BLOCK, MIN_BOOT, RULE_N, RULE_SHARE, LIVE_S = 10_000, 20261026, 5, 30, 100, 0.95, 30.0


# ── reading the journal ───────────────────────────────────────────────────────────────────────────
class ReadOnly:
    """A read-only handle on a journal file (the report must never write to the bot's database)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row


def _day_ny(ts_utc: str) -> str:
    return str(pd.Timestamp(ts_utc, tz="UTC").tz_convert(NY).date())


def collect(journal, cfg, book: str, version: str = PROMPT_VERSION) -> list[dict]:
    """One row per closed, reviewed-or-not candidate of this prompt version: its trade result and each provider's review."""
    try:
        cands = [dict(r) for r in journal.db.execute(
            "SELECT c.candidate_id, c.symbol, c.strategy, c.ts, t.r_multiple r, t.qty_initial q, t.entry e, t.initial_stop s, "
            "t.realized pnl FROM dyn_candidates c JOIN trades t ON t.id=c.candidate_id "
            "WHERE c.prompt_version=? AND t.status='closed' AND t.r_multiple IS NOT NULL ORDER BY c.ts", (version,))]
        revs = [dict(r) for r in journal.db.execute(
            "SELECT candidate_id, provider, model, action, latency_ms, cost_usd, tokens_in, tokens_out, called, error "
            "FROM dyn_reviews WHERE prompt_version=?", (version,))]
    except sqlite3.OperationalError:          # no review tables yet
        return []
    by: dict[str, dict] = {}
    for v in revs:
        by.setdefault(v["candidate_id"], {})[v["provider"]] = v
    rows = []
    for c in cands:
        try:
            mult = float(cfg["instruments"][c["symbol"]]["multiplier"])
            risk = float(c["q"]) * abs(float(c["e"]) - float(c["s"])) * mult
        except (KeyError, TypeError, ValueError):
            risk = 0.0
        if not risk and c["r"]:
            risk = abs(float(c["pnl"] or 0) / float(c["r"]))      # fall back to what the trade itself implies
        rows.append({"id": c["candidate_id"], "book": book, "symbol": c["symbol"], "strategy": c["strategy"],
                     "day": _day_ny(c["ts"]), "r": float(c["r"]), "risk_usd": risk or None, "reviews": by.get(c["candidate_id"], {})})
    return rows


def spend(journal, version: str = PROMPT_VERSION) -> dict:
    """Everything the reviewers did, closed trade or not: calls, outcomes, cost, per provider."""
    try:
        rows = [dict(r) for r in journal.db.execute(
            "SELECT provider, model, action, called, cost_usd, tokens_in FROM dyn_reviews WHERE prompt_version=?", (version,))]
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["provider"], {"model": r["model"], "reviews": 0, "calls": 0, "cost_usd": 0.0, "unpriced_calls": 0,
                                           "ENTER": 0, "WAIT": 0, "CANCEL": 0, "ABSTAIN": 0, "NOT_REVIEWED": 0})
        d["reviews"] += 1
        d["calls"] += int(r["called"] or 0)
        d[r["action"]] = d.get(r["action"], 0) + 1
        if r["cost_usd"] is not None:
            d["cost_usd"] = round(d["cost_usd"] + r["cost_usd"], 6)
        elif r["called"] and r["tokens_in"] is not None:
            d["unpriced_calls"] += 1
    return out


def merge_spend(spends: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for sp in spends:
        for p, d in sp.items():
            o = out.setdefault(p, {**{k: 0 for k in d if k != "model"}, "model": d["model"]})
            for k, v in d.items():
                if k != "model":
                    o[k] = round(o.get(k, 0) + v, 6)
    return out


# ── bootstrap ─────────────────────────────────────────────────────────────────────────────────────
def block_boot(days: list[str], vals: np.ndarray, draws: int = DRAWS, seed: int = SEED) -> tuple[float, float]:
    """95% range of the mean of `vals` per candidate: circular moving blocks of 5 consecutive NY weekdays across the
    period (weekdays without a candidate included), the same resampled blocks for every column."""
    if not len(vals):
        return float("nan"), float("nan")
    d = pd.to_datetime(pd.Series(days)).to_numpy("datetime64[D]")
    wd = pd.date_range(d.min(), d.max(), freq="D")
    wd = wd[wd.dayofweek < 5].to_numpy("datetime64[D]")
    pos = np.clip(np.searchsorted(wd, d), 0, len(wd) - 1)       # a weekend day joins the next weekday
    W = len(wd)
    sums = np.bincount(pos, np.asarray(vals, float), W)
    cnt = np.bincount(pos, minlength=W).astype(float)
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(W / BLOCK))
    out = []
    for c in range(0, draws, 500):
        n = min(500, draws - c)
        st = rng.integers(0, W, size=(n, nb))
        ix = ((st[:, :, None] + np.arange(BLOCK)) % W).reshape(n, -1)[:, :W]
        a = cnt[ix].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out.append(np.where(a > 0, sums[ix].sum(1) / a, np.nan))
    m = np.concatenate(out)
    m = m[np.isfinite(m)]
    if not len(m):
        return float("nan"), float("nan")
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ── arms ──────────────────────────────────────────────────────────────────────────────────────────
def _answered(rv: dict | None) -> bool:
    return bool(rv) and rv["action"] in ANSWERS


def _arm_state(row: dict, provs: tuple) -> str:
    """entered | review (WAIT/CANCEL) | abstain | not_reviewed, for one candidate in one arm."""
    if not provs:
        return "entered"
    rvs = [row["reviews"].get(p) for p in provs]
    if all(rv and rv["action"] == "ENTER" for rv in rvs):
        return "entered"
    if any(rv and rv["action"] in ("WAIT", "CANCEL") for rv in rvs):
        return "review"
    if any(rv and rv["action"] == "NOT_REVIEWED" for rv in rvs):
        return "not_reviewed"
    return "abstain"


def _q(v: list, p: float):
    return round(float(np.percentile(v, p)), 1) if v else None


def arm_metrics(rows: list[dict], arm: str, draws: int = DRAWS) -> dict:
    provs = ARMS[arm]
    n = len(rows)
    out: dict = {"arm": arm, "name": ARM_NAME[arm], "candidates": n}
    if not rows or any(not any(p in r["reviews"] for r in rows) for p in provs):
        return {**out, "on": False}              # no review of this arm's provider(s): off (no model / no key / not run)
    st = [_arm_state(r, provs) for r in rows]
    ent = np.array([s == "entered" for s in st], bool)
    r = np.array([x["r"] for x in rows], float)
    skip = ~ent
    out.update(on=True, entered=int(ent.sum()), skipped=int(skip.sum()),
               skipped_by_review=st.count("review"), abstained=st.count("abstain"), not_reviewed=st.count("not_reviewed"),
               total_r=round(float(r[ent].sum()), 3), r_per_candidate=round(float(r[ent].sum() / n), 4) if n else None,
               avoided_losers=int((skip & (r < 0)).sum()), avoided_r=round(float(-r[skip & (r < 0)].sum()), 3) + 0.0,
               missed_winners=int((skip & (r > 0)).sum()), missed_r=round(float(r[skip & (r > 0)].sum()), 3))
    # cost: only the providers of this arm; in R with each trade's own risk
    cost_usd = cost_r = 0.0
    unpriced = unknown_risk = 0
    cost_r_i = np.zeros(n)
    for i, row in enumerate(rows):
        for p in provs:
            rv = row["reviews"].get(p)
            if not rv or not rv.get("called"):
                continue
            if rv["cost_usd"] is None:
                unpriced += 1
                continue
            cost_usd += rv["cost_usd"]
            if row["risk_usd"]:
                cost_r_i[i] += rv["cost_usd"] / row["risk_usd"]
            else:
                unknown_risk += 1
    cost_r = float(cost_r_i.sum())
    out["cost"] = {"usd": round(cost_usd, 4), "r": round(cost_r, 4), "unpriced_calls": unpriced, "no_risk_amount": unknown_risk,
                   "note": ("price not set" if unpriced and not cost_usd else
                            f"{unpriced} call(s) without a price" if unpriced else None)}
    out["net_r"] = round(out["total_r"] - cost_r, 3) + 0.0
    out["net_r_per_candidate"] = round((out["total_r"] - cost_r) / n, 4) if n else None
    if provs:
        lat, fast, reviewed = [], 0, 0
        for row in rows:
            rvs = [row["reviews"].get(p) for p in provs]
            reviewed += all(_answered(rv) for rv in rvs)
            ls = [rv["latency_ms"] for rv in rvs if rv and rv.get("called") and rv.get("latency_ms") is not None]
            if ls:
                lat.append(max(ls))
            fast += all(_answered(rv) and rv.get("latency_ms") is not None and rv["latency_ms"] <= LIVE_S * 1000 for rv in rvs)
        out["reviewed"] = reviewed
        out["latency_ms"] = {"p50": _q(lat, 50), "p95": _q(lat, 95), "max": _q(lat, 100), "n": len(lat)}
        out["share_within_30s"] = round(fast / n, 4) if n else None
        # paired difference to A, per candidate: skipping a trade removes its R (negative if it was a winner)
        gross = np.where(ent, 0.0, -r)
        net = gross - cost_r_i
        out["vs_a"] = {"gross_per_candidate": round(float(gross.mean()), 4), "net_per_candidate": round(float(net.mean()), 4),
                       "net_total_r": round(float(net.sum()), 3)}
        if reviewed >= MIN_BOOT:
            days = [x["day"] for x in rows]
            lo, hi = block_boot(days, net, draws)
            out["vs_a"].update(net_ci=[round(lo, 4), round(hi, 4)] if np.isfinite(lo) else None)
            g_lo, g_hi = block_boot(days, gross, draws)
            out["vs_a"].update(gross_ci=[round(g_lo, 4), round(g_hi, 4)] if np.isfinite(g_lo) else None)
        else:
            out["vs_a"].update(net_ci=None, gross_ci=None, ci_note=f"needs >= {MIN_BOOT} reviewed closed trades (has {reviewed})")
        ci = out["vs_a"].get("net_ci")
        interim = reviewed < RULE_N
        out["rule"] = {"reviewed": reviewed, "needs": RULE_N, "interim": interim,
                       "net_ci_above_0": None if ci is None else bool(ci[0] > 0),
                       "share_within_30s": out["share_within_30s"], "share_ok": bool((out["share_within_30s"] or 0) >= RULE_SHARE),
                       "worth_live_trial": None if interim else bool(ci is not None and ci[0] > 0 and (out["share_within_30s"] or 0) >= RULE_SHARE)}
    return out


def score(rows: list[dict], draws: int = DRAWS) -> dict:
    """Arms A-D overall and per symbol for a set of candidate rows (closed trades only)."""
    res = {"candidates": len(rows), "arms": {a: arm_metrics(rows, a, draws) for a in ARMS}, "by_symbol": {}}
    for sym in sorted({r["symbol"] for r in rows}):
        sub = [r for r in rows if r["symbol"] == sym]
        res["by_symbol"][sym] = {"candidates": len(sub), "arms": {a: arm_metrics(sub, a, draws) for a in ARMS}}
    return res


def scorecard(journal, cfg, book: str, version: str = PROMPT_VERSION, draws: int = DRAWS) -> dict:
    rows = collect(journal, cfg, book, version)
    out = score(rows, draws)
    out.update(book=book, prompt_version=version, spend=spend(journal, version))
    return out


def recent_reviews(journal, limit: int = 50) -> list[dict]:
    """The latest reviews with the trade they were about (R once it has closed), newest first."""
    try:
        rows = [dict(r) for r in journal.db.execute(
            "SELECT v.ts, v.candidate_id, v.provider, v.model, v.action, v.trigger_id, v.invalidation_id, v.evidence, "
            "v.conflicting, v.latency_ms, v.cost_usd, v.error, c.symbol, c.side, c.strategy, t.status, t.r_multiple "
            "FROM dyn_reviews v LEFT JOIN dyn_candidates c ON c.candidate_id=v.candidate_id "
            "LEFT JOIN trades t ON t.id=v.candidate_id ORDER BY v.id DESC LIMIT ?", (limit,))]
    except sqlite3.OperationalError:
        return []
    return rows


# ── report ────────────────────────────────────────────────────────────────────────────────────────
def _f(x, nd=2, sign=False):
    return "—" if x is None else (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}")


def _cost_cell(m: dict) -> str:
    c = m["cost"]
    if c["note"] == "price not set":
        return "price not set"
    return f"${c['usd']:.3f} / {c['r']:.3f}R" + (f" ({c['note']})" if c["note"] else "")


def _spend_cost(d: dict) -> str:
    return "price not set" if d["unpriced_calls"] and not d["cost_usd"] else f"{d['cost_usd']:.3f}"


def _share(m: dict) -> str:
    v = m.get("share_within_30s")
    return "—" if v is None else f"{v * 100:.0f}%"


def _secs(v) -> str:
    return "—" if v is None else f"{v / 1000:.1f}"


def arm_table(sc: dict) -> list[str]:
    L = ["| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | "
         "missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, m in sc["arms"].items():
        if not m.get("on", True):
            L.append(f"| {a} {m['name']} | {m['candidates']} | off: no reviews from this provider | | | | | | | | | |")
            continue
        lat = m.get("latency_ms")
        lat_s = f"{_secs(lat['p50'])} / {_secs(lat['p95'])} / {_secs(lat['max'])}" if lat and lat["n"] else "—"
        L.append(f"| **{a}** {m['name']} | {m['candidates']} | {m['entered']} | {m['skipped']} ({m['skipped_by_review']} / {m['abstained']} / "
                 f"{m['not_reviewed']}) | {_f(m['total_r'], 2, True)} | {_f(m['r_per_candidate'], 3, True)} | {m['avoided_losers']} ({_f(m['avoided_r'], 2, True)}R) | "
                 f"{m['missed_winners']} ({_f(m['missed_r'], 2, True)}R) | {_cost_cell(m)} | {_f(m['net_r'], 2, True)} | {lat_s} | "
                 f"{_share(m)} |")
    return L


def diff_table(sc: dict) -> list[str]:
    L = ["| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |",
         "|---|---|---|---|---|---|"]
    for a in ("B", "C", "D"):
        m = sc["arms"][a]
        if not m.get("on", True):
            L.append(f"| {a} {m['name']} | off | | | | |")
            continue
        v, ru = m["vs_a"], m["rule"]
        ci = v.get("net_ci")
        rng = f"{ci[0]:+.3f} to {ci[1]:+.3f}" if ci else (v.get("ci_note") or "n/a")
        if ru["interim"]:
            rule = f"interim: {ru['reviewed']} of {ru['needs']} reviewed"
        else:
            rule = "**worth a live trial**" if ru["worth_live_trial"] else "stays in shadow / dropped"
        L.append(f"| {a} {m['name']} | {ru['reviewed']} | {_f(v['gross_per_candidate'], 4, True)} | {_f(v['net_per_candidate'], 4, True)} | {rng} | {rule} |")
    return L


def report_md(groups: dict[str, dict], version: str, books: list[str], notes: list[str]) -> str:
    L = [f"# Shadow review gate: scorecard (prompt {version})", "",
         "Milestone 1 of the dynamic controller (docs/dynamic_controller.md). **No review changed any trade.** WAIT counts as skipped; "
         "ABSTAIN and `not_reviewed: budget` are skipped and counted separately; only closed trades are scored. "
         "Costs are USD as billed per token at the prices in `dynamic.prices` (R-equivalent uses each trade's own risk in USD; "
         "the bot books everything in USD, so no CAD conversion is applied). Results are never pooled across prompt versions.", ""]
    L += [f"Books: {', '.join(books)}", ""] + [f"- {n}" for n in notes] + ([""] if notes else [])
    for title, sc in groups.items():
        L += [f"## {title}", "", f"{sc['candidates']} closed candidate(s).", ""]
        if not sc["candidates"]:
            L += ["Nothing to score yet.", ""]
            continue
        L += arm_table(sc) + ["", "Paired difference to A (skipping a trade removes its R; the API cost is subtracted):", ""] + diff_table(sc) + [""]
        if title == "All books" and sc.get("by_symbol"):
            L += ["### By symbol", ""]
            for sym, s in sc["by_symbol"].items():
                L += [f"**{sym}** ({s['candidates']} closed candidates)", ""] + arm_table(s) + [""]
        sp = sc.get("spend")
        if sp:
            L += ["Everything the reviewers did (closed trades or not):", "", "| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |", "|---|---|---|---|---|---|---|---|---|---|"]
            for p, d in sp.items():
                L.append(f"| {p} | {d['model']} | {d['reviews']} | {d['calls']} | {d['ENTER']} | {d['WAIT']} | {d['CANCEL']} | {d['ABSTAIN']} | "
                         f"{d['NOT_REVIEWED']} | {_spend_cost(d)} |")
            L.append("")
    L += ["Decision rule (registered): after >= 100 reviewed closed trades an arm is worth a live trial only if its paired improvement "
          "over A, after API cost, has a 95% range above 0 and its reviews arrive within 30 s for >= 95% of candidates. Otherwise it stays in shadow or is dropped."]
    return "\n".join(L) + "\n"


def journal_path(cfg, book: str) -> str:
    if book == "live":
        return cfg["storage"]["db_path"]
    from ..agents.setup_first import shadow_db_for, shadow_modes
    modes = shadow_modes(cfg)
    return shadow_db_for(cfg, book, first=bool(modes) and modes[0] == book)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--books", default="live,playbook")
    ap.add_argument("--version", default=PROMPT_VERSION)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default="data/year_test/dynamic_review")
    a = ap.parse_args(argv)
    from ..config import apply_broker, load_config
    cfg = load_config(a.config)
    if cfg.get("broker") == "oanda":
        cfg["mode"] = "paper"                     # the trades were booked with the OANDA instrument multipliers
        apply_broker(cfg)
    books = [b.strip() for b in a.books.split(",") if b.strip()]
    all_rows, notes, per_book, spends = [], [], {}, []
    for b in books:
        path = journal_path(cfg, b)
        if not Path(path).exists():
            notes.append(f"{b}: no journal at {path}")
            continue
        j = ReadOnly(path)
        rows = collect(j, cfg, b, a.version)
        all_rows += rows
        sc = score(rows)
        sc["spend"] = spend(j, a.version)
        spends.append(sc["spend"])
        per_book[b] = sc
    pooled = score(all_rows)
    pooled["spend"] = merge_spend(spends)
    groups = {"All books": pooled}
    if len(per_book) > 1:
        groups.update({f"Book: {b}": sc for b, sc in per_book.items()})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report_md(groups, a.version, books, notes))
    (out / "summary.json").write_text(json.dumps({"prompt_version": a.version, "books": books, "groups": groups}, indent=1, default=str))
    print(f"wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
