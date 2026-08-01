# ML Implementation Status

Companion to `docs/ML_IMPLEMENTATION_STRATEGY.md`, recording what is built,
what is deliberately not built, and why. Updated 2026-07-31.

The next implementation sequence is defined in
`docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`.

## Built

| PR | Scope | Modules | Production behavior change |
|---|---|---|---|
| ML-1 | Contracts, manifests, hashing, artifact integrity, boundary tests | `ml/contracts.py`, `ml/hashing.py`, `ml/artifacts.py` | None |
| ML-2 | Point-in-time features/labels, purged walk-forward splits, immutable datasets, leakage-safe transforms | `ml/features.py`, `ml/labels.py`, `ml/splits.py`, `ml/datasets.py`, `ml/transforms.py` | None |
| ML-3 | Latent-factor concentration calculator and typed report | `ml/factor_risk.py` | None (read-only report) |
| ML-4 | Per-security volatility model/baseline/evaluation primitives | `ml/volatility.py`, `ml/baselines.py`, `ml/evaluation.py` | None (read-only research) |
| ML-5 | Earnings-gap mapping, support checks, and model-fit primitives | `ml/earnings_gap.py` | None (read-only research) |
| ML-6 | Shadow persistence plus coverage, freshness, drift, error, and lineage reports | `ml/monitoring.py`, three `ml_*` tables + `portfolio_position_snapshots` in `assistant/storage.py` | Writes observations only when called |
| ML-7 | Cross-sectional ranker model/statistical-evaluation primitives | `ml/cross_sectional.py` | None |
| ML-8 | Filing/transcript extraction contract + deterministic validator | `ml/filings.py` | None (context only) |
| ML-LR-0 | Shared experiment identity, preregistered research gates, run records | `ml/experiment_contracts.py` | None |
| ML-LR-1 | Point-in-time lineage contracts, universe membership, dataset sidecars | `ml/availability.py`, `ml/datasets.py` | None |
| ML-LR-2 | Durable discovery/confirmation runner and CLI | `ml/experiments.py`, `scripts/run_ml_experiment.py` | None |

ML-LR-2 gives both supported tasks a reproducible runner. Verified against
the milestone's own definition of done by invoking the real CLI twice: the
same spec/dataset/commit reproduces identical report, run, and artifact
hashes. Outputs are content-addressed, so an exact retry is a no-op and a
rerun that would change results is refused rather than silently
overwriting.

Every behavior-changing runner input is now frozen into `spec_hash`: ordered
features, target column, and named baseline columns cannot be changed at the
CLI. Confirmation resolves and hash-verifies the parent discovery spec,
report, and run, requires that the parent actually requested confirmation,
and rejects changes to the discovery behavior. Model bundles include the
training-fold standardizer, carry a `ModelManifest`, and are reloaded through
the hash-verifying artifact loader immediately after writing.

The verdict is derived from the preregistered gate, never from inspection:
fold wins alone are treated as necessary-but-insufficient, and a candidate
must also clear the preregistered alpha (tightened by the Bonferroni
correction) at **every** declared block length. A discovery run can never
return `promising_unconfirmed` — the most it can say is
`confirmation_run_requested`, which requires a separate experiment with a
new immutable ID.

Not yet built here: task-specific detail reports beyond fold metrics and
aggregate significance (calibration is emitted empty), and the
`research/ml_specs/` spec library the plan's CLI examples reference. No
experiment has been run against real data, and no research-registry entry
exists.

ML-LR-1 makes `point_in_time_data=True` **derivable but still unreachable
from real data**. `evaluate_point_in_time_coverage()` is now the only code
path that can return True, and `build_dataset_manifest()` refuses a
caller-asserted claim outright. A fixture dataset with explicit lineage does
prove point-in-time (the milestone's definition of done); the real yfinance
path returns `False` with the failures `missing_feature_lineage` and
`no_universe_membership_records`, because `RetroactivelyAdjustedSource`
deliberately returns **no** records rather than synthesizing availability
from download time. Availability, universe, and typed coverage evidence now
participate in `dataset_hash`; their row counts are recorded, and the claim is
replayed during build, save, and load. Swapping lineage, decision cutoffs, or
feature-value bindings therefore changes identity or is refused.

Still external, and still the blocker: an authoritative vendor providing
real historical availability timestamps and index-constituent history. Until
one is configured, every dataset built from live data remains exploratory
and promotion-blocked — which is the honest state, not a gap in the code.

ML-LR-0 supplied the shared contracts now consumed by ML-LR-2. `ExperimentSpec`
fully describes the synthetic volatility and ranker experiments, and the
research gate, invocation columns, and confirmation parent are bound into
`spec_hash`, so moving a threshold or changing a feature produces a different
experiment identity rather than silently mutating one.

Every typed prediction, risk, evaluation, extraction, and monitoring output
carries `production_authoritative=False`, and no module
under `execution/`, `risk/execution_gate.py`, `assistant/execution_service.py`,
or `assistant/allocation_batch.py` imports `ml` — pinned by
`tests/test_ml_import_boundary.py`, which also currently pins **zero** `ml`
imports anywhere under `assistant/`.

`tests/test_ml_integration.py` runs the doc-15.3 end-to-end flow and asserts
that `trade_proposals`, `broker_orders`, `broker_order_events`,
`execution_reservations`, and `allocation_batches` are all still empty
afterwards.

## Deliberately NOT built

### ML-9 — execution-quality modeling

The strategy doc gates this on data this project does not have:

> Do not implement until the order lifecycle has accumulated an adequate and
> representative sample. Paper fills may not reproduce live market impact, so
> a paper-trained model cannot be presumed valid for live execution.

Building it now would produce a model trained entirely on paper fills, whose
slippage and fill-probability estimates would be an artifact of the simulator
rather than the market. **Evidence required to revisit:** a materially sized
sample of *live* order-lifecycle records, plus an explicit decision about
whether paper and live fills may ever be pooled (they probably may not).

### ML-10 — proposal integration

Prohibited by the doc in two places — the PR table ("Separate promotion
review required") and the instructions to the implementation agent:

> Begin with ML-1 only. Do not opportunistically wire model output into the
> assistant, proposal generator, or execution path.

Nothing here may influence a proposal until a model has cleared doc 14.1's
promotion bar. **Evidence required to revisit:** point-in-time and
survivorship-safe data; a preregistered, purged walk-forward confirmation;
dependence and multiplicity handled; economics surviving costs, taxes, and
shared-capital simulation; sufficient paper shadow evidence; owner approval
of a narrowly scoped deterministic adapter; and a separate adversarial review
of that adapter.

## Known gaps and incomplete milestone work

The table above records implemented building blocks, not a claim that every
acceptance criterion in sections 7-12 is complete. In particular:

1. **Real-data `point_in_time_data` remains `False`.** The builder can now
   prove fixture data from persisted per-feature lineage, value hashes,
   decision cutoffs, and historical membership. The configured yfinance
   source supplies none of that authoritative history, so real results remain
   exploratory and promotion-blocked. An authoritative vendor adapter and
   licensed history are still external dependencies.

2. **Real historical universe data is unavailable.** The typed membership
   contract and cutoff-aware validation now reject fixed current-membership
   projections, but no configured source supplies authoritative constituent
   history. Doc 11.2 permits current-member universes for exploratory work
   *if labeled*; they still block production-authoritative research.

3. **No model has been fit on real data and evaluated for edge.** Every test
   here verifies *software behavior* on synthetic or fixture data. Doc 19.6:
   "Do not claim a model works based on tests; tests verify software
   behavior, not market edge." No entry has been written to
   `assistant/research_findings.json`, and none should be until a durable
   runner produces an immutable report.

4. **`ml/filings.py` ships the contract and validator, not a provider.** The
   LLM call itself is intentionally absent so the deterministic acceptance
   rules can be tested with zero network access; wiring a provider is a
   separate change that should reuse `assistant/llm/`'s existing
   provider/audit pattern.

5. **Parquet is not used.** CSV-gzip was chosen because doc 6.1 requires
   pinning a Parquet engine explicitly before depending on one, and none is
   pinned in `requirements.txt`. Revisit if dataset size demands it.

6. **ML-4 is not yet portfolio-forecast complete.** Position snapshots can
   now accumulate the required history, but there is no historical
   portfolio-weight target builder, portfolio forecast runner, interval and
   threshold-calibration fold report, or economic warning analysis by
   year/regime/earnings proximity. The current evaluator covers per-row QLIKE
   and MAE against trailing/EWMA baselines on a common validation sample.

7. **ML-5 is not yet research-complete.** Event-time mapping, realized gaps,
   support checks, and simple fit functions exist. A point-in-time pre-event
   feature builder, grouped walk-forward event evaluator, precision/recall and
   interval report, typed forecast output, and durable runner do not.

8. **ML-6 is not yet operationally shadow-ready.** Persistence now enforces
   registered lineage, immutable conflicts, feature freshness, timezone-aware
   generation, and explicit target maturity. There is no fixed scheduler,
   automatic outcome-maturation job, baseline/calibration monitor, or
   dedicated ML evidence-epoch coordinator yet. Calling these APIs remains an
   explicit research workflow.

9. **ML-7 is statistical-research scaffolding, not the complete ranker
   experiment.** The historically correct universe, immutable benchmark-
   relative dataset runner, confirmation workflow, and shared-capital
   simulation with turnover, slippage, taxes, drawdown, expected shortfall,
   capture, concentration, and liquidity constraints remain unbuilt.

10. **No user-facing ML presentation is wired.** The implementation remains
    deliberately isolated from `assistant/` and execution. Consequently the
    observability presentation in section 16 is also pending; this is safer
    than presenting unevaluated outputs, but it means these modules do not yet
    help a live decision workflow directly.

## ML-LR-3 (in progress)

`ml/portfolio_volatility.py` delivers the section 9.2 target builder and the
9.3 unit convention. Two explicitly distinct targets that are never
substituted for one another: `frozen_weight` (weights known at
`as_of_session`, applied to the next `horizon_sessions` of aligned security
returns) and `realized_account` (flow-adjusted account-equity returns). Each
carries its own `target_kind`, so mixing them downstream is impossible
rather than merely discouraged.

Cash is retained as zero-volatility exposure rather than renormalized away —
verified linear: a 75/50/25%-invested book measures 0.750/0.500/0.250x the
fully-invested volatility, where a renormalizing implementation would report
the fully-invested number for all of them. Every target records its position
snapshot hash and price input hash, refuses a snapshot captured after the
forecast cutoff, and refuses rather than dropping a held security that lacks
prices — dropping one would silently re-weight the survivors and report the
volatility of a book that was never held.

Units are daily-return standard deviation in percent, matching
`compute_forward_realized_vol_labels`. The only annualized value sits behind
a field whose name says `annualized`, and there is no unlabeled
`volatility_pct` key that could be mistaken for either.

`ml/volatility_evaluation.py` completes sections 9.4 and 9.5.

`expanding_out_of_fold_intervals()` is the leakage-critical piece: fold k's
interval is built from residuals observed in folds < k only. Fold 0 gets no
interval at all rather than borrowing later data. Verified decisively --
corrupting a fold's actuals 8x leaves its own interval bounds byte-identical
while its coverage collapses 0.85 -> 0.00, which is only possible if the
fold never informed its own interval. Residuals are on the log scale so
bounds are structurally positive and the upper tail is not understated.

Also delivered: aggregate interval coverage; Brier/log-loss/calibration for
a preregistered mandate ceiling; warning lead time and false-warning rate
versus trailing volatility; and QLIKE/MAE sliced by
year/ticker/volatility-regime/earnings-proximity. The slice report is what
makes doc 8.3's "small aggregate win produced by one crisis window" visible
-- measured: a crisis-only model wins 1 of 4 year buckets (0.25) against 4
of 4 (1.00) for a genuinely better one.

`ShadowVolatilityForecast` carries every plan-9.5 field. A probability is
serialized under the key `experimental_probability` unless calibration has
cleared a preregistered Brier bar, in which case it becomes
`calibrated_probability`; the word "confidence" never appears. Calibration
has three states, not two -- "not measured" and "measured and failed" are
different situations, and collapsing them would let an unmeasured
probability inherit the benefit of the doubt.

All four report families are now wired into `ml/experiments.py`'s volatility
runner and land in the immutable evaluation report: per-fold intervals,
aggregate coverage, ceiling calibration, warning behavior, and performance
slices. Threshold probabilities are derived from the same expanding
out-of-fold residual history the intervals use, so a probability for fold k
is informed only by folds < k.

`ResearchGateSpec` gained `mandate_ceiling_daily_pct` and `maximum_brier`
(both optional, so existing specs stay valid). They are part of `spec_hash`,
which is what makes the ceiling genuinely *preregistered* — moving it
produces a different experiment rather than silently re-grading the same
one. Without a declared ceiling the runner reports `not_measured` rather
than inventing a threshold from the observed distribution, which would be
choosing the bar after seeing the results. `maximum_brier` without a ceiling
is refused outright as a gate that could never be evaluated.

`ml/portfolio_experiments.py` completes section 9.7's portfolio half. It
builds a target per account-session from stored position/equity records,
keeps every refusal with its reason rather than dropping it, and reports
research readiness instead of running on an inadequate sample.

Underfill is a first-class outcome. Measured on a 120-session fixture with a
20-session horizon: 100 targets, 20 refusals (exactly the tail with no
forward window). A 30-session account reports `underfilled` with actionable
blockers — *"only 10 portfolio targets; 60 required"* and *"only 10 targets;
63 needed for 2 purged folds with a 20-session embargo"* — because target
count alone understates what purging costs.

The two target kinds cannot be pooled into one frame; `targets_to_frame()`
refuses, since they measure different quantities. The observation unit is an
account-session, so `ticker` carries the account key — naming it honestly
keeps cross-sectional rank metrics from being applied to a panel with one
name per date, where a rank correlation is undefined.

The portfolio target-preparation half of ML-LR-3 is complete. The module does
not yet satisfy section 9.7's full definition of done: it does not fit a
portfolio model or emit an immutable experiment report and typed forecast.
Those outputs require a frozen portfolio feature/baseline dataset contract
and integration with the shared experiment runner. Portfolio research against
real data also stays underfilled until enough daily position/equity snapshots
accumulate; per plan 9.7 that is reported as unavailable rather than
backfilled. ML-LR-3 therefore remains **in progress** rather than being marked
complete based on target preparation alone.
