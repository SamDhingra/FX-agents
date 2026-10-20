"""h4_donchian_trend_v1: 4H NY alignment, financing charged on 17:00 crossings (the recorded fix), Friday flat, trail."""
import numpy as np
import pandas as pd

import fxagents.h4_donchian as H
from fxagents.gemini_smc import block_mask


def gold(n_days=400, seed=4, sigma=1.1, start="2022-01-02 18:00"):
    """Synthetic 1-minute gold with OANDA's hours: daily 17:00–18:00 NY break, closed Fri 17:00 → Sun 18:00."""
    idx = pd.date_range(start, periods=n_days * 1440, freq="1min", tz="America/New_York")
    m = idx.hour * 60 + idx.minute
    keep = ~((m >= 1020) & (m < 1080)) & ~(idx.dayofweek == 5) & ~((idx.dayofweek == 4) & (m >= 1020)) \
        & ~((idx.dayofweek == 6) & (m < 1080))
    idx = idx[keep]
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.25, len(idx) // 3000 + 1), 3000)[:len(idx)]   # trending stretches
    p = 1800 + np.cumsum(rng.normal(0, sigma, len(idx)) + drift)
    d = pd.DataFrame(index=idx.tz_convert("UTC"))
    wig = np.abs(rng.normal(0, sigma, len(idx)))
    o, c = np.r_[p[0], p[:-1]], p
    for side, sh in (("bid", -0.15), ("ask", 0.15)):
        d[f"{side}_o"], d[f"{side}_c"] = o + sh, c + sh
        d[f"{side}_h"], d[f"{side}_l"] = np.maximum(o, c) + wig + sh, np.minimum(o, c) - wig + sh
    for f in "ohlc":
        d[f"m_{f}"] = (d[f"bid_{f}"] + d[f"ask_{f}"]) / 2
    d["volume"] = 100
    return d


def test_bars_close_on_the_ny_grid():
    a = H.prepare(gold(30))
    assert set(np.unique(a["b4"].end_mod)) <= {60, 300, 540, 780, 1020, 1260}


def test_trades_pay_financing_and_respect_the_exits():
    a = H.prepare(gold())
    tr, ctl = H.execute(a, H.find_trades(a, True), block_mask(a, 15, 15), np.random.default_rng(1))
    T = pd.DataFrame(tr)
    assert len(T) >= 3 and len(ctl) == len(T)
    over = T[T.overnight]
    assert len(over) and (over.swap > 0).all()                       # the fix: overnight holds are charged
    assert (T[~T.overnight].swap == 0).all()
    assert (T.hold_min <= H.MAX_HOLD_MIN + 1).all()
    ex = pd.to_datetime(T.exit_time).dt.tz_convert("America/New_York")
    assert not ((ex.dt.dayofweek == 4) & (ex.dt.hour * 60 + ex.dt.minute > H.FRI_FLAT)).any()
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    assert (loc.dt.hour.isin([1, 5, 9, 13]) & (loc.dt.minute <= 10)).all()
    assert (T[T.exit_reason == "stop"].R <= -0.99 - 1e-9 + 0.01).all()
