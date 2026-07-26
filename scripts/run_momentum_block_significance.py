"""
Re-tests the momentum "up" near-finding (see README / memory) with the
block bootstrap (out_of_sample_significance_by_block()) instead of the
by-date bootstrap that was used to declare it evaporated.

Context: momentum "up" passed row-level bootstrap significance in BOTH
discovery and confirmation (p=0.000, opposite signs) -- looked like the
first real finding in the project. Re-tested with a BY-DATE bootstrap
(because momentum flags ~19-20 correlated tickers every single day),
significance evaporated (p=0.247 discovery, p=0.075 confirmation).

An independent review pointed out that by-date resampling still treats
each trading day as independent, which misses SERIAL dependence across
nearby days -- and momentum is exactly the kind of signal where this
matters most: the top/bottom 20% by trailing momentum turns over slowly,
so the same tickers tend to stay flagged for weeks at a time, and the
5-day hold period means adjacent days' forward returns literally overlap.
This checks whether the "evaporated" conclusion holds up under the
stricter block bootstrap, or whether by-date resampling was still
overstating confidence in the null result too.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import fetch_historical
from backtest.engine import out_of_sample_significance_by_block, out_of_sample_significance_by_date
from signals.momentum import scan_momentum


def main():
    print(f"Fetching real historical data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got data for {len(data)}/{len(UNIVERSE)} tickers.\n")

    print("=== By-DATE bootstrap (previous check -- treats each day as independent) ===")
    by_date = out_of_sample_significance_by_date(data, hold_days=5, scan_fn=scan_momentum, n_tests=2)
    print(by_date.to_string(index=False))

    print("\n=== By-BLOCK bootstrap (accounts for serial dependence across nearby days too) ===")
    print("Testing block lengths 5, 10, 15 trading days (5 = hold_days, the minimum sensible block).")
    by_block = out_of_sample_significance_by_block(
        data, hold_days=5, scan_fn=scan_momentum, block_lengths=(5, 10, 15), n_tests=2,
    )
    print(by_block.to_string(index=False))

    print(
        "\nIf by-block confirmation rows are non-significant across all block lengths (like by-date "
        "already showed), the 'momentum evaporates' conclusion is reinforced, not undermined -- "
        "block bootstrap only ever WIDENS the CI relative to by-date, so it can't manufacture a "
        "false positive that by-date didn't already show; it can only reveal one by-date was "
        "hiding (which would show up as by-date being 'significant' while by-block is not)."
    )


if __name__ == "__main__":
    main()
