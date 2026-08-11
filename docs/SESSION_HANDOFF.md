# Session handoff — reviewed broker activity acknowledgement

Prepared: 2026-08-11

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

This file completely replaces the prior handoff. The newest durable state is
the independent review and correction of Claude's broker activity
acknowledgement feature. Read `docs/OPERATIONAL_FACTS.md` for long-lived
machine and owner facts that must not be copied from memory.

## 0. Outcome at a glance

**Accepted after correction.** Claude's implementation is a valuable design:
one explicit operator decision, bound to the exact broker row, can unblock an
unsupported post-bootstrap activity without requiring another code release.
However, the submitted implementation had six P2 and two P3 defects. Most
materially, the command advertised as read-only actually journaled recognized
rows, acknowledgement immediately posted instead of recording only, the CLI
did not bind activities to the ledger's Alpaca account, and settlement,
currency, missing amount, and cross-type broker-ID facts could be bypassed.
All confirmed findings are corrected in `74376e4`; no P0-P3 finding remains
open.

Claude implementation quality: **6/10**. The fingerprint, additive schema,
bootstrap ordering, amount provenance, migration, and restore-safe sync design
were good. The misses are material because this is an accounting ledger and
the CLI violated its own core contracts, not because the code was merely
untidy.

Full review and stable issue ledger:
`docs/REVIEW_2026-08-11_BROKER_ACTIVITY_ACKNOWLEDGEMENT.md`.

## 1. Exact repository and remote state

Starting/merged `main` and `origin/main`: **`24de4f5`**, PR #188 merge.
That merge contains Claude's submitted feature but **does not contain the
review corrections described here**.

Reviewed implementation branch:
`user/claude/broker-activity-acknowledgement-20260811`, published at
`origin/user/claude/broker-activity-acknowledgement-20260811` = **`b3c61cb`**.
It is already merged through PR #188.

Active review branch:
`codex/review-broker-activity-acknowledgement-20260811`, based on merged
`24de4f5`, with:

1. **`74376e4`** — code and regression-test corrections;
2. **`f7742bd`** — review report, action plan, operational facts, and completed
   milestone record; and
3. the separate handoff commit containing this file.

**REMOTE WARNING:** the active review branch has no configured upstream or
verified remote-tracking ref when this handoff is being prepared. The commits
listed immediately above exist in this local HEAD, but no push was authorized.
Another computer cannot retrieve the branch with `git fetch` until the owner
explicitly authorizes publication and the remote tip is verified. Do not
deploy `main`'s PR #188 implementation without the correction.

The preceding most-active direction implementation and full review chain are
now merged in main through PR #187 (`3b396f8`); the old merge-gap warning is
resolved. Its review branch remains published at `72fecf1` but is not the
active workstream.

## 2. Reviewed commit range and dispositions

Exact submitted range: **`3b396f8..24de4f5`**.

| Commit | Disposition | Result |
|---|---|---|
| `fb66d5f` | **Accepted after correction** | Core table/service/CLI design retained; six P2 and two P3 findings corrected at `74376e4`. |
| `b3c61cb` | **Accepted** | Correctly untracked the accidental shell-redirection file and fixed handoff heading order; no product issue found. |
| `24de4f5` | **Accepted after correction** | PR #188 merge contained no merge-only tree delta relative to `b3c61cb`; it inherits the submitted findings and is corrected by `74376e4`. |

Final issue state: **0 P0, 0 P1, 0 P2, 0 P3 open**.

Resolved findings:

- **BAA-001 (P2):** pending rows, foreign-currency journal amounts, and a
  missing amount treated as zero could pass acknowledgement. Recording and
  application now share immutable broker-fact validation; `no_cash_effect`
  requires an explicit zero.
- **BAA-002 (P2):** one broker ID could receive two accounting meanings.
  Acknowledgement creation and application now reject every cross-type journal
  external-ID collision, including `no_cash_effect`.
- **BAA-003 (P2):** `ledger-activity-review` wrote to the real ledger and did
  not return exact refused rows. It now opens the operator DB read-only and
  executes the real sync only on a verified temporary SQLite snapshot, without
  changing `last_database_backup`.
- **BAA-004 (P2):** activity commands lacked account binding. They now require
  an Alpaca bootstrap with an account ID and compare the connected account
  before any activity fetch; manual/unbound/mismatched ledgers refuse.
- **BAA-005 (P2):** acknowledgement accepted already handled rows and
  immediately ran a batch sync. It now accepts only a currently refused target,
  records only, and leaves application to the next ordinary sync.
- **BAA-006 (P2):** audit idempotency ignored operator and rationale and used
  a select-then-insert race. Atomic conflict handling now treats fingerprint,
  treatment, operator, rationale, and details as the substantive decision.
- **BAA-007 (P3):** naive acknowledgement timestamps were accepted. They now
  require timezone awareness.
- **BAA-008 (P3):** a successful `no_cash_effect` row was omitted from
  `activities_seen`. Successful reports now count every input row examined.

## 3. Accepted feature behavior

When an ordinary broker-activity sync encounters an unsupported post-bootstrap
row, the corrected operator workflow is:

1. Run `ledger-activity-review`. It verifies the connected Alpaca account,
   previews the exact sync against a disposable database copy, and prints
   structured refused rows and recorded decisions without changing the live
   ledger.
2. Run `ledger-activity-acknowledge <id> --treatment
   <fee|dividend|cash_transfer|no_cash_effect> --operator <name> --rationale
   "<reason>"`, adding `--ticker` for a dividend. The row must still be refused
   and the command records no journal entry.
3. The next ordinary `paper-observation` / activity sync re-fetches the broker
   row, requires the stored fingerprint and all immutable facts to agree, and
   applies the decision once through the existing append-only journal path.

The operator chooses treatment, never amount. The broker row supplies every
figure. A decision cannot override pending status, non-USD journal currency,
missing/zero journal amount, sign rules, the explicit-zero requirement for
`no_cash_effect`, the bootstrap cutoff, account binding, changed content, or an
existing accounting identity. A conflicting second decision is loud; an exact
retry is idempotent.

The migration is additive (`broker_activity_acknowledgements` created if
absent), so current and pre-feature databases initialize through the same
idempotent path. The feature changes no proposal, approval, order-submission,
policy, strategy, scheduler, ML/LLM, or live-trading authority.

## 4. Validation on the corrected tree

Environment: Windows, Python **3.13.14**, installed Streamlit **1.52.2**.

- Submitted focused baseline: **122 passed**.
- Red phase on uncorrected `24de4f5`: **10 reviewer regression cases failed
  for the intended reasons**.
- Final ledger and CLI suites: **112 passed** in 28.53s.
- Final schema, import-boundary, backup, operations, and readiness suites:
  **56 passed** in 20.09s.
- Full inventory: **3,405 collected; 3,404 passed; 1 explicitly deselected**:
  - A-F: 1,035 passed, one existing websockets warning;
  - G-M: 1,025 passed, 24 existing joblib/NumPy warnings;
  - N-S: 1,055 passed;
  - T-Z plus nested fault matrix: 289 passed, 1 deselected.
- The one deselection is the unchanged
  `test_every_theme_test_id_is_emitted_by_the_installed_streamlit`. This
  machine has Streamlit 1.52.2; the repository theme contract and unchanged
  test target Streamlit 1.60 and `stRadioOption` is absent from 1.52.2. The
  other 15 theme tests pass. This is recorded as an environment mismatch, not
  counted as green and not mixed into this accounting review.
- Repository `compileall`: clean.
- `git diff --check`: clean apart from Windows line-ending notices.
- Changed-file credential-shape scan: zero matches.
- Active-document consistency after durable review edits: **13 passed**.

Tests used temporary databases and mocks. No broker call, operator-database
write, scheduler change, alert acknowledgement, or epoch mutation occurred.

## 5. Operational truth and deployment boundary

Operational state was **not remeasured** during this review. The last recorded
read-only state remains authoritative until remeasured on the epoch host:

- `paper-epoch-001` and `paper-epoch-002` are closed;
- `paper-epoch-003` is the only active epoch, frozen at deployed **`ef05dc1`**;
- it has one lineage-matched observation from 2026-08-10 and all five required
  drills;
- its latest recorded ledger reconciliation matched with zero mismatches; and
- one open critical AP-7 `portfolio_accounting` alert was recorded from the
  negative-age race; it was not acknowledged here.

Development `main` contains the reviewed CR-W2 dividend/cash-transfer handler
merged as **PR #184 at `0ee3a22`**, both AP-7 freshness fixes, the most-active
UI review chain, and PR #188's uncorrected acknowledgement feature. Generic
JNLC cash journals still fail closed because the broker type does not prove
contributed-capital treatment. Deployed `ef05dc1` contains none of those later
changes. Therefore a refused activity still stalls epoch-003 today.

Do not patch the active epoch. A runtime change closes the epoch and evidence
cannot pool across commits. Deployment requires a separately authorized full
epoch-004 transition using `docs/OPERATIONS_RUNBOOK.md`: disable all four
operational tasks, close epoch-003 on its frozen runtime, deploy the fully
reviewed merge, reconcile and require a match, run readiness, start epoch-004,
record all five drills under exact lineage, re-enable tasks, and verify the
scheduled cycle. Confirm the AP-7 cause is absent before acknowledging its old
alert. The AEP cash dividend remains scheduled for 2026-09-10; CR-W3's first
real DIV subtype remains unverified and may over-refuse safely.

There are two machines and only the epoch host may run the cadence. Do not
enable the disabled duplicate tasks on the development/second host. See
`docs/OPERATIONAL_FACTS.md` for the last verified host identities, task state,
ignored swap evidence, and launcher locations.

## 6. Worktree and local artifacts to preserve

Expected worktree after the handoff commit: clean except for untracked
`ernkgjserng` at the repository root. It is captured `git branch` output from
an accidental shell redirect. It was briefly included by `fb66d5f`, removed
from Git by `b3c61cb`, and deliberately left physically untouched. Do not
stage, print, move, overwrite, or delete it unless the owner explicitly asks.

Two ignored machine-local swap-result JSON files described in
`docs/OPERATIONAL_FACTS.md` also remain outside review scope. Preserve them;
do not commit or expose their contents.

No secret value, account number, licensed artifact, or absolute account
balance belongs in documentation or Git.

## 7. Exact next steps

1. **Owner Git decision:** authorize pushing
   `codex/review-broker-activity-acknowledgement-20260811`. After pushing,
   verify the local and remote tips match before claiming cross-computer
   readiness.
2. **Owner merge decision:** merge that review branch so `main` receives
   `74376e4` and the review/handoff records. Do not deploy PR #188 alone.
3. **Separate owner operations decision:** keep epoch-003 frozen or authorize
   one complete epoch-004 roll. A push/merge is not deployment authority.
4. Only after those decisions, choose the next Phase 6 product milestone from
   `docs/ACTION_PLAN_2026-08-02.md`; do not infer one from an archived plan.

## 8. Non-negotiable boundaries

- Paper only; live trading remains prohibited.
- Exact human approval, deterministic validation, broker preflight, kill
  switch, account binding, and ambiguous-outcome reconciliation remain
  mandatory.
- ML/LLM output remains observational and cannot approve, size, submit, or
  promote trades.
- Do not change code, policy, strategy, model, scheduler, or account lineage
  inside an active evidence epoch.
- Do not manually insert observations, drills, ledger rows, or alert state.
- Do not infer accounting meaning from a generic cash journal or use a manual
  compensating row; the sync will re-read the broker event.
- Do not push, merge, deploy, call the broker, acknowledge alerts, mutate
  scheduled tasks, roll an epoch, or write the operator database without the
  owner's explicit authority for that action.

## 9. Required reading order

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/SESSION_HANDOFF.md`.
3. `docs/REVIEW_2026-08-11_BROKER_ACTIVITY_ACKNOWLEDGEMENT.md`.
4. `docs/ACTION_PLAN_2026-08-02.md`.
5. `docs/OPERATIONAL_FACTS.md`.
6. `docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.
7. `docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.
8. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
9. `docs/OPERATIONS_RUNBOOK.md` before any separately authorized operational
   change.

Before acting:

```powershell
git fetch --all --prune
git status --short --branch
git log -12 --oneline --decorate
git branch -vv
```

If the review branch is published later, switch to it and verify its remote
tip. If it still has no verified remote ref, do not recreate the corrections
from prose; return to the computer holding the branch or obtain an
owner-authorized push.

## 10. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/SESSION_HANDOFF.md,
docs/REVIEW_2026-08-11_BROKER_ACTIVITY_ACKNOWLEDGEMENT.md,
docs/ACTION_PLAN_2026-08-02.md, docs/OPERATIONAL_FACTS.md,
docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md,
docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/OPERATIONS_RUNBOOK.md completely. Verify Git topology and worktree before
acting. Main/origin-main is 24de4f5 and contains PR #188's uncorrected broker
activity acknowledgement implementation. The accepted correction is 74376e4
and its documentation commit is f7742bd on branch
codex/review-broker-activity-acknowledgement-20260811, which had no verified
remote ref when prepared; verify whether the handoff commit and branch were
published later. Six P2 and
two P3 findings were corrected; no P0-P3 issue remains open. Preserve untracked
ernkgjserng. Do not deploy PR #188 without the correction, and do not push,
merge, deploy, call the broker, acknowledge alerts, mutate tasks/database, or
roll an epoch without explicit owner authorization. Epoch-003 remains frozen
at deployed ef05dc1; deployment requires a complete separately authorized
epoch-004 transition.
```
