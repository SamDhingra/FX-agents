"""In-memory stand-in for the OANDA v20 REST API (only the endpoints the bot uses).

Mirrors the documented request/response shapes closely enough to exercise the adapter: precision
checks on prices/units, stopLossOnFill, partial trade closes, stop edits, stop fills, candles.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal

import httpx
import pandas as pd

ACCT = "101-002-1234567-001"
TOKEN = "practice-token"

SPECS = {
    "XAU_USD": {"displayPrecision": 3, "tradeUnitsPrecision": 0, "minimumTradeSize": "1", "marginRate": "0.05", "px": 3650.0},
    "SPX500_USD": {"displayPrecision": 1, "tradeUnitsPrecision": 1, "minimumTradeSize": "0.1", "marginRate": "0.05", "px": 6600.0},
    "NAS100_USD": {"displayPrecision": 1, "tradeUnitsPrecision": 1, "minimumTradeSize": "0.1", "marginRate": "0.05", "px": 24500.0},
    "US30_USD": {"displayPrecision": 1, "tradeUnitsPrecision": 1, "minimumTradeSize": "0.1", "marginRate": "0.05", "px": 46500.0},
}


def _dp(s: str) -> int:
    d = Decimal(s).as_tuple().exponent
    return -d if d < 0 else 0


class FakeOanda:
    def __init__(self, nav: float = 13700.0, currency: str = "CAD", usdcad: float = 1.37) -> None:
        self.nav, self.currency, self.usdcad = nav, currency, usdcad
        self.prices = {k: v["px"] for k, v in SPECS.items()}
        self.trades: dict[str, dict] = {}
        self.next_id = 100
        self.requests: list[tuple[str, str, dict | None]] = []
        self.cancel_next: str | None = None     # make the next order be cancelled with this reason
        self.drop_stop_next = False              # make the next fill come back without its stop
        self.now = pd.Timestamp.now(tz="UTC").floor("min")

    # ── helpers for tests ──
    def hit_stop(self, tid: str) -> None:
        t = self.trades[tid]
        t["state"] = "CLOSED"
        t["averageClosePrice"] = t["stopLossOrder"]["price"]
        t["currentUnits"] = "0"

    def open_trades(self) -> list[dict]:
        return [t for t in self.trades.values() if t["state"] == "OPEN"]

    # ── transport ──
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        if req.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"errorMessage": "Insufficient authorization to perform request."})
        body = json.loads(req.content) if req.content else None
        path = req.url.path
        q = dict(req.url.params)
        self.requests.append((req.method, path, body))
        a = f"/v3/accounts/{ACCT}"
        if path == "/v3/accounts":
            return self.ok({"accounts": [{"id": ACCT, "tags": []}]})
        if path.startswith("/v3/accounts/") and not path.startswith(a):
            return httpx.Response(403, json={"errorMessage": "The provided request was forbidden."})
        if path == f"{a}/summary":
            return self.ok({"account": {"id": ACCT, "alias": "Primary", "currency": self.currency, "NAV": f"{self.nav:.4f}",
                                        "hedgingEnabled": False, "openTradeCount": len(self.open_trades())}})
        if path == f"{a}/instruments":
            names = q.get("instruments", "").split(",")
            return self.ok({"instruments": [{"name": n, "type": "CFD", **{k: v for k, v in SPECS[n].items() if k != "px"}}
                                            for n in names if n in SPECS]})
        if path == f"{a}/pricing":
            n = q["instruments"]
            if n == "USD_CAD":
                return self.ok({"prices": [{"instrument": n, "closeoutBid": str(self.usdcad - 0.0001),
                                            "closeoutAsk": str(self.usdcad + 0.0001)}]})
            return httpx.Response(400, json={"errorMessage": f"Invalid instrument {n}"})
        if path.startswith("/v3/instruments/") and path.endswith("/candles"):
            return self.candles(path.split("/")[3], q)
        if path == f"{a}/orders" and req.method == "POST":
            return self.order(body["order"])
        if path == f"{a}/openTrades":
            return self.ok({"trades": self.open_trades()})
        if path == f"{a}/openPositions":
            pos: dict[str, dict] = {}
            for t in self.open_trades():
                p = pos.setdefault(t["instrument"], {"instrument": t["instrument"], "long": {"units": "0"}, "short": {"units": "0"}})
                u = float(t["currentUnits"])
                side = "long" if u > 0 else "short"
                p[side]["units"] = str(float(p[side]["units"]) + u)
            return self.ok({"positions": list(pos.values())})
        if path.startswith(f"{a}/trades/"):
            parts = path[len(a) + 8:].split("/")
            tid = parts[0]
            t = self.trades.get(tid)
            if t is None:
                return httpx.Response(404, json={"errorCode": "NO_SUCH_TRADE", "errorMessage": "Trade not found"})
            if len(parts) == 1:
                return self.ok({"trade": t})
            if parts[1] == "close":
                return self.close(t, body.get("units", "ALL"))
            if parts[1] == "orders":
                sl = body["stopLoss"]
                if _dp(sl["price"]) > SPECS[t["instrument"]]["displayPrecision"]:
                    return httpx.Response(400, json={"errorCode": "PRICE_PRECISION_EXCEEDED", "errorMessage": "bad precision"})
                if t["state"] != "OPEN":
                    return httpx.Response(404, json={"errorCode": "NO_SUCH_TRADE", "errorMessage": "closed"})
                t["stopLossOrder"] = {"id": str(self._id()), "type": "STOP_LOSS", "price": sl["price"], "timeInForce": "GTC"}
                return self.ok({"stopLossOrderTransaction": {"type": "STOP_LOSS_ORDER", "price": sl["price"]}})
        return httpx.Response(404, json={"errorMessage": f"no route {req.method} {path}"})

    def ok(self, d: dict, code: int = 200) -> httpx.Response:
        return httpx.Response(code, json=d | {"lastTransactionID": str(self.next_id)})

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def candles(self, name: str, q: dict) -> httpx.Response:
        step = {"M1": "1min", "H1": "1h"}[q["granularity"]]
        count = int(q.get("count", 500))
        cur = self.now.floor(step)               # the forming candle
        if "from" in q:
            start = pd.Timestamp(q["from"]).tz_convert("UTC").ceil(step)
            if q.get("includeFirst") == "false" and start == pd.Timestamp(q["from"]):
                start += pd.Timedelta(step)
            idx = pd.date_range(start, cur, freq=step)[:count]
        else:
            idx = pd.date_range(end=cur, periods=count, freq=step)
        base = SPECS[name]["px"]
        out = []
        for ts in idx:
            k = ts.value // 60_000_000_000
            o = base * (1 + 0.002 * math.sin(k / 37))
            c = base * (1 + 0.002 * math.sin((k + 1) / 37))
            dp = SPECS[name]["displayPrecision"]
            out.append({"time": ts.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "volume": 10, "complete": bool(ts < cur),
                        "mid": {"o": f"{o:.{dp}f}", "h": f"{max(o, c) * 1.0003:.{dp}f}",
                                "l": f"{min(o, c) * 0.9997:.{dp}f}", "c": f"{c:.{dp}f}"}})
        return self.ok({"instrument": name, "granularity": q["granularity"], "candles": out})

    def order(self, o: dict) -> httpx.Response:
        n = o["instrument"]
        sp = SPECS[n]
        if o.get("type") != "MARKET" or "stopLossOnFill" not in o:
            return httpx.Response(400, json={"errorCode": "BAD_TEST_ORDER", "errorMessage": "the fake only takes MARKET+SL"})
        if _dp(o["stopLossOnFill"]["price"]) > sp["displayPrecision"]:
            return httpx.Response(400, json={"orderRejectTransaction": {"rejectReason": "STOP_LOSS_ON_FILL_PRICE_PRECISION_EXCEEDED"},
                                             "errorCode": "STOP_LOSS_ON_FILL_PRICE_PRECISION_EXCEEDED", "errorMessage": "precision"})
        if _dp(o["units"].lstrip("-")) > sp["tradeUnitsPrecision"]:
            return httpx.Response(400, json={"errorCode": "UNITS_PRECISION_EXCEEDED", "errorMessage": "units precision"})
        if self.cancel_next:
            why, self.cancel_next = self.cancel_next, None
            return self.ok({"orderCreateTransaction": {"id": str(self._id())},
                            "orderCancelTransaction": {"id": str(self._id()), "reason": why}}, 201)
        tid = str(self._id())
        px = f"{self.prices[n]:.{sp['displayPrecision']}f}"
        t = {"id": tid, "instrument": n, "price": px, "state": "OPEN", "initialUnits": o["units"], "currentUnits": o["units"],
             "realizedPL": "0", "unrealizedPL": "0",
             "stopLossOrder": {"id": str(self._id()), "type": "STOP_LOSS", "price": o["stopLossOnFill"]["price"], "timeInForce": "GTC"}}
        if self.drop_stop_next:
            self.drop_stop_next = False
            t.pop("stopLossOrder")
        self.trades[tid] = t
        return self.ok({"orderCreateTransaction": {"id": str(int(tid) - 1)},
                        "orderFillTransaction": {"id": str(self._id()), "price": px,
                                                 "tradeOpened": {"tradeID": tid, "units": o["units"], "price": px}}}, 201)

    def close(self, t: dict, units: str) -> httpx.Response:
        if t["state"] != "OPEN":
            return httpx.Response(404, json={"orderRejectTransaction": {"rejectReason": "TRADE_DOESNT_EXIST"},
                                             "errorCode": "TRADE_DOESNT_EXIST", "errorMessage": "closed"})
        cur = float(t["currentUnits"])
        sign = 1 if cur > 0 else -1
        n = abs(cur) if units == "ALL" else float(units)
        px = f"{self.prices[t['instrument']]:.{SPECS[t['instrument']]['displayPrecision']}f}"
        fill = {"id": str(self._id()), "price": px}
        if n >= abs(cur) - 1e-9:
            t["state"], t["currentUnits"], t["averageClosePrice"] = "CLOSED", "0", px
            fill["tradesClosed"] = [{"tradeID": t["id"], "units": str(-sign * abs(cur))}]
        else:
            t["currentUnits"] = str(sign * (abs(cur) - n))
            fill["tradeReduced"] = {"tradeID": t["id"], "units": str(-sign * n)}
        return self.ok({"orderCreateTransaction": {"id": str(self._id())}, "orderFillTransaction": fill})
