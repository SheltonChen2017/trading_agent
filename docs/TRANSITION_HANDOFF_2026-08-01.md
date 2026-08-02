# Trading Agent transition handoff — 2026-08-01

This file is the restart point for a new Codex/Claude session on another
computer. Verify the repository and external state before acting; timestamps,
branches, scheduled tasks, credentials, and the live database may have changed
since this was written.

## 1. Repository state at handoff

- Recorded at: `2026-08-01T21:56:44-07:00`
- Repository: `trading_agent`
- Current local branch: `codex/isolate-pytest-live-db`
- Current commit: `ce03386 Isolate pytest from the operator database`
- Worktree was clean before this handoff file was added.
- `origin/main` and local `main`: `d0fee8c`
- PR #92 is merged into `main` at `d0fee8c`.
- Branch `codex/isolate-pytest-live-db` tracks
  `origin/codex/isolate-pytest-live-db`; both pointed to `ce03386` when this
  file was written. The isolation fix was not merged into `main` yet. Confirm
  remote and PR state on the new computer.

Useful first commands:

```powershell
git status --short --branch
git fetch origin
git log --oneline --decorate -12
git branch -vv
```

Do not discard a dirty worktree or reset a branch merely to reproduce this
snapshot. Inspect and preserve any newer work first.

## 2. What has been completed and merged

The ML software track selected for the volatility-first system is substantially
complete:

- ML-LR-0: shared acceptance and experiment contracts
- ML-LR-1: point-in-time lineage and historical-universe contracts
- ML-LR-2: durable experiment orchestration
- ML-LR-3: per-security and portfolio-volatility software paths; real portfolio
  evidence remains underfilled
- ML-LR-4: earnings-gap and filing-context software; real confirmation remains
  externally data-gated
- ML-LR-6: shadow runtime and evidence epochs
- ML-LR-7: monitoring and promotion dossier
- ML-LR-8: read-only presentation
- ML full-system infrastructure: normalized portfolio collection, execution
  telemetry, evidence supervision, Windows installers, and operational checks

Important qualification: ML-LR-5 was deliberately skipped as optional for the
volatility-first path. It is inaccurate to say literally every milestone from
LR-0 through LR-8 was implemented.

Recent merged review work:

- PR #88: Claude review fixes
- PR #89: exact broker-decimal portfolio contract
- PR #90: telemetry failure taxonomy
- PR #91: scheduled-task installer honesty
- PR #92: Codex review corrections
  - deterministic first-party transitive ML import graph
  - relative and literal dynamic import resolution
  - telemetry failure class exposed in materialized ML records
  - exact SQLite text projections and migration/backfill
  - internal exact-numeric consistency validation
  - task replacement errors cannot be hidden by an older task of the same name
  - unelevated `-WhatIf` works for both Windows installers

PR #92 commit: `9b19613 Fix ML evidence review regressions`.

Validation for PR #92:

```text
2322 passed, 1 skipped, 25 warnings
```

The warnings were third-party deprecations from `websockets` and `joblib`, not
test failures.

## 3. Current unmerged isolation fix

Commit `ce03386` adds:

- `tests/conftest.py`: forces every pytest process to use a temporary database
  during collection and execution, then removes it at process exit.
- `tests/test_test_isolation.py`: proves the pytest default database is not the
  operator database.

Why it is necessary: `tests/test_personal_assistant_ui.py` imports
`scripts/personal_assistant_ui.py` during pytest collection. Streamlit bare mode
executes the script body, calls `AssistantStore()` with no explicit path, builds
the sample manual portfolio, and previously wrote briefing rows into
`data/trading_assistant.db`.

Direct verification after the fix:

```text
UI/isolation tests: 32 passed
live portfolio_equity_snapshots before: 78
live portfolio_equity_snapshots after:  78

Full suite: 2323 passed, 1 skipped, 25 warnings
live portfolio_equity_snapshots after full suite: 78
```

Next session should review `ce03386`, push it, and open/merge a focused PR if
that has not already happened.

## 4. Live database state and contamination diagnosis

Database inspected read-only:

```text
data/trading_assistant.db
portfolio_equity_snapshots:   78
portfolio_position_snapshots: 0
portfolio_capture_sessions:   0
paper_account_observations:   0
```

All 78 equity rows had the same sample/test signature:

```text
account_key:       manual:manual
total_equity_text: 28025
cash_text:         5000
source:            manual (inside payload_json)
```

They were created across July 30 through August 2 by repeated Streamlit module
imports during reviewer/test runs. They are briefing-path rows, not immutable
paper-evidence rows, so no evidence epoch was contaminated. The same import
also calls `save_decision_packet`; the database contained 209 decision packets
when inspected, but those rows were not individually classified. Do not delete
either table without explicit owner approval and a scoped backup/query.

At inspection time:

- no Streamlit or personal-assistant runtime was running;
- no `TradingAgent-*` scheduled task existed;
- `paper_account_observations` still contained zero rows.

External state must be rechecked on the new computer.

## 5. Remaining ML blockers

The remaining blockers are mostly not implementation work:

1. **Historical index membership purchase**
   - No authoritative point-in-time historical universe source has been
     supplied.
   - Databento does not supply this dataset.
   - Real builds must keep `point_in_time_data=false`.
   - Results remain exploratory and promotion-blocked.
   - Owner decision required: fund an authoritative source, or formally adopt
     a fixed survivorship-biased universe and cap every claim made from it.
   - A later authoritative source can start a new evidence epoch; old biased
     evidence remains permanently capped, not the entire future system.

2. **Calendar time / observations**
   - Shadow evidence, calibration observations, and real portfolio targets do
     not yet exist in sufficient quantity.

3. **Owner authorization**
   - ML-LR-9 and ML-LR-10 remain deliberately blocked until explicitly
     authorized after a real dossier and sufficient evidence.

4. **Execution-quality data**
   - ML-LR-11 remains deferred because the required real order lifecycle and
     execution dataset does not exist yet.

5. **Other real confirmation data**
   - Earnings/filing research still needs authoritative event data/provider
     inputs if that task is pursued. This is separate from the volatility-first
     shadow collector.

## 6. Evidence epoch correction and A/B decision

Do not start evidence collection from a checkout whose `HEAD` moves with normal
development. Paper evidence recomputes lineage from the clean current Git
commit, mandate, policy, strategy/model identifiers, and broker account. A
commit mismatch fails the scheduled observation and requires a new epoch.
Different epochs must never be pooled.

Two options were discussed:

### Option A — finish GR before collection

Complete GR-0 through GR-6, freeze the runtime, deploy, and then start evidence
collection. This is simpler but loses prospective collection time.

### Option B — pinned operational deployment while main develops

Recommended, but only with stronger isolation than “two checkouts write one
SQLite database.” WAL and a 30-second busy timeout help lock contention; they
do not prove semantic or schema compatibility across changing code versions.

Required topology:

```text
pinned operational worktree + pinned venv
    -> operational SQLite database
    -> Alpaca paper account
    -> operational UI, reconciliation, monitoring, observations, ML shadow

main development worktree
    -> separate development/test database
    -> no paper execution
    -> no writes to the operational database
```

The pinned worktree must be the complete operational runtime, not merely a
collector. If changing main submits paper orders while pinned code records the
results, the evidence epoch's `code_commit` does not truthfully identify the
system that generated the behavior.

Choose Option B only if this operational discipline is acceptable. Otherwise
choose A; A is safer than an informal/shared-write version of B.

## 7. Option B deployment checklist

Do not start an epoch until all of these are satisfied:

1. Merge the pytest database-isolation fix.
2. Create a detached/pinned deployment worktree at a reviewed commit.
3. Create a dedicated virtual environment for that worktree and install the
   pinned requirements.
4. Place policy, mandate, shadow config, and model artifacts at immutable,
   fingerprinted paths used only by the operational deployment.
5. Give the pinned runtime exclusive access to the operational SQLite file.
6. Point main and tests at separate databases through
   `TRADING_ASSISTANT_DB`/explicit CLI paths.
7. Back up the operational database and verify restore before deployment.
8. Run representative concurrent operational commands against a copied
   database and prove no lost writes or unresolved lock errors.
9. During an elevated Windows session, install both task sets using the pinned
   values for `-RepositoryPath`, `-PythonPath`, database, config, and artifact
   paths.
10. Run `scripts/verify_windows_evidence_tasks.ps1`.
11. Confirm each task's action, principal, logon type, state, and
    `LastTaskResult`.
12. Prove S4U tasks can see required credentials and import the Python standard
    library from the pinned interpreter.
13. Manually run one operational cycle, supervisor cycle, and safe shadow
    command; confirm heartbeats and alerts.
14. Start paper and ML evidence epochs from the pinned runtime.
15. Confirm the next scheduled observation/prediction succeeds before treating
    the clock as started.

Roll forward deliberately: stop tasks, checkpoint/backup SQLite, close active
epochs, update the pinned code and venv, run migrations and verification, then
start new epochs and resume tasks.

## 8. General Readiness track

`docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md` defines GR-0 through GR-6:

- GR-0 readiness taxonomy
- GR-1 execution-kernel structural split
- GR-2 risk-check consolidation
- GR-3 fault injection and operational drills
- GR-4 data-layer resilience and honesty
- GR-5 delivered operator alerting
- GR-6 recovery, secrets, and portability

GR-0 through GR-4 are predominantly unblocked code work. The claim that every
part of GR-0 through GR-6 is “pure code” is too broad: GR-5 requires a real
owner-visible delivery channel and receipt test; GR-6 requires off-machine
backup/restore, credential rotation, and second-machine recovery exercises.

Recommended sequence after the pinned operational deployment is proven:

```text
GR-0 -> GR-1 -> GR-2 -> GR-3 -> GR-4 -> GR-5 -> GR-6
```

Follow the plan's delivery rule: one milestone per branch and independent
review before continuing.

## 9. Decisions still required from the owner

Ask explicitly before proceeding:

1. Is there budget for an authoritative historical index-membership source?
2. Approve Option B with strict operational/database isolation, or choose A?
3. Approve deletion/cleanup of the 78 sample equity rows and any positively
   identified test decision packets, after backup?
4. When is the elevated Windows deployment window available?
5. Which owner-visible alert channel should GR-5 implement and verify?

## 10. Suggested prompt for the next session

> Read `docs/TRANSITION_HANDOFF_2026-08-01.md` completely. Then verify the
> current Git/remote state, inspect commit `ce03386` and whether it was merged,
> recheck scheduled tasks and the live database read-only, and summarize any
> drift from the handoff. Do not start an evidence epoch, install tasks, delete
> database rows, or begin GR work until the listed owner decisions and Option B
> deployment gates are resolved.
