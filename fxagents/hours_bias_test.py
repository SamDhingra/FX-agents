"""All-hours and no-bias playbook test (registered Oct 29 2026, research/hours_bias/PREREGISTRATION_2026-10-29.md,
before any run).

Sam's two questions:
  H  "no cut-off": what do the playbook's trades OUTSIDE the current entry windows earn, if entries run all session
     20:00 → 15:50 NY (00:00–02:00, 05:00–08:30, 11:30–13:30 are the gaps today; 15:30–15:50 stays shut by the
     existing no-entries-in-the-last-20-minutes-before-the-15:50-flatten rule; 17:00–20:00 stays shut)?
  B  "bias not followed": what do the playbook's trades INSIDE the current windows earn when the hard bias rule would
     have refused them (neutral or counter-bias)?

One replay per cell with the windows opened and the bias rule off (research engine, live position manager on
1-minute bars, real per-minute bid/ask spread, news blackouts unchanged), then every trade is tagged:
  in_window  its signal candle closed inside today's entry windows
  rel        aligned | neutral | counter (side × bias score against bias.min_align)
  H = not in_window and aligned        B = in_window and not aligned        base = in_window and aligned (reference)

Judged on 2021-01-01 → 2025-10-07 (clean: before the year the playbook research was picked on); Oct 2025 → Sep 2026 is
shown only. Each of H and B passes only if, by itself: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0
at 2× costs, positive in both halves. A group that passes is judged ONCE on 2016–2020 (`--period vault`); nothing else
goes to the vault. No trading change follows from any result before the Nov 5 review; the two shadow books
(playbook_allhours, playbook_nobias) collect the forward record meanwhile.

    python -m fxagents.hours_bias_test [--period seen|vault] [--workers 2]   (./fx.sh hoursbias [seen|vault])
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import playbook_test as PT
from .agents.setup_first import ALLHOURS_WINDOWS
from .config import load_config
from .structure import window_mask

GROUPS = ("H", "B")
NAMES = {"H": "H — outside today's windows, bias-aligned (what the all-hours playbook adds)",
         "B": "B — inside today's windows, bias rule would refuse (neutral or counter)",
         "base": "base — inside windows, aligned (what the playbook trades today; reference only)"}
CLEAN_END = PT.CLEAN[1]                      # 2025-10-08: judged before this
BLOCKS = [("00:00–02:00", 0, 120), ("05:00–08:30", 300, 510), ("11:30–13:30", 690, 810), ("other", -1, -1)]
OUT = {"seen": Path("data/year_test/hours_bias_seen"), "vault": Path("data/year_test/hours_bias_vault")}
HIST = {"seen": Path("data/history_x/seen_2021_2026"), "vault": Path("data/history_x/old_2016_2020")}


def relaxed_cfg(cfg: dict) -> dict:
    c = copy.deepcopy(cfg)
    c["sessions"]["entry_windows"] = [list(w) for w in ALLHOURS_WINDOWS]
    c["bias"]["min_align"] = -9.0             # every finite bias reading passes; NaN (no bias yet) is still skipped
    return c


def tag(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """in_window / rel / group, from the ORIGINAL config's windows and min_align."""
    if not len(t):
        return t.assign(in_window=[], rel=[], group=[], block=[])
    ts = pd.DatetimeIndex(pd.to_datetime(t["ts"]))
    inw = window_mask(ts, cfg["sessions"]["entry_windows"])
    ma = float(cfg["bias"]["min_align"])
    sb = t["side"].to_numpy(float) * t["bias"].to_numpy(float)
    rel = np.where(sb >= ma, "aligned", np.where(np.abs(t["bias"].to_numpy(float)) < ma, "neutral", "counter"))
    grp = np.where(inw & (rel == "aligned"), "base", np.where(~inw & (rel == "aligned"), "H",
                   np.where(inw, "B", "neither")))
    hm = ts.hour * 60 + ts.minute
    blk = np.full(len(t), "other", object)
    for name, a, b in BLOCKS[:-1]:
        blk[(hm >= a) & (hm < b)] = name
    return t.assign(in_window=inw, rel=rel, group=grp, block=blk)


def judged_part(t: pd.DataFrame, period: str) -> pd.DataFrame:
    if period != "seen" or not len(t):
        return t
    d = pd.to_datetime(t["ts"]).dt.tz_localize(None) if pd.to_datetime(t["ts"]).dt.tz is not None else pd.to_datetime(t["ts"])
    return t[d < CLEAN_END]


def row(name: str, st: dict) -> str:
    if not st.get("n"):
        return f"| {name} | — | 0 | | | | | | | |"
    return (f"| {name} | **{'PASS' if st['pass'] else 'no'}** | {st['n']} | {st['win']:.0%} | {st['avg']:+.3f} | "
            f"{st['lo']:+.2f} to {st['hi']:+.2f} | {st['avg2x']:+.3f} | {st['h1']:+.3f} | {st['h2']:+.3f} | {st['cost']:.0%} |")


def info(name: str, g: pd.DataFrame) -> str:
    return f"| {name} | {len(g)} | {g.r.mean():+.3f} | {(g.r - g.cost_r).mean():+.3f} |" if len(g) else f"| {name} | 0 | — | — |"


def run(period: str, cells: list[dict], cfg: dict, workers: int, out: Path, hist: Path, seen_sets: str = "holdout_m1,dev_m1",
        runner=None) -> dict:
    """runner(cfg, cells, hist, workers) -> {cell id: trades}; defaults to playbook_test.run_cells (tests pass a stub)."""
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; the {period} judgement is made once")
    want = list(GROUPS)
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        want = [g for g in GROUPS if (seen.get(g) or {}).get("pass")]
        if not want:
            raise SystemExit("registered: the vault is judged only for a group that passed on 2021 → Oct 2025 (none did, or no seen run)")
    frozen = json.dumps(cells, sort_keys=True)
    sha = hashlib.sha256(frozen.encode()).hexdigest()[:12]
    out.mkdir(parents=True, exist_ok=True)
    (out / "cells_frozen.json").write_text(frozen)
    syms = {c["sym"] for c in cells}
    if runner is None:
        if not all((hist / f"{s}.pkl").exists() for s in syms) and period == "seen":
            PT.build_history(cfg, seen_sets.split(","), syms, hist)
        runner = PT.run_cells
    have = {s for s in syms if (hist / f"{s}.pkl").exists()} if runner is PT.run_cells else syms
    res = runner(relaxed_cfg(cfg), [c for c in cells if c["sym"] in have], hist, workers)
    parts = [t.assign(cell=cid) for cid, t in res.items() if len(t)]
    allt = tag(pd.concat(parts, ignore_index=True), cfg) if parts else tag(pd.DataFrame(), cfg)
    allt.to_csv(out / "trades.csv.gz", index=False)
    j = judged_part(allt, period)
    span = ("2021-01-01 → 2025-10-07 (clean)" if period == "seen" else "2016-01-01 → 2020-12-31 (untouched, judged once)")
    st = {g: PT.judge(j[j.group == g], False) for g in want}
    base = PT.judge(j[j.group == "base"], False)
    md = [f"# All-hours and no-bias playbook test — {period} (frozen {sha}, {len(cells)} cells)", "",
          "Registered Oct 29 2026 before running (research/hours_bias/PREREGISTRATION_2026-10-29.md). One replay per cell "
          "with entries allowed 20:00 → 15:50 NY and the bias rule off (research engine, live position manager on 1-minute "
          "bars, real bid/ask spread, news blackouts unchanged); each trade is tagged by today's windows and what the bias "
          "rule would have said.", "",
          f"**Judged on {span}.** A group passes only by itself: ≥ 100 trades, avg R > 0, 95% day-block range above 0, "
          "avg R > 0 at 2× costs, positive in both halves. Two groups are tested, so about 1 in 10 runs would show a "
          "lucky pass — hence the single 2016–2020 judgement.", "",
          "| group | verdict | trades | win | avg R | 95% range | 2× costs | 1st half | 2nd half | spread / risk |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    md += [row(NAMES[g], st[g]) for g in want]
    md += [row(NAMES["base"], base).replace("**PASS**", "ref").replace("**no**", "ref")]
    missing = sorted({c["sym"] for c in cells} - have)
    if missing:
        md += ["", "No history for: " + ", ".join(missing) + " (their cells are not in this result)."]
    if period == "seen":
        nxt = [g for g in want if st[g]["pass"]]
        md += ["", ("**" + ", ".join(nxt) + " pass" + ("es" if len(nxt) == 1 else "") + " → one judgement on 2016–2020: "
                    "./fx.sh hoursbias vault**") if nxt else
               "**Neither passes → the vault is not touched; both questions are answered: no.**"]
    else:
        md += ["", "**Verdict on 2016–2020: " + "; ".join(f"{g} {'CONFIRMED' if st[g]['pass'] else 'NOT CONFIRMED'}"
                                                       for g in want) + ".** Any trading change is for the Nov 5 review."]
    md += ["", "## Detail (descriptive, can't rescue a failed group)", "", "| slice | trades | avg R | avg R at 2× costs |", "|---|---|---|---|"]
    for name, a, b in BLOCKS:
        md.append(info(f"H, signal {name}", j[(j.group == "H") & (j.block == name)]))
    md.append(info("B, neutral bias", j[(j.group == "B") & (j.rel == "neutral")]))
    md.append(info("B, counter bias", j[(j.group == "B") & (j.rel == "counter")]))
    md.append(info("outside windows and not aligned (neither question)", j[j.group == "neither"]))
    md.append(info("the all-hours playbook as a whole (base + H)", j[j.group.isin(["base", "H"])]))
    md.append(info("the no-bias playbook as a whole (base + B)", j[j.group.isin(["base", "B"])]))
    if period == "seen":
        late = allt[~allt.index.isin(j.index)]
        md += ["", "Oct 8 2025 → Sep 2026 (the year the playbook research was picked on; shown, not judged):", "",
               "| slice | trades | avg R | avg R at 2× costs |", "|---|---|---|---|"]
        md += [info(NAMES[g], late[late.group == g]) for g in ("H", "B", "base")]
    md += ["", "## By cell (descriptive)", "", "| cell | base | H | B |", "|---|---|---|---|"]
    for cid, g in j.groupby("cell"):
        cellv = [f"{len(x)} ({x.r.mean():+.2f})" if len(x) else "—" for x in (g[g.group == k] for k in ("base", "H", "B"))]
        md.append(f"| {cid} | " + " | ".join(cellv) + " |")
    md += ["", "Opening the windows lets a cell's own earlier trade block a later one, so `base` here can differ a little "
           "from the playbook test's numbers. A passing group added to a losing playbook still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    summ = {**st, "base": base, "frozen": sha, "period": period}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ


def main(argv=None):
    ap = argparse.ArgumentParser(description="All-hours and no-bias playbook test (registered Oct 29 2026)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--cells-file", type=Path, default=None, help="default: data/playbook.json now (frozen into the output)")
    a = ap.parse_args(argv)
    cfg = load_config("config.yaml")
    if a.period == "vault":
        cells = json.loads((OUT["seen"] / "cells_frozen.json").read_text())        # the same cells as the seen run
    else:
        pb = json.loads(a.cells_file.read_text()) if a.cells_file else json.loads(Path("data/playbook.json").read_text())
        cells = pb if isinstance(pb, list) else pb["cells"]
        cells = [c for c in cells if c["sym"] in cfg["instruments"]]
    run(a.period, cells, cfg, a.workers, OUT[a.period], HIST[a.period])
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
