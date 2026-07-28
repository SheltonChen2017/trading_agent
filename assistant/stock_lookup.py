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
from signals.regime import compute_trailing_market_volatility

BLENDED_VOL_SHORT_DAYS = 20
BLENDED_VOL_MEDIUM_DAYS = 60
BLENDED_VOL_SHORT_WEIGHT = 0.5  # 50/50 blend by default


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


def compute_blended_volatility(
    close: pd.Series,
    as_of: pd.Timestamp,
    short_days: int = BLENDED_VOL_SHORT_DAYS,
    medium_days: int = BLENDED_VOL_MEDIUM_DAYS,
    short_weight: float = BLENDED_VOL_SHORT_WEIGHT,
) -> float | None:
    """
    Blend of a short-term (default 20-day) and medium-term (default
    60-day) trailing realized volatility, weighted `short_weight` /
    (1 - short_weight). A pure 20-day window can size a ticker mostly off
    whatever happened to occur in the last few weeks -- blending in a
    longer window makes the estimate reflect more typical behavior
    instead (GPT review, 2026-07-27). Returns None only if BOTH windows
    are unavailable; falls back to whichever single window IS available
    if only one is.
    """
    df = pd.DataFrame({"close": close})
    short_vol = compute_trailing_market_volatility(df, as_of, lookback_days=short_days)
    medium_vol = compute_trailing_market_volatility(df, as_of, lookback_days=medium_days)
    if short_vol is None and medium_vol is None:
        return None
    if short_vol is None:
        return medium_vol
    if medium_vol is None:
        return short_vol
    return short_vol * short_weight + medium_vol * (1 - short_weight)


def inverse_volatility_weights(
    volatilities: dict[str, float | None], max_weight_pct: float | None = None
) -> dict[str, float]:
    """Equal-risk-contribution-style weighting: weight inversely
    proportional to trailing volatility, the same principle
    strategies/vol_target_rotation.py uses to size leveraged exposure. A
    risk-based heuristic derived from historical data, NOT a return
    forecast or an expected-return optimization -- it only says "size
    the choppier name smaller," nothing about which one goes up.
    Tickers with unknown/zero volatility get zero weight; if every
    ticker is unknown, splits equally instead of returning all zeros.

    `max_weight_pct`: if set, no single ticker's weight can exceed this
    -- an unusually calm ticker's raw inverse-vol share can otherwise
    dominate the split with no limit (GPT review, 2026-07-27). Excess
    above the cap is redistributed proportionally across the other,
    not-yet-capped tickers (an iterative waterfall, since redistributing
    can itself push another ticker over the cap). If the cap is
    infeasible for this many tickers (e.g. max_weight_pct * count < 100),
    every ticker ends up AT the cap and the weights won't sum to 100 --
    documented behavior, not a silent bug.
    """
    inverse = {t: (1.0 / v if v and v > 0 else 0.0) for t, v in volatilities.items()}
    total = sum(inverse.values())
    if total <= 0:
        equal = 100.0 / len(volatilities) if volatilities else 0.0
        weights = {t: equal for t in volatilities}
    else:
        weights = {t: v / total * 100 for t, v in inverse.items()}

    if max_weight_pct is not None:
        weights = _cap_and_redistribute(weights, max_weight_pct)

    return {t: round(w, 1) for t, w in weights.items()}


def _cap_and_redistribute(weights: dict[str, float], max_weight_pct: float) -> dict[str, float]:
    weights = dict(weights)
    for _ in range(len(weights) + 1):  # bounded: at most one ticker newly capped per pass
        over = {t: w for t, w in weights.items() if w > max_weight_pct}
        if not over:
            break
        excess = sum(w - max_weight_pct for w in over.values())
        for t in over:
            weights[t] = max_weight_pct
        under = {t: w for t, w in weights.items() if t not in over}
        under_total = sum(under.values())
        if under_total <= 0:
            break  # every ticker is capped or zero -- can't redistribute further
        for t in under:
            weights[t] += excess * (weights[t] / under_total)
    return weights
