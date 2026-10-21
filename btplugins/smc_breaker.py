"""SMC — smc_breaker: SMC/ICT breaker block: price sweeps a swing low (liquidity), then breaks the swing high (MSS).
The last up-candle before the sweep leg is the breaker; enter on the retest, stop below the sweep low.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcBreaker(BotSetup):
    name = 'smc_breaker'
    symbol = "BTCUSD"
    description = 'SMC/ICT breaker block: price sweeps a swing low (liquidity), then breaks the swing high (MSS)'
    params = {'setup': 'smc_breaker',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
