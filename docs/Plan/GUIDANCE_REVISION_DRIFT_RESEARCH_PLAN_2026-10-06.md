# Management Guidance Revision Drift

## 1. Decision brief

**Concrete research plan | GDR-1.0 | 6 October 2026**

**Status: queued design candidate, independently unreviewed.** The owner requested a plan, not implementation or trading. Every numeric setting below is a proposed default to approve before research; none is an optimized value, observed return, or promise of profit. The Markdown is the editable source; the PDF is its reading edition.

### The investment hypothesis

Some companies raise their full-year revenue and earnings outlook because business is improving faster than investors recognize. Test whether a liquid-stock portfolio bought after a conservative information delay earns useful returns over approximately one month, after execution costs and comparison with a matched market investment.

Start with **one long-only stock strategy**, not a collection of variants. Academic evidence motivates the question but does not establish this implementation's profitability. More credible forecasts can have larger immediate reactions and less subsequent drift [S1].

| Proposed baseline | Specification |
| --- | --- |
| Signal | Same-period revenue midpoint raised at least 2%; adjusted EPS midpoint raised at least 5%; neither lower bound reduced |
| Instruments | Eligible US primary common shares; no ETFs, options, leverage or shorts |
| Entry | No earlier than the third NYSE session strictly after the announcement date; all inputs must also clear the preceding-session receipt cutoff |
| Holding period | 20 session-to-session intervals: enter on session 1, exit on session 21; earlier risk/invalidation exits apply |
| Portfolio | USD 100,000 illustrative research sleeve; 5% initial position ceiling, 50% gross ceiling, 15% sector ceiling |
| Core comparison | Same entry-budget and exit-schedule SPY portfolio, including costs and idle cash |
| Main outcome | Annualized mean daily net return difference versus that comparator; no result measured yet |
| Evidence status | Historical reconstruction is exploratory; confirmation requires untouched, verifiably available data and an approved testing allocation |

### What this plan does and does not do

It specifies data contracts, deterministic rules, order simulation, research accounting, acceptance gates and a staged implementation path. It does not schedule itself, create a fifth development lane, change the existing four lanes, or authorize provider access, cloud uploads, outcome viewing, a QuantConnect run, a scheduler, paper orders or real-money trading.

This is distinct from analyst-rating/target-price changes: the issuer changes its own guidance. It also differs from the existing Fundamental Inflection blueprint's multi-factor stock screen. Shared data and conceptual overlap must still be disclosed; separate names do not create independent statistical evidence.

**Money-use boundary:** a 20-session holding period is not a promise to earn money within 20 sessions. Household spending money and emergency reserves are outside the proposed research sleeve. No allocation of the owner's actual capital is specified.

<!-- pagebreak -->

## 2. Data feasibility and availability

The stated resources are Sharadar, QuantConnect and Massive-Benzinga ratings/guidance. Subscription ownership is not verification of each field, historical vintage, license or cloud-processing right. No private account or licensed dataset was inspected for this document.

### What public documentation establishes

Massive's guidance endpoint lists current/prior ranges, fiscal identifiers, accounting methods, release type and optional consensus values. It advertises updates every two hours. Its announcement time and last-update fields do not, by themselves, establish an immutable record of what a subscriber could have received historically [S2]. Sharadar distinguishes as-reported AR observations from most-recent MR observations [S3]. QuantConnect data access and licensing depend on the dataset and use [S4].

| Input | Intended use | Required evidence before use |
| --- | --- | --- |
| Guidance | Event and comparable predecessor | Immutable payload versions; issuer/fiscal identity; units and accounting basis; source and receipt clocks |
| QC market/reference data | Orders, quotes, prices, actions and security lifecycle | Exact entitlement, mapping/delisting semantics, history coverage, price normalization and engine configuration |
| Sharadar SF1 | Availability-audited descriptive fundamentals | AR rather than later MR vintage; actual usable time; no future filing joins |
| Dated security/sector reference | Primary-share eligibility and sector limit | Historically valid permanent-ID mapping and classification, including inactive firms |
| Ratings and guidance consensus | Context only in baseline | No trading filter or ranking based on them; missing context remains missing |

Sharadar is not a mandatory profitability screen in this baseline. This avoids mixing a second stock-selection hypothesis into the first test. A current ticker table must not be treated as a historical security master. An Earnings subscription, full analyst-estimate history, an earnings calendar and ETF holdings are not assumed to be owned.

### Two evidence tracks that must stay separate

**Historical reconstruction:** preserve the retrieved vintage and label `point_in_time_data=false` unless original availability is actually proved. A three-session delay can reduce timestamp sensitivity; it cannot reverse overwrites, recover deleted records or establish the original predecessor. Show an accessible-current-row view and a conservative last-update-censored view. Neither can establish confirmation merely by being labelled a holdout.

**Prospective capture:** after separate authorization, record raw content, UTC durable receipt, ingestion completion, all observed versions and an append-only audit trail. Seed the starting corpus as baseline state; old rows discovered during initialization are not fresh trade signals. Never backdate a decision to an issuer's announcement time or a provider's later reconstruction.

**Stop condition:** unresolved rights, ambiguous identity, absent comparable prior guidance or missing reliable availability blocks the affected use. Report lost coverage. Do not silently switch sources, drop a failed company, or accept current metadata as historical evidence.

<!-- pagebreak -->

## 3. Exact event and signal definition

### Eligible guidance pair

Use full-year (`FY`), USD, primary guidance only. Require adjusted EPS and GAAP revenue in both the new disclosure and its immediate comparable predecessor. Both releases must refer to the same permanent issuer, fiscal year/end date, currency, units, share/split basis and accounting definitions. A changed fiscal year length, acquisition-related scope change without comparable figures, or changed adjustment definition is ineligible.

The predecessor must be an earlier management disclosure, not a subsequently edited number. Its content and ordering require an immutable prior capture or verified original disclosure. Vendor previous-value fields alone are insufficient for confirmation. Historical use without that proof stays explicitly exploratory.

For each metric, require finite numeric lower/upper bounds with lower <= upper. A single point can be represented as equal bounds only when the source explicitly describes it as a point. Do not invent a missing bound. Prior revenue midpoint must be positive; prior adjusted EPS midpoint must be at least USD 0.25 per share on the comparable share basis. This chosen floor excludes unstable near-zero percentage changes and turnaround cases.

### Formula and pass rule

For revenue R and adjusted EPS E, calculate:

- `R_old = (R_old_low + R_old_high) / 2`; `R_new = (R_new_low + R_new_high) / 2`.
- `E_old = (E_old_low + E_old_high) / 2`; `E_new = (E_new_low + E_new_high) / 2`.
- `r = R_new / R_old - 1`; `e = E_new / E_old - 1`.
- Qualify only if `r >= 0.02`, `e >= 0.05`, `R_new_low >= R_old_low` and `E_new_low >= E_old_low`.

Compute authoritative thresholds with exact decimal arithmetic. Do not round a sub-threshold event into eligibility. Both scheduled and preliminary disclosures are included; release type is a descriptive tag, not a second optimized strategy.

### Synthetic example - arithmetic only

Revenue guidance changes from USD 980-1,020 million to USD 1,030-1,070 million. Its midpoint rises from 1,000 to 1,050: **+5%**. Adjusted EPS changes from USD 2.00-2.20 to USD 2.20-2.40. Its midpoint rises from 2.10 to 2.30: **+9.5238%**. Both lower bounds rise, so the event passes the signal rule if all other gates pass. This is not a real company, backtest or return example.

### Revisions, duplication and expectations

One economic disclosure creates at most one candidate per issuer. Collapse proven duplicate delivery by disclosure identity; quarantine inconsistent duplicates. If multiple FYs are updated, use the nearest unexpired fiscal year, with its same-period predecessor. A same-ID metadata edit is not fresh management news. Retain the earlier observed version and record any later correction; never rewrite past decisions. A verified correction or withdrawal received before a fill cancels any now-invalid pending candidate/order, including after the usual entry cutoff. It cannot accelerate or create a positive entry. If a fill races cancellation, retain it and apply the exit/reconciliation rules.

A raise relative to prior guidance may still disappoint market expectations. Report the feed's consensus context only when comparable and available as of the decision; do not retrospectively exclude disappointing raises. Without separate earnings-surprise controls, results cannot prove an effect independent of simultaneous earnings news.

<!-- pagebreak -->

## 4. Eligibility and decision clock

### Stock eligibility at the decision cutoff

- Primary common shares listed on NYSE, Nasdaq or NYSE American; exclude OTC, ADRs, funds, preferreds, warrants, units and REIT/FFO cases. Require a dated, unambiguous permanent-security mapping.
- Previous regular-session raw close at least USD 5; at least 60 completed regular sessions of listing history; all last 20 regular sessions have valid prices and volume.
- Trailing 20-session average daily dollar volume (`ADV20`) at least USD 20 million, calculated from each session's contemporaneous raw close times volume. Exclude the entry session from that calculation.
- Historically valid sector classification is required for the sector ceiling. Missing identity, classification, price or liquidity creates a named refusal, not a guessed default.
- Formerly listed firms remain in the dated opportunity set. Mergers, bankruptcies and delistings are handled economically; surviving names alone are never the universe.

### One conservative clock for the baseline

Use the pinned NYSE regular-session calendar and `America/New_York` for session decisions; store source/receipt instants in timezone-aware UTC. Let D be the verified disclosure calendar date and E be the **third NYSE session strictly after D**. This convention is deliberately conservative and is not an assertion of historical availability.

For each prospective session, freeze inputs at **18:00 New York time on the preceding NYSE session**. An event can enter only when its raw payload, predecessor, mapping and all required inputs were durably received and validated by that cutoff, and the entry session is E or later. Date-only ambiguity uses the later defensible date; unresolved dating refuses. A verified publication timestamp must also precede the cutoff.

First receipt must occur by the cutoff for the third entry opportunity, E+2 sessions; otherwise record `stale_event` and do not trade. Use the first eligible opportunity within E, E+1 or E+2. There is only one entry-order attempt per event; an unfilled or refused entry is not retried. Missing polls delay eligibility and never cause backdated fills.

Historical reconstruction substitutes only its declared approximation for absent historical receipt evidence. For its conservative view, an explicit-offset last-update timestamp must be no later than the decision cutoff; a date-only last-update must be strictly earlier than the cutoff's calendar date. That censor may remove much of the archive. Preserve both the rejection ledger and the explicit non-PIT label.

### Deterministic selection

At each cutoff, ignore events for an issuer already held or with a pending order; do not add, reset the holding clock or pyramid. For simultaneous eligible entries, sort by earlier eligibility session, then larger revenue revision, then larger EPS revision, then permanent security ID. Admit in that order while risk and cash capacity remain. Capacity-refused candidates are logged and expire; they are not queued until a convenient future price.

No intraday news-chasing, analyst/LLM interpretation, alternative threshold grid or one-week/eight-week search is included. A faster clock or new horizon would be a new, registered candidate.

<!-- pagebreak -->

## 5. Portfolio, orders and exits

All settings here describe a **simulated research sleeve**, not changes to application policy or permission to place an order. Initial NAV is USD 100,000; no deposits, margin or short positions. Idle cash earns zero in both the strategy and primary comparator, with that conservative convention disclosed.

### Entry and capacity

Target each new position at the smaller of 5% of current sleeve NAV, USD 5,000, 0.1% of ADV20, remaining 50% gross capacity, remaining 15% sector capacity and available cash after reservations. Deduct worst-case pending-buy notional from issuer, sector and gross headroom as well as cash; reserve fees separately. Recheck capacity before each order. Round shares down; zero shares means refusal. Use settled cash only under the simulated account's dated settlement rules; do not spend unsettled proceeds or assumed fills. Release unused reservations exactly once after confirmed terminal fill/cancellation, never on a cancel request alone.

At 10:00 New York time, use the latest completed quote no older than 60 seconds. Require positive bid/ask, ask >= bid and full spread/midpoint <= 0.50%. Submit one marketable-limit buy with limit 1% above that ask, sizing against the limit and worst-case fees. Fill only from subsequent market data, never the bar/quote used to decide. Cancel the unfilled remainder at 10:05; retain a partial position without topping up. Missing quotes, a halt or insufficient cash means no entry.

Simulation fills may consume at most 1% of each subsequent minute's reported volume and the remaining 0.1% ADV20 daily participation allowance. The model must preserve partial fills, limit-price protection, cash reservations and cancellation ordering. Those are implementation requirements to validate, not assumed QC defaults.

### Exit priority and accounting

1. Mandatory corporate-action or delisting handling; no invented last-close liquidation for an untradeable security.
2. Program drawdown stop: after a daily-close NAV drawdown of 15% from its high-water mark, cancel entries and request liquidation at the next executable regular session. New exposure stays disabled; no discretionary restart. Continue recording cash, unresolved positions and comparator NAV through the frozen study end. This stops trading, not observation or the final-look calendar.
3. Position risk stop: after a regular close at or below 90% of its split-adjusted entry cost, exit at the next session's 10:00 execution opportunity. This is not a guaranteed 10% loss limit; overnight gaps can lose more.
4. Guidance invalidation: a later received, comparable disclosure lowering either midpoint, or a verified withdrawal/correction invalidating the qualifying raise, triggers next-eligible-session exit after its receipt cutoff.
5. Time exit: sell at 10:00 on session 21 when entry is session 1, for 20 regular-session holding intervals absent an earlier exit. No take-profit or trailing-stop variant.

Exits use market sell orders, subsequent executable prices, realistic costs and capacity-aware partial fills. If a security is halted, keep the exposure and unresolved exit visible until executable or settled by a verified terminal action. At the daily cutoff, drift above position/sector/gross ceilings schedules risk-reducing trims at the next execution opportunity. Process exits and trims before entries; do not treat scheduled proceeds as settled cash. Valuation gaps pause new entries, but must not suppress legitimate exits.

Keep dividends, splits, fees, partial fills, open positions and receivables in NAV. Do not count adjusted-price dividends again as cash. Retain every residual position at a study boundary. If its terminal accounting cannot be resolved inside the authorized window, label the study incomplete/blocked; do not drop it, invent a liquidation or read protected later dates to finish it.

<!-- pagebreak -->

## 6. Order-based QuantConnect evaluation

QuantConnect Cloud is the proposed authoritative execution environment for this candidate, subject to explicit scheduling, rights and run authorization. Local synthetic fixtures establish software behavior only. No price-vector approximation is substituted for the primary order-based result. Any diagnostic exception must be documented before it runs.

### Execution realism and costs

Use regular-session minute trade and quote data where the audited subscription supports it. Bind the exact engine version, brokerage/account model, normalization mode, fill model, fee model and settlement behavior. QC documents separate fill and slippage models; defaults must be inspected rather than presumed realistic [S5, S6].

Proposed commission floor per filled order is the greater of USD 1 and USD 0.005 per share, accrued across partial fills with the minimum charged once per order. Apply a higher audited schedule if appropriate, and separately include applicable historical fees. For execution price, use the available ask for a buy or bid for a sell plus **5 basis points adverse impact per side**. A limit order fills only if the resulting price respects its limit. Do not add the quoted spread twice. Stress the same frozen signals with 15 basis points adverse impact per side and doubled commission floors. These are disclosed modeling assumptions, not measured transaction costs.

The base and stress executions are both preregistered and counted. Stress cannot replace a failed primary. If quotes or terminal outcomes cannot support this model, stop; a trade-bar fallback requires a separately frozen exploratory specification, not an invisible downgrade. Subscription and cloud costs are reported separately, including their breakeven drag at the owner's eventual capital size; taxes are excluded and disclosed.

### Comparators and diagnostics

**Primary:** a separate order-based SPY portfolio starts with identical cash. Each actual strategy entry fill opens a comparator tranche using the same allocated dollar budget at the next equivalent execution opportunity; each partial/final strategy exit closes the corresponding fraction of that tranche. Apply comparable costs, corporate actions and idle-cash accounting. Preserve unmatched/refused comparator fills and rounding cash; do not discard their dates. Wealth divergence can leave the comparator unable to fund a later entry. Any funding, timing or partial-fill mismatch beyond whole-share rounding blocks confirmatory interpretation; no cash injections or selective omissions repair it. Audit schedule parity before analysis, and test feasibility before freezing confirmation. This matches intended entry budgets and holding schedules, not exact beta or continuously identical exposure.

**Descriptive only:** SPY buy-and-hold, cash, gross versus net strategy returns, sector contributions, concentration, turnover, average exposure, drawdown, fill rate, rejected/underfilled opportunities, holding-time distribution and event-conditioned outcomes. Any sector/factor-adjusted diagnostic requires its own audited data and preregistration; none rescues the primary. Outperforming matched SPY alone is not proof of beta-neutral alpha.

### Each run's evidence package

Record source/version hashes, source rights, availability labels, universe/mapping versions, code commit, configuration hash, calendar/version, research-look receipt, project/compile/backtest IDs, order/fill and refusal ledgers, all costs, daily strategy/comparator NAV and unresolved terminal cases. Disclose which QC-hosted inputs cannot be independently content-hashed.

At most **three unsuccessful QC launch attempts per distinct candidate**, including compile/runtime failures. After the third, stop, tell the owner and use authenticated controllable Mia only if available. Retrieve and diff any Mia-modified source; port verified candidate-specific fixes only. A completed cloud run proves execution completion, not valid economics or acceptance. Log every attempt; a bug-fix rerun does not erase an outcome look.

<!-- pagebreak -->

## 7. Research design and protected evidence

### Existing project boundaries

The local Action Plan reserves a fixed four-lane family, total two-sided FWER 0.05 and permanent maximum 0.0125 per named lane, without redistribution. **This proposal has no allocation in that family.** Its relationship to the four lanes, Fundamental Inflection and prior research must be decided before any new confirmatory look. Calling it a separate family does not automatically justify another 0.05 budget.

The existing shared final holdout is **2027-09-01 through 2029-08-31**. It cannot be borrowed. Until owner-coordinated boundaries are resolved, this proposal also quarantines outcomes from **2026-09-01 onward**, which overlap existing lane validation and future reserved periods. Nothing here silently shifts those dates or allocates the remaining years. Rights to collect raw prospective inputs are a separate decision from rights to inspect their outcomes.

### Proposed sequence of evidence

**A. Structural audit, no outcomes.** Measure field coverage, identity ambiguity, version stability, predecessor comparability, timing and event frequency under a specifically authorized scope. Do not join future prices. Audit results may reveal that this hypothesis cannot be evaluated with the present subscriptions.

**B. Historical exploration, after permission.** Use only owner-approved dates ending no later than 2026-08-31. Propose an earliest common-data date of 2013-01-01, subject to measured coverage/provenance; earlier rows need a new audit of backfill semantics, not just a coverage check. If there are at least six usable years, use the first 60% of eligible calendar sessions for implementation calibration and the remaining 40% for a sealed historical diagnostic. Fix the split without looking at returns. With fewer years, stop to reassess feasibility; this planning floor is not a statistical sufficiency claim.

Freeze a last-entry cutoff 40 sessions before each partition end and a 40-session no-entry embargo after the development partition. Assign issuer/event groups by their information intervals; do not randomly split ticker rows. Retain all resulting positions, even if a halt makes an exit cross the boundary. An unresolved terminal case blocks the affected study instead of being purged based on its realized outcome; no boundary extension may open protected data. Dates previously seen by this project, current-vintage reconstruction and unknown prior access mean that even a sealed diagnostic remains exploratory unless an independent audit proves otherwise.

**C. Genuine confirmation, separately authorized.** After an exact specification/code/data freeze, use a prospectively captured, untouched period that does not conflict with reserved evidence. Start/end dates, total family allocation, sample-size rule and result-access controls must be signed before outcomes are visible. This document does not assign a calendar date because doing so could spend another lane's protected evidence.

### One primary candidate; no null rescue

One threshold pair, one eligibility clock, one 20-session horizon and one portfolio rule form the primary. Every additional performance-bearing variant or outcome look enters the permanent ledger. Alternative delays/costs are frozen diagnostics, not free new winning opportunities. Do not add analyst confirmation, buy-the-dip filters, alternative universes or new exit rules after seeing a null and call it the same test.

Each material source, strategy or producing-code change starts a new evidence epoch. Preserve previous nulls, errors and refusals. Never pool changed epochs as if they were one frozen candidate.

<!-- pagebreak -->

## 8. Metrics, sufficiency and go/no-go gates

Let `x_t = strategy_net_return_t - matched_SPY_net_return_t`, measured on the same daily calendar and full initial-sleeve NAV conventions, including idle cash and costs. The primary estimate is `252 * mean(x_t)`, an annualized arithmetic excess return, not CAGR. Also report each portfolio's CAGR, volatility, maximum drawdown and cash utilization.

Use a predeclared calendar moving-block bootstrap: proposed block length 60 trading sessions, 10,000 resamples and fixed seed 6102026. Resample paired daily outcomes together; do not treat overlapping trades as independent observations. Before confirmation, development-only diagnostics must establish that the block choice handles serial dependence and long unresolved exits. If it fails, re-freeze the method before opening confirmation. Report independent calendar blocks, distinct issuers and event-date clusters; ticker rows are not the independent sample size.

### Power and economic relevance

Propose a minimum useful effect of **3 percentage points annualized net excess on total sleeve NAV** and 80% power to reject zero excess at that true effect and the eventual family-adjusted significance level. This is statistical-rejection power, not an 80% chance of passing every promotion gate: an unbiased point estimate at the +3 pp boundary exceeds that boundary only about half the time. Separately simulate full-gate operating characteristics. Estimate required calendar length from development-only dependence, event frequency, costs and effect injections, with independent review. Freeze the result and final-look date before confirmation. Neither these thresholds nor a convenient trade/day count is an expected return or proof of sufficiency.

If the required untouched period is unavailable or impractically long, report **insufficient evidence / economically impractical**. Do not lower the hurdle after viewing returns. Monitoring before the final look is restricted to integrity and safety; performance-based stopping or repeated inference requires its own sequential error-control contract.

| Gate | Requirement | Failure disposition |
| --- | --- | --- |
| Data validity | Rights, comparable versions, dated identity, receipt/availability and terminal outcomes verified for claimed evidence class | Invalid or blocked; not a market null |
| Software validity | Focused safety fixtures and independently reviewed order/NAV reconciliation; exact QC run completes | Correct verified defects within attempt/look limits |
| Historical feasibility | Frozen primary shows positive net matched-market excess under both declared historical views; usable coverage/power | Valid nonpositive result closes GDR-1.0; uncertainty is inconclusive |
| Confirmation | Sufficient approved untouched sample; family-adjusted two-sided interval entirely above zero; primary point estimate at least +3 pp/year | Null or insufficient; no automatic retuning |
| Robustness and risk | Stressed net excess positive; base maximum drawdown <=15%; no unexplained identity, cost, terminal or accounting gaps | No promotion; report the cause |
| Operations | Separate shadow/paper evidence, reconciliation, freshness, risk controls and owner mandate | No capital authority |

Passing these proposed research gates only makes a dossier eligible for independent review and an owner decision. Historical gains alone cannot pass confirmation. A circuit breaker can gap through 15%; exceeding the drawdown criterion is reported as failure, not disguised by reporting only the pre-stop interval.

No return target, Sharpe target or income forecast is promised. Sparse signals and low deployment can make a statistically interesting effect commercially unattractive after subscriptions and taxes.

<!-- pagebreak -->

## 9. Bounded delivery milestones

These are dependencies for a later scheduled project, not instructions to start now. Only the authoritative Action Plan and the owner's exact authorization can activate one. Estimate work after the structural audit; prospective evidence duration is determined by sufficiency, not an engineering deadline.

| Milestone | Bounded work and deliverable | Exit gate / next action |
| --- | --- | --- |
| GDR-0: design freeze | Resolve section 11 decisions; freeze semantic rules, rights scope, family/look policy and evidence dates | Independent specification review plus explicit owner freeze |
| GDR-1: source audit | Authorized zero-outcome field/version/identity audit; immutable capture design and rights matrix | No silent PIT assumptions; owner decides historical viability and collection authority |
| GDR-2: deterministic implementation | Isolated research-only contracts, event state machine, portfolio simulator and QC adapter; synthetic fixtures | Focused checks, independent review and counter-review; no outcome launch implied |
| GDR-3: historical feasibility | Authorized order-based base/stress studies, fixed comparisons, counted looks and candid data limitations | Stop on valid null; otherwise freeze confirmation design and power requirement |
| GDR-4: prospective evidence | Separately authorized capture, shadow simulation and untouched confirmation under frozen access controls | Sufficient evidence and independent statistical/technical review; otherwise remain blocked |
| GDR-5: paper readiness | Separate owner-approved paper scope, exact account mode, bounds, reconciliation, kill switch and incident runbook | Paper observation is operational evidence, not live permission |
| GDR-6: capital decision | Human review of all evidence, costs, drawdown tolerance and household-money separation | A separately scoped mandate is required; no automatic live deployment |

### Isolation and review workflow

No new lane/worktree is created by this document. If implementation is later activated, first have the owner designate its branch/worktree and permitted file scope. Proposed future ownership is a dedicated guidance research package, its tests and lane record; do not modify assistant execution behavior or another strategy to implement this hypothesis. Reuse shared helpers only after verifying exact accepted contracts; shared fixes require separate routing.

Apply the repository's generic independent-review workflow unless the owner explicitly grants this candidate its own same-branch exception. The existing four lanes' exceptions and provider/QC permissions do not transfer. At each bounded milestone, record the exact commit range, findings/dispositions, corrections, checks, exclusions, gate status and next permitted action.

Codex runs relevant focused/compilation/import-boundary/document checks; a complete suite is not run without owner authorization under the machine-wide agreement. Independent review follows its applicable full-suite obligations. Prioritize proving the authorized order-based backtest actually completes; a notebook plot is not an execution acceptance test.

### Eventual report package

Deliver the frozen specification, rights/availability matrix, source manifests, candidate/look ledger, issuer opportunity and refusal ledgers, reproducible QC source/configuration, orders/fills/cash/NAV reconciliation, base/stress/comparator report, power/sufficiency assessment, reviewer dispositions and a one-page owner decision memo. Preserve zero-signal days, capacity failures, unresolved exits and every unsuccessful run.

<!-- pagebreak -->

## 10. Required checks and principal risks

The following are future acceptance tests, not tests claimed to have run during this planning task. Each material correction needs a regression case that fails without the correction.

| Area | Required cases |
| --- | --- |
| Signal arithmetic | Exactly at and just below 2%/5%; EPS floor; negative/zero values; non-finite numbers; inverted/missing ranges; point guidance |
| Comparability | Wrong FY, changed basis/units/currency, split, fiscal-year transition, acquisition scope, predecessor recorded after event |
| Event identity | Same-ID edit, duplicate delivery, conflicting duplicate, ticker reuse, simultaneous FY disclosures, correction/withdrawal |
| Availability | Delayed receipt, ingestion after cutoff, date-only clock, daylight-saving transition, holiday/weekend, late initialization/backfill |
| Portfolio | Zero affordable shares, fee reservation, sector/gross drift, unsettled cash, multiple same-day events, existing position, partial fill/cancel |
| Exit lifecycle | 20-session boundary, halt, gap through stop, partial exit, invalidation after cutoff, pending sell, delisting/merger proceeds |
| Economics | Split/dividend not double-counted; no same-bar fill; spread once; fees per order; impact/limit interaction; unresolved terminal marks |
| Research controls | Protected-date refusal, immutable look receipt, changed-epoch refusal, contaminated history labels, comparator parity and missing rows |
| Boundaries | No execution-capable import path or broker access from research; malformed/missing input refuses safely |

### Risks that can defeat the strategy

**Information already priced:** a delayed feed and conservative entry may miss the entire adjustment. That is a possible null, not a reason to move fills backward.

**Guidance is not surprise:** an upward revision may still be below expectations; scheduled releases also bundle earnings and other news. The baseline evaluates a tradeable event package, not a clean causal attribution to guidance.

**Selective disclosure and coverage:** companies that guide differ from those that do not. Small samples, sector clustering, missing predecessors and survivorship can exaggerate an apparent edge. Report the entire eligibility/refusal funnel by year and issuer status, including losses of coverage.

**Price gaps and concentration:** ten 5% positions can still share one economic driver. Sector caps and 50% gross exposure do not guarantee a maximum loss. Halted positions remain exposures, and risk reduction must not be blocked by missing advisory output.

**Historical revisions:** a vendor's later corrected record can look like perfect foresight. Delays and censored views are sensitivity disclosures, not a substitute for immutable capture.

**Research overfitting:** choosing the best threshold, horizon or comparator after results creates more tests. A rejected candidate stays rejected; a materially new hypothesis requires a new plan and authorization.

**Cost versus capital:** a strategy that works before subscriptions can fail at small account size. Report annual incremental fixed research costs divided by the intended account capital, separately from trade costs. No minimum viable capital is asserted before that calculation.

<!-- pagebreak -->

## 11. Owner decisions, provenance and sources

### Decisions required before activation

1. Approve or revise the single baseline: FY-only, adjusted EPS/GAAP revenue, 2%/5% raises, EPS floor, third-session timing and 20-session holding. Changes occur before outcome access.
2. Confirm risk preferences and illustrative portfolio settings. USD 100,000 is a modeling scale, not a requested deposit or recommendation to invest that amount.
3. Authorize a specifically bounded structural data/rights audit, identifying local-only versus third-party processing. Do not assume all QC data or earnings products are licensed.
4. Resolve statistical-family membership, total allocation, all permitted looks and independence/contamination accounting. No budget exists for this candidate today.
5. Approve non-conflicting evidence windows and outcome-access controls. Existing validation and final holdout dates remain protected.
6. Decide whether and when to schedule implementation, identify its worktree/file ownership and reviewer, then separately authorize any capture, QC run, paper stage or capital use.

### Repository basis and limitations

Prepared against local base **e1a0efe6f78f2daf20c1af952c1bc22c9c25c22e**. At inspection, local main was 393 commits behind locally recorded origin/main **ff0bb2098d1a06184d41bf1dcc1bb113aaac2174**. No fetch or sync was performed for this task. This document does not claim to describe the latest global lane status. Reconcile current governing contracts before activation.

Repository references are relative to its root:

- `CLAUDE.md` and `AGENTS.md`: safety, workflow and research discipline.
- `docs/ACTION_PLAN_2026-08-20.md`: scheduling, four-slot allocation and protected dates.
- `docs/Plan/README.md`: queued-plan lifecycle; this plan is not active.
- `research/analyst_revisions_v2/accepted_risk_input_pair.py`: existing third-session guidance convention and non-pristine historical-vintage warnings; reference only, not permission or a shared-code change.
- `docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md`: measured overwrite, update-clock, identity and correction limitations; later entries supersede earlier duplicate-handling descriptions.
- `docs/Strategy Description/FUNDAMENTAL_INFLECTION_ALPHA_FOUR_VERSIONS_BLUEPRINT_EN.md`: related, separately unreviewed multi-factor proposal.
- `docs/research/alpha-result.md`: prior null research; it supplies no positive evidence for this candidate.

### Public primary sources - checked 6 October 2026

- **S1.** Ng, Tuna and Verdi, *Management forecast credibility and underreaction to news* (2013), [MIT author-manuscript record](https://dspace.mit.edu/entities/publication/d6ee4b92-1865-4304-97bb-965e56cdf26e). Supports motivation only, not the thresholds, horizon or expected profit.
- **S2.** [Massive: Corporate Guidance](https://massive.com/docs/rest/partners/benzinga/corporate-guidance). Public schema and advertised delivery cadence; not purchase-specific rights or historical first-receipt proof.
- **S3.** [Sharadar: Fundamentals](https://sharadar.com/docs/fundamentals). As-reported versus most-recent dimensions; actual account access and vintage use remain to be audited.
- **S4.** [QuantConnect: Dataset licensing](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing).
- **S5.** [QuantConnect: Trade-fill model concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts).
- **S6.** [QuantConnect: Slippage model concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts).

**Current disposition:** plan delivered for discussion; no implementation, source acquisition, empirical result, independent acceptance, paper pilot or live authority is claimed. The next permitted action is owner review of the proposed specification, not an automatic backtest.
