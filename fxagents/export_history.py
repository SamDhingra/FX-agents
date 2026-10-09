"""Export OANDA bid/ask candles to plain gzipped CSV for outside research (e.g. Astra), with a manifest.

    python -m fxagents.export_history --name dev_m1 --gran M1 --from 2024-10-01 --until 2026-09-30
    python -m fxagents.export_history --name dev_d  --gran D  --from 2012-01-01 --until 2026-09-30

Output: data/export/<name>/<SYMBOL>_<GRAN>.csv.gz + manifest.json (row counts, spans, sha256).
Columns: time (UTC, candle OPEN time, ISO 8601), bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume
(volume = OANDA tick count, NOT traded contracts). Only complete candles. Daily candles use OANDA's default
17:00 New York alignment. No account data, tokens or positions are exported — market prices only.

The holdout rule: data exported for development must never overlap the holdout window, and the holdout
export is run only to score frozen code (fxagents/astra_holdout or by hand), never handed to the researcher.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import apply_broker, load_config
from .oanda import OandaFeed, oanda_from_cfg

COLS = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]
STEP = {"M1": pd.Timedelta("1min"), "M5": pd.Timedelta("5min"), "H1": pd.Timedelta("1h"), "D": pd.Timedelta("1D")}


def rows(cs: list[dict]) -> list[dict]:
    out = []
    for c in cs:
        if not c.get("complete") or "bid" not in c or "ask" not in c:
            continue
        b, a = c["bid"], c["ask"]
        out.append({"time": c["time"], "bid_o": b["o"], "bid_h": b["h"], "bid_l": b["l"], "bid_c": b["c"],
                    "ask_o": a["o"], "ask_h": a["h"], "ask_l": a["l"], "ask_c": a["c"], "volume": int(c.get("volume", 0))})
    return out


async def fetch(client, name: str, gran: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Every complete bid/ask candle with open time in [start, end). Pages forward; no page cap short of the end."""
    out, cur = [], start - STEP[gran]
    while True:
        p = {"granularity": gran, "price": "BA", "count": "5000", "includeFirst": "false",
             "from": cur.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")}
        cs = (await client.req("GET", f"/v3/instruments/{name}/candles", params=p)).get("candles", [])
        if not cs:
            break
        out += rows(cs)
        nxt = pd.Timestamp(cs[-1]["time"])
        if nxt <= cur or nxt >= end:
            break
        cur = nxt
    if not out:
        return pd.DataFrame(columns=["time", *COLS])
    df = pd.DataFrame(out)
    t = pd.to_datetime(df["time"], utc=True)
    df = df[(t >= start) & (t < end)].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df.drop_duplicates("time").sort_values("time")[["time", *COLS]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="folder under data/export/")
    ap.add_argument("--gran", default="M1", choices=sorted(STEP))
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--until", required=True, help="last day included (YYYY-MM-DD)")
    ap.add_argument("--symbols", nargs="*", help="default: every configured instrument; anything not configured is "
                    "taken as an OANDA instrument name as is (e.g. WTICO_USD, XAG_USD, DE30_EUR)")
    a = ap.parse_args()
    cfg = load_config()
    c2 = {**cfg, "mode": "paper", "broker": "oanda", "instruments": {k: dict(v) for k, v in cfg["instruments"].items()}}
    apply_broker(c2)
    client = oanda_from_cfg(c2)
    names = OandaFeed(c2, None, None, client).syms
    syms = a.symbols or list(names)
    names = {s: names.get(s, s) for s in syms}
    start = pd.Timestamp(a.start, tz="UTC")
    end = pd.Timestamp(a.until, tz="UTC") + pd.Timedelta("1D")
    out = Path("data/export") / a.name
    out.mkdir(parents=True, exist_ok=True)
    man = {"source": "OANDA v20 practice API, price=BA (bid and ask candles)", "granularity": a.gran,
           "from": a.start, "until": a.until, "time": "UTC candle open time", "columns": ["time", *COLS],
           "volume": "OANDA tick count (number of price updates), not traded volume",
           "instrument_names": {s: names[s] for s in syms}, "files": {}}

    async def go():
        for s in syms:
            print(f"  {s} ({names[s]}) {a.gran} {a.start} → {a.until} …", flush=True)
            try:
                df = await fetch(client, names[s], a.gran, start, end)
            except Exception as e:  # noqa: BLE001 — an instrument this account can't trade: skip it, keep going
                print(f"    skipped: {e}", flush=True)
                man["files"][f"{s}_{a.gran}.csv.gz"] = {"error": str(e)[:200]}
                continue
            f = out / f"{s}_{a.gran}.csv.gz"
            df.to_csv(f, index=False, compression={"method": "gzip", "mtime": 0})
            man["files"][f.name] = {"rows": len(df), "first": df["time"].iloc[0] if len(df) else None,
                                    "last": df["time"].iloc[-1] if len(df) else None,
                                    "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            print(f"    {len(df):,} candles → {f} ({f.stat().st_size / 1e6:.1f} MB)", flush=True)
    asyncio.run(go())
    (out / "manifest.json").write_text(json.dumps(man, indent=2))
    print(f"done: {out}/manifest.json")


if __name__ == "__main__":
    main()
