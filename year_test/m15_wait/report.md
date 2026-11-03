# Wait one M15 candle before entering against a fresh M15 close

Registered Nov 2 2026 before running (research/m15_wait/PREREGISTRATION_2026-11-02.md). Playbook 3m/5m trades whose last completed M15 candle closed against them wait for the next M15 close and enter there (same stop; cancelled if the stop is touched first or the session ends). Replayed by the playbook's own engine with the real bid/ask spread. Judged once on 2016–2020; 2021–2026 (where the idea came from) shown only.

Engine check (plain replay reproduces the recorded R): 2016–2020 100.0%, 2021–2026 100.0% (98% required).

| period | verdict | trades changed | avg R as recorded | avg R with rule | mean d (95% range) | halves | d at 2× costs |
|---|---|---|---|---|---|---|---|
| 2016–2020 (judged) | **PASS** | 1,757 of 9,120 | -0.147 | -0.138 | +0.009 (+0.001 to +0.017) | +0.010 / +0.008 | +0.020 |
| 2021–2026 (shown) | info | 1,895 of 10,724 | -0.095 | -0.093 | +0.002 (-0.005 to +0.009) | +0.001 / +0.003 | +0.009 |

Flagged trades on 2016–2020: entered 2113, stop_first 218, session 107, no_confirm 23

**m15_wait1 is CONFIRMED on 2016–2020 → shadow tag on the live playbook; any trading change is for the review.**
