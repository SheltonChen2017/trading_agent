"""Safety contracts for the programmable broker used by fault drills."""
from __future__ import annotations

import execution.alpaca_broker as broker_module
from tests.faults.fault_harness import (
    ScriptedBroker,
    accepted_order,
    scripted_broker,
)


def test_fault_harness_patches_only_the_account_scoped_session_opener() -> None:
    original_opener = broker_module.open_alpaca_broker_session
    legacy_facades = {
        name: getattr(broker_module, name)
        for name in (
            "is_configured",
            "assert_account_and_asset_ready",
            "get_latest_quote",
            "submit_market_order",
            "submit_limit_order",
            "find_order_by_client_id",
            "get_order_by_id",
        )
    }
    broker = ScriptedBroker()

    with scripted_broker(broker):
        assert broker_module.open_alpaca_broker_session() is broker
        assert all(
            getattr(broker_module, name) is original
            for name, original in legacy_facades.items()
        )

    assert broker_module.open_alpaca_broker_session is original_opener


def test_fault_harness_never_upgrades_an_arbitrary_partial_order_mapping() -> None:
    partial = {"order_id": "partial-evidence"}
    broker = ScriptedBroker(submit_market_order=partial)

    observed = broker.handler("submit_market_order")(
        "AAPL",
        1,
        idempotency_key="idem-partial",
    )

    assert observed is partial
    assert observed == {"order_id": "partial-evidence"}


def test_fault_harness_materializes_only_the_explicit_accepted_order_marker() -> None:
    broker = ScriptedBroker(
        submit_market_order=accepted_order("accepted-evidence", side="sell")
    )

    observed = broker.handler("submit_market_order")(
        "AAPL",
        1,
        idempotency_key="idem-accepted",
    )

    assert observed["order_id"] == "accepted-evidence"
    assert observed["client_order_id"] == "idem-accepted"
    assert observed["side"] == "sell"
    assert observed["shares_decimal"] == "1"
    assert observed["filled_qty_decimal"] == "0"
