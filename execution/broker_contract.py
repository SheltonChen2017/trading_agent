"""Fail-closed broker-order evidence primitives.

Broker payloads are external evidence, not trusted state.  This module keeps
their structural and material validation in one pure boundary so submission,
lookup, reconciliation, stream, and open-book callers do not invent subtly
different meanings for the same order.  It performs no I/O and grants no
execution authority.

Exact ``*_decimal`` companions are authoritative whenever present.  Legacy
float fields remain accepted as an input compatibility path, but are converted
through their text representation and are never used for tolerance matching.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal


AccountMode = Literal["paper", "live"]

# Alpaca's documented order-status vocabulary.  Keeping this set closed is
# intentional: a newly introduced broker status is unresolved evidence until
# its lifecycle and fill semantics have been reviewed.
KNOWN_BROKER_ORDER_STATUSES = frozenset(
    {
        "accepted",
        "accepted_for_bidding",
        "calculated",
        "held",
        "new",
        "pending_new",
        "pending_review",
        "stopped",
        "suspended",
        "partially_filled",
        "pending_cancel",
        "pending_replace",
        "replaced",
        "filled",
        "canceled",
        "rejected",
        "done_for_day",
        "expired",
    }
)

ACTIVE_BROKER_ORDER_STATUSES = frozenset(
    {
        "accepted",
        "accepted_for_bidding",
        "calculated",
        "held",
        "new",
        "pending_new",
        "pending_review",
        "stopped",
        "suspended",
        "partially_filled",
        "pending_cancel",
        "pending_replace",
    }
)

_UNFILLED_BROKER_ORDER_STATUSES = frozenset(
    {
        "accepted",
        "accepted_for_bidding",
        "held",
        "new",
        "pending_new",
        "pending_review",
        "stopped",
        "suspended",
        "rejected",
    }
)
_PARTIAL_OR_ZERO_BROKER_ORDER_STATUSES = frozenset(
    {
        "pending_cancel",
        "pending_replace",
        "replaced",
        "canceled",
        "done_for_day",
        "expired",
    }
)
_CURRENT_ORDER_TYPES = frozenset({"market", "limit"})
_CURRENT_TIME_IN_FORCE = "day"
_IDENTITY_SENTINELS = frozenset({"none", "null", "unknown"})
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,19}$")
_TIMESTAMP_FIELDS = (
    "updated_at",
    "filled_at",
    "canceled_at",
    "expired_at",
    "failed_at",
    "replaced_at",
)


class BrokerOrderIntegrityError(ValueError):
    """Broker evidence is incomplete, malformed, unknown, or mismatched.

    ``code`` is deliberately stable for containment/alert paths; the message
    remains human-readable diagnostic detail and must not drive branching.
    """

    def __init__(self, code: str, message: str, *, field: str | None = None):
        self.code = code
        self.field = field
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str, *, field: str | None = None) -> None:
    raise BrokerOrderIntegrityError(code, message, field=field)


@dataclass(frozen=True)
class BrokerAccountIdentity:
    """The exact broker account and paper/live authority being observed."""

    account_id: str
    account_mode: AccountMode

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise ValueError("account_id must be a non-empty string")
        if self.account_id != self.account_id.strip():
            raise ValueError("account_id must not contain surrounding whitespace")
        account_id = self.account_id
        if account_id.lower() in _IDENTITY_SENTINELS:
            raise ValueError("account_id must identify a real broker account")
        if self.account_mode not in {"paper", "live"}:
            raise ValueError("account_mode must be exactly 'paper' or 'live'")
        object.__setattr__(self, "account_id", account_id)


@dataclass(frozen=True)
class BrokerOrderValidationContext:
    """Optional material expectations applied after strict row validation.

    Root submissions/lookups provide ``expected_client_order_id``.  Once the
    broker has assigned an order ID, every later observation of that root also
    provides ``expected_order_id``.  A broker replacement instead supplies
    ``expected_replaces_order_id`` and separately requires its own non-empty
    client identity; replacement lineage must never be inferred merely because
    another client ID looks similar.
    """

    expected_account: BrokerAccountIdentity
    observed_account: BrokerAccountIdentity
    expected_order_id: str | None = None
    expected_client_order_id: str | None = None
    require_client_order_id: bool = False
    expected_replaces_order_id: str | None = None
    expected_ticker: str | None = None
    expected_side: str | None = None
    expected_order_type: str | None = None
    expected_quantity: object | None = None
    expected_limit_price: object | None = None
    require_active: bool = False
    require_exact_numerics: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.expected_account, BrokerAccountIdentity):
            raise TypeError("expected_account must be BrokerAccountIdentity")
        if not isinstance(self.observed_account, BrokerAccountIdentity):
            raise TypeError("observed_account must be BrokerAccountIdentity")
        material = (
            self.expected_ticker,
            self.expected_side,
            self.expected_order_type,
            self.expected_quantity,
        )
        if any(value is not None for value in material) and any(
            value is None for value in material
        ):
            raise ValueError(
                "material intent expectations must provide ticker, side, "
                "order type, and quantity together"
            )
        if self.expected_limit_price is not None and self.expected_order_type != "limit":
            raise ValueError(
                "expected_limit_price is valid only with expected_order_type='limit'"
            )
        if self.expected_order_type == "limit" and self.expected_limit_price is None:
            raise ValueError("a limit-order expectation requires expected_limit_price")


@dataclass(frozen=True)
class ValidatedBrokerOrder:
    """Canonical evidence safe for exact comparisons and fingerprinting."""

    order_id: str
    client_order_id: str | None
    ticker: str
    asset_class: Literal["us_equity"]
    order_class: Literal["simple"]
    extended_hours: Literal[False]
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    time_in_force: Literal["day"]
    status: str
    quantity: Decimal | None
    notional: Decimal | None
    limit_price: Decimal | None
    filled_quantity: Decimal
    filled_average_price: Decimal | None
    submitted_at: datetime
    updated_at: datetime | None
    filled_at: datetime | None
    canceled_at: datetime | None
    expired_at: datetime | None
    failed_at: datetime | None
    replaced_at: datetime | None
    replaces: str | None
    replaced_by: str | None
    account: BrokerAccountIdentity | None


def _identity(
    value: object,
    *,
    code: str,
    field: str,
    required: bool,
) -> str | None:
    if value is None:
        if required:
            _fail(code, f"{field} is required", field=field)
        return None
    if not isinstance(value, str):
        _fail(code, f"{field} must be a string, got {type(value).__name__}", field=field)
    text = value.strip()
    if value != text:
        _fail(
            code,
            f"{field} must not contain surrounding whitespace",
            field=field,
        )
    if not text or text.lower() in _IDENTITY_SENTINELS:
        _fail(code, f"{field} is not a usable identity: {value!r}", field=field)
    if len(text) > 128 or not text.isascii() or not text.isprintable():
        _fail(
            code,
            f"{field} contains unsupported characters or exceeds 128 characters",
            field=field,
        )
    return text


def _ticker(value: object, *, code: str = "invalid_ticker") -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code, f"ticker must be a non-empty string, got {value!r}", field="ticker")
    canonical = value.strip().upper()
    if not _TICKER_RE.fullmatch(canonical):
        _fail(code, f"ticker is not a supported stock symbol: {value!r}", field="ticker")
    return canonical


def _choice(
    value: object,
    *,
    field: str,
    choices: frozenset[str],
    code: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code, f"{field} is required", field=field)
    canonical = value.strip().lower()
    if canonical not in choices:
        _fail(code, f"unsupported {field}: {value!r}", field=field)
    return canonical


def _decimal(
    value: object,
    *,
    code: str,
    field: str,
    allow_zero: bool,
) -> Decimal:
    if isinstance(value, bool):
        _fail(code, f"{field} cannot be boolean", field=field)
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BrokerOrderIntegrityError(
            code, f"{field} is not numeric: {value!r}", field=field
        ) from exc
    if not parsed.is_finite():
        _fail(code, f"{field} is not finite: {value!r}", field=field)
    if parsed < 0 or (parsed == 0 and not allow_zero):
        comparator = "nonnegative" if allow_zero else "positive"
        _fail(code, f"{field} must be {comparator}: {value!r}", field=field)
    return parsed


def _optional_decimal_field(
    order: Mapping[str, Any],
    *,
    exact_field: str,
    legacy_field: str,
    code: str,
    allow_zero: bool,
    require_exact: bool = False,
) -> Decimal | None:
    exact = order.get(exact_field)
    legacy = order.get(legacy_field)
    if require_exact and exact is None and legacy is not None:
        _fail(
            "missing_exact_numeric",
            f"{exact_field} is required for strict broker evidence",
            field=exact_field,
        )
    if exact is not None:
        parsed_exact = _decimal(
            exact, code=code, field=exact_field, allow_zero=allow_zero
        )
        if legacy is None:
            _fail(
                "missing_legacy_numeric_companion",
                f"{legacy_field} is required alongside {exact_field}",
                field=legacy_field,
            )
        parsed_legacy = _decimal(
            legacy, code=code, field=legacy_field, allow_zero=allow_zero
        )
        if parsed_legacy != parsed_exact:
            _fail(
                "numeric_companion_mismatch",
                f"{exact_field}={parsed_exact} disagrees with "
                f"{legacy_field}={parsed_legacy}",
                field=legacy_field,
            )
        return parsed_exact
    if legacy is None:
        return None
    return _decimal(
        legacy, code=code, field=legacy_field, allow_zero=allow_zero
    )


def _required_decimal_field(
    order: Mapping[str, Any],
    *,
    exact_field: str,
    legacy_field: str,
    code: str,
    allow_zero: bool,
    require_exact: bool = False,
) -> Decimal:
    parsed = _optional_decimal_field(
        order,
        exact_field=exact_field,
        legacy_field=legacy_field,
        code=code,
        allow_zero=allow_zero,
        require_exact=require_exact,
    )
    if parsed is None:
        _fail(code, f"{exact_field} is required", field=exact_field)
    return parsed


def _aware_timestamp(
    value: object,
    *,
    field: str,
    required: bool,
) -> datetime | None:
    code = f"invalid_{field}"
    if value is None:
        if required:
            _fail(code, f"{field} is required", field=field)
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise BrokerOrderIntegrityError(
                code, f"{field} is not ISO-8601: {value!r}", field=field
            ) from exc
    else:
        _fail(code, f"{field} must be an ISO-8601 timestamp", field=field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code, f"{field} must include a timezone offset", field=field)
    return parsed.astimezone(timezone.utc)


def _expected_decimal(value: object, *, field: str) -> Decimal:
    return _decimal(
        value,
        code="invalid_validation_expectation",
        field=field,
        allow_zero=False,
    )


def _validate_fill_state(
    *,
    status: str,
    quantity: Decimal | None,
    filled_quantity: Decimal,
    filled_average_price: Decimal | None,
) -> None:
    if (filled_quantity == 0) != (filled_average_price is None):
        _fail(
            "invalid_fill_state",
            "filled average price must be absent exactly when filled quantity is zero",
            field="filled_avg_price_decimal",
        )

    if quantity is None:
        # The current project never submits notional orders.  An untouched
        # notional-only active order is still useful exposure evidence, but a
        # filled amount cannot be bounded without a requested share quantity.
        if filled_quantity != 0:
            _fail(
                "invalid_fill_state",
                "a nonzero fill cannot be verified without requested quantity",
                field="filled_qty_decimal",
            )
        if status in {"partially_filled", "filled"}:
            _fail(
                "invalid_fill_state",
                f"{status} requires an exact requested quantity",
                field="shares_decimal",
            )
        return

    if filled_quantity > quantity:
        _fail(
            "invalid_fill_state",
            "filled quantity exceeds requested quantity",
            field="filled_qty_decimal",
        )
    if status in _UNFILLED_BROKER_ORDER_STATUSES and filled_quantity != 0:
        _fail(
            "invalid_fill_state",
            f"status {status!r} requires zero filled quantity",
            field="filled_qty_decimal",
        )
    if status == "partially_filled" and not (
        Decimal("0") < filled_quantity < quantity
    ):
        _fail(
            "invalid_fill_state",
            "partially_filled requires 0 < filled quantity < requested quantity",
            field="filled_qty_decimal",
        )
    if status == "filled" and filled_quantity != quantity:
        _fail(
            "invalid_fill_state",
            "filled requires filled quantity equal requested quantity",
            field="filled_qty_decimal",
        )
    if (
        status in _PARTIAL_OR_ZERO_BROKER_ORDER_STATUSES
        and filled_quantity == quantity
    ):
        _fail(
            "invalid_fill_state",
            f"status {status!r} cannot retain a fully filled quantity",
            field="filled_qty_decimal",
        )


def _validate_lifecycle_evidence(
    *,
    order_id: str,
    status: str,
    submitted_at: datetime,
    updated_at: datetime | None,
    filled_at: datetime | None,
    canceled_at: datetime | None,
    expired_at: datetime | None,
    failed_at: datetime | None,
    replaced_at: datetime | None,
    replaces: str | None,
    replaced_by: str | None,
) -> None:
    """Reject contradictory chronology, terminal markers, and lineage."""
    if replaces == order_id or replaced_by == order_id:
        _fail(
            "invalid_replacement_lineage",
            "an order cannot replace or be replaced by itself",
            field="replaces" if replaces == order_id else "replaced_by",
        )
    if replaces is not None and replaces == replaced_by:
        _fail(
            "invalid_replacement_lineage",
            "replaces and replaced_by cannot identify the same adjacent order",
            field="replaced_by",
        )

    timestamp_values = {
        "updated_at": updated_at,
        "filled_at": filled_at,
        "canceled_at": canceled_at,
        "expired_at": expired_at,
        "failed_at": failed_at,
        "replaced_at": replaced_at,
    }
    for field, value in timestamp_values.items():
        if value is not None and value < submitted_at:
            _fail(
                "invalid_order_chronology",
                f"{field} cannot precede submitted_at",
                field=field,
            )
        if updated_at is not None and value is not None and value > updated_at:
            _fail(
                "invalid_order_chronology",
                f"{field} cannot be later than updated_at",
                field=field,
            )

    marker_rules = {
        "filled_at": ({"filled", "calculated"}, filled_at),
        "canceled_at": ({"canceled"}, canceled_at),
        "expired_at": ({"expired"}, expired_at),
        "failed_at": ({"rejected"}, failed_at),
        "replaced_at": ({"replaced"}, replaced_at),
    }
    for field, (allowed_statuses, value) in marker_rules.items():
        if value is not None and status not in allowed_statuses:
            _fail(
                "invalid_status_timestamp",
                f"{field} is incompatible with status {status!r}",
                field=field,
            )

    required_marker = {
        "filled": ("filled_at", filled_at),
        "canceled": ("canceled_at", canceled_at),
        "expired": ("expired_at", expired_at),
        "rejected": ("failed_at", failed_at),
        "replaced": ("replaced_at", replaced_at),
    }.get(status)
    if required_marker is not None and required_marker[1] is None:
        _fail(
            "missing_status_timestamp",
            f"status {status!r} requires {required_marker[0]}",
            field=required_marker[0],
        )
    if status == "replaced" and replaced_by is None:
        _fail(
            "invalid_replacement_lineage",
            "a replaced order requires replaced_by",
            field="replaced_by",
        )
    if status != "replaced" and replaced_by is not None:
        _fail(
            "invalid_replacement_lineage",
            f"status {status!r} cannot carry replaced_by",
            field="replaced_by",
        )


def validate_broker_order(
    order: Mapping[str, Any],
    *,
    context: BrokerOrderValidationContext,
) -> ValidatedBrokerOrder:
    """Validate and canonicalize one normalized broker order.

    Any missing/unknown/malformed material field raises
    :class:`BrokerOrderIntegrityError`; no partial result is returned.
    """
    if not isinstance(order, Mapping):
        _fail(
            "invalid_order_shape",
            f"broker order must be a mapping, got {type(order).__name__}",
        )
    if not isinstance(context, BrokerOrderValidationContext):
        raise TypeError("context must be BrokerOrderValidationContext")

    order_id = _identity(
        order.get("order_id"),
        code="invalid_order_id",
        field="order_id",
        required=True,
    )
    assert order_id is not None
    if context.expected_order_id is not None:
        expected_order_id = _identity(
            context.expected_order_id,
            code="invalid_validation_expectation",
            field="expected_order_id",
            required=True,
        )
        if order_id != expected_order_id:
            _fail(
                "order_id_mismatch",
                f"expected {expected_order_id!r}, got {order_id!r}",
                field="order_id",
            )

    client_order_id = _identity(
        order.get("client_order_id"),
        code=(
            "client_order_id_mismatch"
            if context.expected_client_order_id is not None
            else "invalid_client_order_id"
        ),
        field="client_order_id",
        required=(
            context.require_client_order_id
            or context.expected_client_order_id is not None
        ),
    )
    if context.expected_client_order_id is not None:
        expected_client_order_id = _identity(
            context.expected_client_order_id,
            code="invalid_validation_expectation",
            field="expected_client_order_id",
            required=True,
        )
        if client_order_id != expected_client_order_id:
            _fail(
                "client_order_id_mismatch",
                f"expected {expected_client_order_id!r}, got {client_order_id!r}",
                field="client_order_id",
            )

    replaces = _identity(
        order.get("replaces"),
        code="invalid_replaces_order_id",
        field="replaces",
        required=False,
    )
    replaced_by = _identity(
        order.get("replaced_by"),
        code="invalid_replaced_by_order_id",
        field="replaced_by",
        required=False,
    )
    if context.expected_replaces_order_id is not None:
        expected_replaces = _identity(
            context.expected_replaces_order_id,
            code="invalid_validation_expectation",
            field="expected_replaces_order_id",
            required=True,
        )
        if replaces != expected_replaces:
            _fail(
                "replacement_lineage_mismatch",
                f"expected replaces={expected_replaces!r}, got {replaces!r}",
                field="replaces",
            )
    if context.expected_client_order_id is not None and replaces is not None:
        _fail(
            "replacement_lineage_mismatch",
            "a root client-order lookup returned a replacement order",
            field="replaces",
        )

    ticker = _ticker(order.get("ticker"))
    asset_class = _choice(
        order.get("asset_class"),
        field="asset_class",
        choices=frozenset({"us_equity"}),
        code="unsupported_asset_class",
    )
    order_class = _choice(
        order.get("order_class"),
        field="order_class",
        choices=frozenset({"simple"}),
        code="unsupported_order_class",
    )
    extended_hours = order.get("extended_hours")
    if type(extended_hours) is not bool or extended_hours:
        _fail(
            "unsupported_extended_hours",
            "broker evidence must explicitly identify a regular-hours order",
            field="extended_hours",
        )
    legs = order.get("legs")
    if legs not in (None, []):
        _fail(
            "unsupported_order_legs",
            "contingent or multi-leg orders are not supported",
            field="legs",
        )
    side = _choice(
        order.get("side"),
        field="side",
        choices=frozenset({"buy", "sell"}),
        code="invalid_side",
    )
    order_type = _choice(
        order.get("type"),
        field="type",
        choices=_CURRENT_ORDER_TYPES,
        code="invalid_order_type",
    )
    time_in_force = _choice(
        order.get("time_in_force"),
        field="time_in_force",
        choices=frozenset({_CURRENT_TIME_IN_FORCE}),
        code="invalid_time_in_force",
    )
    status = _choice(
        order.get("status"),
        field="status",
        choices=KNOWN_BROKER_ORDER_STATUSES,
        code="unknown_status",
    )
    if context.require_active and status not in ACTIVE_BROKER_ORDER_STATUSES:
        _fail(
            "inactive_order_status",
            f"open-order evidence contains non-active status {status!r}",
            field="status",
        )

    quantity = _optional_decimal_field(
        order,
        exact_field="shares_decimal",
        legacy_field="shares",
        code="invalid_quantity",
        allow_zero=False,
        require_exact=context.require_exact_numerics,
    )
    notional = _optional_decimal_field(
        order,
        exact_field="notional_decimal",
        legacy_field="notional",
        code="invalid_notional",
        allow_zero=False,
        require_exact=context.require_exact_numerics,
    )
    if (quantity is None) == (notional is None):
        _fail(
            "invalid_order_size",
            "exactly one positive requested quantity or notional is required",
            field="shares_decimal",
        )
    if quantity is not None:
        normalized_quantity = quantity.normalize()
        decimal_places = max(0, -normalized_quantity.as_tuple().exponent)
        if decimal_places > 9:
            _fail(
                "invalid_quantity",
                "share quantity has more than nine decimal places",
                field="shares_decimal",
            )

    limit_price = _optional_decimal_field(
        order,
        exact_field="limit_price_decimal",
        legacy_field="limit_price",
        code="invalid_limit_price",
        allow_zero=False,
        require_exact=context.require_exact_numerics,
    )
    if order_type == "limit" and limit_price is None:
        _fail(
            "invalid_limit_price",
            "limit orders require an exact positive limit price",
            field="limit_price_decimal",
        )
    if order_type == "market" and limit_price is not None:
        _fail(
            "invalid_limit_price",
            "market orders must not carry a limit price",
            field="limit_price_decimal",
        )

    if context.expected_ticker is not None:
        expected_ticker = _ticker(
            context.expected_ticker, code="invalid_validation_expectation"
        )
        if ticker != expected_ticker:
            _fail(
                "ticker_mismatch",
                f"expected {expected_ticker!r}, got {ticker!r}",
                field="ticker",
            )
    if context.expected_side is not None:
        expected_side = _choice(
            context.expected_side,
            field="expected_side",
            choices=frozenset({"buy", "sell"}),
            code="invalid_validation_expectation",
        )
        if side != expected_side:
            _fail(
                "side_mismatch",
                f"expected {expected_side!r}, got {side!r}",
                field="side",
            )
    if context.expected_order_type is not None:
        expected_order_type = _choice(
            context.expected_order_type,
            field="expected_order_type",
            choices=_CURRENT_ORDER_TYPES,
            code="invalid_validation_expectation",
        )
        if order_type != expected_order_type:
            _fail(
                "order_type_mismatch",
                f"expected {expected_order_type!r}, got {order_type!r}",
                field="type",
            )
    if context.expected_quantity is not None:
        expected_quantity = _expected_decimal(
            context.expected_quantity, field="expected_quantity"
        )
        if quantity != expected_quantity:
            _fail(
                "quantity_mismatch",
                f"expected {expected_quantity}, got {quantity}",
                field="shares_decimal",
            )
    if context.expected_limit_price is not None:
        expected_limit_price = _expected_decimal(
            context.expected_limit_price, field="expected_limit_price"
        )
        if limit_price != expected_limit_price:
            _fail(
                "limit_price_mismatch",
                f"expected {expected_limit_price}, got {limit_price}",
                field="limit_price_decimal",
            )

    filled_quantity = _required_decimal_field(
        order,
        exact_field="filled_qty_decimal",
        legacy_field="filled_qty",
        code="invalid_filled_quantity",
        allow_zero=True,
        require_exact=context.require_exact_numerics,
    )
    filled_average_price = _optional_decimal_field(
        order,
        exact_field="filled_avg_price_decimal",
        legacy_field="filled_avg_price",
        code="invalid_filled_average_price",
        allow_zero=True,
        require_exact=context.require_exact_numerics,
    )
    if filled_quantity == 0 and filled_average_price == 0:
        # Alpaca may emit 0 until an outside-hours order is processed. It is
        # unavailable evidence, not an economic zero fill price.
        filled_average_price = None
    if filled_quantity > 0 and (
        filled_average_price is None or filled_average_price <= 0
    ):
        _fail(
            "invalid_fill_state",
            "a positive fill requires a positive average fill price",
            field="filled_avg_price_decimal",
        )
    _validate_fill_state(
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
        filled_average_price=filled_average_price,
    )

    submitted_at = _aware_timestamp(
        order.get("submitted_at"), field="submitted_at", required=True
    )
    assert submitted_at is not None
    timestamps = {
        field: _aware_timestamp(order.get(field), field=field, required=False)
        for field in _TIMESTAMP_FIELDS
    }

    _validate_lifecycle_evidence(
        order_id=order_id,
        status=status,
        submitted_at=submitted_at,
        updated_at=timestamps["updated_at"],
        filled_at=timestamps["filled_at"],
        canceled_at=timestamps["canceled_at"],
        expired_at=timestamps["expired_at"],
        failed_at=timestamps["failed_at"],
        replaced_at=timestamps["replaced_at"],
        replaces=replaces,
        replaced_by=replaced_by,
    )

    expected_account = context.expected_account
    observed_account = context.observed_account
    if observed_account != expected_account:
        _fail(
            "account_mismatch",
            f"expected {expected_account!r}, got {observed_account!r}",
            field="account",
        )

    return ValidatedBrokerOrder(
        order_id=order_id,
        client_order_id=client_order_id,
        ticker=ticker,
        asset_class=asset_class,  # type: ignore[arg-type]
        order_class=order_class,  # type: ignore[arg-type]
        extended_hours=False,
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        time_in_force=time_in_force,  # type: ignore[arg-type]
        status=status,
        quantity=quantity,
        notional=notional,
        limit_price=limit_price,
        filled_quantity=filled_quantity,
        filled_average_price=filled_average_price,
        submitted_at=submitted_at,
        updated_at=timestamps["updated_at"],
        filled_at=timestamps["filled_at"],
        canceled_at=timestamps["canceled_at"],
        expired_at=timestamps["expired_at"],
        failed_at=timestamps["failed_at"],
        replaced_at=timestamps["replaced_at"],
        replaces=replaces,
        replaced_by=replaced_by,
        account=observed_account,
    )


def validate_active_order_set(
    orders: Sequence[Mapping[str, Any]],
    *,
    expected_account: BrokerAccountIdentity,
    observed_account: BrokerAccountIdentity,
) -> tuple[ValidatedBrokerOrder, ...]:
    """Validate an open-order book atomically from the caller's perspective.

    One invalid row raises and therefore produces no usable partial book.
    Duplicate broker order IDs are also incomplete evidence, not two rows to
    silently deduplicate or double count.
    """
    if isinstance(orders, (str, bytes)) or not isinstance(orders, Sequence):
        _fail(
            "invalid_active_order_set",
            f"active orders must be a sequence, got {type(orders).__name__}",
        )
    if observed_account != expected_account:
        _fail(
            "account_mismatch",
            f"expected {expected_account!r}, got {observed_account!r}",
            field="account",
        )
    context = BrokerOrderValidationContext(
        expected_account=expected_account,
        observed_account=observed_account,
        require_active=True,
        require_exact_numerics=True,
    )
    validated: list[ValidatedBrokerOrder] = []
    seen_order_ids: set[str] = set()
    for index, order in enumerate(orders):
        try:
            current = validate_broker_order(order, context=context)
        except BrokerOrderIntegrityError as exc:
            raise BrokerOrderIntegrityError(
                exc.code,
                f"active order row {index} is unusable: {exc}",
                field=exc.field,
            ) from exc
        if current.order_id in seen_order_ids:
            _fail(
                "duplicate_active_order_id",
                f"active order ID appears more than once: {current.order_id!r}",
                field="order_id",
            )
        seen_order_ids.add(current.order_id)
        validated.append(current)
    return tuple(validated)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def validated_broker_order_mapping(order: ValidatedBrokerOrder) -> dict[str, Any]:
    """Materialize one typed order with identical exact/legacy numerics.

    Lifecycle/storage code historically reads the legacy keys. Returning a
    fresh canonical mapping prevents a validated exact companion from being
    discarded while a conflicting raw legacy value drives projection.
    """
    if not isinstance(order, ValidatedBrokerOrder):
        raise TypeError("order must be ValidatedBrokerOrder")
    quantity = _decimal_text(order.quantity)
    notional = _decimal_text(order.notional)
    limit_price = _decimal_text(order.limit_price)
    filled_quantity = _decimal_text(order.filled_quantity)
    filled_average_price = _decimal_text(order.filled_average_price)
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "asset_class": order.asset_class,
        "order_class": order.order_class,
        "extended_hours": order.extended_hours,
        "legs": None,
        "side": order.side,
        "type": order.order_type,
        "time_in_force": order.time_in_force,
        "status": order.status,
        "shares": quantity,
        "shares_decimal": quantity,
        "notional": notional,
        "notional_decimal": notional,
        "limit_price": limit_price,
        "limit_price_decimal": limit_price,
        "filled_qty": filled_quantity,
        "filled_qty_decimal": filled_quantity,
        "filled_avg_price": filled_average_price,
        "filled_avg_price_decimal": filled_average_price,
        "submitted_at": _timestamp_text(order.submitted_at),
        "updated_at": _timestamp_text(order.updated_at),
        "filled_at": _timestamp_text(order.filled_at),
        "canceled_at": _timestamp_text(order.canceled_at),
        "expired_at": _timestamp_text(order.expired_at),
        "failed_at": _timestamp_text(order.failed_at),
        "replaced_at": _timestamp_text(order.replaced_at),
        "replaces": order.replaces,
        "replaced_by": order.replaced_by,
        "broker_account_id": (
            None if order.account is None else order.account.account_id
        ),
        "broker_account_mode": (
            None if order.account is None else order.account.account_mode
        ),
    }


def _material_record(order: ValidatedBrokerOrder) -> dict[str, Any]:
    if not isinstance(order, ValidatedBrokerOrder):
        raise TypeError("fingerprints require ValidatedBrokerOrder values")
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "asset_class": order.asset_class,
        "order_class": order.order_class,
        "extended_hours": order.extended_hours,
        "side": order.side,
        "type": order.order_type,
        "time_in_force": order.time_in_force,
        "status": order.status,
        "quantity": _decimal_text(order.quantity),
        "notional": _decimal_text(order.notional),
        "limit_price": _decimal_text(order.limit_price),
        "filled_quantity": _decimal_text(order.filled_quantity),
        "filled_average_price": _decimal_text(order.filled_average_price),
        "submitted_at": _timestamp_text(order.submitted_at),
        "updated_at": _timestamp_text(order.updated_at),
        "filled_at": _timestamp_text(order.filled_at),
        "canceled_at": _timestamp_text(order.canceled_at),
        "expired_at": _timestamp_text(order.expired_at),
        "failed_at": _timestamp_text(order.failed_at),
        "replaced_at": _timestamp_text(order.replaced_at),
        "replaces": order.replaces,
        "replaced_by": order.replaced_by,
        "account": (
            None
            if order.account is None
            else {
                "account_id": order.account.account_id,
                "account_mode": order.account.account_mode,
            }
        ),
    }


def active_order_material_fingerprint(
    orders: Sequence[ValidatedBrokerOrder],
) -> str:
    """Order-independent SHA-256 over every risk-relevant active-row field."""
    records = sorted(
        (_material_record(order) for order in orders),
        key=lambda record: record["order_id"],
    )
    encoded = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ACTIVE_BROKER_ORDER_STATUSES",
    "KNOWN_BROKER_ORDER_STATUSES",
    "BrokerAccountIdentity",
    "BrokerOrderIntegrityError",
    "BrokerOrderValidationContext",
    "ValidatedBrokerOrder",
    "active_order_material_fingerprint",
    "validate_active_order_set",
    "validate_broker_order",
    "validated_broker_order_mapping",
]
