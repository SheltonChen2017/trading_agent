"""
Leverage rotation strategy.

Rebalances between an unleveraged ETF ("stable") and its leveraged
same-index counterpart ("leveraged", e.g. TQQQ vs. QQQ/QQQM) based on the
leveraged fund's own daily % move — which is just the underlying index's
move amplified, so it's a clean proxy for "the market moved."

Rule: when the leveraged fund's day-over-day CLOSE-TO-CLOSE move exceeds
+threshold_pct, trim a fixed dollar amount off the leveraged position and
buy the same into stable (bank the amplified gain). When it drops below
-threshold_pct, sell the fixed amount from stable and buy the beaten-down
leveraged fund (re-lever after the amplified drop). Trades are capped at
whatever's actually held — never goes negative.

Decision and execution are DELIBERATELY on different days: the move is
only fully known once day t's close prints, so the trade executes at day
t+1's open, not day t's own close (you can't retroactively trade at a
close you needed to complete in order to make the decision — flagged by
independent code review, 2026-07, after the original same-close version
shipped). A trade decided on the LAST available date has no next day to
execute on and is simply dropped, matching the real constraint.

Optionally models transaction costs and taxes: `cost_pct` (bid-ask
spread/commission, as a fraction of each trade's dollar value) and
`tax_rate` (applied to REALIZED gains only, using a running average cost
basis per leg — no benefit assumed for losses, and every gain is treated
as short-term/ordinary-income, both conservative simplifications). Both
default to 0.0 (pre-tax, pre-cost) for backward compatibility — pass
nonzero values to see the after-tax, after-cost picture. `buy_and_hold()`
never sells after the initial purchase, so it has no realized-gain tax
exposure at all — a real tax advantage of not rebalancing, worth keeping
in mind when comparing to it.
"""
from __future__ import annotations

import pandas as pd


def simulate_leverage_rotation(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    initial_stable: float = 5000.0,
    initial_leveraged: float = 5000.0,
    threshold_pct: float = 2.0,
    trade_size: float = 500.0,
    cost_pct: float = 0.0,
    tax_rate: float = 0.0,
) -> dict:
    """Simulate the rotation rule day by day. Decisions use CLOSE-to-close
    moves; trades execute at the FOLLOWING day's open (see module
    docstring). Returns a dict with the daily portfolio value series
    (marked to market at each day's close, net of any tax/cost already
    paid), final value, total return, number of trades, the trade log,
    and cumulative tax/cost paid."""
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    stable_close = stable_close.reindex(dates)
    leveraged_close = leveraged_close.reindex(dates)
    stable_open = stable_open.reindex(dates)
    leveraged_open = leveraged_open.reindex(dates)

    stable_shares = initial_stable / stable_close.iloc[0]
    leveraged_shares = initial_leveraged / leveraged_close.iloc[0]
    stable_cost_basis = stable_close.iloc[0]
    leveraged_cost_basis = leveraged_close.iloc[0]

    portfolio_values = []
    trade_log = []
    total_tax_paid = 0.0
    total_cost_paid = 0.0
    prev_lev_close = leveraged_close.iloc[0]
    pending_action = None  # decided on the PRIOR day, executed today at today's open

    for i, date in enumerate(dates):
        stable_open_price = stable_open.loc[date]
        lev_open_price = leveraged_open.loc[date]

        if pending_action is not None:
            action = pending_action
            if action == "trim_leveraged":
                sell_value = min(trade_size, leveraged_shares * lev_open_price)
                shares_sold = sell_value / lev_open_price
                realized_gain = (lev_open_price - leveraged_cost_basis) * shares_sold
                tax_owed = tax_rate * max(0.0, realized_gain)
                cost_owed = cost_pct * sell_value
                leveraged_shares -= shares_sold

                net_proceeds = sell_value - tax_owed - cost_owed
                shares_bought = net_proceeds / stable_open_price
                new_total_cost = stable_cost_basis * stable_shares + stable_open_price * shares_bought
                stable_shares += shares_bought
                stable_cost_basis = new_total_cost / stable_shares if stable_shares > 0 else stable_open_price
            else:  # buy_leveraged_dip
                sell_value = min(trade_size, stable_shares * stable_open_price)
                shares_sold = sell_value / stable_open_price
                realized_gain = (stable_open_price - stable_cost_basis) * shares_sold
                tax_owed = tax_rate * max(0.0, realized_gain)
                cost_owed = cost_pct * sell_value
                stable_shares -= shares_sold

                net_proceeds = sell_value - tax_owed - cost_owed
                shares_bought = net_proceeds / lev_open_price
                new_total_cost = leveraged_cost_basis * leveraged_shares + lev_open_price * shares_bought
                leveraged_shares += shares_bought
                leveraged_cost_basis = new_total_cost / leveraged_shares if leveraged_shares > 0 else lev_open_price

            total_tax_paid += tax_owed
            total_cost_paid += cost_owed
            trade_log.append({
                "date": date, "action": action, "value": sell_value,
                "tax_paid": tax_owed, "cost_paid": cost_owed,
            })
            pending_action = None

        lev_close_price = leveraged_close.loc[date]
        stable_close_price = stable_close.loc[date]

        if i > 0:
            daily_move_pct = (lev_close_price / prev_lev_close - 1) * 100
            if daily_move_pct > threshold_pct:
                pending_action = "trim_leveraged"
            elif daily_move_pct < -threshold_pct:
                pending_action = "buy_leveraged_dip"

        portfolio_values.append(stable_shares * stable_close_price + leveraged_shares * lev_close_price)
        prev_lev_close = lev_close_price

    series = pd.Series(portfolio_values, index=dates)
    return {
        "series": series,
        "final_value": float(series.iloc[-1]),
        "total_return_pct": float((series.iloc[-1] / series.iloc[0] - 1) * 100),
        "n_trades": len(trade_log),
        "trade_log": trade_log,
        "max_drawdown_pct": max_drawdown_pct(series),
        "total_tax_paid": total_tax_paid,
        "total_cost_paid": total_cost_paid,
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
