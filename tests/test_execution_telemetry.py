from __future__ import annotations

import json
import sqlite3

from assistant.execution_telemetry import (
    FAILURE_DETERMINISTIC_POLICY,
    FAILURE_INFRASTRUCTURE,
    execution_attempt_id,
    materialize_execution_attempt,
    materialized_record_hash,
    record_validation_exception,
    record_validation_outcome,
)
from assistant.order_lifecycle import journal_broker_order_update
from assistant.storage import AssistantStore


def _proposal(proposal_id: str, *, status: str = "submitting") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-08-01T14:29:00+00:00",
        "expires_at": "2026-08-01T15:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 3,
            "order_type": "limit",
            "limit_price": 100.25,
        },
    }


def _validation_payload() -> dict:
    return {
        "schema_version": "1.0",
        "result": "approved",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "requested_qty": "3",
            "order_type": "limit",
            "limit_price": "100.25",
        },
        "reference_price": "100.10",
        "quote": {
            "available": True,
            "unavailable_reason": None,
            "observed_at": "2026-08-01T14:29:59.500000+00:00",
            "received_at": "2026-08-01T14:30:00+00:00",
            "price": "100.10",
            "bid": "100.00",
            "ask": "100.20",
            "spread": "0.20",
            "spread_pct": "0.1998001998001998001998001998",
            "quote_age_ms": 500.0,
        },
        "violations": [],
        "violation_codes": [],
        "error": None,
    }


def _append_attempt(
    store: AssistantStore,
    proposal_id: str,
    attempt_id: str,
    *,
    account_mode: str = "paper",
    account_id: str = "paper-account-1",
) -> None:
    store.append_execution_telemetry_event(
        attempt_id=attempt_id,
        proposal_id=proposal_id,
        event_type="validation_approved",
        event_at="2026-08-01T14:30:00+00:00",
        account_mode=account_mode,
        broker_account_id=account_id,
        source="test_validation",
        payload=_validation_payload(),
    )
    store.append_execution_telemetry_event(
        attempt_id=attempt_id,
        proposal_id=proposal_id,
        event_type="submission_started",
        event_at="2026-08-01T14:30:01+00:00",
        account_mode=account_mode,
        broker_account_id=account_id,
        source="test_execution",
        payload={"schema_version": "1.0", "client_order_id": f"idem-{proposal_id}"},
    )


def test_execution_telemetry_append_is_content_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    proposal_id = "proposal-idempotent"
    store.save_proposal(_proposal(proposal_id))
    arguments = dict(
        attempt_id="attempt-idempotent",
        proposal_id=proposal_id,
        event_type="validation_approved",
        event_at="2026-08-01T14:30:00+00:00",
        account_mode="paper",
        broker_account_id="paper-account-1",
        source="test_validation",
        payload=_validation_payload(),
    )

    first = store.append_execution_telemetry_event(**arguments)
    repeated = store.append_execution_telemetry_event(**arguments)

    assert first["inserted"] is True
    assert repeated["inserted"] is False
    assert repeated["telemetry_event_id"] == first["telemetry_event_id"]
    assert len(store.list_execution_telemetry_events(attempt_id="attempt-idempotent")) == 1


def test_schema_upgrade_adds_telemetry_without_changing_existing_proposals(tmp_path):
    database = tmp_path / "assistant.db"
    original = _proposal("proposal-before-upgrade")
    store = AssistantStore(database)
    store.save_proposal(original)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE execution_telemetry_events")

    upgraded = AssistantStore(database)

    assert upgraded.get_proposal(original["proposal_id"])["intent"] == original["intent"]
    event = upgraded.append_execution_telemetry_event(
        attempt_id="attempt-after-upgrade",
        proposal_id=original["proposal_id"],
        event_type="validation_approved",
        event_at="2026-08-01T14:30:00+00:00",
        account_mode="paper",
        broker_account_id="paper-account-1",
        source="test_upgrade",
        payload=_validation_payload(),
    )
    assert event["inserted"] is True


def test_materializer_joins_authoritative_broker_lifecycle(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    proposal_id = "proposal-lifecycle"
    attempt_id = "attempt-lifecycle"
    store.save_proposal(_proposal(proposal_id))
    _append_attempt(store, proposal_id, attempt_id)

    original = {
        "order_id": "order-original",
        "client_order_id": f"idem-{proposal_id}",
        "ticker": "AAPL",
        "shares": 3,
        "side": "buy",
        "type": "limit",
        "limit_price": 100.25,
        "status": "accepted",
        "filled_qty": 0,
        "filled_avg_price": None,
        "submitted_at": "2026-08-01T14:30:01.100000+00:00",
        "updated_at": "2026-08-01T14:30:01.200000+00:00",
    }
    journal_broker_order_update(
        store, proposal_id, original,
        event_type="accepted", external_event_id="event-accepted-original",
    )
    journal_broker_order_update(
        store,
        proposal_id,
        {
            **original,
            "status": "replaced",
            "replaced_by": "order-replacement",
            "updated_at": "2026-08-01T14:30:02+00:00",
        },
        event_type="replaced",
        external_event_id="event-replaced",
    )
    replacement = {
        **original,
        "order_id": "order-replacement",
        "status": "accepted",
        "replaces": "order-original",
        "submitted_at": "2026-08-01T14:30:02+00:00",
        "updated_at": "2026-08-01T14:30:02.100000+00:00",
    }
    journal_broker_order_update(
        store, proposal_id, replacement,
        event_type="accepted", external_event_id="event-accepted-replacement",
    )
    journal_broker_order_update(
        store,
        proposal_id,
        {
            **replacement,
            "status": "partially_filled",
            "filled_qty": 1,
            "filled_avg_price": 100.11,
            "updated_at": "2026-08-01T14:30:03+00:00",
        },
        event_type="partial_fill",
        external_event_id="event-partial",
        fill_qty=1,
        fill_price=100.11,
    )
    journal_broker_order_update(
        store,
        proposal_id,
        {
            **replacement,
            "status": "filled",
            "filled_qty": 3,
            "filled_avg_price": 100.12,
            "filled_at": "2026-08-01T14:30:04+00:00",
            "updated_at": "2026-08-01T14:30:04+00:00",
        },
        event_type="fill",
        external_event_id="event-filled",
        fill_qty=2,
        fill_price=100.125,
    )

    first = materialize_execution_attempt(store, attempt_id)
    second = materialize_execution_attempt(store, attempt_id)

    assert first["account"] == {
        "mode": "paper",
        "broker_account_id": "paper-account-1",
        "pool_paper_and_live": False,
    }
    assert first["submission"]["started_at"] == "2026-08-01T14:30:01+00:00"
    assert first["lifecycle"]["acknowledgement_at"] == "2026-08-01T14:30:01.200000+00:00"
    assert first["lifecycle"]["terminal"] is True
    assert first["lifecycle"]["order_ids"] == ["order-original", "order-replacement"]
    assert len(first["lifecycle"]["fills"]) == 2
    assert {
        "from_order_id": "order-original",
        "to_order_id": "order-replacement",
        "at": "2026-08-01T14:30:02+00:00",
    } in first["lifecycle"]["replacements"]
    assert first["quote"]["quote_age_ms"] == 500.0
    assert first["prices"]["limit_distance"] == {
        "available": True,
        "reason": None,
        "signed_price": "0.15",
        "pct_of_arrival": "0.1498501498501498501498501499",
    }
    assert {item["field"] for item in first["unavailable_fields"]} >= {
        "recent_volume",
        "liquidity_bucket",
    }
    assert first["analysis_ready"] is True
    assert materialized_record_hash(first) == materialized_record_hash(second)


def test_non_submitting_override_attempt_does_not_inherit_later_broker_events(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    proposal_id = "proposal-reviewed-then-submitted"
    store.save_proposal(_proposal(proposal_id))
    store.append_execution_telemetry_event(
        attempt_id="attempt-review-only",
        proposal_id=proposal_id,
        event_type="validation_override_available",
        event_at="2026-08-01T14:29:50+00:00",
        account_mode="paper",
        broker_account_id="paper-account-1",
        source="test_validation",
        payload={**_validation_payload(), "result": "override_available"},
    )
    _append_attempt(store, proposal_id, "attempt-that-submitted")
    journal_broker_order_update(
        store,
        proposal_id,
        {
            "order_id": "order-after-review",
            "client_order_id": f"idem-{proposal_id}",
            "ticker": "AAPL",
            "shares": 3,
            "side": "buy",
            "type": "limit",
            "limit_price": 100.25,
            "status": "accepted",
            "filled_qty": 0,
            "filled_avg_price": None,
            "submitted_at": "2026-08-01T14:30:01+00:00",
            "updated_at": "2026-08-01T14:30:01.100000+00:00",
        },
        event_type="accepted",
        external_event_id="event-after-review",
    )

    review_only = materialize_execution_attempt(store, "attempt-review-only")
    submitted = materialize_execution_attempt(store, "attempt-that-submitted")

    assert review_only["lifecycle"]["events"] == []
    assert review_only["lifecycle"]["acknowledgement_at"] is None
    assert submitted["lifecycle"]["acknowledgement_at"] == "2026-08-01T14:30:01.100000+00:00"


def test_paper_and_live_attempts_remain_separate(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal("proposal-paper"))
    store.save_proposal(_proposal("proposal-live"))
    _append_attempt(store, "proposal-paper", "attempt-paper")
    _append_attempt(
        store,
        "proposal-live",
        "attempt-live",
        account_mode="live",
        account_id="live-account-1",
    )

    paper = materialize_execution_attempt(store, "attempt-paper")
    live = materialize_execution_attempt(store, "attempt-live")

    assert paper["account"]["mode"] == "paper"
    assert live["account"]["mode"] == "live"
    assert paper["account"]["broker_account_id"] != live["account"]["broker_account_id"]
    assert paper["account"]["pool_paper_and_live"] is False
    assert live["account"]["pool_paper_and_live"] is False


def _outcome(**kwargs):
    """Minimal ProposalValidationOutcome, built through the real class."""
    from assistant.execution_service import ProposalValidationOutcome

    defaults = dict(proposal=None, intent=None, validation=None, error=None)
    defaults.update(kwargs)
    return ProposalValidationOutcome(**defaults)


def test_infrastructure_failure_is_not_recorded_as_a_policy_rejection(tmp_path):
    """A broker outage and a policy refusal must not share a label.

    Both are trading-safe -- both refuse -- but an execution-quality model
    trained on this journal would otherwise learn that the policy declines
    trades the policy actually approved.
    """
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal("p-infra"))

    outcome = _outcome(
        error="Broker account/asset preflight failed: connection reset",
        failure_class=FAILURE_INFRASTRUCTURE,
    )
    assert outcome.resolved_failure_class == FAILURE_INFRASTRUCTURE

    event = record_validation_outcome(
        store,
        attempt_id=execution_attempt_id("p-infra", "2026-08-01T14:30:00+00:00"),
        proposal_id="p-infra",
        attempted_at="2026-08-01T14:30:00+00:00",
        outcome=outcome,
    )
    payload = json.loads(event["payload_json"]) if "payload_json" in event else event["payload"]
    assert payload["failure_class"] == FAILURE_INFRASTRUCTURE
    assert payload["failure_class"] != FAILURE_DETERMINISTIC_POLICY
    assert payload["result"] != "policy_refusal"

    materialized = materialize_execution_attempt(store, event["attempt_id"])
    assert materialized["validation"] == {
        "event_type": "validation_refused",
        "result": FAILURE_INFRASTRUCTURE,
        "failure_class": FAILURE_INFRASTRUCTURE,
        "violations": [],
        "violation_codes": [],
        "error": "Broker account/asset preflight failed: connection reset",
    }
    assert not any(
        item["field"] == "validation.failure_class"
        for item in materialized["unavailable_fields"]
    )


def test_unclassified_service_error_defaults_to_deterministic_policy(tmp_path):
    """An unlabelled refusal stays in the conservative bucket."""
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal("p-plain"))
    outcome = _outcome(error="Proposal has expired.")
    assert outcome.resolved_failure_class == FAILURE_DETERMINISTIC_POLICY

    event = record_validation_outcome(
        store,
        attempt_id=execution_attempt_id("p-plain", "2026-08-01T14:30:00+00:00"),
        proposal_id="p-plain",
        attempted_at="2026-08-01T14:30:00+00:00",
        outcome=outcome,
    )
    payload = json.loads(event["payload_json"]) if "payload_json" in event else event["payload"]
    assert payload["failure_class"] == FAILURE_DETERMINISTIC_POLICY


def test_validation_exception_is_infrastructure_not_policy(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal("p-exc"))
    event = record_validation_exception(
        store,
        attempt_id=execution_attempt_id("p-exc", "2026-08-01T14:30:00+00:00"),
        proposal_id="p-exc",
        event_at="2026-08-01T14:30:00+00:00",
        error="disk full",
    )
    payload = json.loads(event["payload_json"]) if "payload_json" in event else event["payload"]
    assert payload["failure_class"] == FAILURE_INFRASTRUCTURE


def test_legacy_attempt_does_not_invent_a_failure_class(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal("p-legacy"))
    store.append_execution_telemetry_event(
        attempt_id="attempt-legacy",
        proposal_id="p-legacy",
        event_type="validation_refused",
        event_at="2026-07-31T14:30:00+00:00",
        account_mode="paper",
        broker_account_id="paper-account-1",
        source="legacy-test",
        payload={"schema_version": "1.0", "result": "service_refusal"},
    )

    materialized = materialize_execution_attempt(store, "attempt-legacy")
    assert materialized["validation"]["failure_class"] is None
    assert {
        "field": "validation.failure_class",
        "reason": "validation event predates failure classification",
    } in materialized["unavailable_fields"]


# --------------------------------------------------------------------------
# FCS-009: the record must not imply a delay-cost measurement it cannot make.
# --------------------------------------------------------------------------

def test_decision_and_arrival_price_are_declared_to_be_one_observation():
    """Both fields come from the same validation-time quote.

    `reference_price` is assigned from `quote.get("price_decimal",
    quote["price"])`, which is what the telemetry quote payload's `price` is
    built from -- so implementation shortfall's DELAY component is identically
    zero by construction. ML-9 is gated on this dataset being representative;
    a silent zero would teach that gate there is nothing to model.
    """
    import inspect

    from assistant.execution_kernel import validate as validate_module

    validate_source = inspect.getsource(validate_module)
    assert 'reference_price = quote.get("price_decimal", quote["price"])' in validate_source, (
        "the provenance this test reasons about changed; re-check whether "
        "decision and arrival are still the same observation"
    )

    telemetry_source = inspect.getsource(materialize_execution_attempt)
    assert '"decision_and_arrival_are_the_same_observation": True' in telemetry_source
    assert '"delay_cost_measurable": False' in telemetry_source
    assert '"field": "delay_cost"' in telemetry_source
