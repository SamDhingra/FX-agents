"""SMC — smc_choch: Change of character: the FIRST close above a swing high while the trend was down. After price moves
away, entry on the bullish retest of that level; stop below the low that made the CHoCH.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcChoch(BotSetup):
    name = 'smc_choch'
    symbol = "BTCUSD"
    description = 'Change of character: the FIRST close above a swing high while the trend was down'
    params = {'setup': 'smc_choch',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
