# Session handoff — dividend counter-review and AP-7 correction

Prepared: 2026-08-10 after post-merge independent review

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Current repository and remote state

Merged `main` / `origin/main` is `0ee3a22` (PR #184), containing the complete
CR-W2 chain through Claude's counter-review. Claude's pushed follow-up branch
`user/claude/epoch-003-first-observation-20260810` ends at `f852a69`. The
active checkout is `codex/review-dividend-counterreview-20260810`, with AP-7
correction `89ebcc2` followed by the review/handoff commit containing this
file.

**REMOTE WARNING:** This review branch exists only in the current checkout.
The owner has not authorized publication. Another computer will not receive
the AP-7 correction or this refreshed handoff from an ordinary fetch until the
branch is published. Do not recreate them from memory.

The worktree is expected clean after the final documentation commit. Two
ignored machine-local swap-result JSON files remain preserved; do not stage,
print, move, or delete them. No push, merge, deployment, epoch transition,
scheduler mutation, alert acknowledgement, broker call, order action, policy
change, or operator-database write was performed in this review.

## 1. Exact review scope and outcome

Review range: `a36d75d..f852a69`.

| Commit | Disposition | Result |
|---|---|---|
| `cf9cdc2` | **Accepted after correction** | Claude's market-timezone and clean-prefix-refusal code fixes are correct. Current documentation now synchronizes both milestone audiences and removes an unsupported yfinance-cause claim. |
| `b8f20bb` | **Accepted** | Correct publication state at that historical point; its merge-next instruction is now superseded. |
| `0ee3a22` | **Accepted** | PR #184 merge has no merge-only tree difference from reviewed parent `b8f20bb`. |
| `f852a69` | **Accepted after correction** | First-observation/AP-7 measurements are sound, but AP-7 was under-ranked/unfixed and the appended handoff retained stale topology/evidence instructions plus exact private balances. |

Correction: `89ebcc2` (`Fix concurrent operational freshness checks`).

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Final state | Finding |
|---|---|---|---|
| DCCR-001 | P2 | Closed | AP-7 reused an entry clock after concurrent state writes, causing false critical/warning freshness failures; the safe post-read-clock fix is now implemented without relaxing true future-date refusal. |
| DCCR-002 | P2 | Closed | The canonical handoff retained obsolete base, branch, merge, publication, and zero-evidence instructions. |
| DCCR-003 | P2 | Closed | The handoff published exact private account cash and equity balances. |
| DCCR-004 | P3 | Closed | Action-plan evidence/merge state and the milestone's two audience paragraphs disagreed; one provider-cause claim was unsupported. |

Full evidence is in
`docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.

## 2. Accepted dividend-handler behavior

Merged PR #184 supports only USD fees, legacy plain or explicit-CDIV cash
dividends, explicit CSD deposits, and explicit CSW withdrawals. Dividend tax
classification remains `unknown`. Bare activity dates use New York
market-local midnight so return intervals and tax years agree. Currency,
subtype, signs, arithmetic, and broker-event identity fail closed.

JNLC generic cash journals, SDIV stock dividends, SPD substitute payments,
interest, tax-specific distribution variants, non-USD amounts, and unknown
shapes remain unsupported and loud. Do not create a compensating row or widen
reconciliation tolerance. CR-W3 remains a watch item: the first real account
dividend may carry a subtype other than absent/CDIV and over-refuse while
naming it. That is safer than guessing.

The handler is merged but **not deployed**. The operational host remains on
`ef05dc1`, which still refuses DIV, JNLC, CSD, and CSW. Any authorized
epoch-004 deployment should complete before the scheduled **2026-09-10** AEP
payment while preserving the full transition sequence.

## 3. AP-7 correction

The deployed health check can intermittently read a reconciliation committed
after its entry-time clock, making a matched zero-mismatch row look
future-dated. The same generalized race exists for backup and restore-drill
facts. This produces conservative false failures, can make OperationsCycle
nonzero, and counts an open critical alert against promotion.

Development correction `89ebcc2` captures the comparison clock immediately
after each stored fact is read and includes signed `age_seconds` in health
details. A caller-supplied as-of clock stays frozen, so genuine future rows
still fail closed. No grace period or negative-age clamp was introduced.
This is not deployed and does not alter epoch-003.

## 4. Operational truth remeasured read-only

At approximately 16:56 Pacific:

- `paper-epoch-001` and `paper-epoch-002` were closed;
- `paper-epoch-003` was the only active epoch at deployed `ef05dc1`, with one
  observation for 2026-08-10 and five required drills;
- the observation's capture-time lineage matched the epoch and its ledger
  mismatch count was zero;
- the five latest reconciliations were matched with zero mismatches;
- PaperObservation and OperationsCycle last returned success; OrderMonitor and
  Watchdog were running under their singleton schedule; and
- one open critical `portfolio_accounting` AP-7 alert remained. The latest
  operations heartbeat was healthy with zero failed checks and zero new
  alerts. The alert was not acknowledged or otherwise mutated.

The evidence clock has genuinely started at one session. No exact account
identifier, balance, equity, or private payload belongs in this handoff.

## 5. Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted-tree red regressions: 3 failed as intended (AP-7 race, stale
  handoff, private balances).
- Corrected operational suite: 9 passed in 2.84s.
- Focused counter-review/AP-7 affected suite: 191 passed in 51.62s.
- Active-document consistency after final edits: 13 passed in 0.18s.
- Full suite: **3,367 passed, 0 failed, 0 skipped** — A–F 1,035 in 163.08s;
  G–M 1,025 in 204.90s; N–S 1,018 in 134.38s; T–Z 274 in 199.47s; nested
  fault matrix 15 in 6.63s. The 25 warnings are existing dependency
  deprecations (one websockets and 24 joblib/NumPy).
- Repository-prescribed compile check: clean.
- Diff check: clean apart from expected Windows line-ending notices.
- Non-printing secret/private-balance shape scan of every changed file: zero
  matches.

No test used live broker credentials or mutated the operator database.

## 6. Exact next step

1. Commit the review report and this handoff separately from correction
   `89ebcc2`.
2. Stop. Push and merge require explicit owner authorization.
3. If the owner later authorizes deployment, follow the complete runbook:
   disable tasks, close epoch-003 on its frozen runtime, deploy the reviewed
   merge, reconcile matched, run readiness, start epoch-004, record all five
   drills, re-enable tasks, and verify. Do not patch epoch-003 in place.

## 7. Non-negotiable boundaries

- Paper only; live trading remains prohibited.
- Exact human approval, deterministic validation, broker preflight, kill
  switch, account binding, and ambiguous-outcome reconciliation remain
  mandatory.
- ML/LLM output remains observational and cannot approve, size, submit, or
  promote trades.
- Do not change code, policy, strategy, model, scheduler, or account lineage
  inside an active evidence epoch.
- Do not manually insert observations, drills, ledger rows, or alert state.
- Do not infer accounting meaning from a generic cash journal.

## 8. Required reading order

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/SESSION_HANDOFF.md`.
3. `docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.
4. `docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.
5. `docs/OPERATIONAL_FACTS.md`.
6. `docs/ACTION_PLAN_2026-08-02.md`.
7. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
8. `docs/OPERATIONS_RUNBOOK.md`.

Before acting:

```powershell
git status --short --branch
git log -8 --oneline --decorate
git branch -vv
```

## 9. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/SESSION_HANDOFF.md,
docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md,
docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md,
docs/OPERATIONAL_FACTS.md, docs/ACTION_PLAN_2026-08-02.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/OPERATIONS_RUNBOOK.md completely. Verify Git topology, remote
availability, and worktree state before acting. PR #184 merged the CR-W2
dividend handler at 0ee3a22. Claude's counter-review corrections were accepted;
post-merge correction 89ebcc2 closes the AP-7 concurrent-freshness race and
remains only on the local Codex review branch. Epoch-003 remains active on
deployed ef05dc1 with one lineage-matched observation; do not modify it or
acknowledge its AP-7 alert. Do not push, merge, deploy, mutate tasks/database,
call the broker, or roll an epoch without explicit owner authorization.
```
