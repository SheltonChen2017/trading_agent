# Counter-review — SEP-2 entry-point classification

Reviewer: Codex, 2026-08-22

Reviewed branch: `origin/user/claude/review-sep2-entrypoints-20260822`

Reviewed head: `cd11beaf4dbf40a852928944ef11b23849fd3493`

Implementation head reviewed by Claude: `eb2e22f19ebd4fa817583922b0a8378e18bd5f47`

**Verdict: accepted after correction. No P0/P1; one P2 corrected.**

## Exact range and commit dispositions

The fetched Claude head was stable before review. Its merge-base with the
submitted Codex head was exactly `eb2e22f19ebd4fa817583922b0a8378e18bd5f47`.

| Commit | Disposition | Reason |
|---|---|---|
| `fc89903cdc0463342ac2ade28791b114cbf7fca1` — Close SEP-2 review findings in the entry-point guards | **Accepted after correction** | Claude correctly closed the root-granularity, recursive-inventory, and root-normalization defects. Its new exact-module scanner still missed parent-package `from` imports; CRSEP2-001 closes that final fail-open form. |
| `cd11beaf4dbf40a852928944ef11b23849fd3493` — Record the independent review of the SEP-2 classification tranche | **Accepted after correction** | The report is complete and its reproduced counts are consistent, but its statement that only assistant-hosted entry points can import authority modules was too broad until CRSEP2-001. Historical review prose remains unchanged; this record supplies the dated correction. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CRSEP2-001 | P2 | Closed | `fc89903` | `tests/test_project_separation_entrypoints.py::_imported_modules` | `from assistant import execution_service` imports the authority child module, but the scanner retained only `assistant`; the new authority guard and licensed-surface guard therefore remained green. | The mutation was added to research-hosted `scripts/run_qc_stage0.py`; all 9 entry-point guards passed. | This is the same fail-open authority direction that SEP2-001 was intended to close, and it also permits `from research import acer` to evade the licensed-surface check. | Expand every absolute `ImportFrom` into both its parent and imported child module names; add a regression test for authority and licensed children. | Mutation: 9/9 passed before correction. Corrected focused boundary set: 26/26 passed. |

Resolved findings are retained above. No open P0-P3 item blocks the next
bounded SEP-2 tranche. Claude's recorded SEP2-006 and SEP2-007 remain planned
separation debt rather than defects in the reviewed submission.

## Independent checks

- The remote head, merge-base, and ordered two-commit range were reproduced.
- Claude's recursive 75-file script inventory and 16-file data inventory
  remain exact on the counter-review tree.
- The direct authority mutation used by Claude fails after its correction;
  the parent-package spelling above independently exposed the remaining hole.
- The corrected scanner also closes the equivalent licensed-surface spelling.
- Focused entry-point, project-boundary, and ML import-boundary tests pass
  **26/26** after correction.
- No provider, credential, licensed row, broker, operator database, scheduled
  task, deployment, backtest, result, research look, or evidence epoch was
  accessed or changed.

The complete suite and compilation are run once on the final descendant tree
that also contains the owner-directed next SEP-2 tranche. That avoids treating
an earlier test run as validation of the final pushed state.

## Remaining scope

SEP-2 is not complete. The next tranche must replace the nine-item shared
provider debt with explicit product ownership or justified provider-neutral
services, reduce composition debt without broadening the ledger, preserve
compatibility, and address the recorded lazy operational reach where a narrow
neutral extraction is available.
