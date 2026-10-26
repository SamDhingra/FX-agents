# Round 3, Gemini's checks on the playbook's 3m / 5m entries (seen, stricter judge)

Registered before running (research/round3/gemini/). **m15_impulse_leg** two completed 15m candles stepping against the trade or one wide counter-bar; **ltf_swing_structure_against** 3 hours of 5m swings stepping against it with price on the wrong side of the 1-hour mean; **stop_inside_15m_noise** spread > 8% of the stop OR stop < 0.5 × ATR15; **chasing_exhausted_leg** entering at the extreme of an unretraced ≥ 2 × ATR15 one-hour move in the trade's own direction. Gemini's code unchanged; timeframe labels and unavailable data handled outside it.

Stricter judge: calendar halves split 2023-11-17, circular 5-weekday blocks, random skipping within cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage.

Cohort: 10,724 trades on 3m / 5m, -0.095R average.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| m15_impulse_leg | 933 of 10724 (100% coverage) | -0.103 | -0.094 | +0.009 (-0.069 to +0.086) | -0.044 / +0.073 | 0.5947 | **no** (gates not met) |
| ltf_swing_structure_against | 288 of 10717 (100% coverage) | -0.179 | -0.093 | +0.086 (-0.062 to +0.230) | -0.039 / +0.229 | 0.3580 | **no** (gates not met) |
| stop_inside_15m_noise | 5864 of 10724 (100% coverage) | -0.160 | -0.016 | +0.144 (+0.099 to +0.189) | +0.159 / +0.121 | 0.0001 | **yes** |
| chasing_exhausted_leg | 1760 of 10723 (100% coverage) | -0.065 | -0.100 | -0.035 (-0.091 to +0.020) | -0.017 / -0.058 | 0.7628 | **no** (gates not met) |

### stop_inside_15m_noise, its two halves separately (information only)

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| stop_spread_part | 5859 of 10724 (100% coverage) | -0.160 | -0.016 | +0.144 (+0.098 to +0.189) | +0.158 / +0.120 | 0.0001 | **yes** |
| stop_noise_part | 388 of 10724 (100% coverage) | -0.236 | -0.089 | +0.147 (+0.031 to +0.262) | +0.160 / +0.131 | 0.1551 | **no** (gates not met) |

## By cell (descriptive)

| cell | trades | avg R | m15_impulse_leg flagged (avg R) / kept (avg R) | ltf_swing_structure_against flagged (avg R) / kept (avg R) | stop_inside_15m_noise flagged (avg R) / kept (avg R) | chasing_exhausted_leg flagged (avg R) / kept (avg R) |
|---|---|---|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | -0.085 | 31 (-0.07) / 759 (-0.09) | 26 (+0.04) / 763 (-0.09) | 572 (-0.13) / 218 (+0.03) | 59 (-0.01) / 731 (-0.09) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | -0.116 | 32 (-0.06) / 780 (-0.12) | 26 (-0.19) / 785 (-0.12) | 589 (-0.16) / 223 (-0.01) | 62 (-0.04) / 750 (-0.12) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 730 | -0.119 | 28 (+0.18) / 702 (-0.13) | 29 (-0.29) / 701 (-0.11) | 517 (-0.15) / 213 (-0.04) | 72 (-0.13) / 657 (-0.12) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 728 | -0.076 | 72 (-0.09) / 656 (-0.07) | 6 (+0.04) / 722 (-0.08) | 293 (-0.12) / 435 (-0.05) | 70 (-0.14) / 658 (-0.07) |
| ict_2022_3m_pb-xau-504f | 781 | -0.147 | 68 (-0.14) / 713 (-0.15) | 73 (-0.31) / 708 (-0.13) | 524 (-0.21) / 257 (-0.01) | 19 (+0.40) / 762 (-0.16) |
| ict_amd_3m_pb-us30-013f | 937 | -0.118 | 154 (-0.15) / 783 (-0.11) | 17 (-0.32) / 920 (-0.11) | 253 (-0.15) / 684 (-0.11) | 385 (-0.08) / 552 (-0.14) |
| ict_turtle_soup_5m_pb-xau-285e | 780 | -0.080 | 47 (-0.30) / 733 (-0.07) | 1 (+2.47) / 779 (-0.08) | 218 (-0.17) / 562 (-0.04) | 346 (-0.06) / 434 (-0.10) |
| macd_cross_5m_pb-ndq-d | 1134 | +0.052 | 85 (-0.00) / 1049 (+0.06) | 1 (-1.00) / 1133 (+0.05) | 390 (-0.02) / 744 (+0.09) | 158 (-0.02) / 976 (+0.06) |
| smc_bos_retest_5m_pb-xau-392f | 1671 | -0.079 | 120 (-0.04) / 1551 (-0.08) | 1 (+0.02) / 1666 (-0.08) | 823 (-0.16) / 848 (+0.00) | 361 (-0.07) / 1310 (-0.08) |
| smc_displacement_3m_pb-xau-d | 1278 | -0.181 | 83 (-0.19) / 1195 (-0.18) | 81 (-0.17) / 1196 (-0.18) | 1115 (-0.21) / 163 (-0.00) | 25 (+0.04) / 1253 (-0.19) |
| smc_mss_3m_pb-xau-d | 1083 | -0.110 | 213 (-0.11) / 870 (-0.11) | 27 (+0.04) / 1056 (-0.11) | 570 (-0.17) / 513 (-0.04) | 203 (-0.10) / 880 (-0.11) |

Families: m15_impulse_leg and ltf_swing_structure_against belong to the 'against the higher timeframe' family (its 2016–2020 test was m15_live's) → a pass earns a shadow tag only. chasing_exhausted_leg, if it passes here, is judged once on 2016–2020 (./fx.sh round3g vault). stop_inside_15m_noise is seen-only.
