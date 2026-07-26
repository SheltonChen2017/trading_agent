"""
Compares 6 configurations on SOXX/SOXL -- the one pair with a real,
validated result so far -- to test ideas 1-4 the user asked for:

  A. Baseline: vol-targeting, standard 5% rebalance band (reference point,
     same as the earlier confirmed result: ~33.5% CAGR / -48.8% DD)
  B. Idea #1: vol-targeting with a MUCH WIDER rebalance band (15%),
     attacking trade frequency / tax drag directly
  C. Idea #2: Kelly-criterion sizing instead of inverse-volatility sizing
     (uses SIGNED mean return, not just unsigned volatility)
  D. Idea #2+#3: Kelly sizing + one-way profit ratchet (never buy back
     up into the leveraged leg)
  E. Idea #2+#4: Kelly sizing + trend-acceleration dampening
  F. Idea #2+#3+#4: Kelly + ratchet + acceleration, all combined

Same discipline throughout: grid search on DISCOVERY only (with tax/cost
modeling included in the search itself, not bolted on after), confirmed
on the untouched holdout period, compared to the SAME untaxed 50/50
buy-and-hold baseline used everywhere else in this project.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.market_data import fetch_historical
from strategies.kelly_rotation import grid_search_kelly, simulate_kelly_rotation
from strategies.leverage_rotation import buy_and_hold, cagr_pct, max_drawdown_pct
from strategies.vol_target_rotation import grid_search_vol_target, simulate_vol_target_rotation

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS = 4200
DISCOVERY_FRAC = 0.6
TREND_LOOKBACK_DAYS = 200
LOOKBACK_FOR_SIZING = 20
REBALANCE_CHECK_DAYS = 21
TAX_RATE = 0.37
COST_PCT = 0.0005


def main():
    print(f"Fetching real historical data for {STABLE_TICKER}/{LEVERAGED_TICKER} over {LOOKBACK_DAYS} trading days...")
    data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS)
    stable_close = data[STABLE_TICKER]["close"]
    leveraged_close = data[LEVERAGED_TICKER]["close"]
    stable_open = data[STABLE_TICKER]["open"]
    leveraged_open = data[LEVERAGED_TICKER]["open"]
    dates = stable_close.index.intersection(leveraged_close.index).sort_values()
    print(f"Got {len(dates)} overlapping trading days ({dates[0].date()} to {dates[-1].date()}).")

    split_idx = int(len(dates) * DISCOVERY_FRAC)
    discovery_end = dates[split_idx - 1]
    confirmation_start = dates[split_idx]
    print(f"Discovery: {dates[0].date()} to {discovery_end.date()} | Confirmation: {confirmation_start.date()} to {dates[-1].date()}\n")
    discovery_dates = dates[dates <= discovery_end]

    d_sc, d_lc, d_so, d_lo = [s.reindex(discovery_dates) for s in (stable_close, leveraged_close, stable_open, leveraged_open)]

    results = []

    def run_vol_target(label, band_pct):
        grid = grid_search_vol_target(
            d_sc, d_lc, d_so, d_lo,
            trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=LOOKBACK_FOR_SIZING,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=band_pct,
            tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        best = grid.iloc[0]
        result = simulate_vol_target_rotation(
            stable_close, leveraged_close, stable_open, leveraged_open,
            target_vol_pct=best["target_vol_pct"], max_leveraged_weight=best["max_leveraged_weight"],
            trend_lookback_days=TREND_LOOKBACK_DAYS, vol_lookback_days=LOOKBACK_FOR_SIZING,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=band_pct,
            start_date=confirmation_start, tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        _record(label, result, f"vol={best['target_vol_pct']},cap={best['max_leveraged_weight']:.0%},band={band_pct}%")

    def run_kelly(label, one_way_ratchet, use_trend_acceleration, band_pct=5.0):
        grid = grid_search_kelly(
            d_sc, d_lc, d_so, d_lo,
            trend_lookback_days=TREND_LOOKBACK_DAYS, kelly_lookback_days=LOOKBACK_FOR_SIZING,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=band_pct,
            one_way_ratchet=one_way_ratchet, use_trend_acceleration=use_trend_acceleration,
            tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        best = grid.iloc[0]
        result = simulate_kelly_rotation(
            stable_close, leveraged_close, stable_open, leveraged_open,
            kelly_fraction=best["kelly_fraction"], max_leveraged_weight=best["max_leveraged_weight"],
            trend_lookback_days=TREND_LOOKBACK_DAYS, kelly_lookback_days=LOOKBACK_FOR_SIZING,
            rebalance_check_days=REBALANCE_CHECK_DAYS, band_pct=band_pct,
            one_way_ratchet=one_way_ratchet, use_trend_acceleration=use_trend_acceleration,
            start_date=confirmation_start, tax_rate=TAX_RATE, cost_pct=COST_PCT,
        )
        _record(label, result, f"kelly_frac={best['kelly_fraction']},cap={best['max_leveraged_weight']:.0%}")

    def _record(label, result, params):
        series = result["series"]
        results.append({
            "config": label, "params": params, "n_trades": result["n_trades"],
            "cagr_pct": round(cagr_pct(series), 2), "max_drawdown_pct": round(max_drawdown_pct(series), 1),
            "total_tax_paid": round(result["total_tax_paid"], 0),
        })
        print(f"  done: {label}")

    print("Running configurations (this takes a few minutes)...")
    run_vol_target("A. vol-target, band=5% (baseline)", band_pct=5.0)
    run_vol_target("B. vol-target, band=15% (idea #1: wide band)", band_pct=15.0)
    run_kelly("C. Kelly sizing (idea #2)", one_way_ratchet=False, use_trend_acceleration=False)
    run_kelly("D. Kelly + one-way ratchet (idea #2+#3)", one_way_ratchet=True, use_trend_acceleration=False)
    run_kelly("E. Kelly + trend acceleration (idea #2+#4)", one_way_ratchet=False, use_trend_acceleration=True)
    run_kelly("F. Kelly + ratchet + acceleration (all combined)", one_way_ratchet=True, use_trend_acceleration=True)

    conf_dates = dates[dates >= confirmation_start]
    baseline = buy_and_hold(stable_close.reindex(conf_dates), leveraged_close.reindex(conf_dates), 0.5, 0.5)
    results.append({
        "config": "Baseline: buy & hold 50/50 (no tax)", "params": "-", "n_trades": 0,
        "cagr_pct": round(cagr_pct(baseline["series"]), 2), "max_drawdown_pct": round(baseline["max_drawdown_pct"], 1),
        "total_tax_paid": 0,
    })

    print("\n=== CONFIRMATION PERIOD RESULTS (after-tax/cost) ===")
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()
