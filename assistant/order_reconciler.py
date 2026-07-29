"""Broker order reconciliation via startup polling and trade-update stream."""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any

from assistant.execution_service import (
    ProposalExecutionError,
    _intent_from_dict,
    _order_matches_intent,
)
from assistant.order_lifecycle import journal_broker_order_update
from assistant.proposal_status import (
    BROKER_ACCEPTED,
    CANCEL_PENDING,
    EXECUTED,
    PARTIALLY_FILLED,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
)
from assistant.storage import AssistantStore

_STREAM_SHUTDOWN_POLL_SECONDS = 0.1


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
        store.set_kill_switch(True, reason=f"Malformed intent during reconciliation: {exc}")
        raise ProposalExecutionError(
            f"Malformed stored intent for {proposal.get('proposal_id')}: {exc}"
        ) from exc
    matches, detail = _order_matches_intent(order, intent)
    if not matches:
        reason = (
            f"Broker reconciliation identity mismatch for {proposal['proposal_id']}: {detail}. "
            "Persistent kill switch activated."
        )
        store.update_proposal_status_if_current(
            proposal["proposal_id"],
            expected_statuses=RECONCILABLE_STATUSES,
            new_status=SUBMISSION_UNKNOWN,
            error=reason,
        )
        store.set_kill_switch(True, reason=reason)
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


def handle_trade_update(store: AssistantStore, update: dict[str, Any]) -> dict[str, Any] | None:
    """Process one normalized Alpaca trade-update message."""
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
    result = apply_broker_update(
        store,
        proposal,
        order,
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


def reconcile_nonterminal_orders(
    store: AssistantStore,
    *,
    broker_module=None,
    now: datetime | None = None,
    cancel_stale: bool = False,
    max_order_age_minutes: float = 30.0,
) -> dict[str, Any]:
    """Poll all nonterminal proposals once and optionally cancel stale orders."""
    if broker_module is None:
        import execution.alpaca_broker as broker_module

    now = now or datetime.now(timezone.utc)
    proposals = store.list_proposals_by_statuses(RECONCILABLE_STATUSES)
    result: dict[str, Any] = {
        "checked": len(proposals),
        "updated": 0,
        "cancellation_requested": 0,
        "confirmed_absent": 0,
        "errors": [],
    }
    for proposal in proposals:
        proposal_id = proposal["proposal_id"]
        try:
            order = broker_module.find_order_by_client_id(proposal["idempotency_key"])
            if order is None:
                if proposal["status"] in (SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING):
                    transitioned = store.mark_submission_failed_and_release(
                        proposal_id,
                        expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                        reconciled_at=now.isoformat(),
                        error="Startup reconciliation: broker confirms no matching order exists.",
                    )
                    if transitioned is not None:
                        result["confirmed_absent"] += 1
                else:
                    # A once-known active order disappearing from a lookup is
                    # anomalous; do not reinterpret that as a clean failure.
                    store.update_proposal_status_if_current(
                        proposal_id,
                        expected_statuses=(
                            BROKER_ACCEPTED,
                            PARTIALLY_FILLED,
                            CANCEL_PENDING,
                            EXECUTED,
                        ),
                        new_status=SUBMISSION_UNKNOWN,
                        error=(
                            "A previously known broker order could not be found during reconciliation; "
                            "manual investigation is required."
                        ),
                    )
                continue
            apply_broker_update(
                store,
                proposal,
                order,
                event_type="poll_reconciliation",
            )
            result["updated"] += 1
            refreshed = store.get_proposal(proposal_id)
            if (
                cancel_stale
                and refreshed is not None
                and _cancel_if_stale(
                    store,
                    refreshed,
                    order,
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
    )
    stop = stop_event or Event()

    def poll_loop() -> None:
        while not stop.wait(poll_interval_seconds):
            reconcile_nonterminal_orders(
                store,
                broker_module=broker_module,
                cancel_stale=cancel_stale,
                max_order_age_minutes=max_order_age_minutes,
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
                        lambda update: handle_trade_update(store, update),
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
        poller.join(timeout=min(poll_interval_seconds, 2.0))
        store.set_system_state(
            "trade_stream_state",
            {
                "running": False,
                "stopped_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
            },
        )
    return startup
