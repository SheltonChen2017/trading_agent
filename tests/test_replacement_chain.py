"""
Replacement-order recovery through polling/startup reconciliation.

The first pass at this fix only handled the LIVE direction (a replacement
event arrives on the stream, match it back to the proposal it supersedes via
`replaces`). Polling still looked up only the original order by client id, so
if the replacement's trade-update was missed -- app restart, stream
disconnect, or a replacement made before monitoring began -- the replacement
stayed untracked even once accepted, partially filled, or filled. Reproduced
by an independent review (2026-07-29): the proposal ended submission_unknown,
the stored broker order was still order-1, and get_order_by_id was never
called. These tests pin the durable/restart path specifically, because
live-stream tests alone cannot show it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.order_lifecycle import journal_broker_order_update
from assistant.order_reconciler import (
    handle_trade_update,
    reconcile_nonterminal_orders,
)
from assistant.proposal_status import (
    BROKER_ACCEPTED,
    FILLED,
    PARTIALLY_FILLED,
    SUBMISSION_UNKNOWN,
)
from assistant.storage import AssistantStore


def _proposal(status: str = "broker_accepted", proposal_id: str = "tp-ready") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-29T14:00:00+00:00",
        "expires_at": "2026-07-30T14:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "order_type": "market",
            "limit_price": None,
        },
    }


def _order(status: str, *, filled_qty: float = 0.0) -> dict:
    return {
        "order_id": "order-1",
        "client_order_id": "idem-tp-ready",
        "ticker": "AAPL",
        "shares": 10.0,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "time_in_force": "day",
        "status": status,
        "filled_qty": filled_qty,
        "filled_avg_price": 100.0 if filled_qty else None,
        "submitted_at": "2026-07-29T14:00:00+00:00",
        "updated_at": None,
        "replaced_by": None,
        "replaces": None,
        "replaced_at": None,
    }


def _replaced(order_id: str, replaced_by: str) -> dict:
    order = _order("replaced")
    order["order_id"] = order_id
    order["replaced_by"] = replaced_by
    return order


def _replacement(order_id: str, status: str, replaces: str, *, filled_qty: float = 0.0) -> dict:
    order = _order(status, filled_qty=filled_qty)
    order["order_id"] = order_id
    order["client_order_id"] = f"client-{order_id}"
    order["replaces"] = replaces
    return order


def _chain_broker(orders: dict, *, record: list | None = None):
    """Polling returns the ORIGINAL order by client id (exactly what a real
    broker does after a replacement); the chain is served by get_order_by_id."""

    class ChainBroker:
        @staticmethod
        def find_order_by_client_id(client_order_id):
            return orders.get("order-1")

        @staticmethod
        def get_order_by_id(order_id):
            if record is not None:
                record.append(order_id)
            return orders.get(order_id)

        @staticmethod
        def cancel_order(order_id):
            raise AssertionError("no cancellation expected in these tests")

    return ChainBroker


def _store(temp: str) -> AssistantStore:
    store = AssistantStore(Path(temp) / "assistant.db")
    store.save_proposal(_proposal())
    return store


def test_polling_follows_replaced_by_to_an_accepted_replacement():
    calls: list = []
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replacement("order-2", "accepted", "order-1"),
    }
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store, broker_module=_chain_broker(orders, record=calls)
        )
        assert calls == ["order-2"], f"expected get_order_by_id('order-2'), got {calls}"
        assert store.get_proposal("tp-ready")["status"] == BROKER_ACCEPTED
        assert result["replacements_followed"] == 1


def test_polling_follows_the_chain_to_a_filled_replacement():
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replacement("order-2", "filled", "order-1", filled_qty=10.0),
    }
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == FILLED


def test_polling_follows_the_chain_to_a_partially_filled_replacement():
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replacement("order-2", "partially_filled", "order-1", filled_qty=4.0),
    }
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == PARTIALLY_FILLED


def test_polling_follows_multiple_successive_replacements():
    calls: list = []
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replaced("order-2", "order-3"),
        "order-3": _replacement("order-3", "filled", "order-2", filled_qty=10.0),
    }
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(
            store, broker_module=_chain_broker(orders, record=calls)
        )
        assert calls == ["order-2", "order-3"]
        assert store.get_proposal("tp-ready")["status"] == FILLED


def test_polling_detects_a_replacement_cycle_and_stays_unresolved():
    """A broker reporting A -> B -> A must not loop forever."""
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replaced("order-2", "order-1"),
    }
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert any("cycle" in e for e in result["errors"]), result["errors"]


def test_polling_bounds_an_unterminated_replacement_chain():
    """Every order reports a further replacement, so only the depth bound can
    stop the traversal."""
    orders = {f"order-{i}": _replaced(f"order-{i}", f"order-{i + 1}") for i in range(1, 40)}
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert any("exceeded" in e for e in result["errors"]), result["errors"]


def test_a_missing_replacement_stays_unresolved_rather_than_confirmed_absent():
    """A failed lookup means "we cannot tell", never "no such order" -- the
    latter would release the proposal as a clean failure."""
    orders = {"order-1": _replaced("order-1", "order-2")}  # order-2 absent
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert result["confirmed_absent"] == 0
        assert any("could not be found" in e for e in result["errors"]), result["errors"]


def test_a_replaced_order_without_replaced_by_stays_unresolved():
    orders = {"order-1": _replaced("order-1", "")}
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert any("no replaced_by" in e for e in result["errors"]), result["errors"]


def test_a_broker_lookup_failure_stays_unresolved():
    class ExplodingBroker:
        @staticmethod
        def find_order_by_client_id(client_order_id):
            return _replaced("order-1", "order-2")

        @staticmethod
        def get_order_by_id(order_id):
            raise RuntimeError("broker unavailable")

    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=ExplodingBroker)
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert result["confirmed_absent"] == 0
        assert any("lookup failed" in e for e in result["errors"]), result["errors"]


def test_a_replacement_with_an_altered_quantity_trips_the_kill_switch():
    """An out-of-band replacement is trustworthy only if it still matches the
    stored intent -- a changed quantity must fail closed."""
    altered = _replacement("order-2", "accepted", "order-1")
    altered["shares"] = 999.0
    orders = {"order-1": _replaced("order-1", "order-2"), "order-2": altered}
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_kill_switch()["active"] is True
        assert result["errors"], "the identity mismatch must be reported"


def test_a_replacement_with_an_altered_ticker_trips_the_kill_switch():
    altered = _replacement("order-2", "accepted", "order-1")
    altered["ticker"] = "TSLA"
    orders = {"order-1": _replaced("order-1", "order-2"), "order-2": altered}
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_kill_switch()["active"] is True


def test_a_replacement_with_an_altered_side_trips_the_kill_switch():
    altered = _replacement("order-2", "accepted", "order-1")
    altered["side"] = "sell"
    orders = {"order-1": _replaced("order-1", "order-2"), "order-2": altered}
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_chain_broker(orders))
        assert store.get_kill_switch()["active"] is True


def test_live_and_polling_paths_project_the_same_state_from_a_replacement():
    """A divergence would mean the outcome depends on whether a stream event
    happened to arrive -- which is exactly the inconsistency this fix removes."""
    orders = {
        "order-1": _replaced("order-1", "order-2"),
        "order-2": _replacement("order-2", "filled", "order-1", filled_qty=10.0),
    }
    statuses = []
    for use_stream in (False, True):
        with tempfile.TemporaryDirectory() as temp:
            store = _store(temp)
            broker = _chain_broker(orders)
            if use_stream:
                journal_broker_order_update(
                    store, "tp-ready", _order("accepted"), event_type="accepted"
                )
                handle_trade_update(
                    store,
                    {"order": orders["order-1"], "event": "replaced"},
                    broker_module=broker,
                )
            else:
                reconcile_nonterminal_orders(store, broker_module=broker)
            statuses.append(store.get_proposal("tp-ready")["status"])
    assert statuses[0] == statuses[1], (
        f"polling projected {statuses[0]} but the live path projected {statuses[1]}"
    )


def test_a_late_replaced_event_cannot_regress_an_already_filled_proposal():
    """Stream ordering is not guaranteed: a stale `replaced` event for the old
    order must not drag a proposal back out of a terminal fill."""
    with tempfile.TemporaryDirectory() as temp:
        store = _store(temp)
        journal_broker_order_update(
            store,
            "tp-ready",
            _replacement("order-2", "filled", "order-1", filled_qty=10.0),
            event_type="fill",
        )
        assert store.get_proposal("tp-ready")["status"] == FILLED

        handle_trade_update(
            store, {"order": _replaced("order-1", "order-2"), "event": "replaced"}
        )
        assert store.get_proposal("tp-ready")["status"] == FILLED, (
            "a stale replaced event must not regress a filled proposal"
        )


if __name__ == "__main__":
    test_polling_follows_replaced_by_to_an_accepted_replacement()
    test_polling_follows_the_chain_to_a_filled_replacement()
    test_polling_follows_the_chain_to_a_partially_filled_replacement()
    test_polling_follows_multiple_successive_replacements()
    test_polling_detects_a_replacement_cycle_and_stays_unresolved()
    test_polling_bounds_an_unterminated_replacement_chain()
    test_a_missing_replacement_stays_unresolved_rather_than_confirmed_absent()
    test_a_replaced_order_without_replaced_by_stays_unresolved()
    test_a_broker_lookup_failure_stays_unresolved()
    test_a_replacement_with_an_altered_quantity_trips_the_kill_switch()
    test_a_replacement_with_an_altered_ticker_trips_the_kill_switch()
    test_a_replacement_with_an_altered_side_trips_the_kill_switch()
    test_live_and_polling_paths_project_the_same_state_from_a_replacement()
    test_a_late_replaced_event_cannot_regress_an_already_filled_proposal()
    print("All replacement-chain tests passed.")
