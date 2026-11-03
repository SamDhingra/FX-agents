# Efficiency-ratio chop filter (seen, stricter judge)

Registered Nov 3 2026 before running (research/chop_er/PREREGISTRATION_2026-11-03.md). Skip a playbook 3m/5m entry when Kaufman's efficiency ratio ER(12) of the last completed candles is below 0.3. **er15** (15-minute) decides; er1h is a variant; the current CHOP chop zone and ADX < 20 are shown for comparison.

Cohort: 10,724 trades on 3m / 5m, -0.095R average.

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| er15 | 6556 of 10724 (100% coverage) | -0.104 | -0.080 | +0.025 (-0.023 to +0.073) | +0.019 / +0.029 | 0.0215 | **no** (gates not met) |
| er1h | 5921 of 10724 (100% coverage) | -0.100 | -0.087 | +0.013 (-0.035 to +0.060) | -0.020 / +0.045 | 0.1635 | **no** (gates not met) |

**er15 does not pass → the vault is not touched; the ER filter is closed.**

### For comparison (information only, never a pass)

| check | flagged (coverage) | flagged avg R | kept avg R | kept − flagged (95% range) | halves | stratified random p | pass |
|---|---|---|---|---|---|---|---|
| chop15_skip | 1252 of 10724 (100% coverage) | -0.080 | -0.097 | -0.017 (-0.089 to +0.054) | -0.105 / +0.078 | 0.5230 | **no** (gates not met) |
| adx15 | 4128 of 10724 (100% coverage) | -0.114 | -0.083 | +0.032 (-0.021 to +0.084) | +0.041 / +0.020 | 0.1259 | **no** (gates not met) |

### Average R by 15-minute efficiency ratio (descriptive)

| ER(12) 15m | trades | avg R |
|---|---|---|
| [0.0, 0.1) | 2444 | -0.083 |
| [0.1, 0.2) | 2238 | -0.119 |
| [0.2, 0.3) | 1874 | -0.114 |
| [0.3, 0.4) | 1490 | -0.059 |
| [0.4, 0.5) | 1137 | -0.102 |
| [0.5, 0.6) | 724 | -0.072 |
| [0.6, 1.01) | 817 | -0.093 |

A filter that passes but leaves the kept trades below zero still leaves a losing playbook.
