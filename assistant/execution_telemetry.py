"""Lossless execution-attempt telemetry for later ML analysis.

Only pre-broker facts are written here. Once an order exists, the existing
``broker_order_events`` journal remains the authoritative lifecycle source;
``materialize_execution_attempt`` joins the two without creating a second
mutable order history.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from assistant.storage import AssistantStore


SCHEMA_VERSION = "1.1"

# Why an execution attempt did not proceed. These are training labels as much
# as operational states: collapsing an infrastructure fault into
# "policy_refusal" teaches a later execution-quality model that the policy
# declined trades the policy actually approved. Every value must be
# distinguishable without parsing an error string.
FAILURE_NONE = "none"
#: validate_trade_intent() or an explicit policy rule refused the trade.
FAILURE_DETERMINISTIC_POLICY = "deterministic_policy"
#: A dependency was unavailable or errored -- broker, quote source, market
#: calendar, exposure computation, or the telemetry store itself.
FAILURE_INFRASTRUCTURE = "infrastructure"
#: Stored data was missing or malformed, so no decision could be made.
FAILURE_DATA_INTEGRITY = "data_integrity"
#: A submission was sent but its outcome is unknown. Never a rejection.
FAILURE_BROKER_AMBIGUOUS = "broker_ambiguous"

FAILURE_CLASSES = frozenset({
    FAILURE_NONE,
    FAILURE_DETERMINISTIC_POLICY,
    FAILURE_INFRASTRUCTURE,
    FAILURE_DATA_INTEGRITY,
    FAILURE_BROKER_AMBIGUOUS,
})


def execution_attempt_id(proposal_id: str, attempted_at: str) -> str:
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ValueError("proposal_id must be a non-empty string")
    parsed = _aware(attempted_at, "attempted_at")
    material = f"{proposal_id.strip()}\n{parsed.isoformat()}"
    return "exec-attempt-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _aware(value: Any, name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _number_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return _number_text(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("telemetry datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _intent_payload(intent: Any) -> dict[str, Any] | None:
    if intent is None:
        return None
    raw = dataclasses.asdict(intent) if dataclasses.is_dataclass(intent) else dict(intent)
    return {
        "ticker": str(raw.get("ticker") or "").upper() or None,
        "side": raw.get("side"),
        "requested_qty": _number_text(raw.get("shares")),
        "order_type": raw.get("order_type"),
        "limit_price": _number_text(raw.get("limit_price")),
    }


def _preflight_payload(preflight: dict[str, Any] | None) -> dict[str, Any]:
    preflight = preflight or {}
    account = preflight.get("account") or {}
    asset = preflight.get("asset") or {}
    return {
        "account": {
            "account_id": account.get("account_id"),
            "paper": account.get("paper") if isinstance(account.get("paper"), bool) else None,
            "status": account.get("status"),
        },
        "asset": {
            "ticker": asset.get("ticker") or asset.get("symbol"),
            "status": asset.get("status"),
            "tradable": asset.get("tradable") if isinstance(asset.get("tradable"), bool) else None,
        },
    }


def _account_identity(preflight: dict[str, Any] | None) -> tuple[str, str | None]:
    account = (preflight or {}).get("account") or {}
    paper = account.get("paper")
    mode = "paper" if paper is True else "live" if paper is False else "unavailable"
    account_id = account.get("account_id")
    return mode, str(account_id) if account_id not in (None, "") else None


def _quote_payload(quote: dict[str, Any] | None, received_at: str | None) -> dict[str, Any]:
    if not quote:
        return {
            "available": False,
            "unavailable_reason": "quote was not reached or the quote request failed",
            "observed_at": None,
            "received_at": received_at,
            "price": None,
            "bid": None,
            "ask": None,
            "spread": None,
            "spread_pct": None,
            "quote_age_ms": None,
        }
    observed_raw = quote.get("timestamp")
    observed_at = (
        observed_raw.isoformat()
        if isinstance(observed_raw, datetime)
        else observed_raw
    )
    bid_text = _number_text(quote.get("bid_decimal", quote.get("bid")))
    ask_text = _number_text(quote.get("ask_decimal", quote.get("ask")))
    spread_text = spread_pct_text = None
    if bid_text is not None and ask_text is not None:
        bid = Decimal(bid_text)
        ask = Decimal(ask_text)
        midpoint = (bid + ask) / 2
        if ask >= bid and midpoint > 0:
            spread = ask - bid
            spread_text = _number_text(spread)
            spread_pct_text = _number_text(spread / midpoint * Decimal("100"))
    quote_age_ms = None
    if observed_at and received_at:
        try:
            delta = _aware(received_at, "quote_received_at") - _aware(observed_at, "quote timestamp")
            quote_age_ms = round(delta.total_seconds() * 1000, 3)
        except ValueError:
            quote_age_ms = None
    return {
        "available": True,
        "unavailable_reason": None,
        "observed_at": observed_at,
        "received_at": received_at,
        "price": _number_text(quote.get("price_decimal", quote.get("price"))),
        "bid": bid_text,
        "ask": ask_text,
        "spread": spread_text,
        "spread_pct": spread_pct_text,
        "quote_age_ms": quote_age_ms,
    }


def record_validation_outcome(
    store: AssistantStore,
    *,
    attempt_id: str,
    proposal_id: str,
    attempted_at: str,
    outcome: Any,
) -> dict[str, Any]:
    validation = outcome.validation
    failure_class = getattr(
        outcome, "resolved_failure_class", FAILURE_DETERMINISTIC_POLICY
    )
    if outcome.error is not None:
        event_type = "validation_refused"
        # "service_refusal" previously covered a broker outage, a corrupt
        # stored intent, and a policy rule alike. The result now names the
        # actual class so an infrastructure fault is never counted as the
        # policy declining a trade.
        result = failure_class
    elif validation is not None and validation.approved:
        event_type = "validation_approved"
        result = "approved"
        failure_class = FAILURE_NONE
    elif validation is not None and validation.overridable:
        event_type = "validation_override_available"
        result = "override_available"
        failure_class = FAILURE_NONE
    else:
        event_type = "validation_refused"
        result = "policy_refusal"
        failure_class = FAILURE_DETERMINISTIC_POLICY
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"unknown execution failure class {failure_class!r}")
    preflight = _preflight_payload(outcome.broker_preflight)
    account_mode, account_id = _account_identity(outcome.broker_preflight)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "result": result,
        "failure_class": failure_class,
        "intent": _intent_payload(outcome.intent),
        "reference_price": _number_text(outcome.reference_price),
        "quote": _quote_payload(outcome.quote, outcome.quote_received_at),
        "broker_preflight": preflight,
        "violations": list(validation.violations) if validation is not None else [],
        "violation_codes": list(validation.violation_codes) if validation is not None else [],
        "error": outcome.error,
        "market_context": {
            "recent_volume": {"available": False, "reason": "not provided by the current quote source"},
            "liquidity_bucket": {"available": False, "reason": "not derivable without volume/depth data"},
        },
    }
    return store.append_execution_telemetry_event(
        attempt_id=attempt_id,
        proposal_id=proposal_id,
        event_type=event_type,
        event_at=attempted_at,
        account_mode=account_mode,
        broker_account_id=account_id,
        source="alpaca_execution_validation",
        payload=_json_safe(payload),
    )


def record_validation_exception(
    store: AssistantStore,
    *,
    attempt_id: str,
    proposal_id: str,
    event_at: str,
    error: str,
) -> dict[str, Any]:
    """Record an unexpected failure before a validation result existed."""
    return store.append_execution_telemetry_event(
        attempt_id=attempt_id,
        proposal_id=proposal_id,
        event_type="validation_failed",
        event_at=event_at,
        account_mode="unavailable",
        broker_account_id=None,
        source="alpaca_execution_validation",
        payload={
            "schema_version": SCHEMA_VERSION,
            "result": "validation_failed",
            # An unexpected exception before a validation result existed is
            # never the policy declining a trade.
            "failure_class": FAILURE_INFRASTRUCTURE,
            "error": str(error),
            "intent": None,
            "reference_price": None,
            "quote": _quote_payload(None, None),
            "broker_preflight": _preflight_payload(None),
            "violations": [],
            "violation_codes": [],
            "market_context": {
                "recent_volume": {"available": False, "reason": "validation did not complete"},
                "liquidity_bucket": {"available": False, "reason": "validation did not complete"},
            },
        },
    )


def record_submission_started(
    store: AssistantStore,
    *,
    attempt_id: str,
    proposal_id: str,
    submitted_at: str,
    outcome: Any,
) -> dict[str, Any]:
    account_mode, account_id = _account_identity(outcome.broker_preflight)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "intent": _intent_payload(outcome.intent),
        "reference_price": _number_text(outcome.reference_price),
        "quote": _quote_payload(outcome.quote, outcome.quote_received_at),
        "client_order_id": (outcome.proposal or {}).get("idempotency_key"),
    }
    return store.append_execution_telemetry_event(
        attempt_id=attempt_id,
        proposal_id=proposal_id,
        event_type="submission_started",
        event_at=submitted_at,
        account_mode=account_mode,
        broker_account_id=account_id,
        source="alpaca_execution_service",
        payload=_json_safe(payload),
    )


def _event_order_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    if isinstance(payload.get("order"), dict):
        return payload["order"]
    return payload if isinstance(payload, dict) else {}


def _limit_distance(intent: dict[str, Any] | None, arrival_price: Any) -> dict[str, Any]:
    intent = intent or {}
    if intent.get("order_type") != "limit":
        return {
            "available": False,
            "reason": "order type is not limit",
            "signed_price": None,
            "pct_of_arrival": None,
        }
    limit_text = _number_text(intent.get("limit_price"))
    arrival_text = _number_text(arrival_price)
    if limit_text is None or arrival_text is None or Decimal(arrival_text) <= 0:
        return {
            "available": False,
            "reason": "limit or arrival price is unavailable",
            "signed_price": None,
            "pct_of_arrival": None,
        }
    distance = Decimal(limit_text) - Decimal(arrival_text)
    return {
        "available": True,
        "reason": None,
        "signed_price": _number_text(distance),
        "pct_of_arrival": _number_text(distance / Decimal(arrival_text) * Decimal("100")),
    }


def materialize_execution_attempt(store: AssistantStore, attempt_id: str) -> dict[str, Any]:
    """Build one analysis-ready record without mutating either journal."""
    telemetry = store.list_execution_telemetry_events(attempt_id=attempt_id)
    if not telemetry:
        raise KeyError(f"Unknown execution attempt: {attempt_id}")
    proposal_ids = {event["proposal_id"] for event in telemetry}
    if len(proposal_ids) != 1:
        raise ValueError(f"Execution attempt {attempt_id} spans multiple proposals")
    proposal_id = next(iter(proposal_ids))
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"Unknown proposal for execution attempt: {proposal_id}")
    validation = next((e for e in telemetry if e["event_type"].startswith("validation_")), None)
    submission = next((e for e in telemetry if e["event_type"] == "submission_started"), None)
    # A proposal can have an override-review attempt followed by a separate
    # approved attempt. Only the latter reaches submission; attaching its
    # later broker events to the earlier review would create false training
    # rows. Proposal lifecycle evidence belongs only to the attempt with the
    # pre-broker submission marker.
    broker_events = (
        store.list_broker_order_events(proposal_id=proposal_id)
        if submission is not None
        else []
    )
    account_modes = {e["account_mode"] for e in telemetry}
    account_ids = {e["broker_account_id"] for e in telemetry if e["broker_account_id"]}
    if len(account_modes) != 1 or len(account_ids) > 1:
        raise ValueError(f"Execution attempt {attempt_id} has inconsistent account identity")

    fills = []
    replacements: list[dict[str, str]] = []
    cancellation_at = acknowledgement_at = None
    order_ids: list[str] = []
    terminal_statuses = {"filled", "canceled", "cancelled", "rejected", "expired"}
    terminal = False
    for event in broker_events:
        order_id = str(event["order_id"])
        if order_id not in order_ids:
            order_ids.append(order_id)
        if acknowledgement_at is None:
            acknowledgement_at = event["event_at"]
        status = str(event.get("status") or "").lower()
        event_type = str(event.get("event_type") or "").lower()
        terminal = terminal or status in terminal_statuses
        if status in {"canceled", "cancelled"} or "cancel" in event_type:
            cancellation_at = event["event_at"]
        if event.get("fill_qty") is not None or (
            event.get("filled_qty") is not None and float(event["filled_qty"]) > 0
        ):
            fills.append({
                "event_at": event["event_at"],
                "order_id": order_id,
                "incremental_qty": _number_text(event.get("fill_qty")),
                "incremental_price": _number_text(event.get("fill_price")),
                "cumulative_qty": _number_text(event.get("filled_qty")),
                "cumulative_avg_price": _number_text(event.get("filled_avg_price")),
            })
        order = _event_order_payload(event)
        if order.get("replaced_by"):
            replacements.append({
                "from_order_id": order_id,
                "to_order_id": str(order["replaced_by"]),
                "at": event["event_at"],
            })
        elif order.get("replaces"):
            replacements.append({
                "from_order_id": str(order["replaces"]),
                "to_order_id": order_id,
                "at": event["event_at"],
            })

    validation_payload = validation["payload"] if validation else {}
    quote = validation_payload.get("quote") or {}
    unavailable = []
    if not validation:
        unavailable.append({"field": "validation", "reason": "validation event is missing"})
    elif "failure_class" not in validation_payload:
        # Schema 1.0 events predate the explicit taxonomy. Do not infer a
        # training label from error text or collapse a legacy service refusal
        # into deterministic policy.
        unavailable.append({
            "field": "validation.failure_class",
            "reason": "validation event predates failure classification",
        })
    if not submission:
        unavailable.append({"field": "submission", "reason": "attempt stopped before broker submission"})
    if not broker_events:
        unavailable.append({"field": "broker_lifecycle", "reason": "no broker acknowledgement has been journaled"})
    unavailable.extend([
        {"field": "recent_volume", "reason": "not provided by the current quote source"},
        {"field": "liquidity_bucket", "reason": "not derivable without volume/depth data"},
        # FCS-009: listed as unavailable rather than published as a zero.
        {
            "field": "delay_cost",
            "reason": (
                "decision and arrival price derive from one validation-time "
                "quote; no second quote is taken at dispatch"
            ),
        },
    ])
    intent = validation_payload.get("intent") or proposal.get("intent")
    limit_distance = _limit_distance(intent, quote.get("price"))
    if not limit_distance["available"]:
        unavailable.append({"field": "limit_distance", "reason": limit_distance["reason"]})
    return {
        "schema_version": SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "proposal_id": proposal_id,
        "account": {
            "mode": next(iter(account_modes)),
            "broker_account_id": next(iter(account_ids), None),
            "pool_paper_and_live": False,
        },
        "decision": {"at": proposal.get("created_at"), "intent": intent},
        "validation": {
            "event_type": validation["event_type"] if validation else None,
            "result": validation_payload.get("result"),
            "failure_class": validation_payload.get("failure_class"),
            "violations": validation_payload.get("violations") or [],
            "violation_codes": validation_payload.get("violation_codes") or [],
            "error": validation_payload.get("error"),
        },
        "quote": quote,
        "submission": {"started_at": submission["event_at"] if submission else None},
        "lifecycle": {
            "acknowledgement_at": acknowledgement_at,
            "order_ids": order_ids,
            "events": broker_events,
            "fills": fills,
            "cancellation_at": cancellation_at,
            "replacements": replacements,
            "terminal": terminal,
        },
        "prices": {
            "decision": validation_payload.get("reference_price"),
            "arrival": quote.get("price"),
            # FCS-009: `decision` and `arrival` are the SAME observation, not
            # two measurements. `reference_price` is assigned from
            # `quote.get("price_decimal", quote["price"])` in
            # execution_kernel/validate.py, which is exactly what the quote
            # payload's `price` is built from -- so implementation shortfall's
            # DELAY component (decision -> arrival) is identically zero here by
            # construction, an artifact of the schema rather than a fact about
            # execution. Measuring it needs a second quote taken at dispatch,
            # which this project does not currently take. Stated in the record
            # itself because ML-9 is explicitly gated on this dataset being
            # representative, and a silent zero would train that gate to
            # believe there is no delay cost to model. Same discipline as the
            # `recent_volume` / `liquidity_bucket` unavailability notes.
            "decision_and_arrival_are_the_same_observation": True,
            "delay_cost_measurable": False,
            "delay_cost_unavailable_reason": (
                "decision and arrival price derive from one validation-time "
                "quote; no second quote is taken at dispatch"
            ),
            "fills": [fill.get("incremental_price") or fill.get("cumulative_avg_price") for fill in fills],
            "limit_distance": limit_distance,
        },
        "unavailable_fields": unavailable,
        "source_event_ids": {
            "execution_telemetry": [e["telemetry_event_id"] for e in telemetry],
            "broker_lifecycle": [e["event_id"] for e in broker_events],
        },
        "analysis_ready": validation is not None,
        "materialized_at": datetime.now(timezone.utc).isoformat(),
    }


def materialized_record_hash(record: dict[str, Any]) -> str:
    """Stable lineage hash excluding the intentionally variable build time."""
    canonical = dict(record)
    canonical.pop("materialized_at", None)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
