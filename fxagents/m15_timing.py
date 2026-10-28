"""M15 timing (registered Oct 28 2026, research/m15_timing/PREREGISTRATION_2026-10-28.md, before any run).

Two ideas from the reviewers' post-mortems of losing trades, replayed on the playbook's own engine (research.simulate_live,
real bid/ask spread of every minute, each cell's own exit profile) for the 3m/5m playbook trades:

  A  m15_turn_entry  when the last M15 candle closed against the trade, wait up to 4 M15 candles for one that closes in
                     the trade's direction beyond the previous candle, enter then (same stop); cancel if the stop is
                     touched first, the session ends, or nothing confirms.        control: random later M15 entry.
  B  m15_inval_exit  before the first target, exit at market when a completed M15 candle closes beyond the far side of
                     the last M15 candle closed at entry.                         control: random M15 exit.

Engine check first: the plain replay must reproduce the recorded R on >= 98% of trades, else nothing is judged.
Paired per trade (d = R(rule) - R(recorded, replayed)), circular 5-weekday block bootstrap, both halves, 2x costs, beat the
control. A check that passes on seen is judged once on 2016-2020.

    python -m fxagents.m15_timing [--period seen|vault]   (./fx.sh m15timing [seen|vault]) -> data/year_test/m15_timing_<period>/report.md
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf_whatif as W
from . import whatif_judge as J
from .indicators import resample_ohlc
from .research import full_exit, mgmt_profiles, simulate_live
from .strategies import Strategy
from .structure import window_mask

CHECKS = ("m15_turn_entry", "m15_inval_exit")
WAIT_K = 4
MATCH_TOL, MATCH_MIN = 1e-3, 0.98
DRAWS, SEED_BOOT, SEED_A, SEED_B = 10_000, 7, 11, 13
LOWTF = {"3m": "3min", "3min": "3min", "5m": "5min", "5min": "5min"}


def _ns(idx) -> np.ndarray:
    return pd.DatetimeIndex(idx).as_unit("ns").asi8


class Arrays:
    """Everything one (symbol, timeframe) replay needs, built the way research.run_job builds it."""

    def __init__(self, cfg, m1: pd.DataFrame, tf: str):
        self.tf = tf
        if "volume" not in m1.columns:
            m1 = m1.assign(volume=1.0)
        df = resample_ohlc(m1, tf)
        ctx = Strategy._context(df)
        self.close_ts, self.atr = ctx["close_ts"], ctx["atr"]
        self.C_tf = df["close"].to_numpy(float)
        self.O, self.H, self.L, self.C = (m1[c].to_numpy(float) for c in ("open", "high", "low", "close"))
        self.close1 = m1.index + pd.Timedelta("1min")
        self.tmin = (m1.index.as_unit("ns").asi8 // 60_000_000_000).astype(np.int64)
        s = cfg["sessions"]
        fh, fm = map(int, s["flatten_at"].split(":"))
        mins = self.close1.hour * 60 + self.close1.minute
        self.flat = np.asarray((mins >= fh * 60 + fm) & (mins < 17 * 60), bool)
        late = np.asarray((mins >= fh * 60 + fm - 20) & (mins < 17 * 60), bool)
        self.entry_ok = window_mask(self.close1, s["entry_windows"]) & ~late          # a late entry must still be allowed
        self.max_hold_cfg = float(s["max_hold_minutes"])
        self.hs = (m1["spread"].to_numpy(float) / 2) if "spread" in m1.columns else np.zeros(len(m1))
        d5 = resample_ohlc(m1, "5min")
        c5 = Strategy._context(d5)
        cont5 = {sd: pd.Series(((np.sign(d5["close"].to_numpy() - c5["ema50"]) == sd) & (np.sign(c5["macd_hist"]) == sd)).astype(float),
                               index=d5.index + pd.Timedelta("5min")) for sd in (1, -1)}
        self.cont = {sd: cont5[sd].reindex(cont5[sd].index.union(self.close1)).ffill().reindex(self.close1).fillna(0).to_numpy() > 0.5
                     for sd in (1, -1)}
        self.j_of = np.searchsorted(_ns(m1.index), _ns(self.close_ts - pd.Timedelta("1min")), side="right") - 1
        r15 = m1.resample("15min", label="right", closed="left")
        b15 = pd.DataFrame({"o": r15["open"].first(), "h": r15["high"].max(), "l": r15["low"].min(), "c": r15["close"].last()}).dropna()
        self.lab15 = _ns(b15.index)                                                     # an M15 candle counts at its close
        self.o15, self.h15, self.l15, self.c15 = (b15[k].to_numpy(float) for k in ("o", "h", "l", "c"))
        pos = np.searchsorted(_ns(self.close1), self.lab15)
        ok = (pos < len(self.close1)) & (_ns(self.close1)[np.minimum(pos, len(self.close1) - 1)] == self.lab15)
        self.g15 = np.where(ok, pos, -1)                                                # 1m grid minute of that close (-1: missing)
        self.c1ns = _ns(self.close1)
        self.cts_ns = _ns(self.close_ts)

    def locate(self, ts) -> tuple[int, int] | None:
        """(tf bar i, 1m bar j0) of a recorded trade, checked as run_job checks them."""
        x = _ns(pd.DatetimeIndex([pd.Timestamp(ts)]))[0]
        i = int(np.searchsorted(self.cts_ns, x))
        if i >= len(self.cts_ns) or self.cts_ns[i] != x:
            return None
        j0 = int(self.j_of[i])
        if j0 < 0 or abs(self.C[j0] - self.C_tf[i]) > 1e-9 * max(1.0, abs(self.C_tf[i])):
            return None
        return i, j0

    def ref15(self, j0: int) -> int:
        """The last M15 candle closed at or before the entry minute's close."""
        return int(np.searchsorted(self.lab15, self.c1ns[j0], side="right") - 1)


@dataclasses.dataclass
class Trade:
    i: int
    j0: int
    side: int
    stop: float
    m: object
    fx: bool
    max_hold: float


class Fire:
    """an["inval"] for one trade: true at these 1m minutes only."""

    def __init__(self, js):
        self.js = set(int(j) for j in js)

    def __getitem__(self, j):
        return j in self.js


def sim(A: Arrays, tr: Trade, j: int, stop: float, m, hs, an=None):
    return simulate_live(A.O, A.H, A.L, A.C, A.tmin, j, tr.side, stop, m, hs, A.flat, A.cont[tr.side], tr.max_hold,
                         full_exit=tr.fx, an=an)


def late_entry(A: Arrays, tr: Trade, hs, forced_k: int | None = None) -> tuple[float, int | None, str]:
    """Rule A (forced_k None) or its control (enter at the forced_k-th M15 close; 0 = skip). (R, k entered, why)."""
    q = A.ref15(tr.j0)
    if forced_k == 0:
        return 0.0, None, "control_skip"
    j_prev, side = tr.j0, tr.side
    for k in range(1, WAIT_K + 1):
        qk = q + k
        if qk >= len(A.lab15):
            return 0.0, None, "no_data"
        jk = int(A.g15[qk])
        if jk < 0:
            continue
        seg = slice(j_prev + 1, jk + 1)
        far = (A.H[seg] + hs[seg]) if side < 0 else (A.L[seg] - hs[seg])
        if len(far) and ((far - tr.stop) * side <= 0).any():
            return 0.0, None, "stop_first"
        if A.flat[seg].any() or not A.entry_ok[jk]:
            return 0.0, None, "session"
        prev = A.l15[qk - 1] if side < 0 else A.h15[qk - 1]
        confirm = (k == forced_k) if forced_k else ((A.c15[qk] - A.o15[qk]) * side > 0 and (A.c15[qk] - prev) * side > 0)
        if confirm:
            px = A.C[jk]
            stop = tr.stop
            if (px - stop) * side <= 0:
                return 0.0, None, "stop_side"
            if abs(px - stop) < tr.m.min_stop_atr * A.atr[tr.i]:
                stop = px - side * tr.m.min_stop_atr * A.atr[tr.i]
            if abs(px - stop) / px > tr.m.max_stop_pct:
                return 0.0, None, "stop_too_wide"
            res = sim(A, tr, jk, stop, tr.m, hs)
            return (0.0, None, "no_fill") if res is None else (res["r"], k, "entered")
        j_prev = jk
    return 0.0, None, "no_confirm"


def inval_minutes(A: Arrays, tr: Trade, n: int = 64) -> list[tuple[int, int]]:
    """(k, 1m minute) of the M15 closes after entry that close beyond the reference candle's far side (rule B)."""
    q = A.ref15(tr.j0)
    lvl = A.h15[q] if tr.side < 0 else A.l15[q]
    out = []
    for k in range(1, n + 1):
        qq = q + k
        if qq >= len(A.lab15):
            break
        if A.g15[qq] >= 0 and (A.c15[qq] - lvl) * tr.side < 0:
            out.append((k, int(A.g15[qq])))
    return out


def m15_minute(A: Arrays, tr: Trade, k: int) -> int:
    qq = A.ref15(tr.j0) + k
    return int(A.g15[qq]) if 0 <= qq < len(A.lab15) else -1


def replay_symbol(cfg, g: pd.DataFrame, m1: pd.DataFrame, rng_a, rng_b, ctrl: dict | None) -> pd.DataFrame:
    """All per-trade replays for one symbol. ctrl: the rules' outcome distributions for the controls (None on the first pass)."""
    rows = []
    for tf, gt in g.groupby(g.tf.map(lambda x: LOWTF[str(x)])):
        A = Arrays(cfg, m1, tf)
        profiles = mgmt_profiles(cfg, tf)
        for r in gt.itertuples(index=False):
            out = {"kid": r.kid}
            loc = A.locate(r.ts)
            mg = str(getattr(r, "mgmt", "std"))
            if loc is None or mg not in profiles or not np.isfinite(r.risk_atr):
                rows.append({**out, "ok": False})
                continue
            i, j0 = loc
            m = profiles[mg]
            base = mg.split("|")[0]
            mh = 30.0 if base == "scalp" else 480.0 if base == "trend" else A.max_hold_cfg
            side = int(r.side)
            stop = A.C[j0] - side * float(r.risk_atr) * A.atr[i]
            tr = Trade(i, j0, side, stop, m, full_exit(cfg, mg), mh)
            out["ok"] = True
            for cost, hs in (("1x", A.hs), ("2x", A.hs * 2)):
                b = sim(A, tr, j0, stop, m, hs)
                out[f"base_{cost}"] = b["r"] if b else np.nan
                # A
                q = A.ref15(j0)
                flagged = q >= 0 and (A.c15[q] - A.o15[q]) * side < 0
                out["a_flag"] = bool(flagged)
                if flagged:
                    ra, ka, why = late_entry(A, tr, hs)
                    out[f"a_{cost}"] = ra
                    if cost == "1x":
                        out["a_k"], out["a_why"] = ka, why
                else:
                    out[f"a_{cost}"] = out[f"base_{cost}"]
                # B
                mb = dataclasses.replace(m, inval_exit=True)
                fires = inval_minutes(A, tr)
                bb = sim(A, tr, j0, stop, mb, hs, an={"inval": Fire(j for _, j in fires)})
                out[f"b_{cost}"] = bb["r"] if bb else np.nan
                if cost == "1x":
                    out["b_fired"] = bool(bb and bb["exit_reason"] == "m15_invalidation")
                    out["b_k"] = next((k for k, j in fires if bb and j == bb["j_exit"]), None) if out["b_fired"] else None
            if ctrl is not None:
                if out["a_flag"]:
                    ka = int(rng_a.choice(ctrl["a_ks"], p=ctrl["a_p"]))
                    out["ca_1x"] = late_entry(A, tr, A.hs, forced_k=ka)[0]
                else:
                    out["ca_1x"] = out["base_1x"]
                if rng_b.random() < ctrl["b_share"] and len(ctrl["b_ks"]):
                    kb = int(rng_b.choice(ctrl["b_ks"], p=ctrl["b_p"]))
                    jm = m15_minute(A, tr, kb)
                    cb = sim(A, tr, j0, stop, dataclasses.replace(m, inval_exit=True), A.hs,
                             an={"inval": Fire([jm] if jm >= 0 else [])})
                    out["cb_1x"] = cb["r"] if cb else np.nan
                else:
                    out["cb_1x"] = out["base_1x"]
            rows.append(out)
    return pd.DataFrame(rows)


def paired(t: pd.DataFrame, d: np.ndarray, period: str, draws: int = DRAWS, seed: int = SEED_BOOT) -> dict:
    """Mean of d per trade with a circular 5-weekday block bootstrap over the period's weekdays."""
    wd = J._weekday_index(period)
    day = pd.to_datetime(t["day"].astype(str)).to_numpy("datetime64[D]")
    pos = np.searchsorted(wd.to_numpy("datetime64[D]"), day)
    pos = np.clip(pos, 0, len(wd) - 1)
    S, N = np.zeros(len(wd)), np.zeros(len(wd))
    np.add.at(S, pos, d)
    np.add.at(N, pos, 1)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(wd) / 5))
    starts = rng.integers(0, len(wd), size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(5)[None, None, :]).reshape(draws, -1)[:, :len(wd)] % len(wd)
    s, n = S[idx].sum(1), N[idx].sum(1)
    m = s[n > 0] / n[n > 0]
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(d.mean()), "lo": float(lo), "hi": float(hi)}


def judge(t: pd.DataFrame, rule: str, period: str) -> dict:
    split = J.split_of(period)
    d = (t[f"{rule}_1x"] - t["base_1x"]).to_numpy(float)
    d2 = (t[f"{rule}_2x"] - t["base_2x"]).to_numpy(float)
    dc = (t[f"{rule}_1x"] - t[f"c{rule}_1x"]).to_numpy(float)
    first = (pd.to_datetime(t.ts) < split).to_numpy()
    main, ctrl = paired(t, d, period), paired(t, dc, period, seed=SEED_BOOT + 1)
    halves = (float(d[first].mean()) if first.any() else np.nan, float(d[~first].mean()) if (~first).any() else np.nan)
    changed = int((np.abs(d) > 1e-9).sum())
    gates = {"changed >= 100": changed >= 100, "95% range above 0": main["lo"] > 0,
             "both halves > 0": all(np.isfinite(h) and h > 0 for h in halves), "2x costs > 0": float(np.mean(d2)) > 0,
             "beats control": ctrl["lo"] > 0}
    return {"check": rule, "n": len(t), "changed": changed, "base": float(t["base_1x"].mean()), "rule": float(t[f"{rule}_1x"].mean()),
            "d": main, "halves": halves, "d_2x": float(np.mean(d2)), "control": float(t[f"c{rule}_1x"].mean()), "vs_control": ctrl,
            "gates": gates, "pass": all(gates.values())}


def fmt(j: dict, name: str) -> str:
    d, c = j["d"], j["vs_control"]
    return (f"| {name} | {j['changed']:,} of {j['n']:,} | {j['base']:+.3f} | {j['rule']:+.3f} | {d['mean']:+.3f} ({d['lo']:+.3f} to {d['hi']:+.3f}) | "
            f"{j['halves'][0]:+.3f} / {j['halves'][1]:+.3f} | {j['d_2x']:+.3f} | {j['control']:+.3f}: {c['mean']:+.3f} ({c['lo']:+.3f} to {c['hi']:+.3f}) | "
            + ("**yes**" if j["pass"] else "**no** (" + ", ".join(k for k, v in j["gates"].items() if not v) + ")") + " |")


def run(period: str, src: Path, hist: Path, out: Path, cfg=None) -> dict:
    if cfg is None:
        from .config import load_config
        cfg = load_config("config.yaml")
    todo = list(CHECKS)
    if period == "vault":
        p = Path("data/year_test/m15_timing_seen/summary.json")
        seen = json.loads(p.read_text()) if p.exists() else {}
        todo = [c for c in CHECKS if seen.get(c, {}).get("pass")]
        if not todo:
            raise SystemExit("registered: the vault is judged only for a check that passed on seen (no seen run, or none passed)")
    t = W.load(src, "trades_seen_" if period == "seen" else "trades_old_")
    t = t[t.tf.astype(str).isin(list(LOWTF))].reset_index(drop=True)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True)
    t["kid"] = np.arange(len(t))
    intended = len(t)
    m1s = {}
    for sym in sorted(t.sym.unique()):
        f = hist / f"{sym}.pkl"
        if f.exists():
            m1s[sym] = pd.read_pickle(f)[0]
        else:
            print(f"  no history for {sym}", flush=True)
    # pass 1: the rules (their outcome distributions set the controls); pass 2 adds the controls with fixed seeds
    parts = []
    for sym, m1 in m1s.items():
        parts.append(replay_symbol(cfg, t[t.sym == sym], m1, None, None, None))
        print(f"  {sym}: rules replayed", flush=True)
    a = t.merge(pd.concat(parts, ignore_index=True), on="kid", how="left")
    ok = a["ok"].fillna(False).astype(bool) & np.isfinite(a["base_1x"].astype(float))
    match = ok & (np.abs(a["base_1x"].astype(float) - a["r"].astype(float)) < MATCH_TOL)
    share = float(match.sum() / max(1, intended))
    out.mkdir(parents=True, exist_ok=True)
    head = [f"# M15 timing: late entry on the M15 turn, early exit on M15 invalidation ({period})", "",
            "Registered Oct 28 2026 before running (research/m15_timing/PREREGISTRATION_2026-10-28.md); both ideas came from the "
            "reviewers' post-mortems of losing trades. Each trade replayed by the playbook's own engine (research.simulate_live, "
            "real bid/ask spread per minute, the cell's own exit profile).", "",
            f"Cohort: {intended:,} trades on 3m / 5m. **Engine check:** the plain replay reproduces the recorded R on {match.sum():,} "
            f"({share:.1%}; required {MATCH_MIN:.0%})."]
    if share < MATCH_MIN:
        md = head + ["", "**The replay does not match the recorded trades closely enough, so nothing is judged.** "
                     "Likely cause: the exit settings in config.yaml changed since ./fx.sh pbtest wrote these trades."]
        (out / "report.md").write_text("\n".join(md) + "\n")
        (out / "summary.json").write_text(json.dumps({"engine_match": share}, indent=1))
        return {"engine_match": share}
    fa = a[a.a_flag.fillna(False).astype(bool)]
    ks = fa["a_k"].fillna(0).astype(int).to_numpy()
    a_ks, a_cnt = np.unique(ks, return_counts=True)
    fb = a[a.b_fired.fillna(False).astype(bool)]
    b_ks, b_cnt = np.unique(fb["b_k"].dropna().astype(int).to_numpy(), return_counts=True)
    ctrl = {"a_ks": a_ks if len(a_ks) else np.array([0]), "a_p": (a_cnt / a_cnt.sum()) if len(a_ks) else np.array([1.0]),
            "b_share": float(len(fb) / max(1, ok.sum())), "b_ks": b_ks, "b_p": (b_cnt / b_cnt.sum()) if len(b_ks) else b_cnt}
    parts = []
    rng_a, rng_b = np.random.default_rng(SEED_A), np.random.default_rng(SEED_B)
    for sym, m1 in m1s.items():
        parts.append(replay_symbol(cfg, t[t.sym == sym], m1, rng_a, rng_b, ctrl)[["kid", "ca_1x", "cb_1x"]])
        print(f"  {sym}: controls replayed", flush=True)
    a = a.merge(pd.concat(parts, ignore_index=True), on="kid", how="left")
    v = a[match].reset_index(drop=True)                     # judged on the trades the engine reproduces
    res = {}
    for c, rule in (("m15_turn_entry", "a"), ("m15_inval_exit", "b")):
        if c in todo:
            res[c] = judge(v, rule, period)
    a.to_csv(out / "trades_replayed.csv.gz", index=False)
    why = fa["a_why"].value_counts().to_dict()
    md = head + ["", "Paired per trade: d = R(rule) − R(as recorded). Gates: ≥ 100 trades changed, 95% range of mean d above 0 (circular "
                 f"5-weekday blocks), both halves > 0 (split {J.split_of(period).date()}), > 0 at 2× costs, and the 95% range of "
                 "(rule − control) above 0.", "",
                 "| check | trades changed | avg R as recorded | avg R with rule | mean d (95% range) | halves | d at 2× costs | "
                 "control avg R: rule − control (95% range) | pass |", "|---|---|---|---|---|---|---|---|---|"]
    names = {"m15_turn_entry": "A m15_turn_entry", "m15_inval_exit": "B m15_inval_exit"}
    md += [fmt(res[c], names[c]) for c in res]
    if "m15_turn_entry" in res:
        md += ["", f"A applied to {len(fa):,} trades (last M15 candle closed against the trade): "
               + ", ".join(f"{k} {n:,}" for k, n in sorted(why.items(), key=lambda x: -x[1]))
               + (f"; entered on M15 candle " + ", ".join(f"{k}: {n:,}" for k, n in zip(a_ks, a_cnt) if k) if len(a_ks) else "") + "."]
    if "m15_inval_exit" in res:
        md += [f"B fired on {len(fb):,} trades ({ctrl['b_share']:.1%})."]
    for c in res:
        verdict = (("passes on seen → one judgement on 2016–2020: ./fx.sh m15timing vault" if period == "seen" else
                    "CONFIRMED on 2016–2020 → shadow tag; any trading change is for the Nov 5 review")
                   if res[c]["pass"] else ("does not pass → vault untouched, closed" if period == "seen" else "NOT CONFIRMED → closed"))
        md.append(f"\n**{names[c]} {verdict}.**")
    md += ["", "## By cell (descriptive; it can't rescue a failed check)", "",
           "| cell | trades | avg R recorded | A avg R | B avg R |", "|---|---|---|---|---|"]
    for cell, g in v.groupby("cell"):
        md.append(f"| {cell} | {len(g)} | {g.base_1x.mean():+.3f} | {g.a_1x.mean():+.3f} | {g.b_1x.mean():+.3f} |")
    md += ["", "A rule that passes but leaves the kept trades below zero still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "engine_match": share}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="M15 timing: late entry / early exit (registered Oct 28 2026)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    a = ap.parse_args(argv)
    seen = a.period == "seen"
    src = Path("data/year_test/playbook_test" if seen else "data/year_test/mtf_vault_trades")
    hist = Path("data/history_x/seen_2021_2026" if seen else "data/history_x/old_2016_2020")
    out = Path(f"data/year_test/m15_timing_{a.period}")
    run(a.period, src, hist, out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
