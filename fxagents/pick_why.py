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


def quant(c: dict, min_trades: int, old_penalty: bool = False) -> float:
    """The selector's own statistical score of a candidate (agents.trading.quant_score)."""
    from .agents.trading import quant_score
    rec = c.get("recent") or {}
    return quant_score(float(c.get("this_hour_exp_shrunk", 0.0)), int((c.get("overall") or {}).get("n") or 0),
                       float(rec.get("exp", 0.0) or 0.0), int(rec.get("n") or 0), c.get("live_trades") or {}, min_trades,
                       old_penalty)


def hour_rows(inputs: dict, outputs: dict, cfg, w: float | None = None, old_penalty: bool = False) -> tuple[list[dict], float]:
    w = float(cfg["jev"]["weight"]) if w is None else w
    mins = int(cfg["selector"]["min_trades_for_stats"])
    rows = []
    for k, c in (inputs.get("strategies") or {}).items():
        a = outputs.get(k) or {}
        q = quant(c, mins, old_penalty)
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
            if tok < 0.4 and cfg["jev"].get("trade_ok_gate", True):
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



def picks(rows: list[dict], tok: float, minsel: float, top: int, tok_gate: bool) -> tuple[list[str], str]:
    """The selector's choice for one logged hour: picked ids, and why nothing was picked (or "")."""
    if tok_gate and tok < 0.4:
        return [], "Jev said don't trade this hour (trade_ok < 0.4)"
    per_tf, out = {}, []
    for r in rows:
        if r["combined"] >= minsel and per_tf.get(r["tf"], 0) < top:
            per_tf[r["tf"]] = per_tf.get(r["tf"], 0) + 1
            out.append(r["id"])
    return out, "" if out else f"no strategy scored ≥ {minsel}"


def compare(days: int = 14, cfg=None) -> str:
    """Every hourly rating the account logged in the last `days`, re-picked under the rule before Nov 9 2026 (Jev 60%,
    Jev's trade_ok gate, ×0.6 for few trades) and under today's rule (stats only, evidence-weighted). Read-only."""
    cfg = cfg or load_config("config.yaml")
    con = sqlite3.connect(f"file:{Path(cfg['storage']['db_path'])}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    since = (pd.Timestamp.now(tz="America/New_York") - pd.Timedelta(days=days)).isoformat()
    dec = con.execute("SELECT ts, symbol, source, inputs, outputs FROM decisions WHERE kind='strategy_rating' AND ts >= ? "
                      "ORDER BY ts", (since,)).fetchall()
    con.close()
    minsel, top = float(cfg["jev"]["min_select_score"]), int(cfg["selector"]["top_n_per_tf"])
    n_old = n_new = 0
    why_old, why_new, got_old, got_new, sym_old, sym_new = (Counter() for _ in range(6))
    hours = Counter()
    for d in dec:
        i, o = json.loads(d["inputs"] or "{}"), json.loads(d["outputs"] or "{}")
        hours[d["symbol"]] += 1
        ro, tok = hour_rows(i, o, cfg, w=0.6, old_penalty=True)
        rn, _ = hour_rows(i, o, cfg, w=0.0)
        po, wo = picks(ro, tok, minsel, top, True)
        pn, wn = picks(rn, tok, minsel, top, False)
        n_old += len(po); n_new += len(pn); sym_old[d["symbol"]] += len(po); sym_new[d["symbol"]] += len(pn)
        got_old.update(po); got_new.update(pn)
        if wo: why_old[wo] += 1
        if wn: why_new[wn] += 1
    md = [f"# Hourly pick: before vs after taking Jev out (last {days} days, {len(dec)} logged hourly ratings)", "",
          "Same logged hours, same strategy statistics, re-picked under each rule. Before = Jev 60% of the score, Jev's "
          "trade_ok gate, ×0.6 for strategies with fewer than "
          f"{cfg['selector']['min_trades_for_stats']} trades. Now = statistics only, small samples weighted by evidence. "
          f"A pick needs a score ≥ {minsel}; at most {top} per timeframe.", "",
          "| instrument | hours rated | picks before | picks now |", "|---|---|---|---|"]
    md += [f"| {s} | {hours[s]} | {sym_old[s]} | {sym_new[s]} |" for s in sorted(hours)]
    md += [f"| **all** | {len(dec)} | **{n_old}** | **{n_new}** |", "",
           "## Hours with no pick, and why", "", "| reason | before | now |", "|---|---|---|"]
    for k in sorted(set(why_old) | set(why_new)):
        md.append(f"| {k} | {why_old[k]} | {why_new[k]} |")
    md += ["", "## Strategies picked (times)", "", "| strategy | before | now |", "|---|---|---|"]
    for k in sorted(set(got_old) | set(got_new), key=lambda x: -(got_old[x] + got_new[x])):
        md.append(f"| {k} | {got_old[k]} | {got_new[k]} |")
    return "\n".join(md) + "\n"


def main(argv=None):
    """Prints the report, or with --publish writes it to data/year_test/pick_why_<name>/report.md (for ./fx.sh publish)."""
    import contextlib
    import io
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "compare":
        days = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 14
        out = Path("data/year_test/pick_compare")
        out.mkdir(parents=True, exist_ok=True)
        md = compare(days)
        (out / "report.md").write_text(md)
        print(md)
        return
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
