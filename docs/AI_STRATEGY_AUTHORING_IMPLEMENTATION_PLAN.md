# AI Strategy Authoring, Validation, and Proposal Implementation Plan

Status: execution plan for the development sequence after ML and general
readiness

Prepared: 2026-08-01

Applies after:

- `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`
- `docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`

Companion documents:

- `docs/ML_IMPLEMENTATION_STRATEGY.md` - ML research and architecture
- `docs/ML_IMPLEMENTATION_STATUS.md` - current ML implementation state
- `docs/LIVE_PROMOTION_CHECKLIST.md` - evidence gate for live capital
- `docs/OPERATIONS_RUNBOOK.md` - operational procedures
- `docs/MANDATE.md` - portfolio and risk constraints
- `docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md` - authority boundary

## 1. Objective

Build a governed strategy-development workflow in which:

1. the owner describes a strategy in ordinary language;
2. an LLM converts the description into a structured, reviewable draft;
3. deterministic software validates and compiles the draft;
4. the platform evaluates it with point-in-time data, realistic portfolio
   accounting, frozen baselines, and preregistered evidence rules;
5. the platform reports whether the strategy is invalid, unsupported,
   research-promising, or eligible for paper evaluation;
6. the owner explicitly approves one immutable strategy version for shadow or
   paper operation; and
7. only a separately authorized adapter may turn that fixed strategy's
   output into an approval-gated trade proposal.

This plan makes strategy research easier to express and repeat. It does not
make an LLM a portfolio manager, prove that a backtest will remain profitable,
or permit automatic promotion to live trading.

## 2. Correct architecture for the vision

The desired product flow is realistic, with one important separation of
responsibility:

```text
owner's prose
    |
    v
untrusted LLM-authored StrategyDraft
    |
    v
deterministic validation and owner-visible assumption review
    |
    v
immutable StrategySpec + EvaluationPlan
    |
    v
point-in-time research, backtest, robustness, and evidence dossier
    |
    v
explicit human promotion to shadow or paper scope
    |
    v
deterministic strategy runtime
    |                         approved ML observations, if any
    |                                      |
    +-----------------------> strategy decision
                                           |
                                           v
                              bounded proposal adapter
                                           |
                                           v
                          existing policy and execution gates
                                           |
                                           v
                                exact human approval
```

The ML engine should not own strategies or directly generate executable
proposals. It may produce versioned observations such as volatility,
concentration, or event risk. The strategy runtime may consume only explicitly
approved, serialized observations through a narrow adapter. Proposal creation
belongs to a separate deterministic layer that remains subject to all existing
policy, freshness, approval, reservation, and execution checks.

The LLM is used at authoring time. It is not called while deciding, approving,
or submitting an order.

## 3. What "usable" means

The platform must never return a single vague `usable: true` based on a
backtest. It must report independent dimensions that cannot mask each other:

```text
specification_validity   valid | blocked
data_eligibility         eligible | exploratory_only | blocked
execution_feasibility    supported | degraded | blocked
statistical_evidence     promising | unsupported | insufficient
economic_evidence        promising | unsupported | insufficient
robustness               passed | failed | insufficient
operational_eligibility  research_only | shadow_eligible | paper_eligible
authority                unapproved | approved_shadow | approved_paper | retired
```

No average score is allowed. A strategy is paper-eligible only when every
required dimension independently passes its declared gate. "Promising" means
worthy of additional evaluation, not profitable, safe, or live-authorized.

The user-facing answer should use language such as:

- `invalid specification`;
- `cannot be tested honestly with the available data`;
- `tested and unsupported`;
- `exploratory result only`;
- `research-promising; confirmation required`;
- `eligible for shadow review`; or
- `eligible for paper review; owner approval still required`.

It must not say `confirmed profitable`, `safe to trade`, `guaranteed`, or
`live-ready` merely because historical metrics clear thresholds.

## 4. Non-negotiable boundaries

These rules apply to every milestone:

- LLM output is untrusted input. It has no import, file, network, database,
  broker, proposal, approval, or execution authority.
- The LLM may produce only a draft in the supported schema. It may not emit or
  install executable Python, SQL, shell commands, templates, serialized model
  objects, URLs to load, or arbitrary expressions.
- A strategy must be deterministic once accepted. The immutable specification,
  operator versions, data manifest, cost assumptions, and evaluation plan
  completely determine its behavior.
- No LLM response may write to `assistant/research_findings.json`, promote a
  strategy, update model status, or create a proposal.
- No successful backtest may automatically authorize shadow, paper, or live
  operation.
- No strategy or ML output may weaken a mandate, exposure cap, policy rule,
  kill switch, freshness rule, reconciliation rule, reservation rule, or
  human approval requirement.
- Missing, stale, ambiguous, non-finite, out-of-epoch, or unverifiable inputs
  cause abstention. They never receive a favorable default.
- Risk-reducing sales must not be blocked or delayed by strategy or ML
  unavailability.
- The existing execution path must not import the LLM client, strategy
  authoring code, backtest code, or ML model code.
- Existing ML and investment-committee import-boundary tests remain green.
- Point-in-time-unsuitable data may support software tests or clearly labeled
  exploration, but never confirmation or promotion evidence.
- Every order remains a normal immutable `TradeProposal`, is revalidated with
  a fresh broker snapshot, and requires the exact existing human approval.
- Funded-account influence, including a limited canary, requires a later
  explicit owner request. No implementation agent may infer that authority
  from completion of this plan.

## 5. Delivery rules

Implement one milestone per branch and stop for independent review after each.
The suggested branch pattern is:

```text
user/claude/ai-strategy-as0-contracts-YYYYMMDD
user/claude/ai-strategy-as1-dsl-YYYYMMDD
...
```

Before changing code, the implementation agent must inspect the full milestone,
the current branch, dirty files, existing contracts, and tests. It must reuse
existing hashing, artifact, experiment, money, storage, backtest, proposal,
and policy infrastructure rather than introducing parallel versions.

At every handoff, report:

1. the exact milestone claimed;
2. files and schemas changed;
3. public contracts added or changed;
4. supported and deliberately unsupported strategy concepts;
5. focused and full test results;
6. research-data and elapsed-evidence blockers;
7. any assistant-facing, proposal-facing, or live behavior change; and
8. why the LLM, ML, proposal, and execution boundaries remain intact.

Do not introduce a workflow engine, distributed serving system, feature-store
framework, vector database, or general agent framework. This is a single-owner
local application. A small typed package, content-addressed artifacts, and the
existing SQLite store are sufficient.

## 6. Milestone overview

| Milestone | Purpose | Implementable after prerequisites? | Production behavior |
|---|---|---:|---|
| AS-0 | Freeze vocabulary, authority model, and acceptance contracts | Yes | None |
| AS-1 | Restricted, versioned strategy specification | Yes | None |
| AS-2 | Deterministic compiler, interpreter, and static analysis | Yes | None |
| AS-3 | Point-in-time data-requirement and evaluation-plan compiler | Code: yes; authoritative data may be external | None |
| AS-4 | Honest portfolio backtest and research orchestration | Yes | None |
| AS-5 | LLM strategy-draft authoring and owner clarification workflow | Yes after AS-1..AS-3 | Draft creation only |
| AS-6 | Robustness evaluation and multidimensional usability dossier | Yes; credible results need real data | Read-only report |
| AS-7 | Immutable strategy registry and human promotion workflow | Yes after AS-6 | Registry only |
| AS-8 | Shadow and paper proposal adapter | Requires approved strategy and explicit owner request | Approval-gated paper proposals |
| AS-9 | Operational monitoring, comparison, and retirement | Yes after AS-8 | Monitoring and safe disable only |
| AS-10 | Bounded live influence | Requires all live gates and explicit owner request | Tightly capped live proposals |
| AS-11 | Autonomous strategy mutation or runtime LLM decisions | No; prohibited | None |

Required implementation order:

```text
AS-0 -> AS-1 -> AS-2 -> AS-3 -> AS-4 -> AS-5 -> AS-6 -> AS-7

AS-8, AS-9, and AS-10 require later explicit authorization and accumulated
evidence. AS-11 is not an implementation milestone.
```

Building the deterministic language and evaluation pipeline before connecting
an LLM is intentional. Otherwise the first authoring prototype will generate
concepts the platform cannot validate honestly.

## 7. AS-0 - architecture freeze and shared acceptance contracts

### 7.1 Purpose

Establish precise meanings before creating implementation that silently treats
`generated`, `backtested`, `promising`, `approved`, and `tradable` as synonyms.

### 7.2 Implementation

Add an architecture decision record for the strategy-authoring boundary and
typed enums or value objects for:

- strategy lifecycle status;
- evidence status;
- data eligibility;
- operational eligibility;
- authority scope;
- refusal reason; and
- supported asset, schedule, order-intent, and evaluation categories.

Define four separate immutable identities:

```text
draft_id       - exact prose, model response, and authoring context
strategy_id    - canonical StrategySpec content
experiment_id  - strategy + data + evaluation plan + software identity
promotion_id   - exact strategy/experiment/dossier + approved scope
```

Changing any economically meaningful field must change the corresponding
identity. Display text and timestamps that are intentionally excluded from a
content hash must be documented field by field.

Add an exact authority matrix covering research, presentation, shadow, paper,
and live consumers. No generic `production` or `enabled` boolean is allowed.

### 7.3 Tests

- lifecycle states cannot be skipped by an ordinary transition;
- evidence state cannot grant authority;
- paper authority cannot be interpreted as live authority;
- IDs change when economic content changes and remain stable for canonical
  equivalent input;
- non-finite numeric values and naive timestamps are rejected; and
- every contract is deeply immutable and canonical-JSON serializable.

### 7.4 Definition of done

The repository has one tested vocabulary for strategy identity, evidence, and
authority, and no code path can represent `backtest passed` as `approved`.

## 8. AS-1 - restricted strategy specification language

### 8.1 Purpose

Give the LLM a small language the platform can inspect completely. Do not use
arbitrary generated source code as the strategy format.

### 8.2 StrategySpec v1

Prefer extending the existing `strategies/` package with focused modules such
as `contracts.py`, `operators.py`, and `validation.py`. Before choosing names,
inspect the current package and consolidate overlapping helpers.

`StrategySpec` should contain at least:

```text
schema_version
name and owner-visible description
declared research question
asset class and universe definition
required data series and availability semantics
feature graph using allowlisted operators
entry, exit, and abstention conditions
portfolio construction and rebalance schedule
position, turnover, liquidity, and concentration limits
execution-timing assumptions
cost, spread, slippage, tax, and cash assumptions
benchmarks
evaluation horizons and metrics
missing/stale-data behavior
declared parameters and parameter-search space
```

The universe must distinguish fixed current symbols from historically valid
membership. A fixed current universe is explicitly marked survivorship-biased
unless that statement is genuinely false.

Every quantity carries an explicit unit. Examples include sessions versus
calendar days, fraction versus percent, annualized versus horizon volatility,
dollars versus portfolio weight, and close versus next-open execution.

### 8.3 Expression restrictions

Expressions use a finite operator registry, not Python or an unrestricted
expression evaluator. Each operator declares:

- input and output types;
- units;
- required lookback;
- warm-up behavior;
- missing-data behavior;
- point-in-time availability rule;
- deterministic implementation version; and
- whether it is permitted for research, shadow, paper, or live evaluation.

V1 should support only concepts the platform can evaluate safely, such as
lagged returns, moving statistics, volatility, drawdown, cross-sectional rank,
threshold comparison, boolean composition, fixed or bounded weights, scheduled
rebalance, and time-based exit.

V1 should reject:

- arbitrary source code, imports, callbacks, reflection, templates, or dynamic
  attribute access;
- file paths, URLs, shell commands, SQL, and serialized objects;
- implicit use of today's index membership in historical periods;
- same-bar decisions and fills unless explicitly modeled and justified;
- unbounded leverage, shorting, margin, derivatives, or unsupported order
  types;
- undefined terms such as `high momentum`, `safe`, or `cheap` without a
  measurable definition; and
- unspecified conflict resolution when multiple rules fire.

### 8.4 Validation output

Validation returns all findings with stable codes, JSON pointers to affected
fields, severity, and owner-readable explanations. It does not silently repair
economic meaning.

Mechanical canonicalization may normalize harmless representation differences.
Any change to symbols, thresholds, time, weights, costs, or behavior requires
an explicit owner-visible revision.

### 8.5 Tests

- golden valid specifications for simple trend, volatility targeting, and
  deterministic rebalance strategies;
- invalid and unknown operators;
- cycles in the feature graph;
- unit mismatch and horizon mismatch;
- ambiguous time and execution semantics;
- duplicate JSON keys, unknown fields, NaN, infinity, and extreme values;
- nested mutation attempts after construction;
- malicious strings containing code, prompt instructions, paths, or URLs;
- unsupported asset/order types; and
- deterministic canonicalization and identity generation.

### 8.6 Definition of done

A human can read the complete specification, the validator can explain every
rejection, and no specification can contain executable or open-ended behavior.

## 9. AS-2 - deterministic compiler, interpreter, and static analysis

### 9.1 Purpose

Convert an accepted specification into a deterministic strategy program whose
data needs, timing, and possible outputs are known before evaluation.

### 9.2 Compilation

Compile `StrategySpec` into an immutable internal representation. Compilation
must:

- resolve every operator to an exact implementation version;
- topologically order the feature graph;
- derive maximum lookback and warm-up requirements;
- check units and value domains;
- derive decision and earliest-fill timestamps;
- enumerate all possible symbols from the declared universe rule;
- prove that position and leverage outputs remain within supported bounds;
- make abstention behavior explicit; and
- create a compiler manifest containing the source strategy hash and software
  identity.

The runtime should interpret the restricted representation or invoke an
allowlisted registry of pure functions. It must not generate or execute Python
source.

### 9.3 Temporal and authority analysis

Static checks must reject or block:

- features whose inputs are not available by the decision timestamp;
- target leakage and negative lags;
- same-session fundamental/event data without a proven availability timestamp;
- requested lookback beyond available history;
- a decision that assumes a fill before it could have been submitted;
- a model observation without task/version/epoch/freshness requirements; and
- any output shaped like a broker order.

The compiler output is a `StrategyDecision` or neutral desired-portfolio state,
not an order. It may state an eligible universe, scores, conditions, target
weights, abstention, and trace. Quantity, order type, approval, and submission
remain downstream responsibilities.

### 9.4 Explainability trace

For each evaluation, preserve a deterministic trace containing:

- input observation IDs and as-of timestamps;
- feature values used;
- rule results;
- abstention or decision reasons;
- target state before mandate/risk enforcement; and
- the exact strategy and compiler identities.

The trace is audit evidence, not an LLM-generated explanation.

### 9.5 Tests

- interpreter results match hand calculations;
- results are invariant to input mapping order;
- future or revised data cannot enter an earlier decision;
- warm-up boundaries are exact;
- no-lookahead behavior around market open, close, weekends, holidays, and
  daylight-saving changes;
- operator version changes alter compiler identity;
- traces reproduce the decision exactly; and
- AST/import tests prove the compiler cannot import broker, execution,
  approval, or LLM client modules.

### 9.6 Definition of done

The same immutable specification and point-in-time inputs always produce the
same neutral strategy decision and trace, without executing generated code.

## 10. AS-3 - data requirements and evaluation-plan compiler

### 10.1 Purpose

Determine whether the requested strategy can be evaluated honestly before
spending time on a backtest.

### 10.2 DataRequirementManifest

Derive a manifest containing:

- every price, corporate-action, fundamental, event, macro, universe, model,
  and benchmark series required;
- vendor/source identity;
- observation time, availability time, revision policy, and timezone;
- adjustment semantics;
- historical-universe membership requirements;
- required start/end dates, warm-up, and target maturity;
- expected frequency and calendar;
- missingness tolerance; and
- whether each requirement is authoritative, exploratory-only, or absent.

Do not allow `yfinance` or another retroactively adjusted source to acquire a
point-in-time claim merely because the strategy uses only common indicators.
Use the existing ML availability and dataset-lineage contracts where possible.

### 10.3 EvaluationPlan

Create an immutable evaluation plan before results are known. It should freeze:

- research question and primary outcome;
- discovery versus confirmation status;
- candidate and baseline specifications;
- parameter grid or search budget;
- number of prior and current research looks;
- train/validation/confirmation periods;
- purging, embargo, grouping, and block-bootstrap rules;
- minimum independent dates, events, trades, and regime coverage;
- cost, tax, spread, slippage, and latency stress assumptions;
- rejection and promotion thresholds;
- robustness and sensitivity tests; and
- explicit conditions that force `insufficient` rather than pass or fail.

The owner must accept material assumptions before the confirmation run. The
platform must not choose thresholds after seeing the result.

### 10.4 Capability report

Before backtesting, provide a report such as:

```text
fully_testable
exploratory_only: historical constituent availability not proven
blocked: required filing availability timestamps unavailable
unsupported: options payoff operator is outside the mandate
```

### 10.5 Tests

- data needs are derived transitively from the feature graph;
- warm-up and horizon maturity are computed in market sessions;
- fixed-current and historical universes cannot be confused;
- missing availability timestamp blocks confirmation;
- revised macro/fundamental data does not masquerade as first-release data;
- all research looks are counted, including discarded generated variants;
- candidate and baselines share compatible data and execution assumptions;
  and
- an evaluation plan cannot change after results are attached.

### 10.6 Definition of done

The platform can refuse an untestable idea before backtesting and can explain
the exact external data or specification change needed to proceed.

## 11. AS-4 - research orchestration and realistic backtest

### 11.1 Purpose

Run accepted strategies through the repository's existing research machinery
without creating a second, less rigorous backtester.

### 11.2 Orchestration

Add a strategy experiment runner that records:

- strategy, compiler, data, evaluation-plan, and software identities;
- exact command and environment metadata;
- start, completion, failure, and retry state;
- every generated candidate and research look;
- immutable result and report hashes; and
- explicit discovery/confirmation separation.

Exact retries return the original record. The same identity with different
content is an error. Interrupted writes are atomic and resumable only where the
result identity remains provable.

### 11.3 Portfolio realism

Extend the existing `backtest/` infrastructure. Do not score only independent
rows when the strategy shares capital. The simulator must model, as applicable:

- starting cash and capital contention;
- cash settlement and rejected infeasible trades;
- position overlap and portfolio concentration;
- fractional versus whole-share behavior;
- turnover and liquidity caps;
- next-available execution timing;
- bid/ask spread, commission, fees, market impact proxy, and slippage;
- splits, dividends, delistings, and corporate actions;
- partial fills or conservative fill assumptions;
- taxable lots and declared tax treatment;
- benchmark cash flows on identical dates; and
- refusal when required realism cannot be modeled.

Costs and taxes must be stress parameters, not a single optimistic constant.
Candidate and baselines must use identical capital, dates, prices, costs, and
availability filters.

### 11.4 Evidence hygiene

Evaluate dependence at the correct unit: dates, events, regimes, or overlapping
holding periods rather than assuming every row or trade is independent. Apply
the preregistered multiplicity correction across all generated and manually
edited variants.

Generated strategies that are viewed and discarded still count as research
looks. Starting a new chat or renaming a strategy does not reset that count.

### 11.5 Tests

- hand-built portfolio fixtures with cash contention and overlapping positions;
- cost and tax monotonicity;
- decisions at close cannot fill at that same close by default;
- delisting, split, dividend, and missing-price behavior;
- identical candidate/baseline sampling;
- thin and dependent samples refuse significance;
- changing a result cannot retain an experiment identity;
- retry and crash recovery preserve immutability; and
- running an experiment changes no proposal, order, broker, reservation,
  approval, finding, or promotion state.

### 11.6 Definition of done

An accepted strategy can be reproduced from immutable inputs, and the report
reflects a capital-constrained portfolio rather than an optimistic collection
of independent hypothetical trades.

## 12. AS-5 - LLM authoring and clarification workflow

### 12.1 Purpose

Turn ordinary-language intent into a structured draft while keeping all
financial meaning visible to the owner and all authority in deterministic
code.

### 12.2 Authoring contract

Give the LLM only:

- the owner's strategy description;
- the `StrategySpec` JSON schema;
- the supported operator and data capability catalog;
- mandate-compatible ranges and unsupported-feature list; and
- instructions to distinguish stated requirements, assumptions, and unresolved
  questions.

Require one machine-readable response containing:

```text
draft specification
assumptions introduced
ambiguities and blocking questions
unsupported requested concepts
owner-readable summary
```

Treat prose inside retrieved filings, web pages, datasets, model cards, and old
strategy notes as data, never instructions. The authoring call receives no
tools and no secrets.

### 12.3 Clarification and revision

Ambiguity affecting symbols, direction, timing, price, leverage, sizing,
thresholds, exits, costs, or risk must block acceptance. The owner may answer
questions or edit the structured draft directly.

Every revision shows a semantic diff. The interface must distinguish:

- owner-stated fields;
- LLM-proposed assumptions;
- deterministic derived fields; and
- unavailable or unsupported fields.

The platform must not silently retry until an invalid response becomes valid
by changing strategy meaning. Syntax-repair retries are permitted only when
the exact semantic content is preserved and recorded.

### 12.4 Provider isolation and reproducibility

Store the exact normalized owner prompt, system instruction version, model and
provider identity, sampling settings, raw response hash, parsed draft, and
validation result. Do not store provider credentials or unnecessary private
context.

The LLM call itself need not be reproducible, but the accepted `StrategySpec`
and everything after it must be.

### 12.5 Initial interface

Start with a dedicated command rather than changing `DecisionPacket` or the
main assistant UI:

```text
python scripts/run_strategy_lab.py draft --input strategy_request.md
python scripts/run_strategy_lab.py validate --draft <draft-id>
python scripts/run_strategy_lab.py accept --draft <draft-id>
```

`accept` freezes a research specification only. It grants no shadow, paper, or
live authority.

### 12.6 Tests

- malformed, partial, extra-field, and non-JSON responses;
- prompt injection and code-shaped output;
- unsupported concepts and materially ambiguous requests;
- semantic diff for thresholds, units, symbols, and timing;
- syntax repair cannot change economic content;
- provider failure produces no accepted draft;
- exact authoring audit record is immutable; and
- drafting and accepting create no model promotion, proposal, order, approval,
  broker, reservation, or execution state.

### 12.7 Definition of done

The owner can describe a supported strategy, resolve every material assumption,
and accept an immutable research-only specification without trusting the LLM's
code or judgment.

## 13. AS-6 - robustness evaluation and usability dossier

### 13.1 Purpose

Replace the misleading question `did the backtest pass?` with an auditable,
multidimensional decision-support report.

### 13.2 Required evaluation

For a confirmation candidate, evaluate at least:

- simple frozen baselines and the do-nothing/cash alternative where relevant;
- strictly unseen confirmation periods;
- rolling or expanding walk-forward stability;
- bull, bear, sideways, high-volatility, and low-volatility regimes, without
  inventing independence where regimes are few;
- parameter-neighborhood sensitivity;
- feature and rule ablations;
- higher costs, spread, slippage, latency, and taxes;
- reduced liquidity and capacity;
- missing/stale-data stress and provider outages;
- universe and start/end-date sensitivity;
- concentration and tail loss; and
- calibration or error behavior for any ML observation consumed.

A strategy that works at one narrow parameter value surrounded by losses is
fragile even if the chosen point passes. A strategy that has too few
independent events is `insufficient`, not successful.

### 13.3 Dossier

Produce an immutable dossier containing:

- all identities and lineage;
- capability and point-in-time status;
- the original research question and accepted assumptions;
- every candidate, baseline, parameter search, and research look;
- paired statistical and economic results;
- robustness and failure tests;
- data, model, and operational limitations;
- the eight independent usability dimensions from section 3;
- explicit blockers and expiry/review date; and
- the exact statement that the dossier does not grant authority.

The report must show rejected and unavailable results rather than selecting
only favorable runs.

### 13.4 Tests

- a strong return cannot mask invalid data or failed robustness;
- missing baseline, regime, or cost stress is visible and blocking;
- multiple testing uses the complete recorded research-look count;
- a rejected or insufficient dimension cannot yield paper eligibility;
- dossier content and referenced artifacts are hash-verified;
- report order and JSON serialization are stable; and
- dossier generation is read-only with respect to strategy authority and
  trading state.

### 13.5 Definition of done

The platform can explain, in plain language and exact evidence, why a strategy
is invalid, exploratory, unsupported, promising, or eligible for a later
shadow/paper promotion review.

## 14. AS-7 - immutable strategy registry and human promotion

### 14.1 Purpose

Separate research evidence from authority in the same way the ML roadmap
separates model results from promotion.

### 14.2 Lifecycle

Use explicit, audited transitions such as:

```text
draft
  -> accepted_research
  -> discovery_complete
  -> confirmation_candidate
  -> confirmation_rejected | shadow_candidate
  -> approved_shadow
  -> approved_paper
  -> retired
```

Live scope is deliberately absent from the ordinary transition function. It
belongs to AS-10 and requires a separate owner-authorized operation.

Promotion must require:

- expected current status and strategy hash;
- experiment and dossier hashes;
- no unresolved required blockers;
- owner identity and explicit approval phrase;
- exact permitted consumer, account mode, symbols, capital/notional limits,
  dates, and strategy parameters;
- ML observation task/version/epoch requirements, if any;
- expiry and scheduled review date;
- rollback/retirement conditions; and
- an immutable audit event.

No training, backtest, dossier, scheduler, LLM, or monitoring command may call
promotion automatically.

### 14.3 Change control

Any economic change creates a new `strategy_id` and returns to research.
Changes to a threshold, operator version, universe, rebalance time, cost model,
feature, model dependency, or risk behavior cannot be described as a cosmetic
revision.

Copying evidence from one strategy version to another is prohibited. A dossier
may be referenced historically but never treated as evidence for changed
behavior.

### 14.4 Tests

- invalid transitions and stale expected hashes fail atomically;
- expired approval has no authority;
- scope cannot widen implicitly;
- paper scope cannot reach live configuration;
- changed strategy content invalidates the approval relationship;
- concurrent promotion attempts produce one immutable outcome; and
- promotion does not create a proposal or order.

### 14.5 Definition of done

The owner can approve one exact strategy version for one exact non-live scope,
and every other version remains unauthorized.

## 15. AS-8 - shadow and paper proposal adapter

**Do not implement this milestone merely because AS-7 software exists. It
requires an explicitly approved strategy, completed prerequisite evidence, and
a later owner request.**

### 15.1 Runtime separation

The runtime loads only:

- an approved immutable `StrategySpec` and compiler manifest;
- point-in-time market/account inputs;
- approved serialized ML observations, if declared;
- current mandate and policy state; and
- the exact promotion scope.

It must not load an LLM client, prompt, draft response, research notebook,
unapproved model artifact, or backtest result into the decision path.

### 15.2 ML observation bridge

If a strategy consumes ML output, require all of:

- ML-LR-9 context approval already exists;
- exact task, subject, model, version, epoch, horizon, and maximum age match;
- artifact and monitoring report hashes verify;
- calibration and evidence status meet the strategy's declared requirement;
- no promotion blocker or active critical alert exists; and
- missing or invalid output causes abstention or deterministic no-ML behavior
  declared in advance.

An ML observation may contribute a bounded risk estimate or score. It may not
create a symbol, bypass the strategy specification, or alter execution policy.

### 15.3 Proposal generation

Create a narrow adapter from neutral `StrategyDecision` to the existing
proposal contract. The adapter must:

- be feature-flagged off by default;
- enforce the approved shadow/paper/account/symbol/notional scope;
- preserve original strategy target and every deterministic adjustment;
- create stable, idempotent proposal identities;
- refuse stale account, price, strategy, ML, policy, or promotion state;
- pass every proposal through existing policy and execution validation;
- never directly submit to a broker;
- never block risk-reducing sales; and
- show strategy, experiment, promotion, input, and trace identities in the
  proposal preview.

The initial adapter should run shadow-only. Paper proposals come in a separate
review after decision equivalence and failure behavior are understood.

### 15.4 Tests

- exact policy, notional, concentration, and approval boundaries;
- expired/missing promotion and changed strategy hash;
- stale price/account/model observation and evidence-epoch mismatch;
- duplicate invocation and concurrent proposal creation;
- unavailable ML behavior matches the frozen specification;
- shadow mode creates no executable proposal state;
- paper mode cannot select a live account;
- fresh broker revalidation still occurs after approval; and
- adapter/strategy/ML failure never delays deterministic risk reduction.

### 15.5 Definition of done

One specifically approved strategy can generate explainable shadow decisions
and, only after a separate review, normal human-approved paper proposals. The
LLM remains absent from runtime.

## 16. AS-9 - monitoring, comparison, and retirement

### 16.1 Purpose

Detect when live-like behavior differs from the research assumptions or when
the strategy can no longer be evaluated safely.

### 16.2 Monitoring

Record and report:

- scheduled versus completed decisions;
- abstention and refusal reasons;
- input and model-observation freshness;
- strategy/compiler/promotion identity mismatches;
- shadow versus paper decision differences;
- proposal acceptance, rejection, expiry, and operator overrides;
- predicted versus realized portfolio behavior;
- turnover, costs, slippage, tax, and capacity relative to the dossier;
- drawdown and loss limits;
- data coverage, drift, and regime distribution; and
- open incidents, alerts, approval expiry, and review dates.

Do not pool evidence across changed strategies, compilers, data regimes, ML
epochs, or material execution configurations.

### 16.3 Safe disable and retirement

Add a strategy-specific disable switch independent of the main execution kill
switch and ML disable switch. Disabling a strategy must stop new strategy
proposals while leaving reconciliation, cancellations, approved operational
recovery, and risk-reducing actions available.

Automatic monitoring may disable new strategy influence on an exact hard
failure. It may not automatically select a replacement strategy, retrain a
model, broaden scope, or re-promote a retired version.

### 16.4 Tests

- missed schedules and alerts are visible rather than silently skipped;
- identity, drift, freshness, loss, and approval-expiry failures disable new
  influence in the declared direction;
- evidence remains separated across epochs and strategy versions;
- disabling is idempotent and restart-safe;
- no fallback strategy is activated implicitly; and
- risk reduction and reconciliation remain available.

### 16.5 Definition of done

The owner can determine what the approved strategy did, why it abstained or
proposed, whether paper behavior still matches research, and how to disable or
retire it safely.

## 17. AS-10 - bounded live influence

This is a later operational authorization, not a normal software milestone.
It must not begin until:

- ML and general-readiness prerequisite gates relevant to the strategy pass;
- the full `LIVE_PROMOTION_CHECKLIST.md` passes;
- the strategy has sufficient independent shadow and paper evidence;
- reconciliation and operational alerts are clean;
- AS-9 monitoring and disable drills have been exercised;
- every data source used in the decision has appropriate live and historical
  availability evidence;
- a written canary budget, loss limit, symbol scope, session count, rollback
  condition, and expiry are frozen; and
- the owner explicitly authorizes the exact promotion and funded account.

Start with a tiny, declared scope. Keep all deterministic risk limits, broker
revalidation, human approval, and reconciliation. Compare shadow, paper, and
live decisions and fill quality without pooling them as equivalent evidence.

No confidence-scaled leverage, automatic capital expansion, automatic strategy
generation, automatic parameter tuning, automatic promotion, or automatic
switching between strategies is permitted.

Definition of done is an operational record: the declared canary sessions end
with reconciliation clean, caps never breached, incidents resolved, and an
owner decision to retire, continue unchanged, or begin a separately reviewed
scope. Code completion alone cannot complete AS-10.

## 18. AS-11 - explicitly prohibited autonomy

The following are outside this plan and must not be implemented without a new
architecture and threat review:

- an LLM reading the market and deciding trades at runtime;
- generated Python or arbitrary expressions executed as strategies;
- an agent modifying a promoted strategy in place;
- automatic search until a favorable backtest appears;
- automatic promotion based on metrics;
- automatic deployment of a newly generated strategy;
- self-reward based on paper or live profit;
- automatic increase of capital, leverage, universe, or account scope;
- LLM access to broker credentials or order APIs; and
- autonomous funded trading without per-order human approval.

These behaviors combine non-determinism, data snooping, prompt-injection risk,
and financial authority in one loop. That is a different and substantially
riskier product than the governed research-and-proposal platform described
here.

## 19. Cross-cutting requirements

### 19.1 Time and market semantics

- Use the NYSE calendar where applicable.
- Use timezone-aware timestamps and preserve the original availability zone.
- Distinguish observation time, availability time, decision time, submission
  time, and earliest possible fill time.
- Use market sessions rather than calendar-day arithmetic for market horizons.
- Require explicit before-open, intraday, after-close, and next-session rules.
- Prevent revised values from appearing at their original observation date.

### 19.2 Numeric and money rules

- Validate finiteness before every range comparison.
- Use exact decimal helpers for money, prices, quantities, fees, and taxes.
- Preserve fraction/percent and annualized/horizon units.
- Reject impossible weights, leverage, prices, quantities, and costs.
- Use conservative explicit rounding and whole/fractional-share semantics.
- Do not let NaN become zero risk, zero cost, no signal, or a favorable result.

### 19.3 Integrity and storage

- Use canonical JSON and existing hashing helpers.
- Deep-freeze nested caller-owned data.
- Use atomic, content-addressed artifact writes.
- Verify hashes and expected identities before deserialization.
- Load pickle/joblib only from controlled verified artifact directories.
- Exact retry returns the existing record; conflicting identity raises.
- SQLite changes are additive and migrate databases made by the previous
  version without inventing missing lineage.

### 19.4 Security and privacy

- Keep provider and broker credentials outside prompts, drafts, artifacts, and
  reports.
- Minimize portfolio/account context sent to an authoring provider.
- Redact secrets from errors and logs.
- Treat all retrieved content as untrusted data.
- Bound prompt and response size, latency, retries, and cost.
- Never download or load code, model artifacts, or prompts referenced by LLM
  output.

### 19.5 User presentation

Every strategy view must display:

- exact strategy version and lifecycle state;
- research versus shadow/paper/live authority;
- data eligibility and point-in-time limitations;
- main assumptions and unsupported concepts;
- evidence status, blockers, and expiry;
- current promotion scope; and
- a label stating that historical results are not a guarantee and do not grant
  trading authority.

No action control should imply that `backtest` means `activate`. Acceptance,
research execution, promotion, proposal approval, and broker execution remain
visibly separate actions.

## 20. Required verification for every milestone

At minimum, run:

```text
python -m pytest -q <focused tests>
python -m pytest -q tests
python -m compileall -q assistant data execution risk scripts signals strategies backtest ml tests baskets.py config.py
git diff --check
```

Also perform milestone-appropriate adversarial probes for:

- prompt injection and code-shaped strategy content;
- duplicate and conflicting identity;
- nested mutation;
- NaN and infinity in every public numeric contract;
- unsupported schema and operator versions;
- lookahead at exact session and event boundaries;
- current-universe survivorship leakage;
- missing or revised availability timestamps;
- candidate/baseline sample mismatch;
- uncounted generated research variants;
- artifact corruption and database migration;
- provider, scheduler, and process restart failure;
- strategy/model evidence-epoch change;
- expired or scope-mismatched promotion; and
- proof that unrelated proposal, broker, reservation, allocation, approval, and
  execution state remains unchanged.

Test count alone is not acceptance. Report the behavioral invariants proven and
the failure directions exercised.

## 21. External and calendar-time dependencies

Software completion will not provide all prerequisites. The owner may need:

- an authoritative point-in-time market/fundamental/event data vendor;
- historical constituent membership and corporate-action/delisting data;
- sufficient data-license rights to store and evaluate the required history;
- an LLM provider/API or a locally controlled model for authoring;
- provider privacy and retention settings acceptable for submitted context;
- elapsed shadow and paper sessions across meaningful market conditions; and
- explicit decisions about tax treatment, execution assumptions, capacity,
  evidence thresholds, and capital scope.

A price-only strategy over a fixed declared universe may be explored without
all external data. The capability report must still state survivorship,
adjustment, and availability limitations. Engineering agents must not hide an
unfunded dependency by weakening the evidence gate.

## 22. Sequencing relative to the existing roadmaps

This plan is third in the implementation sequence:

```text
1. ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md
   Build trustworthy observations, shadow evidence, monitoring, and promotion
   governance.

2. GENERAL_READINESS_IMPLEMENTATION_PLAN.md
   Make execution, data, fault handling, alerting, recovery, and the ordinary
   product cycle dependable.

3. AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md
   Add governed prose-to-strategy authoring, honest evaluation, promotion, and
   eventually bounded proposal integration.
```

AS-0 through AS-7 may be implemented after the software portions of the first
two plans are complete and stable. AS-8 through AS-10 additionally require the
real evidence, external data, operational drills, and owner authorizations
specified by their gates.

Completing all three documents creates a mature platform for expressing,
testing, governing, and operating strategies. It still does not guarantee that
the owner has discovered a durable edge. The correct successful outcome for a
generated idea may be a fast, well-supported rejection.

## 23. Recommended first implementation instruction

When the prerequisite roadmaps are complete, start with this scope:

> Implement **AS-0 only** from
> `docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md`. Inspect the current
> repository and the full milestone first. Add the shared strategy lifecycle,
> evidence, data-eligibility, operational-eligibility, authority, refusal, and
> identity contracts plus an architecture decision record and focused tests.
> Do not add an LLM client, strategy DSL, compiler, backtest runner, registry
> transition command, proposal adapter, or execution integration. Run focused
> and full verification, commit on a dedicated branch, and stop for review.

This deliberately begins with authority and identity rather than generation.
The platform must know what an AI-authored artifact is allowed to mean before
it can safely create one.
