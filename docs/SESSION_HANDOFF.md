# Development session handoff

Prepared: 2026-08-02T21:43:40-07:00

Audience: Codex, Claude Code, and the repository owner after moving to another
computer.

Purpose: record the exact post-merge, independently re-reviewed GR-1C tree,
safety posture, Git state, local-data observations, and next step. This file
contains no secret values, brokerage account numbers, or licensed market data.
Every machine-local and time-sensitive statement must be verified after a
move.

## 1. Read this first

On the new computer, clone or update the repository and give either agent this
instruction:

```text
Read CLAUDE.md, docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/SESSION_HANDOFF.md completely before acting. Then read
docs/GENERAL_READINESS_STATUS.md, docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md,
and docs/ARCHITECTURE_DEBT.md. Establish the actual remote branches, HEAD,
worktree, Python version, ignored-data state, credential presence, paper-account
identity, and scheduler state. Preserve uncommitted work. Do not infer live
trading, model promotion, or autonomous execution authority. Report any drift
from the handoff before continuing. GR-1C is implemented and independently
reviewed; do not redo it. Finish the remaining GR-1 facade work before GR-2
unless the owner explicitly changes priority.
```

Initial commands:

```powershell
git fetch --all --prune
git status --short --branch
git log --all -20 --oneline --decorate
git branch --all --verbose
```

Do not reset, clean, delete, or overwrite a dirty worktree merely to reproduce
this snapshot.

## 2. Critical Git snapshot

Repository:

```text
https://github.com/SheltonChen2017/trading_agent.git
```

State after the independent follow-up review correction:

```text
origin/main and local main:
  2882889  Merge PR #110, Claude GR-1C review follow-ups

Original GR-1C implementation and review, pushed and merged:
  b4d9b1f  Claude validation extraction and dependency injection
  465df8d  Codex independent review corrections
  5750af3  review/handoff process documentation
  091efc2  Merge PR #109, reviewed GR-1C

Claude review-of-review follow-up, pushed and merged:
  branch: user/claude/gr-1c-review-followups-20260802
  implementation: 7058cb2
  handoff: b06a281
  merge: 2882889

Codex independent follow-up review branch, clean before this handoff edit:
  branch: codex/review-claude-gr1c-followups-20260802
  correction: c1de927  Complete independent GR-1C follow-up review
  status-doc correction: d2d836b  Correct GR-1C follow-up size accounting
  remote state: LOCAL ONLY, NOT PUSHED
```

The current Codex review branch is based on merged `main` `2882889`. It adds
only the independently verified compatibility/status corrections and this
handoff.
Do not redo or separately cherry-pick the earlier GR-1C commits when taking
this branch; they are already ancestors of `2882889`.

### Local-only strategy-tool document

A separate local branch existed on an earlier computer:

```text
branch: codex/ai-strategy-tool-doc-v2-20260802
commit: a656015  Document AI-driven strategy backtest tool
file: docs/AI_DRIVEN_STRATEGY_FORMING_TOOL_IMPLEMENTATION.md
recorded state: LOCAL ONLY, NOT PUSHED
```

Commit `a656015` is absent from this computer's Git object database and the
file is not in `origin/main`. The similarly named remote commit `929ba09` is a
different GR-1B follow-up and must not be mistaken for it. Retrieve the exact
commit from the earlier computer or a private bundle if it is still wanted;
do not recreate it from memory while an exact copy may exist elsewhere.

### Required action before abandoning the old computer

The following push has **not** been performed because the normal workflow
requires explicit owner authorization:

```powershell
git push -u origin codex/review-claude-gr1c-followups-20260802
```

The original GR-1C implementation, original review, Claude follow-up, and both
merges are already remote. Only Codex corrections `c1de927`/`d2d836b`, the
handoff commit after them, and the unavailable historical `a656015` require
separate treatment.

## 3. Relevant GR-1 commit history

Recent sequence:

```text
d2d836b  Codex: correct GR-1C follow-up size accounting (local)
c1de927  Codex: complete independent GR-1C follow-up review (local)
2882889  Merge PR #110: Claude GR-1C review follow-ups into main
b06a281  Claude: update session handoff after GR-1C review follow-ups
7058cb2  Claude: pin the injection boundary the original review left implicit
091efc2  Merge PR #109: reviewed GR-1C into main
5750af3  Codex: document mandatory review and handoff process
c280142  Codex: replace session handoff after reviewed GR-1C
465df8d  Codex: complete independent GR-1C review
b4d9b1f  Claude: GR-1C validation extraction and dependency injection
5dda78e  Merge PR #107: GR-1B follow-up review into main
9eaa06f  Codex: clarify GR-1B telemetry guard contract
```

Historical branch names are not instructions to resume obsolete work. The
active review branch and current status documents supersede the earlier GR-1A
and GR-1B handoff text.

## 4. GR-1C implementation and independent review

### Claude's implementation

Claude moved the 315-line body of
`validate_proposal_for_execution()` into:

```text
assistant/execution_kernel/validate.py::run_proposal_validation
```

The existing public function remains on `assistant.execution_service` as a
small wrapper. It constructs a frozen `ProposalValidationDeps` object inside
the wrapper on every call, using the facade's current module namespace. This
preserves the established behavior where tests or tooling can replace
`execution_service.validate_trade_intent` and have validation use the
replacement.

Claude also:

- moved `ProposalValidationOutcome` into the kernel and re-exported the exact
  same class object from the facade;
- deferred the broker import through an injected provider so early
  existence/expiry/policy failures retain their historical precedence;
- kept validation read-only with respect to proposal, reservation, telemetry,
  and broker-order state;
- added characterization, identity, export, and mutation-sensitive tests;
- reduced `assistant/execution_service.py` substantially; and
- updated `GENERAL_READINESS_STATUS.md` and `ARCHITECTURE_DEBT.md`.

Claude reported `2405 passed, 1 skipped, 25 warnings` on `b4d9b1f`.

### Independent review finding and correction

The architecture was sound, but the original dependency bundle did not fully
meet its own compatibility claim. Four runtime collaborators that the moved
body previously resolved from the facade still resolved inside the kernel:

```text
datetime     expiration and quote-receipt timestamps
Decimal      zero value for cumulative pending exposure
TradeIntent  normalization of open broker orders
to_decimal   conversion of cumulative batch exposure
```

Claude also removed the previously importable facade names `dataclasses` and
`Decimal` while documenting the facade import surface as a compatibility
contract.

The review added tests before correcting the code. On the exact uncorrected
Claude snapshot:

```text
3 focused tests failed:
  - patched facade TradeIntent/to_decimal did not reach the kernel;
  - patched facade datetime did not control validation time;
  - facade dataclasses/Decimal exports were missing.
```

Commit `465df8d`:

- adds all four collaborators to `ProposalValidationDeps`;
- routes both the expiration clock and quote-receipt clock through the injected
  facade `datetime`;
- routes open-order construction, decimal-zero construction, and conversion
  through the facade-built dependency object;
- restores exact `dataclasses` and `Decimal` facade exports;
- adds red/green characterization coverage;
- changes the validation description from **pure** to **read-only** because it
  reads durable state and performs broker preflight/quote queries; and
- records the independent-review corrections in the readiness documents.

Final exact sizes after review:

```text
assistant/execution_service.py:          1,090 lines
assistant/execution_kernel/validate.py:    462 lines
execute_approved_paper_proposal():         281 lines
reconcile_submission():                    221 lines
```

Assessment: Claude's GR-1C core design and extraction were strong, but the
claim that every runtime facade collaborator was injected was incomplete.
After correction, GR-1C is accepted. A fair quality assessment is about
8.5/10: strong architecture and testing, with a material but contained
compatibility miss caught during independent review.

### Review-of-review follow-ups (Claude, 2026-08-02, after the merge)

Branch `user/claude/gr-1c-review-followups-20260802`, commit `7058cb2`,
based on merged `main` (`091efc2`), pushed. Claude verified every review
change before acceptance: the four injections are complete for their
category, both new seam tests fail under reverse-mutation (each clock read
independently), and the facade-surface rule is internally consistent (`os`
was already dead at `d9e3196`, so the GR-1B removal survives the sharper
rule). Two precision gaps were closed:

- the "injected every runtime collaborator" claim was itself over-broad —
  `ProposalValidationOutcome`, `timezone`, and the `FAILURE_*` constants
  remain kernel-resolved, deliberately; the boundary is now documented in
  the `ProposalValidationDeps` docstring and enforced by a new exact
  two-sided AST allowlist guard over the body's module-global reads
  (mutation-verified in both regression directions); and
- the pure -> read-only sweep missed the `ProposalValidationOutcome` class
  docstring and a `test_personal_assistant.py` section comment (both
  comment-only).

Validation on that tree: `2408 passed, 1 skipped, 25 warnings`
(+1 = the AST guard), compileall clean, `git diff --check` clean.

### Independent review of Claude's follow-up (Codex, 2026-08-02)

Claude correctly identified that the earlier phrase "every runtime
collaborator" overclaimed what the seven-plus-four-field dependency bundle
enforced. Its terminology cleanup and reverse-mutation work were useful, but
the proposed allowlist was not compatible with GR-1's unchanged-facade
contract. Before extraction, the moved body resolved all of these names from
`assistant.execution_service`; after the follow-up, replacing them there no
longer changed validation:

```text
ProposalValidationOutcome  construction of every returned outcome
timezone                   UTC supplied to both validation clock reads
FAILURE_DATA_INTEGRITY     durable failure classification
FAILURE_INFRASTRUCTURE     durable failure classification
```

Three focused characterization tests failed red on the exact merged Claude
tree `2882889`: facade outcome replacement was ignored, facade timezone
replacement was ignored, and facade failure constants were ignored. This is a
P2 public-compatibility regression, not merely an imprecise description.

Correction `c1de927`:

- injects the facade's outcome factory, timezone object, and both
  behavior-bearing failure constants through `ProposalValidationDeps`;
- resolves `timezone.utc` inside the kernel at its historical point in the
  check order rather than evaluating it early in the wrapper;
- routes every outcome construction and validation failure classification
  through the injected bundle;
- replaces the non-empty allowlist with a zero-module-global invariant for
  `run_proposal_validation()`; and
- uses Python's symbol table for the structural guard, covering nested scopes
  and module globals that shadow builtins without the hand-rolled AST
  collector's false-negative cases.

The new guard was mutation-verified: restoring one direct kernel outcome
construction failed by naming `ProposalValidationOutcome`, then passed after
the correction was restored. Claude's follow-up is accepted after correction.
Quality assessment for the follow-up itself: **7.5/10** — strong diagnosis and
test intent, but a material compatibility exception was documented instead of
preserved and the claimed exact guard was not scope-exact.

Current exact sizes after `c1de927` (AST-inclusive function spans):

```text
assistant/execution_service.py:          1,094 lines
assistant/execution_kernel/validate.py:    479 lines
run_proposal_validation():                 294 lines
execute_approved_paper_proposal():         281 lines
reconcile_submission():                    221 lines
```

## 5. GR-1 status and the exact next development step

GR-1 is **partial**. GR-1A, GR-1B, and GR-1C are implemented and independently
reviewed, but `assistant.execution_service` is not yet the plan's thin
composition layer.

Completed and reviewed:

- characterization across all five public execution entry points;
- atomic conditional claim ownership remains in `AssistantStore`;
- outcome interpretation, intent parsing, revalidation inputs, claim fencing,
  submission sizing/dispatch, reservation handling, and shared exception
  definitions are in `assistant/execution_kernel/`;
- execution phases are named and their order remains explicit;
- telemetry failure cannot fall through into order submission;
- ambiguous broker outcomes keep budget reserved;
- replacement-chain identity and mismatch behavior remain fail-closed;
- exact exception identities and facade imports are pinned;
- validation orchestration now lives behind call-time dependency injection
  covering every facade-derived runtime name the moved body resolves; the
  kernel function has zero module-global runtime reads, pinned by a
  mutation-verified symbol-table guard; and
- execution-kernel import boundaries prevent direct or transitive reach into
  proposal-generation code.

Still on the facade:

- the 281-line execution composition;
- the 221-line manual `reconcile_submission()` workflow;
- stale reconciliation/claim recovery wrappers; and
- several compatibility exports and top-level composition responsibilities.

Recommended next milestone:

```text
GR-1D: extract manual reconciliation orchestration behind an explicit,
call-time dependency contract while preserving the public facade, exact
exception identities, broker-absence grace behavior, replacement-chain
handling, reservation holds/releases, kill-switch behavior, and every
existing monkeypatch/import seam.
```

Before implementing GR-1D:

1. read the complete GR-1 definition of done and current GR-1 status;
2. characterize every manual reconciliation branch in its current location;
3. enumerate every runtime global the body resolves from the facade, not only
   the helpers already monkeypatched in the suite;
4. compare the full pre/post facade import surface mechanically;
5. keep storage transactions and conditional transitions in `AssistantStore`;
6. mutation-test confirmed absence, unconfirmed lookup, fresh 404 grace,
   replacement chains, mismatches, journal failures, and state-race recovery;
7. run focused and full validation; and
8. stop for independent review.

After reconciliation extraction, reassess whether one final GR-1E is needed to
thin the 281-line execution composition and recovery wrappers. Do not begin
GR-2 merely because GR-1C is complete.

## 6. Non-negotiable safety boundaries

These rules apply to Codex, Claude, scripts, tests, UI work, and future plans:

- `config.PAPER_TRADING` remains `True`.
- Never operate a funded brokerage account without a new, explicit, narrowly
  scoped owner authorization.
- Every order remains subject to deterministic policy, fresh validation,
  durable idempotency, exact human approval, reservation accounting, and
  broker reconciliation.
- The atomic proposal claim remains a conditional storage operation. Never
  replace it with a service-layer read followed by a write.
- A timeout, network failure, or failed lookup is not proof of broker absence.
- Reserved budget is released only on paths where absence/failure is proven by
  the existing contract; ambiguous outcomes keep the hold.
- A mismatched order under this platform's idempotency key is a platform-halt
  anomaly, not an order to adopt automatically.
- Telemetry must be recorded before broker submission. Telemetry failure must
  not fall through into submission.
- ML and LLM output remains observation, research, explanation, or draft data
  only.
- No ML or LLM output may create, approve, size, submit, cancel, replace, or
  weaken a deterministic trading control.
- Missing, stale, invalid, corrupt, or unavailable AI output is equivalent to
  no AI output.
- AI failure must not stop reconciliation or a legitimate risk-reducing sale.
- Backtests, fixture success, software completion, and shadow predictions do
  not establish market edge or grant promotion authority.
- No UI toggle may enable live trading or autonomous execution.

Read `CLAUDE.md` completely. Its Git, testing, data, safety, and handoff rules
apply equally to both agents.

## 7. Final reviewed validation baseline

Environment used by Codex:

```text
Python 3.12.13 in .venv
```

This matches the project-preferred reconstruction command. The earlier GR-1C
review also passed under Python 3.13.14; preserve both observations rather than
silently assuming all future supported-version runs are equivalent.

Focused GR-1C/execution suite:

```text
402 passed in 58.80 seconds
```

This focused set covered validation, submission characterization,
reconciliation, replacement chains, reservations, telemetry, transaction
readiness, broker isolation, the execution gate, and import boundaries.

Full suite:

```text
2411 passed, 1 skipped, 26 warnings in 166.45 seconds
```

Additional gates:

```text
compileall: clean
git diff --check: clean
review branch: clean before editing this handoff
mutation: direct kernel outcome construction detected, then restored green
```

The warnings were non-failing third-party/environment notices. Do not convert
the count into a readiness claim; the behavioral invariants and red/green
regressions above are the meaningful evidence.

Required validation command pattern:

```powershell
New-Item -ItemType Directory -Force .venv\codex_test_tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings --cache-clear --basetemp=.venv\codex_test_tmp\full
.\.venv\Scripts\python.exe -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

`tests/conftest.py` isolates pytest from the operator database and inherited
broker credentials. Preserve that protection.

## 8. Current machine-local operational snapshot

Captured on this computer during handoff preparation. Recheck after stopping
all writers and again after restoring on the new computer.

### Operator database

```text
path: C:\git\customizedagent\trading_agent\data\trading_assistant.db
size: 2,920,448 bytes
last database-file write UTC: 2026-08-01T20:08:24Z
WAL: present, 0 bytes
SHM: present, 32,768 bytes
SHA-256: 02D468223C5BBB14EF7F90BBF283D737772345F13E392846E29E0206EEEBD69F
PRAGMA quick_check: ok
```

Selected row counts:

```text
decision_packets:               277
trade_proposals:                 31
portfolio_equity_snapshots:     118
portfolio_position_snapshots:     0
paper_account_observations:        0
paper_evidence_epochs:             0
ml_evidence_epochs:                0
broker_orders:                     0
broker_order_events:               0
execution_reservations:            0
operational_alerts:                0
operational_drill_runs:             0
```

This differs from the prior snapshot and should not be silently combined with
it. No paper-evidence epoch has started here, and no broker lifecycle or
reservation evidence exists in this database. The hash identifies the main
database file at the instant measured; it is not a transfer-backup hash.

The database is Git-ignored. Stop Streamlit, tests, schedulers, paper
operations, and other writers before making a transfer backup. Prefer the
documented SQLite backup/restore workflow over copying a live file. Recompute
the hash of the actual backup; the value above identifies only this snapshot.

After restore:

1. verify the transfer hash;
2. run SQLite integrity/quick checks;
3. confirm the expected paper account identity without printing credentials;
4. reconcile the ledger against Alpaca paper state;
5. run operational health/readiness checks; and
6. confirm development/tests use a separate database.

### Credentials

Presence only; no values were read or recorded:

```text
APCA_API_KEY_ID         process=True   user=False
APCA_API_SECRET_KEY     process=True   user=False
DATABENTO_API_KEY       process=True   user=False
ANTHROPIC_API_KEY       process=False  user=False
FINNHUB_API_KEY         process=False  user=False
```

Recreate required secrets through a secure mechanism. Start a new terminal or
agent process so it inherits them. Confirm Alpaca points to the intended paper
account. Never paste values into this document, Git, logs, screenshots, or
issue comments.

### Scheduler

```text
Scheduler state could not be verified: Get-ScheduledTask returned Access denied.
```

Do not infer either installed or absent tasks from that failed query, and do
not assume paper or ML evidence collection is running. Recheck in an elevated
operator session. Install tasks only through reviewed scripts with explicit
repository, Python, database, config, artifact, and alert paths, then verify
`LastTaskResult` and owner-visible delivery.

### Databento artifacts

```text
artifacts/databento/: present (4 files; contents not inspected or recorded here)
DATABENTO_API_KEY: present in this process; value not read
```

Presence does not establish provenance, completeness, or authoritative
point-in-time coverage. Inventory licensed artifacts privately with exact
manifests and hashes before relying on or transferring them; never commit
licensed contents.

### Paper mode

```text
config.py: PAPER_TRADING = True
```

Do not change it as part of environment reconstruction or GR-1 work.

## 9. ML and evidence posture

The ML subsystem is substantial but remains non-authoritative and isolated
from execution authority.

High-level state:

| Area | State |
|---|---|
| Experiment/evaluation contracts | Built |
| Point-in-time data contracts | Built; real authoritative coverage absent |
| Immutable experiment orchestration | Built |
| Volatility/portfolio research software | Built; real evidence underfilled |
| Earnings/filing research software | Built; authoritative event data absent |
| Supervised-volatility shadow runtime | Built, observational only |
| Monitoring/dossier software | Built |
| Read-only ML presentation | Built |
| Promotion registry/bounded adapter | Not implemented or authorized |
| Limited-capital canary | Not authorized |
| Execution-quality modeling | Deferred pending representative order data |
| Paper evidence cadence on this machine | Not deployed |

Yfinance remains exploratory and must not be represented as authoritative
point-in-time evidence. Databento market data alone does not provide historical
strategy/index membership. Raw as-printed prices require vintage-correct
corporate-action handling; splits must not be treated as genuine returns.

Do not begin ML promotion, bounded adapters, or a funded canary merely because
software scaffolding exists. Real-data lineage, untouched confirmation,
paper-evidence duration/counts, monitoring, reconciliation, drills, and a
separate owner decision remain mandatory.

## 10. Product and design documents

### UI feature controls

`docs/UI_FEATURE_CONTROLS_DESIGN.md` is present on the active tree. It is a
design document only. It covers:

- UI controls for `enable_strategy_proposals` and `allow_new_positions`;
- read-only secret/provider availability instead of exposing API key values;
- optional AI feature preferences; and
- a dedicated, research-only ticker-suggestions surface.

It does not authorize a live toggle, secret editing in Streamlit, autonomous
approval, or direct suggestion-to-proposal conversion.

### AI strategy authoring

`docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` is the comprehensive
long-term roadmap. Many prerequisites already exist—backtest engines, research
reports, manifests, LLM provider/auditing, ML experiments, and hand-coded
strategies—but the actual product chain is not implemented:

```text
owner prose -> restricted StrategySpec -> deterministic compiler/interpreter
-> generic backtest adapter -> persisted run -> Backtest UI page
```

The narrower product draft is in local-only commit `a656015`, described in the
Git section above. No strategy-language, compiler, authoring workflow, generic
adapter, job runner, or Backtest page has been implemented.

### Proposal history cleanup

`docs/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` remains planning only.
No destructive cleanup should be inferred or performed from the existence of
that plan.

Do not mix these product plans into the active execution-kernel split unless
the owner explicitly changes priority.

## 11. Files and documents to read in order

For the next coding session:

1. `CLAUDE.md`
2. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
3. `docs/SESSION_HANDOFF.md`
4. `docs/GENERAL_READINESS_STATUS.md`
5. `docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`
6. `docs/ARCHITECTURE_DEBT.md`
7. `assistant/execution_service.py`
8. every file under `assistant/execution_kernel/`
9. `tests/test_execution_characterization.py`
10. reconciliation, replacement-chain, transaction-readiness, telemetry, and
   import-boundary tests
11. `docs/ML_IMPLEMENTATION_STATUS.md`
12. `docs/ML_FULL_SYSTEM_EXECUTION_PLAN.md`
13. `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`
14. `docs/OPERATIONS_RUNBOOK.md`
15. `docs/LIVE_PROMOTION_CHECKLIST.md`
16. `docs/DATABENTO_DATA_SOURCE.md`
17. `docs/UI_FEATURE_CONTROLS_DESIGN.md`
18. `docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md`
19. the focused AI strategy-tool document if branch `a656015` was transferred

The current code and latest specific status section override stale historical
statements in older documents. Update stale text rather than reimplementing
completed work.

## 12. Private transfer checklist

Git does not transfer ignored or host-level state. Before leaving the old
computer, stop writers and privately inventory/transfer as applicable:

- a consistent backup of `data/trading_assistant.db`;
- any licensed Databento raw files and manifests from another machine;
- ML datasets, model artifacts, monitoring reports, dossiers, and shadow
  configurations that are intentionally ignored;
- alert JSONL, heartbeat, backup, restore, and drill evidence;
- local policy/mandate/config files not tracked by Git;
- scheduled-task definitions and service-account requirements;
- the local-only Git branches named in section 2; and
- credentials via a secret manager or manual recreation, never this file.

Use encrypted storage or direct trusted-device transfer. Do not copy `.venv`,
`.pytest_cache`, `__pycache__`, or temporary test directories.

## 13. Environment reconstruction

Preferred clean setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

If the project intentionally standardizes on Python 3.13 instead, record that
decision and rerun the full suite rather than relying on this machine's result.

After restoring machine-local state and verifying paper mode:

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/personal_assistant_ui.py
```

Do not let UI/development tests share the restored operational database.

## 14. Owner workflow preferences

- Codex and Claude may alternate implementation and independent review.
- When reviewing Claude, verify the exact commit, reproduce findings, correct
  confirmed defects where practical, and give a genuine 1-10 assessment.
- Commit review fixes unless the owner says not to; branch first when on main.
- Preserve unrelated/uncommitted work in the shared worktree.
- Do not push, merge, or open a pull request unless explicitly requested.
- Use one coherent milestone per branch and stop after independent review.
- Do not call a milestone complete because files or commands exist; verify its
  definition of done and failure directions.
- Prefer red/green characterization and mutation evidence over raw test count.
- Explain complex roadmap items in plain language when asked.

## 15. Decisions still requiring the owner

Do not infer answers to these:

1. Authorization to push/merge local review branch
   `codex/review-claude-gr1c-followups-20260802` after its handoff commit.
2. Whether to retrieve unavailable local-only strategy-tool commit `a656015`
   from the earlier computer or a private bundle.
3. When to begin GR-1D and whether reconciliation is the selected next slice.
4. Which authoritative historical membership/reference-data source will be
   obtained and funded.
5. When to deploy the operational paper cadence and start the first immutable
   evidence epoch.
6. Which owner-visible delivery channel GR-5 should implement and verify.
7. Whether and how to handle historical operator-database contamination or
   divergent snapshots after backup and provenance analysis.
8. When an elevated Windows deployment/credential-rotation window is
   available.
9. When, if ever, AI strategy authoring, proposal-history cleanup, ranker work,
   promotion adapters, or funded-account work should supersede readiness work.

None of these decisions grants live or funded-account authority by
implication.

## 16. Exact resume sequence on the new computer

If the Codex follow-up review branch was pushed:

```powershell
git fetch --all --prune
git switch --track origin/codex/review-claude-gr1c-followups-20260802
git status --short --branch
git log -6 --oneline --decorate
```

Verify that history contains merged main `2882889`, Codex corrections
`c1de927`/`d2d836b`, and the later handoff commit containing this file. Then
rerun focused/full tests in the reconstructed environment before merging.

If the Codex branch is not remote, it remains local to the computer that
created this handoff. Push it with owner authorization or transfer it as a Git
bundle before that object database is lost. Claude's follow-up and all earlier
GR-1C work are already merged in `origin/main`.

Recommended resume prompt:

```text
Read CLAUDE.md, docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/SESSION_HANDOFF.md completely. Verify origin/main and all branch/commit
claims against Git. GR-1C through Claude follow-up merge 2882889 and Codex
follow-up corrections c1de927/d2d836b are complete; do not redo them. Confirm
whether the Codex review/handoff branch was pushed or merged. Preserve facade
imports and complete call-time DI, including the outcome factory, datetime,
timezone, Decimal, TradeIntent, to_decimal, and behavior-bearing failure
constants. Verify paper mode,
database isolation, credential presence without values, scheduler state, and
ignored artifact transfer. Do not start live trading, an evidence epoch,
scheduled tasks, ML/LLM proposal integration, or destructive cleanup. If the
owner authorizes the next coding milestone, perform a gap analysis for GR-1D
manual reconciliation extraction, add characterization first, implement one
reviewable slice, run focused/full validation, commit, and stop for independent
review before GR-2.
```
