"""Broker submission: sizing, budget reservation, dispatch, and journaling.

GR-1A extraction, extended in GR-1B with the pre-broker submission phases.
Deliberately narrow: this module may not import proposal-generation code
(pinned by tests/test_ml_import_boundary.py::
test_execution_kernel_never_reaches_proposal_generation). The submission
path executes a decision; it must never participate in making one.

Ordering within this module is load-bearing and deliberately not reordered
for tidiness:

    SUBMITTING fence -> reserve budget -> resolve dispatch -> telemetry
    -> broker call -> journal

The fence precedes the reservation so a crash between them leaves a row
recovery can prove never reached the broker. Telemetry precedes the broker
call so an unobserved order attempt is impossible -- a refused attempt is
far cheaper to recover than an unrecorded one.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, NoReturn

from assistant.execution_kernel.claim import transition_pre_broker_claim
from assistant.execution_kernel.errors import (
    ProposalClaimLostError,
    ProposalExecutionError,
)
from assistant.money import MoneyInput, exact_decimal_multiply, to_decimal
from assistant.order_lifecycle import (
    journal_broker_order_update,
    proposal_status_for_order,
)
from assistant.policy import TradingPolicy
from assistant.proposal_status import (
    BLOCKED,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
)
from assistant.storage import (
    AssistantStore,
    BrokerOrderBindingConflictError,
    JournalTransactionConflictError,
)
from risk.execution_gate import TradeIntent, worst_case_fill_price_decimal


def _execution_budget_notional(
    intent: TradeIntent, reference_price: MoneyInput
) -> Decimal:
    """Gross submitted notional reserved against the persistent daily cap.

    This intentionally uses the same side-aware price as the risk gate:
    an aggressive BUY limit is priced at the higher limit, while a SELL
    remains at the reference price so a risk-reducing order is not blocked
    merely because its limit is above the quote.
    """
    # SET1CR-004: `intent.shares` became `int | str` when fractional
    # quantities started travelling as canonical decimal text. Bare
    # `Decimal(<str>)` accepts "NaN"/"Infinity" and raises InvalidOperation --
    # an ArithmeticError, not a ValueError -- on malformed text, so it escapes
    # the ValueError handlers around this call. A NaN here would poison the
    # daily-budget reservation, which is precisely the FPS-001/CFPS-001 class
    # of defect this repository has already paid for three times. The intent
    # is validated before this runs; this is the defense-in-depth copy.
    return exact_decimal_multiply(
        to_decimal(intent.shares, name="intent.shares"),
        worst_case_fill_price_decimal(intent, reference_price),
        name="execution budget notional",
    )


def reserve_daily_budget(
    store: AssistantStore,
    proposal_id: str,
    intent: TradeIntent,
    reference_price: MoneyInput,
    policy: TradingPolicy,
    trading_day: str,
) -> None:
    """Hold this order's notional against the persistent daily caps.

    A refusal blocks through the fenced transition rather than a plain
    status write: this module's invariant is that every pre-broker
    transition is conditional on still owning the claim (independent
    review, 2026-07-31, P2 #2). ``ProposalClaimLostError`` is a
    ``ProposalExecutionError`` subclass, so a lost claim here propagates
    exactly like every other pre-broker failure.
    """
    try:
        store.reserve_execution_budget(
            proposal_id,
            trading_day=trading_day,
            notional=_execution_budget_notional(intent, reference_price),
            max_daily_notional=policy.max_daily_submitted_notional,
            max_daily_orders=policy.max_daily_order_count,
        )
    except Exception as exc:
        message = f"Persistent daily execution budget blocked submission: {exc}"
        transition_pre_broker_claim(
            store, proposal_id,
            expected_status=SUBMITTING, new_status=BLOCKED,
            violations=[message],
        )
        raise ProposalExecutionError(message) from exc


def resolve_submission_call(
    broker_module,
    store: AssistantStore,
    proposal_id: str,
    intent: TradeIntent,
    *,
    whole_shares_only: bool = True,
) -> tuple[Callable[..., Any], dict[str, Any]]:
    """Pick the broker call for this order type, or refuse and release.

    Dispatch explicitly rather than "limit, else market". Two upstream
    layers already prevent anything else reaching here (policy.validate()
    rejects an allowed_order_types outside SUPPORTED_ORDER_TYPES, and the
    allowed_order_types check during validation blocks the proposal), but
    risk/execution_gate.py's validate_trade_intent() DOES still approve
    order_type="stop" -- it is a lower layer with no view of policy. Under
    an else-branch such an intent would be silently submitted as a MARKET
    order, i.e. an unbounded-price order where a stop was intended. Fail
    closed instead, so adding a new order type can never silently degrade
    into a market order (independent review, 2026-07-29).
    """
    # Preserve compatibility with strict whole-share broker seams that predate
    # SET-1 (including operator tooling and test doubles): the broker adapter's
    # own default is strict, so only the newly-authorized fractional direction
    # needs an explicit keyword. This still fails closed if a future caller
    # forgets to pass the policy flag here.
    granularity_kwargs = (
        {} if whole_shares_only else {"whole_shares_only": False}
    )
    if intent.order_type == "limit":
        return broker_module.submit_limit_order, {
            "limit_price": intent.limit_price,
            **granularity_kwargs,
        }
    if intent.order_type == "market":
        return broker_module.submit_market_order, granularity_kwargs
    message = (
        f"No broker submission path implements order_type={intent.order_type!r}; refusing to "
        "submit rather than silently downgrading it to a market order."
    )
    # Independent review, 2026-07-31 (P2 #2): same fencing as the
    # budget-reservation-failure branch above.
    transition_pre_broker_claim(
        store, proposal_id,
        expected_status=SUBMITTING, new_status=BLOCKED,
        violations=[message],
    )
    store.release_execution_reservation(proposal_id)
    raise ProposalExecutionError(message)


def release_after_telemetry_failure(
    store: AssistantStore, proposal_id: str, exc: Exception
) -> NoReturn:
    """Atomically fail and release a reservation whose attempt went unrecorded.

    ``NoReturn`` documents the helper's contract: every current path raises
    after recording the failure. The facade also carries an independent
    bare-``raise`` guard, so a future edit that accidentally adds a normal
    return path here still cannot let a telemetry failure fall through to an
    order submission.

    The CALL to record_submission_started deliberately stays in
    ``assistant.execution_service``: tests and tooling monkeypatch that name
    on the facade module, and resolving it from this module's namespace
    instead would silently defeat every such patch. Only the failure
    HANDLING -- which is pure state management and has no such seam -- lives
    here. Frozen by
    test_pre_submit_telemetry_failure_releases_budget_without_broker_contact,
    which caught exactly that regression during GR-1B.
    """
    message = f"Execution telemetry failed before broker submission: {exc}"
    failed = store.mark_submission_failed_and_release(
        proposal_id,
        expected_statuses=(SUBMITTING,),
        error=message,
    )
    if failed is None:
        raise ProposalClaimLostError(
            f"Proposal {proposal_id} changed state before telemetry failure could be recorded."
        ) from exc
    raise ProposalExecutionError(message) from exc


def journal_accepted_order(
    store: AssistantStore,
    proposal_id: str,
    order: dict,
) -> dict:
    """Record an order the broker DID accept; never report a local failure
    as a submission failure.

    The broker returned normally, so the order genuinely exists. A failure
    here is only in our local journal write -- reporting it as a submission
    failure would misrepresent a live order. Keep the order info in
    ``error`` so it can be reconciled or re-journaled manually.
    """
    try:
        journal_broker_order_update(
            store,
            proposal_id,
            order,
            event_type="submission_response",
        )
    except (BrokerOrderBindingConflictError, JournalTransactionConflictError):
        # Storage already retained the original broker root/event, parked the
        # ambiguity where applicable, and activated global containment. The
        # compatibility fallback below must never overwrite that retained
        # authority with the incoming colliding order.
        raise
    except Exception as exc:
        store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
            new_status=proposal_status_for_order(order),
            broker_order=order,
            broker_status=str(order.get("status", "unknown")),
            error=f"Order was accepted by the broker but local recording failed: {exc}",
        )
    return order
