# Code Review and Session Handoff Process

Status: required development workflow for Codex, Claude, and future agents

Prepared: 2026-08-02

## 1. Purpose

This document defines the repository's standard process for independently
reviewing an implementation produced by another agent or developer.

A review is not complete when the code merely passes tests. It is complete
only when:

1. the exact implementation snapshot was identified;
2. its behavior, compatibility, architecture, and safety properties were
   independently examined;
3. confirmed defects were reproduced and corrected where practical;
4. focused and full validation passed on the corrected tree;
5. review corrections were committed separately; and
6. `docs/SESSION_HANDOFF.md` was updated to reflect the new durable state.

The session handoff is part of the review deliverable, not optional cleanup.
It is read by both Codex and Claude and may be the only reliable context after
a machine change, session reset, or context compaction.

## 2. Core rule

> Every completed independent code review must update
> `docs/SESSION_HANDOFF.md` before the review is handed back to the owner.

The update must describe the final reviewed tree, not the implementer's
original claims. If the review changes code, tests, documentation, milestone
status, branch topology, or the recommended next step, the handoff must record
those changes.

For a small review, updating the affected sections may be sufficient. Replace
the handoff completely when its repository snapshot, active milestone, branch
instructions, machine-transfer information, or recommended next action has
become materially stale.

## 3. Roles

### Implementer

The implementer:

- works on a dedicated branch;
- states the exact milestone and scope;
- preserves public contracts and safety boundaries;
- adds or updates appropriate tests;
- runs focused and full validation;
- commits a stable snapshot; and
- stops for independent review.

The implementer's test report is evidence to verify, not proof of acceptance.

### Reviewer

The reviewer:

- starts from the implementer's exact commit;
- creates a separate review branch;
- examines the code independently rather than accepting the commit message;
- reproduces suspected defects with focused tests;
- applies corrections within the authorized scope;
- reruns validation on the final tree;
- gives a genuine quality assessment;
- commits corrections separately from the implementation; and
- updates and commits `docs/SESSION_HANDOFF.md`.

The same agent should not describe its own implementation as independently
reviewed.

## 4. Review sequence

### Step 1 — establish the exact snapshot

Before reading the diff, record:

```powershell
git status --short --branch
git log --all -15 --oneline --decorate
git branch -vv
```

Confirm:

- implementation branch;
- implementation commit;
- base commit;
- whether the branch is pushed;
- whether the worktree is clean; and
- whether another process is still editing or testing the shared worktree.

Do not review a moving, dirty implementation unless the owner explicitly asks
for an in-progress review. Wait for a stable commit when the implementer is
still working.

### Step 2 — isolate the review

Create a dedicated review branch from the exact implementation commit:

```powershell
git switch -c codex/review-<milestone>-<date> <implementation-commit>
```

Use the appropriate agent prefix if the reviewer is not Codex. Do not mix an
unrelated feature or documentation initiative into the review branch.

In a shared worktree, monitor for concurrent branch switches and commits. A
different agent can unintentionally commit onto the currently active branch.
Recheck `HEAD` and `git status` before staging or committing.

### Step 3 — review the contracts before style

Review in this order:

1. safety and authority boundaries;
2. state transitions and transactional/atomic behavior;
3. failure ordering and fail-closed behavior;
4. public imports, signatures, exception identities, and monkeypatch seams;
5. persistence, idempotency, reconciliation, and recovery;
6. dependency direction and transitive import boundaries;
7. test sensitivity and mutation evidence;
8. documentation accuracy; and
9. readability and maintainability.

For refactors, compare the complete pre/post facade surface mechanically. Do
not preserve only the names used by current in-repository callers when the
milestone promises an unchanged compatibility facade.

When orchestration moves behind dependency injection, enumerate every runtime
global formerly resolved from the old module—including constructors, clocks,
converters, constants with behavioral meaning, and deferred imports. Do not
inject only the collaborator already monkeypatched by one known test.

### Step 4 — prove findings red before fixing

For every material suspected regression:

1. add or identify the narrowest meaningful test;
2. run it on the uncorrected implementation;
3. confirm it fails for the expected reason;
4. apply the smallest correct fix; and
5. rerun it green.

Avoid tests that pass through an earlier refusal and therefore never exercise
the behavior they claim to characterize. Assert the path was reached and the
important observable effects occurred—or did not occur.

If a finding cannot be reproduced, report it as an open concern rather than a
confirmed defect.

### Step 5 — validate proportionally

At minimum, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q <focused tests>
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

Use a fresh writable `--basetemp` when required. Preserve the test isolation
that prevents inherited brokerage credentials or the operator database from
affecting collection.

Record:

- exact focused count and duration;
- exact full count, skipped count, warnings, and duration;
- Python version;
- compile result;
- diff-check result; and
- any environment deviation from the prior baseline.

Test count alone is not acceptance. State which failure directions and
contracts were exercised.

### Step 6 — commit review corrections

Stage only the intended files. Verify the staged diff, then commit the review
separately from the implementation:

```powershell
git diff --cached --check
git status --short --branch
git diff --cached --stat
git commit -m "Complete independent <milestone> review"
```

Do not push, merge, or open a pull request unless the owner has authorized it.

### Step 7 — update the session handoff

After the correction commit exists, update `docs/SESSION_HANDOFF.md`. This
ordering allows the handoff to name the exact implementation and review
commits.

The handoff must include:

- preparation date/time and audience;
- repository URL;
- `origin/main` commit;
- implementation branch and commit;
- review branch and correction commit;
- whether each branch is local, pushed, or merged;
- current worktree state;
- implementation summary;
- confirmed findings and corrections;
- final validation results and Python version;
- current milestone status and honest definition-of-done assessment;
- the exact recommended next milestone;
- non-negotiable safety and authority boundaries;
- relevant machine-local database/artifact/credential/scheduler state when a
  computer transition is expected;
- local-only commits that will be lost unless pushed or transferred;
- required reading order; and
- a copyable resume prompt usable by both Codex and Claude.

Remove or rewrite stale instructions. Do not leave the old handoff's next step
at the top and append a contradictory update at the bottom.

Never place secret values, account numbers, licensed data, or private artifact
contents in the handoff. Credential presence booleans, file hashes, sizes, and
non-sensitive row counts are acceptable when useful.

### Step 8 — verify and commit the handoff

Run:

```powershell
git diff --check -- docs/SESSION_HANDOFF.md
git diff -- docs/SESSION_HANDOFF.md
git status --short --branch
```

Perform a narrow secret-shape scan. Then commit the handoff separately:

```powershell
git add -- docs/SESSION_HANDOFF.md
git diff --cached --check
git commit -m "Update session handoff after reviewed <milestone>"
```

Recheck that the branch is clean and that history contains, in order:

```text
implementation commit
review correction commit
handoff commit
```

### Step 9 — report to the owner

The final review report should state:

- acceptance, conditional acceptance, or rejection;
- findings ordered by severity;
- what was fixed;
- an honest 1–10 implementation-quality rating;
- focused and full validation results;
- implementation, review, and handoff commits;
- branch and push/merge state;
- whether the overall roadmap milestone is genuinely complete; and
- the exact next step.

Lead with the outcome. Do not inflate a small hardening change into an
architectural milestone, and do not understate a difficult safety-preserving
refactor merely because its final diff is small.

## 5. Session handoff maintenance rules

Update the handoff after:

- every independent implementation review;
- every merge that changes the active milestone or next step;
- every machine transition;
- every meaningful change to local-only branch availability;
- every change to operator-database or licensed-artifact transfer state;
- every change to paper/live authority posture;
- every deployment or scheduler-state change; and
- every owner decision that reorders the roadmap.

Do not rewrite machine-local hashes or credential/scheduler observations from
memory. Re-measure them read-only when a transition handoff needs them.

Historical status documents may retain milestone narratives, but
`docs/SESSION_HANDOFF.md` must always tell the next agent what is true now and
what to do next.

## 6. Review severity guide

Use severity consistently:

- **P0 — catastrophic:** active or imminent loss of funds/data, live authority
  escape, or unrecoverable corruption.
- **P1 — critical:** credible order duplication, unsafe execution, broken
  atomicity, false broker outcome, or security/secret exposure.
- **P2 — material:** public compatibility regression, incorrect durable state,
  meaningful fail-open/fail-closed error, missing recovery, or roadmap
  definition-of-done violation.
- **P3 — minor:** inaccurate documentation, weak test naming, maintainability
  issue, or low-risk edge case without current behavioral impact.

Severity describes impact, not how many lines are required to fix it.

## 7. Repository-specific safety checklist

Every execution-related review must explicitly verify, as applicable:

- paper mode remains enabled;
- exact human approval remains required;
- the kill switch cannot be bypassed;
- atomic claims remain storage-level conditional transitions;
- reservations are retained for ambiguous broker outcomes;
- only confirmed failure/absence paths release budget;
- telemetry failure cannot fall through to submission;
- idempotency keys and broker identity matching remain exact;
- replacement chains are resolved before adopting an order;
- mismatched orders halt rather than auto-resolve;
- proposal/execution roots cannot reach LLM, ML, strategy-authoring,
  backtest, or proposal-generation code through forbidden imports; and
- ML/LLM output remains observational and non-authoritative.

If a review does not touch a checklist item, say it was out of scope rather
than implying it was re-proven.

## 8. Minimal reusable instruction

Use this when assigning an implementation review:

```text
Review the implementer's exact committed branch independently. Read CLAUDE.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, docs/SESSION_HANDOFF.md, and
the active milestone/status documents completely. Create a separate review
branch. Check safety, state transitions, compatibility imports and exception
identities, call-time dependency seams, persistence, recovery, import
boundaries, and test sensitivity. Reproduce material findings red before
fixing them. Run focused tests, the full suite, compileall, and git diff
checks. Commit corrections separately. Then update and commit
docs/SESSION_HANDOFF.md with the exact final commits, validation, remaining
work, branch availability, and next step. Give a genuine 1–10 assessment. Do
not push or merge unless explicitly authorized.
```
