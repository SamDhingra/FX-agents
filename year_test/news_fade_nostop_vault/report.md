# News fade, no-stop variant (vault: 2016-01-01 → 2021-01-01)

**No-stop variant** (addendum of Oct 28 2026, after the registered rule failed on 2023–2026): exit only at T+150 / 15:50, no stop. Its only test, judged once; weaker evidence than a confirmation.

Registered Oct 28 2026 before this data was read (research/news_fade/PREREGISTRATION_2026-10-28.md). At T+30 after a FOMC / CPI / NFP / PPI release, trade against the move from T−1 to T+30; exit at T+150 or 15:50 NY (first), emergency stop 4 × ATR15, real bid/ask fills. Results in ATR15 net of the spread (R = 4 × ATR15).

| | trades | mean net ATR15 (95% range) | in R | halves | 2× costs | size-matched control (trades) | release − control (95% range) |
|---|---|---|---|---|---|---|---|
| all releases | 649 | +0.10 (-0.33..+0.55) | — | +0.05 / +0.15 | -0.09 | -0.41 (891) | +0.51 (-0.05..+1.08) |

| gate | result |
|---|---|
| ≥ 100 trades | yes |
| 95% range above 0 | **no** |
| both halves > 0 | yes |
| 2× costs > 0 | **no** |
| beats the size-matched control | **no** |

**Does not pass → the news fade is closed.**

## Information only (never a pass)

Unmatched control (every no-release day at 08:30 / 14:00): -0.10 ATR15 on 6309 trades. Size-match thresholds (|first move| ÷ ATR15): NDQ 08:30 1.19, NDQ 14:00 1.30, US30 08:30 1.16, US30 14:00 1.45, XAUUSD 08:30 1.99, XAUUSD 14:00 2.71.
Stop hits: 0 of 649.

| type | XAUUSD | NDQ | US30 | all |
|---|---|---|---|---|
| FOMC | -0.43 (-1.55..+0.69) (39) | +0.04 (-1.12..+1.22) (39) | +0.58 (-0.62..+1.79) (39) | +0.06 (-0.76..+0.92) (117) |
| CPI | -0.34 (-1.31..+0.78) (58) | +0.98 (-0.18..+2.27) (58) | +0.80 (-0.14..+1.76) (58) | +0.48 (-0.30..+1.35) (174) |
| NFP | -0.51 (-1.68..+0.68) (60) | -1.36 (-2.77..+0.03) (60) | +0.92 (-0.33..+2.21) (60) | -0.32 (-1.19..+0.56) (180) |
| PPI | +0.13 (-0.79..+1.12) (60) | +0.03 (-1.30..+1.37) (59) | +0.36 (-0.75..+1.52) (59) | +0.18 (-0.73..+1.15) (178) |

Per cell n is small (≈ 35 a type per instrument): these rows can't rescue or sink the pooled verdict.
