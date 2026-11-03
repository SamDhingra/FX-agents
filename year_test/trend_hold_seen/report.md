# Trend rules held, NDQ SuperTrend, SuperTrend in EMA21/RSI55 — seen (2021-01-01 → 2026-10-01)

Registered Nov 2 2026 before running (research/trend_hold/PREREGISTRATION_2026-11-02.md). Real bid/ask 1-minute data, entries at the signal candle's close, stops on the 1-minute bid/ask, one trade at a time.

Gates: ≥ 100 trades, avg R > 0, 95% range above 0, avg R > 0 at 2× costs, both halves > 0, beats its control.

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| Held — SuperTrend rule, 1h | no | 2764 | 32% | -0.023 | -0.072 to +0.035 | -0.041 | -0.037 / -0.010 | -0.015 | 1% |
| Held — SuperTrend rule, 4h | no | 728 | 33% | -0.029 | -0.125 to +0.081 | -0.039 | -0.080 / +0.020 | +0.076 | 1% |
| Held — EMA21/RSI55, 1h | no | 2506 | 29% | -0.001 | -0.042 to +0.035 | -0.015 | -0.012 / +0.009 | -0.041 | 1% |
| Held — EMA21/RSI55, 4h | no | 656 | 29% | +0.004 | -0.058 to +0.086 | -0.002 | +0.013 / -0.004 | -0.031 | 1% |
| EMA21/RSI55 + SuperTrend agrees (gold, US30, 15m) | no | 3427 | 28% | -0.021 | -0.056 to +0.014 | -0.055 | -0.020 / -0.023 | -0.008 | 3% |
| EMA21/RSI55 gold, 06:00 hour only | no | 114 | 17% | -0.205 | -0.304 to -0.086 | -0.253 | -0.198 / -0.212 | -0.017 | 5% |

Held trades pay financing at 5% a year of the position value (registered). Same trades at 0% / 10%:

| primary | avg R at 0% | at 5% | at 10% | avg nights held |
|---|---|---|---|---|
| Held — SuperTrend rule, 1h | +0.006 | -0.023 | -0.053 | 1.5 |
| Held — SuperTrend rule, 4h | +0.024 | -0.029 | -0.082 | 5.5 |
| Held — EMA21/RSI55, 1h | +0.013 | -0.001 | -0.016 | 0.8 |
| Held — EMA21/RSI55, 4h | +0.030 | +0.004 | -0.021 | 3.0 |

**Nothing passed on 2021–2026. ./fx.sh trendhold vault still runs the registered NDQ-only check (part 2).**

## Shown, not judged

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| EMA21/RSI55 as the paper book (base) | info | 4607 | 28% | -0.008 | -0.038 to +0.021 | -0.043 | -0.011 / -0.005 | +nan | 3% |
| EMA21/RSI55 with SuperTrend stop/trail/exit | info | 2672 | 33% | -0.011 | -0.072 to +0.052 | -0.054 | +0.008 / -0.030 | +nan | 4% |

### Held — SuperTrend rule, 1h by instrument

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | info | 935 | 34% | -0.008 | -0.079 to +0.084 | -0.019 | +0.012 / -0.028 | +nan | 1% |
| US30 | info | 955 | 31% | -0.078 | -0.160 to +0.011 | -0.090 | -0.077 / -0.078 | +nan | 1% |
| XAUUSD | info | 874 | 32% | +0.020 | -0.081 to +0.130 | -0.011 | -0.046 / +0.090 | +nan | 2% |

### Held — SuperTrend rule, 4h by instrument

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | info | 242 | 34% | -0.028 | -0.183 to +0.153 | -0.034 | -0.098 / +0.038 | +nan | 0% |
| US30 | info | 246 | 31% | -0.120 | -0.255 to +0.030 | -0.127 | -0.076 / -0.161 | +nan | 0% |
| XAUUSD | info | 240 | 35% | +0.064 | -0.133 to +0.286 | +0.047 | -0.066 / +0.186 | +nan | 1% |

### Held — EMA21/RSI55, 1h by instrument

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | info | 848 | 31% | +0.003 | -0.058 to +0.069 | -0.006 | -0.014 / +0.021 | +nan | 1% |
| US30 | info | 855 | 29% | -0.002 | -0.061 to +0.062 | -0.012 | +0.007 / -0.011 | +nan | 1% |
| XAUUSD | info | 803 | 28% | -0.005 | -0.069 to +0.053 | -0.028 | -0.028 / +0.019 | +nan | 2% |

### Held — EMA21/RSI55, 4h by instrument

| primary | verdict | trades | win | avg R | 95% range | 2× costs | halves | control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | info | 231 | 32% | -0.005 | -0.093 to +0.107 | -0.009 | +0.021 / -0.029 | +nan | 0% |
| US30 | info | 223 | 27% | -0.031 | -0.128 to +0.087 | -0.036 | +0.016 / -0.083 | +nan | 0% |
| XAUUSD | info | 202 | 27% | +0.054 | -0.063 to +0.211 | +0.042 | +0.000 / +0.106 | +nan | 1% |

### EMA21/RSI55 (base): avg R by instrument × entry hour (NY), trades in brackets

| hour | XAUUSD | US30 |
|---|---|---|
| 02 | -0.05 (208) | -0.12 (234) |
| 03 | -0.02 (194) | +0.00 (306) |
| 04 | -0.04 (148) | +0.04 (193) |
| 05 | +0.17 (88) | -0.06 (118) |
| 06 | -0.24 (105) | +0.01 (129) |
| 07 | -0.01 (141) | +0.15 (149) |
| 08 | -0.05 (380) | -0.05 (229) |
| 09 | -0.00 (232) | +0.09 (419) |
| 10 | -0.02 (227) | -0.10 (307) |
| 11 | +0.05 (92) | +0.07 (149) |
| 12 | +0.15 (45) | -0.13 (85) |
| 13 | -0.04 (47) | +0.12 (96) |
| 14 | -0.14 (69) | +0.11 (101) |
| 15 | -0.01 (46) | +0.06 (70) |

### EMA21/RSI55 + SuperTrend agrees: avg R by instrument × entry hour (NY), trades in brackets

| hour | XAUUSD | US30 |
|---|---|---|
| 02 | -0.05 (147) | -0.14 (174) |
| 03 | -0.07 (144) | -0.02 (244) |
| 04 | -0.03 (112) | +0.06 (133) |
| 05 | +0.13 (63) | -0.14 (80) |
| 06 | -0.23 (76) | -0.00 (94) |
| 07 | -0.06 (102) | +0.17 (111) |
| 08 | -0.12 (273) | -0.07 (181) |
| 09 | -0.04 (176) | +0.13 (336) |
| 10 | -0.04 (166) | -0.07 (245) |
| 11 | +0.04 (60) | +0.09 (98) |
| 12 | +0.18 (33) | -0.14 (57) |
| 13 | -0.09 (35) | +0.11 (70) |
| 14 | -0.10 (59) | +0.00 (75) |
| 15 | -0.02 (35) | +0.02 (48) |
