# Higher-timeframe liquidity checks — playbook trades, 2021 → Sep 2026 (seen data)

Levels of weight ≥ 2 (4H / daily / weekly swings, prior day / week high & low), each known only from the close of the bar that confirms it and untaken until price trades through it. Parameters were fixed before this ran: **trap** = such a level on the trade's side was swept in the 60 min before entry and price is back inside it; **no room** = the nearest untaken one ahead is closer than 0.5 × ATR(1H, 14).

A check passes when the trades it removes do worse than the ones it keeps: day-block 95% range of the difference above 0, positive in both halves, and better than removing the same number at random (p < 0.05). Passing earns a paper filter on the scorecard, not a change to the practice account.

| check | removed | removed avg R | kept avg R | kept − removed (95% range) | halves | random p | pass |
|---|---|---|---|---|---|---|---|
| trap | 458 of 16456 | -0.040 | -0.091 | -0.052 (-0.168 to +0.055) | -0.039 / -0.071 | 0.865 | **no** |
| no_room | 501 of 16456 | -0.083 | -0.090 | -0.007 (-0.115 to +0.101) | -0.005 / -0.013 | 0.549 | **no** |
| either | 950 of 16456 | -0.054 | -0.092 | -0.038 (-0.115 to +0.045) | -0.030 / -0.052 | 0.879 | **no** |

All trades: -0.090R average. A filter that passes but leaves the kept trades below zero still leaves a losing playbook.

## By cell

| cell | trades | trap (avg R) | no room (avg R) | neither: avg R |
|---|---|---|---|---|
| dtfx_close_fib_15m_pb-us30-b988 | 789 | 46 (-0.095) | 20 (-0.311) | -0.09 |
| dtfx_close_fib_15m_pb-us30-b988-trend | 764 | 45 (-0.165) | 20 (-0.401) | -0.075 |
| dtfx_close_fib_3m_pb-xau-4a8c | 790 | 18 (0.049) | 30 (-0.069) | -0.089 |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 812 | 19 (-0.014) | 30 (-0.142) | -0.118 |
| dtfx_wick_fib_15m_pb-ndq-b988 | 919 | 48 (-0.177) | 27 (0.099) | -0.04 |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 730 | 15 (0.113) | 17 (-0.093) | -0.126 |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 728 | 21 (-0.089) | 33 (-0.016) | -0.079 |
| ict_2022_3m_pb-xau-504f | 781 | 22 (0.059) | 13 (0.036) | -0.156 |
| ict_amd_3m_pb-us30-013f | 937 | 7 (-0.024) | 33 (0.013) | -0.124 |
| ict_turtle_soup_15m_pb-xau-6062 | 922 | 5 (-0.313) | 0 (—) | -0.135 |
| ict_turtle_soup_15m_pb-xau-6062-trend | 922 | 5 (-0.397) | 0 (—) | -0.114 |
| ict_turtle_soup_5m_pb-xau-285e | 780 | 7 (0.087) | 14 (-0.385) | -0.076 |
| macd_cross_5m_pb-ndq-d | 1134 | 3 (0.719) | 30 (-0.139) | 0.055 |
| smc_bos_retest_5m_pb-xau-392f | 1671 | 72 (0.116) | 147 (-0.051) | -0.094 |
| smc_displacement_3m_pb-xau-d | 1278 | 95 (-0.063) | 36 (-0.202) | -0.191 |
| smc_mss_3m_pb-xau-d | 1083 | 9 (-0.405) | 22 (0.031) | -0.11 |
| smt_divergence_15m_pb-ndq-06e2-trend | 731 | 11 (-0.151) | 9 (-0.004) | -0.009 |
| sr_rejection_30m_pb-us30-d-trend | 685 | 10 (0.436) | 20 (0.061) | -0.07 |
