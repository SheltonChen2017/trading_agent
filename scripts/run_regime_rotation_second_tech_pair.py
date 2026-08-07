"""
Second tech-heavy generalization check for the trend+volatility regime
rotation strategy. The SPY/UPRO cross-pair test (run_regime_rotation_
cross_pair.py) failed -- the QQQ/TQQQ-tuned architecture, independently
grid-searched and confirmed on SPY/UPRO's own data, underperformed plain
50/50 buy-and-hold on both CAGR and drawdown there.

Two live hypotheses for why QQQ/TQQQ worked but SPY/UPRO didn't:
  (a) something specific to QQQ/Nasdaq-100's own price history
  (b) tech-concentration -> higher realized volatility swings -> this
      design happens to exploit THAT, not leverage rotation in general

This tests (b) directly: SOXX (1x semiconductor index) / SOXL (3x
semiconductor, Direxion) -- a DIFFERENT, even more concentrated
tech-adjacent index than QQQ. If this pair ALSO beats its own 50/50
buy-and-hold baseline out-of-sample, that's real evidence for (b). If it
fails the same way SPY/UPRO did, that weakens (b) and points back toward
"QQQ/TQQQ-specific, not yet understood why" as the more honest read.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import calibrate_threshold_from_discovery
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.trend_vol_rotation import (
    build_state_weights,
    grid_search_state_weights,
    simulate_regime_rotation,
)

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
VOL_LOOKBACK_DAYS = 60
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0

# Taxable brokerage account assumption, per user: every realized gain
# taxed at a conservative short-term/ordinary-income rate (37%), since
# rebalances can be spaced only months apart. cost_pct is a rough
# bid-ask-spread/commission estimate for liquid ETFs (5 basis points
# round-trip) -- major brokers charge $0 commission on ETF trades today,
# so spread is the dominant real cost here.
TAX_RATE = 0.37
COST_PCT = 0.0005


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    if STABLE_TICKER not in data or LEVERAGED_TICKER not in data:
        print("Failed to fetch data for one or both tickers.")
        return

    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery period:    {dates[0].date()} to {discovery_end.date()}")
    print(f"Confirmation period: {confirmation_start.date()} to {dates[-1].date()}\n")

    benchmark_df = pd.DataFrame({"close": stable_close.reindex(dates)})
    vol_threshold = calibrate_threshold_from_discovery(benchmark_df, discovery_end, lookback_days=VOL_LOOKBACK_DAYS)

    discovery_dates = dates[dates <= discovery_end]
    discovery_stable_close = stable_close.reindex(discovery_dates)
    discovery_leveraged_close = leveraged_close.reindex(discovery_dates)
    discovery_stable_open = stable_open.reindex(discovery_dates)
    discovery_leveraged_open = leveraged_open.reindex(discovery_dates)

    stable_conf = stable_close.reindex(dates[dates >= confirmation_start])
    leveraged_conf = leveraged_close.reindex(dates[dates >= confirmation_start])
    baseline_5050 = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)  # buy-and-hold never sells -> no tax exposure either way

    rows = []
    for label, tax_rate, cost_pct in (("pre-tax/cost", 0.0, 0.0), ("after-tax/cost", TAX_RATE, COST_PCT)):
        print(f"=== Grid search on DISCOVERY period only ({label}) ===")
        grid_df = grid_search_state_weights(
            discovery_stable_close, discovery_leveraged_close, discovery_stable_open, discovery_leveraged_open,
            vol_threshold_pct=vol_threshold, trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT, tax_rate=tax_rate, cost_pct=cost_pct,
        )
        print(grid_df.to_string(index=False))

        best = grid_df.iloc[0]
        best_weights = build_state_weights(best["low_vol_lev_weight"], best["high_vol_lev_weight"])
        print(f"Best by Calmar ratio on discovery: uptrend_low_vol={best['low_vol_lev_weight']:.0%}, "
              f"uptrend_high_vol={best['high_vol_lev_weight']:.0%}\n")

        regime_result = simulate_regime_rotation(
            stable_close, leveraged_close, stable_open, leveraged_open, vol_threshold_pct=vol_threshold,
            state_weights=best_weights, trend_lookback_days=TREND_LOOKBACK_DAYS,
            vol_lookback_days=VOL_LOOKBACK_DAYS, rebalance_check_days=REBALANCE_CHECK_DAYS,
            band_pct=BAND_PCT, start_date=confirmation_start, tax_rate=tax_rate, cost_pct=cost_pct,
        )
        regime_series = regime_result["series"]
        rows.append({
            "scenario": label,
            "weights": f"{best['low_vol_lev_weight']:.0%}/{best['high_vol_lev_weight']:.0%}",
            "n_trades": regime_result["n_trades"],
            "cagr_pct": round(cagr_pct(regime_series), 2),
            "max_drawdown_pct": round(max_drawdown_pct(regime_series), 1),
            "total_tax_paid": round(regime_result["total_tax_paid"], 0),
            "total_cost_paid": round(regime_result["total_cost_paid"], 0),
        })

    rows.append({
        "scenario": "buy & hold 50/50 (no rebalance, no tax exposure)", "weights": "-", "n_trades": 0,
        "cagr_pct": round(cagr_pct(baseline_5050["series"]), 2),
        "max_drawdown_pct": round(baseline_5050["max_drawdown_pct"], 1),
        "total_tax_paid": 0, "total_cost_paid": 0,
    })

    print("=== Confirmation-period comparison: pre-tax vs. after-tax/cost vs. buy-and-hold ===")
    print(pd.DataFrame(rows).to_string(index=False))

    after_tax_row = rows[1]
    baseline_row = rows[2]
    beats_both_after_tax = (
        after_tax_row["cagr_pct"] > baseline_row["cagr_pct"]
        and after_tax_row["max_drawdown_pct"] > baseline_row["max_drawdown_pct"]
    )
    print(f"\nBeats 50/50 buy-and-hold on BOTH CAGR and drawdown, AFTER tax/cost: {beats_both_after_tax}")
    print(
        f"(Assumes a taxable brokerage account, every realized gain taxed at {TAX_RATE:.0%} "
        f"short-term/ordinary-income rate, {COST_PCT:.2%} round-trip cost per trade. "
        "Buy-and-hold pays no tax at all since it never sells.)"
    )


if __name__ == "__main__":
    main()
