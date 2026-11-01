"""Encryption at rest for secrets the live site must keep: members' OANDA API tokens and everyone's authenticator
secrets. Fernet (AES-128-CBC + HMAC-SHA256) with a key that lives ONLY in the server's .env.live as LIVE_VAULT_KEY
(never in git, never in the database, never logged).

    python -m fxagents.live.vault new-key      prints a fresh key for .env.live (do this once)

Losing the key = every stored member token and authenticator secret becomes unreadable (members re-enter their key,
everyone resets 2FA). Rotating: set LIVE_VAULT_KEY_OLD to the old key and LIVE_VAULT_KEY to the new one; values are
read with either and re-written with the new one on the next save.
"""
from __future__ import annotations

import os
import sys

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, key: str, old: str | None = None) -> None:
        if not key:
            raise VaultError("LIVE_VAULT_KEY is not set (python -m fxagents.live.vault new-key)")
        try:
            keys = [Fernet(key.encode())] + ([Fernet(old.encode())] if old else [])
        except (ValueError, TypeError) as e:
            raise VaultError("LIVE_VAULT_KEY is not a valid key") from e
        self._f = MultiFernet(keys)

    def enc(self, plain: str) -> str:
        return self._f.encrypt(str(plain).encode()).decode()

    def dec(self, token: str) -> str:
        try:
            return self._f.decrypt(str(token).encode()).decode()
        except InvalidToken as e:
            raise VaultError("a stored secret can't be decrypted with LIVE_VAULT_KEY") from e

    def __repr__(self) -> str:                    # never print key material
        return "Vault(<hidden>)"


def vault_from_env() -> Vault:
    return Vault(os.environ.get("LIVE_VAULT_KEY", ""), os.environ.get("LIVE_VAULT_KEY_OLD") or None)


def mask(token: str) -> str:
    """What the UI may show of an API token: its last 4 characters."""
    t = str(token or "")
    return "••••" + t[-4:] if len(t) >= 8 else "••••"


if __name__ == "__main__":
    if sys.argv[1:] == ["new-key"]:
        print(Fernet.generate_key().decode())
    else:
        raise SystemExit(__doc__)
