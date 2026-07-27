"""
Re-validates the three already-REJECTED signal findings that use
out_of_sample_significance_by_block() (macro cross-asset signals,
momentum, analyst price-target gap) under REALISTIC next-day-open
execution timing, alongside the original same_close timing, using real
market data.

Context (see memory: project_execution_realism_gaps): run_backtest()
defaulted to entering AND exiting at the signal date's own close --
not realistically executable, since that close isn't known until the
signal itself is computed. entry_timing="next_open" (enter next day's
open, exit hold_days of opens later) was built and tested in isolation
but never used to re-check any actual finding. This script closes that
gap for the three signals that already use the correct by-block
(serial-dependence-aware) significance method -- the older, row-level-
only rejected findings (original z-score scan, relative/breakout/PEAD/
fundamentals/analyst-rating) are not re-run here; they used a less
rigorous method that predates the by-block upgrade and would need
separate work to re-plumb.

None of these three are expected to flip from rejected to confirmed --
realistic execution timing generally makes results WORSE, not better,
since same_close is the more favorable (unrealistic) assumption. The
point of this script is to confirm that, not to go looking for a
different answer.
"""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    CREDIT_SPREAD_HY_TICKER,
    CREDIT_SPREAD_IG_TICKER,
    LOOKBACK_DAYS,
    UNIVERSE,
    VIX_TICKER,
    YIELD_CURVE_LONG_TICKER,
    YIELD_CURVE_SHORT_TICKER,
)
from data.market_data import fetch_historical
from data.macro_data import build_credit_spread_proxy, build_yield_curve_proxy
from data.price_target_data import fetch_price_target_history
from backtest.engine import out_of_sample_significance_by_block
from signals.vix_spike import scan_vix_spike
from signals.credit_spread import scan_credit_spread
from signals.yield_curve import scan_yield_curve
from signals.momentum import scan_momentum
from signals.analyst_target import scan_analyst_target_gap


def _run_one(name: str, data: dict, scan_fn) -> None:
    print(f"\n{'=' * 20} {name} {'=' * 20}")
    for entry_timing in ("same_close", "next_open"):
        result = out_of_sample_significance_by_block(
            data, hold_days=5, scan_fn=scan_fn, n_tests=2, entry_timing=entry_timing,
        )
        if result.empty:
            print(f"  [{entry_timing}] No signals fired -- nothing to test.")
            continue
        primary = result[result["primary"]]
        confirmation_primary = primary[primary["period"] == "confirmation"]
        survivors = confirmation_primary[confirmation_primary["significant"]]
        print(f"  [{entry_timing}] {len(survivors)} of {len(confirmation_primary)} confirmation-period primary cells significant.")
        if not confirmation_primary.empty:
            print(confirmation_primary.to_string(index=False))


def main():
    print(f"Fetching real historical price data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got price data for {len(data)}/{len(UNIVERSE)} tickers.")

    macro_tickers = [VIX_TICKER, CREDIT_SPREAD_HY_TICKER, CREDIT_SPREAD_IG_TICKER, YIELD_CURVE_SHORT_TICKER, YIELD_CURVE_LONG_TICKER]
    macro_raw = fetch_historical(macro_tickers, lookback_days=LOOKBACK_DAYS)
    vix_data = macro_raw[VIX_TICKER]
    credit_spread_proxy = build_credit_spread_proxy(macro_raw[CREDIT_SPREAD_HY_TICKER], macro_raw[CREDIT_SPREAD_IG_TICKER])
    yield_curve_proxy = build_yield_curve_proxy(macro_raw[YIELD_CURVE_SHORT_TICKER], macro_raw[YIELD_CURVE_LONG_TICKER])

    _run_one("VIX spike", data, partial(scan_vix_spike, vix_data=vix_data))
    _run_one("Credit spread widening", data, partial(scan_credit_spread, spread_data=credit_spread_proxy))
    _run_one("Yield curve inversion", data, partial(scan_yield_curve, curve_data=yield_curve_proxy))
    _run_one("Momentum (12-1 month)", data, scan_momentum)

    print(f"\nFetching analyst price-target history for {len(UNIVERSE)} tickers...")
    price_targets = fetch_price_target_history(UNIVERSE)
    _run_one("Analyst price-target gap", data, partial(scan_analyst_target_gap, price_target_history=price_targets))


if __name__ == "__main__":
    main()
