"""Stoic — stoic_sbs: Stoic Trader Swing Breakout Sequence: breakout (HH) → first tap (HL) → quick scalp (new HH) →
return to liquidate the first tap → double-bottom reversal → target the new swing high. Entry on the lower-timeframe
break after the double bottom.

The bot's own setup code (fxagents/strategies) run with the bot's live rules — see fxagents/bt/botsetups.py.
Entry timeframe: `tf` ("5min", "15min", …). Default instrument BTCUSD; pick any on the Backtester page.
"""
from fxagents.bt.botsetups import BotSetup


class StoicSbs(BotSetup):
    name = 'stoic_sbs'
    symbol = "BTCUSD"
    description = 'Stoic Trader Swing Breakout Sequence: breakout (HH) → first tap (HL) → quick scalp (new HH) → return to liquidate the first tap → double-bottom …'
    params = {'setup': 'stoic_sbs',
              'tf': '5min',
              'setup_params': {},
              'use_bias': True,
              'min_align': 0.25,
              'min_stop_atr': 0.5,
              'max_stop_pct': 0.1,
              'stall_min': 45,
              'stall_gap_r': 0.5,
              'mgmt': 'live'}
