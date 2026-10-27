# Backlog

Agreed work that is not scheduled yet. Newest decisions first. Each item says where it came from and what "done" means.

## Bias system — batch 3 (deferred Oct 26 2026; revisit after the Nov 5 review)

From ChatGPT's bias-filter audit (Oct 26 2026). Batches 1 and 2 are done (b50f359, c37b310): restart-safe and
per-book loss guards, stale-bias block, Jev audits bound/expiring/deduped, bias refreshed before boundary entries,
hour completeness recorded, stale check in the precheck, 15m shadow tag.

1. **One bias-policy evaluator for live and research.** Today research applies only the alignment threshold; live Risk
   adds loss suspension, Jev doubt and reversal exceptions. Extract a deterministic evaluator (structural snapshot +
   book guard state + candidate + any valid audit → disposition, reason codes, risk multiplier, management
   restrictions); use it in the trader precheck, Risk and chronological replay; version policy + config on every
   run and trade. Done when identical inputs give identical decisions live and in replay (aligned, neutral, in-doubt,
   suspended, reversal, missing data, expired audit).
2. **Decision-relevant bias evaluation.** Replace the forward-direction "accuracy" headline with: an explicit horizon and
   missing-price policy, deduplicated samples, and the incremental value of the gate measured on the full candidate
   stream (blocked candidates too) in net R with day-block uncertainty.
3. **Structural snapshot fields.** snapshot_id, policy_version, computed_at / data_asof / last_complete_bar_end per
   component, validity + unavailable reason, invalidation level, coverage — and a missing-component policy decided
   before it is evaluated (h1_minutes / h1_complete are recorded since c37b310 but not used).
4. **Suspension release contract.** Decide whether release is "H1 direction flips" (today) or "any fresh structure
   break"; if changed, it is a policy change that needs its own replay.

## Jev adviser fixes (found Oct 26 2026 in ChatGPT's dynamic-trading review; small)

Done Oct 26 2026 (1ce2105): the HOLD "helped" sign is fixed (dashboard column now "Advice right"), and the Jev call
runs as a background task with a deadline, one per position, dropping replies for closed positions. Still open:

- CUT is chosen when p_worse ≥ 0.6, which ignores payoff sizes (80% × −0.2R and 20% × +1R is still +0.04R). Collect
  payoff-relevant forecasts before giving CUT any authority.
- Prices and candles are rounded to 2 decimals in prompts; keep instrument precision if forex is ever added.
- Action-level intervals resample rows independently; cluster by trade and use calendar blocks.

## Dynamic trading controller (research proposal, Oct 26 2026 — not started)

ChatGPT's proposal (sections 8–14 of its bias-filter document): candidates go OBSERVE → REVIEW → WAIT/ARMED → OPEN,
with independent OpenAI and Claude reviews (sealed, structured output: ENTER / WAIT / CANCEL from a finite set of
triggers and invalidations), deterministic arbitration, and the existing Risk / PositionManager as the only route to
the broker. Models plan while a setup forms; local code watches the trigger and executes.

First milestone if we do it: fix the adviser items above, build the as-of snapshot contract (numeric facts + optional
locally rendered chart), then run independent reviews in SHADOW on a frozen candidate stream with one action policy
(entry WAIT/CANCEL or open-trade EXIT, not both), every candidate and every API cost counted. Arms: baseline, +OpenAI,
+Claude, +both. Needs an OpenAI API key on the server. Decide from net cash contribution after all review costs.
