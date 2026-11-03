"""Trailing stop for the gold overnight breakout (registered Nov 3 2026, research/gold_trail/PREREGISTRATION_2026-11-03.md,
before any run). Same entries as the gold_breakout book (fxagents/breakout_test.py: 00–07 GMT+3 range, stop orders at
the range, 1% stop, flat 20:00 GMT+3, real bid/ask); only the stop after entry changes.

    python -m fxagents.gold_trail [--period seen|vault]     (./fx.sh goldtrail [seen|vault])
    → data/year_test/gold_trail_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .breakout_test import MIN_RANGE_MIN, RANGE_END, SL_PCT, to_broker
from .simple_rules import NY, PIP, load

PERIODS = {"seen": (["holdout_m1", "dev_m1"], "2021-01-01", "2026-10-01", "2023-11-17"),
           "vault": (["old_m1"], "2016-01-01", "2021-01-01", "2018-07-01")}
OUT = {p: Path(f"data/year_test/gold_trail_{p}") for p in PERIODS}
CLOSE_HOUR = 20
MODES = ("base", "trail_half", "be_half", "trail_1r", "chandelier")
PRIMARY = "trail_half"
SEED = 20261103


def arrays(m1: pd.DataFrame) -> dict:
    a = {k: m1[k].to_numpy(float) for k in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
                                             "m_h", "m_l")}
    a["idx"], a["ns"] = m1.index, m1.index.as_unit("ns").asi8
    mid = pd.DataFrame({"h": m1["m_h"], "l": m1["m_l"], "c": (m1["bid_c"] + m1["ask_c"]) / 2}, index=m1.index)
    b = mid.resample("15min", label="left", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
    pc = b.c.shift()
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    done = (b.index + pd.Timedelta("15min")).as_unit("ns").asi8              # ATR known at each candle's close
    k = np.searchsorted(done, a["ns"], side="right") - 1
    av = atr.to_numpy()
    a["atr15"] = np.where(k >= 0, av[np.maximum(k, 0)], np.nan)
    return a


def entries(a: dict) -> list[tuple]:
    """(j, side, entry, stop, risk, spread, t1) per broker day, exactly as breakout_test.run (pct stop, 20:00 close)."""
    bday, bmin = to_broker(a["idx"])
    starts = np.r_[0, np.nonzero(np.diff(bday))[0] + 1]
    ends = np.r_[starts[1:], len(bday)]
    out = []
    for k, (s0, e0) in enumerate(zip(starts, ends)):
        if k == 0:
            continue
        mins = bmin[s0:e0]
        rng_n = int(np.searchsorted(mins, RANGE_END))
        if rng_n < MIN_RANGE_MIN:
            continue
        rh, rl = a["m_h"][s0:s0 + rng_n].max(), a["m_l"][s0:s0 + rng_n].min()
        t0 = s0 + rng_n
        t1 = s0 + int(np.searchsorted(mins, CLOSE_HOUR * 60))
        if t1 <= t0:
            continue
        up, dn = a["ask_h"][t0:t1] >= rh, a["bid_l"][t0:t1] <= rl
        iu = int(np.argmax(up)) if up.any() else None
        idn = int(np.argmax(dn)) if dn.any() else None
        if iu is None and idn is None:
            continue
        if idn is None or (iu is not None and iu < idn):
            side, j = 1, t0 + iu
        elif iu is None or idn < iu:
            side, j = -1, t0 + idn
        else:
            o = (a["ask_o"][t0 + iu] + a["bid_o"][t0 + iu]) / 2
            side, j = (1, t0 + iu) if (rh - o) <= (o - rl) else (-1, t0 + idn)
        entry = max(rh, a["ask_o"][j]) if side > 0 else min(rl, a["bid_o"][j])
        spread = a["ask_o"][j] - a["bid_o"][j]
        stop = entry * (1 - side * SL_PCT / 100)
        risk = side * (entry - stop)
        if risk > 0:
            out.append((j, side, entry, stop, risk, spread, t1))
    return out


def walk(a: dict, j0: int, j_end: int, side: int, entry: float, stop: float, risk: float, mode: str) -> tuple[int, float, str]:
    """Minute by minute from the entry minute: stop check with the level set BEFORE this minute, then move the stop.
    Same closure / time-exit handling as breakout_test.exit_walk."""
    t = a["ns"]
    j_end = min(j_end, len(t))
    gaps = np.nonzero(np.diff(t[j0:j_end + 1]) > 60 * 60_000_000_000)[0]
    stop_end = j0 + int(gaps[0]) + 1 if len(gaps) else j_end
    best = entry
    moved_be = False
    for j in range(j0, stop_end):
        lo = a["bid_l"][j] if side > 0 else a["ask_h"][j]
        if (lo - stop) * side <= 0:
            op = a["bid_o"][j] if side > 0 else a["ask_o"][j]
            px = stop if j == j0 else (min(stop, op) if side > 0 else max(stop, op))
            return j, px, "stop" if mode == "base" or abs(stop - entry * (1 - side * SL_PCT / 100)) < 1e-9 else "trail"
        if mode == "base":
            continue
        hi = a["bid_h"][j] if side > 0 else a["ask_l"][j]
        if (hi - best) * side > 0:
            best = hi
        gain = (best - entry) * side
        new = stop
        if mode == "trail_half" and gain >= 0.5 * risk:
            new = best - side * 0.5 * risk
        elif mode == "trail_1r" and gain >= 1.0 * risk:
            new = best - side * 1.0 * risk
        elif mode == "be_half" and gain >= 0.5 * risk and not moved_be:
            new, moved_be = entry, True
        elif mode == "chandelier" and np.isfinite(a["atr15"][j]):
            new = best - side * 3.0 * a["atr15"][j]
        if (new - stop) * side > 0:
            stop = new
    if len(gaps):
        j = stop_end - 1
        return j, (a["bid_c"][j] if side > 0 else a["ask_c"][j]), "closure"
    if j_end >= len(t):
        j = len(t) - 1
        return j, (a["bid_c"][j] if side > 0 else a["ask_c"][j]), "end"
    return j_end, (a["bid_o"][j_end] if side > 0 else a["ask_o"][j_end]), "time"


def trades(m1: pd.DataFrame) -> pd.DataFrame:
    a = arrays(m1)
    rows = []
    for j, side, entry, stop, risk, spread, t1 in entries(a):
        r = {"entry_time": a["idx"][j], "side": side, "entry": entry, "risk": risk, "spread": spread}
        for mode in MODES:
            jx, px, why = walk(a, j, t1, side, entry, stop, risk, mode)
            r[f"R_{mode}"] = side * (px - entry) / risk
            r[f"pts_{mode}"] = side * (px - entry)
            r[f"why_{mode}"] = why
        rows.append(r)
    return pd.DataFrame(rows)


def paired(t: pd.DataFrame, d: np.ndarray, seed: int = SEED) -> tuple[float, float]:
    """95% range of the mean d, resampling 5-day blocks of NY trading days."""
    day = pd.to_datetime(t.entry_time).dt.tz_convert(NY).dt.normalize()
    days = pd.bdate_range(day.min().tz_localize(None), day.max().tz_localize(None))
    g = pd.DataFrame({"d": d, "day": day.dt.tz_localize(None)}).groupby("day").d.agg(["sum", "count"]).reindex(days, fill_value=0)
    s, k = g["sum"].to_numpy(), g["count"].to_numpy()
    n = len(s)
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (4000, -(-n // 5)))[:, :, None] + np.arange(5)).reshape(4000, -1)[:, :n] % n
    den = k[ix].sum(1)
    m = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    lo, hi = np.nanquantile(m, [0.025, 0.975])
    return float(lo), float(hi)


def judge(t: pd.DataFrame, mode: str, split: str) -> dict:
    d = (t[f"R_{mode}"] - t["R_base"]).to_numpy(float)
    lo, hi = paired(t, d)
    first = (pd.to_datetime(t.entry_time) < pd.Timestamp(split, tz=NY)).to_numpy()
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    changed = int((np.abs(d) > 1e-9).sum())
    gates = {"changed ≥ 100": changed >= 100, "95% range above 0": lo > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves)}
    pip = PIP["XAUUSD"]
    return {"mode": mode, "n": len(t), "changed": changed, "avg_base": float(t.R_base.mean()), "avg": float(t[f"R_{mode}"].mean()),
            "d": float(d.mean()), "lo": lo, "hi": hi, "halves": halves, "win": float((t[f"R_{mode}"] > 0).mean()),
            "net_pips": float(t[f"pts_{mode}"].sum() / pip), "gates": gates, "pass": all(gates.values())}


def line(name: str, j: dict, gate: bool) -> str:
    v = ("**PASS**" if j["pass"] else "**no** (" + ", ".join(k for k, ok in j["gates"].items() if not ok) + ")") if gate else "info"
    return (f"| {name} | {v} | {j['changed']} of {j['n']} | {j['win']:.0%} | {j['avg']:+.3f} | {j['d']:+.3f} "
            f"({j['lo']:+.3f} to {j['hi']:+.3f}) | {j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['net_pips']:,.0f} |")


def run(period: str, out: Path | None = None, m1: pd.DataFrame | None = None) -> dict:
    out = out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not (seen.get(PRIMARY) or {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if trail_half passed on seen")
    sets, a, b, split = PERIODS[period]
    if m1 is None:
        parts = [load(Path("data/export") / s / "XAUUSD_M1.csv.gz") for s in sets
                 if (Path("data/export") / s / "XAUUSD_M1.csv.gz").exists()]
        if not parts:
            raise SystemExit(f"no XAUUSD bid/ask export in {sets}")
        m1 = pd.concat(parts).sort_index()
        m1 = m1[~m1.index.duplicated()]
    m1 = m1[(m1.index >= pd.Timestamp(a, tz="UTC")) & (m1.index < pd.Timestamp(b, tz="UTC"))]
    t = trades(m1)
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / "trades.csv.gz", index=False)
    res = {m: judge(t, m, split) for m in MODES if m != "base"}
    base_pips = float(t.pts_base.sum() / PIP["XAUUSD"]) if len(t) else 0.0
    head = ("| variant | verdict | trades changed | win | avg R | change vs no trail (95% range) | halves | net pips |\n"
            "|---|---|---|---|---|---|---|---|")
    md = [f"# Gold overnight breakout: trailing stop ({period}, {a} → {b})", "",
          "Registered Nov 3 2026 before running (research/gold_trail/PREREGISTRATION_2026-11-03.md). Same entries as the "
          "gold_breakout book (00–07 GMT+3 range, 1% stop, flat 20:00 GMT+3, real OANDA bid/ask); only the stop after "
          "entry changes. Paired per trade against the rule without a trail.", "",
          f"No trail (the book today): {len(t)} trades, {float((t.R_base > 0).mean()) if len(t) else 0:.0%} win, "
          f"avg {t.R_base.mean() if len(t) else float('nan'):+.3f}R, net {base_pips:,.0f} pips.", "", head,
          line("trail 0.5R after +0.5R (primary)", res[PRIMARY], True), line("break-even at +0.5R", res["be_half"], False),
          line("trail 1R after +1R", res["trail_1r"], False), line("chandelier 3 × ATR15", res["chandelier"], False)]
    if period == "seen":
        md += ["", ("**trail_half passes → one judgement on 2016–2020: ./fx.sh goldtrail vault**" if res[PRIMARY]["pass"]
                    else "**trail_half does not pass → the vault is not touched; the book keeps its rule.**")]
        if len(t):
            md += ["", "### Trades that reached +0.5R and then closed below 0 without a trail (the Nov 3 pattern)", ""]
            gave_back = t[(t.R_base <= 0) & (t.R_trail_half > t.R_base)]
            big = t[t.R_base >= 2]
            md += [f"- {len(gave_back)} trades were turned from a loss into a smaller loss or a gain by the 0.5R trail "
                   f"(avg {gave_back.R_base.mean() if len(gave_back) else float('nan'):+.2f}R → "
                   f"{gave_back.R_trail_half.mean() if len(gave_back) else float('nan'):+.2f}R).",
                   f"- {len(big)} trades made ≥ 2R without a trail; with it they made "
                   f"{big.R_trail_half.mean() if len(big) else float('nan'):+.2f}R on average instead of "
                   f"{big.R_base.mean() if len(big) else float('nan'):+.2f}R."]
    else:
        md += ["", f"**Verdict on 2016–2020: {'CONFIRMED → the paper book gets the 0.5R trail' if res[PRIMARY]['pass'] else 'NOT CONFIRMED → the book keeps its rule'}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gold breakout trailing stop (registered Nov 3 2026)")
    ap.add_argument("--period", choices=tuple(PERIODS), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
