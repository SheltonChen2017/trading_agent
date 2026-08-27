"""Broker order reconciliation via startup polling and trade-update stream."""
from __future__ import annotations

import inspect
import hashlib
import time
from collections.abc import Mapping
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any
from uuid import UUID

from assistant.execution_kernel.broker_evidence import (
    assert_expected_broker_account,
    canonical_order_for_proposal,
    observed_broker_account,
)
from assistant.execution_service import (
    ProposalExecutionError,
    _intent_from_dict,
    _order_matches_intent,
)
from assistant.dispatch_fence import (
    _latch_runtime_emergency_stop_failure,
    activate_runtime_emergency_stop,
    execution_dispatch_fence,
    get_runtime_emergency_stop,
    list_runtime_dispatch_attempts,
)
from assistant.order_lifecycle import (
    CHAIN_ERROR_IDENTITY_MISMATCH,
    CHAIN_ERROR_UNRESOLVED,
    ReplacementResolution,
    is_replaced_order,
    journal_broker_order_update,
    resolve_replacement_chain,
)
from assistant.proposal_status import (
    BROKER_ABSENCE_GRACE_SECONDS,
    BROKER_ACCEPTED,
    CANCEL_PENDING,
    EXECUTED,
    PARTIALLY_FILLED,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    UNRESOLVED_BROKER_STATE_STATUSES,
)
from assistant.storage import AssistantStore
from assistant.temporal_integrity import (
    MAX_ABSENCE_AGE_SECONDS as _MAX_ABSENCE_AGE_SECONDS,
    MAX_MONITOR_INTERVAL_SECONDS as _MAX_MONITOR_INTERVAL_SECONDS,
    MAX_ORDER_AGE_MINUTES as _MAX_ORDER_AGE_MINUTES,
    bounded_timing_number,
    timestamp_disposition,
)

_STREAM_SHUTDOWN_POLL_SECONDS = 0.1

# How long a proposal must have sat in a pre-broker/unresolved status before a
# "no such order" lookup is treated as PROOF the order never reached the
# broker. Must comfortably exceed one submit round trip (broker account/asset
# preflight + submit + the broker's own order-indexing latency). See
# _absence_is_believable() for why believing it too early is harmful.
MIN_ABSENCE_AGE_SECONDS = BROKER_ABSENCE_GRACE_SECONDS
_CANCEL_ALL_MAX_BOOK_SCANS = 5
_CANCEL_ALL_REQUIRED_STABLE_SCANS = 3
_CANCEL_ALL_SCAN_INTERVAL_SECONDS = 0.05


def _enter_best_effort_emergency_fence(
    database,
) -> tuple[ExitStack, Exception | None]:
    """Acquire the drain fence without making its failure block cancellation."""
    stack = ExitStack()
    try:
        stack.enter_context(execution_dispatch_fence(database))
    except Exception as exc:
        return stack, exc
    return stack, None


def _record_cancel_all_incomplete(
    store: AssistantStore,
    *,
    reason: str,
    seen_at: str,
    details: dict[str, Any],
    fence_acquired: bool,
) -> None:
    """Persist a critical disposition without retrying a broken fence."""
    if fence_acquired:
        store.activate_reconciliation_halt(
            proposal_id="emergency-cancel-all",
            reason=reason,
            seen_at=seen_at,
            details=details,
        )
        return
    store.upsert_operational_alert(
        fingerprint="emergency_cancel_all:incomplete",
        severity="critical",
        category="broker_reconciliation",
        message=reason,
        details={"proposal_id": "emergency-cancel-all", **details},
        seen_at=seen_at,
    )


def _bounded_timing_number(
    name: str,
    value: Any,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
) -> float:
    """Validate an interval before any broker, database, or thread contact."""
    return bounded_timing_number(
        name,
        value,
        minimum=minimum,
        maximum=maximum,
        minimum_inclusive=minimum_inclusive,
    )


def _aware_utc_now(value: datetime | None, *, name: str = "now") -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a timezone-aware datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _account_scoped_broker(broker_provider: Any) -> Any:
    """Return one frozen session for all reads in a reconciliation pass."""
    opener = getattr(broker_provider, "open_alpaca_broker_session", None)
    if callable(opener):
        return opener()
    if (
        getattr(broker_provider, "account_mode", None) in {"paper", "live"}
        and callable(getattr(broker_provider, "get_account", None))
    ):
        return broker_provider
    raise ProposalExecutionError(
        "Order reconciliation requires an account-scoped broker session."
    )


def _emergency_order_mapping(order: Any) -> dict[str, Any]:
    """Extract cancellation identity without requiring attribution evidence."""
    if isinstance(order, Mapping):
        return dict(order)
    normalized: dict[str, Any] = {}
    for target, candidates in (
        ("order_id", ("order_id", "id")),
        ("client_order_id", ("client_order_id",)),
        ("ticker", ("ticker", "symbol")),
    ):
        for candidate in candidates:
            value = getattr(order, candidate, None)
            if value is not None:
                normalized[target] = value
                break
    return normalized


def _emergency_order_id(order: Any) -> tuple[str | None, dict[str, Any]]:
    normalized = _emergency_order_mapping(order)
    raw = normalized.get("order_id")
    if isinstance(raw, UUID):
        return str(raw), normalized
    if not isinstance(raw, str):
        return None, normalized
    if (
        not raw
        or raw != raw.strip()
        or raw.lower() in {"none", "null", "unknown"}
    ):
        return None, normalized
    return raw, normalized


def _resolve_chain_for(
    proposal: dict[str, Any],
    order: dict[str, Any],
    broker_module: Any,
    *,
    observed_account,
) -> ReplacementResolution:
    """Resolve `order`'s replacement chain, validating every hop against this
    proposal's stored intent.

    Thin adapter over order_lifecycle.resolve_replacement_chain(): it supplies
    the broker lookup and injects `_order_matches_intent` as the per-hop
    validator (the resolver cannot import that itself without a circular
    dependency). A malformed stored intent yields an unresolved result rather
    than an exception, so the caller records it and moves on to the next
    proposal instead of aborting the whole reconciliation pass.
    """
    try:
        intent = _intent_from_dict(proposal["intent"])
    except Exception as exc:
        return ReplacementResolution(
            None, (), (),
            f"stored intent could not be parsed for replacement validation: {exc}",
            CHAIN_ERROR_UNRESOLVED,
        )
    try:
        root_order = canonical_order_for_proposal(
            order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=True,
        )
    except Exception as exc:
        raw_root_order_id = order.get("order_id")
        return ReplacementResolution(
            None,
            (),
            (),
            f"root broker order failed strict validation: {exc}",
            CHAIN_ERROR_IDENTITY_MISMATCH,
            (
                raw_root_order_id
                if isinstance(raw_root_order_id, str) and raw_root_order_id
                else None
            ),
        )
    resolution = resolve_replacement_chain(
        root_order,
        # Lazy: resolving broker_module.get_order_by_id EAGERLY made every
        # broker/fake without that method raise AttributeError even for orders
        # that were never replaced (it broke a pre-existing poll test). Now the
        # attribute is only touched when a hop is genuinely fetched, and a
        # missing method surfaces as an unresolved chain rather than a crash.
        lambda oid: broker_module.get_order_by_id(oid),
        validate=lambda candidate: _order_matches_intent(
            candidate,
            intent,
            proposal=proposal,
            observed_account=observed_account,
            root_order=False,
        ),
    )
    if resolution.error is not None:
        return resolution
    assert resolution.authoritative_order is not None
    try:
        authoritative = canonical_order_for_proposal(
            resolution.authoritative_order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=not resolution.followed_a_replacement,
        )
    except Exception as exc:
        return ReplacementResolution(
            None,
            resolution.traversed_orders,
            resolution.chain,
            f"authoritative broker order failed strict validation: {exc}",
            CHAIN_ERROR_IDENTITY_MISMATCH,
            resolution.root_order_id,
        )
    return ReplacementResolution(
        authoritative,
        resolution.traversed_orders,
        resolution.chain,
        root_order_id=resolution.root_order_id,
    )


def _record_chain_failure(
    store: AssistantStore,
    proposal_id: str,
    resolution: ReplacementResolution,
    result: dict[str, Any] | None = None,
) -> str:
    """Park a proposal whose replacement chain could not be trusted.

    An identity mismatch anywhere in the chain trips the persistent kill switch
    -- it means an order under our own idempotency key was altered out of band,
    which is exactly the anomaly that protection exists for. An unresolved
    lookup does NOT: that is "we cannot tell yet", so the proposal is left at
    submission_unknown and stays retryable.
    """
    mismatch = resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH
    reason = (
        f"Replacement chain could not be trusted for {proposal_id}: {resolution.error}. "
        + ("Persistent kill switch activated; investigate manually."
           if mismatch else "Manual investigation is required.")
    )
    if mismatch:
        store.park_reconciliation_anomaly_and_halt(
            proposal_id,
            expected_statuses=RECONCILABLE_STATUSES,
            reason=reason,
            reconciled_at=datetime.now(timezone.utc).isoformat(),
            details={"path": "startup_replacement_chain"},
            anomaly_key="startup_replacement_chain_identity_mismatch",
        )
    else:
        store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=RECONCILABLE_STATUSES,
            new_status=SUBMISSION_UNKNOWN,
            error=reason,
        )
    if result is not None:
        result["errors"].append(reason)
    return reason


def _stream_stop_kwargs(broker_module: Any, stop: Event) -> dict[str, Any]:
    """
    Pass `stop_event` to run_trade_update_stream() only if that broker
    implementation accepts it.

    Running the stream on its own daemon thread already guarantees
    monitor_orders() returns promptly, but the underlying socket would be left
    open until process exit. A broker that accepts `stop_event` can tear the
    stream down properly instead. Signature-checked rather than try/except
    TypeError, so a genuine TypeError raised INSIDE the stream is never
    mistaken for an unsupported-parameter signal -- and so the test fakes that
    take only `callback` keep working unchanged.
    """
    try:
        parameters = inspect.signature(broker_module.run_trade_update_stream).parameters
    except (TypeError, ValueError):
        return {}
    return {"stop_event": stop} if "stop_event" in parameters else {}


RECONCILABLE_STATUSES = (
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    BROKER_ACCEPTED,
    PARTIALLY_FILLED,
    CANCEL_PENDING,
    EXECUTED,
)


def _proposal_for_update(store: AssistantStore, order: dict[str, Any]) -> dict[str, Any] | None:
    client_order_id = order.get("client_order_id")
    if client_order_id:
        proposal = store.get_proposal_by_idempotency_key(str(client_order_id))
        if proposal is not None:
            return proposal
    order_id = order.get("order_id")
    if order_id:
        proposal = store.get_proposal_by_broker_order_id(str(order_id))
        if proposal is not None:
            return proposal

    # Replacement chain: a replaced order is terminal for its own id and the
    # replacement arrives with a NEW order id (and usually a new
    # client_order_id), so neither lookup above can find the proposal it
    # supersedes -- the update was silently dropped while the proposal sat
    # waiting, and the replacement could fill untracked (GPT review,
    # 2026-07-29). `replaces` holds the ORIGINAL broker order id, which is the
    # id the proposal was stored under.
    #
    # Matching here is safe rather than presumptuous: apply_broker_update()
    # still runs _order_matches_intent() on the replacement, so an equivalent
    # replacement is tracked normally and one whose ticker/side/quantity was
    # altered out-of-band trips the identity-mismatch kill switch instead of
    # being quietly accepted.
    replaces = order.get("replaces")
    return store.get_proposal_by_broker_order_id(str(replaces)) if replaces else None


def apply_broker_update(
    store: AssistantStore,
    proposal: dict[str, Any],
    order: dict[str, Any],
    *,
    event_type: str,
    event_at: str | None = None,
    external_event_id: str | None = None,
    fill_qty: float | None = None,
    fill_price: float | None = None,
    raw_event: dict[str, Any] | None = None,
    observed_account=None,
    already_validated: bool = False,
    broker_order_root_id: str | None = None,
    replacement_order_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Verify identity, append the event, and update proposal state."""
    try:
        intent = _intent_from_dict(proposal["intent"])
    except Exception as exc:
        reason = f"Malformed intent during reconciliation: {exc}"
        store.activate_reconciliation_halt(
            proposal_id=str(proposal.get("proposal_id") or "unknown"),
            reason=reason,
            details={"path": "broker_update_malformed_intent"},
        )
        raise ProposalExecutionError(
            f"Malformed stored intent for {proposal.get('proposal_id')}: {exc}"
        ) from exc
    try:
        expected_parent = None
        root_order = not bool(order.get("replaces"))
        if not root_order and not already_validated:
            prior = proposal.get("broker_order")
            if isinstance(prior, Mapping):
                raw_prior_id = prior.get("order_id")
                raw_incoming_id = order.get("order_id")
                if isinstance(raw_prior_id, str) and raw_prior_id:
                    # A later status/fill observation for the SAME replacement
                    # must retain that replacement's already-proven parent.
                    # Only a genuinely new child is expected to replace the
                    # current order ID.
                    raw_parent = (
                        prior.get("replaces")
                        if raw_incoming_id == raw_prior_id
                        else raw_prior_id
                    )
                    if isinstance(raw_parent, str) and raw_parent:
                        expected_parent = raw_parent
        canonical_order = canonical_order_for_proposal(
            order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=root_order,
            expected_replaces_order_id=expected_parent,
        )
    except Exception as evidence_exc:
        detail = str(evidence_exc)
        reason = (
            f"Broker reconciliation identity mismatch for {proposal['proposal_id']}: {detail}. "
            "Persistent kill switch activated."
        )
        store.park_reconciliation_anomaly_and_halt(
            proposal["proposal_id"],
            expected_statuses=RECONCILABLE_STATUSES,
            reason=reason,
            reconciled_at=datetime.now(timezone.utc).isoformat(),
            details={"mismatch": detail, "path": "broker_update_identity"},
            anomaly_key="broker_update_identity_mismatch",
        )
        raise ProposalExecutionError(reason)
    return journal_broker_order_update(
        store,
        proposal["proposal_id"],
        canonical_order,
        event_type=event_type,
        event_at=event_at,
        external_event_id=external_event_id,
        fill_qty=fill_qty,
        fill_price=fill_price,
        raw_event=raw_event,
        clear_error=True,
        broker_order_root_id=broker_order_root_id,
        replacement_order_path=replacement_order_path,
    )


def handle_trade_update(
    store: AssistantStore,
    update: dict[str, Any],
    *,
    broker_module: Any = None,
    observed_account=None,
) -> dict[str, Any] | None:
    """Process one normalized Alpaca trade-update message.

    `broker_module` is optional. When supplied, a `replaced` event resolves
    through the replacement chain exactly as polling does, so the live and
    polling paths project the same proposal state from the same authoritative
    order instead of the live path parking it at submission_unknown. Without
    it (older callers, tests with a callback-only fake) the event is handled
    as before -- the backward `replaces` match in _proposal_for_update() still
    attaches a replacement event to the right proposal either way.
    """
    order = update["order"]
    proposal = _proposal_for_update(store, order)
    if proposal is None:
        # The stream can include orders placed outside this assistant.
        # They are not safe to attach heuristically to a proposal.
        store.set_system_state(
            "trade_stream_heartbeat",
            {"at": datetime.now(timezone.utc).isoformat(), "unmanaged_order": True},
        )
        return None

    projected = order
    broker_order_root_id = None
    replacement_order_path: tuple[str, ...] = ()
    if observed_account is None and broker_module is not None:
        observed_account = observed_broker_account(broker_module)
    if broker_module is not None and is_replaced_order(order):
        resolution = _resolve_chain_for(
            proposal,
            order,
            broker_module,
            observed_account=observed_account,
        )
        if resolution.error is not None:
            # Unresolved is unresolved on this path too: park it for a human
            # rather than projecting from the stale replaced order. Shares
            # _record_chain_failure with polling so both paths make the same
            # kill-switch-vs-retryable decision.
            _record_chain_failure(store, proposal["proposal_id"], resolution)
            return None
        projected = resolution.authoritative_order
        broker_order_root_id = resolution.root_order_id
        replacement_order_path = resolution.order_path
        update = dict(update, replacement_chain=list(resolution.chain))

    result = apply_broker_update(
        store,
        proposal,
        projected,
        event_type=str(update.get("event") or order.get("status") or "trade_update"),
        event_at=update.get("event_at"),
        external_event_id=update.get("event_id"),
        fill_qty=update.get("fill_qty"),
        fill_price=update.get("fill_price"),
        raw_event=update,
        observed_account=observed_account,
        already_validated=(projected is not order),
        broker_order_root_id=broker_order_root_id,
        replacement_order_path=replacement_order_path,
    )
    store.set_system_state(
        "trade_stream_heartbeat",
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "proposal_id": proposal["proposal_id"],
            "event": update.get("event"),
        },
    )
    return result


def _parse_datetime(value: Any) -> datetime | None:
    """Parse only timezone-aware timestamps; ambiguity must stay visible."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _order_timestamp_disposition(value: Any, *, now: datetime) -> dict[str, Any]:
    """Classify broker time evidence without collapsing integrity failures."""
    return timestamp_disposition(value, now=now, field="submitted_at")


def _cancel_if_stale(
    store: AssistantStore,
    proposal: dict[str, Any],
    order: dict[str, Any],
    *,
    broker_module,
    now: datetime,
    max_order_age_minutes: float,
    observed_account,
) -> dict[str, Any]:
    if proposal["status"] not in (BROKER_ACCEPTED, PARTIALLY_FILLED):
        return {
            "proposal_id": proposal["proposal_id"],
            "order_id": order.get("order_id"),
            "timestamp": {"kind": "not_evaluated", "integrity_ok": True},
            "cancellation": {"kind": "not_cancelable_status", "requested": False},
            "integrity_failure": False,
            "error": None,
        }
    timestamp = _order_timestamp_disposition(order.get("submitted_at"), now=now)
    if not timestamp["integrity_ok"]:
        reason = (
            f"Broker order timestamp integrity failure for {proposal['proposal_id']}: "
            f"submitted_at is {timestamp['kind']} ({timestamp['raw']!r}). "
            "Persistent kill switch activated; explicit operator recovery is "
            "required before any cancellation decision from ambiguous time evidence."
        )
        alert_error: str | None = None
        try:
            store.activate_reconciliation_halt(
                proposal_id=proposal["proposal_id"],
                reason=reason,
                seen_at=now.isoformat(),
                details={
                    "path": "stale_order_timestamp_integrity",
                    "order_id": order.get("order_id"),
                    "timestamp_disposition": timestamp,
                    "cancellation_disposition": "operator_recovery_required",
                },
            )
        except Exception as exc:
            alert_error = f"; durable alert failed: {exc}"
        return {
            "proposal_id": proposal["proposal_id"],
            "order_id": order.get("order_id"),
            "timestamp": timestamp,
            "cancellation": {
                "kind": "operator_recovery_required",
                "requested": False,
            },
            "integrity_failure": True,
            "error": reason + (alert_error or ""),
        }

    age_seconds = max(0.0, float(timestamp["signed_age_seconds"] or 0.0))
    if age_seconds < max_order_age_minutes * 60.0:
        return {
            "proposal_id": proposal["proposal_id"],
            "order_id": order.get("order_id"),
            "timestamp": timestamp,
            "cancellation": {"kind": "recent", "requested": False},
            "integrity_failure": False,
            "error": None,
        }
    try:
        cancel_result = broker_module.cancel_order(str(order["order_id"]))
    except Exception as exc:
        return {
            "proposal_id": proposal["proposal_id"],
            "order_id": order.get("order_id"),
            "timestamp": timestamp,
            "cancellation": {"kind": "request_failed", "requested": False},
            "integrity_failure": False,
            "error": f"broker cancellation request failed: {exc}",
        }
    # A successful cancel request is a real state transition even when the
    # immediate GET still reports "new" before Alpaca emits pending_cancel.
    pending = dict(order)
    pending.update(cancel_result or {})
    pending["status"] = "pending_cancel"
    pending["cancel_requested_at"] = now.isoformat()
    projection_error: str | None = None
    try:
        apply_broker_update(
            store,
            proposal,
            pending,
            event_type="cancel_requested",
            event_at=now.isoformat(),
            observed_account=observed_account,
            already_validated=True,
        )
    except Exception as exc:
        projection_error = f"cancellation requested but local projection failed: {exc}"
    return {
        "proposal_id": proposal["proposal_id"],
        "order_id": order.get("order_id"),
        "timestamp": timestamp,
        "cancellation": {
            "kind": "requested_for_staleness",
            "requested": True,
            "projected": projection_error is None,
        },
        "integrity_failure": False,
        "error": projection_error,
    }


def _record_cancellation_disposition(
    result: dict[str, Any], disposition: dict[str, Any]
) -> None:
    result["cancellation_dispositions"].append(disposition)
    if disposition["cancellation"].get("requested"):
        result["cancellation_requested"] += 1
    if disposition.get("integrity_failure"):
        result["timestamp_integrity_failures"] += 1
    if disposition.get("error"):
        result["errors"].append(
            {
                "proposal_id": disposition.get("proposal_id"),
                "order_id": disposition.get("order_id"),
                "error": disposition["error"],
                "timestamp_disposition": disposition.get("timestamp"),
                "cancellation_disposition": disposition.get("cancellation"),
            }
        )


def cancel_assistant_order(
    store: AssistantStore,
    proposal_id: str,
    *,
    broker_module=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cancel the authoritative broker order for one assistant proposal."""
    requested_at = _aware_utc_now(now, name="cancel timestamp")
    if broker_module is None:
        import execution.alpaca_broker as broker_module

    broker_session = _account_scoped_broker(broker_module)
    observed_account = observed_broker_account(broker_session)
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"Unknown proposal: {proposal_id}")
    if proposal["status"] not in RECONCILABLE_STATUSES:
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is not in a cancelable broker state "
            f"(status={proposal['status']!r})."
        )

    assert_expected_broker_account(proposal, observed_account)
    order = broker_session.find_order_by_client_id(
        proposal["idempotency_key"]
    )
    if order is None:
        raise ProposalExecutionError(
            f"Broker confirms no order exists for proposal {proposal_id}."
        )
    resolution = _resolve_chain_for(
        proposal,
        order,
        broker_session,
        observed_account=observed_account,
    )
    if resolution.error is not None:
        # If an altered replacement was actually located, cancellation is a
        # risk-reducing action and must not be obstructed by the identity
        # anomaly. Follow the remaining structural chain without trusting
        # identity, cancel the latest order we can locate, then always
        # park/kill-switch—even if the broker rejects the cancellation.
        if resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH:
            anomalous = (
                resolution.traversed_orders[-1]
                if resolution.traversed_orders
                else order
            )
            untrusted_tail = resolve_replacement_chain(
                anomalous,
                lambda order_id: broker_session.get_order_by_id(order_id),
                require_back_reference=False,
            )
            cancel_target = (
                untrusted_tail.authoritative_order
                or (
                    untrusted_tail.traversed_orders[-1]
                    if untrusted_tail.traversed_orders
                    else anomalous
                )
            )
            cancel_error: str | None = None
            cancel_target_id, _ = _emergency_order_id(cancel_target)
            try:
                if cancel_target_id is None:
                    raise ValueError("anomalous broker order has no usable order ID")
                broker_session.cancel_order(cancel_target_id)
            except Exception as exc:
                cancel_error = str(exc)
            reason = _record_chain_failure(store, proposal_id, resolution)
            if cancel_error:
                reason += (
                    " The emergency cancellation request for "
                    f"{cancel_target.get('order_id')} also failed: "
                    f"{cancel_error}"
                )
            raise ProposalExecutionError(reason)
        reason = _record_chain_failure(store, proposal_id, resolution)
        raise ProposalExecutionError(reason)

    authoritative = resolution.authoritative_order
    cancel_result = broker_session.cancel_order(
        str(authoritative["order_id"])
    )
    pending = dict(authoritative)
    pending.update(cancel_result or {})
    pending["status"] = "pending_cancel"
    pending["cancel_requested_at"] = requested_at.isoformat()
    projected = apply_broker_update(
        store,
        proposal,
        pending,
        event_type="operator_cancel_requested",
        event_at=requested_at.isoformat(),
        raw_event={
            "operator_cancel": True,
            "replacement_chain": list(resolution.chain),
            "order": pending,
        },
        observed_account=observed_account,
        already_validated=True,
        broker_order_root_id=resolution.root_order_id,
        replacement_order_path=resolution.order_path,
    )
    return {
        "proposal_id": proposal_id,
        "order_id": str(authoritative["order_id"]),
        "status": projected["status"],
        "cancel_requested_at": requested_at.isoformat(),
        "replacement_chain": list(resolution.chain),
    }


def cancel_all_open_orders(
    store: AssistantStore,
    *,
    broker_module=None,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Engage the durable kill switch, then cancel every broker open order.

    Unmanaged and identity-mismatched orders are still canceled. Emergency
    risk reduction must not depend on the assistant being able to attribute
    an order cleanly; attribution errors are returned and preserved for
    investigation after the cancellation request.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("cancel-all reason must be non-empty")
    normalized_reason = reason.strip()
    requested_at = _aware_utc_now(now, name="cancel-all timestamp")
    containment_reason = f"Emergency cancel-all requested: {normalized_reason}"
    incident_id = "cancel-all:" + hashlib.sha256(
        f"{store.path.resolve()}:{requested_at.isoformat()}:{normalized_reason}".encode(
            "utf-8"
        )
    ).hexdigest()[:40]
    errors: list[dict[str, Any]] = []
    runtime_stop_error: str | None = None
    try:
        runtime_stop = activate_runtime_emergency_stop(
            store.path,
            incident_id=incident_id,
            reason=containment_reason,
            changed_at=requested_at.isoformat(),
        )
    except Exception as exc:
        runtime_stop = None
        runtime_stop_error = str(exc)
        errors.append(
            {
                "order_id": None,
                "error": (
                    "shared runtime emergency stop could not be persisted: "
                    f"{exc}"
                ),
            }
        )
    local_stop_error: str | None = None
    try:
        local_result = store.set_kill_switch(
            True,
            reason=containment_reason,
            incident_id=incident_id,
            changed_at=requested_at.isoformat(),
        )
        runtime_stop = local_result["runtime_stop"]
    except Exception as exc:
        local_stop_error = str(exc)
        errors.append(
            {
                "order_id": None,
                "error": f"local database kill switch could not be persisted: {exc}",
            }
        )

    try:
        observed_runtime_stop = get_runtime_emergency_stop(store.path)
        runtime_stop_active = observed_runtime_stop.get("active") is True
        runtime_stop_confirmed = (
            runtime_stop_active
            and not observed_runtime_stop.get("integrity_error")
            and any(
                item.get("incident_id") == incident_id
                for item in observed_runtime_stop.get("open_incidents", [])
            )
        )
    except Exception as exc:
        observed_runtime_stop = None
        runtime_stop_active = None
        runtime_stop_confirmed = False
        runtime_stop_error = runtime_stop_error or str(exc)
        errors.append(
            {
                "order_id": None,
                "error": f"shared runtime emergency stop could not be read: {exc}",
            }
        )
    try:
        observed_local_stop = store.get_kill_switch()
        local_stop_active = observed_local_stop.get("active") is True
        local_stop_confirmed = local_stop_active
    except Exception as exc:
        observed_local_stop = None
        local_stop_active = None
        local_stop_confirmed = False
        local_stop_error = local_stop_error or str(exc)
        errors.append(
            {
                "order_id": None,
                "error": f"local database kill switch could not be read: {exc}",
            }
        )
    containment_evidence = {
        "kill_switch_requested": True,
        "kill_switch_active": local_stop_active,
        "local_stop_confirmed": local_stop_confirmed,
        "runtime_stop_requested": True,
        "runtime_stop_active": runtime_stop_active,
        "runtime_stop_confirmed": runtime_stop_confirmed,
        "runtime_stop_error": runtime_stop_error,
        "local_stop_error": local_stop_error,
    }

    canceled: list[dict[str, Any]] = []
    unmanaged = 0
    requested_ids: set[str] = set()
    previous_ids: frozenset[str] | None = None
    consecutive_stable_scans = 0
    initial_order_count: int | None = None
    final_open_order_count: int | None = None
    unresolved_attempt_count = 0
    book_stable = False
    bulk_cancel_requested = False
    scans = 0

    # The switch is already durable. Acquiring the common fence now drains a
    # dispatch that passed an earlier switch check. Open-order indexing may lag
    # a successful submit, so every scan also resolves durable local attempts
    # by order ID or idempotency key; one empty endpoint response is never
    # accepted as proof that cancellation is complete.
    fence_stack, fence_error = _enter_best_effort_emergency_fence(store.path)
    fence_acquired = fence_error is None
    if fence_error is not None:
        errors.append(
            {
                "order_id": None,
                "error": (
                    "dispatch fence could not be acquired; proceeding with "
                    f"best-effort emergency cancellation: {fence_error}"
                ),
            }
        )
    with fence_stack:
        # An operator clear can race the first publication before this drain
        # begins. Re-prove (or republish) this exact incident while the global
        # dispatch fence prevents any new broker contact.
        if fence_acquired:
            try:
                fenced_runtime_stop = get_runtime_emergency_stop(store.path)
                fenced_incident_open = (
                    not fenced_runtime_stop.get("integrity_error")
                    and any(
                        item.get("incident_id") == incident_id
                        and item.get("reason") == containment_reason
                        and item.get("origin_database") == str(store.path.resolve())
                        for item in fenced_runtime_stop.get("open_incidents", [])
                    )
                )
                if not fenced_runtime_stop.get("integrity_error") and not fenced_incident_open:
                    activate_runtime_emergency_stop(
                        store.path,
                        incident_id=incident_id,
                        reason=containment_reason,
                        changed_at=requested_at.isoformat(),
                    )
                    fenced_runtime_stop = get_runtime_emergency_stop(store.path)
                    fenced_incident_open = (
                        not fenced_runtime_stop.get("integrity_error")
                        and any(
                            item.get("incident_id") == incident_id
                            and item.get("reason") == containment_reason
                            and item.get("origin_database") == str(store.path.resolve())
                            for item in fenced_runtime_stop.get("open_incidents", [])
                        )
                    )
                runtime_stop_active = fenced_runtime_stop.get("active") is True
                runtime_stop_confirmed = (
                    runtime_stop_active
                    and fenced_incident_open
                )
                observed_runtime_stop = fenced_runtime_stop
            except Exception as exc:
                runtime_stop_active = None
                runtime_stop_confirmed = False
                runtime_stop_error = runtime_stop_error or str(exc)
                _latch_runtime_emergency_stop_failure(exc)
                errors.append(
                    {
                        "order_id": None,
                        "error": (
                            "shared runtime emergency stop could not be proved "
                            f"under the dispatch fence: {exc}"
                        ),
                    }
                )
            containment_evidence.update(
                {
                    "runtime_stop_active": runtime_stop_active,
                    "runtime_stop_confirmed": runtime_stop_confirmed,
                    "runtime_stop_error": runtime_stop_error,
                }
            )
            try:
                fenced_local_stop = store.get_kill_switch()
                local_stop_active = fenced_local_stop.get("active") is True
                local_stop_confirmed = local_stop_active
                observed_local_stop = fenced_local_stop
            except Exception as exc:
                local_stop_active = None
                local_stop_confirmed = False
                local_stop_error = local_stop_error or str(exc)
                errors.append(
                    {
                        "order_id": None,
                        "error": (
                            "local database kill switch could not be proved under "
                            f"the dispatch fence: {exc}"
                        ),
                    }
                )
            containment_evidence.update(
                {
                    "kill_switch_active": local_stop_active,
                    "local_stop_confirmed": local_stop_confirmed,
                    "local_stop_error": local_stop_error,
                }
            )
        if broker_module is None:
            # Open the immutable credential/mode context only AFTER the stop is
            # durable.  If SDK/client construction fails, the account may be
            # unreachable but another process must still observe the halt.
            try:
                from execution.alpaca_broker import open_alpaca_broker_session

                broker_module = open_alpaca_broker_session()
            except Exception as exc:
                errors.append(
                    {
                        "order_id": None,
                        "error": f"broker session could not be opened: {exc}",
                    }
                )
                _record_cancel_all_incomplete(
                    store,
                    reason=(
                        "Emergency cancel-all engaged the stop but could not "
                        "open a broker session; cancellation completeness is unknown."
                    ),
                    seen_at=requested_at.isoformat(),
                    details={"reason": normalized_reason, "error": str(exc)},
                    fence_acquired=fence_acquired,
                )
                result = {
                    "requested_at": requested_at.isoformat(),
                    "reason": normalized_reason,
                    **containment_evidence,
                    "initial_open_order_count": None,
                    "cancel_requested_count": 0,
                    "managed_order_count": 0,
                    "unmanaged_order_count": 0,
                    "canceled": [],
                    "errors": errors,
                    "book_scan_count": 0,
                    "book_stable": False,
                    "final_open_order_count": None,
                    "unresolved_attempt_count": 0,
                    "bulk_cancel_requested": False,
                    "dispatch_fence_acquired": fence_acquired,
                    "dispatch_fence_error": (
                        None if fence_error is None else str(fence_error)
                    ),
                    "scan_book_stable": False,
                }
                store.set_system_state("last_cancel_all_open_orders", result)
                return result
        else:
            # An explicitly supplied production facade still has to collapse
            # to one frozen session. Test doubles may already be sessions.
            opener = getattr(broker_module, "open_alpaca_broker_session", None)
            if callable(opener):
                try:
                    broker_module = opener()
                except Exception as exc:
                    errors.append(
                        {
                            "order_id": None,
                            "error": f"broker session could not be opened: {exc}",
                        }
                    )
                    _record_cancel_all_incomplete(
                        store,
                        reason=(
                            "Emergency cancel-all engaged the stop but could not "
                            "open a broker session; cancellation completeness is unknown."
                        ),
                        seen_at=requested_at.isoformat(),
                        details={"reason": normalized_reason, "error": str(exc)},
                        fence_acquired=fence_acquired,
                    )
                    result = {
                        "requested_at": requested_at.isoformat(),
                        "reason": normalized_reason,
                        **containment_evidence,
                        "initial_open_order_count": None,
                        "cancel_requested_count": 0,
                        "managed_order_count": 0,
                        "unmanaged_order_count": 0,
                        "canceled": [],
                        "errors": errors,
                        "book_scan_count": 0,
                        "book_stable": False,
                        "final_open_order_count": None,
                        "unresolved_attempt_count": 0,
                        "bulk_cancel_requested": False,
                        "dispatch_fence_acquired": fence_acquired,
                        "dispatch_fence_error": (
                            None if fence_error is None else str(fence_error)
                        ),
                        "scan_book_stable": False,
                    }
                    store.set_system_state("last_cancel_all_open_orders", result)
                    return result
        emergency_observed_account = None
        if (
            getattr(broker_module, "account_mode", None) in {"paper", "live"}
            and callable(getattr(broker_module, "get_account", None))
        ):
            try:
                emergency_observed_account = observed_broker_account(broker_module)
            except Exception as exc:
                # Attribution/projection can fail, but risk-reducing
                # cancellation below must continue using every minimally
                # usable order ID.
                errors.append(
                    {
                        "order_id": None,
                        "error": f"broker account attribution unavailable: {exc}",
                    }
                )
        bulk_cancel = getattr(broker_module, "cancel_all_orders", None)
        if callable(bulk_cancel):
            try:
                bulk_cancel()
                bulk_cancel_requested = True
            except Exception as exc:
                errors.append(
                    {
                        "order_id": None,
                        "error": f"broker bulk cancellation failed: {exc}",
                    }
                )
        scan_index = 0
        runtime_scan_not_after: datetime | None = None
        while (
            scan_index < _CANCEL_ALL_MAX_BOOK_SCANS
            or (
                runtime_scan_not_after is not None
                and datetime.now(timezone.utc) <= runtime_scan_not_after
            )
        ):
            scan_index += 1
            scans += 1
            scan_incomplete = False
            candidates: dict[
                str, tuple[dict[str, Any], dict[str, Any] | None]
            ] = {}

            emergency_enumeration_needed = False
            try:
                orders = broker_module.get_open_orders()
            except Exception as exc:
                orders = []
                scan_incomplete = True
                emergency_enumeration_needed = True
                errors.append(
                    {
                        "order_id": None,
                        "error": f"open-order query failed: {exc}",
                    }
                )
            if not isinstance(orders, (list, tuple)):
                orders = []
                scan_incomplete = True
                emergency_enumeration_needed = True
                errors.append(
                    {
                        "order_id": None,
                        "error": (
                            "open-order query returned a non-sequence; "
                            "cancellation completeness is unknown"
                        ),
                    }
                )
            if not emergency_enumeration_needed:
                strict_ids: set[str] = set()
                for strict_order in orders:
                    strict_order_id, _ = _emergency_order_id(strict_order)
                    if strict_order_id is None or strict_order_id in strict_ids:
                        emergency_enumeration_needed = True
                        break
                    strict_ids.add(strict_order_id)
            if emergency_enumeration_needed:
                emergency_enumerator = getattr(
                    broker_module, "get_open_order_ids_for_emergency", None
                )
                if callable(emergency_enumerator):
                    try:
                        enumeration = emergency_enumerator()
                        if not isinstance(enumeration, dict) or set(enumeration) != {
                            "order_ids",
                            "complete",
                            "errors",
                        }:
                            raise ValueError(
                                "emergency open-order enumeration is malformed"
                            )
                        raw_ids = enumeration["order_ids"]
                        enumeration_errors = enumeration["errors"]
                        if (
                            type(enumeration["complete"]) is not bool
                            or not isinstance(raw_ids, list)
                            or not isinstance(enumeration_errors, list)
                            or any(not isinstance(item, dict) for item in enumeration_errors)
                        ):
                            raise ValueError(
                                "emergency open-order enumeration is malformed"
                            )
                        usable_ids: list[str] = []
                        for raw_id in raw_ids:
                            if (
                                not isinstance(raw_id, str)
                                or not raw_id
                                or raw_id != raw_id.strip()
                                or raw_id in usable_ids
                            ):
                                raise ValueError(
                                    "emergency open-order enumeration contains "
                                    "a malformed or repeated ID"
                                )
                            usable_ids.append(raw_id)
                        for item in enumeration_errors:
                            errors.append(
                                {
                                    "order_id": item.get("order_id"),
                                    "error": (
                                        "emergency open-order enumeration: "
                                        f"{item.get('error', 'unknown row error')}"
                                    ),
                                }
                            )
                        scan_incomplete = (
                            not enumeration["complete"] or bool(enumeration_errors)
                        )
                        for order_id in usable_ids:
                            candidates[order_id] = ({"order_id": order_id}, None)
                    except Exception as exc:
                        scan_incomplete = True
                        errors.append(
                            {
                                "order_id": None,
                                "error": (
                                    "emergency open-order enumeration failed: "
                                    f"{exc}"
                                ),
                            }
                        )
            if initial_order_count is None and not scan_incomplete:
                initial_order_count = len(orders)

            for order in orders:
                order_id, normalized_order = _emergency_order_id(order)
                if order_id is None:
                    scan_incomplete = True
                    errors.append(
                        {"order_id": None, "error": "broker open order has no usable ID"}
                    )
                    continue
                if order_id in candidates:
                    emergency_candidate = candidates[order_id][0]
                    if emergency_candidate == {"order_id": order_id}:
                        normalized_order["order_id"] = order_id
                        candidates[order_id] = (normalized_order, None)
                        continue
                    scan_incomplete = True
                    errors.append(
                        {
                            "order_id": order_id,
                            "error": "broker open-order response repeated an order ID",
                        }
                    )
                    continue
                normalized_order["order_id"] = order_id
                candidates[order_id] = (normalized_order, None)

            open_book_complete = not scan_incomplete

            unresolved_attempt_count = 0
            try:
                durable_proposals = store.list_proposals_by_statuses(
                    UNRESOLVED_BROKER_STATE_STATUSES
                )
            except Exception as exc:
                durable_proposals = []
                scan_incomplete = True
                errors.append(
                    {
                        "order_id": None,
                        "error": f"durable submission query failed: {exc}",
                    }
                )
            for proposal in durable_proposals:
                order: dict[str, Any] | None = None
                for key in ("broker_order", "broker_order_update"):
                    value = proposal.get(key)
                    if isinstance(value, Mapping):
                        order = dict(value)
                        break
                order_id: str | None = None
                if order is not None:
                    order_id, order = _emergency_order_id(order)
                if order_id is None:
                    idempotency_key = proposal.get("idempotency_key")
                    lookup = getattr(broker_module, "find_order_by_client_id", None)
                    if not isinstance(idempotency_key, str) or not idempotency_key:
                        scan_incomplete = True
                        unresolved_attempt_count += 1
                        errors.append(
                            {
                                "order_id": None,
                                "proposal_id": proposal.get("proposal_id"),
                                "error": "unresolved submission has no usable idempotency key",
                            }
                        )
                        continue
                    if not callable(lookup):
                        scan_incomplete = True
                        unresolved_attempt_count += 1
                        continue
                    try:
                        found = lookup(idempotency_key)
                    except Exception as exc:
                        scan_incomplete = True
                        unresolved_attempt_count += 1
                        errors.append(
                            {
                                "order_id": None,
                                "proposal_id": proposal.get("proposal_id"),
                                "error": f"unresolved submission lookup failed: {exc}",
                            }
                        )
                        continue
                    if found is None:
                        # Broker absence is not credible during this short
                        # emergency drain; normal reconciliation owns the
                        # documented absence-grace proof.
                        scan_incomplete = True
                        unresolved_attempt_count += 1
                        continue
                    order_id, order = _emergency_order_id(found)
                if order_id is None or order is None:
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    errors.append(
                        {
                            "order_id": None,
                            "proposal_id": proposal.get("proposal_id"),
                            "error": "unresolved broker evidence has no usable order ID",
                        }
                    )
                    continue
                order["order_id"] = order_id
                existing = candidates.get(order_id)
                candidates[order_id] = (
                    existing[0] if existing is not None else order,
                    proposal,
                )

            # A different worktree/database can have passed its final stop
            # check immediately before this emergency was published. Its local
            # proposal row is invisible here, so consult the runtime attempt
            # ledger written immediately before every broker contact.
            try:
                runtime_attempts = list_runtime_dispatch_attempts(store.path)
            except Exception as exc:
                runtime_attempts = []
                scan_incomplete = True
                errors.append(
                    {
                        "order_id": None,
                        "error": f"shared dispatch-attempt ledger is unreadable: {exc}",
                    }
                )
            observed_account_id = getattr(
                emergency_observed_account, "account_id", None
            )
            observed_account_mode = getattr(
                emergency_observed_account, "account_mode", None
            )
            for attempt in runtime_attempts:
                # The global runtime may serialize more than one configured
                # account. Never use one account's durable client ID against
                # another; the runtime stop remains conservatively global.
                if (
                    observed_account_id is None
                    or observed_account_mode is None
                ):
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    continue
                if (
                    attempt.get("account_id") != observed_account_id
                    or attempt.get("account_mode") != observed_account_mode
                ):
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    errors.append(
                        {
                            "order_id": attempt.get("order_id"),
                            "proposal_id": attempt.get("proposal_id"),
                            "error": (
                                "shared dispatch attempt belongs to a different "
                                "broker account/mode; refusing cross-account "
                                "cancellation while retaining containment"
                            ),
                        }
                    )
                    continue
                attempted_at = _parse_datetime(attempt.get("attempted_at"))
                if attempted_at is None:
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    continue
                observed_at = datetime.now(timezone.utc)
                age = observed_at - attempted_at
                if age < timedelta(0):
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    continue
                grace_deadline = attempted_at + timedelta(
                    seconds=BROKER_ABSENCE_GRACE_SECONDS
                )
                old_attempt = observed_at > grace_deadline
                if old_attempt and open_book_complete:
                    # After the same frozen absence grace used by ordinary
                    # reconciliation, the open-book endpoint is authoritative.
                    continue

                order_id = attempt.get("order_id")
                order: dict[str, Any] | None = None
                if old_attempt:
                    lookup = None
                    lookup_value = None
                    durable_order_id = (
                        order_id.strip()
                        if isinstance(order_id, str) and order_id.strip()
                        else None
                    )
                    lookup_failed = False
                    if durable_order_id is not None:
                        lookup = getattr(broker_module, "get_order_by_id", None)
                        lookup_value = durable_order_id
                    else:
                        lookup = getattr(
                            broker_module, "find_order_by_client_id", None
                        )
                        lookup_value = attempt["idempotency_key"]
                    if callable(lookup):
                        try:
                            found = lookup(lookup_value)
                        except Exception as exc:
                            found = None
                            lookup_failed = True
                            scan_incomplete = True
                            unresolved_attempt_count += 1
                            errors.append(
                                {
                                    "order_id": order_id,
                                    "proposal_id": attempt.get("proposal_id"),
                                    "error": (
                                        "old shared dispatch-attempt exact lookup "
                                        f"failed: {exc}"
                                    ),
                                }
                            )
                        if found is not None:
                            order_id, order = _emergency_order_id(found)
                        elif durable_order_id is not None:
                            # The open-book scan is incomplete, so even an
                            # exact lookup miss/error cannot safely suppress a
                            # cancellation attempt using retained broker ID.
                            order_id = durable_order_id
                            order = {"order_id": durable_order_id}
                        elif not lookup_failed:
                            # A successful exact post-grace client-ID absence
                            # resolves an attempt that never retained an order.
                            continue
                    elif durable_order_id is not None:
                        # Still issue the safest possible cancellation using
                        # durable accepted-order identity, but retain the scan
                        # as incomplete because exact current state is unknown.
                        scan_incomplete = True
                        order_id = durable_order_id
                        order = {"order_id": durable_order_id}
                    else:
                        scan_incomplete = True
                        unresolved_attempt_count += 1
                elif isinstance(order_id, str) and order_id.strip():
                    order_id = order_id.strip()
                    order = {"order_id": order_id}
                else:
                    lookup = getattr(
                        broker_module, "find_order_by_client_id", None
                    )
                    if callable(lookup):
                        try:
                            found = lookup(attempt["idempotency_key"])
                        except Exception as exc:
                            found = None
                            errors.append(
                                {
                                    "order_id": None,
                                    "proposal_id": attempt.get("proposal_id"),
                                    "error": (
                                        "shared dispatch-attempt lookup failed: "
                                        f"{exc}"
                                    ),
                                }
                            )
                        if found is not None:
                            order_id, order = _emergency_order_id(found)
                if order_id is None or order is None:
                    scan_incomplete = True
                    unresolved_attempt_count += 1
                    extension = grace_deadline + timedelta(
                        seconds=(
                            _CANCEL_ALL_REQUIRED_STABLE_SCANS
                            * _CANCEL_ALL_SCAN_INTERVAL_SECONDS
                        )
                    )
                    runtime_scan_not_after = max(
                        runtime_scan_not_after or extension,
                        extension,
                    )
                    continue
                order["order_id"] = order_id
                existing = candidates.get(order_id)
                candidates[order_id] = (
                    existing[0] if existing is not None else order,
                    existing[1] if existing is not None else None,
                )

            current_ids = frozenset(candidates)
            final_open_order_count = (
                None if scan_incomplete else len(current_ids)
            )

            # Retry failed requests on later scans. Stability is evaluated only
            # after every currently visible/durable ID has a successful broker
            # cancellation acknowledgement.
            for order_id, (order, proposal_hint) in candidates.items():
                if order_id in requested_ids:
                    continue
                try:
                    cancel_result = broker_module.cancel_order(order_id)
                except Exception as exc:
                    errors.append({"order_id": order_id, "error": str(exc)})
                    continue
                requested_ids.add(order_id)

                proposal = proposal_hint
                if proposal is None:
                    try:
                        proposal = _proposal_for_update(store, order)
                    except Exception as exc:
                        errors.append(
                            {
                                "order_id": order_id,
                                "error": (
                                    "cancel requested; local attribution failed: "
                                    f"{exc}"
                                ),
                            }
                        )
                canceled.append(
                    {
                        "order_id": order_id,
                        "proposal_id": (
                            proposal.get("proposal_id") if proposal else None
                        ),
                    }
                )
                if proposal is None:
                    unmanaged += 1
                    continue
                try:
                    pending = dict(order)
                    if isinstance(cancel_result, Mapping):
                        pending.update(cancel_result)
                    pending["status"] = "pending_cancel"
                    pending["cancel_requested_at"] = requested_at.isoformat()
                    apply_broker_update(
                        store,
                        proposal,
                        pending,
                        event_type="emergency_cancel_all_requested",
                        event_at=requested_at.isoformat(),
                        raw_event={
                            "emergency_cancel_all": True,
                            "reason": normalized_reason,
                            "order": pending,
                        },
                        observed_account=emergency_observed_account,
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "order_id": order_id,
                            "proposal_id": proposal.get("proposal_id"),
                            "error": (
                                "cancel requested; local projection failed: "
                                f"{exc}"
                            ),
                        }
                    )

            all_current_requested = current_ids.issubset(requested_ids)
            if (
                not scan_incomplete
                and all_current_requested
                and current_ids == previous_ids
            ):
                consecutive_stable_scans += 1
            else:
                consecutive_stable_scans = 1 if (
                    not scan_incomplete and all_current_requested
                ) else 0
            previous_ids = current_ids
            if consecutive_stable_scans >= _CANCEL_ALL_REQUIRED_STABLE_SCANS:
                book_stable = True
                break
            if (
                scan_index < _CANCEL_ALL_MAX_BOOK_SCANS
                or (
                    runtime_scan_not_after is not None
                    and datetime.now(timezone.utc) <= runtime_scan_not_after
                )
            ):
                time.sleep(_CANCEL_ALL_SCAN_INTERVAL_SECONDS)

        scan_book_stable = book_stable
        containment_incomplete = (
            fence_error is not None
            or not runtime_stop_confirmed
            or not local_stop_confirmed
        )
        if containment_incomplete:
            book_stable = False
        if not book_stable:
            _record_cancel_all_incomplete(
                store,
                reason=(
                    "Emergency cancel-all could not prove every broker order "
                    "received a cancellation request or could not prove the "
                    "cross-process stop/drain boundary."
                ),
                seen_at=requested_at.isoformat(),
                details={
                    "reason": normalized_reason,
                    "book_scan_count": scans,
                    "unresolved_attempt_count": unresolved_attempt_count,
                    "requested_order_ids": sorted(requested_ids),
                    "scan_book_stable": scan_book_stable,
                    "dispatch_fence_error": (
                        None if fence_error is None else str(fence_error)
                    ),
                    "runtime_stop_error": runtime_stop_error,
                    "local_stop_error": local_stop_error,
                },
                fence_acquired=fence_acquired,
            )

        result = {
            "requested_at": requested_at.isoformat(),
            "reason": normalized_reason,
            **containment_evidence,
            "open_order_count": initial_order_count,
            "cancel_requested_count": len(canceled),
            "unmanaged_order_count": unmanaged,
            "canceled": canceled,
            "errors": errors,
            "book_scan_count": scans,
            "book_stable": book_stable,
            "final_open_order_count": final_open_order_count,
            "unresolved_attempt_count": unresolved_attempt_count,
            "bulk_cancel_requested": bulk_cancel_requested,
            "dispatch_fence_acquired": fence_acquired,
            "dispatch_fence_error": (
                None if fence_error is None else str(fence_error)
            ),
            "scan_book_stable": scan_book_stable,
        }
        store.set_system_state("last_cancel_all_open_orders", result)
        return result


def _absence_is_believable(
    proposal: dict[str, Any],
    *,
    now: datetime,
    min_absence_age_seconds: float,
) -> bool:
    """Is a "broker has no such order" lookup old enough to be BELIEVED?

    execute_approved_paper_proposal() writes "submitting" and reserves daily
    budget BEFORE it calls the broker, so between that write and the
    order becoming visible at Alpaca there is a real window -- a full
    HTTP round trip, plus the broker's own indexing latency -- during
    which a lookup correctly returns nothing for an order that is about
    to exist. Believing that lookup marks a live order
    "submission_failed" and RELEASES its daily reservation
    (mark_submission_failed_and_release), so the order that then
    succeeds no longer counts against max_daily_submitted_notional /
    max_daily_order_count, and it briefly leaves the duplicate-risk set
    that stops a second real order for the same ticker/side. The
    reconciler runs on a poller/stream thread concurrently with
    approvals, so this is reachable in normal operation, not only after
    a crash (independent review, 2026-07-30).

    Absence is therefore only believed once the proposal has been in its
    current non-terminal status for at least `min_absence_age_seconds`.
    `updated_at` is rewritten by every status transition, so on a
    "submitting" row it is exactly when submission began -- the same
    mechanism recover_stale_reconciliation() already uses to avoid
    reclaiming a genuinely in-flight attempt.

    Fails CLOSED: a missing or unparseable `updated_at` returns False
    (absence not believed). Declining to act costs one more poll cycle;
    acting wrongly drops a live order's budget reservation.
    """
    updated_at = _parse_datetime(proposal.get("updated_at"))
    if updated_at is None:
        return False
    return now - updated_at >= timedelta(seconds=min_absence_age_seconds)


def reconcile_nonterminal_orders(
    store: AssistantStore,
    *,
    broker_module=None,
    now: datetime | None = None,
    cancel_stale: bool = False,
    max_order_age_minutes: float = 30.0,
    min_absence_age_seconds: float = MIN_ABSENCE_AGE_SECONDS,
) -> dict[str, Any]:
    """Poll all nonterminal proposals once and optionally cancel stale orders.

    `min_absence_age_seconds` is the grace period before a broker lookup
    that finds nothing is believed to PROVE the order does not exist --
    see _absence_is_believable(). Validated FIRST, before any broker call
    or state mutation: a non-finite or negative value would silently
    disable the guard rather than fail, which is the exact failure mode
    the guard exists to prevent. 0.0 is permitted (it restores the old,
    racy behavior) but must be passed deliberately.
    """
    if type(cancel_stale) is not bool:
        raise ValueError("cancel_stale must be an actual bool")
    max_order_age_minutes = _bounded_timing_number(
        "max_order_age_minutes",
        max_order_age_minutes,
        minimum=0.0,
        maximum=_MAX_ORDER_AGE_MINUTES,
        minimum_inclusive=False,
    )
    min_absence_age_seconds = _bounded_timing_number(
        "min_absence_age_seconds",
        min_absence_age_seconds,
        minimum=0.0,
        maximum=_MAX_ABSENCE_AGE_SECONDS,
    )
    explicit_now = now is not None
    now = _aware_utc_now(now)
    if broker_module is None:
        import execution.alpaca_broker as broker_module

    broker_session = _account_scoped_broker(broker_module)
    observed_account = observed_broker_account(broker_session)

    proposals = store.list_proposals_by_statuses(RECONCILABLE_STATUSES)
    result: dict[str, Any] = {
        "checked": len(proposals),
        "updated": 0,
        "cancellation_requested": 0,
        "confirmed_absent": 0,
        "skipped_too_recent": 0,
        "timestamp_integrity_failures": 0,
        "cancellation_dispositions": [],
        # Legacy "executed" rows the broker no longer returns. Counted, never
        # rewritten -- see the EXECUTED branch below.
        "legacy_unverifiable": 0,
        "errors": [],
    }
    for proposal in proposals:
        proposal_id = proposal["proposal_id"]
        try:
            try:
                assert_expected_broker_account(proposal, observed_account)
            except Exception as binding_exc:
                reason = (
                    f"Reconciliation cannot bind proposal {proposal_id} to the "
                    f"connected broker account: {binding_exc}. Persistent kill "
                    "switch activated; no broker state was projected."
                )
                store.park_reconciliation_anomaly_and_halt(
                    proposal_id,
                    expected_statuses=RECONCILABLE_STATUSES,
                    reason=reason,
                    reconciled_at=now.isoformat(),
                    details={"path": "poll_account_binding"},
                    anomaly_key="poll_account_binding_mismatch",
                )
                result["errors"].append(
                    {"proposal_id": proposal_id, "error": reason}
                )
                continue
            order = broker_session.find_order_by_client_id(
                proposal["idempotency_key"]
            )
            # With no caller-frozen as-of clock, classify the evidence against
            # a clock captured after the broker read.  A slow lookup must not
            # make a newly indexed order/replacement look materially future.
            observed_at = (
                now if explicit_now else datetime.now(timezone.utc)
            )
            if order is None:
                if proposal["status"] in (SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING):
                    if not _absence_is_believable(
                        proposal,
                        now=observed_at,
                        min_absence_age_seconds=min_absence_age_seconds,
                    ):
                        result["skipped_too_recent"] += 1
                        continue
                    transitioned = store.mark_submission_failed_and_release(
                        proposal_id,
                        expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                        reconciled_at=observed_at.isoformat(),
                        error="Startup reconciliation: broker confirms no matching order exists.",
                        # Recheck age inside the SAME transaction that releases
                        # the reservation. The proposal snapshot above can go
                        # stale while the broker lookup is in flight.
                        not_updated_after=(
                            observed_at
                            - timedelta(seconds=min_absence_age_seconds)
                        ).astimezone(timezone.utc).isoformat(),
                    )
                    if transitioned is not None:
                        result["confirmed_absent"] += 1
                elif proposal["status"] == EXECUTED:
                    # Legacy "executed" rows are NOT reinterpreted on absence.
                    #
                    # proposal_status_for_order() never returns EXECUTED -- it
                    # only exists on rows written before fill-aware lifecycle
                    # tracking, i.e. OLD trades. Brokers age orders out of their
                    # lookup window, so "not found" for one of these is the
                    # EXPECTED answer, not an anomaly. Flipping it to
                    # submission_unknown discards the only fact we do know:
                    # this is a legacy row whose historical meaning was
                    # "broker accepted", not a newly ambiguous submission.
                    # Both statuses deliberately remain fail-closed in
                    # duplicate prevention/readiness because absence cannot
                    # prove whether the old order filled or was cancelled.
                    #
                    # The row stays in RECONCILABLE_STATUSES on purpose: if the
                    # broker DOES return the order, apply_broker_update() below
                    # still migrates it to a real fill-aware status. Absence
                    # simply is not evidence either way, so nothing is written.
                    result["legacy_unverifiable"] += 1
                else:
                    # A once-known ACTIVE order disappearing from a lookup is
                    # anomalous; do not reinterpret that as a clean failure.
                    store.update_proposal_status_if_current(
                        proposal_id,
                        expected_statuses=(
                            BROKER_ACCEPTED,
                            PARTIALLY_FILLED,
                            CANCEL_PENDING,
                        ),
                        new_status=SUBMISSION_UNKNOWN,
                        error=(
                            "A previously known broker order could not be found during reconciliation; "
                            "manual investigation is required."
                        ),
                    )
                continue
            if cancel_stale and proposal["status"] in (
                BROKER_ACCEPTED,
                PARTIALLY_FILLED,
            ):
                timestamp = _order_timestamp_disposition(
                    order.get("submitted_at"), now=observed_at
                )
                if not timestamp["integrity_ok"]:
                    disposition = _cancel_if_stale(
                        store,
                        proposal,
                        order,
                        broker_module=broker_session,
                        now=observed_at,
                        max_order_age_minutes=max_order_age_minutes,
                        observed_account=observed_account,
                    )
                    _record_cancellation_disposition(result, disposition)
                    continue
            # An order that came back `replaced` is terminal for its own id;
            # the live state lives on the replacement. Follow the chain before
            # projecting anything, or a replacement whose stream event was
            # missed stays untracked even after it fills.
            resolution = _resolve_chain_for(
                proposal,
                order,
                broker_session,
                observed_account=observed_account,
            )
            if resolution.error is not None:
                # Strict replacement validation can itself fail on a missing,
                # naive, or materially future submitted_at.  During an
                # explicitly cancellation-enabled pass, preserve that as the
                # same structured temporal-integrity disposition instead of
                # collapsing it into a generic identity mismatch.
                timestamp_candidate = (
                    resolution.traversed_orders[-1]
                    if resolution.traversed_orders
                    else order
                )
                timestamp_observed_at = (
                    now if explicit_now else datetime.now(timezone.utc)
                )
                timestamp = _order_timestamp_disposition(
                    timestamp_candidate.get("submitted_at"),
                    now=timestamp_observed_at,
                )
                if (
                    cancel_stale
                    and proposal["status"]
                    in (BROKER_ACCEPTED, PARTIALLY_FILLED)
                    and not timestamp["integrity_ok"]
                ):
                    disposition = _cancel_if_stale(
                        store,
                        proposal,
                        timestamp_candidate,
                        broker_module=broker_session,
                        now=timestamp_observed_at,
                        max_order_age_minutes=max_order_age_minutes,
                        observed_account=observed_account,
                    )
                    _record_cancellation_disposition(result, disposition)
                    continue
                _record_chain_failure(store, proposal_id, resolution, result)
                continue
            authoritative = resolution.authoritative_order

            apply_broker_update(
                store,
                proposal,
                authoritative,
                event_type="poll_reconciliation",
                # Audit trail: which replacement ids were traversed to reach
                # the order this projection is based on.
                raw_event={"replacement_chain": list(resolution.chain)} if resolution.chain else None,
                observed_account=observed_account,
                already_validated=True,
                broker_order_root_id=resolution.root_order_id,
                replacement_order_path=resolution.order_path,
            )
            result["updated"] += 1
            if resolution.followed_a_replacement:
                result["replacements_followed"] = result.get("replacements_followed", 0) + 1
            refreshed = store.get_proposal(proposal_id)
            if cancel_stale and refreshed is not None:
                # `authoritative`, NOT `order`: cancelling the SUPERSEDED order
                # left the live replacement running while the proposal was
                # projected to cancel_pending against the dead id.
                disposition = _cancel_if_stale(
                    store,
                    refreshed,
                    authoritative,
                    broker_module=broker_session,
                    now=(
                        now
                        if explicit_now
                        else datetime.now(timezone.utc)
                    ),
                    max_order_age_minutes=max_order_age_minutes,
                    observed_account=observed_account,
                )
                _record_cancellation_disposition(result, disposition)
        except Exception as exc:
            result["errors"].append({"proposal_id": proposal_id, "error": str(exc)})
    completed_at = now if explicit_now else datetime.now(timezone.utc)
    store.set_system_state(
        "last_order_reconciliation",
        {
            "at": completed_at.isoformat(),
            "checked": result["checked"],
            "updated": result["updated"],
            "error_count": len(result["errors"]),
            "timestamp_integrity_error_count": result[
                "timestamp_integrity_failures"
            ],
        },
    )
    return result


def monitor_orders(
    store: AssistantStore,
    *,
    broker_module=None,
    cancel_stale: bool = False,
    max_order_age_minutes: float = 30.0,
    poll_interval_seconds: float = 30.0,
    reconnect_delay_seconds: float = 5.0,
    min_absence_age_seconds: float = MIN_ABSENCE_AGE_SECONDS,
    stop_event: Event | None = None,
) -> dict[str, Any]:
    """Reconcile continuously while consuming a reconnecting trade stream."""
    if type(cancel_stale) is not bool:
        raise ValueError("cancel_stale must be an actual bool")
    max_order_age_minutes = _bounded_timing_number(
        "max_order_age_minutes",
        max_order_age_minutes,
        minimum=0.0,
        maximum=_MAX_ORDER_AGE_MINUTES,
        minimum_inclusive=False,
    )
    min_absence_age_seconds = _bounded_timing_number(
        "min_absence_age_seconds",
        min_absence_age_seconds,
        minimum=0.0,
        maximum=_MAX_ABSENCE_AGE_SECONDS,
    )
    poll_interval_seconds = _bounded_timing_number(
        "poll_interval_seconds",
        poll_interval_seconds,
        minimum=0.0,
        maximum=_MAX_MONITOR_INTERVAL_SECONDS,
        minimum_inclusive=False,
    )
    reconnect_delay_seconds = _bounded_timing_number(
        "reconnect_delay_seconds",
        reconnect_delay_seconds,
        minimum=0.0,
        maximum=_MAX_MONITOR_INTERVAL_SECONDS,
        minimum_inclusive=False,
    )
    if broker_module is None:
        import execution.alpaca_broker as broker_module

    broker_session = _account_scoped_broker(broker_module)
    observed_account = observed_broker_account(broker_session)

    startup = reconcile_nonterminal_orders(
        store,
        broker_module=broker_session,
        cancel_stale=cancel_stale,
        max_order_age_minutes=max_order_age_minutes,
        min_absence_age_seconds=min_absence_age_seconds,
    )
    stop = stop_event or Event()

    def poll_loop() -> None:
        while not stop.wait(poll_interval_seconds):
            reconcile_nonterminal_orders(
                store,
                broker_module=broker_session,
                cancel_stale=cancel_stale,
                max_order_age_minutes=max_order_age_minutes,
                min_absence_age_seconds=min_absence_age_seconds,
            )

    poller = Thread(target=poll_loop, name="order-reconciliation-poller", daemon=True)
    poller.start()
    try:
        while not stop.is_set():
            started_at = datetime.now(timezone.utc).isoformat()
            store.set_system_state(
                "trade_stream_state",
                {"running": True, "started_at": started_at, "last_error": None},
            )
            # The stream runs on its OWN thread so `stop` can interrupt this
            # function promptly. Previously run_trade_update_stream() was
            # called directly here, and since it blocks until the stream ends,
            # stop_event could not interrupt a HEALTHY stream at all -- a
            # shutdown requested at 0.05s did not return until the stream
            # happened to end at 0.65s, and a real connected stream would have
            # blocked graceful programmatic shutdown indefinitely (GPT review,
            # 2026-07-29).
            stream_error: list[str | None] = [None]

            def consume_stream() -> None:
                try:
                    broker_session.run_trade_update_stream(
                        lambda update: handle_trade_update(
                            store,
                            update,
                            broker_module=broker_session,
                            observed_account=observed_account,
                        ),
                        **_stream_stop_kwargs(broker_session, stop),
                    )
                except Exception as exc:  # surfaced on the main thread below
                    stream_error[0] = str(exc)

            streamer = Thread(target=consume_stream, name="trade-update-stream", daemon=True)
            streamer.start()
            while streamer.is_alive() and not stop.is_set():
                streamer.join(timeout=_STREAM_SHUTDOWN_POLL_SECONDS)
            if stop.is_set():
                break
            error = stream_error[0] or "Trade-update stream returned unexpectedly."
            store.set_system_state(
                "trade_stream_state",
                {
                    "running": False,
                    "started_at": started_at,
                    "disconnected_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": error,
                },
            )
            stop.wait(reconnect_delay_seconds)
    finally:
        stop.set()
        # A short polling interval must not also become an unrealistically
        # short shutdown deadline. The poller may already be finishing one
        # reconciliation/database transaction when stop is set; returning
        # while it still owns SQLite leaves the caller with a live background
        # worker and, on Windows, a database file that cannot be moved or
        # removed. Keep shutdown bounded for a genuinely stuck broker call,
        # but give an in-flight normal poll a real opportunity to finish.
        poller.join(timeout=max(2.0, min(poll_interval_seconds, 30.0)))
        store.set_system_state(
            "trade_stream_state",
            {
                "running": False,
                "stopped_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
            },
        )
    return startup
