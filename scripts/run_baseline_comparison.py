"""
Compares the scanner's flagged-signal returns against a baseline of just
holding each stock for the same period on an arbitrary day — the control
group needed to tell whether an apparent edge is real, or just the whole
universe drifting during the test window.

Uses synthetic data by default — see README for switching to real data.
On synthetic random-walk data, edge_vs_baseline_pct should sit near zero
at every horizon, since neither the signal nor the baseline has any real
predictive information there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import compare_signal_to_baseline


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Comparing flagged signals against the 'hold any day' baseline across hold periods...\n")
    comparison = compare_signal_to_baseline(data)

    if comparison.empty:
        print("No signals or baseline data to compare.")
        return

    print(comparison.to_string(index=False))
    print(
        "\nedge_vs_baseline_pct = signal_mean_return_pct - baseline_mean_return_pct.\n"
        "Near zero means the signal isn't adding anything beyond what holding the\n"
        "stock any day would have returned over the same period — a real edge\n"
        "needs edge_vs_baseline_pct to be clearly positive, consistently, across\n"
        "hold periods, not just at one."
    )


if __name__ == "__main__":
    main()
