"""Astra's 15-strategy screen is vendored unchanged; the wrapper must not alter its inputs."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from fxagents import astra15_oanda as w

D = Path(__file__).resolve().parents[1] / "fxagents" / "astra15"


def test_vendored_files_are_astras_originals():
    assert hashlib.sha256((D / "backtest.py").read_bytes()).hexdigest().startswith("697e407e3b50c2ed")
    assert hashlib.sha256((D / "strategies.json").read_bytes()).hexdigest().startswith("9501f34e93b55310")


def test_export_keeps_mid_ohlcv_and_cuts_window(tmp_path):
    idx = pd.date_range("2026-03-20 13:00", periods=4 * 1440, freq="1min", tz="UTC")
    p = 100 + np.cumsum(np.random.default_rng(1).normal(0, .1, len(idx)))
    m1 = pd.DataFrame({"open": p, "high": p + .2, "low": p - .2, "close": p, "volume": 5.0}, index=idx)
    for s in w.SYMS:
        pd.to_pickle((m1, None), tmp_path / f"{s}.pkl")
    span = w.export(tmp_path, tmp_path / "csv", "2026-03-21", "2026-03-22")
    out = w.bt.load_data(tmp_path / "csv" / "XAUUSD.csv")
    assert span["XAUUSD"][:2] == ["2026-03-21", "2026-03-22"]
    assert out.index.min() >= pd.Timestamp("2026-03-21", tz="UTC") and out.index.max() < pd.Timestamp("2026-03-23", tz="UTC")
    assert np.allclose(out.close.to_numpy(), m1.loc[out.index, "close"].to_numpy())
