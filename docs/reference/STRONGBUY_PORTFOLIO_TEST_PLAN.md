# Strong-Buy portfolio test plan

Status: **DRAFT — owner-requested revision, not yet adopted or frozen.**

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
| Minimum basket size | 8 stocks; below 8 is a named monthly refusal, not permission to loosen a rule |
| Volatility window | 63 completed trading sessions of adjusted daily closes, ending before the decision cutoff |
| Stock-weight formula | `raw_i = 1 / sample_std(daily_return_i)`; normalize raw weights to 100% |
| Direct-stock cap | 10% per stock, enforced by iterative redistribution; an infeasible cap is a refusal |
| Rebalance cadence | Monthly; first admissible portfolio enters at the next trading session's close |
| No-trade band | 25% relative band around each target; positions outside the band move to target, and actual turnover is charged |
| Leveraged sleeve | 5% of portfolio value; the Strong-Buy stock core receives 95% |
| Minimum ETF overlap | 50% of the Strong-Buy core by the weight-based definition in section 5 |
| Look-through issuer cap | 15%, including direct stock plus leveraged look-through exposure |
| Ordinary security cost | 10 basis points per traded side |
| Leveraged ETF cost | 25 basis points per traded side |
| Primary benchmark | QQQ; SPY remains a secondary descriptive benchmark |
| Minimum evidence | 24 matured monthly outcomes; 12 captures are an operational checkpoint, not evidence of profitability |

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
3. The month refuses if either source arrived after the cutoff, lacks its
   required identity, fails its hash, or uses information not known at the
   cutoff.
4. Only after the cutoff does the constructor use price history ending before
   the cutoff. Orders or shadow fills use the next trading session's close.
5. The portfolio remains in force until the next admissible monthly decision.

No same-close trade, backfilled capture, retry on a more favorable day, or
replacement for a missing selected stock is allowed.

## 4. Stock selection and inverse-volatility allocation

Counts must be finite, non-negative integers and must sum exactly to `total`.
Unavailable tickers remain in the capture record but cannot qualify. The four
eligibility conditions in section 2 are applied without rounding.

Every qualifying ticker is included. Ties therefore do not affect selection.
The output must record every pass/fail component so the result can be rebuilt
without prose interpretation.

For each selected ticker, compute close-to-close adjusted returns from exactly
63 completed exchange sessions. A zero/non-finite volatility, a missing
session, or insufficient history refuses the entire monthly basket; no next
stock is substituted. After inverse-volatility normalization, repeatedly cap
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
same-index evidence, or the best score is below 50%, the overlay is
unavailable for that month. Never improvise a substitute.

The leveraged fund is an overlay, not the whole portfolio. Proposed effective
issuer exposure is:

`direct_weight_i + leveraged_sleeve_weight * stated_daily_leverage * leveraged_fund_holding_weight_i`

If any issuer exceeds 15%, the leveraged variant refuses for that month. The
system must not silently shrink the sleeve or optimize around the cap.

## 6. Portfolios and comparisons

The variants isolate one decision at a time:

| ID | Portfolio | What it tests |
|---|---|---|
| P0 | 100% QQQ | Primary benchmark |
| P1 | Equal-weight eligible Strong-Buy stocks | Whether the frozen ratings filter adds value |
| P2 | Inverse-volatility eligible Strong-Buy stocks | Whether inverse-volatility weighting improves on equal weight |
| P3 | 95% P2 + 5% selected ordinary ETF | Whether the overlap-selected fund adds value without leverage |
| P4 | 95% P2 + 5% verified leveraged counterpart | Whether leverage adds value beyond the same ordinary-fund overlay |

The primary paired comparisons are P1−P0, P2−P1, P3−P2, and P4−P3. P0–P2
form the core block. P2–P4 form the overlay block and use only dates on which
all three overlay-block portfolios are available. This preserves aligned
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

For the four primary paired monthly excess-return series, use a stationary
bootstrap with 20,000 draws and family-wise threshold `0.05 / 4 = 0.0125`.
The primary claim requires positive after-cost mean excess return at that
threshold. A nicer Sharpe, smaller drawdown, positive CAGR, or win against SPY
alone is not proof of selection edge.

Twenty-four months is only a minimum observation floor and may still have low
power. A null result closes this frozen family; it does not authorize threshold
tuning. A positive historical/prospective result still does not promise
profit.

## 8. Evidence, refusal, and look accounting

- Freeze this complete contract before using any captured month in a
  price-linked evaluation.
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
- Independent review confirms this plan was frozen before an admissible
  price-linked look.

Definition of done: adopted status and exact source/config hashes are recorded
in the Action Plan and Session Handoff. No code or cloud run is part of SBP-0.

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
- Run the frozen analysis once, record all four cells, and close the family.

Definition of done: every result is VALID, INVALID, or REFUSED with immutable
provenance; no follow-on tuning is implied.

### SBP-5 — deployment decision, if any

Any move beyond reviewed Alpaca Paper evidence is a separate milestone with a
new owner decision, risk review, release epoch, and explicit execution gates.
This research plan never grants live-trading authority.

## 10. Plain-language summary

First, make a strict rule for what “Strong Buy” means and keep every stock that
passes it. Put less money into stocks that jump around more and more money into
stocks that move less, but never let one stock become too large. Next, compare
that basket with a small, pre-approved list of funds and choose the fund whose
actual holdings overlap the basket the most. Put only a small part of the
portfolio into the matching leveraged fund.

Then compare each step separately. If the equal-weight stocks cannot beat QQQ,
the ratings filter did not help. If inverse volatility cannot beat equal
weight, the sizing rule did not help. If the ordinary ETF cannot improve the
stock basket, the overlap idea did not help. If the leveraged ETF cannot beat
the ordinary ETF after extra costs and risk, leverage did not help. This keeps
one exciting-looking result from hiding which part actually worked.
