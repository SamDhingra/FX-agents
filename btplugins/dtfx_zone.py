"""DTFX — dtfx_zone: DTFX-style, simplified (the original version here — not a formal DTFX definition; see the dtfx_*
setups for those): the leg that broke structure becomes the zone (30/50/70% levels); enter on a confirmed rejection
from the zone, stop beyond the zone origin (100%).

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class DtfxZone(BotSetup):
    name = 'dtfx_zone'
    symbol = "BTCUSD"
    description = 'DTFX-style, simplified (the original version here — not a formal DTFX definition; see the dtfx_* setups for those): the leg that broke structure …'
    params = {'setup': 'dtfx_zone',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
