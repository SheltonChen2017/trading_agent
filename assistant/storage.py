"""
Small SQLite state store for the personal assistant.

SQLite is deliberately used before introducing an external service: it
provides transactions, uniqueness constraints, and an auditable history
without creating deployment or credential overhead for one user.
"""
from __future__ import annotations

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
                    payload_json TEXT NOT NULL
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
                CREATE INDEX IF NOT EXISTS idx_proposals_status
                    ON trade_proposals(status, created_at);
                """
            )
            # Deduplicate any pre-existing rows sharing a generated_at
            # (from before this fix -- e.g. the UI re-saving the same
            # st.cache_data-cached packet from a second browser tab or a
            # page reload, which had no server-side identity/uniqueness
            # to catch it) BEFORE creating the unique index below --
            # CREATE UNIQUE INDEX fails outright on a table that already
            # contains duplicates (GPT review, 2026-07-31). No-op (0 rows
            # affected) once already deduplicated, so safe to run on
            # every AssistantStore() construction.
            connection.execute(
                """
                DELETE FROM decision_packets
                WHERE id NOT IN (SELECT MIN(id) FROM decision_packets GROUP BY generated_at)
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_packets_generated_at "
                "ON decision_packets(generated_at)"
            )

    def save_decision_packet(self, packet: DecisionPacket) -> int:
        """Persists one decision packet, keyed by `generated_at` -- an
        ISO timestamp set exactly once per real build_decision_packet()
        call, so two saves sharing it really are the same underlying
        packet. Idempotent: saving the same packet.generated_at twice is
        a safe no-op that returns the ORIGINAL row's id, never a new
        duplicate row (GPT review, 2026-07-31: this used to insert an
        unconditional new row every call -- since the UI layer now caches
        packets via st.cache_data, a page reload, a new browser tab, or a
        second session had no server-side way to recognize "this is the
        same cached packet I already saved" and would insert it again;
        deduplication needed to live in storage, not only in UI session
        state, which starts fresh for every new session)."""
        payload = json.dumps(packet.to_dict(), sort_keys=True)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO decision_packets(generated_at, schema_version, payload_json) VALUES (?, ?, ?) "
                "ON CONFLICT(generated_at) DO NOTHING",
                (packet.generated_at, packet.schema_version, payload),
            )
            if cursor.rowcount == 1:
                return int(cursor.lastrowid)
            existing = connection.execute(
                "SELECT id FROM decision_packets WHERE generated_at = ?", (packet.generated_at,)
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
