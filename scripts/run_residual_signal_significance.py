"""
Frozen confirmatory test of three candidate price signals (2026-08-03).

The three ideas came from an external LLM brainstorm; the specification
below was frozen BEFORE any result was observed, which is the only thing
that makes the confirmation-period numbers interpretable at all.

FROZEN SPECIFICATION
--------------------
Signals and their pre-committed hold periods:

  residual_momentum     hold 21d  — a ~1 month horizon, matching the
                                    "next 1-3 months" claim for momentum.
  vol_scaled_momentum   hold 21d  — same horizon, same claim.
  residual_reversal     hold  3d  — the middle of the specified "1-5 day"
                                    reversal window.

  entry_timing    = "next_open"  (this project's realistic default: a
                    signal computed from a close is entered at the NEXT
                    open, never at the close that generated it)
  discovery_frac  = 0.6          (engine default)
  block bootstrap = block lengths (hold, 2x, 3x), the engine default

MULTIPLICITY. 3 signals x 2 directions = 6 pre-registered cells, so
n_tests=6 and every Bonferroni threshold below is alpha/6. The weighting
and block-length variants that each cell reports are sensitivity checks,
NOT extra tests to pick from — backtest/engine.py marks exactly one
`primary` row per (period, direction), and only that row in the
CONFIRMATION period counts as evidence. Reading any other row as a
finding is the researcher-degrees-of-freedom trap this project has
already been burned by once (the `analyst` "dip" cell).

DIRECTION SEMANTICS. The backtester only ever goes long. For the two
momentum signals the "up" leg is the well-evidenced academic half and
the "dip" leg is a long position in losers, which is NOT what the
literature supports — read it as a control, not a second bet. For the
reversal signal only the "dip" leg tests the stated hypothesis at all;
see signals/residual.py's module docstring.

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
from signals.residual import build_residual_frames, scan_residual_momentum, scan_residual_reversal
from signals.vol_scaled_momentum import scan_vol_scaled_momentum

BENCHMARK_TICKER = "SPY"
N_TESTS = 6  # 3 signals x 2 directions, frozen in advance


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
            f"{BENCHMARK_TICKER} did not resolve — the residual signals cannot be computed "
            f"without a benchmark, and silently substituting another one would change the "
            f"hypothesis being tested."
        )
    benchmark_df = benchmark_data[BENCHMARK_TICKER]
    print(f"Benchmark {BENCHMARK_TICKER}: {len(benchmark_df)} sessions "
          f"({benchmark_df.index[0].date()} to {benchmark_df.index[-1].date()}).")

    # Report history depth honestly: a thin ticker cannot be told apart
    # from a deep one once results are pooled, so say so up front.
    depths = pd.Series({t: len(df) for t, df in data.items()})
    thin = depths[depths < 0.9 * LOOKBACK_DAYS].sort_values()
    if not thin.empty:
        print(f"\n{len(thin)} ticker(s) with <90% of the requested history "
              f"(they contribute proportionally fewer signals):")
        print(thin.to_string())

    print("\nPrecomputing residual frames (causal; identical rows to per-date computation)...")
    residual_frames = build_residual_frames(data, benchmark_df)

    runs = [
        ("residual_momentum", scan_residual_momentum, {"residual_frames": residual_frames}, 21),
        ("vol_scaled_momentum", scan_vol_scaled_momentum, {}, 21),
        ("residual_reversal", scan_residual_reversal, {"residual_frames": residual_frames}, 3),
    ]

    for name, scan_fn, scan_kwargs, hold_days in runs:
        print(f"\n{'=' * 78}")
        print(f"{name} — hold {hold_days}d, entry next_open, n_tests={N_TESTS} (Bonferroni alpha/6)")
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
            print("No signals flagged — nothing to test.")
            continue

        print("\n--- PRIMARY rows (the only ones that count as evidence) ---")
        primary = table[table["primary"]] if "primary" in table.columns else table
        print(primary.to_string(index=False))

        print("\n--- Full sensitivity grid (weightings x block lengths; NOT independent tests) ---")
        print(table.to_string(index=False))

        if "primary" in table.columns and "period" in table.columns:
            evidence = primary[primary["period"] == "confirmation"]
            passed = evidence[evidence["significant"]] if "significant" in evidence.columns else evidence.iloc[0:0]
            verdict = (
                f"CONFIRMATION-PERIOD PRIMARY ROWS SIGNIFICANT: {passed['direction'].tolist()}"
                if not passed.empty
                else "No confirmation-period primary row cleared the corrected threshold."
            )
            print(f"\n>>> {name}: {verdict}")

    print(f"\n{'=' * 78}")
    print(
        "Reminder: a confirmation-period primary row clearing alpha/6 is ONE piece of\n"
        "evidence from ONE historical sample of ONE universe, on adjusted yfinance data\n"
        "that is explicitly NOT point-in-time. It is not a validated edge, and nothing\n"
        "here authorizes any trading."
    )


if __name__ == "__main__":
    main()
