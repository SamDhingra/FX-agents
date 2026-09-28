"""Economic calendar: filter trading around news, and stay aware of what is coming.

Source: the Forex Factory weekly JSON feed (free, no key). Refreshed hourly, cached to disk, and
merged with any events you add by hand in config.yaml.

Tiers (USD events by default: they move gold and the US indices):
  tier1  = High impact AND a market-moving keyword (FOMC, NFP, CPI, PCE, Fed Chair …)
  high   = other High impact
  medium = Medium impact (optional)

Policy per tier (config.news):
  • no new entries inside [event − before, event + after]
  • open positions N minutes before: `protect` (stop to breakeven+ if in profit, otherwise close),
    `close`, or `none`
  • tier-1 days trade at reduced size all day (event_day_risk_mult)
  • heads-up push notification ahead of each event; upcoming events go to Jev and the dashboard
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger("news")
FIXTURE = Path(__file__).parent / "fixtures" / "news_week.json"


class NewsCalendar:
    def __init__(self, cfg) -> None:
        self.c = cfg["news"]
        self.tz = cfg["timezone"]
        self.events: list[dict] = []
        self.last_refresh: pd.Timestamp | None = None
        self.source = "none"
        self.cache = Path(cfg["storage"]["db_path"]).parent / "news_cache.json"

    # ── loading ───────────────────────────────────────────────────────────
    def tier(self, e: dict) -> str | None:
        imp = str(e.get("impact", "")).lower()
        if e.get("country", "").upper() not in [c.upper() for c in self.c["currencies"]] and not e.get("manual"):
            return None
        title = e.get("title", "").lower()
        if imp == "high" and any(k.lower() in title for k in self.c["tier1_keywords"]):
            return "tier1"
        if imp == "high":
            return "high"
        if imp == "medium" and self.c.get("include_medium", True):
            return "medium"
        return e.get("tier") if e.get("manual") else None

    def load(self, raw: list[dict], source: str) -> None:
        evs = []
        for e in raw + [dict(m, manual=True) for m in (self.c.get("manual_events") or [])]:
            t = self.tier(e)
            if not t:
                continue
            ts = pd.Timestamp(e["date"])
            ts = ts.tz_convert(self.tz) if ts.tzinfo else ts.tz_localize(self.tz)
            evs.append({"id": f"{ts.isoformat()}|{e['title']}", "ts": ts, "title": e["title"],
                        "country": e.get("country", "USD"), "impact": e.get("impact", "High"), "tier": t,
                        "forecast": e.get("forecast", ""), "previous": e.get("previous", "")})
        self.events = sorted({e["id"]: e for e in evs}.values(), key=lambda e: e["ts"])
        self.source = source
        log.info("news: %d relevant events loaded (%s)", len(self.events), source)

    async def refresh(self, now: pd.Timestamp) -> None:
        if not self.c.get("enabled", True):
            return
        self.last_refresh = now
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "fx-agents/1.0"}) as c:
                r = await c.get(self.c["feed_url"])
                r.raise_for_status()
                raw = r.json()
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps(raw))
            self.load(raw, "forexfactory")
        except Exception as e:
            log.warning("news feed unavailable (%s) — using cache", e)
            if self.cache.exists():
                self.load(json.loads(self.cache.read_text()), "cache")
            elif not self.events:
                self.load([], "manual-only")

    def load_sim(self, first_day: pd.Timestamp, days: int) -> None:
        """Sim mode: replay this week's real USD calendar onto the simulated days (by weekday)."""
        raw = json.loads(FIXTURE.read_text())
        out, day = [], first_day.normalize()
        placed = 0
        while placed < days:
            if day.dayofweek < 5:
                for e in raw:
                    t = pd.Timestamp(e["date"])
                    if t.dayofweek == day.dayofweek:
                        out.append(e | {"date": (day + pd.Timedelta(hours=t.hour, minutes=t.minute)).isoformat()})
                placed += 1
            day += pd.Timedelta("1D")
        self.load(out + raw, "sim (this week's real USD calendar, replayed + upcoming)")

    # ── queries ───────────────────────────────────────────────────────────
    def _win(self, tier: str) -> tuple[int, int]:
        b, a = self.c["windows"].get(tier, [0, 0])
        return int(b), int(a)

    def blocked(self, now: pd.Timestamp) -> dict | None:
        for e in self.events:
            b, a = self._win(e["tier"])
            if e["ts"] - pd.Timedelta(minutes=b) <= now <= e["ts"] + pd.Timedelta(minutes=a):
                return e | {"phase": "before" if now < e["ts"] else "after"}
        return None

    def pre_actions(self, now: pd.Timestamp) -> list[dict]:
        out = []
        for e in self.events:
            pa = self.c["pre_news_action"].get(e["tier"])
            if not pa or pa.get("action", "none") == "none":
                continue
            if e["ts"] - pd.Timedelta(minutes=pa["minutes"]) <= now < e["ts"]:
                out.append(e | {"action": pa["action"]})
        return out

    def risk_mult(self, now: pd.Timestamp) -> float:
        today = now.date()
        if any(e["tier"] == "tier1" and e["ts"].date() == today for e in self.events):
            return float(self.c.get("event_day_risk_mult", 0.5))
        return 1.0

    def upcoming(self, now: pd.Timestamp, hours: float = 36) -> list[dict]:
        end = now + pd.Timedelta(hours=hours)
        return [e for e in self.events if now - pd.Timedelta(minutes=30) <= e["ts"] <= end]

    def public(self, now: pd.Timestamp, hours: float = 24 * 7) -> list[dict]:
        out = []
        for e in self.upcoming(now, hours):
            b, a = self._win(e["tier"])
            out.append({"title": e["title"], "ts": e["ts"].isoformat(), "tier": e["tier"], "impact": e["impact"],
                        "country": e["country"], "forecast": e["forecast"], "previous": e["previous"],
                        "minutes_to": round((e["ts"] - now).total_seconds() / 60),
                        "blackout": [b, a]})
        return out

    def brief(self, now: pd.Timestamp, hours: float = 6) -> list[dict]:
        """Compact list for Jev's state."""
        return [{"event": e["title"], "tier": e["tier"], "in_minutes": round((e["ts"] - now).total_seconds() / 60)}
                for e in self.upcoming(now, hours)][:6]
