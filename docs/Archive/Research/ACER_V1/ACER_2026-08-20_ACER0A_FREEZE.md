# ACER-0A freeze — stock-level signal validation (ACER-2)

Archive status: **SUPERSEDED by Analyst Revisions V2 on 2026-08-25; retained
only to reproduce V1 decisions and existing capability tests.**

Status: **PARTIAL FREEZE by owner decision, 2026-08-20
(America/Los_Angeles; 2026-08-21 UTC).** The owner decisions recorded below
are frozen for **ACER-2 only**, but this is **not yet an executable
preregistration**. Section 9 names the remaining definitions. Until every one
is frozen in writing, ACER-2 must refuse any join between real signals and
real outcomes and must not consume either real-outcome execution slot.

Scope split, per the owner's decision: **ACER-0A** freezes the decisive
stock-level test. **ACER-0B** — the contingent ETF-level ACER-3 test —
is deliberately NOT frozen, so that ETF benchmark and investability choices
are not forced before a stock-level signal is shown to exist. ACER-0B is
authorized only by a separate owner act, and only if ACER-2 passes.

Governing contract shape: `docs/Archive/Plans/ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md`.
Source specification: `docs/Archive/Reference/analyst-consensus-etf-strategy-v1.pdf`
(SHA-256 `3700ab4bb64dfd6e29e5f8bbc2b7e3dd3fa089050b25cbb5e315450a8d86cf23`).
Where they differ, this freeze governs for ACER-2.

**Nothing here authorizes** a data purchase, a price or outcome join, a
backtest, a QuantConnect upload, a deployment, an epoch action, or any live
or paper order.

---

## 1. The frozen hypothesis

Do stock-level analyst recommendation revisions carry **incremental
out-of-sample cross-sectional information** about subsequent residual
returns, after controlling for momentum, earnings surprise, size, liquidity,
volatility, value, and sector?

**Expected sign, frozen in advance: positive.** Upgrades (positive notch
change) predict higher subsequent residualized returns; downgrades predict
lower. A result of the opposite sign at any magnitude is a **failure**, not
a discovery, and may not be reinterpreted as a contrarian signal within
ACER.

## 2. The family: six cells

| Dimension | Frozen values | Count |
|---|---|---:|
| Encoding | (a) ordinal rating-notch change; (b) direction-only action sign | 2 |
| Decay half-life | 21, 63, 126 trading sessions | 3 |
| Aggregation | coverage-neutral per-firm mean **only** | 1 |
| Outcome horizon | 21 trading sessions | 1 |
| **Family size** | 2 x 3 x 1 x 1 | **6** |

**Raw sum is deliberately excluded as a second aggregation.** It mainly
rewards analyst coverage — a large-cap with forty covering analysts
accumulates a larger sum than an identical signal on a thinly covered name —
so it measures coverage as much as revision, and it would double the family
for that. Coverage enters the study as a control, not as a second scoring
rule.

**Primary cell (one, designated in advance):** ordinal notch change,
63-session half-life, per-firm mean, 21-session outcome horizon.

**Primary statistic:** out-of-sample residualized cross-sectional
information coefficient, computed on observations the model did not see.
In-sample correlation is not a pass under any circumstance.

**Family threshold: Bonferroni 0.05 / 6 = 0.008333.** The primary cell must
clear the *corrected* threshold, not the uncorrected 0.05. This is
deliberately conservative: designating a primary cell would justify testing
it at 0.05, and the owner chose to apply the family correction to it anyway.

## 3. Pass and fail rules

ACER-2 passes only if **all** of the following hold:

1. The primary cell clears p < 0.008333 on the primary statistic;
2. with the frozen expected sign (positive);
3. and the result is **not driven by a single year, a single sector, or a
   small number of securities** (see the open item in section 9 — this
   condition is frozen in principle but its numeric operationalization is
   not yet fixed, and must be fixed before the development run);
4. using out-of-sample block significance from this repository's existing
   toolkit, never pooled, row-level, or by-date-only significance.

The five secondary cells are **descriptive and robustness evidence only**.
An isolated secondary-cell pass does **not** override a failed primary cell,
and may not be promoted to primary after the fact.

**A null primary result closes ACER.** No post-result tuning of thresholds,
decay half-lives, aggregation, universe, horizon, or controls is permitted.
A null is a valid result and is recorded as such.

## 4. Provisional run budget and look accounting

| Category | Budget |
|---|---|
| Synthetic/local tests that never join real signals to real outcomes | Unlimited |
| Frozen walk-forward / development execution against real outcomes | **One slot**, after the preregistration becomes complete |
| Untouched confirmation execution | **One slot**, launched only if the fully specified development gate passes |
| ACER-3 executions | **Zero** until ACER-2 passes and the owner separately authorizes ACER-0B |

Rules:

- Every execution against real outcomes — including refusals, errors, and
  accidental launches — is appended to `docs/research/alpha-result.md` as a new
  `R-nnn` entry with full identity, and counts permanently. Records are
  never removed.
- **No corrected rerun is authorized at present.** With exactly two slots, any
  corrected rerun would be a third real-outcome execution, and whether one may
  ever happen is precisely what ACER-0A.9 has to rule. If the owner does
  authorize one, these constraints apply and are not themselves the
  authorization: it may repair **code** only, never the hypothesis,
  parameters, universe, controls, or gates; it is itself a permanently
  recorded look; and repairing a bug does not restore a consumed slot.
- The confirmation period stays untouched until the single frozen
  confirmation pass. It is not inspected, plotted, or summarized before then.
- The owner has not yet ruled whether an error or refusal merely consumes its
  slot or ends ACER-2. That failure rule, the exact development/confirmation
  date boundaries, and the confirmation pass rule are open item ACER-0A.9.
  Until it is ruled, no third run and no replacement of a consumed slot is
  permitted under any reading of this section.

## 5. Benchmark policy

- **ACER-2 has no index benchmark.** The primary gate is residualized
  stock-level IC after the frozen controls. SPY, QQQ, and ETF baskets are
  not comparators for this milestone, because a cross-sectional IC test does
  not have a market-return alternative.
- **If ACER-2 passes**, ACER-3's primary benchmark will be an equal-weight
  basket of the same eligible ETFs on identical dates. That is recorded here
  as owner intent; it is frozen only when ACER-0B is frozen.
- SPY and QQQ are **secondary descriptive comparisons only**, at every stage.

## 6. Universe — frozen, point-in-time, with named refusals

Eligibility is evaluated **as of each decision date** using only information
available at that time. Every criterion below is a point-in-time test.

- US **primary-listed common stocks only**;
- **excluded**: ETFs, funds, preferred shares, warrants, OTC securities, and
  any security whose mapping is ambiguous;
- **unambiguous point-in-time security identity** is required (see the
  issuer-identity dependency in section 8);
- at least **252 prior trading sessions** of listed history;
- price at least **$5** at eligibility time;
- **60-session median daily dollar volume of at least $10 million**;
- required point-in-time controls present: momentum, earnings surprise,
  size, liquidity, volatility, value, sector;
- **delisted securities remain eligible while they were historically
  listed** — survivorship bias is a disqualifying defect, not a convenience;
- missing or ambiguous inputs produce **recorded refusals**, never silent
  row deletion and never present-day substitution.

ETF AUM, ETF spread, ETF volume, and holdings-coverage thresholds are
**deliberately not frozen here**. They belong to ACER-0B.

## 7. Control dataset — candidate, not yet adopted

**Preferred candidate:** the Massive/Benzinga Earnings expansion.
**Authorized budget: $99 for an initial one-month audit.** The audit is
structural, consumes no research look, and must complete and pass before the
dataset is adopted.

The audit must measure:

1. history depth and completeness;
2. delisted-company coverage;
3. whether `estimated_eps` is the estimate **genuinely available before the
   report**, not a value back-filled afterwards;
4. revisions and restatements, diffed on stable `benzinga_id`;
5. earnings announcement timing and next-session availability;
6. GAAP, adjusted, and FFO coverage and consistency;
7. missingness and issuer-mapping behavior;
8. licence and retention boundaries.

**`eps_surprise_percent` is not trusted automatically.** Actual EPS and
estimated EPS are preserved as delivered, and this project freezes **its
own** standardized-surprise formula after the audit and **before any price
or outcome join**. That formula becomes ACER-0A.2 (section 9).

**Retention interaction, flagged:** a one-month subscription that is then
cancelled raises the same deletion-on-termination question the ratings audit
identified. If the applicable terms require deletion on termination, an
evidence snapshot taken during the audit month may not outlive the
subscription, and any preregistration resting on it must disclose that. The
audit's licence step must answer this explicitly.

## 8. Engine, access, and data-boundary rulings

- **Owner amendment, 2026-08-21 — engine: QuantConnect Cloud is the
  authoritative path for ACER historical and outcome backtests.** Local LEAN
  is retained for implementation, unit/synthetic/integration tests and sample
  validation only. It must not be used for ACER outcome runs. This supersedes
  the earlier local-LEAN-authoritative ruling before any ACER outcome was
  observed.
- **Correction, 2026-08-22 — do not turn a disclaimer into a research ban.**
  Massive's investment-advice disclaimer does not prohibit personal,
  non-commercial ACER research, and its Analyst Ratings documentation
  explicitly names **backtesting rating impact** as a use case.
  (Independently verified 2026-08-22 during the SEP-1 adapter review, at
  <https://massive.com/docs/rest/partners/benzinga/analyst-ratings>: the
  page's use-case list reads "Market sentiment tracking, portfolio alerts,
  backtesting rating impact, trend analysis", and the page itself carries no
  licensing or restriction language — the restriction question lives in the
  ToS/order-form documents, exactly as this bullet states. Vendor pages
  change without notice; re-verify or preserve bytes before relying on this
  quote in a preregistration.) Testing an
  investment strategy therefore does not by itself require written
  permission. Before any ratings representation is processed through
  QuantConnect custom data, verify the order form and additional terms that
  actually govern this purchase. They may already permit the intended use;
  this repository has not inspected them and must not claim either permission
  or prohibition. A separate permission letter is needed only if the
  applicable terms require one or leave a material ambiguity the owner elects
  to resolve that way. Raw licensed rows remain uncommitted, and no upload is
  authorized by this correction. QuantConnect's separate **Download** licence
  distinction does not answer the terms governing owner-supplied custom data.
  See its official [Cloud and Download licence distinction](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing).
- **Scope limit, not a green light: QuantConnect work is confined to
  read-only, zero-outcome structural activity** — issuer/symbol mapping, and
  measuring the account's dataset entitlements, coverage and field semantics.
  **This bullet bounds what an authorized session may do; it is not itself the
  authorization to start one.** Action Plan §7 item 1 still lists "authorize a
  read-only, zero-outcome capability audit of the current Massive and
  QuantConnect accounts" as an open owner decision, and its Massive half has
  no counterpart here at all. Until the owner grants that decision in writing,
  no provider call is authorized under either document. (CDR2-002: the
  2026-08-21 wording chain — a scope widening, then a handoff that read the
  widened scope as permission, then a guard pinning it — converted a pending
  authorization into an assumed one without anyone deciding it. Fail closed
  until the owner says otherwise.) During any authorized work: no Benzinga
  upload, no price or outcome join, no backtest launch, and no research look.
  Provenance is preserved, and ticker-reuse or rename ambiguity produces a
  refusal rather than a guess. (Amended 2026-08-21 with the engine ruling
  above, which made a cloud capability audit the next technical step; the
  prior wording authorized symbol mapping alone and would have forbidden it.
  The prohibitions are unchanged — this widens what may be *measured*, never
  what may be *run*.)
- **SBR-1 remains CLOSED and uninstalled.** Read-only measurement of task
  presence and artifact counts is permitted; if anything is found installed
  or running, it is reported and nothing is changed. (Measured 2026-08-20 —
  see `docs/operations/OPERATIONAL_FACTS.md`: task absent, zero artifacts.)

## 9. Named open items that must close BEFORE the development run

The owner decisions are frozen, but the ACER-2 preregistration is **not
complete**. In particular, naming "residualized IC" does not define a
reproducible statistic, and naming an encoding does not define the rating
scale that produces it. Each item below must be frozen — in writing, with the
owner's agreement — before the single development execution, and none may be
settled after seeing a result.

**Concrete proposals for ACER-0A.5 through 0A.9 are drafted in
`docs/Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`**, including a
five-level rating scale measured against the corpus's 54 distinct rating
strings, the decay and aggregation equations, control and outcome
definitions, the estimation and significance protocol with a frozen bootstrap
seed, and slot-failure rules. **Those proposals are not frozen**; they exist
so the owner has concrete options to accept, amend, or reject. They acquire
authority only when the owner freezes them in writing.

Independent review accepted the proposal set after correction at `1eb3649`.
The review preserved proposal-only status while repairing decay cancellation,
in-sample validation residualization, reversed embargo wording, a bootstrap
algorithm mismatch, incomplete action/state semantics, and incomplete
disclosure of the measured refusal vocabulary. See
`docs/Archive/Review/REVIEW_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`.

| ID | Open item | Why it cannot wait |
|---|---|---|
| **ACER-0A.1** | Numeric rule for "not driven by one year, sector, or a small number of securities" (section 3.3). | Left unquantified, this becomes a judgement made while looking at the result, which is the exact failure mode the freeze exists to prevent. A concrete proposal is offered below and requires owner confirmation. |
| **ACER-0A.2** | The standardized-surprise formula, deliberately deferred by the owner until after the earnings audit. | It is a control definition; choosing it after seeing how it affects the IC would contaminate the primary statistic. |
| **ACER-0A.3** | QuantConnect Cloud source and point-in-time semantics for the **value** control. | Value needs fundamentals. The ratings and earnings expansions do not supply them, and authenticated cloud access does not establish usable point-in-time fundamentals. |
| **ACER-0A.4** | QuantConnect Cloud coverage and semantics for prices, corporate actions, historical eligibility, delisted securities, and the trading-session calendar that defines "21/63/126 sessions"; terminal delisting returns remain a separate explicit requirement. | Cloud is authoritative, but account entitlement, history, delisted coverage and field semantics have not been measured for ACER. QuantConnect's documented delisting event does not by itself prove a CRSP-style terminal delisting return. |
| **ACER-0A.5** | Canonical rating scale and firm-specific aliases: exact notch values; treatment of initiations, reiterations, maintains, missing `previous_rating`, same-day duplicates, and unusable or ambiguous actions. | "Ordinal notch change" and "direction-only sign" are not computable without these rules. Choosing aliases after viewing returns would tune the signal. |
| **ACER-0A.6** | Exact signal construction: availability session, decay equation and age convention, per-firm state/mean definition, minimum coverage, coverage control, and same-security/same-session aggregation. | The six family labels still permit materially different score series and sample sizes. |
| **ACER-0A.7** | Exact control and outcome definitions: momentum, size, liquidity, volatility, value, sector and analyst coverage formulas; normalization/winsorization; forward residual-return endpoints; corporate-action handling; and refusal/missingness rules. | A list of control names is not a frozen design. Different standard definitions can materially change both residuals and eligibility. |
| **ACER-0A.8** | Exact estimation and significance protocol: model form, training window, walk-forward folds, purge/embargo, development and untouched confirmation periods, Pearson-versus-Spearman IC, minimum names/dates, block construction, bootstrap draws/seed/tail, and finite-sample refusal floors. | "Existing toolkit" exposes choices; it does not select them. A p-value is not reproducible until these choices are fixed. |
| **ACER-0A.9** | Execution-slot failure rules and confirmation gate: whether a refused/errored development or confirmation attempt ends the program, exact ledger identity, and what the confirmation run must independently pass. | The current text both caps each category at one and discusses corrected reruns. Without a ruling, an error can be used to justify an undeclared extra look. |
| **ACER-0A.10** | Point-in-time universe implementation details: authoritative security type/listing source, first-252-session convention, price and dollar-volume field/adjustment rules, sector classification availability, and mapping-version identity. | The numeric thresholds are frozen, but the data semantics that decide membership are not. |

**Proposed rule for ACER-0A.1, offered for owner confirmation and not yet
frozen:** the primary cell's result must retain its sign and remain below
the corrected threshold under (a) leave-one-calendar-year-out, (b)
leave-one-GICS-sector-out, and (c) removal of the 1% of securities
contributing the largest absolute share of the statistic. Any exception is a
failure of condition 3. These numbers are a proposal precisely because
inventing them silently would be the defect this item exists to prevent.

## 10. What this freeze deliberately does not do

It does not adopt an ETF-level design, benchmark, or investability rule; it
does not authorize a purchase beyond the $99 audit; it does not authorize
any outcome join or backtest; it does not grant execution authority to any
artifact; and it does not reopen the closed alpha, allocation-policy, or
Strong-Buy programs. It also does not claim ACER-0A is executable: the frozen
owner decisions remain binding while section 9 is completed.
