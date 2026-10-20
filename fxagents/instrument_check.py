"""READ-ONLY instrument check before adding one to the bot: can this OANDA account trade it, at what size, margin,
spread and overnight financing?  No orders, no account data beyond the instrument's terms.

    python -m fxagents.instrument_check BTC_USD          (./fx.sh instcheck BTC_USD)

Also prints the median bid/ask spread of the downloaded 1-minute history (data/bt/cache, from ./fx.sh export) over
the last 90 days — overall, at the open of each bot entry window, and at the 18:00 daily open.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd

from .config import apply_broker, load_config
from .oanda import oanda_from_cfg

ALIAS = {"BTC_USD": "BTCUSD", "ETH_USD": "ETHUSD", "XAU_USD": "XAUUSD", "NAS100_USD": "NDQ", "US30_USD": "US30"}
WINDOWS = {"London 02:00–05:00": (120, 300), "NY AM 08:30–11:30": (510, 690), "NY PM 13:30–15:30": (810, 930),
           "Asia 20:00–23:59": (1200, 1440), "daily open 18:00–18:05": (1080, 1085)}


def cached_spread(sym: str) -> None:
    for ds in ("seen", "vault"):
        cd = Path("data/bt/cache") / f"{ds}_{sym}"
        if not (cd / "ns.npy").exists():
            continue
        ns = np.load(cd / "ns.npy", mmap_mode="r")
        i0 = int(np.searchsorted(ns, ns[-1] - 90 * 86400 * 10 ** 9))
        sp = np.load(cd / "ask_o.npy", mmap_mode="r")[i0:] - np.load(cd / "bid_o.npy", mmap_mode="r")[i0:]
        mid = (np.load(cd / "ask_o.npy", mmap_mode="r")[i0:] + np.load(cd / "bid_o.npy", mmap_mode="r")[i0:]) / 2
        loc = pd.DatetimeIndex(np.asarray(ns[i0:]).astype("datetime64[ns]")).tz_localize("UTC").tz_convert("America/New_York")
        mod = loc.hour * 60 + loc.minute
        print(f"  downloaded history ({ds}, last 90 days to {loc[-1]:%Y-%m-%d}): median spread {np.median(sp):.4g} "
              f"({np.median(sp / mid) * 1e4:.2f} bps of price), 90th percentile {np.percentile(sp, 90):.4g}")
        for k, (a, b) in WINDOWS.items():
            m = (mod >= a) & (mod < b)
            if m.any():
                print(f"    {k:24} median {np.median(sp[m]):.4g}")
        return
    print("  no downloaded history in data/bt/cache for this symbol (run ./fx.sh export, then any backtest on it)")


async def check(names: list[str]) -> None:
    cfg = load_config()
    c2 = {**cfg, "mode": "paper", "broker": "oanda", "instruments": {k: dict(v) for k, v in cfg["instruments"].items()}}
    apply_broker(c2)
    c = oanda_from_cfg(c2)
    res = await c.req("GET", c.acct("/instruments"), params={"instruments": ",".join(names)})
    by = {i["name"]: i for i in res.get("instruments", [])}
    px = {}
    try:
        pr = await c.req("GET", c.acct("/pricing"), params={"instruments": ",".join(n for n in names if n in by)})
        px = {p["instrument"]: p for p in pr.get("prices", [])}
    except Exception as e:  # noqa: BLE001
        print(f"(live price unavailable: {e})")
    for n in names:
        print(f"\n{n}")
        i = by.get(n)
        if i is None:
            print("  NOT tradeable on this OANDA account (the account doesn't offer it).")
        else:
            f = i.get("financing") or {}
            print(f"  tradeable: yes ({i.get('type')}, {i.get('displayName')})")
            print(f"  minimum size {i.get('minimumTradeSize')} units, unit step 10^-{i.get('tradeUnitsPrecision')}, "
                  f"price decimals {i.get('displayPrecision')}, margin {float(i.get('marginRate', 0)) * 100:.1f}%")
            if f:
                lr, sr = float(f.get("longRate", 0)), float(f.get("shortRate", 0))
                days = ", ".join(f"{d['dayOfWeek'][:3]}×{d['daysCharged']}" for d in f.get("financingDaysOfWeek", []))
                print(f"  overnight financing (yearly rate): long {lr * 100:+.2f}%, short {sr * 100:+.2f}%  "
                      f"(per day ≈ long {lr / 365 * 1e4:+.2f} bps, short {sr / 365 * 1e4:+.2f} bps)  days: {days}")
            p = px.get(n)
            if p and p.get("bids") and p.get("asks"):
                b, a = float(p["bids"][0]["price"]), float(p["asks"][0]["price"])
                print(f"  live quote now: bid {b} ask {a} → spread {a - b:.4g} ({(a - b) / ((a + b) / 2) * 1e4:.2f} bps), "
                      f"tradeable now: {p.get('tradeable')}")
        cached_spread(ALIAS.get(n, n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instruments", nargs="+", help="OANDA names, e.g. BTC_USD")
    asyncio.run(check(ap.parse_args().instruments))


if __name__ == "__main__":
    main()
