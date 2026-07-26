"""
Overlapping themed groupings of the trading universe (config.BASKETS).

A ticker can belong to multiple baskets at once — TSLA is both
"consumer_discretionary" and "ai_related", for instance — which is
deliberate: real companies don't fit one box, and stocks worth watching
for one theme (AI capex) are often also relevant to another (semis,
mega-cap tech).

Per-basket ML MODEL TRAINING is intentionally not implemented yet. See
the BASKETS docstring in config.py: splitting the universe into smaller
groups shrinks an already-thin per-signal sample further, and the pooled
43-ticker model's own walk-forward accuracy (~48%, essentially coin-flip)
is a reason for caution, not for fragmenting the data more. What IS built
here is basket-level backtest/baseline reporting (backtest/engine.py's
per-basket functions) — enough to see whether any basket's signals look
more promising than others, without pretending a model trained on a
handful of per-basket signals is trustworthy.

Every function below accepts an optional `scan_fn`/`scan_kwargs` pair
(default: the original z-score dip/up scanner) so any signal module
(signals/momentum.py, relative.py, breakout.py, pead.py) can be reported
on per-basket using this exact same rigor toolkit.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from backtest.engine import (
    MARKET_COMPARISON_COLUMNS,
    OUT_OF_SAMPLE_BASELINE_COLUMNS,
    OUT_OF_SAMPLE_MARKET_COLUMNS,
    PER_TICKER_COMPARISON_COLUMNS,
    SUMMARY_COLUMNS,
    _signals_with_own_ticker_baseline,
    bonferroni_threshold,
    bootstrap_edge_significance,
    compare_signal_to_baseline_per_ticker,
    compare_signal_to_market_index,
    out_of_sample_backtest,
    out_of_sample_baseline_comparison,
    out_of_sample_market_comparison,
    run_backtest,
    summarize_backtest,
)
from config import (
    BACKTEST_HOLD_DAYS,
    BASKETS,
    HIGH_VOLATILITY_BASKET_SIZE,
    RETURN_Z_THRESHOLD,
    SLIPPAGE_PCT,
    VOLUME_Z_THRESHOLD,
)
from signals.scanner import scan_dips_and_ups


def get_basket_tickers(basket_name: str) -> list[str]:
    """Tickers in a named basket. Raises KeyError with the valid names
    listed if the basket doesn't exist — easy to catch a typo."""
    if basket_name not in BASKETS:
        raise KeyError(f"Unknown basket '{basket_name}'. Valid baskets: {sorted(BASKETS)}")
    return BASKETS[basket_name]


def baskets_for_ticker(ticker: str) -> list[str]:
    """Which basket(s) a ticker belongs to — empty list if none. Since
    baskets deliberately overlap, this can return more than one name."""
    return [name for name, tickers in BASKETS.items() if ticker in tickers]


def compute_high_volatility_basket(
    data: dict[str, pd.DataFrame], top_n: int = HIGH_VOLATILITY_BASKET_SIZE
) -> list[str]:
    """
    The empirical stand-in for an "unstable stocks" basket: ranks every
    ticker in `data` by its realized daily-return standard deviation over
    the full history provided, and returns the `top_n` most volatile.

    Computed from data rather than hand-picked, so it updates automatically
    as the universe or lookback window changes, instead of going stale like
    a hardcoded list would.
    """
    volatility = {}
    for ticker, df in data.items():
        returns = df["close"].pct_change().dropna()
        if len(returns) < 2:
            continue
        volatility[ticker] = returns.std()

    ranked = sorted(volatility.items(), key=lambda kv: kv[1], reverse=True)
    return [ticker for ticker, _ in ranked[:top_n]]


def all_basket_names() -> list[str]:
    return sorted(BASKETS)


def _basket_data(data: dict[str, pd.DataFrame], basket_name: str) -> dict[str, pd.DataFrame]:
    tickers = get_basket_tickers(basket_name)
    return {t: data[t] for t in tickers if t in data}


def summarize_by_basket(
    data: dict[str, pd.DataFrame],
    basket_names: list[str] | None = None,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """
    Quick per-basket overview: restrict `data` to each basket's tickers,
    run the normal backtest, and summarize win rate/return by direction —
    same numbers as backtest.engine.summarize_backtest(), just broken out
    per basket instead of one number for the whole universe. A ticker in
    multiple baskets is scored independently in each; that's intentional,
    since baskets overlap by design (see config.BASKETS docstring).

    This is a summary, NOT a trained model — no basket gets its own
    classifier here (see this module's docstring for why that's deferred).
    """
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        results = run_backtest(
            basket_data,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        summary = summarize_backtest(results)
        if summary.empty:
            continue
        summary.insert(0, "basket", basket_name)
        rows.append(summary)

    columns = ["basket"] + SUMMARY_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


def compare_baskets_to_baseline(
    data: dict[str, pd.DataFrame],
    basket_names: list[str] | None = None,
    hold_days_options: list[int] = (BACKTEST_HOLD_DAYS,),
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """
    Per-basket version of compare_signal_to_baseline_per_ticker(): within
    each basket, matches every flagged signal against its own stock's
    any-day baseline (not the whole basket pooled), so you can see whether
    any basket's signals show real, baseline-beating edge — without
    needing a separate trained model per basket to find out.

    Defaults to a single hold period (BACKTEST_HOLD_DAYS) to keep runtime
    reasonable; pass a longer hold_days_options list for a full sweep per
    basket (expensive — this reruns the backtest for every hold period,
    for every basket).
    """
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        comparison = compare_signal_to_baseline_per_ticker(
            basket_data,
            hold_days_options=list(hold_days_options),
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        if comparison.empty:
            continue
        comparison.insert(0, "basket", basket_name)
        rows.append(comparison)

    columns = ["basket"] + PER_TICKER_COMPARISON_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


def compare_baskets_to_market_index(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    basket_names: list[str] | None = None,
    hold_days_options: list[int] = (BACKTEST_HOLD_DAYS,),
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """
    Per-basket version of compare_signal_to_market_index(): within each
    basket, matches every flagged signal to what the market benchmark
    (e.g. SPY) itself returned starting that EXACT same date — the
    strictest of the three comparisons available (own history -> own
    ticker's baseline -> the whole market on that specific date). A
    basket only clears this bar if its signals beat not just their own
    stock's typical day, but the broad market on the very days they fired.
    """
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        comparison = compare_signal_to_market_index(
            basket_data,
            benchmark_df,
            hold_days_options=list(hold_days_options),
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        if comparison.empty:
            continue
        comparison.insert(0, "basket", basket_name)
        rows.append(comparison)

    columns = ["basket"] + MARKET_COMPARISON_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


# --- Out-of-sample validation, per basket ---------------------------------
# Every basket-level function above can be (and has been) rerun on the
# SAME historical window while hunting for a promising basket/direction —
# these split each basket's signals into a discovery period and a later
# confirmation (holdout) period never used to identify anything. A
# candidate basket should look similarly good in both, not just in
# discovery (see backtest/engine.py's out-of-sample section).

def out_of_sample_backtest_by_basket(
    data: dict[str, pd.DataFrame],
    basket_names: list[str] | None = None,
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Per-basket version of out_of_sample_backtest()."""
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        result = out_of_sample_backtest(
            basket_data,
            discovery_frac=discovery_frac,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        if result.empty:
            continue
        result.insert(0, "basket", basket_name)
        rows.append(result)

    columns = ["basket", "period"] + SUMMARY_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


def out_of_sample_baseline_by_basket(
    data: dict[str, pd.DataFrame],
    basket_names: list[str] | None = None,
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Per-basket version of out_of_sample_baseline_comparison()."""
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        result = out_of_sample_baseline_comparison(
            basket_data,
            discovery_frac=discovery_frac,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        if result.empty:
            continue
        result.insert(0, "basket", basket_name)
        rows.append(result)

    columns = ["basket"] + OUT_OF_SAMPLE_BASELINE_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


def out_of_sample_market_by_basket(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    basket_names: list[str] | None = None,
    discovery_frac: float = 0.6,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Per-basket version of out_of_sample_market_comparison()."""
    rows = []
    for basket_name in (basket_names if basket_names is not None else all_basket_names()):
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        result = out_of_sample_market_comparison(
            basket_data,
            benchmark_df,
            discovery_frac=discovery_frac,
            hold_days=hold_days,
            slippage_pct=slippage_pct,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            scan_fn=scan_fn,
            scan_kwargs=scan_kwargs,
        )
        if result.empty:
            continue
        result.insert(0, "basket", basket_name)
        rows.append(result)

    columns = ["basket"] + OUT_OF_SAMPLE_MARKET_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


# --- Statistical significance, per basket ---------------------------------

def basket_significance(
    data: dict[str, pd.DataFrame],
    basket_names: list[str] | None = None,
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    n_bootstrap: int = 2000,
    scan_fn: Callable = scan_dips_and_ups,
    scan_kwargs: dict | None = None,
) -> pd.DataFrame:
    """
    For each basket/direction, bootstrap the per-ticker-baseline edge
    (edge_vs_own_ticker_pct) to get a mean, 95% CI, and p-value, then flag
    whether it survives a Bonferroni-corrected significance threshold
    given how many basket/direction cells were tested at once (every
    basket in `basket_names`, times 2 directions). A basket/direction only
    gets `significant=True` if its p-value beats that corrected threshold
    — a much stricter bar than the uncorrected 0.05 usually used for a
    single test, appropriate here since many cells are being scanned
    simultaneously looking for a candidate.
    """
    names = basket_names if basket_names is not None else all_basket_names()
    n_tests = len(names) * 2  # 2 directions per basket
    threshold = bonferroni_threshold(n_tests, alpha=0.05)

    rows = []
    for basket_name in names:
        basket_data = _basket_data(data, basket_name)
        if not basket_data:
            continue
        detailed = _signals_with_own_ticker_baseline(
            basket_data, hold_days, slippage_pct, return_z_threshold, volume_z_threshold, scan_fn, scan_kwargs
        )
        if detailed.empty:
            continue

        for direction in ("dip", "up"):
            subset = detailed[detailed["direction"] == direction]
            if subset.empty:
                continue
            stats = bootstrap_edge_significance(subset["edge_vs_own_ticker_pct"], n_bootstrap=n_bootstrap)
            rows.append(
                {
                    "basket": basket_name,
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

    columns = ["basket", "direction", "n", "mean_edge_pct", "ci_low", "ci_high", "p_value", "bonferroni_threshold", "significant"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns]
