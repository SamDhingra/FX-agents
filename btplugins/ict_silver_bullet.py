"""ICT — ict_silver_bullet: ICT Silver Bullet: only inside 03–04, 10–11 or 14–15 NY. A displacement candle inside the
hour leaves a fair value gap (optionally after a raid on nearby sell-side liquidity); entry on the first retrace
into the FVG before the hour ends, stop below the FVG's first candle or the raid.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class IctSilverBullet(BotSetup):
    name = 'ict_silver_bullet'
    symbol = "BTCUSD"
    description = 'ICT Silver Bullet: only inside 03–04, 10–11 or 14–15 NY'
    params = {'setup': 'ict_silver_bullet',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
