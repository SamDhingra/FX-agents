"""SMC — smc_displacement: Displacement continuation: a displacement candle (body ≥ k × ATR, ≥ 60% of its range) that
breaks structure and leaves a fair value gap. Entry on the first retrace to the gap (its top, or its 50% 'consequent
encroachment'), stop below the displacement candle.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class SmcDisplacement(BotSetup):
    name = 'smc_displacement'
    symbol = "BTCUSD"
    description = 'Displacement continuation: a displacement candle (body ≥ k × ATR, ≥ 60% of its range) that breaks structure and leaves a fair value gap'
    params = {'setup': 'smc_displacement',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5}
