# What-if: was the higher timeframe moving against the trade at entry? — playbook trades, 2021 → Sep 2026

Checks fixed before this ran (see fxagents/mtf_whatif.py): **m15_live** the 15m candle the entry is in had moved against the trade from its open; **m15_closed** the last completed 15m candle closed against it; **m15_trend** the 15m EMA(20) slopes against it (now vs 3 candles earlier); **h1_live** the 1H candle the entry is in had moved against it.

A check passes when the trades it flags do worse than the ones it keeps: day-block 95% range of kept − flagged above 0, positive in both halves, and better than skipping as many trades at random (p < 0.05). Four checks → about a 1-in-5 chance one passes by luck; a pass earns a paper filter and one test on 2016–2020.

16,424 trades with full price data (32 skipped for gaps).

## Sam's case: entries on 3m / 5m (10,713 trades, -0.095R average)

| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 2569 of 10713 | -0.150 | -0.077 | +0.073 (+0.021 to +0.123) | +0.109 / +0.037 | 0.001 | **yes** |
| m15_closed | 2799 of 10713 | -0.100 | -0.093 | +0.007 (-0.046 to +0.060) | -0.033 / +0.045 | 0.364 | **no** |
| m15_trend | 4213 of 10713 | -0.096 | -0.094 | +0.002 (-0.045 to +0.048) | -0.001 / +0.003 | 0.455 | **no** |
| h1_live | 1725 of 10713 | -0.110 | -0.092 | +0.018 (-0.047 to +0.080) | +0.012 / +0.021 | 0.234 | **no** |

### Losers vs winners: how often was each check true?

| check | share of losing trades flagged | share of winning trades flagged |
|---|---|---|
| m15_live | 25% | 22% |
| m15_closed | 26% | 26% |
| m15_trend | 39% | 39% |
| h1_live | 16% | 16% |

### By cell (3m / 5m)

| cell | trades | avg R | m15_live flagged (avg R) / kept (avg R) | m15_closed flagged (avg R) / kept (avg R) | m15_trend flagged (avg R) / kept (avg R) | h1_live flagged (avg R) / kept (avg R) |
|---|---|---|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | -0.085 | 297 (-0.03) / 493 (-0.12) | 182 (-0.08) / 608 (-0.09) | 266 (-0.13) / 524 (-0.06) | 162 (+0.04) / 628 (-0.12) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | -0.116 | 302 (-0.12) / 510 (-0.12) | 187 (-0.06) / 625 (-0.13) | 272 (-0.12) / 540 (-0.11) | 166 (-0.06) / 646 (-0.13) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 729 | -0.120 | 214 (-0.13) / 515 (-0.12) | 166 (-0.07) / 563 (-0.14) | 229 (-0.19) / 500 (-0.09) | 129 (-0.07) / 600 (-0.13) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 727 | -0.075 | 167 (-0.05) / 560 (-0.08) | 276 (-0.03) / 451 (-0.11) | 205 (-0.09) / 522 (-0.07) | 129 (-0.00) / 598 (-0.09) |
| ict_2022_3m_pb-xau-504f | 780 | -0.148 | 472 (-0.14) / 308 (-0.16) | 212 (-0.17) / 568 (-0.14) | 289 (-0.23) / 491 (-0.10) | 247 (-0.16) / 533 (-0.14) |
| ict_amd_3m_pb-us30-013f | 935 | -0.118 | 70 (-0.14) / 865 (-0.12) | 309 (-0.14) / 626 (-0.11) | 432 (-0.15) / 503 (-0.09) | 142 (-0.20) / 793 (-0.10) |
| ict_turtle_soup_5m_pb-xau-285e | 779 | -0.080 | 7 (-0.12) / 772 (-0.08) | 108 (-0.06) / 671 (-0.08) | 504 (-0.04) / 275 (-0.15) | 17 (-0.67) / 762 (-0.07) |
| macd_cross_5m_pb-ndq-d | 1130 | +0.051 | 47 (-0.09) / 1083 (+0.06) | 230 (-0.00) / 900 (+0.06) | 820 (+0.06) / 310 (+0.03) | 100 (+0.04) / 1030 (+0.05) |
| smc_bos_retest_5m_pb-xau-392f | 1670 | -0.079 | 202 (-0.15) / 1468 (-0.07) | 387 (-0.07) / 1283 (-0.08) | 164 (-0.21) / 1506 (-0.06) | 134 (-0.06) / 1536 (-0.08) |
| smc_displacement_3m_pb-xau-d | 1278 | -0.181 | 790 (-0.24) / 488 (-0.08) | 316 (-0.22) / 962 (-0.17) | 394 (-0.23) / 884 (-0.16) | 353 (-0.21) / 925 (-0.17) |
| smc_mss_3m_pb-xau-d | 1083 | -0.110 | 1 (-1.00) / 1082 (-0.11) | 426 (-0.11) / 657 (-0.11) | 638 (-0.07) / 445 (-0.17) | 146 (-0.15) / 937 (-0.10) |

## For comparison: entries on 15m and above (5,711 trades, -0.082R average)

| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 64 of 5711 | -0.091 | -0.082 | +0.010 (-0.354 to +0.319) | +0.083 / -0.078 | 0.504 | **no** |
| m15_closed | 64 of 5711 | -0.091 | -0.082 | +0.010 (-0.354 to +0.319) | +0.083 / -0.078 | 0.504 | **no** |
| m15_trend | 2999 of 5711 | -0.086 | -0.077 | +0.009 (-0.063 to +0.084) | +0.022 / -0.004 | 0.389 | **no** |
| h1_live | 2045 of 5711 | -0.092 | -0.076 | +0.016 (-0.058 to +0.089) | +0.054 / -0.021 | 0.293 | **no** |

A check that passes but leaves the kept trades below zero still leaves a losing playbook.
