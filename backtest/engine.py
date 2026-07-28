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

from typing import Callable

import numpy as np
import pandas as pd

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
        )
        for hold_days in hold_days_options
    }


def summarize_multi_horizon(results_by_horizon: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """
    Combine summarize_backtest() across every horizon in
    run_multi_horizon_backtest()'s output into one table, with
    `hold_days`/`horizon` columns so results can be compared side by side.
    """
    columns = ["hold_days", "horizon"] + SUMMARY_COLUMNS
    rows = []
    for hold_days, results in results_by_horizon.items():
        summary = summarize_backtest(results)
        if summary.empty:
            continue
        summary.insert(0, "horizon", HORIZON_LABELS.get(hold_days, f"{hold_days}d"))
        summary.insert(0, "hold_days", hold_days)
        rows.append(summary)

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.concat(rows, ignore_index=True)[columns]


def run_baseline_forward_returns(
    data: dict[str, pd.DataFrame],
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """
    The control group for run_backtest(): for EVERY date (not just flagged
    signal dates), compute the same forward return over `hold_days`, minus
    slippage. This answers "what would holding this stock for the same
    period have returned on an arbitrary day" — the baseline a flagged
    signal's return needs to beat. Without this, an apparent edge over a
    rising test window can just be the whole universe drifting upward, not
    anything the scanner detected.

    `entry_timing` must match whatever was passed to run_backtest() for the
    signal side of the comparison, or the two aren't measuring the same
    thing: "same_close" compares close-to-close over `hold_days`; "next_open"
    shifts both legs forward one day and compares open-to-open, matching
    run_backtest()'s next-day-open execution assumption (see its docstring);
    "same_day_open_to_close" compares open-to-close on the SAME day
    (`hold_days` is ignored in this mode).
    """
    if entry_timing not in ("same_close", "next_open", "same_day_open_to_close"):
        raise ValueError(
            f"entry_timing must be 'same_close', 'next_open', or 'same_day_open_to_close', got {entry_timing!r}"
        )

    frames = []
    for ticker, df in data.items():
        if entry_timing == "same_close":
            entry_price, forward_price = df["close"], df["close"].shift(-hold_days)
        elif entry_timing == "same_day_open_to_close":
            entry_price, forward_price = df["open"], df["close"]
        else:  # next_open
            entry_price, forward_price = df["open"].shift(-1), df["open"].shift(-(1 + hold_days))
        if entry_timing != "same_day_open_to_close" and len(df) <= hold_days:
            continue
        raw_return_pct = (forward_price - entry_price) / entry_price * 100
        net_return_pct = raw_return_pct - 2 * slippage_pct * 100
        frame = pd.DataFrame({"ticker": ticker, "date": df.index, "net_return_pct": net_return_pct})
        frames.append(frame.dropna(subset=["net_return_pct"]))

    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "net_return_pct"])

    return pd.concat(frames, ignore_index=True)


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
        )
        baseline = run_baseline_forward_returns(data, hold_days=hold_days, slippage_pct=slippage_pct)
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
    "hold_days", "horizon", "direction", "signal_count",
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
            data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
        )

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else pd.DataFrame()

            if subset.empty:
                rows.append(
                    {
                        "hold_days": hold_days,
                        "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                        "direction": direction,
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
    "hold_days", "horizon", "direction", "signal_count",
    "signal_mean_return_pct", "mean_market_return_pct",
    "mean_edge_vs_market_pct", "pct_signals_beating_market",
]


def compute_benchmark_forward_returns(
    benchmark_df: pd.DataFrame,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
) -> pd.Series:
    """
    Forward return of a single reference series (e.g. SPY, QQQ) over
    `hold_days`, indexed by date — the same math as
    run_baseline_forward_returns(), applied to one benchmark instead of a
    universe of stocks. Used to check whether a signal beat the broad
    market on the EXACT SAME days it fired, the strictest baseline of the
    three this project computes (own history -> own ticker's baseline ->
    the whole market on that specific date).
    """
    forward_close = benchmark_df["close"].shift(-hold_days)
    raw_return_pct = (forward_close - benchmark_df["close"]) / benchmark_df["close"] * 100
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
) -> pd.DataFrame:
    """
    Per-signal detail shared by compare_signal_to_market_index() and
    out_of_sample_market_comparison(): run_backtest()'s output annotated
    with what the benchmark returned starting that EXACT signal date
    (market_return_pct, edge_vs_market_pct). Signals whose date falls
    outside the benchmark's own history are dropped, not miscounted.
    """
    results = run_backtest(
        data,
        hold_days=hold_days,
        slippage_pct=slippage_pct,
        return_z_threshold=return_z_threshold,
        volume_z_threshold=volume_z_threshold,
        scan_fn=scan_fn,
        scan_kwargs=scan_kwargs,
    )
    benchmark_returns = compute_benchmark_forward_returns(benchmark_df, hold_days=hold_days, slippage_pct=slippage_pct)

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
            data, benchmark_df, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
        )

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else pd.DataFrame()

            if subset.empty:
                rows.append(
                    {
                        "hold_days": hold_days,
                        "horizon": HORIZON_LABELS.get(hold_days, f"{hold_days}d"),
                        "direction": direction,
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
    signals on/before `split_date` (discovery) and after (confirmation)."""
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
    )
    columns = ["period"] + SUMMARY_COLUMNS
    if results.empty:
        return pd.DataFrame(columns=columns)

    split_date = _discovery_split_date(data, discovery_frac)
    discovery, confirmation = _split_by_date(results, split_date)
    rows = []
    for period, subset in zip(OUT_OF_SAMPLE_PERIODS, (discovery, confirmation)):
        summary = summarize_backtest(subset)
        if summary.empty:
            continue
        summary.insert(0, "period", period)
        rows.append(summary)

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


OUT_OF_SAMPLE_BASELINE_COLUMNS = [
    "period", "direction", "signal_count",
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
) -> pd.DataFrame:
    """
    Out-of-sample version of compare_signal_to_baseline_per_ticker(): the
    per-ticker-matched edge, split into a discovery period and a
    confirmation (holdout) period never used to find anything — including
    the baseline itself, computed SEPARATELY per period (see
    _out_of_sample_own_ticker_detail()).
    """
    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
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
                    "signal_count": len(d),
                    "mean_edge_vs_own_ticker_pct": round(d["edge_vs_own_ticker_pct"].mean(), 3),
                    "pct_signals_beating_own_ticker_baseline": round((d["edge_vs_own_ticker_pct"] > 0).mean() * 100, 1),
                }
            )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_BASELINE_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_BASELINE_COLUMNS]


OUT_OF_SAMPLE_MARKET_COLUMNS = [
    "period", "direction", "signal_count",
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
) -> pd.DataFrame:
    """
    Out-of-sample version of compare_signal_to_market_index(): the
    market-matched edge, split into a discovery period and a confirmation
    (holdout) period never used to find anything.
    """
    detailed = _signals_with_market_edge(
        data, benchmark_df, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
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
    """
    df = pd.DataFrame({"edge": pd.Series(edge_values).to_numpy(), "date": pd.Series(dates).to_numpy()})
    df = df.dropna(subset=["edge"])
    unique_dates = np.sort(df["date"].unique())
    n_dates = len(unique_dates)

    if len(df) < 5 or n_dates < max(5, block_length):
        return {
            "n": len(df), "n_dates": n_dates, "block_length": block_length,
            "mean": None, "ci_low": None, "ci_high": None, "p_value": None,
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
    df = pd.DataFrame({"edge": pd.Series(edge_values).to_numpy(), "date": pd.Series(dates).to_numpy()})
    df = df.dropna(subset=["edge"])
    daily = df.groupby("date")["edge"].mean().sort_index()
    unique_dates = daily.index.to_numpy()
    n_dates = len(unique_dates)

    if len(df) < 5 or n_dates < max(5, block_length):
        return {
            "n": len(df), "n_dates": n_dates, "block_length": block_length,
            "mean": None, "ci_low": None, "ci_high": None, "p_value": None,
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
    }


def bonferroni_threshold(n_tests: int, alpha: float = 0.05) -> float:
    """
    The Bonferroni-corrected significance threshold for `n_tests`
    simultaneous comparisons: instead of asking "is p < 0.05", ask
    "is p < alpha/n_tests". Conservative (some real effects will be missed),
    but appropriate here given how many basket/direction/horizon cells
    tend to get scanned at once looking for a candidate.

    CAUTION: `bootstrap_edge_significance()` run on a POOLED sample (all
    signals across the full date range) is only ever exploratory, not
    confirmatory — pooling mixes the discovery period (which is expected
    to look good, since it's the data any pattern was found in) with the
    confirmation period (the honest test), and a strong discovery-period
    effect can drag a misleading "significant" p-value out of an
    honestly-noisy confirmation period. This happened for real in this
    project (`analyst` "dip": pooled p=0.014, looked significant;
    confirmation-only p=0.656, not even close). Use
    `out_of_sample_significance()` below for any claim that a signal's
    edge is actually real — it computes significance SEPARATELY per
    period and makes clear only the confirmation row counts as evidence.

    SECOND CAUTION: `bootstrap_edge_significance()` and
    `out_of_sample_significance()` both resample individual signal ROWS,
    treating same-date signals as independent draws even though they're
    typically correlated (driven by the same market-wide move) — use
    `bootstrap_edge_significance_by_date()` / `out_of_sample_significance_
    by_date()` instead (caught via `momentum`: row-level bootstrap said
    p=0.000 significant in both periods; by-date revealed the 17,506/
    14,000-row samples were really only ~912/700 independent trading days,
    and significance evaporated).

    THIRD CAUTION: by-date resampling still treats each TRADING DAY as
    independent of every other day, which misses SERIAL dependence across
    nearby dates — real when hold_days > 1 (overlapping return windows),
    when market regimes persist, or when a signal has slow turnover (e.g.
    momentum keeps flagging the same tickers for weeks). Use
    `bootstrap_edge_significance_by_block()` / `out_of_sample_significance_
    by_block()` for the most rigorous check available — it block-
    resamples consecutive dates instead of independent ones.
    """
    if n_tests <= 0:
        return alpha
    return alpha / n_tests


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
    THE correct way to test whether a signal's edge is statistically
    real: bootstraps significance SEPARATELY for the discovery period and
    the confirmation (holdout) period, rather than pooling both together
    (see the CAUTION in bonferroni_threshold()'s docstring for why
    pooling is a trap — it already fooled a check in this project once).

    Only the CONFIRMATION row's `significant` flag is evidence the edge
    is real. The DISCOVERY row is informational only (how good did it
    look before checking) — never cite discovery-period significance on
    its own as confirmatory.

    `n_tests` sets the Bonferroni correction denominator — default 2 (one
    signal's dip + up). Override with the total cell count when this is
    being called across multiple baskets/signals at once (see
    `baskets.basket_out_of_sample_significance()`), so the correction
    reflects everything actually being tested simultaneously.
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
    n_bootstrap: int = 2000,
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
    discovery, confirmation = _out_of_sample_own_ticker_detail(
        data, discovery_frac, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs,
        entry_timing=entry_timing,
    )
    if discovery.empty and confirmation.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS)

    if block_lengths is None:
        block_lengths = (hold_days, hold_days * 2, hold_days * 3)
    primary_block_length = block_lengths[min(1, len(block_lengths) - 1)]  # 2x hold_days by default

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
                        }
                    )

    if not rows:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS)
    return pd.DataFrame(rows)[OUT_OF_SAMPLE_SIGNIFICANCE_BY_BLOCK_COLUMNS]
