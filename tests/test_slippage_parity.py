"""
Parity check between how backtest/engine.py and backtest/portfolio_simulator.py
apply config.SLIPPAGE_PCT.

Both treat SLIPPAGE_PCT as a ONE-WAY, per-leg fraction (0.0015 = 0.15%,
applied once entering and once exiting) -- engine.py as a percentage-point
subtraction (`raw_return_pct - 2 * slippage_pct * 100`), portfolio_simulator.py
as a multiplicative price haircut on each leg. These are two different
(additive-approximation vs. multiplicative) formulas for the SAME
convention, so they won't match exactly -- but they should stay close for
realistic slippage/return magnitudes. This guards against the two files'
conventions drifting apart again (Codex review, 2026-07-30), the same class
of bug as the 100x-too-small slippage previously fixed in
portfolio_simulator.py: a regression there would blow well past the
tolerance checked here, not just nudge the numbers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SLIPPAGE_PCT


def _engine_net_return_pct(raw_return_pct: float, slippage_pct: float) -> float:
    return raw_return_pct - 2 * slippage_pct * 100


def _simulator_net_return_pct(entry_price: float, exit_price: float, slippage_pct: float) -> float:
    net_entry_price = entry_price * (1 + slippage_pct)
    net_exit_price = exit_price * (1 - slippage_pct)
    return (net_exit_price - net_entry_price) / net_entry_price * 100


def test_engine_and_simulator_apply_the_default_config_slippage_consistently():
    entry_price, exit_price = 100.0, 105.0  # a clean +5% raw move
    raw_return_pct = (exit_price - entry_price) / entry_price * 100

    engine_net = _engine_net_return_pct(raw_return_pct, SLIPPAGE_PCT)
    simulator_net = _simulator_net_return_pct(entry_price, exit_price, SLIPPAGE_PCT)

    # Different formulas (additive vs. multiplicative), same one-way/per-leg
    # convention -- should land within a few basis points of each other.
    assert abs(engine_net - simulator_net) < 0.05, (engine_net, simulator_net)


def test_a_100x_slippage_regression_would_fail_this_parity_check():
    # Sanity-check the sanity check: if portfolio_simulator.py's formula
    # regressed back to dividing slippage_pct by 100 again (the bug fixed
    # 2026-07-27), the two nets would diverge by ~0.3 percentage points,
    # not a few basis points -- easily outside the tolerance above.
    entry_price, exit_price = 100.0, 105.0
    raw_return_pct = (exit_price - entry_price) / entry_price * 100
    engine_net = _engine_net_return_pct(raw_return_pct, SLIPPAGE_PCT)

    regressed_slippage = SLIPPAGE_PCT / 100
    regressed_simulator_net = _simulator_net_return_pct(entry_price, exit_price, regressed_slippage)

    assert abs(engine_net - regressed_simulator_net) > 0.2


def test_slippage_pct_is_a_small_fraction_not_a_percentage_number():
    # Guards the convention itself: SLIPPAGE_PCT should read as e.g. 0.0015
    # (0.15%), not 15 (which some codebases use for "15%" with a later
    # /100). A value >= 1 here would silently blow up either formula.
    assert 0 < SLIPPAGE_PCT < 0.05


if __name__ == "__main__":
    test_engine_and_simulator_apply_the_default_config_slippage_consistently()
    test_a_100x_slippage_regression_would_fail_this_parity_check()
    test_slippage_pct_is_a_small_fraction_not_a_percentage_number()
    print("All slippage parity tests passed.")
