"""
Runs each of the 4 new signals (momentum, relative, breakout — PEAD
needs real earnings data and is skipped here, see below) through the
backtest + out-of-sample rigor toolkit. None of these are proven any
more than the original scanner was — they're recommendations with better
academic track records, still needing the same rigorous testing (this
script, plus scripts/run_significance_check.py and
scripts/run_baseline_comparison.py-style tools) before being trusted.

Uses synthetic data by default, so it runs with zero setup. See README
for pointing this at real data via fetch_historical(), and for how to
run PEAD (it needs data.earnings_data.fetch_earnings_history(), which
requires real tickers — no synthetic equivalent exists for earnings
events).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BACKTEST_HOLD_DAYS, LOOKBACK_DAYS, SLIPPAGE_PCT, UNIVERSE
from data.market_data import generate_synthetic  # swap for fetch_historical for real data
from backtest.engine import out_of_sample_backtest, run_backtest, summarize_backtest
from signals.breakout import scan_52_week_breakout
from signals.momentum import scan_momentum
from signals.relative import scan_relative_dips_and_ups

SIGNALS = {
    "momentum": (scan_momentum, {}),
    "relative": (scan_relative_dips_and_ups, {}),
    "breakout": (scan_52_week_breakout, {}),
}


def main():
    print(f"Generating synthetic data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} days...")
    data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)

    for name, (scan_fn, scan_kwargs) in SIGNALS.items():
        print(f"\n{'=' * 70}\n{name.upper()}\n{'=' * 70}")

        results = run_backtest(
            data, hold_days=BACKTEST_HOLD_DAYS, slippage_pct=SLIPPAGE_PCT, scan_fn=scan_fn, scan_kwargs=scan_kwargs
        )
        print(f"{len(results)} signals scored.")
        if results.empty:
            print("(nothing flagged — nothing to report)")
            continue
        print(summarize_backtest(results).to_string(index=False))

        print("\nOut-of-sample (discovery vs. confirmation):")
        oos = out_of_sample_backtest(
            data, hold_days=BACKTEST_HOLD_DAYS, slippage_pct=SLIPPAGE_PCT, scan_fn=scan_fn, scan_kwargs=scan_kwargs
        )
        print(oos.to_string(index=False) if not oos.empty else "  (not enough signals to split)")

    print(
        "\nPEAD isn't included above — it needs real earnings data, which doesn't\n"
        "exist for synthetic tickers. Run it against real data:\n\n"
        "  from functools import partial\n"
        "  from data.earnings_data import fetch_earnings_history\n"
        "  from signals.pead import scan_pead\n"
        "  earnings = fetch_earnings_history(list(data.keys()))\n"
        "  run_backtest(data, scan_fn=partial(scan_pead, earnings_data=earnings), scan_kwargs={})\n"
    )


if __name__ == "__main__":
    main()
