"""
Kelly-criterion rotation between an unleveraged index ETF ("stable") and
a leveraged same-index fund ("leveraged"), with two optional refinements
on top: a one-way profit ratchet and a trend-acceleration multiplier.

WHY THIS MECHANISM: strategies/vol_target_rotation.py sizes leveraged
exposure by INVERSE VOLATILITY alone — target_weight = target_vol /
realized_vol. That formula has no way to tell "scary because crashing"
from "scary because ripping upward," since volatility is unsigned; it
was identified as the reason vol-targeting cost QQQ/TQQQ real upside (see
memory: project_vol_target_rotation). This instead uses the classic
Kelly criterion / growth-optimal sizing formula, which uses the SIGNED
mean return in the numerator:

    target_leveraged_weight = clip(kelly_fraction * mean_daily_return / variance_daily_return, 0, max_leveraged_weight)

A period with strong positive mean return AND high variance can still
size UP under this formula (if the mean is large enough relative to the
variance), whereas vol-targeting would have sized it down purely because
variance rose. A period with negative mean return sizes toward zero
automatically (clipped at the floor), without needing a separate trend
filter — though the same downtrend-forces-zero override from
vol_target_rotation.py is kept as an extra defensive layer regardless.

`kelly_fraction` is a risk-aversion knob (1.0 = full Kelly, usually too
aggressive in practice; 0.5 = "half-Kelly", a common conservative
starting point) — swept in the grid search rather than assumed.

TWO OPTIONAL REFINEMENTS, each independently togglable:
  - `one_way_ratchet=True`: only ever TRIM the leveraged position toward
    a lower target; never buys UP into it when the target rises. Cuts
    round-trip trades roughly in half by construction (fewer taxable
    events) and avoids re-leveraging into what might be a falling knife.
  - `use_trend_acceleration=True`: dampens the target weight when a
    medium-term moving average is flattening/decelerating even while
    still technically above the long-term trend filter — leaning in
    hardest during accelerating uptrends, not just any uptrend.

Same execution discipline as the rest of this project: decisions use
each check date's own CLOSE; the rebalance trade executes at the
FOLLOWING trading day's OPEN. Tax/cost modeling built in from the start.
"""
from __future__ import annotations

import math
from numbers import Real

import pandas as pd

from data.research_input_contracts import (
    require_aligned_price_series,
    require_combined_rates_at_most_one,
    require_finite_number,
    require_long_only_weights,
    require_positive_int,
    require_positive_number,
    require_rate,
)
from strategies.leverage_rotation import cagr_pct, max_drawdown_pct
from strategies.trend_vol_rotation import classify_trend

TREND_ACCELERATION_DAMPENING = 0.5  # multiplier applied when the medium-term trend is decelerating


def compute_trailing_mean_and_variance(close: pd.Series, as_of: pd.Timestamp, lookback_days: int) -> tuple[float | None, float | None]:
    """Trailing daily mean return and variance (both as plain decimals,
    e.g. 0.001 = 0.1%/day), ending at (and including) `as_of`. Purely
    backward-looking. Returns (None, None) if there isn't enough history."""
    require_aligned_price_series({"close": close})
    lookback_days = require_positive_int(lookback_days, name="lookback_days")
    if as_of not in close.index:
        return None, None
    idx = close.index.get_loc(as_of)
    start_idx = idx - lookback_days
    if start_idx < 0:
        return None, None
    window = close.iloc[start_idx : idx + 1]
    daily_returns = window.pct_change().dropna()
    if len(daily_returns) < 2:
        return None, None
    return float(daily_returns.mean()), float(daily_returns.var())


def compute_trend_acceleration_multiplier(
    close: pd.Series, as_of: pd.Timestamp, medium_lookback_days: int, slope_lookback_days: int
) -> float:
    """1.0 if the medium-term (e.g. 50-day) moving average is HIGHER than
    it was `slope_lookback_days` ago (accelerating/steady uptrend);
    TREND_ACCELERATION_DAMPENING if it's flattening or falling
    (decelerating), even if the underlying is still above its long-term
    trend filter. Returns 1.0 (no dampening) if there isn't enough
    history to compute the slope, rather than guessing."""
    require_aligned_price_series({"close": close})
    medium_lookback_days = require_positive_int(medium_lookback_days, name="medium_lookback_days")
    slope_lookback_days = require_positive_int(slope_lookback_days, name="slope_lookback_days")
    if as_of not in close.index:
        return 1.0
    idx = close.index.get_loc(as_of)
    if idx - slope_lookback_days - medium_lookback_days + 1 < 0:
        return 1.0

    def _sma_ending_at(end_idx: int) -> float:
        return float(close.iloc[end_idx - medium_lookback_days + 1 : end_idx + 1].mean())

    sma_now = _sma_ending_at(idx)
    sma_before = _sma_ending_at(idx - slope_lookback_days)
    return 1.0 if sma_now >= sma_before else TREND_ACCELERATION_DAMPENING


def compute_kelly_leveraged_weight(
    mean_daily_return: float | None,
    variance_daily_return: float | None,
    kelly_fraction: float,
    max_leveraged_weight: float,
) -> float:
    """Returns 0.0 if inputs are missing or non-finite, or if variance is
    zero/negative (can't size against unknown/zero variance).

    Non-finiteness is checked explicitly for the same reason as
    strategies/vol_target_rotation.py's compute_target_leveraged_weight()
    (independent review, 2026-07-29): a NaN mean or variance defeats every
    ordered comparison, so it passed the guard, and
    `min(max_leveraged_weight, NaN)` then returned `max_leveraged_weight` --
    unknown inputs produced the MAXIMUM leveraged weight. None/zero/
    negative/inf were already handled correctly; only NaN failed, and it
    failed toward more leverage."""
    kelly_fraction = require_finite_number(
        kelly_fraction,
        name="kelly_fraction",
        minimum=0.0,
        maximum=1.0,
    )
    max_leveraged_weight = require_finite_number(
        max_leveraged_weight,
        name="max_leveraged_weight",
        minimum=0.0,
        maximum=1.0,
    )
    if (
        mean_daily_return is None
        or variance_daily_return is None
        or isinstance(mean_daily_return, bool)
        or isinstance(variance_daily_return, bool)
        or not isinstance(mean_daily_return, Real)
        or not isinstance(variance_daily_return, Real)
        or not math.isfinite(float(mean_daily_return))
        or not math.isfinite(float(variance_daily_return))
        or variance_daily_return <= 0
    ):
        return 0.0
    return max(0.0, min(max_leveraged_weight, kelly_fraction * mean_daily_return / variance_daily_return))


def simulate_kelly_rotation(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    kelly_fraction: float,
    max_leveraged_weight: float = 1.0,
    trend_lookback_days: int = 200,
    kelly_lookback_days: int = 20,
    rebalance_check_days: int = 21,
    band_pct: float = 5.0,
    one_way_ratchet: bool = False,
    use_trend_acceleration: bool = False,
    trend_acceleration_medium_days: int = 50,
    trend_acceleration_slope_days: int = 20,
    initial_total: float = 10_000.0,
    fallback_weights: tuple[float, float] = (0.5, 0.5),
    start_date: pd.Timestamp | None = None,
    cost_pct: float = 0.0,
    tax_rate: float = 0.0,
) -> dict:
    require_aligned_price_series(
        {
            "stable_close": stable_close,
            "leveraged_close": leveraged_close,
            "stable_open": stable_open,
            "leveraged_open": leveraged_open,
        }
    )
    kelly_fraction = require_finite_number(
        kelly_fraction,
        name="kelly_fraction",
        minimum=0.0,
        maximum=1.0,
    )
    max_leveraged_weight = require_finite_number(
        max_leveraged_weight,
        name="max_leveraged_weight",
        minimum=0.0,
        maximum=1.0,
    )
    trend_lookback_days = require_positive_int(trend_lookback_days, name="trend_lookback_days")
    kelly_lookback_days = require_positive_int(kelly_lookback_days, name="kelly_lookback_days")
    rebalance_check_days = require_positive_int(rebalance_check_days, name="rebalance_check_days")
    trend_acceleration_medium_days = require_positive_int(
        trend_acceleration_medium_days,
        name="trend_acceleration_medium_days",
    )
    trend_acceleration_slope_days = require_positive_int(
        trend_acceleration_slope_days,
        name="trend_acceleration_slope_days",
    )
    band_pct = require_finite_number(band_pct, name="band_pct", minimum=0.0, maximum=100.0)
    initial_total = require_positive_number(initial_total, name="initial_total")
    fallback_weights = require_long_only_weights(
        fallback_weights,
        name="fallback_weights",
        expected_size=2,
    )
    cost_pct = require_rate(cost_pct, name="cost_pct")
    tax_rate = require_rate(tax_rate, name="tax_rate", allow_one=True)
    require_combined_rates_at_most_one(
        cost_pct,
        tax_rate,
        first_name="cost_pct",
        second_name="tax_rate",
    )
    all_dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    stable_close = stable_close.reindex(all_dates)
    leveraged_close = leveraged_close.reindex(all_dates)
    stable_open = stable_open.reindex(all_dates)
    leveraged_open = leveraged_open.reindex(all_dates)

    sim_dates = all_dates[all_dates >= start_date] if start_date is not None else all_dates
    if len(sim_dates) == 0:
        raise ValueError("start_date leaves no dates to simulate")

    stable_w0, lev_w0 = fallback_weights
    stable_shares = (initial_total * stable_w0) / stable_close.loc[sim_dates[0]]
    leveraged_shares = (initial_total * lev_w0) / leveraged_close.loc[sim_dates[0]]
    stable_cost_basis = stable_close.loc[sim_dates[0]]
    leveraged_cost_basis = leveraged_close.loc[sim_dates[0]]

    portfolio_values = []
    trade_log = []
    current_target_lev_w = None
    pending_rebalance = None
    total_tax_paid = 0.0
    total_cost_paid = 0.0

    for i, date in enumerate(sim_dates):
        stable_open_price = stable_open.loc[date]
        lev_open_price = leveraged_open.loc[date]
        stable_close_price = stable_close.loc[date]
        lev_close_price = leveraged_close.loc[date]

        if pending_rebalance is not None:
            label, target_stable_w, target_lev_w = pending_rebalance
            total_value = stable_shares * stable_open_price + leveraged_shares * lev_open_price
            target_stable_value = total_value * target_stable_w
            target_lev_value = total_value * target_lev_w
            current_stable_value = stable_shares * stable_open_price
            current_lev_value = leveraged_shares * lev_open_price

            tax_owed = 0.0
            cost_owed = 0.0
            if target_stable_value < current_stable_value:
                sell_value = current_stable_value - target_stable_value
                shares_sold = sell_value / stable_open_price
                realized_gain = (stable_open_price - stable_cost_basis) * shares_sold
                tax_owed += tax_rate * max(0.0, realized_gain)
                cost_owed += cost_pct * sell_value
            if target_lev_value < current_lev_value:
                sell_value = current_lev_value - target_lev_value
                shares_sold = sell_value / lev_open_price
                realized_gain = (lev_open_price - leveraged_cost_basis) * shares_sold
                tax_owed += tax_rate * max(0.0, realized_gain)
                cost_owed += cost_pct * sell_value

            net_total_value = total_value - tax_owed - cost_owed
            new_stable_shares = (net_total_value * target_stable_w) / stable_open_price
            new_leveraged_shares = (net_total_value * target_lev_w) / lev_open_price

            if new_stable_shares > stable_shares:
                shares_bought = new_stable_shares - stable_shares
                new_total_cost = stable_cost_basis * stable_shares + stable_open_price * shares_bought
                stable_cost_basis = new_total_cost / new_stable_shares if new_stable_shares > 0 else stable_open_price
            if new_leveraged_shares > leveraged_shares:
                shares_bought = new_leveraged_shares - leveraged_shares
                new_total_cost = leveraged_cost_basis * leveraged_shares + lev_open_price * shares_bought
                leveraged_cost_basis = new_total_cost / new_leveraged_shares if new_leveraged_shares > 0 else lev_open_price

            stable_shares = new_stable_shares
            leveraged_shares = new_leveraged_shares
            total_tax_paid += tax_owed
            total_cost_paid += cost_owed
            trade_log.append({
                "date": date, "label": label,
                "target_stable_w": target_stable_w, "target_lev_w": target_lev_w,
                "tax_paid": tax_owed, "cost_paid": cost_owed,
            })
            pending_rebalance = None

        if i % rebalance_check_days == 0:
            trend = classify_trend(stable_close, date, trend_lookback_days)
            mean_ret, var_ret = compute_trailing_mean_and_variance(leveraged_close, date, kelly_lookback_days)

            if trend is None or mean_ret is None:
                label = "warming_up"
                target_stable_w, target_lev_w = fallback_weights
            elif trend == "downtrend":
                label = "downtrend_defensive"
                target_stable_w, target_lev_w = 1.0, 0.0
            else:
                target_lev_w = compute_kelly_leveraged_weight(mean_ret, var_ret, kelly_fraction, max_leveraged_weight)
                accel_note = ""
                if use_trend_acceleration:
                    multiplier = compute_trend_acceleration_multiplier(
                        stable_close, date, trend_acceleration_medium_days, trend_acceleration_slope_days
                    )
                    target_lev_w = min(max_leveraged_weight, target_lev_w * multiplier)
                    accel_note = f",accel_mult={multiplier}"
                target_stable_w = 1.0 - target_lev_w
                label = f"uptrend_kelly(mean={mean_ret:.5f},var={var_ret:.6f}{accel_note})"

            total_value = stable_shares * stable_close_price + leveraged_shares * lev_close_price
            current_lev_w = (leveraged_shares * lev_close_price) / total_value if total_value else 0.0
            drift_pct = abs(current_lev_w - target_lev_w) * 100

            should_rebalance = current_target_lev_w is None or drift_pct > band_pct
            if should_rebalance and one_way_ratchet and target_lev_w > current_lev_w:
                should_rebalance = False  # ratchet: never buy UP into the leveraged leg

            if should_rebalance:
                pending_rebalance = (label, target_stable_w, target_lev_w)
            current_target_lev_w = target_lev_w

        portfolio_values.append(stable_shares * stable_close_price + leveraged_shares * lev_close_price)

    series = pd.Series(portfolio_values, index=sim_dates)
    return {
        "series": series,
        "final_value": float(series.iloc[-1]),
        "total_return_pct": float((series.iloc[-1] / series.iloc[0] - 1) * 100),
        "n_trades": len(trade_log),
        "trade_log": trade_log,
        "total_tax_paid": total_tax_paid,
        "total_cost_paid": total_cost_paid,
    }


def grid_search_kelly(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    kelly_fraction_options: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
    max_leveraged_weight_options: tuple[float, ...] = (0.6, 0.8, 1.0),
    **simulate_kwargs,
) -> pd.DataFrame:
    """Grid-searches (kelly_fraction, max_leveraged_weight), scored by
    Calmar ratio. Caller is responsible for only passing DISCOVERY-period
    price series."""
    require_aligned_price_series(
        {
            "stable_close": stable_close,
            "leveraged_close": leveraged_close,
            "stable_open": stable_open,
            "leveraged_open": leveraged_open,
        }
    )
    if not kelly_fraction_options or not max_leveraged_weight_options:
        raise ValueError("kelly_fraction_options and max_leveraged_weight_options must be non-empty")
    kelly_fraction_options = tuple(
        require_finite_number(
            value,
            name="kelly_fraction_options item",
            minimum=0.0,
            maximum=1.0,
        )
        for value in kelly_fraction_options
    )
    max_leveraged_weight_options = tuple(
        require_finite_number(
            value,
            name="max_leveraged_weight_options item",
            minimum=0.0,
            maximum=1.0,
        )
        for value in max_leveraged_weight_options
    )
    rows = []
    for kelly_fraction in kelly_fraction_options:
        for max_weight in max_leveraged_weight_options:
            result = simulate_kelly_rotation(
                stable_close, leveraged_close, stable_open, leveraged_open,
                kelly_fraction=kelly_fraction, max_leveraged_weight=max_weight, **simulate_kwargs,
            )
            series = result["series"]
            dd = max_drawdown_pct(series)
            cagr = cagr_pct(series)
            calmar = cagr / abs(dd) if dd != 0 else float("nan")
            rows.append({
                "kelly_fraction": kelly_fraction, "max_leveraged_weight": max_weight,
                "n_trades": result["n_trades"], "cagr_pct": round(cagr, 2),
                "max_drawdown_pct": round(dd, 1), "calmar_ratio": round(calmar, 3),
                "total_tax_paid": round(result["total_tax_paid"], 0),
                "total_cost_paid": round(result["total_cost_paid"], 0),
            })
    return pd.DataFrame(rows).sort_values("calmar_ratio", ascending=False).reset_index(drop=True)
