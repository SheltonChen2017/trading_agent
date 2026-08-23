# Counter-review — Claude SEP-3 alert-ownership review

Reviewer: Codex, 2026-08-23

Reviewed remote branch: `origin/user/claude/review-sep3-alertown-20260823`

Implementation snapshot reviewed by Claude:
`4bea7f9defa10b7599b4de2ff4c25b1b7c808bd2`

Claude review head: `dabf00f051007527820c14ea0fea404c2ac1a003`

Merge-base: `4bea7f9defa10b7599b4de2ff4c25b1b7c808bd2`

**Verdict: accepted after correction.** Claude's substantive acceptance of the
third SEP-3 dry run reproduces independently. No P0, P1, or P2 issue was found.
One P3 test-sensitivity gap in Claude's finding-ID guard is corrected by
`ee7d2ed784761d0e04d309a452f87f4ee1a9b2cc`.

## Ordered commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `d7c521d341ba1283aa3d39a6a11036aca1ae0c48` | **accepted after correction** | The expanded review globs and `CRSEP...` grammar are correct and the post-merge statement is honest. The permanent grammar test omitted a `CRSEP...` example; `ee7d2ed` pins that direction. |
| `effcddace82935113259654f84db71e795ad433b` | **accepted** | The review record gives all seven implementation commits dispositions, discloses the prior mixed-scope census error, and accurately reports the current blockers and non-authority scope. |
| `dabf00f051007527820c14ea0fea404c2ac1a003` | **accepted** | The independently rerun complete suite reproduces 4,552 passes and 25 known dependency warnings; the duration difference is environmental only. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CRSEP3A-001 | P3 | Resolved | `d7c521d` | `tests/test_active_document_consistency.py` | Claude added `CRSEP...` recognition to the guard, but the direct grammar test asserted only `SEP...` examples. A later deletion of the optional prefix could therefore escape the narrow unit test and rely only on current report/handoff coincidence. | Inspection of the submitted test showed no `CRSEP...` full-match assertion. | The guard exists specifically to retain counter-review findings; its dangerous prefix direction should be pinned directly rather than incidentally. | `ee7d2ed` adds `CRSEP3R2-001` to the permanent grammar examples. | With `(?:CR)?` temporarily removed, the focused test failed on that exact assertion; after restoration, the focused grammar and report/handoff guards passed 2/2. |

No open issue remains.

## Independent reproduction

The dry-run validator was executed from the final Claude tree and reproduced
the exact candidate `73acf482cf8d4c36c28b2d1745bd914ae08eb6a3`, 745
tracked paths, inventory SHA-256
`a985372c467d5841dd9a2d99dbda64e6e91d6e4c70a3d78e39d7b4e4cfdf9cfd`,
destination counts 501 trading assistant / 240 strategy research / 4 shared,
and test partitions 83 / 70 / 1 / 54. It independently reproduced all nine
dual-use stranded modules, 11 composition files, six Python crossing roots,
four non-assistant operator-store importers, pending governance ownership, and
`physical_extraction_authorized=false`.

The assistant-only `data.operational_alerts` assignment is honest. Product-
owned research code is forbidden from importing it, while the two research-
hosted composition runners remain explicit composition debt. The remaining
nine modules are imported by both products. No dynamic, relative, or transitive
bypass was accepted, and no review claim treats this valid dry run as physical
extraction readiness.

## Validation

- Focused SEP and active-document suites: **97 passed** in 345.27 seconds.
- CRSEP grammar/report guard after correction: **2 passed**; direct grammar
  rerun: **1 passed**.
- Dangerous-direction mutation: removing `CRSEP...` recognition produced the
  intended **1 failed** result; the restored implementation passed.
- Complete suite: **4,552 passed / 0 failed / 25 known warnings** in 1,066.28
  seconds on Python 3.13.14.
- `compileall` including `research/`: passed.
- All `architecture/*.json` files parsed successfully.
- Dry-run validator: passed and reproduced the exact inventory, partitions,
  blockers, and refusal state above.
- `git diff --check`: clean.

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, evidence epoch, or
`paper-epoch-006` state was accessed or changed.

## Next step

Proceed from the finalized counter-review tree to the earliest safe bounded
SEP-3 partition item. Physical repository creation, history rewrite,
operator-database movement, installed-task movement, and deployment remain
unauthorized. If the next dual-use-module decision requires new owner policy,
stop rather than choosing a cross-repository dependency or expanding the tiny
shared package silently.
