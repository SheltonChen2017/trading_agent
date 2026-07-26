"""
Walk-forward robustness check for the Kelly + one-way-ratchet rotation
(strategies/kelly_rotation.py, one_way_ratchet=True) on SOXX/SOXL -- the
combination that looked best in the single-split comparison (33.56% CAGR
/ -45.8% DD / 1 trade / $0 tax vs. baseline's 36.34%/-73.9%), but fired
only ONE rebalance in that one confirmation window -- too little
evidence on its own to trust (see memory: project_kelly_ratchet_rotation).

Same procedure as the earlier regime-rotation walk-forward: grid search
(kelly_fraction x max_leveraged_weight) on discovery only, with tax/cost
modeling included in the search itself, applied unchanged to confirmation,
across THREE non-overlapping folds spanning different market eras.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.kelly_rotation import grid_search_kelly, simulate_kelly_rotation
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS = 4200
TREND_LOOKBACK_DAYS = 200
KELLY_LOOKBACK_DAYS = 20
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0
TAX_RATE = 0.37
COST_PCT = 0.0005

CUTOFFS = [0.4, 0.6, 0.8, 1.0]


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
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

        discovery_dates = dates[dates <= discovery_end]
        d_sc, d_lc, d_so, d_lo = [s.reindex(discovery_dates) for s in (stable_close, leveraged_close, stable_open, leveraged_open)]

        grid_df = grid_search_kelly(
            d_sc, d_lc, d_so, d_lo,
            trend_lookback_days=TREND_LOOKBACK_DAYS, kelly_lookback_days=KELLY_LOOKBACK_DAYS,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
            one_way_ratchet=True, use_trend_acceleration=False,
            tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        best = grid_df.iloc[0]

        confirm_dates = dates[(dates >= confirm_start) & (dates <= confirm_end)]
        result = simulate_kelly_rotation(
            stable_close, leveraged_close, stable_open, leveraged_open,
            kelly_fraction=best["kelly_fraction"], max_leveraged_weight=best["max_leveraged_weight"],
            trend_lookback_days=TREND_LOOKBACK_DAYS, kelly_lookback_days=KELLY_LOOKBACK_DAYS,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
            one_way_ratchet=True, use_trend_acceleration=False,
            start_date=confirm_start, tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        fold_series = result["series"].reindex(confirm_dates)
        fold_n_trades = sum(1 for t in result["trade_log"] if t["date"] in set(confirm_dates))
        fold_tax = sum(t["tax_paid"] for t in result["trade_log"] if t["date"] in set(confirm_dates))

        baseline = buy_and_hold(stable_close.reindex(confirm_dates), leveraged_close.reindex(confirm_dates), 0.5, 0.5)

        strategy_cagr = cagr_pct(fold_series)
        strategy_dd = max_drawdown_pct(fold_series)
        baseline_cagr = cagr_pct(baseline["series"])
        baseline_dd = baseline["max_drawdown_pct"]

        fold_rows.append({
            "fold": i + 1,
            "confirm_period": f"{confirm_start.date()} to {confirm_end.date()}",
            "kelly_fraction": best["kelly_fraction"], "max_leveraged_weight": best["max_leveraged_weight"],
            "n_trades": fold_n_trades, "tax_paid": round(fold_tax, 0),
            "strategy_cagr_pct": round(strategy_cagr, 2), "strategy_dd_pct": round(strategy_dd, 1),
            "baseline_cagr_pct": round(baseline_cagr, 2), "baseline_dd_pct": round(baseline_dd, 1),
            "beats_baseline_on_both": strategy_cagr > baseline_cagr and strategy_dd > baseline_dd,
        })

    print("\n=== Walk-forward summary across all folds ===")
    summary_df = pd.DataFrame(fold_rows)
    print(summary_df.to_string(index=False))
    n_wins = summary_df["beats_baseline_on_both"].sum()
    print(f"\nBeat 50/50 buy-and-hold on BOTH CAGR and drawdown in {n_wins}/{len(summary_df)} folds.")
    total_trades = summary_df["n_trades"].sum()
    print(f"Total trades across all 3 folds: {total_trades} (vs. 23 for the original vol-target design over the single confirmation window).")


if __name__ == "__main__":
    main()
