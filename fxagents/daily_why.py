"""Why the daily RSI(2)/ADX(2) book has (not) traded (Nov 9 2026, read-only).

Rebuilds the book's 17:00-New-York daily candles from OANDA hourly mid candles with the book's own code
(daily_rule_trader.daily_frame / rule_state) and shows, for every daily close since the book started, each entry
condition and whether it held. Also shows how many daily candles the bot's own 120-day hourly window gives (the book
needs 60).

    python -m fxagents.daily_why [--since 2026-10-20] [--symbol XAUUSD] [--publish]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import pandas as pd

from .agents.daily_rule_trader import daily_frame, rule_state

OUT = Path("data/year_test/daily_why")
NY = "America/New_York"


def table(h1: pd.DataFrame, since: pd.Timestamp, until: pd.Timestamp, window_days: int = 120, min_days: int = 60) -> pd.DataFrame:
    """One row per weekday 17:00 NY close in [since, until]: the rule's inputs and which conditions held."""
    rows = []
    naive = lambda x: (x.tz_convert(NY).tz_localize(None) if x.tzinfo else x).normalize()   # noqa: E731
    for d in pd.bdate_range(naive(since), naive(until)):
        boundary = (d + pd.Timedelta(hours=17)).tz_localize(NY)
        if boundary > until:
            break
        b = daily_frame(h1, boundary)
        if not len(b) or b["end"].iloc[-1] != boundary:
            rows.append({"close_at": boundary, "note": "no completed candle at this close"})
            continue
        st = rule_state(b)
        win = daily_frame(h1[h1.index >= boundary - pd.Timedelta(days=window_days)], boundary)
        rows.append({"close_at": boundary, "close": st["c"], "sma50": st["sma50"], "ema7": st["ema7"], "rsi2": st["rsi2"],
                     "adx2": st["adx2"], "above_sma50": st["c"] > st["sma50"], "above_ema7": st["c"] > st["ema7"],
                     "rsi2_gt_adx2": st["rsi2"] > st["adx2"], "entry": st["entry"], "exit": st["exit"],
                     "bot_window_days": len(win), "enough_history": len(win) >= min_days, "note": ""})
    return pd.DataFrame(rows)


def report(t: pd.DataFrame, sym: str) -> str:
    yes = lambda v: "✅" if v is True else "❌" if v is False else ""     # noqa: E731
    md = [f"# Daily RSI(2)/ADX(2) book on {sym}: every daily close", "",
          "Rebuilt from OANDA hourly mid candles with the book's own code. **Entry needs all three:** close above the "
          "50-day SMA, close above the 7-day EMA, RSI(2) above ADX(2). Long only. Exit: RSI(2) below ADX(2). "
          "\"Bot window\" = daily candles the bot's 120-day hourly history gives (it needs 60).", "",
          "| daily close (NY) | close | SMA50 | EMA7 | RSI2 | ADX2 | > SMA50 | > EMA7 | RSI2 > ADX2 | **entry** | bot window |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in t.iterrows():
        if r.get("note"):
            md.append(f"| {r.close_at:%a %d %b} | {r.note} | | | | | | | | | |")
            continue
        md.append(f"| {r.close_at:%a %d %b} | {r.close:,.2f} | {r.sma50:,.2f} | {r.ema7:,.2f} | {r.rsi2:.1f} | {r.adx2:.1f} | "
                  f"{yes(r.above_sma50)} | {yes(r.above_ema7)} | {yes(r.rsi2_gt_adx2)} | **{yes(r.entry)}** | "
                  f"{r.bot_window_days}{'' if r.enough_history else ' ⚠️ < 60'} |")
    ok = t[t.note == ""] if "note" in t else t
    n = len(ok)
    if n:
        md += ["", f"**{int(ok.entry.sum())} entry signal(s) in {n} daily closes.** Conditions held on: above SMA50 "
               f"{int(ok.above_sma50.sum())}, above EMA7 {int(ok.above_ema7.sum())}, RSI2 > ADX2 {int(ok.rsi2_gt_adx2.sum())}. "
               f"Bot's history short on {int((~ok.enough_history).sum())} of them."]
    return "\n".join(md) + "\n"


async def fetch_h1(cfg, sym: str, days: int = 220) -> pd.DataFrame:
    from .oanda import OandaFeed, _inst, oanda_from_cfg
    from .trade_atlas import journal_cfg
    cfg = journal_cfg(cfg)          # read-only commands run in sim mode, which skips the OANDA instrument names
    client = oanda_from_cfg(cfg)
    try:
        feed = OandaFeed(cfg, None, None, client)
        cs = await feed._paged(_inst(cfg, sym), "H1", pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days))
        return feed._frame(cs, vol=False)
    finally:
        await client.aclose()


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-20")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config("config.yaml")
    h1 = asyncio.run(fetch_h1(cfg, a.symbol))
    t = table(h1, pd.Timestamp(a.since), pd.Timestamp.now(tz=NY))
    md = report(t, a.symbol)
    print(md)
    if a.publish:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "report.md").write_text(md)


if __name__ == "__main__":
    sys.exit(main())
