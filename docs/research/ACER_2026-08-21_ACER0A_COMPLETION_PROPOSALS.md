# ACER-0A completion proposals (ACER-0A.5–0A.9)

Status: **PROPOSALS AWAITING OWNER CONFIRMATION. Nothing here is frozen.**
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

---

## ACER-0A.5 — canonical rating scale

### Measured vocabulary

The corpus contains **54 distinct rating strings** (53 as current ratings, 47
as previous). Coverage is extremely concentrated: the top 19 strings account
for **99.57%** of the 584,916 events, and the 34 strings below 500 events
together account for 2,530 events (0.43%).

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
level. The explicitly unmappable strings measured in the corpus are `mixed`,
`fair value`, `not rated`, and `tender`: they express no position on an
ordinal buy-to-sell axis. Defaulting an unknown string to 3 (hold) would
manufacture a zero-notch observation out of missing information and quietly
dilute the signal toward zero; refusing keeps the sample honest and the
refusal counted.

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
- **Per-firm state.** Each (issuer, firm) pair carries at most one live
  rating. A new action from that firm replaces its previous state. This makes
  the aggregate a genuine consensus rather than a sum over duplicate opinions.
- **Decay.** An action's weight at session *t* is `exp(-ln(2) * age / H)`
  where `age` is the number of **trading sessions** since the action became
  eligible and `H` is the frozen half-life (21, 63, or 126). Age is counted in
  sessions, not calendar days, so the decay does not accelerate across
  weekends and holidays.
- **Aggregation (the frozen coverage-neutral per-firm mean).** For issuer *i*
  at session *t*, the score is the decay-weighted mean over that issuer's
  live per-firm actions: `sum(w * notch) / sum(w)`. Dividing by the weight
  sum is what makes it coverage-neutral — an issuer with forty analysts and
  one with four are on the same scale.
- **Minimum coverage.** An issuer needs at least **3** live firm actions
  within the trailing `2 * H` sessions to receive a score; below that the
  issuer is refused for that session rather than scored from one opinion.
  This threshold is a proposal and is deliberately not tuned.
- **Encoding (b) does not depend on the scale.** Direction-only sign is taken
  from `rating_action` — `upgrades` → +1, `downgrades` → −1, everything else
  → 0 — measured directly from the vendor's own action field. This makes
  encoding (b) implementable independently of ACER-0A.5, and gives the family
  one member immune to the cardinality assumption above.
- **Same-session collisions.** If one firm issues two actions on the same
  issuer with the same eligibility session, both are refused rather than
  arbitrarily ordered: same-day vendor ordering does not establish
  chronology, a fact already measured in the identity work.

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
- **Residualization.** At each session, regress the outcome on the controls
  cross-sectionally by ordinary least squares and take the residual. The
  primary statistic is the cross-sectional **Spearman** correlation between
  the signal and that residual, averaged across sessions. Spearman rather
  than Pearson because the notch encoding is ordinal with heavy mass at zero,
  where a Pearson coefficient would be dominated by a few large moves.
- **Missing controls refuse the row.** An issuer missing any required control
  for a session is refused for that session and the refusal is counted. No
  control is ever imputed, carried forward, or replaced with a
  cross-sectional mean.

---

## ACER-0A.8 — estimation and significance protocol

- **Development period:** 2012-01-01 through 2021-12-31.
  **Untouched confirmation period:** 2022-01-01 through the corpus end. The
  confirmation period is not inspected, plotted, or summarized before the
  single confirmation pass.
- **Walk-forward:** expanding-window folds with a minimum 3-year initial
  training window, stepping annually, within the development period only.
- **Purge and embargo:** because the 21-session outcome overlaps, each fold's
  training data is purged of observations whose outcome window overlaps the
  test window, with an additional **21-session embargo** after the test
  window. Overlapping observations are the reason a naive test would produce
  a spurious p-value.
- **Independent observation unit: the session**, not the issuer-row. Rows
  within one session share market-wide shocks and are not independent.
- **Significance:** stationary block bootstrap over sessions using this
  repository's existing out-of-sample block toolkit, with **expected block
  length 21 sessions** (matched to the outcome horizon), **10,000 draws**,
  **seed 20260821**, and a **two-sided** test. Seed and draw count are frozen
  here so the p-value is reproducible.
- **Finite-sample floors:** at least **60 issuers** in a session for that
  session to contribute, and at least **500 contributing sessions** in the
  development period. Below either floor the result is **insufficient**, which
  is a distinct outcome from a null and does not consume the confirmation
  slot.

---

## ACER-0A.9 — execution-slot failure rules

Proposed, to remove the ambiguity the counter-review found:

1. A development or confirmation attempt that **refuses before touching
   outcomes** (a data, lineage, or floor refusal) does **not** consume its
   slot. It is still ledgered as an `R-nnn` look with its refusal reason.
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
