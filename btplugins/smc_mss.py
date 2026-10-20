"""SMC — smc_mss: Market structure shift (aggressive entry): sell-side liquidity is swept (a swing low is taken), then
a displacement candle closes above the last swing high — a CHoCH made with displacement. Entry at that close, stop
below the sweep low.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcMss(BotSetup):
    name = 'smc_mss'
    symbol = "BTCUSD"
    description = 'Market structure shift (aggressive entry): sell-side liquidity is swept (a swing low is taken), then a displacement candle closes above the last …'
    params = {'setup': 'smc_mss',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
