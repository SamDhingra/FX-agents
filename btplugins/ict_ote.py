"""ICT — ict_ote: ICT Optimal Trade Entry: after a market-structure break, enter the 62–79% retracement of the impulse
leg inside a killzone, stop beyond the leg origin.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class IctOte(BotSetup):
    name = 'ict_ote'
    symbol = "BTCUSD"
    description = 'ICT Optimal Trade Entry: after a market-structure break, enter the 62–79% retracement of the impulse leg inside a killzone, stop beyond the leg …'
    params = {'setup': 'ict_ote',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
