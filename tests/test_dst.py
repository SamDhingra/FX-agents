"""Nov 1 2026 incident: New York's repeated 01:00–02:00 hour broke Timestamp.floor and killed the price feed."""
import pandas as pd
import pytest

from fxagents.timeutil import tfloor

TZ = "America/New_York"


def test_plain_floor_fails_in_the_repeated_hour_and_tfloor_does_not():
    t = pd.Timestamp("2026-11-01 05:00:07", tz="UTC").tz_convert(TZ)        # 01:00:07 EDT (first pass)
    with pytest.raises(ValueError):
        t.floor("5min")
    assert tfloor(t, "5min") == pd.Timestamp("2026-11-01 05:00", tz="UTC")
    t2 = pd.Timestamp("2026-11-01 06:00:07", tz="UTC").tz_convert(TZ)       # 01:00:07 EST (second pass)
    assert tfloor(t2, "min") == pd.Timestamp("2026-11-01 06:00", tz="UTC")
    assert tfloor(t2, "h") == pd.Timestamp("2026-11-01 06:00", tz="UTC")
    for f in ("min", "5min", "15min", "h"):                                  # same as before on ordinary days
        x = pd.Timestamp("2026-10-28 10:37:21", tz=TZ)
        assert tfloor(x, f) == x.floor(f)
    assert tfloor(pd.Timestamp("2026-03-08 03:30", tz=TZ), "h") == pd.Timestamp("2026-03-08 03:00", tz=TZ)   # spring forward
    assert tfloor(pd.Timestamp("2026-10-28 10:37"), "h") == pd.Timestamp("2026-10-28 10:00")                 # naive


def test_feed_loop_survives_an_error(monkeypatch):
    import asyncio
    from tests.test_oanda import setup
    cfg, fake, c, st, bus, feed, b = setup()
    calls = {"n": 0}

    async def boom():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("Cannot infer dst time")
        return 0
    feed.poll_once = boom
    feed.poll_seconds = 0.01
    feed.last_ts = {}

    async def go():
        t = asyncio.ensure_future(feed.run())
        await asyncio.sleep(2.5)
        t.cancel()
    import fxagents.oanda as O
    monkeypatch.setattr(O.asyncio, "sleep", asyncio.sleep)
    asyncio.run(go())
    assert calls["n"] >= 2                     # kept polling after the error
