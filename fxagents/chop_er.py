"""Efficiency-ratio chop filter (registered Nov 3 2026, research/chop_er/PREREGISTRATION_2026-11-03.md, before any run).

Skip a playbook 3m/5m entry when the market is choppy by Kaufman's efficiency ratio:
  er15 (primary)   ER(12) of the last 12 completed 15m candles < 0.30
  er1h (variant)   ER(12) of the last 12 completed 1h candles < 0.30
  info             chop15_skip (CHOP(14) 15m ≥ 61.8, the current filter's chop zone, as a skip), adx15 (ADX(14) 15m < 20)
Judged with the stricter judge (whatif_judge); vault only for er15 and only if it passed seen.

    python -m fxagents.chop_er [--period seen|vault]     (./fx.sh choper [seen|vault]) → data/year_test/chop_er_<period>/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf_whatif as W
from . import whatif_judge as J
from .regime import CHOP_HI, chop_index
from .round3_gemini import DAY, LOW, _bars

PRIMARY, VARIANT = "er15", "er1h"
INFO = ("chop15_skip", "adx15")
ER_N, ER_MIN, ADX_MIN = 12, 0.30, 20.0


def efficiency(close: np.ndarray, n: int = ER_N) -> float:
    """|c[-1] − c[-1-n]| / Σ|Δc| over the last n changes; NaN without n+1 closes or no movement."""
    c = np.asarray(close, float)
    if len(c) < n + 1:
        return float("nan")
    w = c[-(n + 1):]
    path = np.abs(np.diff(w)).sum()
    return float(abs(w[-1] - w[0]) / path) if path > 0 else float("nan")


def adx(b: pd.DataFrame, n: int = 14) -> float:
    """Wilder's ADX(n) of the last candle; NaN when too short."""
    if len(b) < 3 * n:
        return float("nan")
    h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    up, dn = h[1:] - h[:-1], l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    w = lambda x: pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = w(tr)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi, mdi = 100 * w(pdm) / atr, 100 * w(mdm) / atr
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    return float(w(np.nan_to_num(dx))[-1])


def measure(ts: pd.Timestamp, m1: pd.DataFrame) -> dict | None:
    df = m1.loc[(m1.index >= ts - 5 * DAY) & (m1.index < ts)]
    if not len(df):
        return None
    b15, b60 = _bars(df, 15, ts), _bars(df, 60, ts)
    if len(b15) < ER_N + 1 or len(b60) < ER_N + 1:
        return None
    ch = chop_index(b15)
    return {"er15": efficiency(b15["close"].to_numpy()), "er1h": efficiency(b60["close"].to_numpy()),
            "chop15": float(ch.iloc[-1]) if len(ch) and np.isfinite(ch.iloc[-1]) else float("nan"), "adx15": adx(b15)}


def flags(m: dict | None) -> dict:
    nan = {k: np.nan for k in (PRIMARY, VARIANT, *INFO)}
    if m is None:
        return nan
    f = lambda v, cond: float(cond(v)) if np.isfinite(v) else np.nan
    return {"er15": f(m["er15"], lambda v: v < ER_MIN), "er1h": f(m["er1h"], lambda v: v < ER_MIN),
            "chop15_skip": f(m["chop15"], lambda v: v >= CHOP_HI), "adx15": f(m["adx15"], lambda v: v < ADX_MIN)}


def flag_all(g: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    idx = m1.index
    rows = []
    for r in g.itertuples(index=False):
        ts = pd.Timestamp(r.ts)
        a, b = idx.searchsorted(ts - 5 * DAY), idx.searchsorted(ts)
        m = measure(ts, m1.iloc[a:b])
        rows.append({**flags(m), **({f"v_{k}": v for k, v in m.items()} if m else {})})
    return pd.concat([g.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def run(period: str, src: Path, hist: Path, out: Path) -> dict:
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    if period == "vault":
        p = Path("data/year_test/chop_er_seen/summary.json")
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not seen.get(PRIMARY, {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if er15 passed on seen (no seen run, or it failed)")
    t = W.load(src, "trades_seen_" if period == "seen" else "trades_old_")
    t = t[t.tf.isin(list(LOW))].reset_index(drop=True)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True)
    intended = len(t)
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}: {len(g)} trades unavailable", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(flag_all(g, m1))
        print(f"  {sym}: {len(g)} trades", flush=True)
    a = pd.concat(parts, ignore_index=True)
    names = [PRIMARY] if period == "vault" else [PRIMARY, VARIANT]

    def jd(k):
        ok = np.isfinite(a[k].to_numpy(float))
        return J.judge(a[ok].assign(**{k: a.loc[ok, k].astype(bool)}), k, period, intended)
    res = {k: jd(k) for k in names}
    info = {k: jd(k) for k in INFO} if period == "seen" else {}
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades_flagged.csv.gz", index=False)
    md = [f"# Efficiency-ratio chop filter ({period}, stricter judge)", "",
          "Registered Nov 3 2026 before running (research/chop_er/PREREGISTRATION_2026-11-03.md). Skip a playbook 3m/5m "
          f"entry when Kaufman's efficiency ratio ER({ER_N}) of the last completed candles is below {ER_MIN}. **er15** "
          "(15-minute) decides; er1h is a variant; the current CHOP chop zone and ADX < 20 are shown for comparison.", "",
          f"Cohort: {intended:,} trades on 3m / 5m, {t.r.mean():+.3f}R average.", "", J.HEAD]
    md += [J.fmt(res[k]) for k in names]
    if period == "seen":
        md += ["", ("**er15 passes on seen → one judgement on 2016–2020: ./fx.sh choper vault**" if res[PRIMARY].get("pass")
                    else "**er15 does not pass → the vault is not touched; the ER filter is closed.**"),
               "", "### For comparison (information only, never a pass)", "", J.HEAD] + [J.fmt(j) for j in info.values()]
        v = a[np.isfinite(a.get("v_er15", pd.Series(dtype=float)).astype(float))]
        if len(v):
            v = v.assign(b=pd.cut(v.v_er15.astype(float), [0, .1, .2, .3, .4, .5, .6, 1.01], right=False))
            md += ["", "### Average R by 15-minute efficiency ratio (descriptive)", "", "| ER(12) 15m | trades | avg R |",
                   "|---|---|---|"] + [f"| {k} | {len(g)} | {g.r.mean():+.3f} |" for k, g in v.groupby("b", observed=True)]
    else:
        md += ["", "**Verdict on 2016–2020: " + ("CONFIRMED → shadow tag on the live playbook; any switch is for the review"
                                              if res[PRIMARY].get("pass") else "NOT CONFIRMED → the ER filter is closed") + ".**"]
    md += ["", "A filter that passes but leaves the kept trades below zero still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "info": info}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Efficiency-ratio chop filter (registered Nov 3 2026)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    a = ap.parse_args(argv)
    seen = a.period == "seen"
    src = Path("data/year_test/playbook_test" if seen else "data/year_test/mtf_vault_trades")
    hist = Path("data/history_x/seen_2021_2026" if seen else "data/history_x/old_2016_2020")
    out = Path(f"data/year_test/chop_er_{a.period}")
    run(a.period, src, hist, out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
