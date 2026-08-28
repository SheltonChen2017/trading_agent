"""
Portfolio risk copilot — deterministic answers to the questions GPT's
design review specifically called out ("am I overexposed to X", "what
happens if the market falls N%", "do I have hidden duplication between
correlated holdings"). Every number here is computed from real
historical data or the portfolio snapshot directly — nothing is an LLM
estimate (see schemas.py's module docstring for why that rule matters).
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from config import BASKETS, INVERSE_LEVERAGED_ETF_TICKERS, LEVERAGED_ETF_UNDERLYING
from data.market_data import fetch_historical
from assistant.policy import TradingPolicy
from assistant.money import (
    deterministic_decimal_divide,
    deterministic_decimal_quantize,
    exact_decimal_multiply,
    exact_decimal_sum,
    to_decimal,
)
from assistant.schemas import PortfolioSnapshot, RiskExposure


def check_concentration(risk: RiskExposure, basket_name: str | None = None) -> str:
    """
    Answers "am I overexposed to X?" for a specific basket, or a general
    concentration summary if `basket_name` is omitted. Uses the SAME
    concentration_warnings already computed by build_risk_exposure() —
    doesn't recompute the threshold logic separately.

    NOTE: this is DESCRIPTIVE, not a policy-compliance check --
    concentration_warnings uses fixed informational thresholds (see
    context_builder.build_risk_exposure()), not the active TradingPolicy's
    real numeric caps. A position can be well under this function's
    threshold while still breaching the policy (GPT review, 2026-07-28,
    reproduced: a 10% position with a 5% policy cap reported "no
    concentration warnings" here while proposal generation would flag it).
    Use check_policy_compliance() for an actual policy-bound answer.
    """
    if not risk.available:
        return (
            "Concentration analysis unavailable: "
            + (risk.unavailable_reason or "portfolio integrity could not be proved")
        )
    if basket_name is not None:
        pct = risk.basket_exposure_pct.get(basket_name)
        if pct is None:
            return f"No current exposure to '{basket_name}'."
        flagged = any(basket_name in w for w in risk.concentration_warnings)
        verdict = "This is flagged as a concentration risk." if flagged else "Not flagged as a concentration risk."
        return f"'{basket_name}' exposure is {pct}% of total equity. {verdict}"

    if not risk.concentration_warnings:
        return "No concentration warnings — largest single position is " \
               f"{risk.largest_single_position_pct}% of equity, leveraged ETF exposure is " \
               f"{risk.leveraged_etf_exposure_pct}%."
    return "Concentration warnings:\n" + "\n".join(f"  - {w}" for w in risk.concentration_warnings)


def find_correlated_clusters(snapshot: PortfolioSnapshot) -> list[str]:
    """
    Flags "hidden duplication": holding both a leveraged ETF AND its own
    unleveraged underlying index counts as ONE concentrated bet on that
    index, not two diversified positions — a portfolio can obey a
    per-ticker cap while still being dangerously concentrated this way.

    Inverse (bear) leveraged ETFs -- e.g. SPXU vs. SPY -- are excluded:
    they move OPPOSITE their underlying, so holding both is a partial
    HEDGE, not a duplicated same-direction bet (GPT review, 2026-07-28:
    reproduced SPY+SPXU being wrongly described as "one amplified SPY
    bet").
    """
    held = {p.ticker.upper() for p in snapshot.positions}
    value_by_ticker = {p.ticker.upper(): p.market_value for p in snapshot.positions}
    total = snapshot.total_equity
    warnings = []
    if not math.isfinite(total) or total <= 0:
        return [
            "Correlated-holdings check unavailable: total equity must be "
            "positive and finite."
        ]

    for leveraged, underlying in LEVERAGED_ETF_UNDERLYING.items():
        if leveraged in INVERSE_LEVERAGED_ETF_TICKERS:
            continue
        if leveraged in held and underlying in held:
            combined_value = value_by_ticker[leveraged] + value_by_ticker[underlying]
            combined_pct = round(combined_value / total * 100, 1) if total else 0.0
            warnings.append(
                f"Holding both {underlying} and {leveraged} — this is really ONE concentrated bet on the "
                f"{underlying} index (amplified by {leveraged}'s leverage), not two separate positions. "
                f"Combined: {combined_pct}% of total equity."
            )
    return warnings


def estimate_stress_impact(
    snapshot: PortfolioSnapshot,
    benchmark_ticker: str,
    benchmark_move_pct: float,
    lookback_days: int = 252,
) -> dict:
    """
    "What happens if [benchmark] falls N%?" — estimates the $ impact on
    each position using its own historically-measured beta to the
    benchmark (ordinary least squares on trailing daily returns), NOT a
    guess or an assumed leverage multiple. Positions with insufficient
    history report beta=None and are excluded from the total estimate
    (flagged, not silently dropped).
    """
    if not math.isfinite(benchmark_move_pct):
        return {
            "benchmark_ticker": benchmark_ticker,
            "benchmark_move_pct": benchmark_move_pct,
            "position_impacts": [],
            "total_estimated_impact": None,
            "warning": "Benchmark move must be finite.",
        }
    tickers = [p.ticker for p in snapshot.positions]
    data = fetch_historical([benchmark_ticker] + tickers, lookback_days=lookback_days)

    if benchmark_ticker not in data or data[benchmark_ticker].empty:
        return {
            "benchmark_ticker": benchmark_ticker, "benchmark_move_pct": benchmark_move_pct,
            "position_impacts": [], "total_estimated_impact": None,
            "warning": f"No data available for benchmark {benchmark_ticker}.",
        }

    benchmark_returns = (
        pd.to_numeric(
            data[benchmark_ticker]["close"], errors="coerce"
        )
        .pct_change(fill_method=None)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    position_impacts = []
    total_impact = 0.0
    missing_beta_tickers = []
    for p in snapshot.positions:
        if (
            p.ticker not in data
            or data[p.ticker].empty
            or not math.isfinite(p.market_value)
        ):
            position_impacts.append({"ticker": p.ticker, "beta": None, "estimated_impact": None})
            missing_beta_tickers.append(p.ticker)
            continue

        ticker_returns = (
            pd.to_numeric(data[p.ticker]["close"], errors="coerce")
            .pct_change(fill_method=None)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
        aligned = (
            pd.concat(
                [ticker_returns, benchmark_returns],
                axis=1,
                join="inner",
            )
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
        if len(aligned) < 20:
            position_impacts.append({"ticker": p.ticker, "beta": None, "estimated_impact": None})
            missing_beta_tickers.append(p.ticker)
            continue

        aligned.columns = ["ticker", "benchmark"]
        benchmark_variance = float(
            np.var(aligned["benchmark"], ddof=1)
        )
        if not math.isfinite(benchmark_variance) or benchmark_variance <= 0:
            position_impacts.append(
                {
                    "ticker": p.ticker,
                    "beta": None,
                    "estimated_impact": None,
                }
            )
            missing_beta_tickers.append(p.ticker)
            continue
        beta = float(
            np.cov(aligned["ticker"], aligned["benchmark"])[0, 1]
            / benchmark_variance
        )
        if not math.isfinite(beta):
            position_impacts.append(
                {
                    "ticker": p.ticker,
                    "beta": None,
                    "estimated_impact": None,
                }
            )
            missing_beta_tickers.append(p.ticker)
            continue
        estimated_impact = p.market_value * beta * (benchmark_move_pct / 100)
        position_impacts.append({"ticker": p.ticker, "beta": round(beta, 2), "estimated_impact": round(estimated_impact, 2)})
        total_impact += estimated_impact

    result = {
        "benchmark_ticker": benchmark_ticker,
        "benchmark_move_pct": benchmark_move_pct,
        "position_impacts": position_impacts,
        "total_estimated_impact": round(total_impact, 2),
    }
    if missing_beta_tickers:
        result["warning"] = (
            f"Beta unavailable for {', '.join(missing_beta_tickers)} (insufficient history) — "
            "excluded from the total estimate, not assumed to be zero."
        )
    return result


def portfolio_risk_decomposition(
    snapshot: PortfolioSnapshot,
    *,
    benchmark_ticker: str = "SPY",
    lookback_days: int = 252,
    min_observations: int = 60,
    correlation_threshold: float = 0.75,
) -> dict:
    """Finite-safe portfolio beta, volatility contributions, and clusters.

    Every return series is explicitly aligned on the same dates before the
    covariance matrix is built. A holding with insufficient common history
    makes the decomposition unavailable instead of silently being assigned
    zero risk. Correlation clusters use positive correlation only; a strong
    negative relationship is a hedge, not hidden duplication.
    """
    if (
        isinstance(min_observations, bool)
        or not isinstance(min_observations, int)
        or min_observations < 20
    ):
        raise ValueError("min_observations must be an integer of at least 20")
    if (
        not math.isfinite(correlation_threshold)
        or not 0 < correlation_threshold < 1
    ):
        raise ValueError("correlation_threshold must be between 0 and 1")
    if (
        not math.isfinite(snapshot.total_equity)
        or snapshot.total_equity <= 0
    ):
        return {
            "available": False,
            "reason": "portfolio total equity must be positive and finite",
        }

    positions = [
        position
        for position in snapshot.positions
        if math.isfinite(position.market_value) and position.market_value > 0
    ]
    invalid_positions = [
        position.ticker
        for position in snapshot.positions
        if not math.isfinite(position.market_value)
        or position.market_value < 0
    ]
    if invalid_positions:
        return {
            "available": False,
            "reason": (
                "non-finite/negative market value for "
                + ", ".join(sorted(invalid_positions))
            ),
        }
    if not positions:
        return {"available": False, "reason": "portfolio has no invested positions"}

    tickers = list(
        dict.fromkeys(
            [position.ticker.upper() for position in positions]
            + [benchmark_ticker.upper()]
        )
    )
    data = fetch_historical(tickers, lookback_days=lookback_days)
    return_series: dict[str, pd.Series] = {}
    missing: list[str] = []
    for ticker in tickers:
        frame = data.get(ticker)
        if frame is None or frame.empty or "close" not in frame:
            missing.append(ticker)
            continue
        returns = (
            pd.to_numeric(frame["close"], errors="coerce")
            .pct_change(fill_method=None)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
        if len(returns) < min_observations:
            missing.append(ticker)
            continue
        return_series[ticker] = returns.rename(ticker)

    holding_tickers = [position.ticker.upper() for position in positions]
    missing_holdings = [
        ticker for ticker in holding_tickers if ticker not in return_series
    ]
    if missing_holdings:
        return {
            "available": False,
            "reason": (
                "insufficient finite history for "
                + ", ".join(sorted(missing_holdings))
            ),
            "missing_tickers": sorted(set(missing)),
        }

    aligned = (
        pd.concat(
            [return_series[ticker] for ticker in holding_tickers],
            axis=1,
            join="inner",
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(aligned) < min_observations:
        return {
            "available": False,
            "reason": (
                f"only {len(aligned)} common finite observations across "
                "all holdings after date alignment"
            ),
            "missing_tickers": sorted(set(missing)),
        }

    covariance = aligned.cov().to_numpy(dtype=float) * 252.0
    correlation = aligned.corr().to_numpy(dtype=float)
    if not np.isfinite(covariance).all() or not np.isfinite(correlation).all():
        return {
            "available": False,
            "reason": "covariance/correlation contains non-finite values",
        }

    weights = np.asarray(
        [
            position.market_value / snapshot.total_equity
            for position in positions
        ],
        dtype=float,
    )
    portfolio_variance = float(weights @ covariance @ weights)
    if not math.isfinite(portfolio_variance) or portfolio_variance <= 0:
        return {
            "available": False,
            "reason": "portfolio variance is non-positive or non-finite",
        }
    portfolio_volatility = math.sqrt(portfolio_variance)
    covariance_times_weights = covariance @ weights
    component_variance = weights * covariance_times_weights

    benchmark_betas: dict[str, float | None] = {}
    benchmark = return_series.get(benchmark_ticker.upper())
    for ticker in holding_tickers:
        if benchmark is None:
            benchmark_betas[ticker] = None
            continue
        pair = (
            pd.concat(
                [return_series[ticker], benchmark],
                axis=1,
                join="inner",
            )
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )
        if len(pair) < min_observations:
            benchmark_betas[ticker] = None
            continue
        benchmark_variance = float(pair.iloc[:, 1].var(ddof=1))
        beta = (
            float(pair.iloc[:, 0].cov(pair.iloc[:, 1]))
            / benchmark_variance
            if benchmark_variance > 0
            else float("nan")
        )
        benchmark_betas[ticker] = beta if math.isfinite(beta) else None

    contributions = []
    for index, position in enumerate(positions):
        ticker = position.ticker.upper()
        contributions.append(
            {
                "ticker": ticker,
                "portfolio_weight_pct": round(weights[index] * 100.0, 4),
                "beta": (
                    round(benchmark_betas[ticker], 4)
                    if benchmark_betas[ticker] is not None
                    else None
                ),
                "contribution_to_variance_pct": round(
                    component_variance[index] / portfolio_variance * 100.0,
                    4,
                ),
                "component_volatility_pct_points": round(
                    component_variance[index]
                    / portfolio_volatility
                    * 100.0,
                    4,
                ),
            }
        )

    adjacency: dict[str, set[str]] = {
        ticker: set() for ticker in holding_tickers
    }
    correlation_matrix: dict[str, dict[str, float]] = {}
    for left_index, left in enumerate(holding_tickers):
        correlation_matrix[left] = {}
        for right_index, right in enumerate(holding_tickers):
            value = float(correlation[left_index, right_index])
            correlation_matrix[left][right] = round(value, 4)
            if (
                left_index < right_index
                and value >= correlation_threshold
            ):
                adjacency[left].add(right)
                adjacency[right].add(left)

    clusters: list[dict[str, Any]] = []
    visited: set[str] = set()
    position_value = {
        position.ticker.upper(): position.market_value
        for position in positions
    }
    for ticker in holding_tickers:
        if ticker in visited:
            continue
        stack = [ticker]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        visited.update(component)
        if len(component) < 2:
            continue
        members = sorted(component)
        pairs = [
            correlation_matrix[left][right]
            for index, left in enumerate(members)
            for right in members[index + 1 :]
        ]
        clusters.append(
            {
                "tickers": members,
                "combined_weight_pct": round(
                    sum(position_value[item] for item in members)
                    / snapshot.total_equity
                    * 100.0,
                    4,
                ),
                "minimum_pairwise_correlation": round(min(pairs), 4),
            }
        )

    known_betas = [
        weights[index] * benchmark_betas[position.ticker.upper()]
        for index, position in enumerate(positions)
        if benchmark_betas[position.ticker.upper()] is not None
    ]
    all_betas_known = len(known_betas) == len(positions)
    return {
        "available": True,
        "as_of": str(aligned.index[-1]),
        "common_observations": len(aligned),
        "benchmark_ticker": benchmark_ticker.upper(),
        "portfolio_beta": (
            round(sum(known_betas), 4) if all_betas_known else None
        ),
        "annualized_volatility_pct": round(
            portfolio_volatility * 100.0, 4
        ),
        "contributions": contributions,
        "correlation_matrix": correlation_matrix,
        "correlated_clusters": clusters,
        "correlation_threshold": correlation_threshold,
        "missing_tickers": sorted(set(missing)),
    }


def check_policy_compliance(portfolio: PortfolioSnapshot, policy: TradingPolicy) -> list[str]:
    """
    Compares ACTUAL exposure against the active TradingPolicy's real
    numeric limits -- position, basket, leveraged-ETF, TOTAL exposure, and
    MINIMUM cash reserve -- unlike check_concentration(), which uses fixed
    informational thresholds unrelated to any policy.

    Computes every percentage directly from PortfolioSnapshot, NEVER from
    RiskExposure's display fields (GPT review, 2026-07-28, reproduced: a
    40.04% basket exposure against a 40% policy limit rounded to 40.0% in
    RiskExposure.basket_exposure_pct -- build_risk_exposure() rounds to 1
    decimal for display -- and silently evaded this check; same class of
    bug assistant/proposals.py's total-exposure remediation already fixed
    for proposal generation on 2026-07-31, for the same reason: a true
    exposure just above a boundary can round DOWN to exactly the limit).
    Also previously missing max_total_exposure_pct and min_cash_reserve_pct
    entirely (reproduced: a 60%-invested portfolio against a 50% total-
    exposure cap reported no violation) -- both now checked, matching the
    full set of caps assistant/proposals.py and risk/execution_gate.py
    already enforce.
    """
    from assistant.portfolio_snapshot import (
        PortfolioSnapshotIntegrityError,
        validate_long_only_portfolio_snapshot,
    )

    try:
        validate_long_only_portfolio_snapshot(portfolio)
    except PortfolioSnapshotIntegrityError as exc:
        return [f"Portfolio integrity unavailable: {exc}"]

    total = portfolio.total_equity_exact_decimal
    if total <= 0:
        return [
            "Portfolio total equity is non-positive; policy "
            "compliance cannot be computed safely."
        ]

    def percentage(value: Decimal, *, name: str) -> Decimal:
        ratio = deterministic_decimal_divide(value, total, name=f"{name} ratio")
        projected = exact_decimal_multiply(
            ratio,
            Decimal("100"),
            name=f"{name} percentage",
        )
        return deterministic_decimal_quantize(
            projected,
            Decimal("0.01"),
            name=f"{name} percentage display",
        )

    try:
        position_rows = [
            (position, position.exact_field("market_value"))
            for position in portfolio.positions
        ]
        max_position_value = exact_decimal_multiply(
            to_decimal(policy.max_position_pct, name="policy.max_position_pct"),
            total,
            name="maximum position value",
        )
        max_basket_value = exact_decimal_multiply(
            to_decimal(policy.max_basket_pct, name="policy.max_basket_pct"),
            total,
            name="maximum basket value",
        )
        max_leveraged_value = exact_decimal_multiply(
            to_decimal(
                policy.max_leveraged_etf_pct,
                name="policy.max_leveraged_etf_pct",
            ),
            total,
            name="maximum leveraged ETF value",
        )
        max_invested_value = exact_decimal_multiply(
            to_decimal(
                policy.max_total_exposure_pct,
                name="policy.max_total_exposure_pct",
            ),
            total,
            name="maximum invested value",
        )
        minimum_cash_value = exact_decimal_multiply(
            to_decimal(
                policy.min_cash_reserve_pct,
                name="policy.min_cash_reserve_pct",
            ),
            total,
            name="minimum cash reserve value",
        )
        position_limit_pct = percentage(
            max_position_value,
            name="maximum position exposure",
        )
        basket_limit_pct = percentage(
            max_basket_value,
            name="maximum basket exposure",
        )
        leveraged_limit_pct = percentage(
            max_leveraged_value,
            name="maximum leveraged ETF exposure",
        )
        invested_limit_pct = percentage(
            max_invested_value,
            name="maximum total exposure",
        )
        cash_limit_pct = percentage(
            minimum_cash_value,
            name="minimum cash reserve",
        )

        violations: list[str] = []
        for position, market_value in position_rows:
            if market_value > max_position_value:
                pct = percentage(
                    market_value,
                    name=f"{position.ticker} position exposure",
                )
                violations.append(
                    f"{position.ticker} is {pct:.2f}% of equity, exceeding the policy's "
                    f"max_position_pct limit of {position_limit_pct:.1f}%."
                )

        for basket_name, basket_tickers in BASKETS.items():
            basket_value = exact_decimal_sum(
                (
                    market_value
                    for position, market_value in position_rows
                    if position.ticker.upper() in basket_tickers
                ),
                name=f"{basket_name} basket value",
            )
            if basket_value > max_basket_value:
                pct = percentage(
                    basket_value,
                    name=f"{basket_name} basket exposure",
                )
                violations.append(
                    f"Basket '{basket_name}' is {pct:.2f}% of equity, exceeding the policy's "
                    f"max_basket_pct limit of {basket_limit_pct:.1f}%."
                )

        leveraged_value = exact_decimal_sum(
            (
                market_value
                for position, market_value in position_rows
                if position.is_leveraged_etf
            ),
            name="leveraged ETF value",
        )
        if leveraged_value > max_leveraged_value:
            leveraged_pct = percentage(
                leveraged_value,
                name="leveraged ETF exposure",
            )
            violations.append(
                f"Leveraged-ETF exposure is {leveraged_pct:.2f}% of equity, exceeding the policy's "
                f"max_leveraged_etf_pct limit of {leveraged_limit_pct:.1f}%."
            )

        invested_value = exact_decimal_sum(
            (market_value for _position, market_value in position_rows),
            name="total invested value",
        )
        if invested_value > max_invested_value:
            invested_pct = percentage(
                invested_value,
                name="total invested exposure",
            )
            violations.append(
                f"Total invested exposure is {invested_pct:.2f}% of equity, exceeding the policy's "
                f"max_total_exposure_pct limit of {invested_limit_pct:.1f}%."
            )

        cash_value = portfolio.cash_exact_decimal
        if cash_value < minimum_cash_value:
            cash_pct = percentage(cash_value, name="cash reserve")
            violations.append(
                f"Cash reserve is {cash_pct:.2f}% of equity, below the policy's "
                f"min_cash_reserve_pct minimum of {cash_limit_pct:.1f}%."
            )
        return violations
    except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
        return [
            "Portfolio policy-compliance arithmetic unavailable: "
            f"{exc}"
        ]
