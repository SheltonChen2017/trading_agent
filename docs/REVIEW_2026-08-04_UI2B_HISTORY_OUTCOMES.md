# Independent review — UI-2b History outcome filtering

Reviewed: 2026-08-04

Scope: Claude implementation 335c9fc and handoff 8ff2017, based on main
3c991a3. Review branch: codex/review-ui-2b-history-outcomes-20260804.

Final disposition: accepted after correction. The production implementation
matches the frozen action-plan taxonomy and is read-only. No P0, P1, or P2
issue was found. Submitted quality: 9/10; corrected quality: 9.5/10.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| 335c9fc | Accepted after UI2BREV-001 test hardening | Production mapping, SQL filtering, UI intersection, unknown-status handling, and navigation persistence are correct. |
| 8ff2017 | Accepted after replacement | Accurate implementation handoff; superseded by the completed-review handoff. |
| 9dcff80 | Accepted | Review-only regression closes the acknowledged UI pagination sensitivity gap. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UI2BREV-001 | P3 | Resolved | 335c9fc | tests/test_ui_history_outcome_filter.py | Storage tests proved filtering before limit, but the real UI was not pinned to that query; a future fetch-then-filter rewrite could hide older matching rows behind newer nonmatching rows. | Claude explicitly recorded the coverage limit. A new AppTest seeds six newer nonmatches above an older filled row and lowers the UI limit to five. | The newest-N-of-filtered-kind contract is user-visible and prevents incomplete History results; its final UI wiring should be regression-protected. | 9dcff80 adds the large-history AppTest without changing production code. | Real implementation passes. A temporary fetch-then-filter reverse mutation failed exactly because the filled row disappeared; restoration passed all six UI-2b AppTests. |

No reviewed issue remains open.

## Verification

- Frozen mapping matches every action-plan group exactly and covers all 19
  canonical statuses.
- Legacy executed remains Broker working / unresolved; Filled contains only
  filled; unknown/non-string statuses display Other / unknown.
- SQL known/unknown union is parameterized, ordered newest-first, limited after
  filtering, and read-only.
- Outcome and exact-status filters intersect and explain empty intersections.
- Reconcile/cancel controls remain limited to the displayed rows and retain
  their explicit confirmation and service calls.
- No schema, proposal lifecycle, broker, policy, scheduler, evidence epoch,
  ML/LLM, or execution-authority change exists.

Validation on Python 3.13.14:

- submitted focused baseline: 65 passed;
- strengthened focused UI/mapping/import-boundary suite: 73 passed in 38.18s;
- reverse mutation: 1 failed for the expected pagination reason;
- full suite: 2,576 passed, 1 skipped, 25 warnings in 397.43s;
- compileall and git diff --check: clean.

Warnings are the existing WebSockets and joblib/NumPy deprecations.

