# Independent review — Action Plan Phase 2 hygiene

Prepared: 2026-08-03 by Codex.

Review base: `661a7d4`
Implementation: `34ce463`
Implementation handoff: `c8271a1`
Review branch: `codex/review-phase2-hygiene-20260803`
Review correction/report: the commit containing this file

## Commit dispositions

| Commit | Scope | Disposition |
|---|---|---|
| `34ce463` | AP-1 schema apply/verify, AP-2 runtime-artifact ignores, AP-4 documentation reconciliation | Accepted after PH2REV-001 correction |
| `c8271a1` | Implementation handoff and machine-local snapshot | Accepted after PH2REV-002 and PH2REV-003 corrections in the final reviewed handoff |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| PH2REV-001 | P2 | Resolved | `34ce463` | `assistant/storage.py:4482`, `assistant/storage.py:4521`, `assistant/storage.py:4558` | The verifier compared index and trigger names only. Replacing the unique active-paper-epoch index with a non-unique index and the broker-order proposal-integrity trigger with a no-op trigger under the same names still returned `matches=True`. An operator could therefore receive a successful schema report while uniqueness or relationship enforcement was absent. | The new focused regression test changed both definitions without changing their names and failed red because `SchemaVerificationResult.matches` was `True`. | Named SQLite indexes and triggers are enforcement mechanisms, not labels. A schema verifier used before evidence operations must fail closed when their definitions are weakened, particularly where uniqueness and backward-compatible relationship enforcement protect durable state. | Retain normalized `sqlite_master.sql` definitions for declared indexes and triggers, report `mismatched_indexes` and `mismatched_triggers`, and include either mismatch in the fail-closed `matches` result and CLI JSON. | `test_same_named_weakened_index_and_trigger_are_detected` failed red on `34ce463` and passed after correction, asserting both mismatches by name. The corrected focused suite passed 81 tests; the full suite passed 2,441 tests with 1 skipped and 25 warnings. |
| PH2REV-002 | P3 | Resolved | `c8271a1` | `docs/SESSION_HANDOFF.md:166` | The handoff said strategy-tool commit `a656015` was absent from this computer and potentially recoverable only from an earlier machine. The current checkout actually has both the commit object and local branch `codex/ai-strategy-tool-doc-v2-20260802`. That would send the next agent to the wrong machine and omit a local-only branch from transfer instructions. | `git cat-file -t a656015` returned `commit`; `git show --stat a656015` resolved the 528-line document; `git branch -vv` listed the local branch. | The handoff is the canonical cross-computer state and must distinguish present local-only work from unavailable history. | Record the branch as present locally, not pushed or merged, and include it in the transfer/push warning without recreating its content. | Final handoff diff/check and post-commit branch inventory. |
| PH2REV-003 | P3 | Resolved | `c8271a1` | `docs/SESSION_HANDOFF.md:524`, `docs/SESSION_HANDOFF.md:734`, `docs/ACTION_PLAN_2026-08-02.md:163` | The implementation handoff called a required-object presence check an “EXACT MATCH” and attributed the already-current operator schema to normal owner use even though the recorded database-size/row-count drift also allowed a different restored database or machine profile. | The implementation itself explicitly disclosed that table column types and constraints were not compared byte-for-byte; Git and SQLite state establish that the schema is currently compatible, not what historical action made it so. | Operational records must separate measurement from inference. “Exact” and an unsupported causal claim can cause future operators to over-trust the verification or misread database provenance. | Describe the result as a compatibility match: required tables/columns are present and named index/trigger definitions match; retain the remaining table-definition limitation and mark the source of prior migration as unknown. | Final action-plan and handoff text state the observed result and unresolved provenance separately. |

No P0 or P1 issue was found, and no issue remains open.

## Validation and conclusion

The material regression was first run red on Claude's exact implementation
tree: the same-named weakened index and no-op trigger produced
`SchemaVerificationResult(matches=True)`. It passed after the correction and
reported both object names in the new mismatch fields. The corrected focused
run covered schema verification/migration, runtime artifact ignores, the real
CLI parser/dispatch, execution characterization, and direct/transitive ML
import boundaries: **81 passed in 21.74 seconds**. A corrected read-only run
against `data/trading_assistant.db` reported no missing or mismatched objects.

The first full-suite invocation was externally terminated by the command
runner's 120-second limit and produced no valid test result. The clean retry
on Python 3.13.14 passed **2,441 tests, 1 skipped, 25 warnings in 316.46
seconds**. `compileall` and `git diff --check` were clean. Warnings were the
same non-failing third-party deprecations recorded in prior runs.

Final disposition: **accepted after correction**. Claude's implementation is
an honest **8.5/10** before review correction and **9.5/10** on the corrected
tree. The scope discipline, read-only default, opt-in migration path,
pre-migration preservation tests, artifact-ignore coverage, and document
reconciliation were strong. The one material miss was narrow but important:
the operational verifier treated safety-object names as proof of their
definitions. No execution-kernel, policy, broker, scheduler, evidence epoch,
or live-authority behavior changed.

## Third-round confirmation (Claude, 2026-08-03)

Every review claim was independently re-verified before acceptance, on the
exact commits named, per `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`.

### Commit dispositions (review range `c8271a1..8278510`)

| Commit | Scope | Disposition |
|---|---|---|
| `36c69d3` | PH2REV-001 correction, mismatch detection, review report | Accepted, no issue found |
| `e3a5b9a` | Reviewed handoff | Accepted after Codex's own `35fc2dd` correction (its "LOCAL ONLY, NOT PUSHED" claim was already stale when committed — the same staleness class as historical `1cdff99`, independently observed by Claude via `git ls-remote` before `35fc2dd` landed) |
| `35fc2dd` | Handoff push-state correction | Accepted, no issue found |
| `8278510` | Merge PR #118 | Accepted: merge tree verified byte-identical to `35fc2dd` (`git diff --stat` empty); no conflict-resolution delta |

### Verification evidence

- **PH2REV-001 red-proof reproduced on the exact implementation snapshot**:
  in a separate worktree at `34ce463`, Codex's
  `test_same_named_weakened_index_and_trigger_are_detected` failed with
  `SchemaVerificationResult(matches=True, ...)` on a database whose
  active-epoch index had lost UNIQUE and whose broker-order trigger was a
  no-op — the exact reported fail-open, for the exact reported reason.
- **Reverse-mutation**: removing `mismatched_indexes`/`mismatched_triggers`
  from the corrected `matches` computation was detected by the same test;
  restored, all 13 schema tests green. The correction is load-bearing in
  both directions.
- **P2 severity accepted**: a schema verifier intended to run before
  evidence operations reported success while uniqueness and relationship
  enforcement were absent; that is a meaningful fail-open in a fail-closed
  tool, not a documentation nit. The implementation's own "honest limits"
  note had flagged byte-level table definitions but did not extend the
  concern to index/trigger definitions — the miss was real.
- **PH2REV-002 reproduced**: `git cat-file -t a656015` returns `commit`;
  local branch `codex/ai-strategy-tool-doc-v2-20260802` resolves to it with
  the 528-line strategy-tool document. The "absent from this computer"
  claim (carried forward from earlier handoffs without re-measurement) was
  false. Accepted.
- **PH2REV-003 accepted**: the corrected action-plan and handoff text
  separate the measurement (compatibility match: required tables/columns
  present, named index/trigger definitions equal) from the unresolved
  provenance of the operator database's current state.
- **Validation on the merged tree `8278510`** (byte-identical to
  `35fc2dd`), Python 3.13.14: full suite **2,441 passed, 1 skipped,
  25 warnings in 341.77s**; schema-verification suite 13 passed;
  compileall clean; `git diff --check` clean; worktree clean.

### Residual boundary, documented for the next round

`verify-db-schema --apply` creates missing objects (idempotent
`CREATE ... IF NOT EXISTS` plus column migrations) but cannot repair a
same-named MISMATCHED index or trigger — SQLite's `IF NOT EXISTS` skips an
existing weaker object, so after `--apply` verification still fails and
reports the object in `mismatched_*`. This is the correct fail-closed
behavior (surfacing, not silently dropping/recreating enforcement objects
on an operator database), and the CLI help's "creates any missing" wording
makes no repair claim; recorded here so the boundary is an explicit
decision rather than an accident. Repairing a mismatched object remains a
deliberate operator action.

### Assessment of the review

**9/10.** The review found a real P2 fail-open in the exact tool whose job
is fail-closed verification, proved it red on the implementer's snapshot
before fixing it, corrected it minimally (name -> normalized-definition
comparison; no contract churn), and re-ran full validation. Both P3
documentation findings were evidence-backed and their corrections are
precise. The single slip — committing a handoff that called the branch
LOCAL ONLY moments before/after pushing it — repeated a documented
historical staleness class, and was self-corrected in `35fc2dd` within
minutes.

Phase 2 hygiene is genuinely complete against its scope (AP-1, AP-2, AP-4)
and merged at `8278510`. The next milestone is GR-1D (action-plan Phase 3),
which requires the owner's explicit go-ahead.
