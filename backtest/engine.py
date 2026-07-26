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
) -> pd.DataFrame:
    """
    Walk every date in the universe, run the live scanner as-of that date,
    and score each flagged signal against its actual forward return.

    Returns one row per flagged signal that had enough forward data to
    evaluate, with columns: RESULT_COLUMNS (see above). `net_return_pct`
    already has simulated slippage deducted; `win` is True when
    net_return_pct > 0 under the "go long the signal" hypothesis.
    """
    kwargs = _resolve_scan_kwargs(scan_fn, scan_kwargs, return_z_threshold, volume_z_threshold)
    all_dates = sorted(set().union(*(df.index for df in data.values())))
    # Skip the front of history where no ticker has enough trailing data
    # yet, and the tail where no ticker has `hold_days` of forward data —
    # cheap early exit, scan_fn would just return empty anyway. This is a
    # heuristic sized for the default scanner (ROLLING_WINDOW) — a slower
    # signal (e.g. momentum, 52-week breakout) needing more history simply
    # returns empty for the earlier dates in this range too; correctness
    # isn't affected, just a few wasted no-op scan calls.
    usable_dates = all_dates[ROLLING_WINDOW : len(all_dates) - hold_days] if hold_days > 0 else all_dates[ROLLING_WINDOW:]

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
            if idx + hold_days >= len(df):
                continue  # not enough forward history to score this one yet

            entry_price = float(df["close"].iloc[idx])
            exit_price = float(df["close"].iloc[idx + hold_days])
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
) -> pd.DataFrame:
    """
    The control group for run_backtest(): for EVERY date (not just flagged
    signal dates), compute the same close-to-close forward return over
    `hold_days`, minus slippage. This answers "what would holding this
    stock for the same period have returned on an arbitrary day" — the
    baseline a flagged signal's return needs to beat. Without this, an
    apparent edge over a rising test window can just be the whole universe
    drifting upward, not anything the scanner detected.
    """
    frames = []
    for ticker, df in data.items():
        if len(df) <= hold_days:
            continue
        forward_close = df["close"].shift(-hold_days)
        raw_return_pct = (forward_close - df["close"]) / df["close"] * 100
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
    )
    baseline = run_baseline_forward_returns(data, hold_days=hold_days, slippage_pct=slippage_pct)
    baseline_mean_by_ticker = (
        baseline.groupby("ticker")["net_return_pct"].mean() if not baseline.empty else pd.Series(dtype=float)
    )

    if not results.empty:
        results = results.copy()
        results["own_ticker_baseline_pct"] = results["ticker"].map(baseline_mean_by_ticker)
        results["edge_vs_own_ticker_pct"] = results["net_return_pct"] - results["own_ticker_baseline_pct"]

    return results


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
    confirmation (holdout) period never used to find anything.
    """
    detailed = _signals_with_own_ticker_baseline(
        data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
    )
    if detailed.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_BASELINE_COLUMNS)

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
    detailed = _signals_with_own_ticker_baseline(
        data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
    )
    if detailed.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_COLUMNS)

    split_date = _discovery_split_date(data, discovery_frac)
    discovery, confirmation = _split_by_date(detailed, split_date)
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
    detailed = _signals_with_own_ticker_baseline(
        data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
    )
    if detailed.empty:
        return pd.DataFrame(columns=OUT_OF_SAMPLE_SIGNIFICANCE_BY_DATE_COLUMNS)

    split_date = _discovery_split_date(data, discovery_frac)
    discovery, confirmation = _split_by_date(detailed, split_date)
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
