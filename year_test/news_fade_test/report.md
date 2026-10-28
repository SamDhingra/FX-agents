# News fade (test: 2023-11-17 → 2026-10-01)

Registered Oct 28 2026 before this data was read (research/news_fade/PREREGISTRATION_2026-10-28.md). At T+30 after a FOMC / CPI / NFP / PPI release, trade against the move from T−1 to T+30; exit at T+150 or 15:50 NY (first), emergency stop 4 × ATR15, real bid/ask fills. Results in ATR15 net of the spread (R = 4 × ATR15).

| | trades | mean net ATR15 (95% range) | in R | halves | 2× costs | size-matched control (trades) | release − control (95% range) |
|---|---|---|---|---|---|---|---|
| all releases | 361 | +0.16 (-0.42..+0.77) | +0.040 | +0.57 / -0.26 | +0.09 | +0.11 (417) | +0.05 (-0.64..+0.75) |

| gate | result |
|---|---|
| ≥ 100 trades | yes |
| 95% range above 0 | **no** |
| both halves > 0 | **no** |
| 2× costs > 0 | yes |
| beats the size-matched control | **no** |

**Does not pass → closed.** 2016–2020 is not read.

## Information only (never a pass)

Unmatched control (every no-release day at 08:30 / 14:00): +0.05 ATR15 on 3639 trades. Size-match thresholds (|first move| ÷ ATR15): NDQ 08:30 2.55, NDQ 14:00 1.08, US30 08:30 2.56, US30 14:00 1.42, XAUUSD 08:30 1.69, XAUUSD 14:00 1.31.
Stop hits: 145 of 361.

| type | XAUUSD | NDQ | US30 | all |
|---|---|---|---|---|
| FOMC | -0.89 (-2.51..+1.10) (23) | -1.22 (-2.41..+0.07) (23) | -1.03 (-2.34..+0.35) (23) | -1.05 (-2.24..+0.31) (69) |
| CPI | -0.33 (-1.28..+0.66) (33) | +1.19 (-1.07..+4.17) (33) | +0.14 (-1.51..+1.95) (33) | +0.33 (-0.74..+1.47) (99) |
| NFP | +0.22 (-1.38..+1.98) (32) | +2.23 (-0.03..+4.77) (32) | +0.15 (-1.75..+2.28) (31) | +0.87 (-0.43..+2.30) (95) |
| PPI | +0.38 (-0.61..+1.41) (33) | +0.15 (-1.28..+1.67) (33) | -0.09 (-1.64..+1.61) (32) | +0.15 (-0.75..+1.08) (98) |

Per cell n is small (≈ 35 a type per instrument): these rows can't rescue or sink the pooled verdict.
