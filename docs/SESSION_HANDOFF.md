# Development session handoff

Prepared: 2026-08-10, after Codex independently reviewed and corrected
Claude's broker-activity ingestion fix for the stalled paper evidence epoch,
and Claude counter-reviewed the correction. **Counter-review outcome:
accepted in full — all seven findings confirmed, none a false alarm, no
correction to the correction required.** See section 5a and the review
report's §6 for the live-endpoint evidence and reverse-mutation record.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the previous session
handoff. Durable owner decisions and machine-local facts live in
`docs/OPERATIONAL_FACTS.md`; sequencing authority lives in
`docs/ACTION_PLAN_2026-08-02.md`.

## 0. Read this first — exact current state

- Repository: `C:\git\customizedAgent\trading_agent` on this development
  computer.
- Active branch: `codex/review-epoch-activity-ingestion-20260810`.
- Review base: merged `main` / `origin/main` at `e871f2f` (PR #181).
- Claude submission: branch
  `user/claude/broker-activity-ingestion-20260810`, implementation `f10b47d`,
  handoff `8f922a9`. That branch is on the remote at `8f922a9`.
- Codex correction: `a8174b9` — `Correct broker activity epoch recovery`.
- Review report:
  `docs/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md`.
- Final review status: **accepted after correction; 0 P0, 0 P1, 0 P2,
  and 0 P3 open**.
- The Codex correction is committed in this checkout at `a8174b9`.
- The review branch is pushed:
  `origin/codex/review-epoch-activity-ingestion-20260810` is tip-equal to
  local HEAD at counter-review commit `4355347` (verified by hash), so
  another computer can fetch the complete review history. It is NOT merged
  and NOT deployed.
- Review made no broker call, operational-database mutation, scheduler
  change, epoch close/start, deployment, policy change, order submission,
  or live-trading change.

## 1. What was reviewed and the disposition of every commit

The ordered range `e871f2f..8f922a9` and its cumulative tree were reviewed.

| Commit | Disposition | Summary |
|---|---|---|
| `f10b47d` | **Accepted after correction** | Correct diagnosis and architecture, but three P2 implementation defects and one P3 input-boundary defect required `a8174b9`. |
| `8f922a9` | **Accepted after correction** | Correct incident evidence, but API/recovery claims, severity, deployment wording, and next-step ordering required documentation correction. |

Correction `a8174b9` preserves Claude's intended design: a bounded direct
Alpaca REST read, idempotent fee journal entries, FILL exclusion, and
fail-closed unsupported post-bootstrap activities. The correction changes
four behaviors:

1. It accepts Alpaca's published non-trade response shape. `created_at` and
   `status` are useful extensions but are not required by the published
   schema. Missing `created_at` is accepted only when the caller proves it
   queried with Alpaca's exclusive `after` bound exactly equal to bootstrap;
   the ledger does not guess timestamp meaning from an activity ID.
2. It queries exactly after bootstrap and skips every pre-bootstrap non-trade
   row before activity-type handling. An opening-balance dividend, interest,
   or transfer can no longer poison the first reconciliation.
3. An unsupported post-bootstrap activity still fails `operations-cycle`,
   but snapshot reconciliation, verified backup, operational health, and the
   critical alert run before the original error is re-raised.
   `paper-observation` still stops immediately and writes no evidence.
4. `page_size` now requires a real non-bool integer from 1 through 100; bool,
   fractional, and string values are not silently coerced.

## 2. Prioritized review findings

The complete evidence and red/green record is in the review report. Summary:

| ID | Priority | Final state | Finding |
|---|---|---|---|
| EPOCHR-001 | P2 | Closed in `a8174b9` | Required undocumented Alpaca `created_at` and `status`, rejecting a published-success shape. |
| EPOCHR-002 | P2 | Closed in `a8174b9` | Thirty-day overlap plus type-before-cutoff ordering let pre-bootstrap non-fee activity block reconciliation. |
| EPOCHR-003 | P2 | Closed in `a8174b9` | Activity failure suppressed snapshot reconciliation, backup, and health in `operations-cycle`. |
| EPOCHR-004 | P2 | Closed in docs | Deployment/epoch instructions were in the wrong order and falsely implied deployment closes durable epoch state. |
| EPOCHR-005 | P3 | Closed in `a8174b9` | `page_size` silently coerced bools, floats, and strings. |
| EPOCHR-006 | P3 | Closed | Comments falsely said a manual journal entry could acknowledge an unsupported broker activity. |
| EPOCHR-007 | P3 | Closed | AP-6 severity and active/stalled epoch wording contradicted repository definitions and measured state. |

No P0 or P1 issue was found. AP-6 is P2: it caused incorrect durable ledger
state and missing recovery, but no unsafe execution, duplicate order, broken
atomicity, false broker outcome, immediate secret exposure, or live-authority
escape.

Claude's quality for this round is **6/10**. The operational diagnosis was
excellent: all 16 fills were reconciled, three post-bootstrap CAT fees were
isolated to the exact $0.03, and widening the tolerance was correctly
rejected. The architectural direction was also right. The score is held down
by three material code paths that made the submission unsuitable to deploy
without review correction, plus an unsafe deployment sequence in the handoff.

## 3. Operational truth — epoch-002 is active but stalled

The following was measured by Claude read-only on the separate epoch host;
Codex did not repeat the broker/database inspection:

- `paper-epoch-002` remains the active durable epoch, frozen at commit
  `9a91498` and bound to `my_policy.json`.
- It has exactly **1 captured session (2026-08-06), 0 epoch orders, and 0 of
  5 required drills**.
- Every post-close observation since 2026-08-07 has failed closed on ledger
  reconciliation, so the 60-session / 30-order mandate evidence is **not
  accumulating**.
- Ledger cash is $74,389.33 versus broker cash $74,389.30. Three Alpaca CAT
  fees posted after the 2026-08-05 bootstrap explain the exact $0.03. Two
  earlier fees were already inside opening cash. All 16 broker fills matched.
- A critical `scheduled-paper-observation-failure` alert is open.
- The account holds AEP, so future dividends are a real unsupported activity
  case. They must continue to fail closed until a deliberate reviewed handler
  exists. A separate manual dividend posting does not acknowledge the broker
  activity and will not unblock this sync.
- The reviewed fix has not run against the operator database. The statement
  that it will self-heal $0.03 is an implementation expectation, not completed
  operational evidence.

Standing host details, task permissions, credential-lift behavior, local-only
backup limitations, and the second-host prohibition are maintained in
`docs/OPERATIONAL_FACTS.md`. In particular, only the epoch host may run the
cadence; the second computer's four scheduled tasks must stay disabled while
the same Alpaca paper account is bound to the epoch host.

## 4. Required owner-authorized epoch swap sequence

Nothing below has been performed. The next useful step is owner authorization
to push and merge this accepted review. Deployment is a separate owner action.
When deployment is authorized, preserve this exact order:

1. On the epoch host, disable all four `TradingAgent-Paper-*` tasks using the
   elevated machine-local swap procedure. Merely stopping them is not enough;
   triggers can restart them.
2. While the frozen `9a91498` runtime is still present, explicitly close
   `paper-epoch-002`. Deployment does not close stored epoch state.
3. Deploy only the merged, independently reviewed AP-6 tree. Do not deploy a
   local review branch directly.
4. Run `ledger-reconcile` against the operational database. Require
   `matched: true`; verify the three CAT fees were inserted once and the cash
   mismatch is zero. Stop if any unsupported activity or mismatch remains.
5. Run readiness on the exact deployed commit.
6. Start `paper-epoch-003` with the intended strategy/model/policy lineage.
   Do not start it before step 4 succeeds.
7. Run all five required drills inside epoch-003.
8. Re-enable all four scheduled tasks and verify actual execution/heartbeats,
   not merely task existence.

Closing an epoch does not delete positions, cash, journal entries, tax lots,
orders, or prior evidence. Evidence from epoch-002 cannot be pooled with
epoch-003 to satisfy mandate thresholds.

## 5. Validation on the corrected tree

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted focused baseline: 100 passed in 14.98s (Claude's record).
- New regression run on the uncorrected tree: 7 failures as intended in
  17.02s.
- Final affected files: **107 passed** in 13.02s.
- Full suite collection: **3334 tests**.
- Full suite, deterministic file batches: **3334 passed, 0 failed, 0
  skipped** — 1045 in 124.41s; 1025 in 214.14s; 990 in 131.50s; 274 in
  215.19s. There were 25 existing dependency deprecation warnings.
- Two monolithic runs timed out at the desktop command-channel boundary at
  120s and 600s without a test failure; they are not counted as passes. The
  four successful batches cover the exact collection once.
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected LF-to-CRLF checkout notices.
- Active-document consistency: **8 passed** in 0.18s. The broader four-file
  documentation-consumer batch: **98 passed** in 4.17s.
- Narrow non-printing secret-shape scan of the README/docs diff: clean.

No live Alpaca end-to-end test was performed. Provider-contract conclusions
come from Alpaca's official account-activities reference and OpenAPI schema,
linked in the review report.

## 5a. Counter-review (Claude, same day) — accepted in full

Claude counter-reviewed `a8174b9` and `74dd309` per
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`. Both commits: **accepted**.
Full record in `docs/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md` §6.

- **All seven EPOCHR findings confirmed; none downgraded.** EPOCHR-002 was
  strengthened with live read-only endpoint evidence Codex did not have:
  (a) the account's full activity history contains a `JNLC +$100,000`
  funding journal created 2026-07-26, inside the submitted 30-day window —
  with the submitted type-before-cutoff ordering, the first production run
  would have refused on the account's own funding deposit, so the submitted
  fix was dead on arrival; (b) `after=<bootstrap instant>` returned exactly
  the three post-bootstrap CAT fees (including the 08-05-dated fee created
  08-06T00:06Z) and nothing earlier, live-proving Alpaca's `after` is an
  exclusive creation-time bound, the claim the corrected exact-bootstrap
  window depends on.
- **Four reverse mutations** proved the corrected guards load-bearing
  (cutoff-before-type ordering, +1µs surrogate, operations-cycle
  failure-preservation, strict `page_size`); each turned exactly its
  intended test red, and the restored tree re-verified green (107 focused).
- **Single uninterrupted full-suite run** on the exact corrected tree:
  **3334 passed, 0 failed, 25 warnings** (the same pre-existing dependency
  deprecations) — closing the review's monolithic-run gap left by its
  batched validation.
- **Two P3 watch items recorded** (review report §6): CR-W1 — a
  surrogate-journaled fee whose row later gains `created_at` would raise a
  loud content conflict on re-sync (fail-closed, correct direction); CR-W2 —
  a future post-bootstrap paper-cash top-up (`JNLC`) fails closed by design
  until a small reviewed handler maps it to `record_cash_transfer`.
- Counter-review made no broker mutation (two read-only activity GETs), no
  operational-database access, and no epoch, scheduler, policy, or
  deployment action.

## 6. Documentation synchronized in this round

- `docs/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md` — full commit
  dispositions, P0-P3 ledger, provider evidence, validation, and rating.
- `docs/ACTION_PLAN_2026-08-02.md` — AP-6 accepted-after-correction state,
  P2 severity, stalled epoch, and exact owner deployment sequence.
- `docs/OPERATIONAL_FACTS.md` — durable active-but-stalled machine fact and
  no-unverified-self-heal warning.
- `docs/OPERATIONS_RUNBOOK.md` — close-before-deploy and
  reconcile-before-new-epoch procedure; operations-cycle failure isolation.
- `README.md` — fee activity sync and unsupported-activity behavior.
- `docs/FEATURE_MILESTONE_RECORD.md` — exactly two-paragraph completed AP-6
  record.
- This canonical handoff replaces the stale AUI-first handoff.

## 7. Unchanged boundaries and later work

- Paper only. Live trading remains prohibited.
- No LLM/ML component gains proposal, approval, sizing, or execution
  authority.
- Unsupported broker activity types remain intentionally unimplemented; do
  not add dividend/interest/corporate-action accounting casually.
- Three-sleeve M3 dividend-earmark accounting and APPROVE-gated reinvestment
  proposals remain absent and unauthorized.
- GR-6 off-machine backup remains blocked on the corporate epoch host except
  for a permitted physical device; do not suggest corporate or personal cloud
  upload.
- The current critical path is restoring a clean frozen evidence epoch, not
  starting another development milestone on the operational checkout.

## 8. Required reading order on resume

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/OPERATIONAL_FACTS.md`.
3. `docs/ACTION_PLAN_2026-08-02.md`.
4. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
5. `docs/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md`.
6. `docs/OPERATIONS_RUNBOOK.md`.
7. `docs/FEATURE_MILESTONE_RECORD.md`.

Before acting, run:

```powershell
git status --short --branch
git log -8 --oneline --decorate
git branch -vv
```

Expected branch in this checkout is
`codex/review-epoch-activity-ingestion-20260810`, containing Claude's
`f10b47d`, `8f922a9`, then correction `a8174b9` and the documentation commit
that contains this handoff. If the branch is absent on another computer, the
remote-availability warning remains true; do not reconstruct the correction
from chat memory.

## 9. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/OPERATIONAL_FACTS.md,
docs/ACTION_PLAN_2026-08-02.md, docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, docs/SESSION_HANDOFF.md,
and docs/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md completely. Confirm
branch, HEAD, remote reachability, and worktree state before acting. The
latest work is the accepted-after-correction AP-6 broker-activity review on
branch codex/review-epoch-activity-ingestion-20260810. The branch has no
upstream; correction a8174b9 closes all findings. Do not push, merge, deploy,
touch the operator database, or close/start an epoch without explicit owner
authorization.
paper-epoch-002 remains active in storage but stalled at frozen 9a91498 with
one session and no accumulating mandate evidence. If deployment is authorized,
follow the close-before-deploy, reconcile-before-epoch-003 sequence in the
handoff and runbook exactly.
```
