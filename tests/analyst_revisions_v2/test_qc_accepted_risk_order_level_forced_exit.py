import dataclasses
import json
from decimal import Decimal, localcontext

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_forced_exit as forced_exit,
)


SID_ALPHA = "SID-ALPHA-UNIQUE-47"
SID_BETA = "SID-BETA-UNIQUE-83"
TAG = "Liquidate from delisting"


def _record(ledger=None, **overrides):
    values = {
        "authenticated_delisted_security_ids": frozenset({SID_ALPHA}),
        "security_id": SID_ALPHA,
        "order_id": 837291,
        "event_id": 99172,
        "event_message": TAG,
        "order_tag": TAG,
        "status": "Filled",
        "maximum_sale_quantity": 17,
        "signed_fill_quantity": Decimal("-17"),
        "fill_price": Decimal("23.125"),
        "fee_amount": Decimal("0"),
        "fee_currency": forced_exit.LEAN_NULL_CURRENCY,
    }
    values.update(overrides)
    return forced_exit.record_forced_delisting_fill(
        forced_exit.empty_forced_delisting_ledger()
        if ledger is None
        else ledger,
        **values,
    )


def _refuses(message, **overrides):
    with pytest.raises(forced_exit.ForcedDelistingError) as caught:
        _record(**overrides)
    assert str(caught.value) == message
    assert SID_ALPHA not in str(caught.value)


def _reseal(ledger):
    return dataclasses.replace(
        ledger,
        integrity_sha256=forced_exit._sha(forced_exit._ledger_seed(ledger)),
    )


def test_empty_and_filled_summaries_are_exact_redacted_aggregates():
    empty = forced_exit.empty_forced_delisting_ledger()
    assert forced_exit.forced_delisting_summary(empty) == {
        "schema": "arv2-order-level-forced-delisting-summary-v1",
        "order_count": 0,
        "event_count": 0,
        "fill_event_count": 0,
        "terminal_order_count": 0,
        "absolute_filled_quantity": 0,
        "filled_notional": "0",
        "actual_engine_fee_amount": "0",
        "accounting_complete": True,
        "ledger_sha256": forced_exit.forced_delisting_summary(empty)[
            "ledger_sha256"
        ],
        "raw_order_rows_in_summary": False,
        "raw_security_rows_in_summary": False,
    }
    assert len(forced_exit.forced_delisting_summary(empty)["ledger_sha256"]) == 64

    ledger = _record(fill_price=Decimal("0"))
    assert forced_exit.forced_delisting_signed_quantity(ledger, SID_ALPHA) == -17
    assert forced_exit.forced_delisting_signed_quantity(ledger, SID_BETA) == 0
    summary = forced_exit.forced_delisting_summary(ledger)
    assert summary == {
        **summary,
        "schema": forced_exit.FORCED_DELISTING_SUMMARY_SCHEMA,
        "order_count": 1,
        "event_count": 1,
        "fill_event_count": 1,
        "terminal_order_count": 1,
        "absolute_filled_quantity": 17,
        "filled_notional": "0",
        "actual_engine_fee_amount": "0",
        "accounting_complete": True,
        "raw_order_rows_in_summary": False,
        "raw_security_rows_in_summary": False,
    }


def test_ledger_and_summary_are_deterministic_across_arrival_order():
    def add_alpha(ledger):
        return _record(ledger)

    def add_beta(ledger):
        return _record(
            ledger,
            authenticated_delisted_security_ids=frozenset({SID_BETA}),
            security_id=SID_BETA,
            order_id=837292,
            event_id=99173,
            maximum_sale_quantity=3,
            signed_fill_quantity=Decimal("-3"),
            fill_price=Decimal("10.50"),
        )

    with localcontext() as context:
        context.prec = 3
        empty = forced_exit.empty_forced_delisting_ledger()
        alpha_beta = add_beta(add_alpha(empty))
        beta_alpha = add_alpha(add_beta(empty))
    assert alpha_beta == beta_alpha
    assert forced_exit.forced_delisting_summary(alpha_beta) == (
        forced_exit.forced_delisting_summary(beta_alpha)
    )
    summary = forced_exit.forced_delisting_summary(alpha_beta)
    assert summary["absolute_filled_quantity"] == 20
    assert summary["filled_notional"] == "424.625"
    assert forced_exit.forced_delisting_signed_quantity(
        alpha_beta, SID_ALPHA
    ) == -17
    assert forced_exit.forced_delisting_signed_quantity(
        alpha_beta, SID_BETA
    ) == -3


@pytest.mark.parametrize(
    "overrides",
    (
        {"authenticated_delisted_security_ids": {SID_ALPHA}},
        {"authenticated_delisted_security_ids": frozenset()},
        {"security_id": SID_BETA},
        {"event_message": "Liquidate from Delisting"},
        {"event_message": None},
        {"order_tag": "Liquidate from Delisting"},
        {"order_tag": None},
    ),
)
def test_sid_message_and_order_tag_mismatches_keep_unknown_order_refusal(overrides):
    _refuses(forced_exit.UNKNOWN_ORDER_REFUSAL, **overrides)


@pytest.mark.parametrize(
    "security_id",
    ("", " SID-ALPHA", "SID-ALPHA ", "SID-\N{SNOWMAN}", "X" * 513, 1),
)
def test_security_id_requires_one_bounded_printable_exact_string(security_id):
    _refuses(forced_exit.UNKNOWN_ORDER_REFUSAL, security_id=security_id)


@pytest.mark.parametrize(
    "member",
    ("", " OTHER", "OTHER ", "OTHER-\N{SNOWMAN}", "X" * 513, 1),
)
def test_every_authenticated_sid_member_requires_the_same_exact_syntax(member):
    _refuses(
        forced_exit.UNKNOWN_ORDER_REFUSAL,
        authenticated_delisted_security_ids=frozenset({SID_ALPHA, member}),
    )


@pytest.mark.parametrize(
    "status",
    (
        "New",
        "Submitted",
        "PartiallyFilled",
        "Canceled",
        "None",
        "Invalid",
        "CancelPending",
        "UpdateSubmitted",
        "FILLED",
        3,
        None,
    ),
)
def test_only_exact_reflected_filled_status_is_accepted(status):
    _refuses(forced_exit.STATUS_REFUSAL, status=status)


@pytest.mark.parametrize("order_id", (True, -1, 1.0, "1", None))
def test_order_id_requires_an_exact_nonnegative_integer(order_id):
    _refuses(forced_exit.ORDER_ID_REFUSAL, order_id=order_id)


@pytest.mark.parametrize("event_id", (True, -1, 1.0, "1", None))
def test_event_id_requires_an_exact_nonnegative_integer(event_id):
    _refuses(forced_exit.EVENT_ID_REFUSAL, event_id=event_id)


@pytest.mark.parametrize(
    "quantity",
    (
        Decimal("0"),
        Decimal("1"),
        Decimal("-1.5"),
        Decimal("NaN"),
        Decimal("Infinity"),
        -17,
    ),
)
def test_fill_quantity_requires_an_exact_negative_integral_decimal(quantity):
    _refuses(forced_exit.QUANTITY_REFUSAL, signed_fill_quantity=quantity)


@pytest.mark.parametrize(
    "maximum_sale_quantity",
    (
        True,
        0,
        -1,
        17.0,
        Decimal("17"),
        79228162514264337593543950336,
    ),
)
def test_maximum_sale_quantity_requires_a_positive_clr_decimal_bounded_int(
    maximum_sale_quantity,
):
    _refuses(
        forced_exit.QUANTITY_REFUSAL,
        maximum_sale_quantity=maximum_sale_quantity,
    )


def test_over_close_and_partial_close_have_distinct_refusals():
    _refuses(
        forced_exit.OVER_CLOSE_REFUSAL,
        signed_fill_quantity=Decimal("-18"),
    )
    _refuses(
        forced_exit.INCOMPLETE_CLOSE_REFUSAL,
        signed_fill_quantity=Decimal("-16"),
    )


@pytest.mark.parametrize(
    "fill_price",
    (Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), 0, "0"),
)
def test_fill_price_requires_a_finite_nonnegative_exact_decimal(fill_price):
    _refuses(forced_exit.PRICE_REFUSAL, fill_price=fill_price)


@pytest.mark.parametrize(
    "overrides",
    (
        {"fee_amount": Decimal("0.01")},
        {"fee_amount": Decimal("-0.01")},
        {"fee_amount": Decimal("NaN")},
        {"fee_amount": 0},
        {"fee_currency": "USD"},
        {"fee_currency": "qcc"},
        {"fee_currency": None},
    ),
)
def test_official_engine_direct_delisting_fill_requires_exact_zero_qcc_fee(
    overrides,
):
    _refuses(forced_exit.FEE_REFUSAL, **overrides)


def test_duplicate_and_reused_event_or_order_id_refuse_separately():
    ledger = _record()
    _refuses(forced_exit.DUPLICATE_EVENT_REFUSAL, ledger=ledger)
    _refuses(
        forced_exit.EVENT_ID_MUTATION_REFUSAL,
        ledger=ledger,
        fill_price=Decimal("23.126"),
    )
    _refuses(
        forced_exit.ORDER_ID_MUTATION_REFUSAL,
        ledger=ledger,
        event_id=99173,
    )


def test_changed_economics_change_the_ledger_digest():
    original = forced_exit.forced_delisting_summary(_record())
    changed = forced_exit.forced_delisting_summary(
        _record(fill_price=Decimal("23.126"))
    )
    assert original["ledger_sha256"] != changed["ledger_sha256"]


def test_tampered_or_wrong_ledger_is_refused_before_use():
    ledger = _record()
    for changed in (
        None,
        dataclasses.replace(
            ledger,
            event_bindings=(
                dataclasses.replace(
                    ledger.event_bindings[0],
                    fill_price_coefficient=1,
                ),
            ),
        ),
        dataclasses.replace(ledger, integrity_sha256="0" * 64),
    ):
        with pytest.raises(
            forced_exit.ForcedDelistingError,
            match="^order-level forced delisting ledger changed$",
        ):
            forced_exit.forced_delisting_summary(changed)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_event",
        "zero_quantity",
        "nonzero_fee",
        "payload_mismatch",
        "unsorted_bindings",
        "duplicate_event_order_mapping",
    ),
)
def test_correctly_rehashed_semantically_impossible_ledgers_are_refused(
    mutation,
):
    one = _record()
    second = _record(
        one,
        authenticated_delisted_security_ids=frozenset({SID_BETA}),
        security_id=SID_BETA,
        order_id=837292,
        event_id=99173,
        maximum_sale_quantity=3,
        signed_fill_quantity=Decimal("-3"),
        fill_price=Decimal("10.50"),
    )
    bad_quantity = dataclasses.replace(
        one.order_bindings[0],
        maximum_sale_quantity=0,
    )
    bad_fee = dataclasses.replace(
        one.event_bindings[0],
        fee_amount_coefficient=1,
    )
    bad_payload = dataclasses.replace(
        one.event_bindings[0],
        payload_sha256="0" * 64,
    )
    first_order = second.order_bindings[0]
    kept_event = next(
        item
        for item in second.event_bindings
        if item.order_key_sha256 == first_order.order_key_sha256
    )
    changed_event = next(
        item
        for item in second.event_bindings
        if item.order_key_sha256 != first_order.order_key_sha256
    )
    bad_event_order = dataclasses.replace(
        changed_event,
        order_key_sha256=first_order.order_key_sha256,
    )
    bad_event_order = dataclasses.replace(
        bad_event_order,
        payload_sha256=forced_exit._sha(
            forced_exit._payload_seed(first_order, bad_event_order)
        ),
    )
    malformed = {
        "missing_event": dataclasses.replace(one, event_bindings=()),
        "zero_quantity": dataclasses.replace(one, order_bindings=(bad_quantity,)),
        "nonzero_fee": dataclasses.replace(one, event_bindings=(bad_fee,)),
        "payload_mismatch": dataclasses.replace(
            one,
            event_bindings=(bad_payload,),
        ),
        "unsorted_bindings": dataclasses.replace(
            second,
            order_bindings=tuple(reversed(second.order_bindings)),
            event_bindings=tuple(reversed(second.event_bindings)),
        ),
        "duplicate_event_order_mapping": dataclasses.replace(
            second,
            event_bindings=tuple(
                sorted(
                    (kept_event, bad_event_order),
                    key=lambda item: item.event_key_sha256,
                )
            ),
        ),
    }
    with pytest.raises(
        forced_exit.ForcedDelistingError,
        match="^order-level forced delisting ledger changed$",
    ):
        forced_exit.forced_delisting_summary(_reseal(malformed[mutation]))


def test_ledger_and_summary_never_retain_raw_identifiers_or_rows():
    ledger = _record()
    encoded_ledger = json.dumps(
        dataclasses.asdict(ledger), sort_keys=True, default=str
    )
    encoded_summary = json.dumps(
        forced_exit.forced_delisting_summary(ledger), sort_keys=True
    )
    for forbidden in (SID_ALPHA, TAG, "837291", "99172"):
        assert forbidden not in encoded_ledger
        assert forbidden not in encoded_summary
    assert set(forced_exit.forced_delisting_summary(ledger)) == {
        "schema",
        "order_count",
        "event_count",
        "fill_event_count",
        "terminal_order_count",
        "absolute_filled_quantity",
        "filled_notional",
        "actual_engine_fee_amount",
        "accounting_complete",
        "ledger_sha256",
        "raw_order_rows_in_summary",
        "raw_security_rows_in_summary",
    }
