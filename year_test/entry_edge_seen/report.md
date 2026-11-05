# Do the playbook's entries beat random timing? (seen)

Registered Nov 5 2026 before running (research/entry_edge/PREREGISTRATION_2026-11-05.md). Each playbook trade replayed on the playbook's own engine with the real spread, against the same trade entered at a random candle of the same day (5 draws, same side, stop, exit) and against the opposite side at the same moment.

Cohort: 16,456 trades; the engine reproduces 100.0% (16,456 judged).

| comparison | verdict | trades | real avg R | control avg R | real − control (95% range) | halves | 2× costs |
|---|---|---|---|---|---|---|---|
| vs random timing (primary) | **no edge** (95% range above 0, both halves > 0, 2× costs > 0) | 16,456 | -0.090 | -0.044 | -0.045 (-0.065 to -0.026) | -0.044 / -0.047 | -0.041 |
| vs the opposite side | info | 16,456 | -0.090 | -0.070 | -0.019 (-0.063 to +0.023) | -0.031 / -0.006 | -0.016 |

### By instrument

| instrument | trades | real | random timing | real − random | opposite side |
|---|---|---|---|---|---|
| NDQ | 3,512 | -0.012 | +0.013 | -0.025 | -0.073 |
| XAUUSD | 9,769 | -0.117 | -0.086 | -0.031 | -0.100 |
| US30 | 3,175 | -0.093 | +0.019 | -0.112 | +0.022 |

### By timeframe

| timeframe | trades | real | random timing | real − random | opposite side |
|---|---|---|---|---|---|
| 30min | 685 | -0.059 | -0.073 | +0.014 | -0.052 |
| 15min | 5,047 | -0.084 | -0.057 | -0.026 | -0.008 |
| 5min | 4,313 | -0.044 | +0.003 | -0.047 | -0.099 |
| 3min | 6,411 | -0.129 | -0.063 | -0.066 | -0.102 |

### By exit profile

| exit | trades | real | random timing | real − random | opposite side |
|---|---|---|---|---|---|
| trend | 3,102 | -0.072 | -0.081 | +0.009 | -0.014 |
| scalp | 1,540 | -0.097 | -0.072 | -0.025 | -0.098 |
| std | 11,814 | -0.093 | -0.031 | -0.062 | -0.081 |

### By setup (best and worst 8 by real − random, at least 20 trades)

| setup | trades | real | random timing | real − random | opposite side |
|---|---|---|---|---|---|
| ict_turtle_soup | 2,624 | -0.112 | -0.188 | +0.076 | -0.064 |
| macd_cross | 1,134 | +0.052 | +0.010 | +0.042 | -0.161 |
| sr_rejection | 685 | -0.059 | -0.073 | +0.014 | -0.052 |
| smt_divergence | 731 | -0.011 | -0.015 | +0.004 | -0.018 |
| smc_displacement | 1,278 | -0.181 | -0.139 | -0.042 | -0.157 |
| smc_mss | 1,083 | -0.110 | -0.039 | -0.071 | -0.078 |
| dtfx_wick_fib | 2,377 | -0.076 | +0.009 | -0.086 | -0.063 |
| ict_2022 | 781 | -0.147 | -0.052 | -0.095 | -0.083 |
| dtfx_close_fib | 3,155 | -0.097 | +0.002 | -0.098 | -0.031 |
| smc_bos_retest | 1,671 | -0.079 | +0.032 | -0.110 | -0.094 |
| ict_amd | 937 | -0.118 | -0.008 | -0.111 | -0.004 |

**The entries do not beat random timing: the setups' timing adds nothing over a random entry with the same stop and exit. Filters and exits on top cannot make the playbook pay.**
