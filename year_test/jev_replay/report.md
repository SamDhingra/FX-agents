# Can Jev read the next hour from candles? Historical replay

Registered Nov 9 2026 (research/jev_replay/PREREGISTRATION_2026-11-09.md). Hourly decisions 02:00–14:00 NY, 2026-01-02 → 2026-09-30, XAUUSD / NDQ / US30. Jev saw anonymised candles only (no dates, prices or symbol). Outcome over the next hour: UP / DOWN (a sustained move of ≥ ½ hourly range) or NEITHER. Lower Brier = better (always NEITHER ≈ the base rate).

Decisions: 7,509 · Jev answered 100.0% · outcomes neither 4,459, up 1,569, down 1,481 · Jev calls made this run: 15,018
Model(s): jev-1.14.0

| forecast | mean Brier |
|---|---|
| hour-only benchmark | 0.5492 |
| momentum-only benchmark | 0.5502 |
| measured benchmark (primary baseline) | 0.5515 |
| **measured + Jev (candidate)** | **0.5733** |
| Jev alone (where it answered) | 0.6586 (measured on the same: 0.5515) |

**Improvement of the candidate over measured: -0.02177 (95% range -0.02648 to -0.01714); halves -0.01956 / -0.02388. FAIL: 95% range above 0, both halves > 0, beats momentum-only.**

## Information

- direction when the hour did move (3,050): Jev's likelier side right 48.8%, following the previous hour 49.6%
- mirror check (7,509): Jev's p(up) vs its p(down) on the upside-down packet: correlation 0.33, mean gap 0.031; p(neither) gap 0.052; average p(up) 0.071 vs 0.062 upside down

| Jev p(move) band | decisions | average p(move) | actually moved |
|---|---|---|---|
| 0.0–0.2 | 6,262 | 0.14 | 0.39 |
| 0.2–0.4 | 1,244 | 0.24 | 0.48 |
| 0.4–0.6 | 3 | 0.40 | 0.67 |

| instrument | decisions | measured | candidate | Jev alone |
|---|---|---|---|---|
| NDQ | 2,504 | 0.5482 | 0.5708 | 0.6599 |
| US30 | 2,504 | 0.5879 | 0.6210 | 0.7280 |
| XAUUSD | 2,501 | 0.5184 | 0.5280 | 0.5877 |

**Jev adds nothing over a simple statistical forecast of the next hour: evidence for removing or reducing its weight in the hourly pick (Sam's decision). Not re-run with another prompt on these data.**
