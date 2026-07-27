"""
Tests for backtest/portfolio_simulator.py -- the capital-constrained,
event-driven portfolio simulator (see its module docstring for context:
memory project_execution_realism_gaps, gap #2).

Uses small, hand-built custom scan_fns (matching run_backtest()'s scan_fn
contract) so every result here is independently verifiable, not just
"runs without crashing" -- same discipline as test_backtest.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from backtest.portfolio_simulator import simulate_portfolio


def _flat_series(days: int, seed: int, start_price: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0005, scale=0.005, size=days)
    close = start_price * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close + 0.3, "high": close * 1.001 + 0.3, "low": close * 0.999, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _flag_once(ticker_to_flag: str, date_to_flag) -> callable:
    def scan_fn(data, as_of=None, **_ignored):
        if as_of != date_to_flag or ticker_to_flag not in data:
            return pd.DataFrame(columns=["ticker", "date", "direction", "return_zscore", "volume_zscore"])
        return pd.DataFrame(
            [{"ticker": ticker_to_flag, "date": as_of, "direction": "up", "return_zscore": 5.0, "volume_zscore": 5.0}]
        )

    return scan_fn


def _flag_all_on_date(date_to_flag) -> callable:
    def scan_fn(data, as_of=None, **_ignored):
        if as_of != date_to_flag:
            return pd.DataFrame(columns=["ticker", "date", "direction", "return_zscore", "volume_zscore"])
        return pd.DataFrame(
            [{"ticker": t, "date": as_of, "direction": "up", "return_zscore": 5.0, "volume_zscore": 5.0} for t in data]
        )

    return scan_fn


def _flag_never(data, as_of=None, **_ignored):
    return pd.DataFrame(columns=["ticker", "date", "direction", "return_zscore", "volume_zscore"])


def test_empty_data_returns_empty_result():
    result = simulate_portfolio({}, initial_cash=10_000.0)
    assert result["equity_curve"].empty
    assert result["n_trades"] == 0
    assert result["final_cash"] == 10_000.0


def test_no_signals_leaves_cash_untouched():
    df = _flat_series(60, seed=0)
    result = simulate_portfolio({"A": df}, scan_fn=_flag_never, initial_cash=10_000.0, hold_days=5)
    assert result["n_trades"] == 0
    assert result["final_cash"] == 10_000.0
    assert result["final_equity"] == 10_000.0


def test_rejects_invalid_entry_timing():
    df = _flat_series(60, seed=0)
    try:
        simulate_portfolio({"A": df}, scan_fn=_flag_never, entry_timing="bogus")
        assert False, "expected ValueError for invalid entry_timing"
    except ValueError:
        pass


def test_single_trade_matches_hand_computed_shares_and_pnl():
    days = 60
    df = _flat_series(days, seed=0)
    hold_days = 5
    flag_date = df.index[30]
    scan_fn = _flag_once("A", flag_date)

    result = simulate_portfolio(
        {"A": df}, scan_fn=scan_fn, hold_days=hold_days, entry_timing="next_open",
        slippage_pct=0.0, initial_cash=10_000.0, position_size_pct=0.10, max_concurrent_positions=5,
    )
    assert result["n_trades"] == 1
    trade = result["trade_log"].iloc[0]

    idx = df.index.get_loc(flag_date)
    expected_entry_price = float(df["open"].iloc[idx + 1])
    expected_exit_price = float(df["open"].iloc[idx + 1 + hold_days])
    expected_shares = (10_000.0 * 0.10) / expected_entry_price
    expected_pnl = expected_shares * (expected_exit_price - expected_entry_price)

    assert abs(trade["entry_price"] - expected_entry_price) < 0.01
    assert abs(trade["exit_price"] - expected_exit_price) < 0.01
    assert abs(trade["shares"] - expected_shares) < 0.001
    assert abs(result["final_cash"] - (10_000.0 + expected_pnl)) < 1.0
    assert not trade["forced_close"]


def test_respects_max_concurrent_positions():
    days = 60
    flag_date = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:][30]
    tickers = {f"T{i}": _flat_series(days, seed=i, start_price=50.0 + i) for i in range(5)}
    scan_fn = _flag_all_on_date(flag_date)

    result = simulate_portfolio(
        tickers, scan_fn=scan_fn, hold_days=5, entry_timing="next_open",
        initial_cash=1_000_000.0, position_size_pct=0.05, max_concurrent_positions=2,
    )
    assert result["n_signals_seen"] == 5
    assert result["n_trades"] == 2  # only the capacity cap's worth actually opened
    assert result["n_signals_skipped_capacity"] == 3


def test_stops_opening_new_positions_once_cash_exhausted():
    days = 60
    flag_date = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:][30]
    tickers = {f"T{i}": _flat_series(days, seed=i, start_price=50.0 + i) for i in range(10)}
    scan_fn = _flag_all_on_date(flag_date)

    # Tiny cash relative to position sizing -> only the first couple of
    # signals (processed in the scanner's own row order) can actually be
    # funded; the rest must be skipped for cash, not silently overspent.
    result = simulate_portfolio(
        tickers, scan_fn=scan_fn, hold_days=5, entry_timing="next_open",
        initial_cash=100.0, position_size_pct=0.5, max_concurrent_positions=10,
    )
    assert result["n_signals_seen"] == 10
    assert result["n_signals_skipped_cash"] > 0
    assert result["final_cash"] >= -1e-6  # never goes negative
    # every closed/open position's committed value should never have exceeded starting cash
    assert result["trade_log"]["position_value"].sum() <= 100.0 + 1e-6 or result["n_trades"] <= 2


def test_force_closes_open_positions_at_end_of_data():
    # Flag a signal near the tail of the USABLE date range (not the very
    # end of the raw data): run_backtest()-style tail trimming guarantees
    # its exit index is in-bounds within the ticker's own data (so it's
    # accepted, not skipped), but its exit DATE falls after the last date
    # this simulation actually iterates over -- so the day-by-day "close
    # when exit_date is reached" check can never fire, and the position
    # must be force-closed in the end-of-run cleanup instead.
    days = 80
    df = _flat_series(days, seed=3)
    hold_days = 10
    dates = df.index
    flag_date = dates[-15]
    scan_fn = _flag_once("A", flag_date)

    result = simulate_portfolio(
        {"A": df}, scan_fn=scan_fn, hold_days=hold_days, entry_timing="same_close",
        initial_cash=10_000.0, position_size_pct=0.5, max_concurrent_positions=5,
    )
    assert result["n_trades"] == 1
    assert bool(result["trade_log"].iloc[0]["forced_close"]) is True
    assert result["final_cash"] == result["final_equity"]  # nothing left open


def test_equity_curve_is_marked_to_market_daily():
    days = 60
    df = _flat_series(days, seed=0)
    flag_date = df.index[10]
    scan_fn = _flag_once("A", flag_date)

    result = simulate_portfolio(
        {"A": df}, scan_fn=scan_fn, hold_days=5, entry_timing="next_open",
        initial_cash=10_000.0, position_size_pct=0.10, max_concurrent_positions=5,
    )
    curve = result["equity_curve"]
    assert not curve.empty
    assert curve.iloc[0] == 10_000.0  # nothing opened yet before the flag date
    assert (curve > 0).all()


if __name__ == "__main__":
    test_empty_data_returns_empty_result()
    test_no_signals_leaves_cash_untouched()
    test_rejects_invalid_entry_timing()
    test_single_trade_matches_hand_computed_shares_and_pnl()
    test_respects_max_concurrent_positions()
    test_stops_opening_new_positions_once_cash_exhausted()
    test_force_closes_open_positions_at_end_of_data()
    test_equity_curve_is_marked_to_market_daily()
    print("All portfolio_simulator tests passed.")
