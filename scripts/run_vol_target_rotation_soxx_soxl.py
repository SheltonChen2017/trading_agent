"""
Tests the continuous volatility-targeting rotation strategy
(strategies/vol_target_rotation.py) on SOXX/SOXL -- the one pair where
the ORIGINAL discrete 4-bucket regime design actually worked (survived
walk-forward + parameter sensitivity, though it lost its CAGR edge after
tax modeling -- see memory: project_leverage_rotation_strategy).

Question this answers: does the continuous vol-targeting mechanism
(which made QQQ/TQQQ and QQQ/QLD's drawdown protection better but their
CAGR gap WORSE -- see memory: project_vol_target_rotation) also improve
on the discrete-bucket result here, or is discrete-bucket actually the
better fit specifically for this pair?

Same discipline: next-day-open execution built into the strategy itself,
tax/cost modeling (37% short-term capital gains, 0.05% round-trip cost)
included throughout the grid search AND confirmation, not bolted on
after the fact.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.vol_target_rotation import grid_search_vol_target, simulate_vol_target_rotation

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 20
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0
TAX_RATE = 0.37
COST_PCT = 0.0005

TARGET_VOL_OPTIONS = (0.5, 1.0, 1.5, 2.0, 2.5)
MAX_LEVERAGED_WEIGHT_OPTIONS = (0.6, 0.8, 1.0)


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery: {dates[0].date()} to {discovery_end.date()} | Confirmation: {confirmation_start.date()} to {dates[-1].date()}\n")

    discovery_dates = dates[dates <= discovery_end]
    print("=== Grid search on DISCOVERY (tax/cost included throughout) ===")
    grid_df = grid_search_vol_target(
        stable_close.reindex(discovery_dates), leveraged_close.reindex(discovery_dates),
        stable_open.reindex(discovery_dates), leveraged_open.reindex(discovery_dates),
        target_vol_options=TARGET_VOL_OPTIONS, max_leveraged_weight_options=MAX_LEVERAGED_WEIGHT_OPTIONS,
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        tax_rate=TAX_RATE, cost_pct=COST_PCT,
    )
    print(grid_df.to_string(index=False))

    best = grid_df.iloc[0]
    print(f"\nBest by Calmar: target_vol_pct={best['target_vol_pct']}, max_leveraged_weight={best['max_leveraged_weight']}\n")

    print("=== Applying that SAME combo to the CONFIRMATION period ===")
    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        target_vol_pct=best["target_vol_pct"], max_leveraged_weight=best["max_leveraged_weight"],
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        start_date=confirmation_start, tax_rate=TAX_RATE, cost_pct=COST_PCT,
    )
    series = result["series"]
    stable_conf = stable_close.reindex(series.index)
    leveraged_conf = leveraged_close.reindex(series.index)
    baseline = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)

    comparison = pd.DataFrame([
        {"strategy": f"vol-target rotation (vol={best['target_vol_pct']}, cap={best['max_leveraged_weight']:.0%})",
         "n_trades": result["n_trades"],
         "cagr_pct": round(cagr_pct(series), 2), "max_drawdown_pct": round(max_drawdown_pct(series), 1),
         "total_tax_paid": round(result["total_tax_paid"], 0), "total_cost_paid": round(result["total_cost_paid"], 0)},
        {"strategy": "buy & hold 50/50 (no tax exposure)", "n_trades": 0,
         "cagr_pct": round(cagr_pct(baseline["series"]), 2), "max_drawdown_pct": round(baseline["max_drawdown_pct"], 1),
         "total_tax_paid": 0, "total_cost_paid": 0},
    ])
    print(comparison.to_string(index=False))

    beats_both = (
        cagr_pct(series) > cagr_pct(baseline["series"])
        and max_drawdown_pct(series) > baseline["max_drawdown_pct"]
    )
    print(f"\nBeats 50/50 buy-and-hold on BOTH CAGR and drawdown (after-tax): {beats_both}")
    print(
        "\nFor reference, the discrete-bucket design on this same pair (after-tax/cost): "
        "33.9% CAGR / -54.0% DD vs. this same 36.3%/-73.9% baseline."
    )


if __name__ == "__main__":
    main()
