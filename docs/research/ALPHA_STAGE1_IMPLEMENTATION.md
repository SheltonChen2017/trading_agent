# Stage 1 implementation report — REP-H52 and REP-IDV

Date: 2026-08-16
Author: Claude
Plan: `docs/Alpha_Test_Implementation_Plan.md` section 6
Code: `research/lean/alpha_stage1_replications.py`,
`research/lean/alpha_stage1_benchmark.py`,
`scripts/analyse_qc_alpha_stage1.py`, and their tests
Status: **Submitted at `dc63eec`, independently corrected first at `b143c60`
and then as part of full research/QC audit correction `855941a`. NOT run on
QuantConnect from the reviewed source. Claude counter-review is required.**

This report exists because the implementation landed under a one-line
commit message and the reasoning below belongs in the repository rather
than in a chat log. History is not rewritten to fix that.

## Classification, stated before any result

Both specifications are **method replications**, not exact data
replications, and the differences are recorded now so they cannot be
softened later:

- **REP-H52** scores `close_t / max(close[t-251:t])` over 252 aligned
  sessions. The local signal held **126 days**; this holds **21** to match
  the common monthly outcome contract. It therefore answers a narrower
  one-month portfolio question than the signal it replicates.
- **REP-IDV** replicates this project's **rejected market-model proxy**,
  not the Fama-French three-factor specification. Intercept and market
  beta are frozen on the 90 returns ending *before* the 21-session
  formation month; residuals are taken against those frozen coefficients
  and the point-in-time equal-weight market return; the score is the
  negative sample standard deviation of the 21 residuals.

No industry, size or factor variant may be added after seeing a result.
That would be a separately named and counted look.

## The machinery is copied, deliberately

The submission copied most machinery from `alpha_battery_monthly.py`, but the
2026-08-17 review proved that copying did not preserve the frozen experiment:
it scored on the first monthly session, settled at the next month's entry,
applied score-date membership backward to market-factor history, and had no
cadence-matched benchmark or acceptable analysis path. Those statements in
the original report are retained as implementation history, not current
evidence that the machinery was safe.

The corrected implementation freezes the previous month-end, enters at the
next distinct close, tracks overlapping cohorts for exactly 21 sessions,
records point-in-time daily market factors, refuses session gaps, and uses a
matching benchmark and provenance-strict analyser. The full audit also
standardized current QuantConnect Python syntax and added directory-wide
guards against legacy API members and framework-member shadowing. See
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`.

Rewriting reviewed machinery for a new pair of scores is precisely how the
previous round reintroduced defects that had just been fixed. Copying it
is the lower-risk choice even though it duplicates code.

## Two defects of mine, caught before review

**1. The copy carried the wrong completeness contract.** It inherited the
monthly battery's ten-specification list, so the guard would have demanded
`MOM_12_1`, `QUALITY_COMPOSITE` and others that this algorithm never
computes — refusing every run spuriously. Corrected to
`("REP_H52", "REP_IDV")` and pinned by a test that reads the constant from
the AST.

**2. My "behavioural" tests tested a copy of the algorithm.** The first
version reimplemented both scores *inside the test file*. Every assertion
computed a real number, and every one would have passed no matter what the
algorithm did. This is AQR1-004 in a new disguise, one round after I
recorded that lesson.

It surfaced only because **a mutation of the algorithm failed to redden
anything**. The scores are now module-level pure functions
(`_h52_score`, `_idio_vol_score`) that the tests execute directly.

### The lesson that actually holds

"Write behavioural tests" was already my stated resolution entering this
round, and I still got it wrong — because a test that computes numbers
*feels* behavioural regardless of what it is computing them from.

The check that works is mechanical: **mutate the implementation and
confirm the test dies.** A test suite that stays green under a mutated
implementation is not testing that implementation, whatever its assertions
look like.

## Verification

- 7 tests, all executing the algorithm's own functions.
- **4 mutations against the real implementation, 4 detected**: leaking the
  formation month into the beta fit (stock leg), the same for the market
  leg, dividing H52 by the low instead of the high, and reverting the
  specification list.
- Behavioural spot checks: H52 scores exactly 1.0 at the 52-week high and
  0.5 at half of it; IDV scores ~0 for a pure-beta stock, ranks a noisier
  stock worse, and a shock confined to the formation month provably does
  not move the estimated beta.
- Full suite: **4,131 passed / 0 failed**.

## What is deliberately not done

- **No QuantConnect run.** Stage 1 code has not been reviewed by Codex, and
  the workflow forbids using cloud compute to exercise unreviewed code.
- **No result claimed.** There is no Stage 1 entry in
  `docs/alpha-result.md` because no run exists.
- **Stage 0 is incomplete** and nothing here depends on it: one run stalled
  at 86.5% holding the only backtest node, and the organisation exhausted
  its coding sessions. No Stage 0 statistic exists.
