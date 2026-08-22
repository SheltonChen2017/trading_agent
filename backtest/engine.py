"""
Walk-forward backtest for the dip/up scanner.

Reuses scan_dips_and_ups() as-of every historical date in the universe —
the exact same function that runs "live" — so whatever the backtest scores
is exactly what the scanner would have flagged in real time. This is the
one property that makes the numbers here trustworthy: no separate
backtest-only signal logic to drift out of sync.

For every flagged signal, we look `hold_days` trading days forward and
measure the close-to-close return, minus a simulated round-trip slippage
cost. The default hypothesis tested is "go long every flagged signal" —
for a dip that means betting on mean reversion, for an up that means
betting on momentum continuation. Shorting is a different strategy and
isn't modeled here.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Callable

import numpy as np
import pandas as pd

from data.research_statistics import bonferroni_threshold

from config import (
    BACKTEST_HOLD_DAYS,
    HORIZON_LABELS,
    HORIZON_SWEEP_DAYS,
    RETURN_Z_THRESHOLD,
    ROLLING_WINDOW,
    SLIPPAGE_PCT,
    VOLUME_Z_THRESHOLD,
)
from signals.scanner import scan_dips_and_ups
from market_analytics import run_baseline_forward_returns  # noqa: F401 (re-exported for callers)

RESULT_COLUMNS = [
    "ticker", "date", "direction", "return_zscore", "volume_zscore",
    "entry_price", "exit_price", "raw_return_pct", "net_return_pct", "win",
]

# Every function below defaults to scan_dips_and_ups (the original z-score
# dip/up scanner) for 100% backward compatibility. Pass a different
# `scan_fn` (see signals/momentum.py, relative.py, breakout.py, pead.py)
# plus `scan_kwargs` with whatever parameters THAT function needs — any
# scan function is usable here as long as it returns a DataFrame with the
# same column contract as scan_dips_and_ups (ticker, date, close,
# return_pct, return_zscore, volume_zscore, direction), which is what lets
# a brand-new signal reuse every backtest/baseline/market/out-of-sample/
# significance tool in this file completely unchanged.
# return_z_threshold/volume_z_threshold are only meaningful for the
# default scanner and are ignored when a custom scan_fn+scan_kwargs pair
# is supplied.


def _resolve_scan_kwargs(
    scan_fn: Callable,
    scan_kwargs: dict | None,
    return_z_threshold: float,
    volume_z_threshold: float,
) -> dict:
    if scan_kwargs is not None:
        return scan_kwargs
    if scan_fn is scan_dips_and_ups:
        return {"return_z_threshold": return_z_threshold, "volume_z_threshold": volume_z_threshold}
    return {}


def run_backtest(
    data: dict[str, pd.DataFrame],
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Walk every date in the universe, run the live scanner as-of that date,
    and score each flagged signal against its actual forward return.

    Returns one row per flagged signal that had enough forward data to
    evaluate, with columns: RESULT_COLUMNS (see above). `net_return_pct`
    already has simulated slippage deducted; `win` is True when
    net_return_pct > 0 under the "go long the signal" hypothesis.

    `entry_timing`:
      - "next_open" (default since 2026-07-28, GPT review): enter at the
        NEXT trading day's open, exit at the open `hold_days` trading
        days after that — signal known after day t's close -> act at day
        t+1's open, a conservative, actually-executable assumption. This
        used to be opt-in with "same_close" as the default, which made it
        easy for new research to silently use an unrealistic entry
        timing; now the reverse is true.
      - "same_close": enter AND exit at the signal date's own close — the
        timing used by every finding registered before 2026-07 (now
        legacy). NOT realistically executable for signals that need that
        day's own completed close/volume to compute (true of every
        signal here) — you can't know the finalized signal early enough
        to also transact at that exact close, short of a market-on-close
        order submitted blind to the final print. Only pass this
        explicitly to reproduce a pre-existing legacy result; do not use
        it for new research. Any "confirmed" finding still resting only
        on "same_close" evidence has NOT been revalidated under
        executable timing — see [[project_execution_realism_gaps]] in
        memory, and do not treat a "same_close"-only result as equivalent
        to a "next_open" one when comparing conclusions.
      - "same_day_open_to_close": enter at TODAY's own open, exit at
        TODAY's own close (e.g. signals/overnight_gap.py -- a signal
        known at the open, like an overnight-gap reversal, rather than
        after that day's own close). `hold_days` is IGNORED in this mode
        (entry and exit are always the same row) -- pass any value. Use
        this explicitly for a signal that's genuinely known at the open;
        do not rely on the general "next_open" default for it.

        UNRESOLVED REALISM GAP (GPT review, 2026-07-31, same class of
        issue as "same_close" above, not yet fixed): the signal is
        computed FROM this same row's `open` column, then this backtest
        also enters AT that exact `open` price -- the official opening
        print cannot both reveal the signal (so you know to act on it)
        AND remain available to transact at via an order submitted after
        seeing it. A real overnight-gap strategy would need either
        intraday/post-open execution data (this project only has daily
        OHLC) to model the first ACTUALLY-executable post-open price, or
        a genuine pre-open indicative-price/market-on-open process (this
        project has no pre-market/indicative-price feed either). Treat
        any "same_day_open_to_close" result as a look-ahead-optimistic
        upper bound, not an executable one, until one of those is built
        -- do not promote a finding resting only on this timing to
        confirmed/production-authoritative.
    """
    if entry_timing not in ("same_close", "next_open", "same_day_open_to_close"):
        raise ValueError(
            f"entry_timing must be 'same_close', 'next_open', or 'same_day_open_to_close', got {entry_timing!r}"
        )

    kwargs = _resolve_scan_kwargs(scan_fn, scan_kwargs, return_z_threshold, volume_z_threshold)
    all_dates = sorted(set().union(*(df.index for df in data.values())))
    # Skip the front of history where no ticker has enough trailing data
    # yet, and the tail where no ticker has enough forward data — cheap
    # early exit, scan_fn would just return empty anyway. This is a
    # heuristic sized for the default scanner (ROLLING_WINDOW) — a slower
    # signal (e.g. momentum, 52-week breakout) needing more history simply
    # returns empty for the earlier dates in this range too; correctness
    # isn't affected, just a few wasted no-op scan calls.
    if entry_timing == "next_open":
        tail_buffer = hold_days + 1
    elif entry_timing == "same_day_open_to_close":
        tail_buffer = 0  # exit is the SAME row as entry -- no forward data needed at all
    else:
        tail_buffer = hold_days
    usable_dates = all_dates[ROLLING_WINDOW : len(all_dates) - tail_buffer] if tail_buffer > 0 else all_dates[ROLLING_WINDOW:]

    rows = []
    for as_of in usable_dates:
        signals = scan_fn(data, as_of=as_of, **kwargs)
        if signals.empty:
            continue

        for _, sig in signals.iterrows():
            df = data[sig["ticker"]]
            if as_of not in df.index:
                continue
            idx = df.index.get_loc(as_of)

            if entry_timing == "same_close":
                entry_idx, exit_idx, entry_col, exit_col = idx, idx + hold_days, "close", "close"
            elif entry_timing == "same_day_open_to_close":
                entry_idx, exit_idx, entry_col, exit_col = idx, idx, "open", "close"
            else:  # next_open
                entry_idx, exit_idx, entry_col, exit_col = idx + 1, idx + 1 + hold_days, "open", "open"

            if exit_idx >= len(df):
                continue  # not enough forward history to score this one yet

            entry_price = float(df[entry_col].iloc[entry_idx])
            exit_price = float(df[exit_col].iloc[exit_idx])
            raw_return_pct = (exit_price - entry_price) / entry_price * 100
            # Round-trip slippage: paid once entering, once exiting.
            net_return_pct = raw_return_pct - 2 * slippage_pct * 100

            rows.append(
                {
                    "ticker": sig["ticker"],
                    "date": sig["date"],
                    "direction": sig["direction"],
                    "return_zscore": sig["return_zscore"],
                    "volume_zscore": sig["volume_zscore"],
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "raw_return_pct": round(raw_return_pct, 3),
                    "net_return_pct": round(net_return_pct, 3),
                    "win": net_return_pct > 0,
                }
            )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    return pd.DataFrame(rows, columns=RESULT_COLUMNS).sort_values("date").reset_index(drop=True)


SUMMARY_COLUMNS = [
    "direction", "count", "win_rate_pct", "mean_net_return_pct", "median_net_return_pct",
    "mean_return_zscore", "mean_volume_zscore",
]


def summarize_backtest(results: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate backtest results by signal direction: count, win rate, mean
    and median net return, plus the average return/volume z-score of the
    signals in that group (context on how unusual the underlying moves
    were — this doesn't depend on hold period, unlike the return stats).
    An empty/near-50% win rate on synthetic random data is the EXPECTED,
    correct result — it means the pipeline isn't conjuring fake alpha out
    of noise. Only real historical data can tell you whether the scanner
    has genuine edge.
    """
    if results.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = results.groupby("direction")
    summary = grouped.agg(
        count=("win", "size"),
        win_rate_pct=("win", lambda s: round(s.mean() * 100, 1)),
        mean_net_return_pct=("net_return_pct", lambda s: round(s.mean(), 3)),
        median_net_return_pct=("net_return_pct", lambda s: round(s.median(), 3)),
        mean_return_zscore=("return_zscore", lambda s: round(s.mean(), 2)),
        mean_volume_zscore=("volume_zscore", lambda s: round(s.mean(), 2)),
    ).reset_index()

    return summary[SUMMARY_COLUMNS]


def run_multi_horizon_backtest(
    data: dict[str, pd.DataFrame],
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> dict[int, pd.DataFrame]:
    """
    Run run_backtest() once per hold period in `hold_days_options`, so you
    can compare a signal's win rate/return across several exit timings
    (e.g. 1 day vs 1 week vs 1 month) instead of trusting one arbitrarily
    chosen BACKTEST_HOLD_DAYS. Returns {hold_days: results_df}.
    """
    return {
        hold_days: run_backtest(
            data,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
            entry_timing=entry_timing,
        )
        for hold_days in hold_days_options
    }


def summarize_multi_horizon(
    results_by_horizon: dict[int, pd.DataFrame], entry_timing: str | None = None,
) -> pd.DataFrame:
    """
    Combine summarize_backtest() across every horizon in
    run_multi_horizon_backtest()'s output into one table, with
    `hold_days`/`horizon` columns so results can be compared side by side.

    `entry_timing`: this function only processes already-computed
    results, so it can't know what timing was used to generate them --
    pass whatever was given to run_multi_horizon_backtest() to stamp it
    into the output for audit purposes (GPT review, 2026-07-29: report
    metadata should make timing assumptions auditable, not just correct).
    Omitted (None) leaves the column out entirely, for callers that don't
    need it.
    """
    columns = ["hold_days", "horizon"] + (["entry_timing"] if entry_timing is not None else []) + SUMMARY_COLUMNS
    rows = []
    for hold_days, results in results_by_horizon.items():
        summary = summarize_backtest(results)
        if summary.empty:
            continue
        if entry_timing is not None:
            summary.insert(0, "entry_timing", entry_timing)
        summary.insert(0, "horizon", HORIZON_LABELS.get(hold_days, f"{hold_days}d"))
        summary.insert(0, "hold_days", hold_days)
        rows.append(summary)

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.concat(rows, ignore_index=True)[columns]


def _return_stats(returns: pd.Series) -> dict:
    if returns.empty:
        return {"count": 0, "win_rate_pct": None, "mean_net_return_pct": None, "median_net_return_pct": None}
    return {
        "count": int(returns.size),
        "win_rate_pct": round((returns > 0).mean() * 100, 1),
        "mean_net_return_pct": round(returns.mean(), 3),
        "median_net_return_pct": round(returns.median(), 3),
    }


def compare_signal_to_baseline(
    data: dict[str, pd.DataFrame],
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    For each hold period, compare the flagged signals' returns against the
    baseline "hold this stock any day" returns, per direction. The key
    output is `edge_vs_baseline_pct` = signal mean return - baseline mean
    return: positive means the scanner is adding something beyond the
    universe's general drift over the test window; near zero means an
    apparent edge is likely just that drift, not real signal.
    """
    rows = []
    for hold_days in hold_days_options:
        results = run_backtest(
            data,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
            entry_timing=entry_timing,
        )
        baseline = run_baseline_forward_returns(
            data, hold_days=hold_days, slippage_pct=slippage_pct, entry_timing=entry_timing,
        )
        baseline_stats = _return_stats(baseline["net_return_pct"])

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else results
            signal_stats = _return_stats(subset["net_return_pct"] if not subset.empty else pd.Series(dtype=float))

            edge = None
            if signal_stats["mean_net_return_pct"] is not None and baseline_stats["mean_net_return_pct"] is not None:
                edge = round(signal_stats["mean_net_return_pct"] - baseline_stats["mean_net_return_pct"], 3)

            rows.append(
                {
                    "hold_days": hold_days,
                    "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                    "direction": direction,
                    "entry_timing": entry_timing,
                    "signal_count": signal_stats["count"],
                    "signal_win_rate_pct": signal_stats["win_rate_pct"],
                    "signal_mean_return_pct": signal_stats["mean_net_return_pct"],
                    "baseline_count": baseline_stats["count"],
                    "baseline_win_rate_pct": baseline_stats["win_rate_pct"],
                    "baseline_mean_return_pct": baseline_stats["mean_net_return_pct"],
                    "edge_vs_baseline_pct": edge,
                }
            )

    return pd.DataFrame(rows)


PER_TICKER_COMPARISON_COLUMNS = [
    "hold_days", "horizon", "direction", "entry_timing", "signal_count",
    "signal_mean_return_pct", "mean_own_ticker_baseline_pct",
    "mean_edge_vs_own_ticker_pct", "pct_signals_beating_own_ticker_baseline",
]


def _signals_with_own_ticker_baseline(
    data: dict[str, pd.DataFrame],
    hold_days: int,
    slippage_pct: float,
    return_z_threshold: float,
    volume_z_threshold: float,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Per-signal detail shared by compare_signal_to_baseline_per_ticker()
    and out_of_sample_baseline_comparison(): run_backtest()'s output
    annotated with each signal's own ticker's any-day baseline return and
    the edge over it (own_ticker_baseline_pct, edge_vs_own_ticker_pct).
    """
    results = run_backtest(
        data,
        hold_days=hold_days,
        slippage_pct=slippage_pct,
        return_z_threshold=return_z_threshold,
        volume_z_threshold=volume_z_threshold,
        scan_fn=scan_fn,
        scan_kwargs=scan_kwargs,
        entry_timing=entry_timing,
    )
    baseline = run_baseline_forward_returns(data, hold_days=hold_days, slippage_pct=slippage_pct, entry_timing=entry_timing)
    baseline_mean_by_ticker = (
        baseline.groupby("ticker")["net_return_pct"].mean() if not baseline.empty else pd.Series(dtype=float)
    )

    if not results.empty:
        results = results.copy()
        results["own_ticker_baseline_pct"] = results["ticker"].map(baseline_mean_by_ticker)
        results["edge_vs_own_ticker_pct"] = results["net_return_pct"] - results["own_ticker_baseline_pct"]

    return results


def _split_data_by_date(data: dict[str, pd.DataFrame], split_date) -> tuple[dict, dict]:
    """Slice each ticker's own price history at `split_date`: discovery
    keeps rows on/before it, confirmation keeps rows after."""
    discovery = {ticker: df[df.index <= split_date] for ticker, df in data.items()}
    confirmation = {ticker: df[df.index > split_date] for ticker, df in data.items()}
    return discovery, confirmation


def _out_of_sample_own_ticker_detail(
    data: dict[str, pd.DataFrame],
    discovery_frac: float,
    hold_days: int,
    slippage_pct: float,
    return_z_threshold: float,
    volume_z_threshold: float,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Per-signal detail (run_backtest() output + own-ticker baseline edge),
    already split into (discovery, confirmation) — with the baseline
    computed SEPARATELY from each period's own price history, unlike
    _signals_with_own_ticker_baseline() (which computes one baseline over
    the FULL window and is fine for compare_signal_to_baseline_per_ticker(),
    where no period separation is being claimed).

    Reusing one full-window baseline for both periods would let a
    discovery-period signal's edge be measured against a baseline that
    already reflects the confirmation period's own returns (and vice
    versa) — not trading look-ahead (this is a comparison statistic, not a
    model feature), but it blurs the discovery/confirmation separation
    every out_of_sample_* function exists to enforce, and can distort the
    estimated edge if a ticker's typical return shifts between regimes.
    The signals themselves (entry/exit prices, dates) are unaffected —
    only which baseline mean gets subtracted changes.
    """
    results = run_backtest(
        data, hold_days=hold_days, slippage_pct=slippage_pct,
        return_z_threshold=return_z_threshold, volume_z_threshold=volume_z_threshold,
        scan_fn=scan_fn, scan_kwargs=scan_kwargs, entry_timing=entry_timing,
    )
    if results.empty:
        return results, results

    split_date = _discovery_split_date(data, discovery_frac)
    discovery_data, confirmation_data = _split_data_by_date(data, split_date)
    discovery_results, confirmation_results = _split_by_date(results, split_date)

    out = []
    for period_results, period_data in ((discovery_results, discovery_data), (confirmation_results, confirmation_data)):
        if period_results.empty:
            out.append(period_results)
            continue
        baseline = run_baseline_forward_returns(period_data, hold_days=hold_days, slippage_pct=slippage_pct, entry_timing=entry_timing)
        baseline_mean_by_ticker = (
            baseline.groupby("ticker")["net_return_pct"].mean() if not baseline.empty else pd.Series(dtype=float)
        )
        period_results = period_results.copy()
        period_results["own_ticker_baseline_pct"] = period_results["ticker"].map(baseline_mean_by_ticker)
        period_results["edge_vs_own_ticker_pct"] = period_results["net_return_pct"] - period_results["own_ticker_baseline_pct"]
        out.append(period_results)

    return tuple(out)


def compare_signal_to_baseline_per_ticker(
    data: dict[str, pd.DataFrame],
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Like compare_signal_to_baseline(), but each flagged signal is matched
    against ITS OWN ticker's any-day baseline, not the whole universe
    pooled together.

    Pooling risks a stock-composition confound: if flagged signals cluster
    on naturally higher- (or lower-) drift stocks, a pooled baseline that
    also mixes in every other name's typical day can make the signal look
    better or worse than it really is, for reasons that have nothing to do
    with the signal's timing. Matching each signal only to its own stock's
    baseline isolates that timing effect — "did buying THIS stock on its
    flagged day beat buying THIS SAME stock on an arbitrary day?" — which
    is the more rigorous comparison.

    Returns one row per (hold_days, direction) with:
      - signal_mean_return_pct: average return of the flagged signals
      - mean_own_ticker_baseline_pct: average, across those same signals,
        of EACH one's own ticker's any-day baseline return
      - mean_edge_vs_own_ticker_pct: mean of each signal's OWN edge
        (its return minus its own ticker's baseline) — the primary number
      - pct_signals_beating_own_ticker_baseline: what fraction of
        individual signals beat their own ticker's baseline (useful
        alongside the mean, which one outlier stock could otherwise skew)
    """
    rows = []
    for hold_days in hold_days_options:
        results = _signals_with_own_ticker_baseline(
            data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
            entry_timing=entry_timing,
        )

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else pd.DataFrame()

            if subset.empty:
                rows.append(
                    {
                        "hold_days": hold_days,
                        "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                        "direction": direction,
                        "entry_timing": entry_timing,
                        "signal_count": 0,
                        "signal_mean_return_pct": None,
                        "mean_own_ticker_baseline_pct": None,
                        "mean_edge_vs_own_ticker_pct": None,
                        "pct_signals_beating_own_ticker_baseline": None,
                    }
                )
                continue

            rows.append(
                {
                    "hold_days": hold_days,
                    "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                    "direction": direction,
                    "entry_timing": entry_timing,
                    "signal_count": len(subset),
                    "signal_mean_return_pct": round(subset["net_return_pct"].mean(), 3),
                    "mean_own_ticker_baseline_pct": round(subset["own_ticker_baseline_pct"].mean(), 3),
                    "mean_edge_vs_own_ticker_pct": round(subset["edge_vs_own_ticker_pct"].mean(), 3),
                    "pct_signals_beating_own_ticker_baseline": round(
                        (subset["edge_vs_own_ticker_pct"] > 0).mean() * 100, 1
                    ),
                }
            )

    if not rows:
        return pd.DataFrame(columns=PER_TICKER_COMPARISON_COLUMNS)

    return pd.DataFrame(rows)[PER_TICKER_COMPARISON_COLUMNS]


MARKET_COMPARISON_COLUMNS = [
    "hold_days", "horizon", "direction", "entry_timing", "signal_count",
    "signal_mean_return_pct", "mean_market_return_pct",
    "mean_edge_vs_market_pct", "pct_signals_beating_market",
]


def compute_benchmark_forward_returns(
    benchmark_df: pd.DataFrame,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    entry_timing: str = "next_open",
) -> pd.Series:
    """
    Forward return of a single reference series (e.g. SPY, QQQ) over
    `hold_days`, indexed by the ORIGINAL signal date -- the same math as
    run_baseline_forward_returns(), applied to one benchmark instead of a
    universe of stocks. Used to check whether a signal beat the broad
    market on the EXACT SAME days it fired, the strictest baseline of the
    three this project computes (own history -> own ticker's baseline ->
    the whole market on that specific date).

    `entry_timing` MUST match whatever was passed to run_backtest() for
    the signal side of the comparison -- this used to always compute a
    same-close-to-close return regardless of what timing the signal
    itself used, so a next_open signal (enter next day's open, exit
    `hold_days` opens later) was compared against a same-close-to-close
    benchmark return indexed by the signal date -- different entry
    price, different exit price, and a shifted holding window entirely
    (GPT review, 2026-07-29). Mirrors run_baseline_forward_returns()'s
    three modes exactly; the returned Series stays indexed by the
    ORIGINAL row date in every mode so it still maps onto signal rows by
    that date regardless of when the benchmark leg itself actually
    starts/ends.
    """
    if entry_timing not in ("same_close", "next_open", "same_day_open_to_close"):
        raise ValueError(
            f"entry_timing must be 'same_close', 'next_open', or 'same_day_open_to_close', got {entry_timing!r}"
        )

    if entry_timing == "same_close":
        entry_price, forward_price = benchmark_df["close"], benchmark_df["close"].shift(-hold_days)
    elif entry_timing == "same_day_open_to_close":
        entry_price, forward_price = benchmark_df["open"], benchmark_df["close"]
    else:  # next_open
        entry_price, forward_price = benchmark_df["open"].shift(-1), benchmark_df["open"].shift(-(1 + hold_days))
    raw_return_pct = (forward_price - entry_price) / entry_price * 100
    net_return_pct = raw_return_pct - 2 * slippage_pct * 100
    return net_return_pct.dropna()


def _signals_with_market_edge(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    hold_days: int,
    slippage_pct: float,
    return_z_threshold: float,
    volume_z_threshold: float,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Per-signal detail shared by compare_signal_to_market_index() and
    out_of_sample_market_comparison(): run_backtest()'s output annotated
    with what the benchmark returned starting that EXACT signal date
    (market_return_pct, edge_vs_market_pct). Signals whose date falls
    outside the benchmark's own history are dropped, not miscounted.

    `entry_timing` is passed to BOTH run_backtest() (the signal leg) and
    compute_benchmark_forward_returns() (the benchmark leg) -- they must
    always match (GPT review, 2026-07-29; see compute_benchmark_forward_
    returns()'s docstring for what went wrong when they didn't).
    """
    results = run_backtest(
        data,
        hold_days=hold_days,
        slippage_pct=slippage_pct,
        return_z_threshold=return_z_threshold,
        volume_z_threshold=volume_z_threshold,
        scan_fn=scan_fn,
        scan_kwargs=scan_kwargs,
        entry_timing=entry_timing,
    )
    benchmark_returns = compute_benchmark_forward_returns(
        benchmark_df, hold_days=hold_days, slippage_pct=slippage_pct, entry_timing=entry_timing,
    )

    if not results.empty:
        results = results.copy()
        results["market_return_pct"] = results["date"].map(benchmark_returns)
        results["edge_vs_market_pct"] = results["net_return_pct"] - results["market_return_pct"]
        results = results.dropna(subset=["market_return_pct"])

    return results


def compare_signal_to_market_index(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    For each hold period, match every flagged signal to what the market
    benchmark (e.g. SPY) itself returned starting that EXACT same date,
    not just the benchmark's average over the whole test window. This
    answers "did this signal beat just buying the index that same day?" —
    a stricter, date-matched version of compare_signal_to_baseline().
    Signals whose date falls outside the benchmark's own history (e.g. a
    ticker with a longer lookback than the benchmark data provided) are
    dropped rather than silently miscounted.
    """
    rows = []
    for hold_days in hold_days_options:
        results = _signals_with_market_edge(
            data, benchmark_df, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
            entry_timing=entry_timing,
        )

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else pd.DataFrame()

            if subset.empty:
                rows.append(
                    {
                        "hold_days": hold_days,
                        "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                        "direction": direction,
                        "entry_timing": entry_timing,
                        "signal_count": 0,
                        "signal_mean_return_pct": None,
                        "mean_market_return_pct": None,
                        "mean_edge_vs_market_pct": None,
                        "pct_signals_beating_market": None,
                    }
                )
                continue

            rows.append(
                {
                    "hold_days": hold_days,
                    "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                    "direction": direction,
                    "entry_timing": entry_timing,
                    "signal_count": len(subset),
                    "signal_mean_return_pct": round(subset["net_return_pct"].mean(), 3),
                    "mean_market_return_pct": round(subset["market_return_pct"].mean(), 3),
                    "mean_edge_vs_market_pct": round(subset["edge_vs_market_pct"].mean(), 3),
                    "pct_signals_beating_market": round((subset["edge_vs_market_pct"] > 0).mean() * 100, 1),
                }
            )

    if not rows:
        return pd.DataFrame(columns=MARKET_COMPARISON_COLUMNS)

    return pd.DataFrame(rows)[MARKET_COMPARISON_COLUMNS]


# --- Out-of-sample validation --------------------------------------------
# Everything above can be (and has been) run repeatedly on the SAME
# historical window while hunting for an interesting basket/direction/
# horizon combination — which means a "finding" might just be that
# window's noise, not real edge (see README's multiple-comparisons note).
# The functions below split signals in time into an earlier DISCOVERY
# period and a later CONFIRMATION (holdout) period that was never used to
# identify anything, and report both separately. A real edge should look
# similar in both; one that's strong in discovery and weak/flipped in
# confirmation was very likely noise.
#
# Note this only ever uses TRAILING data at every point (rolling stats,
# backtest scoring) — splitting the already-computed signals by date
# afterward doesn't introduce any look-ahead; it's just partitioning
# results that were already computed causally.

OUT_OF_SAMPLE_PERIODS = ["discovery", "confirmation"]


def _discovery_split_date(data: dict[str, pd.DataFrame], discovery_frac: float):
    """
    The calendar date marking the boundary between the discovery period
    (the earlier `discovery_frac` of the full date range) and the
    confirmation/holdout period — computed from the FULL universe's date
    range, not from where signals happen to fall. Signals are sparse and
    clustered, so deriving the split from signal dates instead would let a
    handful of them skew where the boundary actually lands.
    """
    all_dates = sorted(set().union(*(df.index for df in data.values())))
    split_idx = max(0, min(len(all_dates) - 1, int(len(all_dates) * discovery_frac)))
    return all_dates[split_idx]


def _split_by_date(df: pd.DataFrame, split_date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a results-like DataFrame (must have a `date` column) into
    signals on/before `split_date` (discovery) and after (confirmation).

    KNOWN LIMITATION -- no embargo (independent review, 2026-07-29). The
    boundary itself is clean (`<=` vs `>`, so no row lands in both), but a
    signal firing ON `split_date` has its forward return measured over the
    following `hold_days`, which fall INSIDE the confirmation period. The
    last ~`hold_days` of discovery and the first ~`hold_days` of
    confirmation therefore share overlapping return windows, so the two
    sets are not perfectly independent. Standard walk-forward practice
    embargoes `hold_days` around the split to remove this.

    Deliberately NOT changed here: doing so would shift every number in
    `assistant/research_findings.json` (a versioned evidence record), which
    is a research-methodology decision, not a bug fix. The practical
    magnitude is small -- roughly `hold_days` dates out of a several-hundred
    date confirmation period -- and it biases toward discovery and
    confirmation AGREEING, so it cannot manufacture a rejection. Every
    finding recorded so far is a rejection or a risk-shape result, so no
    current verdict depends on it. Add an embargo before trusting any
    FUTURE confirmation that reports a positive edge."""
    if df.empty:
        return df, df
    discovery = df[df["date"] <= split_date]
    confirmation = df[df["date"] > split_date]
    return discovery, confirmation


def out_of_sample_backtest(
    data: dict[str, pd.DataFrame],
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Out-of-sample version of summarize_backtest(): splits run_backtest()'s
    signals by date into a discovery period (the earlier `discovery_frac`
    of the date range) and a confirmation/holdout period, and reports win
    rate / mean return separately for each, by direction.
    """
    results = run_backtest(
        data,
        hold_days=hold_days,
        slippage_pct=slippage_pct,
        return_z_threshold=return_z_threshold,
        volume_z_threshold=volume_z_threshold,
        scan_fn=scan_fn,
        scan_kwargs=scan_kwargs,
        entry_timing=entry_timing,
    )
    columns = ["period", "entry_timing"] + SUMMARY_COLUMNS
    if results.empty:
        return pd.DataFrame(columns=columns)

    split_date = _discovery_split_date(data, discovery_frac)
    discovery, confirmation = _split_by_date(results, split_date)
    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        summary = summarize_backtest(subset)
        if summary.empty:
            continue
        summary.insert(0, "entry_timing", entry_timing)
        summary.insert(0, "period", period)
        rows.append(summary)

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


OUT_OF_SAMPLE_BASELINE_COLUMNS = [
    "period", "direction", "entry_timing", "signal_count",
    "mean_edge_vs_own_ticker_pct", "pct_signals_beating_own_ticker_baseline",
]


def out_of_sample_baseline_comparison(
    data: dict[str, pd.DataFrame],
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Out-of-sample version of compare_signal_to_baseline_per_ticker(): the
    per-ticker-matched edge, split into a discovery period and a
    confirmation (holdout) period never used to find anything — including
    the baseline itself, computed SEPARATELY per period (see
    _out_of_sample_own_ticker_detail()).
    """
    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if discovery.empty and confirmation.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_BASELINE_COLUMNS)

    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        for direction in ("dip", "up"):
            d = subset[subset["direction"] == direction] if not subset.empty else pd.DataFrame()
            if d.empty:
                continue
            rows.append(
                {
                    "period": period,
                    "direction": direction,
                    "entry_timing": entry_timing,
                    "signal_count": len(d),
                    "mean_edge_vs_own_ticker_pct": round(d["edge_vs_own_ticker_pct"].mean(), 3),
                    "pct_signals_beating_own_ticker_baseline": round((d["edge_vs_own_ticker_pct"] > 0).mean() * 100, 1),
                }
            )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_BASELINE_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_BASELINE_COLUMNS]


OUT_OF_SAMPLE_MARKET_COLUMNS = [
    "period", "direction", "entry_timing", "signal_count",
    "mean_edge_vs_market_pct", "pct_signals_beating_market",
]


def out_of_sample_market_comparison(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Out-of-sample version of compare_signal_to_market_index(): the
    market-matched edge, split into a discovery period and a confirmation
    (holdout) period never used to find anything.
    """
    detailed = _signals_with_market_edge(
        data, benchmark_df, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if detailed.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_MARKET_COLUMNS)

    split_date = _discovery_split_date(data, discovery_frac)
    discovery, confirmation = _split_by_date(detailed, split_date)
    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        for direction in ("dip", "up"):
            d = subset[subset["direction"] == direction] if not subset.empty else pd.DataFrame()
            if d.empty:
                continue
            rows.append(
                {
                    "period": period,
                    "direction": direction,
                    "entry_timing": entry_timing,
                    "signal_count": len(d),
                    "mean_edge_vs_market_pct": round(d["edge_vs_market_pct"].mean(), 3),
                    "pct_signals_beating_market": round((d["edge_vs_market_pct"] > 0).mean() * 100, 1),
                }
            )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_MARKET_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_MARKET_COLUMNS]


# --- Statistical significance ---------------------------------------------
# All the comparison functions above report a MEAN edge, but a mean alone
# doesn't say whether that edge is distinguishable from noise. These
# functions estimate that directly, via bootstrap resampling (not a
# parametric t-test) since trade-return distributions are often skewed/
# fat-tailed rather than normal, and correct for how many things were
# tested at once — with N basket/direction cells tested simultaneously, a
# couple are expected to look "significant" by chance alone even with zero
# real edge anywhere unless the threshold accounts for that.

def bootstrap_edge_significance(edge_values: pd.Series, n_bootstrap: int = 2000, seed: int = 0) -> dict:
    """
    Bootstrap the mean of `edge_values` (e.g. a basket/direction's
    edge_vs_own_ticker_pct or edge_vs_market_pct values) to estimate a 95%
    confidence interval and a two-sided p-value against the null
    hypothesis that the true mean edge is zero.

    Returns {n, mean, ci_low, ci_high, p_value}. p_value/CI are None when
    there are too few observations (<5) to bootstrap meaningfully.
    """
    values = pd.Series(edge_values).dropna().to_numpy()
    if len(values) < 5:
        return {"n": len(values), "mean": None, "ci_low": None, "ci_high": None, "p_value": None}

    rng = np.random.default_rng(seed)
    boot_means = np.array(
        [rng.choice(values, size=len(values), replace=True).mean() for _ in range(n_bootstrap)]
    )
    mean = values.mean()
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    # Two-sided p-value: how much of the bootstrap distribution sits on
    # the opposite side of zero from the observed mean, doubled.
    p_value = min(1.0, 2 * min((boot_means <= 0).mean(), (boot_means >= 0).mean()))

    return {
        "n": len(values),
        "mean": round(float(mean), 3),
        "ci_low": round(float(ci_low), 3),
        "ci_high": round(float(ci_high), 3),
        "p_value": round(float(p_value), 4),
    }


def bootstrap_edge_significance_by_date(
    edge_values: pd.Series, dates: pd.Series, n_bootstrap: int = 2000, seed: int = 0
) -> dict:
    """
    Like bootstrap_edge_significance(), but resamples whole TRADING DAYS
    at a time (a block/cluster bootstrap), not individual signal rows.

    Signals fired on the same date are often driven by the same
    market-wide move (correlated) — a broad market correction can flag
    dozens of tickers at once. Treating each one as an independent draw,
    the way bootstrap_edge_significance() does, understates the true
    uncertainty: what looks like hundreds of independent observations may
    really be a handful of distinct EVENTS, each replicated across many
    correlated tickers. This resamples by date instead, preserving
    within-day correlation, which is the standard fix for this and gives
    a more honest (typically wider) confidence interval.

    `edge_values` and `dates` must be aligned (same order/index). Returns
    {n, n_dates, mean, ci_low, ci_high, p_value} — `n_dates` (the number
    of distinct trading days signals fired on) is worth checking directly:
    a small n_dates relative to n is a sign the naive row-level bootstrap
    would have been especially misleading for this subset.
    """
    df = pd.DataFrame({"edge": pd.Series(edge_values).to_numpy(), "date": pd.Series(dates).to_numpy()})
    df = df.dropna(subset=["edge"])
    unique_dates = df["date"].unique()

    if len(df) < 5 or len(unique_dates) < 5:
        return {"n": len(df), "n_dates": len(unique_dates), "mean": None, "ci_low": None, "ci_high": None, "p_value": None}

    grouped = {d: g["edge"].to_numpy() for d, g in df.groupby("date")}
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sampled_dates = rng.choice(unique_dates, size=len(unique_dates), replace=True)
        pooled = np.concatenate([grouped[d] for d in sampled_dates])
        boot_means[i] = pooled.mean()

    mean = df["edge"].mean()
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    p_value = min(1.0, 2 * min((boot_means <= 0).mean(), (boot_means >= 0).mean()))

    return {
        "n": len(df),
        "n_dates": int(len(unique_dates)),
        "mean": round(float(mean), 3),
        "ci_low": round(float(ci_low), 3),
        "ci_high": round(float(ci_high), 3),
        "p_value": round(float(p_value), 4),
    }


# Below this many distinct signal dates the moving-block bootstrap is not
# calibrated -- see _block_bootstrap_refusal() for the measurements.
MIN_BLOCK_BOOTSTRAP_DATES = 50

# A raw date count is not enough: the calibration degrades as a block consumes
# more of the available history.  Require enough full blocks that the circular
# resample is not dominated by rotations of the same few long runs.
MIN_BLOCK_BOOTSTRAP_BLOCKS = 10

# How many distinct p-values must fit below the significance threshold before
# a "p < threshold" verdict is a measurement rather than a rounding artifact.
_MIN_RESOLVABLE_STEPS_BELOW_THRESHOLD = 10

# Conventional target used by the approximate MDE reported with each cell.
MIN_DETECTABLE_EFFECT_POWER = 0.80


def _require_positive_int(value, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return int(value)


def recommended_n_bootstrap(
    n_tests: int, alpha: float = 0.05, floor: int = 2000, cap: int = 20000
) -> int:
    """Resamples needed for the p-value to actually resolve `threshold`.

    The percentile bootstrap's p-value is ``2 * min(tail fractions)``, so the
    smallest non-zero value it can EVER return is ``2 / n_bootstrap`` -- 0.001
    at the long-standing default of 2000. Meanwhile Bonferroni pushes the
    threshold down as the run widens: 16 cells gives 0.003125, so only three
    distinct p-values (0.0, 0.001, 0.002) exist below the bar and "significant"
    becomes a near-binary artifact of resampling granularity rather than a
    measurement. At 32 cells the threshold (0.0016) sits nearly ON the floor.

    Scales n_bootstrap so at least `_MIN_RESOLVABLE_STEPS_BELOW_THRESHOLD`
    distinct values fit underneath, never below `floor` (no run gets cheaper
    than the historical default) and never above `cap` (bounded runtime).

    Noted while calibrating the block bootstrap, 2026-07-30: this is a
    resolution limit, not the calibration defect fixed alongside it, and it
    bites hardest in exactly the wide multi-signal scans where the correction
    is strictest.
    """
    n_tests = _require_positive_int(n_tests, name="n_tests")
    floor = _require_positive_int(floor, name="floor")
    cap = _require_positive_int(cap, name="cap")
    if cap < floor:
        raise ValueError(f"cap must be >= floor, got cap={cap}, floor={floor}")
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError(f"alpha must be finite and between 0 and 1, got {alpha!r}")
    threshold = bonferroni_threshold(n_tests, alpha=alpha)
    needed = int(math.ceil(2 * _MIN_RESOLVABLE_STEPS_BELOW_THRESHOLD / threshold))
    return max(floor, min(cap, needed))


def _min_detectable_effect_pct(
    ci_low, ci_high, threshold: float, power: float = MIN_DETECTABLE_EFFECT_POWER
) -> float | None:
    """Approximate smallest true edge detectable with the requested power.

    Reported alongside every verdict so a rejection states what it could
    have seen. Derived from the bootstrap CI's own width: half-width /1.96
    approximates the standard error. A two-sided test at `threshold` and
    target power `power` needs ``z_(1-alpha/2) + z_power`` standard errors.

    Without this, "not significant" reads as "no effect" when it often
    means "this test could not resolve an effect of the size claimed" --
    the failure mode measured across the 2026-07-30 candidate run, where
    the monthly signals' floor was 1.6-5.7%/month against a literature
    claim of ~0.5-1%/month.
    """
    if ci_low is None or ci_high is None:
        return None
    if (
        not math.isfinite(threshold)
        or not 0 < threshold < 1
        or not math.isfinite(power)
        or not 0.5 < power < 1
    ):
        return None
    standard_error = (float(ci_high) - float(ci_low)) / 2 / 1.96
    if not math.isfinite(standard_error) or standard_error <= 0:
        return None
    alpha_critical = float(NormalDist().inv_cdf(1 - threshold / 2))
    power_critical = float(NormalDist().inv_cdf(power))
    return round((alpha_critical + power_critical) * standard_error, 3)


def _block_bootstrap_refusal(n_rows: int, n_dates: int, block_length: int) -> str | None:
    """Why this (n_rows, n_dates, block_length) cannot yield a usable p-value.

    Returns a reason string, or None when the bootstrap may proceed.
    Shared by both block-bootstrap variants so the rule cannot drift apart
    between them.

    Measured on pure noise (true mean edge exactly zero), 2026-07-30:

      shape                       null          false-positive rate @0.05
      400 dates, block 10         independent   0.050   (nominal -- exact)
      400 dates, block 10         factor        0.083
      31 dates,  block 10         independent   0.185   (3.7x nominal)
      31 dates,  block 10         factor        0.265   (5.3x nominal)
      50 dates,  block 5          independent   0.042
      50 dates,  block 10         independent   0.100
      50 dates,  block 20         independent   0.167

    Two findings drive the rules below.

    1. `block_length >= n_dates` is degenerate, not merely coarse. With
       n_blocks_needed == 1, every circular resample is a ROTATION of the
       entire date set -- identical dates, identical values, every draw. So
       boot_means is constant, the CI collapses to zero width, and
       p = 2 * min(0, 1) = 0 for ANY nonzero mean. The previous guard used
       `n_dates < max(5, block_length)`, which is strict, so exact equality
       slipped through. This fired on real project data: a VIX-spike
       discovery cell with block_length=15 and n_dates=15 reported a mean
       edge of +0.013% as "significant" at p=0.0.

    2. Requiring merely 2 blocks is not enough either. The false-positive
       rate degrades continuously as block_length approaches n_dates. Even
       at 50 dates, block lengths 10 and 20 measured 10.0% and 16.7% false
       positives at a nominal 5%, while block 5 (10 full blocks) measured
       4.2%. The guard therefore requires at least 10 full blocks as well
       as 50 dates. Below 50 dates no block length tested was well calibrated
       (3.5x to 6.5x nominal at 31 dates). Refusing is the honest answer
       there: a number that reads as evidence but is wrong 1 time in 5 is
       worse than no number.

    NOTE the direction: this error made significance EASIER, so it never
    manufactured a false REJECTION. Verdicts recorded as rejected are
    unaffected; positive results at small n_dates are the ones to re-check.
    """
    if n_rows < 5 or n_dates < 5:
        return f"too few observations (n={n_rows}, n_dates={n_dates}; need >=5 of each)"
    if n_dates < MIN_BLOCK_BOOTSTRAP_BLOCKS * block_length:
        return (
            f"block_length={block_length} leaves fewer than "
            f"{MIN_BLOCK_BOOTSTRAP_BLOCKS} full blocks across {n_dates} dates; measured "
            "false-positive rates rise sharply when a few long blocks dominate each "
            "circular resample"
        )
    if n_dates < MIN_BLOCK_BOOTSTRAP_DATES:
        return (
            f"only {n_dates} distinct signal dates (need >={MIN_BLOCK_BOOTSTRAP_DATES}); "
            "measured false-positive rate on pure noise is 3.5-6.5x nominal at this sample "
            "size for every block length, so no p-value here would be trustworthy"
        )
    return None


def _prepare_block_bootstrap_inputs(
    edge_values: pd.Series,
    dates: pd.Series,
    *,
    block_length: int,
    n_bootstrap: int,
) -> tuple[pd.DataFrame, int, int]:
    """Validate public parameters and remove unusable edge/date pairs."""

    block_length = _require_positive_int(block_length, name="block_length")
    n_bootstrap = _require_positive_int(n_bootstrap, name="n_bootstrap")
    edges = pd.Series(edge_values).reset_index(drop=True)
    date_values = pd.Series(dates).reset_index(drop=True)
    if len(edges) != len(date_values):
        raise ValueError(
            "edge_values and dates must have the same length, got "
            f"{len(edges)} and {len(date_values)}"
        )
    numeric_edges = pd.to_numeric(edges, errors="coerce")
    df = pd.DataFrame({"edge": numeric_edges, "date": date_values})
    df = df[
        np.isfinite(df["edge"].to_numpy(dtype=float))
        & df["date"].notna().to_numpy()
    ]
    return df, block_length, n_bootstrap


def bootstrap_edge_significance_by_block(
    edge_values: pd.Series, dates: pd.Series, block_length: int, n_bootstrap: int = 2000, seed: int = 0
) -> dict:
    """
    Like bootstrap_edge_significance_by_date(), but resamples BLOCKS of
    `block_length` consecutive trading dates instead of independent
    single dates — accounts for SERIAL dependence across nearby dates,
    which by-date resampling alone still misses. Adjacent trading days
    aren't independent when hold_days > 1 (their forward-return windows
    overlap), when market regimes persist for stretches, or when a
    cross-sectional signal (e.g. momentum) has slow turnover and keeps
    flagging the same tickers for weeks. By-date resampling fixes the
    WITHIN-day correlation (see bootstrap_edge_significance_by_date) but
    still treats each day as an independent draw, which understates
    uncertainty when nearby days are themselves correlated.

    Uses a circular moving-block bootstrap: unique dates are treated as a
    ring (wrapping from the last date back to the first) so every date
    has an equal chance of starting a block, avoiding under-representing
    dates near the edges of the sample.

    There's no universally correct `block_length` — it should be at least
    the signal's hold_days (the most direct source of serial dependence,
    from overlapping return windows), but the right value also depends on
    how persistent the signal's own membership/regime is. Test several
    (see out_of_sample_significance_by_block(), which does this for you)
    rather than trusting one arbitrary choice — a real effect should hold
    up across nearby block lengths.

    A LONGER BLOCK IS NOT THE CONSERVATIVE CHOICE. This is the natural
    reading of "accounts for more serial dependence" and it is backwards.
    Measured on pure noise at 31 signal dates, the false-positive rate at
    alpha=0.05 rose monotonically with block length: 12.5% at block 5,
    18.5% at block 10, 29.0% at block 15. With `n_dates` fixed, a longer
    block means fewer independent blocks per resample, so the resample
    distribution narrows and p shrinks. The right block length scales with
    `n_dates`, not with `hold_days` alone — at n_dates 120-240 block 10 is
    near-nominal (1.6-1.7x), while at n_dates 31 no block length is
    (3.5-6.5x). `_block_bootstrap_refusal()` now declines the cases where
    this bites hardest.
    """
    df, block_length, n_bootstrap = _prepare_block_bootstrap_inputs(
        edge_values,
        dates,
        block_length=block_length,
        n_bootstrap=n_bootstrap,
    )
    unique_dates = np.sort(df["date"].unique())
    n_dates = len(unique_dates)

    refusal = _block_bootstrap_refusal(len(df), n_dates, block_length)
    if refusal is not None:
        # The MEAN is descriptive and needs no resampling, so it is still
        # reported; only the INFERENCE (CI, p-value) is withheld. Nulling the
        # mean too would destroy a legitimate descriptive statistic and
        # conflate "we cannot test this" with "there is nothing here".
        return {
            "n": len(df), "n_dates": n_dates, "block_length": block_length,
            "mean": round(float(df["edge"].mean()), 3) if len(df) else None,
            "ci_low": None, "ci_high": None, "p_value": None,
            "refusal_reason": refusal,
        }

    grouped = {d: g["edge"].to_numpy() for d, g in df.groupby("date")}
    n_blocks_needed = int(np.ceil(n_dates / block_length))

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        block_starts = rng.integers(0, n_dates, size=n_blocks_needed)
        sampled_dates = []
        for start in block_starts:
            sampled_dates.extend(unique_dates[(start + np.arange(block_length)) % n_dates])
        sampled_dates = sampled_dates[:n_dates]  # trim so every bootstrap draw is the same total size
        pooled = np.concatenate([grouped[d] for d in sampled_dates])
        boot_means[i] = pooled.mean()

    mean = df["edge"].mean()
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    p_value = min(1.0, 2 * min((boot_means <= 0).mean(), (boot_means >= 0).mean()))

    return {
        "n": len(df),
        "n_dates": int(n_dates),
        "block_length": block_length,
        "mean": round(float(mean), 3),
        "ci_low": round(float(ci_low), 3),
        "ci_high": round(float(ci_high), 3),
        "p_value": round(float(p_value), 4),
        "refusal_reason": None,
    }


def bootstrap_daily_edge_significance_by_block(
    edge_values: pd.Series, dates: pd.Series, block_length: int, n_bootstrap: int = 2000, seed: int = 0
) -> dict:
    """
    Equal-DATE-weighted counterpart to bootstrap_edge_significance_by_block().

    bootstrap_edge_significance_by_block() (and the by-date/row-level
    versions) pool every signal ROW together, so a date with 25 flagged
    tickers has 25x the influence on the mean edge as a date with 1 —
    appropriate if the estimand is "expected return per individual trade,
    assuming every signal is traded independently at equal notional," but
    NOT if the real constraint is a fixed daily capital/risk budget (that
    date's 25 signals compete for the same capital; they don't each get
    their own separate allocation). This instead first collapses to ONE
    equal-weighted observation per date (the date's own mean edge), then
    block-bootstraps THAT daily series — every trading decision date
    counts once, regardless of how many tickers it flagged that day.

    Compare this against bootstrap_edge_significance_by_block() on the
    same data: if they disagree substantially, signal BREADTH (how many
    tickers fire per date) is driving the trade-weighted result, not a
    real per-day edge.
    """
    df, block_length, n_bootstrap = _prepare_block_bootstrap_inputs(
        edge_values,
        dates,
        block_length=block_length,
        n_bootstrap=n_bootstrap,
    )
    daily = df.groupby("date")["edge"].mean().sort_index()
    unique_dates = daily.index.to_numpy()
    n_dates = len(unique_dates)

    refusal = _block_bootstrap_refusal(len(df), n_dates, block_length)
    if refusal is not None:
        # See the sibling function: the equal-date-weighted mean is likewise
        # descriptive, so it survives the refusal; the inference does not.
        return {
            "n": len(df), "n_dates": n_dates, "block_length": block_length,
            "mean": round(float(daily.mean()), 3) if n_dates else None,
            "ci_low": None, "ci_high": None, "p_value": None,
            "refusal_reason": refusal,
        }

    values = daily.to_numpy()
    n_blocks_needed = int(np.ceil(n_dates / block_length))

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        block_starts = rng.integers(0, n_dates, size=n_blocks_needed)
        sampled = []
        for start in block_starts:
            sampled.extend(values[(start + np.arange(block_length)) % n_dates])
        sampled = sampled[:n_dates]
        boot_means[i] = np.mean(sampled)

    mean = float(values.mean())
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    p_value = min(1.0, 2 * min((boot_means <= 0).mean(), (boot_means >= 0).mean()))

    return {
        "n": len(df),
        "n_dates": int(n_dates),
        "block_length": block_length,
        "mean": round(mean, 3),
        "ci_low": round(float(ci_low), 3),
        "ci_high": round(float(ci_high), 3),
        "p_value": round(float(p_value), 4),
        "refusal_reason": None,
    }


OUT_OF_SAMPLE_SIGNIFICANCE_COLUMNS = [
    "period", "direction", "n", "mean_edge_pct", "ci_low", "ci_high",
    "p_value", "bonferroni_threshold", "significant",
]


def out_of_sample_significance(
    data: dict[str, pd.DataFrame],
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    n_bootstrap: int = 2000,
    n_tests: int = 2,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Splits discovery from confirmation and bootstraps each SEPARATELY,
    rather than pooling both together (see the CAUTION in
    bonferroni_threshold()'s docstring for why pooling is a trap — it
    already fooled a check in this project once).

    NOT SUFFICIENT ON ITS OWN, despite the plain name. This docstring
    used to open by declaring itself the definitive test of whether a
    signal's edge is real, which contradicted the SECOND CAUTION in
    bonferroni_threshold() a few dozen lines above: this function
    resamples individual signal ROWS, treating same-date signals as
    independent draws when they are typically driven by the same
    market-wide move. That inflates significance. The function with the
    most authoritative name and the most confident docstring was the one
    the module elsewhere warns against (independent review, 2026-07-30).

    Use `out_of_sample_significance_by_block()` for any claim that an
    edge is real. That is this project's standing bar — block resampling
    handles both cross-sectional correlation (same-date clustering) and
    serial correlation, and by-date alone is not enough either. Reach for
    THIS function only when signals genuinely cannot cluster in time.

    Only the CONFIRMATION row's `significant` flag is evidence the edge
    is real. The DISCOVERY row is informational only (how good did it
    look before checking) — never cite discovery-period significance on
    its own as confirmatory.

    `n_tests` sets the Bonferroni correction denominator. The default of
    2 covers exactly ONE signal's dip + up and is wrong for anything
    else: a sweep over signals x baskets x horizons must pass the total
    cell count, or the correction is too lenient by one to two orders of
    magnitude. That has happened here for real — a runner's denominator
    was 10x too lenient (see tests/test_significance_multiplicity.py,
    which pins derived denominators at the runner call sites precisely
    because this default cannot detect its own misuse).
    """
    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if discovery.empty and confirmation.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_COLUMNS)

    threshold = bonferroni_threshold(n_tests, alpha=0.05)

    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        for direction in ("dip", "up"):
            d = subset[subset["direction"] == direction] if not subset.empty else pd.DataFrame()
            if d.empty:
                continue
            stats = bootstrap_edge_significance(d["edge_vs_own_ticker_pct"], n_bootstrap=n_bootstrap)
            rows.append(
                {
                    "period": period,
                    "direction": direction,
                    "n": stats["n"],
                    "mean_edge_pct": stats["mean"],
                    "ci_low": stats["ci_low"],
                    "ci_high": stats["ci_high"],
                    "p_value": stats["p_value"],
                    "bonferroni_threshold": round(threshold, 6),
                    "significant": stats["p_value"] is not None and stats["p_value"] < threshold,
                }
            )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_SIGNIFICANCE_COLUMNS]


OUT_OF_SAMPLE_SIGNIFICANCE_BY_DATE_COLUMNS = [
    "period", "direction", "n", "n_dates", "mean_edge_pct", "ci_low", "ci_high",
    "p_value", "bonferroni_threshold", "significant",
]


def out_of_sample_significance_by_date(
    data: dict[str, pd.DataFrame],
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    n_bootstrap: int = 2000,
    n_tests: int = 2,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Cross-sectional-correlation-aware version of out_of_sample_significance():
    same discovery/confirmation split, but bootstraps significance via
    bootstrap_edge_significance_by_date() (resampling whole trading days,
    not individual signal rows) instead of the plain row-level bootstrap.

    Use this — not out_of_sample_significance() — whenever a signal can
    fire on many tickers on the same date (true of every signal in this
    project), since same-day signals are typically correlated (driven by
    the same market-wide move) and the plain bootstrap can understate
    uncertainty as a result. Check the `n_dates` column directly: a small
    n_dates relative to `n` is a sign the plain row-level bootstrap would
    have been especially misleading for that cell.

    Only the CONFIRMATION row's `significant` flag is evidence the edge
    is real — same caveat as out_of_sample_significance().
    """
    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if discovery.empty and confirmation.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_DATE_COLUMNS)

    threshold = bonferroni_threshold(n_tests, alpha=0.05)

    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        for direction in ("dip", "up"):
            d = subset[subset["direction"] == direction] if not subset.empty else pd.DataFrame()
            if d.empty:
                continue
            stats = bootstrap_edge_significance_by_date(d["edge_vs_own_ticker_pct"], d["date"], n_bootstrap=n_bootstrap)
            rows.append(
                {
                    "period": period,
                    "direction": direction,
                    "n": stats["n"],
                    "n_dates": stats["n_dates"],
                    "mean_edge_pct": stats["mean"],
                    "ci_low": stats["ci_low"],
                    "ci_high": stats["ci_high"],
                    "p_value": stats["p_value"],
                    "bonferroni_threshold": round(threshold, 6),
                    "significant": stats["p_value"] is not None and stats["p_value"] < threshold,
                }
            )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_DATE_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_SIGNIFICANCE_BY_DATE_COLUMNS]


OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS = [
    "period", "direction", "weighting", "block_length", "primary", "n", "n_dates", "mean_edge_pct", "ci_low", "ci_high",
    "p_value", "bonferroni_threshold", "significant",
    # Added 2026-07-30. `min_detectable_effect_pct` is the approximate
    # smallest true edge detectable with 80% power at this cell's corrected
    # threshold; read every `significant=False` against it before calling the
    # result a rejection. `refusal_reason` is non-null when the bootstrap
    # declined to produce a p-value at all -- which is NOT the same as
    # "tested and found nothing".
    "min_detectable_effect_pct", "refusal_reason",
]


def out_of_sample_significance_by_block(
    data: dict[str, pd.DataFrame],
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
    block_lengths: tuple[int, ...] | None = None,
    n_bootstrap: int | None = None,
    n_tests: int = 2,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    Serial-dependence-aware version of out_of_sample_significance_by_date():
    same discovery/confirmation split, but resamples BLOCKS of consecutive
    trading dates (bootstrap_edge_significance_by_block()) instead of
    independent single dates — see the THIRD CAUTION in
    bonferroni_threshold()'s docstring for why by-date resampling alone
    still isn't enough when hold_days > 1 or the signal has slow turnover.

    Tests several block lengths by default (hold_days, 2x, 3x) rather
    than trusting one arbitrary choice — pass `block_lengths` to override.
    A real effect should hold up across nearby block lengths, the same
    way a real edge should hold up across nearby hold-period choices.

    Reports BOTH weightings per (period, direction, block_length):
    `weighting="trade_weighted"` (every signal row counts once, so a date
    with 25 flagged tickers has 25x the influence of a 1-ticker date —
    the right estimand if every signal is traded independently at equal
    notional) and `weighting="equal_date_weighted"` (every trading date
    counts once regardless of how many tickers it flagged — the right
    estimand under a fixed daily capital/risk budget, where a date's
    signals compete for the same allocation rather than each getting
    their own). If the two disagree substantially, signal BREADTH is
    driving the trade-weighted result, not a real per-day edge — check
    both before trusting either alone.

    MULTIPLE-TESTING CAUTION: this reports up to 2 weightings x N block
    lengths per (period, direction) cell, all under the SAME Bonferroni
    threshold (from `n_tests`, which counts basket/signal/direction cells,
    NOT weighting/block-length variants). Every row still gets its own
    `significant` flag, but treating "any row passed" as evidence is a
    researcher-degrees-of-freedom trap (flagged by independent code
    review, 2026-07) — with enough variants inspected, one is likely to
    look significant by chance even with zero real edge. The `primary`
    column marks exactly ONE pre-specified row per (period, direction) —
    `equal_date_weighted` at the middle default block length (2x
    hold_days) — as the only row that counts as actual evidence; every
    other row is a sensitivity/robustness check only, not an independent
    test to cherry-pick from. Only the CONFIRMATION period's primary row's
    `significant` flag is evidence the edge is real — same "confirmation
    only" caveat as out_of_sample_significance().

    Also note: the underlying p-value is a percentile-bootstrap
    approximation (is 0 outside the resampled distribution's tails), not
    a null-centered hypothesis test — treat it as a useful, honest
    approximation alongside the confidence interval, not as an exact
    p-value in the classical sense.
    """
    n_tests = _require_positive_int(n_tests, name="n_tests")
    if block_lengths is None:
        block_lengths = (hold_days, hold_days * 2, hold_days * 3)
    if not block_lengths:
        raise ValueError("block_lengths must contain at least one positive integer")
    normalized_block_lengths = tuple(
        _require_positive_int(value, name="block_lengths item")
        for value in block_lengths
    )
    if tuple(sorted(set(normalized_block_lengths))) != normalized_block_lengths:
        raise ValueError(
            "block_lengths must be strictly increasing with no duplicates, got "
            f"{block_lengths!r}"
        )
    block_lengths = normalized_block_lengths
    primary_block_length = block_lengths[min(1, len(block_lengths) - 1)]  # 2x hold_days by default

    # Default the resample count to whatever actually RESOLVES this run's
    # threshold, rather than a fixed 2000 whose p-value floor (2/2000 = 0.001)
    # creeps up on the Bonferroni bar as the run widens -- see
    # recommended_n_bootstrap(). An explicit n_bootstrap still wins, so
    # existing callers and tests are unaffected.
    if n_bootstrap is None:
        n_bootstrap = recommended_n_bootstrap(n_tests)
    else:
        n_bootstrap = _require_positive_int(n_bootstrap, name="n_bootstrap")

    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if discovery.empty and confirmation.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS)

    threshold = bonferroni_threshold(n_tests, alpha=0.05)

    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        for direction in ("dip", "up"):
            d = subset[subset["direction"] == direction] if not subset.empty else pd.DataFrame()
            if d.empty:
                continue
            for block_length in block_lengths:
                trade_weighted_stats = bootstrap_edge_significance_by_block(
                    d["edge_vs_own_ticker_pct"], d["date"], block_length=block_length, n_bootstrap=n_bootstrap
                )
                daily_weighted_stats = bootstrap_daily_edge_significance_by_block(
                    d["edge_vs_own_ticker_pct"], d["date"], block_length=block_length, n_bootstrap=n_bootstrap
                )
                for weighting, stats in (
                    ("trade_weighted", trade_weighted_stats),
                    ("equal_date_weighted", daily_weighted_stats),
                ):
                    is_primary = weighting == "equal_date_weighted" and block_length == primary_block_length
                    rows.append(
                        {
                            "period": period,
                            "direction": direction,
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

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS]
