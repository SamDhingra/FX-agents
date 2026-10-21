"""DTFX — dtfx_close_origin: DTFX — close-based structure, zone = the origin candle (last opposing candle at the valid
low); entry on the first return to the zone, stop below the zone.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class DtfxCloseOrigin(BotSetup):
    name = 'dtfx_close_origin'
    symbol = "BTCUSD"
    description = 'DTFX — close-based structure, zone = the origin candle (last opposing candle at the valid low); entry on the first return to the zone, stop below the …'
    params = {'setup': 'dtfx_close_origin',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
