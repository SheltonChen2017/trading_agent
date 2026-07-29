"""
Portfolio risk copilot — deterministic answers to the questions GPT's
design review specifically called out ("am I overexposed to X", "what
happens if the market falls N%", "do I have hidden duplication between
correlated holdings"). Every number here is computed from real
historical data or the portfolio snapshot directly — nothing is an LLM
estimate (see schemas.py's module docstring for why that rule matters).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import BASKETS, INVERSE_LEVERAGED_ETF_TICKERS, LEVERAGED_ETF_UNDERLYING
from data.market_data import fetch_historical
from assistant.policy import TradingPolicy
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
    tickers = [p.ticker for p in snapshot.positions]
    data = fetch_historical([benchmark_ticker] + tickers, lookback_days=lookback_days)

    if benchmark_ticker not in data or data[benchmark_ticker].empty:
        return {
            "benchmark_ticker": benchmark_ticker, "benchmark_move_pct": benchmark_move_pct,
            "position_impacts": [], "total_estimated_impact": None,
            "warning": f"No data available for benchmark {benchmark_ticker}.",
        }

    benchmark_returns = data[benchmark_ticker]["close"].pct_change().dropna()

    position_impacts = []
    total_impact = 0.0
    missing_beta_tickers = []
    for p in snapshot.positions:
        if p.ticker not in data or data[p.ticker].empty:
            position_impacts.append({"ticker": p.ticker, "beta": None, "estimated_impact": None})
            missing_beta_tickers.append(p.ticker)
            continue

        ticker_returns = data[p.ticker]["close"].pct_change().dropna()
        aligned = pd.concat([ticker_returns, benchmark_returns], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            position_impacts.append({"ticker": p.ticker, "beta": None, "estimated_impact": None})
            missing_beta_tickers.append(p.ticker)
            continue

        aligned.columns = ["ticker", "benchmark"]
        beta = float(np.cov(aligned["ticker"], aligned["benchmark"])[0, 1] / np.var(aligned["benchmark"], ddof=1))
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
    violations: list[str] = []
    total = portfolio.total_equity
    if total <= 0:
        return violations

    for position in portfolio.positions:
        pct = position.market_value / total * 100
        if pct > policy.max_position_pct * 100:
            violations.append(
                f"{position.ticker} is {pct:.2f}% of equity, exceeding the policy's "
                f"max_position_pct limit of {policy.max_position_pct * 100:.1f}%."
            )

    for basket_name, basket_tickers in BASKETS.items():
        basket_value = sum(p.market_value for p in portfolio.positions if p.ticker in basket_tickers)
        if basket_value <= 0:
            continue
        pct = basket_value / total * 100
        if pct > policy.max_basket_pct * 100:
            violations.append(
                f"Basket '{basket_name}' is {pct:.2f}% of equity, exceeding the policy's "
                f"max_basket_pct limit of {policy.max_basket_pct * 100:.1f}%."
            )

    leveraged_value = sum(p.market_value for p in portfolio.positions if p.is_leveraged_etf)
    leveraged_pct = leveraged_value / total * 100
    if leveraged_pct > policy.max_leveraged_etf_pct * 100:
        violations.append(
            f"Leveraged-ETF exposure is {leveraged_pct:.2f}% of equity, exceeding the policy's "
            f"max_leveraged_etf_pct limit of {policy.max_leveraged_etf_pct * 100:.1f}%."
        )

    invested_pct = sum(p.market_value for p in portfolio.positions) / total * 100
    if invested_pct > policy.max_total_exposure_pct * 100:
        violations.append(
            f"Total invested exposure is {invested_pct:.2f}% of equity, exceeding the policy's "
            f"max_total_exposure_pct limit of {policy.max_total_exposure_pct * 100:.1f}%."
        )

    cash_pct = portfolio.cash / total * 100
    if cash_pct < policy.min_cash_reserve_pct * 100:
        violations.append(
            f"Cash reserve is {cash_pct:.2f}% of equity, below the policy's "
            f"min_cash_reserve_pct minimum of {policy.min_cash_reserve_pct * 100:.1f}%."
        )

    return violations
