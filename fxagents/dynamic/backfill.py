"""Retrospective backfill of the shadow review gate (Oct 27 2026, docs/dynamic_controller.md): run, once by hand, the same
Claude + OpenAI review on the book's last N CLOSED trades, as if it had been asked at their entry minute.

    python -m fxagents.dynamic.backfill --book live --last 10        (./fx.sh dynbackfill [book=live] [n=10])

What it does, in order:
  1. picks the book's last N closed trades (r_multiple known, newest close first) that have no review yet; N <= 50.
  2. rebuilds each trade's inputs AS OF its entry minute from OANDA: M1 bid/ask candles (complete only) for the 5 calendar
     days (~3 trading days) before entry up to the minute BEFORE entry, and H1 mid candles for the 60 days before entry,
     of which only bars that had closed by the entry minute are kept. Nothing at or after the entry minute is requested,
     and every frame is checked against it (a violation aborts that trade).
  3. builds the packet with packet.build_packet unchanged, the bias with the live BiasAgent computation (context.compute_bias)
     on that past data, the spread from the last bid/ask minute before entry, cost_r = spread / stop distance.
  4. prints the trades and a cost estimate, then runs the live review path (dynamic/runner.py: round 1 for both providers
     concurrently, then the exchange when both are valid; same prompts, validation, budget counter and deadlines).
  5. stores rows in the same tables with dyn_candidates.source = 'backfill' (plus retrospective = 1 and reviewed_at on the
     row only: the packet text the models see is the live format and says nothing about the trade being in the past),
     prints a per-trade table and writes data/year_test/dynamic_backfill/report.md.

Backfill rows are scored apart from the live ones (dynamic/score.py): never part of the decision rule, no latency figures.
Without an OpenAI model + key it runs Claude only and says so (the exchange is then skipped, as live).
Read-only on OANDA (candles only). Needs OANDA_API_TOKEN / OANDA_ACCOUNT_ID and the provider keys in the environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from ..agents.context import compute_bias, hour_stats
from ..indicators import resample_ohlc
from ..state import trading_day
from . import store
from .packet import build_packet, canonical
from .providers import EXCHANGE_SYSTEM_PROMPT, PROMPT_VERSION, SYSTEM_PROMPT, build_providers
from .runner import ReviewRunner

log = logging.getLogger("dynamic.backfill")
MAX_TRADES = 50
M1_DAYS = 5                  # calendar days of M1 before entry (~3 trading days, with a weekend in between)
H1_DAYS = 60                 # H1 history before entry (bias needs >= 48 bars)
MIN_H1 = 48
MAX_GAP_MIN = 30             # the last M1 bar must be this close to the entry, else the market data is not there
CHUNK_M1, CHUNK_H1 = pd.Timedelta(minutes=4000), pd.Timedelta(hours=4000)   # OANDA answers at most 5000 candles per request
OUT = Path("data/year_test/dynamic_backfill")
DEFAULT_OUT_TOKENS = {1: 350, 2: 450}
CHARS_PER_TOKEN = 3.2
ROUND2_EXTRA_TOKENS = 700    # the exchange addendum is in the system prompt (counted there); two repeated answers in the user text


# ── choosing the trades ───────────────────────────────────────────────────────────────────────────────────────
ANSWERS = ("ENTER", "WAIT", "CANCEL")


def redoable_ids(journal) -> set[str]:
    """Backfill candidates where ANY provider's round-1 review is a non-answer (ABSTAIN / NOT_REVIEWED): --redo re-asks only
    that provider (the others' valid round-1 answers are kept) and runs the exchange again. Live rows are never included."""
    return {r[0] for r in journal.db.execute(
        "SELECT c.candidate_id FROM dyn_candidates c WHERE COALESCE(c.source,'live')='backfill' AND EXISTS "
        f"(SELECT 1 FROM dyn_reviews v WHERE v.candidate_id=c.candidate_id AND COALESCE(v.round,1)=1 "
        f"AND v.action NOT IN ({','.join('?' * len(ANSWERS))}))", ANSWERS)}


def stored_answers(journal, cid: str, packet_hash: str | None = None) -> dict[str, dict]:
    """provider -> the stored VALID round-1 answer of this candidate, as the same result dict the runner produces.
    With packet_hash, only answers given on that exact packet text."""
    from .providers import result
    out = {}
    for r in journal.db.execute(
            "SELECT provider, model, packet_hash, action, trigger_id, invalidation_id, evidence, conflicting, missing, latency_ms, "
            "tokens_in, tokens_out, cost_usd, error, response FROM dyn_reviews WHERE candidate_id=? AND COALESCE(round,1)=1 "
            f"AND prompt_version=? AND action IN ({','.join('?' * len(ANSWERS))})", (cid, PROMPT_VERSION, *ANSWERS)):
        r = dict(r)
        if packet_hash is not None and r["packet_hash"] != packet_hash:
            continue
        try:
            missing = json.loads(r["missing"] or "[]")
        except ValueError:
            missing = []
        out[r["provider"]] = result(r["action"], None, trigger_id=r["trigger_id"], invalidation_id=r["invalidation_id"],
                                    evidence=r["evidence"], conflicting=r["conflicting"], missing=missing, latency_ms=r["latency_ms"],
                                    tokens_in=r["tokens_in"], tokens_out=r["tokens_out"], cost_usd=r["cost_usd"], response=r["response"])
    return out


def prepare_redo(journal, packets: dict[str, dict], providers) -> dict[str, dict]:
    """For these backfill candidates (id -> rebuilt packet): keep the valid round-1 rows of the configured providers (same packet
    hash), delete every other review row (abstained round 1, ALL round 2) and the exchange fields. Returns id -> {provider:
    stored result} to hand the runner. source='backfill' only, never a live row."""
    prior: dict[str, dict] = {}
    for cid, packet in packets.items():
        if not journal.db.execute("SELECT 1 FROM dyn_candidates WHERE candidate_id=? AND COALESCE(source,'live')='backfill'", (cid,)).fetchone():
            continue
        valid = stored_answers(journal, cid, packet["packet_hash"])
        keep = {p: res for p, res in valid.items() if p in providers}
        journal.db.execute("DELETE FROM dyn_reviews WHERE candidate_id=? AND NOT (COALESCE(round,1)=1 AND prompt_version=? AND packet_hash=? "
                           "AND action IN (%s))" % ",".join("?" * len(ANSWERS)), (cid, PROMPT_VERSION, packet["packet_hash"], *ANSWERS))
        journal.db.execute("UPDATE dyn_candidates SET exchange_status=NULL, exchange_ms=NULL, exchange_decision=NULL WHERE candidate_id=?", (cid,))
        prior[cid] = keep
    journal.db.commit()
    return prior


def clear_backfill(journal, ids) -> int:
    """Delete the dyn_reviews and the dyn_candidates row of these backfill trades (source='backfill' only). Returns the count."""
    n = 0
    for tid in ids:
        if journal.db.execute("SELECT 1 FROM dyn_candidates WHERE candidate_id=? AND COALESCE(source,'live')='backfill'", (tid,)).fetchone():
            journal.db.execute("DELETE FROM dyn_reviews WHERE candidate_id=?", (tid,))
            journal.db.execute("DELETE FROM dyn_candidates WHERE candidate_id=? AND COALESCE(source,'live')='backfill'", (tid,))
            n += 1
    journal.db.commit()
    return n


def pick_trades(journal, cfg, n: int, redo: bool = False) -> tuple[list[dict], list[str]]:
    """The last n closed trades with an R result and no review yet, newest close first. With redo, a trade whose backfill
    reviews are all non-answers counts as unreviewed too (it is cleared later, only once it has been rebuilt).
    (trades, notes about rows left out)"""
    if not (1 <= n <= MAX_TRADES):
        raise ValueError(f"--last must be 1 to {MAX_TRADES} (asked for {n})")
    rows = [dict(r) for r in journal.db.execute(
        "SELECT id, symbol, side, strategy, opened, closed, entry, initial_stop, r_multiple, events, m15_live FROM trades "
        "WHERE status='closed' AND r_multiple IS NOT NULL AND closed IS NOT NULL "
        "AND id NOT IN (SELECT candidate_id FROM dyn_candidates)")]
    if redo:
        again = redoable_ids(journal)
        rows += [dict(r) for r in journal.db.execute(
            "SELECT id, symbol, side, strategy, opened, closed, entry, initial_stop, r_multiple, events, m15_live FROM trades "
            "WHERE status='closed' AND r_multiple IS NOT NULL AND closed IS NOT NULL AND id IN (%s)" % ",".join("?" * len(again)),
            tuple(again))] if again else []
    rows.sort(key=lambda r: pd.Timestamp(r["closed"]).tz_convert("UTC"), reverse=True)
    out, notes = [], []
    for r in rows:
        why = None
        if r["symbol"] not in cfg["instruments"]:
            why = "symbol not in the config"
        elif r["side"] not in ("LONG", "SHORT"):
            why = f"side {r['side']!r}"
        elif not r["opened"] or r["entry"] is None or r["initial_stop"] is None:
            why = "no opened / entry / initial_stop in the journal"
        elif abs(float(r["entry"]) - float(r["initial_stop"])) <= 0:
            why = "zero stop distance"
        if why:
            notes.append(f"{r['id']} {r['symbol']}: left out ({why})")
            continue
        out.append(r)
        if len(out) == n:
            break
    return out, notes


# ── OANDA candles ─────────────────────────────────────────────────────────────────────────────────────────────
def _ts(x: pd.Timestamp) -> str:
    return x.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


async def fetch_candles(client, name: str, gran: str, price: str, start: pd.Timestamp, end: pd.Timestamp, tz: str) -> pd.DataFrame:
    """Complete candles with start <= time < end, from OANDA, in windows that never reach past `end`. price "BA" gives
    bid/ask: the frame holds the mid OHLC plus the closing bid and ask (columns bid, ask). price "M" gives the mid only."""
    step = CHUNK_M1 if gran == "M1" else CHUNK_H1
    rows, cur = [], start
    while cur < end:
        stop = min(cur + step, end)
        res = await client.req("GET", f"/v3/instruments/{name}/candles",
                               params={"granularity": gran, "price": price, "from": _ts(cur), "to": _ts(stop)})
        for c in res.get("candles", []):
            if not c.get("complete"):
                continue
            t = pd.Timestamp(c["time"])
            if t >= end:
                continue
            if price == "BA":
                b, a = c.get("bid"), c.get("ask")
                if not b or not a:
                    continue
                rows.append({"ts": t, **{k: (float(b[k[0]]) + float(a[k[0]])) / 2 for k in ("open", "high", "low", "close")},
                             "volume": float(c.get("volume") or 0), "bid": float(b["c"]), "ask": float(a["c"])})
            else:
                m = c.get("mid")
                if not m:
                    continue
                rows.append({"ts": t, **{k: float(m[k[0]]) for k in ("open", "high", "low", "close")}, "volume": float(c.get("volume") or 0)})
        cur = stop
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"] + (["bid", "ask"] if price == "BA" else []))
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(tz)
    return df.set_index("ts").sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


class RetroStore:
    """Read-only stand-in for the live DataStore, holding one symbol's candles as of one entry minute: m1(sym), tf(sym, rule)
    and h1(sym), the calls build_packet's inputs come from. Construction refuses anything at or after the entry minute."""

    def __init__(self, symbol: str, entry: pd.Timestamp, m1: pd.DataFrame, h1: pd.DataFrame) -> None:
        self.symbol, self.entry = symbol, entry
        if len(m1) and m1.index.max() >= entry:
            raise AssertionError(f"{symbol}: M1 candle at {m1.index.max()} is not before the entry {entry}")
        if len(h1) and h1.index.max() + pd.Timedelta("1h") > entry:
            raise AssertionError(f"{symbol}: H1 candle {h1.index.max()} was still open at the entry {entry}")
        self._m1, self._h1 = m1, h1

    def m1(self, symbol: str | None = None) -> pd.DataFrame:
        return self._m1

    def h1(self, symbol: str | None = None) -> pd.DataFrame:
        return self._h1

    def tf(self, symbol: str | None, rule: str, complete_only: bool = True) -> pd.DataFrame:
        m1 = self._m1
        if not len(m1):
            return m1
        df = resample_ohlc(m1[["open", "high", "low", "close", "volume"]], rule)
        if complete_only and len(df) and m1.index[-1] + pd.Timedelta("1min") < df.index[-1] + pd.Timedelta(rule):
            df = df.iloc[:-1]
        return df


def entry_minute(opened: str, tz: str) -> pd.Timestamp:
    return pd.Timestamp(opened).tz_convert(tz).floor("min")


def setup_record(journal, strategy: str, before: pd.Timestamp) -> dict | None:
    """The setup's own record as known at the entry: its closed trades that had closed before the entry minute."""
    rs = [r[0] for r in journal.db.execute(
        "SELECT r_multiple, closed FROM trades WHERE status='closed' AND r_multiple IS NOT NULL AND strategy=?", (strategy,)).fetchall()
        if r[1] and pd.Timestamp(r[1]) < before]
    return {"trades": len(rs), "avg_r": round(sum(rs) / len(rs), 3)} if rs else None


def target_r_of(events: str | None) -> float | None:
    """The target R the position was opened with, from its "entry" event (logged there since Oct 28 2026), else None.
    Never from a partial exit: a partial is only logged when the target was REACHED, so reading it leaked the outcome into
    the packet (found Oct 28 2026: every loser had target_r null, every winner with a partial had it set)."""
    try:
        for e in json.loads(events or "[]"):
            if e.get("kind") == "entry" and e.get("rr") is not None:
                return float(e["rr"])
    except (ValueError, TypeError, AttributeError):
        pass
    return None


async def rebuild(client, journal, cfg, book: str, t: dict) -> dict:
    """Fetch the as-of candles for one trade and build its packet. Raises ValueError for a trade that can't be rebuilt."""
    from ..oanda import _inst
    tz = cfg["timezone"]
    sym = t["symbol"]
    ts = entry_minute(t["opened"], tz)
    name = _inst(cfg, sym)
    m1 = await fetch_candles(client, name, "M1", "BA", ts - pd.Timedelta(days=M1_DAYS), ts, tz)
    h1 = await fetch_candles(client, name, "H1", "M", ts - pd.Timedelta(days=H1_DAYS), ts, tz)
    h1 = h1[h1.index + pd.Timedelta("1h") <= ts][["open", "high", "low", "close"]]   # the hour in progress at the entry is not known yet
    if not len(m1):
        raise ValueError("no M1 candles before the entry")
    if ts - m1.index[-1] > pd.Timedelta(minutes=MAX_GAP_MIN):
        raise ValueError(f"last M1 candle is {m1.index[-1]:%Y-%m-%d %H:%M}, too far before the entry")
    if len(h1) < MIN_H1:
        raise ValueError(f"only {len(h1)} H1 candles (the bias needs {MIN_H1})")
    rs = RetroStore(sym, ts, m1, h1)                            # raises if anything is at or after the entry minute
    last = m1.iloc[-1]
    spread = float(last["ask"] - last["bid"])
    side = 1 if t["side"] == "LONG" else -1
    entry, stop = float(t["entry"]), float(t["initial_stop"])
    cost_r = spread / abs(entry - stop)
    bc = cfg["bias"]
    b = compute_bias(rs.h1(sym), ts, float(last["close"]), bc["weights"], bc["min_align"])
    n_min, full = hour_stats(rs.m1(sym).index, ts)
    b = b | {"h1_minutes": n_min, "h1_complete": full, "updated": ts.isoformat(timespec="minutes")}
    packet = build_packet(
        candidate_id=t["id"], book=book, symbol=sym, side=side, strategy=t["strategy"], ts=ts, entry=entry, stop=stop,
        target_r=target_r_of(t.get("events")), spread=spread, cost_r=cost_r, instrument=cfg["instruments"].get(sym),
        m1=rs.m1(sym), h1=rs.h1(sym), bias=b, record=setup_record(journal, t["strategy"], ts),
        m15_live=None if t.get("m15_live") is None else bool(t["m15_live"]))
    return {"trade": t, "packet": packet, "entry_ts": ts, "m1_rows": len(m1), "h1_rows": len(h1), "spread": spread}


# ── the runner ────────────────────────────────────────────────────────────────────────────────────────────────
class BackfillRunner(ReviewRunner):
    """The live review path (ReviewRunner) on a plain journal. Calls are made now, so the daily budget counts against TODAY's
    trading day (what it protects is the spend), and the stored review timestamps are the real ones."""
    source = "backfill"

    def __init__(self, journal, cfg, providers: dict) -> None:
        c = cfg.get("dynamic") or {}
        self.ctx = SimpleNamespace(journal=journal)
        self.cfg = cfg
        self.state = SimpleNamespace(now=None)
        self.log = log
        self.providers = providers
        self.deadline = float(c.get("deadline_s", 25))
        self.exchange_deadline = float(c.get("exchange_deadline_s", 45))
        self.budget = int(c.get("daily_call_budget", 120))
        self.conc = max(1, int(c.get("max_concurrency", 4)))
        self.sem = asyncio.Semaphore(self.conc)
        self.used: dict[tuple[str, str], int] = {}

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=self.cfg["timezone"])

    def now_iso(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def budget_day(self, packet: dict) -> str:
        return trading_day(self.now())

    async def review(self, packet: dict, prior: dict | None = None) -> None:
        store.add_candidate(self.ctx.journal, packet, "pending", PROMPT_VERSION, source="backfill", reviewed_at=self.now_iso())
        await self._review_all(packet["candidate"]["id"], packet, prior)

    async def run(self, packets: list[dict], prior: dict[str, dict] | None = None) -> None:
        """Several trades at once, each already two providers wide: half the concurrency limit, so a call never waits for a
        slot long enough to eat its deadline."""
        pool = asyncio.Semaphore(max(1, self.conc // 2))

        async def one(p):
            async with pool:
                await self.review(p, (prior or {}).get(p["candidate"]["id"]))
        await asyncio.gather(*[one(p) for p in packets])


# ── cost estimate ─────────────────────────────────────────────────────────────────────────────────────────────
def typical_out_tokens(journal, provider: str, round_no: int) -> tuple[int, str]:
    """Average output tokens of past calls of this provider and round if there are at least 3, else a default."""
    try:
        v = "dyn-v1" if round_no == 1 else "dyn-x1"
        r = journal.db.execute("SELECT AVG(tokens_out), COUNT(*) FROM dyn_reviews WHERE provider=? AND prompt_version=? AND called=1 "
                               "AND tokens_out IS NOT NULL", (provider, v)).fetchone()
        if r and r[1] and r[1] >= 3:
            return int(r[0]), f"avg of {r[1]} past calls"
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_OUT_TOKENS[round_no], "default"


def estimate(journal, providers: dict, packets: list[dict], today_used: dict[str, int], budget: int,
             reuse: dict[str, int] | None = None) -> dict:
    """Upper-bound cost: round 1 for every trade and provider, round 2 for every trade when two providers are on (it only runs
    when both round-1 answers are valid). Input tokens from the real packet text; output tokens typical."""
    sys1, sys2 = len(SYSTEM_PROMPT) / 4.0, len(EXCHANGE_SYSTEM_PROMPT) / 4.0
    texts = [len(canonical(p)) / CHARS_PER_TOKEN for p in packets]
    two = len(providers) >= 2
    out: dict = {"providers": {}, "total_usd": 0.0, "unpriced": [], "two_rounds": two}
    for name, prov in providers.items():
        o1, src1 = typical_out_tokens(journal, name, 1)
        o2, src2 = typical_out_tokens(journal, name, 2)
        n_reuse = (reuse or {}).get(name, 0)           # --redo: valid round-1 answers kept, not paid twice
        tin1 = sum(sys1 + x for x in texts) * (len(packets) - n_reuse) / max(1, len(packets))
        tin2 = sum(sys2 + x + ROUND2_EXTRA_TOKENS for x in texts) if two else 0
        calls1, calls2 = len(packets) - n_reuse, (len(packets) if two else 0)
        tout = o1 * calls1 + o2 * calls2
        tin = int(tin1 + tin2)
        usd = prov.cost(tin, tout)
        pr = prov.prices
        out["providers"][name] = {"model": prov.model, "calls": calls1 + calls2, "tokens_in": tin, "tokens_out": tout, "usd": usd,
                                  "price_in": pr.get("in_per_mtok"), "price_out": pr.get("out_per_mtok"),
                                  "out_source": f"{src1}; round 2: {src2}", "used_today": today_used.get(name, 0),
                                  "over_budget": today_used.get(name, 0) + calls1 + calls2 > budget}
        if usd is None:
            out["unpriced"].append(name)
        else:
            out["total_usd"] += usd
    out["total_usd"] = round(out["total_usd"], 4)
    return out


def estimate_lines(e: dict, budget: int) -> list[str]:
    L = []
    for name, d in e["providers"].items():
        cost = "price not set (dynamic.prices)" if d["usd"] is None else f"about ${d['usd']:.3f} (${d['price_in']}/Mtok in, ${d['price_out']}/Mtok out)"
        L.append(f"{name} {d['model']}: up to {d['calls']} calls x typical tokens = ~{d['tokens_in']:,} in / ~{d['tokens_out']:,} out "
                 f"(output {d['out_source']}) -> {cost}")
        if d["over_budget"]:
            L.append(f"  WARNING {name}: {d['used_today']} calls already today + {d['calls']} here is over the daily budget of {budget}; "
                     "the calls beyond it are recorded as not_reviewed: budget")
    L.append(f"Estimated total: ${e['total_usd']:.3f}" + (f" (+ unpriced: {', '.join(e['unpriced'])})" if e["unpriced"] else "")
             + ("" if e["two_rounds"] else " (one reviewer: no exchange round)")
             + ". An upper bound: round 2 only runs when both round-1 answers are valid.")
    return L


# ── the per-trade table ───────────────────────────────────────────────────────────────────────────────────────
def trade_rows(journal, items: list[dict], tz: str) -> list[dict]:
    from . import score
    out = []
    for it in items:
        t, cid = it["trade"], it["trade"]["id"]
        rv = {(r["provider"], r["round"]): r for r in store.reviews_for(journal, cid)}
        ex = store.exchange_for(journal, cid)
        costs = [r["cost_usd"] for r in rv.values() if r.get("cost_usd") is not None]

        def cell(p, rnd):
            r = rv.get((p, rnd))
            if r is None:
                return "—"
            if r["action"] in ANSWERS:
                return r["action"]
            return f"{r['action']}: {score.short_reason(r.get('error'), 60)}"
        out.append({"id": cid, "symbol": t["symbol"], "side": t["side"], "entry_time": it["entry_ts"].strftime("%Y-%m-%d %H:%M"),
                    "r": float(t["r_multiple"]), "claude_r1": cell("claude", 1), "claude_r2": cell("claude", 2),
                    "openai_r1": cell("openai", 1), "openai_r2": cell("openai", 2),
                    "exchange": ("—" if ex is None else (ex["decision"] if ex["status"] == "done" else ex["status"])),
                    "cost_usd": round(sum(costs), 4) if costs else None})
    return out


def table_md(rows: list[dict]) -> list[str]:
    L = ["| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['symbol']} | {r['side']} | {r['entry_time']} | {r['r']:+.2f} | {r['claude_r1']} | {r['claude_r2']} | {r['openai_r1']} | "
                 f"{r['openai_r2']} | {r['exchange']} | {'—' if r['cost_usd'] is None else format(r['cost_usd'], '.4f')} |")
    return L


# ── the run ───────────────────────────────────────────────────────────────────────────────────────────────────
def say(*a) -> None:
    print(*a, flush=True)


async def run(cfg, book: str, n: int, out: Path, dry_run: bool = False, client=None, journal=None, providers: dict | None = None,
              redo: bool = False) -> int:
    """`client` (an OANDA-like object with `req`), `journal` and `providers` can be handed in (tests); otherwise they are made
    from the config and the environment."""
    from . import score
    tz = cfg["timezone"]
    if not (1 <= n <= MAX_TRADES):
        say(f"refused: --last must be 1 to {MAX_TRADES} (asked for {n}); the cap keeps one hand-run cheap and reviewable")
        return 2
    dyn = cfg.get("dynamic") or {}
    own_journal = journal is None
    if own_journal:
        from ..journal import Journal
        path = score.journal_path(cfg, book)
        if not Path(path).exists():
            say(f"no journal for book {book!r} at {path}")
            return 1
        journal = Journal(path)
    store.ensure_schema(journal)
    notes: list[str] = []
    if providers is None:
        providers = build_providers(dyn)
    if not dyn.get("openai_model"):
        notes.append("OpenAI is not configured (dynamic.openai_model is empty): Claude only, the exchange is skipped (as live).")
    for name in [k for k, p in providers.items() if not p.available()]:
        notes.append(f"No {providers[name].env_key} in the environment: the {name} arm is left out (no calls, no rows), the exchange is skipped.")
        providers = {k: p for k, p in providers.items() if k != name}
    if not providers:
        say("nothing to review with: no provider is configured and has its key. " + " ".join(notes))
        return 1
    for x in notes:
        say("NOTE:", x)

    trades, skipped = pick_trades(journal, cfg, n, redo)
    notes += skipped
    if not trades:
        say("no closed, unreviewed trade to backfill in book", book)
        for x in skipped:
            say(" ", x)
        return 0
    if client is None:
        from ..oanda import oanda_from_cfg
        from ..reconcile import broker_cfg
        cfg = broker_cfg(cfg)
        client = oanda_from_cfg(cfg)
    items, failed = [], []
    try:
        for t in trades:
            try:
                items.append(await rebuild(client, journal, cfg, book, t))
            except Exception as e:  # noqa: BLE001 — one trade that can't be rebuilt must not stop the others
                failed.append((t, f"{type(e).__name__}: {e}"))
                notes.append(f"{t['id']} {t['symbol']} {t['opened']}: not reviewed ({type(e).__name__}: {e})")
    finally:
        aclose = getattr(client, "aclose", None)
        if aclose:
            await aclose()
    say(f"\nBook {book}: {len(trades)} trade(s) picked (newest closed first), {len(items)} rebuilt as of their entry minute"
        + (f", {len(failed)} could not be rebuilt" if failed else "") + ".")
    for it in items:
        t = it["trade"]
        say(f"  {t['id']}  {t['symbol']:7} {t['side']:5} {it['entry_ts']:%Y-%m-%d %H:%M} NY  R {float(t['r_multiple']):+.2f}  "
            f"{t['strategy']}  (M1 {it['m1_rows']} bars, H1 {it['h1_rows']} bars, spread {it['spread']:.5g})")
    for t, why in failed:
        say(f"  {t['id']}  {t['symbol']}  SKIPPED: {why}")
    if not items:
        return 1
    runner = BackfillRunner(journal, cfg, providers)
    redo_ids = [it["trade"]["id"] for it in items if redo and it["trade"]["id"] in redoable_ids(journal)]
    reuse: dict[str, int] = {}
    if redo_ids:
        for it in items:
            if it["trade"]["id"] in redo_ids:
                for p in stored_answers(journal, it["trade"]["id"], it["packet"]["packet_hash"]):
                    if p in providers:
                        reuse[p] = reuse.get(p, 0) + 1
        say(f"--redo: {len(redo_ids)} trade(s) had a round-1 non-answer; their abstained rounds and all round-2 rows will be deleted and re-run "
            f"(valid round-1 answers kept: {', '.join(f'{k} x{v}' for k, v in reuse.items()) or 'none'}): {', '.join(redo_ids)}")
    day = trading_day(runner.now())
    est = estimate(journal, providers, [it["packet"] for it in items], {p: store.calls_on(journal, p, day) for p in providers}, runner.budget, reuse)
    say("\nCost estimate (before any call):")
    for line in estimate_lines(est, runner.budget):
        say(" ", line)
    if dry_run:
        say("\n--dry-run: nothing was called or stored.")
        return 0
    prior = prepare_redo(journal, {it["trade"]["id"]: it["packet"] for it in items if it["trade"]["id"] in redo_ids}, providers) if redo_ids else {}
    say("\nReviewing (same prompts, validation, budget and deadlines as the live gate)...")
    await runner.run([it["packet"] for it in items], prior)
    rows = trade_rows(journal, items, tz)
    actual = sum(r["cost_usd"] or 0 for r in rows)
    L = ["# Retrospective review of past trades (dynamic backfill)", "",
         f"Run {runner.now():%Y-%m-%d %H:%M} NY, book **{book}**, prompt {PROMPT_VERSION}. These {len(rows)} trades had already closed; each was rebuilt "
         "as of its entry minute from OANDA candles and reviewed through the live path. The models were not told it was a past trade. "
         "Stored as `source = 'backfill'`: **not part of the live scorecard or its decision rule; latency is not meaningful.**", ""]
    L += [f"- {x}" for x in notes] + ([""] if notes else [])
    L += ["What was fetched from OANDA per trade: M1 bid/ask candles (price BA, complete only) for the 5 days before entry up to the minute "
          "before it, and H1 mid candles for the 60 days before entry (only hours closed by the entry minute are kept). Nothing at or after "
          "the entry minute was requested or used.", ""]
    L += ["Cost estimate before the calls:", ""] + [f"- {x.strip()}" for x in estimate_lines(est, runner.budget)]
    L += ["", f"Actual cost: ${actual:.4f}", "", "## Per trade", ""] + table_md(rows) + [""]
    L += score.retro_md(score.retro_scorecard(journal, cfg, book), "##")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(L) + "\n")
    (out / "summary.json").write_text(json.dumps({"book": book, "trades": rows, "notes": notes, "estimate": est, "actual_usd": actual},
                                                 indent=1, default=str))
    say("\n" + "\n".join(table_md(rows)))
    say(f"\nActual cost ${actual:.4f}. Wrote {out / 'report.md'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--book", default="live")
    ap.add_argument("--last", type=int, default=10, help=f"how many of the latest unreviewed closed trades (max {MAX_TRADES})")
    ap.add_argument("--dry-run", action="store_true", help="fetch, build the packets, print the trades and the cost estimate, call nothing")
    ap.add_argument("--redo", action="store_true", help="also redo backfilled trades where ANY provider's round 1 is ABSTAIN / NOT_REVIEWED: valid round-1 answers are kept, the rest (and all round 2) deleted and re-run (live rows never)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    if not (1 <= a.last <= MAX_TRADES):
        say(f"refused: --last must be 1 to {MAX_TRADES} (asked for {a.last})")
        return 2
    from ..config import load_config
    cfg = load_config(a.config)
    if cfg.get("broker") == "oanda":
        from ..reconcile import broker_cfg
        cfg = broker_cfg(cfg)               # paper/live view with OANDA's instrument values (the journal was booked with them)
    return asyncio.run(run(cfg, a.book, a.last, Path(a.out), a.dry_run, redo=a.redo))


if __name__ == "__main__":
    sys.exit(main())
