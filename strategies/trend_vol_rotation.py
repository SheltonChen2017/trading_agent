"""
Trend + volatility regime overlay for the QQQ/TQQQ rotation idea.

The fixed-threshold version (leverage_rotation.py) trades on every daily
wiggle and back-tested worse than simply buying and holding 50/50 (see
README/memory) — mostly because trimming the leveraged fund on every 2%
pop caps upside during trends, while re-buying it on every 2% drop keeps
catching a falling knife during declines, all while racking up trades
(and, in a real account, taxes).

This instead classifies the market into one of four states using two
independent, purely backward-looking signals, checked on a schedule
(e.g. monthly) rather than daily:

  - trend: is the underlying above or below its own trailing N-day moving
    average? Leveraged ETFs compound well in sustained trends and get
    chewed up by daily-rebalancing decay in choppy/declining markets —
    this is the well-documented reason "leveraged ETF + trend filter" is
    a real strategy family, not just a arbitrary heuristic.
  - volatility regime: is trailing realized volatility above or below a
    threshold calibrated from DISCOVERY-period data only (reuses
    signals/regime.py, built for exactly this purpose, so confirmation
    stays honestly out-of-sample).

Each state maps to a target QQQ/TQQQ weight split (more leveraged
exposure in the "goldilocks" uptrend+low_vol state, fully defensive in
any downtrend state). Rebalancing only happens on the schedule and only
if actual weights have drifted from target beyond a band, to keep
turnover low.

Classification and rebalance EXECUTION are deliberately on different
days: the trend/vol state on a check date needs that date's own
completed close, so the rebalance trade executes at the FOLLOWING
trading day's open, not the check date's own close (you can't
retroactively trade at a close you needed to complete in order to
classify the regime — flagged by independent code review, 2026-07, after
the original same-close version shipped). A rebalance decided on the
LAST available date has no next day to execute on and is dropped,
matching the real constraint.
"""
from __future__ import annotations

import pandas as pd

from strategies.leverage_rotation import cagr_pct, max_drawdown_pct
from signals.regime import classify_regime, compute_trailing_market_volatility  # noqa: F401 (re-exported for callers)


def classify_trend(close: pd.Series, as_of: pd.Timestamp, lookback_days: int = 200) -> str | None:
    """"uptrend" if `close` at `as_of` is at/above its own trailing
    `lookback_days` moving average, else "downtrend". None if there isn't
    enough trailing history yet."""
    if as_of not in close.index:
        return None
    idx = close.index.get_loc(as_of)
    if idx < lookback_days - 1:
        return None
    window = close.iloc[idx - lookback_days + 1 : idx + 1]
    sma = window.mean()
    return "uptrend" if close.loc[as_of] >= sma else "downtrend"


DEFAULT_STATE_WEIGHTS: dict[str, tuple[float, float]] = {
    # (stable_weight, leveraged_weight) — must sum to 1.0
    "uptrend_low_vol": (0.3, 0.7),     # the goldilocks zone for leverage
    "uptrend_high_vol": (0.6, 0.4),    # trend's still good, but chop raises decay risk
    "downtrend_low_vol": (1.0, 0.0),   # defensive regardless of vol once trend breaks
    "downtrend_high_vol": (1.0, 0.0),
}


def simulate_regime_rotation(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    vol_threshold_pct: float,
    state_weights: dict[str, tuple[float, float]] | None = None,
    trend_lookback_days: int = 200,
    vol_lookback_days: int = 60,
    rebalance_check_days: int = 21,
    band_pct: float = 5.0,
    initial_total: float = 10_000.0,
    fallback_weights: tuple[float, float] = (0.5, 0.5),
    start_date: pd.Timestamp | None = None,
    cost_pct: float = 0.0,
    tax_rate: float = 0.0,
) -> dict:
    """
    Simulate the trend+volatility-regime allocation. `stable_close` and
    `leveraged_close` may span MORE history than the period you want
    simulated (pass `start_date` to start trading/tracking partway
    through) — earlier rows are still used for trend/volatility lookback,
    so classification isn't starved of history right at the start of a
    confirmation period.

    Rebalance decisions are classified using each check date's own CLOSE;
    execution happens at the FOLLOWING trading day's open (see module
    docstring). The portfolio value series is marked to market at each
    day's CLOSE throughout, net of any tax/cost already paid.

    Optionally models transaction costs and taxes: `cost_pct` (bid-ask
    spread/commission, as a fraction of the dollar value of whichever leg
    is trimmed at each rebalance) and `tax_rate` (applied to REALIZED
    gains only on the trimmed leg, via a running average cost basis —
    every gain treated as short-term/ordinary-income, no benefit assumed
    for losses; both conservative simplifications). Both default to 0.0
    for backward compatibility.
    """
    state_weights = state_weights or DEFAULT_STATE_WEIGHTS
    all_dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    stable_close = stable_close.reindex(all_dates)
    leveraged_close = leveraged_close.reindex(all_dates)
    stable_open = stable_open.reindex(all_dates)
    leveraged_open = leveraged_open.reindex(all_dates)
    benchmark_df = pd.DataFrame({"close": stable_close})

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
    current_state = None
    pending_rebalance = None  # (state, target_stable_w, target_lev_w) decided on the prior check day
    total_tax_paid = 0.0
    total_cost_paid = 0.0

    for i, date in enumerate(sim_dates):
        stable_open_price = stable_open.loc[date]
        lev_open_price = leveraged_open.loc[date]
        stable_close_price = stable_close.loc[date]
        lev_close_price = leveraged_close.loc[date]

        if pending_rebalance is not None:
            state, target_stable_w, target_lev_w = pending_rebalance
            total_value = stable_shares * stable_open_price + leveraged_shares * lev_open_price
            target_stable_value = total_value * target_stable_w
            target_lev_value = total_value * target_lev_w
            current_stable_value = stable_shares * stable_open_price
            current_lev_value = leveraged_shares * lev_open_price

            tax_owed = 0.0
            cost_owed = 0.0
            if target_stable_value < current_stable_value:  # trimming stable
                sell_value = current_stable_value - target_stable_value
                shares_sold = sell_value / stable_open_price
                realized_gain = (stable_open_price - stable_cost_basis) * shares_sold
                tax_owed += tax_rate * max(0.0, realized_gain)
                cost_owed += cost_pct * sell_value
            if target_lev_value < current_lev_value:  # trimming leveraged
                sell_value = current_lev_value - target_lev_value
                shares_sold = sell_value / lev_open_price
                realized_gain = (lev_open_price - leveraged_cost_basis) * shares_sold
                tax_owed += tax_rate * max(0.0, realized_gain)
                cost_owed += cost_pct * sell_value

            net_total_value = total_value - tax_owed - cost_owed
            new_stable_shares = (net_total_value * target_stable_w) / stable_open_price
            new_leveraged_shares = (net_total_value * target_lev_w) / lev_open_price

            if new_stable_shares > stable_shares:  # topping up stable -> update its cost basis
                shares_bought = new_stable_shares - stable_shares
                new_total_cost = stable_cost_basis * stable_shares + stable_open_price * shares_bought
                stable_cost_basis = new_total_cost / new_stable_shares if new_stable_shares > 0 else stable_open_price
            if new_leveraged_shares > leveraged_shares:  # topping up leveraged -> update its cost basis
                shares_bought = new_leveraged_shares - leveraged_shares
                new_total_cost = leveraged_cost_basis * leveraged_shares + lev_open_price * shares_bought
                leveraged_cost_basis = new_total_cost / new_leveraged_shares if new_leveraged_shares > 0 else lev_open_price

            stable_shares = new_stable_shares
            leveraged_shares = new_leveraged_shares
            total_tax_paid += tax_owed
            total_cost_paid += cost_owed
            trade_log.append({
                "date": date, "state": state,
                "target_stable_w": target_stable_w, "target_lev_w": target_lev_w,
                "tax_paid": tax_owed, "cost_paid": cost_owed,
            })
            pending_rebalance = None

        if i % rebalance_check_days == 0:
            trend = classify_trend(stable_close, date, trend_lookback_days)
            vol_regime = classify_regime(benchmark_df, date, vol_threshold_pct, vol_lookback_days)

            if trend is None or vol_regime is None:
                state = "warming_up"
                target_stable_w, target_lev_w = fallback_weights
            else:
                state = f"{trend}_{vol_regime}"
                target_stable_w, target_lev_w = state_weights.get(state, fallback_weights)

            total_value = stable_shares * stable_close_price + leveraged_shares * lev_close_price
            current_lev_w = (leveraged_shares * lev_close_price) / total_value if total_value else 0.0
            drift_pct = abs(current_lev_w - target_lev_w) * 100

            if state != current_state or drift_pct > band_pct:
                pending_rebalance = (state, target_stable_w, target_lev_w)
            current_state = state

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


def build_state_weights(low_vol_lev_weight: float, high_vol_lev_weight: float) -> dict[str, tuple[float, float]]:
    """State-weight table with both downtrend states fully defensive
    (0% leveraged) — only the two uptrend states' leveraged aggressiveness
    is parameterized, since defensive-on-downtrend is what delivers the
    drawdown protection (see strategies/trend_vol_rotation.py findings in
    memory)."""
    return {
        "uptrend_low_vol": (1 - low_vol_lev_weight, low_vol_lev_weight),
        "uptrend_high_vol": (1 - high_vol_lev_weight, high_vol_lev_weight),
        "downtrend_low_vol": (1.0, 0.0),
        "downtrend_high_vol": (1.0, 0.0),
    }


def grid_search_state_weights(
    stable_close: pd.Series,
    leveraged_close: pd.Series,
    stable_open: pd.Series,
    leveraged_open: pd.Series,
    vol_threshold_pct: float,
    low_vol_weights: tuple[float, ...] = (0.5, 0.7, 0.85, 1.0),
    high_vol_weights: tuple[float, ...] = (0.2, 0.4, 0.6),
    **simulate_kwargs,
) -> pd.DataFrame:
    """
    Runs simulate_regime_rotation() over every coherent
    (low_vol_lev_weight, high_vol_lev_weight) combo (skipping combos more
    aggressive in the choppier state than the calm one), scored by Calmar
    ratio (CAGR / |max drawdown|). Caller is responsible for only passing
    DISCOVERY-period price series here — this function doesn't split data
    itself, to keep the discovery/confirmation discipline explicit at the
    call site.
    """
    rows = []
    for low in low_vol_weights:
        for high in high_vol_weights:
            if high > low:
                continue
            state_weights = build_state_weights(low, high)
            result = simulate_regime_rotation(
                stable_close, leveraged_close, stable_open, leveraged_open, vol_threshold_pct=vol_threshold_pct,
                state_weights=state_weights, **simulate_kwargs,
            )
            series = result["series"]
            dd = max_drawdown_pct(series)
            cagr = cagr_pct(series)
            calmar = cagr / abs(dd) if dd != 0 else float("nan")
            rows.append({
                "low_vol_lev_weight": low, "high_vol_lev_weight": high,
                "n_trades": result["n_trades"], "cagr_pct": round(cagr, 2),
                "max_drawdown_pct": round(dd, 1), "calmar_ratio": round(calmar, 3),
            })
    return pd.DataFrame(rows).sort_values("calmar_ratio", ascending=False).reset_index(drop=True)
