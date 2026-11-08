"""Dow 30 member minute bars for the US30 one-stock reversal test (registered Nov 7 2026, research/dow_reversal/).

Alpaca historical 1-minute bars, as-traded prices (adjustment=raw), SIP feed. Each ticker is fetched only over its
own membership period with `asof` = that period's start, so renamed tickers resolve point-in-time. Keys come from the
environment (ALPACA_KEY_ID / ALPACA_SECRET_KEY, set in .env) and are never printed or stored.

    python -m fxagents.dow_data fetch [--start 2016-01-01] [--end 2026-09-30]
    python -m fxagents.dow_data coverage

Files: data/dow_m1/<TICKER>/<YYYY-MM>.csv.gz (ts = bar start UTC, c = close), regular hours 09:25–16:05 NY only.
Resumable: finished months are kept; a month with no bars is recorded in data/dow_m1/manifest.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

NY = "America/New_York"
ROOT = Path("data/dow_m1")
URL = "https://data.alpaca.markets/v2/stocks/{sym}/bars"

BASE_2016 = ("MMM AXP AAPL BA CAT CVX CSCO KO DD XOM GE GS HD INTC IBM JNJ JPM MCD MRK MSFT NKE PFE PG TRV UNH UTX VZ V "
             "WMT DIS").split()
# effective before the open on each date (Wikipedia "Historical components of the DJIA"; S&P DJI Jun 23 2026 release)
CHANGES = [("2017-09-01", ["DWDP"], ["DD"]), ("2018-06-26", ["WBA"], ["GE"]), ("2019-04-02", ["DOW"], ["DWDP"]),
           ("2020-04-03", ["RTX"], ["UTX"]), ("2020-08-31", ["AMGN", "HON", "CRM"], ["XOM", "PFE", "RTX"]),
           ("2024-02-26", ["AMZN"], ["WBA"]), ("2024-11-08", ["NVDA", "SHW"], ["INTC", "DOW"]),
           ("2026-06-29", ["GOOGL"], ["VZ"])]
SKIP_DAYS = {pd.Timestamp(d) for d, _, _ in CHANGES} | {pd.Timestamp("2020-04-06")}


def members(day) -> list[str]:
    """The 30 members on NY date `day`."""
    day = pd.Timestamp(day).normalize()
    m = list(BASE_2016)
    for d, add, rem in CHANGES:
        if day >= pd.Timestamp(d):
            m = [x for x in m if x not in rem] + add
    assert len(m) == 30, (day, len(m))
    return m


def periods(start="2016-01-01", end="2026-09-30") -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """ticker → [(first day, last day)] of membership inside [start, end]."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    edges = [start] + [pd.Timestamp(d) for d, _, _ in CHANGES if start < pd.Timestamp(d) <= end] + [end + pd.Timedelta(days=1)]
    out: dict = {}
    for a, b in zip(edges[:-1], edges[1:]):
        for s in members(a):
            seg = out.setdefault(s, [])
            if seg and seg[-1][1] == a - pd.Timedelta(days=1):
                seg[-1] = (seg[-1][0], b - pd.Timedelta(days=1))
            else:
                seg.append((a, b - pd.Timedelta(days=1)))
    return out


def _get(session, sym: str, params: dict, tries: int = 6) -> dict:
    for k in range(tries):
        r = session.get(URL.format(sym=sym), params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** k)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"{sym}: Alpaca {r.status_code}: {r.text[:200]}")   # the body never holds the keys
        return r.json()
    raise RuntimeError(f"{sym}: Alpaca kept refusing ({r.status_code})")


def fetch_month(session, sym: str, a: pd.Timestamp, b: pd.Timestamp, asof: pd.Timestamp, feed: str) -> pd.DataFrame:
    params = {"timeframe": "1Min", "start": a.tz_localize(NY).tz_convert("UTC").isoformat().replace("+00:00", "Z"),
              "end": (b + pd.Timedelta(days=1)).tz_localize(NY).tz_convert("UTC").isoformat().replace("+00:00", "Z"),
              "adjustment": "raw", "feed": feed, "limit": 10000, "asof": asof.strftime("%Y-%m-%d")}
    rows, tok = [], None
    while True:
        if tok:
            params["page_token"] = tok
        j = _get(session, sym, params)
        rows += [(x["t"], x["c"]) for x in (j.get("bars") or [])]
        tok = j.get("next_page_token")
        time.sleep(0.32)                                            # ≤ 200 calls a minute
        if not tok:
            break
    if not rows:
        return pd.DataFrame(columns=["ts", "c"])
    d = pd.DataFrame(rows, columns=["ts", "c"])
    d["ts"] = pd.to_datetime(d.ts, utc=True)
    loc = d.ts.dt.tz_convert(NY)
    mins = loc.dt.hour * 60 + loc.dt.minute
    return d[(mins >= 9 * 60 + 25) & (mins <= 16 * 60 + 5)].reset_index(drop=True)


def fetch(start="2016-01-01", end="2026-09-30", root: Path = ROOT, session=None, feed: str | None = None) -> dict:
    kid, sec = os.environ.get("ALPACA_KEY_ID"), os.environ.get("ALPACA_SECRET_KEY")
    if session is None:
        import httpx
        if not kid or not sec:
            raise SystemExit("set ALPACA_KEY_ID and ALPACA_SECRET_KEY in .env (free Alpaca account → API keys)")
        session = httpx.Client(headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec})
    feed = feed or os.environ.get("ALPACA_FEED", "sip")
    root.mkdir(parents=True, exist_ok=True)
    man_f = root / "manifest.json"
    man = json.loads(man_f.read_text()) if man_f.exists() else {}
    todo = []
    for sym, segs in periods(start, end).items():
        for a, b in segs:
            for m in pd.period_range(a, b, freq="M"):
                ma, mb = max(a, m.start_time.normalize()), min(b, m.end_time.normalize())
                key = f"{sym}/{m}"
                if not (root / sym / f"{m}.csv.gz").exists() and key not in man:
                    todo.append((sym, ma, mb, a, m, key))
    print(f"dow data: {len(todo)} ticker-months to fetch (feed {feed})", flush=True)
    for n, (sym, ma, mb, asof, m, key) in enumerate(todo, 1):
        d = fetch_month(session, sym, ma, mb, asof, feed)
        (root / sym).mkdir(exist_ok=True)
        if len(d):
            d.to_csv(root / sym / f"{m}.csv.gz", index=False)
        man[key] = len(d)
        if n % 25 == 0 or n == len(todo):
            man_f.write_text(json.dumps(man, indent=0, sort_keys=True))
            print(f"  {n}/{len(todo)}  last {key}: {len(d):,} bars", flush=True)
    man_f.write_text(json.dumps(man, indent=0, sort_keys=True))
    return man


def load_day_closes(day: pd.Timestamp, root: Path = ROOT, _cache: dict = {}) -> pd.DataFrame:
    """Minute closes (index = bar start, NY) × the day's 30 members, raw dollars. Missing bars stay NaN."""
    day = pd.Timestamp(day).normalize()
    cols = {}
    for s in members(day):
        key = (str(root), s, str(day.to_period("M")))
        if key not in _cache:
            f = root / s / f"{day.to_period('M')}.csv.gz"
            if f.exists():
                d = pd.read_csv(f)
                d.index = pd.DatetimeIndex(pd.to_datetime(d.pop("ts"), utc=True)).tz_convert(NY)
                _cache[key] = d["c"]
            else:
                _cache[key] = pd.Series(dtype=float)
            if len(_cache) > 400:                                       # keep memory flat over ten years
                _cache.pop(next(iter(_cache)))
        x = _cache[key]
        cols[s] = x[(x.index >= day.tz_localize(NY)) & (x.index < (day + pd.Timedelta(days=1)).tz_localize(NY))] if len(x) else x
    return pd.DataFrame(cols)


def coverage(root: Path = ROOT, start="2016-01-01", end="2026-09-30") -> str:
    man = json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").exists() else {}
    lines = ["| ticker | months | months with bars | bars |", "|---|---|---|---|"]
    by: dict = {}
    for k, v in man.items():
        s = k.split("/")[0]
        a = by.setdefault(s, [0, 0, 0])
        a[0] += 1; a[1] += v > 0; a[2] += v
    for s in sorted(by):
        lines.append(f"| {s} | {by[s][0]} | {by[s][1]} | {by[s][2]:,} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["fetch", "coverage"])
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2026-09-30")
    a = ap.parse_args(argv)
    if a.what == "fetch":
        fetch(a.start, a.end)
    print(coverage(start=a.start, end=a.end))


if __name__ == "__main__":
    sys.exit(main())
