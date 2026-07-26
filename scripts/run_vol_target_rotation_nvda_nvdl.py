"""
Tests the continuous volatility-targeting rotation strategy
(strategies/vol_target_rotation.py) on NVDA/NVDL -- a SINGLE STOCK paired
with its 2x leveraged fund (GraniteShares), rather than a diversified
index. Never tested with any mechanism in this project before.

IMPORTANT CAVEAT printed at the end: NVDL only launched Dec 2022, so
there's only ~3.6 years of history total -- far less than SOXX/SOXL or
SPY/UPRO's 16+ years, and it covers almost entirely ONE specific market
era (the 2023-2026 AI-driven NVDA rally). Any result here is much weaker
evidence than the other pairs' -- a single-stock result over one bull
run is close to the textbook definition of a small, regime-specific
sample, not a validated finding (see memory: feedback_rigor_before_trust
for why this project treats that combination with real skepticism).

Same discipline otherwise: next-day-open execution built into the
strategy itself, tax/cost modeling (37% short-term capital gains, 0.05%
round-trip cost) included throughout the grid search AND confirmation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.vol_target_rotation import grid_search_vol_target, simulate_vol_target_rotation

STABLE_TICKER = "NVDA"
LEVERAGED_TICKER = "NVDL"
LOOKBACK_DAYS = 4200  # NVDL will just return however much real history it has (~904 days)
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 100  # shorter than the usual 200 -- NVDL doesn't have 200+250 days to spare for warmup
VOL_LOOKBACK_DAYS = 20
REBALANCE_CHECK_DAYS = 21
BAND_PCT = 5.0
TAX_RATE = 0.37
COST_PCT = 0.0005

TARGET_VOL_OPTIONS = (0.5, 1.0, 1.5, 2.0, 2.5)
MAX_LEVERAGED_WEIGHT_OPTIONS = (0.6, 0.8, 1.0)


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).")
    print(f"NOTE: NVDL's full history is only {len(dates)} trading days (~{len(dates)/252:.1f} years) -- see module docstring caveat.\n")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery: {dates[0].date()} to {discovery_end.date()} | Confirmation: {confirmation_start.date()} to {dates[-1].date()}\n")

    discovery_dates = dates[dates <= discovery_end]
    print("=== Grid search on DISCOVERY (tax/cost included throughout) ===")
    grid_df = grid_search_vol_target(
        stable_close.reindex(discovery_dates), leveraged_close.reindex(discovery_dates),
        stable_open.reindex(discovery_dates), leveraged_open.reindex(discovery_dates),
        target_vol_options=TARGET_VOL_OPTIONS, max_leveraged_weight_options=MAX_LEVERAGED_WEIGHT_OPTIONS,
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        tax_rate=TAX_RATE, cost_pct=COST_PCT,
    )
    print(grid_df.head(5).to_string(index=False))

    best = grid_df.iloc[0]
    print(f"\nBest by Calmar: target_vol_pct={best['target_vol_pct']}, max_leveraged_weight={best['max_leveraged_weight']}\n")

    print("=== Applying that SAME combo to the CONFIRMATION period ===")
    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        target_vol_pct=best["target_vol_pct"], max_leveraged_weight=best["max_leveraged_weight"],
        trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=VOL_LOOKBACK_DAYS,
        rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=BAND_PCT,
        start_date=confirmation_start, tax_rate=TAX_RATE, cost_pct=COST_PCT,
    )
    series = result["series"]
    stable_conf = stable_close.reindex(series.index)
    leveraged_conf = leveraged_close.reindex(series.index)
    baseline = buy_and_hold(stable_conf, leveraged_conf, 0.5, 0.5)

    comparison = pd.DataFrame([
        {"strategy": f"vol-target rotation (vol={best['target_vol_pct']}, cap={best['max_leveraged_weight']:.0%})",
         "n_trades": result["n_trades"],
         "cagr_pct": round(cagr_pct(series), 2), "max_drawdown_pct": round(max_drawdown_pct(series), 1),
         "total_tax_paid": round(result["total_tax_paid"], 0), "total_cost_paid": round(result["total_cost_paid"], 0)},
        {"strategy": "buy & hold 50/50 (no tax exposure)", "n_trades": 0,
         "cagr_pct": round(cagr_pct(baseline["series"]), 2), "max_drawdown_pct": round(baseline["max_drawdown_pct"], 1),
         "total_tax_paid": 0, "total_cost_paid": 0},
    ])
    print(comparison.to_string(index=False))

    beats_both = (
        cagr_pct(series) > cagr_pct(baseline["series"])
        and max_drawdown_pct(series) > baseline["max_drawdown_pct"]
    )
    print(f"\nBeats 50/50 buy-and-hold on BOTH CAGR and drawdown (after-tax): {beats_both}")
    print(
        "\nCAVEAT: this entire test spans only ~"
        f"{len(dates)/252:.1f} years, almost all of it the 2023-2026 NVDA AI rally -- "
        "one stock, one market era. Treat this result as exploratory at best, not "
        "comparable in confidence to the SOXX/SOXL or SPY/UPRO results (16+ years, "
        "multiple market regimes each)."
    )


if __name__ == "__main__":
    main()
