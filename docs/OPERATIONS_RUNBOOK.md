# Operations runbook

The order monitor, operations watchdog, scheduled operations cycle, post-close
evidence capture, and ML evidence supervisor are independent controls. The monitor owns
broker-order reconciliation; the watchdog records frequent health
heartbeats; the cycle synchronizes the ledger, reconciles Alpaca, maintains
verified backups, and emits alerts; the post-close job records the paper
equity curve; the ML supervisor verifies that expected evidence arrived. No one
process may be the only copy of another control.

## Before starting a paper evidence epoch

1. Keep `config.PAPER_TRADING = True`.
2. Configure Alpaca paper credentials and choose one writable SQLite path.
3. Commit the exact code that will run. Evidence capture refuses a dirty
   worktree or a commit other than the one that started the epoch.
4. Run `readiness`.
5. Explicitly bootstrap the portfolio journal once, then reconcile it.
6. Start the epoch before its first trading session, using immutable strategy
   and model identifiers.
7. Run a backup/restore drill while that epoch is active:

```text
python scripts/run_personal_assistant.py --database data/paper.db readiness
python scripts/run_personal_assistant.py --database data/paper.db ledger-bootstrap --confirm bootstrap
python scripts/run_personal_assistant.py --database data/paper.db ledger-reconcile
python scripts/run_personal_assistant.py --database data/paper.db paper-epoch-start paper-2026q3 --strategy-id shared-capital-scanner --strategy-version 1.0.0 --model-id deterministic-no-model
python scripts/run_personal_assistant.py --database data/paper.db recovery-drill
```

The epoch binds the Git commit, mandate fingerprint, policy fingerprint,
strategy ID/version, model ID, and the connected Alpaca paper account ID. A
material change to any of them—or switching broker accounts—requires:

```text
python scripts/run_personal_assistant.py --database data/paper.db paper-epoch-close paper-2026q3
```

Commit the change and start a new epoch. Do not combine observations from
different epochs to satisfy a promotion threshold.

When replacing a frozen runtime to repair a stalled active epoch, use this
order. Deployment does not close durable epoch state, and a new epoch must not
start before the upgraded ledger reconciles:

1. Disable all scheduled operational tasks; stopping them is insufficient on
   the epoch host because their triggers can restart them.
2. Close the old epoch while its frozen runtime is still checked out.
3. Deploy only the merged, independently reviewed replacement commit.
4. Run `ledger-reconcile`; require `matched: true` before proceeding.
5. Run `readiness`, then start the new epoch on the exact deployed commit.
6. Run all five required drills, re-enable the tasks, and verify they execute.

An epoch created before broker-account lineage was introduced cannot be
continued under the stronger schema. Close it, complete any required legacy
`ledger-bind-account` migration, commit the upgraded runtime, and start a new
epoch bound to the verified account.

## Unattended cadence

| Control | Cadence | Command |
| --- | --- | --- |
| Order monitor | Continuous; 30-second polling fallback | `monitor-orders --cancel-stale --poll-seconds 30` |
| Watchdog | Continuous; 60-second health heartbeat | `run_operations_watchdog.py --interval-seconds 60` |
| Operations cycle | Every 10 minutes | `operations-cycle --cancel-stale --alerts-jsonl data/alerts.jsonl` |
| Paper observation | Once after each NYSE close | `paper-observation --cancel-stale --alerts-jsonl data/alerts.jsonl` |
| ML prediction/maturity/monitoring | Once after each weekday close at staggered times | `run_ml_shadow.py predict`, `mature`, and `monitor` |
| ML evidence supervisor | Every 15 minutes | `run_ml_evidence_supervisor.py` |

`operations-cycle` runs order reconciliation, idempotent fill-to-ledger sync,
broker-activity sync, broker-versus-ledger reconciliation, conditional
verified backup, and the operational health check in that order. An
unsupported broker activity remains a failing result, but snapshot
reconciliation, backup, health, and the critical alert still run before that
failure returns. Backups default to a 20-hour maximum age, leaving margin
before the 24-hour health limit. It exits nonzero on a ledger mismatch or
unhealthy result. Exceptions create a deduplicated critical SQLite alert and,
when configured, append it to the JSONL delivery boundary.

`paper-observation` is post-close and scheduler-idempotent: a retry returns
the already-recorded immutable observation. It skips weekends and exchange
holidays, refuses pre-close capture, requires a matching reconciliation no
older than 30 minutes, verifies the current evidence lineage, and records
cash-transfer-adjusted NAV plus the exact benchmark close. A real failure
creates a critical alert.

The same accepted observation is also the source of truth for normalized ML
portfolio history. The command writes one `portfolio_equity_snapshots` row,
one `portfolio_position_snapshots` row per holding, and then a final
`portfolio_capture_sessions` manifest binding their hashes to the paper
observation and evidence epoch. A manifest with `position_count=0` is a valid
cash-only portfolio; a missing manifest means normalization did not complete.
Retry the same `paper-observation` command after correcting the failure. The
retry derives normalized records from the stored immutable observation—not a
newer broker snapshot—and repairs missing children or the manifest
idempotently.

## Execution telemetry collection

No separate telemetry daemon is required. For each proposal successfully
claimed by `execute_approved_paper_proposal()`, the service appends validation
and quote evidence to `execution_telemetry_events`. If execution reaches the
broker boundary, it appends `submission_started` before the API call. A failure
to persist that event blocks the call and releases the execution-budget
reservation. Do not bypass this service to place assistant-originated orders;
direct broker orders cannot produce a complete pre-broker record.

Acknowledgements, fills, cancels, and replacements continue to come from the
order monitor's authoritative `broker_order_events` journal. Keep
`monitor-orders` running and retain the same SQLite database for the execution
service and monitor. The analysis record is rebuilt with
`assistant.execution_telemetry.materialize_execution_attempt(store,
attempt_id)`; no mutable materialized table needs repair.

For a quick completeness check:

```sql
SELECT attempt_id, proposal_id, event_type, event_at,
       account_mode, broker_account_id
FROM execution_telemetry_events
ORDER BY event_at DESC;
```

A refused validation normally has one event. A dispatched attempt has both a
validation event and `submission_started`; subsequent lifecycle rows are in
`broker_order_events`. Paper and live rows must remain partitioned by
`account_mode` and `broker_account_id`. Recent volume and liquidity bucket are
currently marked unavailable because Alpaca's latest-quote response contains
neither volume nor depth; do not backfill estimates and present them as
observations.

The continuous processes can also be started directly:

```text
python scripts/run_personal_assistant.py --database data/paper.db monitor-orders --cancel-stale --poll-seconds 30
python scripts/run_operations_watchdog.py --database data/paper.db --interval-seconds 60 --alerts-jsonl data/alerts.jsonl
```

### Windows Task Scheduler

On a new Windows host, `scripts/setup_operational_host.ps1` can create the
separate operational clone, dedicated venv, launcher, and elevated installation
wrapper. It is non-elevated and refuses a dirty operational checkout, a
Microsoft Store Python alias, or any failed native Git/Python/pip command. Its
generated wrapper uses Interactive logon because Credential Guard blocked S4U
launches on the first operational host. Preparing a second host never permits
two hosts to collect into one epoch: close the active epoch before moving the
cadence, database, or frozen runtime.

Preview the four operational tasks under the intended least-privilege account:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_windows_operational_tasks.ps1 -PythonPath C:\path\to\python.exe -DatabasePath C:\path\to\paper.db -RunAsUser "MACHINE\trading-agent" -WhatIf
```

Remove `-WhatIf` only after checking the resolved Python, repository,
database, alert path, and local post-close time. The installer registers the
monitor and watchdog at boot for S4U (or at the named user's logon for
interactive mode), the operations cycle every 10 minutes, and the paper
observation at 4:30 PM local time on weekdays. On this workstation that time
is safely after the NYSE close. Start the boot-triggered tasks manually once
after first installation; their automatic trigger otherwise begins at the next
boot.

The installers default to the current user, S4U logon, and `Limited` run level.
Prefer a dedicated account and pass it explicitly with `-RunAsUser`. Grant only
"Log on as a batch job", read/execute access to Python and the repository,
read access to credentials/config/artifacts, write access to the selected
database/backups/alerts/reports, and outbound access required by the configured
providers. Use `-TaskLogonType Interactive` only when operation exclusively
while that user is logged on is intentional.

Preview the four ML tasks (predict, mature, monitor, and independent
supervisor) with the same account:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_windows_ml_shadow_tasks.ps1 -PythonPath C:\path\to\python.exe -DatabasePath C:\path\to\paper.db -ConfigPath C:\path\to\shadow.json -ArtifactPath C:\path\to\artifact-dir -RunAsUser "MACHINE\trading-agent" -WhatIf
```

Remove `-WhatIf` only after reviewing every resolved path and local scheduled
time. Provide required environment-variable *names* through
`-RequiredCredentialNames`; never place secret values in task arguments.
After installing only the four operational tasks, start each manually once and
run the operational verifier scope:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_windows_evidence_tasks.ps1 -Scope operational -RunAsUser "MACHINE\trading-agent" -PythonPath C:\path\to\python.exe -DatabasePath C:\path\to\paper.db -RequireTaskRun
```

If the four optional ML tasks were also installed, start all eight manually
once and run the default full scope:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_windows_evidence_tasks.ps1 -RunAsUser "MACHINE\trading-agent" -PythonPath C:\path\to\python.exe -DatabasePath C:\path\to\paper.db -ConfigPath C:\path\to\shadow.json -ArtifactPath C:\path\to\artifact-dir -RequireTaskRun
```

The verifier is read-only and non-authoritative. It checks paths, credential
presence without printing values, selected task principals/logon types/actions,
and last task results. `-Scope operational` checks four tasks and lists the six
omitted ML checks explicitly in `SkippedChecks`; default scope `all` checks all
eight and requires the ML config/artifact paths. `-RequireTaskRun` rejects the
never-ran scheduler state and is mandatory after manually starting tasks; omit
it only when checking registration before a first start. Run it as the task account to
verify user-scoped credentials; when run as another account, only
machine-scoped credentials are accepted as visible to the target. A never-run
task is reported but is not a successful manual-run receipt; retain Task
Scheduler history, stdout/stderr, SQLite alerts, JSONL delivery, and
heartbeat/report evidence separately before declaring the host operational.

The supervisor should also:

- restart long-lived processes on unexpected exit with bounded backoff;
- capture stdout/stderr;
- alert when either process has not produced a heartbeat;
- never substitute restart loops for investigating repeated failures.

`data/alerts.jsonl` is a local delivery boundary for a log shipper or paging
sidecar. Durable alert state remains in SQLite until acknowledged.

The ML supervisor can also be run directly:

```text
python scripts/run_ml_evidence_supervisor.py --database data/paper.db --config artifacts/shadow.json --artifact-dir artifacts/model --required-credential APCA_API_KEY_ID --required-credential APCA_API_SECRET_KEY --alerts-jsonl data/alerts.jsonl --output artifacts/ml-evidence-supervisor.json
```

It exits nonzero and creates deduplicated `ml_evidence_operations` alerts when
expected paper observations/capture manifests, ML runs/outcomes, explicit
healthy heartbeats, verified backup/restore evidence, credentials, database
integrity, or artifact integrity are absent. It never creates a missing
observation, prediction, or outcome. Treat a persistent alert as an incident,
not as permission to edit the evidence database manually.

## Authoritative Databento feature replay

Capture statistics for each required session plus security-master and
adjustment-factor reference windows with `run_databento_ingest.py`. Accepted
statistics captures contain the paid raw DBN, a normalized JSON replay
artifact, and a manifest binding both hashes. Reference captures retain raw and
canonical forms. Do not edit any of these files.

Prepare a separately reviewed historical-universe snapshot. A Databento
listing record proves listing state and security identity; it does not prove
membership in an index or strategy universe. The universe snapshot must retain
the upstream artifact hash and every membership's announcement/availability
time. Then provide exact per-session decision cutoffs and build:

```text
python scripts/run_databento_ingest.py build-authoritative --statistics-manifest artifacts/databento/STATS.manifest.json --security-master-manifest artifacts/databento/SECURITY.manifest.json --adjustment-factors-manifest artifacts/databento/ADJUSTMENTS.manifest.json --universe-snapshot artifacts/databento/universe.json --decision-cutoffs-json artifacts/databento/cutoffs.json --output-dir artifacts/databento
```

Repeat `--statistics-manifest` for multiple sessions. Output is stored beneath
its `batch_hash`; an exact replay is idempotent and conflicting bytes are
refused. A `point_in_time_data=true` result means the supplied rows have
complete cutoff-valid feature and universe evidence. It does not establish
that the upstream universe source itself was appropriately licensed, complete,
or reviewed; retain that external review with the source artifact.

## Paper evidence status

Use the derived status rather than manually entering session or order counts:

```text
python scripts/run_personal_assistant.py --database data/paper.db paper-evidence-status paper-2026q3
```

A paper session is one immutable, reconciled post-close account observation.
Coverage is checked against the NYSE calendar between the first and latest
observations. Paper orders are distinct broker-observed order IDs submitted
during the observed session window; accepted, filled, canceled, and rejected
outcomes all count. Orders before the first recorded session do not count.
Deposits and withdrawals posted as `cash_transfer` entries are removed from
period returns before mandate metrics are calculated.

## Required drills

Run every drill against the active epoch and retain logs, screenshots, alert
delivery receipts, or incident notes outside SQLite. `recovery-drill`
automatically records its detailed backup/restore and integrity evidence.
Record each other outcome from a JSON object containing at least `operator`
and `artifact`:

```json
{
  "operator": "owner@example.com",
  "artifact": "data/drill_evidence/2026-08-03-kill-switch.txt",
  "procedure": "Enabled the switch, attempted an approved paper submission, verified the block, then disabled it after review.",
  "observed": "Execution was blocked before broker submission."
}
```

```text
python scripts/run_personal_assistant.py --database data/paper.db record-drill kill_switch pass data/drill_evidence/kill-switch.json
python scripts/run_personal_assistant.py --database data/paper.db record-drill ambiguous_submission pass data/drill_evidence/ambiguous-submission.json
python scripts/run_personal_assistant.py --database data/paper.db record-drill restart_recovery pass data/drill_evidence/restart-recovery.json
python scripts/run_personal_assistant.py --database data/paper.db recovery-drill
python scripts/run_personal_assistant.py --database data/paper.db record-drill alert_delivery pass data/drill_evidence/alert-delivery.json
```

The latest recorded result for each drill type is authoritative, so a later
failure invalidates an earlier pass. Do not record a pass from capability
alone: execute the procedure and point `artifact` to durable evidence. The
machine-local `data/drill_evidence/` directory is Git-ignored so recording
artifacts does not invalidate the clean-worktree lineage check; back it up
through the operator's evidence-retention system.

## Incident response

1. Run `cancel-all-orders --confirm "cancel all open orders" --reason
   "<incident>"`; it activates the persistent kill switch before attempting
   every open broker-order cancellation.
2. Preserve logs, the database and WAL files.
3. Check ambiguous broker outcomes before retrying anything.
4. Query Alpaca directly for current orders, positions and account state.
5. Run order synchronization and portfolio-ledger reconciliation.
6. Keep the kill switch active until every discrepancy is explained.
7. Record the incident, corrective action and recovery evidence.

If cancel-all exits nonzero, treat every reported failure as potentially
still live and verify it directly at Alpaca. Do not clear the kill switch
until the broker has no unexplained open orders.

### Alert delivery (GR-5): critical alerts reach you without looking

Owner channel decision (2026-08-03): **Windows desktop notification is the
mandatory immediate channel for `critical` alerts**; `warning` batches into
the daily briefing instead of interrupting; a webhook channel is
deliberately out of scope.

```powershell
# deliver open critical alerts (add --dry-run to verify without notifying)
.\.venv\Scripts\python.exe scripts/run_personal_assistant.py deliver-alerts

# weekly: prove the channel still works, end to end
.\.venv\Scripts\python.exe scripts/run_personal_assistant.py alert-self-test --record-drill --operator "<name>"
```

| Behavior | Guarantee |
|---|---|
| Delivery record | Every attempt appends an immutable `alert_deliveries` row (channel, outcome, timestamps, occurrence count). A later success never erases an earlier failure. |
| Failure | Escalates two ways: nonzero CLI exit AND a durable critical `alert_delivery` alert. A failed attempt is never recorded as delivered. |
| Re-delivery | Occurrence-based: an unchanged condition is not re-toasted every sweep, but a genuinely new occurrence is delivered again. |
| Self-test | Emits a synthetic critical alert, delivers it, and verifies the receipt **read back from storage**; records the `alert_delivery` promotion drill (epoch-bound only when the runtime commit exactly matches the epoch lineage, else verification-only). A failed self-test is recorded too. |
| Detection | `platform-readiness` reports `critical_alert_delivery` (mandatory) and `alert_channel_self_test` (degrades only). These live in the READ-ONLY readiness report on purpose: `operational_health` persists an alert per failing check, so an "undelivered critical" check there would raise a critical alert that is itself undelivered, manufacturing a new alert every cycle. |
| Operator surface | The Streamlit **Operations** tab shows undelivered criticals, self-test freshness, open alerts with a delivered flag, recent delivery attempts, readiness dimensions, heartbeat/backup/epoch state, and recent drills. |

Schedule `deliver-alerts` alongside the operations cycle and `alert-self-test`
weekly. A channel that silently broke is worse than no channel.

### Fault-drill matrix (GR-3): each incident class and its exercised behavior

Every failure class below has a standing adversarial drill in
`tests/faults/test_fault_matrix.py`, run end to end by:

```powershell
.\.venv\Scripts\python.exe scripts/run_fault_drill.py
```

The harness atomically writes a hash-stamped JSON report (default under the
Git-ignored `artifacts/`), and `--record-database <db> --operator "<name>"`
additionally records the `ambiguous_submission`, `restart_recovery`, and
`kill_switch` promotion drill types in `operational_drill_runs`
(epoch-bound when an active paper evidence epoch exists; marked
`verification_only` otherwise). Active-epoch recording requires the report's
exact clean commit to match the epoch's lineage; dirty, unknown, or different
code is refused. A dirty worktree can still produce a standalone report with
`code_commit=unknown`, but never promotion evidence. Skips, missing/unmapped
tests, and abnormal pytest exits fail closed.

| Fault | Observed platform behavior (drilled) |
|---|---|
| F1 broker timeout after submit | resolved by idempotency-key lookup; exactly one submit call, never a blind resubmit; reservation retained |
| F2 duplicate order ID on retry | one `broker_orders` row, one order; crash-retry adopts, never resubmits |
| F3 process killed mid-submission | startup lookup adopts an already-accepted `submitting` order without resubmit and with its reservation held; pre-broker and dead-reconciliation recovery cases are also drilled |
| F4 unexpected order under our key | persistent kill switch and deduplicated critical reconciliation alert are written atomically; proposal stays `submission_unknown`, further submissions are refused |
| F5 ticker halted before submit | per-ticker refusal (`blocked`), kill switch NOT engaged, risk-reducing sells in other tickers still execute |
| F6 corporate action between snapshot and submit | share-count mismatch refused before any broker call |
| F7 stale quote / clock skew | freshness refusal in both directions (old and future timestamps) |
| F8 disk-full error during journal write | a statement-level injected `sqlite3.OperationalError` makes the atomic projection roll back whole (no half-journal); the accepted order is never reported failed and reconciliation repairs it afterwards; this does not physically exhaust a disk |
| F9 kill switch mid-flight | no new submissions; the in-flight order still reconciles cleanly |
| F10 (regression 2026-08-02) | pytest sessions are pinned away from the operator database |
| F11 (regression 2026-08-02) | no brokerage credentials reach the test suite; live calls impossible |

`alert_delivery` is produced by GR-5's storage-verified weekly channel self-
test and is visible in the Operations surface. `backup_restore` keeps its
dedicated `recovery-drill` producer above.

The recovery drill creates a consistent backup, restores it to a temporary
database, runs SQLite integrity checks on both copies, and compares every
table count. It never replaces the live database. A successful drill expires
for health purposes after 30 days by default.

## Portfolio-volatility research preparation

Use complete `portfolio_capture_sessions` only. Build either `frozen_weight`
or `realized_account` targets for one exact account key; never pool target
kinds, broker accounts, or paper/live identities. Then use
`PortfolioDatasetContract` and `build_portfolio_dataset_frames()` to bind the
ordered features, cash exposure, horizon, and distinct trailing/EWMA baseline
columns. An unavailable result is an operationally valid outcome: inspect its
refusals and readiness blockers instead of filling missing holdings or account
sessions.

A portfolio experiment spec must use task
`portfolio_volatility_forecast` and freeze these exact task parameters:

```json
{
  "observation_unit": "account_session",
  "target_kind": "frozen_weight",
  "target_units": "daily_return_standard_deviation_pct"
}
```

Run the resulting content-addressed dataset through the existing
`run_ml_experiment.py` workflow. Preserve the emitted spec, report, model
manifests, model artifacts, and run manifest together. This is research-only:
do not edit the research registry, proposals, or execution state based on the
result. Until enough genuine daily captures exist, report the path as
underfilled rather than validating it on reconstructed positions.

## Inspecting prospective shadow evidence

New volatility artifacts must contain a frozen `prospective_profile` generated
by the experiment runner from out-of-fold residuals and a preregistered mandate
ceiling. Do not retrofit that profile into an old artifact: rerun the immutable
experiment under a new artifact identity and start a new evidence epoch.

Each stored prediction's `prediction.prospective_contract` is the review
surface. Verify that it contains the point and interval, an
`experimental_probability` or `calibrated_probability` label, calibration and
baseline state, per-feature observations, reference-distribution hash,
regime/event categories, target availability, and complete lineage. For a
refusal, the point, interval, and probability must remain null and the reason
must be present. Never reconstruct these fields when an outcome matures.

An experimental label is not a confidence statement. A calibrated label only
means the preregistered calibration gate encoded in that model's immutable
evaluation cleared; it still has no proposal or execution authority. Any
artifact, provider, schedule, configuration, code, or feature-semantics change
requires a new evidence epoch before collection resumes.

## Review-gated discovery and confirmation

First place an already-built dataset into the authoritative content-addressed
store. This command replays all hashes and point-in-time coverage and refuses
exploratory data:

```text
python scripts/run_ml_research_campaign.py materialize-dataset --source-dir artifacts/datasets/staging --dataset-id volatility-discovery-2026q3 --store-root artifacts/datasets/authoritative
```

Review `research/ml_specs/volatility-discovery-v1.json` and its review request.
An identified reviewer must create a separate `SpecReviewAttestation`; the
repository request is deliberately not an approval. Verify it before running:

```text
python scripts/run_ml_research_campaign.py verify-spec-review --spec research/ml_specs/volatility-discovery-v1.json --review artifacts/reviews/volatility-discovery-v1.approved.json
python scripts/run_ml_research_campaign.py run-reviewed --spec research/ml_specs/volatility-discovery-v1.json --review artifacts/reviews/volatility-discovery-v1.approved.json --dataset-dir artifacts/datasets/authoritative/DATASET_HASH --dataset-id volatility-discovery-2026q3 --output-dir artifacts/experiments/volatility-v1 --code-commit COMMIT_HASH
```

Only a verified `confirmation_run_requested` discovery may prepare
confirmation. Supply a separately materialized, different dataset hash:

```text
python scripts/run_ml_research_campaign.py prepare-confirmation --discovery-output-dir artifacts/experiments/volatility-v1 --discovery-experiment-id volatility-discovery-v1 --confirmation-dataset-dir artifacts/datasets/authoritative/CONFIRMATION_DATASET_HASH --confirmation-dataset-id volatility-confirmation-2026q4 --confirmation-experiment-id volatility-confirmation-v1 --created-at REVIEW_REQUEST_TIME --spec-output artifacts/experiments/volatility-v1/volatility-confirmation-v1.pending.json --request-output artifacts/experiments/volatility-v1/volatility-confirmation-v1.request.json
```

Review and attest the generated confirmation spec separately, then call
`run-reviewed` with `--confirmation-request`. Do not retune a failed
confirmation identity or copy discovery rows into its dataset. These commands
write research artifacts only and never update the model registry or trading
state.
