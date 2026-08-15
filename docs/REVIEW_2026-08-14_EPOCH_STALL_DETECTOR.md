# Codex independent review — epoch stall detector

Date: 2026-08-14
Reviewer: Codex
Base reviewed: `60027af` (current `main` / `origin/main`)
Submitted commit: `6aa7069`
Review branch: `codex/review-epoch-stall-detector-20260814`
Product/test correction: `4273de6`
Final disposition: **accepted after correction**

## Scope and method

This review covered the only commit added by Claude's feature branch,
`6aa7069`, file by file and through the complete cadence path: market-calendar
selection, epoch start and grace arithmetic, active-epoch lookup, read-only
SQLite opening, CLI exit status, operator wording, and the usage guide. The
review compared the model with the measured installed
`TradingAgent-Paper-PaperObservation` trigger rather than inferring the
schedule from source or market hours. Generalized searches covered the
existing paper-observation failure path, storage constructors and writers,
active-epoch constraints, scheduler documentation, and every new status.

Regression tests were written and run red against the submitted behavior
before corrections. The review also exercised a real temporary SQLite file
through the detector's read-only connection and made one read-only invocation
against the operator database. No database write, scheduler edit, broker
request, order, deployment, epoch transition, funded-account access, or live
trading action occurred.

## Commit-by-commit disposition

| Commit | Type | Disposition | Result |
|---|---|---|---|
| `6aa7069` | Claude implementation, tests, and usage text | **Accepted after correction** | The pure classifier, read-only CLI boundary, tail-miss definition, and five-state presentation are useful. The submitted scheduler model moved a fixed Windows trigger on early-close days, and the no-active-epoch result exited successfully. Five additional validation, evidence, and wording defects also required correction. |
| `4273de6` | Codex product/test correction | **Accepted** | Models a configurable fixed wall-clock trigger, makes unhealthy absence nonzero, validates public inputs, proves SQLite read-only behavior, and makes operational/status prose truthful. |

## Prioritized issue ledger

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| CODSTALL-001 | P2 | Closed | `assistant/epoch_cadence.py`, `scripts/check_epoch_cadence.py`, `HOW_TO_USE.md` | The submitted code derived capture time as market close plus 3.5 hours. The installed epoch-host task is a fixed 16:30 Pacific wall-clock trigger, so the Friday-after-Thanksgiving 13:00 Eastern close made the detector declare that session due three hours early and could manufacture a missing or stalled session. There was no way to pass a remeasured trigger. | Expected sessions now use a fixed local time and timezone. Defaults match the measured host; `--capture-time` and `--capture-timezone` let an operator supply a newly measured task without changing code. | The early-close and configurable-trigger tests failed on the submitted tree and pass after correction; the complete suite passes. |
| CODSTALL-002 | P2 | Closed | `assistant/epoch_cadence.py`, `scripts/check_epoch_cadence.py` | `NO_ACTIVE_EPOCH` had `report.ok == True`, so a scheduler or monitor received exit 0 when no epoch was collecting evidence. That made the most important absence look healthy. | Only `HEALTHY` and `NOT_DUE_YET` are successful states. No active epoch exits 1. | Classifier and CLI subprocess regressions failed before correction and pass after it. |
| CODSTALL-003 | P3 | Closed | `assistant/epoch_cadence.py` | `stall_threshold` accepted zero, negatives, booleans, and floats; zero produced the impossible explanation “last 0 expected sessions.” Negative grace and naive wall-clock inputs were also accepted at the public boundary. | Require a positive, non-boolean integer threshold, non-negative grace, and timezone-aware datetimes. | Invalid-boundary regressions failed before correction and pass after it. |
| CODSTALL-004 | P3 | Closed | `tests/test_epoch_cadence.py`, `scripts/check_epoch_cadence.py` | The submitted read-only test searched source text for `mode=ro`; dead text or a later writable connection would still pass, and the Windows URI path was not exercised. | Tests now open an actual temporary SQLite database, prove a write raises `sqlite3.OperationalError`, prove detector reads leave database bytes unchanged, and prove no WAL/SHM side files appear. | The behavioral read-only suite and full suite pass. |
| CODSTALL-005 | P3 | Closed | `HOW_TO_USE.md`, `assistant/epoch_cadence.py`, `tests/test_epoch_cadence.py` | The new prose said a refused paper observation lets the task report success and nothing crashes. The real command creates a critical alert, re-raises, and exits nonzero. This could send an operator looking for a silent-success failure mode that does not exist. | Wording now says the cadence detector complements the existing nonzero task result and critical alert by answering whether observations are accumulating. | Generalized trace of `command_paper_observation` plus focused prose assertions. |
| CODSTALL-006 | P3 | Closed | Action Plan, milestone record, Session Handoff | The feature commit did not update the project-required current records. The existing Action Plan and handoff also still called `7055142` current main although PR #220 had moved it to `60027af`. | This review adds the durable review, two-paragraph milestone, current feature row, corrected topology, and replacement handoff. | Active-document and directly affected post-record suite: 86 passed; staged diff checks are clean. |
| CODSTALL-007 | P3 | Closed | `assistant/epoch_cadence.py` | During the grace window an observation may already exist even though none is overdue. The submitted `NOT_DUE_YET` detail always claimed zero observations, contradicting its own recorded-session field. | The detail now distinguishes a genuinely empty new epoch from observations already recorded inside the current grace window. | The targeted test failed before correction; the corrected cadence module passes 24 tests. |

Issue total: **0 P0 / 0 P1 / 2 P2 / 5 P3; all closed; 0 open**.

## Verified design that was retained

- The cadence decision is a pure function; database access remains in the
  standalone adapter.
- Expected sessions begin at the active epoch's actual start and include only
  market sessions whose fixed task time plus grace has elapsed.
- A stall is a configurable consecutive-missing tail, not any historical gap;
  a recovered older gap remains `BEHIND`, not a current `STALLED` claim.
- Recorded sessions are preserved in the report, and the CLI exposes expected,
  recorded, missing, last-recorded, and tail counts.
- The detector is advisory and read-only. It does not repair evidence,
  restart tasks, change epochs, alter schedules, or enter an execution path.

## Validation

Authoritative environment: repository `.venv`, Python 3.13.14, Streamlit
1.60.0, Windows.

- Submitted focused suite: **17 passed**.
- Initial regression run: **4 failed / 16 passed**, exposing CODSTALL-001,
  CODSTALL-002, and CODSTALL-003 before correction.
- Corrected cadence module: **24 passed**.
- Corrected cadence plus paper-evidence, schema-verification, and ML import
  boundaries: **59 passed** before the final message regression was added;
  all remain covered by the complete run.
- Full exact corrected tree in the pinned `.venv`: **3,783 passed / 0 failed /
  25 known dependency warnings** in 900.86 seconds.
- Post-record active-document and directly affected suite: **86 passed**.
- Repository `compileall`: clean. `git diff --check`: clean.
- Environment note: a first full command accidentally used the user Python's
  Streamlit 1.52.2 instead of the repository-pinned 1.60.0 and produced 14 UI
  API failures (`AppTest.segmented_control` is absent there). The three
  affected files passed **40/40** in `.venv`, and the authoritative complete
  `.venv` run above passed. A failed pip replacement rolled the shared
  environment back to 1.52.2; no shared package change was retained.

The full authoritative run occurred on one settled product tree. No source
or documentation was edited concurrently with it.

## Live read-only observation and boundaries

The CLI was invoked once against the operator database through SQLite
`mode=ro` and reported active epoch-005 as `NOT_DUE_YET` at the observation
time. That was a point-in-time read, not deployment proof and not a promise
about the next scheduled capture. The installed trigger had previously been
measured at 16:30 Pacific; if it is reinstalled or changed, operators must
remeasure it and pass the matching CLI options.

The frozen operational runtime remains `752d3b7`. The owner's 2026-08-14
decision to leave epoch-005 unchanged for 60 days is unaffected. This feature
has not been deployed or scheduled, and this review does not authorize merge,
push, deployment, scheduler installation, database mutation, epoch roll,
funded-account access, or live trading.
