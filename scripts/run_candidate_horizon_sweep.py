"""
Multi-horizon sweep for the current candidate baskets (unstable, tech,
fintech, rare_earth_minerals) — the specific gap flagged when reviewing
basket-level results: summarize_by_basket()/compare_baskets_to_baseline()/
compare_baskets_to_market_index() all default to a single hold period
(BACKTEST_HOLD_DAYS), so a candidate that "looks good" has usually only
been checked at one arbitrary exit timing. This sweeps the full
HORIZON_SWEEP_DAYS for just these candidates (a full 16-basket sweep
would take a very long time).

Uses synthetic data by default — see README for switching to real data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import HORIZON_SWEEP_DAYS, LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from baskets import compare_baskets_to_baseline, compare_baskets_to_market_index

CANDIDATE_BASKETS = ["unstable", "tech", "fintech", "rare_earth_minerals"]


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)
    benchmark_df = generate_synthetic(["SPY_SYNTHETIC"], days=LOOKBACK_DAYS, seed=99)["SPY_SYNTHETIC"]

    print(f"\n=== Multi-horizon: candidate baskets vs. own-ticker baseline ({CANDIDATE_BASKETS}) ===")
    baseline_sweep = compare_baskets_to_baseline(
        data, basket_names=CANDIDATE_BASKETS, hold_days_options=HORIZON_SWEEP_DAYS
    )
    print(baseline_sweep.to_string(index=False) if not baseline_sweep.empty else "No signals.")

    print("\n=== Multi-horizon: candidate baskets vs. the market (SPY) ===")
    market_sweep = compare_baskets_to_market_index(
        data, benchmark_df, basket_names=CANDIDATE_BASKETS, hold_days_options=HORIZON_SWEEP_DAYS
    )
    print(market_sweep.to_string(index=False) if not market_sweep.empty else "No signals.")
    print(
        "\nA candidate should show a similarly positive edge across MOST hold periods,\n"
        "not just the one it was originally found at — a result that's only good at a\n"
        "single arbitrary horizon is the same kind of overfitting risk as testing many\n"
        "baskets/directions at once."
    )


if __name__ == "__main__":
    main()
