"""Live dashboard (FastAPI + WebSocket). Responsive: works on the phone and the laptop.

Security: set DASHBOARD_TOKEN. Then every page/API/WebSocket needs the token (open
http://host:8088/?token=… once; it is stored in an HttpOnly cookie). Controls (pause,
resume, flatten) always need it. Reach it privately over Tailscale; if you ever expose it
through Cloudflare, put Cloudflare Access in front as well.
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import hmac
import io
import json
from pathlib import Path

import pandas as pd

from .. import units
from . import biasgrid, extras, ghosts, insights
from .ask import Asker
from .lessons import LessonWriter
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

STATIC = Path(__file__).parent / "static"


def snapshot(ctx) -> dict:
    st, cfg = ctx.state, ctx.cfg
    inst = cfg["instruments"]
    positions = [units.position(cfg, p.to_public(float(inst[p.symbol]["multiplier"])))
                 for p in st.positions.values() if p.status == "open"]
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
        "book": getattr(ctx, "book_key", "shadow") if getattr(ctx, "is_shadow", False) else "live",
        "selection_mode": getattr(ctx, "selection_mode", "hourly_pick"),
        "shadow": getattr(ctx, "shadow_info", None),
        "flow": insights.flow(ctx),
    }


def shadow_of(ctx, name: str | None):
    """'shadow' (older links) → the first shadow book; a mode name → that book; anything else → None."""
    shs = getattr(ctx, "shadows", None) or {}
    if not name or name == "live":
        return None
    if name == "shadow":
        return getattr(ctx, "shadow", None)
    return shs.get(name)


def compare_start(ctx, sh=None) -> str | None:
    """When a shadow book started recording (first thing it journaled) — comparisons start there."""
    sh = sh if sh is not None else getattr(ctx, "shadow", None)
    if sh is None:
        return None
    row = sh.journal.db.execute("SELECT MIN(t) FROM (SELECT MIN(ts) t FROM signals UNION ALL "
                                "SELECT MIN(opened) t FROM trades)").fetchone()
    return row[0] if row and row[0] else None


def _range_since(now, rng: str) -> str | None:
    import pandas as pd
    if now is None:
        return None
    return {"today": now.normalize().isoformat(), "week": (now.normalize() - pd.Timedelta(days=6)).isoformat()}.get(rng)


def league(ctx, rng: str) -> dict:
    """Every book (real + each shadow) over the range. Each book counts from the range start or its OWN first
    record, whichever is later (its `since`), so adding a new book never hides the other books' trades.
    (It used to clip every book to the youngest book's start — a book added at 13:00 blanked the morning.)"""
    shs = getattr(ctx, "shadows", None) or {}
    since = _range_since(ctx.state.now, rng)
    rows = []
    for key, c in (("live", ctx), *shs.items()):
        own = compare_start(ctx, c) if key != "live" else None
        s_b = own if own and (since is None or own > since) else since
        sm = c.journal.summary(since=s_b)
        rows.append({"book": key, "mode": getattr(c, "selection_mode", ""), "trades": sm["trades"],
                     "wins": round(sm["trades"] * sm["win_rate"]), "win_rate": sm["win_rate"], "sum_r": sm["sum_r"],
                     "avg_r": sm.get("avg_r", 0.0), "pnl": sm["pnl"], "since": s_b,
                     "open": sum(1 for p in c.state.positions.values() if p.status == "open")})
    return {"since": since, "rows": rows}


def compare(ctx, rng: str, sh=None) -> dict:
    sh = sh if sh is not None else ctx.shadow
    now = ctx.state.now
    start = compare_start(ctx, sh)
    since = _range_since(now, rng)
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
    return {"range": rng, "since": since, "started": start, "books": books, "days": rows[::-1], "curve": curve,
            "vs": getattr(sh, "book_key", "shadow"), "league": league(ctx, rng)}


def build_app(ctx) -> FastAPI:
    books = lambda: [ctx, *(getattr(ctx, "shadows", None) or {}).values()]

    lw = LessonWriter(ctx) if getattr(ctx, "journal", None) is not None else None

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        """Play out passed and taken setups every 5 minutes, before the bars roll out of memory (read-only)."""
        async def run():
            while True:
                for c in books():
                    try:
                        while ghosts.resolve(c) >= 400:
                            await asyncio.sleep(0)
                    except Exception:  # noqa: BLE001
                        pass
                await asyncio.sleep(300)
        task = asyncio.create_task(run()) if getattr(ctx, "journal", None) is not None else None
        ltask = asyncio.create_task(lw.run()) if lw is not None and lw.on else None
        try:
            yield
        finally:
            for t in (task, ltask):
                if t:
                    t.cancel()

    app = FastAPI(title="FX-Agents", docs_url=None, redoc_url=None, lifespan=lifespan)
    for c in books():
        insights.install_tap(c)                 # Mission Control: every bus message, read-only


    def bk(request):
        """?book=<mode> (or the older ?book=shadow) → that shadow book's context (same endpoints, same shapes)."""
        return shadow_of(ctx, request.query_params.get("book")) or ctx
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

    def login_page(error: str = "", status: int = 401) -> HTMLResponse:
        msg = f"<p style='color:#f87171;font-size:14px'>{error}</p>" if error else ""
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>FX-Agents</title><body style='margin:0;background:#0d0f14;color:#f3f5f9;font:16px system-ui'>"
            "<form method=post action='login' style='margin:18vh auto;max-width:320px;padding:0 16px'>"
            "<h2 style='margin:0 0 6px'>FX-Agents</h2><p style='color:#aab2c2;margin:0 0 16px;font-size:14px'>"
            "Enter the dashboard token (DASHBOARD_TOKEN in .env). This device will remember it.</p>"
            f"{msg}<input name=username value=fx-agents autocomplete=username readonly tabindex=-1 aria-hidden=true "
            "style='position:absolute;left:-9999px;width:1px;height:1px;opacity:0'>"
            "<input name=token type=password autocomplete=current-password autofocus required "
            "style='width:100%;box-sizing:border-box;padding:12px;border-radius:10px;border:1px solid #313848;"
            "background:#161a23;color:inherit;font:inherit' placeholder='Dashboard token'>"
            "<button style='margin-top:10px;padding:12px;width:100%;border:0;border-radius:10px;background:#4f8ff7;"
            "color:#fff;font:600 15px system-ui'>Open dashboard</button></form>", status)

    def with_cookie(resp, request: Request, value: str):
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        # Lax, not Strict: Strict drops the cookie whenever the page is opened from another app or site (a
        # notification link, Messages, the home-screen launcher on some iOS versions), which looked like "it
        # forgot me". Lax still blocks cross-site POSTs, so Pause/Flatten stay protected. A year, renewed on
        # every visit, so a device you use never has to sign in again.
        resp.set_cookie("fx_token", value, httponly=True, samesite="lax", secure=secure,
                        max_age=60 * 60 * 24 * 365, path="/")
        return resp

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        qtok = request.query_params.get("token")
        if qtok is not None:
            # old ?token= links still work once: set the cookie and bounce to the clean address
            if authed(qtok):
                return with_cookie(RedirectResponse("./", status_code=303), request, qtok)
            return login_page("That token isn't right.")
        have = request.cookies.get("fx_token")
        if not authed(have or request.headers.get("x-token")):
            return login_page()
        page = HTMLResponse((STATIC / "index.html").read_text())
        return with_cookie(page, request, have) if token and have else page    # sliding expiry

    @app.post("/login")
    async def login(request: Request):
        from urllib.parse import parse_qs
        form = parse_qs((await request.body()).decode(errors="ignore"))
        value = (form.get("token") or [""])[0].strip()
        if not token or not authed(value):
            await asyncio.sleep(1.0)       # slow down guessing
            return login_page("That token isn't right.")
        return with_cookie(RedirectResponse("./", status_code=303), request, value)

    @app.get("/logout")
    async def logout():
        resp = RedirectResponse("./", status_code=303)
        resp.delete_cookie("fx_token", path="/")
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
            r["draw"] = json.loads(r["draw"]) if r.get("draw") else None
            units.trade(bk(request).cfg, r)
        return rows

    @app.get("/api/now")
    async def api_now(request: Request):
        need(request)
        return JSONResponse(insights.now_info(ctx))

    @app.get("/api/evidence")
    async def api_evidence(request: Request):
        need(request)
        return JSONResponse(insights.evidence(ctx))

    @app.get("/api/story/{trade_id}")
    async def api_story(trade_id: str, request: Request):
        need(request)
        c = bk(request)
        out = insights.story(ctx, c, trade_id)
        if out is None:
            raise HTTPException(404, "no such trade")
        if out.get("lesson") is None and lw is not None:
            try:
                out["lesson"] = await lw.for_trade(c, trade_id)     # a closed trade without one gets it now
            except Exception:  # noqa: BLE001 — never fail the story over a lesson
                pass
        return JSONResponse(json.loads(json.dumps(out, default=str)))

    @app.get("/api/bars")
    async def api_bars(request: Request, symbol: str, start: str, end: str):
        need(request)
        if symbol not in ctx.cfg["instruments"]:
            raise HTTPException(400, "unknown symbol")
        return JSONResponse(insights.bars(ctx, symbol, start, end))

    asker = Asker(ctx)

    @app.post("/api/ask")
    async def api_ask(request: Request):
        need(request)
        body = await request.json()
        out = await asker.answer(str(body.get("question", "")), body.get("history") or [])
        return JSONResponse(json.loads(json.dumps(out, default=str)))

    @app.get("/api/timeline")
    async def api_timeline(request: Request, day: str | None = None):
        need(request)
        return JSONResponse(json.loads(json.dumps(extras.timeline(ctx, bk(request), day), default=str)))

    @app.get("/api/atlas")
    async def api_atlas(request: Request):
        need(request)
        return JSONResponse(extras.atlas(ctx))

    @app.get("/api/patterns")
    async def api_patterns(request: Request, symbol: str, start: str, end: str, tf: int = 15):
        need(request)
        if symbol not in ctx.cfg["instruments"]:
            raise HTTPException(400, "unknown symbol")
        return JSONResponse(insights.patterns(ctx, symbol, start, end, tf))

    @app.get("/api/tradingview")
    async def api_tradingview(request: Request, symbol: str, days: int = 30):
        """Pine Script (v6) that draws the selected book's trades on this symbol in TradingView."""
        need(request)
        c = bk(request)
        if symbol not in c.cfg["instruments"]:
            raise HTTPException(400, "unknown symbol")
        book = request.query_params.get("book") or "live"
        return JSONResponse({"symbol": symbol, "tv_symbol": extras.tv_symbol(c.cfg, symbol),
                             "script": extras.pine_script(c.cfg, c, symbol, book, max(1, min(days, 365)))})

    @app.get("/api/recap")
    async def api_recap(request: Request, day: str | None = None, ai: int = 0):
        need(request)
        rc = json.loads(json.dumps(extras.recap(ctx, day), default=str))
        if ai:
            rc.update(await asker.narrate(rc))
        else:
            rc["source"] = "facts"
        return JSONResponse(rc)

    # ── home-screen app (public: no account data in these files) ──
    @app.get("/manifest.webmanifest")
    async def manifest():
        return JSONResponse({"name": "FX-Agents", "short_name": "FX-Agents", "start_url": "./", "scope": "./",
                             "display": "standalone", "background_color": "#0c101b", "theme_color": "#0c101b",
                             "description": "Your trading agents, live.",
                             "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                                       {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                                       {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]},
                            media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        return PlainTextResponse((STATIC / "sw.js").read_text(), media_type="application/javascript",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/lib/{name}.js")
    async def lib(name: str):
        """Self-hosted third-party scripts (static/lib; see NOTICE.txt)."""
        from fastapi.responses import FileResponse
        f = STATIC / "lib" / f"{name}.js"
        if not name.replace("-", "").replace(".", "").isalnum() or not f.exists():
            raise HTTPException(404)
        return FileResponse(f, media_type="application/javascript", headers={"Cache-Control": "max-age=604800"})

    @app.get("/fonts/{name}.woff2")
    async def font(name: str):
        from fastapi.responses import FileResponse
        if name not in ("geist", "bricolage"):
            raise HTTPException(404)
        return FileResponse(STATIC / "fonts" / f"{name}.woff2", media_type="font/woff2",
                            headers={"Cache-Control": "public, max-age=2592000, immutable"})

    @app.get("/{name}.png")
    async def icon(name: str):
        from fastapi.responses import FileResponse
        if name not in ("icon-192", "icon-512", "icon-maskable-512", "apple-touch-icon"):
            raise HTTPException(404)
        return FileResponse(STATIC / f"{name}.png", media_type="image/png", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/ghosts")
    async def api_ghosts(request: Request, symbol: str | None = None, start: str | None = None, end: str | None = None,
                         since: str | None = None):
        need(request)
        c = bk(request)
        ghosts.resolve(c, limit=200)
        return JSONResponse({"scorecard": ghosts.scorecard(c, since), "recent": ghosts.recent(c, symbol, start, end)})

    @app.get("/api/analyst")
    async def api_analyst(request: Request):
        """Trade analyst (shadow): per-check scorecard of its advice vs what the trades really did, + recent verdicts."""
        need(request)
        from ..agents.analyst import scorecard
        c = bk(request)
        if getattr(c, "journal", None) is None:
            return JSONResponse({"n_trades": 0, "checks": [], "recent": []})
        return JSONResponse(scorecard(c.journal))

    @app.get("/api/jev_advice")
    async def api_jev_advice(request: Request):
        """Jev trade adviser (shadow): its hold / cut / add calls on open trades, scored against how they finished."""
        need(request)
        from ..agents.jev_advisor import scorecard as jsc
        c = bk(request)
        if getattr(c, "journal", None) is None:
            return JSONResponse({"n_trades": 0, "actions": [], "recent": []})
        return JSONResponse(jsc(c.journal))

    @app.get("/api/dynamic")
    async def api_dynamic(request: Request):
        """Shadow review gate (Oct 26 2026): arms A-D scored on closed trades, plus the latest reviews. Reading only."""
        need(request)
        from ..dynamic import score as dscore
        from ..dynamic.providers import PROMPT_VERSION
        c = bk(request)
        if getattr(c, "journal", None) is None:
            return JSONResponse({"candidates": 0, "arms": {}, "recent": []})
        dyn = c.cfg.get("dynamic") or {}
        out = dscore.scorecard(c.journal, c.cfg, getattr(c, "book_key", None) or "live")
        out["recent"] = dscore.recent_reviews(c.journal, 50)
        out["config"] = {"enabled": bool(dyn.get("enabled")), "books": dyn.get("books"), "claude_model": dyn.get("claude_model"),
                         "openai_model": dyn.get("openai_model") or None, "prompt_version": PROMPT_VERSION}
        return JSONResponse(json.loads(json.dumps(out, default=str)))

    @app.get("/api/bias_grid")
    async def api_bias_grid(request: Request):
        need(request)
        return JSONResponse(biasgrid.grid(bk(request)))

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

    @app.get("/api/books_daily")
    async def api_books_daily(request: Request):
        """Every book's closed-trade results per day (Performance → Books): the account and each shadow book,
        from its own first record, so books of different ages compare on their own dates."""
        need(request)
        out = []
        for key, c in (("live", ctx), *(getattr(ctx, "shadows", None) or {}).items()):
            out.append({"book": key, "mode": getattr(c, "selection_mode", ""), "days": c.journal.daily(),
                        "open": sum(1 for p in c.state.positions.values() if p.status == "open")})
        return {"books": out}

    @app.get("/api/day/{day}")
    async def api_day(day: str, request: Request):
        need(request)
        return {"trades": [units.trade(bk(request).cfg, t) for t in bk(request).journal.day_trades(day)],
                "events": [{"title": e["title"], "tier": e["tier"], "time": e["ts"].strftime("%H:%M")}
                           for e in (ctx.news.events if ctx.news else []) if e["ts"].strftime("%Y-%m-%d") == day]}

    @app.get("/api/journal.csv")
    async def journal_csv(request: Request):
        need(request)
        c = bk(request)
        rows = [units.trade(c.cfg, r) for r in c.journal.trades(100000)]
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=[k for k in rows[0] if k != "events"], extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename="
                                          + (f"journal_{getattr(c, 'book_key', 'shadow')}.csv" if c is not ctx else "journal.csv")})

    @app.post("/api/trades/{trade_id}/note")
    async def note(trade_id: str, request: Request):
        need(request, always=True)
        body = await request.json()
        bk(request).journal.set_note(trade_id, str(body.get("note", ""))[:2000])
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
        c = shadow_of(ctx, websocket.query_params.get("book")) or ctx
        await websocket.accept()
        try:
            while True:
                await websocket.send_text(json.dumps(snapshot(c), default=str))
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/api/setup_map")
    async def api_setup_map(request: Request, symbol: str = "ALL", tf: str = "all", weekday: str = "all"):
        need(request)
        h = getattr(ctx, "setup_map", None)
        if h is None:
            return {"status": {"state": "off"}}
        now = ctx.state.now
        out = {"status": h.status, "symbols": list(ctx.cfg["instruments"]),
               "tfs": [str(t).replace("min", "m") for t in ctx.cfg["timeframes"]["entry"]],
               "hour": now.hour if now is not None else None, "weekday": now.dayofweek if now is not None else None}
        if h.map is not None:
            tfl = {"5m": "5m", "15m": "15m"}.get(tf, "all")
            out["grid"] = h.map.grid(symbol if symbol in ctx.cfg["instruments"] else "ALL", tfl, weekday)
            # columns = hours that can trade (entry windows) plus any hour with history
            win = set()
            for w in ctx.cfg["sessions"]["entry_windows"]:
                a_, b_ = (int(x.split(":")[0]) for x in (w[0], w[1])) if isinstance(w, (list, tuple)) else (None, None)
                if a_ is not None:
                    win.update(range(a_, b_ + (0 if w[1].endswith(":00") else 1)))
            out["grid"]["hours"] = sorted(set(out["grid"]["hours"]) | win)
            if now is not None:
                syms = [symbol] if symbol in ctx.cfg["instruments"] else list(ctx.cfg["instruments"])
                # this hour if it can trade, otherwise the next hour that can (weekdays only)
                t, nxt = now.floor("h"), False
                for _ in range(24 * 4):
                    if t.dayofweek < 5 and t.hour in win:
                        break
                    t, nxt = t + pd.Timedelta(hours=1), True
                out["best_for"] = {"hour": t.hour, "weekday": t.dayofweek, "next": nxt}
                out["best_now"] = h.map.best_now([x.id for x in ctx.book.live()], syms, t.hour, t.dayofweek)
        return out

    @app.post("/api/setup_map/rebuild")
    async def api_setup_map_rebuild(request: Request):
        need(request, always=True)
        a = getattr(ctx, "setup_map_agent", None)
        if a is None:
            raise HTTPException(400, "setup map is off")
        return {"started": a.rebuild(), "status": ctx.setup_map.status}

    def _real(sid, since):
        n, tot = 0, 0.0
        for j in [ctx.journal] + [sh.journal for sh in (getattr(ctx, "shadows", None) or {}).values()]:
            s_ = j.live_stats(strategy=sid, since=since)
            n += s_["n"]; tot += s_["n"] * s_["expectancy"]
        return {"n": n, "expectancy": round(tot / n, 3) if n else 0.0}

    @app.get("/api/learner")
    async def api_learner(request: Request):
        """Learner-made versions: what changed, forward record vs parent, real trades, live vetting."""
        need(request)
        rows = []
        for r in ctx.journal.strategy_rows():
            spec = json.loads(r["spec"] or "{}")
            if not str(spec.get("origin", "")).startswith("learner:"):
                continue
            sid, meta = spec.get("id") or r["id"], spec.get("meta") or {}
            parent = meta.get("parent") or spec["origin"].split(":", 1)[1]
            since = spec.get("created")
            rows.append({"id": sid, "status": r["status"], "parent": parent, "kind": meta.get("kind"),
                         "change": meta.get("change"), "created": since, "updated": r["updated"], "note": r["notes"],
                         "vetted": bool(spec.get("vetted")), "oos_gain_r": meta.get("oos_gain_r"),
                         "jev_robust": meta.get("jev_robust"),
                         "forward": ctx.journal.forward_stats(sid, since),
                         "parent_forward": ctx.journal.forward_stats(parent, since),
                         "real": _real(sid, since)})
        rows.sort(key=lambda x: x["created"] or "", reverse=True)
        ec = ctx.cfg["evaluator"]
        return {"rows": rows, "mode": ctx.cfg["mode"], "require_vetting": bool(ctx.book.require_vetting),
                "live_requires_vetting": bool((ctx.cfg.get("learner") or {}).get("live_requires_vetting", True)),
                "min_trades_promote": ec["min_trades_promote"], "promote_margin_r": ec["promote_margin_r"]}

    @app.post("/api/strategies/{sid}/vet")
    async def api_vet(sid: str, request: Request):
        need(request, always=True)
        if getattr(ctx, "is_shadow", False) or sid not in ctx.book.items:
            raise HTTPException(404, "unknown or retired version")
        st = ctx.book.items[sid]
        if not st.origin.startswith("learner:"):
            raise HTTPException(400, "only learner-made versions need vetting")
        body = await request.json()
        ctx.book.set_vetted(sid, bool(body.get("vetted", True)), ctx.state.now.isoformat(timespec="seconds"))
        ctx.state.alert("warn", f"{sid} {'vetted for live' if st.vetted else 'vetting removed'}")
        return {"ok": True, "vetted": st.vetted}

    def _bt_dir():
        from ..replay import backtests_dir
        return backtests_dir(ctx.cfg)

    @app.get("/api/research")
    async def api_research(request: Request):
        """Strategy research + playbook validation (written by run_research.py / the playbook refresh)."""
        need(request)
        from fxagents.research import research_dir
        p = research_dir(ctx.cfg) / "summary.json"
        if not p.exists():
            return {"ready": False}
        out = json.loads(p.read_text())
        out["ready"] = True
        # pinned cells (config playbook.pinned) trade every week: show them even if research predates the pin
        from fxagents import playbook as _pbk
        if isinstance(out.get("playbook"), dict):
            out["playbook"] = _pbk.with_pinned(ctx.cfg, out["playbook"])
            for c in out["playbook"]["cells"]:
                inst = (out.get("instruments") or {}).get(c["sym"])
                if c.get("pinned") and inst is not None and not any(x.get("id") == c["id"] for x in inst.get("cells", [])):
                    inst.setdefault("cells", []).append(c)
        # how the playbook has done since it went live (whichever book runs it)
        live = {}
        for name, c in (("live", ctx), *(("shadow", sh) for sh in (getattr(ctx, "shadows", None) or {}).values())):
            if c is None or getattr(c, "selection_mode", "") != "playbook":
                continue
            rows = [t for t in c.journal.trades(limit=2000) if t.get("status") == "closed" and "@pb-" in (t.get("strategy") or "")]
            rs = [float(t.get("r_multiple") or 0) for t in rows]
            live[name] = {"trades": len(rs), "win_rate": round(sum(r > 0 for r in rs) / len(rs), 3) if rs else 0.0,
                          "sum_r": round(sum(rs), 2), "pnl": round(sum(float(t.get("realized") or 0) for t in rows), 2),
                          "by_symbol": {s: round(sum(float(t.get("r_multiple") or 0) for t in rows if t.get("symbol") == s), 2)
                                        for s in sorted({t.get("symbol") for t in rows})}}
        out["live"] = live
        pb = getattr(ctx, "playbook", None)
        out["running"] = pb.summary() if pb is not None and pb.data.get("cells") is not None else None
        return out

    @app.get("/api/backtests")
    async def api_backtests(request: Request):
        need(request)
        d, runs = _bt_dir(), []
        if d.exists():
            for r in sorted(d.iterdir(), reverse=True):
                mp = r / "meta.json"
                if not mp.exists():
                    continue
                try:
                    m = json.loads(mp.read_text())
                    pp = r / "progress.json"
                    if pp.exists():
                        m["progress"] = json.loads(pp.read_text())
                    m["has_report"] = (r / "report.json").exists()
                    runs.append(m)
                except (OSError, ValueError):
                    continue
        return {"runs": runs[:50], "history_ready": (Path(ctx.cfg["storage"]["db_path"]).parent / "history").exists()}

    @app.get("/api/backtests/{rid}")
    async def api_backtest(rid: str, request: Request):
        need(request)
        if not rid.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(400, "bad id")
        p = _bt_dir() / rid / "report.json"
        if not p.exists():
            raise HTTPException(404, "no report yet")
        return JSONResponse(json.loads(p.read_text()))

    # ── backtest app (fxagents/bt): plugins in btplugins/, jobs run by the fxbt worker, results in data/bt ──
    import re as _re

    def _rid(rid: str) -> str:
        if not _re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", rid):
            raise HTTPException(400, "bad run id")
        return rid

    @app.get("/api/bt")
    async def api_bt(request: Request):
        need(request)
        from ..bt import ledger
        return JSONResponse(await asyncio.to_thread(ledger.catalog))

    @app.post("/api/bt/run")
    async def api_bt_run(request: Request):
        need(request, always=True)
        from ..bt import ledger
        b = await request.json()
        params = b.get("params") or {}
        if not isinstance(params, dict):
            raise HTTPException(400, "params must be an object")
        try:
            rid = await asyncio.to_thread(ledger.enqueue, str(b.get("plugin", "")), str(b.get("dataset", "seen")),
                                          b.get("symbol") or None, params, "app", str(b.get("note") or ""))
        except (ValueError, PermissionError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))
        return {"id": rid}

    @app.post("/api/bt/cancel_all")
    async def api_bt_cancel_all(request: Request):
        need(request, always=True)
        from ..bt import ledger
        n, k = await asyncio.to_thread(ledger.cancel_all)
        return {"queued": n, "running": k}

    @app.post("/api/bt/run/{rid}/cancel")
    async def api_bt_cancel(rid: str, request: Request):
        need(request, always=True)
        from ..bt import ledger
        r = ledger.get(_rid(rid))
        if not r:
            raise HTTPException(404, "no such run")
        if r["status"] == "queued":
            ledger.update(rid, status="cancelled", stage="cancelled")
        elif r["status"] == "running":
            ledger.update(rid, status="cancel")
        return {"ok": True}

    @app.get("/api/bt/run/{rid}")
    async def api_bt_get(rid: str, request: Request):
        need(request)
        import gzip
        from ..bt import ledger
        r = ledger.get(_rid(rid))
        if not r:
            raise HTTPException(404, "no such run")
        d = ledger.run_dir(rid)
        out = {"run": r, "summary": None, "trades": []}
        if (d / "summary.json").exists():
            out["summary"] = json.loads((d / "summary.json").read_text())
        if (d / "trades.json.gz").exists():
            with gzip.open(d / "trades.json.gz", "rt") as fh:
                out["trades"] = json.load(fh)
        return JSONResponse(out)

    @app.get("/api/bt/run/{rid}/{what}")
    async def api_bt_file(rid: str, what: str, request: Request):
        need(request)
        from ..bt import ledger
        f = {"report": "report.md", "code": "code.py"}.get(what)
        p = ledger.run_dir(_rid(rid)) / (f or "-")
        if not f or not p.exists():
            raise HTTPException(404, "not found")
        return PlainTextResponse(p.read_text())

    @app.get("/api/bt/bars")
    async def api_bt_bars(request: Request, run: str, t0: str, t1: str, tf: str = "auto"):
        """Mid candles + bid/ask closes of a run's dataset between t0 and t1 (ISO times) — the trade chart."""
        need(request)
        from ..bt import data as btdata, ledger
        r = ledger.get(_rid(run))
        if not r:
            raise HTTPException(404, "no such run")
        try:
            a, b = pd.Timestamp(t0), pd.Timestamp(t1)
            a = a.tz_localize("UTC") if a.tzinfo is None else a
            b = b.tz_localize("UTC") if b.tzinfo is None else b
        except ValueError:
            raise HTTPException(400, "bad time")
        span = (b - a).total_seconds() / 60
        if span <= 0 or span > 60 * 24 * 120:
            raise HTTPException(400, "range must be 0–120 days")
        if tf == "auto":
            tf = next((x for x in (1, 5, 15, 60, 240) if span / x <= 1500), 1440)
        if str(tf) not in ("1", "5", "15", "60", "240", "1440"):
            raise HTTPException(400, "tf: 1, 5, 15, 60, 240, 1440 or auto")
        tf = int(tf)

        def build():
            m = btdata.window(r["dataset"], r["symbol"], a.value, b.value)
            if not len(m):
                return {"tf": tf, "bars": []}
            key = {60: "1h", 240: "4h", 1440: "1d"}.get(tf, tf)
            bb = m.bars(key)
            sp = pd.Series(m.spread, index=m.idx).resample(f"{tf}min").mean() if tf < 240 else None
            rows = []
            for i in range(len(bb)):
                st = int(bb.start.iloc[i] // 1_000_000_000)
                row = [st] + [round(float(bb[k].iloc[i]), 5) for k in "ohlc"]
                if sp is not None:
                    v = sp.get(pd.Timestamp(st, unit="s", tz="UTC"))
                    row.append(None if v is None or pd.isna(v) else round(float(v), 5))
                rows.append(row)
            return {"tf": tf, "bars": rows}
        return JSONResponse(await asyncio.to_thread(build))

    # ── strategy lab: candidates are tested before they reach the playbook ──
    lab_proc: dict = {}

    @app.get("/api/lab")
    async def api_lab(request: Request):
        need(request)
        from fxagents import lab
        from fxagents.strategies import ALL, SETUPS
        p = lab_proc.get("p")
        running = lab_proc.get("id") if p is not None and p.returncode is None else None
        pine = {x.stem for x in (Path(__file__).resolve().parents[2] / "pine").glob("*.pine")}
        return {"candidates": lab.load(ctx.cfg), "pins": lab.lab_pinned(ctx.cfg), "criteria": lab.CRITERIA,
                "running": running, "symbols": list(ctx.cfg["instruments"]), "pine": sorted(pine),
                "setups": {n: {"params": c.default_params, "grid": getattr(c, "param_grid", {}),
                               "description": c.description, "playbook": n in SETUPS} for n, c in sorted(ALL.items())}}

    @app.post("/api/lab")
    async def api_lab_add(request: Request):
        need(request, always=True)
        from fxagents import lab
        b = await request.json()
        try:
            c = lab.add(ctx.cfg, b.get("setup", ""), b.get("params") or {}, b.get("symbols") or None,
                        b.get("tfs") or None, str(b.get("note") or "")[:200])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return c

    @app.post("/api/lab/{cid}/{action}")
    async def api_lab_action(cid: str, action: str, request: Request):
        need(request, always=True)
        from fxagents import lab
        if not cid.isalnum() or lab.get(ctx.cfg, cid) is None:
            raise HTTPException(404, "no such candidate")
        b = {}
        try:
            b = await request.json()
        except Exception:  # noqa: BLE001
            pass
        if action == "run":
            p = lab_proc.get("p")
            if p is not None and p.returncode is None:
                raise HTTPException(409, "a lab test is already running")
            import sys
            args = ["nice", "-n", "15", sys.executable, "-m", "fxagents.lab", "run", cid]
            if b.get("days"):
                args += ["--days", str(int(b["days"]))]
            import re
            for k, flag in (("from", "--from"), ("until", "--until")):     # optional out-of-sample window
                if b.get(k):
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b[k])):
                        raise HTTPException(400, f"{k}: use YYYY-MM-DD")
                    args += [flag, str(b[k])]
            lab.update(ctx.cfg, cid, status="testing", error=None)
            import os
            logf = lab.lab_dir(ctx.cfg) / f"{cid}.log"
            fh = open(logf, "wb")
            env = {**os.environ, "FX_DB_PATH": str(ctx.cfg["storage"]["db_path"])}   # same lab folder as this app
            proc = await asyncio.create_subprocess_exec(*args, stdout=fh, stderr=asyncio.subprocess.STDOUT, env=env)
            lab_proc.update(id=cid, p=proc)

            async def watch():
                rc = await proc.wait()
                fh.close()
                c = lab.get(ctx.cfg, cid)
                if c and c.get("status") == "testing":
                    tail = logf.read_text(errors="replace")[-400:] if logf.exists() else ""
                    lab.update(ctx.cfg, cid, status="error", error=f"test stopped (exit {rc}): {tail}")
            asyncio.ensure_future(watch())
            return {"ok": True, "running": cid}
        try:
            if action == "promote":          # only cells that cleared the promotion gate, unless force (recorded)
                return lab.promote(ctx.cfg, cid, b.get("cells") or None, force=bool(b.get("force")))
            if action == "reject":
                return lab.unpromote(ctx.cfg, cid)
        except ValueError as e:
            raise HTTPException(400, str(e))
        raise HTTPException(404, "unknown action")

    @app.get("/api/pine/{name}")
    async def api_pine(name: str, request: Request):
        need(request)
        p = Path(__file__).resolve().parents[2] / "pine" / f"{name}.pine"
        if not name.replace("_", "").isalnum() or not p.exists():
            raise HTTPException(404, "no Pine script for that setup yet")
        return PlainTextResponse(p.read_text(), headers={"Content-Disposition": f"attachment; filename={name}.pine"})

    @app.get("/api/compare")
    async def api_compare(request: Request, range: str = "week", vs: str = "shadow"):
        need(request)
        if getattr(ctx, "shadow", None) is None:
            return {"enabled": False}
        sh = shadow_of(ctx, vs) or ctx.shadow
        return {"enabled": True, "book_list": list(getattr(ctx, "shadows", {}) or {}),
                **compare(ctx, range if range in ("today", "week", "all") else "week", sh)}

    @app.get("/healthz")
    async def health():
        return {"ok": True}

    return app
