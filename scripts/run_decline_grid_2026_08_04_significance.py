"""
Frozen confirmatory test of the user-dictated "decline grid" strategy
(strategies/decline_grid.py): buy a stock making a fresh 3-month low
after a sharp recent decline, then trim on rallies / average down on
drops using a resetting percentage ladder, until it fully exits, stops
out, or hits a max hold period. Full construction, all frozen decisions,
and the risk controls this project added (position cap, stop-loss, max
hold -- NOT in the user's original description, added after explicit
clarification, 2026-08-04) are documented in strategies/decline_grid.py's
module docstring; this script only wires that module up to a significance
test.

BESPOKE HARNESS, same reasoning as scripts/run_calendar_effects_2026_08_03
_significance.py: episodes are path-dependent, variable-duration, and
one ticker can only hold one open episode at a time -- nothing like
run_backtest()'s fixed-hold_days row-per-signal contract. This reuses
backtest/engine.py's own block-bootstrap primitives directly on
episode-level edge values keyed by each episode's ENTRY date, and reuses
_discovery_split_date() so the discovery/confirmation boundary is
computed identically to every other finding in this project.

FROZEN SPECIFICATION (before any result was observed):
  edge            = edge_vs_buy_and_hold_pct per episode -- net episode
                     return MINUS simply buying the same entry and
                     holding it, unrebalanced, through the SAME
                     entry->exit window (isolates whether the ladder
                     itself adds value over just being long a beaten-
                     down decliner through its bounce/recovery, which is
                     just contrarian/reversal exposure already tested
                     elsewhere in this project as residual_reversal)
  window_days     = 10 (primary, ~2 trading weeks -- the middle of the
                     user's stated 1-3 week range); 5 and 15 reported as
                     sensitivity checks only, same convention this
                     project already uses for block-length/weighting
                     variants -- NOT additional confirmatory tests
  trim_pct        = 0.10 AND 0.20 -- BOTH independently pre-registered
                     primaries per the user's explicit choice (2026-08-04)
                     over freezing one midpoint
  discovery_frac  = 0.6 (engine default)
  block_lengths   = (5, 10, 15) trading days in ENTRY-DATE space (not
                     hold_days -- episode duration varies enormously,
                     18 to 250+ trading days observed on synthetic data,
                     so there is no single natural "2x hold_days"
                     analogue; these instead capture whether many
                     episodes cluster in the SAME calendar stretch, e.g.
                     a broad selloff triggering many entries at once)
  primary row     = equal_date_weighted at block_length=10

MULTIPLICITY. trim_pct in {0.10, 0.20} = 2 pre-registered cells, its own
family independent of every earlier 2026-08 screen. Bonferroni alpha/2.

This script REPORTS. It does not promote anything, write to any
registry, or authorize any trading. See strategies/decline_grid.py's
module docstring for the position-cap/stop-loss/max-hold risk controls
and the documented limitations (daily-close-only trigger detection,
independently-capitalized episodes) before treating any result here as
more than exploratory.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import LOOKBACK_DAYS, UNIVERSE
from data.market_data import fetch_historical
from backtest.engine import (
    _discovery_split_date,
    bonferroni_threshold,
    bootstrap_daily_edge_significance_by_block,
    bootstrap_edge_significance_by_block,
    recommended_n_bootstrap,
    _min_detectable_effect_pct,
)
from strategies.decline_grid import run_decline_grid_backtest

N_TESTS = 2
BLOCK_LENGTHS = (5, 10, 15)
PRIMARY_BLOCK_LENGTH = 10
DISCOVERY_FRAC = 0.6
WINDOW_DAYS_PRIMARY = 10
WINDOW_DAYS_SENSITIVITY = (5, 15)
TRIM_PCTS = (0.10, 0.20)

RESULT_COLUMNS = [
    "trim_pct", "window_days", "primary_window", "period", "weighting", "block_length", "primary",
    "n", "n_dates", "mean_edge_pct", "ci_low", "ci_high", "p_value",
    "bonferroni_threshold", "significant", "min_detectable_effect_pct",
    "refusal_reason",
]


def _significance_rows(trim_pct: float, window_days: int, episodes: pd.DataFrame, split_date, n_bootstrap: int, threshold: float) -> list[dict]:
    if episodes.empty:
        return []
    edges = episodes.rename(columns={"entry_signal_date": "date", "edge_vs_buy_and_hold_pct": "edge_pct"})
    discovery = edges[edges["date"] <= split_date]
    confirmation = edges[edges["date"] > split_date]

    rows = []
    for period, subset in (("discovery", discovery), ("confirmation", confirmation)):
        if subset.empty:
            continue
        for block_length in BLOCK_LENGTHS:
            trade_weighted_stats = bootstrap_edge_significance_by_block(
                subset["edge_pct"], subset["date"], block_length=block_length, n_bootstrap=n_bootstrap
            )
            daily_weighted_stats = bootstrap_daily_edge_significance_by_block(
                subset["edge_pct"], subset["date"], block_length=block_length, n_bootstrap=n_bootstrap
            )
            for weighting, stats in (
                ("trade_weighted", trade_weighted_stats),
                ("equal_date_weighted", daily_weighted_stats),
            ):
                is_primary = (
                    weighting == "equal_date_weighted"
                    and block_length == PRIMARY_BLOCK_LENGTH
                    and window_days == WINDOW_DAYS_PRIMARY
                )
                rows.append(
                    {
                        "trim_pct": trim_pct,
                        "window_days": window_days,
                        "primary_window": window_days == WINDOW_DAYS_PRIMARY,
                        "period": period,
                        "weighting": weighting,
                        "block_length": block_length,
                        "primary": is_primary,
                        "n": stats["n"],
                        "n_dates": stats["n_dates"],
                        "mean_edge_pct": stats["mean"],
                        "ci_low": stats["ci_low"],
                        "ci_high": stats["ci_high"],
                        "p_value": stats["p_value"],
                        "bonferroni_threshold": round(threshold, 6),
                        "significant": stats["p_value"] is not None and stats["p_value"] < threshold,
                        "min_detectable_effect_pct": _min_detectable_effect_pct(
                            stats["ci_low"], stats["ci_high"], threshold
                        ),
                        "refusal_reason": stats.get("refusal_reason"),
                    }
                )
    return rows


def main():
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 50)

    print(f"Fetching real history for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got data for {len(data)}/{len(UNIVERSE)} tickers.")

    split_date = _discovery_split_date(data, DISCOVERY_FRAC)
    print(f"Discovery/confirmation split date: {split_date.date()}")

    threshold = bonferroni_threshold(N_TESTS, alpha=0.05)
    n_bootstrap = recommended_n_bootstrap(N_TESTS)
    print(f"n_tests={N_TESTS} -> Bonferroni threshold alpha/{N_TESTS}={threshold:.6f}, n_bootstrap={n_bootstrap}")

    all_rows = []
    all_episodes = {}
    for trim_pct in TRIM_PCTS:
        for window_days in (WINDOW_DAYS_PRIMARY,) + WINDOW_DAYS_SENSITIVITY:
            print(f"\nSimulating trim_pct={trim_pct:.0%}, window_days={window_days}...")
            episodes = run_decline_grid_backtest(data, trim_pct=trim_pct, window_days=window_days)
            print(f"  {len(episodes)} completed episodes")
            if not episodes.empty:
                print(f"  outcome counts: {episodes['outcome'].value_counts().to_dict()}")
                print(f"  mean net_return_pct: {episodes['net_return_pct'].mean():.2f}%  "
                      f"mean edge_vs_buy_and_hold_pct: {episodes['edge_vs_buy_and_hold_pct'].mean():.2f}%  "
                      f"mean hold_days: {episodes['hold_days'].mean():.0f}")
            all_episodes[(trim_pct, window_days)] = episodes
            rows = _significance_rows(trim_pct, window_days, episodes, split_date, n_bootstrap, threshold)
            all_rows.extend(rows)

    if not all_rows:
        print("\nNo episodes at all -- entry filter never fired on this universe/lookback. Nothing to test.")
        return

    table = pd.DataFrame(all_rows)[RESULT_COLUMNS]

    for trim_pct in TRIM_PCTS:
        print(f"\n{'=' * 90}")
        print(f"trim_pct={trim_pct:.0%} -- PRIMARY rows (window_days={WINDOW_DAYS_PRIMARY} only; the only rows that count as evidence)")
        print("=" * 90)
        primary = table[(table["trim_pct"] == trim_pct) & table["primary"]]
        print(primary.to_string(index=False))

        confirmation_primary = primary[primary["period"] == "confirmation"]
        passed = confirmation_primary.loc[confirmation_primary["significant"]]
        verdict = (
            "CONFIRMATION-PERIOD PRIMARY ROW SIGNIFICANT"
            if not passed.empty
            else "No confirmation-period primary row cleared the corrected threshold."
        )
        print(f"\n>>> trim_pct={trim_pct:.0%}: {verdict}")

    print(f"\n{'=' * 90}")
    print("Full sensitivity grid (window_days variants x block lengths x weightings; NOT independent tests)")
    print("=" * 90)
    print(table.to_string(index=False))

    print(f"\n{'=' * 90}")
    print(
        f"Reminder: a confirmation-period primary row clearing alpha/{N_TESTS} is ONE piece of\n"
        "evidence from ONE historical sample of ONE universe, on adjusted yfinance data\n"
        "that is explicitly NOT point-in-time. It is not a validated edge, and nothing\n"
        "here authorizes any trading. See strategies/decline_grid.py's module docstring\n"
        "for the risk controls this project added and the strategy's documented limitations\n"
        "(independently-capitalized episodes, daily-close-only trigger detection)."
    )


if __name__ == "__main__":
    main()
