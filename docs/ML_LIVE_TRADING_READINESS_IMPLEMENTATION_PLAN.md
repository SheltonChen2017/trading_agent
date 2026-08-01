# ML Live-Trading Readiness Implementation Plan

Status: execution plan for the next implementation sequence
Prepared: 2026-07-31
Applies after: `docs/ML_IMPLEMENTATION_STRATEGY.md` ML-1 through ML-8
Current-state companion: `docs/ML_IMPLEMENTATION_STATUS.md`

## 1. Objective

Turn the current ML research foundation into an operational, auditable,
shadow-tested decision-support layer that can eventually become eligible for
a narrowly bounded live-trading integration review.

This plan does **not** assume that code completion proves a model has edge. It
separates three different outcomes that must not be conflated:

1. **software complete** — contracts, runners, monitoring, and controls work;
2. **research supported** — an immutable confirmation experiment clears its
   preregistered statistical and economic gates; and
3. **live-authorized** — the owner separately approves a deterministic adapter
   after sufficient shadow evidence and an adversarial review.

The implementation agent may complete software. It cannot manufacture the
elapsed evidence, external point-in-time data, or owner authorization required
for outcomes 2 and 3.

## 2. Non-negotiable safety boundary

Until ML-LR-9 is explicitly authorized in a later request:

- no ML output may create, approve, size, submit, cancel, or replace an order;
- no execution-capable module may import `ml`;
- no model may weaken a policy, exposure limit, execution gate, kill switch,
  reconciliation rule, or stale-order rule;
- no model may block or delay a risk-reducing sale;
- missing, stale, invalid, or unavailable ML output must be operationally
  equivalent to no ML output;
- training, evaluation, shadow monitoring, and filing extraction must never
  edit `assistant/research_findings.json` automatically;
- no script may promote a model as a side effect of fitting or monitoring;
- no test result or synthetic fixture may be described as evidence of market
  edge; and
- paper fills must not be treated as evidence for a live execution-quality
  model.

Keep `tests/test_ml_import_boundary.py` passing. A read-only presentation
adapter, if later introduced, requires an exact-file allowlist and a separate
AST test proving that it cannot import proposal, execution, broker, or risk-gate
modules.

## 3. Current baseline

The repository already has:

- immutable dataset/model/prediction contracts and artifact verification;
- point-in-time-safe price-feature arithmetic, explicit labels, and purged
  grouped walk-forward splitting;
- PCA/shrinkage concentration reporting;
- per-security volatility model and evaluation primitives;
- earnings-gap event mapping and basic model-fit primitives;
- cross-sectional ranker and date-level statistical metrics;
- structured filing-extraction validation;
- append-only model, prediction, outcome, equity, and position persistence;
- initial coverage, freshness, drift, error, and lineage monitoring; and
- a regression boundary preventing ML from entering execution.

The important remaining gaps are not another model family. They are
point-in-time lineage, reproducible experiment runners, complete economic
evaluation, automatic shadow operation, evidence-epoch control, monitored
presentation, and explicit human promotion governance.

## 4. Delivery rules for Claude

### 4.1 One milestone per branch and review

Do not implement this entire document in one sweep. Use the following order
and stop for review after every milestone:

```text
ML-LR-0 -> ML-LR-1 -> ML-LR-2 -> ML-LR-3 -> ML-LR-4
        -> ML-LR-6 -> ML-LR-7 -> ML-LR-8

ML-LR-5 may begin after ML-LR-2, but promotion remains blocked on ML-LR-1.
ML-LR-9 and ML-LR-10 require explicit later owner authorization.
ML-LR-11 remains data-gated and must not be implemented now.
```

Suggested branch naming:

```text
user/claude/ml-live-lr0-baseline-YYYYMMDD
user/claude/ml-live-lr1-point-in-time-YYYYMMDD
...
```

At the end of each milestone:

1. state exactly what is implemented and what is still missing;
2. list all schema and contract changes;
3. identify any behavior that can affect the live assistant;
4. run focused tests, full tests, compilation, and `git diff --check`;
5. update `docs/ML_IMPLEMENTATION_STATUS.md` conservatively;
6. do not call a milestone complete when only its primitives exist; and
7. stop and request review before starting the next milestone.

### 4.2 Preserve existing infrastructure

Before adding a helper, inspect and reuse:

- `ml/contracts.py`, `ml/hashing.py`, and `ml/artifacts.py` for immutable
  contracts, canonical JSON, and atomic artifact handling;
- `ml/datasets.py` for content-addressed research datasets;
- `ml/splits.py` for purged grouped walk-forward folds;
- `ml/evaluation.py` and `backtest/engine.py` for evaluation and
  dependence-aware significance;
- `assistant/storage.py` for SQLite initialization, migrations, and immutable
  conflict behavior;
- `assistant/money.py` for exact decimals;
- existing portfolio/backtest/tax modules before implementing economic
  simulation; and
- `scripts/install_windows_operational_tasks.ps1` for Windows scheduling
  conventions.

Do not introduce MLflow, Airflow, an external database, a feature-store
framework, or a distributed serving framework. The current single-user app
does not need them.

## 5. Milestone overview

| Milestone | Purpose | Implementable now? | Production behavior |
|---|---|---:|---|
| ML-LR-0 | Freeze baseline and shared acceptance contracts | Yes | None |
| ML-LR-1 | Point-in-time lineage and historical universe contracts | Code: yes; authoritative data: external | None |
| ML-LR-2 | Durable experiment specifications and runners | Yes | None |
| ML-LR-3 | Complete volatility and portfolio-risk research | Partly; history must accumulate | None |
| ML-LR-4 | Complete earnings-gap research and filing context | Software complete; real confirmation needs authoritative event data | None |
| ML-LR-5 | Complete ranker economic evaluation | Code: yes; credible confirmation data: external | None |
| ML-LR-6 | Automated shadow runtime and ML evidence epochs | Yes | Observation writes only |
| ML-LR-7 | Monitoring and promotion dossier | Yes after LR-6 | Read-only reports |
| ML-LR-8 | Read-only user presentation | Yes after LR-6 | Context display only |
| ML-LR-9 | Human promotion registry and bounded adapter | Later explicit approval | Initially context only |
| ML-LR-10 | Limited-capital canary process | Requires evidence and owner action | Carefully bounded live influence |
| ML-LR-11 | Execution-quality modeling | No; live-order data absent | None |

## 6. ML-LR-0 — baseline freeze and shared acceptance contracts

### 6.1 Purpose

Create a small, reviewed foundation for the remaining milestones so each
runner does not invent its own experiment identity, evidence gates, or report
layout.

### 6.2 Implementation

Add `ml/experiment_contracts.py` containing frozen, JSON-serializable
contracts such as:

```python
ExperimentSpec
ExperimentIdentity
ResearchGateSpec
ConfirmationSpec
ExperimentRunRecord
```

`ExperimentSpec` should include at least:

```text
schema_version
experiment_id
task
mode: discovery | confirmation
created_at
primary_outcome
candidate_models
frozen_baselines
feature_set_version
label_version
benchmark
horizon_sessions
universe_definition
research_look_dimensions
split_configuration
cost_tax_liquidity_assumptions
minimum_coverage
calibration_requirements
failure_slices
random_seed
confirmation_parent_hash (required in confirmation mode)
```

Requirements:

- recursively freeze all mappings and sequences;
- reject NaN, infinity, unknown fields, duplicate variants, naive timestamps,
  invalid hashes, and inconsistent discovery/confirmation fields;
- derive `spec_hash` from canonical JSON;
- make confirmation mode require an immutable parent discovery report/spec
  hash;
- make research-look count derive from the variants actually present in the
  spec; and
- include no field named `production`, `approved`, `authority`, `side`,
  `quantity`, `target_weight`, or similar.

Extend `EvaluationReport` only when a field is genuinely shared by every
experiment. Prefer task-specific nested metrics to a giant optional contract.

### 6.3 Tests

- round trip and stable hash;
- behavior-relevant field changes alter the hash;
- nested caller mutation cannot change a constructed spec;
- confirmation without a parent hash is refused;
- duplicate research variants are refused;
- naive timestamps and non-finite nested values are refused;
- forbidden execution-shaped fields cannot enter serialized output; and
- pure report construction creates no SQLite or execution state.

### 6.4 Definition of done

At least one existing synthetic volatility experiment and one ranker
experiment can be described completely by the new spec without changing
their results. No runner is required yet.

## 7. ML-LR-1 — point-in-time lineage and historical universe

### 7.1 Purpose

Remove the largest research blocker: the current builder must always report
`point_in_time_data=False` because it cannot prove when each feature became
available.

### 7.2 New contracts

Add `ml/availability.py` with frozen contracts:

```text
FeatureAvailabilityRecord
  as_of_session
  ticker
  feature_name
  event_at
  available_at
  observed_at
  source_id
  source_version
  revision_id
  raw_value_hash

UniverseMembershipRecord
  universe_id
  ticker
  effective_from
  effective_to
  announced_at
  available_at
  source_id
  source_version
```

All event and availability timestamps must be timezone-aware. Date-only
market sessions must use canonical `YYYY-MM-DD`. Enforce:

```text
event_at <= available_at <= observed_at
available_at <= feature decision cutoff
membership.available_at <= the session on which membership is used
```

Do not infer these timestamps from download time when the data vendor cannot
provide them. Mark the record unsupported and keep the dataset exploratory.

### 7.3 Dataset sidecars

Extend `ml/datasets.py` to save and load immutable sidecars alongside
features and labels:

```text
<dataset>.features.csv.gz
<dataset>.labels.csv.gz
<dataset>.availability.csv.gz
<dataset>.universe.csv.gz
<dataset>.manifest.json
```

The manifest must contain the hashes and row counts for every sidecar.
Dataset identity must change if any sidecar changes.

Add validation that:

- every non-derived feature column has an availability record;
- deterministic derived features identify their complete input lineage;
- every `(as_of_session, ticker)` is eligible under the recorded universe;
- no duplicate feature-availability identity exists;
- no availability timestamp is later than the decision cutoff;
- no membership interval overlaps another interval for the same
  `(universe_id, ticker)`;
- revisions visible only later cannot overwrite an older historical record;
  and
- `point_in_time_data=True` is derived only when all coverage checks pass.

The caller must not be able to set `point_in_time_data=True` directly.

### 7.4 Data-source adapters

Define a small protocol rather than hard-coding a vendor:

```python
class PointInTimeSource(Protocol):
    def feature_records(...) -> Sequence[FeatureAvailabilityRecord]: ...
    def universe_membership(...) -> Sequence[UniverseMembershipRecord]: ...
    def source_manifest(...) -> Mapping[str, str]: ...
```

The existing yfinance path must explicitly identify itself as
retroactively-adjusted/exploratory. It must never synthesize historical
availability or universe membership.

An authoritative adapter cannot be completed without a source that actually
provides historical availability and constituent history. Document the
required external data rather than fabricating an implementation.

### 7.5 Tests

- a future availability timestamp is refused;
- an after-close datum is unavailable to a same-session pre-close decision;
- a later revision does not replace the historically visible value;
- missing lineage keeps `point_in_time_data=False`;
- complete valid lineage is the only path to `True`;
- current index members projected backward are labeled survivorship-biased;
- historical membership intervals select the correct names per session;
- timezone-equivalent timestamps have consistent ordering;
- sidecar hash mismatch refuses load; and
- prefix invariance: appending future source records cannot alter an earlier
  dataset snapshot.

### 7.6 Definition of done

The code can prove a fixture dataset point-in-time using explicit fixture
lineage. Real yfinance datasets remain honestly exploratory. If no external
authoritative source is configured, stop there and report that production
promotion remains blocked.

## 8. ML-LR-2 — durable experiment orchestration

### 8.1 Purpose

Replace ad hoc function calls with reproducible discovery and confirmation
runs whose inputs, outputs, code, and decisions are immutable.

### 8.2 Shared runner

Add `ml/experiments.py` with a small orchestration layer. It may coordinate
existing functions but must not hide task logic behind a framework.

Suggested API:

```python
run_experiment(
    spec: ExperimentSpec,
    dataset_directory: Path,
    output_directory: Path,
    code_commit: str,
) -> ExperimentRunRecord
```

The runner must:

1. load and verify the dataset manifest and hashes;
2. verify the spec task, feature set, label, benchmark, and horizon match;
3. generate purged grouped walk-forward folds;
4. fit transformations on training rows only;
5. fit frozen baselines before candidates;
6. evaluate all comparable models on identical validation rows;
7. retain out-of-fold predictions by independent date/event;
8. compute dependence-aware and multiplicity-adjusted uncertainty;
9. produce an immutable `EvaluationReport` and task-specific details;
10. save model artifacts atomically and verify them after writing;
11. write a run manifest containing every output hash; and
12. leave `assistant/research_findings.json`, the model registry, proposals,
    and execution tables unchanged.

### 8.3 CLI

Add a dedicated script, not a subcommand that shares execution code:

```text
scripts/run_ml_experiment.py
```

Example interface:

```text
python scripts/run_ml_experiment.py \
  --spec research/ml_specs/volatility-discovery-v1.json \
  --dataset-dir artifacts/datasets/volatility-v1 \
  --output-dir artifacts/experiments/volatility-v1
```

Required CLI properties:

- caller-supplied paths;
- non-zero exit on hash, schema, leakage, coverage, or fit failure;
- JSON summary on stdout;
- no hidden network fetch during a confirmation run;
- no overwrite when an experiment ID exists with different content;
- exact retries are idempotent; and
- `--mode confirmation` refuses a spec whose hash differs from the frozen
  confirmation request.

### 8.4 Confirmation discipline

Discovery and confirmation must use different immutable experiment IDs.
Confirmation may not:

- add or remove features after seeing confirmation results;
- change the benchmark or horizon;
- retune hyperparameters;
- change failure slices or the primary outcome;
- select a favorable block length after inspecting results; or
- omit failed candidate variants from the research-look count.

If confirmation fails, the report verdict is rejected. A new idea requires a
new discovery experiment and counts as another research look.

### 8.5 Tests

- complete fixture experiment is byte/hash reproducible;
- column reordering, artifact corruption, and spec mismatch are refused;
- transformations receive training rows only;
- candidates and baselines share validation identities;
- a pure-noise experiment cannot receive a promising verdict;
- a planted effect is detectable without leaking future rows;
- a confirmation-spec mutation is refused;
- an exact rerun is idempotent;
- a conflicting rerun is refused; and
- all execution and proposal tables remain empty.

### 8.6 Definition of done

A single command reproduces the same fixture report and artifacts from the
same spec/dataset/commit. Real-data output is still exploratory unless ML-LR-1
has established full point-in-time coverage.

## 9. ML-LR-3 — complete volatility and portfolio-risk research

### 9.1 Scope

Make volatility the first predictive model eligible for shadow operation.
It is a risk forecast, not an alpha selector.

### 9.2 Portfolio target builder

Add `ml/portfolio_volatility.py` with pure functions that accept already
loaded position/equity records. Do not import a broker or execution service.

Build two explicitly different targets:

1. **frozen-weight forward volatility** — weights known at `as_of_session`
   applied to the next `horizon_sessions` aligned security returns; and
2. **realized account volatility** — flow-adjusted account-equity returns,
   used only when daily equity and external-flow coverage are complete.

Never silently substitute one target for the other.

For frozen weights:

- derive weights from exact stored market values;
- retain cash as zero-volatility exposure rather than renormalizing it away;
- reject negative weights unless the mandate later supports shorts;
- align every security explicitly by session;
- refuse a target when a held security lacks a required future return;
- record the exact position snapshot hash and price input hashes; and
- never use a position snapshot captured after the forecast cutoff.

### 9.3 Unit convention

Choose and enforce one convention:

- model targets and fold metrics use daily-return standard deviation in
  percent, matching `compute_forward_realized_vol_labels`; and
- display output may annualize by `sqrt(252)`, with the serialized field name
  explicitly stating `annualized`.

Do not compare a daily-percent target with an annualized baseline.

### 9.4 Evaluation completion

Extend the volatility experiment to report:

- QLIKE and MAE against trailing and EWMA baselines;
- empirical prediction intervals built only from prior out-of-fold residuals;
- interval coverage by fold and aggregate;
- Brier score, log loss, and calibration for a preregistered mandate ceiling;
- warning lead time and false-warning rate versus trailing volatility;
- coverage/refusal rates;
- performance by year, ticker, volatility regime, and earnings proximity;
- portfolio and per-security results separately; and
- fold wins against EWMA, never only an aggregate win.

The boosted candidate remains rejected unless it beats EWMA on the
preregistered primary metric in the required number of untouched folds.

### 9.5 Typed output

Extend or wrap `VolatilityForecast` so every shadow forecast includes:

```text
task and subject
model key and artifact hash
as-of session and exact target-availability timestamp
horizon
daily and annualized units where applicable
point estimate and interval
threshold probability and calibration status
trailing and EWMA baseline values
feature freshness and missingness
evidence status
production_authoritative=false
what_this_does_not_mean
```

If calibration has not cleared its preregistered gate, serialize the
probability as experimental and never label it confidence.

### 9.6 Tests

- cash is not renormalized away;
- a future position snapshot is rejected;
- mismatched histories refuse rather than silently drop a held name;
- zero/negative/non-finite weights or prices fail safely;
- daily and annualized units cannot be mixed;
- model and baselines use identical validation rows;
- intervals use only residuals available before the prediction date;
- planted volatility beats a naive baseline;
- a crisis-only aggregate win fails multi-fold stability; and
- portfolio forecasts create no proposal or execution state.

### 9.7 Definition of done

The per-security and portfolio experiment runners emit immutable reports and
typed forecasts on fixtures. Real portfolio research may remain underfilled
until enough daily position/equity snapshots have accumulated; report this
as unavailable rather than backfilling guessed holdings.

## 10. ML-LR-4 — complete earnings-gap and filing-context research

### 10.1 Event dataset

Add `ml/earnings_features.py`. Each row must have a stable event identity
derived from ticker, canonical announcement instant, source, and source-event
ID. Deduplicate timezone-equivalent instants.

Feature rows may contain only information available before the event cutoff:

- prior signed and absolute gaps;
- prior surprise values with reliable historical availability;
- pre-event volatility and downside volatility;
- market/industry volatility and trend;
- residual momentum;
- volume/liquidity;
- days since the prior event; and
- analyst revisions only when their point-in-time timestamp is authoritative.

Explicitly prohibit post-release price, transcript text, revised consensus,
and later filings from pre-event features.

If announcement timing is naive, unknown, or intraday, the primary experiment
must record an unavailable event. Do not guess.

### 10.2 Models

Evaluate in frozen order:

1. historical median absolute gap by ticker/industry where supported;
2. logistic probability that absolute gap exceeds the threshold;
3. a separate downside-tail classifier;
4. quantile models for absolute magnitude; and
5. boosted models only after simple models and support checks.

All fitting and evaluation must group by distinct event date. Repeated
feature rows, documents, or tickers do not create independent evidence.

### 10.3 Evaluation

Report:

- distinct events and tickers;
- upside/downside class support in every fold;
- Brier score and log loss;
- calibration curves and calibration error;
- precision/recall at a threshold declared in the spec;
- pinball loss and interval coverage;
- performance by ticker, industry, year, volatility regime, and release
  timing; and
- comparison with historical-median and unconditional-frequency baselines.

The current software minimum of 30 events and 8 observations per tail is a
fit-refusal threshold, not a promotion threshold. A confirmation spec must
justify its sample requirement using effect size or power, and must count
distinct events rather than rows.

### 10.4 Typed output

Add `EarningsGapForecast` with no trade fields:

```text
ticker and event ID
announcement timestamp and release timing
as-of and target-availability timestamps
absolute-gap interval
probability above absolute threshold
probability below downside threshold
baseline values
calibration status
event support counts
model/artifact/feature hashes
evidence status
production_authoritative=false
```

This output may eventually accompany the deterministic earnings blackout. It
must never override the calendar rule or obstruct risk reduction.

### 10.5 Filing provider, context only

Add a separate orchestration script such as:

```text
scripts/run_filing_extraction.py
```

The script may reuse the existing generic LLM provider/audit infrastructure
and `ml/filings.py`, but it must have no broker, proposal, or execution tools.

Controls:

- fixed system instructions and versioned prompt/schema;
- retrieved filing text supplied only as untrusted data;
- no tool calls initiated by retrieved text;
- every excerpt must be found verbatim in a source document;
- every date, amount, percentage, and unit must validate;
- direct extraction and model inference remain visibly distinct;
- deterministic validation is rerun when creating the audit record;
- invalid extraction is persisted as rejected, not silently discarded; and
- extracted sentiment never becomes a model feature without a separate
  point-in-time experiment.

### 10.6 Tests

- timezone and DST event mapping;
- holiday/weekend and missing-session refusal;
- duplicate event instants count once;
- future revisions and transcripts are rejected from pre-event features;
- thin folds refuse fitting;
- fabricated inference numbers fail just like fabricated direct numbers;
- prompt-injection text cannot change output schema or call a tool;
- rejected extraction cannot produce an accepted audit record; and
- no event or filing output alters a proposal or blackout rule.

### 10.7 Definition of done

The event runner and typed output work on point-in-time fixtures and produce
complete evaluation reports. Real confirmation remains blocked if historical
surprise/revision timestamps or event coverage are not authoritative.

## 11. ML-LR-5 — ranker economic evaluation

### 11.1 Purpose

Complete the ranker as a research experiment. Do not expose it to the live
assistant merely because its statistical IC is positive.

### 11.2 Dataset and universe

Require ML-LR-1 lineage for any confirmation claim. The experiment spec must
freeze:

- historically correct universe or deliberately fixed-universe claim;
- QQQ or SOXX benchmark before confirmation;
- 20-session next-open-to-exit label;
- rebalance cadence;
- maximum positions and per-name/sector constraints;
- liquidity screen;
- transaction costs, slippage, taxes, and capital assumptions; and
- every feature/model/horizon variant in the research-look count.

### 11.3 Statistical evaluation

Retain:

- date-level Spearman IC;
- dispersion, information ratio, and sign consistency;
- top-minus-bottom quantile spread;
- dependence-aware block-bootstrap uncertainty; and
- multiplicity correction.

Add explicit failure slices by year, volatility regime, market direction,
earnings proximity, liquidity bucket, and ticker. A good average hiding one
destructive regime is not sufficient.

### 11.4 Shared-capital economic simulation

Reuse the existing backtest, exact-money, portfolio, and tax-lot machinery
where possible. Do not simulate every ticker as an independent account.

The simulation must:

- operate one shared pool of capital;
- enter at the next tradable open;
- prevent overlapping signals from spending the same cash twice;
- enforce turnover, concentration, liquidity, and mandate constraints;
- apply slippage and transaction costs;
- apply the configured tax assumptions and lot-selection behavior;
- compare against buy-and-hold and residual-momentum baselines using the same
  capital and dates;
- report CAGR only with drawdown, expected shortfall, time under water,
  upside/downside capture, turnover, tax drag, and rejected-order counts; and
- preserve every simulated decision for audit.

The ranker cannot receive a promising verdict unless statistical and economic
results both clear the frozen gates.

### 11.5 Tests

- same-day names never count as independent time observations;
- shared capital cannot be overspent;
- changing input ticker order does not change allocations;
- no look-ahead open or future membership enters a decision;
- costs and taxes monotonically reduce otherwise identical performance;
- liquidity/concentration limits bind at exact boundaries;
- pure noise produces neither statistical nor economic skill;
- a discovery winner that fails confirmation is rejected; and
- the runner produces observations only, never `TradeIntent` or proposals.

### 11.6 Definition of done

The runner can evaluate a ranker honestly. It does not mean the ranker is
eligible for live use. Eligibility additionally requires authoritative data,
an untouched confirmation, sufficient shadow history, and ML-LR-9 approval.

## 12. ML-LR-6 — automated shadow runtime and evidence epochs

### 12.1 Purpose

Generate predictions on schedule, record failures as evidence, mature outcomes
exactly once, and prevent results from different systems being pooled.

### 12.2 Storage schema

Add migration-safe tables following `AssistantStore._initialize()` patterns:

```text
ml_evidence_epochs
  evidence_epoch TEXT PRIMARY KEY
  model_key TEXT NOT NULL
  task TEXT NOT NULL
  started_at TEXT NOT NULL
  closed_at TEXT
  status TEXT NOT NULL
  lineage_json TEXT NOT NULL
  lineage_hash TEXT NOT NULL
  created_by TEXT NOT NULL

ml_shadow_runs
  run_id TEXT PRIMARY KEY
  schedule_key TEXT NOT NULL
  scheduled_for TEXT NOT NULL
  started_at TEXT NOT NULL
  completed_at TEXT
  status TEXT NOT NULL
  code_commit TEXT NOT NULL
  configuration_hash TEXT NOT NULL
  evidence_epoch TEXT NOT NULL
  prediction_count INTEGER NOT NULL
  unavailable_count INTEGER NOT NULL
  error_json TEXT
```

Add nullable legacy-compatible `evidence_epoch` and `shadow_run_id` columns to
`ml_predictions`, then require them for all new scheduled predictions.

Use a partial unique index to allow at most one active epoch per
`(model_key, task)`. Use a unique identity for `(schedule_key, scheduled_for)`
so an exact retry is idempotent and concurrent runs cannot duplicate evidence.

Lineage JSON must include at least:

```text
model manifest/artifact hash
experiment/evaluation report hash
feature set and label version
dataset/provider identity
policy-relevant configuration hash
code commit
schedule version
```

Any change starts a new epoch. Do not pool across epochs.

### 12.3 Shadow orchestration

Add `ml/shadow.py` for pure scheduling/maturity rules and:

```text
scripts/run_ml_shadow.py
```

Suggested commands:

```text
predict --task volatility --scheduled-for ...
mature --task volatility --as-of ...
monitor --task volatility --output ...
status --task volatility
```

The script may import both `ml` and `AssistantStore`; `assistant/` must not
import model code.

Prediction behavior:

1. claim the scheduled run transactionally;
2. load only a registered shadow model with verified artifact hash;
3. build features using the recorded decision cutoff;
4. record one available or unavailable attempt per subject;
5. include frozen baseline values;
6. close the run with counts and durable errors; and
7. never retry a partial run by rewriting an existing prediction.

Maturity behavior:

- derive the target session from the exchange calendar and task label;
- require all target prices/events to be observable;
- reject outcome attachment before exact target availability;
- attach each immutable outcome once;
- reject outcomes for unavailable predictions;
- record missing target data as pending/unavailable, never as zero; and
- support crash-safe reruns.

### 12.4 Scheduling

Add a separate installer:

```text
scripts/install_windows_ml_shadow_tasks.ps1
```

Do not add ML work to the order monitor or deterministic operations cycle.
Use separate scheduled tasks, `MultipleInstances IgnoreNew`, explicit
execution limits, retries, and a caller-supplied Python/database/artifact
path. Default predictions should run only after the relevant market data is
final.

### 12.5 Operational failures

Persist and alert on:

- artifact mismatch;
- missing model registration;
- stale/missing features;
- provider failure;
- clock or timezone error;
- database lock after bounded retries;
- duplicate/conflicting scheduled run;
- outcome underfill;
- evidence-epoch mismatch; and
- unexpected schema/model output.

These failures must never stop reconciliation, risk reduction, the order
monitor, or the kill switch.

### 12.6 Tests

- concurrent claims create one run;
- crash after some predictions resumes without rewriting them;
- exact retry is idempotent and conflict is loud;
- model/config/provider change requires a new epoch;
- predictions from different epochs are never pooled;
- exchange holidays mature on the correct session;
- unavailable attempts cannot mature;
- clock skew and naive timestamps fail closed;
- artifact corruption prevents scoring;
- operational errors are durable; and
- the full shadow cycle leaves every execution table unchanged.

### 12.7 Definition of done

A supervised task can run predict/mature/monitor repeatedly on fixtures and
paper data without manual database edits. The existence of a scheduler does
not make the model production-authoritative.

## 13. ML-LR-7 — complete monitoring and promotion dossier

### 13.1 Monitoring report

Extend `ml/monitoring.py` or add `ml/monitoring_reports.py` when the existing
module becomes too large. Report by evidence epoch:

- scheduled attempts, coverage, refusals, and reason counts;
- feature missingness, age, and stale counts;
- per-feature distribution drift with out-of-range observations included;
- output drift;
- realized error by rolling unique-date window;
- calibration and interval coverage;
- performance versus each frozen baseline on identical matured observations;
- failure slices by year/regime/ticker/event category;
- lineage consistency;
- target/outcome underfill;
- operational run failures; and
- whether the independent sample is sufficient for each conclusion.

Never pool ticker rows as independent observations when their dates overlap.
Never report a drift or calibration conclusion from a thin sample without an
explicit insufficiency marker.

### 13.2 Promotion dossier

Add a frozen `PromotionDossier` report. It is read-only and always carries
`production_authoritative=False`.

It should collect hashes and results for:

```text
discovery specification and report
confirmation specification and report
dataset/availability/universe manifests
model manifest and artifact
economic simulation
shadow evidence epoch
coverage/calibration/drift/baseline report
known limitations and unresolved incidents
proposed adapter scope
```

Its `promotion_blockers` must include every unmet gate and must always include
`separate_owner_promotion_review_required`. No method on the dossier may
change registry status.

### 13.3 Initial review gates

The confirmation spec must set exact gates before results are observed. At a
minimum:

- complete point-in-time and universe coverage for the claim being made;
- at least three untouched walk-forward folds when data permits;
- baseline wins in more than one fold, not one aggregate crisis-period win;
- multiplicity-adjusted and dependence-aware uncertainty;
- stable direction under preregistered block-length sensitivity;
- acceptable calibration and interval coverage;
- adequate prediction coverage with explained refusals;
- economics after costs/taxes/shared capital where trading is involved;
- no material mandate degradation;
- zero unresolved leakage or lineage incidents; and
- a sufficiently long matured shadow epoch.

Do not hard-code a tiny universal sample count. The spec must justify sample
requirements using task frequency, overlap, effect size, and power. As
operational lower-bound guidance only:

- volatility evidence should span multiple volatility regimes and at least a
  year of scheduled dates before live influence is considered;
- earnings confirmation should contain materially more distinct events and
  tail outcomes than the software fit minimum;
- ranker evidence should cover multiple market years/regimes with historical
  membership; and
- execution-quality evidence requires a representative live-order sample,
  not paper orders.

### 13.4 Tests

- predictions from two epochs cannot enter one dossier;
- missing confirmation, economics, calibration, or lineage creates blockers;
- caller mutation cannot alter a dossier after hashing;
- sample counts use unique dates/events;
- model underperformance cannot be hidden by missing baseline rows;
- an operational incident remains visible after later successful runs; and
- dossier construction has no registry or execution side effect.

### 13.5 Definition of done

The application can explain why a model is or is not eligible to be reviewed.
It still cannot promote the model.

## 14. ML-LR-8 — read-only user presentation

### 14.1 First surface

Implement a dedicated read-only command before changing `DecisionPacket`:

```text
python scripts/run_ml_shadow.py status --task volatility
```

Display:

- task, model, version, and evidence epoch;
- as-of date and horizon;
- estimate, interval, and frozen baselines;
- calibration status;
- feature freshness and refusals;
- evidence status and promotion blockers;
- the label below; and
- no recommendation, side, quantity, target weight, or approval control.

Required label:

```text
Experimental model observation — not a recommendation and not used by the
execution gate.
```

### 14.2 Briefing integration, separate review

Only after the dedicated surface is stable may a later PR add read-only
briefing context. Prefer a script-level composition that reads serialized
observations rather than making `assistant/` import ML model code.

If an assistant adapter is unavoidable:

- allowlist exactly one file in `test_ml_import_boundary.py`;
- restrict it to storage and frozen serialized contracts;
- add an AST test forbidding imports from execution, proposal, broker,
  allocation, approval, and risk-gate modules;
- do not change `DecisionPacket` without an explicit schema-version decision;
  and
- make adapter failure omit the ML section without failing the briefing.

### 14.3 Tests

- unavailable/stale output displays unavailable, never a default estimate;
- uncalibrated probability is not labeled confidence;
- rejected evidence is visibly rejected;
- no action-shaped keys or UI controls exist;
- display failure does not fail the deterministic briefing;
- presentation cannot mutate stored predictions; and
- import-boundary and zero-execution-state tests remain green.

### 14.4 Definition of done

The owner can inspect shadow evidence without giving it trading authority.

## 15. ML-LR-9 — promotion registry and bounded adapter review

**Do not implement this milestone as part of the initial Claude sequence.**
It requires an explicit later owner request after a real dossier exists.

### 15.1 Registry transition

If authorized, extend model status through explicit, audited transitions:

```text
research -> shadow -> confirmation_candidate -> approved_context_only -> retired
```

Avoid a generic `production` status. `approved_context_only` must state the
exact allowed consumer and fields.

A transition must require:

- current status and expected manifest hash;
- promotion dossier hash;
- owner identity and timestamp;
- explicit scope;
- expiration/review date;
- recorded blockers equal to none except the owner review being satisfied;
- an immutable audit record; and
- no automatic invocation from training or monitoring.

### 15.2 First allowed adapter

The first approved adapter should remain context-only. If a later request
permits proposal influence, start with a deterministic new-risk constraint,
not a trade generator:

- it may reduce or refuse **new/increasing** exposure within a declared scope;
- it may never increase size;
- it may never create a ticker, direction, or order;
- it may never modify or delay a risk-reducing sell;
- it may never bypass the deterministic execution gate;
- stale, missing, uncalibrated, out-of-epoch, or rejected output has no
  effect; and
- every changed proposal must display the original value, bounded change,
  model observation ID, and deterministic reason.

The adapter requires its own adversarial review, tests at every exact policy
boundary, and a feature flag defaulting off.

## 16. ML-LR-10 — limited-capital canary and rollback

This is an operational process, not something Claude can complete with code
alone.

When and only when ML-LR-9 is approved:

1. deploy the adapter disabled;
2. compare disabled/enabled decisions in shadow;
3. resolve every divergence and incident;
4. enable for a tiny declared symbol/notional scope;
5. retain all deterministic limits and human approval;
6. monitor live coverage, latency, drift, calibration, and baseline-relative
   outcomes;
7. scale only after a separately declared review period; and
8. roll back immediately on lineage, freshness, calibration, or operational
   failure.

Add an ML-specific disable switch independent of the execution kill switch.
Disabling ML must restore deterministic behavior without stopping legitimate
risk reduction or reconciliation.

Never use confidence-scaled sizing, automatic retraining, automatic rollback
to an unverified artifact, or automatic promotion.

## 17. ML-LR-11 — execution-quality modeling remains deferred

Do not implement an execution model until a representative live-order dataset
exists and the owner explicitly authorizes the research.

Before that future milestone, the application may improve deterministic order
telemetry by recording:

- decision, arrival, submit, acknowledgement, fill, cancel, and replacement
  timestamps;
- bid/ask/spread and quote age;
- requested/filled quantity;
- order type and limit distance;
- partial fills and replacement chains;
- decision, arrival, and fill prices;
- liquidity bucket and recent volume; and
- paper/live source identity.

Paper and live records must remain distinguishable and should not be pooled by
default. Deterministic telemetry capture is allowed; fitting a paper-trained
model and calling it live-ready is not.

## 18. Cross-cutting operational requirements

### 18.1 Fail-closed behavior

Return unavailable with durable reasons for:

- missing/stale/non-finite features;
- incomplete lineage;
- model or artifact mismatch;
- unsupported schema;
- column-order mismatch;
- missing baseline;
- insufficient class/event/date support;
- incomplete target horizon;
- evidence-epoch mismatch; and
- provider or scheduler failure.

Do not impute a confident default in an inference path.

### 18.2 Time and calendar rules

- market sessions use the NYSE calendar where applicable;
- generated/event timestamps are timezone-aware;
- market decisions use America/New_York session identity;
- exact target availability is recorded at prediction creation;
- date arithmetic never substitutes for trading-session arithmetic; and
- all event timestamps are converted to Eastern before before-open,
  intraday, or after-close classification.

### 18.3 Numeric rules

- validate `math.isfinite` before range comparisons;
- preserve decimal points and units;
- use exact decimals for money and position history;
- reject non-positive values where model mathematics requires positivity;
- score candidates and baselines on identical paired observations; and
- never let NaN silently turn into “no concentration,” “no drift,” or a
  favorable reduction in evaluation coverage.

### 18.4 Immutability and conflict rules

- exact retry returns the original record;
- same identity with different content raises;
- artifact/report/dataset writes are atomic;
- caller-owned nested mappings cannot mutate a constructed contract;
- migrations preserve legacy records but do not guess missing lineage; and
- legacy predictions without provable target maturity cannot receive new
  outcomes.

### 18.5 Security and model loading

- load joblib/pickle only from the controlled artifact directory;
- verify manifest, expected identity, schema, and SHA-256 before load;
- never load a model or prompt supplied by retrieved text;
- filing/transcript content has no tools or instruction authority; and
- secrets and provider credentials remain outside artifacts and reports.

## 19. Required verification for every milestone

Run at minimum:

```text
python -m pytest -q <focused tests>
python -m pytest -q tests
python -m compileall -q assistant data execution risk scripts signals strategies backtest ml tests baskets.py config.py
git diff --check
```

Also run milestone-specific fault probes that tests do not make obvious:

- duplicate/conflicting identity;
- same-day premature outcome;
- timezone-equivalent earnings event;
- NaN/infinity in every public numeric contract;
- shifted drift data outside reference bounds;
- missing baseline row versus candidate row;
- artifact corruption;
- scheduler crash/retry;
- evidence-epoch change; and
- proof that proposal, broker, reservation, allocation, and execution tables
  remain unchanged.

Test counts are not an acceptance criterion. Report the actual behavioral
invariants demonstrated.

## 20. Handoff checklist for each Claude milestone

Claude must provide the reviewer:

```text
Branch and commit(s)
Milestone claimed
Files added/changed
Schema migrations
Public contract changes
Exact experiment/report artifacts created
Focused and full test commands/results
Known gaps and intentionally skipped work
External data/evidence blockers
Any assistant-facing or live behavior change
Why execution and risk-reduction boundaries remain intact
```

The reviewer should independently inspect:

- clock and availability semantics;
- duplicate/conflict behavior;
- non-finite and thin-sample refusal;
- baseline comparability;
- factor/event/date independence assumptions;
- artifact and lineage integrity;
- shallow versus deep immutability;
- claimed milestone completeness; and
- imports or adapters that could reach proposals or execution.

## 21. Recommended immediate instruction to Claude

Use this exact scope for the next task:

> Implement **ML-LR-0 only** from
> `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`. Inspect the current
> branch and existing ML contracts first. Do not begin ML-LR-1, do not add a
> shadow scheduler, do not integrate ML into the assistant, and do not change
> proposal or execution behavior. Add focused tests, run the full suite,
> update the status document conservatively, commit on a dedicated branch,
> and stop for review.

This deliberately small first step is the control against another broad
implementation that passes tests while hiding cross-module contract errors.
