# Room to the next M15 level (seen, stricter judge)

Registered Oct 28 2026 before running (research/room/PREREGISTRATION_2026-10-28.md); the idea came from the reviewers' post-mortems of losing trades. **room_swing** (decides): nearest M15 swing on the target side among the last 16 completed M15 candles closer than 1.0 × the stop. **room_last2** (variant): the last two completed M15 candles' low (short) / high (long) closer than 1.0 × the stop. Related check already failed: liqtest no_room (4H+ levels, 0.5 × ATR 1H).

Stricter judge: calendar halves split 2023-11-17, circular 5-weekday blocks, random skipping within cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage.

Cohort: 10,724 trades on 3m / 5m, -0.095R average. Room ÷ stop (median, where a swing exists): 0.35.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| room_swing | 6519 of 10724 (100% coverage) | -0.096 | -0.093 | +0.003 (-0.041 to +0.048) | -0.003 / +0.011 | 0.0458 | **no** (gates not met) |
| room_last2 | 6468 of 10724 (100% coverage) | -0.108 | -0.074 | +0.034 (-0.006 to +0.073) | +0.024 / +0.050 | 0.0253 | **no** (gates not met) |

**room_swing does not pass → the vault is not touched; the idea is closed.**

### Sensitivity (information only, never a pass)

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| room_swing_x0.75 | 5892 of 10724 (100% coverage) | -0.087 | -0.103 | -0.016 (-0.058 to +0.027) | -0.013 / -0.018 | 0.2558 | **no** (gates not met) |
| room_swing_x1.5 | 7144 of 10724 (100% coverage) | -0.096 | -0.092 | +0.004 (-0.041 to +0.049) | -0.001 / +0.011 | 0.0711 | **no** (gates not met) |

## By cell (descriptive; it can't rescue a failed check)

| cell | trades | avg R | room_swing flagged (avg R) / kept (avg R) | room_last2 flagged (avg R) / kept (avg R) |
|---|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | -0.085 | 449 (-0.07) / 341 (-0.10) | 647 (-0.08) / 143 (-0.10) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | -0.116 | 458 (-0.15) / 354 (-0.07) | 665 (-0.12) / 147 (-0.12) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 730 | -0.119 | 411 (-0.09) / 319 (-0.16) | 588 (-0.14) / 142 (-0.04) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 728 | -0.076 | 476 (-0.07) / 252 (-0.08) | 590 (-0.06) / 138 (-0.13) |
| ict_2022_3m_pb-xau-504f | 781 | -0.147 | 561 (-0.16) / 220 (-0.10) | 559 (-0.15) / 222 (-0.13) |
| ict_amd_3m_pb-us30-013f | 937 | -0.118 | 591 (-0.16) / 346 (-0.06) | 398 (-0.14) / 539 (-0.10) |
| ict_turtle_soup_5m_pb-xau-285e | 780 | -0.080 | 524 (-0.09) / 256 (-0.05) | 344 (-0.13) / 436 (-0.04) |
| macd_cross_5m_pb-ndq-d | 1134 | +0.052 | 1041 (+0.05) / 93 (+0.04) | 611 (+0.04) / 523 (+0.07) |
| smc_bos_retest_5m_pb-xau-392f | 1671 | -0.079 | 643 (-0.10) / 1028 (-0.07) | 1041 (-0.10) / 630 (-0.04) |
| smc_displacement_3m_pb-xau-d | 1278 | -0.181 | 600 (-0.23) / 678 (-0.14) | 598 (-0.17) / 680 (-0.19) |
| smc_mss_3m_pb-xau-d | 1083 | -0.110 | 765 (-0.09) / 318 (-0.15) | 427 (-0.18) / 656 (-0.06) |

A check that passes but leaves the kept trades below zero still leaves a losing playbook.
