"""Why isn't a setup trading? (Nov 4 2026, Sam: sr_rejection has not traded since Oct 29.) Read-only.

    python -m fxagents.cell_why [setup=sr_rejection] [--days 14]       (./fx.sh cellwhy [setup] [days])

Prints, for the setup:
  1. whether any of its cells are in the playbook the bots trade now (data/playbook.json) and since when it was built;
  2. day by day over the last N trading days, whether the weekly/daily selection (same policy, same research trades)
     would include each of its cells, and if not, the first rule that keeps it out;
  3. its cells' current window statistics against each selection rule;
  4. the last time each playbook book journaled a trade of it.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from . import playbook as pbk
from .config import load_config


def reasons(row, pol: pbk.Policy, rank: int | None, cap: int) -> str:
    r = pbk._rule(pol, row.sym)
    min_n = r.min_n if r.min_n is not None else pol.min_n
    out = []
    if r.role == "off":
        out.append(f"{row.sym} is off")
    if row.tf not in pol.tfs:
        out.append(f"timeframe {row.tf} not traded")
    if row.n < min_n:
        out.append(f"only {int(row.n)} trades in the window (needs {min_n})")
    if pol.halves_positive and not (row.exp1 > 0 and row.exp2 > 0):
        out.append(f"a half of the window is not positive ({row.exp1:+.3f} / {row.exp2:+.3f})")
    if row.e < r.min_e:
        out.append(f"shrunk expectancy {row.e:+.3f} < {r.min_e:+.3f}")
    if row.p < r.min_p:
        out.append(f"shrunk win rate {row.p:.2f} < {r.min_p:.2f}")
    if not out and rank is not None and rank >= cap:
        out.append(f"ranked {rank + 1} on {row.sym}, only the top {cap} are kept")
    return "; ".join(out) or "selected"


def table(cfg, setup: str, b: int, cube, pol) -> pd.DataFrame:
    st = pbk.score(cube.window(b - pol.window_days, b, cutoff=cube.days[b] if b < len(cube.days) else None), pol)
    ok = pbk.eligible(st, pol)
    ranked = st[ok].sort_values("e", ascending=False).drop_duplicates(["sym", "tf", "setup", "mgmt"])
    rank = {}
    for sym, g in ranked.groupby("sym"):
        for k, ix in enumerate(g.index):
            rank[ix] = k
    mine = st[st.setup == setup].copy()
    mine["why"] = [reasons(r, pol, rank.get(ix), pbk._rule(pol, r.sym).max_cells) for ix, r in zip(mine.index, mine.itertuples())]
    return mine


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Why isn't a setup trading? (read-only)")
    ap.add_argument("setup", nargs="?", default="sr_rejection")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--since", default="2026-10-29", help="signals from this date on")
    ap.add_argument("--signals", type=int, default=15, help="signals shown per journal")
    ap.add_argument("--old-index-rules", action="store_true",
                    help="judge with the NDQ/US30 rules in force before Nov 4 2026 (stricter than gold)")
    a = ap.parse_args(argv)
    cfg = load_config("config.yaml")
    if a.old_index_rules:
        pc = cfg.setdefault("playbook", {})
        pc.pop("instruments", None)
        pc.pop("index_group_max", None)
    pol = pbk.policy_from_cfg(cfg)
    print(f"Rules: NDQ {pbk._rule(pol, 'NDQ')}; US30 {pbk._rule(pol, 'US30')}\n" if "NDQ" in pol.instruments else "")
    print(f"# Why isn't {a.setup} trading?\n")
    p = pbk.playbook_path(cfg)
    if p.exists():
        d = json.loads(p.read_text())
        mine = [c for c in d.get("cells", []) if c.get("setup") == a.setup]
        print(f"Playbook in use: as of {d.get('asof')} (file written {pd.Timestamp(p.stat().st_mtime, unit='s'):%Y-%m-%d %H:%M} UTC), "
              f"{len(d.get('cells', []))} cells; {a.setup}: " + (", ".join(c['id'] for c in mine) if mine else "NONE"))
    else:
        print("No data/playbook.json — the books select as of each day from the research trades.")
    cube = pbk.load_cube(cfg)
    if cube is None:
        raise SystemExit("no research trades (data/research/trades.pkl) — ./fx.sh research")
    days = cube.days
    print(f"Research trades: {days[0]} → {days[-1]} ({len(days)} trading days). Window: {pol.window_days} trading days.\n")
    if not (cube.cells.setup == a.setup).any():
        raise SystemExit(f"{a.setup} has no cells in the research trades at all")
    print("## Day by day (selection made at the start of each day)\n")
    for b in range(max(1, len(days) - a.days + 1), len(days) + 1):
        t = table(cfg, a.setup, b, cube, pol)
        day = days[b] if b < len(days) else "next"
        sel = t[t.why == "selected"]
        print(f"- {day}: " + (", ".join(f"{r.sym} {r.tf} {r.variant} {r.mgmt}" for r in sel.itertuples()) + " selected"
                              if len(sel) else "no cell selected"))
    print("\n## Its cells now (window ending at the last research day)\n")
    t = table(cfg, a.setup, len(days), cube, pol).sort_values(["sym", "e"], ascending=[True, False])
    print("| sym | tf | variant | exit | trades | avg R | shrunk e | halves | verdict |\n|---|---|---|---|---|---|---|---|---|")
    for r in t.itertuples():
        print(f"| {r.sym} | {r.tf} | {r.variant} | {r.mgmt} | {int(r.n)} | {r.raw_e:+.3f} | {r.e:+.3f} | "
              f"{r.exp1:+.3f} / {r.exp2:+.3f} | {r.why} |")
    print("\n## Last trade of it in each journal\n")
    db = Path(cfg["storage"]["db_path"])
    for f in sorted(db.parent.glob(db.stem + "*.sqlite")):
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            r = con.execute("SELECT MAX(opened), COUNT(*) FROM trades WHERE strategy LIKE ?", (f"{a.setup}%",)).fetchone()
            con.close()
        except sqlite3.Error:
            continue
        print(f"- {f.name}: {r[1]} trades, last opened {r[0] or '—'}")
    print("\n## Its signals since the playbook last picked it up, per playbook book (what each book did and why)\n")
    for f in sorted(db.parent.glob(db.stem + "*.sqlite")):
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            rows = con.execute("SELECT ts, symbol, side, action, why FROM signals WHERE strategy LIKE ? AND ts >= ? "
                               "ORDER BY ts DESC LIMIT ?", (f"{a.setup}%", a.since, a.signals)).fetchall()
            con.close()
        except sqlite3.Error:
            continue
        if not rows:
            continue
        print(f"### {f.name}\n")
        for ts, sym, side, act, why in rows:
            print(f"- {str(ts)[:16]} {sym} {side} → {act}: {(why or '')[:160]}")
        print()



def main(argv=None):
    """Prints the report, or with --publish writes it to data/year_test/cell_why_<name>/report.md (for ./fx.sh publish)."""
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
    out = Path(f"data/year_test/cell_why_{name}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(buf.getvalue())
    print(f"wrote {out / 'report.md'} ({len(buf.getvalue().splitlines())} lines)")


if __name__ == "__main__":
    main()
