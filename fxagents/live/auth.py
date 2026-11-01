"""Accounts for the live site: owner + private members, password + authenticator code (TOTP), server-side sessions.

Nothing secret is ever stored or logged in clear:
  • passwords: scrypt (n=2^14, r=8, p=1, 16-byte salt), compared in constant time
  • TOTP secrets: encrypted with the vault key (vault.py), decrypted only to check a code
  • sessions: a random 32-byte token in an HttpOnly cookie; only its SHA-256 is stored; 30 days sliding. Every login
    needs the code, and owner actions that change real-money settings ask for a fresh code (step-up)
  • invites: one-time codes (SHA-256 stored), expire after 72 h, made by the owner
Login throttling: 5 failures for a user name or an address in 15 minutes → locked for 15 minutes.

    python -m fxagents.live.auth add-owner <name>     prints a one-time setup link for the authenticator app
    python -m fxagents.live.auth reset-2fa <name>     new authenticator secret (owner lost the phone)
    python -m fxagents.live.auth list
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import struct
import sys
import time
from pathlib import Path

from .vault import Vault

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, role TEXT NOT NULL,
  pw_hash TEXT NOT NULL, totp_enc TEXT NOT NULL, created REAL NOT NULL, disabled INTEGER DEFAULT 0,
  last_login REAL, last_totp_step INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL NOT NULL, seen REAL NOT NULL,
  expires REAL NOT NULL, ip TEXT, ua TEXT);
CREATE TABLE IF NOT EXISTS invites(
  code_hash TEXT PRIMARY KEY, role TEXT NOT NULL, note TEXT, created REAL NOT NULL, expires REAL NOT NULL,
  used_by INTEGER);
CREATE TABLE IF NOT EXISTS login_fail(key TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, user_id INTEGER, action TEXT,
  detail TEXT);
"""
SESSION_DAYS = 30
INVITE_HOURS = 72
FAIL_MAX, FAIL_WINDOW = 5, 15 * 60
NAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
ROLES = ("owner", "member")


# ── TOTP (RFC 6238: HMAC-SHA1, 30 s, 6 digits) ───────────────────────────────
def totp_new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_check(secret: str, code: str, now: float | None = None, last_step: int = 0) -> int | None:
    """The matching time step (±1 step of clock drift), or None. A step at or before `last_step` is refused, so a
    code can't be replayed."""
    code = re.sub(r"\s", "", str(code or ""))
    if not re.fullmatch(r"\d{6}", code):
        return None
    t = int((now if now is not None else time.time()) // 30)
    for s in (t, t - 1, t + 1):
        if s > last_step and hmac.compare_digest(totp_at(secret, s), code):
            return s
    return None


def otpauth_uri(secret: str, name: str, issuer: str = "FX-Agents Live") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(name)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


# ── passwords ────────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    d = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(d).decode()


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, s, d = stored.split("$")
        got = hashlib.scrypt(str(pw).encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(d))
    except (ValueError, TypeError):
        return False


def pw_problem(pw: str) -> str | None:
    if len(pw or "") < 12:
        return "use at least 12 characters"
    if len(set(pw)) < 6:
        return "use more different characters"
    return None


def _h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


class AuthStore:
    def __init__(self, path: str | Path, vault: Vault) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.vault = vault
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ── users ──
    def users(self) -> list[dict]:
        return [dict(r) | {"pw_hash": None, "totp_enc": None}
                for r in self.db.execute("SELECT * FROM users ORDER BY id")]

    def user(self, uid: int) -> dict | None:
        r = self.db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(r) if r else None

    def by_name(self, name: str) -> dict | None:
        r = self.db.execute("SELECT * FROM users WHERE name=?", (str(name or "").strip().lower(),)).fetchone()
        return dict(r) if r else None

    def create_user(self, name: str, pw: str, role: str, totp_secret: str) -> int:
        name = str(name).strip().lower()
        if not NAME_RE.match(name):
            raise ValueError("user name: 3–32 of a-z 0-9 _ . -")
        if role not in ROLES:
            raise ValueError("unknown role")
        why = pw_problem(pw)
        if why:
            raise ValueError(f"password: {why}")
        if self.by_name(name):
            raise ValueError("that user name is taken")
        cur = self.db.execute("INSERT INTO users(name, role, pw_hash, totp_enc, created) VALUES (?,?,?,?,?)",
                              (name, role, hash_pw(pw), self.vault.enc(totp_secret), time.time()))
        self.db.commit()
        self.log(cur.lastrowid, "user_created", role)
        return int(cur.lastrowid)

    def set_disabled(self, uid: int, disabled: bool, by: int) -> None:
        u = self.user(uid)
        if not u:
            raise ValueError("no such user")
        if u["role"] == "owner" and disabled and self.owner_count() <= 1:
            raise ValueError("the last owner can't be disabled")
        self.db.execute("UPDATE users SET disabled=? WHERE id=?", (int(disabled), uid))
        if disabled:
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        self.db.commit()
        self.log(by, "user_disabled" if disabled else "user_enabled", str(uid))

    def set_password(self, uid: int, old: str, new: str) -> None:
        u = self.user(uid)
        if not u or not check_pw(old, u["pw_hash"]):
            raise ValueError("current password is wrong")
        why = pw_problem(new)
        if why:
            raise ValueError(f"password: {why}")
        self.db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new), uid))
        self.db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))       # every device signs in again
        self.db.commit()
        self.log(uid, "password_changed", "")

    def reset_totp(self, uid: int) -> str:
        sec = totp_new_secret()
        self.db.execute("UPDATE users SET totp_enc=?, last_totp_step=0 WHERE id=?", (self.vault.enc(sec), uid))
        self.db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        self.db.commit()
        self.log(uid, "totp_reset", "")
        return sec

    def owner_count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM users WHERE role='owner' AND disabled=0").fetchone()[0])

    # ── login ──
    def _failed(self, keys: list[str]) -> bool:
        cut = time.time() - FAIL_WINDOW
        self.db.execute("DELETE FROM login_fail WHERE ts<?", (cut,))
        return any(self.db.execute("SELECT COUNT(*) FROM login_fail WHERE key=?", (k,)).fetchone()[0] >= FAIL_MAX
                   for k in keys)

    def login(self, name: str, pw: str, code: str, ip: str = "", ua: str = "") -> tuple[str | None, str]:
        """(session token, "") or (None, why). The same message for every wrong credential."""
        name = str(name or "").strip().lower()
        keys = [f"u:{name}", f"ip:{ip}"]
        if self._failed(keys):
            return None, "too many attempts — wait 15 minutes"
        u = self.by_name(name)
        ok = u is not None and not u["disabled"] and check_pw(pw, u["pw_hash"])
        step = None
        if ok:
            step = totp_check(self.vault.dec(u["totp_enc"]), code, last_step=int(u["last_totp_step"] or 0))
        if not ok or step is None:
            if u is None:
                check_pw(pw, hash_pw("x" * 12))          # same work for unknown names (no user-name probing by timing)
            for k in keys:
                self.db.execute("INSERT INTO login_fail(key, ts) VALUES (?,?)", (k, time.time()))
            self.db.commit()
            self.log(u["id"] if u else None, "login_failed", name)
            return None, "user name, password or code is wrong"
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute("INSERT INTO sessions(token_hash, user_id, created, seen, expires, ip, ua) VALUES (?,?,?,?,?,?,?)",
                        (_h(token), u["id"], now, now, now + SESSION_DAYS * 86400, ip[:64], ua[:200]))
        self.db.execute("UPDATE users SET last_login=?, last_totp_step=? WHERE id=?", (now, step, u["id"]))
        self.db.execute("DELETE FROM login_fail WHERE key=?", (f"u:{name}",))
        self.db.commit()
        self.log(u["id"], "login", ip[:64])
        return token, ""

    def session(self, token: str | None) -> dict | None:
        """The signed-in user for a session token (sliding expiry), or None."""
        if not token:
            return None
        r = self.db.execute("SELECT s.*, u.name, u.role, u.disabled FROM sessions s JOIN users u ON u.id=s.user_id "
                            "WHERE s.token_hash=?", (_h(token),)).fetchone()
        now = time.time()
        if r is None or r["disabled"] or r["expires"] < now:
            return None
        if now - r["seen"] > 300:
            self.db.execute("UPDATE sessions SET seen=?, expires=? WHERE token_hash=?",
                            (now, now + SESSION_DAYS * 86400, _h(token)))
            self.db.commit()
        return {"id": r["user_id"], "name": r["name"], "role": r["role"]}

    def logout(self, token: str | None) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_h(token),))
            self.db.commit()

    def sessions_of(self, uid: int) -> list[dict]:
        return [{k: r[k] for k in ("created", "seen", "ip", "ua")}
                for r in self.db.execute("SELECT * FROM sessions WHERE user_id=? ORDER BY seen DESC", (uid,))]

    def check_code(self, uid: int, code: str) -> bool:
        """A fresh authenticator code (step-up for owner actions that move real money settings)."""
        u = self.user(uid)
        if not u:
            return False
        step = totp_check(self.vault.dec(u["totp_enc"]), code, last_step=int(u["last_totp_step"] or 0))
        if step is None:
            return False
        self.db.execute("UPDATE users SET last_totp_step=? WHERE id=?", (step, uid))
        self.db.commit()
        return True

    # ── invites ──
    def invite(self, by: int, role: str = "member", note: str = "") -> str:
        if role not in ROLES:
            raise ValueError("unknown role")
        code = secrets.token_urlsafe(18)
        now = time.time()
        self.db.execute("INSERT INTO invites(code_hash, role, note, created, expires) VALUES (?,?,?,?,?)",
                        (_h(code), role, str(note)[:80], now, now + INVITE_HOURS * 3600))
        self.db.commit()
        self.log(by, "invite_created", f"{role} {note[:40]}")
        return code

    def invites(self) -> list[dict]:
        return [{k: r[k] for k in ("role", "note", "created", "expires", "used_by")}
                for r in self.db.execute("SELECT * FROM invites ORDER BY created DESC LIMIT 50")]

    def redeem(self, code: str, name: str, pw: str) -> tuple[int, str]:
        """New account from a one-time invite → (user id, authenticator secret to show once)."""
        r = self.db.execute("SELECT * FROM invites WHERE code_hash=?", (_h(str(code or "").strip()),)).fetchone()
        if r is None or r["used_by"] is not None or r["expires"] < time.time():
            raise ValueError("this invite is not valid (used, expired or mistyped)")
        sec = totp_new_secret()
        uid = self.create_user(name, pw, r["role"], sec)
        self.db.execute("UPDATE invites SET used_by=? WHERE code_hash=?", (uid, r["code_hash"]))
        self.db.commit()
        return uid, sec

    # ── audit ──
    def log(self, uid: int | None, action: str, detail: str = "") -> None:
        self.db.execute("INSERT INTO audit(ts, user_id, action, detail) VALUES (?,?,?,?)",
                        (time.time(), uid, action, str(detail)[:300]))
        self.db.commit()

    def audit(self, limit: int = 200, uid: int | None = None) -> list[dict]:
        q = "SELECT a.ts, a.action, a.detail, u.name FROM audit a LEFT JOIN users u ON u.id=a.user_id"
        args: tuple = ()
        if uid is not None:
            q += " WHERE a.user_id=?"
            args = (uid,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY a.id DESC LIMIT ?", (*args, limit))]


def store_for(cfg) -> AuthStore:
    from .vault import vault_from_env
    return AuthStore(Path(cfg["storage"]["db_path"]).parent / "users.sqlite", vault_from_env())


def _cli(argv: list[str]) -> None:
    import getpass
    from ..config import load_config
    if not argv:
        raise SystemExit(__doc__)
    st = store_for(load_config("config.yaml"))
    cmd = argv[0]
    if cmd == "list":
        for u in st.users():
            print(f"{u['id']:>3} {u['name']:<20} {u['role']:<7} {'disabled' if u['disabled'] else 'active'}")
        return
    if cmd == "add-owner" and len(argv) == 2:
        pw = getpass.getpass("password (12+ characters): ")
        if pw != getpass.getpass("again: "):
            raise SystemExit("passwords differ")
        sec = totp_new_secret()
        st.create_user(argv[1], pw, "owner", sec)
        print("\nAdd this to your authenticator app (shown once):\n  key: " + sec + "\n  link: " + otpauth_uri(sec, argv[1]))
        return
    if cmd == "reset-2fa" and len(argv) == 2:
        u = st.by_name(argv[1])
        if not u:
            raise SystemExit("no such user")
        sec = st.reset_totp(u["id"])
        print("\nNew authenticator key (shown once): " + sec + "\n  link: " + otpauth_uri(sec, argv[1]))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    _cli(sys.argv[1:])
