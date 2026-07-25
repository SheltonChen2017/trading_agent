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


def run_backtest(
    data: dict[str, pd.DataFrame],
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Walk every date in the universe, run the live scanner as-of that date,
    and score each flagged signal against its actual forward return.

    Returns one row per flagged signal that had enough forward data to
    evaluate, with columns: RESULT_COLUMNS (see above). `net_return_pct`
    already has simulated slippage deducted; `win` is True when
    net_return_pct > 0 under the "go long the signal" hypothesis.
    """
    all_dates = sorted(set().union(*(df.index for df in data.values())))
    # Skip the front of history where no ticker has enough trailing data
    # yet, and the tail where no ticker has `hold_days` of forward data —
    # cheap early exit, scan_dips_and_ups would just return empty anyway.
    usable_dates = all_dates[ROLLING_WINDOW : len(all_dates) - hold_days] if hold_days > 0 else all_dates[ROLLING_WINDOW:]

    rows = []
    for as_of in usable_dates:
        signals = scan_dips_and_ups(
            data,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            as_of=as_of,
        )
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


def compare_signal_to_baseline_per_ticker(
    data: dict[str, pd.DataFrame],
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
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
        results = run_backtest(
            data,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
        )
        baseline = run_baseline_forward_returns(data, hold_days=hold_days, slippage_pct=slippage_pct)
        baseline_mean_by_ticker = (
            baseline.groupby("ticker")["net_return_pct"].mean() if not baseline.empty else pd.Series(dtype=float)
        )

        if not results.empty:
            results = results.copy()
            results["own_ticker_baseline_pct"] = results["ticker"].map(baseline_mean_by_ticker)
            results["edge_vs_own_ticker_pct"] = results["net_return_pct"] - results["own_ticker_baseline_pct"]

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


def compare_signal_to_market_index(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    hold_days_options: list[int] = HORIZON_SWEEP_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
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
        results = run_backtest(
            data,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
        )
        benchmark_returns = compute_benchmark_forward_returns(benchmark_df, hold_days=hold_days, slippage_pct=slippage_pct)

        if not results.empty:
            results = results.copy()
            results["market_return_pct"] = results["date"].map(benchmark_returns)
            results["edge_vs_market_pct"] = results["net_return_pct"] - results["market_return_pct"]

        for direction in ("dip", "up"):
            subset = results[results["direction"] == direction] if not results.empty else pd.DataFrame()
            if not subset.empty:
                subset = subset.dropna(subset=["market_return_pct"])

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
