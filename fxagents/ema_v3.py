"""EMA21 family, round 3 (registered Nov 7 2026: research/ema_v3/PREREGISTRATION_2026-11-07.md).

Configurations, long only, day version, live-book stop (entry − 3 × ATR):
  ref      the original EMA21 + RSI55 cross (reference, not judged)
  A_norsi  the EMA21 cross without the RSI condition
  B_h1     the original cross, and the last completed 1h candle closed above its own EMA21
Each trade gets a causal random-timing control: entries at random long-state candles of the same NY hour and period
half, with the same exits.

    python -m fxagents.ema_v3 dev|holdout|vault
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .simple_rules import NY, PIP, bars, load

CONFIGS = ("ref", "A_norsi", "B_h1")
JUDGED = ("A_norsi", "B_h1")
SYMS = ("XAUUSD", "NDQ", "US30")
STOP_ATR = 3.0
K_RANDOM = 20
STAGES = {  # stage: (export, split, previous stage)
    "dev": ("dev_m1", "2025-10-01", None),
    "holdout": ("holdout_m1", "2022-11-16", "dev"),
    "vault": ("old_m1", "2018-07-01", "holdout"),
}
OUT = Path("data/year_test")


def out_dir(stage: str) -> Path:
    return OUT / f"ema_v3_{stage}"


class Market:
    """One instrument's minutes and candles, with a single-trade simulator shared by rule and random entries."""

    def __init__(self, m1: pd.DataFrame):
        self.m1 = m1
        self.b = bars(m1, "15min")
        self.t1 = m1.index
        self.ns = self.t1.as_unit("ns").asi8
        self.ask_o, self.bid_o, self.bid_c, self.bid_l = (m1[c].to_numpy() for c in ("ask_o", "bid_o", "bid_c", "bid_l"))
        self.sp = (m1.ask_o - m1.bid_o).to_numpy()
        self.gap = np.r_[np.diff(self.ns), 0] > 60 * 60 * 1_000_000_000
        self.gap_ix = np.flatnonzero(self.gap)
        b = self.b
        self.loc = b.index.tz_convert(NY)
        self.mins = (self.loc.hour * 60 + self.loc.minute).to_numpy()
        self.c, self.e, self.rsi, self.atr = (b[x].to_numpy() for x in ("c", "ema21", "rsi", "atr"))
        self.first = np.searchsorted(self.ns, b.index.as_unit("ns").asi8)
        h1 = bars(m1, "1h")
        pos = np.searchsorted(h1.index.as_unit("ns").asi8, b.index.as_unit("ns").asi8, side="right") - 1
        up = (h1.c > h1.ema21).to_numpy()
        self.h1_up = np.where(pos >= 0, up[np.clip(pos, 0, None)], False)
        self.flat = (self.loc.normalize() + pd.Timedelta(hours=15, minutes=50)).tz_convert("UTC").as_unit("ns").asi8
        self.cache: dict = {}

    def ok(self, i: int) -> bool:
        """Entry-able candle: indicators ready, inside 02:00–15:30 NY, a tradable minute within 5 min of the close."""
        if i < 1 or not (np.isfinite(self.e[i]) and np.isfinite(self.e[i - 1]) and np.isfinite(self.rsi[i])
                         and np.isfinite(self.atr[i]) and self.atr[i] > 0):
            return False
        if not (120 <= self.mins[i] <= 930) or self.loc[i].dayofweek >= 5:
            return False
        j0 = self.first[i]
        return j0 < len(self.t1) and self.ns[j0] - self.b.index[i].value <= 5 * 60 * 1_000_000_000

    def signal(self, i: int, cfg: str) -> bool:
        c, e = self.c, self.e
        cross = c[i - 1] <= e[i - 1] and c[i] > e[i]
        if cfg == "A_norsi":
            return cross
        if not (cross and self.rsi[i] > 55):
            return False
        return cfg == "ref" or bool(self.h1_up[i])

    def trade(self, i: int, stop: bool = True):
        """One long from candle i. Returns (record, index of the candle where it ended) or None at the data end."""
        key = (i, stop)
        if key in self.cache:
            return self.cache[key]
        b, t1, n = self.b, self.t1, len(self.b)
        j0 = self.first[i]
        entry, atr = self.ask_o[j0], self.atr[i]
        st = entry - STOP_ATR * atr
        g = np.searchsorted(self.gap_ix, j0)
        nxt_gap = self.gap_ix[g] if g < len(self.gap_ix) else None
        k, jx, why = i + 1, None, None
        while k < n:
            jk = min(self.first[k], len(t1) - 1)
            if nxt_gap is not None and jk > nxt_gap:
                jx, why = nxt_gap, "closure"
                break
            if b.index[k].value > self.flat[i]:
                jx, why = int(np.searchsorted(self.ns, self.flat[i])), "flat_1550"
                break
            if self.c[k] < self.e[k]:
                jx, why = jk, "ema_exit"
                break
            k += 1
        if jx is None or jx >= len(t1):
            self.cache[key] = None
            return None
        px = self.bid_c[jx] if why == "closure" else self.bid_o[jx]
        end = jx + 1 if why == "closure" else jx
        if stop and end > j0:
            hit = np.flatnonzero(self.bid_l[j0:end] <= st)
            if len(hit):
                jx, why = j0 + int(hit[0]), "stop"
                px = min(st, self.bid_o[jx]) if jx > j0 else st
        cost = (self.sp[j0] + self.sp[jx]) / 2
        R = (px - entry) / atr
        rec = {"entry_time": t1[j0], "exit_time": t1[jx], "signal_i": i, "hour": int(self.loc[i].hour),
               "entry": entry, "exit": px, "atr": atr, "points": px - entry, "R": R, "R_2x": R - cost / atr,
               "R_stop_units": R / STOP_ATR, "cost_R": cost / atr, "exit_reason": why,
               "hold_min": (t1[jx] - t1[j0]).total_seconds() / 60}
        self.cache[key] = (rec, k)
        return self.cache[key]

    def run(self, cfg: str, stop: bool = True) -> pd.DataFrame:
        out, i, n = [], 1, len(self.b)
        while i < n:
            if self.ok(i) and self.signal(i, cfg):
                r = self.trade(i, stop)
                if r is None:
                    break
                out.append(r[0])
                i = max(r[1], i + 1)
            else:
                i += 1
        return pd.DataFrame(out)

    def random_control(self, t: pd.DataFrame, split: pd.Timestamp, seed: int = 7) -> np.ndarray:
        """Per trade: mean R of K random long-state candles at the same NY hour in the same period half."""
        if not len(t):
            return np.array([])
        cand = np.array([i for i in range(1, len(self.b)) if self.ok(i) and self.c[i] > self.e[i]])
        half = np.where(self.b.index[cand] < split, 1, 2)
        hour = self.loc[cand].hour.to_numpy()
        pools = {}
        rng = np.random.default_rng(seed)
        ctrl = np.full(len(t), np.nan)
        for n_, (sig, h) in enumerate(zip(t.signal_i, t.hour)):
            hf = 1 if self.b.index[sig] < split else 2
            pool = pools.setdefault((h, hf), cand[(hour == h) & (half == hf)])
            if not len(pool):
                continue
            rs = [r[0]["R"] for r in (self.trade(int(j)) for j in rng.choice(pool, K_RANDOM)) if r is not None]
            if rs:
                ctrl[n_] = float(np.mean(rs))
        return ctrl


def weekdays(m1: pd.DataFrame) -> pd.DatetimeIndex:
    d = pd.DatetimeIndex(sorted(set(m1.index.tz_convert(NY).tz_localize(None).normalize())))
    return d[d.dayofweek < 5]


def daily(t: pd.DataFrame, col: str, days: pd.DatetimeIndex) -> pd.DataFrame:
    if not len(t):
        return pd.DataFrame({"sum": 0.0, "count": 0}, index=days)
    d = t.entry_time.dt.tz_convert(NY).dt.tz_localize(None).dt.normalize()
    return t.groupby(d)[col].agg(["sum", "count"]).reindex(days, fill_value=0)


def block_range(g: pd.DataFrame, q=(0.025, 0.975), B: int = 4000, blk: int = 5, seed: int = 7) -> tuple:
    """Range of sum/count over 5-day blocks of weekdays (zero-trade days included)."""
    s, k = g["sum"].to_numpy(float), g["count"].to_numpy(float)
    nd = len(s)
    if nd < 10 or k.sum() == 0:
        return (float("nan"),) * len(q)
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, nd, (B, -(-nd // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :nd] % nd
    den = k[ix].sum(1)
    m = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    return tuple(float(x) for x in np.nanquantile(m, q))


def judge(t: pd.DataFrame, ref: pd.DataFrame, days: pd.DatetimeIndex, split: pd.Timestamp) -> dict:
    if not len(t):
        return {"trades": 0, "pass": False, "gates": {}}
    dR = daily(t, "R", days)
    lo, hi = block_range(dR)
    a6 = 0.05 / len(JUDGED * len(SYMS)) / 2                                     # Bonferroni for the 6 configurations
    lo99, hi99 = block_range(dR, (a6, 1 - a6))
    td = t.dropna(subset=["d"])
    dlo, dhi = block_range(daily(td, "d", days))
    first = t.entry_time < split
    inc = float((dR["sum"] - daily(ref, "R", days)["sum"]).mean())
    st = {"trades": len(t), "per_day": len(t) / len(days), "win": float((t.R > 0).mean()), "avg_R": float(t.R.mean()),
          "lo": lo, "hi": hi, "lo99": lo99, "hi99": hi99, "avg_R_2x": float(t.R_2x.mean()),
          "h1": float(t.R[first].mean()) if first.any() else float("nan"),
          "h2": float(t.R[~first].mean()) if (~first).any() else float("nan"),
          "ctrl": float(td.ctrl.mean()) if len(td) else float("nan"), "d": float(td.d.mean()) if len(td) else float("nan"),
          "d_lo": dlo, "d_hi": dhi, "inc_daily": inc, "avg_stop_units": float(t.R_stop_units.mean()),
          "stop_share": float((t.exit_reason == "stop").mean()), "cost_R": float(t.cost_R.mean()),
          "net_pips": float(t.points.sum()), "exits": t.exit_reason.value_counts().to_dict()}
    g = {"≥100 trades": st["trades"] >= 100, "95% range > 0": lo > 0, "2× costs > 0": st["avg_R_2x"] > 0,
         "both halves > 0": st["h1"] > 0 and st["h2"] > 0, "beats random timing": dlo > 0,
         "adds to the daily result vs ref": inc > 0}
    st["gates"] = g
    st["pass"] = all(g.values())
    return st


def allowed(stage: str) -> list[tuple[str, str]] | None:
    """(symbol, config) pairs this stage may run; None = all."""
    prev = STAGES[stage][2]
    if prev is None:
        return None
    f = out_dir(prev) / "summary.json"
    if not f.exists():
        raise SystemExit(f"{stage} needs the {prev} result first ({f} missing)")
    s = json.loads(f.read_text())
    ok = [(r["symbol"], r["config"]) for r in s["rows"] if r["config"] in JUDGED and r.get("pass")]
    if stage == "vault" and ok:
        best = max(ok, key=lambda x: next(r["lo"] for r in s["rows"] if (r["symbol"], r["config"]) == x))
        ok = [best]
    if not ok:
        raise SystemExit(f"nothing passed {prev}: the registration stops here; {stage} is not run")
    return ok


def run_stage(stage: str, src: Path | None = None, out: Path | None = None, syms=SYMS) -> dict:
    export, split, _ = STAGES[stage]
    split = pd.Timestamp(split, tz="UTC")
    pairs = allowed(stage)
    src = src or Path("data/export") / export
    out = out or out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
    rows, missing = [], []
    for sym in syms:
        f = src / f"{sym}_M1.csv.gz"
        want = [c for c in JUDGED if pairs is None or (sym, c) in pairs]
        if not want:
            continue
        if not f.exists():
            missing.append(sym)
            continue
        mk = Market(load(f))
        days = weekdays(mk.m1)
        ref = mk.run("ref")
        ref_nostop = mk.run("ref", stop=False)
        for cfg in ("ref",) + tuple(want):
            t = ref if cfg == "ref" else mk.run(cfg)
            if len(t):
                t["ctrl"] = mk.random_control(t, split)
                t["d"] = t.R - t.ctrl
                t["points"] = t.points / PIP.get(sym, 1.0)
                t.assign(symbol=sym, config=cfg).to_csv(out / f"trades_{sym}_{cfg}.csv.gz", index=False)
            st = judge(t, ref, days, split)
            if cfg == "ref":
                st["pass"] = None
                st["nostop_avg_R"] = float(ref_nostop.R.mean()) if len(ref_nostop) else float("nan")
                st["nostop_trades"] = len(ref_nostop)
            rows.append({"symbol": sym, "config": cfg, **st})
            print(f"  {sym:7s} {cfg:8s} {st['trades']:5d} trades  avg {st.get('avg_R', np.nan):+.3f}R "
                  f"[{st.get('lo', np.nan):+.3f}, {st.get('hi', np.nan):+.3f}]  vs random {st.get('d', np.nan):+.3f}  "
                  f"{'PASS' if st['pass'] else '' if st['pass'] is None else 'fail'}", flush=True)
        del mk
    summ = {"stage": stage, "export": export, "split": str(split.date()), "rows": rows, "missing": missing,
            "passed": [(r["symbol"], r["config"]) for r in rows if r.get("pass")]}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    (out / "report.md").write_text(report(summ))
    return summ


def f3(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.3f}"


def report(s: dict) -> str:
    md = [f"# EMA21 round 3: {s['stage']} ({s['export']}, halves split {s['split']})", "",
          "Registered Nov 7 2026 (research/ema_v3/PREREGISTRATION_2026-11-07.md). Long only, entries 02:00–15:30 NY, "
          "flat 15:50, exit on the first 15m close below EMA21, resting stop at entry − 3 × ATR (as the live book). "
          "R = ATR(14, 15m) at entry (a stop-out ≈ −3R; the live journal's R = this ÷ 3). Real OANDA bid/ask.", "",
          "`ref` = the original EMA21 + RSI55 (reference). `A_norsi` = the cross without RSI. `B_h1` = the original "
          "cross with the last completed 1h candle above its EMA21. **vs random** = average R minus the same-hour, "
          "same-half random entries with the same exits.", ""]
    hd = ("| instrument | config | trades | win | avg R | 95% range | 99.2% range | 2× costs | halves | random | vs random "
          "(95%) | daily vs ref | stop hits | result |")
    md += [hd, "|" + "---|" * 14]
    for r in s["rows"]:
        if not r.get("trades"):
            md.append(f"| {r['symbol']} | {r['config']} | 0 | | | | | | | | | | | — |")
            continue
        res = "reference" if r["pass"] is None else "**PASS**" if r["pass"] else \
            "fail: " + ", ".join(k for k, v in r["gates"].items() if not v)
        md.append(f"| {r['symbol']} | {r['config']} | {r['trades']:,} | {r['win']:.0%} | **{f3(r['avg_R'])}** | "
                  f"{f3(r['lo'])} to {f3(r['hi'])} | {f3(r['lo99'])} to {f3(r['hi99'])} | {f3(r['avg_R_2x'])} | "
                  f"{f3(r['h1'])} / {f3(r['h2'])} | {f3(r['ctrl'])} | {f3(r['d'])} ({f3(r['d_lo'])} to {f3(r['d_hi'])}) | "
                  f"{'—' if r['config'] == 'ref' else f3(r['inc_daily'])} | {r['stop_share']:.1%} | {res} |")
    md += ["", "## Information", "", "| instrument | config | trades/day | net pips | avg R in stop units (live journal) | spread R | exits |",
           "|---|---|---|---|---|---|---|"]
    for r in s["rows"]:
        if r.get("trades"):
            md.append(f"| {r['symbol']} | {r['config']} | {r['per_day']:.2f} | {r['net_pips']:+,.0f} | "
                      f"{f3(r['avg_stop_units'])} | {r['cost_R']:.3f} | "
                      + ", ".join(f"{k} {v}" for k, v in r["exits"].items()) + " |")
    refs = [r for r in s["rows"] if r["config"] == "ref" and r.get("trades")]
    if refs:
        md += ["", "Code check, `ref` without the stop (should match the earlier v2 day-long results on dev_m1): " +
               ", ".join(f"{r['symbol']} {r['nostop_trades']} trades {f3(r['nostop_avg_R'])}R" for r in refs)]
    if s["missing"]:
        md += ["", f"Missing exports: {', '.join(s['missing'])}."]
    md += ["", f"**Passed: {', '.join(f'{a} {b}' for a, b in s['passed']) or 'none'}.**"]
    nxt = {"dev": "Configurations that passed go to `./fx.sh emav3 holdout` (2021 → Sep 2024).",
           "holdout": "If any passed, ONE nominee (highest holdout lower bound) goes to `./fx.sh emav3 vault`.",
           "vault": "A pass earns a frozen paper book; a fail closes the EMA21 family."}[s["stage"]]
    md += ["", nxt if s["passed"] else "Nothing passed: per the registration, EMA21 research stops here."]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(STAGES))
    a = ap.parse_args(argv)
    s = run_stage(a.stage)
    print(f"passed: {s['passed'] or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
