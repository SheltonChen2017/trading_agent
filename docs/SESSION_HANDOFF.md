# Session handoff — epoch stall detector independently reviewed

Prepared: 2026-08-14 by Codex after reviewing Claude's read-only epoch stall
detector and correcting the active project records.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REVIEW_2026-08-14_EPOCH_STALL_DETECTOR.md`
4. `docs/REVIEW_2026-08-14_CODEX_SET1_COUNTERREVIEW.md`
5. `docs/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md`
6. `docs/REVIEW_2026-08-13_OBSERVATION_CLOCK_AND_EPOCH005_ROLL.md`
7. `docs/OPERATIONAL_FACTS.md`
8. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes push, merge, deployment, evidence repair, an epoch
roll, M4, funded-account access, live trading, operator-database mutation, or
a scheduled-task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Current `main` and `origin/main`: `60027af` (PR #220). Its first parent is
  PR #219, which merged Codex's verified SET-1 counter-review correction; its
  second current-state change records the owner's 60-day epoch-005 hold.
- Claude feature branch: `user/claude/epoch-stall-detector-20260814`, available
  remotely at submitted commit `6aa7069`.
- Active review branch: `codex/review-epoch-stall-detector-20260814`, created
  from exact submitted commit `6aa7069`.
- Product/test correction: `4273de6`.
- The branch has not been pushed. The documentation commit that contains this
  handoff follows the product correction as a separate commit.
- The operational checkout remains separate at frozen commit `752d3b7`; no
  development commit in this review was copied there.

Relevant current review history:

- `4de784e`: Claude's epoch-005 observation-clock and roll implementation
  chain began here.
- `1cb8abf`: Codex's independent correction of that roll chain.
- `c048a94`: owner decision to keep epoch-005 unchanged for 60 days.
- `60027af`: PR #220, current main after that decision.
- `6aa7069`: Claude's read-only stall-detector implementation.
- `4273de6`: Codex's product/test correction.
- The completed BUY-1 review branch remains
  `codex/review-buy1-suggestion-picker-20260813`, correction `44a7f85`; it is
  historical recovery context, not reopened work.

The review began from a clean worktree and exact submitted commit. No
unrelated user work is included.

## 2. Outcome and commit dispositions

Final disposition: **accepted after correction**.

Issue total: **0 P0 / 0 P1 / 2 P2 / 5 P3; all closed; 0 open**.

- `6aa7069`: **accepted after correction**. The classifier/adapter split,
  active-epoch anchoring, trailing-miss definition, five statuses, and
  read-only intent were retained. The scheduler model and unhealthy-exit
  semantics were not safe to accept unchanged.
- `4273de6`: Codex product/test correction. Expected capture sessions now use
  a configurable fixed wall-clock trigger; defaults match the measured
  installed task. No active epoch exits nonzero. Public inputs fail closed,
  real SQLite behavior proves read-only access, and all operator messages
  describe actual state and failure behavior.

Closed findings:

- P2 CODSTALL-001: market close plus 3.5 hours moved the fixed Windows trigger
  on early-close sessions and could manufacture a stall. Corrected to fixed
  wall clock with explicit time/timezone options.
- P2 CODSTALL-002: `NO_ACTIVE_EPOCH` returned success. It now exits 1.
- P3 CODSTALL-003: invalid thresholds, negative grace, and naive clocks were
  accepted. They now refuse.
- P3 CODSTALL-004: source-text searching did not prove SQLite read-only
  behavior. Temporary-file tests now prove write refusal, byte stability, and
  absence of WAL/SHM side files.
- P3 CODSTALL-005: submitted prose falsely said a refused observation task
  reports success. It now reflects the real nonzero exit and critical alert.
- P3 CODSTALL-006: required milestone/current records were absent and the
  Action Plan/handoff still named old main `7055142`. Current records now
  identify `60027af` and this review.
- P3 CODSTALL-007: `NOT_DUE_YET` always claimed zero observations, even when a
  capture already existed inside the grace window. Detail is now data-aware.

The full evidence and red-before-green record are in
`docs/REVIEW_2026-08-14_EPOCH_STALL_DETECTOR.md`.

## 3. Final feature behavior

- `assistant/epoch_cadence.py` is a pure classifier. It does not open a
  database or perform an operational action.
- `scripts/check_epoch_cadence.py` opens the supplied SQLite path through
  `mode=ro`, reads the single active epoch and its observation session dates,
  and prints either human text or JSON.
- Expected sessions begin at the epoch's actual `started_at` and become due
  only after the installed task's fixed wall-clock time plus grace.
- Defaults are the currently measured 16:30 Pacific task time. Operators must
  read the installed task and pass `--capture-time` / `--capture-timezone` if
  that task is reinstalled or changed; never derive it from market close.
- `NOT_DUE_YET`: no session is overdue. This is exit 0 whether the new epoch
  is still empty or an observation already arrived inside the grace window.
- `HEALTHY`: every due session is present; exit 0.
- `BEHIND`: at least one session is missing, but the consecutive missing tail
  is below the stall threshold; exit 1.
- `STALLED`: the consecutive missing tail meets the threshold; exit 1.
- `NO_ACTIVE_EPOCH`: nothing is collecting evidence; exit 1.
- The detector does not write, repair missing rows, restart a task, create an
  alert, change a schedule, roll an epoch, deploy code, or enter any trading
  path. A monitor may use its nonzero exit, but no monitor/task was installed
  by this review.

## 4. Validation

Authoritative environment: repository `.venv`, Python 3.13.14, Streamlit
1.60.0, Windows.

- Submitted detector suite: **17 passed**.
- Red regression evidence: **4 failed / 16 passed** before correction,
  covering the wrong early-close schedule, absent configurable trigger,
  successful no-active-epoch status, and invalid threshold acceptance.
- Corrected detector module after the final message test: **24 passed**.
- Detector plus adjacent paper-evidence/schema/import boundaries: **59 passed**
  before the final message test; all are included in the complete run.
- Previously failing UI files under the correct pinned environment:
  **40 passed**.
- Full settled product tree in `.venv`: **3,783 passed / 0 failed / 25 known
  dependency warnings** in 900.86 seconds.
- Repository `compileall`: clean. `git diff --check`: clean.

One non-authoritative full run used the user Python by mistake. That runtime
has Streamlit 1.52.2, while the repository pins 1.60.0, so 14 UI tests failed
because `AppTest.segmented_control` is unavailable. A pip replacement failed
on a malformed shared-package record and rolled back; the user installation
remains 1.52.2. The authoritative `.venv` run above is green and the running
development app was not stopped or changed.

No source or documentation was edited concurrently with the authoritative
full run. Test broker/provider seams were fakes or monkeypatches.

## 5. Operational truth and owner decision

- `paper-epoch-005` is active on the epoch host at frozen deployed commit
  `752d3b7`. Epochs 001 through 004 are closed and cannot pool evidence into
  it.
- Owner decision, 2026-08-14: epoch-005 runs unchanged for 60 days. Do not
  deploy, roll, or otherwise disturb it. TRADE-1, BUY-1, SET-1, the fractional
  path, SET-1 counter-review corrections, and STALL-1 remain development-only.
- The measured installed `TradingAgent-Paper-PaperObservation` trigger is
  Monday-Friday at 16:30 Pacific/local. Fresh installer source may express a
  different timezone; the installed task is the authority.
- Sixty calendar days produces roughly 43 weekday observations, not 60
  sessions. Whether the owner's target means days or observations remains an
  owner clarification before completion is claimed.
- The one live detector invocation used SQLite read-only mode and reported
  epoch-005 `NOT_DUE_YET` at that moment. This point-in-time read neither
  changed the database nor establishes future cadence.
- The owner may exercise development UI features with
  `scripts/launch_dev_app.ps1`; its default scratch database and environment
  kill switch prevent submission. `-AllowPaperOrders` reaches the shared
  Alpaca paper account and must not be used while the 60-day hold stands.
- CR-W3 remains a watch item: the first real AEP dividend subtype may fail
  closed around 2026-09-10 and require the reviewed acknowledgement path. Do
  not widen reconciliation tolerance or post a manual compensating entry.

No account identifier, balance, credential value, private artifact content,
or secret is recorded here.

## 6. Next authorized step

1. Claude may independently verify `4273de6` and the documentation commit on
   `codex/review-epoch-stall-detector-20260814`. The branch must be pushed only
   if the owner asks. Verification does not authorize merge or deployment.
2. If the owner accepts the review later, merge through the normal PR process.
   Keep STALL-1 unscheduled and undeployed during the 60-day epoch hold unless
   the owner explicitly changes that decision.
3. If the installed observation task changes, remeasure its trigger with the
   command in `HOW_TO_USE.md` and pass matching CLI time/timezone options.
4. Separately answer whether the 60-day decision means calendar days or 60
   captured market sessions before declaring the evidence target complete.
5. The earlier SET-1 design question also remains open: whether strict
   whole-share mode should permit a fractional sell only when it closes the
   entire position.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 7. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REVIEW_2026-08-14_EPOCH_STALL_DETECTOR.md, and
docs/SESSION_HANDOFF.md. main and origin/main are 60027af (PR #220). Claude's
STALL-1 implementation is 6aa7069. Codex accepted it after correction on
codex/review-epoch-stall-detector-20260814; product/test correction 4273de6
uses the measured fixed scheduler wall clock, makes NO_ACTIVE_EPOCH unhealthy,
hardens inputs, proves real SQLite read-only behavior, and corrects operator
messages. The full pinned-environment tree passed 3,783 tests. The review
branch has not been pushed. The operational runtime remains frozen at 752d3b7
under active paper-epoch-005 and the owner's 60-day unchanged hold. Do not
push, merge, deploy, schedule the detector, roll the epoch, mutate the operator
database, begin M4, access a funded account, or enable live trading without
explicit owner authorization.
```
