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

ML-LR-0 delivers **contracts only** — no runner, no CLI, no experiment has
been executed through them. `ExperimentSpec` can fully describe the existing
synthetic volatility and ranker experiments (the milestone's definition of
done), and the research gate and confirmation parent are bound into
`spec_hash`, so moving a preregistered threshold produces a different
experiment identity rather than silently mutating one. The runner that would
consume these specs is ML-LR-2.

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
