"""Gold breakout: A) no-progress exit, B) add when a pullback resumes (registered Nov 3 2026,
research/gold_more/PREREGISTRATION_2026-11-03.md, before any run). Same entries as the gold_breakout book.

    python -m fxagents.gold_more [--period seen|vault]     (./fx.sh goldmore [seen|vault])
    → data/year_test/gold_more_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import gold_trail as GT
from .simple_rules import load

OUT = {p: Path(f"data/year_test/gold_more_{p}") for p in GT.PERIODS}
A_MODES = {"noprog3h": (3, "prog"), "noprog2h": (2, "prog"), "noprog4h": (4, "prog"), "under3h": (3, "under")}
B_MODES = {"add_resume": (1.0, "ext"), "add_early": (0.5, "ext"), "add_stop0": (1.0, "stop0")}
PRIMARY_A, PRIMARY_B = "noprog3h", "add_resume"
HOUR_NS = 3_600_000_000_000


def bars15(m1: pd.DataFrame) -> dict:
    mid = pd.DataFrame({"o": (m1.bid_o + m1.ask_o) / 2, "h": m1.m_h, "l": m1.m_l, "c": (m1.bid_c + m1.ask_c) / 2})
    b = mid.resample("15min", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return {"close_ns": (b.index + pd.Timedelta("15min")).as_unit("ns").asi8, **{k: b[k].to_numpy(float) for k in "ohlc"}}


def _span(a, j0, t1):
    t = a["ns"]
    t1 = min(t1, len(t))
    gaps = np.nonzero(np.diff(t[j0:t1 + 1]) > 60 * 60_000_000_000)[0]
    return t1, (j0 + int(gaps[0]) + 1 if len(gaps) else t1), bool(len(gaps))


def _final(a, t1, stop_end, gap, side):
    t = a["ns"]
    if gap:
        j = stop_end - 1
        return a["bid_c"][j] if side > 0 else a["ask_c"][j]
    if t1 >= len(t):
        return a["bid_c"][-1] if side > 0 else a["ask_c"][-1]
    return a["bid_o"][t1] if side > 0 else a["ask_o"][t1]


def noprog(a, j0, t1, side, entry, stop, risk, hours, kind) -> float:
    """R of the day's trade under the no-progress exit."""
    t1, stop_end, gap = _span(a, j0, t1)
    t = a["ns"]
    check = t[j0] + hours * HOUR_NS
    best, checked = entry, False
    for j in range(j0, stop_end):
        op = a["bid_o"][j] if side > 0 else a["ask_o"][j]
        if not checked and t[j] >= check:
            checked = True
            g = (best - entry) * side
            if (kind == "prog" and g < 0.5 * risk) or (kind == "under" and (op - entry) * side < 0):
                return side * (op - entry) / risk
        lo = a["bid_l"][j] if side > 0 else a["ask_h"][j]
        if (lo - stop) * side <= 0:
            px = stop if j == j0 else (min(stop, op) if side > 0 else max(stop, op))
            return side * (px - entry) / risk
        hi = a["bid_h"][j] if side > 0 else a["ask_l"][j]
        if (hi - best) * side > 0:
            best = hi
    return side * (_final(a, t1, stop_end, gap, side) - entry) / risk


def add_on(a, b, j0, t1, side, entry, stop0, risk, arm_r, stop_kind) -> dict | None:
    """The add's result in the day's R (0.5R risked), or None when no add happened."""
    t1, stop_end, gap = _span(a, j0, t1)
    t = a["ns"]
    k = int(np.searchsorted(b["close_ns"], t[j0], side="right"))   # next 15m bar to complete
    best, ext, armed = entry, None, False
    add = None                                                     # {'e','s','dist'}
    for j in range(j0, stop_end):
        # 15m bars completed by the open of minute j
        while k < len(b["close_ns"]) and b["close_ns"][k] <= t[j]:
            if add is None and armed and k > 0:
                o, c = b["o"][k], b["c"][k]
                sig = (c > o and c > b["h"][k - 1]) if side > 0 else (c < o and c < b["l"][k - 1])
                if sig:
                    e = a["ask_o"][j] if side > 0 else a["bid_o"][j]
                    s = ext if stop_kind == "ext" else stop0
                    dist = max(side * (e - s), 0.25 * risk) if stop_kind == "ext" else side * (e - s)
                    if dist > 0:
                        add = {"e": e, "s": e - side * dist, "dist": dist, "from": j + 1, "j": j}
            k += 1
        lo = a["bid_l"][j] if side > 0 else a["ask_h"][j]
        op = a["bid_o"][j] if side > 0 else a["ask_o"][j]
        if add is not None and j >= add["from"] and (lo - add["s"]) * side <= 0:
            px = min(add["s"], op) if side > 0 else max(add["s"], op)
            return {"R": 0.5 * side * (px - add["e"]) / add["dist"], "spread": a["ask_o"][add["j"]] - a["bid_o"][add["j"]],
                    "dist": add["dist"]}
        if (lo - stop0) * side <= 0:                               # original trade stopped
            if add is None:
                return None
            px = min(add["s"], op) if side > 0 else max(add["s"], op)
            return {"R": 0.5 * side * (px - add["e"]) / add["dist"], "spread": a["ask_o"][add["j"]] - a["bid_o"][add["j"]],
                    "dist": add["dist"]}
        hi = a["bid_h"][j] if side > 0 else a["ask_l"][j]
        if (hi - best) * side > 0:
            best, ext, armed = hi, None, False
        if add is None:
            ext = lo if ext is None or (lo - ext) * side < 0 else ext
            if (best - entry) * side >= arm_r * risk and (best - ext) * side >= 0.5 * risk:
                armed = True
    if add is None:
        return None
    px = _final(a, t1, stop_end, gap, side)
    return {"R": 0.5 * side * (px - add["e"]) / add["dist"], "spread": a["ask_o"][add["j"]] - a["bid_o"][add["j"]],
            "dist": add["dist"]}


def reach_half_within(a, j0, t1, side, entry, risk, hours) -> bool:
    t = a["ns"]
    t1 = min(t1, len(t))
    end = int(np.searchsorted(t, t[j0] + hours * HOUR_NS))
    end = min(max(end, j0 + 1), t1)
    hi = (a["bid_h"] if side > 0 else a["ask_l"])[j0:end]
    return bool(len(hi) and (side * (hi - entry)).max() >= 0.5 * risk)


def judge_add(t: pd.DataFrame, mode: str, split: str) -> dict:
    s = t[t[f"has_{mode}"]].reset_index(drop=True)
    n = len(s)
    if n < 2:
        return {"mode": mode, "n": n, "pass": False, "gates": {"adds ≥ 100": False}, "d": float("nan"), "lo": float("nan"),
                "hi": float("nan"), "halves": (float("nan"), float("nan")), "d_2x": float("nan"), "win": float("nan")}
    d = s[f"add_{mode}"].to_numpy(float)
    lo, hi = GT.paired(s, d)
    first = (pd.to_datetime(s.entry_time) < pd.Timestamp(split, tz=GT.NY)).to_numpy()
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    d2 = d - 0.5 * s[f"sp_{mode}"].to_numpy(float) / s[f"dist_{mode}"].to_numpy(float)
    gates = {"adds ≥ 100": n >= 100, "95% range above 0": lo > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2× costs > 0": float(d2.mean()) > 0}
    return {"mode": mode, "n": n, "d": float(d.mean()), "lo": lo, "hi": hi, "halves": halves, "d_2x": float(d2.mean()),
            "win": float((d > 0).mean()), "gates": gates, "pass": all(gates.values())}


def run(period: str, out: Path | None = None, m1: pd.DataFrame | None = None) -> dict:
    out = out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    which = list(A_MODES) + list(B_MODES)
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        which = [m for m in (PRIMARY_A, PRIMARY_B) if (seen.get(m) or {}).get("pass")]
        if not which:
            raise SystemExit("registered: the vault is judged only for a primary that passed on seen")
    sets, a0, b0, split = GT.PERIODS[period]
    if m1 is None:
        parts = [load(Path("data/export") / s / "XAUUSD_M1.csv.gz") for s in sets
                 if (Path("data/export") / s / "XAUUSD_M1.csv.gz").exists()]
        if not parts:
            raise SystemExit(f"no XAUUSD bid/ask export in {sets}")
        m1 = pd.concat(parts).sort_index()
        m1 = m1[~m1.index.duplicated()]
    m1 = m1[(m1.index >= pd.Timestamp(a0, tz="UTC")) & (m1.index < pd.Timestamp(b0, tz="UTC"))]
    a, b = GT.arrays(m1), bars15(m1)
    rows = []
    for j, side, entry, stop, risk, spread, t1, rh, rl in GT.entries(a):
        _, px, _ = GT.walk(a, j, t1, side, entry, stop, risk, "base")
        r = {"entry_time": a["idx"][j], "side": side, "entry": entry, "risk": risk, "spread": spread,
             "R_base": side * (px - entry) / risk, "pts_base": side * (px - entry)}
        for h in (2, 3, 4):
            r[f"half_{h}h"] = reach_half_within(a, j, t1, side, entry, risk, h)
        for m in A_MODES:
            if m in which:
                hrs, kind = A_MODES[m]
                r[f"R_{m}"] = noprog(a, j, t1, side, entry, stop, risk, hrs, kind)
                r[f"pts_{m}"] = r[f"R_{m}"] * risk
        for m in B_MODES:
            if m in which:
                arm, sk = B_MODES[m]
                x = add_on(a, b, j, t1, side, entry, stop, risk, arm, sk)
                r[f"has_{m}"] = x is not None
                r[f"add_{m}"] = x["R"] if x else 0.0
                r[f"sp_{m}"] = x["spread"] if x else 0.0
                r[f"dist_{m}"] = x["dist"] if x else 1.0
        rows.append(r)
    t = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / "trades.csv.gz", index=False)
    res = {m: GT.judge(t, m, split) for m in A_MODES if m in which}
    res.update({m: judge_add(t, m, split) for m in B_MODES if m in which})

    def verdict(j, gate):
        return ("**PASS**" if j["pass"] else "**no** (" + ", ".join(k for k, ok in j["gates"].items() if not ok) + ")") if gate else "info"
    md = [f"# Gold overnight breakout: no-progress exit and add-on-resume ({period}, {a0} → {b0})", "",
          "Registered Nov 3 2026 before running (research/gold_more/PREREGISTRATION_2026-11-03.md). Same entries as the "
          "gold_breakout book; each primary judged on its own against the book as it trades today.", "",
          f"The book today: {len(t)} days, avg {t.R_base.mean():+.3f}R, {float((t.R_base > 0).mean()):.0%} win.", "",
          "## A. Cutting trades that go nowhere", "",
          "| rule | verdict | days changed | win | avg R | change vs today (95% range) | halves |", "|---|---|---|---|---|---|---|"]
    names = {"noprog3h": "3h, never +0.5R → out (primary)", "noprog2h": "2h, never +0.5R → out",
             "noprog4h": "4h, never +0.5R → out", "under3h": "3h, below entry → out"}
    for m in A_MODES:
        if m in res:
            j = res[m]
            md.append(f"| {names[m]} | {verdict(j, m == PRIMARY_A)} | {j['changed']} of {j['n']} | {j['win']:.0%} | "
                      f"{j['avg']:+.3f} | {j['d']:+.3f} ({j['lo']:+.3f} to {j['hi']:+.3f}) | {j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} |")
    md += ["", "## B. Adding when a pullback turns back into the trend", "",
           "| rule | verdict | adds | add wins | add avg (day R) | 95% range | halves | 2× costs |", "|---|---|---|---|---|---|---|---|"]
    bn = {"add_resume": "armed at +1R, stop at pullback extreme (primary)", "add_early": "armed at +0.5R",
          "add_stop0": "stop at the day's original stop"}
    for m in B_MODES:
        if m in res:
            j = res[m]
            md.append(f"| {bn[m]} | {verdict(j, m == PRIMARY_B)} | {j['n']} | {j['win']:.0%} | {j['d']:+.3f} | "
                      f"{j['lo']:+.3f} to {j['hi']:+.3f} | {j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['d_2x']:+.3f} |")
    if period == "seen":
        big = t[t.R_base >= 2]
        md += ["", "### The 25-ish big days (≥ 2R) and these rules", "",
               f"- {len(big)} days. Reached +0.5R within 2h: {int(big.half_2h.sum())}, within 3h: {int(big.half_3h.sum())}, "
               f"within 4h: {int(big.half_4h.sum())} (the rest would be cut by that no-progress rule)."]
        if "has_add_resume" in t:
            bb = big[big.has_add_resume]
            md.append(f"- The add fired on {len(bb)} of them, adding {bb.add_add_resume.mean() if len(bb) else float('nan'):+.2f}R "
                      "on average.")
        losers = t[t.R_base < 0]
        md.append(f"- Losing days today: {len(losers)} (avg {losers.R_base.mean():+.2f}R); with the 3h rule they average "
                  f"{losers.R_noprog3h.mean():+.2f}R.")
        for m, lbl in ((PRIMARY_A, "no-progress exit"), (PRIMARY_B, "add-on-resume")):
            md.append("")
            md.append(f"**{lbl}: " + ("passes → one judgement on 2016–2020: ./fx.sh goldmore vault**" if res[m]["pass"]
                                       else "does not pass → the vault is not touched for it.**"))
    else:
        for m in which:
            md += ["", f"**Verdict on 2016–2020 for {m}: {'CONFIRMED → shadow book beside gold_breakout' if res[m]['pass'] else 'NOT CONFIRMED → the book keeps its rule'}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gold breakout no-progress exit and add-on-resume (registered Nov 3 2026)")
    ap.add_argument("--period", choices=tuple(GT.PERIODS), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
