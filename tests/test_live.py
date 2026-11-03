"""The live site (Oct 31 2026): accounts + authenticator codes, encrypted member keys, the copy engine, owner controls,
and the web layer's security rules. No network: OANDA is the in-memory fake."""
from __future__ import annotations

import asyncio
import copy
import time
from types import SimpleNamespace

import pandas as pd
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fxagents.live import auth as A
from fxagents.live import members as M
from fxagents.live.copier import CopyEngine
from fxagents.live.vault import Vault, VaultError, mask
from fxagents.oanda import OandaClient
from tests.fake_oanda import ACCT, FakeOanda
from tests.test_oanda import pos, setup

KEY = Fernet.generate_key().decode()
MTOKEN = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6-e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"     # a member's (fake) OANDA token


def run(c):
    return asyncio.run(c)


@pytest.fixture
def vault(monkeypatch):
    monkeypatch.setenv("LIVE_VAULT_KEY", KEY)
    return Vault(KEY)


# ── TOTP, passwords, vault ──
def test_totp_matches_rfc6238_and_refuses_replay():
    import base64
    sec = base64.b32encode(b"12345678901234567890").decode()
    assert A.totp_at(sec, 59 // 30) == "287082"                      # RFC 6238 test vector (SHA-1, T=59), 6 digits
    step = A.totp_check(sec, "287 082", now=59)
    assert step == 1 and A.totp_check(sec, "287082", now=59, last_step=1) is None
    assert A.totp_check(sec, "12345", now=59) is None


def test_password_hash_and_vault_never_show_secrets(vault):
    h = A.hash_pw("correct horse battery")
    assert A.check_pw("correct horse battery", h) and not A.check_pw("wrong", h) and "correct" not in h
    e = vault.enc(MTOKEN)
    assert MTOKEN not in e and vault.dec(e) == MTOKEN and "hidden" in repr(vault)
    with pytest.raises(VaultError):
        Vault(Fernet.generate_key().decode()).dec(e)
    assert mask(MTOKEN) == "••••" + MTOKEN[-4:]
    with pytest.raises(VaultError):
        Vault("")


def test_login_needs_password_and_code_and_locks_after_five_failures(tmp_path, vault):
    st = A.AuthStore(tmp_path / "users.sqlite", vault)
    sec = A.totp_new_secret()
    st.create_user("sam", "a long enough pw!", "owner", sec)
    assert st.login("sam", "a long enough pw!", "000000")[0] is None
    tok, _ = st.login("sam", "a long enough pw!", A.totp_at(sec, int(time.time() // 30)))
    assert tok and st.session(tok)["role"] == "owner"
    assert st.login("sam", "a long enough pw!", A.totp_at(sec, int(time.time() // 30)))[0] is None     # replay
    for _ in range(4):
        st.login("sam", "nope", "123456")
    tok2, why = st.login("sam", "a long enough pw!", A.totp_at(sec, int(time.time() // 30) + 1))
    assert tok2 is None and "too many" in why
    assert "pw" not in str(st.users()) or st.users()[0]["pw_hash"] is None
    st.logout(tok)
    assert st.session(tok) is None
    with pytest.raises(ValueError):
        st.create_user("x", "short", "member", sec)


def test_invite_is_single_use(tmp_path, vault):
    st = A.AuthStore(tmp_path / "users.sqlite", vault)
    code = st.invite(None, "member", "Raj")
    uid, sec = st.redeem(code, "raj", "another long password")
    assert st.user(uid)["role"] == "member" and len(sec) == 32
    with pytest.raises(ValueError):
        st.redeem(code, "raj2", "another long password")


# ── members ──
def member_store(tmp_path, vault):
    return M.MemberStore(tmp_path / "members.sqlite", vault)


def test_member_copy_needs_every_switch(tmp_path, vault):
    ms = member_store(tmp_path, vault)
    ms.save_key(5, ACCT, MTOKEN, "practice", {"currency": "CAD", "alias": "raj"})
    pub = ms.public(5)
    assert "token_enc" not in pub and MTOKEN not in str(pub) and pub["token_mask"].endswith(MTOKEN[-4:])
    with pytest.raises(ValueError):
        ms.set_copy(5, True)                                       # no consent yet
    ms.set_copy(5, True, consent=True)
    assert ms.active("NDQ") == []                                  # owner switch off, not approved
    ms.set_setting("copy_enabled", True)
    assert ms.active("NDQ") == []
    ms.set_approved(5, True)
    assert [m["user_id"] for m in ms.active("NDQ")] == [5] and ms.active("XAUUSD") == []
    with pytest.raises(ValueError):
        ms.set_limits(5, 0.05, 5, 0.02, ["NDQ"])                   # above the 1% cap
    ms.delete_key(5)
    assert ms.active("NDQ") == [] and ms.token(5) is None


def test_check_key_reads_summary_and_hides_the_token():
    fake = FakeOanda()
    fake.token = MTOKEN
    s = run(M.check_key(ACCT, MTOKEN, "practice", transport=fake.transport()))
    assert s["currency"] == "CAD"
    bad = FakeOanda()
    bad.token = "x" * 60
    with pytest.raises(ValueError) as e:
        run(M.check_key(ACCT, MTOKEN, "practice", transport=bad.transport()))
    assert MTOKEN not in str(e.value) and "refused" in str(e.value)
    with pytest.raises(ValueError):
        run(M.check_key("12345", MTOKEN, "practice"))


# ── copy engine ──
def copy_setup(tmp_path, vault, risk_pct=0.005):
    cfg, fake, c, st, bus, feed, b = setup()
    mfake = FakeOanda(nav=27400.0, currency="CAD", usdcad=1.37)       # the member's account: US$20,000
    mfake.token = MTOKEN
    ms = member_store(tmp_path, vault)
    ms.set_setting("copy_enabled", True)
    ms.save_key(7, ACCT, MTOKEN, "practice", {"currency": "CAD"})
    ms.set_limits(7, risk_pct, 50, 0.02, ["NDQ"])
    ms.set_copy(7, True, consent=True)
    ms.set_approved(7, True)
    ctx = SimpleNamespace(cfg=cfg, bus=bus, state=st)
    eng = CopyEngine(ctx, ms, client_factory=lambda t, a, e: OandaClient(t, a, e, transport=mfake.transport()))
    eng.start()
    return cfg, fake, mfake, st, bus, feed, b, ms, eng


def test_copy_follows_open_stop_and_close(tmp_path, vault):
    cfg, fake, mfake, st, bus, feed, b, ms, eng = copy_setup(tmp_path, vault)

    async def go():
        await feed.qualify(); await b.connect()
        await eng.restore()
        st.last_prices["NDQ"] = 24500.0
        p = pos()                                            # long NDQ, stop 24400 (100 points)
        await b.open(p, 2, 24500)
        p.opened_ts = st.now
        await bus.publish("position_opened", p)
        await eng.drain()
        mt = mfake.open_trades()
        assert len(mt) == 1 and float(mt[0]["currentUnits"]) == pytest.approx(1.0)   # $20k × 0.5% / 100 = 1 unit
        await b.move_stop(p, 24450)
        await bus.publish("position_updated", {"position": p, "event": "stop_to_profit"})
        await eng.drain()
        assert float(mfake.open_trades()[0]["stopLossOrder"]["price"]) == pytest.approx(24450)
        p.status, p.exit_reason = "closed", "target"
        await bus.publish("position_closed", {"position": p, "price": 24600})
        await eng.drain()
        return p
    run(go())
    assert mfake.open_trades() == []
    rows = ms.copies(7)
    assert rows[0]["status"] == "closed" and rows[0]["qty"] == 1.0 and rows[0]["master_id"]


def test_copy_skips_old_entries_and_small_sizes_and_never_breaks_the_master(tmp_path, vault):
    cfg, fake, mfake, st, bus, feed, b, ms, eng = copy_setup(tmp_path, vault, risk_pct=0.0001)

    async def go():
        await feed.qualify(); await b.connect()
        st.last_prices["NDQ"] = 24500.0
        p = pos()
        await b.open(p, 1, 24500)
        p.opened_ts = st.now
        await bus.publish("position_opened", p)              # $2 risk / $100 per unit → below 0.1 unit
        q = pos()
        q.opened_ts = st.now - pd.Timedelta(minutes=5)
        await bus.publish("position_opened", q)
        await eng.drain()
    run(go())
    st_ = {r["status"]: r["error"] for r in ms.copies(7)}
    assert "skipped" in st_ and mfake.open_trades() == []
    assert any("too old" in (r["error"] or "") for r in ms.copies(7))
    assert any("minimum" in (r["error"] or "") for r in ms.copies(7))


def test_bad_member_key_is_recorded_not_raised(tmp_path, vault):
    cfg, fake, mfake, st, bus, feed, b, ms, eng = copy_setup(tmp_path, vault)
    mfake.token = "z" * 64                                    # the member revoked their key at OANDA

    async def go():
        await feed.qualify(); await b.connect()
        st.last_prices["NDQ"] = 24500.0
        p = pos()
        await b.open(p, 1, 24500)
        p.opened_ts = st.now
        await bus.publish("position_opened", p)
        await eng.drain()
    run(go())
    r = ms.copies(7)[0]
    assert r["status"] == "failed" and MTOKEN not in str(r) and ms.public(7)["last_error"]


# ── owner controls (through the position manager) ──
def test_manual_controls_keep_the_broker_rules():
    from fxagents.agents.trading import PositionManagerAgent
    from fxagents.agents.core import Ctx
    cfg, fake, c, st, bus, feed, b = setup()
    ctx = Ctx(cfg, bus, st, None, b, None, None, None)
    pm = PositionManagerAgent(ctx)
    pm.start()

    async def go():
        await feed.qualify(); await b.connect()
        p = pos()
        await b.open(p, 2, 24500)
        st.positions[p.id] = p
        out = []
        for ev in ({"action": "stop", "id": p.id, "price": 24300},          # loosening: refused
                   {"action": "stop", "id": p.id, "price": 24600},          # through price: refused
                   {"action": "breakeven", "id": p.id},
                   {"action": "partial", "id": p.id, "frac": 0.5},
                   {"action": "partial", "id": p.id, "frac": 1.0},
                   {"action": "close", "id": p.id},
                   {"action": "close", "id": "nope"}):
            st.last_prices["NDQ"] = 24560.0
            await bus.publish("manual", ev)
            out.append(ev["result"])
        return p, out
    p, out = run(go())
    assert not out[0]["ok"] and "toward profit" in out[0]["msg"]
    assert not out[1]["ok"] and "through" in out[1]["msg"]
    assert out[2]["ok"] and p.stop > p.initial_stop
    assert out[3]["ok"] and not out[4]["ok"]
    assert out[5]["ok"] and p.status == "closed" and "manual close" in p.exit_reason
    assert not out[6]["ok"]


# ── web layer ──
def live_client(tmp_path, monkeypatch):
    from fxagents.config import load_config
    from fxagents.dashboard.server import build_app
    from fxagents.journal import Journal
    from fxagents.state import LiveState
    monkeypatch.setenv("LIVE_VAULT_KEY", KEY)
    cfg = copy.deepcopy(load_config("config.yaml"))
    cfg["live_app"] = {"enabled": True}
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    st = LiveState(mode="live")
    st.now = pd.Timestamp("2026-11-02 10:00", tz="America/New_York")
    ctx = SimpleNamespace(cfg=cfg, journal=Journal(cfg["storage"]["db_path"]), state=st, bus=None, shadows={}, news=None)
    app = build_app(ctx)
    au = A.store_for(cfg)
    sec_o, sec_m = A.totp_new_secret(), A.totp_new_secret()
    au.create_user("sam", "owner password 123", "owner", sec_o)
    au.create_user("raj", "member password 123", "member", sec_m)
    return TestClient(app, base_url="https://live.example"), ctx, au, sec_o, sec_m


def login(c, name, pw, sec, step=0):
    return c.post("/login", data={"name": name, "pw": pw, "code": A.totp_at(sec, int(time.time() // 30) + step)},
                  follow_redirects=False)


def test_live_site_roles_and_csrf(tmp_path, monkeypatch):
    c, ctx, au, so, sm = live_client(tmp_path, monkeypatch)
    r = c.get("/")
    assert "Authenticator code" in r.text and "Dashboard token" not in r.text
    assert c.get("/api/state").status_code == 401
    assert c.get("/?token=whatever").status_code == 200 and "Authenticator" in c.get("/").text   # old token links don't open it
    r = login(c, "sam", "owner password 123", so)
    assert r.status_code == 303 and "httponly" in r.headers["set-cookie"].lower() and "secure" in r.headers["set-cookie"].lower()
    page = c.get("/").text
    assert "window.FX_LIVE" in page and "live_owner.js" in page
    assert c.get("/api/live/desk").status_code == 200
    assert c.get("/api/bt").status_code == 404 and c.get("/api/backtests").status_code == 404
    assert c.post("/api/live/invite", json={"note": "x"}).status_code == 403                 # no x-fx header
    assert c.post("/api/live/invite", json={"note": "x"}, headers={"x-fx": "1", "origin": "https://evil.example"}).status_code == 403
    inv = c.post("/api/live/invite", json={"note": "Raj"}, headers={"x-fx": "1"}).json()
    assert len(inv["code"]) > 20
    r = c.post("/api/live/settings", json={"copy_enabled": True, "code": "000000"}, headers={"x-fx": "1"})
    assert r.status_code == 403
    r = c.post("/api/live/settings", json={"copy_enabled": True, "code": A.totp_at(so, int(time.time() // 30) + 1)},
               headers={"x-fx": "1"})
    assert r.status_code == 200 and r.json()["copy_enabled"] is True
    assert any(a["action"] == "settings" for a in au.audit())
    # a member sees only their own pages and /api/m
    m = TestClient(c.app, base_url="https://live.example")
    login(m, "raj", "member password 123", sm)
    assert "window.FX_LIVE" not in m.get("/").text
    assert m.get("/api/state").status_code == 403 and m.get("/api/live/desk").status_code == 403
    assert m.get("/live_owner.js").status_code == 403
    me = m.get("/api/m/me").json()
    assert me["role"] == "member" and me["member"]["has_key"] is False
    fd = m.get("/api/m/feed").json()
    assert "open" in fd and "equity" not in str(fd)


def test_member_key_flow_never_returns_the_token(tmp_path, monkeypatch):
    c, ctx, au, so, sm = live_client(tmp_path, monkeypatch)

    async def fake_check(acct, tok, env, transport=None):
        if tok != MTOKEN:
            raise ValueError("OANDA refused this key for that account")
        return {"currency": "CAD", "alias": "raj", "NAV": "1000", "hedging": False}
    from fxagents.live import web
    monkeypatch.setattr(web, "check_key", fake_check)
    login(c, "raj", "member password 123", sm)
    h = {"x-fx": "1"}
    r = c.post("/api/m/key", json={"account_id": ACCT, "token": "y" * 60, "environment": "live"}, headers=h)
    assert r.status_code == 400 and "y" * 20 not in r.text
    r = c.post("/api/m/key", json={"account_id": ACCT, "token": MTOKEN, "environment": "live"}, headers=h)
    assert r.status_code == 200 and MTOKEN not in r.text and r.json()["member"]["has_key"]
    assert MTOKEN not in str(au.audit())
    assert c.post("/api/m/copy", json={"on": True}, headers=h).status_code == 400            # consent first
    assert c.post("/api/m/copy", json={"on": True, "consent": True}, headers=h).json()["copy_on"] == 1
    assert MTOKEN not in c.get("/api/m/me").text
    assert c.delete("/api/m/key", headers=h).json()["member"]["has_key"] is False


def test_hold_file_blocks_the_account_until_released_with_a_code(tmp_path, monkeypatch):
    from fxagents.live import hold as H
    c, ctx, au, so, sm = live_client(tmp_path, monkeypatch)
    H.set_hold(ctx.cfg, True, "setup")
    assert H.is_on(ctx.cfg)
    login(c, "sam", "owner password 123", so)
    h = {"x-fx": "1"}
    assert c.post("/api/live/hold", json={"on": False, "code": "000000"}, headers=h).status_code == 403
    assert H.is_on(ctx.cfg)
    r = c.post("/api/live/hold", json={"on": False, "code": A.totp_at(so, int(time.time() // 30) + 1)}, headers=h)
    assert r.status_code == 200 and not H.is_on(ctx.cfg) and ctx.state.hold == ""
    assert c.post("/api/live/hold", json={"on": True}, headers=h).json()["hold"] is True
    assert H.is_on(ctx.cfg) and ctx.state.hold == H.REASON
    assert c.get("/api/live/desk").json()["hold"] is True


def test_risk_refuses_entries_on_hold():
    from fxagents.agents.trading import RiskAgent
    from fxagents.live.hold import REASON
    from fxagents.models import Signal
    from tests.test_oanda import setup as osetup
    cfg, fake, c, st, bus, feed, b = osetup()
    st.hold = REASON
    rejected = []
    me = SimpleNamespace(cfg=cfg, state=st, now=lambda: st.now, beat=lambda: None,
                         _reject=lambda rec, why: rejected.append(why), ctx=SimpleNamespace(news=None))
    sig = Signal("NDQ", "x:5m@v1", 1, 24500.0, 24400.0, st.now)
    run(RiskAgent.on_request(me, {"signal": sig, "record": {}, "grade": {}}))
    assert rejected and "on hold" in rejected[0]
