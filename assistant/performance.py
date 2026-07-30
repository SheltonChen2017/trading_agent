"""
Return attribution: what the asset did, versus what YOU did.

WHY THIS EXISTS
---------------
`tax_lots` answers "how many dollars am I up". It cannot answer "were my
decisions any good", because dollar P&L conflates two different things.

The motivating case: buy 2 shares at 100, buy 2 more at 90, price recovers to
95. Dollar P&L is exactly $0 -- and the tax-lot ledger says so correctly. But
the ASSET fell 5% over that window (100 -> 95). You came out flat instead of
down because you added money at the low. That 5-point difference is the entire
measurable value of the decision, and nothing in the app could see it.

Two standard measures separate them:

  * Time-weighted return (TWR) chains sub-period returns and is INSENSITIVE to
    how much money you had in at each point. It measures the ASSET (or the
    strategy's allocation decisions), which is why it is the fund-reporting
    standard -- a manager should not be judged on when clients deposited.
  * Money-weighted return (MWR / IRR) is the rate that makes your actual cash
    flows net to zero. It measures YOUR OUTCOME, including timing.

MWR minus TWR is the timing contribution. Positive means your contribution
timing helped; negative means it hurt. For the case above:
TWR = -5.00%, MWR = 0.00%, timing = +5.00 points.

NOT a performance guarantee or a skill measurement. A single favourable timing
episode is one observation. This module reports the decomposition; it does not
claim the timing was skill rather than luck. See the project's research
discipline for why that distinction matters (memory: project_rigor_toolkit).

CONVENTIONS
-----------
Flows are stated from the POSITION's point of view: a purchase is money flowing
IN (positive `flow`), a sale is money flowing OUT (negative). The IRR helper
uses the opposite, standard finance sign convention internally (investments
negative); `position_performance` handles the translation so callers never mix
them.

Annualized figures over very short windows are arithmetically correct and
practically meaningless -- 1% over two days annualizes past 500%. Every result
therefore carries `period_days` and an explicit `annualized_is_meaningful`
flag rather than leaving the caller to notice.
"""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime

DAYS_PER_YEAR = 365.25
# Below this many days, an annualized figure is reported but flagged as not
# meaningful. Chosen as a quarter -- short enough to be permissive, long enough
# that compounding a few days into a year is never presented as a real rate.
MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION = 90


class PerformanceError(ValueError):
    """Malformed observations or cash flows."""


@dataclasses.dataclass(frozen=True)
class Observation:
    """
    A valuation point.

    `value_before_flow` is the position/portfolio value at `at` BEFORE the
    flow at that timestamp is applied; `flow` is money added (positive) or
    removed (negative) at that timestamp. Splitting them is what lets TWR
    break the period at each flow instead of mistaking a deposit for a gain --
    the single most common way a hand-rolled return calculation goes wrong.
    """

    at: datetime
    value_before_flow: float
    flow: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.at, datetime):
            raise PerformanceError(f"Observation.at must be a datetime, got {self.at!r}")
        for field, value in (("value_before_flow", self.value_before_flow), ("flow", self.flow)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise PerformanceError(f"{field} must be a number, got {value!r}")
            if not math.isfinite(value):
                raise PerformanceError(
                    f"{field} must be finite, got {value!r} -- a non-finite value would "
                    "propagate through every chained return and silently defeat the "
                    "comparisons below"
                )
        if self.value_before_flow < 0:
            raise PerformanceError(
                f"value_before_flow cannot be negative, got {self.value_before_flow}"
            )
        if self.value_after_flow < 0:
            raise PerformanceError(
                "value_after_flow cannot be negative; the flow removes more than "
                f"the observed value ({self.value_before_flow} + {self.flow})"
            )
        if self.at.tzinfo is None:
            raise PerformanceError(f"Observation.at must be timezone-aware, got {self.at!r}")

    @property
    def value_after_flow(self) -> float:
        return self.value_before_flow + self.flow


@dataclasses.dataclass(frozen=True)
class Distribution:
    """One per-share cash distribution for live total-return attribution.

    ``ex_at`` drives the asset total-return calculation. ``paid_at`` drives
    the investor cash flow and defaults to ``ex_at`` when a separate payment
    timestamp is unavailable. ``cash_amount`` may carry the broker-confirmed
    account amount; otherwise it is derived from shares held at ``ex_at``.
    """

    ticker: str
    ex_at: datetime
    amount_per_share: float
    paid_at: datetime | None = None
    cash_amount: float | None = None
    tax_classification: str = "unknown"

    def __post_init__(self) -> None:
        if self.ex_at.tzinfo is None or (
            self.paid_at is not None and self.paid_at.tzinfo is None
        ):
            raise PerformanceError("distribution timestamps must be timezone-aware")
        for field, value in (
            ("amount_per_share", self.amount_per_share),
            ("cash_amount", self.cash_amount),
        ):
            if value is None:
                continue
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise PerformanceError(
                    f"distribution {field} must be positive and finite, got {value!r}"
                )
        classification = self.tax_classification.lower()
        if classification not in ("qualified", "ordinary", "unknown"):
            raise PerformanceError(
                "distribution tax_classification must be qualified, ordinary, or unknown"
            )


def _period_days(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86400.0


def _annualize(total_return_pct: float, days: float) -> float | None:
    """Compound a period return to a yearly rate. None when undefined."""
    if days <= 0:
        return None
    growth = 1.0 + total_return_pct / 100.0
    if growth <= 0:
        return None  # a total loss has no finite annualized rate
    try:
        return math.expm1(math.log(growth) * DAYS_PER_YEAR / days) * 100.0
    except OverflowError:
        return None


def time_weighted_return(observations: list[Observation]) -> dict:
    """
    Chain-linked return, neutral to the size and timing of flows.

    Each sub-period return is `value_before_flow[i] / value_after_flow[i-1] - 1`,
    so a deposit is never counted as a gain. A sub-period whose starting value
    is zero (the position was fully closed, then re-opened) is SKIPPED rather
    than treated as an infinite return -- and the skip is reported, because
    silently dropping periods would overstate a chained result.
    """
    if len(observations) < 2:
        raise PerformanceError("time_weighted_return needs at least two observations")
    ordered = sorted(observations, key=lambda o: o.at)

    growth = 1.0
    sub_returns: list[float] = []
    skipped = 0
    for previous, current in zip(ordered, ordered[1:]):
        start = previous.value_after_flow
        if start <= 0:
            skipped += 1
            continue
        sub = current.value_before_flow / start
        sub_returns.append((sub - 1.0) * 100.0)
        growth *= sub

    if not sub_returns:
        raise PerformanceError(
            "no measurable sub-period: every interval started from a zero value"
        )

    total_pct = (growth - 1.0) * 100.0
    days = _period_days(ordered[0].at, ordered[-1].at)
    return {
        "total_return_pct": round(total_pct, 4),
        "annualized_return_pct": (
            round(a, 4) if (a := _annualize(total_pct, days)) is not None else None
        ),
        "period_days": round(days, 2),
        "annualized_is_meaningful": days >= MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION,
        "sub_period_returns_pct": [round(r, 4) for r in sub_returns],
        "sub_periods_skipped_zero_value": skipped,
        "method": "time_weighted",
    }


def _scaled_npv(log_annual_growth: float, flows: list[tuple[float, float]]) -> float:
    """
    Sign-preserving NPV evaluated in log-rate space.

    Searching on ``log(1 + rate)`` covers the complete valid IRR domain
    ``rate > -1`` without a hard upper-rate ceiling. Scaling both the cash
    amounts and exponential terms prevents overflow while preserving the sign
    needed by bisection.
    """
    amount_scale = max(abs(amount) for _, amount in flows)
    exponents = [-years * log_annual_growth for years, _ in flows]
    exponent_scale = max(exponents)
    return math.fsum(
        (amount / amount_scale) * math.exp(exponent - exponent_scale)
        for exponent, (_, amount) in zip(exponents, flows)
    )


def _have_opposite_signs(left: float, right: float) -> bool:
    return (left < 0 < right) or (right < 0 < left)


def _period_return_from_log_rate(log_annual_growth: float, days: float) -> float | None:
    if days <= 0:
        return None
    try:
        return math.expm1(log_annual_growth * days / DAYS_PER_YEAR) * 100.0
    except OverflowError:
        return None


def money_weighted_return(
    flows: list[tuple[datetime, float]], *, max_iterations: int = 200
) -> dict:
    """
    Internal rate of return on actual cash flows -- YOUR outcome, timing
    included.

    `flows` uses the standard finance convention: investments NEGATIVE, proceeds
    and the terminal value POSITIVE. Conventional cash-flow series (at most one
    sign change) are solved by bisection in log-rate space, which has no fixed
    upper-rate ceiling and cannot diverge the way Newton can.

    Returns `irr_annualized_pct=None` with a `note` when no unique rate can be
    reported. IRR genuinely does not exist when all flows have the same sign,
    is undefined over a zero-duration schedule, and may be non-unique when cash
    flow signs alternate more than once. Failing closed beats reporting a
    plausible fiction -- the same principle the execution gate uses.
    """
    if len(flows) < 2:
        raise PerformanceError("money_weighted_return needs at least two cash flows")
    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or max_iterations <= 0
    ):
        raise PerformanceError("max_iterations must be a positive integer")
    for at, amount in flows:
        if not isinstance(at, datetime):
            raise PerformanceError(f"cash flow timestamp must be a datetime, got {at!r}")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise PerformanceError(f"cash flow amount must be a number, got {amount!r}")
        if not math.isfinite(amount):
            raise PerformanceError(f"cash flow amount must be finite, got {amount!r}")
        if at.tzinfo is None:
            raise PerformanceError(f"cash flow timestamps must be timezone-aware, got {at!r}")

    invested = -sum(amount for _, amount in flows if amount < 0)
    returned = sum(amount for _, amount in flows if amount > 0)
    simple_pct = ((returned / invested) - 1.0) * 100.0 if invested else None

    # Same-timestamp flows have the same discount factor, so aggregate them.
    # Keeping zero-net timestamps preserves the requested measurement window.
    by_time: dict[datetime, float] = {}
    for at, amount in flows:
        by_time[at] = by_time.get(at, 0.0) + amount
    ordered = sorted(by_time.items())
    start = ordered[0][0]
    days = _period_days(start, ordered[-1][0])
    in_years = [(_period_days(start, at) / DAYS_PER_YEAR, amount) for at, amount in ordered]

    result = {
        "period_days": round(days, 2),
        "annualized_is_meaningful": days >= MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION,
        "total_invested": round(invested, 2),
        "total_returned": round(returned, 2),
        # Not MWR and not annualized: simply (out / in) - 1. Retained as a
        # separate cash-on-cash diagnostic, never used for timing attribution.
        "simple_return_pct": round(simple_pct, 4) if simple_pct is not None else None,
        "period_return_pct": None,
        "method": "money_weighted_irr",
    }

    if days <= 0:
        result["irr_annualized_pct"] = None
        result["note"] = (
            "cash flows do not span a positive amount of time, so an annualized "
            "IRR is undefined"
        )
        return result

    signs = [1 if amount > 0 else -1 for _, amount in ordered if amount != 0]
    if not signs or 1 not in signs or -1 not in signs:
        result["irr_annualized_pct"] = None
        result["note"] = (
            "cash flows need at least one investment and one return; with only "
            "one sign, no IRR exists"
        )
        return result
    sign_changes = sum(left != right for left, right in zip(signs, signs[1:]))
    if sign_changes > 1:
        result["irr_annualized_pct"] = None
        result["note"] = (
            "cash-flow signs change more than once, so IRR may be non-unique; "
            "refusing to select one root arbitrarily"
        )
        return result

    # Expand symmetrically in log-rate space until the unique conventional root
    # is bracketed. This admits rates far above 1000% over short windows.
    low, high = -1.0, 1.0
    npv_low = _scaled_npv(low, in_years)
    npv_high = _scaled_npv(high, in_years)
    for _ in range(64):
        if npv_low == 0.0 or npv_high == 0.0 or _have_opposite_signs(npv_low, npv_high):
            break
        low *= 2.0
        high *= 2.0
        npv_low = _scaled_npv(low, in_years)
        npv_high = _scaled_npv(high, in_years)
    else:
        result["irr_annualized_pct"] = None
        result["note"] = "unable to bracket a finite IRR for this cash-flow schedule"
        return result

    if npv_low == 0.0:
        root = low
    elif npv_high == 0.0:
        root = high
    else:
        for _ in range(max_iterations):
            mid = (low + high) / 2.0
            npv_mid = _scaled_npv(mid, in_years)
            if abs(npv_mid) < 1e-13 or abs(high - low) < 1e-13:
                low = high = mid
                break
            if not _have_opposite_signs(npv_mid, npv_low):
                low, npv_low = mid, npv_mid
            else:
                high = mid
        root = (low + high) / 2.0

    period_return = _period_return_from_log_rate(root, days)
    if period_return is not None and math.isfinite(period_return):
        result["period_return_pct"] = round(period_return, 4)
    else:
        result["note"] = "the period-equivalent IRR exceeds the finite numeric range"

    try:
        irr = math.expm1(root)
    except OverflowError:
        result["irr_annualized_pct"] = None
        result["note"] = "the annualized IRR exceeds the finite numeric range"
        return result
    if not math.isfinite(irr):
        result["irr_annualized_pct"] = None
        result["note"] = "the annualized IRR exceeds the finite numeric range"
        return result

    result["irr_annualized_pct"] = round(irr * 100.0, 4)
    return result


def position_performance(
    fills: list,
    prices: list[tuple[datetime, float]],
    *,
    distributions: list[Distribution] | None = None,
    prices_include_distributions: bool = False,
) -> dict:
    """
    Decompose one position's result into the asset's return and yours.

    `fills` are `assistant.tax_lots.Fill`s; `prices` is `[(at, price), ...]`.
    Prices must begin on or before the first fill and end on or after the last
    fill. The final price is the valuation point for still-open shares.

    `asset_return` is a continuously invested benchmark, including supplied
    cash distributions unless ``prices_include_distributions`` says the input
    series is already adjusted for them. It includes
    intervals when the position itself was closed. `your_return` is the
    cash-flow-sensitive MWR. `timing_contribution_pct` compares its
    period-equivalent return with TWR, so both sides cover the same horizon.
    """
    if not fills:
        raise PerformanceError("position_performance needs at least one fill")
    if len(prices) < 2:
        raise PerformanceError("position_performance needs at least two price points")

    ordered_fills = sorted(fills, key=lambda f: f.at)
    unique_prices: dict[datetime, float] = {}
    for at, price in prices:
        if not isinstance(at, datetime):
            raise PerformanceError(f"price timestamp must be a datetime, got {at!r}")
        if at.tzinfo is None:
            raise PerformanceError(f"price timestamps must be timezone-aware, got {at!r}")
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise PerformanceError(f"price at {at} must be positive and finite, got {price!r}")
        if at in unique_prices and unique_prices[at] != price:
            raise PerformanceError(
                f"conflicting prices at {at}: {unique_prices[at]} and {price}"
            )
        unique_prices[at] = price
    ordered_prices = sorted(unique_prices.items())
    if len(ordered_prices) < 2:
        raise PerformanceError(
            "position_performance needs at least two distinct price timestamps"
        )

    tickers = {f.ticker.upper() for f in ordered_fills}
    if len(tickers) != 1:
        raise PerformanceError(f"position_performance is per-ticker, got {sorted(tickers)}")

    first_fill_at = ordered_fills[0].at
    last_fill_at = ordered_fills[-1].at
    final_at, final_price = ordered_prices[-1]
    if ordered_prices[0][0] > first_fill_at:
        raise PerformanceError(
            "prices must include a valuation on or before the first fill "
            f"({first_fill_at})"
        )
    if final_at < last_fill_at:
        raise PerformanceError(
            "the terminal valuation precedes the latest fill: "
            f"{final_at} < {last_fill_at}"
        )
    if final_at <= first_fill_at:
        raise PerformanceError("terminal valuation must be after the first fill")

    start_price = next(price for at, price in reversed(ordered_prices) if at <= first_fill_at)
    benchmark_prices = [(first_fill_at, start_price)]
    benchmark_prices.extend((at, price) for at, price in ordered_prices if at > first_fill_at)
    relevant_distributions = sorted(
        (
            distribution
            for distribution in (distributions or [])
            if distribution.ticker.upper() in tickers
            and first_fill_at < distribution.ex_at <= final_at
        ),
        key=lambda distribution: distribution.ex_at,
    )
    foreign_distributions = [
        distribution.ticker
        for distribution in (distributions or [])
        if distribution.ticker.upper() not in tickers
    ]
    if foreign_distributions:
        raise PerformanceError(
            "position_performance received distributions for another ticker: "
            + ", ".join(sorted(set(foreign_distributions)))
        )

    if relevant_distributions and not prices_include_distributions:
        growth = 1.0
        sub_returns = []
        for (previous_at, previous_price), (current_at, current_price) in zip(
            benchmark_prices, benchmark_prices[1:]
        ):
            paid_per_share = sum(
                distribution.amount_per_share
                for distribution in relevant_distributions
                if previous_at < distribution.ex_at <= current_at
            )
            factor = (current_price + paid_per_share) / previous_price
            growth *= factor
            sub_returns.append((factor - 1.0) * 100.0)
        total_pct = (growth - 1.0) * 100.0
        days = _period_days(benchmark_prices[0][0], benchmark_prices[-1][0])
        twr = {
            "total_return_pct": round(total_pct, 4),
            "annualized_return_pct": (
                round(annualized, 4)
                if (
                    annualized := _annualize(total_pct, days)
                ) is not None
                else None
            ),
            "period_days": round(days, 2),
            "annualized_is_meaningful": (
                days >= MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION
            ),
            "sub_period_returns_pct": [
                round(value, 4) for value in sub_returns
            ],
            "sub_periods_skipped_zero_value": 0,
            "method": "time_weighted_total_return",
        }
    else:
        twr = time_weighted_return(
            [
                Observation(at=at, value_before_flow=price)
                for at, price in benchmark_prices
            ]
        )
        if prices_include_distributions:
            twr["method"] = "time_weighted_adjusted_price_total_return"

    # Build standard-sign cash flows while validating that this long-only
    # position never sells more shares than it owns.
    cash_by_time: dict[datetime, float] = {}
    shares = 0.0
    for fill in ordered_fills:
        if fill.side == "buy":
            shares += fill.qty
            cash = -(fill.qty * fill.price)
        else:
            shares -= fill.qty
            if shares < -1e-9:
                raise PerformanceError(
                    f"sale at {fill.at} exceeds available shares; short positions "
                    "are not supported by position_performance"
                )
            if abs(shares) <= 1e-9:
                shares = 0.0
            cash = fill.qty * fill.price
        cash_by_time[fill.at] = cash_by_time.get(fill.at, 0.0) + cash

    def _shares_held_at(at: datetime) -> float:
        held = 0.0
        for fill in ordered_fills:
            if fill.at > at:
                break
            held += fill.qty if fill.side == "buy" else -fill.qty
        return max(0.0, held)

    gross_distribution_cash = 0.0
    pending_distribution_cash = 0.0
    classifications: dict[str, float] = {}
    for distribution in relevant_distributions:
        cash_amount = (
            distribution.cash_amount
            if distribution.cash_amount is not None
            else _shares_held_at(distribution.ex_at)
            * distribution.amount_per_share
        )
        if cash_amount <= 0:
            continue
        paid_at = distribution.paid_at or distribution.ex_at
        if paid_at > final_at:
            pending_distribution_cash += cash_amount
            continue
        cash_by_time[paid_at] = cash_by_time.get(paid_at, 0.0) + cash_amount
        gross_distribution_cash += cash_amount
        classification = distribution.tax_classification.lower()
        classifications[classification] = (
            classifications.get(classification, 0.0) + cash_amount
        )

    # MWR: purchases are investments (negative), sales proceeds positive, and
    # the still-open shares are a positive terminal value. A zero terminal flow
    # preserves the same comparison horizon for a position closed earlier.
    terminal_value = shares * final_price
    cash_by_time[final_at] = cash_by_time.get(final_at, 0.0) + terminal_value
    cash_flows = sorted(cash_by_time.items())
    mwr = money_weighted_return(cash_flows)

    asset_pct = twr["total_return_pct"]
    yours_pct = mwr["period_return_pct"]
    return {
        "ticker": sorted(tickers)[0],
        "shares_open": round(shares, 6),
        "final_price": final_price,
        "asset_return": twr,
        "your_return": mwr,
        "timing_contribution_pct": (
            round(yours_pct - asset_pct, 4) if yours_pct is not None else None
        ),
        "timing_basis": "money_weighted_period_return_minus_time_weighted_return",
        "interpretation": _describe_timing(yours_pct, asset_pct, mwr.get("note")),
        "distributions": {
            "count": len(relevant_distributions),
            "gross_cash": round(gross_distribution_cash, 2),
            "pending_cash_after_valuation": round(
                pending_distribution_cash, 2
            ),
            "cash_by_tax_classification": {
                key: round(value, 2)
                for key, value in sorted(classifications.items())
            },
            "asset_series_already_adjusted": bool(
                prices_include_distributions
            ),
        },
    }


def _describe_timing(
    yours_pct: float | None, asset_pct: float, unavailable_reason: str | None = None
) -> str:
    if yours_pct is None:
        reason = f" Reason: {unavailable_reason}" if unavailable_reason else ""
        return f"Money-weighted return is unavailable, so timing cannot be attributed.{reason}"
    delta = yours_pct - asset_pct
    if abs(delta) < 0.005:
        return (
            "Your return matches the asset's: contribution timing made no measurable "
            "difference (a single lump-sum purchase looks like this)."
        )
    direction = "helped" if delta > 0 else "hurt"
    return (
        f"The asset returned {asset_pct:+.2f}% while you returned {yours_pct:+.2f}%. "
        f"Contribution timing {direction} by {abs(delta):.2f} percentage points. "
        "One episode is one observation -- this is not evidence of skill."
    )
