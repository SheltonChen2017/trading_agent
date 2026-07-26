"""
Tests the redesigned volatility-targeting rotation strategy
(strategies/vol_target_rotation.py) on QQQ paired with BOTH TQQQ (3x) and
QLD (2x), side by side -- isolating whether leverage MAGNITUDE was part
of why the discrete-bucket regime design worked for SOXX/SOXL but mostly
failed for QQQ/TQQQ (see memory: project_leverage_rotation_strategy).

Same discipline as the rest of this project, but with two things fixed
from the start this time instead of bolted on after discovering they
mattered: next-day-open execution (built into the strategy itself, not
optional) and tax/cost modeling (37% short-term capital gains in a
taxable account, 0.05% round-trip cost -- the user's own stated
assumptions) applied THROUGHOUT the grid search, not just tacked onto
the final confirmation number.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.vol_target_rotation import grid_search_vol_target, simulate_vol_target_rotation

STABLE_TICKER = "QQQ"
LEVERAGED_TICKERS = ["TQQQ", "QLD"]
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


def run_for_pair(leveraged_ticker: str) -> dict:
    print(f"\n{'=' * 70}\n{STABLE_TICKER}/{leveraged_ticker}\n{'=' * 70}")
    data = fetch_historical([STABLE_TICKER, leveraged_ticker], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[leveraged_ticker]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[leveraged_ticker]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery: {dates[0].date()} to {discovery_end.date()} | Confirmation: {confirmation_start.date()} to {dates[-1].date()}")

    discovery_dates = dates[dates <= discovery_end]
    grid_df = grid_search_vol_target(
        stable_close.reindex(discovery_dates), leveraged_close.reindex(discovery_dates),
        stable_open.reindex(discovery_dates), leveraged_open.reindex(discovery_dates),
        target_vol_options=TARGET_VOL_OPTIONS, max_leveraged_weight_options=MAX_LEVERAGED_WEIGHT_OPTIONS,
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        tax_rate=TAX_RATE, cost_pct=COST_PCT,
    )
    print("\nGrid search on DISCOVERY (tax/cost included throughout):")
    print(grid_df.head(5).to_string(index=False))

    best = grid_df.iloc[0]
    print(f"\nBest by Calmar: target_vol_pct={best['target_vol_pct']}, max_leveraged_weight={best['max_leveraged_weight']}")

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

    summary = {
        "pair": f"{STABLE_TICKER}/{leveraged_ticker}",
        "target_vol_pct": best["target_vol_pct"], "max_leveraged_weight": best["max_leveraged_weight"],
        "n_trades": result["n_trades"],
        "strategy_cagr_pct": round(cagr_pct(series), 2),
        "strategy_dd_pct": round(max_drawdown_pct(series), 1),
        "total_tax_paid": round(result["total_tax_paid"], 0),
        "total_cost_paid": round(result["total_cost_paid"], 0),
        "baseline_cagr_pct": round(cagr_pct(baseline["series"]), 2),
        "baseline_dd_pct": round(baseline["max_drawdown_pct"], 1),
    }
    summary["beats_baseline_on_both"] = (
        summary["strategy_cagr_pct"] > summary["baseline_cagr_pct"]
        and summary["strategy_dd_pct"] > summary["baseline_dd_pct"]
    )
    print("\nConfirmation period (after-tax/cost) vs. buy & hold 50/50 (no tax exposure):")
    print(pd.DataFrame([summary]).to_string(index=False))
    return summary


def main():
    summaries = [run_for_pair(t) for t in LEVERAGED_TICKERS]
    print(f"\n{'=' * 70}\nSIDE-BY-SIDE SUMMARY\n{'=' * 70}")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
