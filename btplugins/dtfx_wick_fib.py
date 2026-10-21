"""DTFX — dtfx_wick_fib: DTFX — wick-based structure (any trade through a swing counts as the break and as the
invalidation), Fibonacci zone valid low → leg extreme, first-touch entry, stop below the protected low.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class DtfxWickFib(BotSetup):
    name = 'dtfx_wick_fib'
    symbol = "BTCUSD"
    description = 'DTFX — wick-based structure (any trade through a swing counts as the break and as the invalidation), Fibonacci zone valid low → leg extreme, …'
    params = {'setup': 'dtfx_wick_fib',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
