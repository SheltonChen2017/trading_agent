"""
Sanity tests for the risk manager. Run with: python -m pytest tests/ -v
(or `python tests/test_risk.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from risk.manager import allocate, check_stop_loss, size_position


def _signal(ticker="AAA", close=100.0, direction="dip", win_probability=None):
    return pd.Series(
        {
            "ticker": ticker,
            "date": pd.Timestamp("2024-01-01"),
            "close": close,
            "return_pct": -3.0,
            "return_zscore": -2.5,
            "volume_zscore": 2.0,
            "direction": direction,
            **({"win_probability": win_probability} if win_probability is not None else {}),
        }
    )


def test_size_position_full_size_when_unscored():
    sized = size_position(_signal(close=100.0), account_equity=100_000, max_position_pct=0.05)
    # 100_000 * 0.05 = 5000 -> 50 shares at $100
    assert sized["shares"] == 50
    assert sized["dollar_amount"] == 5000.0
    assert sized["win_probability"] is None


def test_size_position_zero_at_low_confidence():
    sized = size_position(_signal(win_probability=0.4), account_equity=100_000)
    assert sized["shares"] == 0
    assert sized["dollar_amount"] == 0.0


def test_size_position_scales_with_confidence():
    low = size_position(_signal(win_probability=0.6), account_equity=100_000)
    high = size_position(_signal(win_probability=0.95), account_equity=100_000)
    assert high["shares"] > low["shares"] > 0


def test_size_position_stop_loss_price():
    sized = size_position(_signal(close=100.0), stop_loss_pct=0.03)
    assert sized["stop_loss_price"] == 97.0


def test_allocate_respects_total_exposure_cap():
    signals = pd.DataFrame(
        [
            _signal("AAA", close=100.0, win_probability=1.0),
            _signal("BBB", close=100.0, win_probability=0.9),
            _signal("CCC", close=100.0, win_probability=0.85),
        ]
    )
    # Each would want 5% (5000) alone = 15000 total, but cap total exposure at 8% (8000).
    sized = allocate(signals, account_equity=100_000, max_position_pct=0.05, max_total_exposure_pct=0.08)

    assert sized["dollar_amount"].sum() <= 8_000.0 + 1e-6
    # Highest-confidence signal (AAA) should be sized first/fully.
    assert sized.loc[sized["ticker"] == "AAA", "dollar_amount"].iloc[0] == 5000.0


def test_allocate_empty_signals():
    sized = allocate(pd.DataFrame())
    assert sized.empty
    assert list(sized.columns) == [
        "ticker", "direction", "entry_price", "shares", "dollar_amount", "stop_loss_price", "win_probability",
    ]


def test_check_stop_loss_triggers_and_does_not():
    assert check_stop_loss(entry_price=100.0, current_price=96.0, stop_loss_pct=0.03) is True
    assert check_stop_loss(entry_price=100.0, current_price=98.0, stop_loss_pct=0.03) is False


if __name__ == "__main__":
    test_size_position_full_size_when_unscored()
    test_size_position_zero_at_low_confidence()
    test_size_position_scales_with_confidence()
    test_size_position_stop_loss_price()
    test_allocate_respects_total_exposure_cap()
    test_allocate_empty_signals()
    test_check_stop_loss_triggers_and_does_not()
    print("All risk manager tests passed.")
