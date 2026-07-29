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


def test_account_and_asset_preflight_rejects_a_broker_trading_block():
    account = type("Account", (), {
        "id": "paper-account",
        "status": _FakeEnumValue("ACTIVE"),
        "equity": "10000",
        "cash": "5000",
        "buying_power": "5000",
        "trading_blocked": True,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
    })()
    fake_client = type("FakeClient", (), {"get_account": staticmethod(lambda: account)})()
    original_get_client = broker._get_client
    original_paper = broker.PAPER_TRADING
    broker._get_client = lambda: fake_client
    broker.PAPER_TRADING = True
    try:
        try:
            broker.assert_account_and_asset_ready("AAPL")
            assert False, "expected broker-side trading block to fail preflight"
        except broker.BrokerPreflightError as exc:
            assert "trading_blocked" in str(exc)
    finally:
        broker._get_client = original_get_client
        broker.PAPER_TRADING = original_paper


def test_account_and_asset_preflight_rejects_an_untradable_asset():
    account = type("Account", (), {
        "id": "paper-account",
        "status": _FakeEnumValue("ACTIVE"),
        "equity": "10000",
        "cash": "5000",
        "buying_power": "5000",
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
    })()
    asset = type("Asset", (), {
        "symbol": "AAPL",
        "status": _FakeEnumValue("active"),
        "asset_class": _FakeEnumValue("us_equity"),
        "tradable": False,
        "fractionable": True,
    })()
    fake_client = type("FakeClient", (), {
        "get_account": staticmethod(lambda: account),
        "get_asset": staticmethod(lambda ticker: asset),
    })()
    original_get_client = broker._get_client
    original_paper = broker.PAPER_TRADING
    broker._get_client = lambda: fake_client
    broker.PAPER_TRADING = True
    try:
        try:
            broker.assert_account_and_asset_ready("AAPL")
            assert False, "expected untradable asset to fail preflight"
        except broker.BrokerPreflightError as exc:
            assert "not broker-tradable" in str(exc)
    finally:
        broker._get_client = original_get_client
        broker.PAPER_TRADING = original_paper


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
    test_submit_market_order_refuses_live_without_confirmation()
    test_submit_market_order_requires_idempotency_key()
    test_submit_limit_order_requires_idempotency_key()
    test_find_order_by_client_id_returns_the_complete_material_identity()
    test_find_order_by_client_id_market_order_has_no_limit_price()
    test_account_and_asset_preflight_rejects_a_broker_trading_block()
    test_account_and_asset_preflight_rejects_an_untradable_asset()
    print("All Alpaca broker tests passed.")
