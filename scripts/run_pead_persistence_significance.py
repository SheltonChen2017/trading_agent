"""
Frozen confirmatory test of the consecutive-earnings-surprise
persistence signal (2026-08-03).

FROZEN SPECIFICATION
--------------------
  signal          signals.pead_persistence.scan_pead_persistence
  streak gate     >= 4 consecutive same-sign surprises, window 8 quarters
  surprise gate   |current surprise| >= PEAD_SURPRISE_THRESHOLD_PCT
  hold            40 trading days (middle of the specified 20-60 window)
  entry_timing    "next_open"
  discovery_frac  0.6

MULTIPLICITY. This is cell 7 and 8 of the same 2026-08-03 candidate
screen that produced the three price signals in
run_residual_signal_significance.py — 4 signals x 2 directions = 8
pre-registered cells in total. Both runners import the same frozen family
contract and use n_tests=8. The first price-signal run used alpha/6 before
this fourth signal was built; nothing cleared that looser bar, so no prior
positive conclusion changes, but every future run uses the full alpha/8
family threshold directly.

SAMPLE SIZE IS THE POINT OF FAILURE HERE. An event signal that requires
a 4-quarter streak fires rarely. Read `n`, `n_dates` and
`min_detectable_effect_pct` before reading any edge number: a
non-significant result from a handful of events is an underpowered
test, not evidence that the effect is absent.

NOT POINT-IN-TIME: yfinance earnings figures are as-recorded-now, and
only currently-listed tickers exist in the universe at all. See
signals/pead_persistence.py.

DIRECTION SEMANTICS. The engine goes long every signal. The "up" row tests
continuation after beats; the "dip" row is a long-after-misses reversal
test, not a short test of downward PEAD. Its edge sign must be read before
attaching an interpretation; see signals/pead_persistence.py.

This script REPORTS. It does not promote anything or authorize trading.
"""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import fetch_historical
from data.earnings_data import fetch_earnings_history
from backtest.engine import out_of_sample_significance_by_block
from scripts.candidate_screen_20260803 import N_TESTS, confirmation_primary_rows
from signals.pead_persistence import scan_pead_persistence

HOLD_DAYS = 40


def main():
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    print(f"Fetching real history for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got price data for {len(data)}/{len(UNIVERSE)} tickers.")

    print("Fetching earnings history (up to 40 quarters per ticker)...")
    earnings = fetch_earnings_history(list(data.keys()), limit=40)
    resolved = {t: df for t, df in earnings.items() if df is not None and not df.empty}
    print(f"Got earnings for {len(resolved)}/{len(data)} tickers.")

    if not resolved:
        raise SystemExit("No earnings history resolved — nothing to test.")

    counts = pd.Series({t: len(df) for t, df in resolved.items()})
    print(f"Earnings events per ticker: min={counts.min()}, median={int(counts.median())}, "
          f"max={counts.max()}, total={counts.sum()}")

    scan_fn = partial(scan_pead_persistence, earnings_data=resolved)

    print(f"\n{'=' * 78}")
    print(f"pead_persistence — hold {HOLD_DAYS}d, entry next_open, n_tests={N_TESTS} (Bonferroni alpha/8)")
    print("=" * 78)

    table = out_of_sample_significance_by_block(
        data,
        hold_days=HOLD_DAYS,
        scan_fn=scan_fn,
        scan_kwargs={},
        n_tests=N_TESTS,
        entry_timing="next_open",
    )

    if table.empty:
        print("No signals flagged — the streak gate never fired. Nothing to test.")
        return

    # Validate the evidence schema before printing any row as primary.
    evidence = confirmation_primary_rows(table)
    primary = table.loc[table["primary"]]
    print("\n--- PRIMARY rows (the only ones that count as evidence) ---")
    print(primary.to_string(index=False))

    print("\n--- Full sensitivity grid (NOT independent tests) ---")
    print(table.to_string(index=False))

    passed = evidence.loc[evidence["significant"]]
    print(
        f"\n>>> pead_persistence: "
        + (f"CONFIRMATION-PERIOD PRIMARY ROWS SIGNIFICANT: {passed['direction'].tolist()}"
           if not passed.empty
           else "No confirmation-period primary row cleared the corrected threshold.")
    )

    print(
        "\nCheck n / n_dates / min_detectable_effect_pct above before concluding anything: "
        "with an event signal this selective, a null result is very likely an underpowered "
        "test rather than a demonstrated absence of effect."
    )


if __name__ == "__main__":
    main()
