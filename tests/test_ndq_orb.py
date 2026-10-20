"""ndq_orb_vwap_v1: entries only 09:48–11:15 NY after the 09:30–09:45 range, one a day, exact coin flip, spec fixes."""
import numpy as np
import pandas as pd

import fxagents.ndq_orb as N
from fxagents.gemini_smc import block_mask
from tests.test_gemini_smc import frame, walk


def index_data(seed=5, days=150):
    m = frame(walk(n_days=days, seed=seed, base=15000.0), sp=0.2)
    for c in [c for c in m.columns if c != "volume"]:
        m[c] = 15000 + (m[c] - 15000) * 12
    for s in "ohlc":                                       # keep the bid/ask 1.5 points apart after the scaling
        mid = m[f"m_{s}"]
        m[f"bid_{s}"], m[f"ask_{s}"] = mid - 0.75, mid + 0.75
    return m


def test_trades_follow_the_spec():
    a = N.prepare(index_data())
    assert a["i15_or"] and all(pd.Timestamp(a["b15"].index[i]).tz_convert("America/New_York").strftime("%H:%M") == "09:30"
                               for i in list(a["i15_or"].values())[:20])
    ents = N.find_trades(a, True)
    tr, ctl = N.execute(a, ents, block_mask(a, 15, 15), cad_fx=True)
    T = pd.DataFrame(tr)
    assert len(T) >= 5 and len(ctl) == len(T)
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    m = loc.dt.hour * 60 + loc.dt.minute
    assert ((m >= N.WIN[0]) & (m <= N.WIN[1])).all()
    assert T.groupby(loc.dt.date).size().max() == 1
    assert set(T.exit_reason) <= {"stop", "trail_stop", "target", "flat_1555", "closure", "end"}
    assert (T[T.exit_reason == "stop"].R < -1.0).all()                 # stop slippage + 1% CAD on losses
    C = pd.DataFrame(ctl)
    assert (C.exit_reason == "exact_coin").all()
