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

TWR - MWR is the timing contribution. Positive MWR-minus-TWR means your
contribution timing helped; negative means it hurt. For the case above:
TWR = -5.00%, MWR = 0.00%, timing = +5.00 points.

NOT a performance guarantee or a skill measurement. A single favourable timing
episode is one observation, and buying a dip that keeps falling produces the
opposite number. This module reports the decomposition; it does not claim the
timing was skill rather than luck. See the project's research discipline for
why that distinction matters (memory: project_rigor_toolkit).

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
            raise PerformanceError(f"value_before_flow cannot be negative, got {self.value_before_flow}")
        if self.at.tzinfo is None:
            raise PerformanceError(f"Observation.at must be timezone-aware, got {self.at!r}")

    @property
    def value_after_flow(self) -> float:
        return self.value_before_flow + self.flow


def _period_days(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86400.0


def _annualize(total_return_pct: float, days: float) -> float | None:
    """Compound a period return to a yearly rate. None when undefined."""
    if days <= 0:
        return None
    growth = 1.0 + total_return_pct / 100.0
    if growth <= 0:
        return None  # a total loss has no finite annualized rate
    return (growth ** (DAYS_PER_YEAR / days) - 1.0) * 100.0


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


def _npv(rate: float, flows: list[tuple[float, float]]) -> float:
    """flows as (years_from_start, amount), standard signs (investment negative)."""
    total = 0.0
    for years, amount in flows:
        total += amount / ((1.0 + rate) ** years)
    return total


def money_weighted_return(
    flows: list[tuple[datetime, float]], *, max_iterations: int = 200
) -> dict:
    """
    Internal rate of return on actual cash flows -- YOUR outcome, timing
    included.

    `flows` uses the standard finance convention: investments NEGATIVE, proceeds
    and the terminal value POSITIVE. Solved by bisection on the annualized rate,
    which needs no dependency and cannot diverge the way Newton can on the
    flat-NPV shapes that ordinary buy-and-hold produces.

    Returns `irr_annualized_pct=None` with a `note` when no rate solves it,
    rather than a fabricated number: NPV has no sign change when every flow
    points the same way (all buys, nothing sold and no terminal value), and an
    IRR genuinely does not exist there. Failing closed beats reporting a plausible
    fiction -- the same principle the execution gate uses.
    """
    if len(flows) < 2:
        raise PerformanceError("money_weighted_return needs at least two cash flows")
    for at, amount in flows:
        if not math.isfinite(amount):
            raise PerformanceError(f"cash flow amount must be finite, got {amount!r}")
        if at.tzinfo is None:
            raise PerformanceError(f"cash flow timestamps must be timezone-aware, got {at!r}")

    ordered = sorted(flows, key=lambda f: f[0])
    start = ordered[0][0]
    days = _period_days(start, ordered[-1][0])
    in_years = [(_period_days(start, at) / DAYS_PER_YEAR, amount) for at, amount in ordered]

    invested = -sum(a for _, a in ordered if a < 0)
    returned = sum(a for _, a in ordered if a > 0)
    simple_pct = ((returned / invested) - 1.0) * 100.0 if invested else None

    result = {
        "period_days": round(days, 2),
        "annualized_is_meaningful": days >= MIN_DAYS_FOR_MEANINGFUL_ANNUALIZATION,
        "total_invested": round(invested, 2),
        "total_returned": round(returned, 2),
        # Not time-weighted and not annualized: simply (out / in) - 1. For a
        # position this is the number that answers "did I make money".
        "simple_return_pct": round(simple_pct, 4) if simple_pct is not None else None,
        "method": "money_weighted_irr",
    }

    low, high = -0.999999, 10.0
    npv_low, npv_high = _npv(low, in_years), _npv(high, in_years)
    if npv_low * npv_high > 0:
        result["irr_annualized_pct"] = None
        result["note"] = (
            "no sign change in NPV over the searched range, so no IRR exists "
            "(typical when every flow has the same sign -- e.g. only purchases, "
            "with no sale or terminal value supplied)"
        )
        return result

    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        npv_mid = _npv(mid, in_years)
        if abs(npv_mid) < 1e-10:
            break
        if npv_mid * npv_low > 0:
            low, npv_low = mid, npv_mid
        else:
            high = mid
    irr = (low + high) / 2.0
    result["irr_annualized_pct"] = round(irr * 100.0, 4)
    return result


def position_performance(
    fills: list, prices: list[tuple[datetime, float]]
) -> dict:
    """
    Decompose one position's result into the asset's return and yours.

    `fills` are `assistant.tax_lots.Fill`s; `prices` is `[(at, price), ...]`
    covering at least the first and last fill dates. The final price is the
    valuation point for still-open shares.

    Returns both measures plus `timing_contribution_pct` = MWR - TWR, which is
    the part attributable to WHEN you put money in rather than to what the asset
    did. For the 2-at-100 / 2-at-90 / price-95 case: asset -5.00%, yours 0.00%,
    timing +5.00 points.
    """
    if not fills:
        raise PerformanceError("position_performance needs at least one fill")
    if len(prices) < 2:
        raise PerformanceError("position_performance needs at least two price points")

    ordered_fills = sorted(fills, key=lambda f: f.at)
    ordered_prices = sorted(prices, key=lambda p: p[0])
    for at, price in ordered_prices:
        if not math.isfinite(price) or price <= 0:
            raise PerformanceError(f"price at {at} must be positive and finite, got {price!r}")

    tickers = {f.ticker.upper() for f in ordered_fills}
    if len(tickers) != 1:
        raise PerformanceError(f"position_performance is per-ticker, got {sorted(tickers)}")

    # Build observations at every date that is either a fill or the final price.
    flow_by_time: dict[datetime, float] = {}
    shares_delta: dict[datetime, float] = {}
    for fill in ordered_fills:
        signed_qty = fill.qty if fill.side == "buy" else -fill.qty
        cash = fill.qty * fill.price * (1 if fill.side == "buy" else -1)
        flow_by_time[fill.at] = flow_by_time.get(fill.at, 0.0) + cash
        shares_delta[fill.at] = shares_delta.get(fill.at, 0.0) + signed_qty

    price_at = dict(ordered_prices)
    final_at, final_price = ordered_prices[-1]
    timeline = sorted(set(flow_by_time) | {final_at})

    def _price_on(when: datetime) -> float:
        if when in price_at:
            return price_at[when]
        earlier = [p for t, p in ordered_prices if t <= when]
        if earlier:
            return earlier[-1]
        return ordered_prices[0][1]

    observations: list[Observation] = []
    shares = 0.0
    for when in timeline:
        value_before = shares * _price_on(when)
        flow = flow_by_time.get(when, 0.0)
        observations.append(Observation(at=when, value_before_flow=value_before, flow=flow))
        shares += shares_delta.get(when, 0.0)

    twr = time_weighted_return(observations)

    # MWR: purchases are investments (negative), sales proceeds positive, and
    # the still-open shares are a positive terminal value.
    terminal_value = shares * final_price
    cash_flows = [(when, -flow_by_time[when]) for when in sorted(flow_by_time)]
    if terminal_value > 0:
        last = cash_flows[-1]
        if last[0] == final_at:
            cash_flows[-1] = (final_at, last[1] + terminal_value)
        else:
            cash_flows.append((final_at, terminal_value))
    mwr = money_weighted_return(cash_flows)

    asset_pct = twr["total_return_pct"]
    yours_pct = mwr["simple_return_pct"]
    return {
        "ticker": sorted(tickers)[0],
        "shares_open": round(shares, 6),
        "final_price": final_price,
        "asset_return": twr,
        "your_return": mwr,
        "timing_contribution_pct": (
            round(yours_pct - asset_pct, 4) if yours_pct is not None else None
        ),
        "interpretation": _describe_timing(yours_pct, asset_pct),
    }


def _describe_timing(yours_pct: float | None, asset_pct: float) -> str:
    if yours_pct is None:
        return "Your return is undefined (nothing realized and nothing held)."
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
