# Round 3: context checks on the playbook's 3m / 5m entries (seen, stricter judge)

Registered before running (research/round3/PREREGISTRATION_chatgpt_2026-10-26.md). **A1** a material, efficient 15-minute move against the trade; **A2** active 30-minute back-and-forth with little net progress (both ChatGPT's code, unchanged); **m15_live** our check (the 15m candle in progress moved against the trade), re-judged the same way.

Stricter judge (fxagents/whatif_judge.py): fixed calendar halves (split 2023-11-17), circular 5-weekday block bootstrap (10,000 draws), random skipping **within each stratum** (cell × side × hour × half), ≥ 30 flagged and kept trades per half, ≥ 90% coverage.

Cohort: 10,724 trades on 3m / 5m, -0.095R average.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 2569 of 10713 (100% coverage) | -0.150 | -0.077 | +0.072 (+0.023 to +0.122) | +0.101 / +0.042 | 0.1363 | **no** (gates not met) |
| A1_opposing_path_v1 | 9 of 7817 (73% coverage) | 0.114 | -0.0751 | — | -0.486 / +0.177 | — | **no** (coverage 73% < 90% (inconclusive); fewer than 30 flagged or kept trades in a half) |
| A2_two_way_chop_v1 | 4522 of 7817 (73% coverage) | -0.0966 | -0.045 | — | +0.008 / +0.092 | — | **no** (coverage 73% < 90% (inconclusive)) |

Unavailable trades (gaps in the minutes before entry), by hour of entry:

- m15_live: 11 — {2: 4, 4: 3, 14: 1, 22: 1, 23: 2}
- A1_opposing_path_v1: 2907 — {2: 602, 3: 317, 4: 169, 8: 23, 9: 72, 10: 31, 11: 5, 13: 5, 14: 34, 15: 3, 20: 686, 21: 612, 22: 255, 23: 93}
- A2_two_way_chop_v1: 2907 — {2: 602, 3: 317, 4: 169, 8: 23, 9: 72, 10: 31, 11: 5, 13: 5, 14: 34, 15: 3, 20: 686, 21: 612, 22: 255, 23: 93}

## By cell (descriptive; it can't rescue a failed check)

| cell | trades | avg R | m15_live flagged (avg R) / kept (avg R) | A1_opposing_path_v1 flagged (avg R) / kept (avg R) | A2_two_way_chop_v1 flagged (avg R) / kept (avg R) |
|---|---|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | -0.085 | 297 (-0.03) / 493 (-0.12) | 0 (+nan) / 528 (-0.05) | 346 (-0.07) / 182 (-0.03) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | -0.116 | 302 (-0.12) / 510 (-0.12) | 0 (+nan) / 544 (-0.10) | 358 (-0.12) / 186 (-0.07) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 730 | -0.119 | 214 (-0.13) / 515 (-0.12) | 0 (+nan) / 659 (-0.10) | 442 (-0.10) / 217 (-0.11) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 728 | -0.076 | 167 (-0.05) / 560 (-0.08) | 0 (+nan) / 486 (-0.09) | 342 (-0.09) / 144 (-0.10) |
| ict_2022_3m_pb-xau-504f | 781 | -0.147 | 472 (-0.14) / 308 (-0.16) | 6 (+0.22) / 710 (-0.15) | 536 (-0.17) / 180 (-0.05) |
| ict_amd_3m_pb-us30-013f | 937 | -0.118 | 70 (-0.14) / 865 (-0.12) | 0 (+nan) / 479 (-0.07) | 225 (-0.05) / 254 (-0.09) |
| ict_turtle_soup_5m_pb-xau-285e | 780 | -0.080 | 7 (-0.12) / 772 (-0.08) | 0 (+nan) / 693 (-0.06) | 230 (-0.11) / 463 (-0.03) |
| macd_cross_5m_pb-ndq-d | 1134 | +0.052 | 47 (-0.09) / 1083 (+0.06) | 0 (+nan) / 731 (+0.08) | 340 (+0.12) / 391 (+0.06) |
| smc_bos_retest_5m_pb-xau-392f | 1671 | -0.079 | 202 (-0.15) / 1468 (-0.07) | 0 (+nan) / 1179 (-0.06) | 486 (-0.10) / 693 (-0.03) |
| smc_displacement_3m_pb-xau-d | 1278 | -0.181 | 790 (-0.24) / 488 (-0.08) | 3 (-0.10) / 821 (-0.14) | 621 (-0.13) / 203 (-0.17) |
| smc_mss_3m_pb-xau-d | 1083 | -0.110 | 1 (-1.00) / 1082 (-0.11) | 0 (+nan) / 978 (-0.09) | 596 (-0.13) / 382 (-0.04) |

A pass earns a paper filter (and, for A2 only, one judgement on the 2016–2020 trades); the counterflow family's vault use is m15_live's confirmation. A check that passes but leaves the kept trades below zero still leaves a losing playbook.
