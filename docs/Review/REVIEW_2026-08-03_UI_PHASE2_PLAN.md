# Independent review — UI Phase 2 implementation plan

Reviewed: 2026-08-03

Scope: Claude's single documentation commit `3a35d8d`, based on merge
`17605f5`. No UI or storage implementation was submitted. The plan is accepted
after the corrections below; implementation has not started.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `3a35d8d` | Accepted after correction | It captured all four owner requests and protected broker audit history, but its sequencing duplicated navigation work and it understated two behavioral/persistence changes. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UIPLAN-001 | P2 | Resolved | `3a35d8d` | Action plan UI-2c | Sidebar navigation was called presentation-only. Current `st.tabs` code executes every tab body on every rerun; conditional sidebar routing will execute only the selected page and can change warning reads, portfolio capture, network loading, and other page effects. | `scripts/personal_assistant_ui.py` creates eight tabs followed by eight executable bodies rather than isolated passive views. | Treating a control-flow change as cosmetic can silently remove required behavior or move side effects to surprising times. | Plan now requires a page-effect inventory, explicit global/page-local boundaries, and AppTest reachability/behavior coverage. | Cross-checked against the current UI structure and briefing/history effects. |
| UIPLAN-002 | P3 | Resolved | `3a35d8d` | Action plan UI-2a/UI-2c sequencing | Renaming the tab and its tests before replacing the tab navigation would modify the same labels and navigation tests twice, while the owner's layout request landed third. | Submitted sequence shipped UI-2a with filtering, then independently reworked navigation for UI-2c. | Duplicate churn adds review cost and delays the owner's highest-impact layout change. | UI-2a and UI-2c are now one first milestone; filtering follows second. | Revised sequence changes navigation labels and tests once. |
| UIPLAN-003 | P3 | Resolved | `3a35d8d` | Action plan UI-2b | Outcome groups were examples without an exhaustive status contract or rules for combining the new and old filters. Legacy `executed` means broker acceptance, not a confirmed fill. | Canonical `STATUSES` contains nineteen values with distinct broker meanings; the current UI exposes one exact-status selector. | An incomplete mapping can show an unresolved order as completed or produce confusing empty results from contradictory filters. | Plan requires a canonical exhaustive mapping, unknown-status fail-safe, exact-status Advanced filter, intersection semantics, and visible active-filter state. | Cross-checked against `assistant/proposal_status.py` and current History filtering. |
| UIPLAN-004 | P3 | Resolved | `3a35d8d` | Action plan UI-2d and archived cleanup plan | “Entry removal” implicitly bundled durable dismissal, automatic expiry on History rendering, CLI work, and deferred purge while calling the phase non-runtime. | Archived plan required `expire_due_proposals()` during History rendering and made automatic expiry part of dismissal DoD. | A read-oriented page should not gain an unrelated lifecycle mutation without an explicit product decision, and durable state work must not be described as non-runtime. | Dismissal is the first durable milestone; automatic expiry is a separately approved follow-up with an explicit trigger; physical purge remains deferred. | Action and archived plans now distinguish all three scopes and definitions of done. |

No P0 or P1 issue was found. No issue remains open. The owner's statement that
Streamlit is running is accepted as authoritative; the review environment's
isolated port view cannot observe the owner's host process and is not evidence
to the contrary.

`docs/FEATURE_MILESTONE_RECORD.md` is unchanged because this is a plan review,
not a completed feature or milestone.
