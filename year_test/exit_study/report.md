# Exit study — protection before the first target

18 cells of the current playbook (as of 2026-10-10), 2025-10-08 → 2026-10-08, every candidate entry of each cell replayed on 1-minute bars with real spread under each exit rule. Same entries for every variant — only the exit changes, so the differences are paired. R per trade after spread.

**Today's rules turn a good start into a loss on 457 of 3221 entries (14%)**: they reached +0.5R or more and still closed at or below zero (avg -0.85R on those). Entries reaching +0.5R at all: 59%; reaching +1R: 38%.

**No variant beats today's rules by more than noise in both halves** (best: E, +0.003R per entry, 95% -0.009 to +0.015).

| Variant | Rule | Entries | Win | Avg R | vs today (per entry) | 95% range of the difference | 1st half | 2nd half | Big runners (today ≥ +2R) |
|---|---|---|---|---|---|---|---|---|---|
| **A** | today (50% at +1R) | 3221 | 48% | +0.002 | — |  — | — | — | — |
| **B** | 50% at +0.5R, stop to BE | 3221 | 62% | -0.018 | -0.021 | -0.046 to +0.004 | -0.001 | -0.040 | -0.96R on 101 |
| **C** | stop to BE at +0.5R | 3221 | 34% | -0.009 | -0.011 | -0.035 to +0.012 | -0.003 | -0.019 | -0.69R on 101 |
| **D** | give back half after +0.5R → out | 3221 | 60% | -0.043 | -0.045 | -0.080 to -0.014 | -0.014 | -0.077 | -1.59R on 101 |
| **E** | 50% at 100 pips, stop to BE | 3221 | 53% | +0.005 | +0.003 | -0.009 to +0.015 | +0.000 | +0.006 | -0.24R on 101 |

## By instrument (avg R per entry)

| Instrument | Entries | A | B | C | D | E |
|---|---|---|---|---|---|---|
| NDQ | 612 | +0.047 | +0.046 | +0.056 | +0.011 | +0.054 |
| US30 | 576 | -0.056 | -0.037 | -0.030 | -0.108 | -0.039 |
| XAUUSD | 2033 | +0.005 | -0.032 | -0.022 | -0.040 | +0.003 |

## By cell (avg R per entry)

| Cell | Entries | A | B | C | D | E |
|---|---|---|---|---|---|---|
| dtfx_close_fib:15m@pb-us30-b988-trend | 138 | -0.182 | -0.155 | -0.172 | -0.173 | -0.085 |
| dtfx_close_fib:3m@pb-xau-4a8c | 159 | +0.107 | +0.011 | +0.031 | +0.004 | +0.091 |
| dtfx_close_fib:3m@pb-xau-4a8c-scalp | 159 | +0.038 | -0.031 | -0.003 | -0.032 | +0.031 |
| dtfx_wick_fib:15m@pb-ndq-b988 | 158 | +0.065 | +0.094 | +0.086 | +0.069 | +0.097 |
| dtfx_wick_fib:15m@pb-ndq-b988-trend | 158 | +0.125 | +0.124 | +0.158 | +0.075 | +0.131 |
| dtfx_wick_fib:3m@pb-xau-4a8c | 223 | +0.113 | +0.005 | +0.017 | +0.008 | +0.086 |
| ict_2022:3m@pb-xau-504f | 145 | -0.104 | -0.111 | -0.086 | -0.109 | -0.085 |
| ict_amd:3m@pb-us30-013f | 155 | -0.078 | -0.058 | -0.060 | -0.121 | -0.063 |
| ict_amd:5m@pb-us30-013f | 149 | -0.099 | -0.046 | -0.054 | -0.120 | -0.101 |
| ict_turtle_soup:5m@pb-xau-285e | 120 | -0.022 | -0.028 | -0.012 | -0.019 | -0.039 |
| smc_bos_retest:5m@pb-xau-00dd | 386 | -0.007 | -0.026 | -0.025 | -0.048 | +0.004 |
| smc_displacement:3m@pb-xau-d | 232 | +0.005 | -0.021 | -0.018 | -0.074 | +0.019 |
| smc_ifvg:15m@pb-xau-d | 169 | +0.111 | +0.062 | +0.098 | +0.072 | +0.065 |
| smc_mss:3m@pb-xau-3c77-scalp | 264 | -0.064 | -0.071 | -0.077 | -0.064 | -0.057 |
| smc_mss:3m@pb-xau-d | 176 | -0.113 | -0.117 | -0.121 | -0.117 | -0.096 |
| smt_divergence:3m@pb-ndq-d-scalp | 164 | -0.075 | -0.050 | -0.043 | -0.074 | -0.076 |
| sr_rejection:30m@pb-ndq-d | 132 | +0.083 | +0.014 | +0.022 | -0.030 | +0.073 |
| sr_rejection:30m@pb-us30-d-trend | 134 | +0.147 | +0.119 | +0.177 | -0.015 | +0.106 |
