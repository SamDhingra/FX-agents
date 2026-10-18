"""READ-ONLY spread probe for a FOREX.com (GAIN / City Index Trading API) account — no orders, ever.

    python -m fxagents.forexcom_probe [--days 10] [--out data/year_test/forexcom_spreads]     (./fx.sh fxcprobe)

Credentials from .env: FOREXCOM_USERNAME, FOREXCOM_PASSWORD, FOREXCOM_APPKEY (optional FOREXCOM_REST_URL, default
https://ciapi.cityindex.com/TradingAPI). Endpoints as used by the open-source `forexcom` SDK (github.com/ali-zahedi/
forexcom): POST /session, GET /UserAccount/ClientAndTradingAccount, GET /market/fullsearchwithtags,
GET /market/{id}/tickhistorybetween (one price side per call: BID or ASK).

What it does:
  1. logs in and prints the account's name/currency (never the credentials);
  2. searches each instrument's likely market names and prints every match, picking the preferred name;
  3. for the last --days weekdays, samples a 10-minute window in every hour (:25–:35 UTC), fetches BID and ASK ticks,
     pairs them by timestamp (nearest within 1 s) and measures the spread;
  4. compares with OANDA's spread in the same New York hour, from the last 60 days of the dev_m1 export;
  5. writes report.md + spreads.csv.gz and publishes like the other tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

NY = "America/New_York"
BASE = os.environ.get("FOREXCOM_REST_URL", "https://ciapi.cityindex.com/TradingAPI").rstrip("/")
# preferred market names first; every match is printed so a wrong pick is visible
TRANSPORT = None                      # tests inject an httpx.MockTransport here
CANDIDATES = {
    "XAUUSD": ["Spot Gold", "Gold", "XAU/USD", "Gold Spot"],
    "US30": ["US 30", "Wall Street", "US30", "Dow Jones", "Wall St"],
    "NDQ": ["US Tech 100", "NAS100", "US NAS 100", "Nasdaq 100", "US 100"],
}


class Api:
    def __init__(self, user: str, pw: str, key: str):
        self.user, self.c = user, httpx.Client(base_url=BASE, timeout=30, transport=TRANSPORT)
        r = self.c.post("/session", json={"UserName": user, "Password": pw, "AppKey": key, "AppVersion": "1",
                                          "AppComments": "fx-agents read-only spread probe"})
        body = self._json(r)
        if r.status_code != 200 or not body.get("Session"):
            raise SystemExit(f"login failed: HTTP {r.status_code} {self._safe(body)}")
        self.h = {"UserName": user, "Session": body["Session"]}

    @staticmethod
    def _json(r) -> dict:
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text[:300]}

    @staticmethod
    def _safe(body: dict) -> str:
        return json.dumps({k: v for k, v in body.items() if k.lower() not in ("session", "password", "appkey")})[:400]

    def get(self, path: str, **params):
        for attempt in range(4):
            r = self.c.get(path, params={k: v for k, v in params.items() if v is not None}, headers=self.h)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 + 3 * attempt)
                continue
            return r.status_code, self._json(r)
        return r.status_code, self._json(r)


def ticks(api: Api, mid: int, side: str, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    code, body = api.get(f"/market/{mid}/tickhistorybetween", priceType=side,
                         fromTimeStampUTC=int(t0.timestamp()), toTimestampUTC=int(t1.timestamp()))
    rows = body.get("PriceTicks") or []
    if code != 200 or not rows:
        return pd.DataFrame(columns=["t", side.lower()])
    t = pd.to_datetime([int(re.sub(r"\D", "", x["TickDate"])[:13]) for x in rows], unit="ms", utc=True)
    return pd.DataFrame({"t": t, side.lower(): [float(x["Price"]) for x in rows]}).sort_values("t")


def ratio(x: float, base: float) -> str:
    return "—" if not np.isfinite(base) or not base else f"{x / base:.0%}"


def oanda_by_hour(sym: str) -> pd.Series:
    f = Path("data/export/dev_m1") / f"{sym}_M1.csv.gz"
    if not f.exists():
        return pd.Series(dtype=float)
    d = pd.read_csv(f, usecols=["time", "bid_o", "ask_o"])
    d.index = pd.to_datetime(d.pop("time"), utc=True)
    d = d[d.index >= d.index.max() - pd.Timedelta(days=60)]
    sp = d.ask_o - d.bid_o
    return sp.groupby(sp.index.tz_convert(NY).hour).median()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--out", type=Path, default=Path("data/year_test/forexcom_spreads"))
    a = ap.parse_args()
    env = {k: os.environ.get(k, "").strip() for k in ("FOREXCOM_USERNAME", "FOREXCOM_PASSWORD", "FOREXCOM_APPKEY")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise SystemExit("missing in .env: " + ", ".join(missing))
    api = Api(*env.values())
    code, acct = api.get("/UserAccount/ClientAndTradingAccount")
    tas = acct.get("TradingAccounts") or [{}]
    print(f"logged in to {BASE} — account: {tas[0].get('TradingAccountName', '?')} "
          f"({acct.get('ClientAccountCurrency', '?')}), {len(tas)} trading account(s)")
    a.out.mkdir(parents=True, exist_ok=True)
    picks, found = {}, {}
    for sym, names in CANDIDATES.items():
        seen = {}
        for q in names:
            code, body = api.get("/market/fullsearchwithtags", query=q, maxResults=20)
            for m in body.get("MarketInformation") or []:
                seen[m.get("MarketId")] = m.get("Name")
        found[sym] = seen
        pick = next((mid for want in names for mid, nm in seen.items() if (nm or "").strip().lower() == want.lower()), None)
        if pick is None:
            pick = next((mid for want in names for mid, nm in seen.items() if want.lower() in (nm or "").lower()), None)
        picks[sym] = pick
        print(f"  {sym}: {len(seen)} matches → {seen.get(pick, 'NONE')} (id {pick}); all: "
              + "; ".join(f"{n} [{i}]" for i, n in list(seen.items())[:12]))
    now = pd.Timestamp.now(tz="UTC").floor("h")
    rows = []
    for sym, mid in picks.items():
        if mid is None:
            continue
        for h in range(a.days * 24, 0, -1):
            t0 = now - pd.Timedelta(hours=h) + pd.Timedelta(minutes=25)
            if t0.tz_convert(NY).dayofweek >= 5 or (t0.tz_convert(NY).dayofweek == 4 and t0.tz_convert(NY).hour >= 17):
                continue
            t1 = t0 + pd.Timedelta(minutes=10)
            b, k = ticks(api, mid, "BID", t0, t1), ticks(api, mid, "ASK", t0, t1)
            if b.empty or k.empty:
                continue
            m = pd.merge_asof(b, k, on="t", direction="nearest", tolerance=pd.Timedelta("1s")).dropna()
            m = m[m.ask >= m.bid]
            if len(m):
                sp = m.ask - m.bid
                rows.append({"symbol": sym, "hour_utc": t0, "ny_hour": t0.tz_convert(NY).hour, "n": len(m),
                             "median": float(sp.median()), "mean": float(sp.mean()), "p90": float(sp.quantile(.9)),
                             "mid": float(((m.ask + m.bid) / 2).median())})
            time.sleep(0.25)
        print(f"  {sym}: {sum(r['symbol'] == sym for r in rows)} hourly samples", flush=True)
    S = pd.DataFrame(rows)
    if len(S):
        S.to_csv(a.out / "spreads.csv.gz", index=False)
    md = [f"# FOREX.com spread probe (read-only) — {BASE}", "",
          f"Last {a.days} weekdays to {now:%Y-%m-%d %H:%M} UTC; a 10-minute BID+ASK tick sample each hour, paired within "
          "1 s. OANDA column = median minute-open spread in the same New York hour over the last 60 days of the dev_m1 "
          "export (a different period: compare levels, not exact values). Spreads in price points. A commission, if "
          "the account type charges one, is NOT included.", ""]
    for sym, mid in picks.items():
        md.append(f"## {sym} — FOREX.com market: {found[sym].get(mid, 'not found')} (id {mid})")
        md.append("")
        x = S[S.symbol == sym] if len(S) else pd.DataFrame()
        if not len(x):
            md += ["No price ticks returned for this market.", ""]
            continue
        o = oanda_by_hour(sym)
        g = x.groupby("ny_hour").agg(samples=("n", "size"), median=("median", "median"), p90=("p90", "median"),
                                     price=("mid", "median"))
        overall = float(x["median"].median())
        oo = float(o.median()) if len(o) else float("nan")
        md.append(f"**Typical spread: FOREX.com {overall:.3f} vs OANDA {oo:.3f}** "
                  f"({overall / oo:.0%} of OANDA)." if np.isfinite(oo) and oo else f"**Typical spread: {overall:.3f}.**")
        md += ["", "| NY hour | Samples | FOREX.com median | FOREX.com p90 | OANDA median | Ratio |", "|---|---|---|---|---|---|"]
        for hr, r in g.iterrows():
            ov = o.get(hr, np.nan)
            md.append(f"| {hr:02d}:00 | {int(r.samples)} | {r['median']:.3f} | {r.p90:.3f} | "
                      f"{'—' if not np.isfinite(ov) else f'{ov:.3f}'} | "
                      f"{ratio(r['median'], ov)} |")
        md.append("")
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "markets.json").write_text(json.dumps({"base": BASE, "picks": picks, "matches": found}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    sys.exit(main())
