"""htf_b_daily_h1_cisd — Sam's model B (Oct 23 2026): Daily FVG or PDH/PDL taken → 1H FVG + CISD → resting-liquidity target.

Rules fixed before any run: see fxagents/bt/htf_poi.py (its text, the level map in fxagents/liquidity.py and the
helpers are part of this plugin's fingerprint). Param `entry`: "market" (confirmation close) or "limit_mid" (limit at
the confirmation FVG's midpoint) — both are run and judged together. Instruments: NDQ, US30.
"""
from fxagents.bt import Exits, Strategy
from fxagents.bt.htf_poi import MODELS


class HtfBDailyH1Cisd(Strategy):
    name = "htf_b_daily_h1_cisd"
    symbol = "NDQ"
    description = "Model B: Daily FVG or PDH/PDL taken → 1H FVG + CISD → nearest untaken liquidity ≥ 1R."
    params = {"entry": "market"}
    exits = Exits(flat_at=950)
    entry_windows = [(510, 690), (810, 930)]
    max_per_day = 2
    warmup_days = 250                 # 60-day target levels + daily ATR settle well inside this (audit re-runs)

    def signals(self, m):
        return MODELS["B"](m, self.params)
