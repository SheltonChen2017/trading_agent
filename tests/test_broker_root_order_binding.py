"""Durable broker-order binding and explicit replacement regressions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
import sqlite3

import pytest

import assistant.dispatch_fence as dispatch_fence_module
from assistant.dispatch_fence import get_runtime_emergency_stop
from assistant.execution_kernel.errors import ProposalExecutionError
from assistant.execution_kernel.submit import journal_accepted_order
from assistant.order_lifecycle import journal_broker_order_update
from assistant.order_reconciler import handle_trade_update
from assistant.storage import (
    AssistantStore,
    BrokerOrderBindingConflictError,
    JournalTransactionConflictError,
)
from execution.broker_contract import (
    BrokerAccountIdentity,
    BrokerOrderIntegrityError,
    BrokerOrderValidationContext,
    validate_broker_order,
)


_ACCOUNT = BrokerAccountIdentity("paper-account-1", "paper")
_SNAPSHOT_ID = "a" * 64
_POLICY_FINGERPRINT = "b" * 64


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path, monkeypatch):
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setattr(dispatch_fence_module, "_RUNTIME_FENCE_ROOT", runtime_root)


def _proposal(*, status: str = "broker_accepted") -> dict:
    return {
        "proposal_id": "proposal-1",
        "created_at": "2026-08-25T15:00:00+00:00",
        "expires_at": "2026-08-25T16:00:00+00:00",
        "status": status,
        "idempotency_key": "idem-proposal-1",
        "broker_execution_context": {
            "account_id": _ACCOUNT.account_id,
            "account_mode": _ACCOUNT.account_mode,
            "snapshot_id": _SNAPSHOT_ID,
            "policy_fingerprint": _POLICY_FINGERPRINT,
        },
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "order_type": "market",
            "limit_price": None,
        },
    }


def _order(order_id: str, *, replaces: str | None = None) -> dict:
    observed_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    return {
        "order_id": order_id,
        "client_order_id": (
            "idem-proposal-1" if replaces is None else f"replacement-{order_id}"
        ),
        "ticker": "AAPL",
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "shares": "10",
        "shares_decimal": "10",
        "notional": None,
        "notional_decimal": None,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "limit_price_decimal": None,
        "time_in_force": "day",
        "status": "accepted",
        "filled_qty": "0",
        "filled_qty_decimal": "0",
        "filled_avg_price": None,
        "filled_avg_price_decimal": None,
        "submitted_at": observed_at,
        "updated_at": observed_at,
        "filled_at": None,
        "canceled_at": None,
        "expired_at": None,
        "failed_at": None,
        "replaced_at": None,
        "replaces": replaces,
        "replaced_by": None,
    }


def _store(tmp_path, *, status: str = "broker_accepted") -> AssistantStore:
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(_proposal(status=status))
    return store


def _journal_root(store: AssistantStore, order_id: str = "order-1") -> None:
    journal_broker_order_update(
        store,
        "proposal-1",
        _order(order_id),
        event_type="submission_response",
        external_event_id=f"accepted-{order_id}",
    )


def test_strict_contract_rejects_a_different_later_root_order_id():
    context = BrokerOrderValidationContext(
        expected_account=_ACCOUNT,
        observed_account=_ACCOUNT,
        expected_order_id="order-1",
        expected_client_order_id="idem-proposal-1",
        expected_ticker="AAPL",
        expected_side="buy",
        expected_order_type="market",
        expected_quantity=Decimal("10"),
        require_exact_numerics=True,
    )

    with pytest.raises(BrokerOrderIntegrityError) as caught:
        validate_broker_order(_order("order-2"), context=context)

    assert caught.value.code == "order_id_mismatch"


def test_later_same_client_id_cannot_replace_the_durable_root(tmp_path):
    store = _store(tmp_path)
    _journal_root(store)

    with pytest.raises(ProposalExecutionError, match="order_id_mismatch"):
        handle_trade_update(
            store,
            {
                "event": "accepted",
                "event_id": "forged-root-observation",
                "order": _order("order-2"),
            },
            observed_account=_ACCOUNT,
        )

    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == "order-1"
    assert proposal["broker_order"]["order_id"] == "order-1"
    assert proposal["status"] == "submission_unknown"
    assert store.get_proposal_by_broker_order_id("order-2") is None
    assert store.get_kill_switch()["active"] is True


def test_explicit_replacement_transition_preserves_the_root(tmp_path):
    store = _store(tmp_path)
    _journal_root(store)

    handle_trade_update(
        store,
        {
            "event": "accepted",
            "event_id": "replacement-accepted",
            "order": _order("order-2", replaces="order-1"),
        },
        observed_account=_ACCOUNT,
    )

    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == "order-1"
    assert proposal["broker_order"]["order_id"] == "order-2"
    assert store.get_kill_switch()["active"] is False


def test_later_observation_of_the_same_replacement_keeps_its_parent(tmp_path):
    store = _store(tmp_path)
    _journal_root(store)
    replacement = _order("order-2", replaces="order-1")
    handle_trade_update(
        store,
        {"event": "accepted", "event_id": "replacement-first", "order": replacement},
        observed_account=_ACCOUNT,
    )

    result = handle_trade_update(
        store,
        {"event": "accepted", "event_id": "replacement-later", "order": replacement},
        observed_account=_ACCOUNT,
    )

    assert result["broker_event_projected"] is True
    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == "order-1"
    assert proposal["broker_order"]["order_id"] == "order-2"
    assert proposal["broker_order"]["replaces"] == "order-1"


def test_delayed_known_ancestor_is_journaled_but_cannot_regress_projection(tmp_path):
    store = _store(tmp_path)
    _journal_root(store)
    handle_trade_update(
        store,
        {
            "event": "accepted",
            "event_id": "replacement-current",
            "order": _order("order-2", replaces="order-1"),
        },
        observed_account=_ACCOUNT,
    )

    delayed = handle_trade_update(
        store,
        {
            "event": "accepted",
            "event_id": "delayed-root",
            "order": _order("order-1"),
        },
        observed_account=_ACCOUNT,
    )

    assert delayed["broker_event_inserted"] is True
    assert delayed["broker_event_projected"] is False
    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == "order-1"
    assert proposal["broker_order"]["order_id"] == "order-2"


def test_new_root_binding_persists_even_when_status_blocks_projection(tmp_path):
    store = _store(tmp_path, status="filled")

    result = journal_broker_order_update(
        store,
        "proposal-1",
        _order("order-1"),
        event_type="delayed_accepted",
        external_event_id="delayed-first-observation",
    )

    assert result["broker_event_inserted"] is True
    assert result["broker_event_projected"] is False
    proposal = store.get_proposal("proposal-1")
    assert proposal["status"] == "filled"
    assert proposal["broker_order_root_id"] == "order-1"
    assert "broker_order" not in proposal


def test_explicit_multi_hop_path_is_the_only_new_id_escape_hatch(tmp_path):
    store = _store(tmp_path)
    _journal_root(store)

    journal_broker_order_update(
        store,
        "proposal-1",
        _order("order-3", replaces="order-2"),
        event_type="poll_reconciliation",
        external_event_id="multi-hop-replacement",
        broker_order_root_id="order-1",
        replacement_order_path=("order-1", "order-2", "order-3"),
        raw_event={"replacement_chain": ["order-2", "order-3"]},
    )

    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == "order-1"
    assert proposal["broker_order"]["order_id"] == "order-3"


def test_concurrent_first_observations_cannot_establish_two_roots(tmp_path):
    store = _store(tmp_path, status="submitting")
    barrier = Barrier(2)

    def observe(order_id: str):
        barrier.wait(timeout=5)
        return journal_broker_order_update(
            store,
            "proposal-1",
            _order(order_id),
            event_type="submission_reconciled",
            external_event_id=f"race-{order_id}",
        )

    results: list[object] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(observe, order_id) for order_id in ("order-1", "order-2")]
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except Exception as exc:  # captured for exact dangerous-direction assertions
                results.append(exc)

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(
        isinstance(result, BrokerOrderBindingConflictError) for result in results
    ) == 1
    events = store.list_broker_order_events(proposal_id="proposal-1")
    assert len(events) == 1
    proposal = store.get_proposal("proposal-1")
    assert proposal["broker_order_root_id"] == events[0]["order_id"]
    assert proposal["broker_order"]["order_id"] == events[0]["order_id"]
    assert store.get_kill_switch()["active"] is True


def test_journal_accepted_order_cannot_overwrite_retained_root_on_collision(
    tmp_path,
):
    store = _store(tmp_path, status="submitting")
    _journal_root(store, "order-A")
    store.update_proposal_status("proposal-1", "submission_unknown")
    before = store.get_proposal("proposal-1")

    with pytest.raises(BrokerOrderBindingConflictError):
        journal_accepted_order(store, "proposal-1", _order("order-B"))

    after = store.get_proposal("proposal-1")
    assert after["broker_order_root_id"] == "order-A"
    assert after["broker_order"] == before["broker_order"]
    events = store.list_broker_order_events(proposal_id="proposal-1")
    assert len(events) == 1
    assert events[0]["order_id"] == "order-A"
    assert get_runtime_emergency_stop(store.path)["active"] is True


def test_journal_accepted_order_preserves_root_when_containment_trigger_aborts(
    tmp_path,
):
    store = _store(tmp_path, status="submitting")
    _journal_root(store, "order-A")
    store.update_proposal_status("proposal-1", "submission_unknown")
    before = store.get_proposal("proposal-1")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "CREATE TRIGGER inject_event_mutation_during_binding_containment "
            "AFTER UPDATE ON trade_proposals BEGIN "
            "UPDATE broker_order_events SET status = 'tampered' "
            "WHERE proposal_id = NEW.proposal_id; END"
        )

    with pytest.raises(JournalTransactionConflictError):
        journal_accepted_order(store, "proposal-1", _order("order-B"))

    after = store.get_proposal("proposal-1")
    assert after["broker_order_root_id"] == "order-A"
    assert after["broker_order"] == before["broker_order"]
    assert len(store.list_broker_order_events(proposal_id="proposal-1")) == 1
    assert get_runtime_emergency_stop(store.path)["active"] is True


def test_order_id_reused_across_proposals_is_globally_contained(tmp_path):
    store = _store(tmp_path, status="submitting")
    _journal_root(store, "shared-order")
    second = _proposal(status="submitting")
    second.update(
        proposal_id="proposal-2",
        idempotency_key="idem-proposal-2",
    )
    store.save_proposal(second)
    incoming = {
        **_order("shared-order"),
        "client_order_id": "idem-proposal-2",
    }

    with pytest.raises(BrokerOrderBindingConflictError, match="already bound"):
        journal_broker_order_update(
            store,
            "proposal-2",
            incoming,
            event_type="submission_response",
            external_event_id="second-proposal-shared-order",
        )

    assert store.get_proposal("proposal-1")["broker_order_root_id"] == "shared-order"
    assert store.get_proposal("proposal-2")["status"] == "submission_unknown"
    assert store.list_broker_order_events(proposal_id="proposal-2") == []
    assert get_runtime_emergency_stop(store.path)["active"] is True
