"""Cheap live probe of the shadow review providers (Oct 27 2026):

    python -m fxagents.dynamic.probe        (./fx.sh dynprobe)

Sends ONE round-1 review per configured provider (dynamic.claude_model / dynamic.openai_model, keys from the environment)
through the real provider code path (same prompt, request body, schema, parsing and validation as the live gate), on a small
SYNTHETIC packet: candidate id `probe-<timestamp>`, made-up XAUUSD numbers. Prints per provider the model, the action (or
ABSTAIN with the full error text), latency, tokens and cost. Stores nothing: no journal is opened, no row is written.
Exit code 0 only when every configured provider answered ENTER / WAIT / CANCEL.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import numpy as np
import pandas as pd

from .packet import build_packet, canonical
from .providers import ACTIONS, build_providers

TZ = "America/New_York"


def synthetic_packet(now: pd.Timestamp | None = None) -> dict:
    """A plausible but entirely made-up LONG XAUUSD candidate, with ~3 days of random-walk M1 candles before `now`."""
    ts = (now or pd.Timestamp.now(tz=TZ)).tz_convert(TZ).floor("min")
    idx = pd.date_range(ts - pd.Timedelta(days=3), ts - pd.Timedelta(minutes=1), freq="1min", tz=TZ)
    rng = np.random.default_rng(7)
    c = 2650.0 + np.cumsum(rng.normal(0, 0.3, len(idx)))
    m1 = pd.DataFrame({"open": c - 0.05, "high": c + 0.4, "low": c - 0.4, "close": c, "volume": 10.0}, index=idx)
    h1 = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    entry = round(float(c[-1]), 2)
    stop = round(entry - 2.0, 2)
    bias = {"label": "BULLISH", "score": 0.6, "d": 1, "h4": 1, "h1": 1, "updated": ts.isoformat(timespec="minutes"),
            "h1_minutes": 60, "h1_complete": True, "pdh": round(entry + 8, 2), "pdl": round(entry - 14, 2), "asia_hi": round(entry + 3, 2),
            "asia_lo": round(entry - 6, 2), "h4_swing_hi": round(entry + 10, 2), "h4_swing_lo": round(entry - 12, 2)}
    return build_packet(candidate_id="probe-" + ts.strftime("%Y%m%d%H%M%S"), book="probe", symbol="XAUUSD", side=1,
                        strategy="macd_cross:5m@probe", ts=ts, entry=entry, stop=stop, target_r=2.0, spread=0.31, cost_r=0.155,
                        instrument={"tick_size": 0.01}, m1=m1, h1=h1, bias=bias, record={"trades": 12, "avg_r": 0.2}, m15_live=False)


async def probe(providers: dict, packet: dict | None = None) -> list[dict]:
    """One round-1 review per provider, concurrently, via Provider.review (the live call). Nothing is stored."""
    packet = packet or synthetic_packet()
    text, cid = canonical(packet), packet["candidate"]["id"]
    names = list(providers)
    res = await asyncio.gather(*[providers[n].review(text, cid) for n in names])
    return [{"provider": n, "model": providers[n].model, **r} for n, r in zip(names, res)]


def line(r: dict) -> str:
    ok = r["action"] in ACTIONS
    lat = "—" if r.get("latency_ms") is None else f"{r['latency_ms'] / 1000:.2f} s"
    tok = f"{r.get('tokens_in')} in / {r.get('tokens_out')} out" if r.get("tokens_in") is not None else "no usage"
    cost = "—" if r.get("cost_usd") is None else f"${r['cost_usd']:.5f}"
    s = f"{r['provider']:7} {r['model']}: {'OK ' if ok else 'FAIL '}{r['action']}"
    if ok and r.get("trigger_id"):
        s += f" (trigger {r['trigger_id']})"
    s += f"  latency {lat}  tokens {tok}  cost {cost}"
    if r.get("error"):
        s += f"\n    error: {r['error']}"
    return s


async def run(cfg, providers: dict | None = None, packet: dict | None = None) -> int:
    providers = build_providers(cfg.get("dynamic") or {}) if providers is None else providers
    if not providers:
        print("no provider is configured (dynamic.claude_model / dynamic.openai_model are empty)", flush=True)
        return 1
    packet = packet or synthetic_packet()
    print(f"Probe {packet['candidate']['id']} (synthetic packet, nothing stored): one round-1 review per provider", flush=True)
    rows = await probe(providers, packet)
    for r in rows:
        print(line(r), flush=True)
    bad = [r["provider"] for r in rows if r["action"] not in ACTIONS]
    print("ALL PROVIDERS ANSWERED" if not bad else f"NOT ANSWERED: {', '.join(bad)}", flush=True)
    return 0 if not bad else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args(argv)
    from ..config import load_config
    return asyncio.run(run(load_config(a.config)))


if __name__ == "__main__":
    sys.exit(main())
