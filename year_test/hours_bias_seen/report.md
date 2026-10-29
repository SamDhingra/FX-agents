# All-hours and no-bias playbook test — seen (frozen eab009372932, 16 cells)

Registered Oct 29 2026 before running (research/hours_bias/PREREGISTRATION_2026-10-29.md). One replay per cell with entries allowed 20:00 → 15:50 NY and the bias rule off (research engine, live position manager on 1-minute bars, real bid/ask spread, news blackouts unchanged); each trade is tagged by today's windows and what the bias rule would have said.

**Judged on 2021-01-01 → 2025-10-07 (clean).** A group passes only by itself: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves. Two groups are tested, so about 1 in 10 runs would show a lucky pass — hence the single 2016–2020 judgement.

| group | verdict | trades | win | avg R | 95% range | 2× costs | 1st half | 2nd half | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| H — outside today's windows, bias-aligned (what the all-hours playbook adds) | **no** | 2963 | 43% | -0.063 | -0.12 to -0.01 | -0.133 | -0.051 | -0.074 | 5% |
| B — inside today's windows, bias rule would refuse (neutral or counter) | **no** | 18000 | 42% | -0.097 | -0.12 to -0.07 | -0.182 | -0.101 | -0.093 | 7% |
| base — inside windows, aligned (what the playbook trades today; reference only) | ref | 10782 | 44% | -0.093 | -0.12 to -0.06 | -0.175 | -0.090 | -0.095 | 7% |

**Neither passes → the vault is not touched; both questions are answered: no.**

## Detail (descriptive, can't rescue a failed group)

| slice | trades | avg R | avg R at 2× costs |
|---|---|---|---|
| H, signal 00:00–02:00 | 678 | -0.221 | -0.325 |
| H, signal 05:00–08:30 | 1496 | -0.043 | -0.110 |
| H, signal 11:30–13:30 | 789 | +0.036 | -0.010 |
| H, signal other | 0 | — | — |
| B, neutral bias | 6718 | -0.080 | -0.164 |
| B, counter bias | 11282 | -0.107 | -0.193 |
| outside windows and not aligned (neither question) | 4194 | -0.094 | -0.167 |
| the all-hours playbook as a whole (base + H) | 13745 | -0.086 | -0.166 |
| the no-bias playbook as a whole (base + B) | 28782 | -0.095 | -0.179 |

Oct 8 2025 → Sep 2026 (the year the playbook research was picked on; shown, not judged):

| slice | trades | avg R | avg R at 2× costs |
|---|---|---|---|
| H — outside today's windows, bias-aligned (what the all-hours playbook adds) | 611 | +0.014 | -0.014 |
| B — inside today's windows, bias rule would refuse (neutral or counter) | 3377 | -0.061 | -0.088 |
| base — inside windows, aligned (what the playbook trades today; reference only) | 2106 | -0.049 | -0.075 |

## By cell (descriptive)

| cell | base | H | B |
|---|---|---|---|
| dtfx_close_fib:15m@pb-us30-b988 | 632 (-0.09) | 303 (-0.03) | 881 (-0.04) |
| dtfx_close_fib:15m@pb-us30-b988-trend | 575 (-0.08) | 276 (-0.06) | 782 (-0.06) |
| dtfx_close_fib:5m@pb-xau-6641 | 670 (-0.12) | 399 (-0.05) | 1102 (-0.11) |
| dtfx_wick_fib:15m@pb-ndq-b988 | 716 (-0.07) | 376 (+0.02) | 1035 (-0.02) |
| dtfx_wick_fib:15m@pb-us30-b988-trend | 623 (-0.09) | 318 (+0.02) | 925 (-0.07) |
| dtfx_wick_fib:3m@pb-xau-2ca4 | 588 (-0.13) | — | 903 (-0.10) |
| ict_2022:3m@pb-xau-504f | 625 (-0.16) | — | 1085 (-0.13) |
| ict_amd:5m@pb-ndq-013f | 559 (-0.05) | — | 953 (-0.05) |
| ict_turtle_soup:15m@pb-xau-6062 | 761 (-0.16) | — | 1710 (-0.14) |
| ict_turtle_soup:15m@pb-xau-6062-trend | 734 (-0.15) | — | 1642 (-0.15) |
| ict_turtle_soup:5m@pb-xau-285e | 595 (-0.10) | — | 1122 (-0.13) |
| smc_bos_retest:15m@pb-xau-00dd | 581 (-0.03) | 307 (-0.12) | 698 (-0.09) |
| smc_bos_retest:5m@pb-xau-392f | 1234 (-0.10) | 671 (-0.13) | 1851 (-0.12) |
| smc_mss:3m@pb-xau-d | 769 (-0.07) | — | 1387 (-0.09) |
| smc_mss:5m@pb-xau-3c77 | 632 (+0.01) | — | 1189 (-0.08) |
| sr_rejection:30m@pb-us30-d-trend | 488 (-0.06) | 313 (-0.09) | 735 (-0.04) |

Opening the windows lets a cell's own earlier trade block a later one, so `base` here can differ a little from the playbook test's numbers. A passing group added to a losing playbook still leaves a losing playbook.
