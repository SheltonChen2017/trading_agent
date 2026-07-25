"""
Demo entry point — generates a synthetic universe (no internet required)
and runs the scanner against it, printing any flagged dips/ups.

Once you've validated the pipeline, switch generate_synthetic(...) below
to fetch_historical(...) to run against real market data (needs
`pip install yfinance` and internet access).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from signals.scanner import scan_dips_and_ups


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Scanning for statistically unusual moves confirmed by volume...\n")
    signals = scan_dips_and_ups(data)

    if signals.empty:
        print("No dips/ups flagged today.")
    else:
        print(signals.to_string(index=False))


if __name__ == "__main__":
    main()
