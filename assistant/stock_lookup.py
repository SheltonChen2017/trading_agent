"""
Deterministic building blocks for the Watchlist "cart" feature: analyst
price targets by firm, a historical hold-period best/worst range, and
inverse-volatility weight suggestions for a combination of tickers.

Deliberately NO probability-of-return number anywhere in this module --
see scripts/personal_assistant_ui.py's Watchlist tab docstring for why:
this project has confirmed zero signals as real edge after rigorous
testing, so a bare probability would be fabricated or would dress up an
already-rejected backtest as more confident than it is. Everything here
is either a real historical fact (price targets that were actually
published, actual historical return ranges) or a well-established risk
heuristic (inverse-vol weighting) -- never a forecast.
"""
from __future__ import annotations

import pandas as pd

from backtest.engine import run_baseline_forward_returns
from data.price_target_data import fetch_price_target_history


def latest_price_targets_by_firm(ticker: str, max_firms: int = 4) -> list[dict]:
    """Most recent still-published price target per analyst firm, most
    recently updated firms first. Real per-firm data (via yfinance), not
    the synthesized trimmed consensus used elsewhere in this project
    (data/price_target_data.py's compute_consensus_price_target) --
    this shows the individual institutions' own numbers."""
    history = fetch_price_target_history([ticker]).get(ticker)
    if history is None or history.empty:
        return []
    sorted_history = history.sort_index()
    latest_per_firm = sorted_history.groupby("firm").tail(1).sort_index(ascending=False)
    return [
        {"firm": row["firm"], "price_target": round(float(row["price_target"]), 2), "as_of": str(idx.date())}
        for idx, row in latest_per_firm.head(max_firms).iterrows()
    ]


def historical_hold_period_range(
    ticker: str, data: dict[str, pd.DataFrame], hold_days: int = 20
) -> dict | None:
    """The REAL range of hold_days forward returns across this ticker's
    own price history -- not a forecast. Answers "historically, what was
    the best and worst outcome of holding this for N days starting on
    any day," using run_baseline_forward_returns() (every day, not just
    flagged signal days) so it isn't biased toward any particular entry
    rule. Returns None if the ticker has no/insufficient data.
    """
    if ticker not in data or data[ticker].empty:
        return None
    baseline = run_baseline_forward_returns({ticker: data[ticker]}, hold_days=hold_days, slippage_pct=0.0)
    if baseline.empty:
        return None
    returns = baseline["net_return_pct"]
    return {
        "hold_days": hold_days,
        "n_periods": int(len(returns)),
        "best_pct": round(float(returns.max()), 2),
        "worst_pct": round(float(returns.min()), 2),
        "median_pct": round(float(returns.median()), 2),
    }


def inverse_volatility_weights(volatilities: dict[str, float | None]) -> dict[str, float]:
    """Equal-risk-contribution-style weighting: weight inversely
    proportional to trailing volatility, the same principle
    strategies/vol_target_rotation.py uses to size leveraged exposure. A
    risk-based heuristic derived from historical data, NOT a return
    forecast or an expected-return optimization -- it only says "size
    the choppier name smaller," nothing about which one goes up.
    Tickers with unknown/zero volatility get zero weight; if every
    ticker is unknown, splits equally instead of returning all zeros.
    """
    inverse = {t: (1.0 / v if v and v > 0 else 0.0) for t, v in volatilities.items()}
    total = sum(inverse.values())
    if total <= 0:
        equal = 100.0 / len(volatilities) if volatilities else 0.0
        return {t: round(equal, 1) for t in volatilities}
    return {t: round(v / total * 100, 1) for t, v in inverse.items()}
