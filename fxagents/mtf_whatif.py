"""What-if: was the higher timeframe moving against the trade at entry? (Sam, Oct 26 2026)

Sam's observation from watching the bot: a short taken on 3m / 5m while the 15m candle is still rising (the overall
bias bearish, the 15m pulling up) tends to lose, because the 15m keeps going the other way for a while; the same for
longs. This asks the playbook's own 16,456 trades (2021 → Sep 2026, ./fx.sh pbtest, real spreads) whether that is
true, with checks FIXED BEFORE THIS RAN (Oct 26 2026) — nothing here was tuned on the result:

  m15_live    the 15m candle the entry happens in (the one containing the minute before entry; at a 15m boundary,
              the one that just closed) has moved against the trade from its open to the entry price.
  m15_closed  the last COMPLETED 15m candle closed against the trade (red for a long, green for a short).
  m15_trend   the 15m EMA(20) of completed candles is sloping against the trade (now vs 3 candles earlier).
  h1_live     the 1H candle the entry happens in has moved against the trade from its open to the entry price.

Each check is judged like the liquidity checks: it passes when the trades it flags do worse than the ones it keeps —
day-block 95% range of (kept − flagged) above 0, positive in both halves, and better than skipping the same number of
trades at random (p < 0.05). Four checks at once → about one in five chance that one passes by luck, so a pass earns a
paper filter on the scorecard, then the untouched 2016–2020 data once — not a change to the practice account.

The primary test is Sam's case, entries on 3m and 5m. 15m+ entries are shown for comparison only.

    python -m fxagents.mtf_whatif   → data/year_test/mtf_whatif/report.md

CONFIRMATION (registered Oct 26 2026, after m15_live — and only m15_live — passed on 2021 → Sep 2026): the same eleven
3m/5m playbook cells, unchanged, run once on the untouched 2016–2020 data (./fx.sh mtfvault), and m15_live judged on
those trades with exactly the same pass rule. Only m15_live counts there; the other three are printed for information.
macd_cross 5m NDQ's own 2016–2020 trades were already looked at (Oct 2026, its own test), so the result is also shown
without that cell.

    python -m fxagents.mtf_whatif --src data/year_test/mtf_vault_trades --pattern trades_old_ \
        --hist data/history_x/old_2016_2020 --confirm --out data/year_test/mtf_whatif_2016_2020
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .liquidity import judge

CHECKS = ("m15_live", "m15_closed", "m15_trend", "h1_live")
LOW_TF = ("3m", "5m", "3min", "5min", "1m", "1min")
EMA_N, SLOPE_BARS = 20, 3
MIN = pd.Timedelta("1min")


def bars(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    return m1[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def annotate(t: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """Flags for one instrument's trades. t.ts = the entry (the signal candle's close, filled at that price)."""
    b15, b60 = bars(m1, "15min"), bars(m1, "1h")
    ema = b15.close.ewm(span=EMA_N, adjust=False).mean()
    close1 = m1.close
    ts = pd.DatetimeIndex(t.ts)
    last_min = ts - MIN
    px = close1.reindex(last_min).to_numpy()                          # the entry price: close of the minute before ts
    side = t.side.to_numpy()

    def live(b, rule):
        o = b.open.reindex(last_min.floor(rule)).to_numpy()
        return side * (px - o) < 0, np.isfinite(o)

    a15, ok15 = live(b15, "15min")
    a60, ok60 = live(b60, "1h")
    done = ts.floor("15min") - pd.Timedelta("15min")                  # last 15m candle complete at ts
    c, o = b15.close.reindex(done).to_numpy(), b15.open.reindex(done).to_numpy()
    closed = side * (c - o) < 0
    e_now = ema.reindex(done).to_numpy()
    e_old = ema.reindex(done - SLOPE_BARS * pd.Timedelta("15min")).to_numpy()
    trend = side * (e_now - e_old) < 0
    good = np.isfinite(px) & ok15 & ok60 & np.isfinite(c) & np.isfinite(o) & np.isfinite(e_now) & np.isfinite(e_old)
    out = t.copy()
    out["m15_live"], out["m15_closed"], out["m15_trend"], out["h1_live"] = a15, closed, trend, a60
    out["ok"] = good
    return out


def live_m15_against(m1: pd.DataFrame, ts, side: int, price: float) -> bool | None:
    """The m15_live check for ONE entry from the live 1-minute store (Oct 26 2026) — shadow tag only. Same rule as
    annotate(): the 15m candle (NY clock, left-labelled) containing the minute before `ts` has moved against the
    trade from its open to the entry price. None when the minute bars or the price are missing."""
    try:
        ts = pd.Timestamp(ts)
        last = ts - MIN
        start = last.floor("15min")
        if m1 is None or not len(m1) or not np.isfinite(float(price)) or last not in m1.index:
            return None
        o = float(m1.loc[(m1.index >= start) & (m1.index <= last), "open"].iloc[0])
        return bool(side * (float(price) - o) < 0)
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def load(src: Path, pattern: str = "trades_seen_") -> pd.DataFrame:
    files = sorted(src.glob(f"{pattern}*.csv.gz"))
    if not files:
        raise SystemExit(f"no {pattern}*.csv.gz in {src} — run ./fx.sh pbtest (or ./fx.sh mtfvault) first")
    t = pd.concat([pd.read_csv(f).assign(cell=f.name[len(pattern):-7]) for f in files], ignore_index=True)
    t["ts"] = pd.to_datetime(t["ts"], utc=True).dt.tz_convert("America/New_York")
    t["day"] = t["day"].astype(str)
    t["tf"] = t["tf"].astype(str)
    return t


def run(src: Path, hist: Path, out: Path, pattern: str = "trades_seen_", confirm: bool = False) -> dict:
    t = load(src, pattern)
    if confirm:
        return confirm_run(t, hist, out)
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym} — skipped {len(g)} trades", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(annotate(g.reset_index(drop=True), m1))
        print(f"  {sym}: {len(g)} trades", flush=True)
    a = pd.concat(parts, ignore_index=True)
    dropped = int((~a.ok).sum())
    a = a[a.ok].reset_index(drop=True)
    out.mkdir(parents=True, exist_ok=True)
    a.drop(columns=["ok"]).to_csv(out / "trades_flagged.csv.gz", index=False)
    low = a[a.tf.isin(LOW_TF)]
    high = a[~a.tf.isin(LOW_TF)]
    res = {"low_tf": {k: judge(low, k) for k in CHECKS}, "15m_plus": {k: judge(high, k) for k in CHECKS}}
    md = ["# What-if: was the higher timeframe moving against the trade at entry? — playbook trades, 2021 → Sep 2026", "",
          "Checks fixed before this ran (see fxagents/mtf_whatif.py): **m15_live** the 15m candle the entry is in had "
          "moved against the trade from its open; **m15_closed** the last completed 15m candle closed against it; "
          f"**m15_trend** the 15m EMA({EMA_N}) slopes against it (now vs {SLOPE_BARS} candles earlier); **h1_live** the "
          "1H candle the entry is in had moved against it.", "",
          "A check passes when the trades it flags do worse than the ones it keeps: day-block 95% range of kept − flagged "
          "above 0, positive in both halves, and better than skipping as many trades at random (p < 0.05). Four checks → "
          "about a 1-in-5 chance one passes by luck; a pass earns a paper filter and one test on 2016–2020.", "",
          f"{len(a):,} trades with full price data ({dropped} skipped for gaps).", "",
          f"## Sam's case: entries on 3m / 5m ({len(low):,} trades, {low.r.mean():+.3f}R average)", "",
          "| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |",
          "|---|---|---|---|---|---|---|---|"] + [_fmt(j) for j in res["low_tf"].values()]
    md += ["", "### Losers vs winners: how often was each check true?", "",
           "| check | share of losing trades flagged | share of winning trades flagged |", "|---|---|---|"]
    for k in CHECKS:
        md.append(f"| {k} | {low[low.r < 0][k].mean():.0%} | {low[low.r > 0][k].mean():.0%} |")
    md += ["", "### By cell (3m / 5m)", "", "| cell | trades | avg R | " + " | ".join(f"{k} flagged (avg R) / kept (avg R)" for k in CHECKS)
           + " |", "|---|---|---|" + "---|" * len(CHECKS)]
    for cell, g in low.groupby("cell"):
        cells = []
        for k in CHECKS:
            f_, k_ = g[g[k]], g[~g[k]]
            cells.append(f"{len(f_)} ({f_.r.mean():+.2f}) / {len(k_)} ({k_.r.mean():+.2f})")
        md.append(f"| {cell} | {len(g)} | {g.r.mean():+.3f} | " + " | ".join(cells) + " |")
    md += ["", f"## For comparison: entries on 15m and above ({len(high):,} trades, {high.r.mean():+.3f}R average)", "",
           "| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |",
           "|---|---|---|---|---|---|---|---|"] + [_fmt(j) for j in res["15m_plus"].values()]
    md += ["", "A check that passes but leaves the kept trades below zero still leaves a losing playbook."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def flag_all(t: pd.DataFrame, hist: Path) -> tuple[pd.DataFrame, int]:
    parts = []
    for sym, g in t.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym} — skipped {len(g)} trades", flush=True)
            continue
        m1, _ = pd.read_pickle(f)
        parts.append(annotate(g.reset_index(drop=True), m1))
        print(f"  {sym}: {len(g)} trades", flush=True)
    a = pd.concat(parts, ignore_index=True)
    dropped = int((~a.ok).sum())
    return a[a.ok].reset_index(drop=True), dropped


def confirm_run(t: pd.DataFrame, hist: Path, out: Path) -> dict:
    """The registered confirmation: m15_live on 3m/5m trades, judged once."""
    a, dropped = flag_all(t, hist)
    low = a[a.tf.isin(LOW_TF)]
    out.mkdir(parents=True, exist_ok=True)
    a.drop(columns=["ok"]).to_csv(out / "trades_flagged.csv.gz", index=False)
    main = judge(low, "m15_live")
    no_macd = low[~low.cell.str.startswith("macd_cross")]
    side = judge(no_macd, "m15_live")
    info = {k: judge(low, k) for k in CHECKS if k != "m15_live"}
    head = "| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |"
    md = ["# Confirmation on untouched 2016 → 2020: the 15m candle in progress against a 3m / 5m entry", "",
          "Registered Oct 26 2026 after **m15_live** passed on 2021 → Sep 2026 (+0.073R, 95% +0.021 to +0.123, both "
          "halves, random p 0.001): the same eleven 3m/5m playbook cells, unchanged, run once on 2016–2020 with the live "
          "filters and position manager and the real per-minute spread; m15_live judged with the same rule (kept − "
          "flagged day-block 95% range above 0, positive in both halves, better than skipping as many at random, p < 0.05).",
          "", f"{len(low):,} trades on 3m / 5m, {low.r.mean():+.3f}R average ({dropped} skipped for price gaps).", "",
          "## The registered check", "", head, "|---|---|---|---|---|---|---|---|", _fmt(main), "",
          f"**Verdict: {'CONFIRMED' if main.get('pass') else 'NOT CONFIRMED'}.**", "",
          "Without macd_cross 5m NDQ (its own 2016–2020 trades were looked at before):", "", head,
          "|---|---|---|---|---|---|---|---|", _fmt(side), "",
          "## For information only (not registered, can't confirm anything)", "", head, "|---|---|---|---|---|---|---|---|"]
    md += [_fmt(j) for j in info.values()]
    md += ["", "## By cell", "", "| cell | trades | avg R | m15_live flagged (avg R) / kept (avg R) |", "|---|---|---|---|"]
    for cell, g in low.groupby("cell"):
        f_, k_ = g[g.m15_live], g[~g.m15_live]
        md.append(f"| {cell} | {len(g)} | {g.r.mean():+.3f} | {len(f_)} ({f_.r.mean():+.2f}) / {len(k_)} ({k_.r.mean():+.2f}) |")
    md += ["", "A confirmed check that leaves the kept trades below zero still leaves a losing playbook: it earns a "
           "shadow tag on the practice account and the 'wait for the 15m to turn' test, not a live change."]
    (out / "report.md").write_text("\n".join(md) + "\n")
    res = {"m15_live": main, "m15_live_without_macd": side, "info": info}
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def _fmt(j: dict) -> str:
    if "diff" not in j:
        return (f"| {j['check']} | {j['removed']} of {j['n']} | {j['removed_avg']} | {j['kept_avg']} | — | — | — | "
                f"**no** ({j['why']}) |")
    h = " / ".join(f"{x:+.3f}" if x is not None else "—" for x in j["halves"])
    return (f"| {j['check']} | {j['removed']} of {j['n']} | {j['removed_avg']:+.3f} | {j['kept_avg']:+.3f} | {j['diff']:+.3f} "
            f"({j['diff_ci'][0]:+.3f} to {j['diff_ci'][1]:+.3f}) | {h} | {j['random_p']:.3f} | "
            f"{'**yes**' if j['pass'] else '**no**'} |")


def main(argv=None):
    ap = argparse.ArgumentParser(description="What-if: higher timeframe against the trade at entry")
    ap.add_argument("--src", type=Path, default=Path("data/year_test/playbook_test"))
    ap.add_argument("--hist", type=Path, default=Path("data/history_x/seen_2021_2026"))
    ap.add_argument("--out", type=Path, default=Path("data/year_test/mtf_whatif"))
    ap.add_argument("--pattern", default="trades_seen_")
    ap.add_argument("--confirm", action="store_true", help="the registered 2016–2020 confirmation (m15_live only)")
    a = ap.parse_args(argv)
    run(a.src, a.hist, a.out, a.pattern, a.confirm)
    print((a.out / "report.md").read_text())


if __name__ == "__main__":
    main()
