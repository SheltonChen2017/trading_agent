"""
Small SQLite state store for the personal assistant.

SQLite is deliberately used before introducing an external service: it
provides transactions, uniqueness constraints, and an auditable history
without creating deployment or credential overhead for one user.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from assistant.proposal_status import (
    FILLED,
    UNRESOLVED_BROKER_STATE_STATUSES,
)
from assistant.schemas import DecisionPacket

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trading_assistant.db"
# Trading days in this project are Eastern-market days (see
# get_execution_budget_usage), not UTC days.
_EASTERN = ZoneInfo("America/New_York")


def _hash_payload(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def configured_db_path() -> Path:
    return Path(os.environ.get("TRADING_ASSISTANT_DB", DEFAULT_DB_PATH))


class DuplicateIntentConflict(Exception):
    """Another proposal for the same ticker/side already has (or may have) a
    live order at the broker.

    Raised by claim_proposal() rather than returned as None so the caller can
    tell "someone else is already trading this ticker/side" apart from the
    ordinary "this proposal was already claimed" outcome, which needs a very
    different message.
    """


class AssistantStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else configured_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS decision_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS trade_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_orders (
                    order_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_order_events (
                    event_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    filled_qty REAL,
                    filled_avg_price REAL,
                    fill_qty REAL,
                    fill_price REAL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_reservations (
                    proposal_id TEXT PRIMARY KEY,
                    trading_day TEXT NOT NULL,
                    reserved_notional REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS system_state (
                    state_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS allocation_batches (
                    batch_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_evaluations (
                    strategy_key TEXT PRIMARY KEY,
                    last_evaluated_at TEXT NOT NULL,
                    last_result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    called_at TEXT NOT NULL,
                    function_name TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    response_json TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS journal_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal_postings (
                    posting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    quantity TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(transaction_id)
                        REFERENCES journal_transactions(transaction_id)
                );
                CREATE TABLE IF NOT EXISTS ledger_reconciliation_runs (
                    reconciliation_id TEXT PRIMARY KEY,
                    reconciled_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    matched INTEGER NOT NULL,
                    mismatch_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operational_alerts (
                    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    acknowledged_at TEXT
                );
                CREATE TABLE IF NOT EXISTS paper_evidence_epochs (
                    evidence_epoch TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    lineage_json TEXT NOT NULL,
                    lineage_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_account_observations (
                    observation_id TEXT PRIMARY KEY,
                    evidence_epoch TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    total_equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    benchmark_ticker TEXT NOT NULL,
                    benchmark_close REAL NOT NULL,
                    net_external_flow REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(evidence_epoch)
                        REFERENCES paper_evidence_epochs(evidence_epoch),
                    UNIQUE(evidence_epoch, session_date)
                );
                CREATE TABLE IF NOT EXISTS operational_drill_runs (
                    drill_id TEXT PRIMARY KEY,
                    drill_type TEXT NOT NULL,
                    performed_at TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    evidence_epoch TEXT,
                    code_commit TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_proposals_status
                    ON trade_proposals(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_broker_events_order_at
                    ON broker_order_events(order_id, event_at);
                CREATE INDEX IF NOT EXISTS idx_broker_events_proposal_at
                    ON broker_order_events(proposal_id, event_at);
                CREATE INDEX IF NOT EXISTS idx_execution_reservations_day
                    ON execution_reservations(trading_day);
                CREATE INDEX IF NOT EXISTS idx_ai_runs_function_called_at
                    ON ai_runs(function_name, called_at);
                CREATE INDEX IF NOT EXISTS idx_journal_postings_transaction
                    ON journal_postings(transaction_id, posting_id);
                CREATE INDEX IF NOT EXISTS idx_ledger_reconciliation_at
                    ON ledger_reconciliation_runs(reconciled_at);
                CREATE INDEX IF NOT EXISTS idx_operational_alerts_status
                    ON operational_alerts(status, severity, last_seen_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_paper_epoch
                    ON paper_evidence_epochs(status) WHERE status = 'active';
                CREATE INDEX IF NOT EXISTS idx_paper_observations_epoch_date
                    ON paper_account_observations(evidence_epoch, session_date);
                CREATE INDEX IF NOT EXISTS idx_operational_drills_type_at
                    ON operational_drill_runs(drill_type, performed_at);
                """
            )
            self._migrate_decision_packet_identity(connection)

    def _migrate_decision_packet_identity(self, connection: sqlite3.Connection) -> None:
        """`generated_at` alone conflates different serialized payloads
        that happen to share a build timestamp -- e.g. the UI's cached
        base packet vs. that same packet enriched with live events via
        `dataclasses.replace(base_packet, upcoming_events=events)`, which
        preserves `generated_at` unchanged (GPT review, 2026-08-01: the
        prior generated_at-only unique index silently discarded whichever
        of the two variants was saved second -- an insertion-order-
        dependent loss of the actual audit record). Backfills
        `payload_hash` for any pre-existing row from before this column
        existed, collapses only EXACT (generated_at, payload_hash)
        duplicates -- never a different payload sharing a timestamp --
        then enforces the composite identity via a unique index. No-op
        once already migrated, so safe on every AssistantStore()
        construction."""
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(decision_packets)")}
        if "payload_hash" not in columns:
            connection.execute("ALTER TABLE decision_packets ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
        unhashed = connection.execute(
            "SELECT id, payload_json FROM decision_packets WHERE payload_hash = ''"
        ).fetchall()
        for row in unhashed:
            connection.execute(
                "UPDATE decision_packets SET payload_hash = ? WHERE id = ?",
                (_hash_payload(row["payload_json"]), row["id"]),
            )
        connection.execute("DROP INDEX IF EXISTS idx_decision_packets_generated_at")
        connection.execute(
            """
            DELETE FROM decision_packets
            WHERE id NOT IN (
                SELECT MIN(id) FROM decision_packets GROUP BY generated_at, payload_hash
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_packets_identity "
            "ON decision_packets(generated_at, payload_hash)"
        )

    def save_decision_packet(self, packet: DecisionPacket) -> int:
        """Persists one decision packet, keyed by (`generated_at`,
        `payload_hash`) -- NOT `generated_at` alone. `generated_at` marks
        when the base account snapshot was built, but `dataclasses.replace()`
        can attach post-build enrichment (e.g. live events) onto a packet
        while preserving its original `generated_at`, producing a genuinely
        different serialized payload under the same timestamp (GPT review,
        2026-08-01: a generated_at-only unique key silently discarded
        whichever variant -- base or event-enriched -- was saved second,
        an insertion-order-dependent loss of the actual audit record).
        `payload_hash` disambiguates those cases while `generated_at` still
        collapses only genuinely IDENTICAL payloads saved more than once
        (e.g. from a second browser tab or a page reload) into one row,
        returning the ORIGINAL row's id rather than inserting a duplicate."""
        payload = json.dumps(packet.to_dict(), sort_keys=True)
        payload_hash = _hash_payload(payload)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO decision_packets(generated_at, schema_version, payload_json, payload_hash) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(generated_at, payload_hash) DO NOTHING",
                (packet.generated_at, packet.schema_version, payload, payload_hash),
            )
            if cursor.rowcount == 1:
                return int(cursor.lastrowid)
            existing = connection.execute(
                "SELECT id FROM decision_packets WHERE generated_at = ? AND payload_hash = ?",
                (packet.generated_at, payload_hash),
            ).fetchone()
            return int(existing["id"])

    def prune_decision_packets_older_than(self, days: int) -> int:
        """Explicit, opt-in retention cleanup -- deletes decision packets
        whose `generated_at` is older than `days` ago. NEVER runs
        automatically or silently (GPT review, 2026-07-31: decision
        packets had no retention policy at all, so the table grows
        unboundedly even after deduplication above) -- exposed as
        `python scripts/run_personal_assistant.py prune-packets
        --older-than-days N`, a command the user must explicitly invoke.

        No foreign-key relationship from trade_proposals/broker_orders/
        allocation_batches to decision_packets currently exists in this
        schema, so pruning is safe project-wide as of this writing; if a
        reference from proposals to decision packets is ever introduced,
        this function must be updated to exclude referenced packets.
        Returns the number of rows deleted."""
        if days <= 0:
            raise ValueError(f"days must be positive, got {days!r}.")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM decision_packets WHERE generated_at < ?", (cutoff,))
            return cursor.rowcount

    def save_proposal(self, proposal: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(proposal, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trade_proposals(
                    proposal_id, created_at, expires_at, status,
                    idempotency_key, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO NOTHING
                """,
                (
                    proposal["proposal_id"],
                    proposal["created_at"],
                    proposal["expires_at"],
                    proposal["status"],
                    proposal["idempotency_key"],
                    payload,
                    now,
                ),
            )

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        proposal = json.loads(row["payload_json"])
        proposal["status"] = row["status"]
        return proposal

    def get_proposal_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM trade_proposals WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        proposal = json.loads(row["payload_json"])
        proposal["status"] = row["status"]
        return proposal

    def get_proposal_by_broker_order_id(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT p.payload_json, p.status
                FROM broker_orders AS b
                JOIN trade_proposals AS p ON p.proposal_id = b.proposal_id
                WHERE b.order_id = ?
                """,
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        proposal = json.loads(row["payload_json"])
        proposal["status"] = row["status"]
        return proposal

    def update_proposal_status(self, proposal_id: str, status: str, **updates: Any) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")
        proposal.update(updates)
        proposal["status"] = status
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE trade_proposals SET status = ?, payload_json = ?, updated_at = ? WHERE proposal_id = ?",
                (status, json.dumps(proposal, sort_keys=True), now, proposal_id),
            )
        return proposal

    def update_proposal_status_if_current(
        self,
        proposal_id: str,
        *,
        expected_statuses: tuple[str, ...],
        new_status: str,
        preserve_updated_at: str | None = None,
        **updates: Any,
    ) -> dict[str, Any] | None:
        """Atomically update only while the proposal is in an expected state.

        `preserve_updated_at` writes that timestamp instead of "now". Use it
        ONLY when reverting a proposal to the state it was already in -- a
        no-progress bounce, not a transition. `updated_at` means "when did
        this enter its current status", and the broker-absence grace period
        is measured from it, so refreshing it on a bounce restarts the very
        clock the caller is waiting on: repeated reconcile attempts inside
        the grace window would each push the deadline out and the proposal
        could never age enough to resolve (found 2026-07-30 while reviewing
        the reconciliation-hardening round).
        """
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json, status FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown proposal: {proposal_id}")
            if row["status"] not in expected_statuses:
                connection.rollback()
                return None
            proposal = json.loads(row["payload_json"])
            proposal.update(updates)
            proposal["status"] = new_status
            now = preserve_updated_at or datetime.now(timezone.utc).isoformat()
            connection.execute(
                "UPDATE trade_proposals SET status = ?, payload_json = ?, updated_at = ? "
                "WHERE proposal_id = ? AND status = ?",
                (
                    new_status,
                    json.dumps(proposal, sort_keys=True, default=str),
                    now,
                    proposal_id,
                    row["status"],
                ),
            )
            connection.commit()
            return proposal
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_proposal(
        self,
        proposal_id: str,
        *,
        expected_status: str | tuple[str, ...] = "proposed",
        new_status: str = "validating",
        not_expired_after: str | None = None,
        conflicting_intent_statuses: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        """
        Atomically flips status from `expected_status` (a single status,
        or a tuple of statuses any of which is acceptable -- e.g.
        reconciliation may claim from either "submitting" or
        "submission_unknown") to `new_status` in one
        `UPDATE ... WHERE status IN (...)` statement, so two concurrent
        callers can never both believe they claimed the same proposal --
        SQLite serializes writers against the same database file, and
        exactly one UPDATE affects a row. Returns the claimed proposal
        (with its embedded "status" updated to `new_status` and transient
        `_claimed_from_updated_at` metadata containing the prior row
        timestamp) on success,
        or None if the row didn't exist, wasn't in one of the
        `expected_status` values (already claimed by someone else,
        already terminal, etc.), or (when `not_expired_after` is given)
        its `expires_at` is already past that timestamp -- callers MUST
        treat None as "stop, do not proceed."

        `not_expired_after` (an ISO-8601 UTC timestamp string, lexically
        comparable the same way every timestamp in this table is stored)
        adds `AND expires_at >= ?` to the guard. Pass it when claiming
        for validation so an already-expired-but-still-"proposed" row can
        never be claimed; omit it when the caller's OWN intent is to
        transition an expired row to "expired" -- that call still only
        succeeds if the row is presently `expected_status`, so it can
        never clobber "executed"/"approved"/"validating"/"submission_failed".

        This replaces the previous pattern of a plain get_proposal() read
        followed by a much-later update_proposal_status() write, which
        left a real window where two concurrent approvals could both pass
        the initial status check before either one wrote back -- and,
        separately, an unconditional expiry write that could stomp an
        already-executed proposal's status if approval was invoked again
        past its expiry.

        `conflicting_intent_statuses` closes the remaining, CROSS-proposal
        race (independent review, 2026-07-30). The guard above serializes
        one proposal_id, but the duplicate-order rule is about ticker+side,
        and that was evaluated from a plain snapshot read
        (recent_executed_intents() plus the broker's open orders) far away
        from any lock. Two DIFFERENT proposals to buy the same ticker,
        approved concurrently before either order became visible at the
        broker, could therefore both observe "no duplicate" and both
        submit -- distinct idempotency keys make them two genuinely
        separate real orders, so idempotency does not help. When this is
        passed, the claim additionally requires that no OTHER proposal
        with the same ticker/side sits in any of those statuses, checked
        inside the claim's own BEGIN IMMEDIATE transaction. Raises
        DuplicateIntentConflict (not None) when one does, so the caller can
        distinguish it from an ordinary failed claim.
        """
        expected_statuses = (expected_status,) if isinstance(expected_status, str) else tuple(expected_status)
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in expected_statuses)
        query = f"UPDATE trade_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status IN ({placeholders})"
        params: list[Any] = [new_status, now, proposal_id, *expected_statuses]
        if not_expired_after is not None:
            query += " AND expires_at >= ?"
            params.append(not_expired_after)

        # BEGIN IMMEDIATE takes the write lock before the conflict SELECT, so
        # the read and the UPDATE are one serialized unit. Without that the
        # duplicate check would be a plain snapshot read and two DIFFERENT
        # proposals for the same ticker/side could both observe "no duplicate"
        # before either became visible at the broker.
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            target_before = connection.execute(
                "SELECT payload_json, status, expires_at, updated_at "
                "FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if target_before is None or target_before["status"] not in expected_statuses:
                connection.rollback()
                return None
            if (
                not_expired_after is not None
                and target_before["expires_at"] < not_expired_after
            ):
                connection.rollback()
                return None
            if conflicting_intent_statuses:
                conflict = self._find_conflicting_intent(
                    connection, proposal_id, tuple(conflicting_intent_statuses)
                )
                if conflict is not None:
                    connection.rollback()
                    raise DuplicateIntentConflict(conflict)
            cursor = connection.execute(query, params)
            if cursor.rowcount != 1:
                connection.rollback()
                return None
            row = connection.execute(
                "SELECT payload_json FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            return None
        proposal = json.loads(row["payload_json"])
        proposal["status"] = new_status
        # Transaction-local metadata used by reconciliation to judge whether
        # the state it just claimed was old enough for a broker 404 to be
        # believable. This is not part of the persisted proposal schema:
        # claim_proposal() never writes payload_json.
        proposal["_claimed_from_updated_at"] = target_before["updated_at"]
        return proposal

    @staticmethod
    def _intent_identity(payload: str) -> tuple[str, str] | None:
        """(TICKER, side) of a stored proposal, or None if unreadable."""
        try:
            intent = json.loads(payload).get("intent") or {}
            ticker = str(intent["ticker"]).upper()
            side = str(intent["side"]).lower()
        except Exception:
            return None
        return (ticker, side) if ticker and side else None

    def _find_conflicting_intent(
        self, connection: sqlite3.Connection, proposal_id: str, statuses: tuple[str, ...],
    ) -> str | None:
        """Describe another proposal that already holds this ticker/side, if any.

        Duplicate identity is ticker+side only, never shares -- the same rule
        the snapshot-based duplicate check in validate_proposal_for_execution()
        uses, so the two cannot disagree about what counts as a duplicate.

        Fails CLOSED on unreadable rows: a proposal whose own intent cannot be
        parsed is not claimable at all, and an OTHER row that cannot be parsed
        is treated as a conflict rather than assumed harmless. Being unable to
        rule out a live order is not evidence that there isn't one.
        """
        target = connection.execute(
            "SELECT payload_json FROM trade_proposals WHERE proposal_id = ?", (proposal_id,),
        ).fetchone()
        if target is None:
            return None  # the UPDATE below will fail on its own terms
        identity = self._intent_identity(target["payload_json"])
        if identity is None:
            return (
                f"Proposal {proposal_id} has no readable ticker/side, so it cannot be "
                "checked for a duplicate live order."
            )
        placeholders = ",".join("?" for _ in statuses)
        rows = connection.execute(
            f"SELECT proposal_id, payload_json, status FROM trade_proposals "
            f"WHERE status IN ({placeholders}) AND proposal_id != ?",
            (*statuses, proposal_id),
        ).fetchall()
        for row in rows:
            other = self._intent_identity(row["payload_json"])
            if other is None:
                return (
                    f"Proposal {row['proposal_id']} (status {row['status']}) has an unreadable "
                    "intent, so a duplicate order for this ticker/side cannot be ruled out."
                )
            if other == identity:
                ticker, side = identity
                return (
                    f"Proposal {row['proposal_id']} is already {side}ing {ticker} "
                    f"(status {row['status']}); refusing to claim a second order for the same "
                    "ticker and side until that one reaches a terminal state."
                )
        return None

    def reclaim_stale_status(
        self,
        proposal_id: str,
        *,
        expected_status: str,
        new_status: str,
        stale_before: str,
        extra_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Like claim_proposal(), but the guard is staleness (`updated_at <
        stale_before`) instead of expiry -- recovers a proposal stranded
        in a non-terminal status (e.g. "reconciling") after a crash left
        no in-process handler to run the normal recovery logic. `updated_at`
        already reflects the moment the proposal entered `expected_status`
        (every status transition, including claim_proposal(), rewrites
        it), so no separate "started_at" column is needed.

        `extra_updates` (e.g. `recovered_at`/`error` audit fields) is
        merged into the JSON payload and written in the SAME conditional
        UPDATE as the status transition -- NOT as a separate, later write.
        A prior version wrote the status transition here and left the
        caller (recover_stale_reconciliation()) to persist audit metadata
        via a separate, unconditional update_proposal_status() call
        afterward; in the gap between the two writes, a different worker
        could claim the now-retryable proposal, resolve it to a genuinely
        terminal state (e.g. "executed"), and have that second
        unconditional write silently stomp it back to `new_status`
        (2026-07-29, GPT review). The final UPDATE below re-verifies
        `status = expected_status AND updated_at < stale_before` at write
        time (not just at an earlier read), so if anything changed the
        row in between, this call safely returns None instead of
        overwriting whatever the row became -- the same principle
        claim_proposal() already relies on for its own atomicity.

        Atomic and safe against a concurrent recovery attempt or a
        genuinely still-in-flight (recent) claim for the same reason
        claim_proposal() is: exactly one `UPDATE ... WHERE status = ? AND
        updated_at < ?` can affect the row, so a proposal claimed only
        moments ago (not actually stranded) is correctly left alone
        (2026-07-28, GPT review).
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM trade_proposals WHERE proposal_id = ? AND status = ? AND updated_at < ?",
                (proposal_id, expected_status, stale_before),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            payload.update(extra_updates or {})
            payload["status"] = new_status
            cursor = connection.execute(
                "UPDATE trade_proposals SET status = ?, payload_json = ?, updated_at = ? "
                "WHERE proposal_id = ? AND status = ? AND updated_at < ?",
                (new_status, json.dumps(payload, sort_keys=True), now, proposal_id, expected_status, stale_before),
            )
            if cursor.rowcount != 1:
                # Something changed the row between our read and this
                # write (a concurrent recovery attempt, or a genuine
                # resolution reaching a different terminal state) --
                # never overwrite whatever it became.
                return None
        return payload

    def list_proposals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT payload_json, status FROM trade_proposals"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            proposal = json.loads(row["payload_json"])
            proposal["status"] = row["status"]
            result.append(proposal)
        return result

    def list_proposals_by_statuses(
        self, statuses: tuple[str, ...] | list[str], limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Proposals in any of `statuses`, each carrying the authoritative
        `status` and `updated_at` from the row rather than from the stored
        payload.

        `updated_at` is rewritten by every status transition, so on a
        non-terminal proposal it is exactly "when did this enter its
        current state" -- which reconciliation needs in order to tell a
        submission that is still in flight from one that has genuinely
        been stranded (see order_reconciler's absence age guard).
        """
        normalized = tuple(dict.fromkeys(statuses))
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json, status, updated_at FROM trade_proposals "
                f"WHERE status IN ({placeholders}) ORDER BY created_at ASC LIMIT ?",
                (*normalized, limit),
            ).fetchall()
        result = []
        for row in rows:
            proposal = json.loads(row["payload_json"])
            proposal["status"] = row["status"]
            proposal["updated_at"] = row["updated_at"]
            result.append(proposal)
        return result

    def project_broker_order_event(
        self,
        *,
        event_id: str,
        proposal_id: str,
        order: dict[str, Any],
        event_type: str,
        event_at: str,
        new_proposal_status: str,
        expected_current_statuses: tuple[str, ...],
        proposal_updates: dict[str, Any],
        fill_qty: float | None = None,
        fill_price: float | None = None,
        raw_event: dict[str, Any] | None = None,
        preserve_if_set: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Atomically append an event and advance its proposal/order projection.

        The conditional current-status set prevents a delayed accepted event
        from racing a fill and moving the proposal backward. A lower
        cumulative filled quantity is also journaled but never projected.
        Duplicate events remain eligible to project so a crash after event
        insertion but before an older-version proposal update can self-heal.

        `preserve_if_set` names fields in `proposal_updates` that must NOT
        overwrite an already-present truthy value on the stored proposal
        (e.g. `broker_accepted_at` -- the first-ever accepted timestamp,
        not whichever concurrent caller's write happens to land last).
        Resolved HERE, against the proposal just read inside this same
        atomic transaction, rather than by the caller reading
        get_proposal() beforehand: that earlier read was a real race --
        two callers processing near-simultaneous events (e.g. the poll
        loop and the trade-update stream) could both read "not yet set"
        before either committed, so the second writer's transaction could
        clobber the first writer's correctly-preserved value (independent
        review, 2026-07-29).
        """
        payload = raw_event if raw_event is not None else order
        now = datetime.now(timezone.utc).isoformat()
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO broker_order_events(
                    event_id, order_id, proposal_id, event_type, event_at,
                    status, filled_qty, filled_avg_price, fill_qty, fill_price,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    event_id,
                    str(order["order_id"]),
                    proposal_id,
                    event_type,
                    event_at,
                    str(order.get("status", "unknown")),
                    order.get("filled_qty"),
                    order.get("filled_avg_price"),
                    fill_qty,
                    fill_price,
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )
            row = connection.execute(
                "SELECT payload_json, status FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown proposal: {proposal_id}")
            proposal = json.loads(row["payload_json"])
            proposal["status"] = row["status"]

            current_filled = 0.0
            incoming_filled = 0.0
            try:
                current_filled = float(
                    (proposal.get("broker_order") or {}).get("filled_qty") or 0.0
                )
                incoming_filled = float(order.get("filled_qty") or 0.0)
            except (TypeError, ValueError):
                # Malformed broker quantities are never used to justify an
                # otherwise-forbidden transition.
                current_filled = incoming_filled = 0.0
            status_allows_projection = row["status"] in expected_current_statuses
            quantity_allows_projection = incoming_filled >= current_filled
            if not status_allows_projection or not quantity_allows_projection:
                connection.commit()
                proposal["broker_event_inserted"] = cursor.rowcount == 1
                proposal["broker_event_projected"] = False
                return proposal

            submitted_at = str(order.get("submitted_at") or event_at)
            connection.execute(
                """
                INSERT INTO broker_orders(
                    order_id, proposal_id, submitted_at, status, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    proposal_id = excluded.proposal_id,
                    status = excluded.status,
                    payload_json = excluded.payload_json
                """,
                (
                    str(order["order_id"]),
                    proposal_id,
                    submitted_at,
                    str(order.get("status", "unknown")),
                    json.dumps(order, sort_keys=True, default=str),
                ),
            )
            effective_updates = dict(proposal_updates)
            for field in preserve_if_set:
                if proposal.get(field):
                    effective_updates.pop(field, None)
            proposal.update(effective_updates)
            proposal["status"] = new_proposal_status
            connection.execute(
                """
                UPDATE trade_proposals
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE proposal_id = ?
                """,
                (
                    new_proposal_status,
                    json.dumps(proposal, sort_keys=True, default=str),
                    now,
                    proposal_id,
                ),
            )
            connection.commit()
            proposal["broker_event_inserted"] = cursor.rowcount == 1
            proposal["broker_event_projected"] = True
            return proposal
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_broker_order_events(
        self,
        *,
        proposal_id: str | None = None,
        order_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM broker_order_events"
        params: list[Any] = []
        clauses = []
        if proposal_id is not None:
            clauses.append("proposal_id = ?")
            params.append(proposal_id)
        if order_id is not None:
            clauses.append("order_id = ?")
            params.append(order_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY event_at ASC, rowid ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "order_id": row["order_id"],
                "proposal_id": row["proposal_id"],
                "event_type": row["event_type"],
                "event_at": row["event_at"],
                "status": row["status"],
                "filled_qty": row["filled_qty"],
                "filled_avg_price": row["filled_avg_price"],
                "fill_qty": row["fill_qty"],
                "fill_price": row["fill_price"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def reserve_execution_budget(
        self,
        proposal_id: str,
        *,
        trading_day: str,
        notional: float,
        max_daily_notional: float,
        max_daily_orders: int,
    ) -> dict[str, Any]:
        """Atomically reserve one submission against persistent daily caps.

        These are gross *submission* counters, not open-exposure counters.
        A broker-observed rejected order therefore continues consuming both
        caps: it reached the broker and must not be retried indefinitely by
        repeatedly releasing the reservation. Only confirmed non-submission
        is released through mark_submission_failed_and_release().
        """
        if not math.isfinite(notional) or notional <= 0:
            raise ValueError(f"notional must be positive and finite, got {notional!r}.")
        if not math.isfinite(max_daily_notional) or max_daily_notional <= 0:
            raise ValueError("max_daily_notional must be positive and finite.")
        if isinstance(max_daily_orders, bool) or not isinstance(max_daily_orders, int) or max_daily_orders <= 0:
            raise ValueError("max_daily_orders must be a positive integer.")
        now = datetime.now(timezone.utc).isoformat()
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM execution_reservations WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return {
                    "proposal_id": proposal_id,
                    "trading_day": existing["trading_day"],
                    "reserved_notional": existing["reserved_notional"],
                    "already_reserved": True,
                }
            totals = connection.execute(
                "SELECT COUNT(*) AS order_count, COALESCE(SUM(reserved_notional), 0) AS notional "
                "FROM execution_reservations WHERE trading_day = ?",
                (trading_day,),
            ).fetchone()
            next_count = int(totals["order_count"]) + 1
            next_notional = float(totals["notional"]) + notional
            if next_count > max_daily_orders:
                raise ValueError(
                    f"Daily order-count budget would be {next_count}, exceeding {max_daily_orders}."
                )
            if next_notional > max_daily_notional:
                raise ValueError(
                    f"Daily submitted notional would be ${next_notional:,.2f}, "
                    f"exceeding ${max_daily_notional:,.2f}."
                )
            connection.execute(
                "INSERT INTO execution_reservations(proposal_id, trading_day, reserved_notional, created_at) "
                "VALUES (?, ?, ?, ?)",
                (proposal_id, trading_day, notional, now),
            )
            connection.commit()
            return {
                "proposal_id": proposal_id,
                "trading_day": trading_day,
                "reserved_notional": notional,
                "daily_order_count": next_count,
                "daily_reserved_notional": next_notional,
                "already_reserved": False,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_execution_budget_usage(self, trading_day: str) -> dict[str, Any]:
        """Usage for one EASTERN trading day.

        `trading_day` is an Eastern-market date (that is how callers build
        it -- see assistant/readiness.py and the reservation write in
        assistant/execution_service.py), but `broker_order_events.event_at`
        is an absolute timestamp, normally UTC. Comparing the two by string
        prefix mis-attributed any fill after 8:00pm Eastern to the NEXT
        trading day, because that instant is already past midnight UTC
        (independent review, 2026-07-29, reproduced with an extended-hours
        fill). Fills are therefore bucketed by converting each event's real
        instant to Eastern, which is also DST-correct -- a fixed UTC offset
        would drift by an hour twice a year.
        """
        with self._connect() as connection:
            reserved = connection.execute(
                "SELECT COUNT(*) AS order_count, COALESCE(SUM(reserved_notional), 0) AS notional "
                "FROM execution_reservations WHERE trading_day = ?",
                (trading_day,),
            ).fetchone()
            # Pre-filter to the 3 UTC dates that can possibly contain the
            # Eastern day (yesterday/today/tomorrow) so this stays an
            # indexed-ish scan rather than reading the whole journal.
            candidate_dates = [trading_day]
            try:
                day = datetime.fromisoformat(trading_day).date()
                candidate_dates = [
                    (day - timedelta(days=1)).isoformat(),
                    day.isoformat(),
                    (day + timedelta(days=1)).isoformat(),
                ]
            except ValueError:
                pass
            placeholders = ",".join("?" for _ in candidate_dates)
            rows = connection.execute(
                f"SELECT event_at, fill_qty, fill_price FROM broker_order_events "
                f"WHERE substr(event_at, 1, 10) IN ({placeholders}) "
                "AND fill_qty IS NOT NULL AND fill_price IS NOT NULL",
                candidate_dates,
            ).fetchall()

        filled_notional = 0.0
        for row in rows:
            try:
                parsed = datetime.fromisoformat(str(row["event_at"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.astimezone(_EASTERN).date().isoformat() != trading_day:
                continue
            try:
                filled_notional += abs(float(row["fill_qty"]) * float(row["fill_price"]))
            except (TypeError, ValueError):
                continue

        return {
            "trading_day": trading_day,
            "submitted_order_count": int(reserved["order_count"]),
            "submitted_notional": float(reserved["notional"]),
            "filled_notional": filled_notional,
        }

    def release_execution_reservation(self, proposal_id: str) -> bool:
        """Release a reservation only when broker absence is definitive.

        Callers must not use this for timeouts or other ambiguous outcomes:
        those still represent possible exposure and must continue consuming
        the daily submission budget until reconciliation proves otherwise.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM execution_reservations WHERE proposal_id = ?",
                (proposal_id,),
            )
        return cursor.rowcount == 1

    def mark_submission_failed_and_release(
        self,
        proposal_id: str,
        *,
        expected_statuses: tuple[str, ...],
        error: str,
        reconciled_at: str | None = None,
        not_updated_after: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically record confirmed broker absence and release its budget.

        When ``not_updated_after`` is supplied, the transition also requires
        the proposal's current status timestamp to be no newer than that UTC
        cutoff. This makes the absence-age check and the destructive release
        one transaction: a poller that read an old row cannot release the
        reservation after another worker has just claimed/refreshed it.
        """
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json, status, updated_at FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown proposal: {proposal_id}")
            if (
                row["status"] not in expected_statuses
                or (
                    not_updated_after is not None
                    and row["updated_at"] > not_updated_after
                )
            ):
                connection.rollback()
                return None
            proposal = json.loads(row["payload_json"])
            proposal.update({"status": "submission_failed", "error": error})
            if reconciled_at is not None:
                proposal["reconciled_at"] = reconciled_at
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "UPDATE trade_proposals SET status = ?, payload_json = ?, updated_at = ? "
                "WHERE proposal_id = ?",
                (
                    "submission_failed",
                    json.dumps(proposal, sort_keys=True, default=str),
                    now,
                    proposal_id,
                ),
            )
            connection.execute(
                "DELETE FROM execution_reservations WHERE proposal_id = ?",
                (proposal_id,),
            )
            connection.commit()
            return proposal
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_system_state(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO system_state(state_key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(state_key) DO UPDATE SET "
                "value_json = excluded.value_json, updated_at = excluded.updated_at",
                (key, json.dumps(value, sort_keys=True), now),
            )

    def get_system_state(self, key: str, default: Any = None) -> Any:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM system_state WHERE state_key = ?", (key,)
            ).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def set_kill_switch(self, active: bool, *, reason: str = "") -> None:
        self.set_system_state(
            "kill_switch",
            {
                "active": bool(active),
                "reason": reason,
                "changed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def get_kill_switch(self) -> dict[str, Any]:
        value = self.get_system_state("kill_switch", default={"active": False, "reason": ""})
        return value if isinstance(value, dict) else {"active": bool(value), "reason": ""}

    def database_integrity_check(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        return [str(row[0]) for row in rows]

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("Backup destination must be different from the live database path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(self.path)
        destination_connection = sqlite3.connect(target)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        integrity = self.verify_database_file(target)
        if integrity != ["ok"]:
            raise RuntimeError(
                f"Backup integrity check failed for {target}: {integrity}"
            )
        self.set_system_state(
            "last_database_backup",
            {
                "path": str(target),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "integrity": integrity,
            },
        )
        return target

    @staticmethod
    def verify_database_file(path: str | Path) -> list[str]:
        connection = sqlite3.connect(Path(path))
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        finally:
            connection.close()
        return [str(row[0]) for row in rows]

    def append_journal_transaction(
        self,
        *,
        transaction_id: str,
        occurred_at: str,
        source: str,
        external_id: str,
        description: str,
        postings: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Append one immutable journal transaction exactly once.

        Balance and numeric validation belong to `assistant.portfolio_ledger`;
        this method owns atomic persistence and external-id idempotency.
        """
        now = datetime.now(timezone.utc).isoformat()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO journal_transactions(
                    transaction_id, occurred_at, source, external_id,
                    description, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO NOTHING
                """,
                (
                    transaction_id,
                    occurred_at,
                    source,
                    external_id,
                    description,
                    json.dumps(metadata or {}, sort_keys=True, default=str),
                    now,
                ),
            )
            if cursor.rowcount != 1:
                connection.commit()
                return False
            connection.executemany(
                """
                INSERT INTO journal_postings(
                    transaction_id, account, asset, amount, quantity,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        transaction_id,
                        posting["account"],
                        posting.get("asset", "USD"),
                        posting["amount"],
                        posting.get("quantity"),
                        json.dumps(
                            posting.get("metadata") or {},
                            sort_keys=True,
                            default=str,
                        ),
                    )
                    for posting in postings
                ],
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_journal_postings(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT t.transaction_id, t.occurred_at, t.source,
                       t.external_id, t.description,
                       p.posting_id, p.account, p.asset, p.amount,
                       p.quantity, p.metadata_json
                FROM journal_transactions t
                JOIN journal_postings p
                  ON p.transaction_id = t.transaction_id
                ORDER BY t.occurred_at ASC, t.transaction_id ASC,
                         p.posting_id ASC
                """
            ).fetchall()
        return [
            {
                "transaction_id": row["transaction_id"],
                "occurred_at": row["occurred_at"],
                "source": row["source"],
                "external_id": row["external_id"],
                "description": row["description"],
                "posting_id": row["posting_id"],
                "account": row["account"],
                "asset": row["asset"],
                "amount": row["amount"],
                "quantity": row["quantity"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def record_ledger_reconciliation(
        self,
        reconciliation_id: str,
        source: str,
        report: dict[str, Any],
    ) -> None:
        reconciled_at = str(
            report.get("reconciled_at")
            or datetime.now(timezone.utc).isoformat()
        )
        mismatch_count = int(report.get("mismatch_count", 0))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ledger_reconciliation_runs(
                    reconciliation_id, reconciled_at, source, matched,
                    mismatch_count, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reconciliation_id,
                    reconciled_at,
                    source,
                    1 if report.get("matched") else 0,
                    mismatch_count,
                    json.dumps(report, sort_keys=True, default=str),
                ),
            )

    def get_latest_ledger_reconciliation(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM ledger_reconciliation_runs
                ORDER BY reconciled_at DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else json.loads(row["payload_json"])

    def upsert_operational_alert(
        self,
        *,
        fingerprint: str,
        severity: str,
        category: str,
        message: str,
        details: dict[str, Any] | None = None,
        seen_at: str | None = None,
    ) -> dict[str, Any]:
        now = seen_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operational_alerts(
                    fingerprint, severity, category, message, details_json,
                    status, occurrences, first_seen_at, last_seen_at,
                    acknowledged_at
                ) VALUES (?, ?, ?, ?, ?, 'open', 1, ?, ?, NULL)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    severity = excluded.severity,
                    category = excluded.category,
                    message = excluded.message,
                    details_json = excluded.details_json,
                    status = 'open',
                    occurrences = operational_alerts.occurrences + 1,
                    last_seen_at = excluded.last_seen_at,
                    acknowledged_at = NULL
                """,
                (
                    fingerprint,
                    severity,
                    category,
                    message,
                    json.dumps(details or {}, sort_keys=True, default=str),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM operational_alerts WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return self._operational_alert_row(row)

    def list_operational_alerts(
        self, *, status: str | None = "open", limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    """
                    SELECT * FROM operational_alerts
                    ORDER BY last_seen_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM operational_alerts
                    WHERE status = ?
                    ORDER BY last_seen_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._operational_alert_row(row) for row in rows]

    def acknowledge_operational_alert(self, alert_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE operational_alerts
                SET status = 'acknowledged', acknowledged_at = ?
                WHERE alert_id = ? AND status = 'open'
                """,
                (now, alert_id),
            )
        return cursor.rowcount == 1

    def start_paper_evidence_epoch(
        self,
        evidence_epoch: str,
        *,
        started_at: str,
        lineage: dict[str, Any],
    ) -> dict[str, Any]:
        """Start one immutable-lineage paper evidence collection epoch."""
        lineage_json = json.dumps(
            lineage, sort_keys=True, separators=(",", ":"), default=str
        )
        lineage_hash = _hash_payload(lineage_json)
        now = datetime.now(timezone.utc).isoformat()
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM paper_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["status"] == "active"
                    and existing["lineage_hash"] == lineage_hash
                ):
                    connection.commit()
                    result = self._paper_evidence_epoch_row(existing)
                    result["already_started"] = True
                    return result
                raise ValueError(
                    f"Paper evidence epoch {evidence_epoch!r} already exists "
                    "with different lineage or is closed."
                )
            active = connection.execute(
                "SELECT evidence_epoch FROM paper_evidence_epochs "
                "WHERE status = 'active'"
            ).fetchone()
            if active is not None:
                raise ValueError(
                    f"Paper evidence epoch {active['evidence_epoch']!r} is "
                    "already active; close it before starting another."
                )
            connection.execute(
                """
                INSERT INTO paper_evidence_epochs(
                    evidence_epoch, started_at, ended_at, status,
                    lineage_json, lineage_hash, created_at
                ) VALUES (?, ?, NULL, 'active', ?, ?, ?)
                """,
                (
                    evidence_epoch,
                    started_at,
                    lineage_json,
                    lineage_hash,
                    now,
                ),
            )
            connection.commit()
            result = {
                "evidence_epoch": evidence_epoch,
                "started_at": started_at,
                "ended_at": None,
                "status": "active",
                "lineage": lineage,
                "lineage_hash": lineage_hash,
                "created_at": now,
                "already_started": False,
            }
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def close_paper_evidence_epoch(
        self, evidence_epoch: str, *, ended_at: str
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE paper_evidence_epochs
                SET status = 'closed', ended_at = ?
                WHERE evidence_epoch = ? AND status = 'active'
                """,
                (ended_at, evidence_epoch),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"Active paper evidence epoch not found: {evidence_epoch}"
                )
        result = self.get_paper_evidence_epoch(evidence_epoch)
        assert result is not None
        return result

    def get_active_paper_evidence_epoch(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_evidence_epochs "
                "WHERE status = 'active' LIMIT 1"
            ).fetchone()
        return None if row is None else self._paper_evidence_epoch_row(row)

    def get_paper_evidence_epoch(
        self, evidence_epoch: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
        return None if row is None else self._paper_evidence_epoch_row(row)

    @staticmethod
    def _paper_evidence_epoch_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "evidence_epoch": row["evidence_epoch"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "status": row["status"],
            "lineage": json.loads(row["lineage_json"]),
            "lineage_hash": row["lineage_hash"],
            "created_at": row["created_at"],
        }

    def append_paper_account_observation(
        self, observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Append one immutable close observation per epoch/session date."""
        payload_json = json.dumps(
            observation, sort_keys=True, separators=(",", ":"), default=str
        )
        payload_hash = _hash_payload(payload_json)
        observation_id = "paperobs-" + payload_hash[:24]
        evidence_epoch = str(observation["evidence_epoch"])
        session_date = str(observation["session_date"])
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            epoch = connection.execute(
                "SELECT status, lineage_hash FROM paper_evidence_epochs "
                "WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
            if epoch is None or epoch["status"] != "active":
                raise ValueError(
                    f"Paper evidence epoch is not active: {evidence_epoch}"
                )
            if observation.get("lineage_hash") != epoch["lineage_hash"]:
                raise ValueError(
                    "Observation lineage does not match the active evidence epoch."
                )
            existing = connection.execute(
                "SELECT * FROM paper_account_observations "
                "WHERE evidence_epoch = ? AND session_date = ?",
                (evidence_epoch, session_date),
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise ValueError(
                        f"Session {session_date} already has a different "
                        "immutable paper observation."
                    )
                connection.commit()
                result = json.loads(existing["payload_json"])
                result.update(
                    {
                        "observation_id": existing["observation_id"],
                        "payload_hash": existing["payload_hash"],
                        "already_recorded": True,
                    }
                )
                return result
            connection.execute(
                """
                INSERT INTO paper_account_observations(
                    observation_id, evidence_epoch, session_date, captured_at,
                    total_equity, cash, benchmark_ticker, benchmark_close,
                    net_external_flow, payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    evidence_epoch,
                    session_date,
                    observation["captured_at"],
                    observation["total_equity"],
                    observation["cash"],
                    observation["benchmark_ticker"],
                    observation["benchmark_close"],
                    observation["net_external_flow"],
                    payload_json,
                    payload_hash,
                ),
            )
            connection.commit()
            return {
                **observation,
                "observation_id": observation_id,
                "payload_hash": payload_hash,
                "already_recorded": False,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_paper_account_observations(
        self, evidence_epoch: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT observation_id, payload_json, payload_hash
                FROM paper_account_observations
                WHERE evidence_epoch = ?
                ORDER BY session_date ASC, captured_at ASC
                """,
                (evidence_epoch,),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.update(
                {
                    "observation_id": row["observation_id"],
                    "payload_hash": row["payload_hash"],
                }
            )
            result.append(payload)
        return result

    def record_operational_drill(
        self,
        *,
        drill_type: str,
        performed_at: str,
        passed: bool,
        evidence_epoch: str | None,
        code_commit: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        material = {
            "drill_type": drill_type,
            "performed_at": performed_at,
            "passed": bool(passed),
            "evidence_epoch": evidence_epoch,
            "code_commit": code_commit,
            "evidence": evidence,
        }
        evidence_json = json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), default=str
        )
        evidence_hash = _hash_payload(evidence_json)
        drill_id = "drill-" + _hash_payload(
            json.dumps(material, sort_keys=True, default=str)
        )[:24]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operational_drill_runs(
                    drill_id, drill_type, performed_at, passed,
                    evidence_epoch, code_commit, evidence_json, evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(drill_id) DO NOTHING
                """,
                (
                    drill_id,
                    drill_type,
                    performed_at,
                    1 if passed else 0,
                    evidence_epoch,
                    code_commit,
                    evidence_json,
                    evidence_hash,
                ),
            )
        return {
            "drill_id": drill_id,
            "drill_type": drill_type,
            "performed_at": performed_at,
            "passed": bool(passed),
            "evidence_epoch": evidence_epoch,
            "code_commit": code_commit,
            "evidence": evidence,
            "evidence_hash": evidence_hash,
        }

    def list_operational_drills(
        self,
        *,
        evidence_epoch: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if evidence_epoch is None:
                rows = connection.execute(
                    "SELECT * FROM operational_drill_runs "
                    "ORDER BY performed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM operational_drill_runs
                    WHERE evidence_epoch = ?
                    ORDER BY performed_at DESC LIMIT ?
                    """,
                    (evidence_epoch, limit),
                ).fetchall()
        return [
            {
                "drill_id": row["drill_id"],
                "drill_type": row["drill_type"],
                "performed_at": row["performed_at"],
                "passed": bool(row["passed"]),
                "evidence_epoch": row["evidence_epoch"],
                "code_commit": row["code_commit"],
                "evidence": json.loads(row["evidence_json"]),
                "evidence_hash": row["evidence_hash"],
            }
            for row in rows
        ]

    @staticmethod
    def _operational_alert_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "alert_id": row["alert_id"],
            "fingerprint": row["fingerprint"],
            "severity": row["severity"],
            "category": row["category"],
            "message": row["message"],
            "details": json.loads(row["details_json"]),
            "status": row["status"],
            "occurrences": row["occurrences"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "acknowledged_at": row["acknowledged_at"],
        }

    def list_broker_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        """Past submitted orders, most recent first, with the originating
        proposal's intent (ticker/side/shares) attached when available."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT bo.order_id, bo.proposal_id, bo.submitted_at, bo.status, bo.payload_json,
                       tp.payload_json AS proposal_payload_json
                FROM broker_orders bo
                LEFT JOIN trade_proposals tp ON tp.proposal_id = bo.proposal_id
                ORDER BY bo.submitted_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        orders = []
        for row in rows:
            order = json.loads(row["payload_json"])
            order["proposal_id"] = row["proposal_id"]
            order["submitted_at"] = row["submitted_at"]
            order["order_status"] = row["status"]
            order["intent"] = None
            if row["proposal_payload_json"]:
                proposal = json.loads(row["proposal_payload_json"])
                order["intent"] = proposal.get("intent")
                order["evidence_status"] = proposal.get("evidence_status")
            orders.append(order)
        return orders

    def list_fills(self) -> list[dict[str, Any]]:
        """
        Every executed fill this app knows about, oldest first, as
        `{ticker, side, qty, price, at, fill_id, order_id, proposal_id}`.

        Reads out of the append-only `broker_order_events` journal rather than a
        separate lots table, so the tax-lot ledger has no second source of truth
        to drift from and can always be rebuilt by replay
        (`assistant.tax_lots.build_ledger`).

        Two event shapes have to be reconciled. The trade-update STREAM delivers
        incremental fills (`fill_qty`/`fill_price` -- one event per execution),
        while POLL reconciliation only ever sees the broker's cumulative
        `filled_qty`/`filled_avg_price`. Incremental values are preferred when
        present. For an order seen only through polling, one fill is emitted at
        the final cumulative quantity and average price: exactly right for a
        single-fill order, and for an order filled in several pieces it collapses
        them into one lot at the average -- which is what brokers report as the
        lot anyway, so no basis information is lost.

        IMPORTANT: covers only fills this app placed and journaled. Positions
        bought before the app existed, or through the Alpaca UI, produce no
        events and therefore no lots. Callers must not present a ledger built
        from these fills as a complete account history -- compare
        `shares_held()` against the broker's reported position to detect the gap.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.event_id, e.order_id, e.proposal_id, e.event_at,
                       e.fill_qty, e.fill_price, e.filled_qty, e.filled_avg_price,
                       tp.payload_json AS proposal_payload_json
                FROM broker_order_events e
                LEFT JOIN trade_proposals tp ON tp.proposal_id = e.proposal_id
                ORDER BY e.event_at ASC, e.rowid ASC
                """
            ).fetchall()

        fills: list[dict[str, Any]] = []
        cumulative_only: dict[str, dict[str, Any]] = {}
        saw_incremental: set[str] = set()

        for row in rows:
            intent = {}
            if row["proposal_payload_json"]:
                intent = json.loads(row["proposal_payload_json"]).get("intent") or {}
            ticker, side = intent.get("ticker"), intent.get("side")
            if not ticker or side not in ("buy", "sell"):
                continue  # cannot attribute a fill without a ticker and side

            qty, price = row["fill_qty"], row["fill_price"]
            if qty and price:
                saw_incremental.add(row["order_id"])
                fills.append({
                    "ticker": ticker, "side": side, "qty": float(qty), "price": float(price),
                    "at": row["event_at"], "fill_id": row["event_id"],
                    "order_id": row["order_id"], "proposal_id": row["proposal_id"],
                })
                continue

            if row["filled_qty"] and row["filled_avg_price"]:
                # Keep the LAST cumulative snapshot per order; only used if no
                # incremental events ever arrived for that order.
                cumulative_only[row["order_id"]] = {
                    "ticker": ticker, "side": side,
                    "qty": float(row["filled_qty"]), "price": float(row["filled_avg_price"]),
                    "at": row["event_at"], "fill_id": f"{row['order_id']}-cumulative",
                    "order_id": row["order_id"], "proposal_id": row["proposal_id"],
                }

        for order_id, fill in cumulative_only.items():
            if order_id not in saw_incremental:
                fills.append(fill)

        fills.sort(key=lambda f: (f["at"], f["fill_id"]))
        return fills

    def create_allocation_batch(
        self, batch_id: str, proposal_ids: list[str], intended_total_notional: float,
    ) -> dict[str, Any]:
        """
        Persists a NEW batch record for a Watchlist allocation split's
        "execute all proposals in this split" action -- GPT review,
        2026-07-28: submitting N proposals sequentially with no
        persisted record of the batch made a UI refresh or process
        restart lose track of which legs had already been attempted,
        risking a double-submission on blind retry. `legs` tracks each
        proposal's own state (unattempted/submitted/failed/unknown/
        blocked_overridable) so execute_allocation_batch() can resume
        idempotently from exactly where it left off.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "batch_id": batch_id,
            "created_at": now,
            "approved_at": None,
            "intended_total_notional": intended_total_notional,
            "proposal_ids": list(proposal_ids),
            "legs": {pid: {"state": "unattempted", "order": None, "error": None} for pid in proposal_ids},
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO allocation_batches(batch_id, created_at, status, payload_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, now, "created", json.dumps(payload, sort_keys=True), now),
            )
        payload["status"] = "created"
        return payload

    def get_allocation_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM allocation_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        if row is None:
            return None
        batch = json.loads(row["payload_json"])
        batch["status"] = row["status"]
        return batch

    def update_allocation_batch(self, batch_id: str, status: str | None = None, **updates: Any) -> dict[str, Any]:
        batch = self.get_allocation_batch(batch_id)
        if batch is None:
            raise KeyError(f"Unknown batch_id: {batch_id}")
        batch.update(updates)
        if status is not None:
            batch["status"] = status
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE allocation_batches SET status = ?, payload_json = ?, updated_at = ? WHERE batch_id = ?",
                (batch["status"], json.dumps(batch, sort_keys=True), now, batch_id),
            )
        return batch

    def recent_executed_intents(
        self,
        limit: int = 100,
        max_age_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Intents from recently-executed proposals, PLUS every intent
        whose broker submission outcome is still unresolved (status in
        UNRESOLVED_BROKER_STATE_STATUSES) regardless of age. A submission
        that hit an ambiguous error might still have reached the broker --
        until that's reconciled, the duplicate-order check must keep
        treating it as if the order exists, or a regenerated proposal for
        the same ticker/side could submit a second real order."""
        proposals = self.list_proposals(status=FILLED, limit=limit)
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_minutes * 60
        intents = [
            p["intent"]
            for p in proposals
            if "intent" in p
            and p.get("executed_at")
            and datetime.fromisoformat(p["executed_at"]).timestamp() >= cutoff
        ]
        for status in UNRESOLVED_BROKER_STATE_STATUSES:
            intents.extend(
                p["intent"] for p in self.list_proposals(status=status, limit=limit) if "intent" in p
            )
        return intents

    def record_strategy_evaluation(self, strategy_key: str, evaluated_at: str, result: dict[str, Any]) -> None:
        """Persists "this strategy was checked at this time, with this
        outcome" -- pure bookkeeping, no enforcement (docs/
        ALLOCATION_SERVICE_DESIGN.md, 2026-07-28). Closes a gap
        assistant/strategy_proposals.py's generate_soxx_soxl_rebalance_
        proposals() already documented: its backtest assumed a fixed
        ~21-trading-day check counter, but the live version had no
        equivalent memory of when it was last evaluated. Overwrites the
        previous row for the same strategy_key -- only the most recent
        evaluation is kept, this is not an audit log."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO strategy_evaluations(strategy_key, last_evaluated_at, last_result_json) "
                "VALUES (?, ?, ?) ON CONFLICT(strategy_key) DO UPDATE SET "
                "last_evaluated_at = excluded.last_evaluated_at, last_result_json = excluded.last_result_json",
                (strategy_key, evaluated_at, json.dumps(result, sort_keys=True)),
            )

    def get_last_strategy_evaluation(self, strategy_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT last_evaluated_at, last_result_json FROM strategy_evaluations WHERE strategy_key = ?",
                (strategy_key,),
            ).fetchone()
        if row is None:
            return None
        return {
            "strategy_key": strategy_key,
            "last_evaluated_at": row["last_evaluated_at"],
            "last_result": json.loads(row["last_result_json"]),
        }

    def record_ai_run(
        self,
        function_name: str,
        model: str,
        prompt_version: str,
        input_hash: str,
        latency_ms: float,
        success: bool,
        response: Any = None,
        error: str | None = None,
        called_at: str | None = None,
    ) -> None:
        """Append-only audit log for every LLM call this project makes
        (independent review: AI runs were not persisted anywhere -- no
        model, prompt version, input hash, latency, or response was
        recorded, making the AI layer unauditable after the fact). Every
        row is a genuinely new call, never an update -- unlike
        record_strategy_evaluation(), this IS meant to accumulate as a log,
        not just track "most recent". `input_hash` is a hash of the
        prompt's actual inputs (never the API key or any secret), so two
        identical calls are visibly identical without storing raw PII/
        portfolio data twice if the caller chooses to hash rather than
        store the full input."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ai_runs(called_at, function_name, model, prompt_version, input_hash, "
                "latency_ms, success, response_json, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    called_at or datetime.now(timezone.utc).isoformat(),
                    function_name,
                    model,
                    prompt_version,
                    input_hash,
                    latency_ms,
                    1 if success else 0,
                    json.dumps(response, sort_keys=True, default=str) if response is not None else None,
                    error,
                ),
            )

    def list_ai_runs(self, function_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if function_name is not None:
                rows = connection.execute(
                    "SELECT * FROM ai_runs WHERE function_name = ? ORDER BY id DESC LIMIT ?",
                    (function_name, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM ai_runs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [
            {
                "id": row["id"],
                "called_at": row["called_at"],
                "function_name": row["function_name"],
                "model": row["model"],
                "prompt_version": row["prompt_version"],
                "input_hash": row["input_hash"],
                "latency_ms": row["latency_ms"],
                "success": bool(row["success"]),
                "response": json.loads(row["response_json"]) if row["response_json"] is not None else None,
                "error": row["error"],
            }
            for row in rows
        ]
