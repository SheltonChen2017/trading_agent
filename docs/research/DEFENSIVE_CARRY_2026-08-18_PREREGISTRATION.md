# Defensive-Carry Overlay — Preregistration (FROZEN 2026-08-19)

Status: **FROZEN in this commit, 2026-08-19, by owner adoption**
("yes accept as is") — before any confirmation computation, any shadow
stream registration, and any statistic. Every draft placeholder is
frozen at its proposed value. Changing any frozen weight, window,
threshold, or count after this commit requires a NEW named
preregistration; the SHW-4 registration binds this document's SHA-256
as of this commit.

## 1. Honest look accounting (why this is confirmation, not discovery)

The 2026-07-31 exploratory probe (`scripts/run_defensive_carry_probe.py`)
already observed one full-window result on this question: static
TLT/IEF/SHY/GLD overlays at 10/20/30% on an equal-weight UNIVERSE blend,
single lookback, no out-of-sample split. **That was discovery look #1
and it is counted.** Everything below is designed so the confirmation
evidence is structurally distinct: walk-forward folds, block-aware
significance, and — for the decisive evidence — the prospective shadow
stream (SHW-4 in `docs/reference/SHADOW_OBSERVATION_DESIGN.md`).

This is NOT a reopening of the closed cross-sectional alpha program
(ledger A-002): no stock selection, no ranking, no signal. It is an
allocation/risk question about a static overlay, the family where this
project's confirmed results live.

## 2. Hypothesis and endpoints

**H1 (primary):** adding a fixed-weight defensive-carry basket
(equal-weight TLT/IEF/SHY/GLD) to the equal-weight UNIVERSE blend
reduces tail risk at an acceptable upside cost, specifically:

- PRIMARY CELL: 20% carry weight (the middle candidate; chosen now,
  before confirmation, to avoid weight-shopping).
- PRIMARY METRIC (composite, all three must hold in confirmation):
  1. maximum drawdown improves vs the UNIVERSE-only blend by at least
     **15% relative reduction** (FROZEN 2026-08-19);
  2. 95% expected shortfall (monthly) improves by at least
     **10% relative** (FROZEN 2026-08-19); and
  3. upside capture vs SPY stays at or above
     **80% of the UNIVERSE-only blend's** (FROZEN 2026-08-19).
- SECONDARY (descriptive only, no gate): 10% and 30% weights, Sortino,
  time-under-water, downside capture. Reported, never promoted.

**Multiplicity declaration:** one primary cell, one composite gate =
ONE counted hypothesis. The two secondary weights are descriptive; if
either is ever promoted to a gated claim, that is a NEW preregistration
and a new counted look. Lifetime research-look ledger continues from
its current floor (452 cells / 29 runs as of A-002); this study adds
its looks there when executed.

## 3. Method (retrospective confirmation leg)

- Data: the existing pinned daily sources; carry tickers and UNIVERSE
  members sliced at decision cutoffs; survivorship caveat of UNIVERSE
  (documented in the ledger) restated in the report.
- Structure: calendar-year walk-forward folds across the full common
  history, **at least 8 folds** (FROZEN 2026-08-19; fewer available
  folds refuse the study as underpowered rather than running short);
  the overlay is static, so
  folds test regime robustness, not parameter fitting. Rebalancing to
  target weights uses the operational wide-band mechanism (25% band)
  so the tested object matches what deployment would actually do.
- Significance: downside-metric deltas evaluated with the project's
  block bootstrap (`out_of_sample_significance_by_block`, block lengths
  5/10/15 days) — never pooled row-level tests; fold-level sign
  consistency reported (**gate, FROZEN 2026-08-19: improvement in at
  least 2/3 of folds AND block-bootstrap p < 0.05 on the ES delta**).
- Refusals and data gaps recorded, never dropped.

## 4. Prospective leg (the decisive one)

On adoption, the overlay registers as a shadow stream (SHW-4): monthly
observation of the hypothetical blend vs the UNIVERSE-only blend,
**24 required independent months minimum (FROZEN 2026-08-19;
`required_observation_count=24` at SHW-4 registration)** — stated
plainly: 24 monthly observations resolve only large tail-risk
differences; the retrospective leg carries the statistical weight and
the prospective leg tests operational reality and calibration. Sufficiency reporting per the §6 fields; no gate is
evaluated before the required count exists.

## 5. What success and failure mean (bound in advance)

- **Confirmation passes both legs:** the overlay becomes a candidate
  for the owner's allocation decision on the PAPER account — a
  proposal-pipeline change with its own milestone, review, and explicit
  owner approval. Nothing auto-deploys, nothing touches live.
- **Confirmation fails either leg:** the overlay is recorded as
  refuted-at-these-gates in the ledger and is not re-tuned. Weight
  shopping, basket swaps, or gate softening after seeing results are
  prohibited; any variant is a new preregistration with its look
  counted.

## 6. Freeze record (2026-08-19)

Every draft placeholder is frozen above at its proposed value, by
owner adoption ("yes accept as is"), in this commit — which precedes
the first confirmation computation, the shadow stream registration,
and every statistic. Remaining to fix mechanically at study start: the
exact retrospective window end-date and the fold boundaries derived
from it (calendar consequences, not tunables). The study's analysis
script must refuse to run unless this document's SHA-256 matches the
one recorded at registration.
