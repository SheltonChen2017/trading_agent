# Counter-review — SEP-2 completion review

Reviewer: Codex, 2026-08-22
Submitted review: `origin/user/claude/review-sep2-completion-20260822`
Exact submitted head: `e642469df7030deb1a36171f43a85e68e1fd82d1`
Implementation/base and merge-base: `c7087714be8a976a401472f1710e4faa5e1d55d6`

## Verdict

**Accepted after correction.** Claude correctly accepted SEP-2 against its
written definition and correctly separated that milestone from physical
extraction. No P0, P1, or P2 issue was found. One P3 evidence-linkage defect
was confirmed and corrected.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `a464b40c19f49af549589ec070b0b9b3feec51bd` | **accepted after correction** | The manifest-to-guard name linkage is useful provenance, but it did not invoke the named evidence and therefore did not support its stronger claim. `CRSEP2C-001` closes the gap. |
| `e642469df7030deb1a36171f43a85e68e1fd82d1` | **accepted** | The review record accurately dispositions the six implementation commits, reconciles the residual counts, records the limitation, and corrects the unsupported owner-date attribution. |

## P0–P3 ledger

| ID | Priority | Status | Location | Finding | Correction and verification |
|---|---:|---|---|---|---|
| CRSEP2C-001 | P3 | closed | `tests/test_project_separation_entrypoints.py`; `architecture/entry_points.json` | Claude's note said the completion claim could not outlive its evidence, but the certificate only checked that named test functions existed. Claude's own untested-surface disclosure correctly noted that the functions could remain present without meaningful enforcement. The durable note therefore overstated what the code proved. | The certificate now resolves and directly invokes every named fixture-free guard. It also refuses a named guard that acquires pytest fixtures and therefore cannot be run by the certificate. A mutation adding a failing invariant to `test_every_script_is_classified_exactly_once` made the certificate itself fail; the restored focused module passed 23/23. The note now describes the actual mechanism. |

No lower-priority finding is being hidden as an extraction blocker: a test
body can always be maliciously replaced by a no-op, but direct invocation
closes the concrete skip/name-only gap without pretending that source-code
intent is mechanically provable.

## Independent verification

- The exact submitted remote was fetched and remained at `e642469d`.
- The residual inventory reproduces: 11 composition files, six Python
  crossing roots, and four non-assistant operator-database importers.
- The SEP-2 product-boundary guards still report zero direct product crossings
  and zero allowed authority-to-research paths.
- Claude's correction to the owner-decision date is historically accurate at
  its review snapshot. The owner subsequently selected the two-repository plus
  tiny shared-contracts topology; that later decision belongs to SEP-3.
- No provider, credential, licensed row, broker, operator database, installed
  task, deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed.

SEP-2 remains accepted and complete. This counter-review authorizes no physical
move; the next bounded work is the reviewed SEP-3 dry-run extraction artifact.
