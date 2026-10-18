"""FOREX.com spread probe against a fake Trading API: login, market pick, BID/ASK pairing — and no orders."""
import json
import sys

import httpx
import pandas as pd

import fxagents.forexcom_probe as P

SEEN = []


def handler(req: httpx.Request) -> httpx.Response:
    SEEN.append((req.method, req.url.path))
    p = req.url.path
    if p.endswith("/session"):
        b = json.loads(req.content)
        assert b["UserName"] == "u" and b["AppKey"] == "k"
        return httpx.Response(200, json={"Session": "S1", "StatusCode": 1})
    assert req.headers["Session"] == "S1"
    if p.endswith("ClientAndTradingAccount"):
        return httpx.Response(200, json={"ClientAccountCurrency": "USD", "TradingAccounts": [{"TradingAccountName": "Demo"}]})
    if p.endswith("fullsearchwithtags"):
        q = req.url.params["query"]
        names = {"Spot Gold": [(1, "Spot Gold"), (9, "Gold Futures")], "US 30": [(2, "US 30")],
                 "US Tech 100": [(3, "US Tech 100")]}
        return httpx.Response(200, json={"MarketInformation": [{"MarketId": i, "Name": n} for i, n in names.get(q, [])]})
    if "tickhistorybetween" in p:
        side = req.url.params["priceType"]
        t0 = int(req.url.params["fromTimeStampUTC"]) * 1000
        sp = {"1": 0.30, "2": 2.0, "3": 1.0}[p.split("/")[-2]] if p.split("/")[-2] in "123" else 0
        base = 4000.0
        ticks = [{"TickDate": f"/Date({t0 + i * 1000})/", "Price": base + (sp if side == "ASK" else 0)} for i in range(5)]
        return httpx.Response(200, json={"PriceTicks": ticks})
    raise AssertionError("unexpected call " + p)


def test_probe_reads_spreads_and_never_orders(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    monkeypatch.setenv("FOREXCOM_USERNAME", "u")
    monkeypatch.setenv("FOREXCOM_PASSWORD", "secret-pw")
    monkeypatch.setenv("FOREXCOM_APPKEY", "k")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["probe", "--days", "2", "--out", str(tmp_path / "out")])
    P.main()
    out = capsys.readouterr().out
    rep = (tmp_path / "out" / "report.md").read_text()
    assert "Spot Gold (id 1)" in rep and "US 30" in rep and "US Tech 100" in rep
    S = pd.read_csv(tmp_path / "out" / "spreads.csv.gz")
    assert abs(S[S.symbol == "XAUUSD"]["median"].iloc[0] - 0.30) < 1e-9
    assert abs(S[S.symbol == "US30"]["median"].iloc[0] - 2.0) < 1e-9
    assert "secret-pw" not in out + rep and "S1" not in rep
    assert not [p for m, p in SEEN if "order" in p.lower()]           # read-only: no order endpoint ever touched
    assert {m for m, p in SEEN if not p.endswith("/session")} == {"GET"}
