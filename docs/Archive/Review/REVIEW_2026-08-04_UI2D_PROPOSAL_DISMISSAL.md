# Independent review — UI-2d proposal dismissal

Date: 2026-08-04
Reviewer: Codex
Contract: `docs/Archive/Plans/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md`
sections 3–8, 10, and 12 (dismissal release only)

## Outcome

**Accepted after correction.** UI-2d now meets the dismissal-only definition
of done. Automatic expiry was not implemented and remains separately gated;
physical purge remains deferred and owner-authorized. No broker call, order
mutation, policy change, ML/LLM authority, or live-trading path was added.

Submitted implementation quality: **7.5/10**. The architecture, transaction
shape, UI confirmation flow, audit retention, and test breadth were strong,
but two fail-closed evidence gaps could archive proposals that were not
provably unused. Corrected quality: **9.5/10**.

## Reviewed commits and dispositions

| Commit | Disposition | Review |
|---|---|---|
| `6d287f0` | Accepted after correction | Complete implementation diff reviewed; UI2DREV-001 through UI2DREV-003 corrected at `a118470`. |
| `1ff8063` | Accepted after replacement | README/action-plan content was accurate before merge; the handoff became stale after PR #143 and is replaced by the review handoff. |
| `8f2e9a7` | Accepted after correction | PR #143 merge tree is byte-identical to `1ff8063`; UI2DREV-004 records the missing post-merge state update. |
| `a118470` | Accepted | Independent production/test correction; all findings reproduced red before this commit and pass green after it. |

## P0–P4 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UI2DREV-001 | P2 | Resolved | `6d287f0` | `assistant/storage.py::_dismissal_records` | `execution_telemetry_events` was not checked, so a proposal with durable validation-attempt evidence could be archived if its status was corrupted back to `proposed`. | `test_execution_telemetry_refuses_dismissal` failed red with `dismissible_ids == ("p-telemetry",)`. | The contract permits dismissal only when validation was never attempted; durable telemetry is authoritative evidence that it was. | Count telemetry child rows alongside broker orders, broker events, and reservations; any row refuses dismissal. | Red on merged `8f2e9a7`; green at `a118470`. |
| UI2DREV-002 | P2 | Resolved | `6d287f0` | `assistant/storage.py::_allocation_batch_references` | Valid JSON with `proposal_ids` as a string was iterated character-by-character, allowing a structurally corrupt batch reference to evade the fail-closed scan. | `test_structurally_invalid_allocation_batch_payload_fails_closed` failed red and classified `p-any` as dismissible. | A malformed batch means the system cannot prove a proposal was never batched; guessing unused violates the all-or-nothing audit boundary. | Validate the top-level object, `proposal_ids` list, `legs` mapping, and every referenced ID; malformed structure now fails closed against all candidates. | Red on merged `8f2e9a7`; green at `a118470`. |
| UI2DREV-003 | P3 | Resolved | `6d287f0` | `assistant/storage.py::_preview_from_records` | The confirmation hash covered ID/status/updated-at/verdicts but not the displayed intent, timestamps, idempotency key, or raw payload, so an untracked row mutation could change proposal identity without invalidating confirmation. | `test_preview_hash_covers_complete_proposal_state` changed AAPL to MSFT without touching `updated_at`; the old hash still dismissed the row red. | Section 6.2 requires the hash to cover the complete preview and current database state; confirmation must not archive a different identity than the operator reviewed. | Hash created/expires/updated timestamps, idempotency key, exact stored payload, status, ID, and verdicts with deterministic JSON separators. | Red on merged `8f2e9a7`; green at `a118470`. |
| UI2DREV-004 | P3 | Resolved | `8f2e9a7` | `docs/SESSION_HANDOFF.md` and `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` | After PR #143 merged, durable records still said nothing was merged and review was pending. | Git shows `origin/main = 8f2e9a7`; the submitted handoff names `5cb831c` as main and says the owner must open the PR. | Cross-computer recovery depends on the handoff and action plan describing the actual merge/review state. | Replaced the handoff and marked UI-2d complete after correction in the action plan and milestone record. | Final documentation diff and Git topology checked on the review branch. |

No P0, P1, P4, or open issue remains.

## Validation

Environment: Python 3.13.14.

- Red proof on merged `8f2e9a7`: 3 targeted tests failed for the expected
  reasons.
- Corrected targeted proof: 3 passed, 43 deselected.
- UI-2d and History-focused suites: 107 passed in 69.32 seconds.
- Adjacent execution telemetry, allocation batch, import boundary, execution,
  and schema suites: 184 passed in 79.17 seconds.
- Full suite on code commit `a118470`: 2,666 passed, 1 skipped, 25 warnings in
  531.89 seconds.
- Warnings are the existing WebSockets legacy warning and 24 joblib/NumPy
  deprecations.
- Required compileall and final diff/status checks are recorded in the session
  handoff.

## Residual limits

The review did not contact Alpaca, mutate the operator database, exercise a
live Streamlit process, install scheduled tasks, or start an evidence epoch.
The existing single-process transaction tests and storage claim-concurrency
coverage support the `BEGIN IMMEDIATE`/compare-and-set race design; UI-2d still
has no dedicated multi-process dismiss-versus-claim test. This is a remaining
test limit, not evidence of an observed defect.

## Claude counter-review (2026-08-04, appended)

Every finding was independently re-verified red on submitted snapshot
`6d287f0` with fresh probes before acceptance:

- **UI2DREV-001 confirmed red:** a proposal with an
  `execution_telemetry_events` row was reported `dismissible` — durable
  validation-attempt evidence ignored. The finding is correct, and after
  the fix the child-table check list is verified COMPLETE against the
  schema: exactly four tables carry a `proposal_id` column
  (broker_orders, broker_order_events, execution_telemetry_events,
  execution_reservations) and all four now refuse.
- **UI2DREV-002 confirmed red:** a batch payload with
  `"proposal_ids": "p-any"` (a string) was iterated character-by-character
  and the referenced proposal classified dismissible. Correct; the
  structural validation now fails closed.
- **UI2DREV-003 confirmed red:** swapping the stored intent's ticker
  without touching `updated_at` left the old preview hash valid and the
  mutated row was dismissed. Correct; the hash now covers the exact stored
  payload, idempotency key, and all timestamps.
- **UI2DREV-004 accepted:** the handoff/action-plan staleness after the
  owner's fast merge is the known push/merge race; the replacement records
  are accurate.

Verdict: both P2s and both P3s are genuine; the corrections are accepted
as written. Focused suites re-ran green on merged main during the
counter-review.

The generalized-instance search over the corrected code found one residual
member of the UI2DREV-001 evidence class:

| ID | Priority | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| CRUI2D-001 | P3 | Resolved | `assistant/storage.py::_DISMISSAL_EXECUTION_EVIDENCE_KEYS` | The `reviewed_override` payload key — written by the same `override_available` transition that writes `violations` (execution_service stores `build_reviewed_override_record()` under it) — was missing from the frozen evidence-key list. Unreachable without `violations` through any code path, but the payload check exists precisely for arbitrary status/payload corruption, so each override-evidence key must refuse on its own. | Added `reviewed_override` to the frozen tuple with a comment recording the co-write relationship, plus a parametrized refusal case. | Reverse mutation (key removed) failed the new case `test_execution_shaped_payload_evidence_refuses[reviewed_override-...]` and restoration returned it green; focused dismissal/History/outcome suites 69 passed; full suite green on the exact final tree (counts in the session handoff). |
