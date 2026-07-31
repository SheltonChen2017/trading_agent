# Machine-Learning Implementation Strategy

**Status:** implementation handoff

**Initial authority:** research and shadow observation only

**Primary objective:** improve portfolio-risk awareness and research quality without giving a model authority to create, size, approve, or execute trades

**Audience:** implementation agent and subsequent code reviewer

## 1. Outcome and guiding decision

Machine learning should enter this application as a versioned, auditable
observation layer. It should not enter as an autonomous trading agent.

The first useful release is a **Tech Portfolio Risk Forecaster** that adds:

1. latent-factor and effective-concentration analysis;
2. forward portfolio-volatility and correlation-risk estimates;
3. earnings-gap risk estimates for held and watched technology stocks; and
4. durable shadow predictions that can be judged against future outcomes.

Only after those foundations have accumulated credible out-of-sample evidence
should the project attempt a benchmark-relative stock ranker. Language-model
analysis of filings and execution-quality modeling are later phases.

The required authority flow is:

```text
point-in-time source data
        |
        v
versioned feature snapshot + dataset manifest
        |
        v
versioned model artifact
        |
        v
typed prediction with uncertainty and authority=false
        |
        v
research report / shadow evidence
        |
        v
explicit research-registry promotion decision
        |
        v
deterministic assistant strategy adapter (future, separate change)
        |
        v
typed proposal -> exact human approval -> execution gate -> broker
```

There must be no shortcut between a model output and a trade intent.

## 2. Why the prior ML design must not be restored

Commit `e6409b2` removed a disconnected ML/signal-sizing island. That code
trained a small Random Forest to predict whether a scanner event would be a
winner and converted its probability directly into position size. It had four
fundamental problems that this design must not repeat:

- it was disconnected from the production proposal and execution workflow;
- a binary `win` label discarded return magnitude and downside-tail severity;
- model probability was treated as economic confidence and fed into sizing;
- it lacked the current research-registry, immutable-report, paper-lineage,
  and promotion-gate controls.

Do not restore `risk/manager.py`, `scripts/run_agent.py`, the old
`scripts/train_model.py`, or confidence-scaled sizing. Reuse concepts only
where they fit the contracts below.

## 3. Non-negotiable safety and architecture boundaries

### 3.1 Research versus production

The existing boundary remains authoritative:

- `ml/`, `signals/`, `strategies/`, `backtest/`, and ML experiment runners are
  research surfaces;
- `assistant/`, `risk/execution_gate.py`, `execution/`, and the CLI/UI entry
  points are production-capable surfaces;
- no module under `execution/` or `risk/execution_gate.py` may import `ml`;
- the initial implementation must not add an `ml` import anywhere under
  `assistant/` except a future, separately reviewed shadow-observation adapter;
- no model status automatically becomes production authority;
- no model may change policy limits, bypass a kill switch, manufacture an
  approval phrase, or construct an execution authorization.

Add an import-boundary regression test. The test should fail if `execution/`,
`risk/execution_gate.py`, `assistant/execution_service.py`, or
`assistant/allocation_batch.py` imports any `ml` module.

### 3.2 Model outputs are observations, not instructions

Initial output schemas must not contain these fields:

- `side`;
- `shares` or `quantity`;
- `order_type`;
- `limit_price`;
- `stop_price`;
- `approved`;
- `execute`;
- `authorization`.

They may contain a ticker, horizon, predicted distribution, uncertainty,
feature/data timestamps, model identity, and evidence status. Field names and
display text should describe estimates, not recommendations.

### 3.3 Fail closed and preserve risk reduction

- Missing, stale, non-finite, or schema-incompatible features produce an
  unavailable prediction, never a default high-confidence prediction.
- Model failure must not prevent a deterministic risk-reducing sell proposal.
- Model output must not weaken, override, or delay the execution gate.
- An unavailable model must be operationally equivalent to no model.
- A stale model may continue to be evaluated historically, but it must not be
  displayed as current evidence.

### 3.4 Point-in-time truth

The current yfinance-backed research pipeline explicitly identifies its data
as `point_in_time_data=false`. That is acceptable for exploratory development,
but it is a promotion blocker.

For each feature value, the implementation must distinguish:

- `event_at`: when the underlying event occurred;
- `available_at`: when the application could first have known it;
- `observed_at`: when this pipeline retrieved or recorded it;
- `as_of_session`: the market session for which the feature is usable.

No revised fundamental, restated analyst history, future universe membership,
or after-close event may appear in a feature snapshot that predates its
availability.

## 4. Implementation sequence and pull-request boundaries

Implement this plan as small, reviewable changes. Do not combine all phases in
one pull request.

| PR | Scope | Production behavior change |
|---|---|---|
| ML-1 | Contracts, manifests, hashing, dependency pin, boundary tests | None |
| ML-2 | Point-in-time feature/label builder and purged walk-forward splits | None |
| ML-3 | Latent-factor concentration model and report | Read-only report only |
| ML-4 | Volatility/correlation forecasting and evaluation | Read-only report only |
| ML-5 | Earnings-gap risk model and evaluation | Read-only report only |
| ML-6 | Shadow prediction persistence and monitoring | Writes observations only |
| ML-7 | Benchmark-relative stock ranker research | None |
| ML-8 | Structured filing/transcript extraction | Context only |
| ML-9 | Execution-quality research after adequate observations | Advisory only |
| ML-10 | Any proposal integration | Separate promotion review required |

Every PR must include tests, documentation, and an explicit statement that it
does or does not alter proposal/execution authority.

## 5. ML-1: contracts, manifests, and artifact integrity

### 5.1 Dependencies

Add pinned versions of:

- `scikit-learn` for preprocessing, PCA, shrinkage covariance, calibration,
  linear models, and histogram gradient boosting;
- `joblib` for model serialization if it is not installed transitively.

Do not add XGBoost, LightGBM, PyTorch, TensorFlow, MLflow, or a hosted model
registry initially. The sample size and current use cases do not justify the
complexity.

### 5.2 Proposed package

```text
ml/
  __init__.py
  contracts.py
  hashing.py
  artifacts.py
  datasets.py
  features.py
  labels.py
  splits.py
  baselines.py
  evaluation.py
  factor_risk.py
  volatility.py
  earnings_gap.py
  cross_sectional.py
  monitoring.py
```

Keep task-specific modules absent until their phase begins; the list above is
the intended destination, not a request to create empty placeholders.

### 5.3 Core contracts

Use frozen dataclasses and JSON-serializable primitive values. Reject unknown
schema versions and non-finite numeric values.

`DatasetManifest` should contain at least:

```text
schema_version
dataset_id
created_at
task
feature_set_version
label_version
source_descriptions
point_in_time_data
requested_start_date / requested_end_date
actual_start_date / actual_end_date
row_count / distinct_session_count / ticker_count
universe_definition
entry_timing
target_horizon_sessions
embargo_sessions
transaction_cost_bps
tax_assumptions
input_hashes
dataset_hash
git_commit
```

`ModelManifest` should contain at least:

```text
schema_version
model_id / model_version
task
created_at
dataset_id / dataset_hash
feature_set_version / ordered_feature_names
label_version
algorithm
hyperparameters
random_seed
training_window
validation_windows
dependency_versions
artifact_hash
evaluation_report_hash
evidence_status
production_authoritative
```

`PredictionRecord` should contain at least:

```text
schema_version
prediction_id
model_id / model_version / artifact_hash
dataset_or_feature_snapshot_hash
task
ticker or portfolio_account_key
as_of_session / generated_at
horizon_sessions
prediction values
uncertainty or interval
data_available_at
feature_freshness
availability status and refusal reasons
evidence_status
production_authoritative=false
```

Make `production_authoritative` impossible to set to true from ordinary model
training or inference code. Authority must be derived later from a separate,
explicit registry/promotion decision.

### 5.4 Artifact storage

Use a caller-supplied artifact directory; do not hard-code a user path.
Artifacts must be written atomically:

1. serialize to a temporary file in the destination directory;
2. flush and close it;
3. compute SHA-256 over the bytes;
4. atomically replace the final path;
5. write the manifest containing that hash atomically;
6. verify the hash again when loading.

Never load an untrusted pickle/joblib file. Loading must require a manifest,
known schema, expected model ID/version, and matching artifact hash. Document
that joblib artifacts are code-execution-capable and must come only from the
application's own controlled artifact directory.

### 5.5 ML-1 tests

- manifest round trip;
- rejection of missing required fields;
- rejection of unknown schema versions;
- rejection of NaN and infinity anywhere in numeric output;
- artifact hash mismatch refusal;
- ordered feature mismatch refusal;
- unavailable output when features are missing;
- deterministic IDs/hashes for identical canonical inputs;
- different hash for any behavior-relevant change;
- import-boundary enforcement;
- proof that no execution-capable module imports `ml`.

## 6. ML-2: point-in-time dataset and feature engine

### 6.1 Storage shape

Keep raw research datasets outside the production SQLite database. Use
immutable, content-hashed CSV gzip or Parquet artifacts plus JSON manifests.
If Parquet is selected, pin its engine explicitly; do not rely on an undeclared
optional dependency.

Production/shadow predictions will later go into SQLite, but large training
matrices should not.

Every feature matrix must use the unique key:

```text
(as_of_session, ticker)
```

Duplicate keys, unsorted timestamps, timezone-naive event timestamps, and
future availability must fail dataset construction.

### 6.2 Initial market features

Compute features using values known by the end of `as_of_session`. If the
target assumes next-open execution, features may use that session's finalized
close but never the next session's open.

Initial features:

- total returns over 1, 5, 20, 60, 126, and 252 sessions;
- residual returns versus QQQ and SOXX over 5, 20, and 60 sessions;
- distance from 20-, 50-, and 200-session moving averages;
- rolling realized volatility over 10, 20, and 60 sessions;
- downside semivolatility over 20 and 60 sessions;
- rolling maximum drawdown over 60 and 252 sessions;
- average dollar volume and current/average volume ratio;
- trailing beta and correlation to SPY, QQQ, and SOXX;
- rolling overnight-gap statistics;
- market trend/volatility classification from existing generic analytics;
- VIX, credit-spread, and yield-curve values as descriptive context features,
  never as presumed authoritative signals;
- calendar features such as day of week and distance to known earnings.

Do not include ticker price level without a clear transformation. Do not use a
feature merely because it exists; each must have a timestamp and economic
rationale.

### 6.3 Cross-sectional transforms

For ranker research, calculate percentile ranks or robust z-scores within each
session. Fit any learned scaler on training dates only. Never fit a global
scaler before splitting the data.

### 6.4 Labels

Keep labels separate from features and join only during research evaluation.

Define explicit label versions:

- `forward_excess_return_20d_next_open_v1`: return from the next tradable open
  through the configured 20-session exit, less the aligned QQQ or SOXX return
  and round-trip cost;
- `forward_realized_vol_20d_v1`: realized volatility over the following 20
  sessions;
- `forward_abs_earnings_gap_v1`: absolute earnings gap using the release-time
  mapping described in section 9;
- `forward_downside_threshold_v1`: whether the forward return crosses a
  preregistered downside threshold.

Labels must record the entry and exit timestamps/prices used. Tail rows without
a complete forward horizon must be dropped and counted in the manifest.

### 6.5 Purged, grouped walk-forward splitting

Implement a date-grouped splitter; do not use random train/test splits or
ordinary row-level `TimeSeriesSplit` without purging.

For each fold:

1. group all rows from the same `as_of_session` together;
2. train only on sessions strictly earlier than the validation window;
3. purge training examples whose label horizon overlaps validation;
4. apply an embargo at least as long as the prediction horizon;
5. fit transformations and models on the training fold only;
6. score the untouched validation fold;
7. retain dates and predictions for dependence-aware analysis.

The splitter must expose the actual train/validation date ranges and purged row
counts for the evaluation report.

### 6.6 ML-2 tests

- synthetic future feature is detected and refused;
- after-close event is unavailable for a same-session decision;
- every ticker on one date stays in one fold;
- no label interval overlaps a validation window;
- embargo is enforced exactly at its boundary;
- transformations see training rows only;
- mismatched price histories align explicitly by date;
- duplicate rows, NaT, NaN, infinity, zero price, and non-positive volume are
  handled according to documented rules;
- split output is deterministic for a fixed manifest and seed.

## 7. ML-3: latent-factor concentration model

This is the highest-value first model for a technology-heavy portfolio. It is
not an alpha signal.

### 7.1 Method

Implement two baselines before PCA:

1. existing pairwise-correlation clustering from `assistant/risk_copilot.py`;
2. shrinkage covariance using `sklearn.covariance.LedoitWolf`.

Then implement PCA on aligned, finite daily returns:

- default trailing window: 252 sessions;
- minimum observations: explicit and tested;
- standardize returns using training/window-local statistics;
- choose the number of displayed factors by cumulative explained variance,
  with a documented cap;
- orient component signs deterministically for stable reports;
- report loadings, explained variance, portfolio factor exposure, residual
  risk, and effective number of independent bets;
- label factors mechanically (`Factor 1`, `Factor 2`) unless a deterministic
  rule supports a descriptive name. Never ask an LLM to invent factor meaning.

### 7.2 Report contract

Return a typed report containing:

- model/data `as_of` date;
- common observation count and missing tickers;
- covariance estimator;
- explained variance by factor;
- per-position loadings and contribution to each factor;
- portfolio factor exposures;
- residual risk by position;
- effective independent-bet count;
- comparison with the existing correlation-cluster output;
- warnings and availability status.

It must not contain proposed trades or target weights.

### 7.3 Tests

- a synthetic shared semiconductor factor is recovered;
- independent assets do not appear as one concentrated factor;
- duplicate/constant series fail safely;
- mismatched histories align before calculation;
- NaN and infinity never produce a successful report;
- results are invariant to input ticker order apart from display ordering;
- component sign orientation is deterministic;
- missing history is surfaced, not interpreted as zero exposure.

## 8. ML-4: volatility and correlation-risk forecasting

### 8.1 Targets

Forecast 5-, 10-, and 20-session realized volatility, with 20 sessions as the
preregistered primary horizon for the first experiment. Forecast both:

- per-ticker volatility for held/watchlist securities; and
- portfolio volatility when historical holdings/weights are available.

The application currently records account equity history, but a faithful
historical portfolio-risk target also requires daily position/weight history.
Add a separate append-only position snapshot table rather than altering the
versioned `DecisionPacket` schema.

Proposed production table:

```text
portfolio_position_snapshots
  snapshot_id TEXT PRIMARY KEY
  account_key TEXT NOT NULL
  session_date TEXT NOT NULL
  captured_at TEXT NOT NULL
  ticker TEXT NOT NULL
  shares_text TEXT NOT NULL
  market_value_text TEXT NOT NULL
  price_text TEXT NOT NULL
  source TEXT NOT NULL
  snapshot_hash TEXT NOT NULL
```

Use the repository's `CREATE TABLE IF NOT EXISTS` pattern, exact decimal text,
append-only writes, unique constraints, indexes, and timezone-aware timestamps.
Do not make briefing fail merely because this auxiliary capture fails; emit an
operational warning and preserve the primary workflow.

### 8.2 Models

Evaluate in this order:

1. trailing realized volatility;
2. EWMA volatility;
3. linear/regularized regression on log volatility;
4. `HistGradientBoostingRegressor` only if it beats the baselines.

Possible features include lagged realized volatility, downside volatility,
absolute returns, market volatility, volume change, correlation regime, and
distance to earnings.

### 8.3 Metrics

Primary metrics:

- QLIKE loss;
- mean absolute error on volatility;
- interval coverage if prediction intervals are emitted;
- calibration for the event “volatility exceeds mandate ceiling.”

Secondary economic evaluation:

- whether warnings identify future high-risk periods earlier than trailing
  volatility alone;
- false-warning rate;
- performance by year, ticker, volatility regime, and earnings proximity.

Reject the ML candidate if it does not beat the simple EWMA baseline across
multiple untouched folds. A small aggregate win produced by one crisis window
is insufficient.

### 8.4 Output behavior

Display estimates as ranges and probabilities, not certainty. Example:

```json
{
  "task": "portfolio_volatility_forecast",
  "horizon_sessions": 20,
  "annualized_volatility_pct": 24.3,
  "prediction_interval_pct": [18.1, 33.7],
  "probability_above_mandate_ceiling": 0.72,
  "evidence_status": "exploratory",
  "production_authoritative": false
}
```

## 9. ML-5: earnings-gap risk

### 9.1 Scope

Estimate gap magnitude and downside-tail risk; do not predict whether earnings
will “beat” or whether a stock should be bought.

### 9.2 Event-time mapping

This mapping must be explicit and tested:

- after-market-close release: gap from release-day close to next session open;
- before-market-open release: gap from prior session close to release-day open;
- intraday or unknown release time: unavailable for the primary experiment
  unless separately preregistered.

Exchange calendars—not calendar-day arithmetic—must identify sessions.

### 9.3 Features

- prior absolute and signed earnings gaps;
- prior revenue/EPS surprise history where point-in-time values exist;
- pre-event realized volatility and downside volatility;
- market/industry volatility and trend;
- recent residual momentum;
- volume and liquidity;
- days since prior earnings;
- deterministic analyst-revision summaries if their timestamps are reliable.

Do not use post-release price, transcript text, revised consensus, or a later
filing in the pre-release feature row.

### 9.4 Models and metrics

Start with:

- historical median absolute gap by ticker/industry;
- logistic regression for thresholds such as absolute gap above 5% and
  downside gap below -5%;
- quantile regression or gradient boosting for magnitude intervals.

Use Brier score, log loss, calibration curves, precision/recall at a declared
review threshold, pinball loss for quantiles, and interval coverage. Evaluate
by event date, not by individual feature rows.

Refuse model fitting when event count or class support is inadequate. The
report must give the count of distinct earnings events, positive/negative
tail events, and tickers represented.

### 9.5 Intended integration

After successful shadow validation, this output may add context to the existing
earnings warning/blackout display. It must never block or delay a risk-reducing
sell and must not override the deterministic calendar rule.

## 10. ML-6: shadow prediction persistence and monitoring

### 10.1 Database tables

Add tables using the existing storage initialization pattern:

```text
ml_model_registrations
  model_key TEXT PRIMARY KEY
  registered_at TEXT NOT NULL
  manifest_json TEXT NOT NULL
  manifest_hash TEXT NOT NULL
  status TEXT NOT NULL

ml_predictions
  prediction_id TEXT PRIMARY KEY
  model_key TEXT NOT NULL
  task TEXT NOT NULL
  subject_key TEXT NOT NULL
  as_of_session TEXT NOT NULL
  generated_at TEXT NOT NULL
  horizon_sessions INTEGER NOT NULL
  feature_snapshot_hash TEXT NOT NULL
  prediction_json TEXT NOT NULL
  prediction_hash TEXT NOT NULL
  available INTEGER NOT NULL
  refusal_reasons_json TEXT NOT NULL

ml_prediction_outcomes
  prediction_id TEXT PRIMARY KEY
  matured_at TEXT NOT NULL
  outcome_json TEXT NOT NULL
  outcome_hash TEXT NOT NULL
```

Foreign-key or trigger-based integrity should match the repository's existing
SQLite compatibility approach. Prediction insertion must be idempotent. An
outcome cannot exist before its prediction or before its horizon matures.

### 10.2 Shadow behavior

- Generate predictions on a fixed, documented schedule.
- Record unavailable predictions and their reasons; do not log only successes.
- Never rewrite a prediction after its `as_of_session`.
- Attach outcomes only after the complete horizon is observable.
- Detect duplicate generation, model changes, clock errors, and lineage drift.
- Start a new evidence epoch whenever model, feature, label, policy-relevant
  configuration, or data-provider identity changes.

### 10.3 Monitoring

Report:

- prediction coverage and refusal rate;
- feature missingness and freshness;
- feature distribution drift;
- output distribution drift;
- realized error and calibration by rolling window;
- performance relative to frozen baselines;
- model/version lineage consistency;
- whether sample size is sufficient to draw any conclusion.

Monitoring must not retrain or promote a model automatically.

## 11. ML-7: benchmark-relative technology stock ranker

Do not begin this phase until ML-1 through ML-4 are stable.

### 11.1 Research question

Primary preregistered question:

> Among eligible technology holdings/watchlist stocks on each session, can a
> pooled model rank 20-session next-open-to-exit returns relative to QQQ or
> SOXX after transaction costs better than simple residual momentum?

Select QQQ or SOXX before the confirmation run. Testing both is two research
looks and must be counted in multiplicity correction.

### 11.2 Universe

Use a versioned universe definition. Current members cannot be projected
backward without acknowledging survivorship bias. For exploratory work, label
that limitation in the manifest. Production-authoritative research requires a
historically correct membership source or a deliberately fixed universe whose
claim is limited accordingly.

### 11.3 Models

Frozen comparison order:

1. equal score/no-skill baseline;
2. simple 12-1 or residual momentum baseline;
3. elastic-net regression or logistic rank model;
4. histogram gradient boosting;
5. ensemble only if preregistered and component predictions add independent
   validation value.

Do not train one model per ticker. Pool the cross-section and include only
features that can generalize across names.

### 11.4 Evaluation

Statistical metrics:

- date-level Spearman information coefficient;
- IC mean, dispersion, and sign consistency;
- top-minus-bottom quantile spread;
- probability calibration if a classifier is used;
- dependence-aware confidence intervals and block-bootstrap p-values;
- correction for every model, label, benchmark, horizon, and feature-family
  variant examined.

Portfolio metrics:

- shared-capital simulation;
- next-open execution;
- turnover, slippage, and taxes;
- max drawdown, expected shortfall, time under water;
- upside/downside capture;
- concentration and liquidity constraints;
- comparison with buy-and-hold and the simple momentum baseline.

Only confirmation-fold results count as evidence. Feature importance, SHAP,
or an attractive discovery chart does not constitute evidence.

### 11.5 Output

The ranker returns an observation such as:

```json
{
  "ticker": "NVDA",
  "as_of_session": "2026-07-31",
  "horizon_sessions": 20,
  "expected_excess_return_pct": 1.4,
  "probability_positive_excess": 0.61,
  "cross_sectional_percentile": 0.82,
  "uncertainty": "high",
  "model_key": "tech-ranker:0.1.0",
  "evidence_status": "exploratory",
  "production_authoritative": false
}
```

No proposal adapter belongs in ML-7.

## 12. ML-8: structured filing and transcript intelligence

This phase uses a language model as an extractor and organizer, not a source of
market facts.

### 12.1 Tasks

- extract management guidance into a typed schema;
- compare current guidance with the prior quarter;
- extract stated risks and changes in wording;
- identify duplicate or derivative news coverage;
- summarize bull, bear, and uncertainty cases from supplied sources;
- attach source URL/document ID, publication timestamp, and short supporting
  excerpts to every extracted claim.

### 12.2 Controls

- store source-document hashes and prompt/schema/model versions;
- validate every number against supplied source text;
- reject unsupported tickers, dates, amounts, and percentages;
- clearly separate direct extraction from model inference;
- prevent retrieved text from altering system instructions;
- never let prose create a `TradeIntent`;
- use the existing AI-run audit and committee validation patterns where
  applicable.

Sentiment alone is not a trade signal. Any proposed numeric NLP feature must
go through the same point-in-time dataset and out-of-sample research process as
every other feature.

## 13. ML-9: execution-quality modeling

Do not implement until the order lifecycle has accumulated an adequate and
representative sample. Paper fills may not reproduce live market impact, so a
paper-trained model cannot be presumed valid for live execution.

Potential targets:

- fill probability within a fixed interval;
- expected slippage versus decision and arrival price;
- partial-fill probability;
- time to fill;
- cancellation/replacement probability.

Possible features:

- spread and quote age;
- order size relative to recent volume;
- volatility and time of day;
- order type and limit distance;
- ticker liquidity bucket;
- broker/order lifecycle state.

The model may eventually recommend an execution tactic to a human. It may not
submit, cancel, or replace an order. Cancellation and replacement must remain
deterministic state-machine operations.

## 14. Evaluation and research-governance standard

Every experiment must produce an immutable evaluation report containing:

- research question and preregistered primary outcome;
- all candidate models and baselines;
- number of simultaneous research looks;
- dataset and feature hashes;
- actual coverage and underfill warnings;
- point-in-time and survivorship-bias status;
- split dates, embargo, and purged counts;
- entry/exit timing;
- cost, tax, liquidity, and capital assumptions;
- fold-level and aggregate metrics;
- dependence-aware uncertainty;
- failure analysis by date/regime/ticker;
- model calibration;
- mandate metrics where economically applicable;
- explicit limitations;
- one of: `rejected`, `exploratory`, `promising_unconfirmed`, or a request for
  a separate confirmation run.

Do not write smoke-test or scratchpad results into
`assistant/research_findings.json`. A registry entry requires a durable runner,
immutable report, reproducible manifest, accurate claim wording, and review.
Training code must never edit the registry automatically.

### 14.1 Minimum standard for a promising result

A result is not promising merely because one metric improved. At minimum it
must:

- beat its frozen simple baseline in more than one untouched walk-forward
  fold;
- survive the declared multiple-testing correction;
- remain directionally stable under reasonable block lengths;
- remain useful after costs and taxes where trading is involved;
- avoid materially worsening the mandate's drawdown/capture constraints;
- have adequate prediction coverage and no unresolved leakage finding;
- report calibration and uncertainty honestly;
- be reproduced from its immutable dataset and artifact hashes.

These are necessary, not automatically sufficient, conditions.

## 15. Testing strategy

### 15.1 Unit tests

Test contracts, time alignment, feature arithmetic, leakage guards, split
boundaries, missing/non-finite handling, model serialization, prediction
validation, and deterministic hashing.

### 15.2 Synthetic tests

Include datasets where the truth is known:

- pure noise must not produce persistent out-of-sample alpha;
- a planted factor must be recovered by PCA;
- a planted volatility relationship should beat a naive baseline;
- a future-only feature must look powerful if leakage is allowed and be
  rejected by the real builder;
- duplicate same-day cross-sectional rows must not be treated as independent
  time observations;
- a regime-specific effect must reveal instability rather than be summarized
  as universal.

### 15.3 Integration tests

- build a small immutable dataset from fixture data;
- train and evaluate a baseline model;
- save, hash, reload, and score it;
- persist a shadow prediction idempotently;
- attach an outcome only after maturity;
- generate a monitoring report;
- prove that no proposal, authorization, broker call, or execution state is
  created anywhere in that flow.

### 15.4 Regression and full-suite checks

For each PR:

```text
python -m pytest tests -q
python -m compileall -q assistant data execution risk scripts signals strategies backtest ml
git diff --check
```

Use the repository's configured Python runtime. If optional model dependencies
are absent, fail with a clear installation message rather than silently
changing behavior.

## 16. Observability and user presentation

Every displayed ML estimate should show:

- model/task name and version;
- `as_of` date and forecast horizon;
- evidence status and authority;
- estimate plus interval/probability;
- feature freshness and missing-data warnings;
- a baseline comparison;
- a concise “what this does not mean” statement.

Recommended label:

```text
Experimental model observation — not a recommendation and not used by the
execution gate.
```

Never display a raw model probability as “confidence” unless calibration has
been measured and the exact meaning is stated.

## 17. Explicitly deferred or prohibited work

Do not implement in the initial roadmap:

- reinforcement learning;
- end-to-end news-to-order automation;
- direct LLM trade selection or position sizing;
- neural networks for the current tabular sample size;
- online self-training or automatic hyperparameter searches in production;
- per-ticker models with tiny samples;
- automatic model promotion;
- automatic research-registry edits;
- options, futures, shorting, or margin models outside the current mandate;
- confidence-scaled position sizing copied from the deleted legacy module;
- live-order optimization trained only on paper fills.

## 18. Definition of done by milestone

### Foundation complete

- immutable manifests and artifact verification exist;
- point-in-time feature contracts and grouped purged splits are tested;
- research/production import boundaries are pinned;
- a pure-noise end-to-end test produces no false claim of skill.

### Risk forecaster research-complete

- PCA/shrinkage concentration report works on fixture and real exploratory
  data;
- volatility model is compared against trailing and EWMA baselines;
- all reports carry lineage, uncertainty, limitations, and authority=false;
- no production proposal or execution behavior changes.

### Shadow-ready

- predictions and unavailable attempts are append-only and idempotent;
- outcomes mature without rewriting predictions;
- drift, calibration, coverage, and baseline comparisons are reportable;
- model/version lineage changes start a new evidence epoch;
- operational failures are visible but cannot obstruct deterministic risk
  reduction.

### Eligible for a future promotion review

- point-in-time and survivorship-safe data are available;
- the model passes preregistered, purged walk-forward confirmation;
- dependence and multiplicity are handled;
- economic results survive costs, taxes, and shared-capital simulation;
- paper shadow evidence is sufficiently long and lineage-consistent;
- the owner approves a narrowly scoped deterministic adapter;
- that adapter receives a separate adversarial review before it can influence
  proposal generation.

## 19. Instructions to the implementation agent

1. Begin with ML-1 only. Do not opportunistically wire model output into the
   assistant, proposal generator, or execution path.
2. Inspect current repository state and preserve unrelated or untracked user
   files.
3. Reuse existing money, timestamp, hashing, research-report, and storage
   conventions instead of creating subtly different equivalents.
4. Prefer simple baselines and small explicit APIs over framework-heavy
   abstractions.
5. Treat all real-data results produced before point-in-time data is available
   as exploratory and promotion-blocked.
6. Do not claim a model works based on tests; tests verify software behavior,
   not market edge.
7. Stop after each PR-sized milestone, report exactly what changed, run the
   focused and full tests, and request review before beginning the next phase.
8. Document anything intentionally skipped, including the reason and the
   evidence required to revisit it.
