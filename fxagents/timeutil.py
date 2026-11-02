"""DST-safe rounding of timezone-aware timestamps (Nov 1 2026 incident).

pandas' Timestamp.floor/ceil/round on a New York time inside the repeated hour of the autumn clock change (01:00–02:00
on the first Sunday of November) raises "Cannot infer dst time", because it rounds the LOCAL wall time and then has to
localize it again. On Nov 1 2026 that exception killed the OANDA price feed loop: no bars for the whole Sunday open.

These helpers round in UTC and convert back, which is exact for every frequency the bot uses (minutes, 5/15 min,
hours): New York's UTC offset is a whole number of hours. Naive timestamps are rounded as before."""
from __future__ import annotations

import pandas as pd


def _do(ts, freq: str, how: str):
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        return getattr(ts, how)(freq)
    tz = ts.tz
    return getattr(ts.tz_convert("UTC"), how)(freq).tz_convert(tz)


def tfloor(ts, freq: str) -> pd.Timestamp:
    return _do(ts, freq, "floor")


def tceil(ts, freq: str) -> pd.Timestamp:
    return _do(ts, freq, "ceil")
