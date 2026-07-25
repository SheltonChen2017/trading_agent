"""
Sanity tests for the Alpaca execution layer. These deliberately never
import the `alpaca` package or hit any network — they only verify the
module's safety gates (unconfigured credentials, live-trading
confirmation) behave correctly, since that's the part that's easy to get
wrong and expensive to get wrong.

Run with: python tests/test_alpaca_broker.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import execution.alpaca_broker as broker


def _clear_alpaca_env():
    os.environ.pop("APCA_API_KEY_ID", None)
    os.environ.pop("APCA_API_SECRET_KEY", None)
    os.environ.pop("CONFIRM_LIVE_TRADING", None)


def test_is_configured_false_without_env_vars():
    _clear_alpaca_env()
    assert broker.is_configured() is False


def test_is_configured_true_with_both_env_vars():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    assert broker.is_configured() is True
    _clear_alpaca_env()


def test_get_account_raises_when_not_configured():
    _clear_alpaca_env()
    try:
        broker.get_account()
        assert False, "expected AlpacaNotConfigured"
    except broker.AlpacaNotConfigured:
        pass


def test_submit_market_order_rejects_bad_share_count():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", 0)
        assert False, "expected ValueError for zero shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_market_order_refuses_live_without_confirmation():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = False
    try:
        broker.submit_market_order("AAPL", 10)
        assert False, "expected LiveTradingNotConfirmed"
    except broker.LiveTradingNotConfirmed:
        pass
    finally:
        broker.PAPER_TRADING = True
        _clear_alpaca_env()


def test_execute_allocation_skips_zero_share_rows():
    _clear_alpaca_env()
    sized = pd.DataFrame(
        [
            {"ticker": "AAA", "direction": "dip", "entry_price": 100.0, "shares": 0,
             "dollar_amount": 0.0, "stop_loss_price": 97.0, "win_probability": 0.4},
        ]
    )
    # All rows are zero-share -> loop body never calls the (unconfigured) client.
    results = broker.execute_allocation(sized)
    assert results == []


if __name__ == "__main__":
    test_is_configured_false_without_env_vars()
    test_is_configured_true_with_both_env_vars()
    test_get_account_raises_when_not_configured()
    test_submit_market_order_rejects_bad_share_count()
    test_submit_market_order_refuses_live_without_confirmation()
    test_execute_allocation_skips_zero_share_rows()
    print("All Alpaca broker tests passed.")
