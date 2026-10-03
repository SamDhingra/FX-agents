"""Dashboard login: the token never has to sit in the URL."""
from __future__ import annotations

import copy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from fxagents.config import load_config
from fxagents.dashboard.server import build_app

CFG = load_config("config.yaml")


def client():
    cfg = copy.deepcopy(CFG)
    cfg["dashboard"]["token"] = "s3cret-token"
    ctx = SimpleNamespace(cfg=cfg)
    return TestClient(build_app(ctx), base_url="https://trade.example")


def test_login_form_posts_token_and_sets_secure_cookie():
    c = client()
    r = c.get("/")
    assert r.status_code == 401 and "method=post" in r.text
    assert c.post("/login", data={"token": "wrong"}).status_code == 401
    r = c.post("/login", data={"token": "s3cret-token"}, follow_redirects=False)
    assert r.status_code == 303 and "token" not in r.headers["location"]
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "secure" in sc and "samesite=strict" in sc
    c.cookies.set("fx_token", "s3cret-token")
    assert c.get("/").status_code == 200


def test_old_token_links_redirect_to_clean_address():
    c = client()
    r = c.get("/?token=s3cret-token", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "./" and "fx_token=" in r.headers["set-cookie"]
    assert c.get("/?token=nope").status_code == 401


def test_logout_clears_the_cookie():
    r = client().get("/logout", follow_redirects=False)
    assert r.status_code == 303 and 'fx_token=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
