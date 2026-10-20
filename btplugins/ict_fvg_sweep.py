"""ICT — ict_fvg_sweep: ICT Silver-Bullet style: a swing low/high is swept for liquidity, price displaces through
structure (MSS) leaving a fair value gap, entry on the retrace into the FVG inside a killzone, stop beyond the sweep
extreme, filtered by 1H bias.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class IctFvgSweep(BotSetup):
    name = 'ict_fvg_sweep'
    symbol = "BTCUSD"
    description = 'ICT Silver-Bullet style: a swing low/high is swept for liquidity, price displaces through structure (MSS) leaving a fair value gap, entry on the …'
    params = {'setup': 'ict_fvg_sweep',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
