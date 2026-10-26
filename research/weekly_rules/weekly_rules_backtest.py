#!/usr/bin/env python3
"""Your weekly and daily rule books, exactly as written, on OANDA daily bid/ask data.

WEEKLY (decided on COMPLETED weeks, i.e. at Friday 17:00 New York; executed at the next daily open, buy at the ask, sell at the bid):
  WK   LONG  when the weekly RSI turns above 60 AND the weekly close is above the weekly EMA21 (both true for the first time, or again after
             either condition has failed). Stay in, no stop, until a weekly close is BELOW the weekly EMA18.
       SHORT when the weekly RSI turns below 40 AND the weekly close is below the weekly EMA21. Stay in until a weekly close is ABOVE the EMA18.
  WK0  the same without the RSI condition (EMA21 / EMA18 only). Shows what the RSI adds.
DAILY (the weekly RSI is the last completed week's):
  DY1  weekly RSI > 60 and the daily RSI crosses UP through 58 -> buy.   weekly RSI < 40 and the daily RSI crosses DOWN through 42 -> sell.
       No stop; exit when a daily close is below the daily EMA18 (long) / above it (short).
  DY2  DY1 plus the daily close must be on the right side of the daily EMA21 at entry
  DY3  DY1 but the sell trigger is the daily RSI crossing down through 40 (you wrote "40"; the mirror of 58 is 42)
A new trade can only start from a fresh signal. Results are % per trade after the real spread (no swap), the worst dip inside each trade,
time in the market, build versus holdout, the markets we tuned other rules on versus ones we never looked at, by year, and a PLACEBO test:
the RSI series slid to a random other point in time. If the real result is not clearly better than the placebo, the RSI adds nothing.

Run in a throwaway container so the live bot is untouched:
  docker compose run --rm --no-deps -T -e FX_MODE=sim fxagents python - --years 5 --placebo 200 --list WK,DY1 < ~/weekly_rules_backtest.py > ~/fx-results/rules_1.md
Options: --years N  --markets A,B,C  --insample A,B,C  --holdout-months 18  --placebo N  --list WK,DY1  --selftest
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.getcwd())
from fxagents.indicators import ema, rsi      # noqa: E402

NY = "America/New_York"
INST = {"XAUUSD": "XAU_USD", "NDQ": "NAS100_USD", "US30": "US30_USD", "EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "USDJPY": "USD_JPY",
        "AUDUSD": "AUD_USD", "USDCAD": "USD_CAD", "XAGUSD": "XAG_USD", "SPX500": "SPX500_USD", "DE30": "DE30_EUR", "UK100": "UK100_GBP",
        "WTI": "WTICO_USD"}
ALL = "XAUUSD,NDQ,US30,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,XAGUSD,SPX500,DE30,UK100,WTI"
S1 = ("W1", "W2", "W3")
S2 = ("X1", "X2", "X3", "X4")


# ───────────────────────────── data ─────────────────────────────
def fetch_daily(inst, start_utc):
    token, host = os.environ.get("OANDA_API_TOKEN", ""), "https://api-fxpractice.oanda.com"
    rows, cur = [], start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    while True:
        q = urllib.parse.urlencode({"granularity": "D", "price": "BA", "count": 5000, "from": cur, "dailyAlignment": 17,
                                    "alignmentTimezone": "America/New_York"})
        req = urllib.request.Request(f"{host}/v3/instruments/{inst}/candles?{q}", headers={"Authorization": f"Bearer {token}"})
        for attempt in range(6):
            try:
                cs = json.load(urllib.request.urlopen(req, timeout=90)).get("candles", [])
                break
            except Exception as ex:                                      # noqa: BLE001
                if attempt == 5:
                    raise
                print(f"  retry {attempt + 1} after {type(ex).__name__}: {ex}", file=sys.stderr, flush=True)
                time.sleep(3 * (attempt + 1))
        for c in cs:
            if c.get("complete"):
                b, a = c["bid"], c["ask"]
                rows.append((c["time"], *(float(b[k]) for k in "ohlc"), *(float(a[k]) for k in "ohlc")))
        if not cs or cs[-1]["time"] == cur or not cs[-1].get("complete", True):
            break
        cur = cs[-1]["time"]
    df = pd.DataFrame(rows, columns=["t", "bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"])
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("t"), utc=True)).tz_convert(NY)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for k in "ohlc":
        df["m" + k] = (df["b" + k] + df["a" + k]) / 2
    return df


def weekly_from_daily(d):
    """Trading weeks (Sunday 17:00 -> Friday 17:00 New York) from daily candles. Returns (weekly OHLC, avail) where avail[j] is the time
    (UTC ns) at which week j is COMPLETE: the end of its last daily candle."""
    ix = d.index
    dow = np.asarray(ix.dayofweek)
    lab = ix.normalize().tz_localize(None) - pd.to_timedelta((dow + 1) % 7, unit="D")       # the Sunday that starts the trading week
    g = d.groupby(lab)
    w = pd.DataFrame({"open": g["mo"].first(), "high": g["mh"].max(), "low": g["ml"].min(), "close": g["mc"].last()})
    last_label = pd.Series(ix, index=ix).groupby(lab).max()
    ll = pd.DatetimeIndex(last_label.to_list())
    avail = ll.as_unit("ns").asi8 + 24 * 3600 * 10 ** 9                                       # UTC nanoseconds (unit made explicit)
    if len(avail) and ll[-1].tz_convert(NY).dayofweek != 3:                                    # the newest week has not reached Friday's session yet:
        avail[-1] = np.iinfo(np.int64).max                                                     # it is still in progress, never use it
    return w, avail



WEEKLY = ("WK", "WK0")
DAILY = ("DY1", "DY2", "DY3")


def _ret(side, entry, exit_):
    return (exit_ - entry) / entry * 100 if side > 0 else (entry - exit_) / entry * 100


def _mae(X, k_in, k_out, side, entry):
    """Worst dip inside the trade, in % of the entry price (from the daily lows / highs, real bid / ask)."""
    if side > 0:
        return max(0.0, (entry - X["bl"][k_in:k_out + 1].min()) / entry * 100)
    return max(0.0, (X["ah"][k_in:k_out + 1].max() - entry) / entry * 100)


def _close_out(X, k_out_px, side):
    return X["bo"][k_out_px] if side > 0 else X["ao"][k_out_px]


def run_wk(X, wc, rsi_w, e18, e21, widx, mode, start_k):
    n = len(X["bo"]); pos, trades, ent = 0, [], None
    prev_l = prev_s = None; last_j = -2
    for k in range(n - 1):
        j = widx[k]
        if j < 0 or not all(np.isfinite(v[j]) for v in (wc, rsi_w, e18, e21)):
            continue
        c, r, a18, a21 = wc[j], rsi_w[j], e18[j], e21[j]
        lc = (c > a21) and (r > 60 if mode == "WK" else True)
        sc = (c < a21) and (r < 40 if mode == "WK" else True)
        new_week = j != last_j
        if pos != 0 and ((pos > 0 and c < a18) or (pos < 0 and c > a18)):            # exit: a weekly close beyond the EMA18
            px = _close_out(X, k + 1, pos)
            trades.append(dict(side=pos, k_in=ent[0], k_out=k + 1, ret=_ret(pos, ent[1], px), mae=_mae(X, ent[0], k + 1, pos, ent[1]), reason="EMA18 exit"))
            pos = 0
        if pos == 0 and new_week and prev_l is not None and k >= start_k - 1:
            side = 1 if (lc and not prev_l) else -1 if (sc and not prev_s) else 0
            if side:
                ent = (k + 1, X["ao"][k + 1] if side > 0 else X["bo"][k + 1]); pos = side
        if new_week:
            prev_l, prev_s, last_j = lc, sc, j
    if pos != 0:
        px = X["bc"][n - 1] if pos > 0 else X["ac"][n - 1]
        trades.append(dict(side=pos, k_in=ent[0], k_out=n - 1, ret=_ret(pos, ent[1], px), mae=_mae(X, ent[0], n - 1, pos, ent[1]), reason="still open"))
    return trades


def run_dy(X, rsi_d, rsi_w, widx, e18, e21d, dn_level, need21, start_k):
    n = len(X["bo"]); pos, trades, ent = 0, [], None
    for k in range(max(start_k, 30), n - 1):
        if pos != 0 and ((pos > 0 and X["mc"][k] < e18[k]) or (pos < 0 and X["mc"][k] > e18[k])):
            px = _close_out(X, k + 1, pos)
            trades.append(dict(side=pos, k_in=ent[0], k_out=k + 1, ret=_ret(pos, ent[1], px), mae=_mae(X, ent[0], k + 1, pos, ent[1]), reason="EMA18 exit"))
            pos = 0
        if pos == 0:
            j = widx[k]
            rw = rsi_w[j] if j >= 0 else np.nan
            if not np.isfinite(rw) or not np.isfinite(e18[k]):
                continue
            up = rw > 60 and rsi_d[k - 1] <= 58 < rsi_d[k] and (not need21 or X["mc"][k] > e21d[k])
            dn = rw < 40 and rsi_d[k - 1] >= dn_level > rsi_d[k] and (not need21 or X["mc"][k] < e21d[k])
            if up or dn:
                pos = 1 if up else -1
                ent = (k + 1, X["ao"][k + 1] if pos > 0 else X["bo"][k + 1])
    if pos != 0:
        px = X["bc"][n - 1] if pos > 0 else X["ac"][n - 1]
        trades.append(dict(side=pos, k_in=ent[0], k_out=n - 1, ret=_ret(pos, ent[1], px), mae=_mae(X, ent[0], n - 1, pos, ent[1]), reason="still open"))
    return trades


def boot(x, reps=600):
    x = np.asarray(x, float)
    if len(x) < 5:
        return (float(x.mean()), float(x.mean())) if len(x) else (0.0, 0.0)
    rng = np.random.default_rng(1); step = max(1, int(2_000_000 // len(x)))
    m = np.concatenate([x[rng.integers(0, len(x), size=(min(step, reps - i), len(x)))].mean(axis=1) for i in range(0, reps, step)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def row(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return "0 | - | - | - | - | -"
    lo, hi = boot(x)
    gl = -x[x < 0].sum(); pf = x[x > 0].sum() / gl if gl > 0 else float("inf")
    cum = np.cumsum(x); dd = float((np.maximum.accumulate(cum) - cum).max())
    return f"{len(x)} | {(x > 0).mean() * 100:.0f}% | {x.sum():+.1f} | {x.mean():+.2f} ({lo:+.2f}..{hi:+.2f}) | {('%.2f' % pf) if pf != float('inf') else 'inf'} | {dd:.1f}"


def report(T, variants, label, args, cut, expo):
    ins = set(args.insample.split(","))
    L = [f"\n## {label}\n", "### All markets together (% per trade)\n",
         "| Variant | Trades | Win | Total % | Avg % per trade (95% interval) | PF | Deepest fall (%) |\n|---|---|---|---|---|---|---|"]
    for v in variants:
        L.append(f"| {v} | " + row(T[T.variant == v].ret) + " |")
    L.append(f"\n### Markets we tuned other rules on ({','.join(sorted(ins))}) versus markets we never looked at\n")
    L.append("| Variant | Tuned: trades | Tuned: total % | Tuned: avg | Untouched: trades | Untouched: total % | Untouched: avg (95% interval) |\n|---|---|---|---|---|---|---|")
    for v in variants:
        x = T[T.variant == v]; a_, b_ = x[x.market.isin(ins)].ret, x[~x.market.isin(ins)].ret
        lo, hi = boot(b_)
        L.append(f"| {v} | {len(a_)} | {a_.sum():+.1f} | {a_.mean() if len(a_) else 0:+.2f} | {len(b_)} | {b_.sum():+.1f} | {b_.mean() if len(b_) else 0:+.2f} ({lo:+.2f}..{hi:+.2f}) |")
    L.append(f"\n### Build period versus holdout (entries after {cut:%Y-%m-%d})\n")
    L.append("| Variant | Build trades | Build total | Build avg | Holdout trades | Holdout total | Holdout avg |\n|---|---|---|---|---|---|---|")
    for v in variants:
        x = T[T.variant == v]; bd, ho = x[x.t_in < cut].ret, x[x.t_in >= cut].ret
        L.append(f"| {v} | {len(bd)} | {bd.sum():+.1f} | {bd.mean() if len(bd) else 0:+.2f} | {len(ho)} | {ho.sum():+.1f} | {ho.mean() if len(ho) else 0:+.2f} |")
    mk = sorted(T.market.unique())
    L.append("\n### Total % by market (trades)\n")
    L.append("| Variant | " + " | ".join(mk) + " |\n|---|" + "---|" * len(mk))
    for v in variants:
        x = T[T.variant == v]
        L.append(f"| {v} | " + " | ".join(f"{x[x.market == m].ret.sum():+.1f} ({(x.market == m).sum()})" for m in mk) + " |")
    yrs = sorted(T.t_in.dt.year.unique())
    L.append("\n### Total % by year of entry\n")
    L.append("| Variant | " + " | ".join(str(y) for y in yrs) + " |\n|---|" + "---|" * len(yrs))
    for v in variants:
        x = T[T.variant == v]
        L.append(f"| {v} | " + " | ".join(f"{x[x.t_in.dt.year == y].ret.sum():+.1f}" for y in yrs) + " |")
    L.append("\n### Long trades versus short trades\n")
    L.append("| Variant | Long trades | Long total % | Long avg | Short trades | Short total % | Short avg |\n|---|---|---|---|---|---|---|")
    for v in variants:
        x = T[T.variant == v]; lg, sh = x[x.side > 0].ret, x[x.side < 0].ret
        L.append(f"| {v} | {len(lg)} | {lg.sum():+.1f} | {lg.mean() if len(lg) else 0:+.2f} | {len(sh)} | {sh.sum():+.1f} | {sh.mean() if len(sh) else 0:+.2f} |")
    L.append("\n### How long, how much time in the market, and the worst dip inside a trade\n")
    L.append("| Variant | Avg days held | Time in the market | Avg worst dip inside a trade (%) | Worst dip of any trade (%) | Trades still open |\n|---|---|---|---|---|---|")
    for v in variants:
        x = T[T.variant == v]
        L.append(f"| {v} | {x.days.mean() if len(x) else 0:.0f} | {np.mean([e for (vv, _), e in expo.items() if vv == v]) * 100:.0f}% | "
                 f"{x.mae.mean() if len(x) else 0:.1f} | {x.mae.max() if len(x) else 0:.1f} | {(x.reason == 'still open').sum()} |")
    return L



# ───────────────────────────── self-test ─────────────────────────────
def selftest():
    ok = True

    def chk(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name); ok &= bool(cond)
    n = 14; base = np.arange(n) + 100.
    X = dict(bo=base - .1, ao=base + .1, bc=base - .1, ac=base + .1, bl=base - .6, ah=base + .6, mo=base, mc=base)
    ident = np.arange(n)
    # weekly: RSI crosses above 60 while the close is above EMA21 at week 4; stays in until the close drops below EMA18 at week 9
    rsi_w = np.array([50, 50, 55, 58, 65, 66, 67, 66, 64, 62, 61, 66, 67, 68.])
    wc = np.array([10, 10, 10, 10, 12, 12, 12, 12, 12, 8, 8, 12, 12, 12.])
    e21 = np.full(n, 11.); e18 = np.full(n, 10.5)
    t = run_wk(X, wc, rsi_w, e18, e21, ident, "WK", 0)
    chk("long entered at the OPEN after the week where RSI>60 and close>EMA21 first held", t[0]["side"] == 1 and t[0]["k_in"] == 5)
    chk("held (no stop) while RSI fell back to 62 and 61, left only when the close went below the EMA18", t[0]["k_out"] == 10 and t[0]["reason"] == "EMA18 exit")
    chk("no instant re-entry while the condition stayed false; a fresh signal at week 11 re-enters", len(t) == 2 and t[1]["k_in"] == 12)
    chk("pays the spread: buys the ask, sells the bid", abs(t[0]["ret"] - ((X["bo"][10] - 0) / X["ao"][5] - 1) * 100) < 1e-9)
    # no RSI condition (WK0): enters as soon as the close is above the EMA21, even though the RSI is still only 55
    wc_b = np.array([10, 10, 12, 12, 12, 12, 12, 12, 12, 8, 8, 12, 12, 12.])
    t_ema = run_wk(X, wc_b, rsi_w, e18, e21, ident, "WK0", 0)
    t_rsi = run_wk(X, wc_b, rsi_w, e18, e21, ident, "WK", 0)
    chk("WK0 (EMA only) enters at week 2, WK waits for the RSI above 60 at week 4", t_ema[0]["k_in"] == 3 and t_rsi[0]["k_in"] == 5)
    # if the condition is already true at the start there is no trade until a fresh signal
    t_start = run_wk(X, np.full(n, 12.), np.full(n, 70.), e18, e21, ident, "WK", 0)
    chk("already in 'long' territory from the start: no entry without a fresh signal", len(t_start) == 0)
    # short side
    rsi_s = np.array([50, 50, 45, 42, 35, 34, 33, 34, 36, 38, 39, 36, 35, 34.])
    wc_s = np.array([10, 10, 10, 10, 8, 8, 8, 8, 8, 12, 12, 8, 8, 8.])
    ts = run_wk(X, wc_s, rsi_s, np.full(n, 9.5), np.full(n, 9.0 + 1), ident, "WK", 0)
    chk("short: RSI<40 and close<EMA21 -> sell at the bid, buy back when the close is above the EMA18", ts[0]["side"] == -1 and ts[0]["reason"] == "EMA18 exit")
    # worst dip inside the trade comes from the real lows
    chk("worst dip is measured from the daily low", abs(t[0]["mae"] - (X["ao"][5] - X["bl"][5:11].min()) / X["ao"][5] * 100) < 1e-9)
    # daily rule
    m = 60; b2 = np.full(m, 100.); X2 = dict(bo=b2 - .1, ao=b2 + .1, bc=b2 - .1, ac=b2 + .1, bl=b2 - .6, ah=b2 + .6, mo=b2, mc=b2.copy())
    rd = np.full(m, 50.); rd[40] = 59.; rd[39] = 56.
    e18d = np.full(m, 95.); e21d = np.full(m, 95.)
    td = run_dy(X2, rd, np.full(m, 65.), np.zeros(m, int), e18d, e21d, 42, False, 0)
    chk("daily: weekly RSI>60 and the daily RSI crossing up through 58 enters at the next open", len(td) == 1 and td[0]["side"] == 1 and td[0]["k_in"] == 41)
    chk("daily: no entry when the weekly RSI is not above 60", len(run_dy(X2, rd, np.full(m, 55.), np.zeros(m, int), e18d, e21d, 42, False, 0)) == 0)
    X3 = {k: v.copy() for k, v in X2.items()}; X3["mc"][50:] = 90.
    td2 = run_dy(X3, rd, np.full(m, 65.), np.zeros(m, int), e18d, e21d, 42, False, 0)
    chk("daily: held with no stop until a daily close fell below the EMA18, exit at the next open", td2[0]["reason"] == "EMA18 exit" and td2[0]["k_out"] == 51)
    rd_dn = np.full(m, 50.); rd_dn[40] = 41.; rd_dn[39] = 44.
    chk("daily short: weekly<40 and the daily RSI crossing down through 42 (DY1) triggers; 40 (DY3) does not at 41-from-44",
        len(run_dy(X2, rd_dn, np.full(m, 35.), np.zeros(m, int), np.full(m, 105.), np.full(m, 105.), 42, False, 0)) == 1
        and len(run_dy(X2, rd_dn, np.full(m, 35.), np.zeros(m, int), np.full(m, 105.), np.full(m, 105.), 40, False, 0)) == 0)
    chk("daily DY2: the EMA21 side is required at entry", len(run_dy(X2, rd, np.full(m, 65.), np.zeros(m, int), e18d, np.full(m, 120.), 42, True, 0)) == 0)
    # weekly completion logic carried over from the first version
    idx = pd.DatetimeIndex([pd.Timestamp(x, tz=NY) for x in ("2026-10-11 17:00", "2026-10-12 17:00", "2026-10-13 17:00", "2026-10-14 17:00",
                                                             "2026-10-15 17:00", "2026-10-18 17:00", "2026-10-19 17:00")])
    d = pd.DataFrame({"mo": np.arange(7.), "mh": np.arange(7.) + 1, "ml": np.arange(7.) - 1, "mc": np.arange(7.) + .5}, index=idx)
    w, av = weekly_from_daily(d)
    dec = (idx + pd.Timedelta("24h")).as_unit("ns").asi8
    chk("a week is used only after it is complete; the unfinished newest week never", list(np.searchsorted(av, dec, side="right") - 1) == [-1, -1, -1, -1, 0, 0, 0])
    print("SELFTEST", "OK" if ok else "FAILED")
    return ok


# ───────────────────────────── main ─────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=5)
    ap.add_argument("--markets", default=ALL)
    ap.add_argument("--insample", default="XAUUSD,NDQ,US30")
    ap.add_argument("--holdout-months", type=int, default=18)
    ap.add_argument("--placebo", type=int, default=0)
    ap.add_argument("--list", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    now = datetime.now(timezone.utc); start = now - timedelta(days=int(args.years * 365))
    rows, bh, problems, expo = [], [], [], {}
    plc = {"WK": [], "DY1": []}
    for mk in args.markets.split(","):
        try:
            print(f"fetching {mk} ...", file=sys.stderr, flush=True)
            d = fetch_daily(INST[mk], start - timedelta(days=330))              # warm-up: weekly EMA21 / RSI14 need about 30 weeks
            w, avail = weekly_from_daily(d)
            wc, rsi_w = w["close"].to_numpy(), rsi(w["close"], 14).to_numpy()
            ew18, ew21 = ema(w["close"], 18).to_numpy(), ema(w["close"], 21).to_numpy()
            dm = d["mc"]
            rsi_d, ed18, ed21 = rsi(dm, 14).to_numpy(), ema(dm, 18).to_numpy(), ema(dm, 21).to_numpy()
            dec = (d.index + pd.Timedelta("24h")).as_unit("ns").asi8
            widx = np.searchsorted(avail, dec, side="right") - 1
            X = {k: d[k].to_numpy() for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "mo", "mh", "ml", "mc")}
            start_k = int(np.searchsorted(d.index.as_unit("ns").asi8, pd.Timestamp(start).as_unit("ns").value))
            idx = d.index.tz_convert(NY); span = len(d) - start_k
            runs = {"WK": lambda rw=rsi_w: run_wk(X, wc, rw, ew18, ew21, widx, "WK", start_k),
                    "WK0": lambda: run_wk(X, wc, rsi_w, ew18, ew21, widx, "WK0", start_k),
                    "DY1": lambda rw=rsi_w, rdd=rsi_d: run_dy(X, rdd, rw, widx, ed18, ed21, 42, False, start_k),
                    "DY2": lambda: run_dy(X, rsi_d, rsi_w, widx, ed18, ed21, 42, True, start_k),
                    "DY3": lambda: run_dy(X, rsi_d, rsi_w, widx, ed18, ed21, 40, False, start_k)}
            for v, fn in runs.items():
                tr = fn()
                expo[(v, mk)] = sum(t["k_out"] - t["k_in"] for t in tr) / max(span, 1)
                for t in tr:
                    rows.append(dict(market=mk, variant=v, side=t["side"], ret=t["ret"], mae=t["mae"], t_in=idx[t["k_in"]], t_out=idx[t["k_out"]],
                                     days=t["k_out"] - t["k_in"], reason=t["reason"]))
            if args.placebo:
                rng = np.random.default_rng(7 + len(plc["WK"])); nw = len(rsi_w); nd = len(rsi_d)
                sw = rng.integers(20, nw - 20, size=args.placebo); sd = rng.integers(60, nd - 60, size=args.placebo)
                plc["WK"].append(np.array([sum(t["ret"] for t in runs["WK"](np.roll(rsi_w, int(a)))) for a in sw]))
                plc["DY1"].append(np.array([sum(t["ret"] for t in runs["DY1"](np.roll(rsi_w, int(a)), np.roll(rsi_d, int(b)))) for a, b in zip(sw, sd)]))
            bh.append((mk, (d["mc"].iloc[-1] / d["mo"].iloc[start_k] - 1) * 100))
            print(f"  {mk}: done", file=sys.stderr, flush=True)
        except Exception as ex:                                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            problems.append(f"{mk}: {type(ex).__name__}: {ex}")
    if not rows:
        print("no trades - check the data fetch (OANDA_API_TOKEN set?)\n" + "\n".join(problems))
        return
    T = pd.DataFrame(rows)
    T["t_in"] = pd.to_datetime(T["t_in"], utc=True).dt.tz_convert(NY)
    T["t_out"] = pd.to_datetime(T["t_out"], utc=True).dt.tz_convert(NY)
    cut = T.t_in.max() - pd.DateOffset(months=args.holdout_months)
    L = ["# Your weekly and daily rule books\n",
         f"Generated {now:%Y-%m-%d %H:%M} UTC. OANDA daily bid/ask, {args.years:g} years, markets {args.markets}. Decisions on COMPLETED weeks / days only, executed "
         "at the next daily open (buy at the ask, sell at the bid). No stop, as specified. % = return on the price per trade, one unit, no leverage, no swap.\n",
         "Reference, simply holding each market over the same period: " + ", ".join(f"{m} {r:+.0f}%" for m, r in bh) + "\n"]
    L += report(T[T.variant.isin(WEEKLY)], WEEKLY, "WEEKLY rule book (WK = your rule, WK0 = the same without the RSI condition)", args, cut, expo)
    L += report(T[T.variant.isin(DAILY)], DAILY, "DAILY rule book (DY1 = your rule with the sell trigger at 42, DY2 = plus EMA21 side at entry, DY3 = sell trigger at 40)", args, cut, expo)
    if args.placebo and plc["WK"]:
        L.append(f"\n## PLACEBO TEST: does the RSI add anything?  ({args.placebo} random re-timings per market)\n")
        L.append("The RSI series are slid to a random other point in time (same values, same regime lengths, no link to the price); the EMA18 / EMA21 parts stay "
                 "real. Any profit that remains comes from the EMAs and from being in rising markets, not from the RSI.\n")
        L.append("| Rule | Real total % (all markets) | Placebo average | Placebo 5th..95th percentile | Share of placebo runs that beat the real result |\n|---|---|---|---|---|")
        for v, label in (("WK", "WK weekly rule"), ("DY1", "DY1 daily rule")):
            real = T[T.variant == v].ret.sum(); tot = np.sum(plc[v], axis=0)
            L.append(f"| {label} | {real:+.1f} | {tot.mean():+.1f} | {np.percentile(tot, 5):+.1f}..{np.percentile(tot, 95):+.1f} | {(tot >= real).mean() * 100:.0f}% |")
        L.append("\nUnder about 5% in the last column would mean the RSI timing adds something real; a large number means it does not.")
    for v in [x for x in args.list.split(",") if x]:
        x = T[T.variant == v].sort_values(["market", "t_in"])
        L.append(f"\n## EVERY trade of {v} ({len(x)} trades, chronological within each market)\n")
        L.append("| Market | Side | Entry | Exit | Days | Result % | Worst dip % | Ended |\n|---|---|---|---|---|---|---|---|")
        for _, r in x.iterrows():
            L.append(f"| {r.market} | {'long' if r.side > 0 else 'short'} | {r.t_in:%Y-%m-%d} | {r.t_out:%Y-%m-%d} | {r.days} | {r.ret:+.1f} | {r.mae:.1f} | {r.reason} |")
        top = x.sort_values("ret")
        L.append("\nWorst 8: " + "; ".join(f"{r.market} {r.t_in:%Y-%m-%d} {r.ret:+.1f}%" for _, r in top.head(8).iterrows()))
        L.append("\nBest 8: " + "; ".join(f"{r.market} {r.t_in:%Y-%m-%d} {r.ret:+.1f}%" for _, r in top.tail(8).iloc[::-1].iterrows()))
    if problems:
        L.append("\n## Problems during the run (these markets are missing)\n\n" + "\n".join(f"- {p}" for p in problems))
    print("\n".join(L))


if __name__ == "__main__":
    main()
