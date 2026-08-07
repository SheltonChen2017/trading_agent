"""
Frozen confirmatory test of two candidate price signals sourced from a
fresh literature search on 2026-08-03, run AFTER the first 2026-08-03
candidate screen (residual/pead family) had already been observed and
rejected.

Both ideas are well-established, heavily-replicated academic anomalies
that were not previously implemented in this codebase:

  high52_proximity  -- George & Hwang (2004), 52-week-high proximity.
                        Rank stocks by close / trailing-52-week-high;
                        long the top quintile.
  idio_vol          -- Ang, Hodrick, Xing & Zhang (2006), idiosyncratic
                        volatility anomaly. Rank stocks by NEGATIVE
                        trailing idiosyncratic (residual) volatility;
                        long the top quintile (lowest idio vol).

FROZEN SPECIFICATION (see signals/high52_proximity.py and
signals/idio_vol.py module docstrings for the full construction, chosen
before any result was observed):

  high52_proximity  hold 126d (~6mo, the shorter of George & Hwang's two
                     published horizons)
  idio_vol          hold  21d (~1mo, matching Ang et al.'s monthly
                     rebalance exactly)

  entry_timing    = "next_open"  (this project's realistic default)
  discovery_frac  = 0.6          (engine default)
  block bootstrap = block lengths (hold, 2x, 3x), the engine default

MULTIPLICITY. These two signals are ONE 2026-08-03 candidate screen,
separate from and NOT pooled with the earlier residual/PEAD screen that
day: 2 signals x 2 directions = 4 pre-registered cells, so every
Bonferroni threshold below is alpha/4. The shared family contract lives
in candidate_screen_2026_08_03_new_signals.py. The weighting and
block-length variants each cell reports are sensitivity checks, NOT
extra tests to pick from -- only the CONFIRMATION period's `primary` row
per (signal, direction) counts as evidence.

DIRECTION SEMANTICS. The backtester only ever goes long. For
high52_proximity, only "up" (near the 52-week high) tests the studied
hypothesis; "dip" is a control. For idio_vol, only "up" (lowest idio
vol) tests the studied hypothesis; "dip" (highest idio vol) is a
control the anomaly predicts should be weak/negative, not a second bet.

This script REPORTS. It does not promote anything, write to any
registry, or authorize any trading.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import fetch_historical
from backtest.engine import out_of_sample_significance_by_block
from scripts.candidate_screen_2026_08_03_new_signals import N_TESTS, confirmation_primary_rows
from signals.residual import build_residual_frames
from signals.high52_proximity import scan_high52_proximity
from signals.idio_vol import scan_idio_vol

BENCHMARK_TICKER = "SPY"


def main():
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    print(f"Fetching real history for {len(UNIVERSE)} tickers + {BENCHMARK_TICKER} "
          f"over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got data for {len(data)}/{len(UNIVERSE)} tickers.")

    benchmark_data = fetch_historical([BENCHMARK_TICKER], lookback_days=LOOKBACK_DAYS)
    if BENCHMARK_TICKER not in benchmark_data:
        raise SystemExit(
            f"{BENCHMARK_TICKER} did not resolve -- idio_vol cannot be computed "
            f"without a benchmark, and silently substituting another one would "
            f"change the hypothesis being tested."
        )
    benchmark_df = benchmark_data[BENCHMARK_TICKER]
    print(f"Benchmark {BENCHMARK_TICKER}: {len(benchmark_df)} sessions "
          f"({benchmark_df.index[0].date()} to {benchmark_df.index[-1].date()}).")

    depths = pd.Series({t: len(df) for t, df in data.items()})
    thin = depths[depths < 0.9 * LOOKBACK_DAYS].sort_values()
    if not thin.empty:
        print(f"\n{len(thin)} ticker(s) with <90% of the requested history "
              f"(they contribute proportionally fewer signals):")
        print(thin.to_string())

    print("\nPrecomputing residual frames for idio_vol (causal; identical rows to per-date computation)...")
    residual_frames = build_residual_frames(data, benchmark_df)

    runs = [
        ("high52_proximity", scan_high52_proximity, {}, 126),
        ("idio_vol", scan_idio_vol, {"residual_frames": residual_frames}, 21),
    ]

    for name, scan_fn, scan_kwargs, hold_days in runs:
        print(f"\n{'=' * 78}")
        print(f"{name} -- hold {hold_days}d, entry next_open, n_tests={N_TESTS} (Bonferroni alpha/{N_TESTS})")
        print("=" * 78)

        table = out_of_sample_significance_by_block(
            data,
            hold_days=hold_days,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs or None,
            n_tests=N_TESTS,
            entry_timing="next_open",
        )

        if table.empty:
            print("No signals flagged -- nothing to test.")
            continue

        evidence = confirmation_primary_rows(table)
        primary = table.loc[table["primary"]]
        print("\n--- PRIMARY rows (the only ones that count as evidence) ---")
        print(primary.to_string(index=False))

        print("\n--- Full sensitivity grid (weightings x block lengths; NOT independent tests) ---")
        print(table.to_string(index=False))

        passed = evidence.loc[evidence["significant"]]
        verdict = (
            f"CONFIRMATION-PERIOD PRIMARY ROWS SIGNIFICANT: {passed['direction'].tolist()}"
            if not passed.empty
            else "No confirmation-period primary row cleared the corrected threshold."
        )
        print(f"\n>>> {name}: {verdict}")

    print(f"\n{'=' * 78}")
    print(
        f"Reminder: a confirmation-period primary row clearing alpha/{N_TESTS} is ONE piece of\n"
        "evidence from ONE historical sample of ONE universe, on adjusted yfinance data\n"
        "that is explicitly NOT point-in-time. It is not a validated edge, and nothing\n"
        "here authorizes any trading."
    )


if __name__ == "__main__":
    main()
