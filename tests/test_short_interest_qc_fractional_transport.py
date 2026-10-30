"""Fabricated-only pure decimal mirrors; no QC execution or provider data."""
from __future__ import annotations

import dataclasses
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.qc_fractional_transport import (
    CELL_IDS, PROTOCOL_SHA256, MAXIMUM_COMBINED_DRIFT_USD, QUANTUM,
    CellTransportState, FillProof, PendingTransportOrder, QCFractionalTransportError,
    TransportPosition, _decimal, _lattice, accept_fill, prepare_order, transport_policy,
)


def state(cost=10, cash=Fraction(100000)):
    return CellTransportState.new(f"si-qc-L20-C{cost}-equal_weight_common", cash)


def buy(source=None, *, quantity=Fraction(1, 3), price=Fraction(30),
        security="qc:fixture-security", event="fixture-open-1", order_id="fixture-order-1"):
    return prepare_order(source or state(), security_id=security, event_id=event,
                         order_id=order_id, side="buy", economic_quantity=quantity,
                         economic_price=price)


def proof(order, **changes):
    values = {name: getattr(order, name) for name in (
        "cell_id", "security_id", "event_id", "order_id", "side", "fill_price",
        "fee_usd", "posted_notional_usd", "posted_cash_delta_usd")}
    values["filled_quantity"] = order.submitted_quantity
    values.update(changes)
    return FillProof(**values)


def test_prospective_policy_exactly_48_detached_cells_and_zero_authority():
    policy = transport_policy()
    assert hash_payload(policy) == PROTOCOL_SHA256 == "7ce7b5c8ef5c3e49c0f5ef5de45298ce4f403cfe9809c42829fffc1d5c71fe30"
    assert len(CELL_IDS) == len(set(CELL_IDS)) == 48
    assert policy["quantity_lattice"] == {"numerator": 1, "denominator": 10**18}
    assert all(value is False for value in policy["authority"].values())
    policy["cell_ids"].clear(); policy["authority"]["qc_execution_authorized"] = True
    assert hash_payload(transport_policy()) == PROTOCOL_SHA256


@pytest.mark.parametrize("cell", CELL_IDS)
def test_all_cells_have_independent_exact_economic_ledger_and_signed_mirror_close(cell):
    original = CellTransportState.new(cell)
    order = buy(original)
    held = accept_fill(original, order, proof(order))
    rate = Fraction(int(cell.split("-C")[1].split("-")[0]), 10000)
    assert held.economic_cash == Fraction(100000) - 10 * (1 + rate)
    assert held.economic_fees_paid == 10 * rate
    assert held.positions[0].economic_quantity == Fraction(1, 3)
    assert 0 < Fraction(held.positions[0].mirror_quantity) <= Fraction(1, 3)
    sell = prepare_order(held, security_id=order.security_id, event_id="fixture-open-2",
                         order_id="fixture-order-2", side="sell",
                         economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    assert sell.submitted_quantity == -held.positions[0].mirror_quantity
    final = accept_fill(held, sell, proof(sell))
    assert final.positions == ()
    assert final.economic_cash == Fraction(100000) - 20 * rate
    assert final.economic_fees_paid == 20 * rate
    assert final.cumulative_cash_drift_usd + final.cumulative_notional_drift_usd <= MAXIMUM_COMBINED_DRIFT_USD
    assert original.positions == () and original.economic_cash == Fraction(100000)
    assert all(value is False for value in final.to_payload()["authority"].values())


def test_ambient_decimal_precision_does_not_round_authoritative_values():
    original = state()
    with localcontext() as context:
        context.prec = 2
        order = buy(original, price=Fraction(100, 3))
        held = accept_fill(original, order, proof(order))
    assert held.economic_cash == Fraction(100000) - Fraction(100, 9) * Fraction(1001, 1000)
    assert held.positions[0].economic_quantity == Fraction(1, 3)
    assert order.fill_price == Decimal("33.333333333333333333")


def test_buy_reserves_fee_and_posting_quanta_without_borrowing_cash():
    original = state()
    quantity = Fraction(100000) / (Fraction(13, 3) * Fraction(1001, 1000))
    order = buy(original, quantity=quantity, price=Fraction(13, 3))
    held = accept_fill(original, order, proof(order))
    assert held.economic_cash == 0
    assert held.mirror_cash >= 0
    assert Fraction(order.submitted_quantity) <= quantity
    assert Fraction(order.fee_usd) >= Fraction(order.submitted_quantity) * Fraction(order.fill_price) / 1000


@pytest.mark.parametrize("amount,expected", [(Fraction(1, 2) * QUANTUM, 0),
                                             (Fraction(3, 2) * QUANTUM, 2 * QUANTUM),
                                             (Fraction(5, 2) * QUANTUM, 2 * QUANTUM)])
def test_nearest_even_price_and_notional_policy_exact_ties(amount, expected):
    assert _lattice(amount, "nearest_even") == expected


@pytest.mark.parametrize("value", [True, 1, 1.0, Decimal("1"), "1", None])
def test_economic_inputs_never_coerce_bools_floats_or_decimal_context(value):
    with pytest.raises(QCFractionalTransportError):
        buy(quantity=value)
    with pytest.raises(QCFractionalTransportError):
        buy(price=value)


@pytest.mark.parametrize("value", [Fraction(0), Fraction(-1), Fraction(1, 10**19)])
def test_invalid_or_sub_lot_economic_quantities_cannot_fake_an_accepted_fill(value):
    with pytest.raises(QCFractionalTransportError):
        buy(quantity=value)


@pytest.mark.parametrize("value", [Fraction(10**28), Fraction(1, 10**29), Fraction(1, 3)])
def test_system_decimal_representability_refuses_overflow_scale_and_nontermination(value):
    with pytest.raises(QCFractionalTransportError):
        _decimal(value)


def test_28_digit_boundary_and_negative_decimal_are_exact_without_float():
    assert _decimal(Fraction(10**28 - 1)) == Decimal("9999999999999999999999999999")
    assert _decimal(Fraction(-1, 10**28)) == Decimal("-0.0000000000000000000000000001")


@pytest.mark.parametrize("name,value", [("filled_quantity", Decimal("NaN")),
    ("filled_quantity", Decimal("Infinity")), ("filled_quantity", True),
    ("fill_price", 1.0), ("fee_usd", Decimal("-1")),
    ("fill_price", Decimal("1e1000000")), ("fill_price", Decimal("1e-1000000")),
    ("fill_price", Decimal("1" * 5000))])
def test_fill_decimal_types_and_bounds_refuse_before_numeric_coercion(name, value):
    with pytest.raises(QCFractionalTransportError):
        proof(buy(), **{name: value})


@pytest.mark.parametrize("name,value", [("cell_id", CELL_IDS[1]), ("security_id", "qc:other"),
    ("event_id", "other-event"), ("order_id", "other-order"),
    ("filled_quantity", Decimal("0.3")), ("fill_price", Decimal("31")),
    ("fee_usd", Decimal("0")), ("posted_notional_usd", Decimal("11")),
    ("posted_cash_delta_usd", Decimal("-11"))])
def test_every_fill_identity_and_posting_is_bound_and_partial_or_hidden_rounds_refuse(name, value):
    original = state()
    order = buy(original)
    before = original.sha256
    with pytest.raises(QCFractionalTransportError):
        accept_fill(original, order, proof(order, **{name: value}))
    assert original.sha256 == before


def test_cross_cell_stale_and_duplicate_event_or_order_do_not_double_post():
    original = state()
    order = buy(original)
    held = accept_fill(original, order, proof(order))
    with pytest.raises(QCFractionalTransportError, match="stale_state"):
        accept_fill(held, order, proof(order))
    with pytest.raises(QCFractionalTransportError, match="cross_cell"):
        accept_fill(CellTransportState.new(CELL_IDS[1]), order, proof(order))
    for identifiers in ({"order_id": order.order_id, "event": "new-event", "security": "qc:other"},
                        {"order_id": "new-order", "event": order.event_id, "security": order.security_id}):
        with pytest.raises(QCFractionalTransportError, match="duplicate"):
            buy(held, **identifiers)


def test_sell_cannot_freshly_round_economic_quantity_or_partially_close():
    original = state(cost=0, cash=Fraction(10))
    purchased = buy(original, quantity=Fraction(10), price=Fraction(1))
    held = accept_fill(original, purchased, proof(purchased))
    assert Fraction(held.positions[0].mirror_quantity) == 10 - 2 * QUANTUM
    closed = prepare_order(held, security_id=purchased.security_id, event_id="next", order_id="sell",
                           side="sell", economic_quantity=Fraction(10), economic_price=Fraction(1))
    assert Fraction(closed.submitted_quantity) == -(10 - 2 * QUANTUM)
    assert Fraction(closed.submitted_quantity) != -_lattice(Fraction(10), "floor")
    assert accept_fill(held, closed, proof(closed)).positions == ()
    with pytest.raises(QCFractionalTransportError, match="close_existing"):
        prepare_order(held, security_id=purchased.security_id, event_id="next", order_id="sell",
                      side="sell", economic_quantity=Fraction(5), economic_price=Fraction(1))


def test_exact_combined_drift_boundary_accepts_only_no_additional_error():
    original = dataclasses.replace(state(cost=0), cumulative_cash_drift_usd=MAXIMUM_COMBINED_DRIFT_USD)
    order = buy(original, quantity=Fraction(1), price=Fraction(1))
    held = accept_fill(original, order, proof(order))
    assert held.cumulative_cash_drift_usd == MAXIMUM_COMBINED_DRIFT_USD
    assert held.cumulative_notional_drift_usd == 0


def test_cash_and_notional_drift_accumulate_absolutely_even_when_directions_cancel():
    original = state(cash=Fraction(10000000000000))
    with pytest.raises(QCFractionalTransportError, match="drift_budget"):
        buy(original, quantity=Fraction(1, 3), price=Fraction(10000000000000))
    almost = dataclasses.replace(state(), cumulative_cash_drift_usd=MAXIMUM_COMBINED_DRIFT_USD)
    with pytest.raises(QCFractionalTransportError, match="drift_budget"):
        buy(almost)
    with pytest.raises(QCFractionalTransportError, match="drift_budget"):
        dataclasses.replace(state(), cumulative_cash_drift_usd=MAXIMUM_COMBINED_DRIFT_USD + QUANTUM)


def test_round_trip_cash_cancellation_does_not_erase_absolute_transport_drift():
    original = state(cost=0)
    entered = buy(original)
    held = accept_fill(original, entered, proof(entered))
    exited = prepare_order(held, security_id=entered.security_id, event_id="next", order_id="sell",
                           side="sell", economic_quantity=Fraction(1, 3), economic_price=Fraction(30))
    final = accept_fill(held, exited, proof(exited))
    assert final.mirror_cash == original.mirror_cash
    assert final.economic_cash == original.economic_cash
    assert final.cumulative_cash_drift_usd == 20 * QUANTUM
    assert final.cumulative_notional_drift_usd == 20 * QUANTUM


def test_outputs_detached_and_object_mutation_does_not_change_sealed_state_or_pending():
    original = state()
    order = buy(original)
    payload = original.to_payload(); payload["authority"]["qc_execution_authorized"] = True
    payload["economic_cash"]["numerator"] = 999
    assert original.to_payload()["authority"]["qc_execution_authorized"] is False
    held = accept_fill(original, order, proof(order))
    object.__setattr__(held.positions[0], "economic_quantity", Fraction(2))
    with pytest.raises(QCFractionalTransportError, match="identity_changed"):
        held.to_payload()
    changed = buy(original)
    object.__setattr__(changed, "submitted_quantity", Decimal("1"))
    with pytest.raises(QCFractionalTransportError, match="identity_changed"):
        accept_fill(original, changed, proof(order))
    object.__setattr__(original, "economic_cash", Fraction(200000))
    with pytest.raises(QCFractionalTransportError, match="identity_changed"):
        original.to_payload()


def test_reconstructed_pending_with_changed_fee_does_not_bypass_recomputation():
    original = state()
    forged = dataclasses.replace(buy(original), fee_usd=Decimal(0))
    with pytest.raises(QCFractionalTransportError, match="unproven_pending"):
        accept_fill(original, forged, proof(forged))


@pytest.mark.parametrize("kind", [CellTransportState, PendingTransportOrder, FillProof, TransportPosition])
def test_exact_contract_types_cannot_be_subclassed_to_skip_validation(kind):
    class Subclass(kind):
        pass
    with pytest.raises(QCFractionalTransportError):
        if kind is CellTransportState:
            Subclass.new(CELL_IDS[0])
        elif kind is TransportPosition:
            Subclass("qc:fixture", Fraction(1), Decimal(1))
        else:
            reference = buy() if kind is PendingTransportOrder else proof(buy())
            Subclass(**{f.name: getattr(reference, f.name) for f in dataclasses.fields(reference) if f.init})
