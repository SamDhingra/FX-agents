"""SMC — smc_ifvg: Inverse FVG: an opposing fair value gap that price closes through flips polarity; enter on the
retest of the inverted gap, stop beyond it.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcIfvg(BotSetup):
    name = 'smc_ifvg'
    symbol = "BTCUSD"
    description = 'Inverse FVG: an opposing fair value gap that price closes through flips polarity; enter on the retest of the inverted gap, stop beyond it.'
    params = {'setup': 'smc_ifvg',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
