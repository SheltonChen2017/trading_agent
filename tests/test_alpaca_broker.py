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
        broker.submit_market_order("AAPL", 0, idempotency_key="test-key")
        assert False, "expected ValueError for zero shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_market_order_rejects_nan_shares():
    # GPT review, 2026-07-29: `shares <= 0` does not reject NaN (every
    # ordered comparison against NaN is False in Python), so this used to
    # reach client.submit_order() with zero protection at this layer.
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", float("nan"), idempotency_key="test-key")
        assert False, "expected ValueError for NaN shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_market_order_rejects_infinite_shares():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", float("inf"), idempotency_key="test-key")
        assert False, "expected ValueError for infinite shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_market_order_rejects_fractional_shares():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", 1.5, idempotency_key="test-key")
        assert False, "expected ValueError for fractional shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_market_order_rejects_bool_shares():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", True, idempotency_key="test-key")
        assert False, "expected ValueError for bool shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_limit_order_rejects_nan_shares():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_limit_order("AAPL", float("nan"), 150.0, idempotency_key="test-key")
        assert False, "expected ValueError for NaN shares"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_stop_loss_order_rejects_nan_shares():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_stop_loss_order("AAPL", float("nan"), 95.0, idempotency_key="test-key")
        assert False, "expected ValueError for NaN shares"
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
        broker.submit_market_order("AAPL", 10, idempotency_key="test-key")
        assert False, "expected LiveTradingNotConfirmed"
    except broker.LiveTradingNotConfirmed:
        pass
    finally:
        broker.PAPER_TRADING = True
        _clear_alpaca_env()


# --- idempotency_key required (GPT review, 2026-07-31): a broker call
# with no idempotency key at all has ZERO duplicate-order protection, not
# just "less than ideal" protection -- every real caller in this
# project's production paths already supplies one; this only forces any
# future direct caller to supply one too.

def test_submit_market_order_requires_idempotency_key():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        try:
            broker.submit_market_order("AAPL", 10)
            assert False, "expected a missing idempotency_key to raise"
        except TypeError:
            pass  # Python's own required-keyword-argument enforcement
        try:
            broker.submit_market_order("AAPL", 10, idempotency_key="")
            assert False, "expected an empty idempotency_key to raise"
        except ValueError:
            pass
    finally:
        _clear_alpaca_env()


def test_submit_limit_order_requires_idempotency_key():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        try:
            broker.submit_limit_order("AAPL", 10, 150.0, idempotency_key="")
            assert False, "expected an empty idempotency_key to raise"
        except ValueError:
            pass
    finally:
        _clear_alpaca_env()


def test_submit_stop_loss_order_requires_idempotency_key():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        try:
            broker.submit_stop_loss_order("AAPL", 10, 95.0)
            assert False, "expected a missing idempotency_key to raise"
        except TypeError:
            pass
        try:
            broker.submit_stop_loss_order("AAPL", 10, 95.0, idempotency_key="")
            assert False, "expected an empty idempotency_key to raise"
        except ValueError:
            pass
    finally:
        _clear_alpaca_env()


# --- stop_price validation (GPT review, 2026-07-31): submit_stop_loss_
# order() was the one submit function with no validation at all on its
# own price-like argument.

def test_submit_stop_loss_order_rejects_nan_stop_price():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        broker.submit_stop_loss_order("AAPL", 10, float("nan"), idempotency_key="test-key")
        assert False, "expected ValueError for NaN stop_price"
    except ValueError:
        pass
    finally:
        _clear_alpaca_env()


def test_submit_stop_loss_order_rejects_zero_or_negative_stop_price():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        for bad_price in (0.0, -5.0, float("inf")):
            try:
                broker.submit_stop_loss_order("AAPL", 10, bad_price, idempotency_key="test-key")
                assert False, f"expected ValueError for stop_price={bad_price}"
            except ValueError:
                pass
    finally:
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


class _FakeEnumValue:
    """Mimics alpaca-py's enum-like order fields (order.side.value, etc.)
    without importing the real package -- this test file deliberately
    never imports `alpaca` (see module docstring)."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class _FakeOrder:
    def __init__(
        self, order_id, symbol, qty, side, order_type, limit_price=None,
        time_in_force=None, status="accepted", client_order_id=None,
    ):
        self.id = order_id
        self.symbol = symbol
        self.qty = qty
        self.side = _FakeEnumValue(side)
        self.type = _FakeEnumValue(order_type)
        self.limit_price = limit_price
        self.time_in_force = _FakeEnumValue(time_in_force) if time_in_force else None
        self.status = _FakeEnumValue(status)
        self.client_order_id = client_order_id


def test_find_order_by_client_id_returns_the_complete_material_identity():
    # GPT review, 2026-07-28: a prior version returned only order_id/
    # ticker/shares/side/status -- reconciliation had no way to verify
    # order TYPE or limit price, so a market order could be mistaken for
    # a limit order (or vice versa) purely because the lookup never
    # returned the fields needed to tell them apart.
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    fake_client = type("FakeClient", (), {
        "get_order_by_client_id": staticmethod(
            lambda client_order_id: _FakeOrder(
                "order-1", "AAPL", 10, "buy", "limit", limit_price=150.25,
                time_in_force="day", client_order_id=client_order_id,
            )
        ),
    })()
    original_get_client = broker._get_client
    broker._get_client = lambda: fake_client
    try:
        result = broker.find_order_by_client_id("idem-1")
        assert result["order_id"] == "order-1"
        assert result["client_order_id"] == "idem-1"
        assert result["ticker"] == "AAPL"
        assert result["shares"] == 10.0
        assert result["side"] == "buy"
        assert result["type"] == "limit"
        assert result["limit_price"] == 150.25
        assert result["time_in_force"] == "day"
        assert result["status"] == "accepted"
    finally:
        broker._get_client = original_get_client
        _clear_alpaca_env()


def test_find_order_by_client_id_market_order_has_no_limit_price():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    fake_client = type("FakeClient", (), {
        "get_order_by_client_id": staticmethod(
            lambda client_order_id: _FakeOrder("order-2", "TQQQ", 5, "sell", "market")
        ),
    })()
    original_get_client = broker._get_client
    broker._get_client = lambda: fake_client
    try:
        result = broker.find_order_by_client_id("idem-2")
        assert result["type"] == "market"
        assert result["limit_price"] is None
    finally:
        broker._get_client = original_get_client
        _clear_alpaca_env()


def test_submit_stop_loss_order_wires_idempotency_key_to_client_order_id():
    # GPT review, 2026-07-31: submit_stop_loss_order() previously had no
    # idempotency_key parameter at all, so a stop order was never even
    # SENT with a client_order_id -- confirm it now actually reaches the
    # broker request object, not just that the parameter is accepted.
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    captured_requests = []

    def _fake_submit_order(request):
        captured_requests.append(request)
        return _FakeOrder("order-3", "AAPL", 10, "sell", "stop")

    fake_client = type("FakeClient", (), {"submit_order": staticmethod(_fake_submit_order)})()
    original_get_client = broker._get_client
    original_verify = broker.verify_execution_authorization
    broker._get_client = lambda: fake_client
    broker.verify_execution_authorization = lambda *args, **kwargs: None
    try:
        order = broker.submit_stop_loss_order("AAPL", 10, 95.0, idempotency_key="idem-stop-1")
        assert order["order_id"] == "order-3"
        assert len(captured_requests) == 1
        assert captured_requests[0].client_order_id == "idem-stop-1"
    finally:
        broker._get_client = original_get_client
        broker.verify_execution_authorization = original_verify
        broker.PAPER_TRADING = True
        _clear_alpaca_env()


if __name__ == "__main__":
    test_is_configured_false_without_env_vars()
    test_is_configured_true_with_both_env_vars()
    test_get_account_raises_when_not_configured()
    test_submit_market_order_rejects_bad_share_count()
    test_submit_market_order_rejects_nan_shares()
    test_submit_market_order_rejects_infinite_shares()
    test_submit_market_order_rejects_fractional_shares()
    test_submit_market_order_rejects_bool_shares()
    test_submit_limit_order_rejects_nan_shares()
    test_submit_stop_loss_order_rejects_nan_shares()
    test_submit_market_order_refuses_live_without_confirmation()
    test_submit_market_order_requires_idempotency_key()
    test_submit_limit_order_requires_idempotency_key()
    test_submit_stop_loss_order_requires_idempotency_key()
    test_submit_stop_loss_order_rejects_nan_stop_price()
    test_submit_stop_loss_order_rejects_zero_or_negative_stop_price()
    test_execute_allocation_skips_zero_share_rows()
    test_find_order_by_client_id_returns_the_complete_material_identity()
    test_find_order_by_client_id_market_order_has_no_limit_price()
    test_submit_stop_loss_order_wires_idempotency_key_to_client_order_id()
    print("All Alpaca broker tests passed.")
