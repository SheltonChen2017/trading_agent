"""
Grid-searches the trend+volatility regime overlay's state-weight
aggressiveness on the DISCOVERY period only, picks the best by Calmar
ratio, then applies that exact combo to the confirmation period the grid
search never saw — same discipline as run_leverage_rotation_backtest.py's
threshold/trade-size search.

Downtrend states are always fully defensive (0% leveraged) in every
candidate — the earlier hand-picked-default run showed that's what
delivers the drawdown protection, so this only varies how aggressive to
be in the two uptrend states.
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

STABLE_TICKER = "QQQ"
LEVERAGED_TICKER = "TQQQ"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 60
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days.\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]

    benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})
    vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=VOL_LOOKBACK_DAYS)

    discovery_stable = stable_close.reindex(dates[dates <= discovery_end])
    discovery_leveraged = leveraged_close.reindex(dates[dates <= discovery_end])

    print("=== Grid search on DISCOVERY period only ===")
    grid_df = grid_search_state_weights(
        discovery_stable, discovery_leveraged, vol_threshold_pct=vol_threshold,
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
    )
    print(grid_df.to_string(index=False))

    best = grid_df.iloc[0]
    best_low, best_high = best["low_vol_lev_weight"], best["high_vol_lev_weight"]
    print(f"\nBest by Calmar ratio on discovery: uptrend_low_vol={best_low:.0%} TQQQ, "
          f"uptrend_high_vol={best_high:.0%} TQQQ\n")

    print("=== Applying that SAME combo to the CONFIRMATION period ===")
    best_weights = build_state_weights(best_low, best_high)
    regime_result = simulate_regime_rotation(
        stable_close, leveraged_close, vol_threshold_pct=vol_threshold,
        state_weights=best_weights, trend_lookback_days=TREND_LOOKBACK_DAYS,
        vol_lookback_days=VOL_LOOKBACK_DAYS, rebalance_check_days=REBALANCE_CHECK_DAYS,
        band_pct=BAND_PCT, start_date=confirmation_start,
    )
    regime_series = regime_result["series"]

    stable_conf = stable_close.reindex(regime_series.index)
    leveraged_conf = leveraged_close.reindex(regime_series.index)
    baseline_5050 = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)

    comparison = pd.DataFrame([
        {"strategy": f"tuned regime rotation ({best_low:.0%}/{best_high:.0%})",
         "n_trades": regime_result["n_trades"],
         "cagr_pct": round(cagr_pct(regime_series), 2),
         "max_drawdown_pct": round(max_drawdown_pct(regime_series), 1)},
        {"strategy": "hand-picked default (70%/40%) from earlier run", "n_trades": 19,
         "cagr_pct": 25.54, "max_drawdown_pct": -59.2},
        {"strategy": "buy & hold 50/50 (no rebalance)", "n_trades": 0,
         "cagr_pct": round(cagr_pct(baseline_5050["series"]), 2),
         "max_drawdown_pct": round(baseline_5050["max_drawdown_pct"], 1)},
    ])
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
