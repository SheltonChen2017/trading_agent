# Operations runbook

The execution monitor and the operations watchdog are separate processes. The
monitor owns broker-order reconciliation; the watchdog observes readiness,
portfolio-ledger reconciliation, backups and recovery drills. Neither process
may be the only copy of the other.

## Before starting

1. Keep `config.PAPER_TRADING = True`.
2. Configure paper credentials and a writable `TRADING_ASSISTANT_DB`.
3. Run `readiness`.
4. Explicitly bootstrap the portfolio journal once, then reconcile it.
5. Run a backup/restore drill.
6. Configure the external supervisor to restart both processes.

## Supervised commands

```text
python scripts/run_personal_assistant.py monitor-orders --poll-seconds 30
python scripts/run_operations_watchdog.py --interval-seconds 60 --alerts-jsonl data/alerts.jsonl
```

The supervisor should:

- restart on unexpected exit with bounded backoff;
- capture stdout/stderr;
- alert when either process has not produced a heartbeat;
- run under a dedicated OS account with access only to the database,
  credentials and application directory;
- never substitute restart loops for investigating repeated failures.

`data/alerts.jsonl` is a local delivery boundary for a log shipper or paging
sidecar. Durable alert state also remains in SQLite until acknowledged.

## Incident response

1. Activate the persistent kill switch.
2. Preserve logs, the database and WAL files.
3. Check ambiguous broker outcomes before retrying anything.
4. Query Alpaca directly for current orders, positions and account state.
5. Run order synchronization and portfolio-ledger reconciliation.
6. Keep the kill switch active until every discrepancy is explained.
7. Record the incident, corrective action and recovery evidence.

## Recovery drill

The recovery drill creates a consistent backup, restores it to a temporary
database, runs SQLite integrity checks on both copies and compares every table
count. It never replaces the live database. A successful drill is recorded in
`system_state` and expires for health purposes after 30 days by default.
