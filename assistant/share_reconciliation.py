"""Pure share-count reconciliation helpers.

This module is intentionally dependency-light because execution validation
uses it before broker contact. Corporate-action presentation re-exports the
same helper without making the execution facade import performance, tax-lot,
or other read-side modules transitively.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def detect_split_like_share_mismatch(
    recorded_shares: Decimal | int | str,
    broker_shares: Decimal | int | str,
    *,
    relative_tolerance: Decimal = Decimal("0.01"),
) -> dict[str, Any] | None:
    """Classify a share-count mismatch as an integer-ratio split shape.

    This is detection, not confirmation. A matching result must still refuse
    the stale intent or remain a reconciliation mismatch until the corporate
    action is independently confirmed.
    """
    recorded = Decimal(str(recorded_shares))
    broker = Decimal(str(broker_shares))
    if recorded <= 0 or broker <= 0 or recorded == broker:
        return None
    larger, smaller, direction = (
        (broker, recorded, "forward")
        if broker > recorded
        else (recorded, broker, "reverse")
    )
    ratio = larger / smaller
    nearest = ratio.to_integral_value()
    if nearest < 2:
        return None
    if abs(ratio - nearest) > nearest * relative_tolerance:
        return None
    return {
        "ratio": f"{int(nearest)}:1",
        "direction": direction,
        "recorded_shares": str(recorded),
        "broker_shares": str(broker),
    }
