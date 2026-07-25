"""
Per-basket backtest/baseline report — shows which themed groupings
(tech, semiconductors, ai_related, unstable, rare_earth_minerals,
fintech, etc., see config.BASKETS) look more or less promising, WITHOUT
training a separate model per basket. See baskets.py's docstring for why
per-basket model training is deliberately deferred: splitting the
universe further shrinks an already-thin per-signal sample.

Also reports:
  - the empirically-computed high-volatility basket (realized daily-return
    std), as a data-driven cross-check against the hand-curated "unstable"
    basket in config.BASKETS.
  - each basket's signals compared against the S&P 500 (SPY) benchmark on
    the EXACT dates they fired — the strictest of the three baselines this
    project computes (own history -> own ticker's baseline -> the market
    on that specific date).

Uses synthetic data by default — see README for switching to real data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from baskets import (
    all_basket_names,
    compare_baskets_to_baseline,
    compare_baskets_to_market_index,
    compute_high_volatility_basket,
    summarize_by_basket,
)


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)
    # A separate synthetic "benchmark" series stands in for SPY here since
    # this demo has no network access — see README for pointing this at a
    # real SPY/QQQ history via fetch_historical() instead.
    benchmark_df = generate_synthetic(["SPY_SYNTHETIC"], days=LOOKBACK_DAYS, seed=99)["SPY_SYNTHETIC"]

    high_vol = compute_high_volatility_basket(data)
    print(f"\nEmpirically computed high-volatility basket (top {len(high_vol)} by realized daily std): {high_vol}")
    print("Compare this against config.BASKETS['unstable'] — do the hand-picked names show up here too?")

    print(f"\n=== Backtest summary by basket ({len(all_basket_names())} baskets) ===")
    summary = summarize_by_basket(data)
    if summary.empty:
        print("No signals flagged in any basket.")
    else:
        print(summary.to_string(index=False))

    print("\n=== Per-basket edge vs. own-ticker baseline ===")
    comparison = compare_baskets_to_baseline(data)
    if comparison.empty:
        print("No comparison data available.")
    else:
        print(comparison.to_string(index=False))

    print("\n=== Per-basket edge vs. the market (SPY) on the exact signal dates ===")
    market_comparison = compare_baskets_to_market_index(data, benchmark_df)
    if market_comparison.empty:
        print("No comparison data available.")
    else:
        print(market_comparison.to_string(index=False))
        print(
            "\nThis is the strictest bar: did the signal beat just buying the market\n"
            "index on that exact day? A basket that only looks good against its own\n"
            "history or its own baseline, but not against the market, is likely just\n"
            "riding a broad market move rather than showing real, basket-specific edge.\n"
            "With this few signals per basket, treat any single positive result with\n"
            "the same skepticism as a small sample anywhere else in this project."
        )


if __name__ == "__main__":
    main()
