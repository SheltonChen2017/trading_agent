"""Frozen baselines every ML candidate must beat (strategy doc 8.2, 11.3).

These are deliberately trivial and deliberately fixed. Doc 8.3: "Reject the
ML candidate if it does not beat the simple EWMA baseline across multiple
untouched folds." A baseline that gets tuned alongside the model it is
supposed to challenge is not a baseline -- so nothing here takes a fitted
parameter from data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_SESSIONS_PER_YEAR = 252


class BaselineError(ValueError):
    """Inputs cannot support a baseline forecast."""


def trailing_realized_volatility_pct(
    daily_returns: pd.Series, *, window: int
) -> float | None:
    """Baseline #1 (doc 8.2): tomorrow's volatility is today's volatility.

    Non-annualized percent std of daily returns, matching
    signals/regime.py's compute_trailing_market_volatility() convention so
    a baseline number here is directly comparable to the one the live
    briefing already shows.
    """
    if window < 2:
        raise BaselineError("window must be at least 2")
    clean = pd.to_numeric(daily_returns, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if len(clean) < window:
        return None
    value = float(clean.tail(window).std(ddof=1) * 100)
    return value if np.isfinite(value) else None


def ewma_volatility_pct(
    daily_returns: pd.Series, *, halflife: float = 20.0, min_observations: int = 20
) -> float | None:
    """Baseline #2 (doc 8.2): exponentially-weighted volatility.

    This is the baseline doc 8.3 singles out as the one an ML candidate
    must beat "across multiple untouched folds" -- it is a genuinely strong
    volatility forecaster, which is exactly why it is the bar.
    """
    if halflife <= 0 or not np.isfinite(halflife):
        raise BaselineError("halflife must be a positive finite number")
    clean = pd.to_numeric(daily_returns, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if len(clean) < min_observations:
        return None
    variance = clean.pow(2).ewm(halflife=halflife).mean()
    if variance.empty:
        return None
    value = float(np.sqrt(variance.iloc[-1]) * 100)
    return value if np.isfinite(value) else None


def no_skill_rank_baseline(n: int) -> np.ndarray:
    """Baseline #0 for the ranker (doc 11.3): every name scores identically.

    Any ranking metric computed against this must come out at chance. It
    exists so an evaluation harness bug that manufactures apparent skill
    shows up against a score vector that provably contains none.
    """
    if n < 1:
        raise BaselineError("n must be positive")
    return np.zeros(n, dtype=float)


def residual_momentum_score(
    close: pd.Series,
    benchmark_close: pd.Series,
    *,
    lookback_sessions: int = 252,
    skip_sessions: int = 21,
) -> float | None:
    """Baseline #1 for the ranker (doc 11.3): simple 12-1 residual momentum.

    "12-1" skips the most recent month, the standard construction that
    avoids the well-documented short-term reversal effect contaminating a
    momentum measurement. Residual = own return minus the aligned benchmark
    return over the same window.

    NOTE for anyone tempted to promote a momentum result in this project:
    plain and residualized cross-sectional momentum have BOTH already been
    tested here and REJECTED (assistant/research_findings.json), the
    residual version explicitly as "the final momentum-family test per the
    source recommendation". This function exists to be a baseline, not a
    candidate.
    """
    if lookback_sessions < 2 or skip_sessions < 0:
        raise BaselineError("lookback_sessions must be >= 2 and skip_sessions >= 0")
    if lookback_sessions <= skip_sessions:
        raise BaselineError("lookback_sessions must exceed skip_sessions")

    own = pd.to_numeric(close, errors="coerce").where(lambda s: s > 0).dropna()
    bench = pd.to_numeric(benchmark_close, errors="coerce").where(lambda s: s > 0).dropna()
    aligned = pd.DataFrame({"own": own, "bench": bench}).dropna()
    if len(aligned) < lookback_sessions + 1:
        return None

    window = aligned.tail(lookback_sessions + 1)
    start_own = float(window["own"].iloc[0])
    start_bench = float(window["bench"].iloc[0])
    # skip the most recent `skip_sessions` sessions
    end_position = len(window) - 1 - skip_sessions
    if end_position <= 0:
        return None
    end_own = float(window["own"].iloc[end_position])
    end_bench = float(window["bench"].iloc[end_position])
    if start_own <= 0 or start_bench <= 0:
        return None

    own_return = (end_own / start_own - 1.0) * 100
    bench_return = (end_bench / start_bench - 1.0) * 100
    value = own_return - bench_return
    return value if np.isfinite(value) else None
