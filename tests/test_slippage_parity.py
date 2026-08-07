"""
Parity check between how backtest/engine.py and backtest/portfolio_simulator.py
apply config.SLIPPAGE_PCT.

Both treat SLIPPAGE_PCT as a ONE-WAY, per-leg fraction (0.0015 = 0.15%,
applied once entering and once exiting) -- engine.py as a percentage-point
subtraction (`raw_return_pct - 2 * slippage_pct * 100`), portfolio_simulator.py
as a multiplicative price haircut on each leg. These are two different
(additive-approximation vs. multiplicative) formulas for the SAME
convention, so they won't match exactly -- but they should stay close for
realistic slippage/return magnitudes.

Calls the REAL run_backtest()/simulate_portfolio() functions (not
reimplemented copies of their formulas) on a matching single-signal
scenario, so a regression in either file's actual slippage handling is
what gets caught here -- an earlier version of this test only checked two
local re-derivations of the formulas, which would keep passing even if
production code drifted (GPT review, 2026-07-27). Also guards against the
100x-too-small slippage bug previously fixed in portfolio_simulator.py
(Codex review, 2026-07-27).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from backtest.engine import run_backtest
from backtest.portfolio_simulator import simulate_portfolio
from config import SLIPPAGE_PCT


def _flat_series_with_one_signal(days: int, flag_index: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0, scale=0.001, size=days)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1_000_000.0}, index=dates
    )


def _flag_on(ticker: str, date) -> callable:
    def scan_fn(data, as_of=None, **_ignored):
        if as_of != date or ticker not in data:
            return pd.DataFrame(columns=["ticker", "date", "direction", "return_zscore", "volume_zscore"])
        return pd.DataFrame(
            [{"ticker": ticker, "date": as_of, "direction": "up", "return_zscore": 5.0, "volume_zscore": 5.0}]
        )

    return scan_fn


def test_engine_and_simulator_apply_the_default_config_slippage_consistently():
    days = 40
    flag_index = 20
    hold_days = 5
    df = _flat_series_with_one_signal(days, flag_index)
    flag_date = df.index[flag_index]
    scan_fn = _flag_on("A", flag_date)

    engine_result = run_backtest(
        {"A": df}, hold_days=hold_days, slippage_pct=SLIPPAGE_PCT, scan_fn=scan_fn, entry_timing="same_close"
    )
    assert len(engine_result) == 1
    engine_net = engine_result.iloc[0]["net_return_pct"]

    sim_result = simulate_portfolio(
        {"A": df}, scan_fn=scan_fn, hold_days=hold_days, entry_timing="same_close",
        slippage_pct=SLIPPAGE_PCT, initial_cash=10_000.0, position_size_pct=0.5, max_concurrent_positions=5,
    )
    assert sim_result["n_trades"] == 1
    sim_net = sim_result["trade_log"].iloc[0]["net_return_pct"]

    # Different formulas (additive vs. multiplicative), same one-way/per-leg
    # convention -- should land within a few basis points of each other.
    assert abs(engine_net - sim_net) < 0.05, (engine_net, sim_net)


def test_a_100x_slippage_regression_in_the_simulator_would_fail_this_parity_check():
    # Sanity-check the sanity check against the REAL simulate_portfolio():
    # if its slippage handling regressed back to dividing slippage_pct by
    # 100 again (the bug fixed 2026-07-27), it would diverge from the real
    # run_backtest() net by ~0.3 percentage points, not a few basis points.
    days = 40
    flag_index = 20
    hold_days = 5
    df = _flat_series_with_one_signal(days, flag_index)
    flag_date = df.index[flag_index]
    scan_fn = _flag_on("A", flag_date)

    engine_result = run_backtest(
        {"A": df}, hold_days=hold_days, slippage_pct=SLIPPAGE_PCT, scan_fn=scan_fn, entry_timing="same_close"
    )
    engine_net = engine_result.iloc[0]["net_return_pct"]

    regressed_slippage = SLIPPAGE_PCT / 100
    sim_result = simulate_portfolio(
        {"A": df}, scan_fn=scan_fn, hold_days=hold_days, entry_timing="same_close",
        slippage_pct=regressed_slippage, initial_cash=10_000.0, position_size_pct=0.5, max_concurrent_positions=5,
    )
    regressed_sim_net = sim_result["trade_log"].iloc[0]["net_return_pct"]

    assert abs(engine_net - regressed_sim_net) > 0.2


def test_slippage_pct_is_a_small_fraction_not_a_percentage_number():
    # Guards the convention itself: SLIPPAGE_PCT should read as e.g. 0.0015
    # (0.15%), not 15 (which some codebases use for "15%" with a later
    # /100). A value >= 1 here would silently blow up either formula.
    assert 0 < SLIPPAGE_PCT < 0.05


if __name__ == "__main__":
    test_engine_and_simulator_apply_the_default_config_slippage_consistently()
    test_a_100x_slippage_regression_in_the_simulator_would_fail_this_parity_check()
    test_slippage_pct_is_a_small_fraction_not_a_percentage_number()
    print("All slippage parity tests passed.")
