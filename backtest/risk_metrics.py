"""
Canonical risk-shape metrics for an equity curve or return series --
drawdown, tail loss, time spent under water, and up/down capture versus a
benchmark. Deliberately separate from backtest/engine.py's rigor toolkit
(out_of_sample_significance_by_block(), bootstrap_edge_significance(),
etc.), which answers "is this average return edge statistically real";
this module answers "what does the risk SHAPE of a return stream look
like," an orthogonal question (docs/MANDATE.md, 2026-07-28: reframes how
this project evaluates backtests/paper-trading away from leading with
CAGR/Sharpe).

max_drawdown_pct() is the canonical implementation for what used to be
two independent, drifting copies: backtest/portfolio_simulator.py's
private _max_drawdown_pct() and strategies/leverage_rotation.py's public
max_drawdown_pct() -- both now delegate here (docs/ARCHITECTURE_DEBT.md).
"""
from __future__ import annotations

import pandas as pd


def max_drawdown_pct(equity_curve: pd.Series) -> float:
    """Largest peak-to-trough decline in `equity_curve`, as a negative
    percentage (0.0 for an empty series)."""
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min()) * 100


def expected_shortfall_pct(returns: pd.Series, confidence: float = 0.95) -> float:
    """Mean of the worst `(1 - confidence)` fraction of periodic returns
    in `returns` (already expressed as percentages, e.g. from
    `equity_curve.pct_change() * 100`) -- the average loss conditional on
    being in the tail, a.k.a. CVaR. Returns a negative number (or 0.0).

    Fails closed rather than silently interpolating a tail from too few
    points: if fewer than 1 observation would fall in the tail fraction,
    returns 0.0 instead of fabricating a shortfall estimate from noise."""
    clean = returns.dropna()
    if clean.empty or not (0.0 < confidence < 1.0):
        return 0.0
    tail_fraction = 1.0 - confidence
    # round() before int() to absorb float imprecision in tail_fraction
    # (e.g. 1.0 - 0.9 == 0.09999999999999998), which would otherwise
    # truncate an intended tail_size=1 down to 0.
    tail_size = int(round(len(clean) * tail_fraction, 8))
    if tail_size < 1:
        return 0.0
    worst = clean.sort_values().iloc[:tail_size]
    return float(worst.mean())


def time_under_water(equity_curve: pd.Series) -> dict:
    """How long `equity_curve` spends below its own running peak, in
    trading-day index positions (consistent with this project's existing
    `n_years = len(series) / 252` convention, e.g.
    backtest/portfolio_simulator.py's _cagr_pct()) -- not wall-clock days.

    Returns {'max_days_under_water': int, 'pct_of_period_under_water':
    float, 'current_days_under_water': int}. All zero for an empty
    series."""
    if equity_curve.empty:
        return {"max_days_under_water": 0, "pct_of_period_under_water": 0.0, "current_days_under_water": 0}
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
        "pct_of_period_under_water": float(under_water.sum()) / len(equity_curve) * 100,
        "current_days_under_water": current_streak,
    }


def _capture_pct(strategy_returns: pd.Series, benchmark_returns: pd.Series, *, direction: str) -> float | None:
    if not strategy_returns.index.equals(benchmark_returns.index):
        raise ValueError(
            "strategy_returns and benchmark_returns must share the exact same index -- "
            "align them before calling (this project fails closed on data-integrity "
            "mismatches rather than silently reindexing/dropping)."
        )
    mask = benchmark_returns < 0 if direction == "down" else benchmark_returns > 0
    if not mask.any():
        return None  # undefined, not 0.0 -- 0.0 would misleadingly read as "perfect protection"
    benchmark_mean = float(benchmark_returns[mask].mean())
    if benchmark_mean == 0.0:
        return None
    strategy_mean = float(strategy_returns[mask].mean())
    return strategy_mean / benchmark_mean * 100


def downside_capture_pct(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Mean strategy return over periods where the benchmark was down,
    divided by the mean benchmark return over those same periods, x 100.
    Both series must already share the same index. Returns None (not
    0.0) if the benchmark has zero down-periods in the window."""
    return _capture_pct(strategy_returns, benchmark_returns, direction="down")


def upside_capture_pct(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Mirror of downside_capture_pct() over benchmark UP-periods."""
    return _capture_pct(strategy_returns, benchmark_returns, direction="up")
