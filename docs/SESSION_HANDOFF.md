# Development transition handoff

Prepared: 2026-08-02, approximately 11:30 America/Los_Angeles

Purpose: transfer the durable development, safety, Git, data, and operational
context for this repository to another computer. This document intentionally
contains no API keys, brokerage secrets, account numbers, or licensed market
data. Verify every time-sensitive statement after cloning.

## 1. Start here on the new computer

Clone or update the repository, fetch every remote branch, and open the
repository root in Codex or Claude Code. Then use this prompt:

```text
Read CLAUDE.md and docs/SESSION_HANDOFF.md completely. Then read the current
status and implementation documents named in the handoff. Establish the real
Git branch, commit, worktree, local-data, credential, scheduler, and paper
account state before changing anything. Preserve all uncommitted work. Preserve
the ML/LLM observation-only boundary and the exact human approval requirement.
Do not infer live-trading or model-promotion authority from software completion.
Report drift from the handoff and any missing machine-local prerequisites before
continuing the requested milestone.
```

Do not assume the original Codex task or Claude session will synchronize. The
repository, this file, pushed feature branches, and a separately encrypted
transfer of ignored operational data are the durable continuation mechanism.

Initial Git checks:

```powershell
git fetch --all --prune
git status --short --branch
git log -15 --oneline --decorate
git branch --all --verbose
```

The transition branch is:

```text
codex/transition-handoff-20260802-computer-move
```

If it has not been merged into `main`, read or check it out explicitly:

```powershell
git switch --track origin/codex/transition-handoff-20260802-computer-move
```

Do not reset a newer or dirty worktree merely to reproduce this snapshot.

## 2. Authoritative repository snapshot

- Repository: `https://github.com/SheltonChen2017/trading_agent`
- Reviewed and merged base: `6699633`
- Base subject: merge of PR #101, containing the reviewed first GR-1 execution
  kernel extraction.
- `origin/main` pointed to `6699633` when this handoff worktree was created.
- Transition branch base: exactly `6699633`.
- Transition branch: `codex/transition-handoff-20260802-computer-move`.
- The transition commit changes only `docs/SESSION_HANDOFF.md`.
- Python used for the last reviewed full run: 3.12.13 in `.venv`.

Important commits in the current GR sequence:

```text
c8cbf4e  Claude's unmerged remaining-kernel extraction; independent review pending
6699633  Merge PR #101 (reviewed outcome extraction into main)
be5429e  Harden GR-1 execution-kernel boundary
9eb0e3d  Extract broker outcome interpretation into execution_kernel/outcomes.py
dd17a94  Close real concurrent-claim characterization gap
4d60e90  Characterize confirmed-absence release; correct overstated gap
3f8c604  Record the GR-1A mutation coverage and honest limits
df297d5  Close two characterization mutation gaps
c54b165  Extend GR-1A execution characterization
e8b2980  Initial partial GR-1A characterization
2d5f096  Merge reviewed GR-0 platform readiness
2649184  Correct GR-0 readiness classifications
f4f911d  Build GR-0 five-dimension platform readiness
```

## 3. Claude's next GR-1 extraction is pushed but unreviewed

Claude completed and pushed the next extraction while this handoff was being
prepared:

```text
branch: user/claude/gr-1a-extract-kernel-modules-20260802
commit: c8cbf4e5b8fea452e8ab88ae826f8983dff4c30e

changed:
  assistant/execution_service.py
  tests/test_execution_characterization.py
  assistant/execution_kernel/claim.py
  assistant/execution_kernel/errors.py
  assistant/execution_kernel/intents.py
  assistant/execution_kernel/revalidate.py
  assistant/execution_kernel/submit.py
```

The commit contains five new modules plus facade and characterization changes:
412 insertions and 277 deletions. Claude reports `2392 passed, 1 skipped` and
mutation checks for the moved helpers. That report has not yet received the
independent Codex review required by the workflow. The branch was clean and
matched its remote after the push.

This work is not part of `6699633` and is not part of the transition branch.
Retrieve the exact remote commit; do not recreate it from the summary above or
assume its commit message proves the GR-1 definition of done.

The transition branch was created in an isolated Git worktree under `C:\tmp`
specifically so preparing this document could not switch Claude's branch,
modify its files, or stage its work.

## 4. Current platform and safety posture

The application is an approval-gated paper-trading and investment-research
platform with durable proposal/order state, broker reconciliation, a portfolio
ledger, operational checks, paper-evidence epochs, backup/restore drill support,
an audited LLM context layer, and a non-authoritative ML research/shadow layer.

The following boundaries remain mandatory:

- `config.PAPER_TRADING` remains `True`.
- Never operate a funded brokerage account without a new, explicit, narrowly
  scoped owner authorization.
- Every order remains subject to deterministic policy, execution validation,
  exact human approval, durable idempotency, and broker reconciliation.
- A timeout or failed lookup is not a broker rejection and must not release
  reserved budget as if absence were confirmed.
- ML and LLM output remains observation, research, or explanation only.
- No ML or LLM output may create, approve, size, submit, cancel, replace, or
  weaken a deterministic control.
- Missing, stale, invalid, unavailable, or corrupt AI output is equivalent to
  no AI output.
- AI failure must not stop reconciliation or a legitimate risk-reducing sale.
- Software completion, fixture tests, backtests, and shadow predictions are not
  evidence of market edge and grant no promotion or trading authority.

Read `CLAUDE.md` completely before changing code. Its safety, data, testing,
Git, and handoff requirements apply to both Codex and Claude Code.

## 5. General Readiness status

The authoritative roadmap is
`docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`; current deviations and status
are in `docs/GENERAL_READINESS_STATUS.md`.

### GR-0: built and independently reviewed

`assistant/platform_readiness.py` and the `platform-readiness` CLI score five
dimensions independently: strategy, execution integrity, data integrity,
operational readiness, and evidence readiness. They are never averaged.

The fresh-store result is honestly blocked in all five dimensions. That is an
observation, not a software failure. The review corrected five material
misclassifications, including a misspelled stranded-claim check, ledger
reconciliation in the wrong dimension, truthy strings passing boolean checks,
caller-asserted data readiness, and ignoring the 60-session/30-order mandate.

### GR-1: partial; next extraction committed and awaiting review

Completed and reviewed:

- behavior characterization across all five public execution entry points;
- successful/refused submission, call ordering, reservations, telemetry,
  idempotency, timeout reconciliation, manual reconciliation, recovery, and
  broker-absence grace handling;
- mutation verification of the dangerous behavior directions;
- a synchronized four-writer test proving exactly one atomic claim winner;
- first production extraction into
  `assistant/execution_kernel/outcomes.py`;
- a transitive execution-kernel boundary that catches direct, relative,
  submodule, dynamic, and indirect paths into proposal-generation code; and
- preservation of the `assistant.execution_service` public facade.

The reviewed extraction moved outcome lookup, intent matching,
replacement-chain interpretation, and absence-age classification. It did not
change execution behavior.

Still incomplete or unverified:

- independent review and any corrections for Claude's commit `c8cbf4e`;
- decomposition of the interleaved orchestration in
  `execute_approved_paper_proposal()`;
- a genuinely thin `assistant.execution_service` composition facade;
- independent review of each new module and moved behavior; and
- the GR-1 definition of done on the final tree.

Critical constraints for the next review:

- keep the atomic conditional claim in `AssistantStore`; do not reimplement it
  as read-then-write across modules;
- preserve facade import paths and exact exception identities;
- preserve the distinction between confirmed broker absence and an
  unconfirmed lookup;
- preserve all three reservation-release paths and all ambiguous-outcome budget
  holds;
- do not let kernel modules reach proposal generation directly or transitively;
- do not rewrite valid tests to accommodate a refactor; and
- add a mutation result for moved behavior not already frozen.

### GR-2 through GR-9

Not started. Each requires a gap analysis against the post-ML codebase before
implementation. The intended sequence is GR-2 risk-check consolidation, GR-3
fault injection, GR-4 data-layer resilience, GR-5 delivered alerting, GR-6
recovery/secrets/portability, GR-7 product completeness, and only then a
separately authorized GR-8 bounded live canary. GR-9 is explicitly deferred.

GR-5 requires a real owner-visible delivery channel and a receipt test. GR-6
requires off-machine recovery and credential-rotation exercises. They are not
fixture-only code milestones.

## 6. Latest reviewed validation baseline

The reviewed tree underlying `6699633` passed:

```text
2391 passed, 1 skipped, 26 warnings in 152.09 seconds
compileall: clean
git diff --check: clean
```

The warnings were third-party notices: one `websockets.legacy` deprecation,
one joblib physical-core detection warning, and NumPy/joblib pickle shape
deprecations. They were not test failures.

This result does not independently validate Claude's commit `c8cbf4e`. Claude
reports `2392 passed, 1 skipped` for that branch. After retrieving it, run
focused execution/boundary tests first, then the full required validation on
the exact reviewed tree.

Use a writable pytest base directory if the Codex sandbox cannot access the
default Windows temp directory:

```powershell
New-Item -ItemType Directory -Force .venv\codex_test_tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp .venv\codex_test_tmp\full -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

Pytest is isolated from the operator database by `tests/conftest.py`. Keep that
protection intact. Historical test runs previously wrote UI/sample data into
the operator database and, in another incident, inherited live broker
credentials during collection.

## 7. ML software status

The ML layer remains non-authoritative and isolated from proposal and execution
authority.

| Milestone | Current state |
|---|---|
| ML-LR-0 | Shared experiment and acceptance contracts complete |
| ML-LR-1 | PIT contracts complete; real authoritative coverage still blocked |
| ML-LR-2 | Durable experiment orchestration complete |
| ML-LR-3 / ML-FS-4 | Volatility and portfolio-risk software complete; real evidence underfilled |
| ML-LR-4 | Earnings/filing research software complete; authoritative real event data absent |
| ML-LR-5 | Deliberately skipped/deprioritized; ranker remains incomplete |
| ML-LR-6 | Supervised-volatility shadow runtime complete |
| ML-LR-7 | Monitoring report and immutable promotion dossier software complete |
| ML-LR-8 | Read-only presentation complete |
| ML-LR-9 | Promotion registry/bounded adapter not implemented or authorized |
| ML-LR-10 | Limited-capital canary not authorized; cannot be completed by code alone |
| ML-LR-11 | Execution-quality modeling deferred pending representative live-order data |
| ML-FS-1 | Normalized paper portfolio collection software complete |
| ML-FS-2 | Execution telemetry collection/materialization complete |
| ML-FS-3 | Authoritative Databento builder software complete; no real authoritative batch |
| ML-FS-5 | Prospective inference contract software complete |
| ML-FS-6 | Reviewed research-campaign preparation complete; no real campaign run |
| ML-FS-7 | Evidence operations/scheduler verification infrastructure complete; not deployed here |
| ML-FS-8/9 | Not authorized and not implemented |

Do not begin ML-LR-9, ML-FS-8, ML-LR-10, or ML-FS-9 merely because the
software scaffolding exists.

## 8. Remaining ML data and evidence gates

Databento is the selected market-data vendor. The repository can cost-estimate,
capture, retain, and hash-bind raw statistics and reference data, and its pure
builder can derive `point_in_time_data=True` from complete verified fixture
evidence. No real authoritative feature batch has been created.

The remaining real-data gates are:

1. obtain and retain licensed security-master and adjustment-factor history;
2. resolve the exact listing, option, revision, rescission, and factor vintage
   visible at every decision cutoff;
3. obtain an independently sourced, authoritative historical strategy/index
   membership history;
4. build a real content-addressed feature batch through the normal coverage
   gate rather than a caller assertion;
5. have a human review and attest the frozen real discovery specification;
6. run the real preregistered volatility discovery and separate untouched
   confirmation without retuning;
7. operate one immutable shadow evidence epoch for enough independent dates;
8. clear monitoring, economic, operational, and paper-evidence gates; and
9. conduct a separate owner promotion review.

Yfinance remains exploratory and must stay `point_in_time_data=false`.
Databento market data does not itself supply historical index membership.
Raw as-printed prices also require vintage-correct corporate-action handling;
a split must never be interpreted as a genuine extreme return.

The ranker has a low prior after repeated momentum-family rejections. Continue
to prioritize volatility and portfolio-risk evidence unless the owner
explicitly reorders the research roadmap.

## 9. Paper-operation and live-promotion state

No paper evidence epoch has started in the current operator database. No
broker order, broker-order event, execution reservation, operational drill, or
operational alert is recorded there. Therefore the 60-session and 30-order
mandate gates have not begun accumulating in this database.

The unattended cadence, when intentionally deployed against the correct paper
account and isolated operational database, is documented in
`docs/OPERATIONS_RUNBOOK.md`. The core commands are:

```powershell
.\.venv\Scripts\python.exe scripts/run_personal_assistant.py --database <paper-db> operations-cycle --alerts-jsonl <alerts.jsonl>
.\.venv\Scripts\python.exe scripts/run_personal_assistant.py --database <paper-db> paper-observation --alerts-jsonl <alerts.jsonl>
.\.venv\Scripts\python.exe scripts/run_personal_assistant.py --database <paper-db> paper-evidence-status <epoch-id>
```

Do not start an epoch casually from a moving development checkout. The epoch
binds the Git commit, mandate, policy, strategy/model identifiers, schedule,
provider, and broker account. A lineage change starts a new epoch; epochs are
never pooled.

Before any live review, all of these remain real gates:

- approved and fingerprinted mandate;
- reproduced point-in-time research and honest confirmation;
- realistic costs, taxes, liquidity, and shared-capital simulation;
- at least the mandated paper sessions and broker-observed paper orders;
- clean cash/position reconciliation;
- no unresolved broker outcomes or critical alerts;
- kill-switch, ambiguous-submission, restart, backup/restore, and delivered
  alert drills;
- a reviewed tiny-capital canary plan; and
- explicit owner authorization after evidence review.

Passing `evaluate_live_promotion()` only makes the platform eligible for human
review. It does not turn on live trading or authorize an order.

## 10. Operator database snapshot

The database is Git-ignored and must be transferred privately while all writers
are stopped.

Snapshot captured 2026-08-02T11:22:10-07:00:

```text
path: data/trading_assistant.db
size: 2,920,448 bytes
last write: 2026-08-01T20:08:24.4605786Z
SHA-256: 02D468223C5BBB14EF7F90BBF283D737772345F13E392846E29E0206EEEBD69F
PRAGMA quick_check: ok
```

Selected row counts:

```text
decision_packets:              277
trade_proposals:                31
portfolio_equity_snapshots:    118
portfolio_position_snapshots:    0
paper_account_observations:       0
paper_evidence_epochs:            0
ml_evidence_epochs:               0
broker_orders:                    0
broker_order_events:              0
execution_reservations:           0
operational_alerts:               0
operational_drill_runs:            0
```

The 118 equity rows include data written before pytest was isolated from the
operator database. `docs/GENERAL_READINESS_STATUS.md` treats equity history
before 2026-08-02 as unreliable. The 277 decision packets and 31 proposals
have not been individually classified. Do not delete or use them as evidence
without a scoped backup, provenance analysis, explicit owner approval, and a
reviewed cleanup operation.

The hash above is only a snapshot. Recalculate it after stopping writers and
creating the actual transfer backup. Prefer the documented SQLite backup and
restore workflow over copying a live database file.

After restoring on the new computer:

1. verify the transfer hash;
2. run SQLite integrity/quick checks;
3. confirm the expected paper account identity without printing credentials;
4. reconcile the ledger against Alpaca paper state;
5. run the operational health check; and
6. confirm development/tests point to a separate database.

## 11. Licensed Databento artifacts

`artifacts/databento/` is Git-ignored and licensed. Transfer it privately; do
not commit or upload it.

Files present at the snapshot:

```text
databento-equs-summary-20260801T174244622922Z-fb9977a96b02.dbn
  size: 319 bytes
  SHA-256: E94F236F25802834066639D97B79DAEA5D782E454F8245C24D6D127E87E45257

databento-equs-summary-20260801T174244622922Z-fb9977a96b02.manifest.json
  size: 1,170 bytes
  SHA-256: 8F4295E4C230423008ADD6E5BB9675B1D40B894AF91171542C0A531A97E28378

databento-equs-summary-20260801T185751821111Z-4651a31b789d.dbn
  size: 474 bytes
  SHA-256: 1A3DD34834D24809168A4642FBF6EC150E8173411BF14B878FDC98696492F7CB

databento-equs-summary-20260801T185751821111Z-4651a31b789d.manifest.json
  size: 1,330 bytes
  SHA-256: 459D8B154567F0BA4F0E4501F3E87FFAC33BB8C5A4BF722189AE0DD39F0EB588
```

These are tiny unadjusted `EQUS.SUMMARY` samples. They do not prove
point-in-time feature readiness. Preserve each DBN together with its manifest.

For all future requests, follow `docs/DATABENTO_DATA_SOURCE.md`, estimate cost
before downloading, and supply an explicit `--max-cost-usd`. Do not infer
availability timestamps from download time.

## 12. Credentials and host configuration

Never store secret values in this document, Git, logs, screenshots, or issue
comments.

At the snapshot, the current process could see:

```text
APCA_API_KEY_ID: configured in process
APCA_API_SECRET_KEY: configured in process
DATABENTO_API_KEY: configured in process
ANTHROPIC_API_KEY: not configured
FINNHUB_API_KEY: not configured
```

The user-scope environment query returned false for all five names. Recreate
required values on the new computer and start a new terminal/Codex process so
it inherits them. Verify presence without printing values. Keep Alpaca pointed
at the intended paper account.

No Windows scheduled task matching `TradingAgent-*` was installed at the
snapshot. Do not assume the operational or ML evidence cadence is running.
Install tasks only through the reviewed scripts, using explicit repository,
Python, database, config, artifact, and alert paths, then run
`scripts/verify_windows_evidence_tasks.ps1` and inspect `LastTaskResult`.

`config.py` currently has:

```text
PAPER_TRADING = True
```

Do not change it during machine reconstruction.

## 13. What Git will not transfer

Before leaving the old computer, stop Streamlit, scheduled jobs, shadow jobs,
paper operations, and any other database writers. Privately inventory and
transfer, as applicable:

- a consistent backup of `data/trading_assistant.db`;
- `artifacts/databento/` raw files and manifests;
- ML model, dataset, monitoring, dossier, and shadow configuration artifacts
  that are intentionally ignored;
- alert JSONL, heartbeat, drill, and backup evidence files;
- local policy/mandate/config files that are not tracked;
- scheduled-task configuration values and service-account requirements;
- any later uncommitted Claude WIP that could not be pushed; and
- credentials through a secure secret manager or manual recreation, never in
  the transfer document.

Use encrypted storage or direct trusted-device transfer. Recalculate and keep
a separate local transfer manifest of sizes and hashes.

Do not copy `.venv`, `.pytest_cache`, `__pycache__`, or other generated caches.

## 14. Environment reconstruction

Create a new virtual environment from the pinned requirements:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

If Windows long-path problems occur, follow the dependency notes in
`README.md`; do not silently downgrade pinned libraries.

Restore and validate the intended database before starting the UI:

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/personal_assistant_ui.py
```

Do not let development and tests share the restored operational database.

## 15. Documents to read in order

For the current development sequence:

1. `CLAUDE.md`
2. `docs/SESSION_HANDOFF.md`
3. `docs/GENERAL_READINESS_STATUS.md`
4. `docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`
5. `docs/ARCHITECTURE_DEBT.md`
6. `tests/test_execution_characterization.py`
7. the active GR-1 branch diff and all new kernel modules
8. `docs/ML_IMPLEMENTATION_STATUS.md`
9. `docs/ML_FULL_SYSTEM_EXECUTION_PLAN.md`
10. `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`
11. `docs/OPERATIONS_RUNBOOK.md`
12. `docs/LIVE_PROMOTION_CHECKLIST.md`
13. `docs/DATABENTO_DATA_SOURCE.md`
14. `docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md`
15. `docs/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md`

Older passages in status documents may lag later commits. Treat the latest
specific status section and current code/tests as authoritative; update stale
text rather than reimplementing completed work.

## 16. Deferred product plans

### Proposal History cleanup

`docs/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` is planning only. No
cleanup behavior has been implemented. It proposes deterministic expiry,
terminal non-executable dismissal, default hiding, preview-bound bulk actions,
and retention of anything that touched validation, approval, reservation,
submission, allocation, or broker state. Physical deletion remains deferred.

### AI strategy authoring

`docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` is planning only. The safe
intended flow is natural-language description to a typed restricted strategy
specification, deterministic validation/refusal, realistic reproducible
backtesting, untouched confirmation, explicit human promotion, and only then a
paper/shadow proposal adapter behind every existing control. The LLM must not
emit arbitrary executable code or directly authorize trading.

Do not start either plan while GR-1 is half-extracted unless the owner
explicitly changes priority.

## 17. Owner workflow preferences

- Codex generally initiates the plan and alternates implementation/review with
  Claude when requested.
- When reviewing Claude's code, verify findings, fix serious defects where
  possible, and include a 1-10 code-quality rating.
- Commit review fixes unless the owner says not to. If on `main`, branch first.
- Preserve unrelated and uncommitted work in the shared worktree.
- Do not push, merge, or open a pull request unless requested. Cross-computer
  handoffs are an explicit exception when the owner asks for a push.
- Keep one coherent milestone per branch and stop for independent review.
- Do not call a milestone complete because modules or CLI shells exist; verify
  the documented definition of done end to end.

## 18. Recommended next actions

1. Fetch and independently review exact commit `c8cbf4e` from
   `user/claude/gr-1a-extract-kernel-modules-20260802`.
2. Transfer the ignored database and Databento files through encrypted storage
   after stopping writers; verify their hashes after restore.
3. Recreate the Python environment and required credentials on the new
   computer; confirm paper mode and database isolation.
4. Independently review every moved helper,
   facade export, import boundary, exception identity, reservation path,
   idempotency path, and ambiguous-outcome path.
5. Run focused characterization/import/reconciliation tests and then the full
   suite on Claude's exact final tree.
6. Finish GR-1 before starting GR-2 unless the owner explicitly changes the
   sequence.
7. In parallel only at the operational level, decide when and how to deploy an
   isolated paper cadence; do not start an evidence epoch from a moving or
   mixed runtime.
8. Resolve the historical-universe and licensed PIT reference-data dependency
   before claiming authoritative ML evidence.
9. Keep ML promotion, bounded adapters, and funded canaries blocked until the
   real evidence and owner-authorization gates are satisfied.

## 19. Decisions still required from the owner

The following are not safe to infer:

1. Which authoritative historical index-membership vendor/source will be
   funded and used?
2. When should the operational paper cadence and first immutable evidence
   epoch start?
3. Which owner-visible delivery channel should GR-5 implement and verify?
4. Should the pre-isolation database pollution be cleaned after backup and
   provenance analysis, or simply excluded by a dated boundary?
5. When is the elevated Windows deployment/credential-rotation window?
6. When, if ever, should the deferred ranker, proposal-history cleanup, or AI
   strategy-authoring plans take priority?

None of these decisions grants funded-account authority by implication.

## 20. Resume prompt after verifying the new machine

```text
Read CLAUDE.md and docs/SESSION_HANDOFF.md completely. Verify origin/main,
the transition branch, and exact Claude commit c8cbf4e on
user/claude/gr-1a-extract-kernel-modules-20260802. Compare the real state with
the handoff. Verify the restored database and Databento artifact hashes,
paper-mode configuration, credential presence without displaying values, and
scheduled-task state. Do not delete data, start an evidence epoch, install
tasks, enable live trading, or wire ML/LLM output into proposals. If Claude's
GR-1 extraction is committed, review it against the characterization suite and
GR-1 definition of done, fix serious defects, include a 1-10 rating, commit the
review, and stop before GR-2.
```
