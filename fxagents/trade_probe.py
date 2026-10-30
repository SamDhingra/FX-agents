"""What OANDA says about the practice account's open positions (read-only; Oct 30 2026, the trade-803 case).

For every open position in runtime_state.json: each of its broker trade ids, read by id and by the bot's client id
(fxa-<position>-<leg>), plus OANDA's open trades on that instrument and the account's latest closed trades of the
position. Prints to the terminal only (it shows trade ids and units) — nothing is published, nothing is sent.

    python -m fxagents.trade_probe [trade ids…]      (./fx.sh tradeprobe [ids])
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .oanda import OandaError, oanda_from_cfg
from .reconcile import broker_cfg, pos_id


def brief(tr: dict | None) -> str:
    if not tr:
        return "—"
    return (f"id {tr.get('id')} {tr.get('state')} {tr.get('instrument')} units {tr.get('initialUnits')}→{tr.get('currentUnits')} "
            f"open {tr.get('openTime', '')[:19]} @ {tr.get('price')}"
            + (f" · closed {tr.get('closeTime', '')[:19]} @ {tr.get('averageClosePrice')} realizedPL {tr.get('realizedPL')}"
               if tr.get("state") == "CLOSED" else "")
            + f" · tag {(tr.get('clientExtensions') or {}).get('id', '—')}")


async def get(c, path: str):
    try:
        return (await c.req("GET", c.acct(path))), None
    except OandaError as e:
        return None, str(e)


async def probe(cfg, ids: list[str]) -> list[str]:
    rt = Path(cfg["storage"]["db_path"]).parent / "runtime_state.json"
    positions = json.loads(rt.read_text()).get("positions", []) if rt.exists() else []
    c = oanda_from_cfg(cfg)
    out = [f"runtime state: {len(positions)} open position(s) ({rt})"]
    try:
        open_tr, err = await get(c, "/openTrades")
        open_tr = (open_tr or {}).get("trades", [])
        out.append(f"OANDA open trades: {len(open_tr)}" + (f" (error {err})" if err else ""))
        for t in open_tr:
            out.append("  " + brief(t))
        recent, _ = await get(c, "/trades?state=CLOSED&count=50")
        recent = (recent or {}).get("trades", [])
        for p in positions:
            meta = p.get("meta") or {}
            out += ["", f"position {p.get('id')} {p.get('symbol')} side {p.get('side')} {p.get('strategy')} "
                        f"opened {str(p.get('opened'))[:19]} · targets {list((meta.get('tp') or {}).keys())}"]
            for k, t in enumerate(meta.get("trades", [])):
                cid = t.get("cid") or f"fxa-{p.get('id')}-{'initial' if k == 0 else 'pyramid'}{k}"
                by_id, e1 = await get(c, f"/trades/{t['id']}")
                by_cid, e2 = await get(c, f"/trades/@{cid}")
                out.append(f"  leg {k}: bot id {t['id']} units {t.get('units')} · cid {cid}")
                out.append(f"    by id : {brief((by_id or {}).get('trade')) if by_id else e1}")
                out.append(f"    by cid: {brief((by_cid or {}).get('trade')) if by_cid else e2}")
            mine = [t for t in recent if pos_id(t) == p.get("id")]
            out.append(f"  closed trades at OANDA tagged with this position: {len(mine)}")
            out += ["    " + brief(t) for t in mine]
        for tid in ids:
            r, e = await get(c, f"/trades/{tid}")
            out += ["", f"trade {tid}: {brief((r or {}).get('trade')) if r else e}"]
    finally:
        await c.aclose()
    return out


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser(description="Read-only: what OANDA says about the open positions")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    cfg = broker_cfg(load_config("config.yaml"))
    print("\n".join(asyncio.run(probe(cfg, a.ids))))


if __name__ == "__main__":
    main()
