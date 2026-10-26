"""A friend's weekly and daily rule books (research/weekly_rules/weekly_rules_backtest.py, kept UNCHANGED), run as he
wrote them, plus the checks our own tests use that his script doesn't have (Oct 26 2026):

  * financing (swap). His results are "no swap", but the rules hold for weeks to months. CFDs (indices, metals, oil)
    pay our engine's 1.8 bps of price per calendar day (~6.5% a year) long or short; forex pays a flat 0.6 bps a day
    (~2.2% a year, OANDA's markup) and its interest-rate carry is NOT modelled, so long USDJPY looks worse and short
    USDJPY better than it really was. Results are shown with and without swap.
  * 2x costs: every spread paid (entry and exit) and the swap charged once more.
  * volatility units: % per trade divided by the market's average daily range at entry, so gold, NDQ and EURUSD
    count equally when pooled (his "total %" lets the most volatile markets dominate).
  * the exact coin flip: each trade's entry day traded both long and short with the rule's own exit, averaged.
  * random timing: each trade repeated from 20 random other entry days in the same market, same side, same exit rule.
    If the rule's entries can't beat these, the profit comes from the exit and from being in trending markets, not
    from the entry signal.
  * a confidence range that respects overlap: trades are resampled in calendar-month blocks across all markets
    (his bootstrap treats 13 markets' simultaneous USD or risk-off trades as independent).
  * halves of the period by calendar date.

Data: OANDA daily bid/ask (his fetch). Default 5 years: inside our 2021→2026 "seen" period for NDQ / US30 / XAUUSD,
so the 2016–2020 vault stays untouched for this rule family too.

    python -m fxagents.weekly_rules [--years 5] [--markets ...] [--placebo 200]   → data/year_test/weekly_rules/report.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "weekly_rules" / "weekly_rules_backtest.py"
OUT = ROOT / "data" / "year_test" / "weekly_rules"
FX = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD")
SWAP_BPS = {"fx": 0.6, "cfd": 1.8}                      # per calendar day, of price
VARIANTS = ("WK", "WK0", "DY1", "DY2", "DY3")
N_TWINS = 20


def friend():
    spec = importlib.util.spec_from_file_location("weekly_rules_backtest", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── exits from an arbitrary entry (the same logic as his run_wk / run_dy, for the controls) ──
def wk_exit(X, wc, e18, widx, k_in, side):
    """His weekly exit: from the entry day on, the first day whose latest completed week closed beyond the EMA18;
    out at the next daily open. None → still open at the end."""
    n = len(X["bo"])
    for k in range(k_in, n - 1):
        j = widx[k]
        if j < 0 or not (np.isfinite(wc[j]) and np.isfinite(e18[j])):
            continue
        if (side > 0 and wc[j] < e18[j]) or (side < 0 and wc[j] > e18[j]):
            return k + 1
    return None


def dy_exit(X, e18, k_in, side):
    n = len(X["bo"])
    for k in range(k_in, n - 1):
        if (side > 0 and X["mc"][k] < e18[k]) or (side < 0 and X["mc"][k] > e18[k]):
            return k + 1
    return None


def price_ret(mod, X, side, k_in, k_out):
    """% return like his: buy the ask / sell the bid at the open; still open → marked at the last close."""
    n = len(X["bo"])
    e = X["ao"][k_in] if side > 0 else X["bo"][k_in]
    if k_out is None:
        k_out = n - 1
        px = X["bc"][k_out] if side > 0 else X["ac"][k_out]
    else:
        px = X["bo"][k_out] if side > 0 else X["ao"][k_out]
    return mod._ret(side, e, px), k_out


def costs(mk, X, idx, k_in, k_out):
    """(swap %, spread %) for one trade."""
    days = max((idx[k_out] - idx[k_in]).total_seconds() / 86400, 0.0)
    swap = days * SWAP_BPS["fx" if mk in FX else "cfd"] / 100
    sp = ((X["ao"][k_in] - X["bo"][k_in]) + (X["ao"][k_out] - X["bo"][k_out])) / X["mo"][k_in] * 100
    return swap, sp


def adr_pct(X, k):
    lo = max(0, k - 20)
    r = (X["mh"][lo:k] - X["ml"][lo:k]) / X["mc"][lo:k] * 100
    r = r[np.isfinite(r) & (r > 0)]
    return float(r.mean()) if len(r) else np.nan


def month_boot(df: pd.DataFrame, col: str, reps: int = 4000, seed: int = 3) -> tuple[float, float, float]:
    """Mean of `col` and its 95% range, resampling calendar months of entry (all markets together)."""
    x = df[["month", col]].dropna()
    if len(x) < 5:
        m = float(x[col].mean()) if len(x) else float("nan")
        return m, float("nan"), float("nan")
    g = x.groupby("month")[col].agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(g), size=(reps, len(g)))
    means = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    return float(s.sum() / c.sum()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def run(years: float, markets: list[str], placebo: int, mod=None) -> tuple[str, dict]:
    mod = mod or friend()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=int(years * 365))
    rows, problems, expo, bh = [], [], {}, []
    plc = {"WK": [], "DY1": []}
    rng = np.random.default_rng(11)
    for mk in markets:
        try:
            print(f"fetching {mk} ...", file=sys.stderr, flush=True)
            d = mod.fetch_daily(mod.INST[mk], start - timedelta(days=330))
            w, avail = mod.weekly_from_daily(d)
            wc, rsi_w = w["close"].to_numpy(), mod.rsi(w["close"], 14).to_numpy()
            ew18, ew21 = mod.ema(w["close"], 18).to_numpy(), mod.ema(w["close"], 21).to_numpy()
            dm = d["mc"]
            rsi_d, ed18, ed21 = mod.rsi(dm, 14).to_numpy(), mod.ema(dm, 18).to_numpy(), mod.ema(dm, 21).to_numpy()
            dec = (d.index + pd.Timedelta("24h")).as_unit("ns").asi8
            widx = np.searchsorted(avail, dec, side="right") - 1
            X = {k: d[k].to_numpy() for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "mo", "mh", "ml", "mc")}
            start_k = int(np.searchsorted(d.index.as_unit("ns").asi8, pd.Timestamp(start).as_unit("ns").value))
            idx = d.index.tz_convert(mod.NY)
            n = len(d)
            span = n - start_k
            runs = {"WK": lambda rw=rsi_w: mod.run_wk(X, wc, rw, ew18, ew21, widx, "WK", start_k),
                    "WK0": lambda: mod.run_wk(X, wc, rsi_w, ew18, ew21, widx, "WK0", start_k),
                    "DY1": lambda rw=rsi_w, rdd=rsi_d: mod.run_dy(X, rdd, rw, widx, ed18, ed21, 42, False, start_k),
                    "DY2": lambda: mod.run_dy(X, rsi_d, rsi_w, widx, ed18, ed21, 42, True, start_k),
                    "DY3": lambda: mod.run_dy(X, rsi_d, rsi_w, widx, ed18, ed21, 40, False, start_k)}
            new_week = np.r_[False, np.diff(widx) != 0]
            wk_days = np.flatnonzero(new_week & (np.arange(n) >= start_k) & (np.arange(n) < n - 2))
            dy_days = np.arange(max(start_k, 30), n - 2)
            for v, fn in runs.items():
                tr = fn()
                expo[(v, mk)] = sum(t["k_out"] - t["k_in"] for t in tr) / max(span, 1)
                weekly = v.startswith("WK")
                ex = (lambda k, s: wk_exit(X, wc, ew18, widx, k, s)) if weekly else (lambda k, s: dy_exit(X, ed18, k, s))
                pool = wk_days if weekly else dy_days
                for t in tr:
                    k_in, k_out, side = t["k_in"], t["k_out"], t["side"]
                    sw, sp = costs(mk, X, idx, k_in, k_out)
                    a = adr_pct(X, k_in - 1)
                    # exact coin flip: the same entry day, long and short, each with its own exit, averaged
                    cf = []
                    for s in (1, -1):
                        r_, ko = price_ret(mod, X, s, k_in, ex(k_in, s))
                        csw, _ = costs(mk, X, idx, k_in, ko)
                        cf.append(r_ - csw)
                    # random timing: same side, random other entry days (decision day k → entry k+1), same exit rule
                    others = pool[pool != k_in - 1]
                    rt = []
                    for kd in rng.choice(others, size=min(N_TWINS, len(others)), replace=False) if len(others) else []:
                        r_, ko = price_ret(mod, X, side, int(kd) + 1, ex(int(kd) + 1, side))
                        rsw, _ = costs(mk, X, idx, int(kd) + 1, ko)
                        rt.append(r_ - rsw)
                    rows.append(dict(market=mk, variant=v, side=side, ret=t["ret"], mae=t["mae"], t_in=idx[k_in],
                                     t_out=idx[k_out], days=k_out - k_in, reason=t["reason"], swap=sw, spread=sp, adr=a,
                                     coin=float(np.mean(cf)), rand=float(np.mean(rt)) if rt else np.nan))
            if placebo:
                nw, nd = len(rsi_w), len(rsi_d)
                prng = np.random.default_rng(7 + len(plc["WK"]))
                swi, sdi = prng.integers(20, nw - 20, size=placebo), prng.integers(60, nd - 60, size=placebo)
                plc["WK"].append(np.array([sum(t["ret"] for t in runs["WK"](np.roll(rsi_w, int(a)))) for a in swi]))
                plc["DY1"].append(np.array([sum(t["ret"] for t in runs["DY1"](np.roll(rsi_w, int(a)), np.roll(rsi_d, int(b))))
                                            for a, b in zip(swi, sdi)]))
            bh.append((mk, (d["mc"].iloc[-1] / d["mo"].iloc[start_k] - 1) * 100))
            print(f"  {mk}: done", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            problems.append(f"{mk}: {type(e).__name__}: {e}")
    if not rows:
        return "no trades — check the data fetch (OANDA_API_TOKEN set?)\n" + "\n".join(problems), {}
    T = pd.DataFrame(rows)
    T["t_in"] = pd.to_datetime(T["t_in"], utc=True).dt.tz_convert(mod.NY)
    T["t_out"] = pd.to_datetime(T["t_out"], utc=True).dt.tz_convert(mod.NY)
    T["net"] = T.ret - T.swap
    T["net2x"] = T.ret - 2 * T.swap - T.spread
    T["u"] = T.net / T.adr                                         # in average-daily-range units
    T["u2x"] = T.net2x / T.adr
    T["coin_edge_u"] = (T.net - T.coin) / T.adr
    T["rand_edge_u"] = (T.net - T.rand) / T.adr
    T["month"] = T.t_in.dt.strftime("%Y-%m")

    class A:                                                       # his report() reads these
        pass
    args = A()
    args.insample = "XAUUSD,NDQ,US30"
    cut = T.t_in.max() - pd.DateOffset(months=18)
    L = ["# Weekly and daily rule books (a friend's rules), with our controls\n",
         f"Generated {now:%Y-%m-%d %H:%M} UTC. OANDA daily bid/ask, {years:g} years (entries from {start:%Y-%m-%d}), "
         f"markets {','.join(markets)}. Rules and his tables exactly as his script; our checks are the first section.\n",
         "Reference, simply holding each market over the same period: " + ", ".join(f"{m} {r:+.0f}%" for m, r in bh) + "\n"]
    L += ours(T, plc, placebo)
    L += ["\n---\n\n# His tables (no swap, as in his script)\n"]
    L += mod.report(T[T.variant.isin(mod.WEEKLY)], mod.WEEKLY,
                    "WEEKLY rule book (WK = your rule, WK0 = the same without the RSI condition)", args, cut, expo)
    L += mod.report(T[T.variant.isin(mod.DAILY)], mod.DAILY,
                    "DAILY rule book (DY1 = sell trigger at 42, DY2 = plus EMA21 side at entry, DY3 = sell trigger at 40)",
                    args, cut, expo)
    for v in ("WK", "DY1"):
        x = T[T.variant == v].sort_values(["market", "t_in"])
        L.append(f"\n## Every trade of {v} ({len(x)} trades)\n")
        L.append("| Market | Side | Entry | Exit | Days | Result % | Swap % | Net % | Worst dip % | Ended |\n"
                 "|---|---|---|---|---|---|---|---|---|---|")
        for _, r in x.iterrows():
            L.append(f"| {r.market} | {'long' if r.side > 0 else 'short'} | {r.t_in:%Y-%m-%d} | {r.t_out:%Y-%m-%d} | {r.days} | "
                     f"{r.ret:+.1f} | {r.swap:.1f} | {r.net:+.1f} | {r.mae:.1f} | {r.reason} |")
    if problems:
        L.append("\n## Problems during the run (these markets are missing)\n\n" + "\n".join(f"- {p}" for p in problems))
    summ = {v: {k: (None if not np.isfinite(x) else round(float(x), 4)) for k, x in
                zip(("avg_u", "lo", "hi"), month_boot(T[T.variant == v], "u"))} for v in VARIANTS}
    return "\n".join(L) + "\n", {"trades": int(len(T)), "by_variant": summ, "problems": problems}


def ours(T: pd.DataFrame, plc: dict, placebo: int) -> list[str]:
    L = ["## Our checks\n",
         "Swap: CFDs 1.8 bps of price per calendar day long or short (our engine's figure), forex 0.6 bps a day; "
         "forex interest-rate carry is NOT modelled. **u** = % per trade ÷ the market's average daily range (%) at entry, "
         "so every market counts alike. 95% ranges resample calendar months of entry across all markets.\n",
         "| Rule | Trades | Win | Avg % (no swap) | Avg % after swap | **Avg u after swap (95%)** | 2× costs u | "
         "Halves u (by date) | Coin-flip edge u (95%) | Random-timing edge u (95%) | Avg days |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    mid = T.t_in.min() + (T.t_in.max() - T.t_in.min()) / 2
    verdict = {}
    for v in VARIANTS:
        x = T[T.variant == v]
        if not len(x):
            continue
        u, lo, hi = month_boot(x, "u")
        u2 = month_boot(x, "u2x")[0]
        h1, h2 = x[x.t_in < mid].u.mean(), x[x.t_in >= mid].u.mean()
        ce, clo, chi = month_boot(x, "coin_edge_u")
        re, rlo, rhi = month_boot(x, "rand_edge_u")
        L.append(f"| {v} | {len(x)} | {(x.net > 0).mean():.0%} | {x.ret.mean():+.2f} | {x.net.mean():+.2f} | "
                 f"**{u:+.3f}** ({lo:+.3f} … {hi:+.3f}) | {u2:+.3f} | {h1:+.3f} / {h2:+.3f} | "
                 f"{ce:+.3f} ({clo:+.3f} … {chi:+.3f}) | {re:+.3f} ({rlo:+.3f} … {rhi:+.3f}) | {x.days.mean():.0f} |")
        verdict[v] = {"≥ 100 trades (all markets)": len(x) >= 100, "avg > 0 after swap": u > 0,
                      "95% range above 0": lo > 0, "positive at 2× costs": u2 > 0,
                      "positive in both halves": h1 > 0 and h2 > 0, "beats the coin flip (95%)": clo > 0,
                      "beats random timing (95%)": rlo > 0}
    L += ["", "| Gate (pooled, our bar) | " + " | ".join(verdict) + " |", "|---|" + "---|" * len(verdict)]
    for g in next(iter(verdict.values())):
        L.append(f"| {g} | " + " | ".join("yes" if verdict[v][g] else "no" for v in verdict) + " |")
    L.append("| PASS | " + " | ".join("**yes**" if all(verdict[v].values()) else "no" for v in verdict) + " |")
    L.append("\nA pooled pass across markets is weaker evidence than our per-instrument gates: markets move together "
             "(USD, risk-off), and each single market has too few trades for a test of its own.\n")
    L += ["### By market (WK and DY1, avg u after swap; trades)\n",
          "| Market | WK | WK0 | DY1 | Group |", "|---|---|---|---|---|"]
    for mk in sorted(T.market.unique()):
        cells = []
        for v in ("WK", "WK0", "DY1"):
            x = T[(T.variant == v) & (T.market == mk)]
            cells.append(f"{x.u.mean():+.2f} ({len(x)})" if len(x) else "–")
        grp = "looked at before" if mk in ("XAUUSD", "NDQ", "US30") else ("forex" if mk in FX else "other CFD")
        L.append(f"| {mk} | " + " | ".join(cells) + f" | {grp} |")
    L += ["\n### Does the RSI add anything? (WK against WK0, same markets)\n"]
    a, b = T[T.variant == "WK"], T[T.variant == "WK0"]
    L.append(f"WK {a.u.mean():+.3f}u on {len(a)} trades; WK0 (no RSI) {b.u.mean():+.3f}u on {len(b)} trades.")
    if placebo and plc["WK"]:
        L.append("\nHis placebo (the RSI slid to a random point in time; no swap, % summed over markets):\n")
        L.append("| Rule | Real total % | Placebo average | Placebo 5th…95th | Placebo runs ≥ real |\n|---|---|---|---|---|")
        for v in ("WK", "DY1"):
            real = T[T.variant == v].ret.sum()
            tot = np.sum(plc[v], axis=0)
            L.append(f"| {v} | {real:+.1f} | {tot.mean():+.1f} | {np.percentile(tot, 5):+.1f}…{np.percentile(tot, 95):+.1f} | "
                     f"{(tot >= real).mean():.0%} |")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fxagents.weekly_rules")
    ap.add_argument("--years", type=float, default=5)
    ap.add_argument("--markets", default=None, help="default: every market in his script")
    ap.add_argument("--placebo", type=int, default=200)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    mod = friend()
    markets = (a.markets or mod.ALL).split(",")
    txt, summ = run(a.years, markets, a.placebo)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(txt)
    (out / "summary.json").write_text(json.dumps(summ, default=str, indent=1))
    print(txt.split("\n---\n")[0])


if __name__ == "__main__":
    main()
