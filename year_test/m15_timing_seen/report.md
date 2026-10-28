# M15 timing: late entry on the M15 turn, early exit on M15 invalidation (seen)

Registered Oct 28 2026 before running (research/m15_timing/PREREGISTRATION_2026-10-28.md); both ideas came from the reviewers' post-mortems of losing trades. Each trade replayed by the playbook's own engine (research.simulate_live, real bid/ask spread per minute, the cell's own exit profile).

Cohort: 10,724 trades on 3m / 5m. **Engine check:** the plain replay reproduces the recorded R on 10,724 (100.0%; required 98%).

Paired per trade: d = R(rule) − R(as recorded). Gates: ≥ 100 trades changed, 95% range of mean d above 0 (circular 5-weekday blocks), both halves > 0 (split 2023-11-17), > 0 at 2× costs, and the 95% range of (rule − control) above 0.

| check | trades changed | avg R as recorded | avg R with rule | mean d (95% range) | halves | d at 2× costs | control avg R: rule − control (95% range) | pass |
|---|---|---|---|---|---|---|---|---|
| A m15_turn_entry | 2,365 of 10,724 | -0.095 | -0.081 | +0.013 (+0.004 to +0.022) | +0.013 / +0.014 | +0.027 | -0.077: -0.004 (-0.011 to +0.003) | **no** (beats control) |
| B m15_inval_exit | 1,649 of 10,724 | -0.095 | -0.097 | -0.002 (-0.008 to +0.003) | -0.004 / -0.000 | -0.003 | -0.096: -0.001 (-0.008 to +0.006) | **no** (95% range above 0, both halves > 0, 2x costs > 0, beats control) |

A applied to 2,802 trades (last M15 candle closed against the trade): entered 1,642, stop_first 680, session 281, no_confirm 199; entered on M15 candle 1: 1,112, 2: 287, 3: 165, 4: 78.
B fired on 1,649 trades (15.4%).

**A m15_turn_entry does not pass → vault untouched, closed.**

**B m15_inval_exit does not pass → vault untouched, closed.**

## By cell (descriptive; it can't rescue a failed check)

| cell | trades | avg R recorded | A avg R | B avg R |
|---|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | -0.085 | -0.078 | -0.093 |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | -0.116 | -0.104 | -0.121 |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 730 | -0.119 | -0.122 | -0.130 |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 728 | -0.076 | -0.086 | -0.085 |
| ict_2022_3m_pb-xau-504f | 781 | -0.147 | -0.105 | -0.136 |
| ict_amd_3m_pb-us30-013f | 937 | -0.118 | -0.092 | -0.126 |
| ict_turtle_soup_5m_pb-xau-285e | 780 | -0.080 | -0.088 | -0.081 |
| macd_cross_5m_pb-ndq-d | 1134 | +0.052 | +0.058 | +0.051 |
| smc_bos_retest_5m_pb-xau-392f | 1671 | -0.079 | -0.079 | -0.078 |
| smc_displacement_3m_pb-xau-d | 1278 | -0.181 | -0.133 | -0.182 |
| smc_mss_3m_pb-xau-d | 1083 | -0.110 | -0.094 | -0.109 |

A rule that passes but leaves the kept trades below zero still leaves a losing playbook.
