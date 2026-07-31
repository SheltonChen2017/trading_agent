# Operations runbook

The order monitor, operations watchdog, scheduled operations cycle, and
post-close evidence capture are independent controls. The monitor owns
broker-order reconciliation; the watchdog records frequent health
heartbeats; the cycle synchronizes the ledger, reconciles Alpaca, maintains
verified backups, and emits alerts; the post-close job records the paper
equity curve. No one process may be the only copy of another control.

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

`operations-cycle` runs order reconciliation, idempotent fill-to-ledger sync,
broker-versus-ledger reconciliation, conditional verified backup, and the
operational health check in that order. Backups default to a 20-hour maximum
age, leaving margin before the 24-hour health limit. It exits nonzero on a
ledger mismatch or unhealthy result. Exceptions create a deduplicated
critical SQLite alert and, when configured, append it to the JSONL delivery
boundary.

`paper-observation` is post-close and scheduler-idempotent: a retry returns
the already-recorded immutable observation. It skips weekends and exchange
holidays, refuses pre-close capture, requires a matching reconciliation no
older than 30 minutes, verifies the current evidence lineage, and records
cash-transfer-adjusted NAV plus the exact benchmark close. A real failure
creates a critical alert.

The continuous processes can also be started directly:

```text
python scripts/run_personal_assistant.py --database data/paper.db monitor-orders --cancel-stale --poll-seconds 30
python scripts/run_operations_watchdog.py --database data/paper.db --interval-seconds 60 --alerts-jsonl data/alerts.jsonl
```

### Windows Task Scheduler

Preview the four user-level scheduled tasks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_windows_operational_tasks.ps1 -PythonPath C:\path\to\python.exe -DatabasePath C:\path\to\paper.db -WhatIf
```

Remove `-WhatIf` only after checking the resolved Python, repository,
database, alert path, and local post-close time. The installer registers the
monitor and watchdog at logon, the operations cycle every 10 minutes, and
the paper observation at 4:30 PM local time on weekdays. On this workstation
that time is safely after the NYSE close.

By default the tasks use the current user's interactive security context.
For operation while logged out, change them in Task Scheduler to a dedicated
least-privilege account, select "Run whether user is logged on or not", and
verify that account can read the repository and paper credentials, write
only the selected database/backups/alert path, and reach Alpaca. Run each
task manually once and inspect its exit code, SQLite alerts, JSONL output,
and heartbeat before calling the cadence operational.

The supervisor should also:

- restart long-lived processes on unexpected exit with bounded backoff;
- capture stdout/stderr;
- alert when either process has not produced a heartbeat;
- never substitute restart loops for investigating repeated failures.

`data/alerts.jsonl` is a local delivery boundary for a log shipper or paging
sidecar. Durable alert state remains in SQLite until acknowledged.

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

The recovery drill creates a consistent backup, restores it to a temporary
database, runs SQLite integrity checks on both copies, and compares every
table count. It never replaces the live database. A successful drill expires
for health purposes after 30 days by default.
