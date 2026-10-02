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
        "book": "shadow" if getattr(ctx, "is_shadow", False) else "live",
        "selection_mode": getattr(ctx, "selection_mode", "hourly_pick"),
        "shadow": getattr(ctx, "shadow_info", None),
    }


def compare_start(ctx) -> str | None:
    """When the shadow book started recording (first thing it journaled) — comparisons start there."""
    sh = getattr(ctx, "shadow", None)
    if sh is None:
        return None
    row = sh.journal.db.execute("SELECT MIN(t) FROM (SELECT MIN(ts) t FROM signals UNION ALL "
                                "SELECT MIN(opened) t FROM trades)").fetchone()
    return row[0] if row and row[0] else None


def compare(ctx, rng: str) -> dict:
    sh = ctx.shadow
    now = ctx.state.now
    start = compare_start(ctx)
    since = {"today": now.normalize().isoformat() if now is not None else None,
             "week": (now.normalize() - __import__("pandas").Timedelta(days=6)).isoformat() if now is not None else None,
             "all": None}.get(rng)
    if start and (since is None or start > since):
        since = start
    books = {}
    for key, c in (("live", ctx), ("shadow", sh)):
        sm = c.journal.summary(since=since)
        days = c.journal.daily(since[:10] if since else None)
        sm["worst_day"] = min((d["pnl"] for d in days.values()), default=0.0)
        sm["best_day"] = max((d["pnl"] for d in days.values()), default=0.0)
        sm["days"] = days
        sm["mode"] = getattr(c, "selection_mode", "")
        sm["funnel"] = c.journal.signal_funnel(since)
        sm["open"] = sum(1 for p in c.state.positions.values() if p.status == "open")
        books[key] = sm
    all_days = sorted(set(books["live"]["days"]) | set(books["shadow"]["days"]))
    cum = {"live": 0.0, "shadow": 0.0}
    rows, curve = [], []
    for d in all_days:
        row = {"date": d}
        for k in ("live", "shadow"):
            x = books[k]["days"].get(d, {"trades": 0, "pnl": 0.0, "r": 0.0})
            row[k] = {"trades": x["trades"], "pnl": x["pnl"], "r": x["r"]}
            cum[k] = round(cum[k] + x["r"], 2)
        curve.append({"date": d, "live": cum["live"], "shadow": cum["shadow"]})
        rows.append(row)
    for k in books:
        books[k].pop("days")
    return {"range": rng, "since": since, "started": start, "books": books, "days": rows[::-1], "curve": curve}


def build_app(ctx) -> FastAPI:
    app = FastAPI(title="FX-Agents", docs_url=None, redoc_url=None)

    def bk(request):
        """?book=shadow → the shadow book's context (same endpoints, same shapes)."""
        if request.query_params.get("book") == "shadow" and getattr(ctx, "shadow", None) is not None:
            return ctx.shadow
        return ctx
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
        return JSONResponse(snapshot(bk(request)))

    @app.get("/api/trades")
    async def api_trades(request: Request, limit: int = 200):
        need(request)
        rows = bk(request).journal.trades(limit)
        for r in rows:
            r["events"] = json.loads(r["events"] or "[]")
        return rows

    @app.get("/api/signals")
    async def api_signals(request: Request, limit: int = 100):
        need(request)
        return bk(request).journal.signals(limit)

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
        return {"days": bk(request).journal.daily(start, end),
                "events": [{"date": e["ts"].strftime("%Y-%m-%d"), "title": e["title"], "tier": e["tier"],
                            "time": e["ts"].strftime("%H:%M")} for e in (ctx.news.events if ctx.news else [])]}

    @app.get("/api/day/{day}")
    async def api_day(day: str, request: Request):
        need(request)
        return {"trades": bk(request).journal.day_trades(day),
                "events": [{"title": e["title"], "tier": e["tier"], "time": e["ts"].strftime("%H:%M")}
                           for e in (ctx.news.events if ctx.news else []) if e["ts"].strftime("%Y-%m-%d") == day]}

    @app.get("/api/journal.csv")
    async def journal_csv(request: Request):
        need(request)
        c = bk(request)
        rows = c.journal.trades(100000)
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=[k for k in rows[0] if k != "events"], extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename="
                                          + ("journal_shadow.csv" if c is not ctx else "journal.csv")})

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
        # TradingView cancels webhooks that take > 3 s: acknowledge now, process in the background
        asyncio.create_task(ctx.bus.publish("tv_signal", body))
        return {"ok": True, "queued": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        t = websocket.query_params.get("token") or websocket.cookies.get("fx_token")
        if not authed(t):
            await websocket.close(code=4401)
            return
        c = ctx.shadow if websocket.query_params.get("book") == "shadow" and getattr(ctx, "shadow", None) else ctx
        await websocket.accept()
        try:
            while True:
                await websocket.send_text(json.dumps(snapshot(c), default=str))
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/api/compare")
    async def api_compare(request: Request, range: str = "week"):
        need(request)
        if getattr(ctx, "shadow", None) is None:
            return {"enabled": False}
        return {"enabled": True, **compare(ctx, range if range in ("today", "week", "all") else "week")}

    @app.get("/healthz")
    async def health():
        return {"ok": True}

    return app
