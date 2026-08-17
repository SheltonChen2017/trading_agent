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

## Measured limitation: check 4 is lexical (2026-07-30)

Check 4 above ("No portfolio-change or execution language") is a
**presentation filter, not the safety boundary.** The shared advisor filter
was tuned against advisor phrasing and originally leaked 14 of 24 directives
written in formal committee voice. A committee-specific layer now matches
directive framing rather than allocation vocabulary alone. It rejects all 24
measured directives while preserving all 14 neutral descriptions in the probe,
including descriptions of the candidate's weight change, the strategy's
drawdown effect, and relative position size.

`tests/test_committee_action_language_probe.py` pins both measured sets. A
passing finite corpus is not proof that arbitrary prose cannot express the
same idea with different words.

**What actually contains the risk** is everything else in this document: the
committee is read-only, cannot create or modify a proposal, cannot reach a
broker, and human approval plus execution revalidation remain mandatory. Do
not treat a clean validator pass as evidence that the prose carries no
advice. A future structural improvement would constrain the output surface
further so less safety meaning depends on interpreting free prose.

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

### Current implementation status (reviewed 2026-08-05)

The provider, mandatory audit persistence, exact-input UI cache binding, clear
unavailable state, and execution isolation are implemented. The required
frozen replay/adversarial corpus now exists and is enforced:
`tests/committee_corpus/cases.json` holds 69 deterministic cases (51 replay,
10 injection, 8 memory-poisoning) executed through the REAL projection/
validation/error-mapping pipeline by `tests/test_committee_replay_corpus.py`,
whose inventory tests pin the ADR minimums (>=50 replay plus adversarial
categories) and whose canonical SHA-256 assertion freezes the complete case
content, not only IDs and category counts. One injection case deliberately freezes a DOCUMENTED lexical-
filter limitation (a homoglyph-obfuscated directive passes the filter) as a
measurement, not an endorsement — the architectural boundary remains the
containment. The CLI `review unavailable` surface exists as
`committee-review <proposal-id>` in `scripts/run_personal_assistant.py`:
every defined gate, input, provider, schema, validation, and audit failure
prints one `Review unavailable (<code>): ...` line and
exits 2, an accepted review prints its cited sections plus the mandatory
human-approval reminder, and the audit row remains a display precondition.
Independent review added the packet-construction failure path so a configured
broker/data outage cannot escape that surface as a traceback.

**The experimental gate is deliberately NOT removed by this work.** The
Streamlit surface and CLI both still require `ANTHROPIC_API_KEY` AND the
explicit process opt-in `ENABLE_EXPERIMENTAL_COMMITTEE=1`. With the corpus
and CLI surface in place, every listed release-gate prerequisite is
satisfied; removing the gate is now purely a separately reviewed,
owner-authorized decision.
