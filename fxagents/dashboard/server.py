"""Live dashboard (FastAPI + WebSocket). Responsive: works on the phone and the laptop.

Security: set DASHBOARD_TOKEN. Then every page/API/WebSocket needs the token (open
http://host:8088/?token=… once; it is stored in an HttpOnly cookie). Controls (pause,
resume, flatten) always need it. Reach it privately over Tailscale; if you ever expose it
through Cloudflare, put Cloudflare Access in front as well.
"""
from __future__ import annotations

import asyncio
import csv
import hmac
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

STATIC = Path(__file__).parent / "static"


def snapshot(ctx) -> dict:
    st, cfg = ctx.state, ctx.cfg
    inst = cfg["instruments"]
    positions = [p.to_public(float(inst[p.symbol]["multiplier"])) for p in st.positions.values() if p.status == "open"]
    unreal = sum(p["unrealized"] for p in positions)
    open_risk = 0.0
    for p in st.positions.values():
        if p.status == "open":
            open_risk += max(0.0, (p.avg_entry - p.stop) * p.side) * p.open_qty * float(inst[p.symbol]["multiplier"])
    today = ctx.journal.summary(since=(st.now.normalize().isoformat() if st.now is not None else None))
    board = []
    for sym, per in st.strategy_stats.items():
        for sid, s in per.items():
            board.append({"symbol": sym, "id": sid, "status": s.get("status"), "n": s["n"],
                          "win_rate": s["win_rate"], "expectancy": s["expectancy"], "pf": s["pf"],
                          "recent_exp": s["recent_exp"], "rr": s.get("rr"), "tf": s.get("tf"),
                          "hour": s["by_hour"].get(st.now.hour if st.now is not None else -1)})
    return {
        "mode": cfg["mode"], "now": st.now.isoformat() if st.now is not None else None,
        "equity": round(st.equity, 2), "day_pnl": round(st.equity - (st.day_start_equity or st.equity), 2),
        "realized_today": round(st.realized_today, 2), "unrealized": round(unreal, 2),
        "open_risk": round(open_risk, 2), "trading_enabled": st.trading_enabled, "halt_reason": st.halt_reason,
        "today": today, "positions": positions, "prices": st.last_prices,
        "selections": st.selections, "board": board,
        "heartbeats": {k: round(v, 1) for k, v in st.heartbeats.items()},
        "alerts": list(st.alerts)[:40], "learner": list(st.learner_log)[:30],
        "decisions": [{k: d.get(k) for k in ("ts", "kind", "source", "symbol", "strategy", "latency_ms", "outputs")}
                      for d in list(st.decisions)[:40]],
        "equity_curve": list(st.equity_curve)[-600:],
        "registry": st.strategy_registry, "jev_live": ctx.jev.live,
        "bias": st.bias, "news": st.news[:40], "news_source": st.news_source, "news_block": st.news_block,
        "min_align": cfg["bias"]["min_align"],
    }


def build_app(ctx) -> FastAPI:
    app = FastAPI(title="FX-Agents", docs_url=None, redoc_url=None)
    token = (ctx.cfg["dashboard"].get("token") or "").strip()
    tv_secret = (ctx.cfg["tradingview"].get("webhook_secret") or "").strip()

    def authed(req_token: str | None) -> bool:
        return not token or (req_token is not None and hmac.compare_digest(req_token, token))

    def tok(request: Request) -> str | None:
        return request.query_params.get("token") or request.cookies.get("fx_token") or \
            request.headers.get("x-token")

    def need(request: Request, always: bool = False):
        if always and not token:
            raise HTTPException(403, "set DASHBOARD_TOKEN to enable controls")
        if not authed(tok(request)):
            raise HTTPException(401, "token required")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if not authed(tok(request)):
            return HTMLResponse("<meta name=viewport content='width=device-width'><form style='font:16px system-ui;"
                                "margin:20vh auto;max-width:320px'><p>FX-Agents</p><input name=token type=password "
                                "placeholder='Dashboard token' style='width:100%;padding:10px'><button "
                                "style='margin-top:8px;padding:10px;width:100%'>Open</button></form>", 401)
        resp = HTMLResponse((STATIC / "index.html").read_text())
        if request.query_params.get("token"):
            resp.set_cookie("fx_token", request.query_params["token"], httponly=True, samesite="strict",
                            max_age=60 * 60 * 24 * 30)
        return resp

    @app.get("/api/state")
    async def api_state(request: Request):
        need(request)
        return JSONResponse(snapshot(ctx))

    @app.get("/api/trades")
    async def api_trades(request: Request, limit: int = 200):
        need(request)
        rows = ctx.journal.trades(limit)
        for r in rows:
            r["events"] = json.loads(r["events"] or "[]")
        return rows

    @app.get("/api/signals")
    async def api_signals(request: Request, limit: int = 100):
        need(request)
        return ctx.journal.signals(limit)

    @app.get("/api/decisions")
    async def api_decisions(request: Request, limit: int = 100):
        need(request)
        rows = ctx.journal.decisions(limit)
        for r in rows:
            r["inputs"], r["outputs"] = json.loads(r["inputs"] or "null"), json.loads(r["outputs"] or "null")
        return rows

    @app.get("/api/calendar")
    async def api_calendar(request: Request, start: str | None = None, end: str | None = None):
        need(request)
        return {"days": ctx.journal.daily(start, end),
                "events": [{"date": e["ts"].strftime("%Y-%m-%d"), "title": e["title"], "tier": e["tier"],
                            "time": e["ts"].strftime("%H:%M")} for e in (ctx.news.events if ctx.news else [])]}

    @app.get("/api/day/{day}")
    async def api_day(day: str, request: Request):
        need(request)
        return {"trades": ctx.journal.day_trades(day),
                "events": [{"title": e["title"], "tier": e["tier"], "time": e["ts"].strftime("%H:%M")}
                           for e in (ctx.news.events if ctx.news else []) if e["ts"].strftime("%Y-%m-%d") == day]}

    @app.get("/api/journal.csv")
    async def journal_csv(request: Request):
        need(request)
        rows = ctx.journal.trades(100000)
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=[k for k in rows[0] if k != "events"], extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=journal.csv"})

    @app.post("/api/trades/{trade_id}/note")
    async def note(trade_id: str, request: Request):
        need(request, always=True)
        body = await request.json()
        ctx.journal.set_note(trade_id, str(body.get("note", ""))[:2000])
        return {"ok": True}

    @app.post("/api/control/{action}")
    async def control(action: str, request: Request):
        need(request, always=True)
        st = ctx.state
        if action == "pause":
            st.trading_enabled, st.halt_reason = False, "paused from dashboard"
        elif action == "resume":
            st.trading_enabled, st.halt_reason = True, ""
        elif action == "flatten":
            st.trading_enabled, st.halt_reason = False, "flattened from dashboard"
            await ctx.bus.publish("flatten_all", "dashboard")
        else:
            raise HTTPException(400, "unknown action")
        st.alert("warn", f"control: {action}")
        return {"ok": True, "trading_enabled": st.trading_enabled}

    @app.post("/webhook/tradingview")
    async def tradingview(request: Request):
        """TradingView alert message (JSON), e.g.
        {"secret":"…","symbol":"NDQ","side":"buy","price":{{close}},"stop":24410.5,"strategy":"my_pine"}"""
        body = await request.json()
        if not tv_secret or not hmac.compare_digest(str(body.get("secret", "")), tv_secret):
            raise HTTPException(401, "bad secret")
        if body.get("symbol") not in ctx.cfg["instruments"]:
            raise HTTPException(400, "unknown symbol")
        await ctx.bus.publish("tv_signal", body)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        t = websocket.query_params.get("token") or websocket.cookies.get("fx_token")
        if not authed(t):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            while True:
                await websocket.send_text(json.dumps(snapshot(ctx), default=str))
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/healthz")
    async def health():
        return {"ok": True}

    return app
