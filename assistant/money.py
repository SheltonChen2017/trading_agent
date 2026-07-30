"""Exact numeric helpers for execution-critical monetary arithmetic.

Public portfolio/broker payloads in this project historically expose JSON
numbers as ``float``.  Replacing those fields wholesale would break callers
that serialize them, but doing cash/notional/exposure arithmetic with binary
floats can move an exact boundary (for example 0.1 + 0.2 versus a 0.3 daily
cap).  Execution code therefore converts each input through its decimal
*text* representation before performing monetary arithmetic.

Do not quantize here: broker prices and fills may legitimately carry more
than two decimal places.  Presentation code may round for display, while the
risk and reservation layers retain every supplied decimal digit.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypeAlias

MoneyInput: TypeAlias = Decimal | int | float | str


def to_decimal(value: MoneyInput, *, name: str = "value") -> Decimal:
    """Return a finite exact decimal representation of ``value``.

    ``Decimal(str(float_value))`` intentionally uses the value a human/API
    sees (``0.1``), rather than importing the float's hidden binary expansion
    (``Decimal(float_value)``).  Booleans are rejected even though ``bool`` is
    an ``int`` subclass.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite decimal number, got {value!r}.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a finite decimal number, got {value!r}.") from None
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
    """Canonical non-exponent text suitable for exact SQLite persistence."""
    amount = to_decimal(value)
    if amount == 0:
        return "0"
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
