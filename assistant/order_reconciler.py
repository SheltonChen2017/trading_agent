"""Broker order reconciliation via startup polling and trade-update stream."""
from __future__ import annotations

import inspect
import math
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any

from assistant.execution_service import (
    ProposalExecutionError,
    _intent_from_dict,
    _order_matches_intent,
)
from assistant.dispatch_fence import execution_dispatch_fence
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
    if raw is None or isinstance(raw, bool):
        return None, normalized
    order_id = str(raw).strip()
    if not order_id or order_id.lower() in {"none", "null", "unknown"}:
        return None, normalized
    return order_id, normalized


def _resolve_chain_for(
    proposal: dict[str, Any], order: dict[str, Any], broker_module: Any
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
    return resolve_replacement_chain(
        order,
        # Lazy: resolving broker_module.get_order_by_id EAGERLY made every
        # broker/fake without that method raise AttributeError even for orders
        # that were never replaced (it broke a pre-existing poll test). Now the
        # attribute is only touched when a hop is genuinely fetched, and a
        # missing method surfaces as an unresolved chain rather than a crash.
        lambda oid: broker_module.get_order_by_id(oid),
        validate=lambda candidate: _order_matches_intent(candidate, intent),
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
    matches, detail = _order_matches_intent(order, intent)
    if not matches:
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
        order,
        event_type=event_type,
        event_at=event_at,
        external_event_id=external_event_id,
        fill_qty=fill_qty,
        fill_price=fill_price,
        raw_event=raw_event,
        clear_error=True,
    )


def handle_trade_update(
    store: AssistantStore, update: dict[str, Any], *, broker_module: Any = None
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
    if broker_module is not None and is_replaced_order(order):
        resolution = _resolve_chain_for(proposal, order, broker_module)
        if resolution.error is not None:
            # Unresolved is unresolved on this path too: park it for a human
            # rather than projecting from the stale replaced order. Shares
            # _record_chain_failure with polling so both paths make the same
            # kill-switch-vs-retryable decision.
            _record_chain_failure(store, proposal["proposal_id"], resolution)
            return None
        projected = resolution.authoritative_order
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
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _cancel_if_stale(
    store: AssistantStore,
    proposal: dict[str, Any],
    order: dict[str, Any],
    *,
    broker_module,
    now: datetime,
    max_order_age_minutes: float,
) -> bool:
    if proposal["status"] not in (BROKER_ACCEPTED, PARTIALLY_FILLED):
        return False
    submitted_at = _parse_datetime(order.get("submitted_at") or proposal.get("broker_accepted_at"))
    if submitted_at is None:
        return False
    if now - submitted_at < timedelta(minutes=max_order_age_minutes):
        return False
    cancel_result = broker_module.cancel_order(str(order["order_id"]))
    # A successful cancel request is a real state transition even when the
    # immediate GET still reports "new" before Alpaca emits pending_cancel.
    pending = dict(order)
    pending.update(cancel_result or {})
    pending["status"] = "pending_cancel"
    pending["cancel_requested_at"] = now.isoformat()
    apply_broker_update(
        store,
        proposal,
        pending,
        event_type="cancel_requested",
        event_at=now.isoformat(),
    )
    return True


def cancel_assistant_order(
    store: AssistantStore,
    proposal_id: str,
    *,
    broker_module=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cancel the authoritative broker order for one assistant proposal."""
    if broker_module is None:
        import execution.alpaca_broker as broker_module
    requested_at = now or datetime.now(timezone.utc)
    if requested_at.tzinfo is None:
        raise ValueError("cancel timestamp must be timezone-aware")
    requested_at = requested_at.astimezone(timezone.utc)
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"Unknown proposal: {proposal_id}")
    if proposal["status"] not in RECONCILABLE_STATUSES:
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is not in a cancelable broker state "
            f"(status={proposal['status']!r})."
        )

    order = broker_module.find_order_by_client_id(
        proposal["idempotency_key"]
    )
    if order is None:
        raise ProposalExecutionError(
            f"Broker confirms no order exists for proposal {proposal_id}."
        )
    resolution = _resolve_chain_for(proposal, order, broker_module)
    if resolution.error is not None:
        # If an altered replacement was actually located, cancellation is a
        # risk-reducing action and must not be obstructed by the identity
        # anomaly. Follow the remaining structural chain without trusting
        # identity, cancel the latest order we can locate, then always
        # park/kill-switch—even if the broker rejects the cancellation.
        if (
            resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH
            and resolution.traversed_orders
        ):
            anomalous = resolution.traversed_orders[-1]
            untrusted_tail = resolve_replacement_chain(
                anomalous,
                lambda order_id: broker_module.get_order_by_id(order_id),
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
            try:
                broker_module.cancel_order(
                    str(cancel_target["order_id"])
                )
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
    cancel_result = broker_module.cancel_order(
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
    if broker_module is None:
        # One emergency operation must stay on one immutable credential/mode
        # context.  Re-reading module-level environment configuration between
        # the open-book scan, client-ID lookup, and cancel request could query
        # one account and cancel on another if credentials rotate mid-drain.
        from execution.alpaca_broker import open_alpaca_broker_session

        broker_module = open_alpaca_broker_session()
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("cancel-all reason must be non-empty")
    normalized_reason = reason.strip()
    requested_at = now or datetime.now(timezone.utc)
    if requested_at.tzinfo is None:
        raise ValueError("cancel-all timestamp must be timezone-aware")
    requested_at = requested_at.astimezone(timezone.utc)
    store.set_kill_switch(
        True,
        reason=f"Emergency cancel-all requested: {normalized_reason}",
    )

    canceled: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unmanaged = 0
    requested_ids: set[str] = set()
    previous_ids: frozenset[str] | None = None
    consecutive_stable_scans = 0
    initial_order_count: int | None = None
    final_open_order_count: int | None = None
    unresolved_attempt_count = 0
    book_stable = False
    scans = 0

    # The switch is already durable. Acquiring the common fence now drains a
    # dispatch that passed an earlier switch check. Open-order indexing may lag
    # a successful submit, so every scan also resolves durable local attempts
    # by order ID or idempotency key; one empty endpoint response is never
    # accepted as proof that cancellation is complete.
    with execution_dispatch_fence(store.path):
        for scan_index in range(_CANCEL_ALL_MAX_BOOK_SCANS):
            scans += 1
            scan_incomplete = False
            candidates: dict[
                str, tuple[dict[str, Any], dict[str, Any] | None]
            ] = {}

            try:
                orders = broker_module.get_open_orders()
            except Exception as exc:
                orders = []
                scan_incomplete = True
                errors.append(
                    {
                        "order_id": None,
                        "error": f"open-order query failed: {exc}",
                    }
                )
            if not isinstance(orders, (list, tuple)):
                orders = []
                scan_incomplete = True
                errors.append(
                    {
                        "order_id": None,
                        "error": (
                            "open-order query returned a non-sequence; "
                            "cancellation completeness is unknown"
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
            if scan_index + 1 < _CANCEL_ALL_MAX_BOOK_SCANS:
                time.sleep(_CANCEL_ALL_SCAN_INTERVAL_SECONDS)

        if not book_stable:
            store.activate_reconciliation_halt(
                proposal_id="emergency-cancel-all",
                reason=(
                    "Emergency cancel-all could not prove every broker order "
                    "received a cancellation request."
                ),
                seen_at=requested_at.isoformat(),
                details={
                    "reason": normalized_reason,
                    "book_scan_count": scans,
                    "unresolved_attempt_count": unresolved_attempt_count,
                    "requested_order_ids": sorted(requested_ids),
                },
            )

        result = {
            "requested_at": requested_at.isoformat(),
            "reason": normalized_reason,
            "kill_switch_active": True,
            "open_order_count": initial_order_count,
            "cancel_requested_count": len(canceled),
            "unmanaged_order_count": unmanaged,
            "canceled": canceled,
            "errors": errors,
            "book_scan_count": scans,
            "book_stable": book_stable,
            "final_open_order_count": final_open_order_count,
            "unresolved_attempt_count": unresolved_attempt_count,
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
    if (
        isinstance(min_absence_age_seconds, bool)
        or not isinstance(min_absence_age_seconds, (int, float))
        or not math.isfinite(min_absence_age_seconds)
        or min_absence_age_seconds < 0
    ):
        raise ValueError(
            "min_absence_age_seconds must be a finite, non-negative number, "
            f"got {min_absence_age_seconds!r}."
        )
    if broker_module is None:
        import execution.alpaca_broker as broker_module

    now = now or datetime.now(timezone.utc)
    proposals = store.list_proposals_by_statuses(RECONCILABLE_STATUSES)
    result: dict[str, Any] = {
        "checked": len(proposals),
        "updated": 0,
        "cancellation_requested": 0,
        "confirmed_absent": 0,
        "skipped_too_recent": 0,
        # Legacy "executed" rows the broker no longer returns. Counted, never
        # rewritten -- see the EXECUTED branch below.
        "legacy_unverifiable": 0,
        "errors": [],
    }
    for proposal in proposals:
        proposal_id = proposal["proposal_id"]
        try:
            order = broker_module.find_order_by_client_id(proposal["idempotency_key"])
            if order is None:
                if proposal["status"] in (SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING):
                    if not _absence_is_believable(
                        proposal, now=now, min_absence_age_seconds=min_absence_age_seconds,
                    ):
                        result["skipped_too_recent"] += 1
                        continue
                    transitioned = store.mark_submission_failed_and_release(
                        proposal_id,
                        expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                        reconciled_at=now.isoformat(),
                        error="Startup reconciliation: broker confirms no matching order exists.",
                        # Recheck age inside the SAME transaction that releases
                        # the reservation. The proposal snapshot above can go
                        # stale while the broker lookup is in flight.
                        not_updated_after=(
                            now - timedelta(seconds=min_absence_age_seconds)
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
            # An order that came back `replaced` is terminal for its own id;
            # the live state lives on the replacement. Follow the chain before
            # projecting anything, or a replacement whose stream event was
            # missed stays untracked even after it fills.
            resolution = _resolve_chain_for(proposal, order, broker_module)
            if resolution.error is not None:
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
            )
            result["updated"] += 1
            if resolution.followed_a_replacement:
                result["replacements_followed"] = result.get("replacements_followed", 0) + 1
            refreshed = store.get_proposal(proposal_id)
            if (
                cancel_stale
                and refreshed is not None
                # `authoritative`, NOT `order`: cancelling the SUPERSEDED order
                # left the live replacement running while the proposal was
                # projected to cancel_pending against the dead id -- and
                # reconciliation reported cancellation_requested=1 with no
                # errors, so it looked like it had worked (independent review,
                # 2026-07-29, reproduced: canceled order-1, order-2 still
                # active). Passing the authoritative order also makes the
                # staleness window, the cancel target, and the locally
                # projected pending_cancel record all use the live order.
                and _cancel_if_stale(
                    store,
                    refreshed,
                    authoritative,
                    broker_module=broker_module,
                    now=now,
                    max_order_age_minutes=max_order_age_minutes,
                )
            ):
                result["cancellation_requested"] += 1
        except Exception as exc:
            result["errors"].append({"proposal_id": proposal_id, "error": str(exc)})
    store.set_system_state(
        "last_order_reconciliation",
        {
            "at": now.isoformat(),
            "checked": result["checked"],
            "updated": result["updated"],
            "error_count": len(result["errors"]),
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
    if broker_module is None:
        import execution.alpaca_broker as broker_module
    if poll_interval_seconds <= 0 or reconnect_delay_seconds <= 0:
        raise ValueError("poll and reconnect intervals must be positive.")

    startup = reconcile_nonterminal_orders(
        store,
        broker_module=broker_module,
        cancel_stale=cancel_stale,
        max_order_age_minutes=max_order_age_minutes,
        min_absence_age_seconds=min_absence_age_seconds,
    )
    stop = stop_event or Event()

    def poll_loop() -> None:
        while not stop.wait(poll_interval_seconds):
            reconcile_nonterminal_orders(
                store,
                broker_module=broker_module,
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
                    broker_module.run_trade_update_stream(
                        lambda update: handle_trade_update(
                            store, update, broker_module=broker_module
                        ),
                        **_stream_stop_kwargs(broker_module, stop),
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
