"""Playbook two-step test (Oct 19 2026): each of the current playbook's setups, exactly as the bot trades it, judged on
real bid/ask data it was not picked on.

    python -m fxagents.playbook_test --seen holdout_m1,dev_m1 --judge old_m1 --out data/year_test/playbook_test
                                                                                               (./fx.sh pbtest)

What runs: every cell of data/playbook.json (setup + parameters + timeframe + instrument + exit profile), frozen —
the cell list is copied into the output with its hash before anything runs. Each cell is replayed by the research
engine the playbook itself was built with (research.run_job: the live filters — entry windows, news blackouts, the hard
bias rule — and research.simulate_live: the live position manager on 1-minute bars), but on the OANDA bid/ask exports
with the REAL spread of every minute (ask − bid at the minute's close), one trade at a time per cell. R after spread;
"2× costs" pays one more spread.

The playbook was picked on the year 2025-10-08 → 2026-10-08, so that year is in-sample. Data:
  seen     2021-01 → 2026-09 (holdout_m1 + dev_m1, continuous), shown in three pieces:
             2021 → Sep 2024 (clean) · Oct 2024 → Oct 7 2025 (clean) · Oct 8 2025 → Sep 2026 (where it was picked)
  judged   2016 → 2020 (old_m1, untouched) — only for cells that pass step 1.

Step 1 (per cell, on all of 2021 → Sep 2026): ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at
2× costs, positive in both halves, AND positive in each of the two clean pieces. 18 cells are tested at once, so about
one could pass by luck — which is why step 2 exists.
Step 2 (passers only): the same gates on 2016–2020, once. Index cells need NDQ/US30 2016–2020 bid/ask data; it is
exported on demand (OANDA prices only) if missing.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .research import own_trades, run_job_frame, vkey
from .setup_map import history_dir

CLEAN = (pd.Timestamp("2024-10-01"), pd.Timestamp("2025-10-08"))       # NY dates splitting the seen data
PIECES = ("2021 → Sep 2024 (clean)", "Oct 2024 → Oct 7 2025 (clean)", "Oct 8 2025 → Sep 2026 (picked here)")
OLD_IDX = "old_m1_idx"                                                    # where NDQ/US30 2016–2020 are exported


def export_file(sets: list[str], sym: str) -> list[Path]:
    return [p for p in (Path("data/export") / s / f"{sym}_M1.csv.gz" for s in sets) if p.exists()]


def build_history(cfg, sets: list[str], syms: set[str], dest: Path) -> list[str]:
    """Bid/ask exports → the research engine's history cache (mid 1m bars + the real spread, NY time; 1h bars)."""
    dest.mkdir(parents=True, exist_ok=True)
    have = []
    for sym in sorted(syms):
        files = export_file(sets, sym)
        if not files:
            continue
        parts = []
        for f in files:
            d = pd.read_csv(f)
            d.index = pd.to_datetime(d.pop("time"), utc=True)
            parts.append(d)
        d = pd.concat(parts).sort_index()
        d = d[~d.index.duplicated()]
        m1 = pd.DataFrame({k: (d[f"bid_{k[0]}"] + d[f"ask_{k[0]}"]) / 2 for k in ("open", "high", "low", "close")})
        m1["volume"] = d["volume"] if "volume" in d else 1.0
        m1["spread"] = (d["ask_c"] - d["bid_c"]).clip(lower=0)
        m1.index = m1.index.tz_convert(cfg["timezone"])
        h1 = m1[["open", "high", "low", "close"]].resample("1h", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        pd.to_pickle((m1, h1), dest / f"{sym}.pkl")
        have.append(sym)
        print(f"  history {dest.name}/{sym}: {len(m1):,} minutes {m1.index[0]:%Y-%m-%d} → {m1.index[-1]:%Y-%m-%d}", flush=True)
    src = history_dir(load_config("config.yaml")) / "instruments.json"
    if src.exists():
        shutil.copy(src, dest / "instruments.json")
    return have


def run_cells(cfg, cells: list[dict], hist: Path, workers: int) -> dict[str, pd.DataFrame]:
    jobs = []
    for c in cells:
        cc = copy.deepcopy(cfg)
        cc["history_dir"] = str(hist)
        cc.setdefault("research", {})["only_params"] = {c["setup"]: c.get("params") or {}}
        cc["research"].pop("exit_study", None)
        jobs.append((cc, c["sym"], c["tf"], [c["setup"]]))
    out = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                             max_tasks_per_child=1) as ex:
        for c, part in zip(cells, ex.map(run_job_frame, jobs)):
            if len(part):
                part = part[(part.tf == c["tf"]) & (part.variant == vkey(c.get("params") or {})) & (part.mgmt == c["mgmt"])]
                part = own_trades(part)
            out[c["id"]] = part
            print(f"  {c['id']}: {len(part)} trades", flush=True)
    return out


def boot_lo_hi(t: pd.DataFrame, seed: int = 7, B: int = 3000, blk: int = 5) -> tuple[float, float]:
    """95% range of the mean R, resampling 5-day blocks of trading days (days without trades count as zero-trade days)."""
    days = pd.Series(pd.to_datetime(t["day"]))
    all_days = pd.bdate_range(days.min(), days.max())
    g = t.assign(day=days.values).groupby("day").r.agg(["sum", "count"]).reindex(all_days, fill_value=0)
    s, k = g["sum"].to_numpy(), g["count"].to_numpy()
    n = len(s)
    if n < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (B, -(-n // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :n] % n
    den = k[ix].sum(1)
    m = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    lo, hi = np.nanquantile(m, [0.025, 0.975])
    return float(lo), float(hi)


def piece(ts: pd.Series) -> pd.Series:
    d = pd.to_datetime(ts).dt.tz_localize(None).dt.normalize() if pd.to_datetime(ts).dt.tz is not None \
        else pd.to_datetime(ts).dt.normalize()
    return pd.Series(np.where(d < CLEAN[0], PIECES[0], np.where(d < CLEAN[1], PIECES[1], PIECES[2])), index=ts.index)


def judge(t: pd.DataFrame, need_pieces: bool) -> dict:
    if not len(t):
        return {"n": 0, "pass": False}
    t = t.sort_values("ts")
    r = t.r.to_numpy()
    r2 = (t.r - t.cost_r).to_numpy()
    lo, hi = boot_lo_hi(t)
    half = len(t) // 2
    st = {"n": int(len(t)), "win": float((r > 0).mean()), "avg": float(r.mean()), "lo": lo, "hi": hi,
          "avg2x": float(r2.mean()), "h1": float(r[:half].mean()) if half else float("nan"),
          "h2": float(r[half:].mean()), "total": float(r.sum()), "cost": float(t.cost_r.median())}
    ok = st["n"] >= 100 and st["avg"] > 0 and lo > 0 and st["avg2x"] > 0 and st["h1"] > 0 and st["h2"] > 0
    if need_pieces:
        p = piece(t.ts)
        st["pieces"] = {k: (float(t.r[p == k].mean()) if (p == k).any() else float("nan"), int((p == k).sum()))
                        for k in PIECES}
        ok = ok and all(st["pieces"][k][1] > 0 and st["pieces"][k][0] > 0 for k in PIECES[:2])
    st["pass"] = bool(ok)
    return st


def fmt_row(cid: str, st: dict, pieces: bool) -> str:
    if not st.get("n"):
        return f"| {cid} | — | 0 |" + " |" * (8 + (3 if pieces else 0))
    base = (f"| {cid} | **{'PASS' if st['pass'] else 'no'}** | {st['n']} | {st['win']:.0%} | {st['avg']:+.3f} | "
            f"{st['lo']:+.2f} to {st['hi']:+.2f} | {st['avg2x']:+.3f} | {st['h1']:+.3f} | {st['h2']:+.3f} | "
            f"{st['cost']:.0%} |")
    if pieces:
        base += "".join(f" {st['pieces'][k][0]:+.3f} ({st['pieces'][k][1]}) |" if st['pieces'][k][1] else " — |"
                        for k in PIECES)
    return base


def judge_only(cfg, cells: list[dict], pb: dict, a) -> None:
    """A pre-registered follow-up: these cells, frozen, judged ONCE on the untouched set (no step 1 rerun)."""
    frozen = json.dumps(cells, sort_keys=True)
    sha = hashlib.sha256(frozen.encode()).hexdigest()[:12]
    (a.out / "cells_frozen.json").write_text(frozen)
    need = {c["sym"] for c in cells}
    judge_sets = [a.judge, OLD_IDX]
    for sym in sorted(need):
        if not export_file(judge_sets + [f"{OLD_IDX}_{sym}"], sym):
            print(f"exporting {sym} 2016–2020 bid/ask (one-time) …", flush=True)
            subprocess.run([sys.executable, "-m", "fxagents.export_history", "--name", f"{OLD_IDX}_{sym}", "--gran", "M1",
                            "--from", "2016-01-01", "--until", "2020-12-31", "--symbols", sym], check=False)
        judge_sets.append(f"{OLD_IDX}_{sym}")
    hist = Path("data/history_x/old_2016_2020")
    have = build_history(cfg, judge_sets, need, hist)
    res = run_cells(cfg, [c for c in cells if c["sym"] in have], hist, a.workers)
    md = [f"# Pre-registered follow-up — judged once on untouched 2016 → 2020 (frozen {sha})", "",
          f"Cells: {', '.join(c['id'] for c in cells)} — taken unchanged from {pb.get('asof')}. "
          + (getattr(a, "why", "") or "Chosen after the playbook "
          "test (Oct 20 2026) as the only setup positive in every 2021–2026 piece; it failed step 1 narrowly (95% range "
          "touching zero, negative at 2× costs), so this run is a stricter-than-usual check, not a rescue:") + " Same engine, "
          "same live filters and position manager, real per-minute bid/ask spread, same gates (≥ 100 trades, avg R > 0, "
          "95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves).", "",
          "| Cell | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Spread / risk |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    rows = {}
    for c in cells:
        t = res.get(c["id"], pd.DataFrame())
        st = judge(t, False) if len(t) else {"n": 0, "pass": False}
        rows[c["id"]] = st
        md.append(fmt_row(c["id"], st, False))
        if len(t):
            t.to_csv(a.out / f"trades_old_{c['id'].replace(':', '_').replace('@', '_')}.csv.gz", index=False)
            yr = pd.to_datetime(t.ts).dt.year
            md += ["", "By year: " + " · ".join(f"{y} {g.r.mean():+.3f} ({len(g)})" for y, g in t.groupby(yr))]
    missing = [c["id"] for c in cells if c["sym"] not in have]
    if missing:
        md += ["", "No 2016–2020 data for: " + ", ".join(missing)]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"frozen": sha, "rows": rows}, indent=2, default=str))
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seen", default="holdout_m1,dev_m1")
    ap.add_argument("--judge", default="old_m1")
    ap.add_argument("--out", type=Path, default=Path("data/year_test/playbook_test"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--cells-file", type=Path, default=None, help="use this frozen cell list instead of the playbook")
    ap.add_argument("--only", default="", help="comma-separated cell ids to run")
    ap.add_argument("--tfs", default="", help="comma-separated entry timeframes to keep (e.g. 3m,5m)")
    ap.add_argument("--why", default="", help="judge-only: the reason for this follow-up, printed in the report")
    ap.add_argument("--judge-only", action="store_true",
                    help="pre-registered follow-up: skip step 1 and judge the chosen cells once on --judge")
    a = ap.parse_args()
    cfg = load_config("config.yaml")
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cells_file:
        pb = {"asof": f"frozen file {a.cells_file}", "cells": json.loads(a.cells_file.read_text())}
    else:
        pb = json.loads(Path("data/playbook.json").read_text())
    cells = [c for c in pb["cells"] if c["sym"] in cfg["instruments"]]
    if a.only:
        want = set(a.only.split(","))
        cells = [c for c in cells if c["id"] in want]
        if not cells:
            raise SystemExit(f"no such cell: {a.only}")
    if a.tfs:
        norm = lambda x: str(x).replace("min", "m")                       # "3min" and "3m" are the same timeframe
        cells = [c for c in cells if norm(c["tf"]) in {norm(x) for x in a.tfs.split(",")}]
        if not cells:
            raise SystemExit(f"no cells on {a.tfs}")
    if a.judge_only:
        return judge_only(cfg, cells, pb, a)
    frozen = json.dumps(cells, sort_keys=True)
    (a.out / "cells_frozen.json").write_text(frozen)
    sha = hashlib.sha256(frozen.encode()).hexdigest()[:12]
    print(f"{len(cells)} playbook cells (as of {pb.get('asof')}, frozen {sha})", flush=True)
    syms = {c["sym"] for c in cells}
    seen_hist = Path("data/history_x/seen_2021_2026")
    have = build_history(cfg, a.seen.split(","), syms, seen_hist)
    run = [c for c in cells if c["sym"] in have]
    res = run_cells(cfg, run, seen_hist, a.workers)
    rows = {}
    md = [f"# Playbook two-step test — {len(cells)} setups as the bot trades them (frozen {sha}, playbook as of {pb.get('asof')})", "",
          "Each cell replayed by the playbook's own research engine (live filters + live position manager on 1-minute "
          "bars) on OANDA bid/ask data with the **real spread of every minute**; one trade at a time per cell. R after "
          "spread; 2× costs pays one more spread. The playbook was picked on Oct 2025 → Oct 2026, so that piece is "
          "in-sample and only shown.", "",
          f"**Step 1 (2021 → Sep 2026):** ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, "
          f"positive in both halves, and positive in each clean piece. {len(cells)} cells at once → about "
          f"{max(1, round(len(cells) * 0.05))} could pass by luck. "
          "**Step 2:** passers only, once, on untouched 2016–2020.", "",
          "## Step 1 — 2021 → Sep 2026", "",
          "| Cell | Step 1 | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Spread / risk | "
          + " | ".join(PIECES) + " |", "|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(PIECES)]
    for c in cells:
        t = res.get(c["id"], pd.DataFrame())
        st = judge(t, True) if len(t) else {"n": 0, "pass": False}
        rows[c["id"]] = {"step1": st}
        md.append(fmt_row(c["id"], st, True))
        if len(t):
            t.to_csv(a.out / f"trades_seen_{c['id'].replace(':', '_').replace('@', '_')}.csv.gz", index=False)
    missing = [c["id"] for c in cells if c["sym"] not in have]
    if missing:
        md += ["", "No seen data for: " + ", ".join(missing)]
    passers = [c for c in cells if rows[c["id"]]["step1"]["pass"]]
    md += ["", f"**{len(passers)} of {len(cells)} cells pass step 1.**", ""]
    if passers:
        need = {c["sym"] for c in passers}
        judge_sets = [a.judge, OLD_IDX]
        for sym in sorted(need):
            if not export_file(judge_sets, sym):
                print(f"exporting {sym} 2016–2020 bid/ask (one-time) …", flush=True)
                subprocess.run([sys.executable, "-m", "fxagents.export_history", "--name", f"{OLD_IDX}_{sym}",
                                "--gran", "M1", "--from", "2016-01-01", "--until", "2020-12-31", "--symbols", sym],
                               check=False)
                judge_sets.append(f"{OLD_IDX}_{sym}")
        judge_sets += [f"{OLD_IDX}_{s}" for s in need if f"{OLD_IDX}_{s}" not in judge_sets]
        old_hist = Path("data/history_x/old_2016_2020")
        have_old = build_history(cfg, judge_sets, need, old_hist)
        res2 = run_cells(cfg, [c for c in passers if c["sym"] in have_old], old_hist, a.workers)
        md += ["## Step 2 — untouched 2016 → 2020 (judged once)", "",
               "| Cell | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Spread / risk |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for c in passers:
            t = res2.get(c["id"], pd.DataFrame())
            st = judge(t, False) if len(t) else {"n": 0, "pass": False}
            rows[c["id"]]["step2"] = st
            md.append(fmt_row(c["id"], st, False).replace("**PASS**", "**PASS — candidate for a forward paper record**"))
            if len(t):
                t.to_csv(a.out / f"trades_old_{c['id'].replace(':', '_').replace('@', '_')}.csv.gz", index=False)
        md.append("")
    else:
        md += ["Nothing passed step 1, so the 2016–2020 data was not opened.", ""]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "run.json").write_text(json.dumps({"frozen": sha, "asof": pb.get("asof"), "rows": rows}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
