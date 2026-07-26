"""
Statistical significance check across all baskets.

Runs TWO versions:
  - basket_out_of_sample_significance() — THE correct, confirmatory check.
    Bootstraps significance SEPARATELY for the discovery period and the
    confirmation (holdout) period. Only a `period == "confirmation"` row
    with `significant=True` is real evidence of edge.
  - basket_significance() — the pooled (discovery+confirmation together)
    version, shown for comparison only. This project caught a real case
    (the `analyst` "dip" signal) where the pooled check said
    `significant=True` (p=0.014) purely because of a strong discovery-
    period effect, while the honest confirmation-only check said
    `significant=False` (p=0.656) — see backtest/engine.py's
    bonferroni_threshold() docstring for the full story. NEVER trust the
    pooled number alone.

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
from baskets import all_basket_names, basket_out_of_sample_significance, basket_significance


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    basket_names = all_basket_names()
    print(f"\nTesting {len(basket_names)} baskets x 2 directions = {len(basket_names) * 2} cells simultaneously.")

    print("\n=== Out-of-sample significance (THE correct check — trust only 'confirmation' rows) ===")
    oos_result = basket_out_of_sample_significance(data, basket_names=basket_names)
    if oos_result.empty:
        print("No signals to test.")
    else:
        confirmation_only = oos_result[oos_result["period"] == "confirmation"]
        print(confirmation_only.to_string(index=False))
        survivors = confirmation_only[confirmation_only["significant"]]
        print(
            f"\n{len(survivors)} of {len(confirmation_only)} basket/direction cells are significant "
            f"on CONFIRMATION-ONLY data."
        )
        if not survivors.empty:
            print(survivors.to_string(index=False))

    print("\n=== Pooled significance (comparison only — do NOT treat as confirmatory) ===")
    pooled_result = basket_significance(data, basket_names=basket_names)
    if pooled_result.empty:
        print("No signals to test.")
        return
    print(pooled_result.to_string(index=False))
    pooled_survivors = pooled_result[pooled_result["significant"]]
    print(f"\n{len(pooled_survivors)} of {len(pooled_result)} cells look significant when pooled.")
    if not pooled_survivors.empty:
        print(
            "\nCompare each of these against its CONFIRMATION-ONLY row above — a pooled "
            "'significant' result that isn't also confirmation-significant is not real evidence."
        )


if __name__ == "__main__":
    main()
