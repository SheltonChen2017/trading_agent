# Strong-Buy portfolio test plan

Status: **DRAFT, independently reviewed and corrected 2026-08-19 — not yet
adopted or frozen.** Claude's proposed amendments SBPA-001..005 are preserved
in section 11 with their review dispositions. Every value below remains a
proposal until the owner adopts it; adoption freezes the document as written.

This is the proposed successor to the frozen SBR capture contract in
`docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md`.
It does not change that contract. It defines the missing portfolio test that
connects analyst ratings, inverse-volatility stock weights, ETF-holdings
overlap, and a deliberately small leveraged-ETF sleeve.

The separate LEV study in
`docs/research/LEVERAGED_THRESHOLD_2026-08-19_PREREGISTRATION.md` remains a
valid TQQQ timing experiment. It is **not** evidence for this complete
Strong-Buy strategy because it does not consume ratings, construct the stock
basket, inspect ETF holdings, or measure combined look-through exposure.

## 1. Question and honest boundary

The proposed strategy is:

1. identify every stock in the frozen candidate universe that meets a frozen
   definition of “Strong Buy”;
2. weight those stocks by inverse volatility;
3. prospectively identify which eligible ordinary ETF has the greatest
   weight-based overlap with that stock portfolio; and
4. add a capped position in that ETF's verified same-index leveraged version.

The test asks whether each added step improves the result after costs. It does
not assume that analyst labels predict returns, that low-volatility weighting
is automatically safer, or that leverage creates skill.

There is no honest historical shortcut. Current analyst ratings and current
ETF holdings cannot be applied to old prices. Only records captured before the
later return is known are admissible. QuantConnect may later replay committed
point-in-time custom data, but it cannot manufacture missing history.

## 2. Decisions proposed for owner adoption

The values below are proposals. They acquire authority only if the owner
adopts this plan before an admissible price-linked evaluation look.

| Decision | Proposed value |
|---|---|
| Candidate stocks | The 102-symbol list already frozen by SBR-1; constituent changes do not rewrite history |
| Strong-Buy eligibility | `total >= 10`; `strongBuy / total >= 0.50`; `(strongBuy + buy) / total >= 0.80`; `(sell + strongSell) / total <= 0.10` |
| Basket membership | Every candidate meeting all four rules; no discretionary additions, exclusions, or top-N tuning |
| Minimum basket size | 10 stocks; below 10 is a named monthly refusal, not permission to loosen a rule. This is the mathematical minimum under a 10% stock cap; with exactly 10 names, P1 and P2 are necessarily identical |
| Volatility window | Exactly 63 close-to-close daily returns from 64 consecutive completed exchange-session adjusted closes, ending before the decision cutoff |
| Stock-weight formula | `raw_i = 1 / sample_std(daily_return_i)`; normalize raw weights to 100% |
| Direct-stock cap | 10% per stock, enforced by iterative redistribution; an infeasible cap is a refusal |
| Rebalance cadence | Monthly; first admissible portfolio enters at the next trading session's close |
| No-trade band | 25% relative band around each target; positions outside the band move to target, and actual turnover is charged |
| Leveraged sleeve | 5% of portfolio value; the Strong-Buy stock core receives 95% |
| Minimum ETF overlap | **10%** of the Strong-Buy core by the weight-based definition in section 5. This is a proposed permissive policy floor against an almost unrelated match, not an empirically established quality threshold; the relative “highest overlap wins” rule does the selection work |
| Look-through issuer cap | 15%, including direct stock plus leveraged look-through exposure |
| Ordinary security cost | 10 basis points per traded side |
| Leveraged ETF cost | 25 basis points per traded side |
| Primary benchmark | QQQ; SPY remains a secondary descriptive benchmark |
| Minimum evidence | 24 matured monthly outcomes; 12 captures are an operational checkpoint, not evidence of profitability |
| Bootstrap contract | One-sided positive-mean stationary bootstrap; 20,000 draws; fixed mean block length 3 months; family threshold `0.05 / 3` |

If one of these choices is changed after any joined price outcome is seen, the
change is a new hypothesis with new look accounting. It cannot overwrite this
one.

## 3. Monthly information timeline

For each month:

1. SBR captures analyst counts at the frozen 17:15 ET cutoff on the first
   weekday and verifies the append-only file and manifest.
2. A separate holdings capture records eligible ETF holdings from official
   sponsor material. Each record binds the fund, holdings as-of date,
   retrieval timestamp, source location, exact raw bytes, and SHA-256.
3. The constructor also preserves the exact price-window input used for every
   selected stock, including provider, retrieval time, exchange-session list,
   adjustment convention, canonical bytes, and SHA-256. A later vendor query
   is not allowed to restate the historical weighting input.
4. The month refuses if any required source arrived after the cutoff, lacks its
   required identity, fails its hash, or uses information not known at the
   cutoff.
5. Only after the cutoff does the constructor use price history ending before
   the cutoff. Orders or shadow fills use the next trading session's close.
6. The portfolio remains in force until the next admissible monthly decision.

No same-close trade, backfilled capture, retry on a more favorable day, or
replacement for a missing selected stock is allowed.

## 4. Stock selection and inverse-volatility allocation

Counts must be finite, non-negative integers and must sum exactly to `total`.
Unavailable tickers remain in the capture record but cannot qualify. The four
eligibility conditions in section 2 are applied without rounding.

Every qualifying ticker is included. Ties therefore do not affect selection.
The output must record every pass/fail component so the result can be rebuilt
without prose interpretation.

For each selected ticker, compute exactly 63 close-to-close adjusted returns
from 64 consecutive completed exchange-session closes. A zero/non-finite
volatility, a missing session, or insufficient history refuses the entire
monthly basket; no
selected Strong-Buy stock is silently removed and no next stock is
substituted. Ratings-unavailable candidates are different: without a rating
they never pass the signal rule, while a selected ticker with a broken price
window has already passed and cannot be deleted without changing the tested
portfolio. After inverse-volatility normalization, repeatedly cap
weights above 10% and redistribute the remainder among uncapped stocks in
proportion to their raw inverse-volatility weights.

This is a risk allocation rule, not a profit forecast. It can concentrate the
portfolio in slowly moving but economically related stocks, which is why the
look-through cap remains mandatory.

## 5. ETF selection and leveraged mapping

Before the first holdings capture, freeze a small candidate table containing:

- the ordinary ETF ticker and official index;
- the leveraged ETF ticker, stated daily leverage, and official index;
- official issuer evidence that the two products track the same underlying
  index; and
- any frozen liquidity/fund-age eligibility rule.

Suggested pairs for a feasibility check are QQQ/TQQQ, XLK/TECL, and
SOXX/SOXL. They are **not approved pairs yet**. Their index correspondence,
product status, and source evidence must be verified from official issuer
documents before adoption. No pair may be added because it looks favorable
after a month's stock basket is known.

For ordinary ETF `e`, normalize its disclosed holdings to sum to one and
compute:

`overlap_e = sum_i min(strong_buy_core_weight_i, etf_holding_weight_e_i)`

over the union of stock symbols. This measures shared economic weight, not
just how many names appear in both lists. Also report name count and covered
core weight descriptively, but never use them to override the frozen score.

Select the eligible ETF with the largest overlap. Exact ties break by ordinary
ETF ticker in ascending order. If holdings are unavailable, more than 45
calendar days stale at the decision cutoff, the pair lacks verified
same-index evidence, or the best score is below the frozen **10%** floor, the
overlay is unavailable for that month. Never improvise a substitute.

### Pre-adoption structural probe status (2026-08-19 review)

Claude reported an exploratory probe with overlaps from 3.2% to 33.8% and
used it to propose changing the floor from 50% to 10%. The submitted commit
contains no executable probe, input artifact, source/as-of/retrieval identity,
price window, canonical bytes, or hashes. The numbers therefore cannot be
reproduced and are **not evidence**.

The reported 33.8% for an all-candidate basket is also not a mathematical
ceiling for a selected subset. Renormalizing a subset of high-index-weight
stocks can produce a larger overlap. The claim that 50% is unreachable was
therefore rejected. The proposed 10% remains only an owner-visible policy
choice: a permissive floor preventing an almost unrelated match. It is not an
empirically established threshold. Before SBP-0 adoption, a reproducible
feasibility artifact may report the distribution of overlap across declared
structural baskets, but it must use official point-in-time holdings, exact
captured price inputs, a declared basket generator, and complete hashes. It
must not use analyst outcomes, returns, or performance.

One limitation is valid without the rejected numbers: because QQQ covers the
frozen Nasdaq-100 candidate universe, simple name coverage is degenerate.
Weight overlap can still distinguish the broad fund from sector funds, so the
selection is not guaranteed to choose QQQ. A broader stock universe would be
a new preregistration, never a silent edit to SBR-1.

The leveraged fund is an overlay, not the whole portfolio. Because a leveraged
ETF commonly obtains exposure through derivatives, its literal holdings are
not a valid issuer look-through. The verified ordinary same-index ETF weights
are the frozen reference-index proxy. Proposed effective issuer exposure is:

- P3: `0.95 * core_weight_i + 0.05 * ordinary_etf_weight_i`
- P4: `0.95 * core_weight_i + 0.05 * stated_daily_leverage * ordinary_etf_weight_i`

If any issuer exceeds 15%, the affected overlay variant refuses for that
month. The system must not silently shrink the sleeve or optimize around the
cap. Both the ordinary holdings snapshot and same-index mapping must be valid
at the decision cutoff.

## 6. Portfolios and comparisons

The variants isolate one decision at a time:

| ID | Portfolio | What it tests |
|---|---|---|
| P0 | 100% QQQ | Primary benchmark |
| P1 | Equal-weight eligible Strong-Buy stocks | Whether the frozen ratings filter adds value |
| P2 | Inverse-volatility eligible Strong-Buy stocks | Whether inverse-volatility weighting improves on equal weight |
| P3 | 95% P2 + 5% selected ordinary ETF | Whether the overlap-selected fund adds value without leverage |
| P4 | 95% P2 + 5% verified leveraged counterpart | Whether leverage adds value beyond the same ordinary-fund overlay |

The frozen paired comparisons are **P1−P0, P2−P1, and P3−P2 — three
inferential cells**. **P4−P3 is descriptive only**, with no p-value or edge
claim. Its principal difference is intentional incremental index beta, so a
positive mean would not establish a new selection alpha. The earlier
35–40%-annual-return assertion had no preserved calculation or assumptions and
is withdrawn. P4 still reports CAGR, drawdown, capture ratios, turnover, and
look-through exposure beside P3; the separate LEV family addresses threshold
timing on historical TQQQ data without validating this Strong-Buy strategy.

P0–P2 form the core block. P2–P4 form the overlay block and use only dates on
which all three overlay-block portfolios are available. This preserves aligned
comparisons without discarding valid core observations when ETF evidence is
missing.

The current LEV threshold-exit rules are not added to P4 in this test. Doing
so would change stock selection, weighting, ETF choice, leverage, and exit
timing at once. Threshold exits may become a later P5 family only after the
base overlay is measured under its own fresh preregistration.

## 7. Costs, metrics, and claims

Turnover is measured from the drifted pre-trade weights to the executed
post-trade weights, including entry and exit legs. Apply the frozen per-side
costs to actual turnover. Missing turnover refuses the affected row; it never
becomes zero. Taxes are a labeled descriptive scenario only and cannot decide
the primary result.

Report CAGR, annualized volatility, Sharpe, maximum drawdown, time under
water, recovery time, worst month, turnover, beta, and upside/downside capture.
These are descriptive unless a test is explicitly frozen below.

For the **three** frozen paired monthly excess-return series (P1−P0, P2−P1,
P3−P2), use the one-sided positive-mean stationary bootstrap frozen in section
2: 20,000 draws, mean block length 3 months, and family-wise threshold
**`0.05 / 3 = 0.0167`**. The primary claim requires positive after-cost mean
excess return at that threshold. A nicer Sharpe, smaller drawdown, positive
CAGR, or win against SPY alone is not proof of selection edge.

Twenty-four monthly observations is a minimum horizon, not a promise of
adequate power. Claude's submitted “0.6%/month” calculation assumed an
unverified 1.2% tracking error, independence, and a two-sided critical value
while the proposed test is one-sided; it described an approximate rejection
boundary, not statistical power. It is withdrawn. Before adoption, SBP-0 must
record a sensitivity table over declared tracking errors and dependence
assumptions, including an 80%-power minimum-detectable effect. That table is
planning context only and cannot turn 24 observations into sufficient
evidence.

The interpretation is fixed in advance: **a null result at 24 months means
the frozen test did not establish an edge; it does not prove that the true
effect is zero.** It closes this frozen family and authorizes no threshold
tuning or post-result extension. A longer horizon may be frozen before the
first outcome look. After outcomes are scored, any extension is a new
preregistration and cannot present the already-scored months as fresh
confirmation. Descriptive decomposition remains useful but non-confirmatory.

## 8. Evidence, refusal, and look accounting

- Freeze this complete contract before using any captured month in a
  price-linked evaluation.
- **Proposed supersession (SBPA-005):** only on explicit owner adoption, SBP-0
  **replaces the SBR-2 step**
  of `docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md`,
  which had deferred the evaluation preregistration until "after ≥12
  snapshots". Freezing the evaluation contract BEFORE the first capture is
  strictly more conservative and removes any chance of choosing rules from
  data already in hand. The capture contract itself is unchanged; only the
  location and timing of the evaluation freeze move here. Both documents must
  say so, so no future reader finds two contradictory authorities.
- The repository records SBR-1 as not installed and contains no committed
  snapshot. SBP-0 must verify the machine-local stream count before adoption;
  it must not assume that zero snapshots exist merely from repository state.
- If SBR snapshots predate adoption of this plan, label them calibration-only
  and exclude them from confirmatory outcomes. Do not choose thresholds from
  them and then score those same months.
- Preserve every capture and result append-only. A corrected result receives a
  new identity and an explicit supersession link.
- Record source commit, config hash, capture hashes, constructor version,
  decision timestamp, intended/actual fill timestamp, refusal reason, and
  portfolio weights for every month.
- A counts-only integrity or sufficiency check is not an outcome look. Joining
  to future prices, returns, rankings, or portfolio performance is a look and
  must be ledgered.
- One owner-authorized analysis pass is permitted after the minimum floor and
  review gates are satisfied. It closes the family whether positive or null.

Named refusal classes must cover at least: incomplete rating record, too few
eligible stocks, incomplete price window, non-finite volatility, infeasible
stock cap, missing/stale holdings, unverified ETF mapping, insufficient ETF
overlap, look-through cap breach, unaligned outcome, non-finite result, and
provenance/hash mismatch.

## 9. Implementation stages and gates

### SBP-0 — adopt and freeze

- Owner decides every row in section 2.
- Official-source verification freezes the eligible ETF pair table.
- A reproducible structural-feasibility artifact, if used, binds its declared
  baskets, exact point-in-time holdings and price inputs, source timestamps,
  canonical bytes, code identity, and hashes. Its output cannot silently tune
  a threshold.
- Record the power-sensitivity table required by section 7 and decide whether
  24 months remains the fixed first-and-only analysis horizon.
- Verify the machine-local SBR stream count and classify every pre-adoption
  snapshot, if any, before stating that all future months are confirmatory.
- Independent review confirms this plan was frozen before an admissible
  price-linked look.

Definition of done: every proposed value and planning assumption is closed;
adopted status and exact source/config/artifact hashes are recorded in the
Action Plan and Session Handoff. No cloud run or outcome analysis is part of
SBP-0.

### SBP-1 — prospective data capture

- Complete the already reviewed SBR-1 owner-present task install and verify its
  first real firing.
- Add a separate, task-specific official ETF-holdings capture with append-only
  manifests, refusal tests, and no price evaluation imports.
- Independent review and counter-review precede installation.

Definition of done: both streams fire under the intended account, preserve
exact evidence, and fail closed. No performance result exists.

### SBP-2 — pure portfolio constructor

- Implement selection, inverse-volatility caps, overlap scoring, mapping,
  look-through checks, bands, turnover, and P0–P4 construction as pure,
  deterministic functions.
- Add composition-level tests using the real capture schemas, exact exchange
  sessions, missing-data refusals, and reverse mutations.
- Do not add broker or automatic-order authority.

Definition of done: an independently reviewed constructor emits reproducible
weights or a named refusal from frozen fixtures.

### SBP-3 — prospective shadow and optional paper execution

- Start monthly shadow decisions from the first post-freeze admissible capture.
- An optional Alpaca Paper pilot may verify order sizing, fractional-share
  handling, bands, fills, and slippage after a separate owner decision.
- Paper results test execution, not the existence of alpha. Initial paper
  operation remains proposal/approval based; this plan grants no auto-trading
  authority.

Definition of done: each scheduled decision has a complete evidence chain and
the paper account, if used, remains operationally isolated.

### SBP-4 — one frozen analysis

- After at least 24 matured monthly outcomes, run a counts-only sufficiency
  check.
- Independent review verifies identities, alignment, costs, and look counts
  before the owner authorizes the single analysis pass.
- Run the frozen analysis once, record all three inferential cells plus the P4
  descriptive comparison, and close the family.

Definition of done: every result is VALID, INVALID, or REFUSED with immutable
provenance; no follow-on tuning is implied.

### SBP-5 — deployment decision, if any

Any move beyond reviewed Alpaca Paper evidence is a separate milestone with a
new owner decision, risk review, release epoch, and explicit execution gates.
This research plan never grants live-trading authority.

## 10. Timeline

**So it is not a surprise:** this is a two-year instrument. There is
no admissible historical shortcut — applying today's ratings to old prices is
the same look-ahead that closed the Stage 2 PEAD idea. Adopt now → captures
install within weeks → first admissible monthly decision immediately after →
24 matured outcomes roughly two years later → one analysis pass, then the
family closes. The start remains gated on owner adoption, reviewed capture
code, owner-present installation, and first-firing verification; the timeline
does not itself argue for skipping or accelerating a gate.

## 11. Amendment log (2026-08-19, pre-adoption)

| ID | Amendment | Why |
|---|---|---|
| SBPA-001 | **PARTIALLY ACCEPTED, CORRECTED.** Proposed floor 50% → 10%; structural-probe section added | Scrutinizing the floor was correct, but 33.8% was not a ceiling and none of the probe inputs/code was preserved. The numbers are rejected as evidence; 10% remains a disclosed policy proposal pending owner adoption |
| SBPA-002 | **REJECTED.** Proposed ticker-level price exclusion | It deletes a stock after the signal selected it, contradicts “every qualifying ticker,” and creates a selective basket. Whole-month refusal is restored |
| SBPA-003 | **PARTIALLY ACCEPTED, CORRECTED.** P4−P3 descriptive; family has three inferential cells | The beta/claim classification is sound. The unsupported 35–40% assertion is withdrawn and the look-through formula is corrected |
| SBPA-004 | **REJECTED AS POWER EVIDENCE, REPLACED.** Submitted 0.6%/month statement | It mixed unsupported variance/independence assumptions, test sidedness, and a rejection boundary. A pre-adoption sensitivity table is now required; the null interpretation is retained accurately |
| SBPA-005 | **CONDITIONALLY ACCEPTED.** SBP-0 may supersede SBR-2 | It becomes true only upon explicit owner adoption and verified stream state. The already frozen SBR capture contract is not edited prospectively |

**Relationship to LEV (unchanged in substance, stated explicitly):** the LEV
family is SECONDARY to this plan — a frozen historical TQQQ timing experiment
that answers the leverage-and-exit half quickly, on real history. It is not
evidence for this strategy, and this plan does not consume it.

## 12. Plain-language summary

First, make a strict rule for what “Strong Buy” means and keep every stock that
passes it. Put less money into stocks that jump around more and more money into
stocks that move less, but never let one stock become too large. Next, compare
that basket with a small, pre-approved list of funds and choose the fund whose
actual holdings overlap the basket the most. Put only a small part of the
portfolio into the matching leveraged fund.

Then compare each step separately. A failed frozen test means that step did
not establish an improvement; it does not prove the true effect is exactly
zero. The leveraged ETF comparison is descriptive: it shows how much extra
return, drawdown, and concentration came with extra market exposure, but it
does not claim a new alpha. This keeps one exciting-looking result from hiding
which part actually worked.
