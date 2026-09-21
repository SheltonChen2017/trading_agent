"""Pure accounting for LEAN engine-initiated delisting liquidations.

The caller first resolves the event symbol to a canonical security ID,
translates ``OrderStatus`` through the exact reflected enum bridge, and reads
the originating order through an authenticated QC order-ID lookup. Current
LEAN creates one direct ``Filled`` event for a delisting liquidation; every
broader lifecycle or generic unknown-order shape remains a refusal here.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal


class ForcedDelistingError(ValueError):
    """A purported engine delisting fill or ledger was refused."""


FORCED_DELISTING_TAG = "Liquidate from delisting"
LEAN_NULL_CURRENCY = "QCC"
FORCED_DELISTING_SUMMARY_SCHEMA = (
    "arv2-order-level-forced-delisting-summary-v1"
)
_LEDGER_SCHEMA = "arv2-order-level-forced-delisting-ledger-v1"
FILLED_STATUS = "Filled"
_SYSTEM_DECIMAL_MAXIMUM = 79228162514264337593543950335
_SYSTEM_DECIMAL_MAXIMUM_SCALE = 28
_SHA256_LENGTH = 64
_LOWER_HEX = frozenset("0123456789abcdef")

UNKNOWN_ORDER_REFUSAL = "order-level event references an unknown QC order"
LEDGER_REFUSAL = "order-level forced delisting ledger changed"
ORDER_ID_REFUSAL = "order-level forced delisting order identity changed"
EVENT_ID_REFUSAL = "order-level forced delisting event identity changed"
DUPLICATE_EVENT_REFUSAL = "duplicate forced delisting event"
EVENT_ID_MUTATION_REFUSAL = "forced delisting event identity was reused"
ORDER_ID_MUTATION_REFUSAL = "forced delisting order identity was reused"
STATUS_REFUSAL = "order-level forced delisting status is unsupported"
QUANTITY_REFUSAL = "order-level forced delisting quantity is invalid"
OVER_CLOSE_REFUSAL = "order-level forced delisting quantity exceeds holdings"
INCOMPLETE_CLOSE_REFUSAL = "order-level forced delisting did not close holdings"
PRICE_REFUSAL = "order-level forced delisting fill price is invalid"
FEE_REFUSAL = "order-level forced delisting fee is invalid"


@dataclasses.dataclass(frozen=True)
class _OrderBinding:
    order_key_sha256: str
    security_id_sha256: str
    maximum_sale_quantity: int


@dataclasses.dataclass(frozen=True)
class _EventBinding:
    event_key_sha256: str
    order_key_sha256: str
    payload_sha256: str
    fill_price_coefficient: int
    fill_price_exponent: int
    fee_amount_coefficient: int
    fee_amount_exponent: int
    fee_currency: str


@dataclasses.dataclass(frozen=True)
class ForcedDelistingLedger:
    """Immutable state containing identifier commitments, never raw rows."""

    order_bindings: tuple
    event_bindings: tuple
    integrity_sha256: str


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ForcedDelistingError(LEDGER_REFUSAL) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha256(value):
    return (
        type(value) is str
        and len(value) == _SHA256_LENGTH
        and all(character in _LOWER_HEX for character in value)
    )


def _normalise_components(coefficient, exponent):
    if type(coefficient) is not int or coefficient < 0 or type(exponent) is not int:
        raise ForcedDelistingError(LEDGER_REFUSAL)
    if coefficient == 0:
        return 0, 0
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    return coefficient, exponent


def _system_decimal_components_are_valid(coefficient, exponent):
    try:
        if _normalise_components(coefficient, exponent) != (coefficient, exponent):
            return False
    except ForcedDelistingError:
        return False
    if coefficient == 0:
        return exponent == 0
    if exponent < -_SYSTEM_DECIMAL_MAXIMUM_SCALE or exponent > 28:
        return False
    if exponent >= 0:
        return coefficient * (10**exponent) <= _SYSTEM_DECIMAL_MAXIMUM
    return coefficient <= _SYSTEM_DECIMAL_MAXIMUM


def _decimal_components(value, refusal):
    """Return a canonical exact representation of one CLR ``System.Decimal``."""

    if type(value) is not Decimal or not value.is_finite() or value < 0:
        raise ForcedDelistingError(refusal)
    sign, digits, exponent = value.as_tuple()
    if sign:
        raise ForcedDelistingError(refusal)
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    coefficient, exponent = _normalise_components(coefficient, exponent)
    # Python Decimal is unbounded, while every value entering through LEAN is a
    # CLR System.Decimal.  Keeping that exact host bound makes the integer
    # arithmetic below memory-bounded and proves that no ambient Decimal
    # precision or rounding mode can change the ledger.
    if not _system_decimal_components_are_valid(coefficient, exponent):
        raise ForcedDelistingError(refusal)
    return coefficient, exponent


def _decimal_text_from_components(coefficient, exponent):
    coefficient, exponent = _normalise_components(coefficient, exponent)
    if coefficient == 0:
        return "0"
    digits = str(coefficient)
    if exponent >= 0:
        return digits + ("0" * exponent)
    scale = -exponent
    if len(digits) <= scale:
        return "0." + ("0" * (scale - len(digits))) + digits
    return digits[:-scale] + "." + digits[-scale:]


def _sum_components(values):
    values = tuple(values)
    if not values:
        return 0, 0
    minimum_exponent = min(exponent for _, exponent in values)
    coefficient = sum(
        item_coefficient * (10 ** (item_exponent - minimum_exponent))
        for item_coefficient, item_exponent in values
    )
    return _normalise_components(coefficient, minimum_exponent)


def _multiply_components(multiplier, coefficient, exponent):
    if type(multiplier) is not int or multiplier <= 0:
        raise ForcedDelistingError(LEDGER_REFUSAL)
    return _normalise_components(multiplier * coefficient, exponent)


def _printable_identifier(value, message):
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isascii()
        or len(value) > 512
        or any(ord(character) < 32 or ord(character) > 126 for character in value)
    ):
        raise ForcedDelistingError(message)
    return value


def _order_identifier(value):
    if type(value) is not int or value < 0:
        raise ForcedDelistingError(ORDER_ID_REFUSAL)
    return "int:" + str(value)


def _event_identifier(value):
    if type(value) is not int or value < 0:
        raise ForcedDelistingError(EVENT_ID_REFUSAL)
    return "int:" + str(value)


def _order_record(item):
    return {
        "order_key_sha256": item.order_key_sha256,
        "security_id_sha256": item.security_id_sha256,
        "maximum_sale_quantity": item.maximum_sale_quantity,
    }


def _event_record(item):
    return {
        "event_key_sha256": item.event_key_sha256,
        "order_key_sha256": item.order_key_sha256,
        "payload_sha256": item.payload_sha256,
        "fill_price_coefficient": item.fill_price_coefficient,
        "fill_price_exponent": item.fill_price_exponent,
        "fee_amount_coefficient": item.fee_amount_coefficient,
        "fee_amount_exponent": item.fee_amount_exponent,
        "fee_currency": item.fee_currency,
    }


def _ledger_seed(ledger):
    return {
        "schema": _LEDGER_SCHEMA,
        "order_bindings": [_order_record(item) for item in ledger.order_bindings],
        "event_bindings": [_event_record(item) for item in ledger.event_bindings],
    }


def _payload_seed(order, event):
    return {
        "schema": "arv2-order-level-forced-delisting-event-v1",
        "order_key_sha256": order.order_key_sha256,
        "event_key_sha256": event.event_key_sha256,
        "security_id_sha256": order.security_id_sha256,
        "status": FILLED_STATUS,
        "maximum_sale_quantity": order.maximum_sale_quantity,
        "signed_fill_quantity": str(-order.maximum_sale_quantity),
        "fill_price": _decimal_text_from_components(
            event.fill_price_coefficient,
            event.fill_price_exponent,
        ),
        "fee_amount": _decimal_text_from_components(
            event.fee_amount_coefficient,
            event.fee_amount_exponent,
        ),
        "fee_currency": event.fee_currency,
    }


def _require_ledger(ledger):
    try:
        if (
            type(ledger) is not ForcedDelistingLedger
            or type(ledger.order_bindings) is not tuple
            or type(ledger.event_bindings) is not tuple
            or not all(
                type(item) is _OrderBinding for item in ledger.order_bindings
            )
            or not all(
                type(item) is _EventBinding for item in ledger.event_bindings
            )
        ):
            raise ForcedDelistingError(LEDGER_REFUSAL)

        order_keys = tuple(item.order_key_sha256 for item in ledger.order_bindings)
        event_keys = tuple(item.event_key_sha256 for item in ledger.event_bindings)
        event_order_keys = tuple(
            item.order_key_sha256 for item in ledger.event_bindings
        )
        valid = all(
            _is_sha256(item.order_key_sha256)
            and _is_sha256(item.security_id_sha256)
            and type(item.maximum_sale_quantity) is int
            and item.maximum_sale_quantity > 0
            and item.maximum_sale_quantity <= _SYSTEM_DECIMAL_MAXIMUM
            for item in ledger.order_bindings
        )
        valid = valid and all(
            _is_sha256(item.event_key_sha256)
            and _is_sha256(item.order_key_sha256)
            and _is_sha256(item.payload_sha256)
            and _system_decimal_components_are_valid(
                item.fill_price_coefficient,
                item.fill_price_exponent,
            )
            and type(item.fee_amount_coefficient) is int
            and item.fee_amount_coefficient == 0
            and type(item.fee_amount_exponent) is int
            and item.fee_amount_exponent == 0
            and type(item.fee_currency) is str
            and item.fee_currency == LEAN_NULL_CURRENCY
            for item in ledger.event_bindings
        )
        valid = (
            valid
            and tuple(sorted(order_keys)) == order_keys
            and len(set(order_keys)) == len(order_keys)
            and tuple(sorted(event_keys)) == event_keys
            and len(set(event_keys)) == len(event_keys)
            and len(ledger.order_bindings) == len(ledger.event_bindings)
            and len(set(event_order_keys)) == len(event_order_keys)
            and set(event_order_keys) == set(order_keys)
        )
        if valid:
            orders = {item.order_key_sha256: item for item in ledger.order_bindings}
            valid = all(
                _sha(_payload_seed(orders[item.order_key_sha256], item))
                == item.payload_sha256
                for item in ledger.event_bindings
            )
        valid = (
            valid
            and _is_sha256(ledger.integrity_sha256)
            and _sha(_ledger_seed(ledger)) == ledger.integrity_sha256
        )
    except (AttributeError, ForcedDelistingError, KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ForcedDelistingError(LEDGER_REFUSAL)
    return ledger


def _seal(**values):
    seed = ForcedDelistingLedger(integrity_sha256="", **values)
    sealed = dataclasses.replace(seed, integrity_sha256=_sha(_ledger_seed(seed)))
    return _require_ledger(sealed)


def empty_forced_delisting_ledger():
    """Return the sole empty authenticated ledger."""

    return _seal(
        order_bindings=(),
        event_bindings=(),
    )


def record_forced_delisting_fill(
    ledger,
    *,
    authenticated_delisted_security_ids,
    security_id,
    order_id,
    event_id,
    event_message,
    order_tag,
    status,
    maximum_sale_quantity,
    signed_fill_quantity,
    fill_price,
    fee_amount,
    fee_currency,
):
    """Authenticate LEAN's exact direct delisting fill and return a new ledger.

    Quantity and money inputs must already be exact ``Decimal`` objects.
    Failed SID/message/tag authentication deliberately returns the same fixed
    refusal as every other unknown QC order.
    """

    ledger = _require_ledger(ledger)
    if type(authenticated_delisted_security_ids) is not frozenset:
        raise ForcedDelistingError(UNKNOWN_ORDER_REFUSAL)
    security_id = _printable_identifier(security_id, UNKNOWN_ORDER_REFUSAL)
    if (
        security_id not in authenticated_delisted_security_ids
        or any(
            _printable_identifier(item, UNKNOWN_ORDER_REFUSAL) == ""
            for item in authenticated_delisted_security_ids
        )
        or type(event_message) is not str
        or event_message != FORCED_DELISTING_TAG
        or type(order_tag) is not str
        or order_tag != FORCED_DELISTING_TAG
    ):
        raise ForcedDelistingError(UNKNOWN_ORDER_REFUSAL)
    if type(status) is not str or status != FILLED_STATUS:
        raise ForcedDelistingError(STATUS_REFUSAL)
    if (
        type(maximum_sale_quantity) is not int
        or maximum_sale_quantity <= 0
        or maximum_sale_quantity > _SYSTEM_DECIMAL_MAXIMUM
    ):
        raise ForcedDelistingError(QUANTITY_REFUSAL)
    if (
        type(signed_fill_quantity) is not Decimal
        or not signed_fill_quantity.is_finite()
        or signed_fill_quantity >= 0
        or signed_fill_quantity != signed_fill_quantity.to_integral_value()
    ):
        raise ForcedDelistingError(QUANTITY_REFUSAL)
    quantity = int(-signed_fill_quantity)
    if quantity > maximum_sale_quantity:
        raise ForcedDelistingError(OVER_CLOSE_REFUSAL)
    if quantity != maximum_sale_quantity:
        raise ForcedDelistingError(INCOMPLETE_CLOSE_REFUSAL)
    fill_price_coefficient, fill_price_exponent = _decimal_components(
        fill_price,
        PRICE_REFUSAL,
    )
    fee_amount_coefficient, fee_amount_exponent = _decimal_components(
        fee_amount,
        FEE_REFUSAL,
    )
    if (
        fee_amount_coefficient != 0
        or fee_amount_exponent != 0
        or type(fee_currency) is not str
        or fee_currency != LEAN_NULL_CURRENCY
    ):
        raise ForcedDelistingError(FEE_REFUSAL)

    order_key = _sha({"order_id": _order_identifier(order_id)})
    event_key = _sha(
        {"order": order_key, "event_id": _event_identifier(event_id)}
    )
    security_key = _sha({"security_id": "str:" + security_id})
    order_binding = _OrderBinding(
        order_key_sha256=order_key,
        security_id_sha256=security_key,
        maximum_sale_quantity=maximum_sale_quantity,
    )
    event_binding = _EventBinding(
        event_key_sha256=event_key,
        order_key_sha256=order_key,
        payload_sha256="",
        fill_price_coefficient=fill_price_coefficient,
        fill_price_exponent=fill_price_exponent,
        fee_amount_coefficient=fee_amount_coefficient,
        fee_amount_exponent=fee_amount_exponent,
        fee_currency=fee_currency,
    )
    event_binding = dataclasses.replace(
        event_binding,
        payload_sha256=_sha(_payload_seed(order_binding, event_binding)),
    )
    payload_sha256 = event_binding.payload_sha256
    prior_events = {
        item.event_key_sha256: item.payload_sha256
        for item in ledger.event_bindings
    }
    if event_key in prior_events:
        raise ForcedDelistingError(
            DUPLICATE_EVENT_REFUSAL
            if prior_events[event_key] == payload_sha256
            else EVENT_ID_MUTATION_REFUSAL
        )
    bindings = {item.order_key_sha256: item for item in ledger.order_bindings}
    if order_key in bindings:
        raise ForcedDelistingError(ORDER_ID_MUTATION_REFUSAL)
    bindings[order_key] = order_binding
    events = {
        item.event_key_sha256: item for item in ledger.event_bindings
    }
    events[event_key] = event_binding
    return _seal(
        order_bindings=tuple(bindings[key] for key in sorted(bindings)),
        event_bindings=tuple(events[key] for key in sorted(events)),
    )


def forced_delisting_signed_quantity(ledger, security_id):
    """Return the cumulative authenticated signed quantity for one SID."""

    ledger = _require_ledger(ledger)
    security_id = _printable_identifier(security_id, UNKNOWN_ORDER_REFUSAL)
    security_key = _sha({"security_id": "str:" + security_id})
    return -sum(
        item.maximum_sale_quantity
        for item in ledger.order_bindings
        if item.security_id_sha256 == security_key
    )


def forced_delisting_summary(ledger):
    """Return deterministic aggregate evidence with no raw event rows."""

    ledger = _require_ledger(ledger)
    count = len(ledger.order_bindings)
    orders = {item.order_key_sha256: item for item in ledger.order_bindings}
    notional_coefficient, notional_exponent = _sum_components(
        _multiply_components(
            orders[item.order_key_sha256].maximum_sale_quantity,
            item.fill_price_coefficient,
            item.fill_price_exponent,
        )
        for item in ledger.event_bindings
    )
    fee_coefficient, fee_exponent = _sum_components(
        (item.fee_amount_coefficient, item.fee_amount_exponent)
        for item in ledger.event_bindings
    )
    return {
        "schema": FORCED_DELISTING_SUMMARY_SCHEMA,
        "order_count": count,
        "event_count": len(ledger.event_bindings),
        "fill_event_count": len(ledger.event_bindings),
        "terminal_order_count": count,
        "absolute_filled_quantity": sum(
            item.maximum_sale_quantity for item in ledger.order_bindings
        ),
        "filled_notional": _decimal_text_from_components(
            notional_coefficient,
            notional_exponent,
        ),
        "actual_engine_fee_amount": _decimal_text_from_components(
            fee_coefficient,
            fee_exponent,
        ),
        "accounting_complete": True,
        "ledger_sha256": _sha(
            {
                **_ledger_seed(ledger),
                "integrity_sha256": ledger.integrity_sha256,
            }
        ),
        "raw_order_rows_in_summary": False,
        "raw_security_rows_in_summary": False,
    }


__all__ = (
    "FILLED_STATUS",
    "FORCED_DELISTING_SUMMARY_SCHEMA",
    "FORCED_DELISTING_TAG",
    "LEAN_NULL_CURRENCY",
    "ForcedDelistingError",
    "ForcedDelistingLedger",
    "empty_forced_delisting_ledger",
    "forced_delisting_signed_quantity",
    "forced_delisting_summary",
    "record_forced_delisting_fill",
)
