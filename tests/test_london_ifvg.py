"""london_ifvg (a friend's London-sweep / inverse-FVG strategy): the rules fire on a hand-built day."""
import numpy as np
import pandas as pd

from fxagents.bt import data
from fxagents.bt.run import load_plugin


def _five(o, h, l, c):
    """One 5-minute mid candle as five 1-minute candles with the same o/h/l/c."""
    return [(o, h, o, h), (h, h, l, l), (l, l, l, l), (l, l, l, l), (l, max(l, c), l, c)]


def _market(candles, start="2025-03-04 08:30"):          # 08:30 UTC = 03:30 New York (EST)
    rows = [m for cd in candles for m in _five(*cd)]
    idx = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    a = np.array(rows, float)
    d = pd.DataFrame(index=idx)
    for i, f in enumerate("ohlc"):
        d[f"bid_{f}"], d[f"ask_{f}"] = a[:, i] - 0.01, a[:, i] + 0.01
    return data.from_frame(d)


def _day(sweep_close):
    box = [(100.0, 100.5, 99.5, 100.0)] * 60                                     # 03:30 … 08:25
    box += [(100.0, 100.2, 99.8, 100.1), (100.2, 100.9, 100.2, 100.8), (100.8, 101.0, 100.5, 100.9)]   # bullish FVG 100.2–100.5
    box += [(100.6, 100.8, 100.5, 100.6)] * 8                                     # … to 09:20; box high 101.0
    ny = [(100.6, 101.3, 100.6, 101.2),                                           # 09:25 closes above the London high
          (101.2, 101.3, 100.0, sweep_close)]                                     # 09:30 big body back inside
    ny += [(sweep_close, sweep_close, 99.0, 99.1)] * 6
    return _market(box + ny)


def test_high_sweep_then_close_through_the_bullish_fvg_goes_short():
    S, _ = load_plugin("btplugins/london_ifvg.py")
    s = S()
    m = _day(100.1)                                     # closes below the FVG bottom (100.2) on the sweep candle
    sig = s.signals(m)
    assert len(sig) == 1 and sig[0].side == -1 and sig[0].tag == "short_after_high_sweep"
    t = pd.Timestamp(sig[0].t, tz="UTC").tz_convert("America/New_York")
    assert (t.hour, t.minute) == (9, 35)                # decided at the 09:30 candle's close
    assert sig[0].stop > 100.1 > sig[0].target
    risk, reward = sig[0].stop - 100.1, 100.1 - sig[0].target
    assert abs(reward / risk - 0.1) < 1e-9              # preset: 2 ATR stop, 0.2 ATR target


def test_no_inversion_no_trade():
    S, _ = load_plugin("btplugins/london_ifvg.py")
    m = _day(100.3)                                     # back inside, but above the FVG bottom …
    sig = S().signals(m)
    # … the next candles close at 99.1, below it: that IS the IFVG, one candle later
    assert len(sig) == 1 and pd.Timestamp(sig[0].t, tz="UTC").tz_convert("America/New_York").minute == 40


def test_engine_fills_it_and_it_passes_the_lookahead_audit():
    from fxagents.bt import engine
    S, _ = load_plugin("btplugins/london_ifvg.py")
    s = S()
    m = _day(100.1)
    res = engine.simulate(s, m)
    T = res["trades"]
    assert len(T) == 1 and T[0]["exit_reason"] == "target" and 0 < T[0]["R"] < 0.1   # a "win" is worth < 0.1R
    a = engine.lookahead_audit(s, m, s.signals(m), 5, warm_days=0.2)   # 4.8 h of history before the signal
    assert a["checked"] == 1 and a["failed"] == 0
