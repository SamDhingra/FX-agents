# Gemini's rebuilt SMC/ICT/DTFX gold setups (revision 2) — out-of-sample design (dev_m1,holdout_m1)

Rules exactly as Gemini specified (2026-10-17); open points fixed in fxagents/gemini_smc.py before any run. Gemini built them from our one-year setup table (trades 2025-10-08 → 2026-10-08), so that year is **in-sample: shown, not judged**. Judged = clean data only: Oct 2024–Oct 2025 + 2021–Sep 2024. Pass = on the clean data together ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs; avg R > 0 in each clean piece; and better than both controls. Real OANDA bid/ask fills; R includes the spread.

## #1 G-BOS-Retest-15M — **no pass**

Clean combined: 1737 trades, avg -0.041R (95% -0.09 to +0.01), 2× costs -0.101R; each clean piece positive: no; beats both controls: no.

| Test | Data | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Long avg R (n) | Short avg R (n) | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | clean, combined | 1737 | 43% | -0.041 | -0.09 to +0.01 | -70.4 | -0.101 | -0.008 (904) | -0.076 (833) | 122 min |
| **rule** | dev Oct 2024–Oct 2025 (clean) | 341 | 44% | -0.011 | -0.13 to +0.11 | -3.6 | -0.075 | +0.111 (191) | -0.165 (150) | 122 min |
| **rule** | holdout 2021–Sep 2024 (clean) | 1396 | 43% | -0.048 | -0.10 to +0.01 | -66.8 | -0.107 | -0.039 (713) | -0.057 (683) | 122 min |
| **rule** | Oct 2025–Sep 2026 (in-sample) | 283 | 44% | -0.000 | -0.12 to +0.13 | -0.0 | -0.044 | -0.029 (144) | +0.030 (139) | 92 min |
| coin-flip control | clean, combined | 1737 | 40% | -0.123 | -0.17 to -0.07 | -214.3 | -0.183 | -0.120 (884) | -0.127 (853) | 120 min |
| coin-flip control | dev Oct 2024–Oct 2025 (clean) | 341 | 39% | -0.106 | -0.21 to +0.00 | -36.3 | -0.171 | +0.007 (178) | -0.230 (163) | 117 min |
| coin-flip control | holdout 2021–Sep 2024 (clean) | 1396 | 40% | -0.128 | -0.18 to -0.07 | -178.0 | -0.187 | -0.152 (706) | -0.103 (690) | 120 min |
| coin-flip control | Oct 2025–Sep 2026 (in-sample) | 283 | 45% | +0.043 | -0.09 to +0.19 | +12.3 | -0.000 | -0.014 (147) | +0.105 (136) | 85 min |
| deep 75% control | clean, combined | 911 | 43% | -0.038 | -0.11 to +0.03 | -34.2 | -0.099 | -0.055 (481) | -0.018 (430) | 106 min |
| deep 75% control | dev Oct 2024–Oct 2025 (clean) | 172 | 42% | -0.077 | -0.25 to +0.09 | -13.3 | -0.143 | -0.093 (97) | -0.057 (75) | 110 min |
| deep 75% control | holdout 2021–Sep 2024 (clean) | 739 | 43% | -0.028 | -0.11 to +0.05 | -20.8 | -0.089 | -0.045 (384) | -0.010 (355) | 105 min |
| deep 75% control | Oct 2025–Sep 2026 (in-sample) | 130 | 48% | +0.095 | -0.11 to +0.30 | +12.3 | +0.045 | -0.166 (54) | +0.280 (76) | 80 min |

Setups reaching each stage (both data sets, longs + shorts; the last step counts fills after the daily caps): base: close through swing, leg ≥ 1 ATR 11,356 → 1h EMA agrees 7,639 → body ≥ 0.35 and volume ≥ 0.85× 4,910 → filled (after caps) 2,020


## #2 G-DTFX-Wick-5M — **no pass**

Clean combined: 1702 trades, avg -0.083R (95% -0.13 to -0.03), 2× costs -0.156R; each clean piece positive: no; beats both controls: no.

| Test | Data | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Long avg R (n) | Short avg R (n) | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | clean, combined | 1702 | 43% | -0.083 | -0.13 to -0.03 | -141.8 | -0.156 | -0.066 (896) | -0.103 (806) | 80 min |
| **rule** | dev Oct 2024–Oct 2025 (clean) | 345 | 41% | -0.099 | -0.21 to +0.02 | -34.0 | -0.175 | -0.036 (196) | -0.182 (149) | 74 min |
| **rule** | holdout 2021–Sep 2024 (clean) | 1357 | 43% | -0.079 | -0.13 to -0.03 | -107.8 | -0.151 | -0.074 (700) | -0.085 (657) | 82 min |
| **rule** | Oct 2025–Sep 2026 (in-sample) | 288 | 44% | -0.075 | -0.19 to +0.04 | -21.7 | -0.128 | -0.148 (134) | -0.012 (154) | 58 min |
| coin-flip control | clean, combined | 1702 | 43% | -0.080 | -0.13 to -0.03 | -136.2 | -0.152 | -0.080 (872) | -0.080 (830) | 81 min |
| coin-flip control | dev Oct 2024–Oct 2025 (clean) | 345 | 42% | -0.121 | -0.22 to -0.02 | -41.8 | -0.198 | -0.038 (191) | -0.224 (154) | 73 min |
| coin-flip control | holdout 2021–Sep 2024 (clean) | 1357 | 44% | -0.070 | -0.12 to -0.02 | -94.3 | -0.141 | -0.091 (681) | -0.047 (676) | 84 min |
| coin-flip control | Oct 2025–Sep 2026 (in-sample) | 288 | 45% | -0.096 | -0.21 to +0.02 | -27.6 | -0.149 | -0.132 (136) | -0.063 (152) | 60 min |
| close-anchor + low-volume control | clean, combined | 278 | 39% | -0.138 | -0.25 to -0.02 | -38.5 | -0.216 | -0.139 (151) | -0.137 (127) | 72 min |
| close-anchor + low-volume control | dev Oct 2024–Oct 2025 (clean) | 44 | 34% | -0.254 | -0.55 to +0.06 | -11.2 | -0.340 | -0.356 (25) | -0.119 (19) | 62 min |
| close-anchor + low-volume control | holdout 2021–Sep 2024 (clean) | 234 | 40% | -0.117 | -0.24 to +0.01 | -27.3 | -0.192 | -0.096 (126) | -0.141 (108) | 76 min |
| close-anchor + low-volume control | Oct 2025–Sep 2026 (in-sample) | 44 | 32% | -0.380 | -0.60 to -0.12 | -16.7 | -0.437 | -0.422 (32) | -0.268 (12) | 47 min |

Setups reaching each stage (both data sets, longs + shorts; the last step counts fills after the daily caps): base: structure break, wick range ≥ 1.8 ATR(5m) 21,079 → 1h EMA agrees 13,527 → impulse volume ≥ MedVol 11,415 → filled (after caps) 1,990


## #3 G-SBS-Sweep-15M — **no pass**

Clean combined: 693 trades, avg +0.034R (95% -0.04 to +0.11), 2× costs -0.027R; each clean piece positive: yes; beats both controls: yes.

| Test | Data | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Long avg R (n) | Short avg R (n) | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | clean, combined | 693 | 48% | +0.034 | -0.04 to +0.11 | +23.2 | -0.027 | +0.009 (404) | +0.068 (289) | 121 min |
| **rule** | dev Oct 2024–Oct 2025 (clean) | 157 | 49% | +0.086 | -0.08 to +0.25 | +13.4 | +0.018 | -0.031 (108) | +0.342 (49) | 124 min |
| **rule** | holdout 2021–Sep 2024 (clean) | 536 | 47% | +0.018 | -0.07 to +0.11 | +9.8 | -0.040 | +0.023 (296) | +0.012 (240) | 119 min |
| **rule** | Oct 2025–Sep 2026 (in-sample) | 135 | 47% | -0.001 | -0.20 to +0.20 | -0.2 | -0.047 | -0.117 (66) | +0.110 (69) | 84 min |
| coin-flip control | clean, combined | 693 | 46% | -0.041 | -0.12 to +0.04 | -28.1 | -0.101 | -0.062 (356) | -0.018 (337) | 119 min |
| coin-flip control | dev Oct 2024–Oct 2025 (clean) | 157 | 43% | -0.077 | -0.23 to +0.09 | -12.1 | -0.145 | -0.160 (79) | +0.006 (78) | 103 min |
| coin-flip control | holdout 2021–Sep 2024 (clean) | 536 | 47% | -0.030 | -0.11 to +0.06 | -16.0 | -0.089 | -0.034 (277) | -0.025 (259) | 124 min |
| coin-flip control | Oct 2025–Sep 2026 (in-sample) | 135 | 50% | +0.121 | -0.08 to +0.34 | +16.3 | +0.075 | -0.082 (62) | +0.293 (73) | 111 min |
| counter-trend control | clean, combined | 571 | 42% | -0.087 | -0.17 to +0.00 | -49.6 | -0.149 | -0.009 (276) | -0.160 (295) | 126 min |
| counter-trend control | dev Oct 2024–Oct 2025 (clean) | 129 | 37% | -0.205 | -0.37 to -0.05 | -26.4 | -0.271 | -0.072 (52) | -0.294 (77) | 130 min |
| counter-trend control | holdout 2021–Sep 2024 (clean) | 442 | 44% | -0.053 | -0.16 to +0.05 | -23.2 | -0.114 | +0.006 (224) | -0.112 (218) | 123 min |
| counter-trend control | Oct 2025–Sep 2026 (in-sample) | 103 | 46% | +0.004 | -0.23 to +0.24 | +0.4 | -0.044 | -0.096 (60) | +0.143 (43) | 81 min |

Setups reaching each stage (both data sets, longs + shorts; the last step counts fills after the daily caps): base: sweep and close back, range ≥ 0.7 ATR 8,978 → 1h trend + inside the 20-hour range 3,922 → close in upper half and volume ≥ 0.85× 1,621 → filled (after caps) 828


