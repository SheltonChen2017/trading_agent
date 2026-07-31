# ML Implementation Status

Companion to `docs/ML_IMPLEMENTATION_STRATEGY.md`, recording what is built,
what is deliberately not built, and why. Updated 2026-07-31.

## Built

| PR | Scope | Modules | Production behavior change |
|---|---|---|---|
| ML-1 | Contracts, manifests, hashing, artifact integrity, boundary tests | `ml/contracts.py`, `ml/hashing.py`, `ml/artifacts.py` | None |
| ML-2 | Point-in-time features/labels, purged walk-forward splits, immutable datasets, leakage-safe transforms | `ml/features.py`, `ml/labels.py`, `ml/splits.py`, `ml/datasets.py`, `ml/transforms.py` | None |
| ML-3 | Latent-factor concentration model and report | `ml/factor_risk.py` | None (read-only report) |
| ML-4 | Volatility forecasting, frozen baselines, evaluation metrics | `ml/volatility.py`, `ml/baselines.py`, `ml/evaluation.py` | None (read-only report) |
| ML-5 | Earnings-gap risk, exchange-calendar event mapping | `ml/earnings_gap.py` | None (read-only report) |
| ML-6 | Shadow prediction persistence and monitoring | `ml/monitoring.py`, three `ml_*` tables + `portfolio_position_snapshots` in `assistant/storage.py` | Writes observations only |
| ML-7 | Benchmark-relative ranker research | `ml/cross_sectional.py` | None |
| ML-8 | Structured filing/transcript extraction contract + validator | `ml/filings.py` | None (context only) |

Every model output carries `production_authoritative=False`, and no module
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

## Known gaps within what IS built

These are honest limitations, not oversights:

1. **`point_in_time_data` is structurally `False`.** `ml/datasets.py`'s
   builder *refuses* to claim `True` because no per-feature
   `event_at`/`available_at`/`observed_at` lineage sidecar exists yet. The
   underlying yfinance source is retroactively adjusted, so every result
   produced today is exploratory and promotion-blocked by construction. This
   is doc 3.4's promotion blocker, working as intended.

2. **Universe survivorship bias is unresolved.** Datasets record a
   `universe_definition` string, but a fixed current-membership universe
   projected backward still excludes names that failed during the window.
   Doc 11.2 permits this for exploratory work *if labeled*; it blocks
   production-authoritative research.

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
