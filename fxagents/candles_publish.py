"""Keep fresh market candles on a public GitHub branch ('candles') so an outside tool (ChatGPT, a notebook …) can read
them by URL — no OANDA token, no dashboard login, nothing for it to install.

    python -m fxagents.candles_publish --loop 300        (the `fxcandles` container runs this)
    python -m fxagents.candles_publish --once            (./fx.sh candles — write the files and push once)

Per instrument and timeframe (M1 M5 M15 H1 H4 D) one CSV: time (UTC candle OPEN time), open, high, low, close, volume,
complete.  The last row may be the still-forming candle (complete = false) — that is the "live" one.  MID prices from
OANDA's practice feed (no bid/ask, no account data, no tokens).  Plus README.md (what is where, column meanings, the raw
URLs) and latest.json (last price + the time of this refresh).

The branch holds ONE commit that is replaced on every refresh (force-pushed), so the repository doesn't grow.
GitHub's raw links are cached for up to ~5 minutes, so "live" means a few minutes behind.  Anything published here is
public: turn it off with `candles.enabled: false` in config.yaml (or stop the fxcandles container).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import time
from pathlib import Path

import pandas as pd

from .config import apply_broker, load_config
from .oanda import OandaFeed, oanda_from_cfg

GRANS = {"M1": 1440, "M5": 1152, "M15": 1000, "H1": 1000, "H4": 600, "D": 500}      # candles kept per file
OUT = Path(os.environ.get("CANDLES_DIR", "data/candles"))
KEY = Path(os.environ.get("CANDLES_KEY", "/key/key"))
REPO = os.environ.get("CANDLES_REPO", "SamDhingra/FX-agents")
BRANCH = "candles"


def to_csv(candles: list[dict]) -> tuple[str, str | None]:
    """OANDA mid candles → CSV text (oldest first) and the last close."""
    rows, last = ["time,open,high,low,close,volume,complete"], None
    for c in candles:
        m = c.get("mid")
        if not m:
            continue
        t = c["time"][:19] + "Z"
        rows.append(f"{t},{m['o']},{m['h']},{m['l']},{m['c']},{int(c.get('volume', 0))},{str(bool(c.get('complete'))).lower()}")
        last = m["c"]
    return "\n".join(rows) + "\n", last


def readme(syms: list[str], updated: str) -> str:
    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
    files = "\n".join(f"- {s}: " + ", ".join(f"[{g}]({base}/{s}_{g}.csv)" for g in GRANS) for s in syms)
    return f"""# Market candles ({', '.join(syms)})

Refreshed every few minutes. Last refresh: **{updated}** (UTC). GitHub caches raw links for up to ~5 minutes, so the
newest candle can be that much behind. Latest prices: [latest.json]({base}/latest.json)

## Files (CSV, oldest first)
{files}

Columns: `time` = UTC candle OPEN time · `open high low close` = MID price (halfway between bid and ask) ·
`volume` = OANDA tick count (price updates), not traded volume · `complete` = false for the candle still forming (the last row).

Notes
- Source: OANDA practice account v20 API, CFD prices (not futures). Gold = XAU_USD (USD per oz), NDQ = NAS100_USD,
  US30 = US30_USD (index points).
- Candles per file: M1 {GRANS['M1']} · M5 {GRANS['M5']} · M15 {GRANS['M15']} · H1 {GRANS['H1']} · H4 {GRANS['H4']} · D {GRANS['D']}.
- H4 and D candles are aligned to 17:00 New York (OANDA's default): the D candle runs 17:00 → 17:00 New York.
- These are mid prices. Real trades pay the spread (gold about 0.5–0.7 points, NDQ about 2–2.5, US30 about 3) on top.
"""


async def fetch(client, name: str, gran: str) -> list[dict]:
    r = await client.req("GET", f"/v3/instruments/{name}/candles",
                         params={"granularity": gran, "price": "M", "count": str(min(GRANS[gran], 5000))})
    return r.get("candles", [])


async def refresh(out: Path = OUT, client=None, names: dict[str, str] | None = None) -> dict:
    if client is None:
        cfg = load_config()
        c2 = {**cfg, "mode": "paper", "broker": "oanda", "instruments": {k: dict(v) for k, v in cfg["instruments"].items()}}
        apply_broker(c2)
        client = oanda_from_cfg(c2)
        names = OandaFeed(c2, None, None, client).syms
    out.mkdir(parents=True, exist_ok=True)
    last, done = {}, []
    for sym, name in (names or {}).items():
        for g in GRANS:
            try:
                text, px = to_csv(await fetch(client, name, g))
            except Exception as e:  # noqa: BLE001 — one failed request must not stop the others
                print(f"  {sym} {g}: {e}", flush=True)
                continue
            (out / f"{sym}_{g}.csv").write_text(text)
            if g == "M1" and px:
                last[sym] = float(px)
            done.append(f"{sym}_{g}")
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    syms = list(names or {})
    (out / "README.md").write_text(readme(syms, now))
    import json
    (out / "latest.json").write_text(json.dumps({"updated_utc": now, "last_price_mid": last}, indent=1))
    return {"files": len(done), "updated": now}


def push(out: Path = OUT) -> str:
    """Replace the single commit on the 'candles' branch with the current files."""
    if not KEY.exists():
        return f"not pushed: no deploy key at {KEY} (run ./fx.sh publish-setup once, then ./fx.sh update)"
    key = Path("/tmp/candles_key")
    key.write_bytes(KEY.read_bytes())
    key.chmod(0o600)
    env = {**os.environ, "GIT_SSH_COMMAND": f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
                                            f"-o UserKnownHostsFile=/tmp/known_hosts"}

    def git(*a):
        return subprocess.run(["git", "-C", str(out), *a], env=env, capture_output=True, text=True, timeout=120)
    if not (out / ".git").exists():
        git("init", "-q", "-b", BRANCH)
        git("remote", "add", "origin", os.environ.get("CANDLES_REMOTE") or f"git@github.com:{REPO}.git")
    git("add", "-A")
    c = git("-c", "user.name=fx-candles", "-c", "user.email=fx-candles@localhost", "commit", "-q", "--amend", "--no-edit")
    if c.returncode != 0:
        c = git("-c", "user.name=fx-candles", "-c", "user.email=fx-candles@localhost", "commit", "-q", "-m", "candles")
    p = git("push", "-q", "-f", "origin", f"HEAD:{BRANCH}")
    return "pushed" if p.returncode == 0 else f"push failed: {(p.stderr or p.stdout).strip()[:300]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="seconds between refreshes (0 = once)")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if not (load_config().get("candles") or {}).get("enabled", True):
        print("candles.enabled is false in config.yaml — nothing to do", flush=True)
        while a.loop:
            time.sleep(3600)
        return
    while True:
        try:
            info = asyncio.run(refresh())
            print(f"{info['updated']} UTC: {info['files']} files — {push()}", flush=True)
        except SystemExit as e:
            print(f"candles: {e}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"candles: {type(e).__name__}: {e}", flush=True)
        if a.once or not a.loop:
            return
        time.sleep(max(60, a.loop))


if __name__ == "__main__":
    main()
