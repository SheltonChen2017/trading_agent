"""Synthetic diagnostics and source fingerprints; never an alpha verdict."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from data.financial_primitives import (
    decimal_text, deterministic_decimal_divide as divide,
    exact_decimal_multiply as mul, exact_decimal_subtract as sub,
    exact_decimal_sum as total,
)
from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import _read_regular_file, MAX_SOURCE_DOCUMENT_BYTES


def source_manifest() -> dict[str, str]:
    """Hash actual local source bytes, without invoking Git or reading secrets.

    No asserted commit ID stands in for the bytes being executed. The review
    handoff separately binds the eventual Git snapshot. Changes require a new
    fixture epoch even when the economic candidate hash stays the same.
    """
    package = Path(__file__).resolve().parent
    root = package.parents[1]
    paths = sorted(package.glob("*.py")) + [root / "data/hashing.py", root / "data/financial_primitives.py"]
    return {p.relative_to(root).as_posix(): hash_bytes(_read_regular_file(p, MAX_SOURCE_DOCUMENT_BYTES))
            for p in paths}


def paired_nav_diagnostics(rows: tuple[tuple[date, Decimal | None, Decimal | None], ...], *,
                           expected_session_dates: tuple[date, ...]) -> dict:
    """Keep every paired calendar date; missing rows block instead of dropping.

    Return arithmetic is a deterministic 28-digit descriptive projection.
    No interval, p-value, power sufficiency or promotion is inferred from it.
    """
    if type(rows) is not tuple or not 2 <= len(rows) <= 10000:
        raise ValueError("bounded paired daily calendar with at least two observations required")
    if (type(expected_session_dates) is not tuple or not 2 <= len(expected_session_dates) <= 10000
            or any(type(day) is not date for day in expected_session_dates)
            or expected_session_dates != tuple(sorted(set(expected_session_dates)))):
        raise ValueError("explicit ordered unique expected session dates required")
    prior = None
    missing = []
    for row in rows:
        if type(row) is not tuple or len(row) != 3 or type(row[0]) is not date:
            raise ValueError("exact dated strategy/comparator row required")
        if prior is not None and row[0] <= prior:
            raise ValueError("duplicate or nonchronological daily calendar")
        prior = row[0]
        for value in row[1:]:
            if value is None:
                missing.append(row[0].isoformat())
            elif (type(value) is not Decimal or not value.is_finite() or value <= 0
                  or len(value.as_tuple().digits) > 64 or abs(int(value.as_tuple().exponent)) > 32):
                raise ValueError("positive bounded exact NAV or explicit missing value required")
    if tuple(row[0] for row in rows) != expected_session_dates:
        raise ValueError("paired NAV calendar differs from pinned expected sessions")
    result = {
        "kind": "synthetic_descriptive_only", "calendar_observations": len(rows),
        "return_intervals": len(rows) - 1, "missing_dates": sorted(set(missing)),
        "annualized_arithmetic_excess": None, "strategy_max_drawdown": None,
        "comparator_max_drawdown": None, "sufficient_for_research": False,
        "confidence_interval": None, "power_assessment": "not_performed",
        "empirical_interpretation_permitted": False,
    }
    if missing:
        result["status"] = "blocked_missing_paired_nav"
        return result
    excess = []
    for previous, current in zip(rows, rows[1:]):
        excess.append(sub(divide(sub(current[1], previous[1]), previous[1]),
                          divide(sub(current[2], previous[2]), previous[2])))
    result["annualized_arithmetic_excess"] = decimal_text(mul(divide(total(excess), Decimal(len(excess))), Decimal(252)))
    for column, name in ((1, "strategy"), (2, "comparator")):
        peak = rows[0][column]
        drawdown = Decimal(0)
        for row in rows:
            peak = max(peak, row[column])
            drawdown = max(drawdown, divide(sub(peak, row[column]), peak))
        result[name + "_max_drawdown"] = decimal_text(drawdown)
    result["status"] = "fixture_diagnostics_only"
    return result


def source_manifest_sha256() -> str:
    return hash_payload(source_manifest())
