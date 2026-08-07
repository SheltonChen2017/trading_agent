"""
Runs the walk-forward backtest across several hold periods (config's
HORIZON_SWEEP_DAYS — 1 day, 3 days, 1 week, 2 weeks, 1 month by default)
so you can see whether a signal's apparent edge (or lack of it) holds up
across different holding times, instead of trusting one arbitrarily
chosen BACKTEST_HOLD_DAYS.

Uses synthetic data by default — see README for switching to real data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import run_multi_horizon_backtest, summarize_multi_horizon


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    print("Running walk-forward backtest across multiple hold periods...\n")
    results_by_horizon = run_multi_horizon_backtest(data)
    summary = summarize_multi_horizon(results_by_horizon)

    if summary.empty:
        print("No signals were flagged across the entire backtest window.")
        return

    print(summary.to_string(index=False))
    print(
        "\nNote: mean_return_zscore/mean_volume_zscore describe how unusual the\n"
        "underlying signals were at the moment they fired — they don't change\n"
        "with hold period (small variation across rows is just which signals had\n"
        "enough forward data to score at that horizon). Only win_rate_pct and the\n"
        "return columns are hold-period dependent; compare THOSE across rows to\n"
        "see whether a strategy's apparent edge holds up at every horizon or was\n"
        "only ever true for one arbitrarily chosen exit timing."
    )


if __name__ == "__main__":
    main()
