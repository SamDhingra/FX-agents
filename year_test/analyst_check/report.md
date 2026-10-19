# Analyst check — would a live trade analyst's exits have helped?

18 cells of the current playbook (as of 2026-10-17), 2025-10-08 → 2026-10-08, every candidate entry of each cell replayed on 1-minute bars with real spread under each exit rule. Same entries for every variant — only the exit changes, so the differences are paired. R per trade after spread.

**Today's rules turn a good start into a loss on 399 of 2946 entries (14%)**: they reached +0.5R or more and still closed at or below zero (avg -0.85R on those). Entries reaching +0.5R at all: 58%; reaching +1R: 39%.

**No variant beats today's rules by more than noise in both halves** (best: F, -0.001R per entry, 95% -0.017 to +0.016).

| Variant | Rule | Entries | Win | Avg R | vs today (per entry) | 95% range of the difference | 1st half | 2nd half | Big runners (today ≥ +2R) |
|---|---|---|---|---|---|---|---|---|---|
| **A** | today (no analyst) | 2946 | 48% | -0.011 | — |  — | — | — | — |
| **F** | out when the 15m trend flips (close crosses EMA50 against) | 2946 | 45% | -0.012 | -0.001 | -0.017 to +0.016 | +0.002 | -0.003 | -0.31R on 93 |
| **G** | out when 5m structure breaks (close beyond the last swing low/high) | 2946 | 42% | -0.020 | -0.009 | -0.031 to +0.012 | -0.000 | -0.017 | -0.69R on 93 |
| **H** | out after 60 min without a new best while under +0.5R | 2946 | 46% | -0.015 | -0.004 | -0.021 to +0.012 | -0.006 | -0.002 | -0.41R on 93 |
| **X** | all three analyst exits | 2946 | 42% | -0.016 | -0.005 | -0.031 to +0.020 | +0.007 | -0.016 | -0.75R on 93 |

## By instrument (avg R per entry)

| Instrument | Entries | A | F | G | H | X |
|---|---|---|---|---|---|---|
| NDQ | 593 | +0.011 | -0.004 | -0.009 | -0.021 | -0.024 |
| US30 | 565 | -0.058 | -0.037 | -0.083 | -0.033 | -0.048 |
| XAUUSD | 1788 | -0.004 | -0.007 | -0.004 | -0.008 | -0.004 |

## By cell (avg R per entry)

| Cell | Entries | A | F | G | H | X |
|---|---|---|---|---|---|---|
| dtfx_close_fib:15m@pb-us30-b988 | 138 | -0.109 | -0.089 | -0.105 | -0.078 | -0.066 |
| dtfx_close_fib:15m@pb-us30-b988-trend | 138 | -0.182 | -0.182 | -0.132 | -0.087 | -0.079 |
| dtfx_close_fib:3m@pb-xau-4a8c | 159 | +0.107 | +0.102 | +0.083 | +0.093 | +0.101 |
| dtfx_close_fib:3m@pb-xau-4a8c-scalp | 159 | +0.038 | +0.052 | +0.045 | +0.038 | +0.059 |
| dtfx_wick_fib:15m@pb-ndq-b988 | 158 | +0.065 | +0.048 | +0.035 | +0.026 | +0.014 |
| dtfx_wick_fib:3m@pb-xau-2ca4 | 136 | -0.002 | -0.013 | -0.037 | +0.031 | -0.015 |
| dtfx_wick_fib:5m@pb-ndq-4a8c-scalp | 113 | -0.033 | -0.033 | -0.042 | -0.033 | -0.040 |
| ict_2022:3m@pb-xau-504f | 145 | -0.104 | -0.080 | -0.091 | -0.089 | -0.097 |
| ict_amd:3m@pb-us30-013f | 155 | -0.078 | -0.043 | -0.079 | -0.051 | -0.044 |
| ict_turtle_soup:15m@pb-xau-6062 | 134 | -0.054 | -0.081 | -0.044 | -0.054 | -0.048 |
| ict_turtle_soup:15m@pb-xau-6062-trend | 134 | +0.007 | -0.023 | +0.007 | +0.010 | +0.016 |
| ict_turtle_soup:5m@pb-xau-285e | 120 | -0.022 | -0.004 | +0.020 | +0.004 | +0.026 |
| macd_cross:5m@pb-ndq-d | 198 | +0.091 | +0.091 | +0.053 | +0.030 | +0.029 |
| smc_bos_retest:5m@pb-xau-392f | 393 | +0.032 | +0.026 | +0.009 | -0.007 | -0.009 |
| smc_displacement:3m@pb-xau-d | 232 | +0.005 | -0.017 | +0.008 | +0.011 | -0.009 |
| smc_mss:3m@pb-xau-d | 176 | -0.113 | -0.085 | -0.070 | -0.115 | -0.056 |
| smt_divergence:15m@pb-ndq-06e2-trend | 124 | -0.147 | -0.196 | -0.132 | -0.153 | -0.142 |
| sr_rejection:30m@pb-us30-d-trend | 134 | +0.147 | +0.174 | -0.013 | +0.090 | -0.001 |
