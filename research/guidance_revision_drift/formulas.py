"""Proposed GDR-0A range arithmetic, without event or trading authority.

This module checks only four caller-supplied numeric ranges. It does not
establish comparability, fiscal period, units, accounting basis, security
identity, point-in-time availability, a qualifying event, or an order signal.
Equal endpoints are accepted mathematically; source evidence must separately
establish that an equal-ended range really represents point guidance.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from data.financial_primitives import (
    deterministic_decimal_divide,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
)


PROPOSED_REVENUE_RAISE = Decimal("0.02")
PROPOSED_EPS_RAISE = Decimal("0.05")
PROPOSED_PRIOR_EPS_MIDPOINT_FLOOR = Decimal("0.25")
# Resource limits, not investment-universe or economic acceptance criteria.
# Their combination bounds alignment, coefficient growth, and display division.
MAX_COEFFICIENT_DIGITS = 128
MAX_ABSOLUTE_EXPONENT = 128


class GuidanceArithmeticError(ValueError):
    """A supplied numeric range is unsafe or outside the arithmetic contract."""


def _bounded_decimal(value: object, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise GuidanceArithmeticError(f"{name} must be an exact finite Decimal")
    parts = value.as_tuple()
    if (
        len(parts.digits) > MAX_COEFFICIENT_DIGITS
        or abs(int(parts.exponent)) > MAX_ABSOLUTE_EXPONENT
        or (value != 0 and abs(value.adjusted()) > MAX_ABSOLUTE_EXPONENT)
    ):
        raise GuidanceArithmeticError(f"{name} exceeds arithmetic resource bounds")
    return value


@dataclass(frozen=True, slots=True)
class GuidanceRange:
    lower: Decimal
    upper: Decimal

    def __post_init__(self) -> None:
        lower = _bounded_decimal(self.lower, "lower")
        upper = _bounded_decimal(self.upper, "upper")
        if lower > upper:
            raise GuidanceArithmeticError("lower must not exceed upper")


@dataclass(frozen=True, slots=True)
class RangeRevisionEvaluation:
    """Immutable arithmetic observations; passing conveys no other eligibility.

    Revision fractions are deterministic 28-significant-digit display values,
    never the operands used for threshold acceptance. A fraction is unavailable
    when its prior midpoint fails the positive-revenue or EPS-floor condition.
    """

    previous_revenue_midpoint: Decimal
    current_revenue_midpoint: Decimal
    previous_eps_midpoint: Decimal
    current_eps_midpoint: Decimal
    revenue_revision_fraction: Decimal | None
    eps_revision_fraction: Decimal | None
    previous_revenue_positive: bool
    previous_eps_floor_met: bool
    revenue_lower_bound_not_reduced: bool
    eps_lower_bound_not_reduced: bool
    revenue_raise_threshold_met: bool
    eps_raise_threshold_met: bool
    refusal_reasons: tuple[str, ...]

    @property
    def passes_arithmetic(self) -> bool:
        """Only the proposed numeric conditions, never a tradable signal."""
        return all((
            self.previous_revenue_positive,
            self.previous_eps_floor_met,
            self.revenue_lower_bound_not_reduced,
            self.eps_lower_bound_not_reduced,
            self.revenue_raise_threshold_met,
            self.eps_raise_threshold_met,
        ))


def _validated_sum(value: object, name: str) -> Decimal:
    if type(value) is not GuidanceRange:
        raise GuidanceArithmeticError(f"{name} must be an exact GuidanceRange")
    # Revalidate at the boundary even if construction was bypassed or a caller
    # deliberately circumvented a frozen dataclass with object.__setattr__.
    GuidanceRange.__post_init__(value)
    return exact_decimal_add(value.lower, value.upper, name=f"{name} endpoint sum")


def _raise_met(previous_sum: Decimal, current_sum: Decimal, minimum: Decimal) -> bool:
    # The factor of two in both midpoints cancels. Exact cross-multiplication
    # avoids letting a rounded display ratio pass a just-below-threshold input.
    required_sum = exact_decimal_multiply(
        previous_sum, exact_decimal_add(Decimal("1"), minimum),
        name="required endpoint sum",
    )
    return current_sum >= required_sum


def _revision(previous_sum: Decimal, current_sum: Decimal) -> Decimal:
    return deterministic_decimal_divide(
        exact_decimal_subtract(current_sum, previous_sum),
        previous_sum,
        name="display-only midpoint revision fraction",
    )


def evaluate_range_revisions(
    *,
    previous_revenue: GuidanceRange,
    current_revenue: GuidanceRange,
    previous_eps: GuidanceRange,
    current_eps: GuidanceRange,
) -> RangeRevisionEvaluation:
    """Evaluate proposed range arithmetic only; no data, dates, or I/O are read."""
    prior_revenue_sum = _validated_sum(previous_revenue, "previous_revenue")
    revenue_sum = _validated_sum(current_revenue, "current_revenue")
    prior_eps_sum = _validated_sum(previous_eps, "previous_eps")
    eps_sum = _validated_sum(current_eps, "current_eps")

    revenue_positive = prior_revenue_sum > 0
    eps_floor_met = prior_eps_sum >= exact_decimal_multiply(
        PROPOSED_PRIOR_EPS_MIDPOINT_FLOOR, Decimal("2"),
    )
    revenue_low_not_reduced = current_revenue.lower >= previous_revenue.lower
    eps_low_not_reduced = current_eps.lower >= previous_eps.lower
    revenue_raise_met = revenue_positive and _raise_met(
        prior_revenue_sum, revenue_sum, PROPOSED_REVENUE_RAISE,
    )
    eps_raise_met = eps_floor_met and _raise_met(
        prior_eps_sum, eps_sum, PROPOSED_EPS_RAISE,
    )
    checks = (
        (revenue_positive, "previous_revenue_midpoint_not_positive"),
        (eps_floor_met, "previous_eps_midpoint_below_floor"),
        (revenue_low_not_reduced, "revenue_lower_bound_reduced"),
        (eps_low_not_reduced, "eps_lower_bound_reduced"),
        (revenue_raise_met, "revenue_raise_threshold_not_met"),
        (eps_raise_met, "eps_raise_threshold_not_met"),
    )
    half = Decimal("0.5")
    return RangeRevisionEvaluation(
        previous_revenue_midpoint=exact_decimal_multiply(prior_revenue_sum, half),
        current_revenue_midpoint=exact_decimal_multiply(revenue_sum, half),
        previous_eps_midpoint=exact_decimal_multiply(prior_eps_sum, half),
        current_eps_midpoint=exact_decimal_multiply(eps_sum, half),
        revenue_revision_fraction=(
            _revision(prior_revenue_sum, revenue_sum) if revenue_positive else None
        ),
        eps_revision_fraction=(
            _revision(prior_eps_sum, eps_sum) if eps_floor_met else None
        ),
        previous_revenue_positive=revenue_positive,
        previous_eps_floor_met=eps_floor_met,
        revenue_lower_bound_not_reduced=revenue_low_not_reduced,
        eps_lower_bound_not_reduced=eps_low_not_reduced,
        revenue_raise_threshold_met=revenue_raise_met,
        eps_raise_threshold_met=eps_raise_met,
        refusal_reasons=tuple(reason for passed, reason in checks if not passed),
    )
