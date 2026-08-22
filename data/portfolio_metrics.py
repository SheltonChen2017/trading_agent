"""Policy-neutral risk-shape metrics for portfolio evidence.

Both the research workbench and the trading assistant's paper-evidence reader
consume these deterministic measurements. They operate only on caller-supplied
series and grant no research, proposal, promotion, or execution authority.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TRADING_SESSIONS_PER_YEAR = 252


class PortfolioMetricsError(ValueError):
    """Input series cannot support trustworthy portfolio metrics."""


def max_drawdown_pct(equity_curve: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative percentage."""
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min()) * 100


def expected_shortfall_pct(
    returns: pd.Series, confidence: float = 0.95
) -> float:
    """Mean of the worst ``1-confidence`` fraction of percentage returns.

    Fails closed rather than interpolating a tail from too few points: when
    fewer than one observation falls in the tail fraction, returns 0.0 rather
    than manufacturing a shortfall estimate from noise.
    """
    clean = returns.dropna()
    if clean.empty or not (0.0 < confidence < 1.0):
        return 0.0
    tail_fraction = 1.0 - confidence
    tail_size = int(round(len(clean) * tail_fraction, 8))
    if tail_size < 1:
        return 0.0
    return float(clean.sort_values().iloc[:tail_size].mean())


def time_under_water(equity_curve: pd.Series) -> dict[str, float | int]:
    """Measure consecutive and total trading sessions below the running peak.

    Counts index positions, not wall-clock days, matching the repository's
    252-session annualization convention.
    """
    if equity_curve.empty:
        return {
            "max_days_under_water": 0,
            "pct_of_period_under_water": 0.0,
            "current_days_under_water": 0,
        }
    running_max = equity_curve.cummax()
    under_water = equity_curve < running_max
    max_streak = 0
    current_streak = 0
    for is_under in under_water:
        if is_under:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return {
        "max_days_under_water": max_streak,
        "pct_of_period_under_water": (
            float(under_water.sum()) / len(equity_curve) * 100
        ),
        "current_days_under_water": current_streak,
    }


def _capture_pct(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    direction: str,
) -> float | None:
    if not strategy_returns.index.equals(benchmark_returns.index):
        raise ValueError(
            "strategy_returns and benchmark_returns must share the exact "
            "same index -- align them before calling (this project fails "
            "closed rather than silently reindexing or dropping rows)"
        )
    # Jointly remove a date when either side is non-finite. Independent pandas
    # means would otherwise use different samples and can materially distort
    # capture (the original defect changed downside capture from 50% to 16.67%).
    both_finite = np.isfinite(strategy_returns.to_numpy()) & np.isfinite(
        benchmark_returns.to_numpy()
    )
    strategy_returns = strategy_returns[both_finite]
    benchmark_returns = benchmark_returns[both_finite]
    mask = benchmark_returns < 0 if direction == "down" else benchmark_returns > 0
    if not mask.any():
        return None
    benchmark_mean = float(benchmark_returns[mask].mean())
    if benchmark_mean == 0.0:
        return None
    return float(strategy_returns[mask].mean()) / benchmark_mean * 100


def downside_capture_pct(
    strategy_returns: pd.Series, benchmark_returns: pd.Series
) -> float | None:
    return _capture_pct(
        strategy_returns, benchmark_returns, direction="down"
    )


def upside_capture_pct(
    strategy_returns: pd.Series, benchmark_returns: pd.Series
) -> float | None:
    return _capture_pct(strategy_returns, benchmark_returns, direction="up")


def compute_portfolio_metrics(
    equity_curve: pd.Series, benchmark_close: pd.Series
) -> dict[str, Any]:
    """Compute the canonical portfolio risk-shape metric record."""
    if not isinstance(equity_curve, pd.Series) or len(equity_curve) < 2:
        raise PortfolioMetricsError(
            "equity_curve needs at least two observations"
        )
    if not isinstance(benchmark_close, pd.Series) or len(benchmark_close) < 2:
        raise PortfolioMetricsError(
            "benchmark_close needs at least two observations"
        )
    if equity_curve.index.has_duplicates or benchmark_close.index.has_duplicates:
        raise PortfolioMetricsError(
            "metric inputs cannot have duplicate timestamps"
        )
    equity = pd.to_numeric(equity_curve.sort_index(), errors="coerce")
    benchmark = pd.to_numeric(benchmark_close.sort_index(), errors="coerce")
    if (
        not np.isfinite(equity.to_numpy(dtype=float)).all()
        or (equity <= 0).any()
    ):
        raise PortfolioMetricsError(
            "equity_curve must be positive and finite"
        )

    common = equity.index.intersection(benchmark.index)
    if len(common) < 2:
        raise PortfolioMetricsError(
            "equity curve and benchmark have insufficient overlap"
        )
    equity = equity.reindex(common)
    benchmark = benchmark.reindex(common)
    strategy_returns_fraction = equity.pct_change().dropna()
    benchmark_returns_fraction = benchmark.pct_change().dropna()
    aligned = strategy_returns_fraction.index.intersection(
        benchmark_returns_fraction.index
    )
    strategy_returns_pct = strategy_returns_fraction.reindex(aligned) * 100
    benchmark_returns_pct = benchmark_returns_fraction.reindex(aligned) * 100
    annualized_volatility = (
        float(strategy_returns_fraction.std(ddof=1))
        * math.sqrt(TRADING_SESSIONS_PER_YEAR)
        * 100
    )
    underwater = time_under_water(equity)
    downside = downside_capture_pct(
        strategy_returns_pct, benchmark_returns_pct
    )
    upside = upside_capture_pct(strategy_returns_pct, benchmark_returns_pct)
    return {
        "sessions": len(equity),
        "start": str(equity.index.min()),
        "end": str(equity.index.max()),
        "annualized_volatility_pct": round(annualized_volatility, 4),
        "max_drawdown_pct": round(max_drawdown_pct(equity), 4),
        "expected_shortfall_pct_95": round(
            expected_shortfall_pct(strategy_returns_pct, confidence=0.95), 4
        ),
        "max_time_under_water_sessions": underwater[
            "max_days_under_water"
        ],
        "current_time_under_water_sessions": underwater[
            "current_days_under_water"
        ],
        "pct_of_period_under_water": round(
            float(underwater["pct_of_period_under_water"]), 4
        ),
        "downside_capture_pct": (
            None if downside is None else round(downside, 4)
        ),
        "upside_capture_pct": None if upside is None else round(upside, 4),
    }


__all__ = [
    "PortfolioMetricsError",
    "compute_portfolio_metrics",
    "downside_capture_pct",
    "expected_shortfall_pct",
    "max_drawdown_pct",
    "time_under_water",
    "upside_capture_pct",
]
