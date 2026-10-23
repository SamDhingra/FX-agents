"""Read-only views for the dashboard's newer panels. Nothing here changes trading.

  flow        Mission Control: every message on a book's bus (topic, symbol, time), kept in a small ring buffer
  now_info    "What it's waiting for": the next session events with countdowns, plus market weather per instrument
  evidence    Evidence meters: per book and per strategy, average R with a day-block bootstrap 95% range,
              cumulative R and the R list (for the fan of futures)
  story       The trade courtroom: the signal record, Jev's decision and the position's own events for one trade
  bars        1-minute candles around a trade (trade replay), from the in-memory bar store
"""
from __future__ import annotations

import json
import time
from collections import deque

import numpy as np
import pandas as pd

FLOW_MAX = 400
QUIET = {"feed_done", "backfill"}


# ── Mission Control ──────────────────────────────────────────────────────────────────────────────────────────────
def install_tap(c) -> None:
    """Subscribe once to every topic on this book's bus; record (time, topic, symbol). Never raises."""
    if getattr(c, "_flow", None) is not None or getattr(c, "bus", None) is None:
        return
    c._flow = deque(maxlen=FLOW_MAX)
    c._flow_counts = {}

    def tap(item):
        try:
            topic, payload = item
            if topic in QUIET:
                return
            sym = getattr(payload, "symbol", None)
            if sym is None and isinstance(payload, dict):
                p = payload.get("position")
                sym = payload.get("symbol") or (getattr(p, "symbol", None) if p is not None else None)
            c._flow.append((round(time.time(), 3), topic, sym))
            c._flow_counts[topic] = c._flow_counts.get(topic, 0) + 1
        except Exception:  # noqa: BLE001
            pass

    c.bus.subscribe("*", tap)


def flow(c, n: int = 60) -> dict:
    f = getattr(c, "_flow", None)
    if f is None:
        return {"events": [], "counts": {}}
    return {"events": [{"t": t, "topic": tp, "symbol": s} for t, tp, s in list(f)[-n:]],
            "counts": dict(getattr(c, "_flow_counts", {}))}


# ── Now & weather ────────────────────────────────────────────────────────────────────────────────────────────────
def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _next_at(now: pd.Timestamp, hh: int, mm: int) -> pd.Timestamp:
    t = now.normalize() + pd.Timedelta(hours=hh, minutes=mm)
    return t if t > now else t + pd.Timedelta(days=1)


def chop_now(c, sym: str) -> float | None:
    try:
        from ..regime import chop_index
        b = c.store.tf(sym, "15min")
        if len(b) < 20:
            return None
        v = float(chop_index(b).iloc[-1])
        return round(v, 1) if np.isfinite(v) else None
    except Exception:  # noqa: BLE001
        return None


def vol_pct(c, sym: str) -> float | None:
    """Where the latest ATR(14, 15m) sits among the last ~10 days of values (0 = calmest, 1 = wildest)."""
    try:
        b = c.store.tf(sym, "15min")
        if len(b) < 60:
            return None
        tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-960:]
        return round(float((atr <= atr.iloc[-1]).mean()), 2)
    except Exception:  # noqa: BLE001
        return None


def weather(c) -> list[dict]:
    st = c.state
    out = []
    soon = None
    for e in st.news or []:
        m = e.get("minutes_to")
        if m is not None and m >= -30 and e.get("tier") in ("tier1", "high"):
            soon = e if soon is None or m < soon.get("minutes_to", 1e9) else soon
    for sym in c.cfg["instruments"]:
        b = st.bias.get(sym, {}) or {}
        score = float(b.get("score") or 0)
        ch = chop_now(c, sym)
        vp = vol_pct(c, sym)
        storm = bool(st.news_block) or (soon is not None and soon.get("minutes_to", 1e9) <= 30)
        if storm:
            sky = "storm"
        elif ch is not None and ch >= 61.8:
            sky = "chop"
        elif ch is not None and ch <= 38.2:
            sky = "trend"
        else:
            sky = "mixed"
        out.append({"symbol": sym, "price": st.last_prices.get(sym), "sky": sky, "chop": ch, "vol_pct": vp,
                    "bias": round(score, 2), "bias_label": b.get("state") or b.get("label"),
                    "news": ({"title": soon.get("title"), "minutes": soon.get("minutes_to"), "tier": soon.get("tier")}
                             if soon is not None else None)})
    return out


def now_info(main) -> dict:
    """Upcoming moments in NY time: entry windows, the session flatten, gold's overnight range close (when the
    gold_breakout book runs), the next high-impact news. Times are ISO; the page counts them down."""
    st, cfg = main.state, main.cfg
    now = st.now
    if now is None:
        return {"items": [], "weather": weather(main)}
    now = pd.Timestamp(now)
    items = []
    s = cfg["sessions"]
    for a, b in s.get("entry_windows", []):
        start, end = _next_at(now, *_hm(a)), _next_at(now, *_hm(b))
        if end < start:                                      # inside the window right now
            items.append({"key": "window_end", "label": f"Entry window {a}–{b} closes", "at": end.isoformat(), "live": True})
        else:
            items.append({"key": "window", "label": f"Entry window {a}–{b} opens", "at": start.isoformat()})
    items.append({"key": "flatten", "label": "Day-trading flatten", "at": _next_at(now, *_hm(s["flatten_at"])).isoformat()})
    gb = (getattr(main, "shadows", None) or {}).get("gold_breakout")
    if gb is not None:
        c = (cfg.get("shadow") or {}).get("gold_breakout") or {}
        off = float(c.get("broker_utc_offset", 3))
        utc = now.tz_convert("UTC")
        bday = (utc.tz_localize(None) + pd.Timedelta(hours=off)).normalize()
        close = (bday + pd.Timedelta(hours=int(c.get("range_end_hour", 7))) - pd.Timedelta(hours=off)).tz_localize("UTC")
        if close <= utc:
            close += pd.Timedelta(days=1)
        rng = None
        try:
            m1 = main.store.m1("XAUUSD")
            start = close - pd.Timedelta(hours=int(c.get("range_end_hour", 7)))
            seg = m1[(m1.index.tz_convert("UTC") >= start) & (m1.index.tz_convert("UTC") < close)]
            if len(seg):
                rng = {"high": round(float(seg["high"].max()), 2), "low": round(float(seg["low"].min()), 2)}
        except Exception:  # noqa: BLE001
            pass
        items.append({"key": "gold_range", "label": "Gold overnight range closes", "at": close.tz_convert(now.tz).isoformat(),
                      "range": rng})
    nxt = None
    for e in st.news or []:
        m = e.get("minutes_to")
        if m is not None and m >= 0 and e.get("tier") in ("tier1", "high") and (nxt is None or m < nxt["minutes_to"]):
            nxt = e
    if nxt is not None:
        items.append({"key": "news", "label": nxt.get("title", "News"), "tier": nxt.get("tier"),
                      "at": (now + pd.Timedelta(minutes=float(nxt["minutes_to"]))).isoformat()})
    items.sort(key=lambda x: x["at"])
    rk = cfg["risk"]
    eq0 = st.day_start_equity or st.equity or 0.0
    budget = eq0 * float(rk.get("daily_loss_limit_pct", 0.02))
    used = max(0.0, -(st.equity - eq0)) if eq0 else 0.0
    return {"now": now.isoformat(), "items": items[:7], "weather": weather(main),
            "fuel": {"budget": round(budget, 2), "used": round(used, 2),
                     "left_pct": round(max(0.0, 1 - used / budget), 3) if budget else None,
                     "dd_limit_pct": float(rk.get("max_drawdown_pct", 0.06)),
                     "dd_now_pct": round(1 - st.equity / st.equity_peak, 4) if st.equity_peak else 0.0,
                     "blackout": st.news_block}}


# ── Evidence ─────────────────────────────────────────────────────────────────────────────────────────────────────
def boot_ci(r: np.ndarray, day: np.ndarray, B: int = 2000, blk: int = 5, seed: int = 7) -> tuple[float, float] | None:
    """95% range of the average R, resampling whole days in blocks of 5 (same as the research reports)."""
    if len(r) < 5:
        return None
    df = pd.DataFrame({"r": r, "d": day}).groupby("d").r.agg(["sum", "count"])
    s, k = df["sum"].to_numpy(), df["count"].to_numpy()
    nd = len(s)
    rng = np.random.default_rng(seed)
    ix = (rng.integers(0, nd, (B, -(-nd // blk)))[:, :, None] + np.arange(blk)).reshape(B, -1)[:, :nd] % nd
    den = k[ix].sum(1)
    boot = np.where(den > 0, s[ix].sum(1) / np.maximum(den, 1), np.nan)
    lo, hi = np.nanquantile(boot, [0.025, 0.975])
    return float(lo), float(hi)


def _family(strategy: str) -> str:
    return (strategy or "").split(":")[0].split("@")[0] or "other"


def evidence_rows(journal, label: str) -> dict:
    rows = journal.db.execute("SELECT strategy, closed, r_multiple FROM trades WHERE status='closed' "
                              "AND r_multiple IS NOT NULL ORDER BY closed").fetchall()
    def pack(rs):
        r = np.array([x[2] for x in rs], float)
        d = np.array([(x[1] or "")[:10] for x in rs])
        ci = boot_ci(r, d)
        n = len(r)
        verdict = ("none" if n == 0 else "early" if n < 30 else
                   "passing" if (ci and ci[0] > 0 and n >= 100) else
                   "failing" if (ci and ci[1] < 0) else "unproven")
        return {"n": n, "avg_r": round(float(r.mean()), 3) if n else None, "sum_r": round(float(r.sum()), 2) if n else 0.0,
                "win": round(float((r > 0).mean()), 3) if n else None,
                "ci": [round(ci[0], 3), round(ci[1], 3)] if ci else None, "verdict": verdict,
                "cum": [round(float(x), 2) for x in np.cumsum(r)][-400:], "r": [round(float(x), 3) for x in r][-400:],
                "first": rs[0][1] if rs else None, "last": rs[-1][1] if rs else None}
    out = {"book": label, **pack(rows), "strategies": []}
    fam: dict[str, list] = {}
    for x in rows:
        fam.setdefault(_family(x[0]), []).append(x)
    out["strategies"] = sorted(({"name": k, **{kk: vv for kk, vv in pack(v).items() if kk not in ("cum", "r")}}
                                for k, v in fam.items()), key=lambda z: -z["n"])
    days = journal.daily()
    out["days"] = [{"date": d, "r": v["r"], "trades": v["trades"]} for d, v in days.items()][-180:]
    return out


def evidence(main) -> dict:
    books = [("live", main)] + list((getattr(main, "shadows", None) or {}).items())
    return {"books": [{**evidence_rows(c.journal, k), "mode": getattr(c, "selection_mode", k)} for k, c in books]}


# ── Courtroom ────────────────────────────────────────────────────────────────────────────────────────────────────
def story(main, c, trade_id: str) -> dict | None:
    r = c.journal.db.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if r is None:
        return None
    t = dict(r)
    t["events"] = json.loads(t.get("events") or "[]")
    t["draw"] = json.loads(t["draw"]) if t.get("draw") else None
    opened = pd.Timestamp(t["opened"])
    lo, hi = (opened - pd.Timedelta(minutes=10)).isoformat(), (opened + pd.Timedelta(minutes=2)).isoformat()
    sig = c.journal.db.execute("SELECT * FROM signals WHERE symbol=? AND ts>=? AND ts<=? ORDER BY "
                               "CASE action WHEN 'taken' THEN 0 ELSE 1 END, ts DESC LIMIT 1",
                               (t["symbol"], lo, hi)).fetchone()
    dec = main.journal.db.execute("SELECT ts, kind, source, symbol, strategy, latency_ms, outputs, inputs, error FROM decisions "
                                  "WHERE symbol=? AND ts>=? AND ts<=? AND kind IN ('signal_rating','breakout_follow') "
                                  "ORDER BY ts DESC LIMIT 1", (t["symbol"], lo, hi)).fetchone()
    d = None
    if dec is not None:
        d = dict(dec)
        d["outputs"] = json.loads(d["outputs"] or "null")
        inp = json.loads(d.pop("inputs") or "null") or {}
        d["question"] = inp.get("question")
        d["htf_bias"] = inp.get("htf_bias")
    from .lessons import lesson_of
    return {"trade": t, "signal": dict(sig) if sig is not None else None, "jev": d, "lesson": lesson_of(c.journal, trade_id)}


# ── Replay ───────────────────────────────────────────────────────────────────────────────────────────────────────
def bars(c, sym: str, start: str, end: str, max_rows: int = 720) -> dict:
    try:
        m1 = c.store.m1(sym)
    except Exception:  # noqa: BLE001
        return {"bars": [], "note": "no price history"}
    if not len(m1):
        return {"bars": [], "note": "no price history"}
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    seg = m1[(m1.index >= a) & (m1.index <= b)]
    if not len(seg):
        return {"bars": [], "note": "these candles are older than the bot keeps in memory"}
    if len(seg) > max_rows:                                 # long trades: 5-minute candles instead
        seg = seg.resample("5min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return {"bars": [[ts.isoformat(), round(float(x.open), 5), round(float(x.high), 5), round(float(x.low), 5),
                      round(float(x.close), 5)] for ts, x in seg.iterrows()]}


def patterns(c, sym: str, start: str, end: str, tf: int = 15, lookback: int = 80) -> dict:
    """Chart patterns (fxagents/patterns.py) on `tf`-minute candles overlapping [start, end], detected with `lookback`
    extra candles of context before start. Display only."""
    from ..indicators import resample_ohlc
    from ..patterns import detect, to_json
    try:
        m1 = c.store.m1(sym)
    except Exception:  # noqa: BLE001
        return {"patterns": [], "note": "no price history"}
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    tf = max(1, min(int(tf), 240))
    seg = m1[(m1.index >= a - pd.Timedelta(minutes=tf * lookback)) & (m1.index <= b)]
    if len(seg) < 30:
        return {"patterns": [], "note": "not enough candles"}
    df = resample_ohlc(seg, f"{tf}min") if tf > 1 else seg
    return {"tf": tf, "patterns": to_json(df, detect(df), since=a)}
