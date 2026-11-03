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

## Jev adviser fixes — DONE (Oct 26 + Nov 2 2026)

Oct 26 (1ce2105): HOLD "helped" sign fixed; Jev call in the background with a deadline. Nov 2: payoff-aware second
opinion (p_target / p_stop → expected R of holding → `action_ev`, scored next to the p_worse CUT, still no authority);
prices and candles in prompts at the instrument's precision; scorecard 95% ranges resample whole trading days.

## Dynamic trading controller (research proposal, Oct 26 2026 — milestone 1 built: shadow review gate, see docs/dynamic_controller.md)

ChatGPT's proposal (sections 8–14 of its bias-filter document): candidates go OBSERVE → REVIEW → WAIT/ARMED → OPEN,
with independent OpenAI and Claude reviews (sealed, structured output: ENTER / WAIT / CANCEL from a finite set of
triggers and invalidations), deterministic arbitration, and the existing Risk / PositionManager as the only route to
the broker. Models plan while a setup forms; local code watches the trigger and executes.

First milestone if we do it: fix the adviser items above, build the as-of snapshot contract (numeric facts + optional
locally rendered chart), then run independent reviews in SHADOW on a frozen candidate stream with one action policy
(entry WAIT/CANCEL or open-trade EXIT, not both), every candidate and every API cost counted. Arms: baseline, +OpenAI,
+Claude, +both. Needs an OpenAI API key on the server. Decide from net cash contribution after all review costs.

## Open items from Oct 28 – Nov 2 2026

1. **Wait before entry after an M15 candle closes against the trade** (Oct 28 m15_timing A: +0.018R/trade, but random
   later entry did as well). `m15_wait1` passed its 2016–2020 judgement narrowly (+0.009R, range +0.001..+0.017;
   2021–2026 +0.002R) — weak evidence (that data was already used once for the related m15_live). Shadow tag
   `m15_wait` on live 3m/5m entries from Nov 2; for the Nov 5 review.
2. **Members' view-only dashboard** on the live site (Sam asked whether members can see what he sees; proposal: same
   pages, no controls, amounts in R). Waiting for Sam's answer.
3. **Pre-CPI index drift** (news study): too few CPI days to test; revisit when more are recorded.
4. ~~forexcom_probe test fails~~ — fixed Nov 2 (looked back 2 days, which are all weekend on Sundays / early Mondays).
5. **Live site go-live checklist** (docs/live.md): Cloudflare route, vault-key backup, regulator check before members copy.

Closed since Oct 28: room to next M15 level, M15 timing (late entry / early exit), news fade (both variants),
all-hours and no-bias playbook (paper books keep running), SuperTrend + EMA + RSI (pooled, NDQ-only, held 1h/4h, as a
filter in EMA21/RSI55), gold 06:00. Candle-close audit: no early entries.
