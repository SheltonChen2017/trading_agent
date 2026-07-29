"""
Small SQLite state store for the personal assistant.

SQLite is deliberately used before introducing an external service: it
provides transactions, uniqueness constraints, and an auditable history
without creating deployment or credential overhead for one user.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from assistant.proposal_status import EXECUTED, UNRESOLVED_BROKER_STATE_STATUSES
from assistant.schemas import DecisionPacket

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trading_assistant.db"


def _hash_payload(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def configured_db_path() -> Path:
    return Path(os.environ.get("TRADING_ASSISTANT_DB", DEFAULT_DB_PATH))


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
                CREATE INDEX IF NOT EXISTS idx_proposals_status
                    ON trade_proposals(status, created_at);
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

    def claim_proposal(
        self,
        proposal_id: str,
        *,
        expected_status: str | tuple[str, ...] = "proposed",
        new_status: str = "validating",
        not_expired_after: str | None = None,
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
        (with its embedded "status" updated to `new_status`) on success,
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
        """
        expected_statuses = (expected_status,) if isinstance(expected_status, str) else tuple(expected_status)
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in expected_statuses)
        query = f"UPDATE trade_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status IN ({placeholders})"
        params: list[Any] = [new_status, now, proposal_id, *expected_statuses]
        if not_expired_after is not None:
            query += " AND expires_at >= ?"
            params.append(not_expired_after)
        with self._connect() as connection:
            cursor = connection.execute(query, params)
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT payload_json FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        proposal = json.loads(row["payload_json"])
        proposal["status"] = new_status
        return proposal

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

    def record_broker_order(self, proposal_id: str, order: dict[str, Any]) -> None:
        submitted_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO broker_orders(
                    order_id, proposal_id, submitted_at, status, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(order["order_id"]),
                    proposal_id,
                    submitted_at,
                    str(order.get("status", "unknown")),
                    json.dumps(order, sort_keys=True),
                ),
            )

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
        proposals = self.list_proposals(status=EXECUTED, limit=limit)
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
