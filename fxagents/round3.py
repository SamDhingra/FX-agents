"""Round 3 (Oct 26 2026): context checks on the playbook's own 3m/5m entries, judged with the stricter judge.

Registered before any of these ran (research/round3/PREREGISTRATION_chatgpt_2026-10-26.md):
  A1 opposing_path_v1  — a material, efficient 15-minute move against the trade (ChatGPT's code, unchanged)
  A2 two_way_chop_v1   — active 30-minute back-and-forth with little net progress (ChatGPT's code, unchanged)
and, for consistency, our m15_live (fxagents/mtf_whatif) re-judged with the same stricter judge.

The cohort is the 3m/5m cells only. A check's unavailable trades (gaps in the 269 minutes before entry) are dropped
for that check and count against its coverage (≥ 90% required, otherwise inconclusive).

Vault (2016–2020): the counterflow family (m15_live, A1, and the wait-for-the-15m policy B) shares ONE vault use —
m15_live's registered confirmation (./fx.sh mtfvault), started before this round was registered. A1 and B therefore
get no separate vault run on those trades. A2 is a different hypothesis; if it alone passes here, it may be judged
once on the 2016–2020 trades that mtfvault produces.

    python -m fxagents.round3 [--period seen|vault]   → data/year_test/round3_<period>/report.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf_whatif as W
from . import whatif_judge as J

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {"A1_opposing_path_v1": "opposing_path_v1.py", "A2_two_way_chop_v1": "two_way_chop_v1.py"}
LOW = ("3m", "3min", "5m", "5min")
LOOKBACK = pd.Timedelta(minutes=300)


def _load_flag(file: str):
    spec = importlib.util.spec_from_file_location(file[:-3], ROOT / "research" / "round3" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.flag


def flag_trades(t: pd.DataFrame, m1: pd.DataFrame, fn) -> np.ndarray:
    """True / False / NaN (unavailable) per trade. Each call gets only the minutes in [ts − 300 min, ts) — the
    functions read only [start, ts) with start ≥ ts − 269 min, so the result is the same as passing all of m1."""
    idx = m1.index
    out = np.full(len(t), np.nan)
    for i, r in enumerate(t.itertuples(index=False)):
        ts = pd.Timestamp(r.ts)
        a, b = idx.searchsorted(ts - LOOKBACK), idx.searchsorted(ts)
        try:
            out[i] = float(fn({"ts": ts, "side": int(r.side)}, m1.iloc[a:b]))
        except ValueError:
            pass
    return out


def run(period: str, src: Path, hist: Path, out: Path) -> dict:
    pattern = "trades_seen_" if period == "seen" else "trades_old_"
    t = W.load(src, pattern)
    t = t[t.tf.isin(LOW)].reset_index(drop=True)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True)
    intended = len(t)
    use = dict(CHECKS)
    if period == "vault":                         # registered: A1 never on the vault; A2 only if it passed on seen
        seen = Path("data/year_test/round3_seen/summary.json")
        a2 = json.loads(seen.read_text()).get("A2_two_way_chop_v1", {}) if seen.exists() else {}
        use = {k: f for k, f in CHECKS.items() if k.startswith("A2") and a2.get("pass")}
    fns = {k: _load_flag(f) for k, f in use.items()}
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}: {len(g)} trades unavailable", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        g = g.reset_index(drop=True)
        a = W.annotate(g, m1)                                   # m15_live and its validity
        g["m15_live"] = np.where(a.ok, a.m15_live.astype(float), np.nan)
        for k, fn in fns.items():
            g[k] = flag_trades(g, m1, fn)
            print(f"  {sym}: {k} computed for {np.isfinite(g[k]).sum()} of {len(g)}", flush=True)
        parts.append(g)
    a = pd.concat(parts, ignore_index=True)
    res, cover_rows = {}, []
    for k in ["m15_live", *fns]:
        ok = np.isfinite(a[k].to_numpy(float))
        sub = a[ok].assign(**{k: a.loc[ok, k].astype(bool)})
        res[k] = J.judge(sub, k, period, intended)
        miss = a[~ok]
        cover_rows.append((k, len(miss), miss.groupby(pd.to_datetime(miss.ts).dt.hour).size().to_dict()))
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades_flagged.csv.gz", index=False)
    md = [f"# Round 3: context checks on the playbook's 3m / 5m entries ({period}, stricter judge)", "",
          "Registered before running (research/round3/PREREGISTRATION_chatgpt_2026-10-26.md). **A1** a material, efficient "
          "15-minute move against the trade; **A2** active 30-minute back-and-forth with little net progress (both "
          "ChatGPT's code, unchanged); **m15_live** our check (the 15m candle in progress moved against the trade), "
          "re-judged the same way.", "",
          "Stricter judge (fxagents/whatif_judge.py): fixed calendar halves (split "
          f"{J.split_of(period).date()}), circular 5-weekday block bootstrap ({J.DRAWS:,} draws), random skipping "
          "**within each stratum** (cell × side × hour × half), ≥ 30 flagged and kept trades per half, ≥ 90% coverage.", "",
          f"Cohort: {intended:,} trades on 3m / 5m, {t.r.mean():+.3f}R average.", "", J.HEAD]
    md += [J.fmt(res[k]) for k in res]
    md += ["", "Unavailable trades (gaps in the minutes before entry), by hour of entry:", ""]
    md += [f"- {k}: {n} — {d}" for k, n, d in cover_rows]
    md += ["", "## By cell (descriptive; it can't rescue a failed check)", "",
           "| cell | trades | avg R | " + " | ".join(f"{k} flagged (avg R) / kept (avg R)" for k in res) + " |",
           "|---|---|---|" + "---|" * len(res)]
    for cell, g in a.groupby("cell"):
        cells = []
        for k in res:
            v = g[np.isfinite(g[k].to_numpy(float))]
            fl, kp = v[v[k] == 1], v[v[k] == 0]
            cells.append(f"{len(fl)} ({fl.r.mean():+.2f}) / {len(kp)} ({kp.r.mean():+.2f})" if len(v) else "—")
        md.append(f"| {cell} | {len(g)} | {g.r.mean():+.3f} | " + " | ".join(cells) + " |")
    md += ["", "A pass earns a paper filter (and, for A2 only, one judgement on the 2016–2020 trades); the counterflow "
           "family's vault use is m15_live's confirmation. A check that passes but leaves the kept trades below zero "
           "still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Round 3 context checks (stricter judge)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--hist", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    seen = a.period == "seen"
    src = a.src or Path("data/year_test/playbook_test" if seen else "data/year_test/mtf_vault_trades")
    hist = a.hist or Path("data/history_x/seen_2021_2026" if seen else "data/history_x/old_2016_2020")
    out = a.out or Path(f"data/year_test/round3_{a.period}")
    run(a.period, src, hist, out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
