"""US30 one-stock reversal (registered Nov 7 2026: research/dow_reversal/PREREGISTRATION_2026-11-07.md).

When one Dow member's dollar move supplies ≥ 35% of the members' absolute dollar moves over 15 minutes, then stalls
while ≥ 18 of the other 29 turn against it and US30 still holds ≥ 70% of the move, fade US30 for 20 minutes.
Control: the same breadth turn when no member dominates (largest share ≤ 20%), matched by stratum.

    python -m fxagents.dow_reversal seen|vault
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .dow_data import ROOT, SKIP_DAYS, load_day_closes
from .imom import load_sets

NY = "America/New_York"
MIN = pd.Timedelta("1min")
SCANS = [f"{h:02d}:{m:02d}" for h, m in [(10, 0), (10, 5), (10, 10), (10, 15), (10, 20), (10, 25), (10, 30), (10, 35),
                                          (10, 40), (10, 45), (10, 50), (10, 55), (11, 0), (11, 5), (11, 10), (11, 15),
                                          (13, 45), (13, 50), (13, 55), (14, 0), (14, 5), (14, 10), (14, 15), (14, 20),
                                          (14, 25), (14, 30), (14, 35), (14, 40), (14, 45), (14, 50)]]
P = {"conc": 0.35, "ctrl_conc": 0.20, "pause": 0.10, "breadth": 18, "retain": 0.70, "atr_n": 14, "stop_atr": 1.5,
     "entry_atr": 0.15, "cost_frac": 0.10, "cost_mult": 1.1, "hold_min": 20}
STAGES = {"seen": (("holdout_m1", "dev_m1"), "2021-01-01", "2026-09-30", "2023-11-17"),
          "vault": (("old_m1_idx",), "2016-01-01", "2020-12-31", "2018-07-01")}
OUT = Path("data/year_test")


def out_dir(stage):
    return OUT / f"dow_reversal_{stage}"


# ── the decision kernel (Astra's reference logic; control variant added) ─────
def side_of(formation, follow, broker_initial, broker_total, atr_before_pause, control=False):
    """formation / follow: 30 dollar changes; broker moves and ATR in US30 points. Returns (side, info)."""
    f, g = np.asarray(formation, float), np.asarray(follow, float)
    if len(f) != 30 or len(g) != 30 or atr_before_pause <= 0 or not (np.isfinite(f).all() and np.isfinite(g).all()):
        return 0, "basket"
    gross, net = np.abs(f).sum(), f.sum()
    if not gross or not net:
        return 0, "flat"
    largest = np.abs(f).max()
    leaders = np.flatnonzero(np.abs(f) == largest)
    if len(leaders) != 1:
        return 0, "tie"
    L, s = int(leaders[0]), (1 if net > 0 else -1)
    share = largest / gross
    if control:
        if share > P["ctrl_conc"]:
            return 0, "concentrated"
    else:
        if s * f[L] <= 0 or share < P["conc"]:
            return 0, "not concentrated"
        if abs(g[L]) > P["pause"] * largest:
            return 0, "leader kept going"
    if s * broker_initial < atr_before_pause:
        return 0, "US30 moved < 1 ATR"
    rest = np.delete(g, L)
    if (s * rest < 0).sum() < P["breadth"] or s * rest.sum() >= 0:
        return 0, "no breadth turn"
    if s * broker_total < P["retain"] * s * broker_initial:
        return 0, "US30 already gave back"
    return -s, {"L": L, "s": s, "share": float(share)}


# ── US30 helpers ─────────────────────────────────────────────────────────────
class US30:
    def __init__(self, m1: pd.DataFrame):
        self.m1 = m1
        self.idx = m1.index
        self.ns = m1.index.as_unit("ns").asi8
        self.mid = m1.m_c.to_numpy()
        b = m1[["m_o", "m_h", "m_l", "m_c"]].resample("5min", label="left", closed="left").agg(
            {"m_o": "first", "m_h": "max", "m_l": "min", "m_c": "last"}).dropna()
        tr = pd.concat([b.m_h - b.m_l, (b.m_h - b.m_c.shift()).abs(), (b.m_l - b.m_c.shift()).abs()], axis=1).max(axis=1)
        self.b5 = pd.DataFrame({"tr": tr, "start": b.index})
        self.b5_ns = b.index.as_unit("ns").asi8
        self.cols = {c: m1[c].to_numpy() for c in ("ask_o", "bid_o", "ask_h", "bid_l", "bid_c", "ask_c")}

    def at(self, T: pd.Timestamp) -> int | None:
        """Row of the minute bar starting T−1min (or the latest in [T−3, T−1] min)."""
        t = (T - MIN).value
        j = np.searchsorted(self.ns, t, side="right") - 1
        return int(j) if j >= 0 and t - self.ns[j] <= 2 * 60 * 1_000_000_000 else None

    def mid_at(self, T):
        j = self.at(T)
        return None if j is None else float(self.mid[j])

    def atr(self, T) -> float | None:
        """Simple average TR of the 14 complete 5-min bars ending ≤ T; the 15 bars must be consecutive."""
        k = np.searchsorted(self.b5_ns, (T - pd.Timedelta("5min")).value, side="right")
        if k < 15:
            return None
        starts = self.b5_ns[k - 15:k]
        if starts[-1] != (T - pd.Timedelta("5min")).value or np.any(np.diff(starts) != 300 * 1_000_000_000):
            return None
        return float(self.b5.tr.iloc[k - 14:k].mean())

    def minute(self, T) -> int | None:
        """Row of the minute starting exactly at T."""
        j = np.searchsorted(self.ns, T.value)
        return int(j) if j < len(self.ns) and self.ns[j] == T.value else None


def execute(us: US30, T: pd.Timestamp, side: int) -> tuple[dict | None, str]:
    A, mid = us.atr(T), us.mid_at(T)
    j0 = us.minute(T)
    if A is None or mid is None or j0 is None:
        return None, "US30 data"
    c = us.cols
    entry = c["ask_o"][j0] if side > 0 else c["bid_o"][j0]
    stop = mid - side * P["stop_atr"] * A
    risk = abs(entry - stop)
    jm = us.at(T)
    spread = float(c["ask_c"][jm] - c["bid_c"][jm])
    if abs(entry - mid) > P["entry_atr"] * A:
        return None, "entry too far from decision price"
    if side * (entry - stop) <= 0:
        return None, "entry beyond the stop"
    if spread * P["cost_mult"] > P["cost_frac"] * risk:
        return None, "cost > 10% of risk"
    jx_t = T + pd.Timedelta(minutes=P["hold_min"])
    jx = us.minute(jx_t)
    if jx is None:
        k = np.searchsorted(us.ns, jx_t.value)
        if k >= len(us.ns) or us.ns[k] - jx_t.value > 5 * 60 * 1_000_000_000:
            return None, "US30 data"
        jx = int(k)
    px, why, at = None, "time", jx
    for j in range(j0, jx):
        if side > 0 and c["bid_l"][j] <= stop:
            px, why, at = (min(stop, c["bid_o"][j]) if j > j0 else stop), "stop", j
            break
        if side < 0 and c["ask_h"][j] >= stop:
            px, why, at = (max(stop, c["ask_o"][j]) if j > j0 else stop), "stop", j
            break
    if px is None:
        px = c["bid_o"][jx] if side > 0 else c["ask_o"][jx]
    sp_in = c["ask_o"][j0] - c["bid_o"][j0]
    sp_out = c["ask_o"][at] - c["bid_o"][at]
    R = side * (px - entry) / risk
    return {"entry": entry, "exit": px, "stop": stop, "risk": risk, "A": A, "R": R,
            "R_2x": R - (sp_in + sp_out) / 2 / risk, "bps": side * (px - entry) / entry * 1e4,
            "exit_reason": why, "exit_time": us.idx[at]}, "filled"


def price_rows(cl: pd.DataFrame, Ts) -> pd.DataFrame:
    """Members' prices at each T (close of the bar starting T−1min, or the latest within 2 more minutes)."""
    g = cl.reindex(pd.date_range(cl.index.min(), cl.index.max(), freq="1min")).ffill(limit=2) if len(cl) else cl
    return pd.DataFrame({T: (g.loc[T - MIN] if len(g) and (T - MIN) in g.index else pd.Series(np.nan, index=cl.columns))
                         for T in Ts}).T


def scan_day(day: pd.Timestamp, us: US30, root: Path) -> dict:
    """First qualifying scan of the day for the rule and for the control, with execution."""
    cl = load_day_closes(day, root)
    base = day.tz_localize(NY)
    times = [base + pd.Timedelta(hours=int(s[:2]), minutes=int(s[3:])) for s in SCANS]
    need = sorted({x for T in times for x in (T - pd.Timedelta("20min"), T - pd.Timedelta("5min"), T)})
    px = price_rows(cl, need) if len(cl.columns) == 30 else pd.DataFrame()
    out = {"day": day, "scans": 0, "gaps": 0, "rule": None, "ctrl": None, "refused": {}}
    for T in times:
        a, b = T - pd.Timedelta("20min"), T - pd.Timedelta("5min")
        if px.empty or px.loc[[a, b, T]].isna().any().any():
            out["gaps"] += 1
            continue
        m_a, m_b, m_t, A5 = us.mid_at(a), us.mid_at(b), us.mid_at(T), us.atr(b)
        if None in (m_a, m_b, m_t, A5):
            out["gaps"] += 1
            continue
        out["scans"] += 1
        D, F = (px.loc[b] - px.loc[a]).to_numpy(), (px.loc[T] - px.loc[b]).to_numpy()
        for kind, ctrl in (("rule", False), ("ctrl", True)):
            if out[kind] is not None:
                continue
            side, info = side_of(D, F, m_b - m_a, m_t - m_a, A5, control=ctrl)
            if not side:
                continue
            tr, why = execute(us, T, side)
            rec = {"T": T, "side": side, "move_atr": abs(m_b - m_a) / A5, "share": info["share"], "status": why}
            if not ctrl:                                        # information: concentration in % terms, leader / rest after
                pa, pb = px.loc[a].to_numpy(), px.loc[b].to_numpy()
                pct = np.abs((pb - pa) / pa)
                rec["share_pct"] = float(pct[info["L"]] / pct.sum()) if pct.sum() else np.nan
                rec["leader"] = cl.columns[info["L"]]
            if tr:
                rec.update(tr)
                if not ctrl:
                    te = min(tr["exit_time"].tz_convert(NY).floor("min"), T + pd.Timedelta(minutes=P["hold_min"]))
                    pe = price_rows(cl, [te]).iloc[0].to_numpy()
                    if np.isfinite(pe).all():
                        s = info["s"]
                        rec["leader_resumed"] = bool(s * (pe[info["L"]] - px.loc[T].to_numpy()[info["L"]]) > 0)
                        rest = np.delete(pe - px.loc[T].to_numpy(), info["L"])
                        rec["rest_continued"] = bool(s * rest.sum() < 0)
            else:
                out["refused"][why] = out["refused"].get(why, 0) + 1
            out[kind] = rec                                     # one attempt per day, refused or not
        if out["rule"] is not None and out["ctrl"] is not None:
            break
    return out


# ── statistics ───────────────────────────────────────────────────────────────
def block_mean(days: pd.DatetimeIndex, t: pd.DataFrame, col: str, q=(0.025, 0.975), B=4000, blk=5, seed=7):
    """Range of the mean of `col` per trade, resampling 5-session blocks of ALL stage days (zero-event days kept)."""
    if not len(t):
        return (float("nan"),) * len(q)
    g = t.groupby(t.day)[col].agg(["sum", "count"]).reindex(days, fill_value=0)
    s, k, n = g["sum"].to_numpy(float), g["count"].to_numpy(float), len(g)
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, n, (B, -(-n // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :n] % n
    den = k[ix].sum(1)
    m = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    return tuple(float(x) for x in np.nanquantile(m, q))


def vol_terciles(us: US30, days: pd.DatetimeIndex) -> pd.Series:
    close = pd.Series({d: us.mid_at(d.tz_localize(NY) + pd.Timedelta(hours=16)) for d in days}, dtype=float)
    vol = np.log(close).diff().rolling(20).std().shift(1)
    cuts = vol.quantile([1 / 3, 2 / 3]).to_numpy()
    return pd.Series(np.where(vol.isna(), -1, np.digitize(vol, cuts)), index=days)


def match(rule: pd.DataFrame, ctrl: pd.DataFrame) -> pd.Series:
    """Each rule trade's matched control R (nearest |move| / ATR in the same stratum; ties → nearest date)."""
    out = pd.Series(np.nan, index=rule.index)
    for i, r in rule.iterrows():
        c = ctrl[(ctrl.half == r.half) & (ctrl.bucket == r.bucket) & (ctrl.side == r.side) & (ctrl.terc == r.terc)]
        if r.terc < 0 or not len(c):
            continue
        dist = (c.move_atr - r.move_atr).abs()
        dd = (c.day - r.day).abs()
        k = pd.DataFrame({"a": dist, "b": dd}).sort_values(["a", "b"]).index[0]
        out[i] = c.loc[k, "R"]
    return out


def judge(rule, days, split):
    n, nd = len(rule), rule.day.nunique() if len(rule) else 0
    if n < 100 or nd < 100:
        return {"trades": n, "days": nd, "inconclusive": True, "pass": False}
    lo, hi = block_mean(days, rule, "R")
    lo1 = block_mean(days, rule, "R", q=(0.0167,))[0]
    m = rule.dropna(subset=["d"])
    dlo, dhi = block_mean(days, m, "d") if len(m) else (np.nan, np.nan)
    first = rule.day < split
    st = {"trades": n, "days": nd, "inconclusive": False, "win": float((rule.R > 0).mean()), "avg_R": float(rule.R.mean()),
          "lo": lo, "hi": hi, "lo_98_3_onesided": lo1, "avg_R_2x": float(rule.R_2x.mean()),
          "h1": float(rule.R[first].mean()), "h2": float(rule.R[~first].mean()), "bps": float(rule.bps.mean()),
          "coverage": float(len(m) / n), "ctrl_R": float(m.ctrl_R.mean()) if len(m) else np.nan,
          "d": float(m.d.mean()) if len(m) else np.nan, "d_lo": dlo, "d_hi": dhi,
          "stop_share": float((rule.exit_reason == "stop").mean()),
          "best5_share": float(rule.R.nlargest(5).sum() / rule.R[rule.R > 0].sum()) if (rule.R > 0).any() else np.nan}
    g = {"≥100 trades on ≥100 days": True, "control coverage ≥ 90%": st["coverage"] >= 0.9, "95% range > 0": lo > 0,
         "both halves > 0": st["h1"] > 0 and st["h2"] > 0, "2× costs > 0": st["avg_R_2x"] > 0,
         "beats the breadth-turn control (95% > 0)": dlo > 0}
    st["gates"], st["pass"] = g, all(g.values())
    return st


def run_stage(stage: str, root_export: Path = Path("data/export"), stocks: Path = ROOT, out: Path | None = None) -> dict:
    if stage == "vault":
        f = out_dir("seen") / "summary.json"
        if not f.exists() or not json.loads(f.read_text())["result"].get("pass"):
            raise SystemExit("the vault opens only after a seen pass: the registration stops here")
    sets, a, b, split = STAGES[stage]
    split = pd.Timestamp(split)
    m1 = load_sets(sets, "US30", root_export)
    if m1 is None:
        raise SystemExit(f"no US30 export in {sets}")
    m1 = m1[(m1.index >= pd.Timestamp(a, tz=NY)) & (m1.index < pd.Timestamp(b, tz=NY) + pd.Timedelta(days=1))]
    m1.index = m1.index.tz_convert(NY)
    us = US30(m1)
    days = pd.DatetimeIndex(sorted(set(m1.index.tz_localize(None).normalize())))
    days = days[(days.dayofweek < 5) & ~days.isin(list(SKIP_DAYS))]
    rows, scans, gaps, refused = [], 0, 0, {}
    for k, day in enumerate(days):
        r = scan_day(day, us, stocks)
        scans += r["scans"]; gaps += r["gaps"]
        for w, n in r["refused"].items():
            refused[w] = refused.get(w, 0) + n
        for kind in ("rule", "ctrl"):
            if r[kind]:
                rows.append({"kind": kind, "day": day, **r[kind]})
        if (k + 1) % 250 == 0:
            print(f"  {k + 1}/{len(days)} days", flush=True)
    t = pd.DataFrame(rows)
    out = out or out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
    counts = {"days": len(days), "scans": scans, "data_gaps": gaps,
              "rule_signals": int((t.kind == "rule").sum()) if len(t) else 0,
              "rule_filled": int(((t.kind == "rule") & (t.status == "filled")).sum()) if len(t) else 0,
              "ctrl_filled": int(((t.kind == "ctrl") & (t.status == "filled")).sum()) if len(t) else 0, "refused": refused}
    res = {"pass": False, "inconclusive": True, "trades": 0, "days": 0}
    if len(t):
        f = t[t.status == "filled"].copy()
        f["half"] = np.where(f.day < split, 1, 2)
        f["bucket"] = [x.hour * 2 + x.minute // 30 for x in f["T"]]
        terc = vol_terciles(us, days)
        f["terc"] = f.day.map(terc).fillna(-1).astype(int)
        rule, ctrl = f[f.kind == "rule"].copy(), f[f.kind == "ctrl"].copy()
        rule["ctrl_R"] = match(rule, ctrl)
        rule["d"] = rule.R - rule.ctrl_R
        res = judge(rule, days, split)
        t.to_csv(out / "signals.csv.gz", index=False)
        if not res["inconclusive"]:
            res["by_year"] = {int(y): [int(len(g)), float(g.R.mean())] for y, g in rule.groupby(rule.day.dt.year)}
            res["by_side"] = {("long" if s > 0 else "short"): [int(len(g)), float(g.R.mean())] for s, g in rule.groupby("side")}
            res["exits"] = {k: [int(len(g)), float(g.R.mean())] for k, g in rule.groupby("exit_reason")}
            res["leader_resumed"] = float(rule.leader_resumed.mean()) if "leader_resumed" in rule else None
            res["rest_continued"] = float(rule.rest_continued.mean()) if "rest_continued" in rule else None
            res["share_pct_median"] = float(rule.share_pct.median())
            res["control"] = {"trades": len(ctrl), "avg_R": float(ctrl.R.mean()) if len(ctrl) else None}
            res["top_leaders"] = rule.leader.value_counts().head(5).to_dict()
    summ = {"stage": stage, "period": [a, b], "split": str(split.date()), "counts": counts, "result": res}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    (out / "report.md").write_text(report(summ))
    return summ


def f3(x):
    return "—" if x is None or not np.isfinite(x) else f"{x:+.3f}"


def report(s) -> str:
    c, r = s["counts"], s["result"]
    md = [f"# US30 one-stock reversal: {s['stage']} ({s['period'][0]} → {s['period'][1]})", "",
          "Registered Nov 7 2026 (research/dow_reversal/PREREGISTRATION_2026-11-07.md). Fade US30 for 20 min when one Dow "
          "member supplied ≥ 35% of the members' absolute dollar moves, stalled, and ≥ 18 of the other 29 turned. Stop "
          "1.5 × 5-min ATR. Real OANDA bid/ask. Control: the same breadth turn with no dominant member (≤ 20%), matched by "
          "half, 30-min bucket, side and volatility tercile.", "",
          "## Counts (read first)", "",
          f"- trading days: {c['days']:,} · scan times evaluated: {c['scans']:,} · skipped for missing data: {c['data_gaps']:,}",
          f"- rule signals: {c['rule_signals']:,} · filled: {c['rule_filled']:,} · control filled: {c['ctrl_filled']:,}",
          "- refused at execution: " + (", ".join(f"{k} {v}" for k, v in c["refused"].items()) or "none")]
    if r.get("inconclusive"):
        md += ["", f"**Inconclusive: {r['trades']} filled trades on {r['days']} days, below the registered 100.** "
               "Per the registration, returns are not shown and no threshold is changed."]
        return "\n".join(md) + "\n"
    md += ["", "## Result", "", "| trades | days | win | avg R | 95% range | 2× costs | halves | avg bps | control coverage | control R | vs control (95%) | result |",
           "|" + "---|" * 12,
           f"| {r['trades']} | {r['days']} | {r['win']:.0%} | **{f3(r['avg_R'])}** | {f3(r['lo'])} to {f3(r['hi'])} | "
           f"{f3(r['avg_R_2x'])} | {f3(r['h1'])} / {f3(r['h2'])} | {r['bps']:+.2f} | {r['coverage']:.0%} | {f3(r['ctrl_R'])} | "
           f"{f3(r['d'])} ({f3(r['d_lo'])} to {f3(r['d_hi'])}) | "
           + ("**PASS**" if r["pass"] else "fail: " + ", ".join(k for k, v in r["gates"].items() if not v)) + " |",
           "", "## Information", "",
           f"- one-sided 98.33% lower bound (the source's three-candidate level): {f3(r['lo_98_3_onesided'])}",
           f"- stop hits {r['stop_share']:.0%} · best five trades = {r['best5_share']:.0%} of all winning R",
           f"- after entry: leader resumed {r['leader_resumed']:.0%} · other 29 kept going against it {r['rest_continued']:.0%}"
           if r.get("leader_resumed") is not None else "",
           f"- concentration in % terms (median, rule trades): {r['share_pct_median']:.0%}",
           f"- control on its own: {r['control']['trades']} trades, {f3(r['control']['avg_R'])}R",
           "- most frequent leaders: " + ", ".join(f"{k} {v}" for k, v in r["top_leaders"].items()),
           "- by year: " + "; ".join(f"{y} {n} / {f3(m)}" for y, (n, m) in sorted(r["by_year"].items())),
           "- by side: " + "; ".join(f"{k} {n} / {f3(m)}" for k, (n, m) in r["by_side"].items()),
           "- exits: " + "; ".join(f"{k} {n} / {f3(m)}" for k, (n, m) in r["exits"].items())]
    nxt = {"seen": ("**Passed: the 2016–2020 vault is next (`./fx.sh dowrev vault`), once.**" if r["pass"] else
                    "**Did not pass: per the registration, this idea is closed.**"),
           "vault": ("**Confirmed on 2016–2020: a US30 paper book with a live Dow-constituent feed follows.**" if r["pass"]
                     else "**Not confirmed on 2016–2020: closed.**")}[s["stage"]]
    md += ["", nxt]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(STAGES))
    s = run_stage(ap.parse_args(argv).stage)
    print(json.dumps(s["counts"], default=str))
    print("result:", "PASS" if s["result"].get("pass") else "inconclusive" if s["result"].get("inconclusive") else "fail")


if __name__ == "__main__":
    sys.exit(main())
