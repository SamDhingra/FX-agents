"""Statistics and the pass gates for a backtest run (the same bar every test this year has used)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..simple_rules import stats as base_stats
from .data import NY


def frame(trades: list[dict]) -> pd.DataFrame:
    cols = ["entry_time", "exit_time", "side", "R", "R_2x", "cost_R", "hold_min", "overnight", "exit_reason"]
    if not trades:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(trades)


def days_of(m) -> pd.DatetimeIndex:
    loc = m.idx[[0, -1]].tz_convert(NY).normalize()
    d = pd.date_range(loc[0], loc[1], freq="D", tz=NY)
    return d[d.dayofweek < 5]


def equity(t: pd.DataFrame) -> dict:
    if not len(t):
        return {"t": [], "R": [], "max_dd_R": 0.0}
    t = t.sort_values("exit_time")
    cum = t.R.cumsum().to_numpy()
    dd = float((np.maximum.accumulate(np.r_[0, cum])[1:] - cum).max())
    return {"t": [x.isoformat() for x in t.exit_time], "R": [round(float(x), 4) for x in cum], "max_dd_R": dd}


def breakdown(t: pd.DataFrame, key) -> list[dict]:
    if not len(t):
        return []
    g = t.groupby(key).R.agg(["count", "mean", "sum"])
    return [{"key": (k.item() if hasattr(k, "item") else k), "trades": int(r["count"]), "avg_R": float(r["mean"]),
             "total_R": float(r["sum"])} for k, r in g.iterrows()]


def summarize(res: dict, m) -> dict:
    t, c = frame(res["trades"]), frame(res["coin"])
    days = days_of(m)
    s = base_stats(t, days) if len(t) else {"trades": 0}
    sc = base_stats(c, days) if len(c) else {"trades": 0}
    out = {"stats": s, "coin": sc, "funnel": res["funnel"]}
    if len(t) and len(c) == len(t):                  # paired: each real trade minus its own coin-flip twin
        out["coin_edge"] = base_stats(t.assign(R=t.R.to_numpy() - c.R.to_numpy(),
                                               R_2x=t.R_2x.to_numpy() - c.R_2x.to_numpy()), days)
    rd = frame(res.get("rand") or [])
    if len(rd):
        out["random"] = base_stats(rd, days)
        out["timing"] = base_stats(rd.assign(R=rd.edge, R_2x=rd.edge), days)      # real − random twins, per trade
    if len(t):
        loc = t.entry_time.dt.tz_convert(NY)
        half = len(t) // 2
        out["halves"] = [float(t.R.iloc[:half].mean()) if half else float("nan"), float(t.R.iloc[half:].mean())]
        out["by_year"] = breakdown(t, loc.dt.year)
        out["by_hour"] = breakdown(t, loc.dt.hour)
        out["by_side"] = breakdown(t, t.side.map({1: "long", -1: "short"}))
        out["by_exit"] = breakdown(t, t.exit_reason)
        out["equity"] = equity(t)
        out["hist"] = np.histogram(np.clip(t.R, -3, 6), bins=np.arange(-3, 6.25, 0.25))[0].tolist()
    out["gates"] = gates(out)
    return out


def gates(out: dict) -> dict:
    s, c = out["stats"], out["coin"]
    n = s.get("trades", 0)
    g = {
        "≥ 100 trades": n >= 100,
        "avg R > 0": n > 0 and s["avg_R"] > 0,
        "95% range above 0": n > 0 and s["ci_lo"] > 0,
        "positive at 2× costs": n > 0 and s["avg_R_2x"] > 0,
        "positive in both halves": n > 1 and all(x > 0 for x in out.get("halves", [-1])),
    }
    # Oct 22 2026 (PS-1 execution review): a positive average difference is not evidence — the paired difference's
    # 95% range (same day-block bootstrap as the headline) must be above 0.
    ce = out.get("coin_edge")
    if ce is not None:
        g["beats the coin flip (95% above 0)"] = bool(ce.get("trades") and ce["ci_lo"] > 0)
    else:
        g["beats the coin flip"] = n > 0 and c.get("trades", 0) > 0 and s["avg_R"] > c["avg_R"]
    if out.get("timing"):
        g["beats random timing (95% above 0)"] = bool(out["timing"].get("trades") and out["timing"]["ci_lo"] > 0)
    g["PASS"] = all(g.values())
    return g


def add_variant_gate(out: dict):
    """The rule must also beat each of its own variants (e.g. the same trigger without the trend filter)."""
    v = out.get("variants") or {}
    if v:
        s = out["stats"]
        out["gates"]["beats its variants"] = bool(s.get("trades") and all(
            s["avg_R"] > x.get("avg_R", -9) for x in v.values()))
        out["gates"]["PASS"] = all(val for k, val in out["gates"].items() if k != "PASS")


def text(name: str, ds: str, out: dict, audit: dict | None = None) -> str:
    s, c = out["stats"], out["coin"]
    L = [f"# {name} on {ds}", ""]
    if not s.get("trades"):
        L += ["No trades.", "", "Funnel: " + " → ".join(f"{k} {v}" for k, v in out["funnel"].items())]
        return "\n".join(L)
    L += [f"Trades {s['trades']}, win {s['win']:.0%}, avg {s['avg_R']:+.3f}R (95% {s['ci_lo']:+.3f} … {s['ci_hi']:+.3f}),"
          f" 2× costs {s['avg_R_2x']:+.3f}R, halves {out['halves'][0]:+.3f} / {out['halves'][1]:+.3f},"
          f" exact coin flip {c.get('avg_R', float('nan')):+.3f}R, max drawdown {out['equity']['max_dd_R']:.1f}R", ""]
    if out.get("coin_edge"):
        ce = out["coin_edge"]
        L += [f"Coin-flip edge (real − its coin twin, per trade) {ce['avg_R']:+.3f}R "
              f"(95% {ce['ci_lo']:+.3f} … {ce['ci_hi']:+.3f}).", ""]
    if out.get("timing"):
        tm, rd = out["timing"], out["random"]
        L += [f"Random timing (same side, same time of day, random other days, same stop % and exits): "
              f"{rd['avg_R']:+.3f}R. Timing edge (real − random) {tm['avg_R']:+.3f}R "
              f"(95% {tm['ci_lo']:+.3f} … {tm['ci_hi']:+.3f}).", ""]
    L += ["| gate | |", "|---|---|"] + [f"| {k} | {'yes' if v else 'no'} |" for k, v in out["gates"].items()] + [""]
    L += ["Funnel: " + " → ".join(f"{k} {v}" for k, v in out["funnel"].items()), ""]
    L += ["| year | trades | avg R |", "|---|---|---|"] + \
         [f"| {r['key']} | {r['trades']} | {r['avg_R']:+.3f} |" for r in out["by_year"]] + [""]
    L += ["| exit | trades | avg R |", "|---|---|---|"] + \
         [f"| {r['key']} | {r['trades']} | {r['avg_R']:+.3f} |" for r in out["by_exit"]] + [""]
    for k, v in (out.get("variants") or {}).items():
        L.append(f"Variant {k}: {v.get('trades', 0)} trades" + (f", avg {v['avg_R']:+.3f}R" if v.get("trades") else ""))
    if out.get("engine"):
        L += [f"Engine {out['engine']} (fill-minute targets, open-first ordering, market slippage "
              f"{out.get('market_slip_frac', 0):.0%} of spread)."]
    if audit:
        L += [f"Look-ahead audit: {audit['checked']} signals re-run on truncated data (time, side, stop, target, "
              f"entry price and risk limits compared), {audit['failed']} changed"
              + (f" (e.g. {', '.join(audit['examples'])})" if audit["failed"] else "") + "."]
    return "\n".join(L)
