"""ICT — ict_2022: ICT 2022 model: inside a killzone, price raids sell-side liquidity (a swing low, or the
Asia/London/prior-day low), then shifts structure with displacement (close above the last swing high with a ≥1 ATR
body) leaving a fair value gap. Entry on the retrace into that FVG, optionally only in the discount half of the
dealing range; stop beyond the raid low or the FVG.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class Ict2022(BotSetup):
    name = 'ict_2022'
    symbol = "BTCUSD"
    description = 'ICT 2022 model: inside a killzone, price raids sell-side liquidity (a swing low, or the Asia/London/prior-day low), then shifts structure with …'
    params = {'setup': 'ict_2022',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
