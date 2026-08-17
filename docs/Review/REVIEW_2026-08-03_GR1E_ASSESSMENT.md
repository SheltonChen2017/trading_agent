# Independent review — GR-1E composition-thinning assessment

Date: 2026-08-03

Reviewer: Codex

Implementation assessment: `b12058f`

Merged assessment tree: PR #124, `2f4a360`

Final reviewed starting tree: `16e0451`

Review branch: `codex/review-gr1e-assessment-20260803`

## Final disposition

**Accepted after documentation correction. GR-1 is complete against the
intended scope of archived plan sections 6.2–6.4; no additional GR-1E code
extraction is warranted.** The remaining
`execute_approved_paper_proposal()` body is the coordinator: it orders the
already-extracted phases, maps exceptions to terminal outcomes, builds
refusal/telemetry context, and makes exactly one broker-submission call.
Moving that control flow behind another dependency contract would relocate
the composition layer rather than materially thin it.

The original assessment reached the right architectural outcome but
overstated its evidence. It described all remaining work as domain calls and
“no inline logic,” said both recovery wrappers make one storage call, reported
that no test file changed except imports, and marked the whole architecture-
debt chapter closed despite that chapter explicitly including
`allocation_batch.py`. Those statements are corrected in the durable status
documents. No production or test code changed during this review.

Quality assessment: **7.5/10 for the submitted GR-1E assessment; 9.5/10 for
the corrected durable record.** The stop/extract decision was sound and the
source inspection was useful. The lower submitted score reflects evidence
claims that were materially more absolute than the source and Git history
support, not a defect in the already-reviewed execution behavior.

## Exact scope and commit dispositions

The GR-1E review range is `c66db0a..16e0451`:

| Commit | Disposition | Evidence |
|---|---|---|
| `b12058f` | Accepted after GR1EREV-001 and GR1EREV-002 corrections | Docs-only GR-1E assessment. The architectural outcome is accepted; measurement, test-history, recovery-call, and debt-closure wording required correction. |
| `015fc8b` | Accepted as an accurate awaiting-review handoff at commit time | It recorded the assessment branch and correctly stopped for independent review, but later became stale after the review began. |
| `2f4a360` | Accepted | PR #124 merge tree is byte-identical to topic tip `015fc8b`; no conflict-resolution delta. |
| `768a626` | Accepted after GR1EREV-003 correction | Restoring the omitted handoff state was useful, but the claim that commit `32f0378` was lost “during conflict resolution” is not supported by the graph. |
| `16e0451` | Accepted | PR #125 merge tree is byte-identical to topic tip `768a626`; no conflict-resolution delta. |

The earlier GR-1D confirmation commits `2673714` and `c66db0a` are the
review base, not GR-1E implementation commits. Their confirmation content was
already reviewed in the preceding handoff; `c66db0a`'s merge tree is
byte-identical to `2673714`.

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR1EREV-001 | P2 | Resolved | `b12058f` | `docs/operations/GENERAL_READINESS_STATUS.md`, GR-1E; `docs/ACTION_PLAN_2026-08-02.md`, GR-1E | The submitted assessment used a non-retained line-classification method as if it were a reproducible gate, called the residue “no inline logic,” described every call as a domain phase, said both recovery wrappers make one call, and claimed the literal no-test-edit clause held. This weakens the evidence supporting milestone acceptance. | Independent AST inventory finds 54 statement nodes, 49 call nodes, and 28 distinct call expressions, including constructors/formatters. The coordinator contains branches, timestamps, exception mapping, and message/list/dict construction. `recover_stale_claim()` has one static `reclaim_stale_status` call site inside a status loop and can invoke it repeatedly. From pre-GR baseline `d9e3196` to `16e0451`, `tests/test_execution_characterization.py` changed +1,211/-7, while archived plan §6.3 itself requires added characterization. | A milestone assessment must distinguish architectural composition from the ordinary inline control flow that implements it and must adjudicate its definition of done against observable history. Otherwise future reviewers may rely on false invariants or repeat an unnecessary extraction. | Reframed the evidence around source/AST facts; narrowed “no inline logic” to no inline financial computation, transition SQL, or broker interpretation; described the bounded recovery loop; and recorded the archived plan's literal test-edit contradiction while confirming no existing behavioral expectation was relaxed to pass the refactor. | Source inspection and AST inventory on `16e0451`; Git `--numstat` and plan comparison; final document search and diff checks. |
| GR1EREV-002 | P2 | Resolved | `b12058f` | `docs/architecture/ARCHITECTURE_DEBT.md`, item 1 | The assessment marked the “GR-1 chapter” closed while the item it purported to close explicitly scopes both `execution_service.py` and `allocation_batch.py`. It also assigned the batch residual to GR-2 more strongly than the adopted action plan does. | Item 1's opening paragraph names both modules; `allocation_batch.py` still owns cross-leg reservation math. Archived GR-1 §6 is focused on `execution_service.py`; the adopted plan separately sequences GR-2 risk-registry work and later allocation-service/product work. | Closing a broader debt item than the milestone actually resolved hides remaining structural work and can silently reorder the owner-adopted plan. | Marked only the `execution_service.py` portion closed, retained item 1 as partially open for `allocation_batch.py`, and required future ownership/sequencing to come from the adopted action plan. | Cross-document scope comparison and final `rg` checks. |
| GR1EREV-003 | P3 | Resolved | `768a626` | `docs/SESSION_HANDOFF.md`, Git provenance and next-step sections | The handoff said `32f0378` was dropped by PR #123 conflict resolution and retained multiple stale statements saying PR #122 was unmerged and GR-1E was next. This would misdirect the next computer/session. | `32f0378` is not an ancestor of `16e0451`, no current branch contains it, PR #123's topic tip was `2673714`, and `c66db0a` is tree-identical to that tip. PRs #122–#125 are on `main`; the handoff still said “GR-1E: next assessment” in three places. | The handoff is the canonical cross-agent state. Incorrect topology and next-action instructions create duplicate work and unsafe branch assumptions. | Replaced the handoff after the review with verified topology, dispositions, validation, remaining local-only work, Phase 4 as the next owner-directed step, and the correct explanation that `32f0378` simply was not part of PR #123's merged topic history. | `git merge-base --is-ancestor`, `git branch --contains`, merge-tree identity checks, and stale-text search. |

No P0 or P1 issue was found. All confirmed issues were documentation and
milestone-accounting defects; none changed order submission, state
transitions, recovery atomicity, paper-only authority, or broker behavior.

## Independent source assessment

On the merged starting tree:

- `assistant/execution_service.py` is 952 lines, including a 198-line audit
  history docstring and compatibility imports retained by earlier reviews.
- `execute_approved_paper_proposal()` is 281 source lines. A Python-AST walk
  finds 54 statement nodes, 49 calls, and 28 distinct call expressions.
- The function contains one broker-submission call and delegates financial
  sizing, claim fencing, policy/risk authorization, validation, reservation,
  submission-outcome resolution, accepted-order journaling, and durable
  transitions to reviewed modules or storage primitives.
- Its remaining inline work is appropriate composition: branch ordering,
  exception-to-status mapping, timestamps/attempt identifiers, telemetry,
  and diagnostic context construction.
- `recover_stale_reconciliation()` has one static call to the atomic reclaim
  primitive. `recover_stale_claim()` has one static call site inside a bounded
  status loop, so it may call that same primitive more than once.
- Eight direct kernel modules remain independently testable, and an AST test
  forbids private peer imports.
- The atomic claim and reclaim semantics remain in `AssistantStore`; ambiguous
  submissions still resolve through reconciliation rather than blind retry.

This is sufficient to accept outcome 1. Line count alone is not the reason:
the deciding fact is that further extraction would move the coordinator while
leaving the same phase ordering and failure mapping somewhere else.

## Merge and validation evidence

Merge identities:

```text
2673714 -> c66db0a: exact tree
015fc8b -> 2f4a360: exact tree
768a626 -> 16e0451: exact tree
```

Final validation on the corrected review tree:

```text
focused architecture/characterization tests: 93 passed in 31.62s
full suite: 2,485 passed, 1 skipped, 25 warnings in 420.68s
Python: 3.13.14
compileall: clean
git diff --check: clean
```

The first focused invocation used `.tmp/pytest-gr1e-focused` without first
creating its `.tmp` parent: 51 tests passed and 42 fixture setups errored with
`FileNotFoundError`. The corrected invocation used a valid top-level
base-temp path and all 93 tests passed. This was a runner-path error, not a
product failure. Both temporary pytest trees were removed after validation.

The final handoff records exact durations/counts and the review correction
commit. No operator database, brokerage credential, scheduled task, formal
evidence epoch, model registry, policy authority, or live-trading setting was
read or changed for this review.

## Next step

Phase 3 is complete. The adopted action plan names Phase 4 next: GR-5 alert
delivery plus GR-3 fault drills, with GR-2 risk-registry consolidation riding
along. GR-5 requires the owner's alert-channel decision before implementation.
Completion of GR-1 does not authorize starting another milestone, live
trading, operational deployment, an evidence epoch, or autonomous strategy
work.
