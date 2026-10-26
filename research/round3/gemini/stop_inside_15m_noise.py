import numpy as np
import pandas as pd


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flags trades whose stop distance is smaller than 0.50 * ATR15(14) on
    3m/5m entries (inside single-bar 15m noise) OR where the 1-minute bid-ask
    spread at entry exceeds 8% of the stop distance.
    """
    ts = pd.Timestamp(trade["ts"])
    tf_str = str(trade.get("tf", "5m")).strip().lower()
    risk_atr = float(trade.get("risk_atr", 0.0))
    if risk_atr <= 0.0:
        return False

    tf_map = {"3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min"}
    tf_mins = {"3m": 3, "5m": 5, "15m": 15, "30m": 30}
    rule_tf = tf_map.get(tf_str, "5min")
    delta_min = tf_mins.get(tf_str, 5)

    start_cut = ts - pd.Timedelta(days=5)
    df = m1.loc[(m1.index >= start_cut) & (m1.index < ts)]
    if len(df) < 240:
        return False

    # Entry-timeframe completed candles for reconstructing stop distance in price units
    btf = (
        df.resample(rule_tf, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    btf = btf.loc[btf.index + pd.Timedelta(minutes=delta_min) <= ts]
    if len(btf) < 15:
        return False

    htf = btf["high"].to_numpy(dtype=float)
    ltf = btf["low"].to_numpy(dtype=float)
    ctf = btf["close"].to_numpy(dtype=float)
    prev_ctf = np.roll(ctf, 1)
    prev_ctf[0] = btf["open"].iloc[0]
    tr_tf = np.maximum(
        htf - ltf, np.maximum(np.abs(htf - prev_ctf), np.abs(ltf - prev_ctf))
    )
    atr_tf = float(np.mean(tr_tf[-14:]))
    if not np.isfinite(atr_tf) or atr_tf <= 0.0:
        return False

    stop_dist = risk_atr * atr_tf

    # Check 1: Current 1-minute spread exceeds 8% of stop distance
    curr_spread = float(df["spread"].iloc[-1])
    if curr_spread / stop_dist > 0.08:
        return True

    # Check 2: On 3m/5m entries, stop distance is < 0.50 * ATR15(14)
    if tf_str in ("3m", "5m"):
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
        if np.isfinite(atr15) and atr15 > 0.0:
            if stop_dist < 0.50 * atr15:
                return True

    return False