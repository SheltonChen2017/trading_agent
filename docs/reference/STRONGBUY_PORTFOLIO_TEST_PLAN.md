# Strong-Buy portfolio test plan

Status: **DRAFT, AMENDED 2026-08-19 — ready for owner adoption, not yet
frozen.** Amendments SBPA-001..005 (section 11) followed a counter-review
of the original Codex draft and a declared structural feasibility check.
Every value below is a proposal until the owner adopts it; adoption
freezes the document as written.

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
| Minimum ETF overlap | **10%** of the Strong-Buy core by the weight-based definition in section 5 (amended from 50%: the feasibility check in section 5 measured a hard ceiling of 33.8% and a realistic 7–18%; 50% would have refused the overlay every month forever). The threshold is a floor against a degenerate match, NOT a quality bar — the relative "highest overlap wins" rule does the selection work |
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
63 completed exchange sessions. **Amended (SBPA-002):** a zero/non-finite
volatility, a missing session, or insufficient history **disqualifies that
ticker**, with the reason recorded in the monthly output, exactly as a
ratings-unavailable ticker is disqualified. No next stock is substituted —
the basket simply does not contain it — and the MONTH refuses only if the
surviving basket falls below the 8-stock minimum.

The original rule refused the whole month on any single bad price window.
With ~102 candidates that fires often, and every refused month is
permanently lost from a 24-month evidence budget; it also treated two
identical situations (a ticker whose data is unusable) inconsistently
depending on which source was missing. Disqualification is recorded, never
silent, so the selective-sample risk is visible in the record. After inverse-volatility normalization, repeatedly cap
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

### Declared structural feasibility check (2026-08-19, SBPA-001)

Run BEFORE freezing the threshold, and declared here so it is auditable.
Scope: basket weights built exactly as sections 4–5 specify, overlapped
against a **market-cap-weight proxy** for QQQ's holdings (QQQ is a modified
cap-weighted NDX-100 fund; the frozen contract still requires official
sponsor material at capture time). **No returns, no benchmark comparison,
and no portfolio performance were computed** — this is a structural quantity,
so it is not a price-linked outcome look under section 8. It cannot bias the
result toward "positive": it only decides whether the overlay can ever be
available.

Measured weight overlap `Σ min(core_i, etf_i)`:

| Basket | n | Overlap | Covered core weight |
|---|---:|---:|---:|
| All usable candidates | 100 | **33.8%** | 100% |
| Lowest-vol 30 | 30 | 11.2% | 100% |
| Lowest-vol 20 | 20 | 6.9% | 100% |
| Lowest-vol 12 | 12 | 3.2% | 100% |
| Highest-vol 20 | 20 | 11.6% | 100% |
| Mixed 20 (every 5th by vol) | 20 | 18.1% | 100% |

Two findings, both design-relevant:

1. **The 50% threshold was unreachable.** Even holding every candidate,
   overlap tops out at 33.8%; a realistic 20–30 name basket scores 7–18%.
   Inverse-volatility weighting and cap-weighted ETF holdings are
   structurally opposed — the low-volatility names that earn the largest
   basket weights (PEP, KDP, MDLZ, ADP, XEL…) carry roughly half a percent
   each in the fund, while the mega-caps that dominate it (NVDA ~11.6%,
   AAPL ~10.2%, GOOGL+GOOG ~18.4%, MSFT ~7.9% on the proxy) are mid-to-high
   volatility and get small basket weights. P3/P4 would have refused every
   month while the study still "completed".
2. **Covered core weight cannot be the gate either, and the ETF-selection
   step is partly degenerate.** Because the candidate universe IS one
   index's membership, any index fund over that universe covers 100% of the
   basket by construction. "Which ETF holds the most of my picks" only
   becomes a real question when the candidate ETFs cover *different subsets*
   — which is why the candidate table must contain genuine competitors
   (a broad fund plus sector funds), and why the selection is expected to
   resolve to the broad fund in most months. **Recorded limitation:** with
   the frozen NDX-102 candidate universe, P3/P4 substantially measure
   "add 5% of a broad Nasdaq fund (or its 3x)", not a discovered match.
   Making the ETF-selection step genuinely informative requires a broader
   candidate universe, which is a different frozen universe and therefore a
   NEW preregistration — never a silent edit to the SBR capture contract.

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

**Amended (SBPA-003):** the frozen paired comparisons are **P1−P0, P2−P1,
and P3−P2 — three cells**. **P4−P3 is DESCRIPTIVE ONLY**, with no p-value
and no claim. Reason, decided now while no data exists: P4−P3 differs from
P3−P2 by a 5% sleeve at 3x versus 5% at 1x, i.e. about 10% incremental index
exposure. Its excess series is almost entirely market beta, and clearing a
family-wise threshold on 24 months would require the index to compound at
roughly 35–40% annually — in which case the cell would be measuring the
market, not the strategy. Reporting it as a test would invite exactly the
beta-as-edge misreading that closed Stage 0/1. The leverage question is still
answered descriptively (P4's CAGR, drawdown, capture ratios, and after-cost
turnover beside P3's), and the LEV family answers the timing half on real
historical data.

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
P3−P2), use a stationary bootstrap with 20,000 draws and family-wise
threshold **`0.05 / 3 = 0.0167`**. The primary claim requires positive
after-cost mean excess return at that threshold. A nicer Sharpe, smaller
drawdown, positive CAGR, or win against SPY alone is not proof of selection
edge.

**Declared power, frozen before any data (SBPA-004).** Twenty-four monthly
observations is a floor, not a sufficient sample. For a plausible monthly
tracking error of about 1.2% on P1−P0, the standard error of the mean is
roughly 0.25%/month, so clearing the two-sided family threshold requires an
after-cost edge near **0.6%/month — about 7–8% annually**. Effects smaller
than that are undetectable here no matter how real they are.

Therefore the interpretation is fixed in advance: **a null result at 24
months means "no edge large enough to see", NOT "no edge".** It closes this
frozen family and authorizes no threshold tuning, no extra months bolted on
to chase significance, and no re-scoring. Continuing collection beyond 24
months to gain power is legitimate ONLY as a new preregistration that fixes
its own horizon in advance and does not re-use these months' already-scored
outcomes. The descriptive decomposition (which step helped, and by how much,
with what drawdown and turnover) is the durable product of this study and
does not depend on the gate.

## 8. Evidence, refusal, and look accounting

- Freeze this complete contract before using any captured month in a
  price-linked evaluation.
- **Supersession (SBPA-005):** on adoption, SBP-0 **replaces the SBR-2 step**
  of `docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md`,
  which had deferred the evaluation preregistration until "after ≥12
  snapshots". Freezing the evaluation contract BEFORE the first capture is
  strictly more conservative and removes any chance of choosing rules from
  data already in hand. The capture contract itself is unchanged; only the
  location and timing of the evaluation freeze move here. Both documents must
  say so, so no future reader finds two contradictory authorities.
- At adoption there are **zero captured snapshots** (SBR-1 is implemented but
  not installed), so no month is calibration-contaminated and every future
  outcome is confirmatory.
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

## 10. Timeline

**So it is not a surprise:** this is a two-year instrument. There is
no admissible historical shortcut — applying today's ratings to old prices is
the same look-ahead that closed the Stage 2 PEAD idea. Adopt now → captures
install within weeks → first admissible monthly decision immediately after →
24 matured outcomes roughly two years later → one analysis pass, then the
family closes. That argues for starting at once and for keeping the LEV study
running as the fast side-channel, not for cutting corners here.

## 11. Amendment log (2026-08-19, pre-adoption)

| ID | Amendment | Why |
|---|---|---|
| SBPA-001 | Minimum ETF overlap 50% → 10%; declared structural feasibility check added to section 5 | Measured ceiling is 33.8% and realistic baskets score 7–18%; the original threshold would have refused the overlay every month while the study still reported as complete. The check also exposed the recorded degeneracy limitation in the ETF-selection step |
| SBPA-002 | An unusable price window disqualifies THAT TICKER, not the whole month; the month refuses only below the 8-stock floor | The original rule was inconsistent with the ratings-unavailable path and would burn irreplaceable months from a 24-month budget |
| SBPA-003 | P4−P3 becomes DESCRIPTIVE ONLY; frozen family is three cells at 0.05/3 | The cell is ~10% incremental index beta; a "pass" would require the index to compound near 35–40% annually and would measure the market, not the strategy |
| SBPA-004 | Declared power arithmetic and the fixed interpretation of a null | 24 months detects only a ~0.6%/month edge; the meaning of a null must be fixed before the data, not argued after it |
| SBPA-005 | SBP-0 supersedes the SBR-2 evaluation step; zero snapshots exist at adoption | Removes contradictory authorities and records that every future outcome is confirmatory |

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

Then compare each step separately. If the equal-weight stocks cannot beat QQQ,
the ratings filter did not help. If inverse volatility cannot beat equal
weight, the sizing rule did not help. If the ordinary ETF cannot improve the
stock basket, the overlap idea did not help. If the leveraged ETF cannot beat
the ordinary ETF after extra costs and risk, leverage did not help. This keeps
one exciting-looking result from hiding which part actually worked.
