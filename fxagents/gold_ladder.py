"""Gold breakout "ladder" management (registered Nov 3 2026, research/gold_ladder/PREREGISTRATION_2026-11-03.md, before
any run): half-size ratchet leg P (+½ step stop per step), half-size runner R, one half-size re-entry E after a false
reversal, setup-broken rule (15m close back inside the range). Same entries as the gold_breakout book.

    python -m fxagents.gold_ladder [--period seen|vault]     (./fx.sh goldladder [seen|vault])
    → data/year_test/gold_ladder_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import gold_trail as GT
from .breakout_test import to_broker
from .simple_rules import PIP, load

OUT = {p: Path(f"data/year_test/gold_ladder_{p}") for p in GT.PERIODS}
MODES = ("ladder", "ladder_pips", "ladder_noreentry", "ladder_nobreak")
PRIMARY = "ladder"
STEP_R = 0.25
STEP_PIPS = 100


def _exit_px(a, j, side):
    return a["bid_o"][j] if side > 0 else a["ask_o"][j]


def manage(a: dict, end15: np.ndarray, j0: int, t1: int, side: int, entry: float, stop0: float, risk: float,
           rh: float, rl: float, mode: str) -> dict:
    """Walk one day. Returns {'R': day R (legs weighted ½, in the day's 1R), 'legs': n legs opened, 'reentry': bool}."""
    step = STEP_PIPS * PIP["XAUUSD"] if mode == "ladder_pips" else STEP_R * risk
    allow_re = mode != "ladder_noreentry"
    use_break = mode != "ladder_nobreak"
    legs = [{"k": "P", "e": entry, "s": stop0, "best": entry, "ratchet": True, "open": True, "from": j0},
            {"k": "R", "e": entry, "s": stop0, "best": entry, "ratchet": False, "open": True, "from": j0}]
    t = a["ns"]
    t1 = min(t1, len(t))
    gaps = np.nonzero(np.diff(t[j0:t1 + 1]) > 60 * 60_000_000_000)[0]
    stop_end = j0 + int(gaps[0]) + 1 if len(gaps) else t1
    broken = False
    re_level, re_from = None, 0
    re_done = False
    pending_out = False
    res = []

    def close(L, px):
        L["open"] = False
        res.append(side * (px - L["e"]) / risk * 0.5)

    for j in range(j0, stop_end):
        if pending_out:                                  # setup broke at the last 15m close: losing legs out at this open
            for L in legs:
                if L["open"] and L.get("cut"):
                    close(L, _exit_px(a, j, side))
            pending_out = False
        lo = a["bid_l"][j] if side > 0 else a["ask_h"][j]
        op = _exit_px(a, j, side)
        for L in legs:
            if not L["open"] or j < L["from"]:
                continue
            if (lo - L["s"]) * side <= 0:
                px = L["s"] if j == L["from"] else (min(L["s"], op) if side > 0 else max(L["s"], op))
                close(L, px)
                if L["k"] == "P" and side * (px - L["e"]) > 0 and allow_re and not re_done and not broken:
                    re_level, re_from = px, j + 1
        # re-entry: price back to P's exit level (false reversal)
        if re_level is not None and not re_done and not broken and j >= re_from:
            hit = a["ask_h"][j] >= re_level if side > 0 else a["bid_l"][j] <= re_level
            if hit:
                ao = a["ask_o"][j] if side > 0 else a["bid_o"][j]
                e = max(re_level, ao) if side > 0 else min(re_level, ao)
                if (e - stop0) * side > 0:
                    legs.append({"k": "E", "e": e, "s": stop0, "best": e, "ratchet": True, "open": True, "from": j + 1})
                re_done = True
        hi = a["bid_h"][j] if side > 0 else a["ask_l"][j]
        for L in legs:
            if not L["open"] or j < L["from"]:
                continue
            if (hi - L["best"]) * side > 0:
                L["best"] = hi
            if L["ratchet"]:
                g = (L["best"] - L["e"]) * side
                if g >= step:
                    new = L["e"] + side * 0.5 * step * np.floor(g / step)
                    if (new - L["s"]) * side > 0:
                        L["s"] = new
        if use_break and not broken and end15[j]:
            c = (a["bid_c"][j] + a["ask_c"][j]) / 2
            if (side > 0 and c < rh) or (side < 0 and c > rl):
                broken = True
                now = a["bid_c"][j] if side > 0 else a["ask_c"][j]
                for L in legs:
                    if not L["open"]:
                        continue
                    if (now - L["e"]) * side > 0:
                        if (L["e"] - L["s"]) * side > 0:
                            L["s"] = L["e"]
                    else:
                        L["cut"] = True
                        pending_out = True
    for L in legs:
        if L["open"]:
            if len(gaps):
                j = stop_end - 1
                px = a["bid_c"][j] if side > 0 else a["ask_c"][j]
            elif t1 >= len(t):
                px = a["bid_c"][-1] if side > 0 else a["ask_c"][-1]
            else:
                px = _exit_px(a, t1, side)
            close(L, px)
    return {"R": float(sum(res)), "legs": len(legs), "reentry": any(L["k"] == "E" for L in legs)}


def diagnose(a: dict, j0: int, t1: int, side: int, entry: float, risk: float) -> dict:
    """For a no-management trade: deepest pullback (R) from the running best after +0.5R and before the final peak."""
    t1 = min(t1, len(a["ns"]))
    hi = (a["bid_h"] if side > 0 else a["ask_l"])[j0:t1]
    lo = (a["bid_l"] if side > 0 else a["ask_h"])[j0:t1]
    g_hi, g_lo = side * (hi - entry) / risk, side * (lo - entry) / risk
    run = np.maximum.accumulate(g_hi)
    peak_i = int(np.argmax(g_hi))
    on = np.nonzero(run[:peak_i + 1] >= 0.5)[0]
    pull = float((run[on] - g_lo[on]).max()) if len(on) else float("nan")
    return {"peak": float(g_hi.max()), "pull_after_half": pull}


def run(period: str, out: Path | None = None, m1: pd.DataFrame | None = None) -> dict:
    out = out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; judged once")
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not (seen.get(PRIMARY) or {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if ladder passed on seen")
    sets, a0, b0, split = GT.PERIODS[period]
    if m1 is None:
        parts = [load(Path("data/export") / s / "XAUUSD_M1.csv.gz") for s in sets
                 if (Path("data/export") / s / "XAUUSD_M1.csv.gz").exists()]
        if not parts:
            raise SystemExit(f"no XAUUSD bid/ask export in {sets}")
        m1 = pd.concat(parts).sort_index()
        m1 = m1[~m1.index.duplicated()]
    m1 = m1[(m1.index >= pd.Timestamp(a0, tz="UTC")) & (m1.index < pd.Timestamp(b0, tz="UTC"))]
    a = GT.arrays(m1)
    _, bmin = to_broker(a["idx"])
    end15 = (bmin % 15) == 14
    rows = []
    for j, side, entry, stop, risk, spread, t1, rh, rl in GT.entries(a):
        jx, px, why = GT.walk(a, j, t1, side, entry, stop, risk, "base")
        jt, pt, wt = GT.walk(a, j, t1, side, entry, stop, risk, "trail_half")
        r = {"entry_time": a["idx"][j], "side": side, "entry": entry, "risk": risk, "spread": spread,
             "R_base": side * (px - entry) / risk, "R_trail_half": side * (pt - entry) / risk, "why_trail_half": wt,
             **diagnose(a, j, t1, side, entry, risk)}
        for mode in MODES:
            m = manage(a, end15, j, t1, side, entry, stop, risk, rh, rl, mode)
            r[f"R_{mode}"], r[f"re_{mode}"] = m["R"], m["reentry"]
        rows.append(r)
    t = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / "trades.csv.gz", index=False)
    res = {}
    for mode in MODES:
        j = GT.judge(t, mode, split)
        d2 = (t[f"R_{mode}"] - t.R_base - t[f"re_{mode}"].astype(float) * 0.5 * t.spread / t.risk).to_numpy(float)
        j["d_2x"] = float(d2.mean())
        j["reentries"] = int(t[f"re_{mode}"].sum())
        j["gates"]["2× costs > 0"] = j["d_2x"] > 0
        j["pass"] = all(j["gates"].values())
        res[mode] = j
    pip = PIP["XAUUSD"]
    head = ("| version | verdict | days changed | re-entries | win | avg R | change vs no management (95% range) | halves | "
            "2× costs |\n|---|---|---|---|---|---|---|---|---|")

    def ln(name, j, gate):
        v = ("**PASS**" if j["pass"] else "**no** (" + ", ".join(k for k, ok in j["gates"].items() if not ok) + ")") if gate else "info"
        return (f"| {name} | {v} | {j['changed']} of {j['n']} | {j['reentries']} | {j['win']:.0%} | {j['avg']:+.3f} | "
                f"{j['d']:+.3f} ({j['lo']:+.3f} to {j['hi']:+.3f}) | {j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['d_2x']:+.3f} |")
    md = [f"# Gold overnight breakout: ladder management ({period}, {a0} → {b0})", "",
          "Registered Nov 3 2026 before running (research/gold_ladder/PREREGISTRATION_2026-11-03.md). Half leg ratcheted "
          "(+½ step per step, step = 0.25R ≈ 100 pips at today's price), half leg runner, one half-size re-entry after a "
          "false reversal, setup broken = 15m close back inside the range. Paired per day against no management.", "",
          f"No management (the book today): {len(t)} days, avg {t.R_base.mean():+.3f}R.", "", head,
          ln("ladder (primary)", res["ladder"], True), ln("literal 100 / 50 pips", res["ladder_pips"], False),
          ln("no re-entry", res["ladder_noreentry"], False), ln("no setup-broken rule", res["ladder_nobreak"], False)]
    if period == "seen":
        md += ["", ("**ladder passes → one judgement on 2016–2020: ./fx.sh goldladder vault**" if res[PRIMARY]["pass"]
                    else "**ladder does not pass → the vault is not touched; the book keeps its rule.**")]
        big = t[t.R_base >= 2]
        if len(big):
            fine = lambda x: f"{x:.2f}"
            pb = big.pull_after_half.dropna()
            md += ["", f"### What the {len(big)} days of ≥ 2R did (no management)", "",
                   f"- Deepest pullback from the running best after first reaching +0.5R, before the final peak: median "
                   f"{fine(pb.median())}R, {int((pb > 0.5).sum())} of {len(pb)} pulled back more than 0.5R "
                   f"(a 0.5R trail exits these), {int((pb > 0.25).sum())} more than 0.25R.",
                   f"- Peak gain: median {fine(big.peak.median())}R; result at the close: median {fine(big.R_base.median())}R.",
                   f"- 0.5R trail on these days: median {fine(big.R_trail_half.median())}R; ladder: median "
                   f"{fine(big.R_ladder.median())}R.", "",
                   "| day | side | close result R | peak R | pullback after +0.5R (R) | 0.5R trail R | ladder R |",
                   "|---|---|---|---|---|---|---|"]
            for _, r in big.sort_values("entry_time").iterrows():
                md.append(f"| {pd.Timestamp(r.entry_time).date()} | {'long' if r.side > 0 else 'short'} | {r.R_base:+.2f} | "
                          f"{r.peak:+.2f} | {r.pull_after_half:.2f} | {r.R_trail_half:+.2f} | {r.R_ladder:+.2f} |")
            md += ["", f"Net pips, no management: {t.R_base.mul(t.risk).sum() / pip:,.0f}."]
    else:
        md += ["", f"**Verdict on 2016–2020: {'CONFIRMED → shadow ladder book on gold_breakout' if res[PRIMARY]['pass'] else 'NOT CONFIRMED → the book keeps its rule'}.**"]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gold breakout ladder management (registered Nov 3 2026)")
    ap.add_argument("--period", choices=tuple(GT.PERIODS), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
