# Counter-review — SEP-2 launch-surface review

Reviewer: Codex, 2026-08-22

Reviewed branch: `origin/user/claude/review-sep2-launch-20260822`

Reviewed head: `b4b896f8606f7ce520b13fcd4d71f68793328e34`

Submitted Codex head: `7a21597c38287938a574ae1deddceaf61a0dca14`

**Verdict: accepted after correction. No P0/P1/P2; one P3 corrected.**

## Exact range and commit dispositions

The fetched Claude head was stable before review. Its merge-base with the
submitted Codex head was exactly `7a21597c38287938a574ae1deddceaf61a0dca14`.

| Commit | Disposition | Reason |
|---|---|---|
| `8f7a8ac0d3af0b7d96c6b2a5988b9e1c48daf4a1` — Name the operations guard for what it now asserts | **Accepted** | The rename aligns the test name with its zero-tolerance assertion without changing scope or behavior. The dangerous import still fails under the new name. |
| `b4b896f8606f7ce520b13fcd4d71f68793328e34` — Record the independent review of the SEP-2 launch-surface tranche | **Accepted after correction** | The archived report correctly records both P3 findings and every reviewed Codex commit. Its handoff update undercounted those findings as one; CRSEP2L-001 corrects the current handoff without changing the historical review record. |

## P0–P3 ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CRSEP2L-001 | P3 | Closed | `b4b896f` | `docs/SESSION_HANDOFF.md` §7ds | The current handoff said Claude found one P3, while Claude's archived report, verdict, issue ledger, and commit message all correctly record two: SEP2L-001 and SEP2L-002. A new session would undercount the review and miss the corrected stale-baseline defect. | Direct comparison of the handoff with `REVIEW_2026-08-22_SEP2_LAUNCH_SURFACE.md`. | The canonical current-state record must agree with the immutable review record; otherwise commit disposition and issue history are ambiguous. | State two P3 findings and summarize SEP2L-002's stale duplicate-baseline correction in §7ds. | Active-document checks pass on the corrected current handoff; the archived report is preserved unchanged. |

## Independent verification

- Focused entry-point, project-boundary, mandate, and active-document tests pass
  **83/83** on Claude's exact pushed head.
- Reintroducing `assistant.operations` into `scripts/run_ml_shadow.py` makes
  `test_no_entry_point_outside_the_trading_assistant_reaches_broad_operations`
  fail with that exact importer named; restoring the source returns the tree to
  Claude's pushed content.
- The test rename changes no assertion or scan scope.
- Claude's mandate-fingerprint, object-identity, data-inventory, crossing, and
  remaining-scope claims agree with the submitted implementation and current
  architecture records.

No provider, credential, licensed row, broker, operator database, scheduled
task, deployment, backtest, outcome, research look, or evidence epoch was
accessed or changed.

## Remaining scope

SEP-2 remains incomplete. The next bounded tranche inventories and constrains
the six non-assistant entry points that still receive mutable
`assistant.storage` access before any physical database split or task migration
is attempted. It must not deploy, migrate the operator database, move scheduled
tasks, or disturb `paper-epoch-006`.
