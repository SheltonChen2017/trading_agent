"""
Runs the walk-forward backtest and prints a summary.

Uses synthetic data by default (no setup needed). Swap generate_synthetic
for fetch_historical to backtest against real history — see README.

Remember: on synthetic data, ~50% win rates are the EXPECTED, correct
result (see backtest/engine.py docstring). Only real market data can tell
you whether the scanner has genuine edge.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import run_backtest, summarize_backtest


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Running walk-forward backtest (this re-scans every historical date)...\n")
    results = run_backtest(data)

    if results.empty:
        print("No signals were flagged across the entire backtest window.")
        return

    print(f"{len(results)} signals scored.\n")
    summary = summarize_backtest(results)
    print(summary.to_string(index=False))
    print(
        "\nNote: this is synthetic random-walk data, so forward returns are "
        "independent of the flagged signal by construction — a ~50% win rate "
        "here is the correct, expected result, not a failed backtest."
    )


if __name__ == "__main__":
    main()
