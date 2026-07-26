"""
Parameter-sensitivity check for the trend+volatility regime rotation
strategy, applied to SOXX/SOXL instead of QQQ/TQQQ. Same purpose as
run_regime_rotation_sensitivity.py: a real effect should be roughly
stable to nearby trend/vol/rebalance lookback choices, not a sharp spike
that vanishes if any one number shifts slightly.

Holds SOXX/SOXL's own winning state weights (50% SOXL in uptrend_low_vol,
20% in uptrend_high_vol, found via grid search on discovery only under
corrected next-day-open timing) fixed, and varies ONE of
(trend_lookback_days, vol_lookback_days, rebalance_check_days) at a time.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import calibrate_threshold_from_discovery
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.trend_vol_rotation import build_state_weights, simulate_regime_rotation

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6

# Winning combo from run_regime_rotation_second_tech_pair.py (corrected next-open timing)
LOW_VOL_LEV_WEIGHT = 0.5
HIGH_VOL_LEV_WEIGHT = 0.2

DEFAULT_TREND_LOOKBACK = 200
DEFAULT_VOL_LOOKBACK = 60
DEFAULT_REBALANCE_CHECK = 21
BAND_PCT = 5.0

TREND_LOOKBACK_VARIANTS = [150, 200, 250]
VOL_LOOKBACK_VARIANTS = [30, 60, 90]
REBALANCE_CHECK_VARIANTS = [10, 21, 42]


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Confirmation period: {confirmation_start.date()} to {dates[-1].date()}\n")

    weights = build_state_weights(LOW_VOL_LEV_WEIGHT, HIGH_VOL_LEV_WEIGHT)
    benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})

    def run_variant(trend_lb, vol_lb, rebal_days):
        vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=vol_lb)
        result = simulate_regime_rotation(
            stable_close, leveraged_close, stable_open, leveraged_open, vol_threshold_pct=vol_threshold,
            state_weights=weights, trend_lookback_days=trend_lb, vol_lookback_days=vol_lb,
            rebalance_check_days=rebal_days, band_pct=BAND_PCT, start_date=confirmation_start,
        )
        series = result["series"]
        return {
            "trend_lookback_days": trend_lb, "vol_lookback_days": vol_lb,
            "rebalance_check_days": rebal_days, "n_trades": result["n_trades"],
            "cagr_pct": round(cagr_pct(series), 2), "max_drawdown_pct": round(max_drawdown_pct(series), 1),
        }

    print("=== Varying trend_lookback_days (others held at default 60/21) ===")
    rows = [run_variant(v, DEFAULT_VOL_LOOKBACK, DEFAULT_REBALANCE_CHECK) for v in TREND_LOOKBACK_VARIANTS]
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n=== Varying vol_lookback_days (others held at default 200/21) ===")
    rows = [run_variant(DEFAULT_TREND_LOOKBACK, v, DEFAULT_REBALANCE_CHECK) for v in VOL_LOOKBACK_VARIANTS]
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n=== Varying rebalance_check_days (others held at default 200/60) ===")
    rows = [run_variant(DEFAULT_TREND_LOOKBACK, DEFAULT_VOL_LOOKBACK, v) for v in REBALANCE_CHECK_VARIANTS]
    print(pd.DataFrame(rows).to_string(index=False))

    stable_conf = stable_close.reindex(dates[dates >= confirmation_start])
    leveraged_conf = leveraged_close.reindex(dates[dates >= confirmation_start])
    baseline = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)
    print(f"\nFor reference, buy & hold 50/50 over this same window: "
          f"CAGR {cagr_pct(baseline['series']):.2f}%, max drawdown {baseline['max_drawdown_pct']:.1f}%")


if __name__ == "__main__":
    main()
