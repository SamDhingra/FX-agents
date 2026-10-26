"""Round 3, Gemini's four what-if checks (research/round3/gemini/, code UNCHANGED), on the playbook's 3m/5m entries,
judged with the stricter judge (fxagents/whatif_judge.py). Registered Oct 26 2026 before any of them ran.

Two things are done OUTSIDE their code, so it can be judged fairly:
  * the trade's timeframe is passed as "3m"/"5m" (the brief's labels; the trade files say "3min"/"5min" — passed
    as is, their stop check would read 3m trades as 5m and never run its 15m-noise half);
  * availability: their functions return False (= keep) when data is short. Here a trade is UNAVAILABLE — dropped
    for that check and counted against its ≥ 90% coverage — when the same data conditions their code bails out on
    hold (fewer than 240 / 180 one-minute rows in the look-back, too few completed 15m / 5m / entry-TF candles, or
    a non-positive ATR). A missing structure (fewer than two 5m swings) is a real "no", not unavailable.

Family and vault (registered): m15_impulse_leg and ltf_swing_structure_against are in the "against the higher
timeframe" family, whose 2016–2020 test was spent on m15_live → seen only, a pass earns a shadow tag.
chasing_exhausted_leg is a new family: if it passes on seen, it is judged once on the 2016–2020 trades.
stop_inside_15m_noise is a cost / stop-size check: seen only here; its two halves (spread > 8% of the stop; stop
< 0.5 × ATR15) are also shown separately, for information.

    python -m fxagents.round3_gemini [--period seen|vault]  → data/year_test/round3_gemini_<period>/report.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import mtf_whatif as W
from . import whatif_judge as J

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "research" / "round3" / "gemini"
CHECKS = ("m15_impulse_leg", "ltf_swing_structure_against", "stop_inside_15m_noise", "chasing_exhausted_leg")
VAULT_OK = ("chasing_exhausted_leg",)
# Registered Oct 26 2026 after the seen run, BEFORE any 2016–2020 look: the stop check passed only through its spread
# half (spread > 8% of the stop at entry; the noise half failed the stratified test). That half alone — Gemini's exact
# formula, look-ahead free — is judged once on the 2016–2020 trades. It is the rule behind the live bot's existing
# (log-only) cost cap, so its confirmation decides whether that cap is switched on.
VAULT_SPREAD = "stop_spread_part"
LOW = {"3m": "3m", "3min": "3m", "5m": "5m", "5min": "5m"}
TFMIN = {"3m": 3, "5m": 5}
DAY = pd.Timedelta(days=1)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"gemini_{name}", DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.flag


def _bars(df: pd.DataFrame, minutes: int, ts: pd.Timestamp) -> pd.DataFrame:
    b = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return b.loc[b.index + pd.Timedelta(minutes=minutes) <= ts]


def _atr14(b: pd.DataFrame) -> float:
    h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    pc = np.roll(c, 1)
    pc[0] = b["open"].iloc[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(np.mean(tr[-14:]))


def available(name: str, trade: dict, m1: pd.DataFrame) -> tuple[bool, dict]:
    """Do the data conditions their code needs hold? Also returns the stop check's two halves (information only)."""
    ts = trade["ts"]
    days = 3 if name == "ltf_swing_structure_against" else 5
    df = m1.loc[(m1.index >= ts - days * DAY) & (m1.index < ts)]
    if name == "ltf_swing_structure_against":
        return len(df) >= 180 and len(_bars(df, 5, ts)) >= 36, {}
    if len(df) < 240:
        return False, {}
    b15 = _bars(df, 15, ts)
    need = 16 if name == "m15_impulse_leg" else 15
    if len(b15) < need:
        return False, {}
    a15 = _atr14(b15)
    if not np.isfinite(a15) or a15 <= 0:
        return False, {}
    if name == "chasing_exhausted_leg":
        return len(df.loc[df.index >= ts - pd.Timedelta(minutes=60)]) >= 15, {}
    if name == "stop_inside_15m_noise":
        if float(trade.get("risk_atr") or 0) <= 0:
            return False, {}
        btf = _bars(df, TFMIN[trade["tf"]], ts)
        if len(btf) < 15:
            return False, {}
        atf = _atr14(btf)
        if not np.isfinite(atf) or atf <= 0:
            return False, {}
        stop = float(trade["risk_atr"]) * atf
        return True, {"spread_part": float(df["spread"].iloc[-1]) / stop > 0.08, "noise_part": stop < 0.50 * a15}
    return True, {}


def flag_all(g: pd.DataFrame, m1: pd.DataFrame, names) -> pd.DataFrame:
    fns = {n: _load(n) for n in names}
    idx = m1.index
    res = {n: np.full(len(g), np.nan) for n in names}
    parts = {"spread_part": np.full(len(g), np.nan), "noise_part": np.full(len(g), np.nan)}
    for i, r in enumerate(g.itertuples(index=False)):
        ts = pd.Timestamp(r.ts)
        a, b = idx.searchsorted(ts - 5 * DAY), idx.searchsorted(ts)
        sl = m1.iloc[a:b]                          # their code reads at most 5 days before ts
        trade = {"ts": ts, "side": int(r.side), "tf": LOW[str(r.tf)], "risk_atr": float(r.risk_atr)}
        for n, fn in fns.items():
            ok, extra = available(n, trade, sl)
            if not ok:
                continue
            res[n][i] = float(bool(fn(dict(trade), sl)))
            for k, v in extra.items():
                parts[k][i] = float(v)
    out = g.copy()
    for n in names:
        out[n] = res[n]
    if "stop_inside_15m_noise" in names:
        out["stop_spread_part"], out["stop_noise_part"] = parts["spread_part"], parts["noise_part"]
    return out


def run(period: str, src: Path, hist: Path, out: Path) -> dict:
    pattern = "trades_seen_" if period == "seen" else "trades_old_"
    t = W.load(src, pattern)
    t = t[t.tf.isin(list(LOW))].reset_index(drop=True)
    a0, b0, _ = J.PERIODS[period]
    t = t[(t.ts >= a0) & (t.ts < b0)].reset_index(drop=True)
    intended = len(t)
    names = list(CHECKS)
    if period == "vault":                      # registered: only chasing_exhausted_leg, and only if it passed on seen
        p = Path("data/year_test/round3_gemini_seen/summary.json")
        seen = json.loads(p.read_text()) if p.exists() else {}
        names = [n for n in VAULT_OK if seen.get(n, {}).get("pass")]
        if seen.get("info", {}).get(VAULT_SPREAD, {}).get("pass"):
            names.append("stop_inside_15m_noise")              # computed for its spread half (the registered check)
        if not names:
            raise SystemExit("nothing registered for the vault (no seen run, or nothing passed)")
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym}: {len(g)} trades unavailable", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(flag_all(g.reset_index(drop=True), m1, names))
        print(f"  {sym}: {len(g)} trades", flush=True)
    a = pd.concat(parts, ignore_index=True)
    res = {}
    for k in names:
        if period == "vault" and k == "stop_inside_15m_noise":
            k = VAULT_SPREAD
            a[k] = a["stop_spread_part"]
        ok = np.isfinite(a[k].to_numpy(float))
        res[k] = J.judge(a[ok].assign(**{k: a.loc[ok, k].astype(bool)}), k, period, intended)
    info = {}
    if "stop_inside_15m_noise" in names and period == "seen":
        for k in ("stop_spread_part", "stop_noise_part"):
            ok = np.isfinite(a[k].to_numpy(float))
            info[k] = J.judge(a[ok].assign(**{k: a.loc[ok, k].astype(bool)}), k, period, intended)
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades_flagged.csv.gz", index=False)
    md = [f"# Round 3, Gemini's checks on the playbook's 3m / 5m entries ({period}, stricter judge)", "",
          "Registered before running (research/round3/gemini/). **m15_impulse_leg** two completed 15m candles stepping "
          "against the trade or one wide counter-bar; **ltf_swing_structure_against** 3 hours of 5m swings stepping against "
          "it with price on the wrong side of the 1-hour mean; **stop_inside_15m_noise** spread > 8% of the stop OR stop "
          "< 0.5 × ATR15; **chasing_exhausted_leg** entering at the extreme of an unretraced ≥ 2 × ATR15 one-hour move in "
          "the trade's own direction. Gemini's code unchanged; timeframe labels and unavailable data handled outside it.",
          "", f"Stricter judge: calendar halves split {J.split_of(period).date()}, circular 5-weekday blocks, random "
          "skipping within cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage.", "",
          f"Cohort: {intended:,} trades on 3m / 5m, {t.r.mean():+.3f}R average.", "", J.HEAD]
    md += [J.fmt(res[k]) for k in res]
    if period == "vault":
        md += ["", "Registered for 2016–2020: **stop_spread_part** (spread > 8% of the stop at entry) — the half of "
               "stop_inside_15m_noise that passed on seen. **Verdict: "
               + ("CONFIRMED" if res.get(VAULT_SPREAD, {}).get("pass") else "NOT CONFIRMED") + ".**"]
    if info:
        md += ["", "### stop_inside_15m_noise, its two halves separately (information only)", "", J.HEAD]
        md += [J.fmt(j) for j in info.values()]
    shown = [VAULT_SPREAD if (period == "vault" and n == "stop_inside_15m_noise") else n for n in names]
    md += ["", "## By cell (descriptive)", "",
           "| cell | trades | avg R | " + " | ".join(f"{k} flagged (avg R) / kept (avg R)" for k in shown) + " |",
           "|---|---|---|" + "---|" * len(shown)]
    for cell, g in a.groupby("cell"):
        cells = []
        for k in shown:
            v = g[np.isfinite(g[k].to_numpy(float))]
            fl, kp = v[v[k] == 1], v[v[k] == 0]
            cells.append(f"{len(fl)} ({fl.r.mean():+.2f}) / {len(kp)} ({kp.r.mean():+.2f})" if len(v) else "—")
        md.append(f"| {cell} | {len(g)} | {g.r.mean():+.3f} | " + " | ".join(cells) + " |")
    md += ["", "Families: m15_impulse_leg and ltf_swing_structure_against belong to the 'against the higher timeframe' "
           "family (its 2016–2020 test was m15_live's) → a pass earns a shadow tag only. chasing_exhausted_leg, if it "
           "passes here, is judged once on 2016–2020 (./fx.sh round3g vault). Of stop_inside_15m_noise only its spread half "
           "(spread > 8% of the stop) is judged on 2016–2020, registered after it alone passed on seen."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({**res, "info": info}, indent=1, default=str))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Round 3: Gemini's what-if checks (stricter judge)")
    ap.add_argument("--period", choices=("seen", "vault"), default="seen")
    a = ap.parse_args(argv)
    seen = a.period == "seen"
    src = Path("data/year_test/playbook_test" if seen else "data/year_test/mtf_vault_trades")
    hist = Path("data/history_x/seen_2021_2026" if seen else "data/history_x/old_2016_2020")
    out = Path(f"data/year_test/round3_gemini_{a.period}")
    run(a.period, src, hist, out)
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
