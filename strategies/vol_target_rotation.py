"""
Volatility-targeted continuous rotation between an unleveraged index ETF
("stable") and a leveraged same-index fund ("leveraged", e.g. QQQ/TQQQ
or QQQ/QLD).

Genuinely different mechanism than strategies/trend_vol_rotation.py's
DISCRETE 4-bucket regime design (uptrend/downtrend x low/high-vol, each
with a fixed weight) — that design worked for SOXX/SOXL but mostly
failed for QQQ/TQQQ even after its look-ahead bug was fixed (see memory:
project_leverage_rotation_strategy). Here, leveraged exposure is a
CONTINUOUS function of trailing realized volatility instead of jumping
between a few fixed buckets:

    target_leveraged_weight = clip(target_vol_pct / realized_vol_pct, 0, max_leveraged_weight)

This is the same principle real volatility-targeting / risk-parity
strategies use to manage leveraged-instrument decay: decay from daily
rebalancing scales with variance, so holding realized volatility roughly
constant caps how much decay exposure you take on, rather than reacting
to a handful of discrete regime buckets that can whipsaw right at a
boundary.

The one piece of the earlier design that held up under every check run
(walk-forward, sensitivity, tax) is kept as-is: a confirmed DOWNTREND
fully zeroes leveraged exposure, regardless of volatility.

Execution discipline, correct from the start (learned the hard way in
the discrete-bucket version — see memory): decisions use each check
date's own CLOSE; the rebalance trade executes at the FOLLOWING trading
day's OPEN. Tax/cost modeling (running average cost basis, taxing
realized gains on the trimmed leg only, no benefit for losses) is built
in from day one, not bolted on after finding out it mattered.
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
from signals.regime import compute_trailing_market_volatility

TRADING_DAYS_PER_YEAR = 252


def compute_target_leveraged_weight(
    realized_vol_pct: float | None,
    target_vol_pct: float,
    max_leveraged_weight: float,
) -> float:
    """`realized_vol_pct` is trailing DAILY realized volatility (%, not
    annualized) of the leveraged fund. Returns 0.0 if realized_vol_pct is
    None, NaN, zero, or negative (can't size against unknown/zero
    volatility).

    The NaN case is checked explicitly rather than left to `<= 0`
    (independent review, 2026-07-29, reproduced): NaN defeats every
    ordered comparison, so it passed the guard, and
    `min(max_leveraged_weight, target/NaN)` then returns
    `max_leveraged_weight` -- unknown volatility produced the MAXIMUM
    leveraged weight, the exact opposite of this function's purpose and of
    what its own docstring promised. `None` and `inf` already returned 0.0
    correctly; only NaN failed, and it failed toward more leverage."""
    target_vol_pct = require_positive_number(target_vol_pct, name="target_vol_pct")
    max_leveraged_weight = require_finite_number(
        max_leveraged_weight,
        name="max_leveraged_weight",
        minimum=0.0,
        maximum=1.0,
    )
    if (
        realized_vol_pct is None
        or isinstance(realized_vol_pct, bool)
        or not isinstance(realized_vol_pct, Real)
        or not math.isfinite(float(realized_vol_pct))
        or realized_vol_pct <= 0
    ):
        return 0.0
    return max(0.0, min(max_leveraged_weight, target_vol_pct / realized_vol_pct))


def simulate_vol_target_rotation(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    target_vol_pct: float,
    max_leveraged_weight: float = 1.0,
    trend_lookback_days: int = 200,
    vol_lookback_days: int = 20,
    rebalance_check_days: int = 21,
    band_pct: float = 5.0,
    initial_total: float = 10_000.0,
    fallback_weights: tuple[float, float] = (0.5, 0.5),
    start_date: pd.Timestamp | None = None,
    cost_pct: float = 0.0,
    tax_rate: float = 0.0,
) -> dict:
    """
    `target_vol_pct` is the trailing DAILY realized volatility (%) of the
    leveraged fund you're comfortable targeting — e.g. 1.5 means "size the
    leveraged position so its recent daily vol contribution behaves like
    a fund with ~1.5% daily vol," smaller than TQQQ's own unconstrained
    (~3-5%+) daily vol in choppy periods, so exposure shrinks
    automatically when volatility rises and grows when it's calm.

    Same discovery/confirmation, next-day-open execution, and tax/cost
    conventions as strategies/trend_vol_rotation.py — see its module
    docstring for the general mechanics this shares (pending-rebalance
    pattern, running average cost basis, band-based turnover control).
    """
    require_aligned_price_series(
        {
            "stable_close": stable_close,
            "leveraged_close": leveraged_close,
            "stable_open": stable_open,
            "leveraged_open": leveraged_open,
        }
    )
    target_vol_pct = require_positive_number(target_vol_pct, name="target_vol_pct")
    max_leveraged_weight = require_finite_number(
        max_leveraged_weight,
        name="max_leveraged_weight",
        minimum=0.0,
        maximum=1.0,
    )
    trend_lookback_days = require_positive_int(trend_lookback_days, name="trend_lookback_days")
    vol_lookback_days = require_positive_int(vol_lookback_days, name="vol_lookback_days")
    rebalance_check_days = require_positive_int(rebalance_check_days, name="rebalance_check_days")
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
    leveraged_benchmark_df = pd.DataFrame({"close": leveraged_close})

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
    pending_rebalance = None  # (label, target_stable_w, target_lev_w) decided on the prior check day
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
            realized_vol = compute_trailing_market_volatility(leveraged_benchmark_df, date, vol_lookback_days)

            if trend is None or realized_vol is None:
                label = "warming_up"
                target_stable_w, target_lev_w = fallback_weights
            elif trend == "downtrend":
                label = "downtrend_defensive"
                target_stable_w, target_lev_w = 1.0, 0.0
            else:
                target_lev_w = compute_target_leveraged_weight(realized_vol, target_vol_pct, max_leveraged_weight)
                target_stable_w = 1.0 - target_lev_w
                label = f"uptrend_vol_target(realized={realized_vol:.2f}%)"

            total_value = stable_shares * stable_close_price + leveraged_shares * lev_close_price
            current_lev_w = (leveraged_shares * lev_close_price) / total_value if total_value else 0.0
            drift_pct = abs(current_lev_w - target_lev_w) * 100

            if current_target_lev_w is None or drift_pct > band_pct:
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


def grid_search_vol_target(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    target_vol_options: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 2.5),
    max_leveraged_weight_options: tuple[float, ...] = (0.6, 0.8, 1.0),
    **simulate_kwargs,
) -> pd.DataFrame:
    """Grid-searches (target_vol_pct, max_leveraged_weight) combos,
    scored by Calmar ratio (CAGR / |max drawdown|). Caller is responsible
    for only passing DISCOVERY-period price series."""
    require_aligned_price_series(
        {
            "stable_close": stable_close,
            "leveraged_close": leveraged_close,
            "stable_open": stable_open,
            "leveraged_open": leveraged_open,
        }
    )
    if not target_vol_options or not max_leveraged_weight_options:
        raise ValueError("target_vol_options and max_leveraged_weight_options must be non-empty")
    target_vol_options = tuple(
        require_positive_number(value, name="target_vol_options item")
        for value in target_vol_options
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
    for target_vol in target_vol_options:
        for max_weight in max_leveraged_weight_options:
            result = simulate_vol_target_rotation(
                stable_close, leveraged_close, stable_open, leveraged_open,
                target_vol_pct=target_vol, max_leveraged_weight=max_weight, **simulate_kwargs,
            )
            series = result["series"]
            dd = max_drawdown_pct(series)
            cagr = cagr_pct(series)
            calmar = cagr / abs(dd) if dd != 0 else float("nan")
            rows.append({
                "target_vol_pct": target_vol, "max_leveraged_weight": max_weight,
                "n_trades": result["n_trades"], "cagr_pct": round(cagr, 2),
                "max_drawdown_pct": round(dd, 1), "calmar_ratio": round(calmar, 3),
                "total_tax_paid": round(result["total_tax_paid"], 0),
                "total_cost_paid": round(result["total_cost_paid"], 0),
            })
    return pd.DataFrame(rows).sort_values("calmar_ratio", ascending=False).reset_index(drop=True)
