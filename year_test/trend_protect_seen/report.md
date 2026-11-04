# Protection for trend-profile playbook trades (seen)

Registered Nov 4 2026 before running (research/trend_protect/PREREGISTRATION_2026-11-04.md). Trend cells (15m+, first target 2R) have no protection before +2R. Each trade replayed on the playbook's own engine with the real spread; only what happens before the first target changes.

Cohort: 3,102 trend-profile trades; engine reproduces 100.0% of them (3,102 judged).

Today: avg -0.072R, 36% win. 336 trades (11%) reached +1R and still closed at or below 0 (avg -0.93R) — the Nov 4 pattern.

| rule | verdict | changed | win | avg R | change vs today (95% range) | halves | 2× costs | trades ≥ 2R today: today → rule |
|---|---|---|---|---|---|---|---|---|
| stop to +0.1R at +1R (primary) | **no** (95% range above 0, both halves > 0) | 604 of 3,102 | 47% | -0.082 | -0.010 (-0.031 to +0.010) | +0.006 / -0.029 | +0.002 | 315: +2.51 → +1.87 |
| stop to break-even at +0.5R | info | 1,295 of 3,102 | 19% | -0.077 | -0.005 (-0.034 to +0.024) | +0.017 / -0.029 | -0.008 | 315: +2.51 → +1.33 |
| 50% off at +1R, stop to +0.1R | info | 1,239 of 3,102 | 47% | -0.078 | -0.006 (-0.029 to +0.017) | +0.008 / -0.022 | +0.003 | 315: +2.51 → +1.60 |

### By cell (avg R)

| cell | trades | today | lock1 | be05 | half1 |
|---|---|---|---|---|---|
| dtfx_close_fib_15m_pb-us30-b988-trend | 764 | -0.089 | -0.081 | -0.093 | -0.076 |
| ict_turtle_soup_15m_pb-xau-6062-trend | 922 | -0.115 | -0.135 | -0.136 | -0.128 |
| smt_divergence_15m_pb-ndq-06e2-trend | 731 | -0.011 | -0.054 | -0.071 | -0.056 |
| sr_rejection_30m_pb-us30-d-trend | 685 | -0.059 | -0.044 | +0.015 | -0.036 |

**lock1 does not pass → the vault is not touched; the trend profile stays as it is.**
