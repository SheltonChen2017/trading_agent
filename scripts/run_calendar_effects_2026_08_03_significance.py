"""
Frozen confirmatory test of two calendar/session effects sourced from a
fresh literature search on 2026-08-03: overnight (close-to-open) drift
and the turn-of-month effect. See signals/calendar_effects.py for the
full frozen construction (window definitions, chosen before any result
was observed) and why these two don't fit the scan_fn contract every
other signal in this project follows.

BESPOKE HARNESS, NOT out_of_sample_significance_by_block(). Both effects
are UNCONDITIONAL (every ticker/day either is or isn't in the window --
no ranking, no "up"/"dip" bet direction) and one needs a close(t)->
open(t+1) window no existing entry_timing mode supports. Rather than
extend backtest/engine.py's shared entry_timing contract (risking every
already-validated finding that depends on it) for two exploratory tests,
this script calls the SAME underlying block-bootstrap primitives
(bootstrap_edge_significance_by_block, bootstrap_daily_edge_significance_
by_block, bonferroni_threshold, recommended_n_bootstrap) directly on a
hand-built edge series, and reuses the engine's own discovery/
confirmation date-split helper (_discovery_split_date) so the split is
computed identically to every other finding in this project.

FROZEN SPECIFICATION (before any result was observed):
  discovery_frac  = 0.6           (engine default, matches every other
                                    out-of-sample test in this project)
  block_lengths   = (1, 2, 3)     (both effects are single-day events;
                                    1 = the effect's own "hold days")
  primary row     = equal_date_weighted at block_length=2, matching the
                     "2x hold_days" convention out_of_sample_significance_
                     by_block() uses elsewhere
  edge, overnight_drift  = raw close(t)->open(t+1) return, net of ONE
                     round-trip's SLIPPAGE_PCT (this project's existing
                     per-leg cost model) -- realistic because entering at
                     the close of every single session (an unconditional
                     buy-and-hold-overnight strategy needs no same-day
                     signal, so a market-on-close order genuinely can
                     transact there, unlike every scan_fn signal, which
                     needs that day's own completed close to even compute
                     the signal that would trigger the order)
  edge, turn_of_month    = each window day's own return MINUS that
                     ticker's own mean daily return over the SAME
                     discovery/confirmation period (own_ticker_baseline_
                     pct, matching every scan_fn signal's convention),
                     net of one round-trip SLIPPAGE_PCT -- see "CAUGHT
                     BY..." in signals/calendar_effects.py's module
                     docstring for why the vs-zero test this replaced was
                     wrong for this specific (comparative) hypothesis

  Round-trip slippage matters far more here than for a sparse scan_fn
  signal: these two effects trade EVERY single session (not a rare
  flagged subset), so SLIPPAGE_PCT * 2 is subtracted from every single
  observation, not just occasionally.

MULTIPLICITY. Two effects, one cell each (no direction split): N_TESTS=2,
Bonferroni alpha/2. This is its own pre-registered family, independent of
both earlier 2026-08-03 candidate screens.

This script REPORTS. It does not promote anything, write to any
registry, or authorize any trading.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import LOOKBACK_DAYS, SLIPPAGE_PCT, UNIVERSE
from data.market_data import fetch_historical
from backtest.engine import (
    _discovery_split_date,
    bonferroni_threshold,
    bootstrap_daily_edge_significance_by_block,
    bootstrap_edge_significance_by_block,
    recommended_n_bootstrap,
    _min_detectable_effect_pct,
)
from signals.calendar_effects import (
    compute_daily_returns,
    compute_overnight_returns,
    compute_turn_of_month_returns,
)

N_TESTS = 2
BLOCK_LENGTHS = (1, 2, 3)
PRIMARY_BLOCK_LENGTH = 2
DISCOVERY_FRAC = 0.6

RESULT_COLUMNS = [
    "effect", "period", "weighting", "block_length", "primary",
    "n", "n_dates", "mean_edge_pct", "ci_low", "ci_high", "p_value",
    "bonferroni_threshold", "significant", "min_detectable_effect_pct",
    "refusal_reason",
]


def _apply_own_ticker_baseline(edges: pd.DataFrame, daily_returns: pd.DataFrame, split_date) -> pd.DataFrame:
    """
    Subtract each ticker's own mean daily return -- computed SEPARATELY
    within the discovery and confirmation periods, from ALL of that
    ticker's trading days, not just window days -- from `edges`.

    Mirrors backtest/engine.py's _out_of_sample_own_ticker_detail(): the
    baseline must come from each period's own price history so a
    confirmation-period edge is never measured against a baseline that
    already reflects the discovery period's returns (or vice versa). See
    signals/calendar_effects.py's module docstring for why this
    correction is required for turn_of_month but not overnight_drift.
    """
    if edges.empty:
        return edges

    adjusted = []
    for is_discovery in (True, False):
        daily_mask = (daily_returns["date"] <= split_date) if is_discovery else (daily_returns["date"] > split_date)
        edge_mask = (edges["date"] <= split_date) if is_discovery else (edges["date"] > split_date)

        baseline_by_ticker = daily_returns[daily_mask].groupby("ticker")["return_pct"].mean()
        period_edges = edges[edge_mask].copy()
        if period_edges.empty:
            continue
        period_edges["edge_pct"] = period_edges["edge_pct"] - period_edges["ticker"].map(baseline_by_ticker)
        adjusted.append(period_edges)

    if not adjusted:
        return edges.iloc[0:0]
    return pd.concat(adjusted, ignore_index=True).dropna(subset=["edge_pct"])


def _significance_table(effect_name: str, edges: pd.DataFrame, split_date, n_bootstrap: int, threshold: float) -> list[dict]:
    if edges.empty:
        return []

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
                is_primary = weighting == "equal_date_weighted" and block_length == PRIMARY_BLOCK_LENGTH
                rows.append(
                    {
                        "effect": effect_name,
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
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    print(f"Fetching real history for {len(UNIVERSE)} tickers over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)
    print(f"Got data for {len(data)}/{len(UNIVERSE)} tickers.")

    split_date = _discovery_split_date(data, DISCOVERY_FRAC)
    print(f"Discovery/confirmation split date: {split_date.date()}")

    threshold = bonferroni_threshold(N_TESTS, alpha=0.05)
    n_bootstrap = recommended_n_bootstrap(N_TESTS)
    print(f"n_tests={N_TESTS} -> Bonferroni threshold alpha/{N_TESTS}={threshold:.6f}, n_bootstrap={n_bootstrap}")

    print("\nComputing overnight (close-to-open) returns...")
    overnight = compute_overnight_returns(data)
    print(f"  {len(overnight)} ticker-day observations")

    print("Computing turn-of-month returns...")
    tom_raw = compute_turn_of_month_returns(data)
    print(f"  {len(tom_raw)} ticker-day observations (raw window return, before own-ticker baseline)")

    daily = compute_daily_returns(data)
    tom = _apply_own_ticker_baseline(tom_raw, daily, split_date)
    print(f"  {len(tom)} ticker-day observations after subtracting each ticker's own "
          f"period baseline daily return (the actual tested quantity -- see module docstring)")

    # Round-trip slippage, applied to EVERY observation (not just a rare
    # flagged subset -- both effects trade every session), matching how
    # backtest/engine.py's run_backtest() computes net_return_pct from
    # raw_return_pct for every other signal in this project.
    round_trip_cost_pct = 2 * SLIPPAGE_PCT * 100
    print(f"\nApplying round-trip slippage ({round_trip_cost_pct:.3f}%) to every observation...")
    overnight = overnight.assign(edge_pct=overnight["edge_pct"] - round_trip_cost_pct)
    tom = tom.assign(edge_pct=tom["edge_pct"] - round_trip_cost_pct)

    all_rows = []
    for effect_name, edges in (("overnight_drift", overnight), ("turn_of_month", tom)):
        print(f"\n{'=' * 78}")
        print(f"{effect_name}")
        print("=" * 78)
        rows = _significance_table(effect_name, edges, split_date, n_bootstrap, threshold)
        if not rows:
            print("No observations -- nothing to test.")
            continue
        table = pd.DataFrame(rows)[RESULT_COLUMNS]
        all_rows.extend(rows)

        primary = table.loc[table["primary"]]
        print("\n--- PRIMARY rows (the only ones that count as evidence) ---")
        print(primary.to_string(index=False))

        print("\n--- Full sensitivity grid (weightings x block lengths; NOT independent tests) ---")
        print(table.to_string(index=False))

        confirmation_primary = table.loc[table["period"].eq("confirmation") & table["primary"]]
        passed = confirmation_primary.loc[confirmation_primary["significant"]]
        verdict = (
            "CONFIRMATION-PERIOD PRIMARY ROW SIGNIFICANT"
            if not passed.empty
            else "No confirmation-period primary row cleared the corrected threshold."
        )
        print(f"\n>>> {effect_name}: {verdict}")

    print(f"\n{'=' * 78}")
    print(
        f"Reminder: a confirmation-period primary row clearing alpha/{N_TESTS} is ONE piece of\n"
        "evidence from ONE historical sample of ONE universe, on adjusted yfinance data\n"
        "that is explicitly NOT point-in-time. It is not a validated edge, and nothing\n"
        "here authorizes any trading. Overnight drift specifically has recent published\n"
        "evidence (2026) that the effect may already be decaying toward zero net of costs."
    )


if __name__ == "__main__":
    main()
