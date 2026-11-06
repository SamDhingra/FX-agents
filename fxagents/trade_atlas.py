"""Trade atlas (Nov 6 2026, Sam: "which strategy works well at which hour, at which timeframe, in which instrument;
with the bias aligned, neutral or counter; how many pips it makes or loses").

Two parts, two reports:

  forward   every book's real journal so far (practice account + each paper book): setup, instrument, timeframe, hour,
            session, bias at entry, R and pips.  Fast; small samples.
            → data/year_test/atlas_forward/report.md
  history   every playbook setup (default parameters) × XAUUSD/NDQ/US30 × 3m/5m/15m/30m/1h on the 2021 → Sep 2026
            OANDA bid/ask data with the real spread, replayed by the playbook's own engine (research.run_job), with
            THE BIAS RULE OFF (the bias score is recorded on every trade, so each trade is classed aligned / neutral /
            counter exactly as the live rule would) and entries at ALL HOURS (20:00 → 15:50 NY, as the all-hours book),
            standard exit profile, one trade at a time per setup.  Hours; large samples.
            → data/year_test/atlas_history/report.md (+ cells.csv: every slice, for your own filtering)

This is a MAP, not a test: it slices thousands of ways, so some slices look good by luck. A slice is marked
"stands out" only with ≥ 100 trades, a 95% range (5-day blocks of trading days) above 0, positive in both halves and
positive at 2× costs — and the report says how many slices were screened and how many would pass by luck. Anything
worth trading still needs its own registration and the untouched 2016–2020 data.

    python -m fxagents.trade_atlas forward
    python -m fxagents.trade_atlas run [--workers 2]     (resumable: finished instrument × timeframe jobs are kept)
    python -m fxagents.trade_atlas history               (report from whatever jobs have finished)
"""
from __future__ import annotations

import argparse
import copy
import json
import multiprocessing
import sqlite3
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
SYMS = ("XAUUSD", "NDQ", "US30")
TFS = ("3min", "5min", "15min", "30min", "1h")
TF_LABEL = {"1min": "1m", "3min": "3m", "5min": "5m", "15min": "15m", "30min": "30m", "1h": "1h"}
HIST = Path("data/history_x/seen_2021_2026")
OUT_RUN = Path("data/year_test/atlas_trades")
OUT_HIST = Path("data/year_test/atlas_history")
OUT_FWD = Path("data/year_test/atlas_forward")
SPLIT = pd.Timestamp("2023-11-17")            # halves of the 2021 → Sep 2026 data, as every playbook test
BIAS_ORDER = ("aligned", "neutral", "counter", "unknown")
# NY clock, [start, end): the bot trades 20:00 → 15:50
SESSIONS = (("Asia 20–02", 20, 2), ("London 02–08", 2, 8), ("NY AM 08–12", 8, 12), ("NY PM 12–16", 12, 16), ("Other", 16, 20))
SESSION_ORDER = [s[0] for s in SESSIONS]
MIN_CELL = 30                                 # slices with fewer trades are listed but not ranked
STAND_N = 100
BOOK_LABEL = {"practice": "Practice account", "playbook": "Playbook", "playbook_allhours": "Playbook, all hours",
              "playbook_nobias": "Playbook, no bias rule", "playbook_nobias_allhours": "Playbook + no bias, all hours",
              "h1_vol_trend": "Gold H1 trend", "ema21_rsi55": "EMA21 + RSI 55", "gold_breakout": "Gold breakout",
              "daily_rsi2_adx2": "Daily RSI2 ADX2", "c10_afternoon": "C10 afternoon"}


# ── shared helpers ───────────────────────────────────────────────────────────
def session_of(hour) -> str:
    h = int(hour)
    for name, a, b in SESSIONS:
        if (a <= h < b) if a < b else (h >= a or h < b):
            return name
    return "Other"


def bias_class(side, score, min_align: float) -> str:
    if score is None or not np.isfinite(score):
        return "unknown"
    if side * score >= min_align:
        return "aligned"
    if abs(score) < min_align:
        return "neutral"
    return "counter"


def norm_bias_mode(m) -> str:
    """A journal's bias_mode → aligned / neutral / counter / unknown / n/a (rule books have no bias)."""
    m = str(m or "").strip()
    if m.startswith("ignored:"):
        m = m.split(":", 1)[1]
    return {"aligned": "aligned", "in_doubt": "aligned", "neutral": "neutral", "neutral_reduced": "neutral",
            "counter": "counter", "reversal_exception": "counter", "n/a": "n/a"}.get(m, "unknown")


def boot_range(day: pd.Series, r: pd.Series, B: int = 2000, blk: int = 5, seed: int = 7) -> tuple[float, float]:
    """95% range of the mean R, resampling 5-day blocks of trading days (weekdays without trades count, empty)."""
    if len(r) < 10:
        return float("nan"), float("nan")
    d = pd.to_datetime(pd.Series(day.values))
    days = pd.bdate_range(d.min(), d.max())
    g = pd.DataFrame({"day": d.values, "r": r.values}).groupby("day").r.agg(["sum", "count"]).reindex(days, fill_value=0)
    s, k = g["sum"].to_numpy(float), g["count"].to_numpy(float)
    n = len(s)
    if n < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (B, -(-n // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :n] % n
    den = k[ix].sum(1)
    m = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    lo, hi = np.nanquantile(m, [0.025, 0.975])
    return float(lo), float(hi)


def stats(g: pd.DataFrame, boot: bool = True) -> dict:
    """g: r, pips, day, and (history) r2 = R at 2× costs, half (1/2)."""
    n = len(g)
    if not n:
        return {"n": 0}
    r, p = g["r"], g["pips"]
    w, lo_ = p[p > 0], p[p <= 0]
    out = {"n": n, "win": float((r > 0).mean()), "avg": float(r.mean()), "total": float(r.sum()),
           "pips": float(p.sum()), "avg_pips": float(p.mean()),
           "win_pips": float(w.mean()) if len(w) else float("nan"),
           "loss_pips": float(lo_.mean()) if len(lo_) else float("nan")}
    out["payoff"] = out["win_pips"] / abs(out["loss_pips"]) if len(w) and len(lo_) and out["loss_pips"] else float("nan")
    out["lo"], out["hi"] = boot_range(g["day"], r) if boot and n >= MIN_CELL else (float("nan"), float("nan"))
    if "r2" in g:
        out["avg2x"] = float(g["r2"].mean())
    if "half" in g:
        out["h1"] = float(r[g["half"] == 1].mean()) if (g["half"] == 1).any() else float("nan")
        out["h2"] = float(r[g["half"] == 2].mean()) if (g["half"] == 2).any() else float("nan")
    out["stands_out"] = bool(n >= STAND_N and out["lo"] > 0 and out.get("avg2x", 1) > 0
                             and out.get("h1", 1) > 0 and out.get("h2", 1) > 0)
    out["clearly_bad"] = bool(n >= STAND_N and out["hi"] < 0)
    return out


def f_r(x, d=2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{d}f}"


def f_p(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+,.0f}"


def f_rng(st) -> str:
    return "—" if not np.isfinite(st.get("lo", np.nan)) else f"{st['lo']:+.2f} to {st['hi']:+.2f}"


def mark(st) -> str:
    return " ✅" if st.get("stands_out") else " ⛔" if st.get("clearly_bad") else ""


def table(t: pd.DataFrame, keys: list[str], labels: list[str], min_n: int = 1, sort: str = "avg", top: int | None = None,
          extra: bool = True) -> list[str]:
    rows = []
    for k, g in t.groupby(keys, observed=True):
        st = stats(g)
        if st["n"] >= min_n:
            rows.append(((k,) if not isinstance(k, tuple) else k, st))
    rows.sort(key=lambda x: -(x[1][sort] if np.isfinite(x[1][sort]) else -9))
    if top:
        rows = rows[:top]
    head = labels + ["trades", "win", "avg R", "95% range", "net pips", "avg win pips", "avg loss pips"]
    if extra:
        head += ["2× costs", "halves"]
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for k, st in rows:
        line = [str(x) for x in k] + [f"{st['n']:,}", f"{st['win']:.0%}", f"**{f_r(st['avg'])}**{mark(st)}", f_rng(st),
                                      f_p(st["pips"]), f_p(st["win_pips"]), f_p(st["loss_pips"])]
        if extra:
            line += [f_r(st.get("avg2x", np.nan)), f"{f_r(st.get('h1', np.nan))} / {f_r(st.get('h2', np.nan))}"]
        md.append("| " + " | ".join(line) + " |")
    return md


def matrix(t: pd.DataFrame, row: str, col: str, cols: list, min_n: int = MIN_CELL, what: str = "avg") -> list[str]:
    """Rows × columns of avg R (trades). Cells under min_n trades are shown in brackets, not trusted."""
    md = ["| " + row + " | " + " | ".join(str(c) for c in cols) + " | all |", "|" + "---|" * (len(cols) + 2)]
    order = t.groupby(row).r.mean().sort_values(ascending=False).index
    for rk in order:
        g = t[t[row] == rk]
        cells = []
        for c in cols + ["__all__"]:
            gg = g if c == "__all__" else g[g[col] == c]
            if not len(gg):
                cells.append("")
                continue
            v = gg.r.mean() if what == "avg" else gg.pips.sum()
            s = f"{v:+.2f}" if what == "avg" else f"{v:+,.0f}"
            cells.append(f"{s} ({len(gg)})" if len(gg) >= min_n else f"[{s} ({len(gg)})]")
        md.append(f"| {rk} | " + " | ".join(cells) + " |")
    return md


# ── history: run ─────────────────────────────────────────────────────────────
def atlas_cfg(cfg, hist: Path) -> dict:
    from .agents.setup_first import ALLHOURS_WINDOWS
    from .strategies import BUILTIN, SETUPS
    cc = copy.deepcopy(cfg)
    cc["history_dir"] = str(hist)
    r = cc.setdefault("research", {})
    r["only_params"] = {c: {} for c in list(SETUPS) + list(BUILTIN)}          # default parameters only
    r["ignore_bias_rule"] = True
    r["profiles_only"] = ["std"]
    r.pop("exit_study", None)
    r.pop("exit_profiles", None)
    cc["sessions"]["entry_windows"] = ALLHOURS_WINDOWS
    return cc


def job_file(out: Path, sym: str, tf: str) -> Path:
    return out / f"trades_{sym}_{TF_LABEL.get(tf, tf)}.csv.gz"


def run(cfg=None, workers: int = 2, out: Path = OUT_RUN, hist: Path = HIST, syms=SYMS, tfs=TFS) -> list[Path]:
    from .playbook_test import build_history
    from .research import own_trades, run_job_frame
    from .strategies import BUILTIN, SETUPS
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    missing = {s for s in syms if not (hist / f"{s}.pkl").exists()}
    if missing:
        print(f"building history for {sorted(missing)} from the 2021 → Sep 2026 exports", flush=True)
        build_history(cfg, ["holdout_m1", "dev_m1"], missing, hist)
    syms = [s for s in syms if (hist / f"{s}.pkl").exists()]
    out.mkdir(parents=True, exist_ok=True)
    cc = atlas_cfg(cfg, hist)
    classes = list(SETUPS) + list(BUILTIN)
    todo = [(s, tf) for s in syms for tf in tfs if not job_file(out, s, tf).exists()]
    done = [(s, tf) for s in syms for tf in tfs if job_file(out, s, tf).exists()]
    print(f"atlas: {len(done)} jobs already done, {len(todo)} to run ({len(classes)} setups each, bias rule off, "
          f"all hours, std exit)", flush=True)
    todo.sort(key=lambda x: pd.Timedelta(x[1]))          # the slow short timeframes first
    status = out / "status.json"
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                             max_tasks_per_child=1) as ex:
        futs = {ex.submit(run_job_frame, (cc, s, tf, classes)): (s, tf) for s, tf in todo}
        for f in as_completed(futs):
            s, tf = futs[f]
            t = f.result()
            if len(t):
                t = own_trades(t)
            t.to_csv(job_file(out, s, tf), index=False)
            done.append((s, tf))
            status.write_text(json.dumps({"done": [f"{a} {TF_LABEL[b]}" for a, b in done],
                                          "left": len(syms) * len(tfs) - len(done)}, indent=1))
            print(f"  {s} {TF_LABEL[tf]}: {len(t):,} trades ({len(done)}/{len(syms) * len(tfs)} jobs)", flush=True)
    return [job_file(out, s, tf) for s, tf in done]


# ── history: report ──────────────────────────────────────────────────────────
def load_history(cfg, src: Path = OUT_RUN) -> pd.DataFrame:
    from . import units
    files = sorted(src.glob("trades_*.csv.gz"))
    parts = [pd.read_csv(f) for f in files]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    t = pd.concat(parts, ignore_index=True)
    t["ts"] = pd.to_datetime(t["ts"], utc=True).dt.tz_convert(NY)
    t = t[t.ts < pd.Timestamp("2026-10-01", tz=NY)]
    min_align = float(cfg["bias"]["min_align"])
    t["bias_cls"] = [bias_class(s, b, min_align) for s, b in zip(t.side, t.bias)]
    t["tf"] = t["tf"].map(lambda x: TF_LABEL.get(str(x), str(x)))
    t["hour"] = t.ts.dt.hour
    t["session"] = t.hour.map(session_of)
    t["side_lbl"] = np.where(t.side > 0, "long", "short")
    pip = t.sym.map(lambda s: units.pip_size(cfg, s))
    t["pips"] = t.r * t.R_px / pip if "R_px" in t else np.nan
    t["r2"] = t.r - t.cost_r
    t["day"] = pd.to_datetime(t["day"].astype(str))
    t["half"] = np.where(t.ts.dt.tz_localize(None) < SPLIT, 1, 2)
    t["setup"] = t["setup"].astype(str)
    return t.reset_index(drop=True)


SLICES = (  # (name, keys) — every slice goes into cells.csv; the ✅ count is over all of them
    ("setup", ["setup"]), ("setup × instrument", ["setup", "sym"]), ("setup × instrument × timeframe", ["setup", "sym", "tf"]),
    ("setup × instrument × bias", ["setup", "sym", "bias_cls"]),
    ("setup × instrument × timeframe × bias", ["setup", "sym", "tf", "bias_cls"]),
    ("setup × instrument × session", ["setup", "sym", "session"]),
    ("setup × instrument × timeframe × session", ["setup", "sym", "tf", "session"]),
    ("instrument × hour", ["sym", "hour"]), ("setup × instrument × hour", ["setup", "sym", "hour"]),
)


def all_slices(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, keys in SLICES:
        for k, g in t.groupby(keys, observed=True):
            if len(g) < MIN_CELL:
                continue
            k = k if isinstance(k, tuple) else (k,)
            st = stats(g)
            rows.append({"slice": name, **{c: "" for c in ("setup", "sym", "tf", "bias_cls", "session", "hour")},
                         **dict(zip(keys, k)), **{x: st.get(x) for x in
                         ("n", "win", "avg", "lo", "hi", "avg2x", "h1", "h2", "total", "pips", "avg_pips", "win_pips",
                          "loss_pips", "payoff", "stands_out", "clearly_bad")}})
    return pd.DataFrame(rows)


def history_report(cfg=None, src: Path = OUT_RUN, out: Path = OUT_HIST) -> dict:
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    t = load_history(cfg, src)
    out.mkdir(parents=True, exist_ok=True)
    if not len(t):
        (out / "report.md").write_text("# Trade atlas: history\n\nNo trades yet: run `./fx.sh atlas run` first.\n")
        return {"n": 0}
    jobs = sorted(f.name for f in src.glob("trades_*.csv.gz"))
    cells = all_slices(t)
    cells.to_csv(out / "cells.csv", index=False)
    n_cells, n_good, n_bad = len(cells), int(cells.stands_out.sum()), int(cells.clearly_bad.sum())
    eligible = int((cells.n >= STAND_N).sum())
    syms = [s for s in SYMS if s in set(t.sym)]
    tfs = [x for x in ("3m", "5m", "15m", "30m", "1h") if x in set(t.tf)]
    md = ["# Trade atlas: every playbook setup by instrument, timeframe, hour and bias (history)", "",
          f"**{len(t):,} trades**, {t.ts.min():%Y-%m-%d} → {t.ts.max():%Y-%m-%d}, OANDA bid/ask with the real spread, "
          f"replayed by the playbook's own engine. {t.setup.nunique()} setups (default parameters) × {len(syms)} "
          f"instruments × {len(tfs)} timeframes ({len(jobs)} of 15 jobs finished). Standard exit (partial at +1R, "
          "runner trailed), one trade at a time per setup, entries at all hours 20:00 → 15:50 NY, news blackouts on.",
          "",
          "**The bias rule is OFF here.** Each trade's bias at entry is classed exactly as the live rule would: "
          f"aligned (side × score ≥ {cfg['bias']['min_align']}), neutral (|score| below it) or counter. The live "
          "playbook trades only the aligned ones.", "",
          "**How to read.** avg R = average result per trade in units of its risk, after the spread. 95% range = where "
          "the true average probably lies (5-day blocks of trading days). Pips = R × the stop distance (gold 1 pip = "
          "$0.10; NDQ/US30 1 pip = 1 point), per initial unit. Halves split at 2023-11-17. Brackets = under "
          f"{MIN_CELL} trades, don't trust.", "",
          f"✅ **stands out**: ≥ {STAND_N} trades, 95% range above 0, both halves positive, positive at 2× costs. "
          f"⛔ **clearly bad**: ≥ {STAND_N} trades and the whole 95% range below 0.", "",
          f"**This is a map, not a test.** {n_cells:,} slices were screened ({eligible:,} with ≥ {STAND_N} trades); "
          f"about {max(1, round(0.025 * eligible * 0.5)):,} could stand out by luck alone. **{n_good} stand out, "
          f"{n_bad} are clearly bad.** Anything here earns a registered test and the untouched 2016–2020 data before "
          "it trades. Every slice is in `cells.csv` (filter it yourself).", ""]
    # 1. bias: the question asked first
    md += ["## 1. Bias at entry: aligned vs neutral vs counter", "", "### All setups, by instrument", ""]
    md += table(t, ["sym", "bias_cls"], ["instrument", "bias"])
    md += ["", "### Per setup: avg R (trades) by bias, all instruments", ""]
    md += matrix(t, "setup", "bias_cls", [b for b in BIAS_ORDER if b in set(t.bias_cls)])
    md += ["", "### Per setup: net pips by bias", ""]
    md += matrix(t, "setup", "bias_cls", [b for b in BIAS_ORDER if b in set(t.bias_cls)], what="pips")
    # 2. setups overall and by instrument
    md += ["", "## 2. Setups", "", "### Overall (all instruments, timeframes, hours, bias)", ""]
    md += table(t, ["setup"], ["setup"])
    md += ["", "### Setup × instrument: avg R (trades)", ""]
    md += matrix(t, "setup", "sym", syms)
    md += ["", "### Setup × instrument: net pips", ""]
    md += matrix(t, "setup", "sym", syms, what="pips")
    # 3. timeframes per instrument
    md += ["", "## 3. Timeframe: avg R (trades), per instrument", ""]
    for s in syms:
        md += [f"### {s}", ""] + matrix(t[t.sym == s], "setup", "tf", tfs) + [""]
    # 4. hours and sessions
    md += ["## 4. Hour of entry (NY time)", "", "### All setups: by instrument and hour", ""]
    hrs = sorted(t.hour.unique(), key=lambda h: (h - 20) % 24)
    md += ["| hour (NY) | " + " | ".join(f"{s} avg R (trades) | {s} net pips" for s in syms) + " |",
           "|---|" + "---|---|" * len(syms)]
    for h in hrs:
        line = [f"{h:02d}:00"]
        for s in syms:
            g = t[(t.sym == s) & (t.hour == h)]
            line += [f"{g.r.mean():+.3f} ({len(g):,})" if len(g) else "", f"{g.pips.sum():+,.0f}" if len(g) else ""]
        md.append("| " + " | ".join(line) + " |")
    md += ["", "### Setup × session: avg R (trades), per instrument", ""]
    for s in syms:
        md += [f"#### {s}", ""] + matrix(t[t.sym == s], "setup", "session",
                                         [x for x in SESSION_ORDER if x in set(t.session)]) + [""]
    # 5. pips: low win rate but positive pips
    md += ["## 5. Pips: who wins small often, who wins big rarely (setup × instrument, ≥ 100 trades)", ""]
    md += table(t, ["setup", "sym"], ["setup", "instrument"], min_n=STAND_N, sort="pips")
    # 6. best and worst specific cells
    cell = cells[cells.slice == "setup × instrument × timeframe × bias"].copy()
    big = cell[cell.n >= STAND_N].sort_values("avg", ascending=False)
    md += ["", "## 6. Best and worst specific combinations (setup × instrument × timeframe × bias, ≥ 100 trades)", ""]
    hd = "| setup | instrument | tf | bias | trades | win | avg R | 95% range | 2× costs | halves | net pips |\n|---|---|---|---|---|---|---|---|---|---|---|"

    def crow(r):
        st = r.to_dict()
        return (f"| {r.setup} | {r.sym} | {r.tf} | {r.bias_cls} | {int(r.n):,} | {r.win:.0%} | **{r.avg:+.3f}**{mark(st)} | "
                f"{f_rng(st)} | {f_r(r.avg2x, 3)} | {f_r(r.h1)} / {f_r(r.h2)} | {f_p(r.pips)} |")
    md += ["### Top 25", "", hd] + [crow(r) for _, r in big.head(25).iterrows()]
    md += ["", "### Bottom 15", "", hd] + [crow(r) for _, r in big.tail(15).iloc[::-1].iterrows()]
    good = cells[cells.stands_out].sort_values("avg", ascending=False)
    md += ["", f"## 7. Every slice that stands out ✅ ({len(good)})", ""]
    if len(good):
        md += ["| slice | setup | instrument | tf | bias | session | hour | trades | avg R | 95% range | net pips |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in good.iterrows():
            md.append(f"| {r.slice} | {r.setup} | {r.sym} | {r.tf} | {r.bias_cls} | {r.session} | {r.hour} | "
                      f"{int(r.n):,} | {r.avg:+.3f} | {r.lo:+.2f} to {r.hi:+.2f} | {f_p(r.pips)} |")
    else:
        md.append("None.")
    md += ["", "## 8. Long vs short, by instrument", ""] + table(t, ["sym", "side_lbl"], ["instrument", "side"])
    (out / "report.md").write_text("\n".join(md) + "\n")
    summ = {"trades": int(len(t)), "jobs": jobs, "slices": n_cells, "eligible": eligible, "stand_out": n_good,
            "clearly_bad": n_bad}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    return summ


# ── forward: the journals ────────────────────────────────────────────────────
def books(cfg) -> list[tuple[str, str]]:
    from .agents.setup_first import shadow_db_for, shadow_modes
    out = [("practice", cfg["storage"]["db_path"])]
    out += [(m, shadow_db_for(cfg, m, i == 0)) for i, m in enumerate(shadow_modes(cfg))]
    return out


def journal_cfg(cfg) -> dict:
    """The contract sizes the journals were written with. Reports run in sim mode, where config keeps the IBKR futures
    multipliers (gold 10, NDQ 2, US30 0.5); the books trade OANDA units (multiplier 1), so pips need the OANDA spec."""
    from .config import apply_broker
    c = copy.deepcopy(cfg)
    if c.get("broker", "ibkr") == "oanda" and not c.get("_broker_applied"):
        c["mode"] = "paper"
        apply_broker(c)
    return c


def load_forward(cfg, book_list=None) -> pd.DataFrame:
    from .dashboard.analysis import add_pips, setup_of, tf_of
    cfg = journal_cfg(cfg)
    parts = []
    for name, db in (book_list or books(cfg)):
        if not Path(db).exists():
            continue
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            t = pd.read_sql_query("SELECT id, symbol, side, strategy, opened, closed, r_multiple, realized, qty_initial, "
                                  "qty_gross, bias_mode, exit_reason FROM trades WHERE status='closed' "
                                  "AND r_multiple IS NOT NULL", con)
        finally:
            con.close()
        if len(t):
            parts.append(t.assign(book=name))
    if not parts:
        return pd.DataFrame()
    t = pd.concat(parts, ignore_index=True)
    t = add_pips(t, cfg)
    t["ts"] = pd.to_datetime(t.opened, utc=True, format="mixed").dt.tz_convert(NY)
    t["r"] = t.r_multiple.astype(float)
    t["setup"] = t.strategy.map(setup_of)
    t["tf"] = t.strategy.map(tf_of)
    t["sym"] = t.symbol
    t["hour"] = t.ts.dt.hour
    t["session"] = t.hour.map(session_of)
    t["bias_cls"] = t.bias_mode.map(norm_bias_mode)
    t["day"] = t.ts.dt.tz_localize(None).dt.normalize()
    t["side_lbl"] = t.side.str.lower()
    return t


def forward_report(cfg=None, out: Path = OUT_FWD, book_list=None) -> dict:
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    t = load_forward(cfg, book_list)
    out.mkdir(parents=True, exist_ok=True)
    if not len(t):
        (out / "report.md").write_text("# Trade atlas: forward\n\nNo closed trades in any journal.\n")
        return {"n": 0}
    # the same signal often appears in several playbook books: the pooled view counts it once
    t["key"] = t.sym + "|" + t.strategy.astype(str) + "|" + t.side + "|" + t.ts.dt.floor("min").astype(str)
    pool = t.sort_values("book").drop_duplicates("key")
    syms = [s for s in SYMS if s in set(t.sym)] + sorted(set(t.sym) - set(SYMS))
    md = ["# Trade atlas: what every book has actually done (forward)", "",
          f"{len(t):,} closed trades in {t.book.nunique()} books, {t.ts.min():%Y-%m-%d} → {t.ts.max():%Y-%m-%d} "
          f"(pooled across books, the same signal counted once: {len(pool):,}). Pips = net P&L ÷ ($ per pip × all "
          "units traded), as the dashboard. Bias = the bias at entry: the no-bias books record what the rule *would* "
          "have said, so they are where neutral and counter-bias trades show up; rule-based books (C10, gold "
          "breakout, EMA/RSI, …) have no bias (n/a).", "",
          f"**Samples are small.** A slice needs about {STAND_N} trades before its average means much; most here have "
          "far fewer. Read this as what happened, and use the history atlas for what tends to happen.", "",
          "## 1. Books", ""]
    md += table(t, ["book"], ["book"], extra=False)
    md += ["", "## 2. Bias at entry (pooled, each signal once)", ""]
    md += table(pool, ["bias_cls"], ["bias"], extra=False)
    md += ["", "### Setup × bias: avg R (trades)", ""]
    md += matrix(pool, "setup", "bias_cls", [b for b in ("aligned", "neutral", "counter", "unknown", "n/a")
                                             if b in set(pool.bias_cls)], min_n=10)
    md += ["", "### Per book × bias", ""] + table(t, ["book", "bias_cls"], ["book", "bias"], extra=False)
    md += ["", "## 3. Setups (pooled)", ""] + table(pool, ["setup"], ["setup"], extra=False, sort="pips")
    md += ["", "### Setup × instrument: avg R (trades)", ""] + matrix(pool, "setup", "sym", syms, min_n=10)
    md += ["", "### Setup × instrument: net pips", ""] + matrix(pool, "setup", "sym", syms, min_n=10, what="pips")
    md += ["", "### Setup × instrument × timeframe (pooled, ≥ 5 trades)", ""]
    md += table(pool, ["setup", "sym", "tf"], ["setup", "instrument", "tf"], min_n=5, extra=False)
    md += ["", "## 4. Hour of entry (NY, pooled)", ""]
    md += ["| hour (NY) | " + " | ".join(f"{s} avg R (trades) | {s} net pips" for s in syms) + " |",
           "|---|" + "---|---|" * len(syms)]
    for h in sorted(pool.hour.unique(), key=lambda h: (h - 20) % 24):
        line = [f"{h:02d}:00"]
        for s in syms:
            g = pool[(pool.sym == s) & (pool.hour == h)]
            line += [f"{g.r.mean():+.2f} ({len(g)})" if len(g) else "", f"{g.pips.sum():+,.0f}" if len(g) else ""]
        md.append("| " + " | ".join(line) + " |")
    md += ["", "### Setup × session: avg R (trades)", ""]
    md += matrix(pool, "setup", "session", [x for x in SESSION_ORDER if x in set(pool.session)], min_n=10)
    md += ["", "## 5. Per book: setup × instrument × timeframe", ""]
    for b, g in t.groupby("book"):
        md += [f"### {BOOK_LABEL.get(b, b)}", ""] + table(g, ["setup", "sym", "tf", "bias_cls"],
                                                          ["setup", "instrument", "tf", "bias"], extra=False, sort="pips") + [""]
    (out / "report.md").write_text("\n".join(md) + "\n")
    summ = {"trades": int(len(t)), "pooled": int(len(pool)), "books": sorted(t.book.unique())}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    return summ


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["forward", "run", "history"])
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    if a.what == "forward":
        print(forward_report())
    elif a.what == "run":
        run(workers=a.workers)
        print(history_report())
    else:
        print(history_report())


if __name__ == "__main__":
    main()
