# Counter-review — three-strategy project direction

Counter-reviewer: Codex, 2026-08-26

Independent reviewer: Claude

Governing documents: `CLAUDE.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, and
`docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`

**Verdict: accepted after correction.** Claude's four substantive amendments
are retained: isolated lane checkouts, a frozen shared-file surface with
lane-owned namespaces, one main-line execution of shared-provider audits, and
one common final holdout with three-attempt selection accounting. One
research-rule defect, one regression-coverage defect, and one review-record
defect required correction.

## 1. Exact reviewed snapshot

| Item | Exact value |
|---|---|
| Reviewed remote branch | `origin/codex/main-three-strategy-direction-20260826` |
| Codex implementation | `d00c0e0eb7bae35df34aa031404cdb7940d84301` |
| Claude review head | `c88ac4f379aba996b48fb7f70e5210edda3c7320` |
| Merge base | `d00c0e0eb7bae35df34aa031404cdb7940d84301` |
| Ordered Claude range | `d00c0e0eb7bae35df34aa031404cdb7940d84301..c88ac4f379aba996b48fb7f70e5210edda3c7320` |
| Counter-review correction | `a6cc4fb4b9cf83d1651226983e5e80c9bce104a8` |

The reviewed remote head was stable at `c88ac4f379aba996b48fb7f70e5210edda3c7320`
on the final read-only remote check. The three published strategy-lane heads
were independently rechecked at their common baseline
`c9dcdb647914acbfcefce187a138f52fcdad0c68`.

## 2. Commit disposition

| Commit | Scope | Disposition | Findings |
|---|---|---|---|
| `c88ac4f379aba996b48fb7f70e5210edda3c7320` | Four main-line coordination amendments and Claude's review note | **accepted after correction** | `CR3SD-001`, `CR3SD-002`, `CR3SD-003` |

## 3. P0-P3 issue ledger

There are no P0 or P1 findings.

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| CR3SD-001 | P2 | Closed | `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`, main-line integration direction | "No lane re-tunes a null strategy until it passes" remained circular: passing would require the forbidden retuning, while the sentence did not define how a genuinely new later hypothesis could be distinguished from rescuing the failed family. That ambiguity weakens outcome-look and multiplicity discipline. | A valid null now closes the canonical family; it cannot be tuned or rerun to pass. Any later hypothesis must be a separately preregistered family with a new owner-authorized permanent look budget and cannot retroactively rescue the canonical result. | Focused and complete active-document tests pass; the exact rule is pinned in a regression guard. |
| CR3SD-002 | P3 | Closed | `tests/test_active_document_consistency.py` | Claude described the existing consistency tests as review evidence but added no guard for any of the four new coordination gates. The document was correct at review time, but those gates could regress without a red test. | Added one focused guard for isolated checkouts, the shared-file freeze, lane-owned namespaces, single-execution shared audits, the common final holdout, three-attempt accounting, and valid-null handling. | Removing the exact common-holdout requirement made the new test fail; restoration returned the active-document suite to green. |
| CR3SD-003 | P2 | Closed on the final counter-review tree | Claude review commit and `docs/SESSION_HANDOFF.md` | The review appended prose to the direction but omitted the binding commit-by-commit disposition/P0-P3 ledger and did not update the canonical handoff. The handoff therefore still said the direction was being prepared and the Claude review was pending. | This immutable counter-review record supplies the exact range, disposition, findings, and evidence; the following dedicated handoff commit updates current project state without editing any strategy lane. | Active-document consistency, ordered-commit, clean-status, and exact-remote-head checks are recorded below and in the handoff. |

## 4. Independent reproduction

- The Claude commit has exactly one parent, the exact Codex implementation
  head, and changes only `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`.
- Per-lane checkout isolation and lane-owned namespaces reduce cross-lane and
  merge-time contamination without changing any strategy contract.
- Centralizing shared QuantConnect entitlement, security-master,
  price/corporate-action, constituent, and calendar audits avoids three
  inconsistent characterizations of the same account. Provider access still
  requires separate owner authorization.
- Reserving one shared final period before any real-outcome study prevents a
  lane from consuming the combined holdout. Treating the lanes as one
  selection family correctly acknowledges selection from three parallel
  attempts.
- The shared package, SEP-3 freeze, `paper-epoch-006`, execution authority,
  and unlevered canonical scope are unchanged.

## 5. Validation

| Check | Result |
|---|---|
| Focused three-strategy direction checks | 3 passed |
| Complete `tests/test_active_document_consistency.py` | 61 passed |
| Dangerous-direction mutation | deleting the exact one-common-holdout requirement failed the new guard; restored green |
| First complete-suite attempt | 4,570 passed / 1 failed / 25 warnings; the counter-review handoff had omitted the exact open-owner-decision wording required by an existing authorization guard |
| Shared-checkout complete rerun | 4,571 passed / 0 failed / 25 warnings in 1,350.86 seconds; another session changed three unstaged coordination files during the run, so this is corroborating rather than exact-head evidence |
| Exact detached-head complete rerun | **4,571 passed / 0 failed / 25 warnings** in 1,626.69 seconds at `80e76e765ca66ad2735aa1c74a6a4228a519e537` |
| `compileall` including `research/` | passed |
| `git diff --check` | clean before the correction commit |
| Remote review head | stable at `c88ac4f379aba996b48fb7f70e5210edda3c7320` |
| Three remote lane heads | all remain `c9dcdb647914acbfcefce187a138f52fcdad0c68` |
| Outcomes/provider/broker/operator store/QC/deployment | not accessed |

The exact detached worktree was clean before and after its run and was removed
after verification. Concurrent uncommitted owner-workflow edits in the shared
checkout were preserved, not staged or incorporated into this counter-review.

## 6. Remaining gates and next step

This counter-review authorizes no outcome run and starts no strategy code.
Before any lane's first real-outcome study, the owner must freeze the common
final-holdout boundary and the permanent look/multiplicity contract. Shared
provider audits remain separately authorized main-line work. After this
counter-review is complete, each Codex lane may begin only its documented
contract/fixture milestone on its own long-lived branch and isolated
checkout.
