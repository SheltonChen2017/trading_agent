"""
Walk-forward robustness check for the trend+volatility regime rotation
strategy. A single discovery/confirmation split (run_regime_rotation_
grid_search.py) found a combo that beat 50/50 buy-and-hold on ONE
historical confirmation window (2019-2026) — weak evidence on its own,
since that's only one draw from market history.

This re-runs the exact same procedure (calibrate vol threshold from
discovery only, grid-search state weights on discovery only, apply
unchanged to confirmation) across THREE non-overlapping folds spanning
different market eras, using an expanding discovery window each time:

  Fold 1: discovery 2010-2016ish -> confirm ~2016-2019 (late bull market)
  Fold 2: discovery 2010-2019ish -> confirm ~2019-2023 (COVID crash + 2022 bear)
  Fold 3: discovery 2010-2023ish -> confirm ~2023-2026 (AI-driven bull run)

If the tuned strategy beats 50/50 buy-and-hold in most/all folds, that's
real evidence of a structural effect. If it only wins in the fold we
already found, this is likely just overfitting to one lucky period.
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
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 60
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0

# Cumulative fraction cutoffs of the full date range: fold N's discovery is
# [0, CUTOFFS[N]) and its confirmation is [CUTOFFS[N], CUTOFFS[N+1]).
CUTOFFS = [0.4, 0.6, 0.8, 1.0]


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).\n")

    fold_rows = []
    for i in range(len(CUTOFFS) - 1):
        discovery_end_idx = int(len(dates) * CUTOFFS[i]) - 1
        confirm_start_idx = discovery_end_idx + 1
        confirm_end_idx = int(len(dates) * CUTOFFS[i + 1]) - 1
        discovery_end = dates[discovery_end_idx]
        confirm_start = dates[confirm_start_idx]
        confirm_end = dates[confirm_end_idx]

        print(f"--- Fold {i + 1}: discovery {dates[0].date()}-{discovery_end.date()}, "
              f"confirm {confirm_start.date()}-{confirm_end.date()} ---")

        benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})
        vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=VOL_LOOKBACK_DAYS)

        discovery_dates = dates[dates <= discovery_end]
        discovery_stable = stable_close.reindex(discovery_dates)
        discovery_leveraged = leveraged_close.reindex(discovery_dates)

        grid_df = grid_search_state_weights(
            discovery_stable, discovery_leveraged, vol_threshold_pct=vol_threshold,
            trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        )
        best = grid_df.iloc[0]
        best_weights = build_state_weights(best["low_vol_lev_weight"], best["high_vol_lev_weight"])

        confirm_dates = dates[(dates >= confirm_start) & (dates <= confirm_end)]
        # Pass the FULL series (not just confirm slice) so trend/vol lookback
        # has access to pre-fold history; start_date restricts what's traded.
        regime_result = simulate_regime_rotation(
            stable_close, leveraged_close, vol_threshold_pct=vol_threshold,
            state_weights=best_weights, trend_lookback_days=TREND_LOOKBACK_DAYS,
            vol_lookback_days=VOL_LOOKBACK_DAYS, rebalance_check_days=REBALANCE_CHECK_DAYS,
            band_pct=BAND_PCT, start_date=confirm_start,
        )
        # Trim to this fold's confirm window only (simulate runs to end of full series otherwise)
        fold_series = regime_result["series"].reindex(confirm_dates)
        fold_n_trades = sum(1 for t in regime_result["trade_log"] if t["date"] in set(confirm_dates))

        stable_fold = stable_close.reindex(confirm_dates)
        leveraged_fold = leveraged_close.reindex(confirm_dates)
        baseline = buy_and_hold(stable_fold, leveraged_fold, 0.5, 0.5)

        strategy_cagr = cagr_pct(fold_series)
        strategy_dd = max_drawdown_pct(fold_series)
        baseline_cagr = cagr_pct(baseline["series"])
        baseline_dd = baseline["max_drawdown_pct"]
        beats_on_both = strategy_cagr > baseline_cagr and strategy_dd > baseline_dd

        fold_rows.append({
            "fold": i + 1,
            "confirm_period": f"{confirm_start.date()} to {confirm_end.date()}",
            "best_weights": f"{best['low_vol_lev_weight']:.0%}/{best['high_vol_lev_weight']:.0%}",
            "n_trades": fold_n_trades,
            "strategy_cagr_pct": round(strategy_cagr, 2),
            "strategy_dd_pct": round(strategy_dd, 1),
            "baseline_5050_cagr_pct": round(baseline_cagr, 2),
            "baseline_5050_dd_pct": round(baseline_dd, 1),
            "beats_baseline_on_both": beats_on_both,
        })

    print("\n=== Walk-forward summary across all folds ===")
    summary_df = pd.DataFrame(fold_rows)
    print(summary_df.to_string(index=False))

    n_wins = summary_df["beats_baseline_on_both"].sum()
    print(f"\nBeat 50/50 buy-and-hold on BOTH CAGR and drawdown in {n_wins}/{len(summary_df)} folds.")


if __name__ == "__main__":
    main()
