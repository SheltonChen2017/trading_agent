# Overlay Shadow Observation — Design (REVISED DRAFT for owner review)

Status: REVISED DRAFT 2026-08-18 (supersedes the same-day first draft).
Nothing here is implemented beyond SHW-1; this document exists to be
reviewed, corrected, and adopted into the action plan.

## 0. Why this draft was revised (the discovery)

The first draft proposed a strategy-agnostic "shadow stream" framework.
Pre-implementation reconnaissance found that the project ALREADY has a
complete, reviewed shadow infrastructure for its first observed task —
ML-LR-6: `ml/shadow_runtime.py` (computation), `scripts/run_ml_shadow.py`
(register / predict / mature / monitor persistence adapter), the `ml_*`
tables in `assistant/storage.py` (registrations, evidence epochs, runs,
predictions with refusal reasons, matured outcomes), Windows scheduler
installers, and monitoring. That milestone also RECORDED the design
principle a generic framework violates: an untested generic adapter
"would only hide task-specific label and feature semantics behind a
common-looking interface" (`ml/shadow_runtime.py` docstring; CLAUDE.md
section 4 states the same rule).

**Revision: there is no generic shadow framework.** Each observed task
gets its own task-specific runtime that FOLLOWS THE ML-LR-6 PATTERN —
same lifecycle (register → observe → mature → monitor), same storage
conventions (canonical JSON + SHA-256, aware timestamps, idempotent
same-content retries, loud refusal of conflicting content, append-only
with declared unavailability), same epoch discipline (any lineage
change closes the epoch), and same hard boundaries (observation only,
no promotion authority). What is shared is reused from the existing
helpers; what is task-specific stays visible in task-specific code.

## 1. The first (and only planned) new stream: the defensive-carry overlay

Task: observe, prospectively and without any order authority, the
hypothetical performance of the fixed-weight defensive-carry overlay
(equal-weight TLT/IEF/SHY/GLD at the preregistered primary weight)
blended with the equal-weight UNIVERSE, against the UNIVERSE-only
blend — the prospective leg of
`docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md`.

Task-specific semantics that would be hidden by a generic adapter and
are therefore explicit in this design:

- the observation unit is a CALENDAR MONTH settled on exchange
  sessions; a cycle computes month-end index levels for three series
  (universe blend, carry basket, combined overlay) from decision-cutoff
  data;
- rebalancing semantics follow the OPERATIONAL wide-band mechanism
  (25% band) so the observed object matches what deployment would do;
- outcomes are the matured monthly return of each series plus the
  derived tail metrics ONLY at sufficiency time (no rolling peeks);
- unavailability is per-ticker and per-cycle: a missing or stale close
  for any constituent produces a refusal row for the cycle with the
  named tickers, never a partially-imputed observation.

## 2. Components (mirroring ML-LR-6's layout, not importing it)

- `assistant/overlay_shadow.py` — frozen contracts + pure computation
  for THIS task: registration record (stream name, evidence epoch,
  preregistration doc path and SHA-256, code commit, schedule
  key/version, universe members, carry basket, weight, band fraction),
  observation record (cycle session, tz-aware generation time, input
  identity, index levels, availability + refusal reasons), outcome
  record. No `ml` imports, no execution imports; the import-boundary
  tests extend to prove both directions.
- `assistant/storage.py` — three new tables following the `ml_*`
  precedent: `overlay_stream_registrations` (UNIQUE stream+epoch),
  `overlay_observations` (UNIQUE stream+epoch+cycle; refusal rows
  occupy the cycle slot; conflicting content for the same identity is
  rejected loudly), `overlay_outcomes` (keyed to observations; declared
  unavailability recorded). Backward-compatible idempotent migration,
  tested fresh and pre-migration.
- `scripts/run_overlay_shadow.py` (SHW-2) — the persistence adapter:
  register / observe / mature / status subcommands, durable operational
  alerts on failure, serial and idempotent, safe to rerun; a missed
  cycle records a gap.
- Monitoring/status (SHW-3) — the section-6 sufficiency fields
  (observation unit, independent count, preregistered required count,
  sufficiency verdict, insufficiency reasons); gate evaluation happens
  once, only at the preregistered count.

## 3. Hard boundaries (inherited verbatim)

Observation only — nothing here may create, approve, size, submit,
cancel, or replace an order, or write proposal/risk/execution tables;
registration status vocabulary deliberately cannot express authority
(mirroring `register_ml_model`'s shadow/retired-only rule). Fail closed
on missing or stale inputs; risk reduction untouched; promotion is a
separate owner decision fed by the sufficiency report; epochs never
pool.

## 4. Milestones

- **SHW-1 (this round): contracts + storage** for the overlay task,
  with fresh/pre-migration, idempotency, conflict, cross-epoch, and
  read-only-guarantee tests.
- **SHW-2: the runner CLI** (register/observe/mature/status) and
  scheduler wiring.
- **SHW-3: sufficiency reporting** (CLI/file first; UI tab only if the
  owner wants it).
- **SHW-4: stream start** — requires the preregistration's [TO FREEZE]
  values frozen by the owner FIRST; registration binds that document's
  SHA-256 and the epoch clock starts.

## 5. Open decisions for the owner (unchanged)

1. Cycle cadence detail: month-end computation with daily freshness
   checks vs monthly-only computation.
2. Host: operational clone's frozen release commit vs pinned tag on the
   dev machine.
3. Whether SHW-3 surfaces in the Streamlit UI or stays CLI/file-only.

## 6. Non-goals

No generic multi-strategy framework (a second observed task would get
its own runtime, reusing conventions — exactly as this one does beside
ML-LR-6's); no order simulation; no Alpaca paper orders; no
auto-promotion; no LLM involvement; no backtesting.
