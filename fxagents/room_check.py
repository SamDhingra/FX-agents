"""Room to the next M15 level (registered Oct 28 2026, research/room/PREREGISTRATION_2026-10-28.md, before any run).

From the losing-trade post-mortems: "if the nearest M15 low (for a short) is closer than the stop distance, the trade can't
reach 1R before support". Judged on the playbook's 3m/5m entries with the round-3 stricter judge.

  room_swing (primary)  nearest M15 swing low below entry (short) / swing high above entry (long) among the last 16 completed
                        M15 candles; flag when room < 1.0 x stop distance. No swing on that side -> not flagged.
  room_last2 (variant)  the low (short) / high (long) of the last 2 completed M15 candles; flag when 0 < room < 1.0 x stop.
  info only             room_swing at 0.75 x and 1.5 x the stop.

entry = close of the last M1 before the entry time; stop = risk_atr x ATR(14) of the entry-TF candles closed before it.

    python -m fxagents.room_check [--period seen|vault]   (./fx.sh roomcheck [seen|vault]) -> data/year_test/room_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf_whatif as W
from . import whatif_judge as J
from .round3_gemini import DAY, LOW, TFMIN, _atr14, _bars

PRIMARY, VARIANT = "room_swing", "room_last2"
INFO = {"room_swing_x0.75": 0.75, "room_swing_x1.5": 1.5}
N15 = 16


def swing_level(b15: pd.DataFrame, side: int, entry: float) -> float | None:
    """The nearest confirmed M15 swing on the target side of entry (swing low below a short's entry, swing high above a
    long's), among the given completed candles; the first and last candle can't be swings."""
    lo, hi = b15["low"].to_numpy(float), b15["high"].to_numpy(float)
    best = None
    for i in range(1, len(b15) - 1):
        if side < 0 and lo[i] < lo[i - 1] and lo[i] <= lo[i + 1] and lo[i] < entry:
            best = lo[i] if best is None else max(best, lo[i])
        if side > 0 and hi[i] > hi[i - 1] and hi[i] >= hi[i + 1] and hi[i] > entry:
            best = hi[i] if best is None else min(best, hi[i])
    return best


def measure(trade: dict, m1: pd.DataFrame) -> dict | None:
    """{entry, stop, room_swing, room_last2} for one trade from M1 strictly before its time; None when unavailable."""
    ts, side = trade["ts"], int(trade["side"])
    df = m1.loc[(m1.index >= ts - 5 * DAY) & (m1.index < ts)]
    if not len(df) or float(trade.get("risk_atr") or 0) <= 0:
        return None
    b15 = _bars(df, 15, ts)
    btf = _bars(df, TFMIN[trade["tf"]], ts)
    if len(b15) < N15 or len(btf) < 15:
        return None
    atf = _atr14(btf)
    if not np.isfinite(atf) or atf <= 0:
        return None
    entry, stop = float(df["close"].iloc[-1]), float(trade["risk_atr"]) * atf
    last = b15.iloc[-N15:]
    lvl = swing_level(last, side, entry)
    l2 = float(last["low"].iloc[-2:].min()) if side < 0 else float(last["high"].iloc[-2:].max())
    return {"entry": entry, "stop": stop, "room_swing": None if lvl is None else abs(entry - lvl),
            "room_last2": (entry - l2) if side < 0 else (l2 - entry)}


def flags(m: dict | None) -> dict:
    if m is None:
        return {k: np.nan for k in (PRIMARY, VARIANT, *INFO)}
    s, rs, r2 = m["stop"], m["room_swing"], m["room_last2"]
    out = {PRIMARY: float(rs is not None and rs < 1.0 * s), VARIANT: float(0 < r2 < 1.0 * s)}
    for k, x in INFO.items():
        out[k] = float(rs is not None and rs < x * s)
    return out


def flag_all(g: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    idx = m1.index
    rows = []
    for r in g.itertuples(index=False):
        ts = pd.Timestamp(r.ts)
        a, b = idx.searchsorted(ts - 5 * DAY), idx.searchsorted(ts)
        m = measure({"ts": ts, "side": int(r.side), "tf": LOW[str(r.tf)], "risk_atr": float(r.risk_atr)}, m1.iloc[a:b])
        rows.append({**flags(m), "room_swing_r": (m["room_swing"] / m["stop"]) if m and m["room_swing"] is not None else np.nan,
                     "room_last2_r": (m["room_last2"] / m["stop"]) if m else np.nan})
    return pd.concat([g.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def run(period: str, src: Path, hist: Path, out: Path) -> dict:
    if period == "vault":
        p = Path("data/year_test/room_seen/summary.json")
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not seen.get(PRIMARY, {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if room_swing passed on seen (no seen run, or it failed)")
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
    ok = a[np.isfinite(a[PRIMARY].to_numpy(float))]
    md = [f"# Room to the next M15 level ({period}, stricter judge)", "",
          "Registered Oct 28 2026 before running (research/room/PREREGISTRATION_2026-10-28.md); the idea came from the reviewers' "
          "post-mortems of losing trades. **room_swing** (decides): nearest M15 swing on the target side among the last 16 completed "
          "M15 candles closer than 1.0 × the stop. **room_last2** (variant): the last two completed M15 candles' low (short) / high "
          "(long) closer than 1.0 × the stop. Related check already failed: liqtest no_room (4H+ levels, 0.5 × ATR 1H).", "",
          f"Stricter judge: calendar halves split {J.split_of(period).date()}, circular 5-weekday blocks, random skipping within "
          "cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage.", "",
          f"Cohort: {intended:,} trades on 3m / 5m, {t.r.mean():+.3f}R average. Room ÷ stop (median, where a swing exists): "
          f"{np.nanmedian(ok['room_swing_r']):.2f}." if len(ok) else f"Cohort: {intended:,} trades.", "", J.HEAD]
    md += [J.fmt(res[k]) for k in names]
    if period == "seen":
        verdict = "passes on seen → one judgement on 2016–2020: ./fx.sh roomcheck vault" if res[PRIMARY].get("pass") else \
            "does not pass → the vault is not touched; the idea is closed"
        md += ["", f"**room_swing {verdict}.**"]
        md += ["", "### Sensitivity (information only, never a pass)", "", J.HEAD] + [J.fmt(j) for j in info.values()]
    else:
        md += ["", "**Verdict on 2016–2020: " + ("CONFIRMED → shadow tag on the live bot; any trading change is for the Nov 5 review"
                                              if res[PRIMARY].get("pass") else "NOT CONFIRMED → closed") + ".**"]
    md += ["", "## By cell (descriptive; it can't rescue a failed check)", "",
           "| cell | trades | avg R | " + " | ".join(f"{k} flagged (avg R) / kept (avg R)" for k in names) + " |",
           "|---|---|---|" + "---|" * len(names)]
    for cell, g in a.groupby("cell"):
        cells = []
        for k in names:
            v = g[np.isfinite(g[k].to_numpy(float))]
            fl, kp = v[v[k] == 1], v[v[k] == 0]
            cells.append(f"{len(fl)} ({fl.r.mean():+.2f}) / {len(kp)} ({kp.r.mean():+.2f})" if len(v) else "—")
        md.append(f"| {cell} | {len(g)} | {g.r.mean():+.3f} | " + " | ".join(cells) + " |")
    md += ["", "A check that passes but leaves the kept trades below zero still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "info": info}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Room to the next M15 level (registered Oct 28 2026)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    a = ap.parse_args(argv)
    seen = a.period == "seen"
    src = Path("data/year_test/playbook_test" if seen else "data/year_test/mtf_vault_trades")
    hist = Path("data/history_x/seen_2021_2026" if seen else "data/history_x/old_2016_2020")
    out = Path(f"data/year_test/room_{a.period}")
    run(a.period, src, hist, out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
