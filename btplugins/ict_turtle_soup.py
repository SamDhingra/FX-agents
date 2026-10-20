"""ICT — ict_turtle_soup: ICT Turtle Soup: price runs an old low (prior 20/40-bar low, prior-day low or Asia/London
low) to take the stops below it, then fails: entry on the close back above the level (within 3 bars) or on the
change of character that follows. Stop beyond the raid's extreme.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class IctTurtleSoup(BotSetup):
    name = 'ict_turtle_soup'
    symbol = "BTCUSD"
    description = 'ICT Turtle Soup: price runs an old low (prior 20/40-bar low, prior-day low or Asia/London low) to take the stops below it, then fails: entry on the …'
    params = {'setup': 'ict_turtle_soup',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
