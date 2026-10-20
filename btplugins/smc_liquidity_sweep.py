"""SMC — smc_liquidity_sweep: Liquidity raid: price runs the previous day's low/high or the Asia range extreme, closes
back inside, then shifts structure (CHoCH) on the entry timeframe. Stop beyond the raid.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcLiquiditySweep(BotSetup):
    name = 'smc_liquidity_sweep'
    symbol = "BTCUSD"
    description = "Liquidity raid: price runs the previous day's low/high or the Asia range extreme, closes back inside, then shifts structure (CHoCH) on the entry …"
    params = {'setup': 'smc_liquidity_sweep',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
