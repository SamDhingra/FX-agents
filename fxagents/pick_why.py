"""Why doesn't the practice account's hourly pick choose a strategy? (Nov 4 2026, Sam: S/R rejection.) Read-only.

    python -m fxagents.pick_why [name=sr_rejection] [--days 7]        (./fx.sh pickwhy [name] [days])

The hourly pick (agents/trading.py SelectorAgent) rates, every hour and per instrument, each live strategy of the
account's book: combined = w × (Jev confidence × Jev value + (1 − confidence) × quant) + (1 − w) × quant, then keeps the
best ONE per entry timeframe if combined ≥ jev.min_select_score and Jev's trade_ok ≥ 0.4. Every rating is journaled
(decisions, kind strategy_rating) with its inputs, so this replays the same arithmetic per hour and prints:
  1. the account's book: every version of the strategy and its status (live / retired / candidate …);
  2. per hour it was rated: its combined score, rank in its timeframe, and what was picked instead (or why nothing was);
  3. a summary: hours rated, hours picked, the most common reasons and winners.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

from .config import load_config


def quant(c: dict, min_trades: int) -> float:
    """The selector's own statistical score of a candidate (SelectorAgent.select)."""
    rec = (c.get("recent") or {}).get("exp", 0.0) or 0.0
    lr = c.get("live_trades") or {}
    q = 1 / (1 + math.exp(-(3.0 * float(c.get("this_hour_exp_shrunk", 0.0)) + 1.0 * float(rec)
                            + (0.5 * float(lr.get("expectancy", 0.0)) if (lr.get("n") or 0) >= 5 else 0))))
    if ((c.get("overall") or {}).get("n") or 0) < min_trades:
        q *= 0.6
    return q


def hour_rows(inputs: dict, outputs: dict, cfg) -> tuple[list[dict], float]:
    w, mins = float(cfg["jev"]["weight"]), int(cfg["selector"]["min_trades_for_stats"])
    rows = []
    for k, c in (inputs.get("strategies") or {}).items():
        a = outputs.get(k) or {}
        q = quant(c, mins)
        conf, jv = float(a.get("confidence", 0.0)), float(a.get("value", q))
        rows.append({"id": c.get("name"), "tf": c.get("timeframe"), "combined": w * (conf * jv + (1 - conf) * q) + (1 - w) * q,
                     "jev": jv, "quant": q, "hour_exp": c.get("this_hour_exp_shrunk"),
                     "n": (c.get("overall") or {}).get("n"), "exp": (c.get("overall") or {}).get("expectancy")})
    t = (outputs.get("trade_ok") or {}).get("value", 1.0)
    return sorted(rows, key=lambda r: -r["combined"]), float(t)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Why doesn't the hourly pick choose a strategy? (read-only)")
    ap.add_argument("name", nargs="?", default="sr_rejection")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(argv)
    cfg = load_config("config.yaml")
    db = Path(cfg["storage"]["db_path"])
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    print(f"# Why doesn't the hourly pick choose {a.name}?\n")
    print("## The account's strategy book\n")
    vers = con.execute("SELECT id, status, updated, notes FROM strategy_versions WHERE id LIKE ? ORDER BY updated",
                       (f"%{a.name}%",)).fetchall()
    for v in vers:
        print(f"- {v['id']}: **{v['status']}** (updated {str(v['updated'])[:16]}){' — ' + v['notes'][:140] if v['notes'] else ''}")
    if not vers:
        print(f"- no version of {a.name} in the account's book")
    since = (pd.Timestamp.now(tz="America/New_York") - pd.Timedelta(days=a.days)).isoformat()
    dec = con.execute("SELECT ts, symbol, source, inputs, outputs FROM decisions WHERE kind='strategy_rating' AND ts >= ? "
                      "ORDER BY ts", (since,)).fetchall()
    trades = con.execute("SELECT opened, symbol, strategy, r_multiple FROM trades WHERE strategy LIKE ? ORDER BY opened DESC LIMIT 5",
                         (f"%{a.name}%",)).fetchall()
    con.close()
    minsel = float(cfg["jev"]["min_select_score"])
    top = int(cfg["selector"]["top_n_per_tf"])
    print(f"\n## Hour by hour, last {a.days} days ({len(dec)} hourly ratings; picked = best per timeframe, "
          f"score ≥ {minsel}, trade_ok ≥ 0.4)\n")
    rated = picked = 0
    why, winners, absent = Counter(), Counter(), Counter()
    for d in dec:
        inputs, outputs = json.loads(d["inputs"] or "{}"), json.loads(d["outputs"] or "{}")
        rows, tok = hour_rows(inputs, outputs, cfg)
        mine = [r for r in rows if a.name in str(r["id"])]
        if not mine:
            absent[d["symbol"]] += 1
            continue
        for m in mine:
            rated += 1
            same = [r for r in rows if r["tf"] == m["tf"]]
            rank = [r["id"] for r in same].index(m["id"])
            if tok < 0.4:
                reason, best = f"trade_ok {tok:.2f} < 0.4 (whole instrument sat out)", None
            elif rank >= top:
                best = same[0]
                reason = f"rank {rank + 1} of {len(same)} on {m['tf']}: {best['id']} scored {best['combined']:.3f}"
                winners[best["id"]] += 1
            elif m["combined"] < minsel:
                reason, best = f"best on {m['tf']} but {m['combined']:.3f} < {minsel}", None
            else:
                reason, best = "PICKED", None
                picked += 1
            why[reason.split(":")[0] if reason.startswith("rank") else reason.split(" (")[0].split(" but")[0]] += 1
            print(f"- {str(d['ts'])[:16]} {d['symbol']} h{inputs.get('hour_ny')} [{d['source']}] {m['id']} "
                  f"score {m['combined']:.3f} (Jev {m['jev']:.2f}, stats {m['quant']:.2f}, hour exp {m['hour_exp']}, "
                  f"n {m['n']}, exp {m['exp']}) → {reason}")
    print(f"\n## Summary\n\n- rated {rated} times, picked {picked}")
    for k, v in why.most_common(6):
        print(f"- {v}× {k}")
    if winners:
        print("- picked instead: " + ", ".join(f"{k} ({v})" for k, v in winners.most_common(6)))
    if absent:
        print("- hours where it was NOT among the candidates at all (not live in the book, or no stats for that "
              "instrument): " + ", ".join(f"{k} {v}" for k, v in absent.items()))
    print("\n## Its last trades on the account\n")
    for t in trades:
        print(f"- {str(t['opened'])[:16]} {t['symbol']} {t['strategy']} {t['r_multiple']}")



def main(argv=None):
    """Prints the report, or with --publish writes it to data/year_test/pick_why_<name>/report.md (for ./fx.sh publish)."""
    import contextlib
    import io
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--publish" not in argv:
        return _main(argv)
    argv.remove("--publish")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _main(argv)
    name = next((x for x in argv if not x.startswith("-") and not x.isdigit()), "sr_rejection")
    out = Path(f"data/year_test/pick_why_{name}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(buf.getvalue())
    print(f"wrote {out / 'report.md'} ({len(buf.getvalue().splitlines())} lines)")


if __name__ == "__main__":
    main()
