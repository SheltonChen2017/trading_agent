"""
Compares the scanner's flagged-signal returns against a baseline of just
holding each stock for the same period on an arbitrary day — the control
group needed to tell whether an apparent edge is real, or just the whole
universe drifting during the test window.

Shows two versions:
  - pooled (compare_signal_to_baseline): baseline mixes every stock in the
    universe together. Simple, and still useful for spotting a whole-
    universe drift, but can be confounded if flagged signals cluster on
    naturally higher/lower-drift stocks than the universe average.
  - per-ticker (compare_signal_to_baseline_per_ticker): each signal is
    matched only against its OWN stock's any-day baseline, removing that
    confound. This is the one to trust for "does the signal itself add
    value."

Uses synthetic data by default — see README for switching to real data.
On synthetic random-walk data, both edge measures should sit near zero at
every horizon, since neither the signal nor the baseline has any real
predictive information there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import compare_signal_to_baseline, compare_signal_to_baseline_per_ticker


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("\n=== Pooled baseline (all stocks mixed together) ===")
    pooled = compare_signal_to_baseline(data)
    if pooled.empty:
        print("No signals or baseline data to compare.")
    else:
        print(pooled.to_string(index=False))
        print(
            "\nedge_vs_baseline_pct = signal_mean_return_pct - baseline_mean_return_pct.\n"
            "Near zero means the signal isn't adding anything beyond what holding the\n"
            "stock any day would have returned over the same period."
        )

    print("\n=== Per-ticker baseline (each signal vs. its OWN stock's any-day baseline) ===")
    per_ticker = compare_signal_to_baseline_per_ticker(data)
    if per_ticker.empty:
        print("No signals or baseline data to compare.")
    else:
        print(per_ticker.to_string(index=False))
        print(
            "\nmean_edge_vs_own_ticker_pct is the number to trust: each signal compared\n"
            "only to its own stock's typical any-day return, so it isn't confounded by\n"
            "flagged signals clustering on naturally higher- or lower-drift names.\n"
            "pct_signals_beating_own_ticker_baseline shows whether that mean is broad-\n"
            "based or driven by a few outlier trades."
        )


if __name__ == "__main__":
    main()
