"""Trade analyst (shadow): its checks, that it logs verdict changes only, never acts, and scores advice on close."""
import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd

from fxagents.agents.analyst import TradeAnalystAgent, checks_for, scorecard, verdict_of
from fxagents.config import load_config
from fxagents.journal import Journal
from fxagents.models import Leg, Position

NY = "America/New_York"


def frame(closes, start="2026-10-19 08:00", freq="5min", wick=0.3):
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range(start, periods=len(c), freq=freq, tz=NY)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + wick, "low": np.minimum(o, c) - wick, "close": c}, index=idx)


def b5_break():
    b = frame([100, 101, 99, 101, 102, 103, 102, 101, 96])
    b.loc[b.index[2], "low"] = 97.5                       # a clear swing low at 97.5 …
    return b                                              # … broken by the last 5m close (96)


def test_checks():
    up = frame(np.linspace(100, 130, 80), freq="15min")
    flip = frame(np.r_[np.linspace(100, 130, 79), 100.0], freq="15min")       # last close drops through the EMA
    b5 = b5_break()
    b60 = frame(np.linspace(130, 100, 60), freq="1h")                           # falling hourly
    assert "trend_flip" in checks_for(1, b5, flip, b60, 0.2, 0.1, 10, None)
    assert "trend_flip" not in checks_for(1, b5, up, b60, 0.2, 0.1, 10, None)
    c = checks_for(1, b5, up, b60, mfe=1.4, r_now=0.6, idle_min=70, news_in=12)
    assert {"structure_break", "h1_against", "giveback", "news_soon"} <= set(c) and "stall" not in c
    assert "stall" in checks_for(1, b5, up, b60, 0.3, 0.2, 65, None)
    assert verdict_of(["h1_against"]) == "tighten" and verdict_of(["stall", "h1_against"]) == "exit"
    assert verdict_of([]) == "hold"


class Store:
    def __init__(self, frames):
        self.frames = frames

    def tf(self, sym, rule):
        return self.frames[rule]


def agent(tmp_path, frames):
    cfg = load_config("config.yaml")
    j = Journal(str(tmp_path / "j.sqlite"))
    state = SimpleNamespace(positions={}, now=None, beat=lambda n: None)
    ctx = SimpleNamespace(cfg=cfg, bus=SimpleNamespace(subscribe=lambda *a: None), state=state, store=Store(frames),
                          journal=j, news=None)
    a = TradeAnalystAgent(ctx)
    a.start()
    return a, j, state


def test_shadow_agent_logs_changes_only_and_scores_on_close(tmp_path):
    frames = {"5min": b5_break(),
              "15min": frame(np.linspace(100, 130, 80), freq="15min"),
              "1h": frame(np.linspace(100, 130, 60), freq="1h")}
    a, j, state = agent(tmp_path, frames)
    t0 = pd.Timestamp("2026-10-19 08:00", tz=NY)
    pos = Position("XAUUSD", 1, "x:5m@pb", 95.0, 95.0, 5.0, 1.0, t0.to_pydatetime())
    pos.add_leg(Leg(1.0, 100.0, t0.to_pydatetime(), "initial"))
    stop_before = pos.stop
    r1 = a.analyse(pos, 98.0, t0 + pd.Timedelta("45min"))
    a.analyse(pos, 98.2, t0 + pd.Timedelta("50min"))
    assert r1["verdict"] == "exit" and "structure_break" in r1["checks"]
    assert len([e for e in pos.events if e["kind"] == "analyst"]) == 1          # same verdict again → not re-logged
    assert pos.stop == stop_before and pos.status == "open"                     # shadow: never touches the trade
    pos.realized, pos.status = -5.0 * float(a.cfg["instruments"]["XAUUSD"].get("multiplier", 1)), "closed"
    asyncio.run(a.on_closed({"position": pos}))
    sc = scorecard(j)
    row = next(c for c in sc["checks"] if c["check"] == "structure_break")
    assert sc["n_trades"] == 1 and row["n"] == 1
    assert abs(row["avg_value_r"] - (r1["r_if_exit"] - (-1.0))) < 1e-6 and row["avg_value_r"] > 0   # exiting at −0.4R beat −1R
    assert sc["recent"][0]["verdict"] == "exit"
