# ACER-0A completion proposals (ACER-0A.5–0A.9)

Archive status: **SUPERSEDED by Analyst Revisions V2 on 2026-08-25; these
proposals were never an executable freeze and are not current instructions.**

Status: **PROPOSALS AWAITING OWNER CONFIRMATION; INDEPENDENTLY CORRECTED.
Nothing here is frozen.**
The ACER-0A partial freeze records the owner's decisions; the review that
followed established that those decisions are not yet an executable
preregistration, because naming an encoding does not define the rating scale
that produces it and naming "residualized IC" does not define a reproducible
statistic. This document proposes the missing definitions so the owner has
concrete options to accept, amend, or reject rather than a blank page.

**These values acquire authority only when the owner freezes them in
writing.** Until then ACER-2 must not run, and no real-outcome slot may be
consumed. Every choice below was made without inspecting any outcome; the
rating-vocabulary counts are structural measurements of the corpus and
consume no research look.

Open items not covered here: **ACER-0A.1** (numeric robustness rule) already
has a proposal in the freeze document; **ACER-0A.2** depends on the earnings
audit; **ACER-0A.3**, **ACER-0A.4** and **ACER-0A.10** depend on data this
host does not have and on the blocked security-master ruling.

**Independent-review correction, 2026-08-21:** the submitted draft normalized
the signal by the sum of decay weights, which could cancel decay entirely;
fit validation outcomes in their own control regressions while calling the
result out of sample; named a stationary bootstrap that the cited repository
toolkit does not implement; and listed only four of fifteen measured refused
rating strings. The corrected proposals below retain the same frozen family
but remove those contradictions. They remain proposals, not owner decisions.

---

## ACER-0A.5 — canonical rating scale

### Measured vocabulary

The corpus contains **54 distinct rating strings** (53 as current ratings, 47
as previous). Coverage is extremely concentrated: the top 19 strings in the
current-rating field account for **99.57%** of the 584,916 events, and its 34
strings below 500 events together account for 2,530 events (0.43%).

### Proposed five-level ordinal scale

| Level | Meaning | Strings (compared case-insensitively, whitespace collapsed) |
|---:|---|---|
| 5 | strong buy | `strong buy`, `conviction buy`, `top pick`, `action list buy` |
| 4 | buy | `buy`, `outperform`, `overweight`, `market outperform`, `sector outperform`, `positive`, `accumulate`, `add`, `speculative buy`, `long-term buy`, `outperformer`, `above average` |
| 3 | hold | `neutral`, `hold`, `equal-weight`, `market perform`, `sector perform`, `in-line`, `sector weight`, `perform`, `peer perform`, `market weight`, `average` |
| 2 | underperform | `underweight`, `underperform`, `sector underperform`, `market underperform`, `reduce`, `negative`, `underperformer`, `below average`, `trim`, `cautious` |
| 1 | sell | `sell`, `strong sell` |

**Notch change** = level(new) − level(previous), an integer in [−4, +4].

### Refusals, not defaults

Any string **not** in the table produces a **named refusal**, never a default
level. The complete measured refusal vocabulary is `mixed`, `fair value`,
`not rated`, `tender`, `developing`, `equalweight`, `gradually accumulate`,
`hold neutral`, `performer`, `sector overweight`, `sector performer`,
`sector underweight`, `speculative hold`, `trading buy`, and `trading sell`.
The first four express no position on an ordinal buy-to-sell axis; several of
the low-frequency remainder could plausibly be mapped, but doing so is an
owner-visible specification choice rather than an alias silently invented by
the implementation. Any future unrecognized string is refused as well.
Defaulting an unknown string to 3 (hold) would manufacture a zero-notch
observation out of missing information and quietly dilute the signal toward
zero; refusing keeps the sample honest and the refusal counted.

### The judgement calls, stated rather than hidden

Three assignments are genuinely arguable and the owner should rule on them
deliberately:

1. **`speculative buy` at 4.** It is a buy with a risk caveat. Placing it at 4
   treats the caveat as immaterial.
2. **`above average` / `average` / `below average` at 4 / 3 / 2.** This is a
   different rating axis (relative performance banding) mapped onto the
   buy-to-sell axis. Only 27 events are affected; refusing them instead would
   be defensible and simpler.
3. **Firm-idiosyncratic neutrals.** `sector weight` (KeyBanc), `perform`
   (Oppenheimer), `peer perform` (Wolfe) and `market weight` are each one
   firm's neutral. The proposal maps them globally at 3. A **firm-specific**
   map would be more faithful but multiplies the specification by the number
   of firms and creates a large surface for post-hoc adjustment. The global
   map is proposed precisely because it is harder to tune.

**Risk to record:** a global map cannot express that one firm's `outperform`
sits above another's, and it assumes the five levels are equally spaced. The
notch encoding therefore carries a cardinality assumption that the
direction-only encoding does not — which is exactly why the family keeps
both.

---

## ACER-0A.6 — signal construction

- **Availability.** An action becomes eligible at the open of the next
  trading session strictly after the later of its action date and its
  `last_updated` UTC date, per the frozen ACER-1 rule. No intraday timestamp
  is used.
- **Per-firm state and expiry.** Each (issuer, firm) pair carries at most one
  live action per encoding. A new eligible action from that firm replaces its
  previous state, and a state is live only while `0 <= age <= 2 * H`. A newer
  refused action clears that encoding's prior state rather than allowing a
  stale signal to survive information the mapping cannot interpret. This
  makes the aggregate a mean of current firm-level revision signals rather
  than a sum over duplicate opinions or an indefinitely carried history.
- **Event values.** For the ordinal encoding, only `upgrades` and
  `downgrades` create non-zero events. Both current and previous ratings must
  map; an upgrade requires a strictly positive mapped notch and a downgrade a
  strictly negative one. Missing previous ratings, zero or opposite-signed
  mapped changes, blank actions, and unknown actions produce named refusals.
  The measured non-directional actions `maintains`, `initiates_coverage_on`,
  `reiterates`, `assumes`, `reinstates`, `terminates_coverage_on`, `suspends`,
  and `removes` create an explicit zero event. Initiations therefore do not
  manufacture a revision from the absence of a prior rating.
- **Decay.** An action's weight at session *t* is `exp(-ln(2) * age / H)`
  where `age` is the number of **trading sessions** since the action became
  eligible and `H` is the frozen half-life (21, 63, or 126). Age is counted in
  sessions, not calendar days, so the decay does not accelerate across
  weekends and holidays.
- **Aggregation (the frozen coverage-neutral per-firm mean).** For issuer *i*
  at session *t*, let `N_live` be the number of live firm states for that
  encoding. The score is `sum(w * notch) / N_live` (or `sum(w * sign) /
  N_live` for the direction encoding). Dividing by the number of firms keeps
  issuers with forty analysts and four analysts on the same scale while
  preserving absolute decay toward zero. Dividing by `sum(w)` is forbidden:
  three equally old +1 actions would otherwise always score +1 at every age
  and under every half-life, normalizing away the intended decay.
- **Minimum coverage.** An issuer needs `N_live >= 3`, with every counted state
  satisfying `age <= 2 * H`, to receive a score; below that the
  issuer is refused for that session rather than scored from one opinion.
  This threshold is a proposal and is deliberately not tuned.
- **Encoding (b) does not depend on the scale.** Direction-only sign is taken
  from `rating_action`: `upgrades` → +1, `downgrades` → −1, and the eight
  explicitly named measured non-directional actions above → 0. Blank or
  unknown future action values refuse rather than silently becoming neutral.
  This makes encoding (b) implementable independently of ACER-0A.5, and gives
  the family one member immune to the cardinality assumption above.
- **Same-session collisions.** If one firm issues two actions on the same
  issuer with the same eligibility session, both are refused rather than
  arbitrarily ordered: same-day vendor ordering does not establish
  chronology, a fact already measured in the identity work. The ambiguous
  collision clears the prior live state for that encoding at that session.

### The zero-event rule is an owner decision; the submitted scan is not decision-grade

The zero-event rule above means a later `maintains` **erases** an earlier
upgrade's decayed signal, while the alternative below lets that revision keep
decaying. The choice therefore changes the signal and must be frozen before a
development run.

The counter-review attempted to quantify this effect, but the measurement is
**not decision-grade** and its submitted percentages are withdrawn from this
active proposal. It grouped events by **raw ticker** and **raw firm** strings
before issuer identity or firm aliases exist, so it cannot establish “the same
firm on the same issuer.” More importantly, its reported half-life percentages
counted **all later actions** that replaced state, including later upgrades and
downgrades that replace state under both options; they did not isolate the
incremental effect of non-directional zero events. It also converted calendar
days with `252/365` rather than counting exact NYSE trading sessions. Those
quantities cannot support an owner choice between the two rules.

A decision-grade measurement, if the owner wants one before ruling, must wait
for resolved issuer identity and a frozen firm-alias map, use exact NYSE
trading sessions, and report at least three separate cumulative-incidence
curves: replacement by a directional action, replacement by a non-directional
zero event, and expiry at `2 * H`. The tool, grouping keys, source hashes, and
result hash must be committed and independently reviewed before its numbers
enter this proposal.

**Two defensible options, for the owner to choose between:**

1. **Keep the zeroing rule** (as corrected above) and accept the asymmetry,
   recording it as a known property of the family rather than discovering it
   after a result. The rule has a clear reading: a firm's *current* revision
   is nil once it maintains.
2. **Let a non-directional action leave the prior revision decaying
   untouched**, so `maintains` neither refreshes nor erases. The signal then
   measures "how recently and strongly did anyone revise", and the half-life
   dimension means what its name says.

Neither is obviously right, and the choice changes the signal materially, so
it must be frozen before the development run and never after seeing a result.

---

## ACER-0A.7 — controls and outcome

- **Outcome.** Forward **21-session** total return from the eligibility
  session's open to the open 21 sessions later, adjusted for splits and
  dividends. Using opens on both ends avoids a close-to-open gap that the
  signal could not have traded.
- **Controls**, all point-in-time as of the eligibility session:
  momentum (12-month return skipping the most recent month), size (log market
  cap), liquidity (log 60-session median dollar volume), volatility
  (60-session realized), value (book-to-market), sector (GICS, as dummies),
  analyst coverage (count of live firm actions), and earnings surprise
  (ACER-0A.2, pending the audit).
- **Normalization.** Each continuous control is cross-sectionally
  winsorized at the 1st and 99th percentiles **within the session**, then
  z-scored within the session. Winsorizing within the session avoids using
  any cross-sectional information from other dates.
- **Out-of-sample residualization.** For each walk-forward fold, fit one pooled
  ordinary-least-squares control model on the fold's purged and embargoed
  **training rows only**, with an intercept, the normalized continuous
  controls, and the frozen sector indicators. Apply those fixed coefficients
  to the validation controls and define each validation residual as realized
  forward return minus that prediction, **without refitting on validation
  outcomes**. The primary statistic is the cross-sectional **Spearman**
  correlation between the signal and those out-of-sample residuals within
  each validation session, averaged with one equal weight per session.
  Spearman rather than Pearson is proposed because the notch encoding is
  ordinal with heavy mass at zero, where a Pearson coefficient would be
  dominated by a few large moves.
- **Missing controls refuse the row.** An issuer missing any required control
  for a session is refused for that session and the refusal is counted. No
  control is ever imputed, carried forward, or replaced with a
  cross-sectional mean.
- **Dependency disclosure.** ACER-0A.7 cannot become final until ACER-0A.2,
  0A.3, and 0A.10 bind the surprise, value, price/volume, sector, adjustment,
  and mapping sources. The formulas here do not convert those open data
  semantics into frozen facts.

---

## ACER-0A.8 — estimation and significance protocol

- **Development period:** 2012-01-01 through 2021-12-31.
  **Untouched confirmation period:** 2022-01-01 through the exact maximum
  eligible session in the frozen input-dataset manifest. That terminal date
  and dataset identity are recorded before either run; “corpus end” is not an
  open-ended date that can grow between attempts. The confirmation period is
  not inspected, plotted, or summarized before the single confirmation pass.
- **Walk-forward:** seven expanding-window folds. The first training window is
  2012-01-01 through 2014-12-31 and the validation blocks are calendar years
  2015 through 2021, one year per fold. Each fold refits the control model on
  its eligible historical training rows only and emits validation residuals
  under the rule in ACER-0A.7.
- **Purge and embargo:** because the 21-session outcome overlaps, each fold's
  training data is purged of observations whose outcome window overlaps the
  validation window, with an additional **21-session embargo immediately
  before each validation block**. No post-validation embargo is substituted
  for the pre-validation exclusion. Overlapping observations are the reason a
  naive test would produce a spurious p-value.
- **Independent observation unit: the session**, not the issuer-row. Rows
  within one session share market-wide shocks and are not independent.
- **Significance:** apply the repository's existing **circular moving-block
  bootstrap** to the one-IC-per-validation-session series, with fixed block
  length **21 sessions**, **10,000 draws**, **seed 20260821**, and a
  **two-sided** test. This names the algorithm actually implemented by
  `ml.cross_sectional.block_bootstrap_ic_significance`; it is not a stationary
  bootstrap. Before any real outcome is read, the exact sample-floor/block
  combination must pass the toolkit's refusal rule and a recorded **synthetic
  null calibration**. A failed calibration leaves this proposal unfreezable;
  it does not authorize choosing a new block length after seeing outcomes.
- **Finite-sample floors:** at least **60 issuers** in a session for that
  session to contribute, and at least **500 contributing sessions** in the
  out-of-fold development series. Floors computable before outcome access are
  checked first. If either floor fails only after outcomes were read, the
  development slot is consumed under ACER-0A.9 and the program closes; it is
  not reclassified as a free pre-outcome refusal. In every case
  `insufficient` is distinct from `null` and never launches confirmation.
- **Confirmation model:** if and only if development passes, fit the same
  frozen control model once on the fully purged/embargoed development rows and
  apply it to confirmation controls. Confirmation outcomes never participate
  in fitting, normalization choices, feature selection, or parameter changes.

---

## ACER-0A.9 — execution-slot failure rules

Proposed, to remove the ambiguity the counter-review found:

1. A development or confirmation attempt that **refuses before touching
   outcomes** (a data, lineage, mapping, or pre-outcome floor refusal) does
   **not** consume its slot. It is still ledgered as an `R-nnn` look with its
   refusal reason. The future run driver must set a durable monotonic
   `outcomes_read` latch immediately before outcome I/O; a caller-supplied
   status or exception label cannot decide this after the fact.
2. An attempt that **reads outcomes and then errors** **does** consume its
   slot. Reading the data is the irreversible act, not producing a number.
3. A consumed slot is never replaced. If the development slot is consumed
   without a valid result, **ACER-2 ends** and the program closes; it does
   not fall through to the confirmation slot.
4. The confirmation run must independently clear the same frozen gate
   (primary cell, expected sign, corrected threshold, robustness rule) on the
   untouched period. It is a pass/fail replication, not a re-estimation, and
   no parameter may move between the two runs.

Rule 1 is the only one that could be abused — a "refusal" could be
manufactured to retry — so it is deliberately limited to refusals that occur
**before** any outcome is read, which is a checkable property of the code
path rather than a judgement about intent.

---

## What the owner is being asked to do

Accept, amend, or reject each of ACER-0A.5 through 0A.9. Once frozen, they
join the ACER-0A record and become unchangeable after a result is observed.
ACER-2 remains blocked regardless until ACER-0A.2, 0A.3, 0A.4 and 0A.10 also
close, which depends on the earnings audit and on the security-master ruling.
