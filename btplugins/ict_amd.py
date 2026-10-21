"""ICT — ict_amd: ICT AMD / power of three: Accumulation (the Asia range, or price around the midnight open),
Manipulation (a Judas swing below the Asia low / midnight open during London or the NY open), Distribution (price
reclaims it and shifts structure). Entry on the reclaim/CHoCH, stop below the manipulation low. One trade per side
per day.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class IctAmd(BotSetup):
    name = 'ict_amd'
    symbol = "BTCUSD"
    description = 'ICT AMD / power of three: Accumulation (the Asia range, or price around the midnight open), Manipulation (a Judas swing below the Asia low / midnight …'
    params = {'setup': 'ict_amd',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
