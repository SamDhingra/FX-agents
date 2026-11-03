"""SuperTrend + EMA + RSI (registered Nov 2 2026, research/supertrend/PREREGISTRATION_2026-11-02.md, before any run).

Textbook rules, no tuning: SuperTrend(10, 3) up + close above EMA 200 + RSI(14) in 50–70 → long on the first candle
where all three hold (mirror for shorts), 15-minute candles, entries on candles closing 03:00–15:30 NY, stop at the
SuperTrend line (skip < 0.3 or > 4 ATR), stop trails the line, exit on a SuperTrend flip or 15:50. Real per-minute
bid/ask spread. NDQ + gold + US30 pooled. Must beat a random-timing control (same stops/exits, random entry times in
the trend's direction).

    python -m fxagents.supertrend_test [--period seen|vault]     (./fx.sh supertrend [seen|vault])
    → data/year_test/supertrend_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .indicators import resample_ohlc
from .playbook_test import boot_lo_hi

NY = "America/New_York"
SYMS = ("NDQ", "XAUUSD", "US30")
PERIODS = {"seen": ("2021-01-01", "2026-10-01", "2023-11-17"), "vault": ("2016-01-01", "2021-01-01", "2018-07-01")}
HIST = {"seen": Path("data/history_x/seen_2021_2026"), "vault": Path("data/history_x/old_2016_2020")}
OUT = {p: Path(f"data/year_test/supertrend_{p}") for p in PERIODS}
ST_N, ST_M, EMA_N, RSI_N = 10, 3.0, 200, 14
ENTRY_FROM, ENTRY_TO, FLAT = 3 * 60, 15 * 60 + 30, 15 * 60 + 50
MIN_RISK_ATR, MAX_RISK_ATR = 0.3, 4.0
PRIMARY = "st_ema_rsi"
SEED = 20261102


# ── indicators ──────────────────────────────────────────────────────────────
def rma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    a = 1.0 / n
    for i in range(n, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def atr(h, l, c, n=ST_N) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return rma(tr, n)


def supertrend(h, l, c, n=ST_N, m=ST_M) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(line, dir, atr): dir +1 up / −1 down / 0 not ready; line = the active band (below price when up)."""
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl = ub.copy(), lb.copy()
    d = np.zeros(len(c), np.int8)
    line = np.full(len(c), np.nan)
    for i in range(1, len(c)):
        if np.isnan(a[i]):
            continue
        if not np.isnan(fu[i - 1]) and not (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]):
            fu[i] = fu[i - 1]
        if not np.isnan(fl[i - 1]) and not (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]):
            fl[i] = fl[i - 1]
        prev = d[i - 1] if d[i - 1] != 0 else (1 if c[i] >= hl2[i] else -1)
        if prev == -1 and c[i] > fu[i]:
            d[i] = 1
        elif prev == 1 and c[i] < fl[i]:
            d[i] = -1
        else:
            d[i] = prev
        line[i] = fl[i] if d[i] == 1 else fu[i]
    return line, d, a


def ema(c: np.ndarray, n=EMA_N) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return out
    out[n - 1] = c[:n].mean()
    k = 2 / (n + 1)
    for i in range(n, len(c)):
        out[i] = c[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(c: np.ndarray, n=RSI_N) -> np.ndarray:
    d = np.diff(c, prepend=np.nan)
    up, dn = rma(np.where(d > 0, d, 0.0), n), rma(np.where(d < 0, -d, 0.0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dn == 0, 100.0, 100 - 100 / (1 + up / dn))


# ── one instrument, one timeframe ───────────────────────────────────────────
class Market:
    def __init__(self, m1: pd.DataFrame, tf: str) -> None:
        m1 = m1.sort_index()
        self.m1 = m1
        self.O, self.H, self.L, self.C = (m1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.hs = (m1["spread"].to_numpy(float) / 2) if "spread" in m1 else np.zeros(len(m1))
        idx = m1.index
        self.mod = np.asarray(idx.hour * 60 + idx.minute + 1)      # minute-of-day at each 1-minute CLOSE
        self.day = np.asarray(idx.normalize().asi8)
        b = resample_ohlc(m1.assign(volume=m1.get("volume", 1.0)), tf)
        step = pd.Timedelta(tf)
        self.bars = b
        h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
        self.c = c
        self.line, self.dir, self.atr = supertrend(h, l, c)
        self.ema, self.rsi = ema(c), rsi(c)
        close_ts = b.index + step
        self.close_ts = close_ts
        self.bmod = np.asarray(close_ts.hour * 60 + close_ts.minute)
        last = close_ts - pd.Timedelta("1min")
        j = idx.searchsorted(last)
        ok = (j < len(idx)) & (idx[np.minimum(j, len(idx) - 1)] == last)
        self.jend = np.where(ok, j, -1)                             # 1-minute index of each bar's last minute
        self.bar_of_min = np.full(len(idx), -1)                     # minute → the bar it closes (or −1)
        good = self.jend >= 0
        self.bar_of_min[self.jend[good]] = np.nonzero(good)[0]

    def entry_bars(self, kind: str) -> list[tuple[int, int]]:
        """[(bar, side)] for a rule, entry hours applied."""
        d, c, e, r = self.dir, self.c, self.ema, self.rsi
        if kind == "st_only":
            long_ = (d == 1) & (np.r_[0, d[:-1]] == -1)
            short = (d == -1) & (np.r_[0, d[:-1]] == 1)
        else:
            cl = (d == 1) & (c > e) & (r >= 50) & (r <= 70)
            cs = (d == -1) & (c < e) & (r >= 30) & (r < 50)
            long_ = cl & ~np.r_[False, cl[:-1]]
            short = cs & ~np.r_[False, cs[:-1]]
        hours = (self.bmod >= ENTRY_FROM) & (self.bmod < ENTRY_TO) & (self.jend >= 0)
        out = [(k, 1) for k in np.nonzero(long_ & hours)[0]] + [(k, -1) for k in np.nonzero(short & hours)[0]]
        return sorted(out)

    def trade(self, k: int, side: int, rsi_exit: bool = False, cost_mult: float = 1.0) -> dict | None:
        j0 = int(self.jend[k])
        if j0 < 0 or not np.isfinite(self.line[k]) or not np.isfinite(self.atr[k]) or self.dir[k] != side:
            return None
        hs0 = self.hs[j0] * cost_mult
        entry = self.C[j0] + side * hs0
        stop = float(self.line[k])
        risk = (entry - stop) * side
        a = float(self.atr[k])
        if risk <= 0 or risk < MIN_RISK_ATR * a or risk > MAX_RISK_ATR * a:
            return None
        why, px, jx = "flat", None, None
        n = len(self.C)
        for j in range(j0 + 1, n):
            hs = self.hs[j] * cost_mult
            if self.day[j] != self.day[j0] or self.mod[j] > FLAT:          # data gap past the session: out at the open
                jx, px, why = j, self.O[j] - side * hs, "flat"
                break
            far_o = self.O[j] - side * hs                                   # what we'd get at the minute's open
            worst = (self.L[j] - hs) if side > 0 else (self.H[j] + hs)      # bid low for longs, ask high for shorts
            if (worst - stop) * side <= 0:
                jx, px, why = j, (min(far_o, stop) if side > 0 else max(far_o, stop)), "stop"
                break
            kb = self.bar_of_min[j]
            if kb >= 0:
                if self.dir[kb] != side:
                    jx, px, why = j, self.C[j] - side * hs, "flip"
                    break
                if rsi_exit and ((self.rsi[kb] < 50) if side > 0 else (self.rsi[kb] >= 50)):
                    jx, px, why = j, self.C[j] - side * hs, "rsi"
                    break
                ln = self.line[kb]
                if np.isfinite(ln) and (ln - stop) * side > 0:
                    stop = float(ln)
            if self.mod[j] >= FLAT:
                jx, px, why = j, self.C[j] - side * hs, "flat"
                break
        if jx is None:
            return None
        r = (px - entry) * side / risk
        cost_r = (self.hs[j0] + self.hs[jx]) / risk                         # one more full spread, in R
        return {"ts": self.close_ts[k], "exit_ts": self.m1.index[jx], "side": side, "r": float(r), "cost_r": float(cost_r),
                "risk_atr": float(risk / a), "exit": why, "hour": int(self.bmod[k] // 60), "jx": jx}

    def run(self, kind: str, rsi_exit: bool = False) -> pd.DataFrame:
        rows, busy = [], -1
        for k, side in self.entry_bars(kind):
            if int(self.jend[k]) <= busy:
                continue
            t = self.trade(k, side, rsi_exit)
            if t is None:
                continue
            busy = t.pop("jx")
            rows.append(t)
        return pd.DataFrame(rows)

    def control(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        """Random entry times: 15-minute closes in the entry hours, in the SuperTrend's direction, same stops/exits."""
        hours = np.nonzero((self.bmod >= ENTRY_FROM) & (self.bmod < ENTRY_TO) & (self.jend >= 0) & (self.dir != 0)
                           & np.isfinite(self.line))[0]
        rows, tries = [], 0
        while len(rows) < n and tries < 20 * max(n, 1) and len(hours):
            tries += 1
            k = int(rng.choice(hours))
            t = self.trade(k, int(self.dir[k]))
            if t is not None:
                t.pop("jx")
                rows.append(t)
        return pd.DataFrame(rows)


# ── judging ─────────────────────────────────────────────────────────────────
def judge(t: pd.DataFrame, split: str, ctrl: pd.DataFrame | None = None) -> dict:
    if not len(t):
        return {"n": 0, "pass": False}
    t = t.assign(day=pd.to_datetime(t["ts"]).dt.tz_convert(NY).dt.date)
    lo, hi = boot_lo_hi(t)
    first = pd.to_datetime(t["ts"]) < pd.Timestamp(split, tz=NY)
    st = {"n": int(len(t)), "avg": float(t.r.mean()), "lo": lo, "hi": hi, "avg2x": float((t.r - t.cost_r).mean()),
          "h1": float(t.r[first].mean()) if first.any() else float("nan"),
          "h2": float(t.r[~first].mean()) if (~first).any() else float("nan"),
          "win": float((t.r > 0).mean()), "cost": float(t.cost_r.median())}
    st["ctrl"] = float(ctrl.r.mean()) if ctrl is not None and len(ctrl) else float("nan")
    st["pass"] = bool(st["n"] >= 100 and st["avg"] > 0 and lo > 0 and st["avg2x"] > 0 and st["h1"] > 0 and st["h2"] > 0
                      and (ctrl is None or (np.isfinite(st["ctrl"]) and st["avg"] > st["ctrl"])))
    return st


def row(name: str, s: dict, gate: bool = True) -> str:
    if not s.get("n"):
        return f"| {name} | — | 0 |  |  |  |  |  |  |  |"
    v = ("**PASS**" if s["pass"] else "no") if gate else "info"
    return (f"| {name} | {v} | {s['n']} | {s['win']:.0%} | {s['avg']:+.3f} | {s['lo']:+.3f} to {s['hi']:+.3f} | "
            f"{s['avg2x']:+.3f} | {s['h1']:+.3f} / {s['h2']:+.3f} | {s.get('ctrl', float('nan')):+.3f} | {s['cost']:.0%} |")


def load(hist: Path, sym: str, a: str, b: str) -> pd.DataFrame | None:
    f = hist / f"{sym}.pkl"
    if not f.exists():
        return None
    m1, _ = pd.read_pickle(f)
    m1 = m1.tz_convert(NY) if m1.index.tz is not None else m1.tz_localize(NY)
    return m1[(m1.index >= pd.Timestamp(a, tz=NY)) & (m1.index < pd.Timestamp(b, tz=NY))]


def run(period: str, hist: Path | None = None, out: Path | None = None, syms=SYMS, data: dict | None = None) -> dict:
    hist, out = hist or HIST[period], out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; the {period} judgement is made once")
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        if not (seen.get(PRIMARY) or {}).get("pass"):
            raise SystemExit("registered: the vault is judged only if st_ema_rsi passed on the seen period")
    a, b, split = PERIODS[period]
    rng = np.random.default_rng(SEED)
    res = {k: [] for k in (PRIMARY, "control", "st_only", "rsi_exit", "tf_5min", "tf_1h")}
    missing = []
    for sym in syms:
        m1 = data[sym] if data is not None else load(hist, sym, a, b)
        if m1 is None or not len(m1):
            missing.append(sym)
            continue
        mk = Market(m1, "15min")
        p = mk.run(PRIMARY)
        res[PRIMARY].append(p.assign(sym=sym))
        res["control"].append(mk.control(len(p), rng).assign(sym=sym))
        if period == "seen":
            res["st_only"].append(mk.run("st_only").assign(sym=sym))
            res["rsi_exit"].append(mk.run(PRIMARY, rsi_exit=True).assign(sym=sym))
            res["tf_5min"].append(Market(m1, "5min").run(PRIMARY).assign(sym=sym))
            res["tf_1h"].append(Market(m1, "1h").run(PRIMARY).assign(sym=sym))
        print(f"  {sym}: {len(p)} trades", flush=True)
    cat = {k: (pd.concat(v, ignore_index=True) if v and any(len(x) for x in v) else pd.DataFrame()) for k, v in res.items()}
    prim = judge(cat[PRIMARY], split, cat["control"])
    ctrl = judge(cat["control"], split)
    out.mkdir(parents=True, exist_ok=True)
    for k, t in cat.items():
        if len(t):
            t.to_csv(out / f"trades_{k}.csv.gz", index=False)
    head = "| rule | verdict | trades | win | avg R | 95% range | 2× costs | halves | random-timing control | spread / risk |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    md = [f"# SuperTrend + EMA + RSI — {period} ({a} → {b})", "",
          "Registered Nov 2 2026 before running (research/supertrend/PREREGISTRATION_2026-11-02.md). SuperTrend(10, 3) + "
          "EMA 200 + RSI(14) 50–70 / 30–50, 15-minute candles, entries 03:00–15:30 NY at the signal candle's close (real "
          "bid/ask), stop and trail at the SuperTrend line, exit on a flip or 15:50. NDQ + gold + US30 pooled.", "",
          f"Gates: ≥ 100 trades, avg R > 0, 95% range above 0, avg R > 0 at 2× costs, both halves (split {split}) > 0, "
          "and better than the random-timing control.", "", head, sep, row(PRIMARY, prim),
          row("random-timing control", ctrl, gate=False)]
    if period == "seen":
        md += ["", ("**st_ema_rsi passes → one judgement on 2016–2020: ./fx.sh supertrend vault**" if prim["pass"] else
                    "**st_ema_rsi does not pass → the vault is not touched; the idea is closed.**"),
               "", "## Shown, not judged", "", head, sep]
        for k, name in (("st_only", "SuperTrend flips alone"), ("rsi_exit", "same entries, RSI exit"),
                        ("tf_5min", "5-minute candles"), ("tf_1h", "1-hour candles")):
            md.append(row(name, judge(cat[k], split), gate=False))
        t = cat[PRIMARY]
        if len(t):
            md += ["", "### st_ema_rsi by instrument", "", head, sep]
            for sym, g in t.groupby("sym"):
                md.append(row(sym, judge(g.drop(columns="sym"), split), gate=False))
            md += ["", "### by entry hour (NY)", "", "| hour | trades | avg R |", "|---|---|---|"]
            md += [f"| {h:02d} | {len(g)} | {g.r.mean():+.3f} |" for h, g in t.groupby("hour")]
            md += ["", "Exit reasons: " + ", ".join(f"{k} {v}" for k, v in t.exit.value_counts().items())]
    else:
        md += ["", f"**Verdict on 2016–2020: {'CONFIRMED → a paper book first; any trading change is for the review' if prim['pass'] else 'NOT CONFIRMED → closed'}.**"]
    if missing:
        md += ["", "No history for: " + ", ".join(missing)]
    (out / "report.md").write_text("\n".join(md) + "\n")
    summ = {PRIMARY: prim, "control": ctrl, "period": period}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ


def main(argv=None):
    ap = argparse.ArgumentParser(description="SuperTrend + EMA + RSI (registered Nov 2 2026)")
    ap.add_argument("--period", choices=tuple(PERIODS), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
