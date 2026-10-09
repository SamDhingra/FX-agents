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
import csv
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import apply_broker, load_config
from .oanda import OandaFeed, oanda_from_cfg

COLS = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]
STEP = {"M1": pd.Timedelta("1min"), "M5": pd.Timedelta("5min"), "H1": pd.Timedelta("1h"), "D": pd.Timedelta("1D")}


def stamp(t: str) -> str:
    """OANDA RFC 3339 time ('2025-01-02T14:31:00.000000000Z') → '2025-01-02T14:31:00Z' (sortable as text)."""
    return t[:19] + "Z"


async def export_one(client, name: str, gran: str, start: pd.Timestamp, end: pd.Timestamp, path: Path) -> dict:
    """Stream every complete bid/ask candle with open time in [start, end) to a gzipped CSV, page by page
    (5,000 candles at a time), so memory stays flat however long the window is. Returns rows/first/last."""
    lo, hi = stamp(start.strftime("%Y-%m-%dT%H:%M:%S")), stamp(end.strftime("%Y-%m-%dT%H:%M:%S"))
    n, first, last, cur = 0, None, None, start - STEP[gran]
    tmp = path.with_suffix(".part")
    with gzip.open(tmp, "wt", newline="", compresslevel=6) as fh:
        w = csv.writer(fh)
        w.writerow(["time", *COLS])
        while True:
            p = {"granularity": gran, "price": "BA", "count": "5000", "includeFirst": "false",
                 "from": cur.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")}
            cs = (await client.req("GET", f"/v3/instruments/{name}/candles", params=p)).get("candles", [])
            if not cs:
                break
            for c in cs:
                t = stamp(c["time"])
                if not c.get("complete") or "bid" not in c or "ask" not in c or t < lo or t >= hi or (last and t <= last):
                    continue
                b, a = c["bid"], c["ask"]
                w.writerow([t, b["o"], b["h"], b["l"], b["c"], a["o"], a["h"], a["l"], a["c"], int(c.get("volume", 0))])
                n, first, last = n + 1, first or t, t
            nxt = pd.Timestamp(cs[-1]["time"])
            if nxt <= cur or stamp(cs[-1]["time"]) >= hi:
                break
            cur = nxt
    tmp.replace(path)
    return {"rows": n, "first": first, "last": last}


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

    mf = out / "manifest.json"
    if mf.exists():                                   # re-running adds/refreshes files, keeps the others' entries
        prev = json.loads(mf.read_text())
        if (prev.get("granularity"), prev.get("from"), prev.get("until")) == (a.gran, a.start, a.until):
            man["files"] = prev.get("files", {})
            man["instrument_names"] = {**prev.get("instrument_names", {}), **man["instrument_names"]}

    async def go():
        for s in syms:
            f = out / f"{s}_{a.gran}.csv.gz"
            print(f"  {s} ({names[s]}) {a.gran} {a.start} → {a.until} …", flush=True)
            try:
                info = await export_one(client, names[s], a.gran, start, end, f)
            except Exception as e:  # noqa: BLE001 — an instrument this account can't trade: skip it, keep going
                print(f"    skipped: {e}", flush=True)
                man["files"][f.name] = {"error": str(e)[:200]}
            else:
                h = hashlib.sha256()
                with open(f, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                man["files"][f.name] = {**info, "sha256": h.hexdigest()}
                print(f"    {info['rows']:,} candles {info['first']} → {info['last']} ({f.stat().st_size / 1e6:.1f} MB)", flush=True)
            mf.write_text(json.dumps(man, indent=2))   # after every instrument, so a stopped run keeps what it did
    asyncio.run(go())
    print(f"done: {out}/manifest.json")


if __name__ == "__main__":
    main()
