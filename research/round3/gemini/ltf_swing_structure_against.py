import numpy as np
import pandas as pd


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flags trades when confirmed 5m swing structure over the last 3 hours
    (36 completed 5m bars, 2-bar left/right fractal confirmation) has both
    swing highs and swing lows progressing against `side` AND current price
    is on the opposing side of the 5m EMA(12) (1-hour mean).
    """
    ts = pd.Timestamp(trade["ts"])
    side = int(trade["side"])
    if side == 0:
        return False

    start_cut = ts - pd.Timedelta(days=3)
    df = m1.loc[(m1.index >= start_cut) & (m1.index < ts)]
    if len(df) < 180:
        return False

    b5 = (
        df.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    b5 = b5.loc[b5.index + pd.Timedelta(minutes=5) <= ts]
    if len(b5) < 36:
        return False

    h = b5["high"].to_numpy(dtype=float)
    l = b5["low"].to_numpy(dtype=float)
    c = b5["close"].to_numpy(dtype=float)

    # 12-bar (60-minute) EMA on completed 5m closes
    ema_n = 12
    alpha = 2.0 / (ema_n + 1.0)
    seg = c[-48:] if len(c) >= 48 else c
    ema12 = float(seg[0])
    for val in seg[1:]:
        ema12 = alpha * float(val) + (1.0 - alpha) * ema12

    p_now = float(df["close"].iloc[-1])

    # Search confirmed 2-left, 2-right 5m swings in the last 36 completed 5m bars
    win_h = h[-36:]
    win_l = l[-36:]
    swing_highs = []
    swing_lows = []

    for k in range(2, len(win_h) - 2):
        hk = win_h[k]
        if (
            hk >= win_h[k - 2]
            and hk >= win_h[k - 1]
            and hk > win_h[k + 1]
            and hk > win_h[k + 2]
        ):
            swing_highs.append(float(hk))

        lk = win_l[k]
        if (
            lk <= win_l[k - 2]
            and lk <= win_l[k - 1]
            and lk < win_l[k + 1]
            and lk < win_l[k + 2]
        ):
            swing_lows.append(float(lk))

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return False

    sh_prev, sh_last = swing_highs[-2], swing_highs[-1]
    sl_prev, sl_last = swing_lows[-2], swing_lows[-1]

    if side < 0:
        # Shorting into higher 5m swing highs + higher 5m swing lows + above 1H mean
        return (sh_last > sh_prev) and (sl_last > sl_prev) and (p_now > ema12)
    else:
        # Buying into lower 5m swing highs + lower 5m swing lows + below 1H mean
        return (sh_last < sh_prev) and (sl_last < sl_prev) and (p_now < ema12)