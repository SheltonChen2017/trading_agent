"""Strict broker-order evidence tests.

These tests are deliberately pure: no credentials, SDK imports, database, or
broker calls.  The contract is the fail-closed boundary later execution work
can share across submit responses, lookups, polling, streams, and open books.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from execution.broker_contract import (
    BrokerAccountIdentity,
    BrokerOrderIntegrityError,
    BrokerOrderValidationContext,
    active_order_material_fingerprint,
    validate_active_order_set,
    validate_broker_order,
    validated_broker_order_mapping,
)


_PAPER_ACCOUNT = BrokerAccountIdentity(
    account_id="paper-account-1", account_mode="paper"
)


def _limit_order(**overrides):
    order = {
        "order_id": "order-1",
        "client_order_id": "proposal-1:attempt-1",
        "ticker": "AAPL",
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "shares": 10.0,
        "shares_decimal": "10",
        "notional": None,
        "notional_decimal": None,
        "side": "buy",
        "type": "limit",
        "limit_price": 100.01,
        "limit_price_decimal": "100.01",
        "time_in_force": "day",
        "status": "new",
        "filled_qty": 0.0,
        "filled_qty_decimal": "0",
        "filled_avg_price": None,
        "filled_avg_price_decimal": None,
        "replaces": None,
        "replaced_by": None,
        "replaced_at": None,
        "submitted_at": "2026-08-26T15:30:00+00:00",
        "updated_at": "2026-08-26T15:30:01+00:00",
        "filled_at": None,
        "canceled_at": None,
        "expired_at": None,
        "failed_at": None,
    }
    order.update(overrides)
    return order


def _root_context(**overrides):
    values = {
        "expected_client_order_id": "proposal-1:attempt-1",
        "expected_account": _PAPER_ACCOUNT,
        "observed_account": _PAPER_ACCOUNT,
        "expected_ticker": "AAPL",
        "expected_side": "buy",
        "expected_order_type": "limit",
        "expected_quantity": Decimal("10"),
        "expected_limit_price": Decimal("100.01"),
    }
    values.update(overrides)
    return BrokerOrderValidationContext(**values)


def _assert_code(code: str, call) -> BrokerOrderIntegrityError:
    with pytest.raises(BrokerOrderIntegrityError) as caught:
        call()
    assert caught.value.code == code
    return caught.value


def test_valid_root_order_returns_canonical_exact_evidence():
    result = validate_broker_order(_limit_order(), context=_root_context())

    assert result.order_id == "order-1"
    assert result.client_order_id == "proposal-1:attempt-1"
    assert result.ticker == "AAPL"
    assert result.asset_class == "us_equity"
    assert result.order_class == "simple"
    assert result.extended_hours is False
    assert result.quantity == Decimal("10")
    assert result.limit_price == Decimal("100.01")
    assert result.filled_quantity == Decimal("0")
    assert result.account == _PAPER_ACCOUNT
    assert result.submitted_at.utcoffset().total_seconds() == 0

    canonical = validated_broker_order_mapping(result)
    assert canonical["shares"] == canonical["shares_decimal"] == "10"
    assert canonical["limit_price"] == canonical["limit_price_decimal"] == "100.01"
    assert canonical["filled_qty"] == canonical["filled_qty_decimal"] == "0"
    assert canonical["asset_class"] == "us_equity"
    assert canonical["order_class"] == "simple"
    assert canonical["extended_hours"] is False
    assert canonical["legs"] is None


@pytest.mark.parametrize(
    "bad_id", [None, "", "   ", "None", "null", "unknown", 123, "id\nline"]
)
def test_missing_or_sentinel_order_id_refuses(bad_id):
    _assert_code(
        "invalid_order_id",
        lambda: validate_broker_order(
            _limit_order(order_id=bad_id), context=_root_context()
        ),
    )


@pytest.mark.parametrize("bad_client_id", [None, "", "wrong-client-key"])
def test_root_client_order_id_must_match_exactly(bad_client_id):
    _assert_code(
        "client_order_id_mismatch",
        lambda: validate_broker_order(
            _limit_order(client_order_id=bad_client_id), context=_root_context()
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"order_id": " order-1 "}, "invalid_order_id"),
        (
            {"client_order_id": " proposal-1:attempt-1 "},
            "client_order_id_mismatch",
        ),
        ({"replaces": " order-0 "}, "invalid_replaces_order_id"),
        ({"replaced_by": " order-2 "}, "invalid_replaced_by_order_id"),
    ],
)
def test_whitespace_padded_broker_identities_refuse(mutation, expected_code):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


def test_whitespace_padded_account_identity_refuses():
    with pytest.raises(ValueError, match="surrounding whitespace"):
        BrokerAccountIdentity(
            account_id=" paper-account-1 ", account_mode="paper"
        )


def test_bound_account_requires_observed_identity_and_exact_match():
    with pytest.raises(TypeError, match="observed_account"):
        _root_context(observed_account=None)
    _assert_code(
        "account_mismatch",
        lambda: validate_broker_order(
            _limit_order(),
            context=_root_context(
                observed_account=BrokerAccountIdentity(
                    account_id="paper-account-2", account_mode="paper"
                )
            ),
        ),
    )
    _assert_code(
        "account_mismatch",
        lambda: validate_broker_order(
            _limit_order(),
            context=_root_context(
                observed_account=BrokerAccountIdentity(
                    account_id="paper-account-1", account_mode="live"
                )
            ),
        ),
    )


def test_empty_active_book_still_refuses_an_account_mismatch():
    foreign_account = BrokerAccountIdentity(
        account_id="paper-account-2", account_mode="paper"
    )

    _assert_code(
        "account_mismatch",
        lambda: validate_active_order_set(
            [],
            expected_account=_PAPER_ACCOUNT,
            observed_account=foreign_account,
        ),
    )


def test_replacement_lineage_is_separate_from_root_client_identity():
    replacement = _limit_order(
        order_id="order-2",
        client_order_id="broker-replacement-client-2",
        replaces="order-1",
    )
    context = _root_context(
        expected_client_order_id=None,
        require_client_order_id=True,
        expected_replaces_order_id="order-1",
    )

    result = validate_broker_order(replacement, context=context)
    assert result.replaces == "order-1"

    _assert_code(
        "replacement_lineage_mismatch",
        lambda: validate_broker_order(
            dict(replacement, replaces="another-order"), context=context
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"ticker": "MSFT"}, "ticker_mismatch"),
        ({"side": "sell"}, "side_mismatch"),
        ({"type": "market", "limit_price": None,
          "limit_price_decimal": None}, "order_type_mismatch"),
        ({"time_in_force": "gtc"}, "invalid_time_in_force"),
        (
            {"shares": 10.000000001, "shares_decimal": "10.000000001"},
            "quantity_mismatch",
        ),
        (
            {"limit_price": 100.02, "limit_price_decimal": "100.02"},
            "limit_price_mismatch",
        ),
        ({"status": "future_status"}, "unknown_status"),
    ],
)
def test_material_identity_and_closed_status_vocabulary_refuse_drift(
    mutation, expected_code
):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"asset_class": "crypto"}, "unsupported_asset_class"),
        ({"order_class": "bracket"}, "unsupported_order_class"),
        ({"extended_hours": True}, "unsupported_extended_hours"),
        ({"legs": [{"order_id": "child-order"}]}, "unsupported_order_legs"),
    ],
)
def test_unsupported_order_structure_refuses(mutation, expected_code):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected_field"),
    [
        ({"shares": 9.0, "shares_decimal": "10"}, "shares"),
        (
            {
                "shares": None,
                "shares_decimal": None,
                "notional": 999.0,
                "notional_decimal": "1000",
            },
            "notional",
        ),
        (
            {"limit_price": 100.02, "limit_price_decimal": "100.01"},
            "limit_price",
        ),
        ({"filled_qty": 1.0, "filled_qty_decimal": "0"}, "filled_qty"),
        (
            {
                "status": "partially_filled",
                "filled_qty": 1.0,
                "filled_qty_decimal": "1",
                "filled_avg_price": 99.0,
                "filled_avg_price_decimal": "100",
            },
            "filled_avg_price",
        ),
    ],
)
def test_exact_and_legacy_numeric_companions_must_agree(
    mutation, expected_field
):
    error = _assert_code(
        "numeric_companion_mismatch",
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )
    assert error.field == expected_field


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"shares": float("nan"), "shares_decimal": None}, "invalid_quantity"),
        ({"shares": float("inf"), "shares_decimal": None}, "invalid_quantity"),
        ({"shares": True, "shares_decimal": None}, "invalid_quantity"),
        ({"shares": "not-a-number", "shares_decimal": None}, "invalid_quantity"),
        ({"limit_price": float("nan"), "limit_price_decimal": None},
         "invalid_limit_price"),
        ({"filled_qty": float("inf"), "filled_qty_decimal": None},
         "invalid_filled_quantity"),
    ],
)
def test_malformed_or_nonfinite_numeric_evidence_refuses(mutation, expected_code):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"filled_qty": None, "filled_qty_decimal": None},
         "invalid_filled_quantity"),
        ({"status": "new", "filled_qty": 1.0, "filled_qty_decimal": "1",
          "filled_avg_price": 100.0,
          "filled_avg_price_decimal": "100"}, "invalid_fill_state"),
        ({"status": "partially_filled", "filled_qty": 0.0,
          "filled_qty_decimal": "0"},
         "invalid_fill_state"),
        ({"status": "partially_filled", "filled_qty": 10.0,
          "filled_qty_decimal": "10", "filled_avg_price": 100.0,
          "filled_avg_price_decimal": "100"}, "invalid_fill_state"),
        ({"status": "partially_filled", "filled_qty": 1.0,
          "filled_qty_decimal": "1", "filled_avg_price": None,
          "filled_avg_price_decimal": None}, "invalid_fill_state"),
        ({"status": "partially_filled", "filled_qty": 1.0,
          "filled_qty_decimal": "1", "filled_avg_price": 0.0,
          "filled_avg_price_decimal": "0"}, "invalid_fill_state"),
        ({"status": "filled", "filled_qty": 9.0,
          "filled_qty_decimal": "9", "filled_avg_price": 100.0,
          "filled_avg_price_decimal": "100"}, "invalid_fill_state"),
        ({"status": "filled", "filled_qty": 10.0,
          "filled_qty_decimal": "10", "filled_avg_price": None,
          "filled_avg_price_decimal": None}, "invalid_fill_state"),
    ],
)
def test_fill_quantity_and_average_price_must_prove_the_status(
    mutation, expected_code
):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


def test_partial_terminal_order_with_positive_exact_fill_is_valid():
    result = validate_broker_order(
        _limit_order(
            status="canceled",
            filled_qty=2.5,
            filled_qty_decimal="2.5",
            filled_avg_price=99.875,
            filled_avg_price_decimal="99.875",
            canceled_at="2026-08-26T15:30:01Z",
        ),
        context=_root_context(),
    )
    assert result.filled_quantity == Decimal("2.5")
    assert result.filled_average_price == Decimal("99.875")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"submitted_at": None}, "invalid_submitted_at"),
        ({"submitted_at": "2026-08-26T15:30:00"}, "invalid_submitted_at"),
        ({"updated_at": "not-a-time"}, "invalid_updated_at"),
    ],
)
def test_broker_timestamps_must_be_parseable_and_timezone_aware(
    mutation, expected_code
):
    _assert_code(
        expected_code,
        lambda: validate_broker_order(
            _limit_order(**mutation), context=_root_context()
        ),
    )


def test_one_bad_active_row_invalidates_the_entire_open_order_set():
    rows = [
        _limit_order(order_id="order-1", client_order_id="manual-1"),
        _limit_order(
            order_id="order-2",
            client_order_id="manual-2",
            ticker=None,
        ),
    ]

    _assert_code(
        "invalid_ticker",
        lambda: validate_active_order_set(
            rows,
            expected_account=_PAPER_ACCOUNT,
            observed_account=_PAPER_ACCOUNT,
        ),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"order_id": None},
        {"ticker": None},
        {"side": "unknown"},
        {"type": "stop"},
        {"time_in_force": None},
        {"shares": None, "shares_decimal": None},
        {"shares": float("nan"), "shares_decimal": None},
        {"status": "filled", "filled_qty": 10.0,
         "filled_qty_decimal": "10", "filled_avg_price": 100.0,
         "filled_avg_price_decimal": "100"},
    ],
)
def test_active_order_schema_refuses_each_unusable_risk_row(mutation):
    with pytest.raises(BrokerOrderIntegrityError):
        validate_active_order_set(
            [_limit_order(**mutation)],
            expected_account=_PAPER_ACCOUNT,
            observed_account=_PAPER_ACCOUNT,
        )


def test_active_order_material_fingerprint_is_exact_and_order_independent():
    first = _limit_order(order_id="order-1", client_order_id="manual-1")
    second = _limit_order(
        order_id="order-2",
        client_order_id="manual-2",
        ticker="msft",
    )
    validated = validate_active_order_set(
        [first, second],
        expected_account=_PAPER_ACCOUNT,
        observed_account=_PAPER_ACCOUNT,
    )
    reversed_validated = validate_active_order_set(
        [second, first],
        expected_account=_PAPER_ACCOUNT,
        observed_account=_PAPER_ACCOUNT,
    )
    fingerprint = active_order_material_fingerprint(validated)

    assert fingerprint == active_order_material_fingerprint(reversed_validated)

    equivalent = deepcopy(second)
    equivalent["shares_decimal"] = "10.0"
    equivalent_validated = validate_active_order_set(
        [first, equivalent],
        expected_account=_PAPER_ACCOUNT,
        observed_account=_PAPER_ACCOUNT,
    )
    assert fingerprint == active_order_material_fingerprint(equivalent_validated)

    changed = deepcopy(second)
    changed["shares"] = 10.000000001
    changed["shares_decimal"] = "10.000000001"
    changed_validated = validate_active_order_set(
        [first, changed],
        expected_account=_PAPER_ACCOUNT,
        observed_account=_PAPER_ACCOUNT,
    )
    assert fingerprint != active_order_material_fingerprint(changed_validated)
