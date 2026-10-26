import numpy as np
import pandas as pd


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flags trades entering against an active 15m counter-impulse leg:
    either a 2-bar completed 15m staircase against `side` or a single completed
    15m wide-range counter-expansion bar (body >= 0.75 * ATR15(14) closing in
    the opposing 25% tail).
    """
    ts = pd.Timestamp(trade["ts"])
    side = int(trade["side"])
    if side == 0:
        return False

    # Read strictly prior 1-minute bars (up to 5 days back is plenty for 15m ATR(14))
    start_cut = ts - pd.Timedelta(days=5)
    df = m1.loc[(m1.index >= start_cut) & (m1.index < ts)]
    if len(df) < 240:
        return False

    b15 = (
        df.resample("15min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    # Keep only 15m candles that have fully ended by ts
    b15 = b15.loc[b15.index + pd.Timedelta(minutes=15) <= ts]
    if len(b15) < 16:
        return False

    o = b15["open"].to_numpy(dtype=float)
    h = b15["high"].to_numpy(dtype=float)
    l = b15["low"].to_numpy(dtype=float)
    c = b15["close"].to_numpy(dtype=float)

    prev_c = np.roll(c, 1)
    prev_c[0] = o[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr15 = float(np.mean(tr[-14:]))
    if not np.isfinite(atr15) or atr15 <= 0.0:
        return False

    o1, h1, l1, c1 = o[-1], h[-1], l[-1], c[-1]
    o2, h2, l2, c2 = o[-2], h[-2], l[-2], c[-2]

    # Condition 1: 2-bar completed 15m staircase against `side`
    both_opposing = (side * (c2 - o2) < 0.0) and (side * (c1 - o1) < 0.0)
    close_extending = (side * (c1 - c2)) < 0.0
    extreme_extending = (h1 > h2) if side < 0 else (l1 < l2)
    if both_opposing and close_extending and extreme_extending:
        return True

    # Condition 2: Last completed 15m bar is a wide-range counter-marubozu
    rng1 = h1 - l1
    body1 = abs(c1 - o1)
    if rng1 > 0.0 and (side * (c1 - o1) < 0.0) and (body1 >= 0.75 * atr15):
        opposing_tail = (h1 - c1) / rng1 if side < 0 else (c1 - l1) / rng1
        if opposing_tail <= 0.25:
            return True

    return False