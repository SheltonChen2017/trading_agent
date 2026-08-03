# ML Full-System Execution Plan

Status: active execution plan layered on top of
`docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`

Prepared: 2026-08-01

## 1. Objective

Finish the application's ML system so it can:

1. collect trustworthy historical, paper, shadow, and eventually live
   observations without later schema redesign;
2. reproduce discovery and untouched confirmation experiments;
3. operate supervised models prospectively with durable refusals and outcomes;
4. explain model evidence to the owner without creating trading authority; and
5. after a separate evidence and owner review, help trading through a narrowly
   bounded deterministic adapter and limited-capital canary.

This plan does not weaken the ML-LR safety boundary. Code completion, research
support, shadow evidence, owner authorization, and live influence remain
separate outcomes. Until the promotion milestones are explicitly authorized,
ML output may not create, approve, size, submit, cancel, or replace an order and
may not delay a risk-reducing sale.

## 2. Relationship to ML-LR

The ML-LR plan remains the source of truth for experiment integrity, promotion
gates, and model isolation. This plan fills the operational path around it:

- normalized paper/live collection;
- execution telemetry retained before an execution model is permitted;
- authoritative historical and online data providers;
- completion of the volatility-first model path;
- prospective prediction contracts and automated evidence collection;
- explicit deployment, supervision, and recovery acceptance tests; and
- reviewed transition from observation to bounded trading assistance.

Current baseline:

- ML-FS-0 through ML-FS-5 and ML-FS-7 infrastructure is software-complete;
  ML-FS-6 exists only as preparation (dataset admission, attestation
  contracts, reviewed-run wrapper, confirmation-request tooling) — no real
  discovery or confirmation has run and no `SpecReviewAttestation` exists;
  ML-FS-3's real-data
  definition of done remains pending a reviewed licensed historical-universe
  snapshot and an actual authoritative build;
- ML-LR-0, ML-LR-1, ML-LR-2, ML-LR-4, ML-LR-6, ML-LR-7, and
  ML-LR-8 are software-complete within their documented limits;
- ML-LR-3 is software-complete for separate per-security and portfolio
  volatility research paths; real portfolio research remains unavailable
  until enough complete daily account history accumulates;
- ML-LR-5 was deliberately skipped and is optional for the volatility-first
  path;
- real `point_in_time_data=True` remains blocked on authoritative adjustment
  vintages and historical universe membership;
- the scheduled paper observation now writes normalized portfolio history and
  a complete-capture manifest, while claimed execution attempts retain
  pre-broker telemetry joined to the authoritative broker event journal; and
- volatility shadow operation now emits a complete immutable prospective
  contract, and an independent supervisor detects missed or incomplete
  evidence; task installation and elapsed shadow conclusions do not yet exist.

## 3. Delivery rules

Implement one milestone per branch and review. At each milestone:

1. preserve the execution/import boundary;
2. make retries idempotent and conflicting identities loud;
3. persist unavailability and partial failure rather than silently dropping it;
4. keep paper and live identities explicitly separate;
5. test cash-only, missing-data, corruption, retry, and epoch-change cases;
6. run focused tests, the full suite, compilation, and `git diff --check`;
7. update `docs/ML_IMPLEMENTATION_STATUS.md` and the operations runbook; and
8. state which remaining gates require elapsed evidence or owner authority.

No milestone may automatically edit `assistant/research_findings.json`, promote
a model, change proposal state, or write execution authority.

## 4. Milestone sequence

```text
ML-FS-0 plan/baseline
  -> ML-FS-1 normalized portfolio collection
  -> ML-FS-2 execution telemetry collection
  -> ML-FS-3 authoritative historical + online data
  -> ML-FS-4 volatility and portfolio research completion
  -> ML-FS-5 prospective inference contract
  -> ML-FS-6 real discovery + untouched confirmation
  -> ML-FS-7 supervised evidence operations
  -> ML-FS-8 promotion review and context-only integration
  -> ML-FS-9 bounded assistance and limited-capital canary

Optional parallel track after ML-FS-3:
  ML-LR-5 ranker economics -> ranker shadow adapter
```

ML-FS-8 and ML-FS-9 require explicit later owner authorization. ML-LR-11
execution-quality model fitting remains prohibited until representative live
order data exist; ML-FS-2 only records deterministic telemetry.

## 5. ML-FS-0 — plan and baseline

### Implementation

- Record this overlay plan and the audited baseline above.
- Reconcile stale or contradictory statements in
  `docs/ML_IMPLEMENTATION_STATUS.md` as milestones land.
- Keep the existing ML import-boundary test green.

### Definition of done

The repository has one ordered path from the existing ML-LR foundation to
data collection, evidence, reviewed assistance, and canary operation without
describing fixture tests as market evidence.

## 6. ML-FS-1 — normalized portfolio collection

Status: implemented 2026-08-01.

### Purpose

Make the existing scheduled post-close paper observation directly usable by
portfolio-volatility research. Storage tables alone are insufficient when no
production path writes them.

### Implementation

- Treat the immutable `paper_account_observations` payload as the source of
  truth for normalization, including on retries.
- For every accepted paper observation, persist one normalized equity snapshot
  and one normalized position snapshot per holding.
- Use an account key containing provider, paper/live mode, and broker account
  ID so accounts cannot be pooled accidentally.
- Write a final immutable capture manifest that binds the paper observation,
  equity snapshot, position snapshot hashes, evidence epoch, lineage hash,
  session, capture time, source, and position count.
- A zero-position manifest means a genuine cash-only portfolio; absence of a
  manifest means collection is incomplete.
- Exact retries repair missing normalized children and return the same capture;
  conflicting content is refused.
- Do not change `DecisionPacket` and do not create proposal or execution state.

### Tests

- a reconciled post-close paper observation writes all normalized records;
- a cash-only session writes a complete zero-position manifest;
- retry after the paper observation exists derives children from the stored
  immutable payload, not a changed caller snapshot;
- different paper accounts cannot share an account key or capture identity;
- future/pre-close/live-account input remains refused; and
- normalized records contain no action-shaped or authority fields.

### Definition of done

Running the existing scheduled `paper-observation` command once after each
session accumulates the exact equity and holdings history consumed by the
portfolio target builder, with complete-capture evidence and no manual database
edits.

## 7. ML-FS-2 — execution telemetry collection

Status: implemented 2026-08-01. No execution model was fit or enabled.

### Purpose

Retain analysis-ready order-lifecycle evidence now without fitting or deploying
an execution model.

### Implementation

Add an immutable execution observation identity spanning:

- decision, quote, arrival, submit, acknowledgement, fill, cancel, and
  replacement timestamps;
- bid, ask, spread, quote age, requested and filled quantities;
- order type, limit distance, partial fills, replacement chain;
- decision, arrival, and fill prices;
- recent volume and liquidity bucket; and
- broker account ID plus explicit paper/live source.

The event journal remains authoritative. Materialized telemetry must be
rebuildable from its source events and must never pool paper and live records by
default.

The implemented boundary treats a successfully claimed proposal as the start
of an order attempt. It appends validation/quote evidence and, only when the
attempt reaches it, a `submission_started` event before contacting the broker.
Acknowledgement, partial/final fills, cancellation, and replacement chains are
derived from `broker_order_events`; they are not duplicated into a competing
lifecycle store. Current quote data has no recent volume or depth, so those
fields are explicitly unavailable rather than estimated. If the mandatory
pre-submit append fails, the execution service releases its reservation and
refuses the broker call.

### Definition of done

Every assistant-originated order attempt produces a complete or explicitly
unavailable telemetry record suitable for a future dataset. No execution model
is fit.

## 8. ML-FS-3 — authoritative historical and online data

Status: software implemented 2026-08-01. Real-data completion remains blocked
until a reviewed historical-universe source and licensed captures are supplied.

### Implementation

- Reconstruct vintage-correct Databento adjustment factors.
- Resolve historical listing, symbol, option, and rescission state.
- add authoritative historical universe membership;
- emit feature-availability records only when the vendor evidence supports
  them;
- create a Databento-backed online provider with the same decision-cutoff rules
  used during research; and
- prove prefix invariance and revision retention.

### Definition of done

At least one real historical dataset derives `point_in_time_data=True`, and the
online provider can reproduce the same feature semantics without using future
information. If authoritative membership remains unavailable, promotion stays
blocked and the limitation is explicit.

## 9. ML-FS-4 — finish volatility and portfolio research software

Status: software implemented 2026-08-01. Real portfolio evidence remains
underfilled until sufficient complete daily account history accumulates.

### Implementation

- Define the frozen portfolio feature/baseline dataset contract.
- Add the portfolio task to the shared experiment runner.
- Produce immutable portfolio evaluation reports and typed forecasts.
- Keep portfolio and per-security evidence separate.
- Preserve underfilled sessions and cash exposure.

### Definition of done

Both per-security and portfolio volatility paths run end to end on fixtures and
eligible historical data. Insufficient real position history returns
unavailable rather than guessed holdings.

## 10. ML-FS-5 — prospective inference contract

Status: software implemented 2026-08-01. This records prospective evidence;
it does not establish calibration quality or authorize trading use.

### Implementation

Every scheduled prediction must prospectively retain:

- point estimate and interval;
- experimental or calibrated threshold probability;
- calibration state and frozen baselines;
- feature values, age, missingness, and reference-distribution identity;
- regime/event categories;
- target-availability timestamp; and
- provider, dataset, artifact, report, configuration, and evidence-epoch
  lineage.

Unavailable fields remain unavailable; they are never reconstructed from
realized outcomes.

### Definition of done

The shadow runtime produces the complete monitored contract and survives
provider failure, artifact corruption, restart, and epoch change on fixtures.

## 11. ML-FS-6 — real discovery and untouched confirmation

Status: preparation software implemented 2026-08-01. The repository contains
a review-ready discovery spec, not an approval or a real experiment result.
Real discovery and confirmation remain blocked on reviewed authoritative data,
explicit spec attestations, and execution of the elapsed-data workflow.

### Implementation

- Add reviewed specs under `research/ml_specs/`.
- Materialize content-addressed authoritative datasets.
- Run discovery without registry or execution side effects.
- Freeze the selected behavior and run a distinct untouched confirmation.
- Reject failed confirmation without retuning the same confirmation identity.

### Definition of done

A verified artifact is eligible to enter shadow evidence collection only if its
preregistered software, statistical, and task-specific gates pass. Passing does
not grant trading authority.

## 12. ML-FS-7 — supervised evidence operations

Status: supervision infrastructure implemented 2026-08-01. The independent
health rules, durable alerts, limited-principal task installers, and read-only
host verifier are built and fixture-tested. Actual task registration,
credential/permission validation, manual first runs, alert-delivery receipts,
restore evidence, and elapsed sessions must be completed on the operating host.

### Implementation

- Install and verify operational and ML scheduled tasks under a least-privilege
  account.
- Verify credentials, database access, heartbeats, alerts, backups, and restore.
- Run predict/mature/monitor continuously with one lineage per epoch.
- Alert on missed paper observations and incomplete capture manifests.
- Retain every scheduled refusal, outcome underfill, and operational incident.

The implementation checks exchange-calendar session coverage, distinguishes a
cash-only complete capture from a missing manifest, treats stuck/failed ML runs
and matured predictions without outcomes as underfill, and fails closed on
missing or unhealthy heartbeats. It verifies credential *presence* without
emitting values and never creates missing evidence.

### Definition of done

The system collects complete paper, portfolio, execution, prediction, outcome,
and monitoring evidence without manual database edits. Statistical sufficiency
still requires elapsed sessions and cannot be completed by fixture generation.

## 13. ML-FS-8 — promotion review and context-only integration

Requires an explicit owner request after a real promotion dossier exists.

- Verify every dossier hash and blocker.
- Add audited registry transitions ending initially at
  `approved_context_only`.
- Bind approval to owner, scope, consumer, fields, expiration, and artifact.
- Keep adapter failure equivalent to no ML output.
- Complete a separate adversarial review.

### Definition of done

The owner can inspect approved ML context in the trading workflow. ML still
cannot create or increase a trade.

## 14. ML-FS-9 — bounded trading assistance and canary

Requires a second explicit owner request and a clean context-only operating
period.

- Add a feature-flagged deterministic new-risk constraint.
- It may only reduce or refuse new/increasing exposure in declared scope.
- It may never increase size, create a symbol or direction, delay a
  risk-reducing sale, or bypass the execution gate.
- Compare enabled/disabled decisions in shadow before a tiny canary.
- Add an ML-specific disable switch and preregistered rollback triggers.

### Definition of done

After an owner-approved limited-capital canary, the system may help trading only
inside the exact audited scope. Scaling requires a separate review.

## 15. Optional model tracks

ML-LR-5 ranker economics is optional for the volatility-first path. If enabled,
it requires authoritative membership, shared-capital simulation, costs, taxes,
liquidity and mandate constraints, confirmation, a task-specific online
adapter, and its own shadow epoch.

Earnings shadow operation likewise requires reviewed online feature and outcome
semantics. Neither task should be forced through the volatility adapter.

Execution-quality modeling remains deferred until a representative live-order
sample exists and the owner explicitly authorizes that research.
