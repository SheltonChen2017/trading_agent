"""
Out-of-sample check for the current candidate baskets (unstable, tech,
fintech, rare_earth_minerals): splits each basket's signals into an
earlier discovery period and a later confirmation (holdout) period never
used to identify anything, and reports both separately.

A real edge should look similarly positive in both periods. One that's
strong in discovery and weak/flipped in confirmation was very likely
noise — exactly the scenario the project's own multiple-comparisons
warnings predict will happen sometimes.

Uses synthetic data by default — see README for switching to real data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from baskets import (
    out_of_sample_backtest_by_basket,
    out_of_sample_baseline_by_basket,
    out_of_sample_market_by_basket,
)

CANDIDATE_BASKETS = ["unstable", "tech", "fintech", "rare_earth_minerals"]
DISCOVERY_FRAC = 0.6  # first 60% of the window = discovery, last 40% = confirmation


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)
    benchmark_df = generate_synthetic(["SPY_SYNTHETIC"], days=LOOKBACK_DAYS, seed=99)["SPY_SYNTHETIC"]

    print(f"\n=== Out-of-sample win rate/return ({CANDIDATE_BASKETS}) ===")
    backtest_split = out_of_sample_backtest_by_basket(data, basket_names=CANDIDATE_BASKETS, discovery_frac=DISCOVERY_FRAC)
    print(backtest_split.to_string(index=False) if not backtest_split.empty else "No signals.")

    print("\n=== Out-of-sample edge vs. own-ticker baseline ===")
    baseline_split = out_of_sample_baseline_by_basket(data, basket_names=CANDIDATE_BASKETS, discovery_frac=DISCOVERY_FRAC)
    print(baseline_split.to_string(index=False) if not baseline_split.empty else "No signals.")

    print("\n=== Out-of-sample edge vs. the market (SPY) ===")
    market_split = out_of_sample_market_by_basket(
        data, benchmark_df, basket_names=CANDIDATE_BASKETS, discovery_frac=DISCOVERY_FRAC
    )
    print(market_split.to_string(index=False) if not market_split.empty else "No signals.")

    print(
        "\nCompare each basket/direction's 'discovery' row to its 'confirmation' row.\n"
        "Similar sign and rough magnitude in both = the strongest evidence this project\n"
        "can currently produce that an edge is real. A discovery-only result that\n"
        "weakens or flips in confirmation should be treated as noise, not a finding."
    )


if __name__ == "__main__":
    main()
