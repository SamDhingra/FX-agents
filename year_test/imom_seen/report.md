# Intraday momentum into the close: seen (holdout_m1 + dev_m1, halves split 2023-11-17)

Registered Nov 7 2026 (research/imom/PREREGISTRATION_2026-11-07.md). At 15:30 NY: the direction of the move from the previous 16:00 to 15:30; held to 16:00, no stop. Real OANDA bid/ask. Results in basis points of the entry price after the spread (1 bp on NDQ ≈ 2.5 points, on US30 ≈ 4.7 points). Gold (information): 13:00 → 13:30, signal from the previous 13:30.

| instrument | role | trades | right | avg bps | 95% range | 2× costs | halves | always long | vs always long (95%) | random sign p | spread bps | avg move bps | net points | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| US30 | decides | 1,375 | 47% | **-1.05** | -2.13 to +0.08 | -1.54 | -0.58 / -1.53 | -1.23 | +0.18 (-1.51 to +1.82) | 0.785 | 0.49 | 15.1 | -5,780 | fail: 95% range > 0, 2× costs > 0, both halves > 0, beats always-long, beats a random sign (p < 0.05) |
| NDQ | supporting | 1,375 | 49% | **-0.33** | -1.86 to +1.22 | -0.72 | +2.01 / -2.72 | -0.44 | +0.11 (-2.25 to +2.38) | 0.454 | 0.39 | 20.7 | -1,686 | fail: 95% range > 0, 2× costs > 0, both halves > 0, beats always-long, beats a random sign (p < 0.05) |
| XAUUSD | information | 1,455 | 43% | **-1.75** | -2.46 to -0.95 | -3.36 | -1.58 / -1.91 | -2.03 | +0.28 (-0.82 to +1.56) | 0.575 | 1.61 | 9.7 | -6,988 | fail: 95% range > 0, 2× costs > 0, both halves > 0, beats always-long, beats a random sign (p < 0.05) |

## Information (never a pass)

| instrument | variant | trades | avg bps | 95% range | 2× costs | halves | vs always long | random sign p |
|---|---|---|---|---|---|---|---|---|
| US30 | exit 15:50 | 1,375 | -0.23 | -1.05 to +0.62 | -0.79 | -0.14 / -0.33 | +0.87 | 0.198 |
| US30 | signal 15:00→15:30 (Zhang & Hua) | 1,427 | +0.39 | -0.70 to +1.55 | -0.10 | +1.36 / -0.59 | +1.39 | 0.062 |
| US30 | |r| above its running median | 692 | -1.01 | -2.71 to +0.72 | -1.51 | +0.32 / -2.43 | +0.48 | 0.663 |
| NDQ | exit 15:50 | 1,375 | -0.49 | -1.56 to +0.61 | -0.94 | +0.95 / -1.97 | +0.36 | 0.504 |
| NDQ | signal 15:00→15:30 (Zhang & Hua) | 1,425 | +0.06 | -1.48 to +1.62 | -0.33 | +1.61 / -1.52 | +0.44 | 0.302 |
| NDQ | |r| above its running median | 664 | -1.59 | -4.14 to +1.00 | -2.00 | +1.16 / -4.98 | -0.84 | 0.823 |

### By year: trades, avg bps, always-long bps

- **US30**: 2021 243 / -1.57 / -4.28; 2022 239 / -0.84 / -1.07; 2023 237 / +1.21 / +0.53; 2024 240 / -1.44 / -0.70; 2025 237 / -2.37 / -0.77; 2026 179 / -1.36 / -0.95
- **NDQ**: 2021 243 / +0.88 / -2.29; 2022 240 / +4.44 / -0.73; 2023 238 / +0.11 / +0.25; 2024 240 / -2.43 / -1.27; 2025 237 / -4.68 / +0.44; 2026 177 / -0.38 / +1.49
- **XAUUSD**: 2021 245 / -1.74 / -0.80; 2022 257 / -1.73 / -1.29; 2023 255 / -1.80 / -1.28; 2024 257 / -0.85 / -2.47; 2025 254 / -1.18 / -3.74; 2026 187 / -3.71 / -2.77

**US30 did not pass: per the registration, closing-flow momentum on index CFDs is closed. C10 unchanged.**
