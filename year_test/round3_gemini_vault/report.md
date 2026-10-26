# Round 3, Gemini's checks on the playbook's 3m / 5m entries (vault, stricter judge)

Registered before running (research/round3/gemini/). **m15_impulse_leg** two completed 15m candles stepping against the trade or one wide counter-bar; **ltf_swing_structure_against** 3 hours of 5m swings stepping against it with price on the wrong side of the 1-hour mean; **stop_inside_15m_noise** spread > 8% of the stop OR stop < 0.5 × ATR15; **chasing_exhausted_leg** entering at the extreme of an unretraced ≥ 2 × ATR15 one-hour move in the trade's own direction. Gemini's code unchanged; timeframe labels and unavailable data handled outside it.

Stricter judge: calendar halves split 2018-07-02, circular 5-weekday blocks, random skipping within cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage.

Cohort: 9,120 trades on 3m / 5m, -0.147R average.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| stop_spread_part | 7315 of 9120 (100% coverage) | -0.174 | -0.038 | +0.136 (+0.087 to +0.187) | +0.088 / +0.171 | 0.0184 | **yes** |

Registered for 2016–2020: **stop_spread_part** (spread > 8% of the stop at entry) — the half of stop_inside_15m_noise that passed on seen. **Verdict: CONFIRMED.**

## By cell (descriptive)

| cell | trades | avg R | stop_spread_part flagged (avg R) / kept (avg R) |
|---|---|---|---|
| dtfx_close_fib_3m_pb-xau-4a8c | 718 | -0.155 | 676 (-0.16) / 42 (-0.14) |
| dtfx_close_fib_3m_pb-xau-4a8c-scalp | 751 | -0.184 | 708 (-0.19) / 43 (-0.11) |
| dtfx_wick_fib_3m_pb-xau-2ca4 | 677 | -0.136 | 644 (-0.14) / 33 (-0.04) |
| dtfx_wick_fib_5m_pb-ndq-4a8c-scalp | 666 | -0.126 | 416 (-0.19) / 250 (-0.02) |
| ict_2022_3m_pb-xau-504f | 628 | -0.214 | 564 (-0.21) / 64 (-0.21) |
| ict_amd_3m_pb-us30-013f | 771 | -0.046 | 410 (-0.13) / 361 (+0.05) |
| ict_turtle_soup_5m_pb-xau-285e | 645 | -0.108 | 443 (-0.08) / 202 (-0.16) |
| macd_cross_5m_pb-ndq-d | 1020 | -0.110 | 604 (-0.19) / 416 (+0.01) |
| smc_bos_retest_5m_pb-xau-392f | 1377 | -0.164 | 1138 (-0.18) / 239 (-0.10) |
| smc_displacement_3m_pb-xau-d | 1044 | -0.255 | 1028 (-0.26) / 16 (-0.05) |
| smc_mss_3m_pb-xau-d | 823 | -0.091 | 684 (-0.11) / 139 (-0.02) |

Families: m15_impulse_leg and ltf_swing_structure_against belong to the 'against the higher timeframe' family (its 2016–2020 test was m15_live's) → a pass earns a shadow tag only. chasing_exhausted_leg, if it passes here, is judged once on 2016–2020 (./fx.sh round3g vault). Of stop_inside_15m_noise only its spread half (spread > 8% of the stop) is judged on 2016–2020, registered after it alone passed on seen.
