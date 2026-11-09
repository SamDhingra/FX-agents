"""Can Jev read the next hour from candles? Historical replay (registered Nov 9 2026:
research/jev_replay/PREREGISTRATION_2026-11-09.md).

Every NY weekday 02:00–14:00 (hourly) from 2026-01-02 to 2026-09-30, on XAUUSD, NDQ and US30, Jev gets an anonymised
as-of packet (no dates, prices or symbol; candles relative to the decision price in units of the hourly range) and two
yes/no questions about the next hour. Its forecast is blended with a deployable statistical benchmark and scored with
the multiclass Brier loss. Answers are cached, so a stopped run resumes without asking again.

    python -m fxagents.jev_replay [--dry-run] [--max-calls N] [--concurrency 4]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
SYMS = ("XAUUSD", "NDQ", "US30")
HOURS = tuple(range(2, 15))
START, END, SPLIT = pd.Timestamp("2026-01-02"), pd.Timestamp("2026-09-30"), pd.Timestamp("2026-05-15")
OUT = Path("data/year_test/jev_replay")
VERSION = "jev-replay-t60-v1"
K = ("up", "down", "neither")
LABEL = ("You see one liquid instrument as of a decision moment: its latest 15-minute and 1-hour candles, each given as "
         "minutes before the decision and (open, high, low, close) relative to the decision price, in units of the "
         "instrument's average hourly range (1.0 = one typical hourly range). Consider the NEXT four completed "
         "15-minute closes. UP: at least three of them close above the decision price AND the fourth closes at least "
         "+0.5 units above it. DOWN is the exact mirror. Every other path is NEITHER. Judge only from this packet. ")
Q_EVENT = "What is the probability that the outcome is UP or DOWN (not NEITHER)?"
Q_UP = "Conditional on the outcome being UP or DOWN, what is the probability that it is UP?"


# ── candles, labels, packets ─────────────────────────────────────────────────
def mid_bars(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Mid OHLC indexed by the candle's CLOSE (UTC)."""
    r = m1[["m_o", "m_h", "m_l", "m_c"]].resample(rule, label="right", closed="left")
    b = pd.DataFrame({"o": r["m_o"].first(), "h": r["m_h"].max(), "l": r["m_l"].min(), "c": r["m_c"].last()}).dropna()
    return b


def hourly_atr(h1: pd.DataFrame) -> pd.Series:
    tr = pd.concat([h1.h - h1.l, (h1.h - h1.c.shift()).abs(), (h1.l - h1.c.shift()).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr.rolling(14).mean()


def decisions(sym: str, m15: pd.DataFrame, h1: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Every eligible hourly decision in [start, end] (NY dates) with its features, packet and label."""
    Q = pd.Timedelta("15min")
    A = hourly_atr(h1)
    i15, ih = m15.index, h1.index
    out = []
    for d in pd.bdate_range(start, end):
        for hr in HOURS:
            t = (d + pd.Timedelta(hours=hr)).tz_localize(NY).tz_convert("UTC")
            k = i15.searchsorted(t, side="right") - 1
            if k < 15 or i15[k] != t or i15[k] - i15[k - 15] != 15 * Q:
                continue
            g = ih.searchsorted(t, side="right") - 1
            if g < 15 or ih[g] - ih[g - 1] != pd.Timedelta("1h") or t - ih[g] > 3 * Q:
                continue
            a = float(A.iloc[g])
            if not (math.isfinite(a) and a > 0):
                continue
            if k + 4 >= len(i15) or i15[k + 4] - t != 4 * Q:
                continue
            P = float(m15.c.iloc[k])
            cur, prev = h1.iloc[g], h1.iloc[g - 1]
            mid = (cur.h + cur.l) / 2
            last2 = m15.c.iloc[k - 1:k + 1]
            state = ("up" if cur.h > prev.h and cur.l > prev.l and (last2 > mid).all() else
                     "down" if cur.h < prev.h and cur.l < prev.l and (last2 < mid).all() else "mixed")
            mom = int(np.sign(P - m15.c.iloc[k - 4]))
            fut = m15.c.iloc[k + 1:k + 5].to_numpy()
            up = (fut > P).sum() >= 3 and fut[-1] >= P + a / 2
            dn = (fut < P).sum() >= 3 and fut[-1] <= P - a / 2
            y = "up" if up else "down" if dn else "neither"
            loc = t.tz_convert(NY)
            out.append({"sym": sym, "t": t, "date": d, "hour": hr, "state": state, "mom": mom, "y": y,
                        "packet": packet(m15.iloc[k - 15:k + 1], h1.iloc[g - 3:g + 1], P, a, t, loc)})
    return out


def packet(m15: pd.DataFrame, h1: pd.DataFrame, P: float, A: float, t: pd.Timestamp, loc: pd.Timestamp) -> dict:
    """The anonymised as-of packet: no symbol, date or price level."""
    def rows(df):
        return [[int((t - ts).total_seconds() // 60), *(round((float(v[c]) - P) / A, 3) for c in ("o", "h", "l", "c"))]
                for ts, v in df.iterrows()]
    return {"asset": "a liquid CFD", "decision_time_ny": loc.strftime("%a %H:%M"),
            "columns": ["minutes_before_decision", "open", "high", "low", "close"],
            "units": "price minus the decision price, divided by the average hourly range", "m15": rows(m15), "h1": rows(h1)}


def mirror(p: dict) -> dict:
    """The same packet upside down: prices sign-flipped, high and low swapped."""
    flip = lambda r: [r[0], -r[1], -r[3], -r[2], -r[4]]                          # noqa: E731
    return {**p, "m15": [flip(r) for r in p["m15"]], "h1": [flip(r) for r in p["h1"]]}


# ── benchmarks (deployable: the 252 sessions before each date) ──────────────
def _rates(y: pd.Series, prior: np.ndarray | None, w: float) -> np.ndarray:
    c = np.array([(y == k).sum() for k in K], float)
    if prior is None:
        return (c + 1) / (c.sum() + 3)
    return (c + w * prior) / (c.sum() + w)


def benchmarks(lab: pd.DataFrame, eval_dates) -> pd.DataFrame:
    """lab: every decision with sym, date, hour, state, mom, y (incl. the year before). Returns per decision in
    eval_dates the hour-only, momentum-only and measured probability vectors."""
    rows = []
    for sym, gs in lab.groupby("sym"):
        sessions = np.array(sorted(gs.date.unique()))
        for d in sorted(set(eval_dates) & set(gs.date)):
            i = np.searchsorted(sessions, d)
            past = gs[gs.date.isin(sessions[max(0, i - 252):i])]
            for r in gs[gs.date == d].itertuples():
                ph = past[past.hour == r.hour]
                parent = _rates(ph.y, None, 0)
                mom = _rates(ph[ph.mom == r.mom].y, parent, 20)
                meas = _rates(ph[(ph.mom == r.mom) & (ph.state == r.state)].y, parent, 20)
                rows.append({"sym": sym, "t": r.t, "b_hour": parent, "b_mom": mom, "b_meas": meas, "n_hist": len(ph)})
    return pd.DataFrame(rows)


def brier(p: np.ndarray, y: str) -> float:
    o = np.array([y == k for k in K], float)
    return float(((np.asarray(p, float) - o) ** 2).sum())


def compose(e: float, u: float) -> np.ndarray:
    return np.array([e * u, e * (1 - u), 1 - e])


# ── Jev ──────────────────────────────────────────────────────────────────────
def cache_key(sym, t, kind):
    return f"{sym}|{pd.Timestamp(t).isoformat()}|{kind}"


def load_cache(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
                out[r["key"]] = r
            except (ValueError, KeyError):
                continue
    return out


async def ask_all(todo: list[tuple[str, dict]], cache_path: Path, cfg, concurrency: int = 4, client=None) -> int:
    """todo: [(key, packet)]. Appends one JSON line per answer (or error) to the cache. Returns calls made."""
    from .jev import Unreadable, read_answers
    if client is None:
        from typesafe_sdk import AsyncTypeSafeClient
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise SystemExit("TYPESAFE_API_KEY is not set (.env)")
        client = AsyncTypeSafeClient(api_key=key, model=(cfg.get("jev") or {}).get("model") or None, timeout=30)
    try:
        from typesafe_sdk import Noul
    except ImportError:                                   # tests only: a fake client never needs the real type
        def Noul(instructions):                           # noqa: N802
            return {"type": "noul", "instructions": instructions}
    questions = {"event": Noul(instructions=LABEL + Q_EVENT), "up_if_event": Noul(instructions=LABEL + Q_UP)}
    sem, n = asyncio.Semaphore(concurrency), 0
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    f = cache_path.open("a")

    async def one(key, pk):
        nonlocal n
        async with sem:
            rec = {"key": key, "version": VERSION, "asked": pd.Timestamp.now(tz="UTC").isoformat()}
            for attempt in range(3):
                try:
                    resp = await asyncio.wait_for(client.system_one(state=pk, questions=questions), timeout=40)
                    a = read_answers(resp, questions)
                    rec.update(e=a["event"]["value"], u=a["up_if_event"]["value"], model=getattr(resp, "model", None),
                               ok=True, error=None)
                    break
                except Unreadable as ex:
                    rec.update(ok=False, error=f"unreadable: {ex}"[:200])
                    break
                except Exception as ex:  # noqa: BLE001 — network / rate limit: retry, then record the failure
                    rec.update(ok=False, error=f"{type(ex).__name__}: {ex}"[:200])
                    await asyncio.sleep(2 * (attempt + 1))
            n += 1
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if n % 200 == 0:
                print(f"  {n} Jev calls", flush=True)
    try:
        await asyncio.gather(*(one(k, p) for k, p in todo))
    finally:
        f.close()
    return n


# ── judge ────────────────────────────────────────────────────────────────────
def block_ci(dates: pd.Series, d: np.ndarray, B: int = 10_000, blk: int = 5, seed: int = 7) -> tuple[float, float]:
    """Mean d with circular 5-weekday blocks over every weekday of the period; a date's instruments stay together."""
    wd = pd.bdate_range(START, END)
    pos = np.clip(np.searchsorted(wd.to_numpy(), pd.to_datetime(dates).to_numpy()), 0, len(wd) - 1)
    S, N = np.zeros(len(wd)), np.zeros(len(wd))
    np.add.at(S, pos, d)
    np.add.at(N, pos, 1)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(wd) / blk))
    idx = (rng.integers(0, len(wd), (B, nb))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :len(wd)] % len(wd)
    s, n = S[idx].sum(1), N[idx].sum(1)
    m = s[n > 0] / n[n > 0]
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(lo), float(hi)


def judge(v: pd.DataFrame) -> dict:
    """v: eval decisions with y, b_hour, b_mom, b_meas, jev (vector or None), jev_m (mirror vector or None)."""
    has = v.jev.map(lambda x: x is not None)
    cand = [0.5 * (b + j) if j is not None else b for b, j in zip(v.b_meas, v.jev)]
    L = {"hour": [brier(p, y) for p, y in zip(v.b_hour, v.y)], "mom": [brier(p, y) for p, y in zip(v.b_mom, v.y)],
         "meas": [brier(p, y) for p, y in zip(v.b_meas, v.y)], "cand": [brier(p, y) for p, y in zip(cand, v.y)]}
    L = {k: np.asarray(x) for k, x in L.items()}
    d = L["meas"] - L["cand"]
    lo, hi = block_ci(v.date, d)
    first = (v.date < SPLIT).to_numpy()
    halves = (float(d[first].mean()), float(d[~first].mean()))
    cov = float(has.mean())
    j = v[has]
    jl = np.array([brier(p, y) for p, y in zip(j.jev, j.y)]) if len(j) else np.array([])
    side = np.array(["up" if p[0] >= p[1] else "down" for p in j.jev]) if len(j) else np.array([])
    moved = (j.y != "neither").to_numpy() if len(j) else np.array([], bool)
    momside = np.where(j.mom > 0, "up", np.where(j.mom < 0, "down", "none")) if len(j) else np.array([])
    mirror_ok = v.jev_m.map(lambda x: x is not None) & has
    mm = v[mirror_ok]
    mir = {}
    if len(mm):
        pu = np.array([p[0] for p in mm.jev]); pdm = np.array([p[1] for p in mm.jev_m])
        pe = np.array([p[2] for p in mm.jev]); pem = np.array([p[2] for p in mm.jev_m])
        mir = {"n": int(len(mm)), "corr_up_vs_mirror_down": float(np.corrcoef(pu, pdm)[0, 1]) if len(mm) > 2 else np.nan,
               "mean_abs_gap": float(np.abs(pu - pdm).mean()), "mean_abs_gap_neither": float(np.abs(pe - pem).mean()),
               "mean_p_up": float(pu.mean()), "mean_p_up_mirror": float(np.array([p[0] for p in mm.jev_m]).mean())}
    cal = []
    if len(j):
        pe = np.array([1 - p[2] for p in j.jev])
        for a, b in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
            m = (pe >= a) & (pe < b)
            if m.any():
                cal.append([f"{a:.1f}–{min(b, 1):.1f}", int(m.sum()), float(pe[m].mean()), float(moved[m].mean())])
    g = {"Jev answered ≥ 90%": cov >= 0.9, "95% range above 0": lo > 0,
         "both halves > 0": halves[0] > 0 and halves[1] > 0, "beats momentum-only": L["cand"].mean() < L["mom"].mean()}
    by = {}
    for s, gs in v.groupby("sym"):
        ix = (v.sym == s).to_numpy()
        hj = gs.jev.map(lambda x: x is not None).to_numpy()
        by[s] = {"n": int(len(gs)), "meas": float(L["meas"][ix].mean()), "cand": float(L["cand"][ix].mean()),
                 "jev_alone": float(np.mean([brier(p, y) for p, y in zip(gs.jev[hj], gs.y[hj])])) if hj.any() else np.nan}
    return {"n": int(len(v)), "coverage": cov, "brier": {k: float(x.mean()) for k, x in L.items()},
            "jev_alone": float(jl.mean()) if len(jl) else np.nan, "meas_on_jev": float(L["meas"][has.to_numpy()].mean()) if has.any() else np.nan,
            "d": float(d.mean()), "lo": lo, "hi": hi, "halves": halves,
            "outcomes": v.y.value_counts().to_dict(),
            "dir_jev": float((side[moved] == j.y.to_numpy()[moved]).mean()) if moved.any() else np.nan,
            "dir_mom": float((momside[moved] == j.y.to_numpy()[moved]).mean()) if moved.any() else np.nan,
            "moved_n": int(moved.sum()), "mirror": mir, "calibration": cal, "by": by,
            "models": sorted({str(m) for m in v.model.dropna()}) if "model" in v else [],
            "gates": g, "pass": all(g.values())}


def f3(x):
    return "—" if x is None or not np.isfinite(x) else f"{x:.4f}"


def report(r: dict, counts: dict) -> str:
    md = ["# Can Jev read the next hour from candles? Historical replay", "",
          "Registered Nov 9 2026 (research/jev_replay/PREREGISTRATION_2026-11-09.md). Hourly decisions 02:00–14:00 NY, "
          "2026-01-02 → 2026-09-30, XAUUSD / NDQ / US30. Jev saw anonymised candles only (no dates, prices or symbol). "
          "Outcome over the next hour: UP / DOWN (a sustained move of ≥ ½ hourly range) or NEITHER. Lower Brier = better "
          "(always NEITHER ≈ the base rate).", "",
          f"Decisions: {r['n']:,} · Jev answered {r['coverage']:.1%} · outcomes " +
          ", ".join(f"{k} {v:,}" for k, v in r["outcomes"].items()) + f" · Jev calls made this run: {counts.get('calls', 0):,}",
          f"Model(s): {', '.join(r['models']) or 'unknown'}", "",
          "| forecast | mean Brier |", "|---|---|",
          f"| hour-only benchmark | {f3(r['brier']['hour'])} |", f"| momentum-only benchmark | {f3(r['brier']['mom'])} |",
          f"| measured benchmark (primary baseline) | {f3(r['brier']['meas'])} |",
          f"| **measured + Jev (candidate)** | **{f3(r['brier']['cand'])}** |",
          f"| Jev alone (where it answered) | {f3(r['jev_alone'])} (measured on the same: {f3(r['meas_on_jev'])}) |", "",
          f"**Improvement of the candidate over measured: {r['d']:+.5f} (95% range {r['lo']:+.5f} to {r['hi']:+.5f}); "
          f"halves {r['halves'][0]:+.5f} / {r['halves'][1]:+.5f}. "
          + ("PASS" if r["pass"] else "FAIL: " + ", ".join(k for k, ok in r["gates"].items() if not ok)) + ".**", "",
          "## Information", "",
          f"- direction when the hour did move ({r['moved_n']:,}): Jev's likelier side right {r['dir_jev']:.1%}, "
          f"following the previous hour {r['dir_mom']:.1%}"]
    m = r.get("mirror") or {}
    if m:
        md.append(f"- mirror check ({m['n']:,}): Jev's p(up) vs its p(down) on the upside-down packet: correlation "
                  f"{m['corr_up_vs_mirror_down']:.2f}, mean gap {m['mean_abs_gap']:.3f}; p(neither) gap "
                  f"{m['mean_abs_gap_neither']:.3f}; average p(up) {m['mean_p_up']:.3f} vs {m['mean_p_up_mirror']:.3f} upside down")
    md += ["", "| Jev p(move) band | decisions | average p(move) | actually moved |", "|---|---|---|---|"]
    md += [f"| {b} | {n:,} | {p:.2f} | {o:.2f} |" for b, n, p, o in r["calibration"]]
    md += ["", "| instrument | decisions | measured | candidate | Jev alone |", "|---|---|---|---|---|"]
    md += [f"| {s} | {x['n']:,} | {f3(x['meas'])} | {f3(x['cand'])} | {f3(x['jev_alone'])} |" for s, x in r["by"].items()]
    md += ["", ("**Jev adds forecast skill on clean candles: a separately registered trading test comes next.**" if r["pass"] else
                "**Jev adds nothing over a simple statistical forecast of the next hour: evidence for removing or reducing its "
                "weight in the hourly pick (Sam's decision). Not re-run with another prompt on these data.**")]
    return "\n".join(md) + "\n"


# ── run ──────────────────────────────────────────────────────────────────────
def build(root: Path = Path("data/export"), syms=SYMS) -> pd.DataFrame:
    from .imom import load_sets
    rows = []
    for s in syms:
        m1 = load_sets(("dev_m1",), s, root)
        if m1 is None:
            print(f"  no dev_m1 export for {s}", flush=True)
            continue
        rows += decisions(s, mid_bars(m1, "15min"), mid_bars(m1, "1h"), pd.Timestamp("2024-10-07"), END)
    return pd.DataFrame(rows)


def run(dry_run=False, max_calls=None, concurrency=4, out: Path = OUT, cfg=None, root: Path = Path("data/export"),
        client=None, lab: pd.DataFrame | None = None) -> dict:
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    out.mkdir(parents=True, exist_ok=True)
    lab = build(root) if lab is None else lab
    ev = lab[(lab.date >= START) & (lab.date <= END)].reset_index(drop=True)
    cache_path = out / "jev_answers.jsonl"
    cache = load_cache(cache_path)
    todo = []
    for r in ev.itertuples():
        for kind, pk in (("orig", r.packet), ("mirror", mirror(r.packet))):
            k = cache_key(r.sym, r.t, kind)
            if k not in cache:
                todo.append((k, pk))
    tokens = int(np.mean([len(json.dumps(p)) for _, p in todo[:200]]) / 3.5 + 260) if todo else 0
    print(f"decisions {len(ev):,} · cached answers {len(cache):,} · still to ask {len(todo):,} "
          f"(≈ {tokens} input tokens each, ≈ ${len(todo) * tokens * 0.042 / 1e6:.2f})", flush=True)
    if dry_run:
        (out / "sample_packet.json").write_text(json.dumps(todo[0][1] if todo else {}, indent=1))
        return {"dry_run": True, "decisions": len(ev), "todo": len(todo), "tokens_each": tokens}
    if max_calls is not None:
        todo = todo[:max_calls]
    calls = asyncio.run(ask_all(todo, cache_path, cfg, concurrency, client)) if todo else 0
    cache = load_cache(cache_path)

    def vec(sym, t, kind):
        r = cache.get(cache_key(sym, t, kind))
        return compose(r["e"], r["u"]) if r and r.get("ok") else None
    bm = benchmarks(lab[["sym", "t", "date", "hour", "state", "mom", "y"]], sorted(ev.date.unique()))
    v = ev.drop(columns=["packet"]).merge(bm, on=["sym", "t"], how="inner")
    v["jev"] = [vec(s, t, "orig") for s, t in zip(v.sym, v.t)]
    v["jev_m"] = [vec(s, t, "mirror") for s, t in zip(v.sym, v.t)]
    v["model"] = [(cache.get(cache_key(s, t, "orig")) or {}).get("model") for s, t in zip(v.sym, v.t)]
    asked = sum(1 for k in cache if k.endswith("|orig"))
    if asked < len(ev):
        res = {"complete": False, "decisions": len(ev), "answered_or_tried": asked, "calls": calls}
        (out / "summary.json").write_text(json.dumps(res, indent=1))
        print(f"partial: {asked:,} of {len(ev):,} decisions asked; run again to continue", flush=True)
        return res
    res = judge(v)
    res["complete"] = True
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "report.md").write_text(report(res, {"calls": calls}))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-calls", type=int)
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    r = run(a.dry_run, a.max_calls, a.concurrency)
    print("result:", "dry run" if r.get("dry_run") else "PASS" if r.get("pass") else "partial" if not r.get("complete") else "FAIL")


if __name__ == "__main__":
    sys.exit(main())
