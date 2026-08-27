"""Canonical temporal bounds and timestamp evidence classification.

Operational timing knobs and persisted/broker timestamps are safety inputs.
Keeping their limits and future-skew semantics here prevents policy, CLI,
readiness, and reconciliation from accepting different values.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


FUTURE_SKEW_TOLERANCE_SECONDS = 5.0
MAX_ORDER_AGE_MINUTES = 31.0 * 24.0 * 60.0
MAX_ABSENCE_AGE_SECONDS = 7.0 * 24.0 * 60.0 * 60.0
MAX_READINESS_WINDOW_SECONDS = MAX_ABSENCE_AGE_SECONDS
MAX_RECOVERY_WINDOW_SECONDS = MAX_ABSENCE_AGE_SECONDS
MAX_MONITOR_INTERVAL_SECONDS = 60.0 * 60.0

_DATETIME_TYPE = datetime


def bounded_timing_number(
    name: str,
    value: Any,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
) -> float:
    """Return a finite bounded builtin number, excluding bool and overflow."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{name} must be a finite number from {minimum} through {maximum}, "
            f"got {value!r}."
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{name} must be a finite number from {minimum} through {maximum}, "
            f"got {value!r}."
        ) from exc
    lower_ok = parsed >= minimum if minimum_inclusive else parsed > minimum
    if not math.isfinite(parsed) or not lower_ok or parsed > maximum:
        relation = "from" if minimum_inclusive else "greater than"
        raise ValueError(
            f"{name} must be {relation} {minimum} through {maximum}, got {value!r}."
        )
    return parsed


def bounded_positive_int(name: str, value: Any, *, maximum: int) -> int:
    """Return a positive builtin integer no greater than ``maximum``."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > maximum
    ):
        raise ValueError(
            f"{name} must be a positive integer no greater than {maximum}, "
            f"got {value!r}."
        )
    return value


def timestamp_disposition(
    value: Any,
    *,
    now: datetime,
    field: str,
    future_skew_tolerance_seconds: float = FUTURE_SKEW_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Classify timestamp evidence without coercing naive time to UTC."""
    if (
        not isinstance(now, _DATETIME_TYPE)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("now must be a timezone-aware datetime")
    now_utc = now.astimezone(timezone.utc)
    raw = None if value is None else str(value)
    base: dict[str, Any] = {
        "field": field,
        "raw": raw,
        "parsed_at": None,
        "signed_age_seconds": None,
        "future_skew_seconds": None,
        "integrity_ok": False,
    }
    if value is None or value == "":
        return {**base, "kind": "missing"}
    if isinstance(value, _DATETIME_TYPE):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return {**base, "kind": "malformed"}
    else:
        return {**base, "kind": "malformed"}
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return {**base, "kind": "naive"}
    parsed = parsed.astimezone(timezone.utc)
    signed_age = (now_utc - parsed).total_seconds()
    future_skew = max(0.0, -signed_age)
    materially_future = future_skew > future_skew_tolerance_seconds
    return {
        **base,
        "kind": (
            "material_future"
            if materially_future
            else "small_future_skew"
            if future_skew > 0
            else "valid"
        ),
        "integrity_ok": not materially_future,
        "parsed_at": parsed.isoformat(),
        "signed_age_seconds": signed_age,
        "future_skew_seconds": future_skew,
    }


__all__ = [
    "FUTURE_SKEW_TOLERANCE_SECONDS",
    "MAX_ABSENCE_AGE_SECONDS",
    "MAX_MONITOR_INTERVAL_SECONDS",
    "MAX_ORDER_AGE_MINUTES",
    "MAX_READINESS_WINDOW_SECONDS",
    "MAX_RECOVERY_WINDOW_SECONDS",
    "bounded_positive_int",
    "bounded_timing_number",
    "timestamp_disposition",
]
