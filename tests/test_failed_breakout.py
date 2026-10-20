"""Failed-breakout reversal (author's verbatim functions): signals respect the range, window and one-a-day rule."""
import numpy as np
import pandas as pd

import fxagents.failed_breakout as F
from fxagents.gemini_smc import block_mask
from tests.test_gemini_smc import frame, walk


def test_signals_and_trades_follow_the_spec():
    a = F.prepare(frame(walk(seed=17, n_days=200)))
    ents, funnel = F.find_signals(a, block_mask(a, 15, 15))
    vals = list(funnel.values())
    assert all(x >= y for x, y in zip(vals[1:], vals[2:]))               # the funnel only narrows
    assert len({e["sess"] for e in ents}) == len(ents)                     # one trade per day
    tr, ctl = F.execute(a, ents, np.random.default_rng(1))
    T = pd.DataFrame(tr)
    if len(T):
        loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
        m = loc.dt.hour * 60 + loc.dt.minute
        assert ((m > F.WIN[0]) & (m <= F.WIN[1])).all() and (m % 3 == 0).all()
        assert set(T.exit_reason) <= {"stop", "midpoint_target", "flat_1130", "closure", "end"}
        assert (T[T.exit_reason == "stop"].R <= -0.99).all()
