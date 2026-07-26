"""
Leverage rotation strategy.

Rebalances between an unleveraged ETF ("stable") and its leveraged
same-index counterpart ("leveraged", e.g. TQQQ vs. QQQ/QQQM) based on the
leveraged fund's own daily % move — which is just the underlying index's
move amplified, so it's a clean proxy for "the market moved."

Rule: when the leveraged fund's day-over-day move exceeds +threshold_pct,
trim a fixed dollar amount off the leveraged position and buy the same
into stable (bank the amplified gain). When it drops below -threshold_pct,
sell the fixed amount from stable and buy the beaten-down leveraged fund
(re-lever after the amplified drop). Trades are capped at whatever's
actually held — never goes negative.

This is a mechanical, rules-based version of a strategy the user
previously ran by feel/mood. It does NOT model transaction costs or
taxes (frequent trims would realize capital gains, often short-term, in
a real taxable account) — treat all results here as pre-tax, pre-cost.
"""
from __future__ import annotations

import pandas as pd


def simulate_leverage_rotation(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    initial_stable: float = 5000.0,
    initial_leveraged: float = 5000.0,
    threshold_pct: float = 2.0,
    trade_size: float = 500.0,
) -> dict:
    """Simulate the rotation rule day by day. Returns a dict with the daily
    portfolio value series, final value, total return, number of trades,
    and the trade log."""
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    stable_close = stable_close.reindex(dates)
    leveraged_close = leveraged_close.reindex(dates)

    stable_shares = initial_stable / stable_close.iloc[0]
    leveraged_shares = initial_leveraged / leveraged_close.iloc[0]

    portfolio_values = []
    trade_log = []
    prev_lev_price = leveraged_close.iloc[0]

    for i, date in enumerate(dates):
        lev_price = leveraged_close.loc[date]
        stable_price = stable_close.loc[date]

        if i > 0:
            daily_move_pct = (lev_price / prev_lev_price - 1) * 100
            if daily_move_pct > threshold_pct:
                sell_value = min(trade_size, leveraged_shares * lev_price)
                leveraged_shares -= sell_value / lev_price
                stable_shares += sell_value / stable_price
                trade_log.append({"date": date, "action": "trim_leveraged", "value": sell_value})
            elif daily_move_pct < -threshold_pct:
                sell_value = min(trade_size, stable_shares * stable_price)
                stable_shares -= sell_value / stable_price
                leveraged_shares += sell_value / lev_price
                trade_log.append({"date": date, "action": "buy_leveraged_dip", "value": sell_value})

        portfolio_values.append(stable_shares * stable_price + leveraged_shares * lev_price)
        prev_lev_price = lev_price

    series = pd.Series(portfolio_values, index=dates)
    return {
        "series": series,
        "final_value": float(series.iloc[-1]),
        "total_return_pct": float((series.iloc[-1] / series.iloc[0] - 1) * 100),
        "n_trades": len(trade_log),
        "trade_log": trade_log,
        "max_drawdown_pct": max_drawdown_pct(series),
    }


def buy_and_hold(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_weight: float,
    leveraged_weight: float,
    initial_total: float = 10_000.0,
) -> dict:
    """Static baseline: buy once at the given weights, never rebalance."""
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    stable_close = stable_close.reindex(dates)
    leveraged_close = leveraged_close.reindex(dates)

    stable_shares = (initial_total * stable_weight) / stable_close.iloc[0]
    leveraged_shares = (initial_total * leveraged_weight) / leveraged_close.iloc[0]

    series = stable_shares * stable_close + leveraged_shares * leveraged_close
    return {
        "series": series,
        "final_value": float(series.iloc[-1]),
        "total_return_pct": float((series.iloc[-1] / series.iloc[0] - 1) * 100),
        "max_drawdown_pct": max_drawdown_pct(series),
    }


def max_drawdown_pct(series: pd.Series) -> float:
    running_max = series.cummax()
    drawdown = (series - running_max) / running_max
    return float(drawdown.min() * 100)


def cagr_pct(series: pd.Series, trading_days_per_year: int = 252) -> float:
    years = len(series) / trading_days_per_year
    if years <= 0 or series.iloc[0] <= 0:
        return 0.0
    return float(((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1) * 100)
