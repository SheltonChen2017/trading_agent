"""
Cross-pair generalization check for the trend+volatility regime rotation
strategy. Everything so far (grid search, walk-forward, sensitivity) used
QQQ/TQQQ — if the "beats 50/50 buy-and-hold" result only shows up on that
one specific pair, that's a sign the earlier grid search curve-fit noise
in QQQ/TQQQ's particular history rather than finding a real structural
effect of leveraged-ETF decay + trend-following.

This runs the EXACT same procedure (discovery-only vol threshold
calibration, discovery-only state-weight grid search, confirm unchanged
on holdout) on SPY/UPRO (S&P 500 / 3x S&P 500) instead. UPRO inception is
2009-06-25, close to TQQQ's 2010-02-11, so the two backtests cover
similar-length, similar-era history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import calibrate_threshold_from_discovery
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.trend_vol_rotation import (
    build_state_weights,
    grid_search_state_weights,
    simulate_regime_rotation,
)

STABLE_TICKER = "SPY"
LEVERAGED_TICKER = "UPRO"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 60
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0


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
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery period:    {dates[0].date()} to {discovery_end.date()}")
    print(f"Confirmation period: {confirmation_start.date()} to {dates[-1].date()}\n")

    benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})
    vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=VOL_LOOKBACK_DAYS)

    discovery_dates = dates[dates <= discovery_end]
    discovery_stable_close = stable_close.reindex(discovery_dates)
    discovery_leveraged_close = leveraged_close.reindex(discovery_dates)
    discovery_stable_open = stable_open.reindex(discovery_dates)
    discovery_leveraged_open = leveraged_open.reindex(discovery_dates)

    print("=== Grid search on DISCOVERY period only ===")
    grid_df = grid_search_state_weights(
        discovery_stable_close, discovery_leveraged_close, discovery_stable_open, discovery_leveraged_open,
        vol_threshold_pct=vol_threshold, trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
    )
    print(grid_df.to_string(index=False))

    best = grid_df.iloc[0]
    best_weights = build_state_weights(best["low_vol_lev_weight"], best["high_vol_lev_weight"])
    print(f"\nBest by Calmar ratio on discovery: uptrend_low_vol={best['low_vol_lev_weight']:.0%}, "
          f"uptrend_high_vol={best['high_vol_lev_weight']:.0%}\n")

    print("=== Applying that SAME combo to the CONFIRMATION period ===")
    regime_result = simulate_regime_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open, vol_threshold_pct=vol_threshold,
        state_weights=best_weights, trend_lookback_days=TREND_LOOKBACK_DAYS,
        vol_lookback_days=VOL_LOOKBACK_DAYS, rebalance_check_days=REBALANCE_CHECK_DAYS,
        band_pct=BAND_PCT, start_date=confirmation_start,
    )
    regime_series = regime_result["series"]

    stable_conf = stable_close.reindex(regime_series.index)
    leveraged_conf = leveraged_close.reindex(regime_series.index)
    baseline_5050 = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)

    comparison = pd.DataFrame([
        {"strategy": f"tuned regime rotation ({best['low_vol_lev_weight']:.0%}/{best['high_vol_lev_weight']:.0%})",
         "n_trades": regime_result["n_trades"],
         "cagr_pct": round(cagr_pct(regime_series), 2),
         "max_drawdown_pct": round(max_drawdown_pct(regime_series), 1)},
        {"strategy": "buy & hold 50/50 (no rebalance)", "n_trades": 0,
         "cagr_pct": round(cagr_pct(baseline_5050["series"]), 2),
         "max_drawdown_pct": round(baseline_5050["max_drawdown_pct"], 1)},
    ])
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
