"""Pure, bounded-decimal QC order mirror; never a source or execution permit.

Exact rational economic cash/positions remain independent of the decimal
transport diagnostic. No native equity rounding, automatic dividend, split or
delisting treatment is inferred here. A future custom fill/portfolio model
must implement these explicit postings, not native implicit decimal rounding.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction
from typing import Any

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.latest_revised_protocol import (
    ALLOCATION_ROLES, COSTS_BPS, INITIAL_CASH_USD, LOOKBACKS,
    PROTOCOL_SHA256 as ECONOMIC_PROTOCOL_SHA256,
)

QUANTUM = Fraction(1, 10**18)
MAXIMUM_COMBINED_DRIFT_USD = Fraction(1, 10**6)
MAXIMUM_DECIMAL_COEFFICIENT = 10**28 - 1
CELL_IDS = tuple(f"si-qc-L{lookback}-C{cost}-{role}"
                 for lookback in LOOKBACKS for cost in COSTS_BPS
                 for role in ALLOCATION_ROLES)
_CELLS = {f"si-qc-L{lookback}-C{cost}-{role}": (lookback, cost, role)
          for lookback in LOOKBACKS for cost in COSTS_BPS
          for role in ALLOCATION_ROLES}


class QCFractionalTransportError(ValueError):
    """A diagnostic order transition cannot be proven exactly."""


def _refuse(reason: str) -> QCFractionalTransportError:
    return QCFractionalTransportError("REFUSED: " + reason)


def _authority() -> dict[str, bool]:
    return {"source_admitted": False, "outcome_access_authorized": False,
            "qc_execution_authorized": False, "trading_authority": False,
            "forty_eight_book_financial_authority": False}


def _policy() -> dict[str, Any]:
    return {
        "schema": "si-qc-fractional-transport-policy-v1",
        "economic_protocol_sha256": ECONOMIC_PROTOCOL_SHA256,
        "cell_ids": list(CELL_IDS), "initial_cash_usd": INITIAL_CASH_USD,
        "quantity_lattice": {"numerator": 1, "denominator": 10**18},
        "price_and_posting_lattice": {"numerator": 1, "denominator": 10**18},
        "maximum_decimal_coefficient": MAXIMUM_DECIMAL_COEFFICIENT,
        "maximum_decimal_scale": 28,
        "buy_rule": "toward_zero_lattice_with_two_posting_quanta_reserved",
        "sell_rule": "entire_economic_position_existing_mirror_quantity_no_fresh_rounding",
        "price_and_notional_rule": "explicit_nearest_even_lattice",
        "fee_rule": "explicit_upward_lattice_fixed_cell_bps_per_side",
        "cash_rule": "explicit_posted_notional_plus_or_minus_posted_fee",
        "drift_rule": "sum_absolute_cash_and_notional_differences_no_cancellation",
        "maximum_combined_drift_usd": {"numerator": 1, "denominator": 10**6},
        "fill_rule": "exact_cell_security_event_order_side_quantity_price_fee_and_postings",
        "timing_rule": "registered_idealized_open_only_future_custom_fill_integration",
        "corporate_action_rule": "outside_this_transport_no_native_defaults_inferred",
        "scope": "independent_cell_transport_diagnostic_not_QC_completed_backtest",
        "authority": _authority(),
    }


# Pinned prospectively after the detached specification is finalized.
PROTOCOL_SHA256 = "7ce7b5c8ef5c3e49c0f5ef5de45298ce4f403cfe9809c42829fffc1d5c71fe30"


def transport_policy() -> dict[str, Any]:
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256 or len(_CELLS) != 48:
        raise _refuse("transport_policy_hash_mismatch")
    return payload


def _identifier(value: Any) -> None:
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value != value.strip() or not value.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise _refuse("invalid_identity")


def _fraction(value: Any, *, positive: bool = False) -> Fraction:
    if type(value) is not Fraction or value < 0 or (positive and value == 0):
        raise _refuse("exact_nonnegative_fraction_required")
    return value


def _rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _decimal(value: Fraction) -> Decimal:
    """Construct an exact .NET-safe conservative decimal, without context math."""
    if type(value) is not Fraction:
        raise _refuse("exact_fraction_required")
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
        if twos > 28:
            raise _refuse("system_decimal_bound")
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
        if fives > 28:
            raise _refuse("system_decimal_bound")
    if denominator != 1:
        raise _refuse("nonterminating_decimal")
    scale = max(twos, fives)
    coefficient = abs(value.numerator) * 2**(scale - twos) * 5**(scale - fives)
    while scale and coefficient % 10 == 0:
        coefficient //= 10
        scale -= 1
    if scale > 28 or coefficient > MAXIMUM_DECIMAL_COEFFICIENT:
        raise _refuse("system_decimal_bound")
    digits = tuple(int(c) for c in str(coefficient))
    return Decimal((int(value < 0), digits, -scale))


def _proof_decimal(value: Any, *, positive=False, nonnegative=False) -> Fraction:
    if type(value) is not Decimal or not value.is_finite():
        raise _refuse("exact_finite_decimal_required")
    sign, digits, exponent = value.as_tuple()
    if any(digits):
        if exponent >= 0:
            if len(digits) + exponent > 28:
                raise _refuse("system_decimal_bound")
        else:
            while digits[-1] == 0:
                digits = digits[:-1]
                exponent += 1
            if (-exponent > 28 or len(digits) > 28
                    or len(digits) + max(exponent, 0) > 28):
                raise _refuse("system_decimal_bound")
        result = Fraction(Decimal((sign, digits, exponent)))
    else:
        result = Fraction(0)
    _decimal(result)
    if (positive and result <= 0) or (nonnegative and result < 0):
        raise _refuse("invalid_decimal_sign")
    return result


def _text(value: Decimal) -> str:
    text = format(_decimal(_proof_decimal(value)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _lattice(value: Fraction, direction: str) -> Fraction:
    units = value / QUANTUM
    lower, remainder = divmod(units.numerator, units.denominator)
    if direction == "floor":
        chosen = lower
    elif direction == "ceil":
        chosen = lower + bool(remainder)
    elif direction == "nearest_even":
        chosen = lower + (2 * remainder > units.denominator or
                          (2 * remainder == units.denominator and lower % 2 == 1))
    else:
        raise _refuse("unknown_rounding_rule")
    result = chosen * QUANTUM
    _decimal(result)
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class TransportPosition:
    security_id: str
    economic_quantity: Fraction
    mirror_quantity: Decimal

    def __post_init__(self):
        if type(self) is not TransportPosition:
            raise _refuse("exact_position_type_required")
        _identifier(self.security_id)
        _fraction(self.economic_quantity, positive=True)
        amount = _proof_decimal(self.mirror_quantity, positive=True)
        if (amount / QUANTUM).denominator != 1:
            raise _refuse("quantity_not_on_lattice")

    def payload(self):
        TransportPosition.__post_init__(self)
        return {"security_id": self.security_id,
                "economic_quantity": _rational(self.economic_quantity),
                "mirror_quantity": _text(self.mirror_quantity)}


@dataclasses.dataclass(frozen=True, slots=True)
class CellTransportState:
    cell_id: str
    economic_cash: Fraction
    mirror_cash: Decimal
    positions: tuple[TransportPosition, ...] = ()
    consumed_order_ids: tuple[str, ...] = ()
    consumed_event_keys: tuple[tuple[str, str, str], ...] = ()
    economic_fees_paid: Fraction = Fraction(0)
    mirror_fees_paid: Decimal = Decimal(0)
    cumulative_cash_drift_usd: Fraction = Fraction(0)
    cumulative_notional_drift_usd: Fraction = Fraction(0)
    _sealed: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not CellTransportState:
            raise _refuse("exact_state_type_required")
        object.__setattr__(self, "_sealed", canonical_json(self._payload()))

    @classmethod
    def new(cls, cell_id: str, initial_cash: Fraction = Fraction(INITIAL_CASH_USD)):
        _fraction(initial_cash, positive=True)
        mirror = _lattice(initial_cash, "nearest_even")
        return cls(cell_id, initial_cash, _decimal(mirror),
                   cumulative_cash_drift_usd=abs(initial_cash - mirror))

    def _payload(self):
        transport_policy()
        _identifier(self.cell_id)
        if type(self) is not CellTransportState or self.cell_id not in _CELLS:
            raise _refuse("unknown_cell_or_state_type")
        _fraction(self.economic_cash)
        _proof_decimal(self.mirror_cash, nonnegative=True)
        if type(self.positions) is not tuple or any(type(p) is not TransportPosition for p in self.positions):
            raise _refuse("immutable_exact_positions_required")
        rows = [p.payload() for p in self.positions]
        if [p.security_id for p in self.positions] != sorted(set(p.security_id for p in self.positions)):
            raise _refuse("duplicate_or_unordered_positions")
        if type(self.consumed_order_ids) is not tuple:
            raise _refuse("immutable_unique_order_ids_required")
        for value in self.consumed_order_ids:
            _identifier(value)
        if len(set(self.consumed_order_ids)) != len(self.consumed_order_ids):
            raise _refuse("immutable_unique_order_ids_required")
        if type(self.consumed_event_keys) is not tuple:
            raise _refuse("immutable_unique_event_keys_required")
        for key in self.consumed_event_keys:
            if (type(key) is not tuple or len(key) != 3
                    or type(key[2]) is not str or key[2] not in ("buy", "sell")):
                raise _refuse("invalid_event_key")
            _identifier(key[0]); _identifier(key[1])
        if len(set(self.consumed_event_keys)) != len(self.consumed_event_keys):
            raise _refuse("immutable_unique_event_keys_required")
        _fraction(self.economic_fees_paid)
        _proof_decimal(self.mirror_fees_paid, nonnegative=True)
        cash_drift = _fraction(self.cumulative_cash_drift_usd)
        notional_drift = _fraction(self.cumulative_notional_drift_usd)
        if cash_drift + notional_drift > MAXIMUM_COMBINED_DRIFT_USD:
            raise _refuse("cumulative_drift_budget_exceeded")
        return {"schema": "si-qc-cell-transport-state-v1", "cell_id": self.cell_id,
                "protocol_sha256": PROTOCOL_SHA256,
                "economic_cash": _rational(self.economic_cash), "mirror_cash": _text(self.mirror_cash),
                "positions": rows, "consumed_order_ids": list(self.consumed_order_ids),
                "consumed_event_keys": [list(key) for key in self.consumed_event_keys],
                "economic_fees_paid": _rational(self.economic_fees_paid),
                "mirror_fees_paid": _text(self.mirror_fees_paid),
                "cumulative_cash_drift_usd": _rational(cash_drift),
                "cumulative_notional_drift_usd": _rational(notional_drift),
                "authority": _authority()}

    def to_payload(self):
        value = self._payload()
        if self._sealed != canonical_json(value):
            raise _refuse("state_identity_changed")
        value["state_sha256"] = hash_payload(value)
        return value

    @property
    def sha256(self):
        return CellTransportState.to_payload(self)["state_sha256"]


@dataclasses.dataclass(frozen=True, slots=True)
class PendingTransportOrder:
    cell_id: str
    security_id: str
    event_id: str
    order_id: str
    side: str
    economic_quantity: Fraction
    economic_price: Fraction
    source_state_sha256: str
    submitted_quantity: Decimal
    fill_price: Decimal
    fee_usd: Decimal
    posted_notional_usd: Decimal
    posted_cash_delta_usd: Decimal
    _sealed: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not PendingTransportOrder:
            raise _refuse("exact_pending_order_type_required")
        object.__setattr__(self, "_sealed", canonical_json(self._payload()))

    def _payload(self):
        for value in (self.cell_id, self.security_id, self.event_id, self.order_id):
            _identifier(value)
        if (self.cell_id not in _CELLS or type(self.side) is not str
                or self.side not in ("buy", "sell")):
            raise _refuse("unknown_cell_or_side")
        _fraction(self.economic_quantity, positive=True); _fraction(self.economic_price, positive=True)
        if (type(self.source_state_sha256) is not str or len(self.source_state_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_state_sha256)):
            raise _refuse("invalid_state_digest")
        return {"schema": "si-qc-pending-transport-order-v1", "cell_id": self.cell_id,
                "security_id": self.security_id, "event_id": self.event_id, "order_id": self.order_id,
                "side": self.side, "economic_quantity": _rational(self.economic_quantity),
                "economic_price": _rational(self.economic_price), "source_state_sha256": self.source_state_sha256,
                **{name: _text(getattr(self, name)) for name in (
                    "submitted_quantity", "fill_price", "fee_usd", "posted_notional_usd", "posted_cash_delta_usd")},
                "authority": _authority()}

    def to_payload(self):
        value = self._payload()
        if self._sealed != canonical_json(value):
            raise _refuse("pending_order_identity_changed")
        value["order_sha256"] = hash_payload(value)
        return value


@dataclasses.dataclass(frozen=True, slots=True)
class FillProof:
    cell_id: str
    security_id: str
    event_id: str
    order_id: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fee_usd: Decimal
    posted_notional_usd: Decimal
    posted_cash_delta_usd: Decimal

    def __post_init__(self):
        if type(self) is not FillProof:
            raise _refuse("exact_fill_proof_type_required")
        for value in (self.cell_id, self.security_id, self.event_id, self.order_id):
            _identifier(value)
        if (self.cell_id not in _CELLS or type(self.side) is not str
                or self.side not in ("buy", "sell")):
            raise _refuse("unknown_cell_or_side")
        quantity = _proof_decimal(self.filled_quantity)
        if quantity == 0 or (quantity > 0) != (self.side == "buy"):
            raise _refuse("fill_quantity_sign")
        _proof_decimal(self.fill_price, positive=True)
        _proof_decimal(self.fee_usd, nonnegative=True)
        _proof_decimal(self.posted_notional_usd, positive=True)
        _proof_decimal(self.posted_cash_delta_usd)


def prepare_order(state: CellTransportState, *, security_id: str, event_id: str,
                  order_id: str, side: str, economic_quantity: Fraction,
                  economic_price: Fraction) -> PendingTransportOrder:
    if type(state) is not CellTransportState:
        raise _refuse("exact_state_type_required")
    state.to_payload()
    for value in (security_id, event_id, order_id):
        _identifier(value)
    if side not in ("buy", "sell") or type(side) is not str:
        raise _refuse("unknown_side")
    quantity = _fraction(economic_quantity, positive=True)
    price = _fraction(economic_price, positive=True)
    if order_id in state.consumed_order_ids or (security_id, event_id, side) in state.consumed_event_keys:
        raise _refuse("duplicate_order_or_event")
    position = next((p for p in state.positions if p.security_id == security_id), None)
    rate = Fraction(_CELLS[state.cell_id][1], 10000)
    economic_notional = quantity * price
    economic_fee = economic_notional * rate
    mirrored_price = _lattice(price, "nearest_even")
    if mirrored_price <= 0:
        raise _refuse("nonpositive_mirror_price")
    if side == "buy":
        if position is not None or economic_notional + economic_fee > state.economic_cash:
            raise _refuse("buy_position_or_economic_budget")
        available = Fraction(state.mirror_cash) - 2 * QUANTUM
        if available <= 0:
            raise _refuse("mirror_buy_budget")
        mirrored_quantity = _lattice(min(quantity, available / (mirrored_price * (1 + rate))), "floor")
    else:
        if position is None or quantity != position.economic_quantity:
            raise _refuse("sell_must_close_existing_economic_position")
        mirrored_quantity = Fraction(position.mirror_quantity)
    if mirrored_quantity <= 0:
        raise _refuse("nonpositive_mirror_quantity")
    mirror_notional = _lattice(mirrored_quantity * mirrored_price, "nearest_even")
    mirror_fee = _lattice(mirrored_quantity * mirrored_price * rate, "ceil")
    mirror_delta = -(mirror_notional + mirror_fee) if side == "buy" else mirror_notional - mirror_fee
    economic_delta = -(economic_notional + economic_fee) if side == "buy" else economic_notional - economic_fee
    if mirror_notional <= 0 or Fraction(state.mirror_cash) + mirror_delta < 0:
        raise _refuse("mirror_posting_or_cash_budget")
    combined = (state.cumulative_cash_drift_usd + state.cumulative_notional_drift_usd
                + abs(economic_delta - mirror_delta) + abs(economic_notional - mirror_notional))
    if combined > MAXIMUM_COMBINED_DRIFT_USD:
        raise _refuse("cumulative_drift_budget_exceeded")
    _decimal(Fraction(state.mirror_cash) + mirror_delta)
    return PendingTransportOrder(state.cell_id, security_id, event_id, order_id, side,
                                 quantity, price, state.sha256,
                                 _decimal(mirrored_quantity if side == "buy" else -mirrored_quantity),
                                 _decimal(mirrored_price), _decimal(mirror_fee),
                                 _decimal(mirror_notional), _decimal(mirror_delta))


def accept_fill(state: CellTransportState, order: PendingTransportOrder,
                proof: FillProof) -> CellTransportState:
    """One exact all-or-refused fill; never infer success or accept partial fills."""
    if type(state) is not CellTransportState or type(order) is not PendingTransportOrder or type(proof) is not FillProof:
        raise _refuse("exact_fill_inputs_required")
    state.to_payload(); order.to_payload(); FillProof.__post_init__(proof)
    if order.cell_id != state.cell_id or order.source_state_sha256 != state.sha256:
        raise _refuse("cross_cell_or_stale_state")
    expected = prepare_order(state, security_id=order.security_id, event_id=order.event_id,
                             order_id=order.order_id, side=order.side,
                             economic_quantity=order.economic_quantity, economic_price=order.economic_price)
    if order.to_payload() != expected.to_payload():
        raise _refuse("unproven_pending_order")
    for name in ("cell_id", "security_id", "event_id", "order_id", "side", "fill_price",
                 "fee_usd", "posted_notional_usd", "posted_cash_delta_usd"):
        if getattr(proof, name) != getattr(order, name):
            raise _refuse("fill_proof_mismatch")
    if proof.filled_quantity != order.submitted_quantity:
        raise _refuse("hidden_quantity_rounding_or_partial_fill")
    rate = Fraction(_CELLS[state.cell_id][1], 10000)
    notional = order.economic_quantity * order.economic_price
    fee = notional * rate
    economic_delta = -(notional + fee) if order.side == "buy" else notional - fee
    mirror_delta = Fraction(order.posted_cash_delta_usd)
    positions = [p for p in state.positions if p.security_id != order.security_id]
    if order.side == "buy":
        positions.append(TransportPosition(order.security_id, order.economic_quantity, order.submitted_quantity))
    return CellTransportState(state.cell_id, state.economic_cash + economic_delta,
                              _decimal(Fraction(state.mirror_cash) + mirror_delta),
                              tuple(sorted(positions, key=lambda p: p.security_id)),
                              state.consumed_order_ids + (order.order_id,),
                              state.consumed_event_keys + ((order.security_id, order.event_id, order.side),),
                              state.economic_fees_paid + fee,
                              _decimal(Fraction(state.mirror_fees_paid) + Fraction(order.fee_usd)),
                              state.cumulative_cash_drift_usd + abs(economic_delta - mirror_delta),
                              state.cumulative_notional_drift_usd + abs(notional - Fraction(order.posted_notional_usd)))
