"""
Tests the new analyst price-target consensus signal (signals/
analyst_target.py, data/price_target_data.py) against real data using
the project's full rigor toolkit: out-of-sample discovery/confirmation
split, THEN the by-block (serial-dependence-aware) bootstrap — the same
bar every other signal in this project has been held to (see memory:
project_rigor_toolkit, project_signal_findings).

User-proposed signal (2026-07): aggregate real analyst price targets
into a point-in-time trimmed consensus (drop highest/lowest, then
mean/median), flag stocks whose price diverges meaningfully from that
consensus.
"""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import fetch_historical
from data.price_target_data import fetch_price_target_history
from backtest.engine import out_of_sample_significance_by_block
from signals.analyst_target import scan_analyst_target_gap


def main():
    print(f"Fetching real historical price data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got price data for {len(data)}/{len(UNIVERSE)} tickers.")

    print("Fetching real analyst price-target history (one API call per ticker, may take a while)...")
    price_targets = fetch_price_target_history(list(data.keys()))
    tickers_with_targets = [t for t, df in price_targets.items() if not df.empty]
    print(f"Got price-target history for {len(tickers_with_targets)}/{len(data)} tickers.\n")

    scan_fn = partial(scan_analyst_target_gap, price_target_history=price_targets)

    print("=== Out-of-sample, by-block (serial-dependence-aware) significance check ===")
    result = out_of_sample_significance_by_block(data, hold_days=5, scan_fn=scan_fn, n_tests=2)
    if result.empty:
        print("No signals fired -- nothing to test.")
        return
    print(result.to_string(index=False))

    primary = result[result["primary"]]
    confirmation_primary = primary[primary["period"] == "confirmation"]
    print("\n=== Primary (evidentiary) rows only ===")
    print(confirmation_primary.to_string(index=False))

    survivors = confirmation_primary[confirmation_primary["significant"]]
    print(f"\n{len(survivors)} of {len(confirmation_primary)} confirmation-period primary cells are significant.")


if __name__ == "__main__":
    main()
