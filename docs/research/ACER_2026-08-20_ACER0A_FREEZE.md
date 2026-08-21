# ACER-0A freeze — stock-level signal validation (ACER-2)

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

Governing contract shape: `docs/reference/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md`.
Source specification: `docs/reference/analyst-consensus-etf-strategy.pdf`
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
  accidental launches — is appended to `docs/alpha-result.md` as a new
  `R-nnn` entry with full identity, and counts permanently. Records are
  never removed.
- A corrected rerun may repair **code** but may not change the hypothesis,
  parameters, universe, controls, or gates. Each corrected rerun is itself a
  recorded look; repairing a bug does not restore the budget.
- The confirmation period stays untouched until the single frozen
  confirmation pass. It is not inspected, plotted, or summarized before then.
- The owner has not yet ruled whether an error or refusal merely consumes its
  slot or ends ACER-2. That failure rule, the exact development/confirmation
  date boundaries, and the confirmation pass rule are open item ACER-0A.9.
  Therefore this section does not authorize a third "corrected" run or any
  attempt to replace a consumed slot.

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

- **Engine: local LEAN is the authoritative path.** ACER-2 must be designed
  so that cloud execution is optional, never required.
- **Reconstructable Benzinga rows must not be uploaded to QuantConnect**
  unless the owner separately provides explicit evidence that the applicable
  terms permit that third-party transfer.
- **QuantConnect access is authorized for read-only symbol-mapping work
  only**, to establish issuer identity. During that work: no Benzinga upload,
  no price or outcome join, no backtest launch, and no research look.
  Provenance is preserved, and ticker-reuse or rename ambiguity produces a
  refusal rather than a guess.
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

| ID | Open item | Why it cannot wait |
|---|---|---|
| **ACER-0A.1** | Numeric rule for "not driven by one year, sector, or a small number of securities" (section 3.3). | Left unquantified, this becomes a judgement made while looking at the result, which is the exact failure mode the freeze exists to prevent. A concrete proposal is offered below and requires owner confirmation. |
| **ACER-0A.2** | The standardized-surprise formula, deliberately deferred by the owner until after the earnings audit. | It is a control definition; choosing it after seeing how it affects the IC would contaminate the primary statistic. |
| **ACER-0A.3** | Data source for the **value** control under local LEAN. | Value needs fundamentals. The ratings and earnings expansions do not supply them, and it is not yet established that local LEAN has usable point-in-time fundamentals on this machine. |
| **ACER-0A.4** | Local LEAN data availability for prices, corporate actions, delisted securities, and the trading-session calendar that defines "21/63/126 sessions". | The engine ruling makes local LEAN authoritative, but the local data inventory has not been measured. If it is incomplete, ACER-2 cannot run locally as designed. |
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
