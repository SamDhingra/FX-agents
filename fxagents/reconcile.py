"""Reconcile the practice-account journal with OANDA's own trade records (read-only; Oct 2026 audit F9).

    python -m fxagents.reconcile --days 14            (./fx.sh reconcile 14)

The journal is what every report, the Books page and the learner believe happened. This checks it against the broker:
  • matching — every OANDA trade the bot opens carries clientExtensions.id "fxa-<position id>-<leg>"; trades are grouped
    by position id and paired with the journal row of that id;
  • gaps — journal trades with no OANDA trade (or still open at OANDA), OANDA trades the journal never closed or never
    saw, and OANDA trades without the bot's tag (manual or foreign);
  • differences per position — entry fill, exit fill and P&L (OANDA realizedPL + financing) vs the journal, all in R
    of that trade, so a bias in how the bot books P&L shows up as an average;
  • target fills (audit F5) — targets and the 1R partial are market orders sent after a candle touched the level; the
    journal's partial / limit_exit events give the level and the fill, so their slippage in R is measured here. Trades
    from before Oct 21 2026 have no logged level for a full target exit; their partials' level is rebuilt from entry,
    initial stop and the partial's R.

Writes data/year_test/reconcile/report.md + summary.json (./fx.sh publish). Everything is in R, counts and short
journal ids — no account id, no currency amounts, no position sizes, so it is safe on the public results branch.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

TAG = "fxa-"


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def broker_cfg(cfg):
    """The config as the running app sees it: with broker = oanda the instruments carry OANDA's CFD values
    (multiplier 1 …), not the futures defaults (gold 10, NDQ 2, US30 0.5). Reports and repairs must use these."""
    import copy

    from .config import apply_broker
    if cfg.get("_broker_applied") or cfg.get("broker") != "oanda":
        return cfg
    c = copy.deepcopy(cfg)
    if c.get("mode") not in ("paper", "live"):
        c["mode"] = "paper"                     # the practice account's view, whatever the file's default mode
    apply_broker(c)
    return c


def pos_id(trade: dict) -> str | None:
    """Journal position id from the bot's client extension ("fxa-<id>-<leg>"), else None."""
    cid = ((trade.get("clientExtensions") or {}).get("id") or "")
    if not cid.startswith(TAG):
        return None
    rest = cid[len(TAG):]
    return rest.rsplit("-", 1)[0] if "-" in rest else rest


async def fetch_trades(client, since: pd.Timestamp, state: str = "CLOSED", page: int = 500) -> list[dict]:
    """OANDA trades in `state` opened at/after `since`, newest first, paged with beforeID."""
    out, before = [], None
    for _ in range(40):
        p = {"state": state, "count": page}
        if before:
            p["beforeID"] = before
        res = await client.req("GET", client.acct("/trades"), params=p)
        tr = res.get("trades") or []
        if not tr:
            break
        old = False
        for t in tr:
            if pd.Timestamp(t.get("openTime")) < since:
                old = True
                continue
            out.append(t)
        if old or len(tr) < page:
            break
        before = tr[-1]["id"]
    return out


async def fx_table(client, since: pd.Timestamp):
    """USD per unit of the account currency at a time, from OANDA's daily USD_<ccy> mid candles (None for USD)."""
    acct = (await client.req("GET", client.acct("/summary")))["account"]
    ccy = acct.get("currency", "USD")
    if ccy == "USD":
        return None
    res = await client.req("GET", f"/v3/instruments/USD_{ccy}/candles",
                           params={"granularity": "D", "price": "M", "from": (since - pd.Timedelta(days=5)).isoformat()})
    pts = sorted((pd.Timestamp(c["time"]), 1.0 / _f(c["mid"]["c"])) for c in res.get("candles", []) if _f(c["mid"]["c"]))
    if not pts:
        raise SystemExit(f"no USD_{ccy} candles — cannot convert OANDA's {ccy} P&L to the journal's USD")
    ts = [p[0] for p in pts]

    def at(t: pd.Timestamp) -> float:
        k = max(0, int(np.searchsorted(ts, t, side="right")) - 1)
        return pts[k][1]
    at.ccy = ccy
    return at


def load_journal(db: str, since: pd.Timestamp) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM trades WHERE opened >= ? ORDER BY opened",
                                         (since.isoformat(),))]
    con.close()
    return rows


def _risk_ccy(row: dict, mult: float) -> float:
    r, pl = row.get("r_multiple"), row.get("realized")
    if r and pl and abs(r) > 1e-6:
        return abs(pl / r)                                   # the journal's own denominator (same currency as P&L)
    return abs(_f(row.get("qty_initial")) * abs(_f(row.get("entry")) - _f(row.get("initial_stop"))) * mult)


def target_fills(rows: list[dict]) -> list[dict]:
    """Slippage of target-type exits in R (positive = filled better than the level)."""
    out = []
    for r in rows:
        try:
            ev = json.loads(r.get("events") or "[]")
        except ValueError:
            continue
        side = 1 if r["side"] == "LONG" else -1
        e0, s0 = _f(r.get("entry")), _f(r.get("initial_stop"))
        risk = abs(e0 - s0)
        if risk <= 0:
            continue
        for x in ev:
            if x.get("kind") not in ("partial", "limit_exit") or x.get("price") is None:
                continue
            lvl = x.get("level")
            if lvl is None and x.get("kind") == "partial" and x.get("r") is not None:
                lvl = e0 + side * _f(x["r"]) * risk             # older trades: rebuilt from entry, stop and R
            if lvl is None:
                continue
            out.append({"id": r["id"], "symbol": r["symbol"], "kind": x["kind"], "ts": x.get("ts"),
                        "slip_r": round(side * (_f(x["price"]) - _f(lvl)) / risk, 4)})
    return out


OANDA_NAMES = {"NDQ": "NAS100_USD", "US30": "US30_USD", "XAUUSD": "XAU_USD", "SPX": "SPX500_USD", "BTCUSD": "BTC_USD"}


def _inst_of(cfg, sym: str) -> str:
    from .oanda import _inst
    try:
        return _inst(cfg, sym)
    except (Exception, SystemExit):  # noqa: BLE001 — not configured here: OANDA's usual name
        return OANDA_NAMES.get(sym, sym)


def reconcile(cfg, journal: list[dict], closed: list[dict], open_: list[dict], fx=None, match_s: float = 120.0) -> dict:
    """fx(close_time) → USD per unit of the account currency (OANDA's realizedPL is in the account currency, the
    journal books in USD, the instruments' quote currency). None = the account is in USD."""
    by_pos: dict[str, list[dict]] = {}
    untagged = []
    for t in closed + open_:
        pid = pos_id(t)
        if pid:
            by_pos.setdefault(pid, []).append(t)
        else:
            untagged.append(t)
    journal = [r for r in journal if r.get("status") != "void"]          # voided rows hold no trade of their own
    jrows = {r["id"]: r for r in journal}
    # trades from before the bot tagged its orders (≈ Oct 8 2026): pair by instrument and open time
    by_time = set()
    left = []
    free = [r for r in journal if r["id"] not in by_pos]
    for t in untagged:
        ot = pd.Timestamp(t.get("openTime"))
        best, gap = None, match_s
        for r in free:
            if _inst_of(cfg, r["symbol"]) != t.get("instrument") or r["id"] in by_pos:
                continue
            g = abs((pd.Timestamp(r["opened"]) - ot).total_seconds())
            if g <= gap:
                best, gap = r, g
        if best is None:
            left.append(t)
        else:
            by_pos[best["id"]] = [t]
            by_time.add(best["id"])
    untagged = left
    pairs, journal_only, broker_only, state_mismatch = [], [], [], []
    for pid, trs in by_pos.items():
        row = jrows.get(pid)
        if row is None:
            broker_only.append({"id": pid, "instrument": trs[0].get("instrument"), "legs": len(trs),
                                "open_at_oanda": any(t.get("state") == "OPEN" for t in trs)})
            continue
        b_open = any(t.get("state") == "OPEN" for t in trs)
        if (row["status"] == "closed") == b_open:
            state_mismatch.append({"id": pid, "symbol": row["symbol"], "journal": row["status"],
                                   "oanda": "OPEN" if b_open else "CLOSED"})
        if row["status"] != "closed" or b_open:
            continue
        ic = cfg["instruments"].get(row["symbol"], {})
        mult = _f(ic.get("multiplier")) or 1.0
        rc = _risk_ccy(row, mult)
        risk_px = abs(_f(row["entry"]) - _f(row["initial_stop"]))
        side = 1 if row["side"] == "LONG" else -1
        units = [abs(_f(t.get("initialUnits"))) for t in trs]
        tot = sum(units) or 1.0
        b_entry = sum(_f(t.get("price")) * u for t, u in zip(trs, units)) / tot
        b_exit = sum(_f(t.get("averageClosePrice")) * u for t, u in zip(trs, units)) / tot
        rate = 1.0
        if fx is not None:
            ct = max((pd.Timestamp(t["closeTime"]) for t in trs if t.get("closeTime")), default=pd.Timestamp(row["closed"]))
            rate = float(fx(ct))
        b_pl = rate * sum(_f(t.get("realizedPL")) + _f(t.get("financing")) + _f(t.get("dividendAdjustment")) for t in trs)
        j_pl = _f(row.get("realized"))
        q = abs(_f(row.get("qty_gross")))
        j_exit = (_f(row.get("avg_entry") or row["entry"]) + side * (j_pl + _f(row.get("commissions"))) / (q * mult)
                  if q else _f(row.get("exit_price")))          # the journal's AVERAGE exit (partials included)
        pairs.append({
            "id": pid, "symbol": row["symbol"], "strategy": row["strategy"], "opened": row["opened"],
            "exit_reason": row.get("exit_reason"), "journal_r": row.get("r_multiple"),
            "oanda_r": round(b_pl / rc, 3) if rc else None,
            "pl_diff_r": round((b_pl - j_pl) / rc, 3) if rc else None,
            "entry_diff_r": round(side * (_f(row.get("avg_entry") or row["entry"]) - b_entry) / risk_px, 3) if risk_px else None,
            "exit_diff_r": round(side * (b_exit - j_exit) / risk_px, 3) if risk_px and j_exit else None,
            "matched_by": "open time" if pid in by_time else "tag",
            "units_match": abs(tot - abs(_f(row.get("qty_gross")))) <= 1e-6 * max(1.0, tot),
        })
    for r in journal:
        if r["id"] not in by_pos:
            journal_only.append({"id": r["id"], "symbol": r["symbol"], "strategy": r["strategy"], "status": r["status"],
                                 "opened": r["opened"]})
    fills = target_fills([r for r in journal if r["status"] == "closed"])
    return {"pairs": pairs, "journal_only": journal_only, "broker_only": broker_only, "state_mismatch": state_mismatch,
            "untagged": [{"instrument": t.get("instrument"), "opened": t.get("openTime"), "state": t.get("state")}
                         for t in untagged], "target_fills": fills}


def _stat(xs) -> dict:
    xs = [x for x in xs if x is not None and np.isfinite(x)]
    if not xs:
        return {"n": 0}
    a = np.asarray(xs, float)
    return {"n": len(a), "mean": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
            "worst": round(float(a.min()), 4), "sum": round(float(a.sum()), 3)}


def summarize(res: dict) -> dict:
    p = res["pairs"]
    jr = sum(x["journal_r"] or 0 for x in p)
    br = sum(x["oanda_r"] or 0 for x in p)
    return {"matched": len(p), "matched_by_open_time": sum(x.get("matched_by") == "open time" for x in p),
            "journal_only": len(res["journal_only"]), "broker_only": len(res["broker_only"]),
            "state_mismatch": len(res["state_mismatch"]), "untagged": len(res["untagged"]),
            "journal_total_r": round(jr, 2), "oanda_total_r": round(br, 2),
            "pl_diff_r": _stat([x["pl_diff_r"] for x in p]), "entry_diff_r": _stat([x["entry_diff_r"] for x in p]),
            "exit_diff_r": _stat([x["exit_diff_r"] for x in p]),
            "units_mismatch": sum(not x["units_match"] for x in p),
            "target_slip_r": _stat([x["slip_r"] for x in res["target_fills"]]),
            "partial_slip_r": _stat([x["slip_r"] for x in res["target_fills"] if x["kind"] == "partial"]),
            "full_target_slip_r": _stat([x["slip_r"] for x in res["target_fills"] if x["kind"] == "limit_exit"])}


def report(res: dict, s: dict, days: int) -> str:
    L = [f"# Journal vs OANDA — last {days} days", "",
         f"Matched positions {s['matched']} ({s.get('matched_by_open_time', 0)} by instrument + open time: trades from "
         f"before the bot tagged its orders) · journal-only {s['journal_only']} · OANDA-only {s['broker_only']} · "
         f"open/closed disagree {s['state_mismatch']} · untagged OANDA trades {s['untagged']} · unit mismatches "
         f"{s['units_mismatch']}", "",
         f"Total on matched positions: journal **{s['journal_total_r']:+.2f}R**, OANDA **{s['oanda_total_r']:+.2f}R** "
         "(OANDA = realizedPL + financing, converted from the account currency to USD at that day's rate, in each "
         "trade's own R — so the P&L difference holds financing and OANDA's conversion, not just fills).", "",
         "| difference (R per position, OANDA − journal) | n | mean | median | worst | sum |", "|---|---|---|---|---|---|"]
    for k, name in (("pl_diff_r", "P&L"), ("entry_diff_r", "entry fill (+ = OANDA better)"),
                    ("exit_diff_r", "exit fill (+ = OANDA better)")):
        x = s[k]
        L.append(f"| {name} | {x['n']} | " + (" | ".join(f"{x[c]:+.4f}" if c != "sum" else f"{x[c]:+.3f}"
                                                         for c in ("mean", "median", "worst", "sum")) if x["n"] else "– | – | – | –") + " |")
    L += ["", "## Target fills (market order after the level was touched; + = better than the level)", "",
          "| kind | n | mean R | median R | worst R | total R |", "|---|---|---|---|---|---|"]
    for k, name in (("partial_slip_r", "1R partial"), ("full_target_slip_r", "full target"), ("target_slip_r", "all")):
        x = s[k]
        L.append(f"| {name} | {x['n']} | " + (f"{x['mean']:+.4f} | {x['median']:+.4f} | {x['worst']:+.4f} | {x['sum']:+.3f}"
                                              if x["n"] else "– | – | – | –") + " |")
    L.append("")
    L.append("A clearly negative mean here is what resting take-profit orders at the level would save (audit F5).")
    for title, key, cols in (("Journal trades with no OANDA trade", "journal_only", ("id", "symbol", "strategy", "status", "opened")),
                             ("OANDA trades the journal doesn't have", "broker_only", ("id", "instrument", "legs", "open_at_oanda")),
                             ("Open at one side, closed at the other", "state_mismatch", ("id", "symbol", "journal", "oanda")),
                             ("OANDA trades without the bot's tag", "untagged", ("instrument", "opened", "state"))):
        rows = res[key]
        if not rows:
            continue
        L += ["", f"## {title} ({len(rows)})", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        L += ["| " + " | ".join(str(r.get(c)) for c in cols) + " |" for r in rows[:50]]
    big = sorted([x for x in res["pairs"] if x["pl_diff_r"] is not None], key=lambda x: -abs(x["pl_diff_r"]))[:15]
    if big:
        L += ["", "## Largest P&L differences", "", "| id | symbol | strategy | opened | exit | journal R | OANDA R | diff R |",
              "|---|---|---|---|---|---|---|---|"]
        L += [f"| {x['id']} | {x['symbol']} | {x['strategy']} | {x['opened'][:16]} | {x['exit_reason']} | "
              f"{x['journal_r']} | {x['oanda_r']} | {x['pl_diff_r']:+.3f} |" for x in big]
    return "\n".join(L) + "\n"


async def run(cfg, days: int, client=None, out_dir: str = "data/year_test/reconcile") -> dict:
    from .oanda import oanda_from_cfg
    cfg = broker_cfg(cfg)
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    own = client is None
    client = client or oanda_from_cfg(cfg)
    try:
        closed = await fetch_trades(client, since, "CLOSED")
        open_ = await fetch_trades(client, since, "OPEN")
        fx = await fx_table(client, since)
    finally:
        if own:
            await client.aclose()
    journal = load_journal(cfg["storage"]["db_path"], since)
    res = reconcile(cfg, journal, closed, open_, fx=fx)
    s = summarize(res)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report(res, s, days))
    (out / "summary.json").write_text(json.dumps({"days": days, **s}, indent=1))
    return {"summary": s, **res}


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    r = asyncio.run(run(cfg, a.days))
    print((Path("data/year_test/reconcile") / "report.md").read_text())
    return r


if __name__ == "__main__":
    main()
