"""News fade (registered Oct 28 2026, research/news_fade/PREREGISTRATION_2026-10-28.md, before the test data was read).

At T+30 after a FOMC / CPI / NFP / PPI release, trade AGAINST the move from T-1 to T+30, exit at T+150 or 15:50 NY (first),
emergency stop 4 x ATR15, real bid/ask fills; XAUUSD, NDQ, US30. Judged once on 2023-11-17 -> 2026-10-01 against a
size-matched no-release control (same rule at 08:30 / 14:00 on no-release weekdays whose first-30-minute move is at least
the release trades' median). A pass is judged once on 2016-2020.

    python -m fxagents.news_fade [--period test|vault]   (./fx.sh newsfade [test|vault]) -> data/year_test/news_fade_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .news_study import NY, SYMS, TYPES, Prices, control_times, release_times

PERIODS = {"test": (pd.Timestamp("2023-11-17", tz=NY), pd.Timestamp("2026-10-01", tz=NY)),
           "vault": (pd.Timestamp("2016-01-01", tz=NY), pd.Timestamp("2021-01-01", tz=NY))}
HIST = {"test": Path("data/history_x/seen_2021_2026"), "vault": Path("data/history_x/old_2016_2020")}
K, HOLD, STOP_ATR, FLAT = 30, 120, 4.0, (15, 50)
DRAWS, SEED = 10_000, 5


def clock_group(typ: str) -> str:
    return "14:00" if typ in ("FOMC", "ctl_1400") else "08:30"


def trade(P: Prices, T: pd.Timestamp, cost_mult: float = 1.0) -> dict | None:
    """One fade from T+30. None when a price or the ATR is missing, or the first move is 0."""
    u = P.atr15(T - pd.Timedelta(minutes=60))
    if not np.isfinite(u):
        return None
    t_in = T + pd.Timedelta(minutes=K)
    p0, p1 = P.mid(T - pd.Timedelta(minutes=1)), P.mid(t_in)
    if not (np.isfinite(p0) and np.isfinite(p1)) or p1 == p0:
        return None
    d = -1 if p1 > p0 else 1                                       # against the first move
    i_in = P.pos(t_in)
    hs = lambda i: P.sp[i] / 2 * cost_mult                         # noqa: E731
    entry = P.c[i_in] + d * hs(i_in)
    stop = entry - d * STOP_ATR * u
    flat = T.normalize() + pd.Timedelta(hours=FLAT[0], minutes=FLAT[1])
    t_out = min(T + pd.Timedelta(minutes=K + HOLD), flat)
    if t_out <= t_in:
        return None
    end = int(np.searchsorted(P.ns, (t_out - pd.Timedelta(minutes=1)).as_unit("ns").value, side="right"))   # bars starting before t_out
    how, fill = "time", None
    for i in range(i_in + 1, end):
        far = (P.l[i] - hs(i)) if d > 0 else (P.h[i] + hs(i))
        if (far - stop) * d <= 0:
            op = (P.o[i] - hs(i)) if d > 0 else (P.o[i] + hs(i))
            fill, how = (op if (op - stop) * d < 0 else stop), "stop"
            break
    if fill is None:
        i_out = P.pos(t_out)
        if i_out < 0 or i_out <= i_in:
            return None
        fill = P.c[i_out] - d * hs(i_out)
    net = d * (fill - entry) / u
    return {"side": d, "first_move": (p1 - p0) / u, "net": net, "r": net / STOP_ATR, "exit": how, "atr15": u,
            "hold_min": (t_out - t_in).total_seconds() / 60}


def collect(m1s: dict[str, pd.DataFrame], ev: pd.DataFrame, cost_mult: float = 1.0) -> pd.DataFrame:
    rows = []
    for sym, m1 in m1s.items():
        P = Prices(m1)
        for r in ev.itertuples(index=False):
            x = trade(P, r.T, cost_mult)
            if x is not None:
                rows.append({"sym": sym, "type": r.type, "T": r.T, "day": r.day, "group": clock_group(r.type), **x})
    return pd.DataFrame(rows)


def day_means(v: np.ndarray, days: np.ndarray, rng, draws: int) -> np.ndarray:
    u, inv = np.unique(days, return_inverse=True)
    S, N = np.zeros(len(u)), np.zeros(len(u))
    np.add.at(S, inv, v)
    np.add.at(N, inv, 1)
    pick = rng.integers(0, len(u), size=(draws, len(u)))
    return S[pick].sum(1) / N[pick].sum(1)


def boot(v, days, draws=DRAWS, seed=SEED) -> tuple[float, float, float]:
    v, days = np.asarray(v, float), np.asarray(days)
    if len(v) < 5:
        return (float(v.mean()) if len(v) else np.nan, np.nan, np.nan)
    m = day_means(v, days, np.random.default_rng(seed), draws)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(v.mean()), float(lo), float(hi)


def boot_diff(a: pd.DataFrame, c: pd.DataFrame, draws=DRAWS, seed=SEED + 1) -> tuple[float, float, float]:
    if len(a) < 5 or len(c) < 5:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    ma = day_means(a.net.to_numpy(float), a.day.to_numpy(), rng, draws)
    mc = day_means(c.net.to_numpy(float), c.day.to_numpy(), rng, draws)
    lo, hi = np.percentile(ma - mc, [2.5, 97.5])
    return float(a.net.mean() - c.net.mean()), float(lo), float(hi)


def matched(rel: pd.DataFrame, ctl: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Control trades whose |first move| is at least the median of the same instrument's release trades in that clock group."""
    keep, thr = [], {}
    for (sym, grp), g in rel.groupby(["sym", "group"]):
        th = float(np.median(np.abs(g.first_move)))
        thr[f"{sym} {grp}"] = th
        c = ctl[(ctl.sym == sym) & (ctl.group == grp)]
        keep.append(c[np.abs(c.first_move) >= th])
    return (pd.concat(keep, ignore_index=True) if keep else ctl.iloc[:0]), thr


def fmt(m) -> str:
    return "—" if not np.isfinite(m[0]) else (f"{m[0]:+.2f}" + (f" ({m[1]:+.2f}..{m[2]:+.2f})" if np.isfinite(m[1]) else ""))


def run(period: str, hist: Path, out: Path, syms=SYMS) -> dict:
    a0, b0 = PERIODS[period]
    if period == "vault":
        p = Path("data/year_test/news_fade_test/summary.json")
        if not (p.exists() and json.loads(p.read_text()).get("pass")):
            raise SystemExit("registered: 2016-2020 is judged only if the rule passed every gate on the test period")
    ev = release_times(a0, b0)
    ctl_t = control_times(ev, a0, b0)
    m1s = {}
    for s in syms:
        f = hist / f"{s}.pkl"
        if not f.exists():
            print(f"  no history for {s}", flush=True)
            continue
        m1 = pd.read_pickle(f)[0]
        m1s[s] = m1[(m1.index >= a0 - pd.Timedelta(days=5)) & (m1.index < b0)]       # the period only
        print(f"  {s}: {len(m1s[s]):,} minutes", flush=True)
    rel, ctl = collect(m1s, ev), collect(m1s, ctl_t)
    rel2 = collect(m1s, ev, cost_mult=2.0)
    mc, thr = matched(rel, ctl)
    mid = a0 + (b0 - a0) / 2
    main = boot(rel.net, rel.day)
    halves = (float(rel[rel["T"] < mid].net.mean()), float(rel[rel["T"] >= mid].net.mean()))
    two_x = float(rel2.net.mean())
    vs = boot_diff(rel, mc)
    gates = {"≥ 100 trades": len(rel) >= 100, "95% range above 0": bool(np.isfinite(main[1]) and main[1] > 0),
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2× costs > 0": two_x > 0,
             "beats the size-matched control": bool(np.isfinite(vs[1]) and vs[1] > 0)}
    ok = all(gates.values())
    first4 = all(v for k, v in gates.items() if k != "beats the size-matched control")
    if ok:
        verdict = ("**PASS — a news edge.** One judgement on 2016–2020: `./fx.sh newsfade vault`." if period == "test" else
                   "**CONFIRMED on 2016–2020** → to the Nov 5 review (the blackout is unchanged until then).")
    elif first4 and period == "test":
        verdict = ("**Not a news edge:** it pays, but no more than fading an equally big early move on a no-release day. "
                   "\"Fade any big early move\" goes to its own registered test; nothing from this run is traded.")
    else:
        verdict = "**Does not pass → closed.**" + (" 2016–2020 is not read." if period == "test" else "")
    L = [f"# News fade ({period}: {a0.date()} → {b0.date()})", "",
         "Registered Oct 28 2026 before this data was read (research/news_fade/PREREGISTRATION_2026-10-28.md). At T+30 after a "
         "FOMC / CPI / NFP / PPI release, trade against the move from T−1 to T+30; exit at T+150 or 15:50 NY (first), emergency "
         "stop 4 × ATR15, real bid/ask fills. Results in ATR15 net of the spread (R = 4 × ATR15).", "",
         "| | trades | mean net ATR15 (95% range) | in R | halves | 2× costs | size-matched control (trades) | release − control (95% range) |",
         "|---|---|---|---|---|---|---|---|",
         f"| all releases | {len(rel)} | {fmt(main)} | {main[0] / STOP_ATR:+.3f} | {halves[0]:+.2f} / {halves[1]:+.2f} | {two_x:+.2f} | "
         f"{mc.net.mean():+.2f} ({len(mc)}) | {fmt(vs)} |", "",
         "| gate | result |", "|---|---|"] + [f"| {k} | {'yes' if v else '**no**'} |" for k, v in gates.items()]
    L += ["", verdict, "", "## Information only (never a pass)", "",
          f"Unmatched control (every no-release day at 08:30 / 14:00): {ctl.net.mean():+.2f} ATR15 on {len(ctl)} trades. "
          f"Size-match thresholds (|first move| ÷ ATR15): " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(thr.items())) + ".",
          f"Stop hits: {int((rel.exit == 'stop').sum())} of {len(rel)}.", "",
          "| type | " + " | ".join(SYMS) + " | all |", "|---|" + "---|" * (len(SYMS) + 1)]
    for t in TYPES:
        g = rel[rel.type == t]
        L.append(f"| {t} | " + " | ".join(fmt(boot(g[g.sym == s].net, g[g.sym == s].day)) + f" ({int((g.sym == s).sum())})" for s in SYMS)
                 + f" | {fmt(boot(g.net, g.day))} ({len(g)}) |")
    L += ["", "Per cell n is small (≈ 35 a type per instrument): these rows can't rescue or sink the pooled verdict."]
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(L) + "\n")
    rel.to_csv(out / "trades.csv.gz", index=False)
    mc.to_csv(out / "control_matched.csv.gz", index=False)
    res = {"pass": ok, "first_four": first4, "gates": gates, "n": len(rel), "mean": main, "halves": halves, "two_x": two_x,
           "control": float(mc.net.mean()) if len(mc) else None, "vs_control": vs}
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="News fade (registered Oct 28 2026)")
    ap.add_argument("--period", choices=("test", "vault"), default="test")
    a = ap.parse_args(argv)
    out = Path(f"data/year_test/news_fade_{a.period}")
    run(a.period, HIST[a.period], out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
