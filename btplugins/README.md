# Backtest plugins

One `.py` file per strategy, one `Strategy` class per file. The plugin only says **when** to enter and **where** the stop
(and optionally the target) is. The engine does the rest, the same way for every strategy:

- real OANDA bid/ask 1-minute fills, with stop slippage
- spread, financing on 17:00 NY holds, and the 1% CAD conversion
- exits, news blocks and the exact coin-flip control
- statistics and the pass gates
- the look-ahead audit, and the seen/vault protocol

```python
from fxagents.bt import Strategy, Signal, Exits, ind

class MyIdea(Strategy):
    name = "my_idea_v1"
    symbol = "XAUUSD"
    description = "15m close crosses above EMA50; stop under the candle."
    params = {"ema": 50}                       # anything you might vary goes here
    exits = Exits(target_r=2.0, be_at_r=1.0, flat_at=950)   # 950 = 15:50 NY
    entry_windows = [(480, 690)]               # fills 08:00–11:30 NY
    max_per_day = 1
    variants = {"slow": {"ema": 100}}          # controls the rule must beat

    def signals(self, m):                      # m: fxagents.bt.data.Market
        b = m.bars(15)                         # mid candles: o h l c v start end
        e = ind.ema(b.c, self.p("ema"))
        return [Signal(t=int(b.end.iloc[i]), side=1, stop=float(b.l.iloc[i]))
                for i in range(1, len(b)) if b.c.iloc[i] > e[i] and b.c.iloc[i - 1] <= e[i - 1]]
```

## Rules

- **`Signal.t` is when the decision is known.** That is usually a candle's `end`, and the signal may use only data that existed by then.
  - The audit re-runs signals on data that stops at `t`. Any signal that disappears there fails the run.
- **Prices in a Signal are real prices** (shorts are not mirrored). `side` is `1` for long, `-1` for short.
- **Candle sizes:** `m.bars(tf)` takes minutes (`5`, `15`, …), `"1h"`, `"4h"` or `"1d"`. 4H and daily candles follow the New York clock all year: 4H closes at 01/05/09/13/17/21, daily at 17:00.
- **Entry types:** `entry="limit"` or `entry="stop"`, with `price` and `expire_min`. `cancel` sets a level that kills the pending order.
- **Other `Signal` fields:**
  - `target`: overrides `Exits.target_r` with a fixed price.
  - `risk_min` and `risk_max`: skip the fill if its risk falls outside this range.
  - `draw`: shapes for the chart. Boxes take `hi`/`lo`, lines take `px`, and times are ns.
- **`Exits` fields:**
  - `target_r` and `partials=[(at_R, fraction, new_stop_R)]`
  - `be_at_r` and `be_lock_r`
  - `trail`: chandelier, swing or gap_r
  - `max_hold_min`, `flat_at`, `friday_flat_at`, `time_stop` and `hold_overnight`

## Running

Add the file through git, then run `./fx.sh update`. Then either:

- open **Backtester** in the dashboard, or
- run `./fx.sh bt btplugins/<file>.py`.

Every run is recorded with its exact code. The vault (2016–2020) opens once, and only for the identical code, parameters and instrument that passed every gate on seen data.
