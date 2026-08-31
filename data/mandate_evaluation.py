"""Provider-neutral deterministic mandate metric evaluation.

The trading assistant owns approval, persistence, defaults, promotion gates,
and execution policy. This module only compares caller-supplied metrics with
caller-supplied limits so research code does not import the assistant product.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Protocol


class MandateMetricContract(Protocol):
    version: str
    target_annualized_volatility_min_pct: float
    target_annualized_volatility_max_pct: float
    max_drawdown_pct: float
    max_time_under_water_sessions: int
    max_downside_capture_pct: float
    min_upside_capture_pct: float

    def to_dict(self) -> dict[str, Any]: ...


_APPROVAL_METADATA_FIELDS = {
    "status",
    "approved_at",
    "approved_by",
    "approved_fingerprint",
    "notes",
}


def compute_mandate_fingerprint(mandate: MandateMetricContract) -> str:
    payload = {
        key: value
        for key, value in mandate.to_dict().items()
        if key not in _APPROVAL_METADATA_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _metric_check(
    name: str,
    actual: Any,
    *,
    predicate,
    target: str,
) -> dict[str, Any]:
    if actual is None:
        return {
            "name": name,
            "passed": False,
            "available": False,
            "actual": None,
            "target": target,
            "detail": "metric unavailable",
        }
    # bool is an int subclass. Accepting it would turn corrupt metric state
    # into a plausible 0.0/1.0 value and could reverse a mandate gate.
    try:
        # Independent review, 2026-07-31 (P2 #5): float(actual) alone doesn't
        # exclude bool before casting, unlike every other numeric-validation
        # path in this codebase (financial_primitives/money, tax_lots,
        # portfolio_ledger, allocation_proposals) -- isinstance(True, int) is
        # True, so a stray boolean would otherwise silently coerce to 0.0/1.0
        # instead of being rejected as not-a-metric. (Rationale restored after
        # the SEP-1 move dropped it; the check itself moved intact.)
        if isinstance(actual, bool):
            raise TypeError(
                f"metric {name!r} must be a number, got bool {actual!r}"
            )
        value = float(actual)
    except (OverflowError, TypeError, ValueError):
        value = math.nan
    valid = math.isfinite(value)
    return {
        "name": name,
        "passed": bool(valid and predicate(value)),
        "available": valid,
        "actual": value if valid else None,
        "target": target,
        "detail": "evaluated" if valid else "metric is not finite",
    }


def evaluate_mandate_metrics(
    mandate: MandateMetricContract, metrics: dict[str, Any]
) -> dict[str, Any]:
    """Score deterministic metrics against the supplied mandate limits."""
    checks = [
        _metric_check(
            "annualized_volatility_pct",
            metrics.get("annualized_volatility_pct"),
            predicate=lambda value: (
                mandate.target_annualized_volatility_min_pct
                <= value
                <= mandate.target_annualized_volatility_max_pct
            ),
            target=(
                f"{mandate.target_annualized_volatility_min_pct}%–"
                f"{mandate.target_annualized_volatility_max_pct}%"
            ),
        ),
        _metric_check(
            "max_drawdown_pct",
            metrics.get("max_drawdown_pct"),
            predicate=lambda value: (
                value <= 0 and abs(value) <= mandate.max_drawdown_pct
            ),
            target=f"no worse than -{mandate.max_drawdown_pct}%",
        ),
        _metric_check(
            "max_time_under_water_sessions",
            metrics.get("max_time_under_water_sessions"),
            predicate=lambda value: value
            <= mandate.max_time_under_water_sessions,
            target=f"≤ {mandate.max_time_under_water_sessions}",
        ),
        _metric_check(
            "downside_capture_pct",
            metrics.get("downside_capture_pct"),
            predicate=lambda value: value <= mandate.max_downside_capture_pct,
            target=f"≤ {mandate.max_downside_capture_pct}%",
        ),
        _metric_check(
            "upside_capture_pct",
            metrics.get("upside_capture_pct"),
            predicate=lambda value: value >= mandate.min_upside_capture_pct,
            target=f"≥ {mandate.min_upside_capture_pct}%",
        ),
    ]
    return {
        "passed": all(check["passed"] for check in checks),
        "mandate_version": mandate.version,
        "mandate_fingerprint": compute_mandate_fingerprint(mandate),
        "checks": checks,
    }


__all__ = [
    "MandateMetricContract",
    "compute_mandate_fingerprint",
    "evaluate_mandate_metrics",
]
