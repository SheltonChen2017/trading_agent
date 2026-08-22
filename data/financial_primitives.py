"""Product-neutral exact decimal primitives.

These helpers carry no assistant, broker, execution, ML, or research policy.
``assistant.money`` remains a compatibility facade for existing callers.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypeAlias

MoneyInput: TypeAlias = Decimal | int | float | str


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
    """Canonical non-exponent text suitable for exact persistence."""
    amount = to_decimal(value)
    if amount == 0:
        return "0"
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
