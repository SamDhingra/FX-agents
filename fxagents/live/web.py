"""The live site's web layer (installed by dashboard.server.build_app when live_app.enabled).

Security model
  • Sign-in = user name + password + authenticator code. No shared token, no "remember the token" links.
  • Session cookie `fx_live`: random, HttpOnly, Secure behind https, SameSite=Lax, 30 days sliding; only its hash is
    stored server-side, so a copied database can't sign anyone in.
  • Every state-changing request under /api/ must carry the header `x-fx: 1` (a cross-site form can't add it) and,
    when the browser sends Origin, come from this site's own host.
  • Owner: everything the dashboard does today except backtesting (those endpoints answer 404 here), plus live
    controls and the members admin. Changing the copy switch / member risk cap needs a fresh authenticator code.
  • Member: only /api/m/* — their own account, key, limits, copies, and the bot's trades in R (no amounts of the
    owner's account). Every older endpoint is owner-only.
  • Every POST is written to the audit log (user, path, outcome) — bodies are not logged, so no key can end up there.
  • Responses carry no-store, frame-deny, no-sniff and a referrer policy.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .auth import AuthStore, otpauth_uri, store_for
from .members import RISK_STATEMENT, MemberStore, check_key
from .vault import vault_from_env

STATIC = Path(__file__).resolve().parent.parent / "dashboard" / "static"
COOKIE = "fx_live"
BLOCKED = ("/api/bt", "/api/backtests", "/api/lab", "/api/research", "/api/setup_map/rebuild")
TAGS = ["followed plan", "early entry", "late entry", "moved stop", "cut winner", "held loser", "news", "chop",
        "FOMO", "revenge", "great setup", "bad fill"]


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><meta name=robots content=noindex><link rel=stylesheet href='live.css'>"
        f"<body class=auth><main class=authbox>{body}</main></body></html>", status)


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def login_html(err: str = "", name: str = "", note: str = "", status: int = 401) -> HTMLResponse:
    return _page("FX-Agents Live · sign in", f"""
<div class=brand><span class=live-dot></span>FX-Agents <b>LIVE</b></div>
<p class=sub>Real-money account. Sign in with your password and the 6-digit code from your authenticator app.</p>
{f'<p class=ok>{_esc(note)}</p>' if note else ''}{f'<p class=err role=alert>{_esc(err)}</p>' if err else ''}
<form method=post action=login autocomplete=on>
 <label>User name<input name=name autocomplete=username required value="{_esc(name)}" autocapitalize=none spellcheck=false></label>
 <label>Password<input name=pw type=password autocomplete=current-password required></label>
 <label>Authenticator code<input name=code inputmode=numeric pattern="[0-9 ]{{6,7}}" autocomplete=one-time-code required></label>
 <button>Sign in</button>
</form><p class=fine>Have an invite? <a href=join>Create your account</a></p>""", status)


def join_html(err: str = "", code: str = "", name: str = "") -> HTMLResponse:
    return _page("FX-Agents Live · join", f"""
<div class=brand><span class=live-dot></span>FX-Agents <b>LIVE</b></div>
<p class=sub>Create your account with the invite code you were given. You'll need an authenticator app
(Google Authenticator, 1Password, Authy…).</p>{f'<p class=err role=alert>{_esc(err)}</p>' if err else ''}
<form method=post action=join>
 <label>Invite code<input name=invite required value="{_esc(code)}" autocapitalize=none spellcheck=false></label>
 <label>User name<input name=name required value="{_esc(name)}" autocomplete=username autocapitalize=none
   pattern="[a-z0-9_.\\-]{{3,32}}" title="3–32 of a-z 0-9 _ . -"></label>
 <label>Password (12+ characters)<input name=pw type=password autocomplete=new-password required minlength=12></label>
 <button>Create account</button></form>""", 400 if err else 200)


def totp_setup_html(name: str, secret: str) -> HTMLResponse:
    uri = otpauth_uri(secret, name)
    grouped = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return _page("FX-Agents Live · authenticator", f"""
<div class=brand><span class=live-dot></span>FX-Agents <b>LIVE</b></div>
<h2>Add the authenticator</h2>
<p class=sub>Shown <b>once</b>. On this phone, tap the button to add it to your authenticator app, or type the key in by hand.
Then sign in with a code from the app to finish.</p>
<a class=btn href="{_esc(uri)}">Add to authenticator app</a>
<p class=key><code>{_esc(grouped)}</code></p>
<form method=post action=login>
 <input type=hidden name=name value="{_esc(name)}">
 <label>Password<input name=pw type=password autocomplete=current-password required></label>
 <label>Code from the app<input name=code inputmode=numeric autocomplete=one-time-code required></label>
 <button>Finish and sign in</button></form>""")


class Gate:
    def __init__(self, ctx, auth: AuthStore, members: MemberStore) -> None:
        self.ctx, self.auth, self.members = ctx, auth, members
        self.key_checks: dict[int, deque] = {}
        self.acct_cache: dict[int, tuple] = {}

    # ── who is asking ──
    def user(self, request: Request) -> dict | None:
        u = self.auth.session(request.cookies.get(COOKIE))
        request.state.user = u
        return u

    def ws_user(self, websocket) -> dict | None:
        return self.auth.session(websocket.cookies.get(COOKIE))

    def require(self, request: Request, role: str | None = None) -> dict:
        u = getattr(request.state, "user", None) or self.user(request)
        if u is None:
            raise HTTPException(401, "sign in")
        if role == "owner" and u["role"] != "owner":
            raise HTTPException(403, "owner only")
        return u

    # ── pages ──
    def index(self, request: Request, owner_html: str) -> HTMLResponse:
        u = self.user(request)
        if u is None:
            return login_html(status=200)
        if u["role"] == "owner":
            boot = json.dumps({"user": u["name"], "role": "owner", "tags": TAGS})
            html = owner_html.replace("</body>", f"<script>window.FX_LIVE={boot};</script>"
                                                 "<link rel=stylesheet href='live.css'><script src='live_owner.js'></script></body>", 1)
            return HTMLResponse(html)
        return HTMLResponse((STATIC / "member.html").read_text())

    async def _form(self, request: Request) -> dict:
        from urllib.parse import parse_qs
        f = parse_qs((await request.body()).decode(errors="ignore"))
        return {k: (v[0] if v else "") for k, v in f.items()}

    def _cookie(self, resp, request: Request, value: str):
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        resp.set_cookie(COOKIE, value, httponly=True, samesite="lax", secure=secure, max_age=30 * 86400, path="/")
        return resp

    def ip(self, request: Request) -> str:
        return (request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
                or (request.client.host if request.client else "")).strip()

    async def login_post(self, request: Request):
        f = await self._form(request)
        tok, why = self.auth.login(f.get("name", ""), f.get("pw", ""), f.get("code", ""), self.ip(request),
                                   request.headers.get("user-agent", ""))
        if not tok:
            await asyncio.sleep(1.0)
            return login_html(why, f.get("name", ""))
        return self._cookie(RedirectResponse("./", status_code=303), request, tok)

    def logout(self, request: Request):
        self.auth.logout(request.cookies.get(COOKIE))
        resp = RedirectResponse("./", status_code=303)
        resp.delete_cookie(COOKIE, path="/")
        return resp


def install(app, ctx) -> Gate:
    auth = store_for(ctx.cfg)
    vault = vault_from_env()
    members = getattr(ctx, "members", None) or MemberStore(Path(ctx.cfg["storage"]["db_path"]).parent / "members.sqlite", vault)
    gate = Gate(ctx, auth, members)
    ctx.members = members
    ctx.auth = auth
    db = ctx.journal.db
    db.execute("CREATE TABLE IF NOT EXISTS live_review(trade_id TEXT PRIMARY KEY, tags TEXT, grade INTEGER, lesson TEXT, "
               "updated REAL)")
    db.commit()

    @app.middleware("http")
    async def live_guard(request: Request, call_next):
        path = request.url.path
        if any(path.startswith(b) for b in BLOCKED):
            return JSONResponse({"detail": "not on the live site"}, status_code=404)
        mutating = request.method in ("POST", "PUT", "PATCH", "DELETE")
        if mutating and path.startswith("/api/"):
            if request.headers.get("x-fx") != "1":
                return JSONResponse({"detail": "missing x-fx header"}, status_code=403)
            origin = request.headers.get("origin")
            host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            if origin and host and origin.split("://", 1)[-1].rstrip("/") != host:
                return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        who = auth.session(request.cookies.get(COOKIE)) if mutating and path.startswith("/api/") else None
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        if mutating and path.startswith("/api/"):
            auth.log(who["id"] if who else None, "api", f"{request.method} {path} → {resp.status_code}")
        return resp

    # ── public pages ──
    @app.get("/login")
    async def login_get(request: Request):
        return login_html(status=200) if gate.user(request) is None else RedirectResponse("./", status_code=303)

    @app.get("/join")
    async def join_get(code: str = ""):
        return join_html(code=code)

    @app.post("/join")
    async def join_post(request: Request):
        f = await gate._form(request)
        try:
            uid, sec = auth.redeem(f.get("invite", ""), f.get("name", ""), f.get("pw", ""))
        except ValueError as e:
            await asyncio.sleep(1.0)
            return join_html(str(e), f.get("invite", ""), f.get("name", ""))
        if auth.user(uid)["role"] == "member":
            members.get(uid)
        return totp_setup_html(auth.user(uid)["name"], sec)

    @app.get("/live.css")
    async def live_css():
        from fastapi.responses import Response
        return Response((STATIC / "live.css").read_text(), media_type="text/css")

    @app.get("/live_owner.js")
    async def live_js(request: Request):
        from fastapi.responses import Response
        gate.require(request, "owner")
        return Response((STATIC / "live_owner.js").read_text(), media_type="application/javascript")

    # ── everyone signed in ──
    @app.get("/api/live/me")
    async def me(request: Request):
        u = gate.require(request)
        return {"user": u["name"], "role": u["role"], "sessions": auth.sessions_of(u["id"])}

    @app.post("/api/live/password")
    async def password(request: Request):
        u = gate.require(request)
        b = await request.json()
        try:
            auth.set_password(u["id"], str(b.get("old", "")), str(b.get("new", "")))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True, "msg": "password changed — sign in again on your devices"}

    # ── owner: live desk and controls ──
    @app.get("/api/live/desk")
    async def desk(request: Request):
        gate.require(request, "owner")
        return desk_data(ctx)

    @app.post("/api/live/manual")
    async def manual(request: Request):
        u = gate.require(request, "owner")
        b = await request.json()
        act = str(b.get("action", ""))
        if act not in ("close", "breakeven", "stop", "partial"):
            raise HTTPException(400, "unknown action")
        ev = {"action": act, "id": str(b.get("id", "")), "by": u["name"]}
        if act == "stop":
            try:
                ev["price"] = float(b["price"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(400, "stop price needed") from None
        if act == "partial":
            ev["frac"] = float(b.get("frac") or 0)
        await ctx.bus.publish("manual", ev)
        res = ev.get("result") or {"ok": False, "msg": "no position manager answered"}
        auth.log(u["id"], f"manual_{act}", f"{ev['id']} {res.get('msg', '')}"[:200])
        return res

    @app.get("/api/live/review")
    async def review(request: Request, days: int = 30):
        gate.require(request, "owner")
        return review_data(ctx, days)

    @app.post("/api/live/review/{trade_id}")
    async def review_save(trade_id: str, request: Request):
        gate.require(request, "owner")
        b = await request.json()
        tags = [t for t in (b.get("tags") or []) if t in TAGS][:8]
        grade = b.get("grade")
        grade = int(grade) if str(grade or "").isdigit() and 1 <= int(grade) <= 5 else None
        db.execute("INSERT INTO live_review(trade_id, tags, grade, lesson, updated) VALUES (?,?,?,?,?) ON CONFLICT(trade_id) "
                   "DO UPDATE SET tags=excluded.tags, grade=excluded.grade, lesson=excluded.lesson, updated=excluded.updated",
                   (trade_id, json.dumps(tags), grade, str(b.get("lesson") or "")[:1000], time.time()))
        db.commit()
        if "note" in b:
            ctx.journal.set_note(trade_id, str(b.get("note") or "")[:2000])
        return {"ok": True}

    @app.get("/api/live/compare")
    async def lcompare(request: Request, range: str = "month"):
        gate.require(request, "owner")
        return compare_data(ctx, range, members)

    # ── owner: members ──
    @app.get("/api/live/members")
    async def members_list(request: Request):
        gate.require(request, "owner")
        rows = []
        for u in auth.users():
            m = members.public(u["id"]) if u["role"] == "member" else None
            rows.append({"id": u["id"], "name": u["name"], "role": u["role"], "disabled": bool(u["disabled"]),
                         "last_login": u["last_login"], "member": m,
                         "copies": members.summary(u["id"]) if m else None})
        return {"users": rows, "invites": auth.invites(), "settings": {k: members.setting(k) for k in
                ("copy_enabled", "max_member_risk_pct", "copy_symbols")}, "statement": RISK_STATEMENT}

    @app.post("/api/live/invite")
    async def invite(request: Request):
        u = gate.require(request, "owner")
        b = await request.json()
        code = auth.invite(u["id"], "member", str(b.get("note") or ""))
        return {"code": code, "link": f"join?code={code}", "hours": 72}

    @app.post("/api/live/members/{uid}")
    async def member_admin(uid: int, request: Request):
        u = gate.require(request, "owner")
        b = await request.json()
        if "approved" in b:
            members.set_approved(uid, bool(b["approved"]))
            auth.log(u["id"], "member_approved" if b["approved"] else "member_unapproved", str(uid))
        if "disabled" in b:
            try:
                auth.set_disabled(uid, bool(b["disabled"]), u["id"])
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
            if b["disabled"]:
                members.set_copy(uid, False)
        return {"ok": True}

    @app.post("/api/live/settings")
    async def settings(request: Request):
        u = gate.require(request, "owner")
        b = await request.json()
        if not auth.check_code(u["id"], str(b.get("code", ""))):
            raise HTTPException(403, "authenticator code needed for this change")
        if "copy_enabled" in b:
            members.set_setting("copy_enabled", bool(b["copy_enabled"]))
        if "max_member_risk_pct" in b:
            v = float(b["max_member_risk_pct"])
            if not 0 < v <= 0.02:
                raise HTTPException(400, "member risk cap must be above 0 and at most 2% per trade")
            members.set_setting("max_member_risk_pct", v)
        auth.log(u["id"], "settings", json.dumps({k: b[k] for k in ("copy_enabled", "max_member_risk_pct") if k in b}))
        return {k: members.setting(k) for k in ("copy_enabled", "max_member_risk_pct", "copy_symbols")}

    @app.get("/api/live/audit")
    async def audit(request: Request, limit: int = 200):
        gate.require(request, "owner")
        return {"rows": auth.audit(min(int(limit), 1000))}

    @app.get("/api/live/copies")
    async def copies_all(request: Request):
        gate.require(request, "owner")
        names = {u["id"]: u["name"] for u in auth.users()}
        return {"rows": [c | {"name": names.get(c["user_id"])} | {"state": None} for c in members.copies(None, 300)]}

    # ── members ──
    @app.get("/api/m/me")
    async def m_me(request: Request):
        u = gate.require(request)
        m = members.public(u["id"])
        since = time.time() - 30 * 86400
        return {"user": u["name"], "role": u["role"], "member": m, "statement": RISK_STATEMENT,
                "copy_global": bool(members.setting("copy_enabled")), "cap": members.setting("max_member_risk_pct"),
                "copy_symbols": members.setting("copy_symbols"),
                "summary_30d": members.summary(u["id"], since), "summary_all": members.summary(u["id"])}

    @app.get("/api/m/account")
    async def m_account(request: Request):
        u = gate.require(request)
        m = members.get(u["id"])
        hit = gate.acct_cache.get(u["id"])
        if hit and time.time() - hit[0] < 30 and hit[1] == m.get("verified"):
            return hit[2]                                   # one OANDA read per member per 30 s at most
        tok = members.token(u["id"])
        if not tok:
            return {"linked": False}
        try:
            s = await check_key(m["account_id"], tok, m["environment"] or "live")
        except ValueError as e:
            members.set_error(u["id"], str(e))
            return {"linked": True, "error": str(e)}
        finally:
            del tok
        out = {"linked": True, "environment": m["environment"], "currency": s["currency"], "nav": s["NAV"],
               "alias": s["alias"], "key": m["token_mask"]}
        gate.acct_cache[u["id"]] = (time.time(), m.get("verified"), out)
        return out

    @app.post("/api/m/key")
    async def m_key(request: Request):
        u = gate.require(request)
        q = gate.key_checks.setdefault(u["id"], deque(maxlen=5))
        if len(q) == 5 and time.time() - q[0] < 3600:
            raise HTTPException(429, "too many key checks — try again in an hour")
        q.append(time.time())
        b = await request.json()
        env = str(b.get("environment") or "live")
        try:
            s = await check_key(str(b.get("account_id", "")), str(b.get("token", "")), env)
        except ValueError as e:
            auth.log(u["id"], "key_check_failed", str(e)[:100])
            raise HTTPException(400, str(e)) from None
        members.save_key(u["id"], str(b["account_id"]).strip(), str(b["token"]).strip(), env, s)
        auth.log(u["id"], "key_saved", f"{env} {members.public(u['id'])['token_mask']}")
        return {"ok": True, "account": {"currency": s["currency"], "alias": s["alias"], "nav": s["NAV"]},
                "member": members.public(u["id"])}

    @app.delete("/api/m/key")
    async def m_key_delete(request: Request):
        u = gate.require(request)
        members.delete_key(u["id"])
        auth.log(u["id"], "key_deleted", "")
        return {"ok": True, "member": members.public(u["id"])}

    @app.post("/api/m/limits")
    async def m_limits(request: Request):
        u = gate.require(request)
        b = await request.json()
        try:
            return members.set_limits(u["id"], float(b.get("risk_pct", 0)), float(b.get("max_units", 0)),
                                      float(b.get("daily_loss_pct", 0)), list(b.get("symbols") or []))
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/m/copy")
    async def m_copy(request: Request):
        u = gate.require(request)
        b = await request.json()
        try:
            m = members.set_copy(u["id"], bool(b.get("on")), bool(b.get("consent")))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        auth.log(u["id"], "copy_on" if m["copy_on"] else "copy_off", "")
        return m

    @app.get("/api/m/copies")
    async def m_copies(request: Request):
        u = gate.require(request)
        return {"rows": [c | {"state": None} for c in members.copies(u["id"], 200)]}

    @app.get("/api/m/feed")
    async def m_feed(request: Request):
        gate.require(request)
        return feed_data(ctx)

    return gate


# ── data builders (plain functions, tested directly) ─────────────────────────
def _r_now(p) -> float | None:
    try:
        return round(p.r_now(p.last_price), 2) if p.last_price else None
    except Exception:  # noqa: BLE001
        return None


def desk_data(ctx) -> dict:
    st, cfg = ctx.state, ctx.cfg
    inst = cfg["instruments"]
    risk = cfg["risk"]
    today = ctx.journal.summary(since=st.now.normalize().isoformat() if st.now is not None else None)
    loss_cap = float(risk.get("daily_loss_limit_pct", 0.02)) * (st.day_start_equity or st.equity or 0)
    day_pnl = (st.equity or 0) - (st.day_start_equity or st.equity or 0)
    pos = []
    for p in st.positions.values():
        if p.status != "open":
            continue
        mult = float(inst[p.symbol]["multiplier"])
        pos.append({"id": p.id, "symbol": p.symbol, "side": "LONG" if p.side > 0 else "SHORT", "strategy": p.strategy,
                    "qty": p.open_qty, "entry": p.entry, "stop": p.stop, "initial_stop": p.initial_stop,
                    "last": p.last_price, "r_now": _r_now(p), "stage": p.stage, "partial_done": p.partial_done,
                    "opened": p.opened_ts.isoformat() if p.opened_ts is not None else None,
                    "unrealized": round((p.last_price - p.avg_entry) * p.side * p.open_qty * mult, 2) if p.last_price else None,
                    "risk_usd": round(max(0.0, (p.avg_entry - p.stop) * p.side) * p.open_qty * mult, 2),
                    "be": round(p.entry + p.side * float(cfg["management"]["lock_r"]) * p.risk_per_unit, 6),
                    "target_1r": round(p.entry + p.side * p.rr * p.risk_per_unit, 6),
                    "pending_close": p.meta.get("pending_close"), "note": p.meta.get("note", ""),
                    "events": p.events[-12:]})
    markets = []
    for sym, ic in inst.items():
        b = (st.bias or {}).get(sym, {}) if hasattr(st, "bias") else {}
        markets.append({"symbol": sym, "trade": ic.get("trade", True) is not False, "price": st.last_prices.get(sym),
                        "bias": {k: b.get(k) for k in ("label", "score", "d", "h4", "h1", "pdh", "pdl", "state")}})
    sig = []
    try:
        sig = ctx.journal.signals(15)
    except Exception:  # noqa: BLE001
        pass
    news = ctx.news.brief(st.now, hours=8) if getattr(ctx, "news", None) and st.now is not None else []
    blocked = ctx.news.blocked(st.now) if getattr(ctx, "news", None) and st.now is not None else None
    copier = getattr(ctx, "copier", None)
    mem = getattr(ctx, "members", None)
    return {"now": st.now.isoformat() if st.now is not None else None, "mode": cfg["mode"],
            "account": {"equity": round(st.equity or 0, 2), "day_pnl": round(day_pnl, 2), "day_start": round(st.day_start_equity or 0, 2),
                        "loss_cap": round(loss_cap, 2), "loss_used": round(max(0.0, -day_pnl), 2),
                        "risk_pct": float(risk.get("risk_per_trade_pct", 0)),
                        "max_open": int(risk.get("max_open_positions", 0))},
            "trading_enabled": st.trading_enabled, "halt_reason": st.halt_reason, "today": today,
            "positions": pos, "markets": markets, "signals": sig, "news": news, "news_block": blocked,
            "flatten_at": cfg["sessions"]["flatten_at"],
            "members": {"copy_enabled": bool(mem.setting("copy_enabled")) if mem else False,
                        "linked": len(copier.members) if copier else 0}}


def review_data(ctx, days: int = 30) -> dict:
    import pandas as pd
    since = (ctx.state.now - pd.Timedelta(days=max(1, min(int(days), 365)))).isoformat() if ctx.state.now is not None else None
    db = ctx.journal.db
    q = "SELECT t.*, r.tags AS rtags, r.grade, r.lesson FROM trades t LEFT JOIN live_review r ON r.trade_id=t.id " \
        "WHERE t.status='closed'" + (" AND t.closed>=?" if since else "") + " ORDER BY t.closed DESC LIMIT 500"
    rows = [dict(x) for x in db.execute(q, (since,) if since else ())]
    trades, by_tag, by_setup, by_day, by_hour = [], {}, {}, {}, {}
    for t in rows:
        tags = json.loads(t.get("rtags") or "[]")
        r = t.get("r_multiple") or 0.0
        setup = str(t.get("strategy") or "").split(":")[0]
        trades.append({"id": t["id"], "symbol": t["symbol"], "side": t["side"], "strategy": t["strategy"], "opened": t["opened"],
                       "closed": t["closed"], "r": r, "pnl": t.get("realized"), "exit": t.get("exit_reason"),
                       "note": t.get("notes") or "", "tags": tags, "grade": t.get("grade"), "lesson": t.get("lesson") or ""})
        for k, d in [(x, by_tag) for x in tags] + [(setup, by_setup), ((t["closed"] or "")[:10], by_day),
                                                    (int(t.get("hour") or 0), by_hour)]:
            a = d.setdefault(k, {"n": 0, "r": 0.0, "wins": 0})
            a["n"] += 1
            a["r"] = round(a["r"] + r, 3)
            a["wins"] += int(r > 0)
    n = len(trades)
    reviewed = sum(1 for t in trades if t["tags"] or t["grade"] or t["lesson"])
    return {"days": days, "n": n, "reviewed": reviewed, "sum_r": round(sum(t["r"] for t in trades), 2),
            "win_rate": round(sum(t["r"] > 0 for t in trades) / n, 3) if n else 0.0, "trades": trades,
            "by_tag": by_tag, "by_setup": by_setup, "by_day": dict(sorted(by_day.items())), "by_hour": by_hour, "tags": TAGS}


def compare_data(ctx, rng: str, members: MemberStore | None) -> dict:
    import pandas as pd

    from ..dashboard.server import by_symbol, compare_start
    now = ctx.state.now
    days = {"week": 7, "month": 30, "quarter": 90}.get(rng)
    since = (now.normalize() - pd.Timedelta(days=days - 1)).isoformat() if days and now is not None else None
    out = []
    for key, c in (("live", ctx), *((getattr(ctx, "shadows", None) or {}).items())):
        own = compare_start(ctx, c) if key != "live" else None
        s_b = own if own and (since is None or own > since) else since
        sm = c.journal.summary(since=s_b)
        daily = c.journal.daily(s_b[:10] if s_b else None)
        cum, curve = 0.0, []
        for d in sorted(daily):
            cum = round(cum + daily[d]["r"], 2)
            curve.append([d, cum])
        out.append({"book": key, "mode": getattr(c, "selection_mode", key), "paper": key != "live", "since": s_b,
                    "trades": sm["trades"], "win_rate": sm["win_rate"], "sum_r": sm["sum_r"], "avg_r": sm.get("avg_r", 0.0),
                    "pnl": sm["pnl"], "curve": curve, "symbols": by_symbol(c.journal, s_b),
                    "best_day": max((v["r"] for v in daily.values()), default=0.0),
                    "worst_day": min((v["r"] for v in daily.values()), default=0.0)})
    copies = None
    if members is not None:
        rows = [c for c in members.copies(None, 2000) if c["status"] in ("closed", "open", "failed", "skipped")]
        if since:
            t0 = pd.Timestamp(since).timestamp()
            rows = [c for c in rows if (c["opened"] or 0) >= t0]
        done = [c for c in rows if c["status"] == "closed"]
        copies = {"copied": len([c for c in rows if c["status"] in ("closed", "open")]), "closed": len(done),
                  "failed": sum(c["status"] == "failed" for c in rows), "skipped": sum(c["status"] == "skipped" for c in rows),
                  "sum_r": round(sum(c["r"] or 0 for c in done), 2)}
    return {"range": rng, "since": since, "books": out, "copies": copies}


def feed_data(ctx) -> dict:
    """What a member may see of the bot: open trades and recent results, in R and prices only."""
    st = ctx.state
    open_ = [{"symbol": p.symbol, "side": "LONG" if p.side > 0 else "SHORT", "entry": p.entry, "stop": p.stop,
              "r_now": _r_now(p), "opened": p.opened_ts.isoformat() if p.opened_ts is not None else None,
              "setup": str(p.strategy).split(":")[0]} for p in st.positions.values() if p.status == "open"]
    recent = [{"symbol": t["symbol"], "side": t["side"], "r": t.get("r_multiple"), "closed": t.get("closed"),
               "setup": str(t.get("strategy") or "").split(":")[0], "exit": t.get("exit_reason")}
              for t in ctx.journal.trades(30)]
    return {"now": st.now.isoformat() if st.now is not None else None, "open": open_, "recent": recent,
            "trading": st.trading_enabled}
