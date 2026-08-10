# Session handoff — reviewed broker dividend handler

Prepared: 2026-08-10, after independent review and correction, then
Claude's counter-review (section 1a), which **accepted all six findings**
and **corrected two residual defects inside the correction itself**.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Resume state and remote warning

The canonical base is merged `main` / `origin/main` at `c36b615`. Claude's
implementation branch `user/claude/broker-dividend-handler-20260810` is
published at exact commit `25a2e7b`. The active checkout is the review branch
`codex/review-broker-dividend-handler-20260810`, with correction commit
`a6770f7` followed by the documentation/handoff commit containing this file.

**REMOTE WARNING:** The review branch exists only in this checkout. The owner
has not authorized publication. A different computer will not receive these
corrections from an ordinary fetch until the branch is published. Do not
recreate the corrections from memory; continue on this exact history after it
is made available.

No push, merge, pull request, deployment, scheduler change, broker call,
order submission, operator-database mutation, policy change, alert
acknowledgement, or epoch transition was authorized or performed by Codex in
this review. The two ignored local swap-result JSON files remain machine-local
and must not be staged, printed, or deleted.

## 1. Review outcome

Review range: `c36b615..25a2e7b` (one commit).

| Commit | Disposition | Result |
|---|---|---|
| `25a2e7b` | **Accepted after correction** | Sound primitive reuse and idempotency foundation, but five P2 accounting defects and one P3 date/documentation defect required correction in `a6770f7`. |

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Final state | Finding |
|---|---|---|---|
| DHREV-001 | P2 | Closed | Dividend/cash-flow events used creation/bootstrap timestamps rather than economic activity dates, corrupting tax-year or return-interval attribution. |
| DHREV-002 | P2 | Closed | Every `DIV` subtype was treated as cash; `SDIV` stock and `SPD` substitute payments now refuse. |
| DHREV-003 | P2 | Closed | Generic JNLC was guessed to be contributed capital; it now remains fail-closed. |
| DHREV-004 | P2 | Closed | Optional non-USD amounts were posted to USD accounts; they now refuse. |
| DHREV-005 | P2 | Closed | One raw broker ID could be reinterpreted across activity types, including a partial same-batch write; preflight and stored-ID checks now prevent it. |
| DHREV-006 | P3 | Closed | AEP's dates were one day early in tests and current documents. |

Full evidence and corrections are in
`docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.

## 1a. Counter-review (Claude, same day) — accepted, two residuals fixed

Claude restored the submitted `25a2e7b` ledger in place and ran the
review's regressions against it: **all eleven intended cases failed red**,
so every finding is independently confirmed. The real tree was restored
from a byte copy and re-verified green. `DHREV-006` was settled decisively
and without relying on either party's source: **2026-08-09 is a Sunday**,
so it cannot be an ex-dividend date — Claude's submitted dates came from
`yfinance`'s `calendar` field, which was one day early on both dates, and
the issuer dates (Monday 2026-08-10 record/ex, Thursday 2026-09-10
payable) are correct.

Two residual defects were then found **inside the correction** and fixed
in the counter-review commit:

- **DHCR-001 (P2)** — the correction rightly replaced fetch timestamps
  with the provider's activity date, but stamped that bare date at **UTC**
  midnight, which is the previous evening in New York. Every consumer
  buckets in market-local time, so it lands on the wrong side of two
  boundaries, both reproduced rather than reasoned about: (1) under US
  **standard time** the 16:30 Pacific capture falls at `00:30Z` the next
  day, so a flow dated `D` stamped `D 00:00Z` is counted in the
  **previous session's** return interval by
  `paper_evidence._net_external_flow` — the deposit-as-return hazard GR-7c
  already closed once; (2) `tax_year_of(2027-01-01T00:00:00+00:00)`
  returns **2026**, exactly the failure `tax_reporting.py`'s own docstring
  warns about. Fixed by stamping market-local midnight using
  `MARKET_TIMEZONE` imported from `assistant.tax_lots` — one definition,
  imported rather than restated (FCS-016), so the zone that stamps a date
  is provably the zone that buckets it. New coverage: DST-parametrized
  stamping (EDT/EST), plus behavioral tests through the real
  `_net_external_flow` and `tax_year_of` consumers.
- **DHCR-002 (P3)** — `_assert_broker_activity_id_not_retyped` indexed a
  hand-maintained literal dict by activity type, which had to stay in sync
  with a separate handled-types literal. A future type added without a
  prefix raises `KeyError`, which is **not** a `LedgerError` and so
  escapes the per-row refusal handler as an unhandled crash instead of a
  clean fail-closed refusal. Fixed by deriving `_HANDLED_ACTIVITY_TYPES`
  from `_ACTIVITY_EXTERNAL_ID_PREFIXES` (drift now structurally
  impossible) and refusing with a `LedgerError`.

Four mutations, each restored and re-verified: reverting to UTC midnight
turns 7 tests red including both behavioral consumer tests; restoring the
hard dict index reproduces the `KeyError`; removing Codex's cross-type ID
guard and disabling its DIV subtype gate each turn their own tests red,
proving those guards load-bearing.

**CR-W3 (new watch item, recorded not fixed):** the DIV subtype allowlist
accepts only an absent subtype or explicit `CDIV`. No `DIV` activity has
ever appeared on this account, so the subtype the real AEP payment will
carry is unverified. If it carries anything else, that night's observation
fails closed and **names the subtype in the refusal**, and the fix is a
small reviewed allowlist addition. Over-refusing is the correct failure
direction, but expect it as a possibility around 2026-09-10 rather than
be surprised by it.

## 2. Completed behavior and deliberate limitations

`sync_broker_activities()` now supports exactly these USD mappings:

- FEE → the existing idempotent fee journal path;
- legacy plain DIV or explicit CDIV → `record_dividend()`, with tax
  classification recorded as `unknown`; and
- explicit CSD deposit / CSW withdrawal → `record_cash_transfer()`, with
  direction and sign checked.

Dividend and external-flow accounting use the broker activity/settlement
date. `created_at` remains the inclusion boundary after ledger bootstrap and
is only a fallback economic timestamp when the activity date is absent and a
real creation timestamp exists. Optional currency must be USD. Both subtype
field spellings are supported; conflicts refuse. Conflicting reuse of a raw
broker ID is detected before a response can partially post.

Deliberately unsupported and loud: JNLC generic cash journals, SDIV stock
dividends, SPD substitute payments, interest, withholding, return of capital,
capital-gain distributions, non-USD amounts, and unknown activity shapes.
JNLC does not prove owner contribution/withdrawal treatment. Never clear one
with a manual compensating row or wider reconciliation tolerance.

AEP's official schedule is record/ex-date **2026-08-10**, payable
**2026-09-10**, **$0.95/share**. For 39 eligible shares the arithmetic would
be $37.05, but this development review did not call Alpaca and does not assert
account entitlement or payment receipt.

## 3. Operational truth measured read-only

At 2026-08-10 15:21 Pacific, the separate operational checkout was clean on
`main` at exact deployed commit `ef05dc1`. It remains the Epoch 3 runtime and
does **not** contain the dividend-handler branch.

- `paper-epoch-001` and `paper-epoch-002` are closed.
- `paper-epoch-003` is the only active epoch, with 5/5 required drills and 0
  observations at measurement time.
- Latest reconciliation was matched with zero mismatches; the operations
  heartbeat was healthy.
- One open critical `portfolio_accounting` alert remained. Its stored message
  itself says matched with zero mismatches, so it is a retained/reopened alert
  record rather than evidence of a current mismatch. Codex did not acknowledge
  or mutate it.
- OperationsCycle, PaperObservation, and Watchdog were enabled/Ready or
  running as expected. OrderMonitor was running. The first scheduled
  epoch-003 PaperObservation was due at 16:30 Pacific; do not claim evidence
  accumulation until its successful row and lineage are checked read-only.

Do not deploy into epoch-003. A future deployment of this reviewed handler
requires explicit owner authorization and the full runbook sequence for an
epoch-004 transition. Until then, deployed `ef05dc1` still refuses DIV,
JNLC, CSD, and CSW. After deployment, JNLC will continue to refuse by design.

## 4. Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Claude's submitted affected set: 125 passed in 13.57s.
- Submitted-tree review regressions reproduced all eleven intended defect
  cases after two review-fixture argument names were corrected.
- Corrected broker-activity group: 30 passed, 26 deselected in 8.19s.
- Corrected affected ledger/CLI/reporting/document batch: 147 passed in
  19.43s.
- Active-document consistency after final edits: 11 passed in 0.25s.
- Full suite: **3,357 passed, 0 failed, 0 skipped** — A–F 1,033 in 138.10s;
  G–M 1,025 in 223.96s; N–S 1,010 in 146.35s; T–Z 274 in 202.12s; nested
  fault matrix 15 in 7.66s. The 25 warnings are existing dependency
  deprecations (one websockets and 24 joblib/NumPy).
- Repository-prescribed compile check: clean.
- Diff checks: clean apart from ordinary Windows line-ending notices.
- Non-printing secret-shape scan of every changed file: zero matches.

No validation made a live Alpaca request or mutated the operational database.

**Counter-review validation (final tree).** Single uninterrupted full-suite
run: **3,364 passed, 0 failed, 25 warnings** in 698.62s — Codex's 3,357
plus the seven counter-review regressions. Ledger suite 63 passed.
Import-boundary and decimal-guard suites re-run because this correction adds
a package dependency (`assistant.portfolio_ledger` → `assistant.tax_lots`
for `MARKET_TIMEZONE`): **11 passed**. `compileall` clean; `git diff --check`
clean. The full-suite run covered the final *code* tree; the documentation
edits that followed touch only documents, and all four document-reading
suites were re-run afterwards (**43 passed**), so no assertion is validated
against a stale tree. Red baseline: the submitted `25a2e7b` ledger was
restored in place and the review's regressions run against it — 11 failed,
1 passed (the explicit-CDIV case, which correctly passes on both trees) —
then restored from a byte copy and re-verified green.

## 5. Exact next step

1. Commit this review report, milestone record, regression guard, and handoff
   separately from correction `a6770f7`.
2. Stop. Publication, merge, deployment, and epoch transition require the
   owner's explicit instruction.
3. Operationally, verify the first scheduled epoch-003 observation read-only
   after it runs. Do not manually create evidence or acknowledge the retained
   alert as part of this development review.

## 6. Non-negotiable boundaries

- Paper only; live trading remains prohibited.
- Exact human approval, deterministic validation, broker preflight, kill
  switch, and account binding remain mandatory.
- LLM/ML output is observational and cannot approve, size, submit, or promote
  trades.
- Do not change policy, strategy, model, code, scheduler, or account lineage
  inside an active evidence epoch.
- Do not insert observations, drills, ledger rows, or alert state manually.
- Do not infer a generic cash journal's accounting meaning.

## 7. Required reading order

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/SESSION_HANDOFF.md`.
3. `docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.
4. `docs/OPERATIONAL_FACTS.md`.
5. `docs/ACTION_PLAN_2026-08-02.md`.
6. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
7. `docs/OPERATIONS_RUNBOOK.md`.

Before acting, verify:

```powershell
git status --short --branch
git log -6 --oneline --decorate
git branch -vv
```

## 8. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/SESSION_HANDOFF.md,
docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md,
docs/OPERATIONAL_FACTS.md, docs/ACTION_PLAN_2026-08-02.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/OPERATIONS_RUNBOOK.md completely. Verify branch, HEAD, remote
availability, and worktree state before acting. Claude's dividend-handler
commit 25a2e7b was accepted after correction a6770f7 on the review branch.
The supported scope is USD plain/CDIV cash dividends and explicit CSD/CSW;
JNLC, stock/substitute dividends, non-USD money, and unimplemented tax forms
remain fail-closed. The review branch has not been published or deployed.
Epoch-003 remains active on deployed ef05dc1; do not alter it or claim evidence
is accumulating until its scheduled observation is verified read-only. Do not
push, merge, deploy, mutate tasks/database/alerts, call the broker, or roll an
epoch without explicit owner authorization.
```
