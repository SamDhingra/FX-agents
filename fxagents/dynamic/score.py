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

from .providers import EXCHANGE_PROMPT_VERSION, PROMPT_VERSION, exchange_decision

NY = "America/New_York"
ARMS = {"A": (), "B": ("openai",), "C": ("claude",), "D": ("openai", "claude"),
        "E1": ("claude",), "E2": ("openai",), "E3": ("openai", "claude")}
ARM_NAME = {"A": "every entry taken", "B": "OpenAI", "C": "Claude", "D": "both say ENTER",
            "E1": "Claude, round 2", "E2": "OpenAI, round 2", "E3": "exchange decision rule"}
E_ARMS = ("E1", "E2", "E3")          # milestone 1b: decided by the round-2 answers (dyn-x1); scored on exchanged candidates only
BASE_ARMS = ("A", "B", "C", "D")
ANSWERS = ("ENTER", "WAIT", "CANCEL")
DRAWS, SEED, BLOCK, MIN_BOOT, RULE_N, RULE_SHARE, LIVE_S, EXCH_S = 10_000, 20261026, 5, 30, 100, 0.95, 30.0, 45.0


# ── reading the journal ───────────────────────────────────────────────────────────────────────────
class ReadOnly:
    """A read-only handle on a journal file (the report must never write to the bot's database)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row


def _day_ny(ts_utc: str) -> str:
    return str(pd.Timestamp(ts_utc, tz="UTC").tz_convert(NY).date())


def _cols(journal, table: str) -> set:
    return {r[1] for r in journal.db.execute(f"PRAGMA table_info({table})")}


RETRO_TITLE = "Past trades (retrospective, not counted toward the decision rule; latency not meaningful)"


def _source_filter(journal, source: str, alias: str = "c") -> tuple[str, tuple]:
    """SQL fragment keeping candidates of one source. 'live' is everything not marked backfill, so milestone-1 databases
    without the column read as all live and a backfill row can never reach the live scorecard."""
    if "source" not in _cols(journal, "dyn_candidates"):
        return ("AND 1=1", ()) if source == "live" else ("AND 1=0", ())
    return f"AND COALESCE({alias}.source,'live')=?", (source,)


def collect(journal, cfg, book: str, version: str = PROMPT_VERSION, ex_version: str = EXCHANGE_PROMPT_VERSION,
            source: str = "live") -> list[dict]:
    """One row per closed, reviewed-or-not candidate of this prompt version: its trade result, each provider's round-1
    review (`reviews`), round-2 review (`r2`, prompt `ex_version`) and how the exchange went. Milestone-1 journals
    (no round / exchange columns) read as: round 1 only, exchange not run."""
    try:
        ccols = _cols(journal, "dyn_candidates")
        sf, sargs = _source_filter(journal, source)
        ex = ("c.exchange_status xs, c.exchange_ms xms" if {"exchange_status", "exchange_ms"} <= ccols else "NULL xs, NULL xms")
        cands = [dict(r) for r in journal.db.execute(
            f"SELECT c.candidate_id, c.symbol, c.strategy, c.ts, t.r_multiple r, t.qty_initial q, t.entry e, t.initial_stop s, "
            f"t.realized pnl, {ex} FROM dyn_candidates c JOIN trades t ON t.id=c.candidate_id "
            f"WHERE c.prompt_version=? AND t.status='closed' AND t.r_multiple IS NOT NULL {sf} ORDER BY c.ts", (version, *sargs))]
        rc = _cols(journal, "dyn_reviews")
        chg = ("changed, why_changed" if "changed" in rc else "NULL changed, NULL why_changed") + (", changed_reported" if "changed_reported" in rc else ", NULL changed_reported")
        revs = [dict(r) for r in journal.db.execute(
            f"SELECT candidate_id, provider, model, action, trigger_id, latency_ms, cost_usd, tokens_in, tokens_out, called, error, "
            f"prompt_version pv, {chg} FROM dyn_reviews WHERE prompt_version IN (?,?)", (version, ex_version))]
    except sqlite3.OperationalError:          # no review tables yet
        return []
    by: dict[str, dict] = {}
    by2: dict[str, dict] = {}
    for v in revs:
        (by if v["pv"] == version else by2).setdefault(v["candidate_id"], {})[v["provider"]] = v
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
                     "day": _day_ny(c["ts"]), "r": float(c["r"]), "risk_usd": risk or None, "reviews": by.get(c["candidate_id"], {}),
                     "r2": by2.get(c["candidate_id"], {}), "exchange_status": c["xs"], "exchange_ms": c["xms"]})
    return rows


def spend(journal, version: str = PROMPT_VERSION, source: str = "live") -> dict:
    """Everything the reviewers did, closed trade or not: calls, outcomes, cost, per provider (one source only)."""
    try:
        if "source" in _cols(journal, "dyn_candidates"):
            back = "candidate_id IN (SELECT candidate_id FROM dyn_candidates WHERE source='backfill')"
            sf = back if source == "backfill" else "NOT " + back
        else:
            sf = "1=0" if source == "backfill" else "1=1"
        rows = [dict(r) for r in journal.db.execute(
            f"SELECT provider, model, action, called, cost_usd, tokens_in FROM dyn_reviews WHERE prompt_version=? AND {sf}", (version,))]
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


def _inputs(row: dict, arm: str) -> tuple[list, list]:
    """(the review(s) that decide this arm, every review that was paid for to get that decision). A, B, C, D use round 1.
    E arms use round 2 and are charged for the whole exchange that produced them: both reviewers' round 1 and round 2."""
    provs = ARMS[arm]
    if arm in E_ARMS:
        r2 = row.get("r2") or {}
        both = ("openai", "claude")
        return [r2.get(p) for p in provs], [row["reviews"].get(p) for p in both] + [r2.get(p) for p in both]
    rvs = [row["reviews"].get(p) for p in provs]
    return rvs, rvs


def _arm_state(row: dict, arm: str) -> str:
    """entered | review (WAIT/CANCEL) | abstain | not_reviewed, for one candidate in one arm."""
    if not ARMS[arm]:
        return "entered"
    rvs, _ = _inputs(row, arm)
    if arm == "E3":
        if exchange_decision(*[(row.get("r2") or {}).get(p) for p in ("openai", "claude")]) == "enter":
            return "entered"
    elif all(rv and rv["action"] == "ENTER" for rv in rvs):
        return "entered"
    if any(rv and rv["action"] in ("WAIT", "CANCEL") for rv in rvs):
        return "review"
    if any(rv and rv["action"] == "NOT_REVIEWED" for rv in rvs):
        return "not_reviewed"
    return "abstain"


def _q(v: list, p: float):
    return round(float(np.percentile(v, p)), 1) if v else None


def _costs(rows: list[dict], arm: str):
    """(usd, per-candidate cost in R, calls without a price, calls on a trade with no risk amount)"""
    n = len(rows)
    cost_usd = 0.0
    unpriced = unknown_risk = 0
    cost_r_i = np.zeros(n)
    for i, row in enumerate(rows):
        for rv in _inputs(row, arm)[1]:
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
    return cost_usd, cost_r_i, unpriced, unknown_risk


def arm_net(rows: list[dict], arm: str) -> np.ndarray:
    """Per candidate: the arm's R difference to A (a skipped trade removes its R) minus its API cost in R."""
    ent = np.array([_arm_state(r, arm) == "entered" for r in rows], bool)
    r = np.array([x["r"] for x in rows], float)
    return np.where(ent, 0.0, -r) - _costs(rows, arm)[1]


def arm_metrics(rows: list[dict], arm: str, draws: int = DRAWS, share_den: int | None = None, retro: bool = False) -> dict:
    """`share_den`: for E arms, the number of ALL candidates, so the 30-second share is not flattered by the ones where
    no exchange ran (the registered rule asks for 95% of candidates)."""
    provs = ARMS[arm]
    n = len(rows)
    out: dict = {"arm": arm, "name": ARM_NAME[arm], "candidates": n}
    src = "r2" if arm in E_ARMS else "reviews"
    if not rows or any(not any(p in (r.get(src) or {}) for r in rows) for p in provs):
        return {**out, "on": False}              # no review of this arm's provider(s): off (no model / no key / not run)
    st = [_arm_state(r, arm) for r in rows]
    ent = np.array([s == "entered" for s in st], bool)
    r = np.array([x["r"] for x in rows], float)
    skip = ~ent
    out.update(on=True, entered=int(ent.sum()), skipped=int(skip.sum()),
               skipped_by_review=st.count("review"), abstained=st.count("abstain"), not_reviewed=st.count("not_reviewed"),
               total_r=round(float(r[ent].sum()), 3), r_per_candidate=round(float(r[ent].sum() / n), 4) if n else None,
               avoided_losers=int((skip & (r < 0)).sum()), avoided_r=round(float(-r[skip & (r < 0)].sum()), 3) + 0.0,
               missed_winners=int((skip & (r > 0)).sum()), missed_r=round(float(r[skip & (r > 0)].sum()), 3))
    # cost: only the providers of this arm (E arms: the whole exchange); in R with each trade's own risk
    cost_usd, cost_r_i, unpriced, unknown_risk = _costs(rows, arm)
    cost_r = float(cost_r_i.sum())
    out["cost"] = {"usd": round(cost_usd, 4), "r": round(cost_r, 4), "unpriced_calls": unpriced, "no_risk_amount": unknown_risk,
                   "note": ("price not set" if unpriced and not cost_usd else
                            f"{unpriced} call(s) without a price" if unpriced else None)}
    out["net_r"] = round(out["total_r"] - cost_r, 3) + 0.0
    out["net_r_per_candidate"] = round((out["total_r"] - cost_r) / n, 4) if n else None
    if provs:
        lat, fast, reviewed = [], 0, 0
        for row in rows:
            rvs = _inputs(row, arm)[0]
            reviewed += all(_answered(rv) for rv in rvs)
            if arm in E_ARMS:                     # the full exchange: round-1 hand-over to round-2 end
                xm = row.get("exchange_ms")
                if xm is not None:
                    lat.append(xm)
                fast += all(_answered(rv) for rv in rvs) and xm is not None and xm <= LIVE_S * 1000
                continue
            ls = [rv["latency_ms"] for rv in rvs if rv and rv.get("called") and rv.get("latency_ms") is not None]
            if ls:
                lat.append(max(ls))
            fast += all(_answered(rv) and rv.get("latency_ms") is not None and rv["latency_ms"] <= LIVE_S * 1000 for rv in rvs)
        den = share_den or n
        out["reviewed"] = reviewed
        out["latency_ms"] = {"p50": _q(lat, 50), "p95": _q(lat, 95), "max": _q(lat, 100), "n": len(lat)}
        out["share_within_30s"] = round(fast / den, 4) if den else None
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
        if retro:      # past trades never count toward the rule, and their latency says nothing about a live gate
            out["latency_ms"], out["share_within_30s"], out["rule"] = None, None, None
    return out


def paired_diff(rows: list[dict], arm_x: str, arm_y: str, draws: int = DRAWS) -> dict:
    """Arm X minus arm Y on the same candidates, net of each arm's own API cost (R per candidate), with the block
    bootstrap range from 30 candidates where both arms gave an answer."""
    if not rows:
        return {"n": 0}
    d = arm_net(rows, arm_x) - arm_net(rows, arm_y)
    out = {"n": len(rows), "net_per_candidate": round(float(d.mean()), 4), "net_total_r": round(float(d.sum()), 3), "net_ci": None}
    if len(rows) >= MIN_BOOT:
        lo, hi = block_boot([x["day"] for x in rows], d, draws)
        out["net_ci"] = [round(lo, 4), round(hi, 4)] if np.isfinite(lo) else None
    else:
        out["ci_note"] = f"needs >= {MIN_BOOT} exchanged closed trades (has {len(rows)})"
    return out


def _is_exchanged(row: dict) -> bool:
    return row.get("exchange_status") == "done"


def _solo_r(rv: dict | None, r: float) -> float:
    """The R a single reviewer's answer would have earned as a skip gate: the trade's R if ENTER, else 0."""
    return r if rv and rv["action"] == "ENTER" else 0.0


def mind_changes(rows: list[dict]) -> dict:
    """Per reviewer, on exchanged closed trades: how often it said it changed, which way (by the actions: toward ENTER,
    away from ENTER, other), and on those trades the R its round-2 answer earned against its round-1 answer."""
    out = {}
    for p in ("claude", "openai"):
        d = {"exchanged": 0, "changed": 0, "toward_enter": 0, "away_from_enter": 0, "other": 0, "flag_vs_action_mismatch": 0,
             "r_round1": 0.0, "r_round2": 0.0}
        for row in rows:
            if not _is_exchanged(row):
                continue
            v1, v2 = row["reviews"].get(p), (row.get("r2") or {}).get(p)
            if not v2:
                continue
            d["exchanged"] += 1
            if v2.get("changed_reported") is not None and v2.get("changed") is not None and bool(v2["changed_reported"]) != bool(v2["changed"]):
                d["flag_vs_action_mismatch"] += 1       # the model's own `changed` disagreed with the local comparison; stats use the local one
            if not v2.get("changed"):
                continue
            d["changed"] += 1
            a1, a2 = (v1 or {}).get("action"), v2["action"]
            if a2 == "ENTER" and a1 != "ENTER":
                d["toward_enter"] += 1
            elif a1 == "ENTER" and a2 != "ENTER":
                d["away_from_enter"] += 1
            else:
                d["other"] += 1
            d["r_round1"] += _solo_r(v1, row["r"])
            d["r_round2"] += _solo_r(v2, row["r"])
        d["r_round1"], d["r_round2"] = round(d["r_round1"], 3) + 0.0, round(d["r_round2"], 3) + 0.0
        d["r_gain"] = round(d["r_round2"] - d["r_round1"], 3) + 0.0
        out[p] = d
    return out


def exchange_section(rows: list[dict], draws: int = DRAWS, retro: bool = False) -> dict:
    """Milestone 1b: E arms on the exchanged candidates only (A and D on the same subset, E3 - D paired), the
    candidates where no exchange ran, mind-change stats, full-exchange latency and the round-2 cost."""
    n_all = len(rows)
    ex = [r for r in rows if _is_exchanged(r)]
    not_ex: dict[str, int] = {}
    for r in rows:
        if not _is_exchanged(r):
            why = r.get("exchange_status") or "skipped: no exchange recorded (milestone-1 row)"
            not_ex[why] = not_ex.get(why, 0) + 1
    out: dict = {"candidates": n_all, "exchanged": len(ex), "not_exchanged": n_all - len(ex), "not_exchanged_reasons": not_ex}
    arms = {"A": arm_metrics(ex, "A", draws, retro=retro), "D": arm_metrics(ex, "D", draws, retro=retro)}
    arms.update({a: arm_metrics(ex, a, draws, share_den=n_all, retro=retro) for a in E_ARMS})
    out["arms"] = arms
    out["e3_minus_d"] = paired_diff(ex, "E3", "D", draws) if arms["E3"].get("on") and arms["D"].get("on") else {"n": 0}
    out["mind_change"] = mind_changes(ex)
    ms = [r["exchange_ms"] for r in ex if r.get("exchange_ms") is not None]
    out["latency"] = None if retro else {"n": len(ms), "p50_ms": _q(ms, 50), "p95_ms": _q(ms, 95), "max_ms": _q(ms, 100),
                      "share_le_30s": round(sum(m <= LIVE_S * 1000 for m in ms) / len(ms), 4) if ms else None,
                      "share_le_45s": round(sum(m <= EXCH_S * 1000 for m in ms) / len(ms), 4) if ms else None,
                      "share_le_30s_all_candidates": round(sum(m <= LIVE_S * 1000 for m in ms) / n_all, 4) if n_all else None,
                      "slower_than_30s_ge_5pct": bool(ms) and sum(m > LIVE_S * 1000 for m in ms) / len(ms) >= 0.05}
    c1 = c2 = 0.0
    cr2 = 0.0
    unp = 0
    for r in ex:
        for rv in (r.get("r2") or {}).values():
            if rv and rv.get("called"):
                if rv["cost_usd"] is None:
                    unp += 1
                    continue
                c2 += rv["cost_usd"]
                cr2 += rv["cost_usd"] / r["risk_usd"] if r.get("risk_usd") else 0.0
    out["round2_cost"] = {"usd": round(c2, 4), "r": round(cr2, 4), "unpriced_calls": unp}
    return out


def score(rows: list[dict], draws: int = DRAWS, retro: bool = False) -> dict:
    """Arms A-D overall and per symbol for a set of candidate rows (closed trades only), and the exchange section
    (arms E1-E3 on the exchanged candidates only, with A and D on the same subset). `retro` = past trades reviewed
    after the fact: same arms and costs, but no latency figures and no decision-rule verdict."""
    res = {"candidates": len(rows), "arms": {a: arm_metrics(rows, a, draws, retro=retro) for a in BASE_ARMS}, "by_symbol": {},
           "exchange": exchange_section(rows, draws, retro), "retrospective": retro}
    for sym in sorted({r["symbol"] for r in rows}):
        sub = [r for r in rows if r["symbol"] == sym]
        res["by_symbol"][sym] = {"candidates": len(sub), "arms": {a: arm_metrics(sub, a, draws, retro=retro) for a in BASE_ARMS},
                                 "exchange": exchange_section(sub, draws, retro)}
    return res


def scorecard(journal, cfg, book: str, version: str = PROMPT_VERSION, draws: int = DRAWS) -> dict:
    rows = collect(journal, cfg, book, version)
    out = score(rows, draws)
    out.update(book=book, prompt_version=version, spend=spend(journal, version),
               spend_r2=spend(journal, EXCHANGE_PROMPT_VERSION))
    out["retrospective"] = retro_scorecard(journal, cfg, book, version, draws)       # separate: never mixed into the above
    return out


def retro_scorecard(journal, cfg, book: str, version: str = PROMPT_VERSION, draws: int = DRAWS) -> dict:
    """The same arms on past trades reviewed after the fact (source 'backfill'); not part of the decision rule."""
    rows = collect(journal, cfg, book, version, source="backfill")
    out = score(rows, draws, retro=True)
    out.update(book=book, title=RETRO_TITLE, spend=spend(journal, version, "backfill"),
               spend_r2=spend(journal, EXCHANGE_PROMPT_VERSION, "backfill"), reviewed_candidates=backfill_count(journal))
    return out


def backfill_count(journal) -> int:
    """Every backfilled candidate (closed or not)."""
    try:
        return int(journal.db.execute("SELECT COUNT(*) FROM dyn_candidates WHERE source='backfill'").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def recent_reviews(journal, limit: int = 50) -> list[dict]:
    """The latest reviews with the trade they were about (R once it has closed), newest first. Round 2 rows carry
    round / changed / why_changed (round 1 on milestone-1 databases)."""
    try:
        extra = ("v.round, v.changed, v.why_changed, " if "round" in _cols(journal, "dyn_reviews") else "1 round, NULL changed, NULL why_changed, ")
        extra += ("COALESCE(c.source,'live') source, " if "source" in _cols(journal, "dyn_candidates") else "'live' source, ")
        rows = [dict(r) for r in journal.db.execute(
            "SELECT v.ts, v.candidate_id, v.provider, v.model, v.action, v.trigger_id, v.invalidation_id, v.evidence, "
            f"v.conflicting, v.latency_ms, v.cost_usd, v.error, {extra}c.symbol, c.side, c.strategy, t.status, t.r_multiple "
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


def diff_table(sc: dict, names: tuple = ("B", "C", "D")) -> list[str]:
    L = ["| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |",
         "|---|---|---|---|---|---|"]
    for a in names:
        m = sc["arms"][a]
        if not m.get("on", True):
            L.append(f"| {a} {m['name']} | off | | | | |")
            continue
        v, ru = m["vs_a"], m["rule"]
        ci = v.get("net_ci")
        rng = f"{ci[0]:+.3f} to {ci[1]:+.3f}" if ci else (v.get("ci_note") or "n/a")
        if ru is None:                      # retrospective: no verdict, not part of the rule
            L.append(f"| {a} {m['name']} | {m['reviewed']} | {_f(v['gross_per_candidate'], 4, True)} | {_f(v['net_per_candidate'], 4, True)} | {rng} | not counted |")
            continue
        if ru["interim"]:
            rule = f"interim: {ru['reviewed']} of {ru['needs']} reviewed"
        else:
            rule = "**worth a live trial**" if ru["worth_live_trial"] else "stays in shadow / dropped"
        L.append(f"| {a} {m['name']} | {ru['reviewed']} | {_f(v['gross_per_candidate'], 4, True)} | {_f(v['net_per_candidate'], 4, True)} | {rng} | {rule} |")
    return L


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def exchange_md(ex: dict, heading: str = "###") -> list[str]:
    """Milestone 1b section of the report for one group of candidates."""
    L = [f"{heading} Exchange (milestone 1b, prompt {EXCHANGE_PROMPT_VERSION})", ""]
    L.append(f"{ex['exchanged']} of {ex['candidates']} closed candidates were exchanged; **{ex['not_exchanged']} not exchanged** (E1/E2/E3 are not scored on those)"
             + (": " + "; ".join(f"{k} ({v})" for k, v in ex["not_exchanged_reasons"].items()) if ex["not_exchanged_reasons"] else "") + ".")
    L.append("")
    if not ex["exchanged"]:
        return L + ["No exchanged candidates yet.", ""]
    L += ["Arms on the exchanged candidates only (A and D on the same subset, so E3 against D is a fair paired comparison). "
          "E arms are charged for the whole exchange: both reviewers' round 1 and round 2.", ""]
    L += arm_table(ex) + ["", "Paired difference to A on the exchanged subset (API cost subtracted):", ""] + diff_table(ex, ("D", "E1", "E2", "E3")) + [""]
    d = ex["e3_minus_d"]
    if d.get("n"):
        ci = d.get("net_ci")
        L += [f"**E3 minus D** (net of each arm's own cost, R per candidate, {d['n']} candidates): {d['net_per_candidate']:+.4f}"
              + (f", 95% range {ci[0]:+.3f} to {ci[1]:+.3f}" if ci else f" ({d.get('ci_note')})") + f"; total {d['net_total_r']:+.2f}R.", ""]
    L += ["| reviewer | exchanged | changed its answer | toward ENTER | away from ENTER | other | R of round-1 answers on those trades | R of round-2 answers | gain |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p, m in ex["mind_change"].items():
        L.append(f"| {p} | {m['exchanged']} | {m['changed']} | {m['toward_enter']} | {m['away_from_enter']} | {m['other']} | "
                 f"{m['r_round1']:+.2f} | {m['r_round2']:+.2f} | {m['r_gain']:+.2f} |")
    L += ["", "(R of an answer = the trade's R if it said ENTER, else 0, as in arms B / C.)", ""]
    lt = ex["latency"]
    if lt is None:                         # retrospective: latency is not meaningful, only the round-2 cost is shown
        return L + [f"Round-2 cost: ${ex['round2_cost']['usd']:.3f} / {ex['round2_cost']['r']:.3f}R"
                    + (f" ({ex['round2_cost']['unpriced_calls']} call(s) without a price)" if ex['round2_cost']['unpriced_calls'] else "") + ".", ""]
    L += [f"Full-exchange latency (round-1 hand-over to round-2 end): p50 {_secs(lt['p50_ms'])} s, p95 {_secs(lt['p95_ms'])} s, max {_secs(lt['max_ms'])} s; "
          f"within 30 s: {_pct(lt['share_le_30s'])} of exchanged ({_pct(lt['share_le_30s_all_candidates'])} of all candidates); within 45 s: {_pct(lt['share_le_45s'])}.",
          f"Round-2 cost: ${ex['round2_cost']['usd']:.3f} / {ex['round2_cost']['r']:.3f}R" + (f" ({ex['round2_cost']['unpriced_calls']} call(s) without a price)" if ex['round2_cost']['unpriced_calls'] else "") + ".",
          "An exchange slower than 30 s for >= 5% of candidates can only inform slower (15m+) setups"
          + (" — **that is the case here.**" if lt["slower_than_30s_ge_5pct"] else " (not the case so far)."), ""]
    return L


def _spend_tables(sc: dict) -> list[str]:
    L = []
    for key, head in (("spend", "Everything the reviewers did (closed trades or not):"),
                      ("spend_r2", f"Round 2 ({EXCHANGE_PROMPT_VERSION}), everything the reviewers did:")):
        sp = sc.get(key)
        if sp:
            L += [head, "", "| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |", "|---|---|---|---|---|---|---|---|---|---|"]
            for p, d in sp.items():
                L.append(f"| {p} | {d['model']} | {d['reviews']} | {d['calls']} | {d['ENTER']} | {d['WAIT']} | {d['CANCEL']} | {d['ABSTAIN']} | "
                         f"{d['NOT_REVIEWED']} | {_spend_cost(d)} |")
            L.append("")
    return L


def retro_md(sc: dict | None, heading: str = "##") -> list[str]:
    """The separate section for past trades reviewed after the fact: the same arms and costs, no latency, no verdict."""
    L = [f"{heading} {RETRO_TITLE}", ""]
    if not sc or not sc.get("reviewed_candidates"):
        return L + ["No past trade has been reviewed yet (`./fx.sh dynbackfill`).", ""]
    L += ["These trades had already closed when the reviewers saw them, rebuilt as of their entry minute from OANDA candles "
          "(the models were not told). **They are a separate sample: never pooled with the live scorecard above and not counted toward the "
          "decision rule.** Latency is not meaningful (calls were not made at the fill), so no latency or 30-second share is shown.", "",
          f"{sc['reviewed_candidates']} past trade(s) reviewed, {sc['candidates']} closed and scored.", ""]
    if not sc["candidates"]:
        return L + ["Nothing to score yet.", ""]
    L += arm_table(sc) + ["", "Paired difference to A (skipping a trade removes its R; the API cost is subtracted):", ""] + diff_table(sc) + [""]
    if sc.get("exchange"):
        L += exchange_md(sc["exchange"], heading + "#")
    return L + _spend_tables(sc)


def report_md(groups: dict[str, dict], version: str, books: list[str], notes: list[str], retro: dict | None = None) -> str:
    L = [f"# Shadow review gate: scorecard (prompt {version})", "",
         "Milestone 1 of the dynamic controller (docs/dynamic_controller.md). **No review changed any trade.** WAIT counts as skipped; "
         "ABSTAIN and `not_reviewed: budget` are skipped and counted separately; only closed trades are scored. "
         "Costs are USD as billed per token at the prices in `dynamic.prices` (R-equivalent uses each trade's own risk in USD; "
         "the bot books everything in USD, so no CAD conversion is applied). Results are never pooled across prompt versions "
         "or between live and retrospective reviews.", ""]
    L += [f"Books: {', '.join(books)}", ""] + [f"- {n}" for n in notes] + ([""] if notes else [])
    for title, sc in groups.items():
        L += [f"## {title}", "", f"{sc['candidates']} closed candidate(s).", ""]
        if not sc["candidates"]:
            L += ["Nothing to score yet.", ""]
            continue
        L += arm_table(sc) + ["", "Paired difference to A (skipping a trade removes its R; the API cost is subtracted):", ""] + diff_table(sc) + [""]
        if sc.get("exchange"):
            L += exchange_md(sc["exchange"])
        if title == "All books" and sc.get("by_symbol"):
            L += ["### By symbol", ""]
            for sym, s in sc["by_symbol"].items():
                L += [f"**{sym}** ({s['candidates']} closed candidates)", ""] + arm_table(s) + [""]
                if s.get("exchange", {}).get("exchanged"):
                    L += [f"{sym}, exchanged candidates only:", ""] + arm_table(s["exchange"]) + [""]
        L += _spend_tables(sc)
    L += ["Decision rule (registered): after >= 100 reviewed closed trades an arm is worth a live trial only if its paired improvement "
          "over A, after API cost, has a 95% range above 0 and its reviews arrive within 30 s for >= 95% of candidates. Otherwise it stays in shadow or is dropped. "
          "For E arms (milestone 1b) the cost is round 1 + round 2 and the 30 s share is taken over all candidates, exchanged or not.", ""]
    L += retro_md(retro)
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
    all_rows, notes, per_book, spends, spends2 = [], [], {}, [], []
    retro_rows, rsp, rsp2, rcount = [], [], [], 0
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
        sc["spend_r2"] = spend(j, EXCHANGE_PROMPT_VERSION)
        spends.append(sc["spend"])
        spends2.append(sc["spend_r2"])
        per_book[b] = sc
        retro_rows += collect(j, cfg, b, a.version, source="backfill")
        rsp.append(spend(j, a.version, "backfill"))
        rsp2.append(spend(j, EXCHANGE_PROMPT_VERSION, "backfill"))
        rcount += backfill_count(j)
    pooled = score(all_rows)
    pooled["spend"] = merge_spend(spends)
    pooled["spend_r2"] = merge_spend(spends2)
    groups = {"All books": pooled}
    if len(per_book) > 1:
        groups.update({f"Book: {b}": sc for b, sc in per_book.items()})
    retro = score(retro_rows, retro=True)
    retro.update(title=RETRO_TITLE, spend=merge_spend(rsp), spend_r2=merge_spend(rsp2), reviewed_candidates=rcount)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report_md(groups, a.version, books, notes, retro))
    (out / "summary.json").write_text(json.dumps({"prompt_version": a.version, "books": books, "groups": groups,
                                                  "retrospective": retro}, indent=1, default=str))
    print(f"wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
