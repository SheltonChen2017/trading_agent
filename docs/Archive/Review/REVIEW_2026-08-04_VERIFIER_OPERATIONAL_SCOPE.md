# Independent review — verifier operational scope

Date: 2026-08-04

Review base: `6a551cd`

Implementation commit: `90f11ad`

Merge commit: `eaa9c11`

Review branch: `codex/review-verifier-operational-scope-20260804`

## Outcome

Accepted after correction. The `-Scope operational` implementation is
fail-closed and preserves default `all` behavior: it verifies exactly the four
operational tasks, reports six omitted ML checks explicitly, requires the full
ML paths under `all`, emits no credential values, and exits nonzero when
required checks fail. Independent execution reproduced a valid JSON
operational report with four absent-task failures and six visible skips.

Submitted quality: **8.0/10**. The PowerShell correction is sound, but its
active deployment records remained contradictory, its automated regression
did not execute the new behavior, and its defect accounting overstated the
number of pre-existing conditional-expression crashes. Corrected quality:
**9.5/10**.

## Commit dispositions

- `90f11ad` — **accepted after correction**. Runtime behavior is correct;
  VOSREV-001 through VOSREV-003 required documentation and test corrections.
- `eaa9c11` — **accepted after correction**. The merge tree exactly matches
  `90f11ad`; no conflict-only change was introduced.

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| VOSREV-001 | P2 | Resolved | `90f11ad` | `docs/Archive/Operations/PHASE5_DEPLOYMENT_SESSION.md:42-73`; `docs/SESSION_HANDOFF.md:76-81,117-129`; `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md:259-267,403-408` | The active plan, deployment checklist, and handoff still said mandate review/merge was pending and that the verifier could only validate all eight tasks, after this commit merged an operational-only scope. | Repository-wide exact-text search found the old instructions in every primary handoff/sequence document. | These documents drive the owner-led scheduler session. Telling the operator the four-task verifier is unusable can replace the new fail-closed check with manual inspection and misstate the branch's actual merge state. | Reconciled the action plan, Phase 5 checklist, runbook, ML status, and final handoff with PRs #146-#148 and documented the exact `-Scope operational`/default-`all` commands. | Stale-text search and final diff checks; focused/full results below. |
| VOSREV-002 | P3 | Resolved | `90f11ad` | `tests/test_ml_evidence_operations.py:311-333` | Automated coverage only searched PowerShell source strings and regexes; it never bound parameters, evaluated the corrected `$()` expression, serialized the report, selected four tasks, or exercised the nonzero failure path. | The submitted test only used `read_text()` assertions; the claimed end-to-end run existed only as a machine-local observation. | This is a material Windows operational boundary. A future syntactically plausible but non-running edit could pass the static test and recreate the exact defect this change claims to close. | Added a Windows-only subprocess regression over the real verifier with read-only scheduler stubs, omitted ML paths, exact task/skip inventory checks, JSON parsing, and fail-closed exit propagation. | Corrected focused suite passes 13 tests; the new test executes on Windows and skips explicitly on non-Windows CI. |
| VOSREV-003 | P3 | Resolved | `90f11ad` | `docs/Archive/Review/REVIEW_2026-08-04_PHASE5_MANDATE_APPROVAL.md:76-94`; `docs/SESSION_HANDOFF.md:52-58` | The counter-review said two latent statement-position `if` crashes were fixed, but the pre-change verifier contained one such site. The other two `$()` expressions were newly added config/artifact details, not pre-existing crashes. | Direct inspection of `6a551cd:scripts/verify_windows_evidence_tasks.ps1` shows only the credential `-Detail ( if ... )` site. | The durable issue ledger must distinguish a discovered historical defect from defensive syntax used in new code; otherwise review evidence exaggerates both defect count and mutation coverage. | Corrected the counter-review and handoff wording to identify one latent crash and two newly introduced conditional details written correctly from the start. | Pre-change source comparison plus final documentation review. |

No P0 or P1 issue was found. No issue remains open.

## Validation

- Focused evidence-operations suite: 13 passed on Windows.
- Direct operational-scope verifier probe: valid JSON, four absent operational
  task failures, six explicit ML skips, nonzero exit.
- Full suite: 2,668 passed, 1 skipped, 25 warnings in 530.88 seconds.
- Required `compileall`: clean.
- `git diff --check`: clean.
- Environment: Python 3.13.14, Windows PowerShell 5.1.

## Scope and residual limits

The review did not install, modify, start, or stop scheduled tasks; inspect
credential values; contact Alpaca; mutate the operator database; bootstrap the
ledger; or start an evidence epoch. The Windows regression replaces scheduler
cmdlets with no-task stubs. Actual task definitions and successful task output
remain owner-led operational acceptance checks.
