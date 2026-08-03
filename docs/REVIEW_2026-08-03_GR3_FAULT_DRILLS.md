# Independent review — GR-3 fault injection and adversarial drills

Date: 2026-08-03

Reviewer: Codex

Implementation branch: `user/claude/gr-3-fault-drills-20260803`

Implementation commit: `4c395d7`

Implementation tip: `61e0314`

Base: `d5400cc`

Review branch: `codex/review-gr3-fault-drills-20260803`

## Final disposition

**Accepted after correction.** GR-3 now meets archived plan section 8: the
runner executes the complete fault inventory, every mandated fault has
behavioral coverage and applicable no-partial-state assertions, reports are
written atomically, and promotion-drill rows can only enter an active paper
evidence epoch when the exact clean runtime commit matches that epoch's
lineage. F4 now produces the required durable critical alert as well as the
kill switch, and F3 includes a real restart from the broker-ambiguous
`submitting` state without resubmission.

Claude's submitted implementation is **7/10**. The eleven-fault organization,
real temporary SQLite stores, scripted broker boundary, rollback exercise,
inventory mapping, runbook table, and refusal/state assertions are strong.
The submitted operational runner nevertheless had material fail-open evidence
paths, and two plan rows were described more strongly than they were tested.
The corrected tree is **9.5/10**: the remaining limitation is that the disk-
full drill injects the SQLite error at a statement boundary rather than
physically exhausting a filesystem, which is now stated honestly.

## Exact scope and commit dispositions

Review range: `d5400cc..61e0314`.

| Commit | Disposition | Evidence |
|---|---|---|
| `4c395d7` | Accepted after GR3REV-001 through GR3REV-005 corrections | Implements the matrix, runner, status, and runbook. Core test design is useful, but active-epoch lineage, pytest-result interpretation, F3/F4 completeness, and artifact persistence required correction. |
| `9c466f6` | Accepted after GR3REV-006 handoff replacement | Correctly says GR-3 awaits review, but edits an already stale handoff whose canonical Git section still named pre-PR-#126 main and the former review branch. |
| `61e0314` | Accepted after GR3REV-006 handoff replacement | Correctly records that Claude's branch was pushed; the surrounding stale topology and next-action state still required replacement. |

No merge commit is in this review range. Claude's branch was pushed but not
merged when review started.

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR3REV-001 | P2 | Resolved | `4c395d7` | `scripts/run_fault_drill.py::record_drills` | Active-epoch rows inherited the epoch's stored commit without proving the drill report ran from that commit. Dirty (`unknown`) or newer code could therefore be recorded as passing promotion evidence under an older frozen lineage. | A fake active epoch bound to `a…a` accepted both `code_commit=unknown` and `b…b`; the uncorrected function called `record_operational_drill` instead of refusing. Both red cases were reproduced. | Evidence epochs may pool only identical immutable lineage. False commit attribution can make a promotion gate appear satisfied by code that the epoch never ran. | Before any active-epoch row, require a non-unknown report commit exactly equal to `epoch.lineage.code_commit`; verification-only rows remain allowed without an epoch. | Two red-to-green mismatch/unknown tests plus a matching-lineage success test proving all three supported drill types still record. |
| GR3REV-002 | P2 | Resolved | `4c395d7` | `scripts/run_fault_drill.py::_run_fault_matrix` | JUnit `<skipped>` cases were counted as passed, and a nonzero pytest exit with all collected cases shown as passing was ignored. The command could certify an unexecuted fault or a session/teardown failure. | Synthetic JUnit reproduced a skipped case returning `passed=True`; a synthetic exit 1 with an all-pass XML produced no exception. Both tests failed on the submitted tree. | The definition of done requires the whole matrix to run. A skipped or abnormally terminated drill is unavailable, never passed. | Skips are non-passing; exit 1 is accepted only when JUnit contains a corresponding non-passing case so failed drills remain recordable; unexplained exit 1 and pytest exit 2+ abort. | Both regressions green; end-to-end runner reports 11 fault IDs, no unmapped tests, and overall pass. |
| GR3REV-003 | P2 | Resolved | `4c395d7` | F4 in `tests/faults/test_fault_matrix.py`; manual/startup/stream reconciliation | F4 asserted only a kill switch. The archived row explicitly requires a critical alert, and the runtime wrote no `operational_alerts` row. | Strengthened F4 failed red with `len(alerts) == 0` after the mismatch. Generalized search found the same gap in manual direct/replacement and startup/stream identity-halt paths. | A halt hidden only in system state cannot be delivered by GR-5 and does not meet the incident-notification contract. The halt and alert must also not disagree after a partial write. | Added `AssistantStore.activate_reconciliation_halt()`, atomically persisting the kill switch and deduplicated critical `broker_reconciliation` alert; routed all reconciliation identity/malformed-intent halt paths through it. | F4 red-to-green; transaction-injection test proves an alert insert failure rolls back the kill-switch write too; characterization/replacement/transaction focused suites pass. |
| GR3REV-004 | P2 | Resolved | `4c395d7` | F3/F5/F7 in `tests/faults/test_fault_matrix.py` | F3's “process killed mid-submission” inventory contained pre-broker `validating` and already-claimed `reconciling` recovery, but never a restart from `submitting`, the state written immediately before broker contact. F5/F7 also omitted some reservation/order no-partial-state assertions while docs claimed every row asserted them. | Source comparison to archived rows and execution status semantics; `SUBMITTING` is explicitly excluded from pre-broker stale-claim recovery because an order may exist. | A helper-level recovery test does not prove restart handling avoids a duplicate broker submission in the ambiguous state named by the fault. Missing state assertions weaken the definition-of-done claim. | Added a startup reconciler drill from `submitting` that adopts the broker order with zero submit calls and a retained reservation; added missing reservation/order/integrity assertions to F5/F7; updated the F3 inventory. | Corrected matrix and focused suites pass; F3 asserts one lookup, zero submit, accepted projection, retained reservation, one order, and referential integrity. |
| GR3REV-005 | P2 | Resolved | `4c395d7` | `scripts/run_fault_drill.py::main` | The supposedly immutable report used direct `Path.write_text`; a crash/write failure could expose a partial JSON artifact at a path the next run then refuses to overwrite. | Source inspection against the repository's established atomic JSON writers and the persisted-artifact rules in `CLAUDE.md`. | Immutable evidence must be all-or-nothing; a truncated artifact is neither verifiable evidence nor safely retryable under a no-overwrite policy. | Write/flush/fsync to a same-directory temporary file, then publish with an atomic no-overwrite hard link and clean the temporary name on every failure. | Injected publication failure leaves neither destination nor temporary file; end-to-end report parses and carries its hash. |
| GR3REV-006 | P3 | Resolved | `4c395d7`, `9c466f6`, `61e0314` | status/runbook/handoff | Documentation called the hand-built exception “genuine disk full,” said each row was one test, omitted the runner/alert corrections, and retained stale Git/next-action state in the handoff. | The injector explicitly raises `sqlite3.OperationalError`; F3/F7 map to multiple tests; handoff canonical state still named `16e0451` and the old active branch after PR #126. | Operational records must distinguish a statement-level injected error from physical filesystem exhaustion and must be safe to follow on another computer. | Corrected status/runbook wording, recorded 11 fault IDs/14 tests and every review correction, updated the action plan, and replaced the handoff with verified topology. | Cross-document stale-text search, Git graph/remote verification, and diff checks. |

No P0 or P1 finding was found. No live broker, funded account, scheduler,
operator database, or formal evidence epoch was used during review.

## Behavioral assessment

The corrected drill matrix covers:

1. timeout after submit with idempotency lookup and no resubmit;
2. duplicate broker order identity with one projected order;
3. pre-broker stale claim, dead reconciliation, and actual `submitting`
   restart recovery;
4. unexpected/mismatched broker identity with atomic critical alert + halt;
5. per-ticker halt refusal without blocking an unrelated risk-reducing sell;
6. share-count mismatch after a corporate-action-shaped snapshot change;
7. stale and future-skewed quote refusal;
8. mid-transaction journal error rollback and later reconciliation repair;
9. mid-flight kill switch with no new submission and clean reconciliation;
10. test database isolation; and
11. brokerage-credential isolation.

The disk-full case is a controlled statement-level error against a real
SQLite transaction. It proves rollback ordering and application behavior but
does not test OS/filesystem behavior under actual capacity exhaustion. That
limitation does not block GR-3's software fault-injection definition of done.

## Validation

```text
submitted focused matrix: 13 passed in 17.56s
review red runner tests: 4 failed as expected
review red F4 alert test: 1 failed as expected (zero alerts)
corrected focused runner/F3/F4: 6 passed in 1.91s
corrected combined focused suite: 110 passed in 36.40s
corrected end-to-end CLI: passed; 11 fault IDs; 0 unmapped tests
full suite: 2,506 passed, 1 skipped, 25 warnings in 423.31s
post-full runner regression: 7 passed in 13.69s; CLI 11/11, 0 unmapped
Python: 3.13.14
compileall: clean
git diff --check: clean
```

The final handoff records final-tree validation counts and the correction
commit. The command-line report used during the dirty review correctly
reported `code_commit=unknown` and was deleted after inspection.

## Next step

GR-3 is complete after this review. Phase 4 remains active, but GR-5 alert
delivery is blocked on the owner's channel choice; it is the remaining
producer for `alert_delivery`. GR-2 remains the action plan's Phase 4
ride-along. This review does not authorize choosing a channel, implementing a
different milestone, deploying scheduled tasks, starting an evidence epoch,
or enabling live trading.
