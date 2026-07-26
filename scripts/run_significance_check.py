"""
Statistical significance check across all baskets: bootstraps the
per-ticker-baseline edge for each basket/direction to get a mean, 95% CI,
and p-value, then flags whether it survives a Bonferroni-corrected
threshold given how many basket/direction cells are being tested at once.

This replaces "eyeballing whether a win rate looks convincing" with an
actual number — and the correction matters: with ~32 basket/direction
cells tested simultaneously, a couple are expected to look interesting by
chance alone even with zero real edge anywhere, unless the significance
bar accounts for that.

Uses synthetic data by default — see README for switching to real data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from baskets import all_basket_names, basket_significance


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    basket_names = all_basket_names()
    print(f"\nTesting {len(basket_names)} baskets x 2 directions = {len(basket_names) * 2} cells simultaneously.")
    result = basket_significance(data, basket_names=basket_names)

    if result.empty:
        print("No signals to test.")
        return

    print(result.to_string(index=False))

    survivors = result[result["significant"]]
    print(f"\n{len(survivors)} of {len(result)} basket/direction cells survive the Bonferroni-corrected threshold.")
    if survivors.empty:
        print(
            "None of them do — on synthetic data that's the CORRECT, expected result "
            "(there's no real edge to find here by construction)."
        )
    else:
        print(survivors.to_string(index=False))
        print(
            "\nEven a 'significant' result here should still be checked against the "
            "out-of-sample confirmation period (scripts/run_out_of_sample_check.py) "
            "before treating it as real."
        )


if __name__ == "__main__":
    main()
