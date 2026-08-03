# Development session handoff

Prepared: 2026-08-03T17:05:00-07:00

Audience: Codex, Claude Code, and the repository owner after changing
computers or starting a new agent session.

This file replaces every earlier handoff. Fetch and verify its Git claims
before acting; do not follow an older “review GR-3” instruction.

## 1. Read this first

**GR-3 is complete after independent correction, review, and third-round
confirmation.** Claude's core fault-matrix design was strong, but the
submitted runner had material fail-open evidence paths, F4 did not create
its required critical alert, and F3 did not actually rehearse restart from
`submitting`. All confirmed findings are corrected on
`codex/review-gr3-fault-drills-20260803`. Claude's confirmation
(commit `c168b7a` on branch `user/claude/gr-3-review-confirmation-20260803`,
based on review tip `7e846f1`) reproduced all seven red proofs on exact
`4c395d7`, reverse-mutated one runner fix (detected), and found + fixed one
additional P2 of the review's own headline class (GR3CONF-001): the
submit-time mismatch halts in
`assistant/execution_kernel/outcomes.py::resolve_failed_submission` still
used bare `set_kill_switch` with no durable alert; both sites now route
through `activate_reconciliation_halt`, pinned by a third F4 drill test in
the harness inventory. Full suite on the confirmation tree: 2,507 passed /
1 skipped / 25 warnings.

Canonical records:

- `docs/REVIEW_2026-08-03_GR3_FAULT_DRILLS.md` — every commit disposition,
  P0–P3 ledger, red/green proof, limitations, and quality score;
- `docs/ACTION_PLAN_2026-08-02.md` — owner-adopted sequencing authority;
- `docs/GENERAL_READINESS_STATUS.md` — corrected GR-3 status;
- `docs/OPERATIONS_RUNBOOK.md` — exact drill behavior/operator command; and
- `docs/FEATURE_MILESTONE_RECORD.md` — completed two-audience GR-3 record.

**Current state:** Phase 4 remains active. The owner chose the GR-5 channel
on 2026-08-03 (**Windows desktop notification mandatory for critical;
warnings batched into the daily briefing; webhook out of scope**) and
authorized implementation. GR-5 is IMPLEMENTED at commit `00a8d13` on
LOCAL-ONLY branch `user/claude/gr-5-alert-delivery-20260803` and awaits
independent review — do not reimplement it, and do not push or merge it
without owner approval. `alert_delivery` was the last drill type without a
producer, so **AP-5 is now closed**: all five `REQUIRED_PROMOTION_DRILLS`
have producers. GR-2 remains the action plan's Phase 4 ride-along and is
NOT authorized by this handoff.

No GR-3 implementation or review action used a live broker, funded account,
operator database, scheduler, or formal evidence epoch. Nothing authorizes
live trading, deployment, or model/signal promotion.

## 2. Canonical Git state

Repository: `https://github.com/SheltonChen2017/trading_agent`

Verified at handoff preparation:

```text
origin/main = local main = d5400cc6d148eca22fc6bcd5c33c6ac24f523ac9
main meaning = PR #126 merged the reviewed GR-1E branch
Claude GR-3 branch = user/claude/gr-3-fault-drills-20260803
Claude GR-3 tip = 61e03146f6c865c2468b282136883aa442d2fbad (pushed)
active branch = codex/review-gr3-fault-drills-20260803
active HEAD before this handoff = a35d369
worktree = clean before replacing this file
```

Commands on another computer:

```powershell
git fetch --all --prune
git status --short --branch
git log --graph --decorate --oneline -25 --all
git branch -vv
git worktree list
git switch --track origin/codex/review-gr3-fault-drills-20260803
```

Claude implementation history:

```text
d5400cc  base / current main
4c395d7  GR-3 fault matrix and runner implementation
9c466f6  implementation handoff update
61e0314  record pushed Claude branch
```

Independent review history after Claude's tip:

```text
9f5ab5e  Correct and complete independent GR-3 fault-drill review
a35d369  Record completed GR-3 fault-drill milestone
dad82ee  Replace session handoff after reviewed GR-3
```

The review branch was pushed to
`origin/codex/review-gr3-fault-drills-20260803`, configured to track it, and
remote creation through `dad82ee` succeeded. The commit containing this
post-push paragraph is also pushed before handoff completion, so another
computer can fetch the full correction/review and handoff. No pull request
has been opened and neither Claude's branch nor this review branch has been
merged into `main`; PR creation/merge remains an owner decision.

### Shared-worktree caution

A second worktree still exists at:

```text
C:\Users\sheltonchen\AppData\Local\Temp\claude\C--git-customizedAgent-trading-agent\a7c90bdc-bdfc-448e-b7be-0f987527f0ed\scratchpad\bt
```

It holds local branch `user/claude/residual-signals-20260803` at `a1d2587`;
its remote is deleted. Do not delete, move, prune, switch, or commit in that
worktree. Recheck `HEAD`, `git status`, and `git worktree list` before every
future stage/commit because agents share Git objects.

### Other local-only work

`codex/ai-strategy-tool-doc-v2-20260802` remains local-only at `a656015` and
contains the AI-driven strategy/backtest-tool design. Preserve it; do not
recreate, delete, merge, or push it without owner direction.

## 3. GR-3 review result

Final disposition: **accepted after correction**.

Genuine assessment: **7/10 submitted, 9.5/10 corrected**. Claude did well on
the fault taxonomy, real temporary SQLite use, broker scripting, transaction
rollback scenario, inventory mapping, and runbook. The lower submitted score
reflects evidence integrity and definition-of-done failures in an operational
safety milestone, not cosmetic preferences.

Commit dispositions (`d5400cc..61e0314`):

| Commit | Disposition |
|---|---|
| `4c395d7` | accepted after GR3REV-001 through GR3REV-005 corrections |
| `9c466f6` | accepted after GR3REV-006 replacement of its stale handoff state |
| `61e0314` | accepted after GR3REV-006; pushed-state statement was correct |

No merge commit is in the reviewed range.

Resolved findings:

| ID | Priority | Correction |
|---|---|---|
| GR3REV-001 | P2 | Active-epoch recording now refuses `unknown`, dirty, missing, or different runtime lineage; report commit must exactly equal the epoch commit before any row is written. |
| GR3REV-002 | P2 | Skipped tests are failures. Pytest exit 1 is allowed only when JUnit contains a corresponding non-passing case; unexplained exit 1 and exit 2+ abort instead of certifying the matrix. |
| GR3REV-003 | P2 | Reconciliation identity/malformed-intent halts now atomically write both the persistent kill switch and a deduplicated critical `broker_reconciliation` alert across manual, startup, stream, and replacement-chain paths. |
| GR3REV-004 | P2 | F3 now starts from a truly ambiguous `submitting` row and proves startup lookup adopts the broker order with zero resubmit and retained reservation. Missing F5/F7 reservation/order/integrity assertions were added. |
| GR3REV-005 | P2 | Immutable reports now write/flush/fsync a same-directory temporary file and publish through an atomic no-overwrite hard link; failure removes the temporary path. |
| GR3REV-006 | P3 | Corrected “genuine disk full” overstatement, test-count wording, status/runbook details, and stale handoff topology. |

No P0 or P1 issue remains.

## 4. Completed GR-3 behavior

The final matrix contains eleven fault IDs mapped to fourteen behavioral
tests:

1. submit timeout resolves by idempotency lookup, never blind resubmit;
2. duplicate order identity stays one projected order;
3. pre-broker claim recovery, dead reconciliation recovery, and actual
   `submitting` startup recovery;
4. mismatched broker identity creates an atomic critical alert + halt and
   blocks further submissions;
5. one halted ticker refuses while an unrelated risk-reducing sell proceeds;
6. share-count mismatch refuses before broker submission;
7. stale and future-skewed quotes refuse;
8. journal-write disk-full-shaped error rolls back the real SQLite transaction
   and later reconciliation repairs it;
9. mid-flight kill switch blocks new submissions while reconciliation runs;
10. pytest stays off the operator database; and
11. inherited brokerage credentials do not reach the suite.

`scripts/run_fault_drill.py` runs the complete inventory, fails on missing,
skipped, unmapped, or unexplained-abort state, and emits an atomic hash-stamped
report. It can record `ambiguous_submission`, `restart_recovery`, and
`kill_switch` rows. With an active epoch, exact clean commit equality is
mandatory. Without an epoch, rows are explicitly `verification_only` and may
carry `code_commit=unknown`; they are not promotion evidence.

Limitations: F8 injects a `sqlite3.OperationalError` at the event-insert
statement after earlier statements ran in the same real transaction. It
proves application rollback behavior, not physical disk/filesystem exhaustion.
`alert_delivery` remains unproducible until GR-5; `backup_restore` retains its
existing recovery-drill producer.

## 5. Validation and review evidence

```text
Python: 3.13.14
submitted matrix baseline:
  13 passed in 17.56s
red runner reproduction:
  4 failed as expected (skip, unexplained exit, unknown/mismatched epoch)
red F4 reproduction:
  1 failed as expected (zero operational alerts)
corrected narrow runner/F3/F4:
  6 passed in 1.91s
corrected combined focused suite:
  110 passed in 36.40s
full suite:
  2,506 passed, 1 skipped, 25 warnings in 423.31s
post-full runner regression:
  7 passed in 13.69s
post-full CLI:
  passed; 11 fault IDs; 0 unmapped tests
compileall on exact final correction tree:
  clean
git diff --check:
  clean
```

Warnings are the known non-failing `websockets.legacy` and joblib/NumPy
deprecations. Full tests explicitly cleared inherited Alpaca credentials and
used a disposable process database; root pytest isolation also applied. All
review pytest trees and generated drill reports were verified inside the
workspace and removed. The CLI executed from a dirty review worktree, so its
standalone report correctly said `code_commit=unknown`; it was never recorded
to a database and was deleted.

Mutation/red sensitivity:

- the submitted skipped-case parser returned pass; corrected test catches it;
- the submitted unexplained nonzero exit returned pass; corrected test catches
  it;
- the submitted epoch recorder accepted both unknown and mismatched commits;
  two corrected tests catch them while a matching commit still records;
- submitted F4 produced no alert; strengthened drill failed red then passed;
- injected alert-insert failure proves halt + alert roll back together; and
- injected report publication failure leaves no destination or temp file.

## 6. Exact next action and open owner decisions

The action plan remains authoritative. GR-3 is done; do not repeat it.

GR-5 is implemented and awaiting review at `00a8d13`
(`user/claude/gr-5-alert-delivery-20260803`, base `95c4ea1`). Scope:
`assistant/alert_delivery.py` (channel protocol, dependency-free
`WindowsToastChannel` via PowerShell WinRT with alert text passed as JSON on
stdin, occurrence-based re-delivery, storage-verified self-test), an
immutable `alert_deliveries` table plus storage helpers, escalation of any
channel failure through both a nonzero CLI exit and a durable critical
alert, CLI `deliver-alerts` / `alert-self-test` (the latter producing the
`alert_delivery` drill, epoch-bound only on exact lineage match), read-only
`platform-readiness` checks, and the Streamlit **Operations** tab.

One design decision worth carrying forward: the delivery-health checks live
in the READ-ONLY readiness report, not `operational_health`. The latter
persists an alert for every failing check, so an "undelivered critical
alerts exist" check there raised a critical alert that was itself
undelivered — manufacturing a new alert every cycle. A pre-existing dedup
test caught it; `test_delivery_health_never_manufactures_its_own_alert`
pins the resolution.

Validation on that tree: full suite 2,525 passed / 1 skipped / 25 warnings;
18 focused delivery tests; three mutations detected (failure-as-delivered,
dropped severity routing, dropped occurrence-based re-delivery); compileall
and `git diff --check` clean. Honest limits: the Windows channel is
exercised only through its failure directions (never by raising a real
toast in tests), delivery proves the notification was raised rather than
read, and scheduling `deliver-alerts`/`alert-self-test` as tasks is Phase 5
deployment work. GR-2 remains the Phase 4 ride-along and is not authorized
by this handoff.

Other owner decisions remain open:

- whether to open/merge the pushed GR-3 review branch;
- whether to push/merge the local AI-strategy design branch;
- evidence-epoch hosting model and later mandate approval;
- operator database path/divergent snapshot handling;
- historical/reference data vendors and budget; and
- elevated scheduler deployment/credential rotation timing.

None implies live/funded trading authority.

## 7. Non-negotiable safety boundaries

- Paper trading is the only execution mode in scope.
- LLM/ML output is advisory or observational and cannot create approval,
  sizing, execution, cancellation, replacement, or policy authority.
- No funded brokerage path may be enabled or made convenient.
- Exact approval, policy fingerprint, atomic claim, deterministic risk checks,
  reservation, telemetry, idempotent submission, and reconciliation remain
  mandatory.
- Ambiguous submissions are reconciled, never blind-retried.
- A same-key broker mismatch remains unresolved, retains budget, atomically
  halts the platform, creates a critical alert, and requires investigation.
- Never commit credentials, operator databases, licensed data, or generated
  evidence artifacts.

## 8. Machine-local operational state

This review deliberately did not inspect or modify the operator database,
broker account, credentials, scheduler, or formal evidence state. Previous
handoffs contained machine-local measurements, but they were not revalidated
in this session and must not be treated as current. Before operations:

- identify the intended database path explicitly;
- run read-only schema/integrity verification before any apply action;
- confirm the Alpaca account is paper without printing credentials;
- inspect scheduler state in an elevated window;
- keep development/tests on disposable databases; and
- do not start or append to an evidence epoch from a moving/dirty checkout.

The previously recorded local backup path/hash may be useful for provenance
only and must be rechecked before reliance:

```text
data/backups/trading_assistant-pre-phase2-schema-20260803T171810Z.db
cc70b8d39fdd854075c81f17666d5ac8c1147344d46f8837ee2cb3fa41ccb6b5
```

## 9. Required reading order

Before the next implementation:

1. `CLAUDE.md` and `AGENTS.md` completely;
2. `docs/ACTION_PLAN_2026-08-02.md`;
3. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`;
4. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`;
5. `docs/SESSION_HANDOFF.md` (this file);
6. `docs/REVIEW_2026-08-03_GR3_FAULT_DRILLS.md`;
7. `docs/OPERATIONS_RUNBOOK.md` GR-3 section; and
8. the archived plan section for the owner-authorized Phase 4 work.

Every completed review must replace/update and separately commit this handoff.

## 10. Exact resume prompt

```text
Read CLAUDE.md and AGENTS.md completely, then read
docs/ACTION_PLAN_2026-08-02.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md,
docs/SESSION_HANDOFF.md, and
docs/REVIEW_2026-08-03_GR3_FAULT_DRILLS.md. Fetch/prune and verify every SHA,
branch, remote, and worktree before acting. Main is d5400cc. Claude's GR-3
tip is pushed at 61e0314. Independent corrections are 9f5ab5e and the
milestone record is a35d369 on codex/review-gr3-fault-drills-20260803. GR-3
is complete; do not repeat it. GR-5 alert delivery is IMPLEMENTED at 00a8d13
on local-only branch user/claude/gr-5-alert-delivery-20260803 (owner chose
Windows desktop notification for critical, warnings batched to the briefing,
webhook out of scope) and awaits independent review — do not reimplement it.
GR-2 is only the documented ride-along, not implied authority.
Do not enable live trading, start an evidence epoch, deploy scheduled tasks,
promote ML/signals, mutate the operator database, or touch the other Claude
worktree. Preserve local AI-strategy branch a656015 and ignored/credential
state.
```
