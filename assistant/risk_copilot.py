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

from config import INVERSE_LEVERAGED_ETF_TICKERS, LEVERAGED_ETF_UNDERLYING
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
    threshold while still breaching the policy (GPT review, 2026-08-01,
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
    HEDGE, not a duplicated same-direction bet (GPT review, 2026-08-01:
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


def check_policy_compliance(portfolio: PortfolioSnapshot, risk: RiskExposure, policy: TradingPolicy) -> list[str]:
    """
    Compares ACTUAL exposure against the active TradingPolicy's real
    numeric limits (max_position_pct/max_basket_pct/max_leveraged_etf_pct)
    -- unlike check_concentration(), which uses fixed informational
    thresholds unrelated to any policy. GPT review, 2026-08-01: reproduced
    a 10% AAPL position reporting "no concentration warnings" from
    check_concentration() while the active policy's 5% max_position_pct
    would make it a real proposal-generation trigger -- this function
    closes that gap by checking the same numeric caps
    generate_risk_reduction_proposals() uses.
    """
    violations = []
    if portfolio.total_equity > 0:
        for position in portfolio.positions:
            pct = position.market_value / portfolio.total_equity * 100
            if pct > policy.max_position_pct * 100:
                violations.append(
                    f"{position.ticker} is {pct:.1f}% of equity, exceeding the policy's "
                    f"max_position_pct limit of {policy.max_position_pct * 100:.1f}%."
                )
    for basket, pct in risk.basket_exposure_pct.items():
        if pct > policy.max_basket_pct * 100:
            violations.append(
                f"Basket '{basket}' is {pct}% of equity, exceeding the policy's "
                f"max_basket_pct limit of {policy.max_basket_pct * 100:.1f}%."
            )
    if risk.leveraged_etf_exposure_pct > policy.max_leveraged_etf_pct * 100:
        violations.append(
            f"Leveraged-ETF exposure is {risk.leveraged_etf_exposure_pct}%, exceeding the policy's "
            f"max_leveraged_etf_pct limit of {policy.max_leveraged_etf_pct * 100:.1f}%."
        )
    return violations
