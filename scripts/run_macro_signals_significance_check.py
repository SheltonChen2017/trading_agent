"""
Tests all three cross-asset macro signals (signals/vix_spike.py,
signals/credit_spread.py, signals/yield_curve.py) against real data
using the project's full rigor toolkit: out-of-sample discovery/
confirmation split, THEN the by-block (serial-dependence-aware)
bootstrap — the same bar every other signal in this project has been
held to (see memory: project_rigor_toolkit, project_signal_findings).

All three signals share one mechanism: they flag the ENTIRE universe
simultaneously on a macro-stress trigger day (VIX spike, credit-spread
widening, or yield-curve inversion), which creates extreme same-day
cross-sectional correlation by construction -- exactly the case the
by-block bootstrap exists to handle correctly. Never evaluate these
with a row-level or by-date-only bootstrap.

Rebuilt 2026-07-26 after a git resync + machine switch wiped the
original VIX-only version of this script; extended to credit spread
and yield curve per explicit user request ("run everything again from
scratch for Cross-asset macro signals (VIX, credit spreads, yield
curve)").
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
from backtest.engine import out_of_sample_significance_by_block
from signals.vix_spike import scan_vix_spike
from signals.credit_spread import scan_credit_spread
from signals.yield_curve import scan_yield_curve


def _run_one(name: str, data: dict, scan_fn, n_tests: int) -> None:
    print(f"\n{'=' * 20} {name} {'=' * 20}")
    result = out_of_sample_significance_by_block(data, hold_days=5, scan_fn=scan_fn, n_tests=n_tests)
    if result.empty:
        print("No signals fired -- nothing to test.")
        return
    print(result.to_string(index=False))

    primary = result[result["primary"]]
    confirmation_primary = primary[primary["period"] == "confirmation"]
    print(f"\n--- {name}: primary (evidentiary) rows only ---")
    print(confirmation_primary.to_string(index=False))

    survivors = confirmation_primary[confirmation_primary["significant"]]
    print(f"\n{name}: {len(survivors)} of {len(confirmation_primary)} confirmation-period primary cells are significant.")


def main():
    print(f"Fetching real historical price data for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got price data for {len(data)}/{len(UNIVERSE)} tickers.")

    macro_tickers = [VIX_TICKER, CREDIT_SPREAD_HY_TICKER, CREDIT_SPREAD_IG_TICKER, YIELD_CURVE_SHORT_TICKER, YIELD_CURVE_LONG_TICKER]
    print(f"Fetching macro data for {macro_tickers}...")
    macro_raw = fetch_historical(macro_tickers, lookback_days=LOOKBACK_DAYS)
    for t in macro_tickers:
        got = len(macro_raw.get(t, []))
        print(f"  {t}: {got} days")

    vix_data = macro_raw[VIX_TICKER]
    credit_spread_proxy = build_credit_spread_proxy(macro_raw[CREDIT_SPREAD_HY_TICKER], macro_raw[CREDIT_SPREAD_IG_TICKER])
    yield_curve_proxy = build_yield_curve_proxy(macro_raw[YIELD_CURVE_SHORT_TICKER], macro_raw[YIELD_CURVE_LONG_TICKER])

    # Bonferroni denominator must cover EVERY cell scanned in this one run,
    # not just one signal's two directions (out_of_sample_significance_by_block's
    # own docstring: "Override with the total cell count when this is being
    # called across multiple baskets/signals at once"; baskets.py does the
    # same with len(names) * 2). This script scans three signals looking for
    # a survivor, so passing the per-signal default n_tests=2 made the
    # threshold 0.025 when it should be 0.05/6 = 0.0083 -- 3x too lenient,
    # in the exact direction that manufactures a false positive.
    #
    # Derived from `runs`, never hardcoded a second time: adding a fourth
    # macro signal below automatically tightens the correction instead of
    # silently leaving it stale (self-review, 2026-07-29).
    runs = [
        ("VIX spike", partial(scan_vix_spike, vix_data=vix_data)),
        ("Credit spread widening", partial(scan_credit_spread, spread_data=credit_spread_proxy)),
        ("Yield curve inversion", partial(scan_yield_curve, curve_data=yield_curve_proxy)),
    ]
    n_tests = len(runs) * 2  # 2 directions (dip + up) per signal
    print(
        f"\nBonferroni correction: {len(runs)} signals x 2 directions = {n_tests} simultaneous cells "
        f"-> threshold {0.05 / n_tests:.5f}"
    )
    for name, scan_fn in runs:
        _run_one(name, data, scan_fn, n_tests)


if __name__ == "__main__":
    main()
