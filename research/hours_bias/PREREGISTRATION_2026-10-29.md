# All-hours and no-bias playbook — pre-registration (Oct 29 2026, before any run)

Sam's questions (Oct 29 2026):

- **H, no cut-off.** Today the playbook only enters inside 02:00–05:00, 08:30–11:30, 13:30–15:30 and 20:00–23:59 NY.
  What do its setups earn if entries run all session, **20:00 → 15:50 NY**?
- **B, bias not followed.** Several live setups looked good but were refused because they went against the higher-timeframe
  bias. What do those trades earn?

## What runs

- **Cells:** the current `data/playbook.json` at run time, frozen into the output with its hash. The vault run uses the
  same frozen cells.
- **Engine:** the research engine the playbook is built with (`research.run_job`), on OANDA bid/ask 1-minute data with
  the real spread of every minute, through the live position manager. It is the same engine as `./fx.sh pbtest`.
- **Changes in that one replay:**
  - Entry windows are `[20:00, 23:59] + [00:00, 15:50]`.
  - The bias filter passes every finite reading. A missing bias reading is still skipped.
- **Unchanged:**
  - The news blackouts.
  - The 15:50 flatten.
  - The existing rule of no entries in the 20 minutes before the flatten, so 15:30–15:50 stays shut.
  - The closed daily break, 17:00–20:00.
  - Entry at the close of the setup's own candle.
  - One trade at a time per cell.

## How each trade is tagged

Each trade is tagged by the signal candle's close time and by today's rules.

| group | today's windows | bias rule (side × score vs 0.25) |
|---|---|---|
| base (reference) | inside | aligned |
| **H** | outside | aligned |
| **B** | inside | neutral or counter |
| neither (shown only) | outside | neutral or counter |

## Gates

The test is judged on **2021-01-01 → 2025-10-07**. The playbook research was picked on Oct 2025 → Oct 2026, so that year
is shown but not judged.

H and B are each judged by themselves. A group passes only if it meets all of these:

- at least 100 trades
- average R > 0
- 95% range above 0, using a bootstrap over 5-day blocks of days
- average R > 0 at twice the spread
- positive in both halves, split by trade order

Two groups are tested, so roughly 1 in 10 runs would show a lucky pass.

**Vault.** Only a group that passes is judged once on 2016–2020 (`./fx.sh hoursbias vault`). Each period runs only once, and
the code refuses to run it again.

**Not evidence:**

- the per-session-block, neutral/counter and per-cell tables
- the picked year
- the "playbook as a whole" lines

They cannot rescue a failed group.

## What follows

- **No trading change before the Nov 5 review**, whatever the result.
- From Oct 29, two paper books trade forward next to the playbook:
  - **playbook_allhours:** the same cells, entries 20:00 → 15:50.
  - **playbook_nobias:** the same cells, bias rule off. Each trade records what the rule would have said
    (`ignored:aligned`, `ignored:neutral` or `ignored:counter`).
- A confirmed group is a candidate for the Nov 5 review only together with its forward record. The playbook itself is
  negative on 2021–2026 (every cell failed `pbtest`). Adding a passing group to it still leaves a losing playbook unless
  the group is large enough to carry it.

## Outcome (Oct 29 2026): neither group passes, the vault is not touched

Judged on 2021-01-01 → 2025-10-07, 16 cells (frozen eab009372932):

| group | trades | avg R | 95% range | 2× costs |
|---|---|---|---|---|
| H (outside today's windows, aligned) | 2,963 | −0.063 | −0.12 to −0.01 | −0.133 |
| B (inside windows, bias rule would refuse) | 18,000 | −0.097 | −0.12 to −0.07 | −0.182 |
| base (today's playbook, reference) | 10,782 | −0.093 | −0.12 to −0.06 | −0.175 |

- **H:** 00:00–02:00 is the worst block (−0.22R). 11:30–13:30 shows +0.036R in the clean years but −0.010R at 2× costs,
  and it is a sub-slice, so it is not evidence.
- **Not every cell gained hours.** 8 of the 16 cells (the ICT and some SMC/DTFX 3m/5m cells) produced no H trades at
  all, because those setups carry their own session or killzone filter.
- **B:** counter-bias −0.107R and neutral −0.080R, against −0.093R for aligned. The bias rule barely separates winners
  from losers, but switching it off doesn't help either.
- The paper books `playbook_allhours` and `playbook_nobias` keep running as a forward record until the Nov 5 review.
