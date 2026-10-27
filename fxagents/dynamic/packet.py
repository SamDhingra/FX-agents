"""The frozen as-of packet a reviewer sees for one entry (Oct 26 2026, docs/dynamic_controller.md).

Pure function of its arguments: closed candles only (a minute after the entry time is never read), the still-forming
15-minute candle separately labelled partial, prices rounded to the instrument's own precision, deterministic JSON and
a sha256 `packet_hash` over exactly the fields the models are shown. Why: a review is only worth scoring if it saw
what the bot knew at the entry and nothing later, and if the same packet can be rebuilt and checked afterwards.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import pandas as pd

from .. import usd_calendar
from ..indicators import resample_ohlc

NY = "America/New_York"
MIN = pd.Timedelta("1min")
N_M5, N_M15, N_H1 = 24, 16, 24
FALLBACK_DECIMALS = {"XAUUSD": 2, "NDQ": 2, "US30": 1}
LEVEL_KEYS = ("pdh", "pdl", "asia_hi", "asia_lo", "h4_swing_hi", "h4_swing_lo")


def decimals_for(ic: dict | None, symbol: str) -> int:
    """Price decimals from the instrument's tick size (OANDA's displayPrecision is written there at start-up);
    a per-symbol default when the config has none."""
    try:
        tick = float((ic or {}).get("tick_size"))
        if tick > 0 and math.isfinite(tick):
            s = f"{tick:.10f}".rstrip("0")
            return len(s.split(".")[1]) if "." in s else 0
    except (TypeError, ValueError):
        pass
    return FALLBACK_DECIMALS.get(symbol, 5)


def _num(x, nd: int | None = None):
    """float (rounded) or None for missing / NaN / not a number."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd) if nd is not None else v


def timeframe_of(strategy: str) -> str:
    m = re.search(r":(\d+m)@", strategy or "")
    return m.group(1) if m else ""


def _ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(NY) if t.tzinfo is None else t.tz_convert(NY)


def _rows(df: pd.DataFrame, nd: int) -> list:
    return [[t.strftime("%Y-%m-%d %H:%M"), round(float(r.open), nd), round(float(r.high), nd), round(float(r.low), nd),
             round(float(r.close), nd)] for t, r in df.iterrows()]


def closed_bars(m1: pd.DataFrame, rule: str, ts: pd.Timestamp, n: int) -> pd.DataFrame:
    """The last n complete `rule` candles whose last minute is before `ts` (NY clock, left-labelled)."""
    if m1 is None or not len(m1):
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    span = pd.Timedelta(rule) * (n + 2)
    seg = m1[(m1.index >= ts - span) & (m1.index <= ts - MIN)]
    if not len(seg):
        return seg[["open", "high", "low", "close"]]
    df = resample_ohlc(seg, rule)
    return df[df.index + pd.Timedelta(rule) <= ts].iloc[-n:][["open", "high", "low", "close"]]


def forming_m15(m1: pd.DataFrame, ts: pd.Timestamp, nd: int) -> dict | None:
    """The 15-minute candle in progress at `ts`, built from the minutes closed so far; None on a 15-minute boundary."""
    start = ts.floor("15min")
    if ts == start or m1 is None or not len(m1):
        return None
    seg = m1[(m1.index >= start) & (m1.index <= ts - MIN)]
    if not len(seg):
        return None
    return {"partial": True, "start": start.strftime("%Y-%m-%d %H:%M"), "minutes_in": int((ts - start) / MIN),
            "ohlc": [round(float(seg.open.iloc[0]), nd), round(float(seg.high.max()), nd), round(float(seg.low.min()), nd),
                     round(float(seg.close.iloc[-1]), nd)]}


def next_release(ts: pd.Timestamp, events: dict | None = None) -> dict | None:
    """The next scheduled FOMC / CPI / NFP / PPI release after `ts` (fxagents/usd_calendar), or None within 10 days."""
    ev = usd_calendar.events() if events is None else events
    for i in range(0, 11):
        day = ts.normalize() + pd.Timedelta(days=i)
        for minute, name in ev.get(day.strftime("%Y-%m-%d"), []):
            at = day + pd.Timedelta(minutes=int(minute))
            if at > ts:
                return {"name": name, "time_ny": at.strftime("%Y-%m-%d %H:%M"), "minutes_to": int((at - ts) / MIN)}
    return None


def _plain(o):
    """numpy scalars (bias values) → Python numbers for JSON."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not JSON-serialisable: {type(o).__name__}")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=_plain)


def packet_hash(packet: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in packet.items() if k != "packet_hash"}).encode()).hexdigest()


def build_packet(*, candidate_id: str, book: str, symbol: str, side: int, strategy: str, ts, entry: float, stop: float,
                 target_r: float | None, spread: float | None, cost_r: float | None, instrument: dict | None,
                 m1: pd.DataFrame, h1: pd.DataFrame | None, bias: dict | None, record: dict | None = None,
                 m15_live: bool | None = None, events: dict | None = None) -> dict:
    """The packet as a plain dict (JSON-safe, `packet_hash` included). `ts` is the entry time; nothing at or after
    it is read. `record` = {"trades": n, "avg_r": x} for the setup, if known."""
    ts = _ny(ts).floor("min")
    nd = decimals_for(instrument, symbol)
    bias = bias or {}
    updated = bias.get("updated")
    since = None
    if updated:
        try:
            since = max(0, int((ts - _ny(updated)) / MIN))
        except (TypeError, ValueError):
            since = None
    h1c = pd.DataFrame(columns=["open", "high", "low", "close"])
    if h1 is not None and len(h1):
        x = h1[h1.index + pd.Timedelta("1h") <= ts]
        h1c = x.iloc[-N_H1:][["open", "high", "low", "close"]]
    stop_dist = abs(entry - stop)
    p = {
        "candidate": {"id": candidate_id, "book": book, "symbol": symbol, "side": "LONG" if side > 0 else "SHORT",
                      "strategy": strategy, "timeframe": timeframe_of(strategy),
                      "entry_time_utc": ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M"),
                      "entry_time_ny": ts.strftime("%Y-%m-%d %H:%M")},
        "order": {"entry": round(float(entry), nd), "stop": round(float(stop), nd), "stop_distance": round(stop_dist, nd),
                  "target_r": _num(target_r, 2), "spread": _num(spread, nd + 1), "cost_r": _num(cost_r, 3),
                  "tick_size": _num((instrument or {}).get("tick_size")), "price_decimals": nd},
        "bias": {"label": bias.get("label"), "score": _num(bias.get("score"), 3), "d": bias.get("d"), "h4": bias.get("h4"),
                 "h1": bias.get("h1"), "minutes_since_update": since, "h1_minutes": bias.get("h1_minutes"),
                 "h1_complete": bias.get("h1_complete")},
        "candles": {"columns": ["start_ny", "open", "high", "low", "close"],
                    "m5_closed": _rows(closed_bars(m1, "5min", ts, N_M5), nd),
                    "m15_closed": _rows(closed_bars(m1, "15min", ts, N_M15), nd),
                    "h1_closed": _rows(h1c, nd),
                    "m15_forming": forming_m15(m1, ts, nd), "m15_live_against_entry": m15_live},
        "levels": {k: _num(bias.get(k), nd) for k in LEVEL_KEYS},
        "session": {"ny_time": ts.strftime("%H:%M"), "weekday": ts.strftime("%A"), "next_release": next_release(ts, events)},
        "setup_record": ({"trades": int(record["trades"]), "avg_r": _num(record.get("avg_r"), 3)} if record else None),
    }
    p["packet_hash"] = packet_hash(p)
    return json.loads(canonical(p))
