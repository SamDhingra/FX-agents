"""Market Bias page (Oct 22 2026): per instrument, the structure direction on Daily / 4H / 1H (the bot's own bias —
the same numbers the Risk agent enforces) plus 15m / 5m structure for intraday context, and a plain-language
"can it trade right now, and if not why" line built from the same checks the bot applies.

15m / 5m use the same structure rule as the bias (close beyond the last confirmed swing, swing = 2) on completed
candles only. They are context for the reader; the bot's hard rule stays Daily / 4H / 1H."""
from __future__ import annotations

import pandas as pd

from ..bias import structure_state
from ..indicators import in_windows

TFS = [("d", "Daily"), ("h4", "4H"), ("h1", "1H"), ("m15", "15m"), ("m5", "5m")]


def _intraday(store, sym: str, rule: str) -> int | None:
    try:
        df = store.tf(sym, rule)
    except Exception:  # noqa: BLE001 — a symbol without minute data just shows no intraday cell
        return None
    if df is None or len(df) < 20:
        return None
    st = structure_state(df[["open", "high", "low", "close"]], 2)
    return int(st["state"].iloc[-1])


def _next_window(now: pd.Timestamp, wins: list) -> tuple[pd.Timestamp | None, str]:
    """The next entry-window start after `now` (today or tomorrow) and its label."""
    best = None
    for a, b in wins:
        ah, am = map(int, a.split(":"))
        for add in (0, 1):
            t = (now.normalize() + pd.Timedelta(days=add)).replace(hour=ah, minute=am)
            if t > now and (best is None or t < best[0]):
                best = (t, f"{a}–{b}")
    return best if best else (None, "")


def _change(store, sym: str, px: float | None) -> float | None:
    """% change since the last 17:00 New York roll."""
    try:
        h1 = store.h1(sym)
    except Exception:  # noqa: BLE001
        return None
    if px is None or h1 is None or not len(h1):
        return None
    last = h1.index[-1]
    roll = last.normalize() + pd.Timedelta(hours=17)
    if roll > last:
        roll -= pd.Timedelta(days=1)
    before = h1[h1.index < roll]
    if not len(before):
        return None
    ref = float(before["close"].iloc[-1])
    return round((px / ref - 1) * 100, 3) if ref else None


def eligibility(ctx, sym: str, b: dict | None, now) -> dict:
    """Why the bot can or can't open a new trade on `sym` right now — first blocking reason wins."""
    st, cfg = ctx.state, ctx.cfg
    wins = cfg["sessions"]["entry_windows"]
    open_here = [p for p in st.positions.values() if p.status == "open" and p.symbol == sym]
    if open_here:
        p = open_here[0]
        return {"state": "open", "label": "Position open",
                "why": f"{'Long' if p.side > 0 else 'Short'} {p.strategy.split(':')[0]} · {p.r_now(p.last_price or p.entry):+.2f}R now"}
    if not st.trading_enabled:
        return {"state": "blocked", "label": "Entries paused", "why": st.halt_reason or "New entries are paused."}
    nb = st.news_block
    if nb:
        return {"state": "blocked", "label": "News blackout", "why": f"{nb.get('title', 'News')} · no new entries"}
    if b is None:
        return {"state": "wait", "label": "Warming up", "why": "Not enough hourly history for the bias yet."}
    if b.get("suspended"):
        return {"state": "blocked", "label": "Bias suspended",
                "why": "Bias-aligned losses in a row; waits for a fresh 1H structure break."}
    if now is not None and not in_windows(now, wins):
        t, lab = _next_window(now, wins)
        return {"state": "wait", "label": "Outside entry window",
                "why": f"Next window {lab} NY" if t is not None else "No entry window configured.",
                "at": t.isoformat() if t is not None else None}
    if b.get("label") == "NEUTRAL" or b.get("state") == "NEUTRAL":
        return {"state": "wait", "label": "No clear bias",
                "why": "Daily, 4H and 1H disagree, so the bias rule allows no new trade."}
    side = "longs" if b.get("score", 0) > 0 else "shorts"
    extra = " at half size (Jev audit doubts the bias)" if b.get("in_doubt") else ""
    return {"state": "ready", "label": "Scanning",
            "why": f"Eligible for {side} only{extra}; waiting for a setup on a completed candle."}


def grid(ctx) -> dict:
    st, store = ctx.state, ctx.store
    now = st.now
    syms = list(ctx.cfg["instruments"])
    sig_by = {}
    try:
        for r in ctx.journal.signals(300):
            sig_by.setdefault(r.get("symbol"), r)
    except Exception:  # noqa: BLE001
        pass
    rows = []
    for sym in syms:
        b = st.bias.get(sym)
        px = st.last_prices.get(sym, b.get("price") if b else None)
        cells = {"d": b.get("d") if b else None, "h4": b.get("h4") if b else None, "h1": b.get("h1") if b else None,
                 "m15": _intraday(store, sym, "15min"), "m5": _intraday(store, sym, "5min")}
        known = [v for v in cells.values() if v is not None]
        up, dn = sum(v > 0 for v in known), sum(v < 0 for v in known)
        ctx_label = "Mixed"
        if b and b.get("state") in ("SUSPENDED", "IN DOUBT"):
            ctx_label = b["state"].title()
        elif up >= 4 or (b and b.get("label") == "BULLISH" and up > dn):
            ctx_label = "Bullish"
        elif dn >= 4 or (b and b.get("label") == "BEARISH" and dn > up):
            ctx_label = "Bearish"
        s = sig_by.get(sym)
        rows.append({
            "symbol": sym, "price": px, "change_pct": _change(store, sym, px), "cells": cells,
            "up": up, "down": dn, "known": len(known), "context": ctx_label,
            "score": b.get("score") if b else None, "bias_label": b.get("label") if b else None,
            "bias_state": b.get("state") if b else None, "pdh": b.get("pdh") if b else None,
            "pdl": b.get("pdl") if b else None, "pd_pos": b.get("pd_pos") if b else None,
            "accuracy": b.get("accuracy") if b else None, "accuracy_n": b.get("accuracy_n") if b else 0,
            "audit_p": b.get("audit_p") if b else None, "updated": b.get("updated") if b else None,
            "eligibility": eligibility(ctx, sym, b, now),
            "last_signal": {k: s.get(k) for k in ("ts", "strategy", "side", "action", "why")} if s else None,
        })
    return {"now": now.isoformat() if now is not None else None, "tfs": [{"key": k, "label": l} for k, l in TFS],
            "min_align": ctx.cfg["bias"]["min_align"], "windows": ctx.cfg["sessions"]["entry_windows"], "rows": rows}
