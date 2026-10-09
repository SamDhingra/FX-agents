"""export_history streams bid/ask candles page by page, keeps only complete ones inside [start, end)."""
import asyncio

import pandas as pd

from fxagents.export_history import export_one


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


def test_streams_pages_and_clips_window(tmp_path):
    times = list(pd.date_range("2025-01-01", periods=12000, freq="1min", tz="UTC"))
    st = Stub(times)
    start, end = pd.Timestamp("2025-01-01 00:10", tz="UTC"), pd.Timestamp("2025-01-08", tz="UTC")
    f = tmp_path / "XAUUSD_M1.csv.gz"
    info = asyncio.run(export_one(st, "XAU_USD", "M1", start, end, f))
    df = pd.read_csv(f)
    t = pd.to_datetime(df["time"], utc=True)
    assert t.min() == start and t.max() == end - pd.Timedelta("1min")
    assert st.calls >= 3 and info["rows"] == len(df) and t.is_monotonic_increasing and t.is_unique
    assert not (t.dt.minute == 7).any()
    assert list(df.columns)[:3] == ["time", "bid_o", "bid_h"] and df["ask_c"].iloc[0] == 100.5
    assert info["first"] == "2025-01-01T00:10:00Z" and not (tmp_path / "XAUUSD_M1.part").exists()
