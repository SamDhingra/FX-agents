"""Backtest every strategy (with the live trade-management rules) and print a leaderboard.

    python backtest.py --synthetic                               # quick check, no data needed
    python backtest.py --csv NDQ=exports/CME_MINI_MNQ1!, 1.csv    # TradingView "Export chart data" (1m or 5m)
    python backtest.py --ibkr --days 30                          # pull history from IB Gateway/TWS
    (the hard HTF bias rule is applied by default; --no-bias to compare; use ≥ 25 days so Daily structure exists)

Output includes expectancy per hour of day (NY), which is exactly what the Selector uses.
"""
from __future__ import annotations

import argparse
import asyncio

import pandas as pd

from fxagents.bias import bias_frame
from fxagents.config import load_config
from fxagents.indicators import resample_ohlc
from fxagents.sim import Mgmt, backtest, stats, synth_1m
from fxagents.strategies import BUILTIN, Strategy


def load_tv_csv(path: str, tz: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    t = df["time"]
    ts = pd.to_datetime(t, unit="s", utc=True) if pd.api.types.is_numeric_dtype(t) else pd.to_datetime(t, utc=True)
    out = pd.DataFrame({"open": df["open"], "high": df["high"], "low": df["low"], "close": df["close"],
                        "volume": df.get("volume", 0)}).set_index(ts.dt.tz_convert(tz))
    return out.sort_index()


async def load_ibkr(cfg, days: int) -> dict[str, pd.DataFrame]:
    from ib_async import IB
    from fxagents.data import IBKRFeed
    ib = IB()
    await ib.connectAsync(cfg["ibkr"]["host"], int(cfg["ibkr"]["port"]), clientId=int(cfg["ibkr"]["client_id"]) + 50)
    cfg["timeframes"]["history_days"] = days
    feed = IBKRFeed(cfg, None, type("S", (), {"now": None})(), ib)
    await feed.qualify()
    out = {}
    for sym, c in feed.contracts.items():
        bars = await ib.reqHistoricalDataAsync(c, "", f"{days} D", "1 min", feed._what(sym), False, formatDate=2)
        df = pd.DataFrame([{"ts": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                            "volume": b.volume} for b in bars])
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(cfg["timezone"])
        out[sym] = df.set_index("ts")
    ib.disconnect()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--csv", nargs="*", default=[], help="SYMBOL=path.csv (TradingView export)")
    ap.add_argument("--ibkr", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--days", type=int, default=15)
    ap.add_argument("--rr", type=float, default=None)
    ap.add_argument("--no-pyramid", action="store_true")
    ap.add_argument("--no-bias", action="store_true", help="disable the hard HTF bias rule")
    a = ap.parse_args()
    cfg = load_config(a.config)
    tz = cfg["timezone"]
    frames: dict[str, pd.DataFrame] = {}
    for item in a.csv:
        sym, path = item.split("=", 1)
        frames[sym] = load_tv_csv(path, tz)
    if a.ibkr:
        frames |= asyncio.run(load_ibkr(cfg, a.days))
    if a.synthetic or not frames:
        start = pd.Timestamp.now(tz=tz).normalize() - pd.Timedelta(days=a.days)
        for j, (sym, ic) in enumerate(cfg["instruments"].items()):
            frames[sym] = synth_1m(ic["sim_start_price"], ic["sim_daily_vol"], start, a.days, 100 + j, tz)
        print("(synthetic data — useful for plumbing checks only, says nothing about real edge)\n")
    if a.no_pyramid:
        cfg["management"]["pyramid"]["enabled"] = False
    s = cfg["sessions"]
    rows, hours = [], {}
    for sym, d in frames.items():
        h1 = resample_ohlc(d, "1h")
        for tf in cfg["timeframes"]["entry"]:
            m = Mgmt.from_cfg(cfg, rr=a.rr, bar_minutes=int(pd.Timedelta(tf).total_seconds() // 60))
            df = resample_ohlc(d, tf)
            ctx = Strategy.context(df)
            bias = None if a.no_bias else bias_frame(h1, df.index + pd.Timedelta(tf))["score"].to_numpy()
            for name, cls in BUILTIN.items():
                tr = backtest(cls(tf=tf), df, ctx, m, s["entry_windows"], s["flatten_at"], bias_score=bias,
                              min_align=cfg["bias"]["min_align"])
                st = stats(tr)
                name_tf = f"{name}:{tf.replace('min', 'm')}"
                rows.append({"symbol": sym, "strategy": name_tf, "trades": st["n"], "win%": round(st["win_rate"] * 100),
                             "exp_R": st["expectancy"], "sum_R": st["sum_r"], "PF": st["pf"], "maxDD_R": st["max_dd_r"],
                             "reach1.5R%": round(st["reach"].get(1.5, 0) * 100)})
                for h, b in st["by_hour"].items():
                    hours.setdefault((name_tf, h), []).append(b["exp"])
    out = pd.DataFrame(rows).sort_values(["symbol", "exp_R"], ascending=[True, False])
    pd.set_option("display.width", 160)
    print(out.to_string(index=False))
    hm = pd.Series({k: sum(v) / len(v) for k, v in hours.items()}).unstack().round(2)
    print("\nMean expectancy (R) by strategy × NY hour:\n")
    print(hm.to_string())


if __name__ == "__main__":
    main()
