# Development Session Handoff

Prepared: 2026-08-01 (America/Los_Angeles)

This document carries the useful state of the current local Codex task to a
new computer. It intentionally contains no API keys, brokerage credentials,
account numbers, or licensed market-data content.

## 1. Start here on the new computer

Clone the repository and open the repository root in Codex. Then give the new
task this prompt:

```text
Read CLAUDE.md and docs/SESSION_HANDOFF.md completely. Then read the
implementation plan and status documents named by the handoff. Establish the
actual Git branch, commit, worktree, local-data, and credential state before
making changes. Preserve the ML/LLM observation-only boundary. Do not infer
live-trading or model-promotion authority from software completion. Report
what is missing on this computer before continuing the requested milestone.
```

Do not assume that the original Codex conversation will synchronize. The
repository, this handoff, and the separately transferred operational files
are the durable continuation mechanism.

## 2. Repository snapshot

- Repository: `https://github.com/SheltonChen2017/trading_agent`
- Source baseline before this handoff: `main` at `cbf017b0478462745eb4881d803cbfe2f9e489db`
- Baseline subject: merge of the Databento point-in-time reference-retention
  review.
- Repository state at handoff preparation: clean and synchronized with
  `origin/main`.
- Handoff branch: `codex/session-handoff-20260801`.
- Python used for validation: 3.12.13 in `.venv`.
- Dependency check: `pip check` reported no broken requirements.

After cloning, verify rather than trusting this snapshot:

```powershell
git fetch --all --prune
git status --short --branch
git log -12 --oneline --decorate
```

If this handoff branch has not yet been merged into `main`, check it out
explicitly:

```powershell
git switch --track origin/codex/session-handoff-20260801
```

## 3. Current product and safety state

The application is an approval-gated paper-trading and investment-research
platform. It has durable proposal/order state, reconciliation, a portfolio
ledger, operational checks, paper-evidence epochs, backup/restore drills, an
audited LLM context layer, and a non-authoritative ML research/shadow layer.

The following boundaries remain mandatory:

- Alpaca remains configured for paper trading unless the owner separately and
  explicitly authorizes a bounded live milestone.
- Every order remains subject to the deterministic policy, execution gate,
  exact human approval, and broker reconciliation.
- ML and LLM output is observation/explanation only.
- No ML or LLM output may create, approve, size, submit, cancel, replace, or
  weaken a deterministic control.
- Missing or invalid AI output is equivalent to no AI output.
- Software completion, fixture tests, backtests, and shadow predictions are
  not evidence of edge and do not grant trading authority.

Read `CLAUDE.md` completely before changing code. Its safety, testing, Git,
and handoff requirements apply to both Claude Code and Codex work.

## 4. Important plans and status documents

Read these in this order when resuming broad development:

1. `CLAUDE.md`
2. `docs/SESSION_HANDOFF.md`
3. `docs/ML_IMPLEMENTATION_STATUS.md`
4. `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md`
5. `docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`
6. `docs/OPERATIONS_RUNBOOK.md`
7. `docs/LIVE_PROMOTION_CHECKLIST.md`
8. `docs/DATABENTO_DATA_SOURCE.md`
9. `docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md`
10. `docs/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md`

`docs/ML_IMPLEMENTATION_STATUS.md` contains stale passages in its older
"Known gaps" and ML-LR-3 sections. Later commits completed ML-LR-3 and
ML-LR-4/6/7/8 software. Reconcile that document before treating every sentence
as current; do not use the stale text to reimplement completed work.

## 5. ML live-readiness status

The initial non-authoritative software sequence is substantially complete:

- ML-LR-0: shared experiment contracts complete.
- ML-LR-1: point-in-time contracts complete; authoritative real-data coverage
  is not complete.
- ML-LR-2: durable experiment specifications and runners complete.
- ML-LR-3: volatility and portfolio-risk software complete; real portfolio
  evidence remains data/history dependent.
- ML-LR-4: earnings-gap and filing-context software complete; authoritative
  event data and real confirmation remain external evidence gaps.
- ML-LR-5: ranker economic evaluation was deliberately skipped/deprioritized.
- ML-LR-6: supervised volatility shadow runtime complete.
- ML-LR-7: monitoring reports and promotion dossier software complete.
- ML-LR-8: read-only presentation complete.
- ML-LR-9: human promotion registry and bounded adapter are not implemented or
  authorized.
- ML-LR-10: limited-capital canary is not authorized and cannot be completed by
  code alone.
- ML-LR-11: execution-quality modeling remains deferred until representative
  live-order data exists and the owner explicitly authorizes the research.

### Remaining ML evidence gates

Databento ingestion and evidence capture are implemented, but they correctly
remain `point_in_time_data=false`. The next meaningful technical/data work is:

1. obtain and retain the necessary security-master and adjustment-factor
   reference history;
2. implement a separately reviewed adjustment builder that reconstructs the
   exact factor vintage available at each decision cutoff, including
   rescissions, options, and listing identity;
3. configure an authoritative historical strategy/index membership source and
   emit real `UniverseMembershipRecord` evidence;
4. bind raw, receipt-timestamped statistics, reference, adjustment, membership,
   and feature lineage through `evaluate_point_in_time_coverage()`;
5. prove the normal coverage gate derives `point_in_time_data=true` without a
   caller assertion;
6. run real preregistered volatility discovery/confirmation experiments; and
7. operate the shadow schedule long enough to accumulate prospective evidence
   within one immutable evidence epoch.

Do not begin ML-LR-9 merely because the ingestion code works. A real promotion
dossier still needs complete point-in-time coverage, untouched confirmation,
economic evidence, sufficient shadow dates, clean monitoring, no unresolved
operational blockers, and separate owner review.

The ranker has a low prior after repeated momentum-family rejections. Prefer
closing the volatility/risk data and evidence path before deciding whether
ML-LR-5 is worth the research cost.

## 6. General live-readiness work after the ML software phase

`docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md` is the next broad development
roadmap. Separately, the current default mandate requires at least 60 derived
paper sessions and 30 distinct broker-observed paper orders. Those are
calendar/operation evidence gates, not values to enter manually.

The unattended paper cadence is:

```powershell
python scripts/run_personal_assistant.py operations-cycle --alerts-jsonl data/alerts.jsonl
python scripts/run_personal_assistant.py paper-observation --alerts-jsonl data/alerts.jsonl
python scripts/run_personal_assistant.py paper-evidence-status <epoch-id>
```

Before any live review, complete and record the kill-switch,
ambiguous-submission, restart, and real backup/restore drills; keep cash and
positions reconciled; and resolve every ambiguous broker outcome and critical
alert. Follow `docs/OPERATIONS_RUNBOOK.md`, not an improvised procedure.

## 7. Deferred feature plans

### Proposal-history cleanup

`docs/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` is planning only. No
cleanup behavior has been implemented yet.

Its intended first release adds:

- deterministic expiry of stale unused proposals;
- a terminal, non-executable `dismissed` status;
- default hiding of expired/dismissed rows in History;
- preview-bound bulk dismissal with a required reason; and
- complete retention of every proposal that touched validation, approval,
  allocation batching, reservation, submission, or broker state.

Physical deletion remains explicitly deferred. Do not replace dismissal with
an unreviewed `DELETE FROM trade_proposals` command.

### AI strategy authoring

`docs/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` is also planning only. The
platform does not yet accept an unrestricted natural-language strategy and
turn it directly into an executable trading strategy.

The intended safe flow is natural-language description to a typed,
reviewable strategy specification; deterministic validation and refusal;
reproducible backtesting and untouched confirmation; explicit human promotion;
then observation/proposal integration behind the existing policy and approval
boundaries. The LLM must not emit arbitrary executable code or bypass those
stages.

## 8. Machine-local state that Git will not transfer

Transfer these files privately while the application and scheduled tasks are
stopped. Do not upload them to GitHub. Use encrypted storage or a direct
trusted-device transfer.

### SQLite operational database

```text
data/trading_assistant.db
size at handoff: 2,863,104 bytes
SHA-256: 02D468223C5BBB14EF7F90BBF283D737772345F13E392846E29E0206EEEBD69F
```

This database is Git-ignored. Its hash is valid only for the snapshot present
when this handoff was prepared; continued application use will legitimately
change it. Stop writers, make a consistent backup using the documented backup
workflow, transfer that backup, restore it on the new computer, and run SQLite
integrity plus ledger reconciliation checks.

### Licensed Databento snapshots

The entire `artifacts/databento/` directory is Git-ignored and must remain out
of version control. Files present at handoff:

```text
databento-equs-summary-20260801T174244622922Z-fb9977a96b02.dbn
  E94F236F25802834066639D97B79DAEA5D782E454F8245C24D6D127E87E45257
databento-equs-summary-20260801T174244622922Z-fb9977a96b02.manifest.json
  8F4295E4C230423008ADD6E5BB9675B1D40B894AF91171542C0A531A97E28378
databento-equs-summary-20260801T185751821111Z-4651a31b789d.dbn
  1A3DD34834D24809168A4642FBF6EC150E8173411BF14B878FDC98696492F7CB
databento-equs-summary-20260801T185751821111Z-4651a31b789d.manifest.json
  459D8B154567F0BA4F0E4501F3E87FFAC33BB8C5A4BF722189AE0DD39F0EB588
```

Preserve each raw file together with its manifest. These samples are
unadjusted and do not prove point-in-time feature readiness.

Other ignored operational files may be created after this handoff. Before the
move, inspect `data/`, `artifacts/`, local policy/config paths, alert JSONL,
drill evidence, backups, and scheduled-task configuration without adding
credentials or licensed data to Git.

## 9. Secrets and account configuration to recreate

Recreate environment variables on the new computer; do not transfer their
values in this document or commit them anywhere:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- `DATABENTO_API_KEY`
- optional `ANTHROPIC_API_KEY`
- optional `FINNHUB_API_KEY`

Keep `config.py` paper-trading mode enabled. After setting user-level Windows
environment variables, restart PowerShell and Codex so new processes inherit
them. Verify presence without printing values.

For Databento:

```powershell
python scripts/run_databento_ingest.py status
python scripts/run_databento_ingest.py check-access --dataset EQUS.SUMMARY
```

Always estimate before downloading and always use an explicit
`--max-cost-usd`. Follow `docs/DATABENTO_DATA_SOURCE.md`. Reference requests
require subscription confirmation and the explicit acknowledgement option.

## 10. Environment reconstruction

Do not copy `.venv` between computers. Recreate it from the pinned repository
requirements:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

If installation encounters Windows long-path failures, follow the Windows
dependency notes in `README.md`; do not silently downgrade pinned packages.

Run the UI only after restoring the intended database and confirming paper
credentials:

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/personal_assistant_ui.py
```

Reinstall scheduled tasks from the reviewed scripts and runbooks. Do not copy
Task Scheduler definitions blindly because absolute Python, repository,
database, artifact, and alert paths change across machines.

## 11. Fresh validation baseline

On source baseline `cbf017b`, with Alpaca credentials removed only from the
test process and an unrestricted temporary directory:

```text
2256 passed, 1 skipped, 20 warnings in 125.89 seconds
```

Warnings were one `websockets.legacy` deprecation and 19 joblib/NumPy shape
deprecations. `pip check` reported no broken requirements.

The ordinary sandboxed attempt was not a product failure: the test collector
first inherited live Alpaca variables, and later sandbox attempts could not
create pytest temporary directories. The successful baseline used no broker
credentials and made no live broker call.

For a clean offline run in PowerShell, clear credentials only in that shell
before starting pytest:

```powershell
Remove-Item Env:APCA_API_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:APCA_API_SECRET_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q
```

This does not delete user-level variables; it removes them only from the
current PowerShell process. Opening a new shell restores inherited user-level
configuration.

For completed milestones also run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

## 12. Owner workflow preferences

- Codex initiates the execution plan and alternates implementation/review with
  Claude when the owner requests that workflow.
- When reviewing Claude's code, verify findings, fix serious defects where
  possible, and include a 1-10 code-quality rating with the review report.
- After a Claude-code review, commit the review fixes unless the owner says not
  to. If currently on `main`, create a branch before committing.
- Preserve unrelated work in the shared worktree.
- Do not push, merge, or open a pull request unless requested or necessary for
  an explicitly requested cross-computer handoff.
- Use one coherent milestone per branch and stop for independent review.

## 13. Recommended next actions

1. Transfer and restore the ignored database and Databento artifacts, then
   verify their hashes/integrity.
2. Recreate credentials and confirm Alpaca is the intended paper account.
3. Run the offline validation suite on the new machine.
4. Reconcile the stale sections of `docs/ML_IMPLEMENTATION_STATUS.md`.
5. Close the ML-LR-1 authoritative-data gaps: vintage-correct corporate-action
   adjustment and historical universe membership.
6. Run the real volatility experiment and begin one correctly configured
   prospective shadow evidence epoch.
7. Continue the general-readiness roadmap and paper operating cadence while
   shadow evidence accumulates.
8. Defer ML-LR-9, ML-LR-10, and funded trading until their evidence and owner
   authorization gates are genuinely satisfied.
