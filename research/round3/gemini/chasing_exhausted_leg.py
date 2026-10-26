import numpy as np
import pandas as pd


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flags trades that chase an un-retraced 60-minute expansion leg in the
    trade's own direction: 60-minute displacement >= 2.0 * ATR15(14) in `side`
    while entry price is within 0.25 * ATR15(14) of the 60-minute extreme.
    """
    ts = pd.Timestamp(trade["ts"])
    side = int(trade["side"])
    if side == 0:
        return False

    start_cut = ts - pd.Timedelta(days=5)
    df = m1.loc[(m1.index >= start_cut) & (m1.index < ts)]
    if len(df) < 240:
        return False

    b15 = (
        df.resample("15min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    b15 = b15.loc[b15.index + pd.Timedelta(minutes=15) <= ts]
    if len(b15) < 15:
        return False

    h15 = b15["high"].to_numpy(dtype=float)
    l15 = b15["low"].to_numpy(dtype=float)
    c15 = b15["close"].to_numpy(dtype=float)
    prev_c15 = np.roll(c15, 1)
    prev_c15[0] = b15["open"].iloc[0]
    tr15 = np.maximum(
        h15 - l15, np.maximum(np.abs(h15 - prev_c15), np.abs(l15 - prev_c15))
    )
    atr15 = float(np.mean(tr15[-14:]))
    if not np.isfinite(atr15) or atr15 <= 0.0:
        return False

    win60 = df.loc[df.index >= (ts - pd.Timedelta(minutes=60))]
    if len(win60) < 15:
        return False

    h60 = float(win60["high"].max())
    l60 = float(win60["low"].min())
    p_now = float(win60["close"].iloc[-1])

    if side > 0:
        leg_up = p_now - l60
        pullback_from_high = h60 - p_now
        return (leg_up >= 2.0 * atr15) and (pullback_from_high < 0.25 * atr15)
    else:
        leg_dn = h60 - p_now
        bounce_from_low = p_now - l60
        return (leg_dn >= 2.0 * atr15) and (bounce_from_low < 0.25 * atr15)