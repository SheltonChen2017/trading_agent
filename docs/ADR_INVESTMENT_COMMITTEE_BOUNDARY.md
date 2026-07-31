# ADR: Read-only investment-committee boundary

**Status:** Accepted for the foundation layer  
**Date:** 2026-07-30

## Context

The app already computes portfolio values, risk, policy results, research
authority, and candidate trades deterministically. A language model can improve
decision quality by organizing evidence and exposing counterarguments, but a
polished narrative must not become a second trading authority.

The existing optional AI helpers are provider-specific presentation features.
They do not define a reusable, privacy-controlled contract for reviewing an
existing `DecisionPacket` and proposal.

## Decision

The investment committee is a read-only layer after deterministic proposal
generation and before human approval. It receives only:

- an immutable, content-addressed projection of one `DecisionPacket`;
- one existing risk-reducing sell proposal;
- addressable deterministic facts;
- an explicit privacy mode.

The foundation implementation lives in `assistant/llm/` and has no direct
imports from broker, execution, risk-gate, policy, or proposal-generation
modules. The caller supplies a provider that returns one JSON object. The
committee package cannot create or modify a proposal, construct an execution
authorization, or call a broker.

Accepted output must satisfy all of these deterministic checks:

1. Exact schema and enums; no extra fields.
2. Every point cites existing source IDs.
3. Every number and ticker is present in the sources cited by that exact point.
4. No portfolio-change or execution language.
5. Rejected, exploratory, stale, or unavailable research cannot support an
   endorsement.
6. Critical warnings and unavailable critical inputs remain visible.
7. Supportive verdicts contain a counterargument and an invalidation condition.

Any provider, schema, or validation failure returns `review_unavailable`. No
partial or unvalidated prose is accepted.

## Privacy

`percentages_only` is the default. `rounded_dollars` and `exact_dollars` are
explicit opt-ins. Account IDs, credentials, local paths, raw broker objects,
share quantities, and order identifiers are never part of the projection.

The projection contains structured facts rather than raw dataframes, broker
responses, HTML, logs, or concatenated external text.

## Consequences

- A provider adapter, storage/replay record, CLI/Streamlit surface, and replay
  corpus can be added without changing the decision-rights boundary.
- The validator can prove source identity, numeric consistency, ticker scope,
  and research authority. It cannot prove the semantic truth of arbitrary
  non-numeric prose; citations remain necessary but are not sufficient for
  factual correctness.
- The current release is foundation-only. It does not enable autonomous
  trading, new-position creation, live trading, or model-driven proposal
  changes.

## Release gates for the next slice

Before daily model-backed use:

- persist input hash, prompt/schema version, provider/model ID, raw status, and
  accepted/rejected result;
- add a provider adapter with bounded timeout, retries, token budget, and cost
  controls;
- build at least 50 frozen replay cases plus injection and memory-poisoning
  adversarial cases;
- display a clear `review unavailable` state in CLI and Streamlit;
- keep execution revalidation mandatory after any human approval.
