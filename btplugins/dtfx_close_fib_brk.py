"""DTFX — dtfx_close_fib_brk: DTFX — close-based structure, Fibonacci zone anchored valid low → the HIGH OF THE CANDLE
THAT BROKE STRUCTURE (not the later extreme); first-touch entry, stop below the protected low.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class DtfxCloseFibBrk(BotSetup):
    name = 'dtfx_close_fib_brk'
    symbol = "BTCUSD"
    description = 'DTFX — close-based structure, Fibonacci zone anchored valid low → the HIGH OF THE CANDLE THAT BROKE STRUCTURE (not the later extreme); first-touch …'
    params = {'setup': 'dtfx_close_fib_brk',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
