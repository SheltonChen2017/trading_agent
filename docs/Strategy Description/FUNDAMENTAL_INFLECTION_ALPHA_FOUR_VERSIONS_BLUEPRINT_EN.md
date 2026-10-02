# Fundamental Inflection Alpha

## Four strategy versions - research blueprint v1.0

**Prepared 2026-09-14. Status: design candidate, independently unreviewed.**

This blueprint turns the owner's small-cap growth, valuation, profitability,
cash-flow and catalyst screen into four deterministic investment research
strategies. It follows the existing Analyst Revisions, Insider Buying and Short
Interest blueprints: stock evidence first, point-in-time aggregation, investable
portfolios, costs, independent validation and bounded implementation stages.

The owner initially selected 15% / 25% / 20% / 30% maximum drawdowns, then
expressly permitted higher drawdowns for riskier versions, especially those
using leverage. The revised proposed limits are **15% / 35% / 25% / 40%**
for V1 / V2 / V3 / V4. The later permission is recorded; the revised exact
numbers are design assumptions, not a claim that the owner chose those numbers.
Numerical settings below are research parameters, not observed market facts,
expected returns or approved freezes.
There are no backtest results in this document. Outperformance remains a
rejection-capable hypothesis. No target prices or current trade list are given.

The editable Markdown is the design source; the companion PDF is its reading
edition. Any future conflict must be corrected before adopting a specification.
Neither artifact is an executable authorization or an independently accepted
research contract.

## 1. Decision summary

| Version | Investable expression | Maximum equity gross / NAV | Volatility target | Maximum drawdown accepted | Required net economic improvement |
|---|---|---:|---:|---:|---|
| V1 - Balanced ETF rotation | Ordinary equity ETFs plus cash | 1.00x | 10% annualized | 15% | SPY CAGR +3 percentage points |
| V2 - Leveraged ETF rotation | The same ETF selection, portfolio margin borrowing | 1.75x | 18% annualized | 35% | Both SSO and QLD CAGR +3 points |
| V3 - Direct-stock rotation | Long stocks, sales and replacement, plus cash | 1.00x | 14% annualized | 25% | Both V1 and V2 CAGR +2 points |
| V4 - Leveraged stock rotation | V3 selection with conditional borrowing | 1.75x | 20% annualized | 40% | V3 CAGR +2 points |

CAGR means compound annual growth rate, after the complete cost model. A
percentage-point difference is not a percentage uplift. Gross exposure measures
the value of risky positions relative to net asset value (NAV), after borrowing.
The volatility targets scale position size; they do not promise that realized
volatility or losses stay within those values.

The numerical economic hurdles give "significantly beat" a concrete meaning.
Statistical evidence and risk limits must also pass; beating a benchmark by a
small noisy point estimate is insufficient. V3 must beat V2 even if V2 fails its
own benchmark goals. V4 must establish a benefit after financing costs.

**Design judgment:** V3 is the clearest expression of the original stock
thesis. V1 offers diversification but may dilute the signal excessively. V2
has the most demanding benchmark/risk combination. V4 is an extension to test
only after the unlevered stock mechanism works. These are judgments about
testability, not estimates of the probability of success.

## 2. Economic thesis and boundaries

The proposed edge is delayed recognition of an operating inflection: revenue
accelerates, gross margins and cash conversion improve, and financing risk
falls before valuation fully reflects the change. A dated commercial or
regulatory milestone can make that change visible. The screen also tries to
avoid paying an unlimited price for growth.

This mechanism can fail because the information is already priced, consensus
is optimistic, reported improvements are accounting effects, or returns are
ordinary small-cap, momentum or sector exposure. The research must distinguish
those explanations. A company capable of a large price move is not necessarily
an attractive portfolio holding at its present price.

The original request for possible 3x-10x stocks motivates searching for
asymmetric opportunities. It does not become a portfolio return forecast or a
hard signal trained on rare historical winners. Prior discussion of ARQT,
ETON, PAY, DLO and AEHR is discovery knowledge, not a frozen security list or
untouched validation evidence.

Canonical V3/V4 "buying and selling" means entering long positions and later
selling, reducing or replacing them. Short selling, options, inverse funds and
single-stock leveraged ETFs are separate hypotheses. Analyst revisions,
insider transactions and short interest are not added to this score; otherwise
the new mechanism could not be distinguished from the existing lanes.

## 3. Point-in-time information contract

Every raw observation carries source, stable issuer/security ID, field and
units, economic period, public availability time, retrieval time, original
content hash, version, correction link and rights status. Estimates additionally
carry contributor count, GAAP/adjusted basis and exact fiscal-period identity.
Source selection and history availability remain **data to be confirmed**.

**Decision clock:** fundamental eligibility is updated at 16:00 New York time
each trading day. A public non-price fact is first usable at the next trading
session's decision cutoff after its verified publication time. Historical
source availability must be demonstrable; today's retrieval of a revised
historical table cannot establish that an earlier investor knew it. Unknown
publication time means refusal. Observed prices through the decision cutoff
may be used for that cutoff. Execute only in the following trading session.

This adds a conservative full decision-cycle delay to filings and announcements.
It avoids using an after-hours report at that same day's closing price. Actual
ingestion delays, if longer, govern subsequent prospective decisions. Amendments
change future decisions only; they do not overwrite the historical state.

Use as-filed quarterly accounts. Derive fourth-quarter flows from annual minus
the first three quarters only after the annual filing is available. Restated
comparatives may inform later decisions but cannot repair an earlier signal.
Normalize share classes, splits, prefunded warrants, ticker reuse, mergers,
delistings and fiscal-year changes with a dated security master. Never build a
historical universe from companies surviving today.

The SEC permits Form 13F reports after quarter end. Accordingly, use the public
filing acceptance time, not the holdings date, for institutional information.
Late reports, amendments and confidential holdings become usable only when
public. [Source S1]

Freshness limits proposed here: latest quarterly statement period-end no more
than 150 calendar days old; consensus snapshot no more than 30 days old;
contributing estimate updates no more than 120 days old; catalyst evidence
reconfirmed within 90 days; ETF portfolio-holdings publication no more than
five sessions old. Institutional comparisons instead use the latest two
public quarterly cohorts, with the newer holdings period-end at most 150
calendar days old. Required data outside its limit is unavailable, not
silently carried.

## 4. Stock universe and hard gates

Start from point-in-time US-primary-listed operating-company common equity.
Keep historical listings and delistings. This first accounting model excludes
banks, insurers, REITs, funds and premerger SPACs, whose margin/cash measures
are not comparable. ADRs and foreign-primary listings require a separately
defined reporting/identity model. These are disclosed scope restrictions.

Additional investability restrictions: at least 252 listed sessions, latest
price at least $5, and 20-session mean daily dollar turnover at least $5 million.
Use actual traded dollar volume when available; otherwise label close times
share volume as an estimate and preapprove that convention before research.
Every required gate below must pass. Alternatives within a gate are OR branches;
all gates together are AND conditions.

| Gate | Canonical proposed rule |
|---|---|
| Size | Economic equity capitalization $200 million-$5 billion, aggregating equivalent common classes and documented prefunded warrants. Use contemporaneous price and latest publicly known share count. Ambiguous economic dilution refuses entry. |
| Valuation | At least one valid branch in section 5 passes. Missing branches cannot qualify a stock. |
| Profitability | Three successive quarterly ROE observations improve strictly, with quarterly common net income also improving; OR current negative quarterly ROE plus the documented all-in FCF crossover path in section 6. |
| Growth | Three-year actual revenue CAGR at least 20%, and FY1 and FY2 consensus revenue growth each at least 15%; OR the quantified order/capacity acceleration branch below. |
| Gross margin | Latest GAAP quarterly gross margin at least 30% and higher than the year-earlier quarter; OR three consecutive quarterly increases totaling at least one percentage point. All denominators must be positive revenue. |
| Cash generation | Trailing all-in FCF positive and above its previous four-quarter value; OR the documented crossover bridge below. |
| Runway | At least 12 months of operating cash support after unavoidable obligations, under the prescribed stressed monthly cash bridge. |
| Catalyst | At least one sourced, time-bounded milestone within the next 365 days, meeting section 7. |
| Attention | Matched institutional ownership increases or active research coverage increases, meeting section 7. |

**Quarterly ROE** = quarterly net income attributable to common shareholders
divided by average opening/closing common book equity. Both equity balances
must be positive. Two consecutive improvements require Q-2 < Q-1 < Q; this is
not two observations. Net-income improvement prevents a shrinking denominator
alone from manufacturing a turnaround. Negative equity makes this ROE branch
unavailable. The cash-path branch can still be evaluated when ROE is defined
and negative; negative equity is not treated as a positive ROE opportunity.

The original phrase "forward ROE turns positive and grows more than 50%" is
not well-defined as ordinary percentage growth from a negative base. That
standalone branch is **inactive pending a precise owner-approved definition**.
Do not quietly divide by the absolute negative base. TTM ROE is a diagnostic,
not a replacement for quarterly ROE in the canonical strategy. These choices
are stricter than the earlier hand-screen convention and can exclude ARQT.

FY1 is the fiscal year containing the decision date; FY2 and FY3 are its next
two fiscal years. A just-ended year still awaiting actual results uses its
dated consensus for growth comparisons and is marked estimated. Require at
least three independent contributors on a consistent basis for each required
consensus quantity. An IPO without the required three-year history cannot
pass that branch merely through annualization.

**Order/capacity alternative:** a dated issuer filing/release must identify
delivery or commissioning within 12 months and a numeric revenue bridge. Use
contracted delivery values or explicit issuer revenue guidance supported by
capacity and utilization evidence; do not equate installed capacity with sales.
The bridge must imply next-12-month revenue growth at least 15% and at least
five percentage points above current TTM revenue growth. Cancellable orders,
unknown conversion timing and unnamed aspirational customers cannot establish
the bridge. Every conversion assumption is stored, and unsupported items are
zero, not an analyst's discretionary probability.

## 5. Valuation definitions and score

**Forward PEG branch:**

`EPS_growth = (EPS_FY3 / EPS_FY1)^(1/2) - 1`

`PEG = (price / EPS_FY1) / (100 * EPS_growth)`

Require both EPS endpoints and EPS growth to be positive. Pass if PEG <=1.5.
Use diluted per-share consensus on one explicitly identified GAAP or adjusted
basis, with the same basis for both endpoints. Record stock compensation and
expected dilution separately. Very small positive EPS can produce misleadingly
low PEG; flag FY1 net margin below 2% and do not interpret the ratio as proof
of cheapness. A vendor's differently defined PEG cannot be substituted.

**Peer branch:** EV/FY1 sales or equity-value/FY1 sales below the contemporaneous
median of at least eight other comparable issuers in the frozen industry
classification. Match accounting basis, operating model and positive sales;
include qualifying and nonqualifying peers. EV adds debt, preferred equity and
noncontrolling interest, then subtracts unrestricted cash/liquid investments.
Negative or ambiguous EV makes EV/Sales unavailable; P/S may remain valid.

**Own-history branch:** current EV/FY1 sales or P/FY1 sales below its median
over the preceding 60 month-end point-in-time observations, with at least 36
valid observations. Exclude the current observation from the reference. A
current, restated historical ratio chart cannot satisfy this branch.

For each valid valuation branch define a bounded headroom score:

`v_PEG = clip(1 - PEG / 1.5, 0, 1)`

`v_peer = clip(1 - current_multiple / peer_median, 0, 1)`

`v_history = clip(1 - current_multiple / own_median, 0, 1)`

The valuation component V is the maximum valid branch score; this OR treatment
is fixed in advance. Invalid branches are omitted rather than assigned zero.
A passing boundary PEG of exactly 1.5 can qualify while contributing zero
headroom. Multiple sales-ratio branches must all follow their frozen definitions.

**Shared quality score Q, between 0 and 1:**

`Q = 0.30*G + 0.25*P + 0.20*V + 0.15*M + 0.10*A`

Define clip(x,0,1) as truncating values below 0 or above 1. Use fixed bounded
components rather than fitting score weights to realized winners:

- G = clip((g - 0.15)/0.35, 0, 1). For the consensus growth branch, g is the
  smaller of FY1 and FY2 growth. For the order branch, g is the supported
  next-12-month growth. If both qualify, use the smaller valid g.
- P = clip((TTM all-in FCF margin - prior TTM all-in FCF margin)/0.10, 0, 1).
  Margin denominators are revenue for their respective periods. A forward
  crossover can qualify without receiving credit for improvement not yet seen.
- M = clip((latest gross margin - year-earlier gross margin)/0.10, 0, 1).
  A sequential-improvement qualifier can receive zero if its year-over-year
  change is negative. Required historical inputs must still exist.
- A is the larger valid attention score defined in section 7, bounded [0,1].

A missing required score input refuses entry; it is not neutral-filled. Rank
descending Q with stable security ID as final tie-break. No discretionary
"3x probability" or language-model sentiment is part of the calculation.

## 6. Cash accounting and 12-month bridge

Keep two measures to make acquisition-heavy growth visible:

`FCF_standard = operating_cash_flow - cash_PP&E - capitalized_software`

`FCF_all_in = FCF_standard - cash_product_IP_license_intangible_acquisitions`

Do not subtract an item twice when it was already deducted in operating cash
flow or capital expenditures. Retain whole-business acquisition cash separately
in the cash bridge, with any operating-business comparability break disclosed.
Dividends, repurchases, debt principal and lease principal are financing cash
needs, not extra subtractions from FCF. Principal already included elsewhere
is reconciled once. Free cash flow is a defined research measure, not a uniform
GAAP line item.

For a crossover, the next four quarters' cumulative all-in FCF must be positive
and the fourth-quarter all-in FCF run rate positive. Build a source-linked
quarterly bridge from revenue, gross margin, cash operating expense, working
capital, capex and committed product/license payments. Management's adjusted
EBITDA or non-GAAP EPS guidance alone is insufficient. Any unsourced major
input makes the bridge unavailable.

For runway, start with unrestricted cash and saleable short-term investments.
Deduct known debt maturities, lease principal, binding purchase obligations,
committed license/milestone payments and announced mandatory cash uses due
within 12 months. Do not count restricted cash, undrawn/uncommitted borrowing,
an assumed equity raise or contingent milestone receipts as available cash.

Construct 12 monthly balances. Use contractual monthly payment dates; absent
dates, place a known payment at the beginning of its stated quarter, or month
one if only a year is given. Spread quarterly operating flows evenly only
when no better monthly schedule exists, and label that assumption.

Use one dated cash ledger: starting cash plus operating/investing flows less
financing uses. Each payment ID is charged exactly once. License payments in
projected all-in FCF are classified and scheduled as obligations in that
ledger, not subtracted a second time. Reconcile the FCF bridge and obligation
schedule to the same monthly cash balances before accepting runway.

The stressed operating case reduces the bridge's revenue by 20%, reduces
gross margin by five percentage points, holds fixed cash operating costs
unchanged and leaves all committed payments intact. Historical cash-burn
runway using the worse of recent four-quarter average burn and latest-quarter
annualized burn is an additional check, not a substitute for obligations.

Pass runway only if every stressed month-end balance is positive and the final
balance covers one further month of stressed cash operating outflows. Do not
call a company funded for a year because a simple cash/burn ratio ignores an
acquisition payment due next month. These stress magnitudes are proposed
screen settings; they are not issuer forecasts or observed cash needs.

## 7. Catalysts, attention and event risk

Accepted catalyst types are a quantified commercial launch/ramp, signed-order
delivery, supported capacity commissioning, a specified regulatory decision,
an industry-policy implementation tied to the issuer's economics, or a binding
transaction milestone. Store event ID, primary source, publication time,
earliest/latest expected date, business linkage, numeric milestone where
applicable, cancellation status and binary-event flag.

A general addressable-market story, favorable industry headline, rumor or
undated "large customer" does not qualify. If a milestone window expires
without updated public evidence, eligibility fails. An announced delay is a
new version; it cannot be backdated to preserve an earlier signal.

**Institutional route:** use the same manager IDs across two adjacent reported
quarters. Adjust share counts for splits and issuer changes; exclude options,
duplicate manager filings and unresolved amendments. Matched managers must
represent at least 60% of the prior quarter's disclosed institutional common
holdings for that issuer, with at least three distinct managers increasing
shares and positive aggregate matched-manager share growth.

`A_institutional = clip(matched_share_growth / 0.20, 0, 1)`

This measures change within a disclosed cohort, not total current ownership
or proof of fresh buying today. Do not infer motives or distinguish active
from passive flows unless the frozen source permits it. [Source S1]

**Research route:** active independent coverage increases by at least two
firms compared with the point-in-time count 90 days earlier. "Active" means
an attributable published estimate/research update within 120 days. Managers,
analysts and brokerage firms are not interchangeable units.

`A_research = clip(net_new_firms / 5, 0, 1)`

Set A to the larger valid attention score. At least one attention route must
pass; missing alternative coverage is reported. Rumored institutional meetings
or unsourced claims of increasing interest do not count.

For direct stocks, define the event window as five trading sessions before
through one session after a binary clinical/regulatory decision's announced
window. If only a quarter is known, use its entire quarter as the event window.
During this window cap each affected issuer at 2% NAV and their aggregate at
10% NAV. V4 cannot finance that sleeve. A surprise binary event remains a gap
risk. ETFs apply the same 10% NAV aggregate lookthrough binary-event cap.

## 8. Translating company evidence into ETF evidence

The $200 million-$5 billion requirement applies to companies, not ETF assets.
The ETF itself need not have that market capitalization. Do not screen using
a fund's blended ROE, a headline P/E or the score of its single best holding.

Let h_ei be company i's disclosed fraction of ETF e's **total NAV**, P_i its
hard-gate pass indicator and Q_i its shared quality score:

`C_e = sum(h_ei * P_i)`

`S_e = sum(h_ei * P_i * Q_i)`

`N_eff_e = C_e^2 / sum((h_ei * P_i)^2)`

C is qualifying exposure; S is the diluted fund signal; N_eff measures the
effective number of qualifying issuers. Unqualified or missing holdings,
foreign holdings, cash and derivatives remain in the NAV denominator and
contribute no positive signal. Do not renormalize a 1% qualifying sleeve to 100%.

Candidate funds are US-listed transparent ordinary long-only equity ETFs with
252 usable sessions. Exclude leverage, inverse exposure, options-overlay funds,
ETNs and opaque active products from selection. Require at least 95% of NAV
mapped and accounted for, holdings no older than five sessions, at least 20%
qualifying NAV, five distinct qualifying issuers and N_eff >=5.

Also require 20-session average daily dollar turnover >=$20 million and
trailing 30-calendar-day median quoted spread <=20 basis points. Historical
spread and holdings availability must be verified before empirical use. For
covered transparent ETFs, the SEC rule requires disclosure of prior-day
holdings before opening; this does not authenticate a historical archive or
apply to every ETF structure. [Source S2]

Rank all individually eligible funds by S; keep the complete uncapped raw rank
list. Ties use lower measured spread, then stable fund ID. Weighted
holdings overlap is sum_i min(h_ei,h_fi) after issuer aggregation. Greedily
accept funds in the incumbent-then-entry order specified for V1, skipping
overlap above 60% with any already accepted fund, up to six. There is no
preliminary top-six truncation that would erase the incumbent buffer. Use all
mapped holdings for overlap, not just qualifiers.

At least two nonduplicate funds are required to initiate an ETF portfolio.
Insufficient funds means cash, recorded as infeasibility/underfill. A universe
that cannot satisfy the 20% exposure gate does not support the ETF thesis.
Dropping that threshold after seeing returns would create a new hypothesis.

## 9. Shared weighting, volatility and risk mechanics

At each scheduled selection date, retain eligible incumbents within the
specified rank buffer before filling vacancies from the entry ranking. Ties
use stable IDs. Allocate base weights in proportion to inverse 60-session
annualized volatility, using floors of 10% for ETFs and 20% for stocks.
Apply a breadth multiplier min(1, eligible_selected_count / target_count),
so a small portfolio is not silently scaled to full investment.

Estimate portfolio volatility using the proposed target composition and
20-, 60- and 252-session sample covariance matrices of synchronized daily
total returns. Each uses 50% shrinkage to its diagonal. Use the largest of
the three annualized portfolio-volatility estimates. Every held instrument
needs all 252 observations; do not drop bad dates or replace missing returns
with zero. A missing required risk input prevents additions and leverage.

For V1-V3, let u be the normalized unit-gross risky basket, sigma_u its forecast
volatility, B the breadth multiplier and L the currently allowed gross ceiling:

`equity_exposure = min(B * L, volatility_target / sigma_u)`

Target risky weights initially equal equity_exposure times u. For example,
30% unit-basket volatility and an 18% target allow at most 0.60x exposure,
regardless of a 1.75x ceiling. Do not multiply that volatility ratio by the
ceiling again. V4's restricted incremental sleeve uses section 13 instead.
Drawdown, trend, concentration, liquidity and margin constraints can reduce
exposure further. A zero/invalid volatility estimate refuses additions. No
expected-return optimizer fits weights to backtest outcomes.

For concentration, first cap individual weights, then proportionally scale
each breached sector, then the binary-event sleeve, then the whole portfolio
for any remaining constraint. Do not redistribute clipped weight. Inverse
volatility normalization precedes these cuts; all released capital stays cash
or reduces borrowing. Cash interest and financing are accounted separately.

**Drawdown** = 1 - current net liquidation NAV / historical maximum net
liquidation NAV. Mark at least daily and after simulated fills; include costs,
interest, dividends, halted holdings and terminal losses. Never reset the
high-water mark after a loss or at a new calendar year. A fresh research epoch
does not erase the prior epoch's failed evidence.

Risk constraints operate daily at the cutoff; reductions execute at the next
tradable opportunity. Their effect is not retroactive to a gap already suffered.
For a reduction state below the permanent-halt threshold, allow a one-step
increase only at month-end, after drawdown is at least two percentage points
below the threshold that entered that state and trend/risk checks pass.
Crossing a deeper threshold immediately replaces the current state.

At the final reduction threshold in the version tables, liquidate risk when
executable and keep the frozen run in cash to its end. There is no automatic
high-water recovery rule for an all-cash portfolio. A new restart design is a
new hypothesis. A halt remains part of the result even if later markets rally.

## 10. Version 1 - Balanced fundamental ETF rotation

**Purpose:** express the stock signal through diversified funds, seeking
meaningful net SPY outperformance within the owner's 15% drawdown criterion.

- Select monthly at the last trading session's cutoff; trade next session.
- Target six funds. New entries rank in the top six; eligible incumbents can
  remain through rank nine, subject to the overlap rule and concentration caps.
  Apply the overlap rule after ordering retained incumbents by current score,
  then fill from entry ranks. The six-slot cap remains binding.
- Require fund price above its 100-session simple moving average at selection.
  A daily close below that average triggers exit at the next opportunity.
- Equity gross cap 1.00x and annualized volatility target 10%.
- Maximum 25% NAV per fund, 45% lookthrough per sector, 5% lookthrough per
  underlying issuer. ETF event exposure follows section 7.
- If SPY closes below its 200-session simple moving average, cap equity gross
  at 50%. Missing SPY regime data blocks additions and caps equity at 25%.
- Residual unborrowed cash earns the conservative net cash rate in section 14.
  No substitute momentum ETF fills an unavailable fundamental allocation.

Recompute ETF holdings freshness, company pass flags, qualifying NAV, breadth,
lookthrough concentration and event limits daily from usable records. Loss of
an ETF hard gate forces its next-executable exit; a portfolio cap breach
forces reduction. Falling below two eligible funds exits the remaining ETF
portfolio. Rank-only replacement remains monthly, so daily data updates do
not authorize discretionary turnover.

| Drawdown reached | Maximum equity exposure / action |
|---:|---|
| 7.5% | 0.50x |
| 10% | 0.25x |
| 12% | Exit risk, permanent research halt for this run |
| More than 15% | Fails the owner's drawdown acceptance condition |

**How this could work:** broad ownership of improving businesses reduces
single-company surprises; holding cash when breadth collapses can reduce
losses. **What can defeat it:** low qualifying NAV, overlapping sector bets,
late fundamentals and trend whipsaws. A strong SPY bull market can make the
outperformance objective fail even when risk controls work as intended.

## 11. Version 2 - Leveraged fundamental ETF rotation

**Purpose:** test whether selectively financing the same ETF opportunities
adds enough net return to beat continuously held 2x market benchmarks, while
respecting a proposed 35% maximum-drawdown acceptance criterion.

The primary mechanism is portfolio borrowing against **ordinary selected ETF
shares**. This is a leveraged ETF portfolio, not a substitution into an
approximately related daily-leveraged sector ticker. Its own brokerage/margin
feasibility must later be proven. No broker action is part of this blueprint.

- Use V1's fund selection, rank buffer, holdings tests and monthly schedule.
- Gross ceiling 1.75x; annualized volatility target 18%.
- Financing above 1.00x requires at least three selected, nonduplicate funds;
  at least three distinct sectors each representing >=10% of the selected
  unlevered basket; SPY and IWM both above their 200-session averages; and all
  funds above their 100-session averages.
- Also require at least 20 distinct qualifying issuers across the selected
  funds after deduplication, current financing inputs and margin headroom.
- If a leverage condition fails, cap gross at 1.00x. V1's lower SPY regime
  caps still apply. Do not finance cash created by underfill or concentration
  constraints in order to restore nominal exposure.
- Maximum 35% NAV per ETF, 60% NAV per lookthrough sector, 7.5% per underlying
  issuer; binary-event exposure still <=10% NAV. Apply these to economic
  exposure after leverage, not to an imagined unlevered portfolio.
- Equity must be at least 1.5 times modeled maintenance-margin requirements
  and satisfy initial-margin and buying-power requirements. Any tighter
  instrument-specific or broker requirement wins.

| Drawdown reached | Maximum equity exposure / action |
|---:|---|
| 12% | 1.00x |
| 20% | 0.50x |
| 28% | Exit risk, permanent research halt for this run |
| More than 35% | Fails the proposed drawdown acceptance condition |

The primary challenge benchmarks are **SSO and QLD separately**. Their issuer
objectives are twice the daily S&P 500 and Nasdaq-100 returns, respectively;
they are not twice those indices' annual returns. [Sources S3-S5]

Compare additionally against SPY and QQQ scaled to V2's own lagged gross
exposure and financing convention. That diagnostic distinguishes selected ETF
performance from merely changing market exposure. It cannot replace the
harder SSO/QLD goals. A 1.75x ceiling may lose to 2x buy-and-hold in a sustained
rise; this is a genuine hurdle, not a reason to change benchmarks later.

Actual leveraged-ETF wrappers are not mixed into this canonical experiment.
Using them would require exact index mapping, their own point-in-time
availability and daily compounding, and a separately registered execution
variant. A similarly named sector ETF is not an exact substitute.

**Largest failure channels:** weak ETF signal amplified by borrowing; trend
whipsaw plus financing drag; and sudden margin or liquidity changes. A margin
firm may impose higher requirements and liquidate positions to meet a
deficiency. The research model must not assume a warning arrives first.
[Source S6]

## 12. Version 3 - Direct-stock fundamental rotation

**Purpose:** capture more of the company-level signal and reduce ETF dilution,
with enough diversification to seek net superiority over V1 and V2 within
the revised proposed 25% maximum-drawdown condition.

- Weekly selection at the last trading session's cutoff; trade next session.
- Target 18 issuers. New entries from ranks 1-18; eligible incumbents can
  remain through rank 25. Retain incumbents ordered by score, then fill
  vacancies from entry ranks. If more incumbents qualify than slots, retain
  the highest scores. Score and hard eligibility are distinct.
- Gross ceiling 1.00x; volatility target 14%; issuer cap 8% NAV; sector cap
  25% NAV. Breadth scaling and residual cash apply even if only one stock passes.
- Entry requires price above its 100-session average. Two consecutive daily
  closes below that average trigger exit. A five-session earnings blackout
  before and one session after known earnings blocks new entries, while
  existing holdings remain subject to risk limits and event disclosures.
- If SPY is below its 200-session average, cap equity exposure at 50%; if
  that regime input is missing, cap at 25% and block additions.
- Recompute fundamental gates daily when new information becomes usable.
  A failed gate, cash-runway deterioration, missed catalyst, identity failure
  or stale required input triggers removal at the next executable session.
- Rank-only replacement is weekly. No fixed profit target, automatic sale at
  3x, loss averaging or discretionary "story still good" override is used.
  This lets improving businesses remain held while selling broken conditions.

| Drawdown reached | Maximum equity exposure / action |
|---:|---|
| 10% | 0.75x |
| 15% | 0.50x |
| 20% | 0.25x |
| 22% | Exit risk, permanent research halt for this run |
| More than 25% | Fails the proposed drawdown acceptance condition |

Buying and selling is driven by a change in eligibility, rank, trend or risk,
not an obligation to alternate transactions on a schedule. A sale need not
be followed by a replacement if no company qualifies. Data failures block
new risk but must not prohibit an otherwise supported exposure reduction.

**Largest failure channels:** accounting or forecast errors; concentrated
binary/gap losses; and turnover/impact that consumes the signal. The 25%
drawdown requirement may be particularly difficult for $200 million-$5 billion
companies. The strategy must demonstrate it rather than infer it from 18 names.

## 13. Version 4 - Selectively leveraged stock rotation

**Purpose:** test whether financing the V3 mechanism improves after-cost
results without exceeding the revised proposed 40% maximum-drawdown criterion.

- Preserve V3's stock eligibility, ranking, target 18 names, weekly schedule,
  trend exits and binary-event rules. Each version maintains its own path and
  drawdown state; leverage-induced exits need not produce identical holdings.
- Gross ceiling 1.75x; volatility target 20%; issuer cap 14% NAV; sector cap
  40% NAV. Constraints apply after leverage and do not redistribute clipped
  positions. Gross above 1.00x is an allowance, not a target.
- Leverage requires at least 12 current holdings across four sectors, each
  sector at least 10% of the unlevered selected basket; SPY and IWM above their
  200-session averages; and verified financing and margin inputs.
- A financed issuer must have 20-session average dollar turnover >=$15 million.
  Less liquid eligible issuers may be held in the cash-funded sleeve, but
  receive no incremental leverage allocation. A financed sleeve must contain
  at least ten eligible issuers; otherwise cap the portfolio at 1.00x.
- No incremental borrowing funds binary-event-window holdings. Total cash-funded
  binary-event exposure remains <=10% NAV and <=2% per issuer.
- Apply the same 1.5-times-maintenance-equity buffer as V2. Treat unknown or
  prohibited instrument margin treatment as no leverage; do not substitute
  general regulatory minimums for actual brokerage requirements.
- If a leverage gate fails, gross <=1.00x, further reduced by V3's lower
  SPY regime cap, volatility and current drawdown state.

| Drawdown reached | Maximum equity exposure / action |
|---:|---|
| 15% | 1.00x |
| 25% | 0.75x |
| 32% | 0.25x |
| 36% | Exit risk, permanent research halt for this run |
| More than 40% | Fails the proposed drawdown acceptance condition |

Before any use, cash-funded and financed sleeve bookkeeping must enforce a
single NAV and borrowing balance: it cannot count the same dollar as both
cash reserve and margin support. Sell obligations and financing interest take
priority over additions. Unknown buying power prevents more borrowing.

**Exact incremental allocation:** first compute unlevered base weights b using
V4's selected names, 20% volatility target, breadth and risk limits with gross
temporarily capped at 1.00x. Apply concentration/event/liquidity cuts without
redistribution. Let F be the finance-eligible issuers, B_F = sum(b_i for i in F),
and a_i = b_i/B_F for i in F, zero otherwise. If B_F is zero or any leverage
gate fails, incremental size k is zero. Otherwise choose the largest k in
[0, 0.75*B_F] for which w_i = b_i + k*a_i satisfies every current gross,
drawdown, volatility, concentration, margin and liquidity constraint. Recompute
the three covariance forecasts on w itself; its annualized volatility must
be <=20%. The feasible upper boundary follows the frozen quadratic/linear
constraint solver, rounded downward to one basis point of NAV. No leverage
capacity released by an excluded issuer is reallocated to other issuers.
Post-rounding checks may only reduce k. Event-window and less-liquid issuers
therefore receive exactly their base allocation, never a scaled increment.

**Largest failure channels:** correlated small-cap gaps, forced deleveraging
and financing drag. Report a fixed 1.75x V3 control with identical financing
to separate selective leverage from constant leverage. This is an attribution
diagnostic, not an additional success claim.

## 14. Execution, costs, financing and capacity

Research reference capital is **$1 million per version**, with identical
start date and cash. This is a modeling amount, not the owner's account value.
Also report fixed capacity diagnostics at $100,000, $5 million and $10 million;
those cannot replace the reference-capital primary result.

Signals determined at cutoff t execute next session during 09:45-10:15 New York
time against time-stamped prices/quotes. Use marketable limit orders, simulated
as paying the contemporaneous ask for purchases or receiving the bid for sales,
plus the adverse impact model. A limit is at most 50 basis points beyond the
arrival mid for ordinary planned orders. Missing intraday data makes this
canonical fill model unavailable; a daily-bar approximation is exploratory.
If the simulated bid/ask plus adverse impact crosses the limit price, the
quantity is unfilled. Observing the session's high or low does not prove fill.

Ordinary execution may use at most 1% of trailing 20-session daily dollar
turnover and 5% of observed window volume. Unfilled purchases expire after
three sessions; reevaluate signals before each continuation. Planned sales
continue while valid and carry actual inventory/risk until filled. Do not
mark an exit at a stale closing price during a trading halt.

Risk and margin reductions override ordinary participation limits but receive
adverse stressed fills. They cannot assume unlimited liquidity at the last
quote. Forced liquidations, exchange halts, bankruptcy payoffs and corporate
action proceeds must be modeled and retained on every relevant date.

Proposed one-way transaction cost, in addition to observed execution mid:

`cost_bps = quoted_half_spread_bps + max(floor_bps, 0.10 * daily_vol_bps * sqrt(order_notional / ADV20))`

Floor = 2 basis points for ETFs and 10 for stocks; commission assumption =
0.5 basis points on traded notional, plus the effective dated exchange and
regulatory fee schedule. These are starting research assumptions, not claims
about a current account's fees. One basis point is 0.01%. Calibrate adequacy
using separately approved execution data before freezing outcomes; no
post-result reduction of costs is allowed.

The cost formula describes slippage relative to mid. Because bid/ask fills
already include half-spread, the cash ledger charges only additional impact,
commission and fees on top of those fills. It never deducts half-spread again.

Deduct costs from actual traded notional, not NAV turnover rounded in a table.
Record spread, impact, commission and other fees separately. Stock and ETF
dividends enter on their economically available dates; do not grant early
reinvestment or double count them with adjusted returns. Use a validated
total-return ledger for research, actual shares/cash for execution simulation.

V2/V4 borrowing accrues over actual calendar days on the borrowed amount using
ACT/360 and the previous available SOFR plus a proposed 300-basis-point spread.
If the actual supported account schedule is higher, it governs. The SOFR rate
and publication lag must be dated, not copied from today's rate. [Source S7]
For dates before a validated SOFR history, the canonical financing series is
unavailable; do not silently splice another rate.

Unborrowed cash earns max(0, previous available SOFR minus 100 basis points)
under this proposed conservative convention. A known lower account credit
rate governs. Never earn cash interest on a negative cash balance. Margin
interest, leverage rebalancing and collateral liquidations must all enter
net NAV. Actual ETF total-return prices already embed fund expenses and
internal financing; do not deduct those embedded costs twice for benchmarks.

Stress cases are fixed diagnostics: double spread/impact; financing at SOFR
plus 500 basis points; ADV down 50%; margin requirements raised by ten
percentage points; a 10% one-day ETF basket gap; and, separately, a 40% loss in
the largest direct-stock holding plus a 15% loss in its other sector holdings.
Apply each case and their adverse combination to every scheduled post-rebalance
portfolio snapshot and report the worst result; do not select a favorable
shock date. These shocks are hypothetical,
not estimated probabilities or promised worst cases. Report post-shock
equity, liquidity, margin deficit and possible cap breach without smoothing.

Use a conservative model baseline of at least 50% initial and 35% maintenance
equity per marginable position unless a verified stricter requirement applies.
This is a research assumption, not a statement of universal margin rules.
The separate 1.5-times-maintenance buffer makes effective allowed leverage
lower when requirements rise. Unverifiable historical margin treatment limits
the strength of any leveraged feasibility claim. [Source S6]

Personal taxes are excluded from canonical after-cost returns because account
type and tax circumstances are unspecified. Report turnover and realized-gain
characteristics; do not label results after-tax. Leveraged versions must retain
a strictly positive net CAGR advantage over every required comparator under
doubled trading costs and the higher financing spread. Their full +3/+2-point
economic hurdles apply to the canonical cost case, not this stress condition.

## 15. Benchmarks and the definition of market alpha

| Claim ID | Required comparison | Minimum net CAGR advantage | Version drawdown ceiling |
|---|---|---:|---:|
| FIA-E1 | V1 minus SPY | +3 percentage points | 15% |
| FIA-E2 | V2 minus SSO | +3 points | 35% |
| FIA-E3 | V2 minus QLD | +3 points | 35% |
| FIA-E4 | V3 minus V1 | +2 points | 25% |
| FIA-E5 | V3 minus V2 | +2 points | 25% |
| FIA-E6 | V4 minus V3 | +2 points | 40% |

SPY, SSO and QLD are fixed buy-and-hold total-return challenges. Admit all on
the common start date using consistent initial execution costs, hold cash
distributions until their modeled reinvestment time, and include terminal
liquidation costs. Use actual post-launch price histories with dated corporate
actions. Synthetic prelaunch leveraged returns cannot count as confirmation.

Report SPY, QQQ and IWM context, cash, and the matched-exposure SPY/QQQ controls.
The larger of SSO/QLD results is not used as a hindsight-switching benchmark;
V2 must separately pass both fixed comparisons. Three-times funds are outside
the canonical two-times interpretation of the user's unspecified leverage
benchmark. Changing to 3x is a specification amendment before testing.

All six comparisons use identical dates and capital conventions. Cash,
underfill, late data, unavailable funds and permanent-halt intervals stay in
the path. Missing benchmark observations invalidate the common interval;
they cannot selectively remove a losing strategy date. Data deficiencies
are reported as invalid/inconclusive, not a valid zero return.

Raw superiority is not enough to claim market alpha. For each strategy fit
the preregistered monthly excess-return factor regression using market, size,
value, profitability, investment, momentum and sector returns. Use all but
one sector as deviations from market; fix the omitted sector and a
deterministic rank-deficiency refusal rule before outcomes. Report the net
intercept and dependence-aware uncertainty. A validated point-in-time factor
source and accounting basis are prerequisites, not assumptions about a
download. Standard factor definitions are documented by their primary source.
[Source S8]

Also compare the new score with simple growth/value and momentum controls on
the same admitted observations. These are falsification diagnostics, not
unbudgeted alternative candidates that may rescue a failed strategy. Exposure
matching uses only lagged exposures and the frozen finance/cost model.

## 16. Stock-first experiment and walk-forward protocol

**FIA-S0:** does Q predict subsequent company returns beyond established
controls? Sample monthly, before ETF construction, across the full admitted
historical universe. The primary outcome horizon is 126 trading sessions.
Retain delisting losses, mergers and unavailable outcomes with explicit
dispositions. Do not count 18 stocks each month as 18 independent experiments.

Use trailing five-year training windows and successive one-year development
evaluation folds. Fit the return-control model in training only, using log
market value, valuation, profitability, prior 12-minus-1-month momentum,
volatility, liquidity, earnings surprise and sector indicators. The primary
signal statistic is mean date-level Spearman correlation between Q and
out-of-sample residual forward returns. Expected sign is positive. Fixed
score weights are never optimized by that control fit.

Purge training labels whose 126-session outcomes overlap evaluation; apply
an additional 21-session embargo. All stock observations on the same date
belong to the same split. Evaluation-fold labels cannot train controls for
their own fold. Related issuers share identity groups. Freeze the exact
fitting routine, nuisance regularization, minimum cross-section (30 issuers)
and missing-control rules before outcome access. Refused dates count toward
feasibility, not toward a fabricated information coefficient.

The common company mechanism must pass before claiming either ETF or stock
alpha. Failure of ETF feasibility cannot veto a valid V3 mechanism, but a
successful ETF market bet cannot rescue a null company signal.

Exact development and confirmation dates are **unassigned** in this design.
They depend on verified source history, power and program coordination.
Previously seen prices, issuer performance tables and named-stock research
are marked discovery exposure. Do not label an arbitrary historical slice
"untouched" just because this agent has not backtested it.

The proposed confirmation floor is 60 nonoverlapping monthly portfolio
observations, plus a prospective, pre-outcome power study targeting at least
80% power at the allocated threshold for the stated economic effect. This is
a floor, not proof of sufficient power. If the required independent history
is unavailable, report insufficient evidence and specify the observation
period required; do not declare success from a short bullish interval.

Use synchronized circular moving-block bootstrap draws for all portfolio
comparisons, 12-month blocks, 50,000 replicates and fixed seed 20260914.
For overlapping stock forward labels use six-month date blocks. These are
proposed primary settings; synthetic size/power calibration must validate
them before freezing. If calibration fails, revise before outcomes and record
the revision; do not choose a block length from favorable p-values.

## 17. Statistical allocation and permanent research ledger

The existing four named strategy lanes already have total two-sided family
error allocation 0.05, with permanent 1/80 slots. Their unused slots expire.
This new design is not a fifth slot and cannot inherit their data rights,
review status, run budgets or final holdout.

**Proposed new-family allocation:** subject to a later owner-coordinated
program decision, allocate a separate FIA family maximum two-sided error
budget of 0.05 across seven fixed claims: FIA-S0 and FIA-E1 through FIA-E6.
Each receives at most **1/140**, so seven times 1/140 = 0.05. This would be a
new-family guarantee only; it does not preserve a 0.05 guarantee across both
the old and new programs. Actual allocation and outcome access remain zero.

For S0 require positive sign and p <=1/140. For each E claim use the larger
of its paired net-outperformance p-value and its strategy's positive
factor-alpha p-value; require that conjunction p <=1/140, positive estimated
effects and the economic hurdle. Factor tests are prerequisites, not separate
discoveries. V2 needs E2 and E3; V3 needs E4 and E5; V4 needs E6. Every claimed
version also needs S0, valid data/execution, its drawdown cap and stress gates.

Paired outperformance tests use monthly log-return differences, with the
null centered at zero. Economic CAGR hurdles are additional conditions;
statistical significance of a tiny return advantage does not clear them.
Report raw p-values and adjusted claim decisions. For simultaneous intervals
over the eleven unique component quantities (S0, six paired effects and four
factor intercepts), use Bonferroni two-sided component alpha 1/220, giving
joint coverage of at least 95%. Do not call seven claim-level intervals
simultaneous over eleven components. This interval construction does not
increase the seven-claim testing budget.
Never equate a p-value with the probability of future outperformance.

The existing reserved final holdout **2027-09-01 through 2029-08-31** remains
unconsumed by this design. A later coordination decision must assign FIA
confirmation dates and selection accounting before any outcomes are opened.
No results may be borrowed from Analyst Revisions, Insider Buying, Short
Interest or Target-Price Revisions to claim this family passed.

Planned budget after such approval: one immutable development outcome batch
containing all four versions and fixed diagnostics, then one confirmation
batch if its prerequisites pass. Development is exploratory and spends no
confirmatory alpha, but is permanently logged as a research look. Every
attempt, error, refusal, partial reveal and corrected execution is recorded.
A corrected replay never restores an untouched holdout or a consumed look.

Build and fixture-test all four engines before that development batch. Its
prebound dependency graph releases S0 first, and releases/interprets portfolio
results only if S0 meets the development progression criterion fixed before
the run. No intermediate outcome authorizes changing the portfolio rules.
If S0 fails, the unreleased portfolio stages remain unopened and the company
mechanism closes null. Structural engine construction is not stock evidence.

No grid of score weights, leverage levels or stop thresholds is authorized by
four versions. TTM ROE, relaxed ETF breadth, alternative PEG, wrappers, shorts,
options and ensembles are named unimplemented alternatives. Testing any of
them requires a new recorded hypothesis and budget before its outcomes.

## 18. Acceptance, failure and required report

A version is accepted as a research result only when all its required claims
and operational-feasibility tests pass on the independently reviewed frozen
confirmation protocol. Design quality alone is not performance evidence.

Required evidence for every version:

- Complete net equity curve and the same-date benchmark curves; CAGR,
  maximum drawdown, drawdown duration, annualized volatility, Sharpe/Sortino
  under a defined cash rate, Calmar and monthly/annual return tables.
- Corrected paired inference and factor-alpha results; beta and sector
  exposure, turnover, financing, spreads, impact and unrealized/unfilled risk.
- Eligible-universe and fund counts, qualifying NAV, missing-data refusal
  rates, time in cash, risk halts, concentration and capacity by period.
- Contribution by issuer, sector and year; report exclusion of the five
  largest positive issuer contributors as a fragility diagnostic. Do not
  substitute that diagnostic for the complete primary return path.
- Double-cost/higher-financing results and fixed gap/liquidity/margin shocks.
  Leveraged versions require positive net benchmark advantage under cost
  stress and no modeled insolvency or unfinanced margin deficit. All versions
  report whether shocks would exceed the owner's drawdown ceiling; a breach
  rejects the risk-constrained design under that stated scenario.
- Source-year/period labels on all actual financial data, immutable manifests,
  code/config identities, experiment IDs, input/output hashes, and every
  result's valid/null/invalid/inconclusive disposition.

The following are honest failures: no qualifying stocks or ETFs; insufficient
independent dates; no point-in-time consensus/catalyst archive; no incremental
stock signal; net underperformance; risk-cap violation; or financing/capacity
that cannot be supported. A null can close one expression while another has
independent merit. None is fixed by deleting losing dates or loosening the
screen after observing outcomes.

## 19. Implementation sequence and interfaces

These are proposed bounded milestones, not instructions to start jobs:

| Stage | Deliverable | Exit condition |
|---|---|---|
| FIA-0A | Reviewed semantic specification, exact parameters and lineage contracts | Resolve source semantics, ROE branch, global allocation, dates and power protocol; owner freeze |
| FIA-0B | Source-rights and availability register | Verify vintage accounts, consensus, holdings, catalysts, prices, terminal returns, quotes, factors, financing and margin inputs |
| FIA-1 | Deterministic canonicalization and gate/score engine | Synthetic fixture checks; missing/late/amended/negative-equity cases refuse correctly |
| FIA-2 | Stock-first event-study engine and immutable run ledger | Synthetic validation; outcome release remains closed |
| FIA-3 | V1/V3 portfolio construction and execution simulator | PIT holdings, diversification, underfill and cost identities verified |
| FIA-4 | V2/V4 finance and risk extension | Cash/margin accounting, adverse liquidations and leverage attribution verified |
| FIA-5 | Frozen common-date development and confirmation package | All engines built; independent review, stock-first release graph, allocated looks, power and source gates closed before execution |
| FIA-6 | Observation and later promotion package | Separate decisions for shadow, paper, restricted live and any unattended operation |

Use a lane-owned namespace such as `research/fundamental_inflection/` only
after implementation is scheduled. Suggested typed records: `FinancialVintage`,
`ConsensusVintage`, `CashBridge`, `CatalystEvent`, `InstitutionalCohort`,
`EligibilityDecision`, `StockScore`, `EtfHoldingsVintage`, `EtfScore`,
`PortfolioTarget`, `RiskState`, `FinancingState`, `ExecutionDisposition` and
`ExperimentManifest`. Each derived record binds its exact parents and as-of time.

No backtest calls live vendor APIs. Immutable permitted custom/precomputed
data and a deterministic QuantConnect/LEAN research adapter can be designed
after source-processing rights and the engine choice are expressly scheduled.
Local fixtures never count as market evidence. Separate research outputs
from the existing assistant's human-approved paper execution path.

Core algorithm outline:

```text
for each NYSE session t:
    admit only verified facts available by cutoff(t)
    reconcile corporate actions, holdings, cash, interest and pending fills
    evaluate hard company gates; persist pass/refusal and provenance
    compute company Q only when all required score inputs are valid
    daily: recompute ETF hard gates, qualifying NAV, breadth and current caps
    on ETF selection dates: compute full ranking and apply overlap selection
    on each version's selection date: retain eligible buffer names, fill ranks
    compute breadth-scaled inverse-volatility targets
    apply trend, volatility, concentration, event, drawdown and margin limits
    allow reductions when supported; block additions on missing critical data
    schedule next-session executions with costs, limits and unfilled inventory
    mark net NAV; retain cash, halted periods and every refusal in the ledger
```

Dangerous-direction fixture requirements include: filing after cutoff;
quarter-end masquerading as availability; amended holdings; reused ticker;
negative equity; low-base PEG; double-subtracted licenses; restricted cash;
delisted losers; one qualifying ETF holding falsely renormalized; overlapping
funds; insufficient breadth; unknown margin; rate publication lag; leverage
after a drawdown; stale quotes blocking risk reduction; and a trading halt
that prevents a planned exit. Compare independent cash/share/NAV calculations.

## 20. Sources, provenance and current disposition

Primary public sources below were consulted on **2026-09-14** for mechanics.
They do not validate strategy alpha, supply a historical research entitlement
or verify current candidate holdings. No source is quoted at length.

- **S1 - SEC, Form 13F FAQ** (current page accessed 2026): reporting schedule,
  filing requirements and interpretation of disclosed institutional positions.
  https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f
- **S2 - SEC, Exchange-Traded Funds compliance guide** (2019 rule guide,
  accessed 2026): covered ETF holdings disclosure and excluded structures.
  https://www.sec.gov/investment/exchange-traded-funds-small-entity-compliance-guide
- **S3 - ProShares SSO issuer page** (accessed 2026): 2x daily S&P 500 objective.
  https://www.proshares.com/our-etfs/leveraged-and-inverse/sso
- **S4 - ProShares QLD issuer page** (accessed 2026): 2x daily Nasdaq-100 objective.
  https://www.proshares.com/our-etfs/leveraged-and-inverse/QLD
- **S5 - SEC Investor Bulletin, leveraged and inverse ETFs** (2023): daily
  reset objectives and divergence over longer holding periods.
  https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/sec
- **S6 - FINRA, Margin Calls** (accessed 2026): margin changes and liquidation risk.
  https://www.finra.org/investors/insights/margin-calls
- **S7 - Federal Reserve Bank of New York, SOFR** (accessed 2026): secured
  overnight reference-rate definition and publication framework.
  https://www.newyorkfed.org/markets/reference-rates/sofr
- **S8 - Kenneth R. French Data Library** (accessed 2026): primary definitions
  of standard research factors; historical availability and usable vintages
  still require a separate data contract.
  https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

Repository design references: the Analyst Revisions V2, Insider Buying and
Short Interest PDFs in `docs/Strategy Description/`; the current Action Plan;
`docs/THREE_STRATEGY_PROJECT_DIRECTION.md`; and the general review/handoff
process. Existing lane contracts and reserved evidence remain unchanged.

Current disposition: **four complete design chapters; no measured returns,
no validated alpha, no current selection portfolio, no source acquisition,
no outcome run and no implementation/promotion claim**. Numeric design
settings, including the revised higher-risk drawdown assumptions, remain proposals for
independent review. Any actual market/financial field not verified later must
be labeled **data to be confirmed**, never filled with an invented value.
