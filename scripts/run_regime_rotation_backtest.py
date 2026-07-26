"""
Backtests the trend+volatility regime overlay (strategies/trend_vol_rotation.py)
against real QQQ/TQQQ history, using the same discovery/confirmation
discipline as the rest of this project: the volatility threshold is
calibrated from discovery-period data ONLY (signals/regime.py), then the
SAME threshold and state-weight table is applied unchanged to the
confirmation period.

Compares against the same baselines as run_leverage_rotation_backtest.py
(buy & hold 50/50, 100% QQQ, 100% TQQQ) plus the earlier fixed-threshold
daily-rotation result, for direct comparison.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import calibrate_threshold_from_discovery
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.trend_vol_rotation import DEFAULT_STATE_WEIGHTS, simulate_regime_rotation

STABLE_TICKER = "QQQ"      # proxy for QQQM — see strategies/leverage_rotation.py docstring
LEVERAGED_TICKER = "TQQQ"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 60
REBALANCE_CHECK_DAYS = 21   # ~monthly
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
    print(f"Got {len(dates)} overlapping trading days.\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery period:    {dates[0].date()} to {discovery_end.date()}")
    print(f"Confirmation period: {confirmation_start.date()} to {dates[-1].date()}\n")

    benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})
    vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=VOL_LOOKBACK_DAYS)
    print(f"Volatility threshold calibrated from discovery period only: {vol_threshold:.3f}% (daily std)\n")

    # --- Confirmation-period result for the regime strategy ---
    regime_result = simulate_regime_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        vol_threshold_pct=vol_threshold,
        state_weights=DEFAULT_STATE_WEIGHTS,
        trend_lookback_days=TREND_LOOKBACK_DAYS,
        vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS,
        band_pct=BAND_PCT,
        start_date=confirmation_start,
    )
    regime_series = regime_result["series"]

    # --- Baselines over the exact same confirmation window ---
    stable_conf = stable_close.reindex(regime_series.index)
    leveraged_conf = leveraged_close.reindex(regime_series.index)
    baseline_5050 = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)
    baseline_stable = buy_and_hold(stable_conf, leveraged_conf, 1.0, 0.0)
    baseline_leveraged = buy_and_hold(stable_conf, leveraged_conf, 0.0, 1.0)

    print("=== State breakdown over confirmation period (from trade log) ===")
    state_counts = pd.Series([t["state"] for t in regime_result["trade_log"]]).value_counts()
    print(state_counts.to_string())
    print()

    print("=== Confirmation period comparison ===")
    comparison = pd.DataFrame([
        {"strategy": "trend+vol regime rotation", "n_trades": regime_result["n_trades"],
         "total_return_pct": round(regime_result["total_return_pct"], 1),
         "cagr_pct": round(cagr_pct(regime_series), 2),
         "max_drawdown_pct": round(max_drawdown_pct(regime_series), 1)},
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
        "\nFor reference, the earlier fixed-threshold DAILY rotation "
        "(2%/$1000) on this same confirmation period had 948 trades, "
        "25.2% CAGR, -59.3% max drawdown (see run_leverage_rotation_backtest.py)."
    )
    print(
        "\nCaveats: no transaction costs or taxes modeled. QQQ stands in for "
        "QQQM before its Oct-2020 inception. State-weight table "
        "(uptrend_low_vol=70% TQQQ, uptrend_high_vol=40% TQQQ, any downtrend=0% TQQQ) "
        "is a hand-picked starting point, not fit to this data — a natural "
        "next step if this looks promising."
    )


if __name__ == "__main__":
    main()
