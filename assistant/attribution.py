"""GR-7c: where portfolio return came from, against a single benchmark.

Reporting only. Nothing here creates, sizes, ranks, or approves a trade.

**Why one bucket.** Classic Brinson attribution splits active return into
allocation (were you in the right categories?) and selection (did you pick
well inside them?). Both are comparisons against a benchmark with STATED
WEIGHTS. `docs/MANDATE.md` states a volatility band, not target weights, so
there is nothing to be over- or under-weight against at a sector level and
sector allocation is undefined rather than merely hard.

What IS well defined is the single decision this portfolio actually makes:
how much to be invested at all. Against a fully-invested benchmark, the one
bucket is invested-vs-cash, and "allocation" becomes cash drag — which for
an account holding 80%+ cash is the dominant term by a wide margin.

The benchmark is SPY to match what `paper-evidence` already binds into
every observation (`benchmark_ticker`). Using a different index here would
put two benchmarks in one epoch and leave a later reader unable to say
which was authoritative.

**The identity.** With cash earning ~0 over the period:

    R_p  =  w * R_i + (1 - w) * 0          (portfolio = invested share x its return)
    A    =  (w - 1) * R_b                  (allocation: being underinvested vs a full benchmark)
    S    =  (R_p - R_b) - A                (selection: the rest of active return)
    A + S = R_p - R_b                      (exact, by construction)

**Selection is a residual, and this module says so rather than implying a
skill measurement.** It absorbs everything active return contains that cash
drag does not explain: genuine stock picking, but equally the leverage in a
2x product, sector concentration, and the cash-earns-zero approximation. A
positive number here is not proof of skill.

**Cost and tax are NOT components of active return** and are deliberately
not added into the identity. They are already deducted inside `R_p` — a
realized cost has already lowered the equity curve. Adding them again would
double-count. They are reported alongside, as visibility into what is
already inside the number, and the payload labels them that way.
"""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Sequence

from assistant.money import decimal_text, to_decimal
from assistant.performance import Observation, PerformanceError, time_weighted_return

# Below this many valuation points, a decomposition is arithmetic performed
# on noise. The report still computes -- refusing would hide the shape of
# the answer -- but it declares itself insufficient, per CLAUDE.md section 6's
# requirement that a monitoring conclusion carry its independent sample
# count, the required count, and an explicit sufficiency verdict.
DEFAULT_MINIMUM_OBSERVATIONS = 20

# Reconciliation slack. The identity is exact in real arithmetic; this
# absorbs float chaining only, and is asserted rather than assumed.
RECONCILIATION_TOLERANCE_PCT = Decimal("0.0001")


class AttributionError(ValueError):
    """The inputs cannot support an honest attribution."""


@dataclasses.dataclass(frozen=True)
class AttributionPoint:
    """One valuation point: the portfolio, its invested share, the benchmark.

    ``flow`` follows ``performance.Observation`` exactly -- money added
    (positive) or removed (negative) AT this timestamp, applied after
    ``total_equity`` is read. Keeping the same convention is what lets the
    portfolio return reuse the flow-aware chain-linking in
    ``time_weighted_return`` instead of re-deriving it and getting a deposit
    confused with a gain.
    """

    at: datetime
    total_equity: float
    invested_value: float
    benchmark_close: float
    flow: float = 0.0
    # The market session this valuation belongs to. Supplied by the caller
    # because it is recorded alongside the snapshot and must NOT be derived
    # from `at`: `at` is UTC, sessions are Eastern, and taking the UTC date
    # mis-buckets every capture after 8pm Eastern into the next session --
    # the exact defect already found and fixed in
    # storage.get_execution_budget_usage(). None means "unknown", which the
    # sufficiency count treats as its own bucket rather than guessing.
    session_date: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.at, datetime):
            raise AttributionError(f"at must be a datetime, got {self.at!r}")
        if self.at.tzinfo is None:
            raise AttributionError(f"at must be timezone-aware, got {self.at!r}")
        for field in ("total_equity", "invested_value", "benchmark_close", "flow"):
            value = getattr(self, field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise AttributionError(f"{field} must be a number, got {value!r}")
            if not math.isfinite(value):
                raise AttributionError(f"{field} must be finite, got {value!r}")
        if self.total_equity <= 0:
            raise AttributionError(
                f"total_equity must be positive, got {self.total_equity!r}"
            )
        if self.benchmark_close <= 0:
            raise AttributionError(
                f"benchmark_close must be positive, got {self.benchmark_close!r}"
            )
        if self.invested_value < 0:
            raise AttributionError(
                f"invested_value cannot be negative, got {self.invested_value!r}"
            )


def _q(value: Decimal) -> Decimal:
    """Round a reported percentage to 4dp.

    Only for PRESENTATION -- every comparison and the reconciliation check
    above run on the unrounded values, so rounding can never move a result
    across the tolerance.
    """
    return value.quantize(Decimal("0.0001"))


def _twr_pct(observations: list[Observation]) -> Decimal:
    return to_decimal(
        time_weighted_return(observations)["total_return_pct"],
        name="time_weighted_return.total_return_pct",
    )


def evaluate_attribution(
    points: Sequence[AttributionPoint],
    *,
    benchmark_ticker: str = "SPY",
    realized_cost: float | None = None,
    realized_tax: float | None = None,
    minimum_observations: int = DEFAULT_MINIMUM_OBSERVATIONS,
) -> dict[str, Any]:
    """Decompose active return into cash drag and a labelled residual.

    ``realized_cost`` / ``realized_tax`` are amounts ALREADY reflected in the
    equity curve. Passing them adds visibility, never a second deduction;
    omitting them is reported as unavailable rather than assumed zero, since
    a zero would read as "this cost you nothing".
    """
    ordered = sorted(points, key=lambda point: point.at)
    if len(ordered) < 2:
        raise AttributionError(
            "attribution needs at least two valuation points; got "
            f"{len(ordered)}"
        )
    if len({point.at for point in ordered}) != len(ordered):
        raise AttributionError("valuation points must have distinct timestamps")

    try:
        portfolio_pct = _twr_pct(
            [
                Observation(
                    at=point.at, value_before_flow=point.total_equity, flow=point.flow
                )
                for point in ordered
            ]
        )
        # A price series has no external flows; passing any would silently
        # treat an index move as a deposit.
        benchmark_pct = _twr_pct(
            [
                Observation(at=point.at, value_before_flow=point.benchmark_close)
                for point in ordered
            ]
        )
    except PerformanceError as exc:
        raise AttributionError(f"return series is not usable: {exc}") from exc

    # BEGINNING-of-period weights only: each point's weight is the allocation
    # in force during the period that FOLLOWS it, so the final point is
    # excluded. Including it would fold the period's own return back into the
    # weight -- a portfolio that rose because it was invested would show a
    # higher weight *because* it rose, and cash drag would be measured partly
    # against its own consequence. With 50% invested into a +10% benchmark,
    # the honest answer is exactly -5, which averaging the endpoint in
    # quietly turns into -4.81.
    weights = [
        to_decimal(point.invested_value, name="invested_value")
        / to_decimal(point.total_equity, name="total_equity")
        for point in ordered[:-1]
    ]
    average_invested_weight = sum(weights, Decimal("0")) / Decimal(len(weights))

    active_pct = portfolio_pct - benchmark_pct
    allocation_pct = (average_invested_weight - Decimal("1")) * benchmark_pct
    selection_pct = active_pct - allocation_pct

    # Asserted, not assumed: the identity is what makes the two components
    # meaningful, so a future edit that breaks it must fail loudly here
    # rather than publish two numbers that no longer add up.
    residual = abs((allocation_pct + selection_pct) - active_pct)
    if residual > RECONCILIATION_TOLERANCE_PCT:
        raise AttributionError(
            "attribution components do not reconcile with active return: "
            f"allocation {decimal_text(allocation_pct)} + selection "
            f"{decimal_text(selection_pct)} != active {decimal_text(active_pct)} "
            f"(residual {decimal_text(residual)})"
        )

    # The independent unit is the SESSION, not the valuation point. The
    # operator database captures equity many times a day, so a 3-day window
    # can hold 125 snapshots; treating those as 125 independent observations
    # would report a comfortable sample built almost entirely from intraday
    # re-reads of the same account. CLAUDE.md section 6: count independent
    # dates, not correlated rows.
    valuation_points = len(ordered)
    sessions = {
        point.session_date
        if point.session_date is not None
        else f"unknown-at-{point.at.isoformat()}"
        for point in ordered
    }
    independent_count = len(sessions)
    insufficiency: list[str] = []
    if independent_count < minimum_observations:
        insufficiency.append(
            f"only {independent_count} independent session(s) across "
            f"{valuation_points} valuation point(s); {minimum_observations} "
            "sessions required for the decomposition to be more than "
            "arithmetic on noise"
        )
    span_days = (ordered[-1].at - ordered[0].at).total_seconds() / 86400.0
    if span_days < 1:
        insufficiency.append(
            f"observation span is {span_days:.2f} days; a sub-daily window "
            "cannot separate drift from noise"
        )

    def _amount(value: float | None, name: str) -> dict[str, Any]:
        if value is None:
            return {
                "available": False,
                "amount": None,
                "unavailable_reason": f"{name} was not supplied",
            }
        # Same class as GR7BREV-003: callers catch AttributionError, not the
        # raw ValueError to_decimal raises on NaN/Inf.
        try:
            amount = to_decimal(value, name=name)
        except ValueError as exc:
            raise AttributionError(str(exc)) from exc
        return {
            "available": True,
            "amount": decimal_text(amount),
            "unavailable_reason": None,
        }

    average_weight_pct = (average_invested_weight * Decimal("100")).quantize(
        Decimal("0.01")
    )
    if average_invested_weight <= Decimal("1"):
        allocation_meaning = (
            "Cash drag: the return given up by holding cash against a "
            "fully-invested benchmark. Equal to (w-1)*R_benchmark; negative "
            "when underinvested and the benchmark rose."
        )
    else:
        allocation_meaning = (
            "Invested-weight effect vs a fully-invested benchmark: "
            "(w-1)*R_benchmark. Average invested weight exceeded 100% of "
            "equity (e.g. negative cash / leverage), so this is not cash drag."
        )

    return {
        "period": {
            "start": ordered[0].at.isoformat(),
            "end": ordered[-1].at.isoformat(),
            "span_days": round(span_days, 4),
        },
        "benchmark_ticker": benchmark_ticker,
        "returns": {
            "portfolio_pct": decimal_text(_q(portfolio_pct)),
            "benchmark_pct": decimal_text(_q(benchmark_pct)),
            "active_pct": decimal_text(_q(active_pct)),
        },
        "decomposition": {
            "average_invested_weight_pct": decimal_text(average_weight_pct),
            "allocation_pct": decimal_text(_q(allocation_pct)),
            "selection_pct": decimal_text(_q(selection_pct)),
            "reconciles": True,
            "reconciliation_tolerance_pct": decimal_text(
                RECONCILIATION_TOLERANCE_PCT
            ),
            "allocation_meaning": allocation_meaning,
            "selection_meaning": (
                "RESIDUAL, not a skill measurement. Everything active return "
                "contains that the invested-weight effect does not explain -- "
                "stock picking, but equally leverage, concentration, and the "
                "cash-earns-zero approximation."
            ),
        },
        "realized_drags": {
            "already_inside_portfolio_return": True,
            "note": (
                "Costs and taxes are already deducted from the equity curve "
                "and are therefore NOT components of the identity above; "
                "adding them would double-count."
            ),
            "cost": _amount(realized_cost, "realized_cost"),
            "tax": _amount(realized_tax, "realized_tax"),
        },
        "sample_sufficiency": {
            "independent_observation_unit": "market session",
            "independent_count": independent_count,
            "valuation_point_count": valuation_points,
            "required_count": minimum_observations,
            "sufficient": not insufficiency,
            "insufficiency_reasons": tuple(insufficiency),
        },
        "disclaimers": (
            "Reporting only. This report does not create, size, rank, or "
            "approve any order.",
            "A single benchmark bucket measures invested-vs-cash; it cannot "
            "attribute sector allocation, which the mandate does not define.",
        ),
    }
