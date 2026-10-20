"""SMC — smc_bos_retest: Break of structure (continuation): in an up-trend, a close above the last swing high; after
price moves away, entry on the bullish retest of the broken level (old resistance → support). Stop below the leg's
origin low or 1 ATR below the level.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcBosRetest(BotSetup):
    name = 'smc_bos_retest'
    symbol = "BTCUSD"
    description = 'Break of structure (continuation): in an up-trend, a close above the last swing high; after price moves away, entry on the bullish retest of the …'
    params = {'setup': 'smc_bos_retest',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
