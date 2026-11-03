"""The live account's hold switch (Nov 2 2026).

While `HOLD` exists next to the live journal (data_live/HOLD on the server), the live ACCOUNT opens no new trades —
across restarts and trading days, unlike Pause, which clears at the next trading day. Open positions are still managed
and closed as usual; paper books keep trading. `./fx.sh live setup` creates it, so a fresh live site starts on hold.
Release it on the Live desk (authenticator code) or with `./fx.sh live release`; put it back with Hold or
`./fx.sh live hold`.
"""
from __future__ import annotations

from pathlib import Path

REASON = "on hold — release it on the Live desk when you want the live account to trade"


def path(cfg) -> Path:
    return Path(cfg["storage"]["db_path"]).parent / "HOLD"


def is_on(cfg) -> bool:
    return path(cfg).exists()


def set_hold(cfg, on: bool, by: str = "") -> None:
    p = path(cfg)
    if on:
        p.write_text(f"held by {by or 'owner'}\n")
    elif p.exists():
        p.unlink()


def install(ctx) -> None:
    """Keep state.hold in step with the file: checked now and on every clock tick (15 s)."""
    def sync(_=None):
        ctx.state.hold = REASON if is_on(ctx.cfg) else ""
    sync()
    ctx.bus.subscribe("clock", sync)
