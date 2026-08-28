"""Dependency-light canonical identity for broker-traded equity symbols."""
from __future__ import annotations

import re


_CANONICAL_EQUITY_TICKER = re.compile(r"[A-Z][A-Z0-9.\-]{0,31}")


def canonical_equity_ticker(value: object, *, name: str = "ticker") -> str:
    """Normalize one supported equity symbol or reject ambiguous identity.

    This is the grammar historically enforced by Alpaca execution quotes.
    Keeping it below both ``assistant`` and ``execution`` lets portfolio
    evidence and broker quote paths agree without inverting either package's
    dependency boundary.
    """
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    canonical = value.strip().upper()
    if not canonical or _CANONICAL_EQUITY_TICKER.fullmatch(canonical) is None:
        raise ValueError(f"{name} is not a supported canonical equity ticker")
    return canonical


def is_canonical_equity_ticker(value: object) -> bool:
    """Return whether ``value`` is already in exact canonical form."""
    if not isinstance(value, str):
        return False
    try:
        return value == canonical_equity_ticker(value)
    except ValueError:
        return False
