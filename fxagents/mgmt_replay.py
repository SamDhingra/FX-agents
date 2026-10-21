"""Replay the trades the bot ACTUALLY took under different trade-management rules (read-only).

    python -m fxagents.mgmt_replay --days 7                (./fx.sh mgmtreplay 7)
    python -m fxagents.mgmt_replay --days 7 --books live playbook

For every closed intraday trade in the journals (the practice account and each paper book) over the last N days:
the same entry minute, side and initial stop, replayed on OANDA's real 1-minute bid/ask candles with the backtest
engine (fxagents/bt/engine.py — the same fills, slippage and same-minute rules as the Backtester), once per rule:

  actual_exit   full size held to the minute the trade really closed (no partial) — shows what partials cost or saved
  stop_only     the initial stop only; out at 15:50 New York or after 4 hours (the bot's limits)
  target_1r / target_2r / target_3r     a fixed full target
  be1           stop to entry + 0.1R once +1R is reached
  part1_2r      half off at +1R, stop to +0.1R, rest to 2R
  bot_approx    half off at +1R, stop to +0.1R, then trail 1R behind from +2R — close to the bot's live rule, so on
                the practice account it is the FIDELITY check (Oct 21 2026: +6.48R replayed vs +6.49R recorded)
  trail1        no target; once +1R, trail the stop 1R behind the best price
  cut15 / cut30 out if the trade isn't above 0R after 15 / 30 minutes (2R target otherwise)
Every rule also stops at 15:50 or 4 hours. Results in R per trade, before the 1% CAD conversion (as the journal).

Writes data/year_test/mgmt_replay/report.md + summary.json (published with ./fx.sh publish). No orders, no account
data — only the journals on disk and OANDA's public candle endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .bt import Costs, Exits, Signal, Strategy, data, engine

NY = "America/New_York"
BASE = dict(flat_at=950, max_hold_min=240)
RULES = {
    "actual_exit": dict(BASE),
    "stop_only": dict(BASE),
    "target_1r": dict(BASE, target_r=1.0),
    "target_2r": dict(BASE, target_r=2.0),
    "target_3r": dict(BASE, target_r=3.0),
    "be1": dict(BASE, be_at_r=1.0, be_lock_r=0.1),
    "part1_2r": dict(BASE, partials=[(1.0, 0.5, 0.1)], target_r=2.0),
    "bot_approx": dict(BASE, partials=[(1.0, 0.5, 0.1)], trail={"kind": "gap_r", "gap": 1.0}, trail_after_r=2.0),
    "trail1": dict(BASE, trail={"kind": "gap_r", "gap": 1.0}, trail_after_r=1.0),
    "cut15": dict(BASE, time_stop=(15, 0.0), target_r=2.0),
    "cut30": dict(BASE, time_stop=(30, 0.0), target_r=2.0),
}
LABEL = {"actual_exit": "full size to the real exit time", "stop_only": "stop only, hold to 15:50 / 4h",
         "target_1r": "fixed 1R target", "target_2r": "fixed 2R target", "target_3r": "fixed 3R target",
         "be1": "breakeven (+0.1R) at +1R", "part1_2r": "half at 1R, stop +0.1R, rest 2R",
         "bot_approx": "half at 1R, stop +0.1R, trail 1R from +2R (≈ bot)", "trail1": "trail 1R behind from +1R, no target",
         "cut15": "cut if not positive after 15 min, else 2R", "cut30": "cut if not positive after 30 min, else 2R"}


class OneTrade(Strategy):
    """Holds the replayed trade's signal; the engine does the rest."""
    name, news_block, entry_windows, max_per_day = "replay", None, None, None
    costs = Costs(cad=False)

    def __init__(self, sig):
        super().__init__()
        self.sig = sig

    def signals(self, m):
        return [self.sig]


def journals(cfg) -> dict[str, str]:
    from .agents.setup_first import shadow_db_for, shadow_modes
    out = {"live": cfg["storage"]["db_path"]}
    for i, mode in enumerate(shadow_modes(cfg)):
        out[mode] = shadow_db_for(cfg, mode, i == 0)
    return {k: v for k, v in out.items() if Path(v).exists()}


def load_trades(paths: dict[str, str], since: pd.Timestamp) -> list[dict]:
    rows = []
    for book, p in paths.items():
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT id, symbol, side, strategy, opened, closed, entry, initial_stop, r_multiple, "
                             "exit_reason, tf FROM trades WHERE status='closed' AND r_multiple IS NOT NULL"):
            r = dict(r)
            o, c = pd.Timestamp(r["opened"]), pd.Timestamp(r["closed"])
            if o.tzinfo is None:
                o, c = o.tz_localize(NY), c.tz_localize(NY)
            if o < since or (c - o) > pd.Timedelta(hours=20) or not r["initial_stop"] or not r["entry"]:
                continue                                       # overnight books (daily rule) aren't intraday-managed
            rows.append({**r, "book": book, "opened": o, "closed": c})
        con.close()
    return sorted(rows, key=lambda r: r["opened"])


async def fetch(client, name: str, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    p = {"granularity": "M1", "price": "BA", "from": t0.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
         "to": t1.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")}
    cs = (await client.req("GET", f"/v3/instruments/{name}/candles", params=p)).get("candles", [])
    recs = []
    for c in cs:
        if not c.get("complete") or "bid" not in c or "ask" not in c:
            continue
        b, a = c["bid"], c["ask"]
        recs.append({"t": pd.Timestamp(c["time"]), **{f"bid_{k}": float(b[k]) for k in "ohlc"},
                     **{f"ask_{k}": float(a[k]) for k in "ohlc"}, "volume": float(c.get("volume", 0))})
    if not recs:
        return pd.DataFrame()
    return pd.DataFrame(recs).set_index("t")


def replay(tr: dict, frame: pd.DataFrame) -> dict[str, float | None]:
    m = data.from_frame(frame, symbol=tr["symbol"])
    side = 1 if tr["side"] == "LONG" else -1
    t = tr["opened"].floor("1min")
    out = {}
    for rule, ex in RULES.items():
        exit_t = int(tr["closed"].floor("1min").tz_convert("UTC").value) if rule == "actual_exit" else None
        sig = Signal(t=int(t.tz_convert("UTC").value), side=side, stop=float(tr["initial_stop"]), expire_min=3,
                     exits=ex, exit_t=exit_t)
        s = OneTrade(sig)
        s.exits = Exits()
        res = engine.simulate(s, m, controls=False)["trades"]
        out[rule] = round(float(res[0]["R"]), 3) if res else None
    return out


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["replay"].get("stop_only") is not None]
    out = {"trades": len(ok), "actual_total": round(sum(r["r_multiple"] for r in ok), 2), "rules": {}}
    for rule in RULES:
        v = [r["replay"][rule] for r in ok if r["replay"].get(rule) is not None]
        a = [r["r_multiple"] for r in ok if r["replay"].get(rule) is not None]
        if not v:
            continue
        d = np.array(v) - np.array(a)
        out["rules"][rule] = {"n": len(v), "total": round(float(np.sum(v)), 2), "avg": round(float(np.mean(v)), 3),
                              "vs_actual": round(float(np.sum(d)), 2), "better": int((d > 0.05).sum()),
                              "worse": int((d < -0.05).sum())}
    return out


def report(rows: list[dict], days: int, skipped: list[str]) -> str:
    tot = summarize(rows)
    books = sorted({r["book"] for r in rows})
    L = [f"# Trade-management replay — the bot's real trades, last {days} days",
         "",
         f"{tot['trades']} closed intraday trades across {len(books)} book(s): {', '.join(books) or '—'}. Same entry minute, "
         "side and initial stop as the journal, replayed on OANDA 1-minute bid/ask with the Backtester's engine; only the "
         "management changes. R per trade before the CAD conversion. **actual** = what the journal recorded.",
         "", "Read with care: one week is a small sample — a rule that wins here can lose next week. Use it to see *how* "
         "each rule changes outcomes (which trades it saves, which it cuts), then test the winner over years in the Backtester.",
         "", "## All books", "", table(tot), ""]
    live = [r for r in rows if r["book"] == "live"]
    fid = summarize(live)["rules"].get("bot_approx") if live else None
    if fid:
        L += [f"Fidelity: on the practice account (which runs the bot's own management), the ≈ bot rule replays to "
              f"{fid['total']:+.2f}R vs {summarize(live)['actual_total']:+.2f}R recorded. Paper books with their own exit rules "
              "(EMA cross, playbook profiles) won't match it — compare rules with each other there.", ""]
    for b in books:
        s = summarize([r for r in rows if r["book"] == b])
        L += [f"## {b}", "", table(s), ""]
    strats = sorted({str(r["strategy"]).split(":")[0] for r in rows if r.get("replay")})
    if strats:
        L += ["## By setup (total R)", "", "| setup | trades | actual | " + " | ".join(RULES) + " |", "|" + "---|" * (3 + len(RULES))]
        for st in strats:
            sub = [r for r in rows if str(r["strategy"]).split(":")[0] == st and r.get("replay")]
            L.append(f"| {st} | {len(sub)} | {sum(r['r_multiple'] for r in sub):+.2f} | " + " | ".join(
                f"{sum(r['replay'][k] for r in sub if r['replay'].get(k) is not None):+.2f}" for k in RULES) + " |")
        L.append("")
    L += ["## Every trade", "", "| book | opened (NY) | symbol | side | strategy | actual | " + " | ".join(RULES) + " |",
          "|" + "---|" * (6 + len(RULES))]
    for r in rows:
        L.append(f"| {r['book']} | {r['opened'].tz_convert(NY):%a %m-%d %H:%M} | {r['symbol']} | {r['side']} | {r['strategy']} | "
                 f"{r['r_multiple']:+.2f} | " + " | ".join("—" if r["replay"].get(k) is None else f"{r['replay'][k]:+.2f}"
                                                              for k in RULES) + " |")
    if skipped:
        L += ["", f"Not replayed ({len(skipped)}): " + "; ".join(skipped[:30])]
    return "\n".join(L) + "\n"


def table(s: dict) -> str:
    if not s["trades"]:
        return "No trades."
    L = ["| rule | total R | avg R | vs actual | trades better | trades worse |", "|---|---|---|---|---|---|",
         f"| **actual** (journal) | **{s['actual_total']:+.2f}** | {s['actual_total'] / s['trades']:+.3f} | — | — | — |"]
    for k, v in s["rules"].items():
        L.append(f"| {LABEL[k]} | {v['total']:+.2f} | {v['avg']:+.3f} | {v['vs_actual']:+.2f} | {v['better']} | {v['worse']} |")
    return "\n".join(L)


async def main_async(days: int, books: list[str] | None, out: Path):
    from .config import apply_broker, load_config
    from .oanda import OandaFeed, oanda_from_cfg
    cfg = load_config()
    paths = journals(cfg)
    if books:
        paths = {k: v for k, v in paths.items() if k in books}
    now = pd.Timestamp.now(tz=NY)
    rows = load_trades(paths, now.normalize() - pd.Timedelta(days=days))
    print(f"{len(rows)} closed intraday trades in {', '.join(paths)} since {days} days ago", flush=True)
    c2 = {**cfg, "mode": "paper", "broker": "oanda", "instruments": {k: dict(v) for k, v in cfg["instruments"].items()}}
    apply_broker(c2)
    client = oanda_from_cfg(c2)
    names = OandaFeed(c2, None, None, client).syms
    skipped = []
    for i, r in enumerate(rows):
        t0 = r["opened"] - pd.Timedelta(minutes=10)
        t1 = min(r["opened"] + pd.Timedelta(hours=5), now - pd.Timedelta(minutes=1))   # 4h max hold + margin
        try:
            f = await fetch(client, names.get(r["symbol"], r["symbol"]), t0, t1)
        except Exception as e:  # noqa: BLE001
            f = pd.DataFrame()
            print(f"  {r['symbol']} {r['opened']:%m-%d %H:%M}: {e}", flush=True)
        if f.empty or f.index[0] > r["opened"] or f.index[-1] < r["opened"]:
            r["replay"] = {}
            skipped.append(f"{r['book']} {r['symbol']} {r['opened']:%m-%d %H:%M} (no candles)")
            continue
        try:
            r["replay"] = replay(r, f)
        except Exception as e:  # noqa: BLE001
            r["replay"] = {}
            skipped.append(f"{r['book']} {r['symbol']} {r['opened']:%m-%d %H:%M} ({type(e).__name__}: {e})"[:120])
        if i % 20 == 0:
            print(f"  {i + 1}/{len(rows)}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report(rows, days, skipped))
    summ = {"days": days, "all": summarize(rows), "books": {b: summarize([r for r in rows if r["book"] == b])
                                                            for b in sorted({r["book"] for r in rows})}}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    print((out / "report.md").read_text()[:4000])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--books", nargs="*")
    ap.add_argument("--out", type=Path, default=Path("data/year_test/mgmt_replay"))
    a = ap.parse_args()
    asyncio.run(main_async(a.days, a.books, a.out))


if __name__ == "__main__":
    main()
