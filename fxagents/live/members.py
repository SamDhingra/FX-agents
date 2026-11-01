"""Members' OANDA connections and copy settings (live site).

A member links their own OANDA account: account id + API token (+ practice or live). The token is checked against
OANDA once (account summary), then stored encrypted (vault.py); only its last 4 characters are ever shown again, and
it is never logged. The member can replace or delete it at any time.

Copying a trade onto a member's account needs ALL of:
  • the owner's global switch           settings.copy_enabled (off by default; changing it needs an authenticator code)
  • the owner's approval of this member members.approved
  • the member's own switch + consent   members.copy_on, members.consent_ts (they ticked the risk statement)
  • a verified, decryptable key         members.verified
  • the member's own limits             risk_pct (≤ settings.max_member_risk_pct), max_units, daily_loss_pct, symbols
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .vault import Vault, mask

SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
  user_id INTEGER PRIMARY KEY, account_id TEXT, environment TEXT DEFAULT 'live', token_enc TEXT, token_mask TEXT,
  currency TEXT, alias TEXT, verified REAL, last_error TEXT,
  risk_pct REAL DEFAULT 0.0025, max_units REAL DEFAULT 5, daily_loss_pct REAL DEFAULT 0.02, symbols TEXT DEFAULT '["NDQ"]',
  copy_on INTEGER DEFAULT 0, consent_ts REAL, approved INTEGER DEFAULT 0, updated REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS copies(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, master_id TEXT, member_pos TEXT, symbol TEXT, side INTEGER,
  qty REAL, entry REAL, stop REAL, opened REAL, closed REAL, exit_price REAL, realized REAL, r REAL, status TEXT,
  error TEXT, events TEXT, state TEXT);
CREATE INDEX IF NOT EXISTS ix_copies_user ON copies(user_id, opened);
"""
DEFAULTS = {"copy_enabled": False, "max_member_risk_pct": 0.01, "copy_symbols": ["NDQ"]}
RISK_STATEMENT = ("I understand that the bot will place real orders on my own OANDA account using my key, that trading "
                  "CFDs can lose more than I expect, that past results do not predict future ones, and that I can switch "
                  "copying off or delete my key at any time.")


class MemberStore:
    def __init__(self, path: str | Path, vault: Vault) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.vault = vault

    # ── global settings (owner) ──
    def setting(self, key: str):
        r = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else DEFAULTS.get(key)

    def set_setting(self, key: str, value) -> None:
        if key not in DEFAULTS:
            raise ValueError("unknown setting")
        self.db.execute("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value)))
        self.db.commit()

    # ── members ──
    def get(self, uid: int) -> dict:
        r = self.db.execute("SELECT * FROM members WHERE user_id=?", (uid,)).fetchone()
        if r is None:
            self.db.execute("INSERT INTO members(user_id, updated) VALUES (?,?)", (uid, time.time()))
            self.db.commit()
            r = self.db.execute("SELECT * FROM members WHERE user_id=?", (uid,)).fetchone()
        return dict(r)

    def public(self, uid: int) -> dict:
        """Everything the UI may see — never the token."""
        m = self.get(uid)
        m.pop("token_enc", None)
        m["symbols"] = json.loads(m.get("symbols") or "[]")
        m["has_key"] = bool(m.get("token_mask"))
        return m

    def all(self) -> list[dict]:
        return [self.public(r[0]) for r in self.db.execute("SELECT user_id FROM members ORDER BY user_id")]

    def save_key(self, uid: int, account_id: str, token: str, environment: str, summary: dict) -> None:
        self.get(uid)
        self.db.execute("UPDATE members SET account_id=?, environment=?, token_enc=?, token_mask=?, currency=?, alias=?, "
                        "verified=?, last_error=NULL, copy_on=0, updated=? WHERE user_id=?",
                        (account_id, environment, self.vault.enc(token), mask(token), summary.get("currency"),
                         (summary.get("alias") or "")[:60], time.time(), time.time(), uid))
        self.db.commit()

    def delete_key(self, uid: int) -> None:
        self.db.execute("UPDATE members SET account_id=NULL, token_enc=NULL, token_mask=NULL, verified=NULL, copy_on=0, "
                        "updated=? WHERE user_id=?", (time.time(), uid))
        self.db.commit()

    def token(self, uid: int) -> str | None:
        """Decrypted token for the copy engine / key check only. Never return this to a page."""
        r = self.db.execute("SELECT token_enc FROM members WHERE user_id=?", (uid,)).fetchone()
        return self.vault.dec(r[0]) if r and r[0] else None

    def set_limits(self, uid: int, risk_pct: float, max_units: float, daily_loss_pct: float, symbols: list[str]) -> dict:
        cap = float(self.setting("max_member_risk_pct"))
        allowed = set(self.setting("copy_symbols") or [])
        risk_pct = float(risk_pct)
        if not 0 < risk_pct <= cap:
            raise ValueError(f"risk per trade must be above 0 and at most {cap:.2%}")
        if not 0 < float(max_units) <= 1000:
            raise ValueError("max units must be between 0 and 1000")
        if not 0 < float(daily_loss_pct) <= 0.1:
            raise ValueError("daily loss limit must be above 0 and at most 10%")
        syms = [s for s in symbols if s in allowed]
        self.get(uid)
        self.db.execute("UPDATE members SET risk_pct=?, max_units=?, daily_loss_pct=?, symbols=?, updated=? WHERE user_id=?",
                        (risk_pct, float(max_units), float(daily_loss_pct), json.dumps(syms), time.time(), uid))
        self.db.commit()
        return self.public(uid)

    def set_copy(self, uid: int, on: bool, consent: bool = False) -> dict:
        m = self.get(uid)
        if on:
            if not m.get("token_enc") or not m.get("verified"):
                raise ValueError("link and check your OANDA key first")
            if not (consent or m.get("consent_ts")):
                raise ValueError("tick the risk statement first")
        self.db.execute("UPDATE members SET copy_on=?, consent_ts=COALESCE(consent_ts, ?), updated=? WHERE user_id=?",
                        (int(on), time.time() if consent else None, time.time(), uid))
        self.db.commit()
        return self.public(uid)

    def set_approved(self, uid: int, approved: bool) -> dict:
        self.get(uid)
        self.db.execute("UPDATE members SET approved=?, updated=? WHERE user_id=?", (int(approved), time.time(), uid))
        self.db.commit()
        return self.public(uid)

    def set_error(self, uid: int, err: str | None) -> None:
        self.db.execute("UPDATE members SET last_error=? WHERE user_id=?", ((err or None) and str(err)[:300], uid))
        self.db.commit()

    def active(self, symbol: str) -> list[dict]:
        """Members a trade on `symbol` is copied to right now (every switch and limit checked)."""
        if not self.setting("copy_enabled") or symbol not in (self.setting("copy_symbols") or []):
            return []
        out = []
        for r in self.db.execute("SELECT * FROM members WHERE copy_on=1 AND approved=1 AND verified IS NOT NULL "
                                 "AND token_enc IS NOT NULL AND consent_ts IS NOT NULL"):
            m = dict(r)
            if symbol in json.loads(m.get("symbols") or "[]"):
                m.pop("token_enc", None)
                out.append(m)
        return out

    # ── copy records ──
    def add_copy(self, uid: int, master_id: str, member_pos: str | None, symbol: str, side: int, qty: float, entry: float | None,
                 stop: float | None, status: str, error: str | None = None) -> int:
        cur = self.db.execute("INSERT INTO copies(user_id, master_id, member_pos, symbol, side, qty, entry, stop, opened, "
                              "status, error, events) VALUES (?,?,?,?,?,?,?,?,?,?,?, '[]')",
                              (uid, master_id, member_pos, symbol, side, qty, entry, stop, time.time(), status,
                               error and str(error)[:300]))
        self.db.commit()
        return int(cur.lastrowid)

    def copy_event(self, cid: int, kind: str, **kw) -> None:
        r = self.db.execute("SELECT events FROM copies WHERE id=?", (cid,)).fetchone()
        ev = json.loads(r[0] or "[]") if r else []
        ev.append({"ts": time.time(), "kind": kind, **kw})
        self.db.execute("UPDATE copies SET events=? WHERE id=?", (json.dumps(ev[-60:], default=str), cid))
        self.db.commit()

    def close_copy(self, cid: int, exit_price: float | None, realized: float | None, r: float | None, status: str = "closed",
                   error: str | None = None) -> None:
        self.db.execute("UPDATE copies SET closed=?, exit_price=?, realized=?, r=?, status=?, error=COALESCE(?, error) WHERE id=?",
                        (time.time(), exit_price, realized, r, status, error and str(error)[:300], cid))
        self.db.commit()

    def copies(self, uid: int | None = None, limit: int = 200) -> list[dict]:
        q, a = "SELECT * FROM copies", ()
        if uid is not None:
            q, a = q + " WHERE user_id=?", (uid,)
        rows = [dict(r) for r in self.db.execute(q + " ORDER BY id DESC LIMIT ?", (*a, limit))]
        for x in rows:
            x["events"] = json.loads(x.get("events") or "[]")
        return rows

    def summary(self, uid: int, since: float | None = None) -> dict:
        q = "SELECT COUNT(*), COALESCE(SUM(r),0), COALESCE(SUM(realized),0), SUM(CASE WHEN r>0 THEN 1 ELSE 0 END) " \
            "FROM copies WHERE user_id=? AND status='closed'" + (" AND closed>=?" if since else "")
        n, r, pnl, w = self.db.execute(q, (uid, since) if since else (uid,)).fetchone()
        return {"trades": int(n), "sum_r": round(float(r), 2), "pnl": round(float(pnl), 2),
                "win_rate": round((w or 0) / n, 3) if n else 0.0}


async def check_key(account_id: str, token: str, environment: str, transport=None) -> dict:
    """Read the account summary with the member's key (nothing is placed). Returns {currency, alias, NAV} or raises
    ValueError with a message that never contains the token."""
    import re

    from ..oanda import OandaClient, OandaError
    account_id, token = str(account_id or "").strip(), str(token or "").strip()
    if environment not in ("practice", "live"):
        raise ValueError("choose practice or live")
    if not re.fullmatch(r"\d{3}-\d{3}-\d{6,9}-\d{3}", account_id):
        raise ValueError("account id looks like 001-001-1234567-001")
    if not re.fullmatch(r"[A-Za-z0-9-]{40,80}", token):
        raise ValueError("that doesn't look like an OANDA API token")
    c = OandaClient(token, account_id, environment, transport=transport, timeout=10.0)
    try:
        s = (await c.req("GET", c.acct("/summary")))["account"]
    except OandaError as e:
        code = e.status
        raise ValueError("OANDA refused this key for that account" if code in (401, 403) else
                         "OANDA has no such account for this key" if code == 404 else
                         f"OANDA didn't answer (status {code}); try again") from None
    finally:
        await c.aclose()
    return {"currency": s.get("currency"), "alias": s.get("alias"), "NAV": s.get("NAV"),
            "hedging": s.get("hedgingEnabled")}
