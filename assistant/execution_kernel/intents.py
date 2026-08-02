"""Parsing a stored proposal intent back into a TradeIntent.

A shared primitive rather than one seam's helper: the revalidate and submit
phases both parse stored intents, and assistant/order_reconciler.py does too.
Placing it inside claim/ or revalidate/ would force the other seams to import
a peer module's internals, which GR-1 section 6.2 forbids.
"""
from __future__ import annotations

import math

from risk.execution_gate import TradeIntent


def _shares_from_stored_value(raw_shares: object) -> int:
    """Converts a stored proposal's `shares` field to an int WITHOUT ever
    silently truncating a malformed value -- a bare `int(raw["shares"])`
    used to turn a corrupted or hand-edited row's `shares: 1.9` into `1`
    with no error at all (GPT review, 2026-07-29: `int()` truncates
    toward zero rather than rejecting a non-whole value). Raises
    ValueError (caught by this module's callers, which already treat a
    malformed stored intent as a hard, fail-closed error) for anything
    that isn't a real whole-share quantity: a bool, a non-finite float, a
    fractional float, or a non-numeric value."""
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
