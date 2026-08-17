"""
Defensive-carry research probe (docs/operations/MANDATE.md, item 5 -- "test a
defensive-carry expansion cheaply, using existing infrastructure").

EXPLORATORY ONLY -- a single lookback window, no walk-forward, no
out-of-sample split. Not a recommendation, not a live/paper allocation.
See the standing statistical caveats printed at the end of this script's
output, and .claude/skills/real-data-check/SKILL.md, section 4.

Question this asks: does adding config.DEFENSIVE_CARRY_TICKERS
(TLT/IEF/SHY/GLD) to an equal-weight buy-and-hold of config.UNIVERSE
reduce drawdown/tail-loss/downside-capture versus SPY, and if so at what
cost to upside capture? Uses a static-weight buy-and-hold blend (via
strategies.leverage_rotation.buy_and_hold(), reused rather than
reimplemented -- the carry tickers aren't signal-driven, so the
dip/up-scanning portfolio_simulator.py isn't the right tool here) between
two synthetic equal-weight indices: the existing UNIVERSE and the carry
basket.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.risk_metrics import (
    downside_capture_pct,
    expected_shortfall_pct,
    max_drawdown_pct,
    time_under_water,
    upside_capture_pct,
)
from data.market_data import fetch_historical
from strategies.leverage_rotation import buy_and_hold

CANDIDATE_CARRY_WEIGHTS = [0.10, 0.20, 0.30]
MIN_HISTORY_FRACTION = 0.9  # exclude UNIVERSE tickers with materially short history from the equal-weight blend


def _equal_weight_index(price_data: dict[str, pd.DataFrame], lookback_days: int) -> pd.Series:
    """Normalized (starts at 100) equal-weight buy-and-hold index across
    every ticker in `price_data` with at least MIN_HISTORY_FRACTION of
    `lookback_days` rows -- a short-history ticker (e.g. a recent IPO)
    would otherwise truncate the WHOLE blend's common date range down to
    its own short window (real-data-check skill, section 1)."""
    usable = {
        ticker: df["close"]
        for ticker, df in price_data.items()
        if df is not None and len(df) >= lookback_days * MIN_HISTORY_FRACTION
    }
    excluded = sorted(set(price_data) - set(usable))
    if excluded:
        print(f"  (excluded {len(excluded)} short-history ticker(s) from the equal-weight blend: {excluded})")
    if not usable:
        raise ValueError("No tickers with sufficient history to build an equal-weight index.")

    common_dates = None
    for series in usable.values():
        common_dates = series.index if common_dates is None else common_dates.intersection(series.index)
    common_dates = common_dates.sort_values()

    normalized = pd.DataFrame({
        ticker: series.reindex(common_dates) / series.reindex(common_dates).iloc[0]
        for ticker, series in usable.items()
    })
    return normalized.mean(axis=1) * 100


def _risk_report(label: str, series: pd.Series, benchmark_close: pd.Series) -> dict:
    common_dates = series.index.intersection(benchmark_close.index)
    strategy_returns = series.reindex(common_dates).pct_change().dropna() * 100
    benchmark_returns = benchmark_close.reindex(common_dates).pct_change().dropna() * 100
    aligned_dates = strategy_returns.index.intersection(benchmark_returns.index)
    strategy_returns = strategy_returns.reindex(aligned_dates)
    benchmark_returns = benchmark_returns.reindex(aligned_dates)

    report = {
        "label": label,
        "max_drawdown_pct": round(max_drawdown_pct(series), 2),
        "expected_shortfall_pct_95": round(expected_shortfall_pct(strategy_returns, confidence=0.95), 3),
        "time_under_water": time_under_water(series),
        "downside_capture_pct_vs_spy": downside_capture_pct(strategy_returns, benchmark_returns),
        "upside_capture_pct_vs_spy": upside_capture_pct(strategy_returns, benchmark_returns),
    }
    return report


def _print_report(report: dict) -> None:
    tuw = report["time_under_water"]
    dcap = report["downside_capture_pct_vs_spy"]
    ucap = report["upside_capture_pct_vs_spy"]
    print(f"  {report['label']}")
    print(f"    max_drawdown_pct:              {report['max_drawdown_pct']}")
    print(f"    expected_shortfall_pct (95%):  {report['expected_shortfall_pct_95']}")
    print(f"    max_days_under_water:          {tuw['max_days_under_water']} ({tuw['pct_of_period_under_water']:.1f}% of period)")
    print(f"    downside_capture_pct vs SPY:   {'n/a (no down periods)' if dcap is None else round(dcap, 1)}")
    print(f"    upside_capture_pct vs SPY:     {'n/a (no up periods)' if ucap is None else round(ucap, 1)}")


def main() -> None:
    print(f"Fetching {len(config.UNIVERSE)} UNIVERSE tickers, {len(config.DEFENSIVE_CARRY_TICKERS)} "
          f"defensive-carry tickers, and SPY over {config.LOOKBACK_DAYS} sessions...")
    universe_data = fetch_historical(config.UNIVERSE, lookback_days=config.LOOKBACK_DAYS)
    carry_data = fetch_historical(config.DEFENSIVE_CARRY_TICKERS, lookback_days=config.LOOKBACK_DAYS)
    spy_data = fetch_historical(["SPY"], lookback_days=config.LOOKBACK_DAYS)

    missing_carry = set(config.DEFENSIVE_CARRY_TICKERS) - set(carry_data)
    if missing_carry:
        raise SystemExit(f"Defensive-carry ticker(s) failed to fetch, aborting: {sorted(missing_carry)}")

    baseline_index = _equal_weight_index(universe_data, config.LOOKBACK_DAYS)
    carry_index = _equal_weight_index(carry_data, config.LOOKBACK_DAYS)
    spy_close = spy_data["SPY"]["close"]

    print(f"\nBaseline (UNIVERSE equal-weight) window: {baseline_index.index.min().date()} to {baseline_index.index.max().date()}, {len(baseline_index)} sessions")
    print(f"Carry (TLT/IEF/SHY/GLD equal-weight) window: {carry_index.index.min().date()} to {carry_index.index.max().date()}, {len(carry_index)} sessions")

    # --- Correlation: does the carry basket actually diversify anything?
    common = baseline_index.index.intersection(carry_index.index).intersection(spy_close.index)
    baseline_ret = baseline_index.reindex(common).pct_change().dropna()
    carry_ret = carry_index.reindex(common).pct_change().dropna()
    spy_ret = spy_close.reindex(common).pct_change().dropna()
    print("\nDaily-return correlation:")
    print(f"  carry basket vs UNIVERSE baseline: {carry_ret.corr(baseline_ret):.3f}")
    print(f"  carry basket vs SPY:                {carry_ret.corr(spy_ret):.3f}")
    print("  per-ticker vs SPY:")
    for ticker, df in carry_data.items():
        ticker_ret = df["close"].reindex(common).pct_change().dropna()
        aligned = ticker_ret.index.intersection(spy_ret.index)
        print(f"    {ticker}: {ticker_ret.reindex(aligned).corr(spy_ret.reindex(aligned)):.3f}")

    # --- Combined-portfolio risk shape: baseline alone vs baseline+carry
    print("\nCombined-portfolio risk shape (initial_total=$100,000):")
    reports = [_risk_report("Baseline (UNIVERSE only, 0% carry)", baseline_index.reindex(common), spy_close)]
    for weight in CANDIDATE_CARRY_WEIGHTS:
        blend = buy_and_hold(
            stable_close=baseline_index.reindex(common),
            leveraged_close=carry_index.reindex(common),
            stable_weight=1 - weight,
            leveraged_weight=weight,
            initial_total=100_000.0,
        )
        reports.append(_risk_report(f"Baseline + {weight * 100:.0f}% carry", blend["series"], spy_close))

    for report in reports:
        _print_report(report)
        print()

    print(
        "CAVEATS (real-data-check skill, section 4): single lookback window, no walk-forward or "
        "out-of-sample split has been designed for this probe yet -- that would be the next step if "
        "this looks promising, not part of this round. Testing 3 candidate weights (10/20/30%) alongside "
        "the 0% baseline is itself a small multiple-comparisons surface -- treat any one weight looking "
        "best as suggestive, not conclusive. This is a research probe; it does not justify any live or "
        "paper-trading allocation change on its own."
    )


if __name__ == "__main__":
    main()
