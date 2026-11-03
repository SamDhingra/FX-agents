"""Trend rules held overnight, NDQ-only SuperTrend, SuperTrend inside EMA21/RSI55 (registered Nov 2 2026,
research/trend_hold/PREREGISTRATION_2026-11-02.md, before any run).

    python -m fxagents.trend_hold_test --period seen     (./fx.sh trendhold seen)    → parts 1 + 3 on 2021–2026
    python -m fxagents.trend_hold_test --period vault    (./fx.sh trendhold vault)   → part 2 (NDQ, once) + every
                                                                                      part 1/3 primary that passed seen
Report: data/year_test/trend_hold_<period>/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import supertrend_test as S

NY = S.NY
PERIODS = {"seen": ("2021-01-01", "2026-10-01", "2023-11-17"), "vault": ("2016-01-01", "2021-01-01", "2018-07-01")}
OUT = {p: Path(f"data/year_test/trend_hold_{p}") for p in PERIODS}
FIN = 0.05                                            # financing, share of position value per year (registered)
HOLD = ("hold_st_1h", "hold_st_4h", "hold_er_1h", "hold_er_4h")
ER_SYMS = ("XAUUSD", "US30")
SEED = 20261103


def ema_n(c: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(c).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def wilder_rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = pd.Series(c).diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return (100 - 100 / (1 + up / dn)).to_numpy()


class Mk(S.Market):
    """S.Market with: optional session (None = hold), the EMA21/RSI55 rule, financing, and per-trade nights."""

    def __init__(self, m1: pd.DataFrame, tf: str, hours: tuple | None, flat: int | None, fin: float = 0.0) -> None:
        super().__init__(m1, tf)
        self.hours, self.flat_at, self.fin = hours, flat, fin
        b = self.bars
        h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
        self.ema21 = ema_n(c, 21)
        self.rsi_w = wilder_rsi(c, 14)
        pc = np.r_[np.nan, c[:-1]]
        tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
        self.atr14 = pd.Series(tr).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().to_numpy()
        idx = m1.index
        # 17:00 NY rollovers crossed so far (Friday's counts three), for financing
        first_after_break = np.r_[True, np.diff(idx.values) > np.timedelta64(30, 'm')] if len(idx) else np.array([], bool)
        dow = np.asarray(idx.dayofweek)
        mod = np.asarray(idx.hour * 60 + idx.minute)
        # a rollover happens between the last minute before 17:00 and the first minute at/after 18:00 (or Sunday 18:00)
        prev_mod = np.r_[0, mod[:-1]]
        prev_dow = np.r_[0, dow[:-1]]
        crossed = ((mod >= 17 * 60) & (prev_mod < 17 * 60) & (dow == prev_dow)) | (first_after_break & (mod >= 18 * 60))
        weight = np.where(crossed & ((prev_dow == 4) | (dow == 6)), 3, crossed.astype(int))
        self.nights_cum = np.cumsum(weight)

    def entry_bars(self, kind: str, st_filter: bool = False, only_hour: int | None = None, not_hour: int | None = None):
        c, d = self.c, self.dir
        if kind == "er":
            e, r = self.ema21, self.rsi_w
            pe, pc = np.r_[np.nan, e[:-1]], np.r_[np.nan, c[:-1]]
            long_ = (pc <= pe) & (c > e) & (r > 55)
            short = (pc >= pe) & (c < e) & (r < 45)
            if st_filter:
                long_, short = long_ & (d == 1), short & (d == -1)
        else:
            return [x for x in super().entry_bars(kind) if self._hours_ok(x[0])] if self.hours is not None else \
                self._st_any_hour(kind)
        ok = (self.jend >= 0) & np.isfinite(self.atr14)
        if self.hours is not None:
            ok &= (self.bmod >= self.hours[0]) & (self.bmod <= self.hours[1]) & (np.asarray(self.close_ts.dayofweek) < 5)
        hr = self.bmod // 60 % 24                             # the hour a candle closes in (06:00 … 06:59 → 6), as registered
        if only_hour is not None:
            ok &= hr == only_hour
        if not_hour is not None:
            ok &= hr != not_hour
        out = [(k, 1) for k in np.nonzero(long_ & ok)[0]] + [(k, -1) for k in np.nonzero(short & ok)[0]]
        return sorted(out)

    def _hours_ok(self, k: int) -> bool:
        return self.hours[0] <= self.bmod[k] <= self.hours[1]

    def _st_any_hour(self, kind: str):
        d, c, e, r = self.dir, self.c, self.ema, self.rsi
        cl = (d == 1) & (c > e) & (r >= 50) & (r <= 70)
        cs = (d == -1) & (c < e) & (r >= 30) & (r < 50)
        long_, short = cl & ~np.r_[False, cl[:-1]], cs & ~np.r_[False, cs[:-1]]
        ok = self.jend >= 0
        return sorted([(k, 1) for k in np.nonzero(long_ & ok)[0]] + [(k, -1) for k in np.nonzero(short & ok)[0]])

    def trade(self, k: int, side: int, rsi_exit: bool = False, cost_mult: float = 1.0, exit_mode: str = "st") -> dict | None:
        j0 = int(self.jend[k])
        if j0 < 0:
            return None
        hs0 = self.hs[j0] * cost_mult
        entry = self.C[j0] + side * hs0
        if exit_mode == "st":
            if not np.isfinite(self.line[k]) or not np.isfinite(self.atr[k]) or self.dir[k] != side:
                return None
            stop, a = float(self.line[k]), float(self.atr[k])
            risk = (entry - stop) * side
            if risk <= 0 or risk < S.MIN_RISK_ATR * a or risk > S.MAX_RISK_ATR * a:
                return None
        else:
            a = float(self.atr14[k])
            if not np.isfinite(a) or a <= 0:
                return None
            stop = entry - side * 3.0 * a
            risk = 3.0 * a
        why, px, jx = None, None, None
        for j in range(j0 + 1, len(self.C)):
            hs = self.hs[j] * cost_mult
            far_o = self.O[j] - side * hs
            if self.flat_at is not None and (self.day[j] != self.day[j0] or self.mod[j] > self.flat_at):
                jx, px, why = j, far_o, "flat"
                break
            worst = (self.L[j] - hs) if side > 0 else (self.H[j] + hs)
            if (worst - stop) * side <= 0:
                jx, px, why = j, (min(far_o, stop) if side > 0 else max(far_o, stop)), "stop"
                break
            kb = self.bar_of_min[j]
            if kb >= 0:
                if exit_mode == "st":
                    if self.dir[kb] != side:
                        jx, px, why = j, self.C[j] - side * hs, "flip"
                        break
                    ln = self.line[kb]
                    if np.isfinite(ln) and (ln - stop) * side > 0:
                        stop = float(ln)
                elif (self.c[kb] - self.ema21[kb]) * side < 0:
                    jx, px, why = j, self.C[j] - side * hs, "ema"
                    break
            if self.flat_at is not None and self.mod[j] >= self.flat_at:
                jx, px, why = j, self.C[j] - side * hs, "flat"
                break
        if jx is None:
            return None
        r0 = (px - entry) * side / risk
        nights = int(self.nights_cum[jx] - self.nights_cum[j0])
        fin_r_unit = nights / 365 * entry / risk                     # financing in R per 100% a year
        return {"ts": self.close_ts[k], "exit_ts": self.m1.index[jx], "side": side, "r": float(r0 - self.fin * fin_r_unit),
                "r_nofin": float(r0), "fin_unit": float(fin_r_unit), "nights": nights,
                "cost_r": float((self.hs[j0] + self.hs[jx]) / risk), "risk_atr": float(risk / a), "exit": why,
                "hour": int((self.bmod[k] // 60) % 24), "jx": jx}

    def run2(self, kind: str, exit_mode: str, **kw) -> pd.DataFrame:
        rows, busy = [], -1
        for k, side in self.entry_bars(kind, **kw):
            if int(self.jend[k]) <= busy:
                continue
            t = self.trade(k, side, exit_mode=exit_mode)
            if t is None:
                continue
            busy = t.pop("jx")
            rows.append(t)
        return pd.DataFrame(rows)

    def control2(self, n: int, rng, exit_mode: str) -> pd.DataFrame:
        ok = self.jend >= 0
        if self.hours is not None:
            ok &= (self.bmod >= self.hours[0]) & (self.bmod <= self.hours[1])
        if exit_mode == "st":
            ok &= (self.dir != 0) & np.isfinite(self.line)
        else:
            ok &= np.isfinite(self.ema21) & np.isfinite(self.atr14)
        cand = np.nonzero(ok)[0]
        rows, tries = [], 0
        while len(rows) < n and tries < 20 * max(n, 1) and len(cand):
            tries += 1
            k = int(rng.choice(cand))
            side = int(self.dir[k]) if exit_mode == "st" else (1 if self.c[k] >= self.ema21[k] else -1)
            t = self.trade(k, side, exit_mode=exit_mode)
            if t is not None:
                t.pop("jx")
                rows.append(t)
        return pd.DataFrame(rows)


def judge(t: pd.DataFrame, split: str, ctrl_avg: float | None) -> dict:
    s = S.judge(t, split, None)
    if s.get("n"):
        s["ctrl"] = float(ctrl_avg) if ctrl_avg is not None else float("nan")
        s["pass"] = bool(s["pass"] and (ctrl_avg is None or (np.isfinite(ctrl_avg) and s["avg"] > ctrl_avg)))
    return s


def hold_market(m1, tf, fin=FIN) -> Mk:
    return Mk(m1, tf, hours=None, flat=None, fin=fin)


def er_market(m1) -> Mk:
    return Mk(m1, "15min", hours=(120, 930), flat=S.FLAT, fin=0.0)


def run(period: str, hist: Path | None = None, out: Path | None = None, data: dict | None = None) -> dict:
    hist, out = hist or S.HIST[period], out or OUT[period]
    if (out / "summary.json").exists():
        raise SystemExit(f"registered: {out} already holds a result; the {period} judgement is made once")
    a, b, split = PERIODS[period]
    passed = None
    if period == "vault":
        p = OUT["seen"] / "summary.json"
        if not p.exists():
            raise SystemExit("registered: run the seen period first (it decides which part 1/3 primaries reach the vault)")
        seen = json.loads(p.read_text())
        passed = {k for k, v in seen.items() if isinstance(v, dict) and v.get("pass")}
    rng = np.random.default_rng(SEED)
    get = (lambda s: data.get(s)) if data is not None else (lambda s: S.load(hist, s, a, b))
    m1s = {s: get(s) for s in S.SYMS}
    missing = [s for s, m in m1s.items() if m is None or not len(m)]
    res, info, extra = {}, {}, []

    def pool(fn):
        parts = [fn(s, m).assign(sym=s) for s, m in m1s.items() if m is not None and len(m)]
        parts = [p for p in parts if len(p)]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    # part 1 — held trades
    for name in HOLD:
        if passed is not None and name not in passed:
            continue
        tf = "1h" if name.endswith("1h") else "4h"
        mode = "st" if "_st_" in name else "er"
        kind = S.PRIMARY if mode == "st" else "er"
        mk = {s: hold_market(m, tf) for s, m in m1s.items() if m is not None and len(m)}
        t = pool(lambda s, m: mk[s].run2(kind, mode))
        c = pool(lambda s, m: mk[s].control2(len(mk[s].run2(kind, mode)), rng, mode))
        res[name] = judge(t, split, float(c.r.mean()) if len(c) else None)
        res[name]["fin0"] = float(t.r_nofin.mean()) if len(t) else None
        res[name]["fin10"] = float((t.r_nofin - 0.10 * t.fin_unit).mean()) if len(t) else None
        res[name]["nights"] = float(t.nights.mean()) if len(t) else None
        info[name] = t
    # part 2 — NDQ only, vault only
    if period == "vault" and m1s.get("NDQ") is not None and len(m1s["NDQ"]):
        mk = S.Market(m1s["NDQ"], "15min")
        t = mk.run(S.PRIMARY)
        c = mk.control(len(t), rng)
        res["ndq_st_15m"] = judge(t, split, float(c.r.mean()) if len(c) else None)
        info["ndq_st_15m"] = t
    # part 3 — SuperTrend inside EMA21/RSI55, gold + US30 intraday
    er_m = {s: er_market(m1s[s]) for s in ER_SYMS if m1s.get(s) is not None and len(m1s[s])}

    def pool_er(fn, syms=ER_SYMS):
        parts = [fn(er_m[s]).assign(sym=s) for s in syms if s in er_m]
        parts = [p for p in parts if len(p)]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    base = pool_er(lambda m: m.run2("er", "er"))
    info["er_base"] = base
    if passed is None or "er_st_filter" in passed:
        t = pool_er(lambda m: m.run2("er", "er", st_filter=True))
        res["er_st_filter"] = judge(t, split, float(base.r.mean()) if len(base) else None)
        info["er_st_filter"] = t
    if passed is None or "er_gold_06" in passed:
        t = pool_er(lambda m: m.run2("er", "er", only_hour=6), ("XAUUSD",))
        rest = pool_er(lambda m: m.run2("er", "er", not_hour=6), ("XAUUSD",))
        res["er_gold_06"] = judge(t, split, float(rest.r.mean()) if len(rest) else None)
        info["er_gold_06"] = t
    if period == "seen":
        info["er_st_exit"] = pool_er(lambda m: m.run2("er", "st"))
    # report
    out.mkdir(parents=True, exist_ok=True)
    for k, t in info.items():
        if len(t):
            t.to_csv(out / f"trades_{k}.csv.gz", index=False)
    head = "| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    md = [f"# Trend rules held, NDQ SuperTrend, SuperTrend in EMA21/RSI55 — {period} ({a} → {b})", "",
          "Registered Nov 2 2026 before running (research/trend_hold/PREREGISTRATION_2026-11-02.md). Real bid/ask "
          "1-minute data, entries at the signal candle's close, stops on the 1-minute bid/ask, one trade at a time.", "",
          "Gates: ≥ 100 trades, avg R > 0, 95% range above 0, avg R > 0 at 2× costs, both halves > 0, beats its control.",
          "", head, sep]
    labels = {"hold_st_1h": "Held — SuperTrend rule, 1h", "hold_st_4h": "Held — SuperTrend rule, 4h",
              "hold_er_1h": "Held — EMA21/RSI55, 1h", "hold_er_4h": "Held — EMA21/RSI55, 4h",
              "ndq_st_15m": "NDQ only — SuperTrend rule, 15m intraday",
              "er_st_filter": "EMA21/RSI55 + SuperTrend agrees (gold, US30, 15m)",
              "er_gold_06": "EMA21/RSI55 gold, 06:00 hour only"}
    for k in labels:
        if k in res:
            md.append(S.row(labels[k], res[k]))
    if any(k in res for k in HOLD):
        md += ["", "Held trades pay financing at 5% a year of the position value (registered). Same trades at 0% / 10%:", "",
               "| primary | avg R at 0% | at 5% | at 10% | avg nights held |", "|---|---|---|---|---|"]
        for k in HOLD:
            if k in res and res[k].get("n"):
                r = res[k]
                md.append(f"| {labels[k]} | {r['fin0']:+.3f} | {r['avg']:+.3f} | {r['fin10']:+.3f} | {r['nights']:.1f} |")
    passers = [k for k, v in res.items() if v.get("pass")]
    if period == "seen":
        md += ["", ("**Passed on 2021–2026: " + ", ".join(passers) + " → one judgement each on 2016–2020 with "
                    "./fx.sh trendhold vault (NDQ-only SuperTrend is judged there too).**") if passers else
               "**Nothing passed on 2021–2026. ./fx.sh trendhold vault still runs the registered NDQ-only check (part 2).**"]
        md += ["", "## Shown, not judged", "", head, sep, S.row("EMA21/RSI55 as the paper book (base)", S.judge(base, split), gate=False),
               S.row("EMA21/RSI55 with SuperTrend stop/trail/exit", S.judge(info.get("er_st_exit", pd.DataFrame()), split), gate=False)]
        for k in HOLD:
            t = info.get(k)
            if t is not None and len(t):
                md += ["", f"### {labels[k]} by instrument", "", head, sep]
                md += [S.row(s, S.judge(g.drop(columns="sym"), split), gate=False) for s, g in t.groupby("sym")]
        for name, t in (("EMA21/RSI55 (base)", base), ("EMA21/RSI55 + SuperTrend agrees", info.get("er_st_filter", pd.DataFrame()))):
            if len(t):
                md += ["", f"### {name}: avg R by instrument × entry hour (NY), trades in brackets", "",
                       "| hour | " + " | ".join(ER_SYMS) + " |", "|---|" + "---|" * len(ER_SYMS)]
                for h in sorted(t.hour.unique()):
                    cells = []
                    for s in ER_SYMS:
                        g = t[(t.sym == s) & (t.hour == h)]
                        cells.append(f"{g.r.mean():+.2f} ({len(g)})" if len(g) else "—")
                    md.append(f"| {h:02d} | " + " | ".join(cells) + " |")
    else:
        md += ["", "**Verdict on 2016–2020: " + ("; ".join(f"{labels[k]}: {'CONFIRMED' if v.get('pass') else 'not confirmed'}"
                                                      for k, v in res.items()) or "nothing to judge") + ".** "
               "A confirmed rule becomes a paper book first; any trading change is for the review."]
    if missing:
        md += ["", "No history for: " + ", ".join(missing)]
    (out / "report.md").write_text("\n".join(md) + "\n")
    summ = {**res, "period": period}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ


def main(argv=None):
    ap = argparse.ArgumentParser(description="Held trend rules / NDQ SuperTrend / SuperTrend in EMA21-RSI55 (Nov 2 2026)")
    ap.add_argument("--period", choices=tuple(PERIODS), default="seen")
    a = ap.parse_args(argv)
    run(a.period)
    print((OUT[a.period] / "report.md").read_text())


if __name__ == "__main__":
    main()
