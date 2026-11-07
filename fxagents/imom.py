"""Intraday momentum into the close (registered Nov 7 2026: research/imom/PREREGISTRATION_2026-11-07.md).

At 15:30 NY trade the direction of the move from the previous 16:00 to 15:30, held to 16:00. No stop, no target.
US30 decides, NDQ supports, gold is information (COMEX close: 13:00 → 13:30).

    python -m fxagents.imom seen|vault
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .simple_rules import NY, PIP, load

TOL = pd.Timedelta("3min")
STAGES = {"seen": (("holdout_m1", "dev_m1"), "2023-11-17", ("US30", "NDQ", "XAUUSD")),
          "vault": (("old_m1_idx",), "2018-07-01", ("US30", "NDQ"))}
PRIMARY, SUPPORT = "US30", "NDQ"
OUT = Path("data/year_test")
N_PERM = 2000


def out_dir(stage: str) -> Path:
    return OUT / f"imom_{stage}"


def load_sets(sets, sym: str, root: Path = Path("data/export")) -> pd.DataFrame | None:
    parts = [load(root / s / f"{sym}_M1.csv.gz") for s in sets if (root / s / f"{sym}_M1.csv.gz").exists()]
    if not parts:
        return None
    m = pd.concat(parts).sort_index()
    return m[~m.index.duplicated()]


def _times(days: pd.DatetimeIndex, hhmm: str) -> pd.Series:
    h, mi = map(int, hhmm.split(":"))
    return pd.Series((days + pd.Timedelta(hours=h, minutes=mi)).tz_localize(NY, nonexistent="shift_forward", ambiguous="NaT").tz_convert("UTC").as_unit("ns"), index=days)


def _asof(m1: pd.DataFrame, t: pd.Series, cols, before: bool) -> pd.DataFrame:
    """before=True: the last minute starting strictly before t (within 3 min); False: the first at or after t."""
    left = pd.DataFrame({"t": t.array, "day": t.index}).sort_values("t")
    right = m1[cols].reset_index(names="mt").sort_values("mt")
    right["mt"] = right["mt"].dt.as_unit("ns")
    r = pd.merge_asof(left, right, left_on="t", right_on="mt", direction="backward" if before else "forward",
                      allow_exact_matches=not before, tolerance=TOL)
    return r.set_index("day")[cols]


def day_table(m1: pd.DataFrame, sig_t="15:30", ref_t="16:00", exit_t="16:00", ref_prev=True) -> pd.DataFrame:
    """One row per NY weekday: signal r, the trade's net bps both ways, always-long net bps, spread bps.
    ref_prev: the reference price is the PREVIOUS weekday's ref_t (rest-of-day); else today's ref_t (Zhang & Hua)."""
    days = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).tz_localize(None).normalize())))
    days = days[days.dayofweek < 5]
    sig = _asof(m1, _times(days, sig_t), ["m_c"], True)["m_c"]
    ref = _asof(m1, _times(days, ref_t), ["m_c"], True)["m_c"]
    if ref_prev:
        ref = ref.shift(1)                                         # previous weekday with a row (NaN if it had no price)
    ent = _asof(m1, _times(days, sig_t), ["ask_o", "bid_o"], False)
    ex = _asof(m1, _times(days, exit_t), ["bid_c", "ask_c"], True)
    d = pd.DataFrame({"r": sig / ref - 1, "ask_in": ent.ask_o, "bid_in": ent.bid_o, "bid_out": ex.bid_c,
                      "ask_out": ex.ask_c}).dropna()
    mid = (d.ask_in + d.bid_in) / 2
    d["long_bps"] = (d.bid_out - d.ask_in) / mid * 1e4             # buy at the ask, sell at the bid
    d["short_bps"] = (d.bid_in - d.ask_out) / mid * 1e4            # sell at the bid, buy back at the ask
    d["spread_bps"] = ((d.ask_in - d.bid_in) + (d.ask_out - d.bid_out)) / 2 / mid * 1e4
    d["side"] = np.sign(d.r).astype(int)
    d["mid_in"] = mid
    return d


def trades(d: pd.DataFrame) -> pd.DataFrame:
    t = d[d.side != 0].copy()
    t["net_bps"] = np.where(t.side > 0, t.long_bps, t.short_bps)
    t["net2x_bps"] = t.net_bps - t.spread_bps
    t["vs_long"] = t.net_bps - t.long_bps
    return t


def block_ci(x: np.ndarray, B: int = 4000, blk: int = 5, seed: int = 7) -> tuple[float, float]:
    n = len(x)
    if n < 20:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (B, -(-n // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :n] % n
    lo, hi = np.quantile(x[ix].mean(1), [0.025, 0.975])
    return float(lo), float(hi)


def perm_p(t: pd.DataFrame, n: int = N_PERM, seed: int = 7) -> float:
    """Share of random-sign versions (signs from other days) whose mean net bps ≥ the real one."""
    rng = np.random.default_rng(seed)
    s = t.side.to_numpy()
    L, S = t.long_bps.to_numpy(), t.short_bps.to_numpy()
    P = np.array([rng.permutation(s) for _ in range(n)])
    means = np.where(P > 0, L, S).mean(1)
    return float((means >= t.net_bps.mean()).mean())


def judge(t: pd.DataFrame, split: pd.Timestamp, pip: float) -> dict:
    if not len(t):
        return {"trades": 0, "pass": False, "gates": {}}
    x = t.net_bps.to_numpy()
    lo, hi = block_ci(x)
    vlo, vhi = block_ci(t.vs_long.to_numpy())
    first = t.index < split
    st = {"trades": len(t), "win": float((x > 0).mean()), "avg_bps": float(x.mean()), "lo": lo, "hi": hi,
          "avg2x_bps": float(t.net2x_bps.mean()), "h1": float(x[first].mean()) if first.any() else float("nan"),
          "h2": float(x[~first].mean()) if (~first).any() else float("nan"),
          "long_always_bps": float(t.long_bps.mean()), "vs_long": float(t.vs_long.mean()), "vs_long_lo": vlo,
          "vs_long_hi": vhi, "perm_p": perm_p(t), "spread_bps": float(t.spread_bps.mean()),
          "long_share": float((t.side > 0).mean()),
          "net_points": float((x / 1e4 * t.mid_in).sum() / pip), "avg_abs_move_bps": float(t.long_bps.abs().mean())}
    g = {"≥100 trades": st["trades"] >= 100, "95% range > 0": lo > 0, "2× costs > 0": st["avg2x_bps"] > 0,
         "both halves > 0": st["h1"] > 0 and st["h2"] > 0, "beats always-long": vlo > 0,
         "beats a random sign (p < 0.05)": st["perm_p"] < 0.05}
    st["gates"], st["pass"] = g, all(g.values())
    return st


def by_year(t: pd.DataFrame) -> dict:
    return {int(y): [int(len(g)), float(g.net_bps.mean()), float(g.long_bps.mean())]
            for y, g in t.groupby(t.index.year)}


def info_variants(m1: pd.DataFrame, sym: str, split: pd.Timestamp) -> dict:
    pip = PIP.get(sym, 1.0)
    out = {"exit 15:50": judge(trades(day_table(m1, exit_t="15:50")), split, pip),
           "signal 15:00→15:30 (Zhang & Hua)": judge(trades(day_table(m1, ref_t="15:00", ref_prev=False)), split, pip)}
    d = day_table(m1)
    med = d.r.abs().expanding(20).median().shift(1)
    out["|r| above its running median"] = judge(trades(d[d.r.abs() > med]), split, pip)
    return out


def allowed(stage: str) -> None:
    if stage == "vault":
        f = out_dir("seen") / "summary.json"
        if not f.exists():
            raise SystemExit("vault needs the seen result first")
        s = json.loads(f.read_text())
        if not s["rows"].get(PRIMARY, {}).get("pass"):
            raise SystemExit("US30 did not pass seen: the registration stops here; the vault is not opened")


def run_stage(stage: str, root: Path = Path("data/export"), out: Path | None = None) -> dict:
    allowed(stage)
    sets, split, syms = STAGES[stage]
    split = pd.Timestamp(split)
    out = out or out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
    rows, info, years, missing = {}, {}, {}, []
    for sym in syms:
        m1 = load_sets(sets, sym, root)
        if m1 is None:
            missing.append(sym)
            continue
        pip = PIP.get(sym, 1.0)
        if sym == "XAUUSD":                                        # information: the COMEX close
            t = trades(day_table(m1, sig_t="13:00", ref_t="13:30", exit_t="13:30"))
        else:
            t = trades(day_table(m1))
            info[sym] = info_variants(m1, sym, split)
        st = judge(t, split, pip)
        st["role"] = "decides" if sym == PRIMARY else "supporting" if sym == SUPPORT else "information"
        rows[sym] = st
        years[sym] = by_year(t)
        t.to_csv(out / f"trades_{sym}.csv.gz")
        print(f"  {sym:7s} {st['trades']:5d} trades  avg {st.get('avg_bps', np.nan):+.2f} bps "
              f"[{st.get('lo', np.nan):+.2f}, {st.get('hi', np.nan):+.2f}]  vs long {st.get('vs_long', np.nan):+.2f}  "
              f"p {st.get('perm_p', np.nan):.3f}  {'PASS' if st['pass'] else 'fail'}", flush=True)
        del m1
    summ = {"stage": stage, "sets": list(sets), "split": str(split.date()), "rows": rows, "info": info,
            "years": years, "missing": missing}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    (out / "report.md").write_text(report(summ))
    return summ


def f2(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.2f}"


def report(s: dict) -> str:
    md = [f"# Intraday momentum into the close: {s['stage']} ({' + '.join(s['sets'])}, halves split {s['split']})", "",
          "Registered Nov 7 2026 (research/imom/PREREGISTRATION_2026-11-07.md). At 15:30 NY: the direction of the move "
          "from the previous 16:00 to 15:30; held to 16:00, no stop. Real OANDA bid/ask. Results in basis points of "
          "the entry price after the spread (1 bp on NDQ ≈ 2.5 points, on US30 ≈ 4.7 points). Gold (information): "
          "13:00 → 13:30, signal from the previous 13:30.", "",
          "| instrument | role | trades | right | avg bps | 95% range | 2× costs | halves | always long | vs always long (95%) | random sign p | spread bps | avg move bps | net points | result |",
          "|" + "---|" * 15]
    for sym, r in s["rows"].items():
        if not r.get("trades"):
            continue
        res = "**PASS**" if r["pass"] else "fail: " + ", ".join(k for k, v in r["gates"].items() if not v)
        md.append(f"| {sym} | {r['role']} | {r['trades']:,} | {r['win']:.0%} | **{f2(r['avg_bps'])}** | {f2(r['lo'])} to "
                  f"{f2(r['hi'])} | {f2(r['avg2x_bps'])} | {f2(r['h1'])} / {f2(r['h2'])} | {f2(r['long_always_bps'])} | "
                  f"{f2(r['vs_long'])} ({f2(r['vs_long_lo'])} to {f2(r['vs_long_hi'])}) | {r['perm_p']:.3f} | "
                  f"{r['spread_bps']:.2f} | {r['avg_abs_move_bps']:.1f} | {r['net_points']:+,.0f} | {res} |")
    md += ["", "## Information (never a pass)", "", "| instrument | variant | trades | avg bps | 95% range | 2× costs | halves | vs always long | random sign p |",
           "|---|---|---|---|---|---|---|---|---|"]
    for sym, v in s["info"].items():
        for name, r in v.items():
            if r.get("trades"):
                md.append(f"| {sym} | {name} | {r['trades']:,} | {f2(r['avg_bps'])} | {f2(r['lo'])} to {f2(r['hi'])} | "
                          f"{f2(r['avg2x_bps'])} | {f2(r['h1'])} / {f2(r['h2'])} | {f2(r['vs_long'])} | {r['perm_p']:.3f} |")
    md += ["", "### By year: trades, avg bps, always-long bps", ""]
    for sym, ys in s["years"].items():
        md.append(f"- **{sym}**: " + "; ".join(f"{y} {n} / {a:+.2f} / {l:+.2f}" for y, (n, a, l) in sorted(ys.items())))
    if s["missing"]:
        md += ["", f"Missing exports: {', '.join(s['missing'])}."]
    p = s["rows"].get(PRIMARY, {}).get("pass")
    if s["stage"] == "seen":
        md += ["", "**US30 passed: the 2016–2020 vault is next (`./fx.sh imom vault`), once.**" if p else
               "**US30 did not pass: per the registration, closing-flow momentum on index CFDs is closed. C10 unchanged.**"]
    else:
        md += ["", "**US30 confirmed on 2016–2020: a paper book `imom_us30` with its own 16:00 exit follows.**" if p else
               "**US30 not confirmed on 2016–2020: closing-flow momentum on index CFDs is closed.**"]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(STAGES))
    s = run_stage(ap.parse_args(argv).stage)
    print("US30:", "PASS" if s["rows"].get(PRIMARY, {}).get("pass") else "fail")


if __name__ == "__main__":
    sys.exit(main())
