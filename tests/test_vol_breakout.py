"""vol_breakout_v1 (author's verbatim functions): trend-aligned entries, ATR bounds, exits, one trade a day."""
import numpy as np
import pandas as pd

import fxagents.vol_breakout as V
from fxagents.gemini_smc import block_mask
from tests.test_gemini_smc import frame, walk


def test_entries_and_exits_follow_the_spec():
    a = V.prepare(frame(walk(seed=31, n_days=120)))
    ents = V.find_trades(a, True)
    assert ents and {e["mode"] for e in ents} == {"trend_brk"}
    tr, ctl = V.execute(a, ents, block_mask(a, 15, 15), np.random.default_rng(1))
    T = pd.DataFrame(tr)
    assert len(T) > 5 and len(ctl) == len(T)
    assert ((T.atr >= 0) & (T.exit_reason.isin(["stop", "be_stop", "target", "flat_1630", "closure", "end"]))).all()
    assert (T[T.exit_reason == "stop"].R <= -0.99).all()
    assert np.allclose(T[T.exit_reason == "target"].R, V.TP_R, atol=0.05)
    assert (T[T.exit_reason == "be_stop"].R <= V.BE_LOCK_R + 1e-9).all()
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    m = loc.dt.hour * 60 + loc.dt.minute
    assert ((m >= V.WIN[0] - 1) & (m < V.WIN[1])).all()
    assert T.groupby((loc + pd.Timedelta(hours=6)).dt.date).size().max() == 1


def test_calendar_matches_the_authors_copy():
    import fxagents.usd_calendar as U
    assert len(U.FOMC) == 48 + 39 and len(U.CPI) == len(U.NFP) == len(U.PPI) == 69 + 60    # 2016–2020 added Oct 25
