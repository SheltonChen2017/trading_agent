# Shadow Observation Infrastructure — Design (DRAFT for owner review)

Status: DRAFT 2026-08-18, authored under the owner's adopted sequence
(handoff 7aj). Nothing here is implemented; this document exists to be
reviewed, corrected, and then adopted into the action plan as milestones.

## 1. Purpose and position on the evidence ladder

The project treats four states as distinct: software works; research
evidence supports a claim; paper operation has accumulated prospective
evidence; a human owner has authorized live use. This design builds the
machinery for the THIRD state — accumulating prospective, out-of-sample
evidence for a frozen strategy specification — as a strategy-agnostic
service, so that any future candidate (an allocation rule, a carry
overlay, an external-data signal) starts earning prospective evidence
the day its specification is frozen, without new plumbing per idea.

The A-002 closure makes this the highest-value research investment: the
project's surviving wins are portfolio-construction and risk results,
and those are exactly the claims that need prospective observation
rather than more backtests.

## 2. Core concepts

**Shadow stream.** One frozen strategy specification under observation.
A stream binds, immutably at registration:

- the preregistration document (frozen spec, primary endpoint, gates,
  required independent sample count, multiplicity declaration);
- the exact git commit of the computing code (an evidence epoch: any
  code, config, data-source, or schedule change closes the stream's
  epoch and opens a new one — observations never pool across epochs);
- the schedule (cadence and decision cutoff) and the input data
  contract (sources, point-in-time requirements, freshness limits).

**Shadow observation.** One scheduled, deterministic computation of the
stream's outputs (target weights, hypothetical actions, or predictions)
recorded BEFORE outcomes exist. Observations are append-only,
canonical-JSON, SHA-256-identified records (reusing the existing
contract/hashing/artifact helpers — no parallel implementations), each
carrying its epoch id, computation timestamp with timezone, input-data
identity and freshness evidence, and the outputs.

**Outcome settlement.** A later scheduled job attaches realized
outcomes to matured observations (again append-only; an observation is
never edited). Missing or unsettleable outcomes are recorded as
declared unavailability with reasons — never dropped.

**Sufficiency report.** The only consumer-facing product: for each
stream, the §6 monitoring fields — independent observation unit,
independent count so far, preregistered required count, explicit
sufficiency verdict, concrete insufficiency reasons — plus the frozen
gate and, once (and only once) the required count is reached, the gate
evaluation. No peeking summaries along the way beyond counts.

## 3. Hard boundaries (inherited, not new)

- **Observation only.** No shadow component may create, approve, size,
  submit, cancel, or replace an order, or write to proposal, risk-gate,
  or execution tables. Enforced by construction (separate tables, no
  imports from execution-capable modules into the shadow package) and
  by the read-only-command tests the project already uses.
- **Import boundary.** The shadow package must not be imported by
  execution-capable modules; if a stream computes ML outputs it lives
  behind the existing `ml` boundary rules. `tests/test_ml_import_boundary.py`
  and a transitive-closure check extend to the new package.
- **Fail closed, except risk reduction is untouched.** A missing input,
  stale quote, or crashed computation records a durable refusal for
  that cycle; it never substitutes defaults and never blocks
  reconciliation or the operator's real risk-reducing actions.
- **Promotion is a human act.** A stream reaching sufficiency produces
  a report. Registry/status changes, paper-order authority, or live
  anything are separate owner decisions outside this system.

## 4. Storage and identity

New SQLite tables in the operator database (backward-compatible,
idempotent migration, tested against fresh and pre-migration DBs):

- `shadow_streams` — registration row per stream+epoch: name, epoch id,
  preregistration doc path and its SHA-256, code commit, schedule,
  status (`active` / `closed(reason)`); UNIQUE(name, epoch).
- `shadow_observations` — append-only observation records: stream ref,
  cycle timestamp, canonical payload, payload SHA-256, input-identity
  fields; UNIQUE(stream, cycle) makes reruns idempotent, and a refusal
  row occupies the cycle slot so a crash cannot be silently retried
  into a different answer.
- `shadow_outcomes` — settlement rows keyed to observations, including
  declared-unavailable outcomes with reasons.

File artifacts (immutable, hash-named, atomic writes) mirror each
epoch's registration for cross-machine verification via git-tracked
hashes in the ledger, following the QC-campaign evidence pattern.

## 5. Scheduling

Reuse the existing operational cadence host (the machine already
running paper-epoch scheduling): one additional deterministic entry
point `scripts/run_shadow_cycle.py` that iterates active streams whose
cutoff has arrived, computes, records, and settles. Serial, idempotent,
and safe to rerun; a missed day records a gap (declared, visible in the
sufficiency report), never a backfilled pretend-observation. Inputs are
sliced at the decision cutoff before feature construction.

## 6. Milestones (each one branch, one review)

- **SHW-1 Contracts + storage.** Frozen dataclasses, migration, hashing
  and idempotency tests (duplicate cycles, crash/rerun, mutation after
  construction, cross-epoch refusal).
- **SHW-2 Cycle runner + registration CLI.** Register/close streams,
  run cycles, refusal paths; read-only guarantees tested (execution and
  registry tables byte-identical before/after).
- **SHW-3 Sufficiency reporting.** The §6 report, plus a read-only UI
  tab section (presentation only, no action-shaped fields).
- **SHW-4 First stream onboarding.** Whatever preregistration the owner
  adopts first (the defensive-carry draft is the current candidate);
  its epoch starts the prospective clock.

## 7. Open decisions for the owner

1. Cadence of the first stream (daily computation with monthly
   settlement vs monthly both) — affects the sufficiency arithmetic.
2. Whether shadow cycles run on the operational clone's frozen release
   commit (epoch model 2) or a pinned tag on the dev machine.
3. Whether sufficiency reports surface in the Streamlit UI in SHW-3 or
   stay CLI/file-only until a stream exists.

## 8. Explicit non-goals

No order simulation, no Alpaca paper orders (that is a later, separate
authorization), no auto-promotion, no LLM involvement in computation,
no backtesting (streams observe forward only), and no generic
"framework" beyond what the first two concrete streams need.
