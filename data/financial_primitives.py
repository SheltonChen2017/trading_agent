"""Product-neutral exact decimal primitives.

These helpers carry no assistant, broker, execution, ML, or research policy.
``assistant.money`` remains a compatibility facade for existing callers.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import (
    Context,
    Decimal,
    DecimalException,
    Inexact,
    InvalidOperation,
    ROUND_HALF_EVEN,
    Rounded,
    localcontext,
)
from typing import Literal, TypeAlias

MoneyInput: TypeAlias = Decimal | int | float | str

_MAX_EXACT_ARITHMETIC_PRECISION = 4096
_MAX_ABS_ADJUSTED_EXPONENT = 999_999
# Match Decimal's historical/default 28-significant-digit projection while
# making it explicit and immune to caller mutation. Ratios are derived/display
# evidence only; authorization paths cross-multiply exact operands instead.
_DETERMINISTIC_DIVISION_PRECISION = 28


def to_decimal(value: MoneyInput, *, name: str = "value") -> Decimal:
    """Return a finite exact decimal representation of ``value``.

    ``Decimal(str(float_value))`` uses the value a human or API sees instead
    of importing the float's hidden binary expansion. Booleans are rejected
    even though ``bool`` is an ``int`` subclass.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite decimal number, got {value!r}.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(
            f"{name} must be a finite decimal number, got {value!r}."
        ) from None
    if not result.is_finite():
        raise ValueError(f"{name} must be a finite decimal number, got {value!r}.")
    return result


def decimal_or_none(value: object) -> Decimal | None:
    """Best-effort finite conversion used by fail-closed validation paths."""
    try:
        return to_decimal(value)  # type: ignore[arg-type]
    except ValueError:
        return None


def decimal_text(value: MoneyInput) -> str:
    """Canonical non-exponent text suitable for exact persistence.

    Construct the text directly from the immutable decimal tuple.  Decimal's
    ``normalize()`` operation obeys the caller's ambient context and can round
    an exact value before it is persisted (for example, a low-precision
    context used by unrelated analytics code).  Tuple projection is exact and
    treats every representation of signed zero as the single canonical ``0``.
    """
    amount = to_decimal(value)
    if amount == 0:
        return "0"
    decimal_tuple = amount.as_tuple()
    digits = "".join(str(digit) for digit in decimal_tuple.digits)
    exponent = int(decimal_tuple.exponent)
    if exponent >= 0:
        body = digits + ("0" * exponent)
    else:
        decimal_point = len(digits) + exponent
        if decimal_point <= 0:
            body = "0." + ("0" * -decimal_point) + digits
        else:
            body = digits[:decimal_point] + "." + digits[decimal_point:]
        body = body.rstrip("0").rstrip(".")
    return ("-" if decimal_tuple.sign else "") + body


def decimal_effective_scale(value: MoneyInput, *, name: str = "value") -> int:
    """Return the exact number of material fractional decimal places.

    Trailing coefficient zeroes do not increase the effective scale:
    ``1.23000`` has scale two and ``1.0000000000`` is integral.  The result is
    derived from :meth:`Decimal.as_tuple`, so it is independent of ambient
    precision, rounding, exponent limits, and traps.  All signed-zero and
    exponent forms of zero have scale zero.
    """
    amount = to_decimal(value, name=name)
    if amount == 0:
        return 0
    decimal_tuple = amount.as_tuple()
    exponent = int(decimal_tuple.exponent)
    if exponent >= 0:
        return 0
    trailing_zeroes = 0
    for digit in reversed(decimal_tuple.digits):
        if digit != 0:
            break
        trailing_zeroes += 1
    return max(0, -exponent - trailing_zeroes)


def _bounded_decimal(value: MoneyInput, *, name: str) -> Decimal:
    parsed = to_decimal(value, name=name)
    if len(parsed.as_tuple().digits) > _MAX_EXACT_ARITHMETIC_PRECISION:
        raise ValueError(
            f"{name} coefficient exceeds the exact-arithmetic precision bound"
        )
    if parsed and abs(parsed.adjusted()) > _MAX_ABS_ADJUSTED_EXPONENT:
        raise ValueError(
            f"{name} exponent exceeds the exact-arithmetic safety bound"
        )
    return parsed


def _exact_binary_precision(
    left: Decimal,
    right: Decimal,
    operation: Literal["add", "subtract", "multiply"],
) -> int:
    if operation == "multiply":
        precision = len(left.as_tuple().digits) + len(right.as_tuple().digits)
    else:
        left_exponent = int(left.as_tuple().exponent)
        right_exponent = int(right.as_tuple().exponent)
        common_exponent = min(left_exponent, right_exponent)
        left_width = len(left.as_tuple().digits) + left_exponent - common_exponent
        right_width = len(right.as_tuple().digits) + right_exponent - common_exponent
        # One guard digit is sufficient for a carry from addition. It is
        # harmless for subtraction and keeps both operations on one proof.
        precision = max(left_width, right_width) + 1
    precision = max(1, precision)
    if precision > _MAX_EXACT_ARITHMETIC_PRECISION:
        raise ValueError(
            "exact decimal arithmetic exceeds the configured precision bound"
        )
    return precision


def _exact_binary_operation(
    left: MoneyInput,
    right: MoneyInput,
    *,
    operation: Literal["add", "subtract", "multiply"],
    name: str,
) -> Decimal:
    left_decimal = _bounded_decimal(left, name=f"{name} left operand")
    right_decimal = _bounded_decimal(right, name=f"{name} right operand")
    if operation == "multiply" and (not left_decimal or not right_decimal):
        return Decimal("0")
    if operation == "add":
        if not left_decimal:
            return right_decimal
        if not right_decimal:
            return left_decimal
    if operation == "subtract" and not right_decimal:
        return left_decimal

    precision = _exact_binary_precision(left_decimal, right_decimal, operation)
    try:
        arithmetic_context = Context(
            prec=precision,
            rounding=ROUND_HALF_EVEN,
            Emin=-_MAX_ABS_ADJUSTED_EXPONENT,
            Emax=_MAX_ABS_ADJUSTED_EXPONENT,
        )
        arithmetic_context.traps[Inexact] = True
        arithmetic_context.traps[Rounded] = True
        with localcontext(arithmetic_context):
            if operation == "add":
                result = left_decimal + right_decimal
            elif operation == "subtract":
                result = left_decimal - right_decimal
            else:
                result = left_decimal * right_decimal
    except DecimalException as exc:
        raise ValueError(f"{name} cannot be represented exactly") from exc
    if not result.is_finite() or (
        result and abs(result.adjusted()) > _MAX_ABS_ADJUSTED_EXPONENT
    ):
        raise ValueError(f"{name} cannot be represented exactly")
    return result


def exact_decimal_add(
    left: MoneyInput, right: MoneyInput, *, name: str = "decimal sum"
) -> Decimal:
    """Return ``left + right`` with no ambient-context rounding."""
    return _exact_binary_operation(left, right, operation="add", name=name)


def exact_decimal_subtract(
    left: MoneyInput, right: MoneyInput, *, name: str = "decimal difference"
) -> Decimal:
    """Return ``left - right`` with no ambient-context rounding."""
    return _exact_binary_operation(left, right, operation="subtract", name=name)


def exact_decimal_multiply(
    left: MoneyInput, right: MoneyInput, *, name: str = "decimal product"
) -> Decimal:
    """Return ``left * right`` with no ambient-context rounding."""
    return _exact_binary_operation(left, right, operation="multiply", name=name)


def exact_decimal_sum(
    values: Iterable[MoneyInput], *, name: str = "decimal sum"
) -> Decimal:
    """Accumulate finite decimals exactly or fail closed."""
    result = Decimal("0")
    for value in values:
        result = exact_decimal_add(result, value, name=name)
    return result


def deterministic_decimal_divide(
    numerator: MoneyInput,
    denominator: MoneyInput,
    *,
    name: str = "decimal ratio",
) -> Decimal:
    """Divide under one explicit context, never the caller's ambient context.

    Many financial ratios are non-terminating, so they cannot satisfy the
    exact-operation contract above. The explicit 28-significant-digit context
    preserves the historical default-context projection deterministically;
    authorization comparisons must still cross-multiply exact operands.
    """
    numerator_decimal = _bounded_decimal(
        numerator, name=f"{name} numerator"
    )
    denominator_decimal = _bounded_decimal(
        denominator, name=f"{name} denominator"
    )
    if denominator_decimal == 0:
        raise ValueError(f"{name} denominator must be nonzero")
    try:
        with localcontext(
            Context(
                prec=_DETERMINISTIC_DIVISION_PRECISION,
                rounding=ROUND_HALF_EVEN,
                Emin=-_MAX_ABS_ADJUSTED_EXPONENT,
                Emax=_MAX_ABS_ADJUSTED_EXPONENT,
            )
        ):
            result = numerator_decimal / denominator_decimal
    except DecimalException as exc:
        raise ValueError(f"{name} cannot be represented deterministically") from exc
    if (
        not result.is_finite()
        or (numerator_decimal != 0 and result == 0)
        or (result and abs(result.adjusted()) > _MAX_ABS_ADJUSTED_EXPONENT)
    ):
        raise ValueError(f"{name} cannot be represented deterministically")
    return result


def deterministic_decimal_quantize(
    value: MoneyInput,
    quantum: MoneyInput,
    *,
    name: str = "decimal projection",
) -> Decimal:
    """Round ``value`` to ``quantum`` under an explicitly sized context.

    This is for deterministic display/projection only.  Authorization must
    compare the unrounded exact operands instead of a quantized result.
    """
    value_decimal = _bounded_decimal(value, name=f"{name} value")
    quantum_decimal = _bounded_decimal(quantum, name=f"{name} quantum")
    if quantum_decimal <= 0:
        raise ValueError(f"{name} quantum must be positive")
    quantum_exponent = int(quantum_decimal.as_tuple().exponent)
    integer_digits = max(value_decimal.adjusted() + 1, 0) if value_decimal else 0
    fractional_digits = max(-quantum_exponent, 0)
    # One guard digit permits a carry (for example, 9.999 -> 10.00).
    precision = max(1, integer_digits + fractional_digits + 1)
    if precision > _MAX_EXACT_ARITHMETIC_PRECISION:
        raise ValueError(
            f"{name} exceeds the configured projection precision bound"
        )
    try:
        projection_context = Context(
            prec=precision,
            rounding=ROUND_HALF_EVEN,
            Emin=-_MAX_ABS_ADJUSTED_EXPONENT,
            Emax=_MAX_ABS_ADJUSTED_EXPONENT,
        )
        with localcontext(projection_context):
            result = value_decimal.quantize(
                quantum_decimal,
                rounding=ROUND_HALF_EVEN,
            )
    except DecimalException as exc:
        raise ValueError(f"{name} cannot be represented deterministically") from exc
    if not result.is_finite():
        raise ValueError(f"{name} cannot be represented deterministically")
    return result
