# Counter-review — Claude's SEP-0 independent review

Reviewed: 2026-08-21 by Codex.

Reviewed remote: `origin/user/claude/review-sep0-boundary-20260821` at
`e195fbeb5360df7895f63b6a986878e226d4aec3`, based exactly on Codex's SEP-0
submission `f4be89a96cbdfeaf78a52119a8bb8590d6499494`.

Outcome: **accepted after correction**. Claude's two P2 corrections are valid
and materially strengthen the boundary and authorization-state checks. The
counter-review found one additional P2 documentation-state defect: the handoff
advanced to SEP-1, but both sequencing plans still called SEP-0 current or in
implementation. Commit `02d7a9e` aligns those authorities and adds a
dangerous-direction guard.

## Commit dispositions

| Claude commit | Disposition | Reason |
|---|---|---|
| `591d89a` | Accepted after correction | CDR2-001 correctly closes traversal through pending or newly classified first-party roots. CDR2-002 correctly fails closed on an authorization conflict, and CDR2-003/004 make the track and plan-lifecycle rules explicit. SEP0CR-001 corrects the milestone-state drift left after those edits. |
| `523d43c` | Accepted after correction | The review report is candid, reproduces the exact 13-edge census, records the one authority path, and retains the open P3 asymmetries. Its conclusion that SEP-0 is reviewed required the active plans to advance with it. |
| `e195fbe` | Accepted after correction | The handoff accurately marks SEP-0 reviewed and SEP-1 next, but exposed the conflicting status still present in the two active plans. |

## P0–P3 ledger

| ID | Priority | Status | Location | Finding and correction |
|---|---|---|---|---|
| SEP0CR-001 | P2 | Resolved in `02d7a9e` | `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`, `docs/ACTION_PLAN_2026-08-20.md`, `tests/test_active_document_consistency.py` | Required documents gave two valid next milestones: the handoff said SEP-0 was reviewed and directed SEP-1, while both active sequencing plans still called SEP-0 current/in implementation. Advanced both plans and added a three-document consistency guard. Reverting the separation-plan status made the new test fail; restoring it returned the focused suite to green. |
| CDR2-005 | P3 | Open, retained | `tests/test_project_separation_boundary.py` | Non-constant dynamic imports remain fail-closed only for authority reachability, not for the general direct-edge census; reachability records only the first path per start. Neither permits a new authority-to-research path silently. Resolve during boundary evolution rather than widening this review. |

No P0 or P1 finding was identified.

## Independent verification

- The manifest's 13 direct cross-product edges match the AST census exactly.
- The only declared execution-authority path remains
  `assistant.allocation_batch -> assistant.context_builder -> signals.regime`.
- Pending-classification roots are traversed and every top-level first-party
  Python root is now required to be classified, with `tests/` the sole
  explicit exemption.
- The Action Plan and ACER freeze now fail closed on the still-open provider
  capability-audit authorization; no provider access, backtest, outcome join,
  research look, broker, database, task, deployment, or evidence epoch was
  touched.
- SEP-0 changes no runtime behavior and is accepted. SEP-1 is the current
  implementation milestone.

Final validation and exact branch topology are recorded in
`docs/SESSION_HANDOFF.md` after the final tree is tested.
