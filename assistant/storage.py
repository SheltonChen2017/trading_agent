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
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from assistant.proposal_status import (
    DISMISSED,
    DISMISSIBLE_SOURCE_STATUSES,
    EXPIRED,
    FILLED,
    STATUSES,
    UNRESOLVED_BROKER_STATE_STATUSES,
)
from assistant.money import decimal_text, to_decimal
from assistant.schemas import DecisionPacket

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trading_assistant.db"
# Trading days in this project are Eastern-market days (see
# get_execution_budget_usage), not UTC days.
_EASTERN = ZoneInfo("America/New_York")

# ML-LR-6 plan 12.2's minimum lineage. Every one of these can change WITHOUT
# any code change -- a re-fit model, a new report, a swapped provider, an
# edited config -- and each silently invalidates comparison against earlier
# predictions. Requiring them by name is what forces a new epoch rather than
# letting two systems accumulate one indistinguishable track record.
_REQUIRED_LINEAGE_KEYS = frozenset(
    {
        "model_artifact_hash",
        "evaluation_report_hash",
        "feature_set_version",
        "label_version",
        "data_provider_id",
        "configuration_hash",
        "code_commit",
        "schedule_version",
    }
)
_LINEAGE_SHA256_KEYS = frozenset(
    {"model_artifact_hash", "evaluation_report_hash", "configuration_hash"}
)
_COMMIT_HASH = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_EXECUTION_VALUE_KEYS = frozenset(
    {
        "side", "shares", "quantity", "order_type", "limit_price",
        "stop_price", "approved", "execute", "authorization",
        "target_weight", "trade_intent", "recommendation", "action",
    }
)


def _hash_payload(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _canonical_ml_json(payload: Any, name: str) -> str:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite JSON-compatible data") from exc


def _parse_aware_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _parse_session_date(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use canonical YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must use canonical YYYY-MM-DD format")
    return parsed


def _require_sha256(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a lowercase 64-character sha256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a lowercase 64-character sha256 digest") from exc
    if value != value.lower():
        raise ValueError(f"{name} must be a lowercase 64-character sha256 digest")


def _validate_ml_lineage(lineage: Any) -> str:
    """Validate and canonically serialize one evidence-epoch lineage."""
    if not isinstance(lineage, dict) or not lineage:
        raise ValueError("lineage must be a non-empty dictionary")
    missing = sorted(_REQUIRED_LINEAGE_KEYS - set(lineage))
    if missing:
        raise ValueError(f"lineage is missing required key(s): {missing}")
    for name in _REQUIRED_LINEAGE_KEYS:
        value = lineage[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"lineage.{name} must be a non-empty string")
        if value != value.strip():
            raise ValueError(f"lineage.{name} must not contain surrounding whitespace")
    for name in _LINEAGE_SHA256_KEYS:
        _require_sha256(lineage[name], f"lineage.{name}")
    if _COMMIT_HASH.fullmatch(lineage["code_commit"]) is None:
        raise ValueError("lineage.code_commit must be a lowercase 40- or 64-character git hash")
    return _canonical_ml_json(lineage, "lineage")


def _reject_execution_shaped_values(value: Any, *, path: str = "prediction.values") -> None:
    """Recursively keep generic observation payloads free of trade fields."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(key)).strip("_").lower()
            tokens = {token for token in normalized.split("_") if token}
            if normalized in _EXECUTION_VALUE_KEYS or tokens & _EXECUTION_VALUE_KEYS:
                raise ValueError(f"{path}.{key} is an execution-shaped field")
            _reject_execution_shaped_values(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_execution_shaped_values(item, path=f"{path}[{index}]")


def configured_db_path() -> Path:
    return Path(os.environ.get("TRADING_ASSISTANT_DB", DEFAULT_DB_PATH))


# UI-2d: payload keys that only validation/approval/override/submission/
# broker/reconciliation code paths ever write into a proposal payload. A
# pristine generated proposal (see assistant/proposals.py TradeProposal)
# carries none of them. Their PRESENCE is execution-shaped evidence, so a
# proposal whose status was somehow corrupted back to "proposed" still
# refuses dismissal. Extending this tuple is a reviewed change.
_DISMISSAL_EXECUTION_EVIDENCE_KEYS: tuple[str, ...] = (
    "approved_at",
    "broker_order",
    "broker_order_update",
    "broker_status",
    "cancel_requested_at",
    "error",
    "executed_at",
    "filled_at",
    "policy_override",
    "reconciled_at",
    "submitted_at",
    "violations",
)


@dataclass(frozen=True)
class DismissalPreviewRow:
    """One proposal's dismissibility verdict with its exact refusal
    reasons. `status`/`updated_at` participate in the preview hash so any
    concurrent state change invalidates a confirmation built on this row."""

    proposal_id: str
    ticker: str
    side: str
    shares: Any
    status: str
    created_at: str
    expires_at: str
    updated_at: str
    dismissible: bool
    refusal_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DismissalPreview:
    rows: tuple[DismissalPreviewRow, ...]
    dismissible_ids: tuple[str, ...]
    preview_hash: str


@dataclass(frozen=True)
class DismissalResult:
    """dismissed_ids: rows transitioned by THIS call. already_dismissed_ids:
    rows that were dismissed before the call (idempotent replay -- their
    original metadata is never rewritten). dismissed_at is None when the
    call wrote nothing."""

    dismissed_ids: tuple[str, ...]
    already_dismissed_ids: tuple[str, ...]
    dismissed_at: str | None


def _preview_row_from_record(record: dict[str, Any]) -> DismissalPreviewRow:
    intent = record["payload"].get("intent") or {}
    return DismissalPreviewRow(
        proposal_id=record["proposal_id"],
        ticker=str(intent.get("ticker", "?")),
        side=str(intent.get("side", "?")),
        shares=intent.get("shares", "?"),
        status=record["status"],
        created_at=record["created_at"],
        expires_at=record["expires_at"],
        updated_at=record["updated_at"],
        dismissible=record["dismissible"],
        refusal_reasons=record["refusal_reasons"],
    )


def _preview_from_records(records: list[dict[str, Any]]) -> DismissalPreview:
    rows = tuple(_preview_row_from_record(record) for record in records)
    canonical = json.dumps(
        [
            {
                "proposal_id": row.proposal_id,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "updated_at": row.updated_at,
                # Bind the confirmation to the complete durable proposal
                # identity, not only the eligibility verdict. A future writer
                # or manual repair that changes the payload/idempotency key
                # without maintaining updated_at must still invalidate the
                # operator's preview.
                "idempotency_key": record["idempotency_key"],
                "payload_json": record["payload_json"],
                "dismissible": row.dismissible,
                "refusal_reasons": list(row.refusal_reasons),
            }
            for row, record in zip(rows, records, strict=True)
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return DismissalPreview(
        rows=rows,
        dismissible_ids=tuple(row.proposal_id for row in rows if row.dismissible),
        preview_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _allocation_batch_references(
    connection: sqlite3.Connection,
) -> tuple[dict[str, set[str]], tuple[str, ...]]:
    """Map proposal_id -> batch_ids referencing it, scanning payload JSON
    (there is no foreign key from allocation_batches to trade_proposals).
    A batch payload that cannot be parsed fails CLOSED: the error string is
    attached to every candidate, because an unreadable batch might
    reference any of them and 'unused' can no longer be proven."""
    referenced: dict[str, set[str]] = {}
    errors: list[str] = []
    for row in connection.execute(
        "SELECT batch_id, payload_json FROM allocation_batches"
    ).fetchall():
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise TypeError("allocation batch payload is not an object")
            proposal_ids = payload.get("proposal_ids") or []
            legs = payload.get("legs") or {}
            if (
                not isinstance(proposal_ids, list)
                or any(
                    not isinstance(proposal_id, str) or not proposal_id
                    for proposal_id in proposal_ids
                )
                or not isinstance(legs, dict)
                or any(
                    not isinstance(proposal_id, str) or not proposal_id
                    for proposal_id in legs
                )
            ):
                raise TypeError("allocation batch reference fields are malformed")
            leg_ids = list(legs)
        except (ValueError, TypeError, AttributeError):
            errors.append(
                f"allocation batch {row['batch_id']} payload is unreadable; "
                "cannot prove the proposal is unused"
            )
            continue
        for proposal_id in list(proposal_ids) + leg_ids:
            referenced.setdefault(str(proposal_id), set()).add(row["batch_id"])
    return referenced, tuple(errors)


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

    @staticmethod
    def _open_database(path: str | Path) -> sqlite3.Connection:
        """Open a consistently configured connection for every code path."""
        connection = sqlite3.connect(Path(path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _connect(self):
        connection = self._open_database(self.path)
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
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(proposal_id)
                        REFERENCES trade_proposals(proposal_id)
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
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(order_id)
                        REFERENCES broker_orders(order_id),
                    FOREIGN KEY(proposal_id)
                        REFERENCES trade_proposals(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS execution_telemetry_events (
                    telemetry_event_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    order_id TEXT,
                    event_type TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    account_mode TEXT NOT NULL,
                    broker_account_id TEXT,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(proposal_id)
                        REFERENCES trade_proposals(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS execution_reservations (
                    proposal_id TEXT PRIMARY KEY,
                    trading_day TEXT NOT NULL,
                    reserved_notional REAL NOT NULL,
                    reserved_notional_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(proposal_id)
                        REFERENCES trade_proposals(proposal_id)
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
                -- GR-5: one row per delivery ATTEMPT, never overwritten.
                -- A failed attempt is evidence too: "critical alert raised
                -- but never delivered" must be detectable, which is
                -- impossible if failures overwrite or are dropped.
                CREATE TABLE IF NOT EXISTS alert_deliveries (
                    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    alert_id INTEGER,
                    channel TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    delivered_at TEXT,
                    occurrences_at_attempt INTEGER NOT NULL,
                    detail TEXT NOT NULL,
                    FOREIGN KEY(alert_id)
                        REFERENCES operational_alerts(alert_id)
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
                    total_equity_text TEXT NOT NULL,
                    cash_text TEXT NOT NULL,
                    benchmark_close_text TEXT NOT NULL,
                    net_external_flow_text TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(evidence_epoch)
                        REFERENCES paper_evidence_epochs(evidence_epoch),
                    UNIQUE(evidence_epoch, session_date)
                );
                CREATE TABLE IF NOT EXISTS portfolio_equity_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    account_key TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    total_equity_text TEXT NOT NULL,
                    cash_text TEXT NOT NULL,
                    net_external_flow_text TEXT NOT NULL,
                    benchmarks_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS portfolio_position_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    account_key TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    shares_text TEXT NOT NULL,
                    market_value_text TEXT NOT NULL,
                    price_text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS portfolio_capture_sessions (
                    capture_id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL UNIQUE,
                    evidence_epoch TEXT NOT NULL,
                    lineage_hash TEXT NOT NULL,
                    account_key TEXT NOT NULL,
                    account_mode TEXT NOT NULL,
                    broker_account_id TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    equity_snapshot_id TEXT NOT NULL,
                    position_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(observation_id)
                        REFERENCES paper_account_observations(observation_id),
                    FOREIGN KEY(evidence_epoch)
                        REFERENCES paper_evidence_epochs(evidence_epoch),
                    FOREIGN KEY(equity_snapshot_id)
                        REFERENCES portfolio_equity_snapshots(snapshot_id)
                );
                CREATE TABLE IF NOT EXISTS ml_model_registrations (
                    model_key TEXT PRIMARY KEY,
                    registered_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ml_predictions (
                    prediction_id TEXT PRIMARY KEY,
                    model_key TEXT NOT NULL,
                    task TEXT NOT NULL,
                    subject_key TEXT NOT NULL,
                    as_of_session TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    horizon_sessions INTEGER NOT NULL,
                    target_available_at TEXT NOT NULL,
                    feature_snapshot_hash TEXT NOT NULL,
                    prediction_json TEXT NOT NULL,
                    prediction_hash TEXT NOT NULL,
                    available INTEGER NOT NULL,
                    refusal_reasons_json TEXT NOT NULL,
                    FOREIGN KEY(model_key)
                        REFERENCES ml_model_registrations(model_key)
                );
                CREATE TABLE IF NOT EXISTS ml_evidence_epochs (
                    evidence_epoch TEXT PRIMARY KEY,
                    model_key TEXT NOT NULL,
                    task TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    closed_at TEXT,
                    status TEXT NOT NULL,
                    lineage_json TEXT NOT NULL,
                    lineage_hash TEXT NOT NULL,
                    created_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ml_shadow_runs (
                    run_id TEXT PRIMARY KEY,
                    schedule_key TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    code_commit TEXT NOT NULL,
                    configuration_hash TEXT NOT NULL,
                    evidence_epoch TEXT NOT NULL,
                    prediction_count INTEGER NOT NULL,
                    unavailable_count INTEGER NOT NULL,
                    error_json TEXT
                );
                CREATE TABLE IF NOT EXISTS ml_prediction_outcomes (
                    prediction_id TEXT PRIMARY KEY,
                    matured_at TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    outcome_hash TEXT NOT NULL,
                    FOREIGN KEY(prediction_id)
                        REFERENCES ml_predictions(prediction_id)
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
                CREATE INDEX IF NOT EXISTS idx_execution_telemetry_attempt_at
                    ON execution_telemetry_events(attempt_id, event_at);
                CREATE INDEX IF NOT EXISTS idx_execution_telemetry_proposal_at
                    ON execution_telemetry_events(proposal_id, event_at);
                CREATE INDEX IF NOT EXISTS idx_execution_telemetry_order_at
                    ON execution_telemetry_events(order_id, event_at);
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
                CREATE INDEX IF NOT EXISTS idx_alert_deliveries_fingerprint
                    ON alert_deliveries(fingerprint, attempted_at);
                CREATE INDEX IF NOT EXISTS idx_alert_deliveries_outcome
                    ON alert_deliveries(outcome, attempted_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_paper_epoch
                    ON paper_evidence_epochs(status) WHERE status = 'active';
                CREATE INDEX IF NOT EXISTS idx_paper_observations_epoch_date
                    ON paper_account_observations(evidence_epoch, session_date);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_position_snapshot_unique
                    ON portfolio_position_snapshots(
                        account_key, session_date, ticker, captured_at
                    );
                CREATE INDEX IF NOT EXISTS idx_position_snapshot_account_date
                    ON portfolio_position_snapshots(account_key, session_date);
                CREATE INDEX IF NOT EXISTS idx_portfolio_capture_account_date
                    ON portfolio_capture_sessions(account_key, session_date);
                CREATE INDEX IF NOT EXISTS idx_portfolio_capture_epoch_date
                    ON portfolio_capture_sessions(evidence_epoch, session_date);
                -- At most ONE active epoch per (model_key, task). A second
                -- active epoch would let predictions from two different
                -- systems accumulate under one banner, which is exactly the
                -- pooling doc 10.2 forbids.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_epoch_one_active
                    ON ml_evidence_epochs(model_key, task)
                    WHERE status = 'active';
                -- An exact retry of a scheduled run is idempotent; two
                -- concurrent runners cannot both create evidence for the
                -- same slot.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_shadow_run_slot
                    ON ml_shadow_runs(schedule_key, scheduled_for);
                CREATE INDEX IF NOT EXISTS idx_ml_shadow_runs_epoch
                    ON ml_shadow_runs(evidence_epoch, scheduled_for);
                CREATE INDEX IF NOT EXISTS idx_ml_predictions_model_session
                    ON ml_predictions(model_key, as_of_session);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_predictions_identity
                    ON ml_predictions(
                        model_key, task, subject_key, as_of_session, horizon_sessions
                    );
                CREATE INDEX IF NOT EXISTS idx_portfolio_equity_account_date
                    ON portfolio_equity_snapshots(
                        account_key, session_date, captured_at
                    );
                CREATE INDEX IF NOT EXISTS idx_operational_drills_type_at
                    ON operational_drill_runs(drill_type, performed_at);
                CREATE TRIGGER IF NOT EXISTS fk_broker_orders_proposal_insert
                BEFORE INSERT ON broker_orders
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker order proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_orders_proposal_update
                BEFORE UPDATE OF proposal_id ON broker_orders
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker order proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_events_order_insert
                BEFORE INSERT ON broker_order_events
                WHEN NOT EXISTS (
                    SELECT 1 FROM broker_orders
                    WHERE order_id = NEW.order_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker event order does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_events_order_update
                BEFORE UPDATE OF order_id ON broker_order_events
                WHEN NOT EXISTS (
                    SELECT 1 FROM broker_orders
                    WHERE order_id = NEW.order_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker event order does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_events_proposal_insert
                BEFORE INSERT ON broker_order_events
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker event proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_events_proposal_update
                BEFORE UPDATE OF proposal_id ON broker_order_events
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker event proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_execution_reservation_proposal_insert
                BEFORE INSERT ON execution_reservations
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'execution reservation proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_execution_reservation_proposal_update
                BEFORE UPDATE OF proposal_id ON execution_reservations
                WHEN NOT EXISTS (
                    SELECT 1 FROM trade_proposals
                    WHERE proposal_id = NEW.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'execution reservation proposal does not exist');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_trade_proposals_children_delete
                BEFORE DELETE ON trade_proposals
                WHEN EXISTS (
                    SELECT 1 FROM broker_orders
                    WHERE proposal_id = OLD.proposal_id
                ) OR EXISTS (
                    SELECT 1 FROM broker_order_events
                    WHERE proposal_id = OLD.proposal_id
                ) OR EXISTS (
                    SELECT 1 FROM execution_reservations
                    WHERE proposal_id = OLD.proposal_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'trade proposal still has child rows');
                END;
                CREATE TRIGGER IF NOT EXISTS fk_broker_orders_events_delete
                BEFORE DELETE ON broker_orders
                WHEN EXISTS (
                    SELECT 1 FROM broker_order_events
                    WHERE order_id = OLD.order_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'broker order still has event rows');
                END;
                """
            )
            self._migrate_decision_packet_identity(connection)
            self._migrate_execution_reservation_money(connection)
            self._migrate_paper_observation_money(connection)
            self._migrate_ml_prediction_maturity(connection)

    def _migrate_ml_prediction_maturity(self, connection: sqlite3.Connection) -> None:
        """Add immutable target availability to databases created by ML-6's
        first draft. Legacy predictions remain readable but cannot receive an
        outcome: their true maturity was never recorded, so guessing it from
        a session count would fail closed on holidays and non-close targets."""
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ml_predictions)")
        }
        if "target_available_at" not in columns:
            connection.execute(
                "ALTER TABLE ml_predictions ADD COLUMN target_available_at TEXT"
            )
        # ML-LR-6 (plan 12.2): nullable so databases written before the
        # shadow runtime existed still load. Legacy rows keep NULL and are
        # therefore visibly outside every epoch -- which is correct, since
        # their lineage was never recorded and cannot be reconstructed.
        # Scheduled predictions written from now on require both, enforced
        # in record_ml_prediction() rather than by a NOT NULL constraint
        # that would break the existing rows.
        for column in ("evidence_epoch", "shadow_run_id"):
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE ml_predictions ADD COLUMN {column} TEXT"
                )

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

    def _migrate_execution_reservation_money(
        self, connection: sqlite3.Connection
    ) -> None:
        """Add an exact decimal representation beside the legacy REAL.

        SQLite's REAL affinity stores binary floating-point values, so
        summing reservations such as 0.1 and 0.2 can produce a value just
        above an exact 0.3 cap.  The REAL column remains populated for
        backward compatibility and ad-hoc reporting; all enforcement reads
        ``reserved_notional_text`` and sums ``Decimal`` values in Python.
        Existing databases are backfilled from the best representation still
        available in the legacy column.  Precision already lost by an old
        write cannot be recovered, but no subsequent arithmetic adds more
        drift.
        """
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(execution_reservations)"
            )
        }
        if "reserved_notional_text" not in columns:
            connection.execute(
                "ALTER TABLE execution_reservations "
                "ADD COLUMN reserved_notional_text TEXT"
            )
        rows = connection.execute(
            "SELECT proposal_id, reserved_notional "
            "FROM execution_reservations "
            "WHERE reserved_notional_text IS NULL "
            "OR reserved_notional_text = ''"
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE execution_reservations "
                "SET reserved_notional_text = ? WHERE proposal_id = ?",
                (
                    decimal_text(row["reserved_notional"]),
                    row["proposal_id"],
                ),
            )

    def _migrate_paper_observation_money(
        self, connection: sqlite3.Connection
    ) -> None:
        """Keep exact observation decimals beside legacy REAL projections.

        SQLite applies REAL affinity even when decimal text is bound to the
        legacy convenience columns. Exact text columns make direct evidence
        queries lossless too. Existing rows are backfilled from payload_json;
        old JSON floats fall back to their best surviving representation.
        """
        fields = (
            "total_equity",
            "cash",
            "benchmark_close",
            "net_external_flow",
        )
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(paper_account_observations)"
            )
        }
        for field in fields:
            column = f"{field}_text"
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE paper_account_observations ADD COLUMN {column} TEXT"
                )
        rows = connection.execute(
            "SELECT observation_id, payload_json, total_equity, cash, "
            "benchmark_close, net_external_flow, total_equity_text, cash_text, "
            "benchmark_close_text, net_external_flow_text "
            "FROM paper_account_observations"
        ).fetchall()
        for row in rows:
            if all(row[f"{field}_text"] not in (None, "") for field in fields):
                continue
            payload = json.loads(row["payload_json"])
            exact = {
                field: decimal_text(
                    to_decimal(payload.get(field, row[field]), name=field)
                )
                for field in fields
            }
            connection.execute(
                "UPDATE paper_account_observations SET "
                "total_equity_text = ?, cash_text = ?, benchmark_close_text = ?, "
                "net_external_flow_text = ? WHERE observation_id = ?",
                (
                    exact["total_equity"],
                    exact["cash"],
                    exact["benchmark_close"],
                    exact["net_external_flow"],
                    row["observation_id"],
                ),
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

    def append_portfolio_equity_snapshot(
        self, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        """Append one immutable briefing valuation, deduplicated by payload."""
        payload_json = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), default=str
        )
        payload_hash = _hash_payload(payload_json)
        snapshot_id = "equity-" + payload_hash[:24]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_equity_snapshots(
                    snapshot_id, account_key, session_date, captured_at,
                    total_equity_text, cash_text, net_external_flow_text,
                    benchmarks_json, payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO NOTHING
                """,
                (
                    snapshot_id,
                    snapshot["account_key"],
                    snapshot["session_date"],
                    snapshot["captured_at"],
                    snapshot["total_equity"],
                    snapshot["cash"],
                    snapshot["net_external_flow"],
                    json.dumps(
                        snapshot.get("benchmarks", {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    payload_json,
                    payload_hash,
                ),
            )
        return {
            **snapshot,
            "snapshot_id": snapshot_id,
            "payload_hash": payload_hash,
        }

    def list_portfolio_equity_snapshots(
        self,
        account_key: str,
        *,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_id, payload_json, payload_hash
                FROM (
                    SELECT rowid AS storage_rowid, snapshot_id, captured_at,
                           payload_json, payload_hash
                    FROM portfolio_equity_snapshots
                    WHERE account_key = ?
                    ORDER BY captured_at DESC, rowid DESC
                    LIMIT ?
                )
                ORDER BY captured_at ASC, storage_rowid ASC
                """,
                (account_key, limit),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.update(
                snapshot_id=row["snapshot_id"],
                payload_hash=row["payload_hash"],
            )
            result.append(payload)
        return result

    def append_portfolio_position_snapshots(
        self, snapshots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Append per-position holdings for one session (ML strategy doc 8.1).

        A faithful HISTORICAL portfolio-volatility target needs daily
        position/weight history, which portfolio_equity_snapshots (account
        totals only) cannot provide. Doc 8.1 explicitly directs adding a
        separate append-only table "rather than altering the versioned
        DecisionPacket schema" -- so this does not touch DecisionPacket.

        Money is stored as exact decimal TEXT, matching this table's
        *_text column convention and the rest of this module; float
        round-tripping would corrupt a reconstructed historical weight.
        Deduplicated by content hash, so re-capturing an identical session
        is a no-op rather than a duplicate row.
        """
        written: list[dict[str, Any]] = []
        with self._connect() as connection:
            for snapshot in snapshots:
                required = {
                    "account_key", "session_date", "captured_at", "ticker",
                    "shares", "market_value", "price",
                }
                missing = sorted(required - set(snapshot))
                if missing:
                    raise ValueError(f"position snapshot is missing fields: {missing}")
                for name in ("account_key", "ticker"):
                    value = snapshot[name]
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(f"position snapshot {name} must be non-empty")
                ticker = snapshot["ticker"].strip().upper()
                if ticker != snapshot["ticker"]:
                    raise ValueError("position snapshot ticker must be canonical uppercase")
                source = snapshot.get("source", "unknown")
                if not isinstance(source, str) or not source.strip():
                    raise ValueError("position snapshot source must be non-empty")
                session = _parse_session_date(snapshot["session_date"], "session_date")
                captured = _parse_aware_timestamp(snapshot["captured_at"], "captured_at")
                if captured.astimezone(_EASTERN).date() != session:
                    raise ValueError(
                        "captured_at must fall on session_date in America/New_York"
                    )
                shares = to_decimal(snapshot["shares"], name="shares")
                market_value = to_decimal(
                    snapshot["market_value"], name="market_value"
                )
                price = to_decimal(snapshot["price"], name="price")
                if shares < 0 or market_value < 0 or price <= 0:
                    raise ValueError(
                        "position shares and market value must be non-negative and "
                        "price must be positive"
                    )
                canonical = {
                    "account_key": snapshot["account_key"].strip(),
                    "session_date": session.isoformat(),
                    "captured_at": captured.isoformat(),
                    "ticker": ticker,
                    "shares": decimal_text(shares),
                    "market_value": decimal_text(market_value),
                    "price": decimal_text(price),
                    "source": source.strip(),
                }
                payload_json = _canonical_ml_json(canonical, "position snapshot")
                snapshot_hash = _hash_payload(payload_json)
                snapshot_id = "position-" + snapshot_hash[:24]
                connection.execute(
                    """
                    INSERT INTO portfolio_position_snapshots(
                        snapshot_id, account_key, session_date, captured_at,
                        ticker, shares_text, market_value_text, price_text,
                        source, snapshot_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        snapshot_id,
                        canonical["account_key"],
                        canonical["session_date"],
                        canonical["captured_at"],
                        canonical["ticker"],
                        canonical["shares"],
                        canonical["market_value"],
                        canonical["price"],
                        canonical["source"],
                        snapshot_hash,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT snapshot_id, snapshot_hash
                    FROM portfolio_position_snapshots
                    WHERE account_key = ? AND session_date = ? AND ticker = ?
                      AND captured_at = ?
                    """,
                    (
                        canonical["account_key"], canonical["session_date"],
                        canonical["ticker"], canonical["captured_at"],
                    ),
                ).fetchone()
                if row is None or row["snapshot_hash"] != snapshot_hash:
                    raise ValueError(
                        "a different immutable position snapshot already exists "
                        "for this account/session/ticker/capture identity"
                    )
                written.append(
                    {
                        **canonical,
                        "snapshot_id": row["snapshot_id"],
                        "snapshot_hash": snapshot_hash,
                    }
                )
        return written

    def list_portfolio_position_snapshots(
        self, account_key: str, *, session_date: str | None = None, limit: int = 100_000
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM portfolio_position_snapshots WHERE account_key = ?"
        )
        params: list[Any] = [account_key]
        if session_date is not None:
            query += " AND session_date = ?"
            params.append(session_date)
        query += " ORDER BY session_date ASC, ticker ASC, captured_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            {
                "snapshot_id": row["snapshot_id"],
                "account_key": row["account_key"],
                "session_date": row["session_date"],
                "captured_at": row["captured_at"],
                "ticker": row["ticker"],
                "shares": row["shares_text"],
                "market_value": row["market_value_text"],
                "price": row["price_text"],
                "source": row["source"],
                "snapshot_hash": row["snapshot_hash"],
            }
            for row in rows
        ]

    def append_portfolio_capture_session(
        self, capture: dict[str, Any]
    ) -> dict[str, Any]:
        """Commit a manifest proving one normalized portfolio capture is complete.

        The paper observation, equity snapshot, and position snapshots are
        individually append-only. This manifest is deliberately written last:
        its presence means every referenced child exists and matches its hash;
        its absence means a crash or refusal left the normalization incomplete.
        A zero-position manifest is therefore distinguishable from a capture
        that failed before holdings were persisted.
        """
        required = {
            "capture_id",
            "observation_id",
            "observation_payload_hash",
            "evidence_epoch",
            "lineage_hash",
            "account_key",
            "account_mode",
            "broker_account_id",
            "session_date",
            "captured_at",
            "source",
            "equity_snapshot_id",
            "equity_payload_hash",
            "position_snapshot_ids",
            "position_snapshot_hashes",
            "position_count",
        }
        missing = sorted(required - set(capture))
        if missing:
            raise ValueError(f"portfolio capture is missing fields: {missing}")
        for name in (
            "capture_id",
            "observation_id",
            "evidence_epoch",
            "account_key",
            "account_mode",
            "broker_account_id",
            "source",
            "equity_snapshot_id",
        ):
            value = capture[name]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"portfolio capture {name} must be non-empty")
            if value != value.strip():
                raise ValueError(
                    f"portfolio capture {name} must not contain surrounding whitespace"
                )
        for name in (
            "observation_payload_hash",
            "lineage_hash",
            "equity_payload_hash",
        ):
            _require_sha256(capture[name], f"portfolio capture {name}")
        session = _parse_session_date(capture["session_date"], "session_date")
        captured = _parse_aware_timestamp(capture["captured_at"], "captured_at")
        if captured.astimezone(_EASTERN).date() != session:
            raise ValueError(
                "portfolio capture captured_at must fall on session_date in "
                "America/New_York"
            )
        position_count = capture["position_count"]
        if (
            isinstance(position_count, bool)
            or not isinstance(position_count, int)
            or position_count < 0
        ):
            raise ValueError("portfolio capture position_count must be >= 0")
        position_ids = capture["position_snapshot_ids"]
        position_hashes = capture["position_snapshot_hashes"]
        if not isinstance(position_ids, (list, tuple)) or not isinstance(
            position_hashes, (list, tuple)
        ):
            raise ValueError(
                "portfolio capture position snapshot identities must be sequences"
            )
        if len(position_ids) != position_count or len(position_hashes) != position_count:
            raise ValueError(
                "portfolio capture position_count must match its snapshot identities"
            )
        for index, snapshot_id in enumerate(position_ids):
            if not isinstance(snapshot_id, str) or not snapshot_id.strip():
                raise ValueError(
                    f"portfolio capture position_snapshot_ids[{index}] must be non-empty"
                )
        if len(set(position_ids)) != position_count:
            raise ValueError("portfolio capture position snapshot IDs must be unique")
        for index, snapshot_hash in enumerate(position_hashes):
            _require_sha256(
                snapshot_hash,
                f"portfolio capture position_snapshot_hashes[{index}]",
            )

        canonical = {
            "schema_version": str(capture.get("schema_version", "1.0")),
            "capture_id": capture["capture_id"],
            "observation_id": capture["observation_id"],
            "observation_payload_hash": capture["observation_payload_hash"],
            "evidence_epoch": capture["evidence_epoch"],
            "lineage_hash": capture["lineage_hash"],
            "account_key": capture["account_key"],
            "account_mode": capture["account_mode"],
            "broker_account_id": capture["broker_account_id"],
            "session_date": session.isoformat(),
            "captured_at": captured.isoformat(),
            "source": capture["source"],
            "equity_snapshot_id": capture["equity_snapshot_id"],
            "equity_payload_hash": capture["equity_payload_hash"],
            "position_snapshot_ids": list(position_ids),
            "position_snapshot_hashes": list(position_hashes),
            "position_count": position_count,
        }
        payload_json = _canonical_ml_json(canonical, "portfolio capture")
        payload_hash = _hash_payload(payload_json)
        connection = self._open_database(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            observation = connection.execute(
                "SELECT evidence_epoch, payload_hash FROM paper_account_observations "
                "WHERE observation_id = ?",
                (canonical["observation_id"],),
            ).fetchone()
            if observation is None:
                raise ValueError("portfolio capture paper observation does not exist")
            if (
                observation["evidence_epoch"] != canonical["evidence_epoch"]
                or observation["payload_hash"] != canonical["observation_payload_hash"]
            ):
                raise ValueError(
                    "portfolio capture paper observation identity or hash does not match"
                )
            epoch = connection.execute(
                "SELECT lineage_hash FROM paper_evidence_epochs WHERE evidence_epoch = ?",
                (canonical["evidence_epoch"],),
            ).fetchone()
            if epoch is None or epoch["lineage_hash"] != canonical["lineage_hash"]:
                raise ValueError("portfolio capture evidence lineage does not match")
            equity = connection.execute(
                "SELECT account_key, session_date, captured_at, payload_hash "
                "FROM portfolio_equity_snapshots WHERE snapshot_id = ?",
                (canonical["equity_snapshot_id"],),
            ).fetchone()
            if equity is None or any(
                (
                    equity["account_key"] != canonical["account_key"],
                    equity["session_date"] != canonical["session_date"],
                    equity["captured_at"] != canonical["captured_at"],
                    equity["payload_hash"] != canonical["equity_payload_hash"],
                )
            ):
                raise ValueError("portfolio capture equity snapshot does not match")
            actual_positions: dict[str, str] = {}
            if position_ids:
                placeholders = ",".join("?" for _ in position_ids)
                rows = connection.execute(
                    f"SELECT snapshot_id, account_key, session_date, captured_at, "
                    f"snapshot_hash FROM portfolio_position_snapshots "
                    f"WHERE snapshot_id IN ({placeholders})",
                    tuple(position_ids),
                ).fetchall()
                for row in rows:
                    if (
                        row["account_key"] != canonical["account_key"]
                        or row["session_date"] != canonical["session_date"]
                        or row["captured_at"] != canonical["captured_at"]
                    ):
                        raise ValueError(
                            "portfolio capture position snapshot belongs to another capture"
                        )
                    actual_positions[row["snapshot_id"]] = row["snapshot_hash"]
            expected_positions = dict(zip(position_ids, position_hashes))
            if actual_positions != expected_positions:
                raise ValueError(
                    "portfolio capture position snapshot identities or hashes do not match"
                )
            existing_capture = connection.execute(
                "SELECT payload_hash FROM portfolio_capture_sessions WHERE capture_id = ?",
                (canonical["capture_id"],),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO portfolio_capture_sessions(
                    capture_id, observation_id, evidence_epoch, lineage_hash,
                    account_key, account_mode, broker_account_id, session_date,
                    captured_at, source, equity_snapshot_id, position_count,
                    payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    canonical["capture_id"],
                    canonical["observation_id"],
                    canonical["evidence_epoch"],
                    canonical["lineage_hash"],
                    canonical["account_key"],
                    canonical["account_mode"],
                    canonical["broker_account_id"],
                    canonical["session_date"],
                    canonical["captured_at"],
                    canonical["source"],
                    canonical["equity_snapshot_id"],
                    canonical["position_count"],
                    payload_json,
                    payload_hash,
                ),
            )
            row = connection.execute(
                "SELECT * FROM portfolio_capture_sessions WHERE capture_id = ?",
                (canonical["capture_id"],),
            ).fetchone()
            if row is None:
                conflict = connection.execute(
                    "SELECT capture_id FROM portfolio_capture_sessions "
                    "WHERE observation_id = ?",
                    (canonical["observation_id"],),
                ).fetchone()
                raise ValueError(
                    "paper observation already belongs to a different portfolio capture "
                    f"{None if conflict is None else conflict['capture_id']!r}"
                )
            if row["payload_hash"] != payload_hash:
                raise ValueError(
                    "portfolio capture identity already exists with different content"
                )
            connection.commit()
            return {
                **json.loads(row["payload_json"]),
                "payload_hash": row["payload_hash"],
                "already_recorded": existing_capture is not None,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_portfolio_capture_sessions(
        self,
        *,
        account_key: str | None = None,
        evidence_epoch: str | None = None,
        limit: int = 100_000,
    ) -> list[dict[str, Any]]:
        query = "SELECT payload_json, payload_hash FROM portfolio_capture_sessions"
        clauses: list[str] = []
        params: list[Any] = []
        if account_key is not None:
            clauses.append("account_key = ?")
            params.append(account_key)
        if evidence_epoch is not None:
            clauses.append("evidence_epoch = ?")
            params.append(evidence_epoch)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY session_date ASC, captured_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["payload_hash"] = row["payload_hash"]
            result.append(payload)
        return result

    def register_ml_model(
        self, model_key: str, manifest: dict[str, Any], *, status: str = "shadow",
        registered_at: str | None = None,
    ) -> dict[str, Any]:
        """Register a model manifest for shadow observation (doc 10.1).

        `status` deliberately defaults to "shadow". Doc 17 prohibits
        automatic promotion outright, and doc 3.1 says "no model status
        automatically becomes production authority" -- so nothing in the
        training or inference path may write a status implying authority.
        """
        if not isinstance(model_key, str) or not model_key.strip():
            raise ValueError("model_key must be a non-empty string")
        if status not in ("shadow", "retired"):
            raise ValueError(
                "ml model status must be 'shadow' or 'retired'; production "
                "authority requires a separate, explicit promotion decision "
                "that this method deliberately cannot grant"
            )
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("manifest must be a non-empty dictionary")
        manifest_json = _canonical_ml_json(manifest, "manifest")
        manifest_hash = _hash_payload(manifest_json)
        timestamp = registered_at or datetime.now(timezone.utc).isoformat()
        _parse_aware_timestamp(timestamp, "registered_at")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ml_model_registrations(
                    model_key, registered_at, manifest_json, manifest_hash, status
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(model_key) DO NOTHING
                """,
                (model_key, timestamp, manifest_json, manifest_hash, status),
            )
            row = connection.execute(
                "SELECT * FROM ml_model_registrations WHERE model_key = ?", (model_key,)
            ).fetchone()
            if row["manifest_hash"] != manifest_hash or row["status"] != status:
                raise ValueError(
                    f"model_key {model_key!r} is already registered with different "
                    "manifest content or status; use a new versioned model_key"
                )
        return {
            "model_key": row["model_key"],
            "registered_at": row["registered_at"],
            "manifest": json.loads(row["manifest_json"]),
            "manifest_hash": row["manifest_hash"],
            "status": row["status"],
        }

    def get_ml_model_registration(self, model_key: str) -> dict[str, Any] | None:
        """Return one immutable shadow registration without changing status."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ml_model_registrations WHERE model_key = ?",
                (model_key,),
            ).fetchone()
        if row is None:
            return None
        return {
            "model_key": row["model_key"],
            "registered_at": row["registered_at"],
            "manifest": json.loads(row["manifest_json"]),
            "manifest_hash": row["manifest_hash"],
            "status": row["status"],
        }

    def open_ml_evidence_epoch(
        self,
        *,
        evidence_epoch: str,
        model_key: str,
        task: str,
        lineage: dict[str, Any],
        created_by: str,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        """Open one active evidence epoch for (model_key, task) (plan 12.2).

        `lineage` fingerprints the whole system that produced the evidence:
        model artifact, evaluation report, feature/label versions, data
        provider, configuration, code commit, schedule version. Any change
        starts a NEW epoch, because pooling predictions from two different
        systems into one track record produces a number that describes
        neither.

        The partial unique index makes a second active epoch impossible at
        the database level rather than by convention.
        """
        for name, value in (
            ("evidence_epoch", evidence_epoch), ("model_key", model_key),
            ("task", task), ("created_by", created_by),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        lineage_json = _validate_ml_lineage(lineage)
        lineage_hash = _hash_payload(lineage_json)
        timestamp = _parse_aware_timestamp(
            started_at or datetime.now(timezone.utc).isoformat(), "started_at"
        ).astimezone(timezone.utc).isoformat()

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
            if existing is not None:
                if existing["lineage_hash"] != lineage_hash:
                    raise ValueError(
                        f"evidence epoch {evidence_epoch!r} already exists with "
                        "different lineage; a lineage change requires a NEW epoch"
                    )
                if existing["model_key"] != model_key or existing["task"] != task:
                    raise ValueError(
                        f"evidence epoch {evidence_epoch!r} already belongs to "
                        f"{existing['model_key']!r}/{existing['task']!r}; an epoch "
                        "identity cannot be reused for another model or task"
                    )
                return self._ml_epoch_row_to_dict(existing)
            active = connection.execute(
                "SELECT evidence_epoch, lineage_hash FROM ml_evidence_epochs "
                "WHERE model_key = ? AND task = ? AND status = 'active'",
                (model_key, task),
            ).fetchone()
            if active is not None:
                raise ValueError(
                    f"{model_key!r}/{task!r} already has active epoch "
                    f"{active['evidence_epoch']!r}; close it before opening another "
                    "so evidence from two systems is never pooled"
                )
            connection.execute(
                """
                INSERT INTO ml_evidence_epochs(
                    evidence_epoch, model_key, task, started_at, closed_at,
                    status, lineage_json, lineage_hash, created_by
                ) VALUES (?, ?, ?, ?, NULL, 'active', ?, ?, ?)
                """,
                (
                    evidence_epoch, model_key, task, timestamp,
                    lineage_json, lineage_hash, created_by,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
        return self._ml_epoch_row_to_dict(row)

    def close_ml_evidence_epoch(
        self, evidence_epoch: str, *, closed_at: str | None = None
    ) -> dict[str, Any]:
        closed_timestamp = _parse_aware_timestamp(
            closed_at or datetime.now(timezone.utc).isoformat(), "closed_at"
        ).astimezone(timezone.utc)
        timestamp = closed_timestamp.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
            if row is None:
                raise ValueError(f"no evidence epoch {evidence_epoch!r}")
            if row["status"] != "active":
                return self._ml_epoch_row_to_dict(row)
            started_timestamp = _parse_aware_timestamp(
                row["started_at"], "started_at"
            ).astimezone(timezone.utc)
            if closed_timestamp < started_timestamp:
                raise ValueError("closed_at must not precede started_at")
            runs = connection.execute(
                "SELECT run_id, status, completed_at FROM ml_shadow_runs "
                "WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchall()
            claimed_run = next((run for run in runs if run["status"] == "claimed"), None)
            if claimed_run is not None:
                raise ValueError(
                    f"evidence epoch {evidence_epoch!r} still has claimed shadow run "
                    f"{claimed_run['run_id']!r}; complete or fail it before closing the epoch"
                )
            for run in runs:
                if run["completed_at"] is None:
                    raise ValueError(
                        f"closed shadow run {run['run_id']!r} has no completion timestamp"
                    )
                run_completed = _parse_aware_timestamp(
                    run["completed_at"], "shadow_run.completed_at"
                ).astimezone(timezone.utc)
                if closed_timestamp < run_completed:
                    raise ValueError(
                        f"closed_at must not precede shadow run {run['run_id']!r} "
                        "completion"
                    )
            connection.execute(
                "UPDATE ml_evidence_epochs SET status = 'closed', closed_at = ? "
                "WHERE evidence_epoch = ? AND status = 'active'",
                (timestamp, evidence_epoch),
            )
            row = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
        return self._ml_epoch_row_to_dict(row)

    @staticmethod
    def _ml_epoch_row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "evidence_epoch": row["evidence_epoch"],
            "model_key": row["model_key"],
            "task": row["task"],
            "started_at": row["started_at"],
            "closed_at": row["closed_at"],
            "status": row["status"],
            "lineage": json.loads(row["lineage_json"]),
            "lineage_hash": row["lineage_hash"],
            "created_by": row["created_by"],
        }

    def get_active_ml_evidence_epoch(
        self, model_key: str, task: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE model_key = ? AND task = ? "
                "AND status = 'active' LIMIT 1",
                (model_key, task),
            ).fetchone()
        return self._ml_epoch_row_to_dict(row) if row is not None else None

    def get_ml_evidence_epoch(self, evidence_epoch: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ml_evidence_epochs WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
        return self._ml_epoch_row_to_dict(row) if row is not None else None

    def list_ml_evidence_epochs(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ml_evidence_epochs ORDER BY started_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._ml_epoch_row_to_dict(row) for row in rows]

    def claim_ml_shadow_run(
        self,
        *,
        schedule_key: str,
        scheduled_for: str,
        evidence_epoch: str,
        code_commit: str,
        configuration_hash: str,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        """Transactionally claim one scheduled slot (plan 12.3 step 1).

        The unique index on (schedule_key, scheduled_for) is what makes this
        safe: two concurrent runners race on the INSERT and exactly one wins.
        The loser gets the winner's row back rather than an exception, so an
        exact retry is idempotent -- but a retry whose CONFIGURATION differs
        is loud, because that is a different experiment wearing the same
        slot's name.
        """
        for name, value in (
            ("schedule_key", schedule_key), ("evidence_epoch", evidence_epoch),
            ("code_commit", code_commit), ("configuration_hash", configuration_hash),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if _COMMIT_HASH.fullmatch(code_commit) is None:
            raise ValueError("code_commit must be a lowercase 40- or 64-character git hash")
        _require_sha256(configuration_hash, "configuration_hash")
        scheduled_timestamp = _parse_aware_timestamp(
            scheduled_for, "scheduled_for"
        ).astimezone(timezone.utc)
        scheduled_for = scheduled_timestamp.isoformat()
        started_timestamp = _parse_aware_timestamp(
            started_at or datetime.now(timezone.utc).isoformat(), "started_at"
        ).astimezone(timezone.utc)
        if started_timestamp < scheduled_timestamp:
            raise ValueError("started_at must not precede scheduled_for")
        timestamp = started_timestamp.isoformat()
        run_id = "mlrun-" + _hash_payload(
            _canonical_ml_json(
                {"schedule_key": schedule_key, "scheduled_for": scheduled_for},
                "run identity",
            )
        )[:24]

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # An exact retry remains idempotent even after its epoch closes.
            # It cannot add or alter evidence, so epoch status is relevant
            # only when claiming a genuinely new slot.
            row = connection.execute(
                "SELECT * FROM ml_shadow_runs WHERE schedule_key = ? AND scheduled_for = ?",
                (schedule_key, scheduled_for),
            ).fetchone()
            if row is not None:
                if row["configuration_hash"] != configuration_hash:
                    raise ValueError(
                        f"scheduled slot {schedule_key!r}@{scheduled_for!r} already ran with "
                        "a different configuration_hash; a changed configuration is a "
                        "different experiment and requires a new schedule or epoch"
                    )
                if row["code_commit"] != code_commit:
                    raise ValueError(
                        f"scheduled slot {schedule_key!r}@{scheduled_for!r} already ran "
                        "with a different code_commit"
                    )
                if row["evidence_epoch"] != evidence_epoch:
                    raise ValueError(
                        f"scheduled slot {schedule_key!r}@{scheduled_for!r} belongs to epoch "
                        f"{row['evidence_epoch']!r}, not {evidence_epoch!r}"
                    )
                return self._ml_shadow_run_row_to_dict(row)

            epoch = connection.execute(
                "SELECT status, model_key, task, started_at, lineage_json "
                "FROM ml_evidence_epochs "
                "WHERE evidence_epoch = ?",
                (evidence_epoch,),
            ).fetchone()
            if epoch is None:
                raise ValueError(
                    f"evidence epoch {evidence_epoch!r} does not exist; a shadow run "
                    "cannot create evidence outside a registered epoch"
                )
            if epoch["status"] != "active":
                raise ValueError(
                    f"evidence epoch {evidence_epoch!r} is {epoch['status']}; a closed "
                    "epoch cannot accept new predictions"
                )
            epoch_lineage = json.loads(epoch["lineage_json"])
            if epoch_lineage["configuration_hash"] != configuration_hash:
                raise ValueError(
                    "configuration_hash does not match the active evidence epoch; "
                    "a configuration change requires a new epoch"
                )
            if epoch_lineage["code_commit"] != code_commit:
                raise ValueError(
                    "code_commit does not match the active evidence epoch; a code "
                    "change requires a new epoch"
                )
            epoch_started = _parse_aware_timestamp(
                epoch["started_at"], "evidence_epoch.started_at"
            ).astimezone(timezone.utc)
            if scheduled_timestamp < epoch_started:
                raise ValueError(
                    "scheduled_for must not precede the evidence epoch's started_at"
                )
            connection.execute(
                """
                INSERT INTO ml_shadow_runs(
                    run_id, schedule_key, scheduled_for, started_at, completed_at,
                    status, code_commit, configuration_hash, evidence_epoch,
                    prediction_count, unavailable_count, error_json
                ) VALUES (?, ?, ?, ?, NULL, 'claimed', ?, ?, ?, 0, 0, NULL)
                ON CONFLICT(schedule_key, scheduled_for) DO NOTHING
                """,
                (
                    run_id, schedule_key, scheduled_for, timestamp,
                    code_commit, configuration_hash, evidence_epoch,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ml_shadow_runs WHERE schedule_key = ? AND scheduled_for = ?",
                (schedule_key, scheduled_for),
            ).fetchone()
            if row["configuration_hash"] != configuration_hash:
                raise ValueError(
                    f"scheduled slot {schedule_key!r}@{scheduled_for!r} already ran with "
                    "a different configuration_hash; a changed configuration is a "
                    "different experiment and requires a new schedule or epoch"
                )
            if row["code_commit"] != code_commit:
                raise ValueError(
                    f"scheduled slot {schedule_key!r}@{scheduled_for!r} already ran "
                    "with a different code_commit"
                )
            if row["evidence_epoch"] != evidence_epoch:
                raise ValueError(
                    f"scheduled slot {schedule_key!r}@{scheduled_for!r} belongs to epoch "
                    f"{row['evidence_epoch']!r}, not {evidence_epoch!r}"
                )
        return self._ml_shadow_run_row_to_dict(row)

    def complete_ml_shadow_run(
        self,
        run_id: str,
        *,
        status: str,
        prediction_count: int,
        unavailable_count: int,
        error: dict[str, Any] | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        """Close a run with durable counts and errors (plan 12.3 step 6)."""
        if status not in ("completed", "failed"):
            raise ValueError("shadow run status must be 'completed' or 'failed'")
        for name, value in (
            ("prediction_count", prediction_count),
            ("unavailable_count", unavailable_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if unavailable_count > prediction_count:
            raise ValueError("unavailable_count cannot exceed prediction_count")
        if status == "completed" and error is not None:
            raise ValueError("a completed shadow run cannot carry an operational error")
        if status == "failed" and (not isinstance(error, dict) or not error):
            raise ValueError("a failed shadow run must carry a non-empty durable error")
        completed_timestamp = _parse_aware_timestamp(
            completed_at or datetime.now(timezone.utc).isoformat(), "completed_at"
        ).astimezone(timezone.utc)
        timestamp = completed_timestamp.isoformat()
        error_json = (
            _canonical_ml_json(error, "error") if error is not None else None
        )
        with self._connect() as connection:
            # Lock writers before counting predictions so a late prediction
            # cannot slip in between the count and the close transition.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM ml_shadow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"no shadow run {run_id!r}")
            if row["status"] != "claimed":
                # Already closed. Idempotent for an exact repeat, loud for a
                # different result, so a crash-resume cannot silently rewrite
                # a completed run's counts.
                if (
                    row["status"] == status
                    and row["prediction_count"] == prediction_count
                    and row["unavailable_count"] == unavailable_count
                    and row["error_json"] == error_json
                ):
                    return self._ml_shadow_run_row_to_dict(row)
                raise ValueError(
                    f"shadow run {run_id!r} is already {row['status']} with different "
                    "counts; refusing to rewrite a closed run"
                )
            if completed_timestamp < _parse_aware_timestamp(
                row["started_at"], "started_at"
            ).astimezone(timezone.utc):
                raise ValueError("completed_at must not precede started_at")
            predictions = connection.execute(
                "SELECT available, generated_at FROM ml_predictions WHERE shadow_run_id = ?",
                (run_id,),
            ).fetchall()
            actual_prediction_count = len(predictions)
            actual_unavailable_count = sum(
                1 for prediction in predictions if not prediction["available"]
            )
            if (
                actual_prediction_count != prediction_count
                or actual_unavailable_count != unavailable_count
            ):
                raise ValueError(
                    f"shadow run counts do not match immutable predictions: "
                    f"stored={actual_prediction_count}/{actual_unavailable_count} "
                    f"reported={prediction_count}/{unavailable_count}"
                )
            for prediction in predictions:
                generated_at = _parse_aware_timestamp(
                    prediction["generated_at"], "prediction.generated_at"
                ).astimezone(timezone.utc)
                if completed_timestamp < generated_at:
                    raise ValueError(
                        "completed_at must not precede a prediction generated by the run"
                    )
            cursor = connection.execute(
                "UPDATE ml_shadow_runs SET status = ?, completed_at = ?, "
                "prediction_count = ?, unavailable_count = ?, error_json = ? "
                "WHERE run_id = ? AND status = 'claimed'",
                (
                    status, timestamp, prediction_count, unavailable_count,
                    error_json, run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ml_shadow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if cursor.rowcount != 1 and not (
                row["status"] == status
                and row["prediction_count"] == prediction_count
                and row["unavailable_count"] == unavailable_count
                and row["error_json"] == error_json
            ):
                raise ValueError(
                    f"shadow run {run_id!r} was concurrently closed with a different result"
                )
        return self._ml_shadow_run_row_to_dict(row)

    @staticmethod
    def _ml_shadow_run_row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "schedule_key": row["schedule_key"],
            "scheduled_for": row["scheduled_for"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "status": row["status"],
            "code_commit": row["code_commit"],
            "configuration_hash": row["configuration_hash"],
            "evidence_epoch": row["evidence_epoch"],
            "prediction_count": row["prediction_count"],
            "unavailable_count": row["unavailable_count"],
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }

    def list_ml_shadow_runs(
        self,
        *,
        schedule_key: str | None = None,
        evidence_epoch: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if schedule_key is not None:
            clauses.append("schedule_key = ?")
            params.append(schedule_key)
        if evidence_epoch is not None:
            clauses.append("evidence_epoch = ?")
            params.append(evidence_epoch)
        query = "SELECT * FROM ml_shadow_runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY scheduled_for ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._ml_shadow_run_row_to_dict(row) for row in rows]

    def record_ml_prediction(self, prediction: dict[str, Any]) -> dict[str, Any]:
        """Append one shadow prediction, idempotently (doc 10.2).

        Idempotency is enforced by a UNIQUE index on
        (model_key, task, subject_key, as_of_session, horizon_sessions), so
        re-running a scheduled shadow job cannot create a second, possibly
        DIFFERENT prediction for a session already recorded. Doc 10.2:
        "Never rewrite a prediction after its as_of_session" -- an exact
        retry returns the original row, while a conflicting value for the
        same identity is rejected loudly rather than silently hidden.
        """
        required = (
            "model_key",
            "task",
            "subject_key",
            "as_of_session",
            "generated_at",
            "horizon_sessions",
            "target_available_at",
            "data_available_at",
            "feature_freshness",
            "feature_snapshot_hash",
            "evidence_status",
            "production_authoritative",
            "available",
        )
        missing = [name for name in required if name not in prediction]
        if missing:
            raise ValueError(f"prediction is missing required fields: {missing}")
        for name in ("model_key", "task", "subject_key"):
            if not isinstance(prediction[name], str) or not prediction[name].strip():
                raise ValueError(f"prediction.{name} must be a non-empty string")
        # ML-LR-6 (plan 12.2): both are nullable in the schema so pre-shadow
        # rows still load, but a prediction that names EITHER must name BOTH
        # and they must agree with a real, active run. A prediction carrying
        # an epoch but no run cannot be traced to the schedule that produced
        # it, which is precisely the lineage the epoch is supposed to give.
        epoch = prediction.get("evidence_epoch")
        shadow_run_id = prediction.get("shadow_run_id")
        if (epoch is None) != (shadow_run_id is None):
            raise ValueError(
                "evidence_epoch and shadow_run_id must be supplied together; a "
                "prediction inside an epoch must be traceable to the run that made it"
            )
        as_of = _parse_session_date(prediction["as_of_session"], "as_of_session")
        generated_at = _parse_aware_timestamp(prediction["generated_at"], "generated_at")
        target_available_at = _parse_aware_timestamp(
            prediction["target_available_at"], "target_available_at"
        )
        data_available_at = _parse_aware_timestamp(
            prediction["data_available_at"], "data_available_at"
        )
        horizon = prediction["horizon_sessions"]
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise ValueError("horizon_sessions must be a positive integer")
        earliest_possible_target = as_of + timedelta(days=horizon)
        if target_available_at.date() < earliest_possible_target:
            raise ValueError(
                "target_available_at is earlier than the minimum possible date "
                "for horizon_sessions"
            )
        if target_available_at <= generated_at:
            raise ValueError("target_available_at must be after generated_at")
        if data_available_at > generated_at:
            raise ValueError("data_available_at cannot be after generated_at")
        if generated_at.astimezone(_EASTERN).date() != as_of:
            raise ValueError(
                "generated_at must fall on as_of_session in America/New_York; "
                "backfilled predictions require a separate evidence workflow"
            )
        _require_sha256(prediction["feature_snapshot_hash"], "feature_snapshot_hash")
        if not isinstance(prediction["feature_freshness"], dict):
            raise ValueError("feature_freshness must be a dictionary")
        _canonical_ml_json(prediction["feature_freshness"], "feature_freshness")
        if prediction["available"] and not prediction["feature_freshness"]:
            raise ValueError("an available prediction must record feature_freshness")
        if prediction["evidence_status"] not in {
            "exploratory", "promising_unconfirmed", "rejected", "unavailable"
        }:
            raise ValueError("prediction.evidence_status is not recognized")
        if prediction["production_authoritative"] is not False:
            raise ValueError("shadow predictions must be production_authoritative=false")
        if not isinstance(prediction["available"], bool):
            raise ValueError("prediction.available must be a boolean")
        values = prediction.get("values")
        if prediction["available"]:
            if not isinstance(values, dict) or not values:
                raise ValueError("an available prediction must contain non-empty values")
            _canonical_ml_json(values, "prediction.values")
            _reject_execution_shaped_values(values)
            if prediction["evidence_status"] == "unavailable":
                raise ValueError("an available prediction cannot have unavailable evidence")
        elif values not in (None, {}):
            raise ValueError("an unavailable prediction cannot contain predicted values")
        elif prediction["evidence_status"] != "unavailable":
            raise ValueError("an unavailable prediction must have unavailable evidence status")
        prospective = prediction.get("prospective_contract")
        if prospective not in (None, {}):
            if not isinstance(prospective, dict):
                raise ValueError("prediction.prospective_contract must be a dictionary")
            if prospective.get("production_authoritative") is not False:
                raise ValueError(
                    "prediction.prospective_contract must be production_authoritative=false"
                )
            matching = {
                "prediction_id": prediction.get("prediction_id"),
                "task": prediction["task"],
                "subject_key": prediction["subject_key"],
                "as_of_session": prediction["as_of_session"],
                "horizon_sessions": horizon,
                "target_available_at": prediction["target_available_at"],
                "available": prediction["available"],
            }
            mismatches = {
                key: {"prediction": expected, "prospective_contract": prospective.get(key)}
                for key, expected in matching.items()
                if prospective.get(key) != expected
            }
            if mismatches:
                raise ValueError(
                    "prediction.prospective_contract identity mismatch: "
                    f"{mismatches}"
                )
            _canonical_ml_json(prospective, "prediction.prospective_contract")
            _reject_execution_shaped_values(
                prospective, path="prediction.prospective_contract"
            )
        payload_json = _canonical_ml_json(prediction, "prediction")
        prediction_hash = _hash_payload(payload_json)
        prediction_id = prediction.get("prediction_id") or (
            "mlpred-" + prediction_hash[:24]
        )
        available = prediction["available"]
        refusal_reasons = list(prediction.get("refusal_reasons", ()))
        if any(not isinstance(reason, str) or not reason.strip() for reason in refusal_reasons):
            raise ValueError("refusal_reasons must contain non-empty strings")
        if not available and not refusal_reasons:
            raise ValueError(
                "an unavailable prediction must record at least one refusal reason"
            )
        if available and refusal_reasons:
            raise ValueError("an available prediction cannot carry refusal reasons")
        with self._connect() as connection:
            # Serialize prediction writes against run completion. Otherwise a
            # completion could count rows and close the run while this method
            # was still between its lineage checks and INSERT.
            connection.execute("BEGIN IMMEDIATE")
            registration = connection.execute(
                "SELECT status FROM ml_model_registrations WHERE model_key = ?",
                (prediction["model_key"],),
            ).fetchone()
            if registration is None:
                raise ValueError(
                    f"model_key {prediction['model_key']!r} is not registered"
                )
            if registration["status"] != "shadow":
                raise ValueError(
                    f"model_key {prediction['model_key']!r} is not active for shadow predictions"
                )
            existing = connection.execute(
                "SELECT * FROM ml_predictions WHERE model_key = ? AND task = ? "
                "AND subject_key = ? AND as_of_session = ? AND horizon_sessions = ?",
                (
                    prediction["model_key"], prediction["task"],
                    prediction["subject_key"], prediction["as_of_session"], horizon,
                ),
            ).fetchone()
            if existing is not None:
                if existing["prediction_hash"] != prediction_hash:
                    raise ValueError(
                        "a different prediction already exists for this immutable "
                        "model/task/subject/session/horizon identity"
                    )
                return self._ml_prediction_row_to_dict(existing)
            if epoch is not None:
                epoch_row = connection.execute(
                    "SELECT model_key, task, status FROM ml_evidence_epochs "
                    "WHERE evidence_epoch = ?",
                    (epoch,),
                ).fetchone()
                if epoch_row is None:
                    raise ValueError(f"evidence_epoch {epoch!r} does not exist")
                if (
                    epoch_row["model_key"] != prediction["model_key"]
                    or epoch_row["task"] != prediction["task"]
                ):
                    raise ValueError(
                        "prediction model_key/task does not match its evidence epoch"
                    )
                if epoch_row["status"] != "active":
                    raise ValueError(
                        f"evidence_epoch {epoch!r} is {epoch_row['status']}; no new "
                        "prediction may be added"
                    )
                run_row = connection.execute(
                    "SELECT evidence_epoch, scheduled_for, status FROM ml_shadow_runs "
                    "WHERE run_id = ?",
                    (shadow_run_id,),
                ).fetchone()
                if run_row is None:
                    raise ValueError(f"shadow_run_id {shadow_run_id!r} does not exist")
                if run_row["evidence_epoch"] != epoch:
                    raise ValueError(
                        "prediction shadow run belongs to a different evidence epoch"
                    )
                if run_row["status"] != "claimed":
                    raise ValueError(
                        f"shadow run {shadow_run_id!r} is {run_row['status']}; no new "
                        "prediction may be added"
                    )
                scheduled_timestamp = _parse_aware_timestamp(
                    run_row["scheduled_for"], "shadow_run.scheduled_for"
                )
                if scheduled_timestamp.astimezone(_EASTERN).date() != as_of:
                    raise ValueError(
                        "prediction as_of_session does not match its shadow run slot"
                    )
                if generated_at < scheduled_timestamp:
                    raise ValueError(
                        "prediction.generated_at cannot precede its scheduled shadow run"
                    )
            connection.execute(
                """
                INSERT INTO ml_predictions(
                    prediction_id, model_key, task, subject_key, as_of_session,
                    generated_at, horizon_sessions, target_available_at, feature_snapshot_hash,
                    prediction_json, prediction_hash, available, refusal_reasons_json,
                    evidence_epoch, shadow_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    prediction_id,
                    prediction["model_key"],
                    prediction["task"],
                    prediction["subject_key"],
                    prediction["as_of_session"],
                    prediction["generated_at"],
                    horizon,
                    prediction["target_available_at"],
                    prediction["feature_snapshot_hash"],
                    payload_json,
                    prediction_hash,
                    1 if available else 0,
                    json.dumps(refusal_reasons, sort_keys=True, separators=(",", ":")),
                    epoch,
                    shadow_run_id,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM ml_predictions
                WHERE model_key = ? AND task = ? AND subject_key = ?
                  AND as_of_session = ? AND horizon_sessions = ?
                """,
                (
                    prediction["model_key"],
                    prediction["task"],
                    prediction["subject_key"],
                    prediction["as_of_session"],
                    horizon,
                ),
            ).fetchone()
            if row is None:
                raise ValueError(
                    "prediction_id conflicts with a different prediction identity"
                )
            if row["prediction_hash"] != prediction_hash:
                raise ValueError(
                    "a different prediction already exists for this immutable "
                    "model/task/subject/session/horizon identity"
                )
        return self._ml_prediction_row_to_dict(row)

    @staticmethod
    def _ml_prediction_row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "prediction_id": row["prediction_id"],
            "model_key": row["model_key"],
            "task": row["task"],
            "subject_key": row["subject_key"],
            "as_of_session": row["as_of_session"],
            "generated_at": row["generated_at"],
            "horizon_sessions": row["horizon_sessions"],
            "target_available_at": row["target_available_at"],
            "feature_snapshot_hash": row["feature_snapshot_hash"],
            "prediction": json.loads(row["prediction_json"]),
            "prediction_hash": row["prediction_hash"],
            "available": bool(row["available"]),
            "refusal_reasons": json.loads(row["refusal_reasons_json"]),
            # NULL for pre-shadow rows, which is the honest answer: their
            # lineage was never recorded and cannot be reconstructed.
            "evidence_epoch": row["evidence_epoch"],
            "shadow_run_id": row["shadow_run_id"],
        }

    def list_ml_predictions(
        self,
        *,
        model_key: str | None = None,
        evidence_epoch: str | None = None,
        shadow_run_id: str | None = None,
        limit: int | None = 10_000,
    ) -> list[dict[str, Any]]:
        """List predictions, optionally scoped to a model, epoch, and/or run.

        Plan 12.2: "Do not pool across epochs." Any monitoring or scoring
        caller should pass `evidence_epoch`, because a track record spanning
        a model or provider change describes neither system. The unscoped
        form remains available for inventory and debugging, where seeing
        everything is the point.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if model_key is not None:
            clauses.append("model_key = ?")
            params.append(model_key)
        if evidence_epoch is not None:
            clauses.append("evidence_epoch = ?")
            params.append(evidence_epoch)
        if shadow_run_id is not None:
            clauses.append("shadow_run_id = ?")
            params.append(shadow_run_id)
        query = "SELECT * FROM ml_predictions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY as_of_session ASC, subject_key ASC"
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError("limit must be a positive integer or None")
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._ml_prediction_row_to_dict(row) for row in rows]

    def record_ml_prediction_outcome(
        self, prediction_id: str, outcome: dict[str, Any], *, matured_at: str
    ) -> dict[str, Any]:
        """Attach a realized outcome to an existing prediction (doc 10.2).

        Enforces both of doc 10.1's integrity rules explicitly in addition
        to the database foreign key: "An outcome cannot exist before its
        prediction or before its horizon matures." The maturity check uses
        the prediction's immutable target-availability timestamp, so a
        caller cannot attach an outcome early.
        """
        with self._connect() as connection:
            prediction = connection.execute(
                "SELECT * FROM ml_predictions WHERE prediction_id = ?", (prediction_id,)
            ).fetchone()
            if prediction is None:
                raise ValueError(
                    f"no prediction {prediction_id!r} exists; an outcome cannot "
                    "precede its prediction"
                )
            if not bool(prediction["available"]):
                raise ValueError("an unavailable prediction cannot receive a realized outcome")
            matured_timestamp = _parse_aware_timestamp(matured_at, "matured_at")
            target_available_raw = prediction["target_available_at"]
            if not target_available_raw:
                raise ValueError(
                    "legacy prediction has no target_available_at; maturity cannot "
                    "be established safely"
                )
            target_available = _parse_aware_timestamp(
                target_available_raw, "prediction.target_available_at"
            )
            if matured_timestamp < target_available:
                raise ValueError(
                    f"matured_at {matured_at!r} precedes target availability "
                    f"{target_available_raw!r}"
                )
            if not isinstance(outcome, dict) or not outcome:
                raise ValueError("outcome must be a non-empty dictionary")
            outcome_json = _canonical_ml_json(outcome, "outcome")
            outcome_hash = _hash_payload(outcome_json)
            connection.execute(
                """
                INSERT INTO ml_prediction_outcomes(
                    prediction_id, matured_at, outcome_json, outcome_hash
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(prediction_id) DO NOTHING
                """,
                (prediction_id, matured_at, outcome_json, outcome_hash),
            )
            row = connection.execute(
                "SELECT * FROM ml_prediction_outcomes WHERE prediction_id = ?",
                (prediction_id,),
            ).fetchone()
            if row["outcome_hash"] != outcome_hash or row["matured_at"] != matured_at:
                raise ValueError(
                    "a different immutable outcome already exists for this prediction"
                )
        return {
            "prediction_id": row["prediction_id"],
            "matured_at": row["matured_at"],
            "outcome": json.loads(row["outcome_json"]),
            "outcome_hash": row["outcome_hash"],
        }

    def list_ml_prediction_outcomes(self, *, limit: int = 10_000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ml_prediction_outcomes ORDER BY matured_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "prediction_id": row["prediction_id"],
                "matured_at": row["matured_at"],
                "outcome": json.loads(row["outcome_json"]),
                "outcome_hash": row["outcome_hash"],
            }
            for row in rows
        ]

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
        connection = self._open_database(self.path)
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
        connection = self._open_database(self.path)
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

    def list_proposals(
        self,
        status: str | None = None,
        limit: int = 100,
        *,
        include_dismissed: bool = True,
        include_expired: bool = True,
    ) -> list[dict[str, Any]]:
        """Newest proposals, optionally excluding archive-class rows.

        The visibility flags (UI-2d) default to True so every existing
        audit caller keeps seeing complete history, and they apply ONLY
        when `status is None`: an explicit exact-status selection always
        wins, so asking for `status="dismissed"` can never be silently
        contradicted by a hidden visibility flag.
        """
        query = "SELECT payload_json, status FROM trade_proposals"
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        else:
            if not include_dismissed:
                clauses.append("status != ?")
                params.append(DISMISSED)
            if not include_expired:
                clauses.append("status != ?")
                params.append(EXPIRED)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
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

    def list_proposals_for_outcomes(
        self,
        *,
        statuses: tuple[str, ...] | list[str],
        include_unknown_statuses: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read-only History query for UI-2b outcome filtering: the most
        recent proposals whose status is in `statuses`, optionally ALSO any
        row whose status is outside the canonical STATUSES tuple (the
        "Other / unknown" outcome group, which is only expressible as a
        negative match -- a positive IN-list cannot name statuses that do
        not exist yet).

        Same ordering and hydration as list_proposals (created_at DESC,
        authoritative row status over the stored payload's), so the two
        filter paths on the History page share row semantics: "the newest
        `limit` rows OF THE FILTERED KIND", never a client-side subset of
        the newest `limit` rows overall.

        Empty criteria return no rows: an empty outcome selection must not
        silently widen into "(any)".
        """
        known = tuple(dict.fromkeys(statuses))
        clauses: list[str] = []
        params: list[Any] = []
        if known:
            clauses.append(
                f"status IN ({','.join('?' for _ in known)})"
            )
            params.extend(known)
        if include_unknown_statuses:
            clauses.append(
                f"status NOT IN ({','.join('?' for _ in STATUSES)})"
            )
            params.extend(STATUSES)
        if not clauses:
            return []
        query = (
            "SELECT payload_json, status FROM trade_proposals WHERE "
            + " OR ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            proposal = json.loads(row["payload_json"])
            proposal["status"] = row["status"]
            result.append(proposal)
        return result

    # --- UI-2d: proposal dismissal (archive, never delete) -----------------
    #
    # Dismissal removes an unused proposal from the DEFAULT History view
    # while retaining its complete database row, payload, and unique
    # idempotency key. It is the narrow, audited alternative to deletion:
    # no row leaves the database, no broker call is made, and only rows
    # that provably never touched validation, approval, reservation,
    # allocation batching, or any broker lifecycle qualify.

    def proposal_dismissal_eligibility(self, proposal_ids) -> "DismissalPreview":
        """Read-only preview: per-proposal dismissibility, exact refusal
        reasons, and a canonical hash binding the preview to current
        database state. The mutation requires that hash, so the user can
        never confirm one set of proposals while a refresh or concurrent
        process changes their state or identity."""
        ids = self._validated_dismissal_ids(proposal_ids)
        with self._connect() as connection:
            records = self._dismissal_records(connection, ids)
        return _preview_from_records(records)

    def dismiss_proposals(
        self,
        proposal_ids,
        *,
        dismissed_by: str,
        reason: str,
        expected_preview_hash: str,
    ) -> "DismissalResult":
        """Atomically dismiss the requested proposals, all-or-nothing.

        Inside one BEGIN IMMEDIATE transaction, eligibility is recomputed
        with the same rule as the preview and the recomputed preview hash
        must equal `expected_preview_hash` -- any concurrent state change
        (a claim, an expiry, another dismissal of PART of the selection)
        alters a row's status/updated_at and therefore the hash, so the
        stale confirmation is refused and nothing is written.

        Idempotent replay: when EVERY requested proposal is already
        `dismissed`, the call reports them as already dismissed and writes
        nothing (the original dismissal metadata is never rewritten); the
        hash is not enforced on that no-op path because no state changes.

        Never calls a broker and never creates order/event/reservation
        rows; the payload gains dismissed_at/by/reason/from_status in the
        same transaction as the status transition.
        """
        ids = self._validated_dismissal_ids(proposal_ids)
        if not isinstance(dismissed_by, str) or not dismissed_by.strip():
            raise ValueError("dismissed_by must be a non-empty string.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A non-empty dismissal reason is required.")

        connection = self._open_database(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            records = self._dismissal_records(connection, ids)

            already = tuple(
                record["proposal_id"]
                for record in records
                if record["status"] == DISMISSED
            )
            pending = [
                record for record in records if record["status"] != DISMISSED
            ]
            if not pending:
                connection.rollback()
                return DismissalResult(
                    dismissed_ids=(),
                    already_dismissed_ids=already,
                    dismissed_at=None,
                )

            refusals = {
                record["proposal_id"]: record["refusal_reasons"]
                for record in pending
                if not record["dismissible"]
            }
            if refusals:
                connection.rollback()
                detail = "; ".join(
                    f"{proposal_id}: {', '.join(reasons)}"
                    for proposal_id, reasons in sorted(refusals.items())
                )
                raise ValueError(
                    "Dismissal refused (all-or-nothing; nothing was "
                    f"dismissed): {detail}"
                )

            current_hash = _preview_from_records(records).preview_hash
            if current_hash != expected_preview_hash:
                connection.rollback()
                raise ValueError(
                    "Stale dismissal preview: proposal state changed since "
                    "the preview was generated. Nothing was dismissed -- "
                    "refresh the preview and confirm again."
                )

            dismissed_at = datetime.now(timezone.utc).isoformat()
            dismissed_ids: list[str] = []
            for record in pending:
                payload = record["payload"]
                payload["status"] = DISMISSED
                payload["dismissed_at"] = dismissed_at
                payload["dismissed_by"] = dismissed_by.strip()
                payload["dismissed_reason"] = reason.strip()
                payload["dismissed_from_status"] = record["status"]
                cursor = connection.execute(
                    "UPDATE trade_proposals SET status = ?, payload_json = ?, "
                    "updated_at = ? WHERE proposal_id = ? AND status = ?",
                    (
                        DISMISSED,
                        json.dumps(payload, sort_keys=True),
                        dismissed_at,
                        record["proposal_id"],
                        record["status"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"Concurrent change to {record['proposal_id']} during "
                        "dismissal; nothing was dismissed."
                    )
                dismissed_ids.append(record["proposal_id"])
            connection.commit()
            return DismissalResult(
                dismissed_ids=tuple(dismissed_ids),
                already_dismissed_ids=already,
                dismissed_at=dismissed_at,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _validated_dismissal_ids(proposal_ids) -> tuple[str, ...]:
        ids = tuple(proposal_ids)
        if not ids:
            raise ValueError("At least one proposal_id is required.")
        if any(not isinstance(pid, str) or not pid for pid in ids):
            raise ValueError("proposal_ids must be non-empty strings.")
        if len(set(ids)) != len(ids):
            raise ValueError("proposal_ids must be unique.")
        return ids

    def _dismissal_records(
        self, connection: sqlite3.Connection, ids: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        """THE eligibility rule, shared verbatim by preview and mutation so
        the two can never drift. Every check runs against the same
        connection (and, for the mutation, inside its transaction)."""
        batch_referenced, batch_errors = _allocation_batch_references(connection)
        records: list[dict[str, Any]] = []
        for proposal_id in ids:
            row = connection.execute(
                "SELECT payload_json, status, created_at, expires_at, "
                "idempotency_key, updated_at FROM trade_proposals "
                "WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                records.append(
                    {
                        "proposal_id": proposal_id,
                        "payload": {},
                        "status": "(missing)",
                        "created_at": "",
                        "expires_at": "",
                        "updated_at": "",
                        "idempotency_key": "",
                        "payload_json": "",
                        "dismissible": False,
                        "refusal_reasons": ("unknown proposal_id",),
                    }
                )
                continue

            reasons: list[str] = []
            status = row["status"]
            if status != DISMISSED and status not in DISMISSIBLE_SOURCE_STATUSES:
                reasons.append(
                    f"status {status!r} is not dismissible (only "
                    f"{', '.join(DISMISSIBLE_SOURCE_STATUSES)} qualify)"
                )
            for table, label in (
                ("broker_orders", "broker order"),
                ("broker_order_events", "broker order event"),
                ("execution_telemetry_events", "execution telemetry event"),
                ("execution_reservations", "execution reservation"),
            ):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE proposal_id = ?",
                    (proposal_id,),
                ).fetchone()[0]
                if count:
                    reasons.append(f"{count} {label} row(s) reference it")
            if proposal_id in batch_referenced:
                reasons.append(
                    "an allocation batch references it "
                    f"({', '.join(sorted(batch_referenced[proposal_id]))})"
                )
            reasons.extend(batch_errors)

            try:
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, dict):
                    raise ValueError("payload is not an object")
            except (ValueError, TypeError):
                payload = {}
                reasons.append("payload JSON is unreadable")
            evidence = sorted(
                key
                for key in _DISMISSAL_EXECUTION_EVIDENCE_KEYS
                if key in payload
            )
            if evidence:
                reasons.append(
                    "payload carries execution-shaped evidence "
                    f"({', '.join(evidence)})"
                )

            records.append(
                {
                    "proposal_id": proposal_id,
                    "payload": payload,
                    "status": status,
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "updated_at": row["updated_at"],
                    "idempotency_key": row["idempotency_key"],
                    "payload_json": row["payload_json"],
                    "dismissible": not reasons and status != DISMISSED,
                    "refusal_reasons": tuple(
                        reasons if status != DISMISSED else ["already dismissed"]
                    ),
                }
            )
        return records

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
        connection = self._open_database(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json, status FROM trade_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown proposal: {proposal_id}")

            order_id = str(order["order_id"])
            existing_order = connection.execute(
                """
                SELECT proposal_id FROM broker_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
            if (
                existing_order is not None
                and existing_order["proposal_id"] != proposal_id
            ):
                raise ValueError(
                    f"Broker order {order_id} is already bound to proposal "
                    f"{existing_order['proposal_id']}, not {proposal_id}."
                )
            existing_event = connection.execute(
                """
                SELECT order_id, proposal_id
                FROM broker_order_events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
            if existing_event is not None and (
                existing_event["order_id"] != order_id
                or existing_event["proposal_id"] != proposal_id
            ):
                raise ValueError(
                    f"Broker event {event_id} is already bound to order "
                    f"{existing_event['order_id']} / proposal "
                    f"{existing_event['proposal_id']}."
                )

            submitted_at = str(order.get("submitted_at") or event_at)
            # The order row must exist before the event insert now that
            # broker_order_events has a real foreign key. Insert a missing
            # row first, but do not update an existing row until we know this
            # event is new: replaying an old event must not regress the latest
            # broker-order projection. Duplicate events can still repair an
            # old database that contains an event but lacks its order row.
            connection.execute(
                """
                INSERT INTO broker_orders(
                    order_id, proposal_id, submitted_at, status, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO NOTHING
                """,
                (
                    order_id,
                    proposal_id,
                    submitted_at,
                    str(order.get("status", "unknown")),
                    json.dumps(order, sort_keys=True, default=str),
                ),
            )
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
                    order_id,
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

            effective_updates = dict(proposal_updates)
            for field in preserve_if_set:
                if proposal.get(field):
                    effective_updates.pop(field, None)
            proposal.update(effective_updates)
            proposal["status"] = new_proposal_status
            connection.execute(
                """
                UPDATE broker_orders
                SET proposal_id = ?, status = ?, payload_json = ?
                WHERE order_id = ?
                """,
                (
                    proposal_id,
                    str(order.get("status", "unknown")),
                    json.dumps(order, sort_keys=True, default=str),
                    order_id,
                ),
            )
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

    def append_execution_telemetry_event(
        self,
        *,
        attempt_id: str,
        proposal_id: str,
        event_type: str,
        event_at: str,
        account_mode: str,
        source: str,
        payload: dict[str, Any],
        broker_account_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one immutable, analysis-oriented execution event.

        The broker event journal remains authoritative after submission. This
        journal deliberately captures only evidence that otherwise disappears
        before a broker order exists (validation/quote context and submission
        start). Its content-derived key makes exact retries idempotent.
        """
        text_fields = {
            "attempt_id": attempt_id,
            "proposal_id": proposal_id,
            "event_type": event_type,
            "source": source,
        }
        normalized: dict[str, str] = {}
        for name, value in text_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            normalized[name] = value.strip()
        if account_mode not in {"paper", "live", "unavailable"}:
            raise ValueError("account_mode must be paper, live, or unavailable")
        if broker_account_id is not None:
            if not isinstance(broker_account_id, str) or not broker_account_id.strip():
                raise ValueError("broker_account_id must be null or a non-empty string")
            broker_account_id = broker_account_id.strip()
        if order_id is not None:
            if not isinstance(order_id, str) or not order_id.strip():
                raise ValueError("order_id must be null or a non-empty string")
            order_id = order_id.strip()
        timestamp = _parse_aware_timestamp(event_at, "event_at").isoformat()
        payload_json = _canonical_ml_json(payload, "execution telemetry payload")
        payload_hash = _hash_payload(payload_json)
        event_material = _canonical_ml_json(
            {
                **normalized,
                "event_at": timestamp,
                "account_mode": account_mode,
                "broker_account_id": broker_account_id,
                "order_id": order_id,
                "payload_hash": payload_hash,
            },
            "execution telemetry event",
        )
        telemetry_event_id = "exec-tel-" + _hash_payload(event_material)[:32]
        values = (
            telemetry_event_id,
            normalized["attempt_id"],
            normalized["proposal_id"],
            order_id,
            normalized["event_type"],
            timestamp,
            account_mode,
            broker_account_id,
            normalized["source"],
            payload_json,
            payload_hash,
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO execution_telemetry_events(
                    telemetry_event_id, attempt_id, proposal_id, order_id,
                    event_type, event_at, account_mode, broker_account_id,
                    source, payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telemetry_event_id) DO NOTHING
                """,
                values,
            )
            row = connection.execute(
                "SELECT * FROM execution_telemetry_events "
                "WHERE telemetry_event_id = ?",
                (telemetry_event_id,),
            ).fetchone()
        if row is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("execution telemetry insert did not persist")
        return {
            "telemetry_event_id": row["telemetry_event_id"],
            "attempt_id": row["attempt_id"],
            "proposal_id": row["proposal_id"],
            "order_id": row["order_id"],
            "event_type": row["event_type"],
            "event_at": row["event_at"],
            "account_mode": row["account_mode"],
            "broker_account_id": row["broker_account_id"],
            "source": row["source"],
            "payload": json.loads(row["payload_json"]),
            "payload_hash": row["payload_hash"],
            "inserted": cursor.rowcount == 1,
        }

    def list_execution_telemetry_events(
        self,
        *,
        attempt_id: str | None = None,
        proposal_id: str | None = None,
        order_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        query = "SELECT * FROM execution_telemetry_events"
        params: list[Any] = []
        clauses: list[str] = []
        for column, value in (
            ("attempt_id", attempt_id),
            ("proposal_id", proposal_id),
            ("order_id", order_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY event_at ASC, rowid ASC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "telemetry_event_id": row["telemetry_event_id"],
                "attempt_id": row["attempt_id"],
                "proposal_id": row["proposal_id"],
                "order_id": row["order_id"],
                "event_type": row["event_type"],
                "event_at": row["event_at"],
                "account_mode": row["account_mode"],
                "broker_account_id": row["broker_account_id"],
                "source": row["source"],
                "payload": json.loads(row["payload_json"]),
                "payload_hash": row["payload_hash"],
            }
            for row in rows
        ]

    def reserve_execution_budget(
        self,
        proposal_id: str,
        *,
        trading_day: str,
        notional: Decimal | int | float | str,
        max_daily_notional: Decimal | int | float | str,
        max_daily_orders: int,
    ) -> dict[str, Any]:
        """Atomically reserve one submission against persistent daily caps.

        These are gross *submission* counters, not open-exposure counters.
        A broker-observed rejected order therefore continues consuming both
        caps: it reached the broker and must not be retried indefinitely by
        repeatedly releasing the reservation. Only confirmed non-submission
        is released through mark_submission_failed_and_release().
        """
        notional_decimal = to_decimal(notional, name="notional")
        max_daily_notional_decimal = to_decimal(
            max_daily_notional, name="max_daily_notional"
        )
        if notional_decimal <= 0:
            raise ValueError(f"notional must be positive and finite, got {notional!r}.")
        if max_daily_notional_decimal <= 0:
            raise ValueError("max_daily_notional must be positive and finite.")
        if isinstance(max_daily_orders, bool) or not isinstance(max_daily_orders, int) or max_daily_orders <= 0:
            raise ValueError("max_daily_orders must be a positive integer.")
        now = datetime.now(timezone.utc).isoformat()
        connection = self._open_database(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM execution_reservations WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if existing is not None:
                existing_exact = to_decimal(
                    existing["reserved_notional_text"]
                    if existing["reserved_notional_text"]
                    else existing["reserved_notional"],
                    name="stored reserved_notional",
                )
                connection.commit()
                return {
                    "proposal_id": proposal_id,
                    "trading_day": existing["trading_day"],
                    "reserved_notional": float(existing_exact),
                    "reserved_notional_decimal": decimal_text(existing_exact),
                    "already_reserved": True,
                }
            reservations = connection.execute(
                "SELECT reserved_notional, reserved_notional_text "
                "FROM execution_reservations WHERE trading_day = ?",
                (trading_day,),
            ).fetchall()
            reserved_total = sum(
                (
                    to_decimal(
                        row["reserved_notional_text"]
                        if row["reserved_notional_text"]
                        else row["reserved_notional"],
                        name="stored reserved_notional",
                    )
                    for row in reservations
                ),
                Decimal("0"),
            )
            next_count = len(reservations) + 1
            next_notional = reserved_total + notional_decimal
            if next_count > max_daily_orders:
                raise ValueError(
                    f"Daily order-count budget would be {next_count}, exceeding {max_daily_orders}."
                )
            if next_notional > max_daily_notional_decimal:
                raise ValueError(
                    f"Daily submitted notional would be ${next_notional:,.2f}, "
                    f"exceeding ${max_daily_notional_decimal:,.2f}."
                )
            connection.execute(
                "INSERT INTO execution_reservations("
                "proposal_id, trading_day, reserved_notional, "
                "reserved_notional_text, created_at"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    proposal_id,
                    trading_day,
                    float(notional_decimal),
                    decimal_text(notional_decimal),
                    now,
                ),
            )
            connection.commit()
            return {
                "proposal_id": proposal_id,
                "trading_day": trading_day,
                "reserved_notional": float(notional_decimal),
                "reserved_notional_decimal": decimal_text(notional_decimal),
                "daily_order_count": next_count,
                "daily_reserved_notional": float(next_notional),
                "daily_reserved_notional_decimal": decimal_text(next_notional),
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
            reservations = connection.execute(
                "SELECT reserved_notional, reserved_notional_text "
                "FROM execution_reservations WHERE trading_day = ?",
                (trading_day,),
            ).fetchall()
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

        submitted_notional = sum(
            (
                to_decimal(
                    row["reserved_notional_text"]
                    if row["reserved_notional_text"]
                    else row["reserved_notional"],
                    name="stored reserved_notional",
                )
                for row in reservations
            ),
            Decimal("0"),
        )
        filled_notional = Decimal("0")
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
                filled_notional += abs(
                    to_decimal(row["fill_qty"], name="fill_qty")
                    * to_decimal(row["fill_price"], name="fill_price")
                )
            except ValueError:
                continue

        return {
            "trading_day": trading_day,
            "submitted_order_count": len(reservations),
            "submitted_notional": float(submitted_notional),
            "submitted_notional_decimal": decimal_text(submitted_notional),
            "filled_notional": float(filled_notional),
            "filled_notional_decimal": decimal_text(filled_notional),
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
        connection = self._open_database(self.path)
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

    def activate_reconciliation_halt(
        self,
        *,
        proposal_id: str,
        reason: str,
        seen_at: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically persist a reconciliation kill switch and critical alert.

        A broker identity anomaly is not merely a local exception: operators
        and the later GR-5 delivery channel need a durable critical alert.
        Writing the alert and halt in one transaction prevents either record
        from claiming the other safety action occurred when it did not.
        """
        now = seen_at or datetime.now(timezone.utc).isoformat()
        fingerprint = f"broker_reconciliation:{proposal_id}"
        alert_details = {"proposal_id": proposal_id, **(details or {})}
        kill_switch = {
            "active": True,
            "reason": reason,
            "changed_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO system_state(state_key, value_json, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(state_key) DO UPDATE SET "
                "value_json = excluded.value_json, updated_at = excluded.updated_at",
                ("kill_switch", json.dumps(kill_switch, sort_keys=True), now),
            )
            connection.execute(
                """
                INSERT INTO operational_alerts(
                    fingerprint, severity, category, message, details_json,
                    status, occurrences, first_seen_at, last_seen_at,
                    acknowledged_at
                ) VALUES (?, 'critical', 'broker_reconciliation', ?, ?,
                          'open', 1, ?, ?, NULL)
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
                    reason,
                    json.dumps(alert_details, sort_keys=True, default=str),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM operational_alerts WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return self._operational_alert_row(row)

    def get_kill_switch(self) -> dict[str, Any]:
        value = self.get_system_state("kill_switch", default={"active": False, "reason": ""})
        return value if isinstance(value, dict) else {"active": bool(value), "reason": ""}

    def database_integrity_check(self) -> list[str]:
        with self._connect() as connection:
            return self._integrity_results(connection)

    @staticmethod
    def _integrity_results(
        connection: sqlite3.Connection,
    ) -> list[str]:
        """Check SQLite pages plus referential integrity.

        ``PRAGMA integrity_check`` does not include foreign-key validation.
        Explicit relationship queries also cover databases created before
        these broker tables acquired declared foreign keys.
        """
        page_results = [
            str(row[0])
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]
        if page_results != ["ok"]:
            return page_results

        violations = [
            (
                "broker_orders.proposal_id",
                """
                SELECT COUNT(*)
                FROM broker_orders AS child
                LEFT JOIN trade_proposals AS parent
                  ON parent.proposal_id = child.proposal_id
                WHERE parent.proposal_id IS NULL
                """,
            ),
            (
                "broker_order_events.order_id",
                """
                SELECT COUNT(*)
                FROM broker_order_events AS child
                LEFT JOIN broker_orders AS parent
                  ON parent.order_id = child.order_id
                WHERE parent.order_id IS NULL
                """,
            ),
            (
                "broker_order_events.proposal_id",
                """
                SELECT COUNT(*)
                FROM broker_order_events AS child
                LEFT JOIN trade_proposals AS parent
                  ON parent.proposal_id = child.proposal_id
                WHERE parent.proposal_id IS NULL
                """,
            ),
            (
                "execution_reservations.proposal_id",
                """
                SELECT COUNT(*)
                FROM execution_reservations AS child
                LEFT JOIN trade_proposals AS parent
                  ON parent.proposal_id = child.proposal_id
                WHERE parent.proposal_id IS NULL
                """,
            ),
        ]
        results: list[str] = []
        for relationship, query in violations:
            count = int(connection.execute(query).fetchone()[0])
            if count:
                results.append(
                    f"foreign-key violation: {relationship} has "
                    f"{count} orphan row(s)"
                )
        for row in connection.execute("PRAGMA foreign_key_check").fetchall():
            detail = (
                f"foreign-key violation: table={row[0]} rowid={row[1]} "
                f"parent={row[2]} constraint={row[3]}"
            )
            if detail not in results:
                results.append(detail)
        return results or ["ok"]

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("Backup destination must be different from the live database path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source_connection = self._open_database(self.path)
        destination_connection = self._open_database(target)
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
        connection = AssistantStore._open_database(path)
        try:
            return AssistantStore._integrity_results(connection)
        finally:
            connection.close()

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
        connection = self._open_database(self.path)
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

    def record_alert_delivery(
        self,
        *,
        fingerprint: str,
        alert_id: int | None,
        channel: str,
        severity: str,
        outcome: str,
        occurrences_at_attempt: int,
        detail: str = "",
        attempted_at: str | None = None,
        delivered_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one immutable delivery attempt record (GR-5).

        Never an upsert: a later success must not erase an earlier failure,
        because "this critical alert took three attempts" and "this critical
        alert was never delivered" are exactly the facts the operator and the
        undelivered-critical health check need.
        """
        if outcome not in ("delivered", "failed", "suppressed"):
            raise ValueError(
                f"outcome must be delivered/failed/suppressed, got {outcome!r}"
            )
        attempted = attempted_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alert_deliveries(
                    fingerprint, alert_id, channel, severity, outcome,
                    attempted_at, delivered_at, occurrences_at_attempt, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    alert_id,
                    channel,
                    severity,
                    outcome,
                    attempted,
                    delivered_at if outcome == "delivered" else None,
                    int(occurrences_at_attempt),
                    detail,
                ),
            )
            row = connection.execute(
                "SELECT * FROM alert_deliveries WHERE delivery_id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._alert_delivery_row(row)

    def list_alert_deliveries(
        self,
        *,
        fingerprint: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if fingerprint is not None:
            clauses.append("fingerprint = ?")
            params.append(fingerprint)
        if outcome is not None:
            clauses.append("outcome = ?")
            params.append(outcome)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM alert_deliveries {where} "
                "ORDER BY attempted_at DESC, delivery_id DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._alert_delivery_row(row) for row in rows]

    def latest_successful_delivery(
        self, fingerprint: str, *, min_occurrences: int | None = None
    ) -> dict[str, Any] | None:
        """The most recent DELIVERED attempt for a fingerprint.

        ``min_occurrences`` asks "was the alert delivered at or after this
        occurrence count", which is how re-delivery of a recurring alert is
        decided without re-notifying on every sweep.
        """
        clause = "AND occurrences_at_attempt >= ?" if min_occurrences is not None else ""
        params: list[Any] = [fingerprint]
        if min_occurrences is not None:
            params.append(int(min_occurrences))
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM alert_deliveries WHERE fingerprint = ? "
                f"AND outcome = 'delivered' {clause} "
                "ORDER BY attempted_at DESC, delivery_id DESC LIMIT 1",
                params,
            ).fetchone()
        return self._alert_delivery_row(row) if row is not None else None

    @staticmethod
    def _alert_delivery_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "delivery_id": row["delivery_id"],
            "fingerprint": row["fingerprint"],
            "alert_id": row["alert_id"],
            "channel": row["channel"],
            "severity": row["severity"],
            "outcome": row["outcome"],
            "attempted_at": row["attempted_at"],
            "delivered_at": row["delivered_at"],
            "occurrences_at_attempt": row["occurrences_at_attempt"],
            "detail": row["detail"],
        }

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
        connection = self._open_database(self.path)
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
        connection = self._open_database(self.path)
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
                    net_external_flow, total_equity_text, cash_text,
                    benchmark_close_text, net_external_flow_text,
                    payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    decimal_text(
                        to_decimal(observation["total_equity"], name="total_equity")
                    ),
                    decimal_text(to_decimal(observation["cash"], name="cash")),
                    decimal_text(
                        to_decimal(
                            observation["benchmark_close"], name="benchmark_close"
                        )
                    ),
                    decimal_text(
                        to_decimal(
                            observation["net_external_flow"],
                            name="net_external_flow",
                        )
                    ),
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

    def update_allocation_batch(
        self,
        batch_id: str,
        status: str | None = None,
        *,
        expected_legs: dict[str, dict] | None = None,
        **updates: Any,
    ) -> dict[str, Any]:
        # Independent review, 2026-07-31: this used to be a plain
        # read-then-write with no BEGIN IMMEDIATE/conditional-UPDATE guard,
        # unlike every other proposal-mutating method in this file. Two
        # concurrent callers (e.g. two overlapping execute_allocation_batch()
        # invocations for the same batch_id) could each read the batch, merge
        # their own leg update on top, and write back -- last writer wins,
        # silently discarding an earlier writer's correct leg result.
        # Read-modify-write inside a single BEGIN IMMEDIATE transaction, same
        # pattern as project_broker_order_event() above.
        now = datetime.now(timezone.utc).isoformat()
        connection = self._open_database(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json, status FROM allocation_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown batch_id: {batch_id}")
            batch = json.loads(row["payload_json"])
            batch["status"] = row["status"]
            # `legs` is a nested, independently-mutated projection.  Merely
            # serializing this read/modify/write is not sufficient if a caller
            # carries a stale whole-batch snapshot: replacing the mapping can
            # still discard another worker's already-committed leg.  Treat
            # supplied legs as a per-proposal patch and merge them into the
            # freshly-read row while the write lock is held.
            incoming_legs = updates.pop("legs", None)
            if incoming_legs is not None:
                if not isinstance(incoming_legs, dict):
                    raise TypeError("allocation batch legs must be a mapping")
                current_legs = dict(batch.get("legs") or {})
                if expected_legs is not None and any(
                    current_legs.get(str(proposal_id)) != expected_leg
                    for proposal_id, expected_leg in expected_legs.items()
                ):
                    # A same-leg writer committed after the caller took its
                    # snapshot. Return the fresh row without applying the
                    # stale patch; the caller can re-project from the
                    # authoritative proposal and retry.
                    connection.rollback()
                    return batch
                merged_legs = current_legs
                merged_legs.update(
                    {
                        str(proposal_id): dict(leg)
                        for proposal_id, leg in incoming_legs.items()
                    }
                )
                batch["legs"] = merged_legs
            batch.update(updates)
            if status is not None:
                batch["status"] = status
            if incoming_legs is not None or status is not None:
                # Keep the materialized batch status consistent with the
                # freshly locked leg mapping. This also prevents a worker
                # that calculated `completed` from a stale pre-lock snapshot
                # from publishing that status over a newly-unknown leg.
                leg_states = {
                    str(leg.get("state"))
                    for leg in (batch.get("legs") or {}).values()
                }
                terminal_states = {
                    "submitted",
                    "failed",
                    "blocked_overridable",
                }
                if "unknown" in leg_states:
                    batch["status"] = "stopped_unknown"
                elif leg_states and leg_states <= terminal_states:
                    batch["status"] = "completed"
                elif batch["status"] in {"completed", "stopped_unknown"}:
                    batch["status"] = "stopped"
            connection.execute(
                "UPDATE allocation_batches SET status = ?, payload_json = ?, updated_at = ? WHERE batch_id = ?",
                (batch["status"], json.dumps(batch, sort_keys=True), now, batch_id),
            )
            connection.commit()
            return batch
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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


# --- Schema verification (AP-1, ACTION_PLAN 2026-08-02) --------------------
#
# AssistantStore.__init__ applies the declared schema idempotently
# (CREATE ... IF NOT EXISTS plus column-presence-guarded migrations), so a
# database is brought current by simply opening it with current code. What
# opening cannot do is PROVE the result: an operator database written by
# older code silently lacks newer tables until something checks. These
# helpers compare a database's actual schema objects against the schema the
# current code creates, read-only and fail-closed.


@dataclass(frozen=True)
class SchemaVerificationResult:
    """Outcome of comparing a database against the currently declared schema.

    ``matches`` is True only when every declared table and column exists and
    every declared index and trigger exists with the definition produced by
    current code. Index and trigger definitions are enforcement mechanisms,
    not labels: a same-named non-unique index or no-op trigger must fail the
    check. ``extra_tables`` is informational only: legacy or operator-local
    tables never fail verification, because the contract is "current code's
    compatible schema is present", not "nothing else is".
    """

    matches: bool
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]
    missing_indexes: tuple[str, ...]
    missing_triggers: tuple[str, ...]
    mismatched_indexes: tuple[str, ...]
    mismatched_triggers: tuple[str, ...]
    extra_tables: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "missing_tables": list(self.missing_tables),
            "missing_columns": list(self.missing_columns),
            "missing_indexes": list(self.missing_indexes),
            "missing_triggers": list(self.missing_triggers),
            "mismatched_indexes": list(self.mismatched_indexes),
            "mismatched_triggers": list(self.mismatched_triggers),
            "extra_tables": list(self.extra_tables),
        }


def _normalize_schema_sql(sql: str) -> str:
    """Ignore formatting-only whitespace in one declared schema object."""
    return " ".join(sql.split())


def _schema_objects(
    connection: sqlite3.Connection,
) -> tuple[dict[str, set[str]], dict[str, str], dict[str, str]]:
    """Read tables/columns and enforcement-object definitions.

    SQLite-internal objects (``sqlite_*`` tables, ``sqlite_autoindex*``
    implicit indexes) are excluded: they are storage details rather than
    independently declared schema objects. Named index and trigger SQL is
    retained so verification cannot be fooled by a weaker object reusing the
    expected name.
    """
    tables: dict[str, set[str]] = {}
    for row in connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        name = row["name"]
        tables[name] = {
            column["name"]
            for column in connection.execute(f'PRAGMA table_info("{name}")')
        }
    indexes = {
        row["name"]: _normalize_schema_sql(row["sql"])
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex%'"
        ).fetchall()
    }
    triggers = {
        row["name"]: _normalize_schema_sql(row["sql"])
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
    }
    return tables, indexes, triggers


def verify_database_schema(path: str | Path) -> SchemaVerificationResult:
    """Compare the database at ``path`` against the current declared schema.

    Read-only: the target is opened with SQLite's ``mode=ro`` and is never
    created, migrated, or written. Fail-closed: a missing database file
    raises ``FileNotFoundError`` and an unreadable one propagates its
    ``sqlite3`` error -- neither is reported as a match.

    The expected schema is not a hand-maintained list (which would drift):
    it is read from a throwaway reference database built by the exact
    production initialization path, so whatever ``AssistantStore`` creates
    today is by construction what this function requires.
    """
    target_path = Path(path)
    if not target_path.exists():
        raise FileNotFoundError(
            f"Cannot verify schema: database does not exist at {target_path}"
        )
    with tempfile.TemporaryDirectory(prefix="schema-reference-") as reference_dir:
        reference = AssistantStore(Path(reference_dir) / "schema_reference.db")
        reference_connection = AssistantStore._open_database(reference.path)
        try:
            expected_tables, expected_indexes, expected_triggers = _schema_objects(
                reference_connection
            )
        finally:
            reference_connection.close()
    target_connection = sqlite3.connect(
        target_path.resolve().as_uri() + "?mode=ro", uri=True
    )
    target_connection.row_factory = sqlite3.Row
    try:
        actual_tables, actual_indexes, actual_triggers = _schema_objects(
            target_connection
        )
    finally:
        target_connection.close()

    missing_tables = sorted(set(expected_tables) - set(actual_tables))
    missing_columns = sorted(
        f"{table}.{column}"
        for table, expected_columns in expected_tables.items()
        if table in actual_tables
        for column in expected_columns - actual_tables[table]
    )
    missing_indexes = sorted(set(expected_indexes) - set(actual_indexes))
    missing_triggers = sorted(set(expected_triggers) - set(actual_triggers))
    mismatched_indexes = sorted(
        name
        for name in set(expected_indexes) & set(actual_indexes)
        if expected_indexes[name] != actual_indexes[name]
    )
    mismatched_triggers = sorted(
        name
        for name in set(expected_triggers) & set(actual_triggers)
        if expected_triggers[name] != actual_triggers[name]
    )
    extra_tables = sorted(set(actual_tables) - set(expected_tables))
    return SchemaVerificationResult(
        matches=not (
            missing_tables
            or missing_columns
            or missing_indexes
            or missing_triggers
            or mismatched_indexes
            or mismatched_triggers
        ),
        missing_tables=tuple(missing_tables),
        missing_columns=tuple(missing_columns),
        missing_indexes=tuple(missing_indexes),
        missing_triggers=tuple(missing_triggers),
        mismatched_indexes=tuple(mismatched_indexes),
        mismatched_triggers=tuple(mismatched_triggers),
        extra_tables=tuple(extra_tables),
    )
