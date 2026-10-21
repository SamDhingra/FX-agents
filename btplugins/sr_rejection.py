"""Classic — sr_rejection: Support/resistance: horizontal levels built from clustered swing points (≥2 touches). Enter on a rejection candle at the level, stop beyond the wick.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument US30 (the practice account's most-traded setup); pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SrRejection(BotSetup):
    name = 'sr_rejection'
    symbol = "US30"
    description = 'Support/resistance: horizontal levels built from clustered swing points (≥2 touches). Enter on a rejection candle at the level, stop beyond the wick.'
    params = {'setup': 'sr_rejection',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
