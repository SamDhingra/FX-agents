"""Repair journal rows stuck at status 'open' (dry run by default; nothing is changed without --apply).

    python -m fxagents.journal_repair                 (./fx.sh repair)          → shows the plan
    python -m fxagents.journal_repair --apply         (./fx.sh repair --apply)  → backs up each journal, then applies

Why rows get stuck: before Oct 21 2026 the paper books kept positions only in memory, so every update dropped their
open trades and the journal rows stayed 'open' for ever; on the practice account, a few early-October positions were
lost the same way (the reconciliation report found them: journal open, OANDA closed).

What it does — only to rows opened before the current trading day (17:00 New York roll), and never to a position the
running app still holds (the account's runtime_state.json or a paper book's *_runtime.json):
  practice account   the row's OANDA trade(s) (by the bot's tag, else instrument + open time ≤ 2 min) are CLOSED at
                     OANDA → the row is closed with OANDA's result: average close price, P&L (realizedPL + financing,
                     converted to USD as the journal books it) and its R; exit reason 'reconciled_at_oanda'.
                     If an 'orphan:unmanaged' row already booked that same OANDA trade, the stuck row is a duplicate →
                     status 'void'. Still OPEN at OANDA → left alone (it is real). No OANDA trade found → 'void'.
  paper books        their outcome was never recorded and can't be known honestly → status 'void' (excluded from every
                     statistic, kept in the table with a note). Books that hold overnight (daily_rsi2_adx2) are skipped.
'void' rows are not counted anywhere (every statistic reads status = 'closed'). A copy of each journal is saved as
<journal>.bak-<timestamp> before anything is written.
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import shutil
import sqlite3
import time
from pathlib import Path

import pandas as pd

from .reconcile import _f, _inst_of, fetch_trades, fx_table, pos_id

SKIP_BOOKS = ("daily_rsi2_adx2",)        # positions held overnight on purpose; their own trader re-adopts them


def roll_start(now: pd.Timestamp, tz: str) -> pd.Timestamp:
    """Start of the current trading day: the last 17:00 New York."""
    n = now.tz_convert(tz)
    r = n.normalize() + pd.Timedelta(hours=17)
    return r if n >= r else r - pd.Timedelta(days=1)


def held_ids(paths) -> set[str]:
    out = set()
    for p in paths:
        try:
            d = json.loads(Path(p).read_text())
            out |= {x["id"] for x in d.get("positions", [])}
        except (OSError, ValueError, KeyError):
            continue
    return out


def stale_rows(db: str, before: pd.Timestamp, held: set[str]) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM trades WHERE status='open'")]
    finally:
        con.close()
    return [r for r in rows if r["id"] not in held and pd.Timestamp(r["opened"]) < before]


def plan_account(cfg, rows: list[dict], closed: list[dict], open_: list[dict], journal_all: list[dict], fx) -> list[dict]:
    by_pos: dict[str, list[dict]] = {}
    untagged = []
    for t in closed + open_:
        pid = pos_id(t)
        (by_pos.setdefault(pid, []) if pid else untagged).append(t)
    orphans = [r for r in journal_all if (r.get("strategy") or "").startswith("orphan")]
    out = []
    for r in rows:
        trs = by_pos.get(r["id"])
        if not trs:                                     # before order tagging: instrument + open time
            ot = pd.Timestamp(r["opened"])
            near = [t for t in untagged if t.get("instrument") == _inst_of(cfg, r["symbol"])
                    and abs((pd.Timestamp(t["openTime"]) - ot).total_seconds()) <= 120]
            trs = sorted(near, key=lambda t: abs((pd.Timestamp(t["openTime"]) - ot).total_seconds()))[:1]
        if not trs:
            out.append({"id": r["id"], "action": "void", "why": "no OANDA trade found for this journal row"})
            continue
        if any(t.get("state") == "OPEN" for t in trs):
            out.append({"id": r["id"], "action": "keep", "why": "still open at OANDA"})
            continue
        dup = [o for o in orphans if o["symbol"] == r["symbol"] and o["status"] == "closed"
               and any(abs((pd.Timestamp(o["opened"]) - pd.Timestamp(t["openTime"])).total_seconds()) <= 2 for t in trs)]
        if dup:
            out.append({"id": r["id"], "action": "void", "why": f"duplicate: orphan row {dup[0]['id']} booked this OANDA trade"})
            continue
        units = [abs(_f(t.get("initialUnits"))) for t in trs]
        tot = sum(units) or 1.0
        exit_px = sum(_f(t.get("averageClosePrice")) * u for t, u in zip(trs, units)) / tot
        ct = max(pd.Timestamp(t["closeTime"]) for t in trs if t.get("closeTime")) if any(t.get("closeTime") for t in trs) \
            else pd.Timestamp(r["opened"])
        rate = float(fx(ct)) if fx else 1.0
        pl = rate * sum(_f(t.get("realizedPL")) + _f(t.get("financing")) + _f(t.get("dividendAdjustment")) for t in trs)
        mult = _f(cfg["instruments"].get(r["symbol"], {}).get("multiplier")) or 1.0
        risk = abs(_f(r.get("qty_initial")) * (_f(r["entry"]) - _f(r["initial_stop"])) * mult)
        out.append({"id": r["id"], "action": "close", "why": "closed at OANDA", "closed": ct.tz_convert(cfg["timezone"]).isoformat(),
                    "exit_price": round(exit_px, 6), "realized": round(pl, 2),
                    "r_multiple": round(pl / risk, 3) if risk else None})
    return out


def apply(db: str, plan: list[dict]) -> int:
    todo = [p for p in plan if p["action"] in ("close", "void")]
    if not todo:
        return 0
    shutil.copy2(db, f"{db}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    con = sqlite3.connect(db)
    try:
        for p in todo:
            if p["action"] == "close":
                con.execute("UPDATE trades SET status='closed', closed=?, exit_price=?, realized=?, r_multiple=?, "
                            "exit_reason='reconciled_at_oanda', notes=? WHERE id=? AND status='open'",
                            (p["closed"], p["exit_price"], p["realized"], p["r_multiple"],
                             "journal repair: result from OANDA's trade record", p["id"]))
            else:
                con.execute("UPDATE trades SET status='void', exit_reason='void', notes=? WHERE id=? AND status='open'",
                            (f"journal repair: {p['why']}", p["id"]))
        con.commit()
    finally:
        con.close()
    return len(todo)


async def run(cfg, do_apply: bool, client=None, now: pd.Timestamp | None = None) -> dict:
    tz = cfg["timezone"]
    now = now or pd.Timestamp.now(tz="UTC")
    before = roll_start(now, tz)
    main_db = cfg["storage"]["db_path"]
    root = Path(main_db).parent
    held = held_ids([root / "runtime_state.json", *glob.glob(str(root / "*_runtime.json"))])
    report: dict = {"before": before.isoformat(), "books": {}}
    # practice account
    rows = stale_rows(main_db, before, held)
    if rows:
        from .oanda import oanda_from_cfg
        own = client is None
        client = client or oanda_from_cfg(cfg)
        try:
            since = min(pd.Timestamp(r["opened"]) for r in rows) - pd.Timedelta(days=1)
            closed = await fetch_trades(client, since, "CLOSED")
            open_ = await fetch_trades(client, since, "OPEN")
            fx = await fx_table(client, since)
        finally:
            if own:
                await client.aclose()
        con = sqlite3.connect(main_db); con.row_factory = sqlite3.Row
        allrows = [dict(r) for r in con.execute("SELECT * FROM trades WHERE opened >= ?", (since.isoformat(),))]
        con.close()
        plan = plan_account(cfg, rows, closed, open_, allrows, fx)
    else:
        plan = []
    report["books"]["live"] = {"db": main_db, "plan": plan}
    # paper books
    for db in sorted(glob.glob(str(root / "journal_*.sqlite"))):
        book = Path(db).stem[len("journal_"):]
        if book in SKIP_BOOKS:
            continue
        plan = [{"id": r["id"], "action": "void", "symbol": r["symbol"], "strategy": r["strategy"], "opened": r["opened"],
                 "why": "paper position lost in a restart before Oct 21 2026; outcome never recorded"}
                for r in stale_rows(db, before, held)]
        report["books"][book] = {"db": db, "plan": plan}
    if do_apply:
        for b in report["books"].values():
            b["applied"] = apply(b["db"], b["plan"])
    return report


def text(rep: dict, applied: bool) -> str:
    L = [f"Journal repair — rows still 'open' that were opened before {rep['before'][:16]} and aren't held by the app",
         "(APPLIED; backups saved next to each journal)" if applied else "(dry run — nothing changed; add --apply)", ""]
    for book, b in rep["books"].items():
        plan = b["plan"]
        if not plan:
            L.append(f"{book}: nothing to repair")
            continue
        n = {a: sum(p["action"] == a for p in plan) for a in ("close", "void", "keep")}
        L.append(f"{book}: {len(plan)} stuck row(s) — close with OANDA's result {n['close']}, void {n['void']}, keep {n['keep']}")
        for p in plan:
            extra = f" → {p['r_multiple']:+.3f}R at {p['exit_price']}" if p["action"] == "close" and p.get("r_multiple") is not None else ""
            L.append(f"  {p['id']}  {p['action']:<5} {p['why']}{extra}")
    return "\n".join(L)


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser(description="Repair journal rows stuck at 'open' (dry run unless --apply).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    rep = asyncio.run(run(cfg, a.apply))
    print(text(rep, a.apply))
    return rep


if __name__ == "__main__":
    main()
