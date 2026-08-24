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

import math

import pandas as pd

from data.price_target_data import fetch_price_target_history
from assistant.market_analytics import (
    compute_historical_forward_returns,
    compute_trailing_market_volatility,
)

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
    any day," using compute_historical_forward_returns() (every day, not just
    flagged signal days) so it isn't biased toward any particular entry
    rule. Returns None if the ticker has no/insufficient data.
    """
    if ticker not in data or data[ticker].empty:
        return None
    baseline = compute_historical_forward_returns(
        {ticker: data[ticker]}, hold_days=hold_days, slippage_pct=0.0
    )
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
    dominate the split with no limit (GPT review, 2026-07-27). Must be
    finite and in (0, 100]. Excess above the cap is redistributed
    proportionally across tickers not YET capped (an iterative
    waterfall, since redistributing can itself push another ticker over
    the cap -- a prior version recomputed "over the cap" fresh every pass
    instead of permanently excluding already-capped tickers, so a ticker
    capped in an early pass could receive MORE excess in a later pass and
    end up back over the cap; reproduced examples included a 40% cap
    letting a ticker reach 56-73%. GPT review, 2026-07-28). Raises
    ValueError if the cap is infeasible for how many tickers actually
    have a nonzero weight (e.g. a 40% cap with only 2 eligible tickers
    can allocate at most 80% -- the caller must raise the cap, add more
    eligible tickers, or accept leaving cash unallocated some other way).
    """
    if max_weight_pct is not None and (
        not math.isfinite(max_weight_pct) or max_weight_pct <= 0 or max_weight_pct > 100
    ):
        raise ValueError(f"max_weight_pct must be a finite number in (0, 100], got {max_weight_pct}.")

    inverse = {t: (1.0 / v if v and v > 0 else 0.0) for t, v in volatilities.items()}
    total = sum(inverse.values())
    if total <= 0:
        equal = 100.0 / len(volatilities) if volatilities else 0.0
        weights = {t: equal for t in volatilities}
    else:
        weights = {t: v / total * 100 for t, v in inverse.items()}

    if max_weight_pct is not None:
        n_eligible = sum(1 for w in weights.values() if w > 0)
        if n_eligible > 0 and max_weight_pct * n_eligible < 100 - 1e-6:
            raise ValueError(
                f"max_weight_pct={max_weight_pct} is infeasible for {n_eligible} eligible ticker(s) -- "
                f"the minimum feasible cap here is {100 / n_eligible:.2f}%. Raise the cap, add more "
                "eligible tickers, or accept an incomplete allocation some other way."
            )
        weights = _cap_and_redistribute(weights, max_weight_pct)

    return {t: round(w, 1) for t, w in weights.items()}


def _cap_and_redistribute(weights: dict[str, float], max_weight_pct: float) -> dict[str, float]:
    """Caller (inverse_volatility_weights) has already validated the cap
    is feasible for these weights -- this function assumes that and
    enforces it via a hard postcondition assert, so a future change
    can't silently reintroduce the class of bug this replaced."""
    weights = dict(weights)
    tolerance = 1e-9
    frozen: set[str] = set()  # tickers pinned at the cap -- NEVER eligible for more redistribution again

    for _ in range(len(weights) + 1):  # bounded: at least one NEW ticker gets frozen per non-terminal pass
        newly_over = {t for t, w in weights.items() if t not in frozen and w > max_weight_pct + tolerance}
        if not newly_over:
            break
        excess = 0.0
        for t in newly_over:
            excess += weights[t] - max_weight_pct
            weights[t] = max_weight_pct
        frozen |= newly_over

        eligible = [t for t in weights if t not in frozen]
        eligible_total = sum(weights[t] for t in eligible)
        if eligible_total <= 0:
            break  # every remaining ticker is frozen or zero -- can't redistribute further
        for t in eligible:
            weights[t] += excess * (weights[t] / eligible_total)

    for t, w in weights.items():
        assert w <= max_weight_pct + 1e-6, f"cap postcondition violated for {t!r}: {w} > {max_weight_pct}"
    return weights
