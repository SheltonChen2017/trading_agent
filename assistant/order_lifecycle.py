"""Broker-order normalization and proposal lifecycle mapping.

The broker accepting an order request is materially different from the
order filling. This module is the one place that converts broker status
strings into the proposal states used by the rest of the assistant.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from assistant.proposal_status import (
    APPROVED,
    BROKER_ACCEPTED,
    BROKER_EXPIRED,
    BROKER_REJECTED,
    CANCELED,
    CANCEL_PENDING,
    FILLED,
    PARTIALLY_FILLED,
    RECONCILING,
    SUBMISSION_FAILED,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    EXECUTED,
)

if TYPE_CHECKING:
    from assistant.storage import AssistantStore


_ACCEPTED = {
    "accepted",
    "accepted_for_bidding",
    "calculated",
    "held",
    "new",
    "pending_new",
    "stopped",
    "suspended",
}
_PARTIAL = {"partially_filled"}
_CANCEL_PENDING = {"pending_cancel", "pending_replace", "replaced"}
_FILLED = {"filled"}
_CANCELED = {"canceled"}
_REJECTED = {"rejected"}
_EXPIRED = {"done_for_day", "expired"}

_PRE_BROKER = (
    APPROVED,
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    SUBMISSION_FAILED,
    EXECUTED,
)


def _expected_current_statuses(new_status: str) -> tuple[str, ...]:
    if new_status == BROKER_ACCEPTED:
        return _PRE_BROKER + (BROKER_ACCEPTED,)
    if new_status == PARTIALLY_FILLED:
        return _PRE_BROKER + (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING)
    if new_status == CANCEL_PENDING:
        return _PRE_BROKER + (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING)
    if new_status == FILLED:
        return _PRE_BROKER + (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING, FILLED)
    if new_status == CANCELED:
        return _PRE_BROKER + (BROKER_ACCEPTED, PARTIALLY_FILLED, CANCEL_PENDING, CANCELED)
    if new_status == BROKER_REJECTED:
        return _PRE_BROKER + (
            BROKER_ACCEPTED,
            PARTIALLY_FILLED,
            CANCEL_PENDING,
            BROKER_REJECTED,
        )
    if new_status == BROKER_EXPIRED:
        return _PRE_BROKER + (
            BROKER_ACCEPTED,
            PARTIALLY_FILLED,
            CANCEL_PENDING,
            BROKER_EXPIRED,
        )
    return _PRE_BROKER


def normalize_broker_status(value: Any) -> str:
    """Return a stable lowercase broker status.

    alpaca-py enum values normally expose ``.value``; older call sites and
    tests sometimes persist ``str(enum)`` (for example
    ``"OrderStatus.ACCEPTED"``), so the final dotted component is used.
    """
    raw = getattr(value, "value", value)
    text = str(raw or "unknown").strip().lower()
    return text.rsplit(".", 1)[-1]


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def proposal_status_for_order(order: dict[str, Any]) -> str:
    status = normalize_broker_status(order.get("status"))
    if status in _FILLED:
        return FILLED
    if status in _PARTIAL:
        return PARTIALLY_FILLED
    if status in _CANCEL_PENDING:
        return CANCEL_PENDING
    if status in _CANCELED:
        return CANCELED
    if status in _REJECTED:
        return BROKER_REJECTED
    if status in _EXPIRED:
        return BROKER_EXPIRED
    if status in _ACCEPTED:
        return BROKER_ACCEPTED

    filled_qty = _finite_float(order.get("filled_qty")) or 0.0
    requested_qty = _finite_float(order.get("shares"))
    if requested_qty is not None and filled_qty >= requested_qty > 0:
        return FILLED
    if filled_qty > 0:
        return PARTIALLY_FILLED
    # Unknown nonterminal statuses fail conservatively: keep reserving the
    # exposure and require reconciliation rather than declaring a failure.
    return BROKER_ACCEPTED


def broker_event_id(
    order: dict[str, Any],
    *,
    event_type: str | None = None,
    event_at: str | None = None,
    external_event_id: str | None = None,
) -> str:
    """Stable event identity for stream replay and polling deduplication."""
    if external_event_id:
        return str(external_event_id)
    material = {
        "order_id": order.get("order_id"),
        "client_order_id": order.get("client_order_id"),
        "event_type": event_type or normalize_broker_status(order.get("status")),
        "event_at": event_at or order.get("updated_at") or order.get("filled_at"),
        "status": normalize_broker_status(order.get("status")),
        "filled_qty": order.get("filled_qty"),
        "filled_avg_price": order.get("filled_avg_price"),
    }
    encoded = json.dumps(material, sort_keys=True, default=str)
    return "boe_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalized_event_at(order: dict[str, Any], event_at: str | None = None) -> str:
    return str(
        event_at
        or order.get("updated_at")
        or order.get("filled_at")
        or datetime.now(timezone.utc).isoformat()
    )


def journal_broker_order_update(
    store: "AssistantStore",
    proposal_id: str,
    order: dict[str, Any],
    *,
    event_type: str | None = None,
    event_at: str | None = None,
    external_event_id: str | None = None,
    fill_qty: float | None = None,
    fill_price: float | None = None,
    raw_event: dict[str, Any] | None = None,
    clear_error: bool = False,
    extra_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one broker update and project it onto the proposal state."""
    proposal_status = proposal_status_for_order(order)
    normalized_at = normalized_event_at(order, event_at)
    event_id = broker_event_id(
        order,
        event_type=event_type,
        event_at=event_at,
        external_event_id=external_event_id,
    )
    updates: dict[str, Any] = {
        "broker_order": order,
        "broker_status": normalize_broker_status(order.get("status")),
        "last_broker_event_at": normalized_at,
    }
    if clear_error:
        updates["error"] = None
    if proposal_status == BROKER_ACCEPTED:
        current = store.get_proposal(proposal_id) or {}
        updates["broker_accepted_at"] = str(
            current.get("broker_accepted_at")
            or order.get("submitted_at")
            or normalized_at
        )
    elif proposal_status == PARTIALLY_FILLED:
        updates["partially_filled_at"] = normalized_at
    elif proposal_status == FILLED:
        updates["filled_at"] = str(order.get("filled_at") or normalized_at)
        # Preserve the former audit field for downstream readers while its
        # semantics are migrated from "submitted" to genuine execution.
        updates["executed_at"] = updates["filled_at"]
    elif proposal_status in (CANCELED, BROKER_REJECTED, BROKER_EXPIRED):
        updates["broker_terminal_at"] = normalized_at
    updates.update(extra_updates or {})
    return store.project_broker_order_event(
        event_id=event_id,
        proposal_id=proposal_id,
        order=order,
        event_type=event_type or normalize_broker_status(order.get("status")),
        event_at=normalized_at,
        new_proposal_status=proposal_status,
        expected_current_statuses=_expected_current_statuses(proposal_status),
        proposal_updates=updates,
        fill_qty=fill_qty,
        fill_price=fill_price,
        raw_event=raw_event,
    )
