"""
Backtests the leverage-rotation strategy (rebalance between QQQ/QQQM and
TQQQ based on daily move size) against real historical data.

Uses QQQ itself as the "stable" leg. QQQM (the fund the user actually
trades) only launched Oct 2020, but it tracks the identical Nasdaq-100
index as QQQ, just with a lower expense ratio (~0.15% vs ~0.20%/yr) — an
immaterial difference for a strategy backtest, and using QQQ instead lets
the test reach back to TQQQ's own 2010 inception instead of being capped
at ~5 years of data.

Same discovery/confirmation discipline as the rest of this project: grid
search over (threshold_pct, trade_size) on the discovery period only, pick
the best combo there, then report that SAME combo's result on the
confirmation period the grid search never saw — instead of cherry-picking
whatever performed best on the full history.

Caveats printed at the end: this does not model transaction costs or
taxes (frequent trims realize gains, often short-term, in a taxable
account), and — unlike the discrete dip/up signals elsewhere in this repo —
there's no p-value here to "pass." What matters for a rebalancing strategy
like this is the return/drawdown trade-off vs. simply holding, not a
statistical significance test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.leverage_rotation import (
    buy_and_hold,
    cagr_pct,
    max_drawdown_pct,
    simulate_leverage_rotation,
)

STABLE_TICKER = "QQQ"     # proxy for QQQM — see module docstring
LEVERAGED_TICKER = "TQQQ"
LOOKBACK_DAYS = 4200       # ~16.7 years, back to near TQQQ's 2010 inception
DISCOVERY_FRAC = 0.6

THRESHOLD_GRID = [1.0, 2.0, 3.0]
TRADE_SIZE_GRID = [250.0, 500.0, 1000.0]


def _split(*series: pd.Series, frac: float):
    dates = series[0].index
    for s in series[1:]:
        dates = dates.intersection(s.index)
    dates = dates.sort_values()
    split_idx = int(len(dates) * frac)
    split_date = dates[split_idx]
    discovery_dates = dates[dates < split_date]
    confirmation_dates = dates[dates >= split_date]
    return tuple(s.reindex(discovery_dates) for s in series) + tuple(s.reindex(confirmation_dates) for s in series)


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    if STABLE_TICKER not in data or LEVERAGED_TICKER not in data:
        print("Failed to fetch data for one or both tickers.")
        return

    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    print(f"Got {len(stable_close)} days of {STABLE_TICKER}, {len(leveraged_close)} days of {LEVERAGED_TICKER}.\n")

    (stable_close_disc, leveraged_close_disc, stable_open_disc, leveraged_open_disc,
     stable_close_conf, leveraged_close_conf, stable_open_conf, leveraged_open_conf) = _split(
        stable_close, leveraged_close, stable_open, leveraged_open, frac=DISCOVERY_FRAC,
    )
    print(f"Discovery period:    {stable_close_disc.index[0].date()} to {stable_close_disc.index[-1].date()} ({len(stable_close_disc)} days)")
    print(f"Confirmation period: {stable_close_conf.index[0].date()} to {stable_close_conf.index[-1].date()} ({len(stable_close_conf)} days)\n")

    print("=== Grid search on DISCOVERY period only ===")
    rows = []
    for threshold in THRESHOLD_GRID:
        for trade_size in TRADE_SIZE_GRID:
            result = simulate_leverage_rotation(
                stable_close_disc, leveraged_close_disc, stable_open_disc, leveraged_open_disc,
                threshold_pct=threshold, trade_size=trade_size,
            )
            calmar = (
                cagr_pct(result["series"]) / abs(result["max_drawdown_pct"])
                if result["max_drawdown_pct"] != 0 else float("nan")
            )
            rows.append({
                "threshold_pct": threshold, "trade_size": trade_size,
                "n_trades": result["n_trades"],
                "total_return_pct": round(result["total_return_pct"], 1),
                "cagr_pct": round(cagr_pct(result["series"]), 2),
                "max_drawdown_pct": round(result["max_drawdown_pct"], 1),
                "calmar_ratio": round(calmar, 3),
            })
    grid_df = pd.DataFrame(rows).sort_values("calmar_ratio", ascending=False)
    print(grid_df.to_string(index=False))

    best = grid_df.iloc[0]
    best_threshold, best_trade_size = best["threshold_pct"], best["trade_size"]
    print(f"\nBest by Calmar ratio (CAGR / |max drawdown|) on discovery: "
          f"threshold={best_threshold}%, trade_size=${best_trade_size:.0f}\n")

    print("=== Applying that SAME combo to the CONFIRMATION period (never used to pick it) ===")
    strategy_conf = simulate_leverage_rotation(
        stable_close_conf, leveraged_close_conf, stable_open_conf, leveraged_open_conf,
        threshold_pct=best_threshold, trade_size=best_trade_size,
    )
    baseline_5050 = buy_and_hold(stable_close_conf, leveraged_close_conf, 0.5, 0.5)
    baseline_stable = buy_and_hold(stable_close_conf, leveraged_close_conf, 1.0, 0.0)
    baseline_leveraged = buy_and_hold(stable_close_conf, leveraged_close_conf, 0.0, 1.0)

    comparison = pd.DataFrame([
        {"strategy": f"rotation ({best_threshold}%/${best_trade_size:.0f})",
         "n_trades": strategy_conf["n_trades"],
         "total_return_pct": round(strategy_conf["total_return_pct"], 1),
         "cagr_pct": round(cagr_pct(strategy_conf["series"]), 2),
         "max_drawdown_pct": round(strategy_conf["max_drawdown_pct"], 1)},
        {"strategy": "buy & hold 50/50 (no rebalance)", "n_trades": 0,
         "total_return_pct": round(baseline_5050["total_return_pct"], 1),
         "cagr_pct": round(cagr_pct(baseline_5050["series"]), 2),
         "max_drawdown_pct": round(baseline_5050["max_drawdown_pct"], 1)},
        {"strategy": f"buy & hold 100% {STABLE_TICKER}", "n_trades": 0,
         "total_return_pct": round(baseline_stable["total_return_pct"], 1),
         "cagr_pct": round(cagr_pct(baseline_stable["series"]), 2),
         "max_drawdown_pct": round(baseline_stable["max_drawdown_pct"], 1)},
        {"strategy": f"buy & hold 100% {LEVERAGED_TICKER}", "n_trades": 0,
         "total_return_pct": round(baseline_leveraged["total_return_pct"], 1),
         "cagr_pct": round(cagr_pct(baseline_leveraged["series"]), 2),
         "max_drawdown_pct": round(baseline_leveraged["max_drawdown_pct"], 1)},
    ])
    print(comparison.to_string(index=False))

    print(
        "\nCaveats: no transaction costs or taxes modeled (real trims realize "
        "gains, often short-term, in a taxable account). QQQ stands in for "
        "QQQM before QQQM's Oct-2020 inception (same index, near-identical "
        "return). This is a return/drawdown comparison, not a significance "
        "test — there's no p-value to pass here, judge it on whether the "
        "confirmation-period drawdown is something you could actually sit "
        "through."
    )


if __name__ == "__main__":
    main()
