"""Parsing a stored proposal intent back into a TradeIntent.

A shared primitive rather than one seam's helper: the revalidate and submit
phases both parse stored intents, and assistant/order_reconciler.py does too.
Placing it inside claim/ or revalidate/ would force the other seams to import
a peer module's internals, which GR-1 section 6.2 forbids.
"""
from __future__ import annotations

import math
from decimal import Decimal

from risk.execution_gate import TradeIntent, canonical_order_quantity


def _shares_from_stored_value(raw_shares: object) -> int | str:
    """Convert a stored proposal's `shares` field without losing precision.

    Whole quantities remain integers; fractional quantities use canonical
    decimal text with at most nine places. This never silently truncates:
    a bare `int(raw["shares"])`
    silently truncating a malformed value -- a bare `int(raw["shares"])`
    used to turn a corrupted or hand-edited row's `shares: 1.9` into `1`
    with no error at all (GPT review, 2026-07-29: `int()` truncates
    toward zero rather than rejecting a non-whole value). Raises
    ValueError (caught by this module's callers, which already treat a
    malformed stored intent as a hard, fail-closed error) for bools,
    non-finite values, fractional floats, malformed text, and quantities
    beyond the supported precision."""
    if isinstance(raw_shares, bool):
        raise ValueError(f"Stored shares value is a bool ({raw_shares!r}), not a share quantity.")
    if isinstance(raw_shares, int):
        return raw_shares
    if isinstance(raw_shares, float):
        if not math.isfinite(raw_shares):
            raise ValueError(f"Stored shares value is not finite: {raw_shares!r}.")
        if not raw_shares.is_integer():
            raise ValueError(
                f"Stored shares value {raw_shares!r} is fractional, not a whole share count -- refusing "
                "to silently truncate it."
            )
        return int(raw_shares)
    if isinstance(raw_shares, (str, Decimal)):
        quantity = canonical_order_quantity(
            raw_shares, whole_shares_only=False
        )
        if quantity is None:
            raise ValueError(
                f"Stored shares value {raw_shares!r} is not a positive exact "
                "quantity with at most 9 decimal places."
            )
        # Preserve the durable-schema boundary from before SET-1: whole
        # quantities are JSON integers. Decimal text is admitted only when it
        # is genuinely needed to preserve a fractional quantity exactly.
        # This keeps a hand-edited ``"10"`` from silently changing type while
        # still allowing the new canonical ``"0.5"`` representation.
        if isinstance(raw_shares, str) and isinstance(quantity, int):
            raise ValueError(
                f"Stored whole-share value {raw_shares!r} is not numeric in "
                "the durable schema; use an integer, not decimal text."
            )
        return quantity
    raise ValueError(f"Stored shares value {raw_shares!r} ({type(raw_shares).__name__}) is not numeric.")


def _intent_from_dict(raw: dict) -> TradeIntent:
    return TradeIntent(
        ticker=raw["ticker"],
        side=raw["side"],
        shares=_shares_from_stored_value(raw["shares"]),
        order_type=raw.get("order_type", "market"),
        limit_price=raw.get("limit_price"),
        rationale=raw.get("rationale", ""),
    )
