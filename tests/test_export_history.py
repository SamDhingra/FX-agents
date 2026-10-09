"""export_history pages bid/ask candles to the end of the window, keeps only complete ones inside it."""
import asyncio

import pandas as pd

from fxagents.export_history import fetch


class Stub:
    def __init__(self, times):
        self.times, self.calls = times, 0

    async def req(self, method, path, *, params=None, json=None):
        self.calls += 1
        frm = pd.Timestamp(params["from"])
        nxt = [t for t in self.times if t > frm][: int(params["count"])]
        q = lambda x: {"o": str(x), "h": str(x + 1), "l": str(x - 1), "c": str(x)}
        return {"candles": [{"time": t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "complete": t.minute != 7,
                             "bid": q(100.0), "ask": q(100.5), "volume": 3} for t in nxt]}


def test_pages_through_and_clips_window():
    times = list(pd.date_range("2025-01-01", periods=12000, freq="1min", tz="UTC"))
    st = Stub(times)
    start, end = pd.Timestamp("2025-01-01 00:10", tz="UTC"), pd.Timestamp("2025-01-08", tz="UTC")
    df = asyncio.run(fetch(st, "XAU_USD", "M1", start, end))
    t = pd.to_datetime(df["time"])
    assert t.min() == start and t.max() == end - pd.Timedelta("1min")   # every candle in [start, end)
    assert st.calls >= 3                                      # > 5000 candles → several pages
    assert not (t.dt.minute == 7).any()                       # incomplete candles dropped
    assert list(df.columns)[:3] == ["time", "bid_o", "bid_h"] and df["ask_c"].astype(float).iloc[0] == 100.5
    df2 = asyncio.run(fetch(Stub(times), "XAU_USD", "M1", start, pd.Timestamp("2025-01-01 01:00", tz="UTC")))
    assert pd.to_datetime(df2["time"]).max() < pd.Timestamp("2025-01-01 01:00", tz="UTC")
