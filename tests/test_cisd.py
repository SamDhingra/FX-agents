"""CISD level = open of the earliest candle of the last unbroken delivery series; doji skipped."""
import numpy as np

from fxagents.cisd_test import cisd_level


def test_bullish_level_is_first_open_of_down_series_skipping_doji():
    #            up    down  down  doji  down(X)
    o = np.array([9.0, 10.0, 9.5, 9.0, 9.0])
    c = np.array([10.0, 9.5, 9.0, 9.0, 8.0])
    assert cisd_level(o, c, 4, 1) == 10.0          # earliest down candle after the up candle


def test_extreme_candle_closing_up_looks_back_to_the_series():
    o = np.array([12.0, 11.0, 10.0, 9.0])          # down, down, down, then X closes up (wick low)
    c = np.array([11.0, 10.0, 9.2, 9.6])
    assert cisd_level(o, c, 3, 1) == 12.0


def test_bearish_mirror_and_none_without_series():
    o = np.array([10.0, 9.0, 9.5, 10.0])           # down, up, up, up(X)
    c = np.array([9.0, 9.5, 10.0, 10.5])
    assert cisd_level(o, c, 3, -1) == 9.0          # first up candle's open
    assert cisd_level(np.array([1.0, 2.0]), np.array([2.0, 3.0]), 1, 1) is None
