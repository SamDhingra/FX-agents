"""Read-only OANDA connection check. Places NO orders.

    python check_oanda.py              # practice account (default)
    python check_oanda.py --live       # live account (still read-only)

Needs OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env (or the environment).
Prints the account, whether each of the bot's instruments is tradeable here, its precision and
minimum size, the latest 1-minute candle, and roughly what one unit of risk costs.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from fxagents.config import apply_broker, load_config
from fxagents.oanda import OandaClient, OandaError, OandaFeed


async def main(live: bool) -> int:
    cfg = load_config("config.yaml")
    cfg["mode"], cfg["broker"] = ("live" if live else "paper"), "oanda"
    apply_broker(cfg)
    token, acct = os.environ.get("OANDA_API_TOKEN", ""), os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not acct:
        print("Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID in .env first.")
        return 2
    c = OandaClient(token, acct, "live" if live else "practice")
    ok = True
    try:
        try:
            accts = (await c.req("GET", "/v3/accounts"))["accounts"]
        except OandaError as e:
            print(f"✗ token rejected by the {c.environment} server: {e}")
            print("  (a practice token only works on practice, a live token only on live)")
            return 1
        print(f"✓ token OK on {c.environment}. Accounts for this token: {', '.join(a['id'] for a in accts)}")
        if acct not in {a["id"] for a in accts}:
            print(f"✗ OANDA_ACCOUNT_ID {acct} is not one of them")
            return 1
        s = (await c.req("GET", c.acct("/summary")))["account"]
        print(f"✓ account {acct} {s.get('alias') or ''}: NAV {float(s['NAV']):,.2f} {s['currency']}, "
              f"hedging {'on' if s.get('hedgingEnabled') else 'off'}, open trades {s.get('openTradeCount')}")
        feed = OandaFeed(cfg, None, None, c)
        try:
            await feed.qualify()
        except SystemExit as e:
            print(f"✗ {e}")
            return 1
        print("\n  symbol  instrument    last close   tick    unit step  min units  margin  $ per unit per point")
        for sym, name in feed.syms.items():
            ic = cfg["instruments"][sym]
            cs = await feed.candles(name, "M1", count=2)
            last = next((x for x in reversed(cs) if x.get("complete")), cs[-1] if cs else None)
            px = float(last["mid"]["c"]) if last else float("nan")
            print(f"  {sym:<7} {name:<12} {px:>11,.2f}  {ic['tick_size']:<6g}  {ic['qty_step']:<9g}  "
                  f"{ic['min_units']:<9g}  {100*ic['margin_rate']:>4.1f}%  {float(ic['multiplier']):g}")
            if not cs:
                ok = False
                print(f"    ✗ no candles for {name}")
        eq = float(s["NAV"])
        print(f"\nAt 0.5% risk per trade the bot risks about {0.005*eq:,.2f} {s['currency']} per trade on this balance.")
        print("If that is smaller than one minimum unit × your typical stop distance, those trades are skipped.")
    finally:
        await c.aclose()
    print("\nAll good — no orders were placed." if ok else "\nSome checks failed (see ✗ above).")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="check the live account instead of practice")
    sys.exit(asyncio.run(main(ap.parse_args().live)))
