"""SMC — smc_order_block: SMC order block: after a displacement leg breaks structure (BOS), the last opposing candle
before the leg is the order block. Enter on the first return into the block, stop beyond it. Optional: the leg must
leave an FVG.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcOrderBlock(BotSetup):
    name = 'smc_order_block'
    symbol = "BTCUSD"
    description = 'SMC order block: after a displacement leg breaks structure (BOS), the last opposing candle before the leg is the order block'
    params = {'setup': 'smc_order_block',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
