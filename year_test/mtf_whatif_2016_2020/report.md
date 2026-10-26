# Confirmation on untouched 2016 → 2020: the 15m candle in progress against a 3m / 5m entry

Registered Oct 26 2026 after **m15_live** passed on 2021 → Sep 2026 (+0.073R, 95% +0.021 to +0.123, both halves, random p 0.001): the same eleven 3m/5m playbook cells, unchanged, run once on 2016–2020 with the live filters and position manager and the real per-minute spread; m15_live judged with the same rule (kept − flagged day-block 95% range above 0, positive in both halves, better than skipping as many at random, p < 0.05).

9,070 trades on 3m / 5m, -0.148R average (50 skipped for price gaps).

## The registered check

| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 2248 of 9070 | -0.217 | -0.126 | +0.091 (+0.040 to +0.142) | +0.025 / +0.157 | 0.000 | **yes** |

**Verdict: CONFIRMED.**

Without macd_cross 5m NDQ (its own 2016–2020 trades were looked at before):

| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| m15_live | 2195 of 8060 | -0.215 | -0.129 | +0.086 (+0.030 to +0.139) | +0.013 / +0.157 | 0.001 | **yes** |

## For information only (not registered, can't confirm anything)

| check | flagged | flagged avg R | kept avg R | kept − flagged (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| m15_closed | 2443 of 9070 | -0.121 | -0.158 | -0.038 (-0.089 to +0.011) | -0.082 / +0.006 | 0.953 | **no** |
| m15_trend | 3411 of 9070 | -0.139 | -0.153 | -0.014 (-0.065 to +0.035) | +0.033 / -0.059 | 0.769 | **no** |
| h1_live | 1380 of 9070 | -0.147 | -0.148 | -0.002 (-0.067 to +0.063) | -0.001 / -0.001 | 0.539 | **no** |

## By cell

| cell | trades | avg R | m15_live flagged (avg R) / kept (avg R) |
|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 713 | -0.155 | 257 (-0.15) / 456 (-0.16) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 746 | -0.185 | 268 (-0.16) / 478 (-0.20) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 676 | -0.137 | 189 (-0.21) / 487 (-0.11) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 662 | -0.132 | 154 (-0.06) / 508 (-0.16) |
| ict_2022_3m_pb-xau-504f | 626 | -0.217 | 413 (-0.22) / 213 (-0.21) |
| ict_amd_3m_pb-us30-013f | 765 | -0.048 | 51 (-0.26) / 714 (-0.03) |
| ict_turtle_soup_5m_pb-xau-285e | 643 | -0.108 | 15 (+0.05) / 628 (-0.11) |
| macd_cross_5m_pb-ndq-d | 1010 | -0.110 | 53 (-0.27) / 957 (-0.10) |
| smc_bos_retest_5m_pb-xau-392f | 1368 | -0.163 | 203 (-0.23) / 1165 (-0.15) |
| smc_displacement_3m_pb-xau-d | 1038 | -0.255 | 645 (-0.30) / 393 (-0.18) |
| smc_mss_3m_pb-xau-d | 823 | -0.091 | 0 (+nan) / 823 (-0.09) |

A confirmed check that leaves the kept trades below zero still leaves a losing playbook: it earns a shadow tag on the practice account and the 'wait for the 15m to turn' test, not a live change.
