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
