"""Compatibility facade for product-neutral exact decimal primitives.

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
from data.financial_primitives import (
    MoneyInput,
    decimal_or_none,
    decimal_text,
    to_decimal,
)

__all__ = ["MoneyInput", "decimal_or_none", "decimal_text", "to_decimal"]
