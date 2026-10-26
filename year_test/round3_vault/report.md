# Round 3: context checks on the playbook's 3m / 5m entries (vault, stricter judge)

Registered before running (research/round3/PREREGISTRATION_chatgpt_2026-10-26.md). **A1** a material, efficient 15-minute move against the trade; **A2** active 30-minute back-and-forth with little net progress (both ChatGPT's code, unchanged); **m15_live** our check (the 15m candle in progress moved against the trade), re-judged the same way.

Stricter judge (fxagents/whatif_judge.py): fixed calendar halves (split 2018-07-02), circular 5-weekday block bootstrap (10,000 draws), random skipping **within each stratum** (cell × side × hour × half), ≥ 30 flagged and kept trades per half, ≥ 90% coverage.

Cohort: 9,120 trades on 3m / 5m, -0.147R average.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 2248 of 9070 (99% coverage) | -0.217 | -0.126 | +0.091 (+0.039 to +0.142) | +0.029 / +0.147 | 0.0412 | **yes** |

Unavailable trades (gaps in the minutes before entry), by hour of entry:

- m15_live: 50 — {2: 10, 3: 2, 4: 2, 8: 2, 10: 1, 14: 5, 20: 4, 21: 7, 22: 9, 23: 8}

## By cell (descriptive; it can't rescue a failed check)

| cell | trades | avg R | m15_live flagged (avg R) / kept (avg R) |
|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 718 | -0.155 | 257 (-0.15) / 456 (-0.16) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 751 | -0.184 | 268 (-0.16) / 478 (-0.20) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 677 | -0.136 | 189 (-0.21) / 487 (-0.11) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 666 | -0.126 | 154 (-0.06) / 508 (-0.16) |
| ict_2022_3m_pb-xau-504f | 628 | -0.214 | 413 (-0.22) / 213 (-0.21) |
| ict_amd_3m_pb-us30-013f | 771 | -0.046 | 51 (-0.26) / 714 (-0.03) |
| ict_turtle_soup_5m_pb-xau-285e | 645 | -0.108 | 15 (+0.05) / 628 (-0.11) |
| macd_cross_5m_pb-ndq-d | 1020 | -0.110 | 53 (-0.27) / 957 (-0.10) |
| smc_bos_retest_5m_pb-xau-392f | 1377 | -0.164 | 203 (-0.23) / 1165 (-0.15) |
| smc_displacement_3m_pb-xau-d | 1044 | -0.255 | 645 (-0.30) / 393 (-0.18) |
| smc_mss_3m_pb-xau-d | 823 | -0.091 | 0 (+nan) / 823 (-0.09) |

A pass earns a paper filter (and, for A2 only, one judgement on the 2016–2020 trades); the counterflow family's vault use is m15_live's confirmation. A check that passes but leaves the kept trades below zero still leaves a losing playbook.
