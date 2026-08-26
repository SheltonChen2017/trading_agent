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
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker


def _session_account_model(account_id="paper-account-1"):
    return SimpleNamespace(
        id=account_id,
        status="ACTIVE",
        equity="1000",
        cash="1000",
        buying_power="1000",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        transfers_blocked=False,
    )


def _session_asset_model(ticker, *, fractionable):
    return SimpleNamespace(
        symbol=ticker,
        status="active",
        asset_class="us_equity",
        tradable=True,
        fractionable=fractionable,
    )


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


def test_fractional_market_order_uses_exact_rest_quantity_text(monkeypatch):
    monkeypatch.setattr(broker, "verify_execution_authorization", lambda *_a, **_k: None)
    captured = {}

    def fake_post(_self, url, payload):
        captured.update(url=url, payload=payload)
        return {
            "id": "fractional-1",
            "client_order_id": payload["client_order_id"],
            "symbol": payload["symbol"],
            "qty": payload["qty"],
            "side": payload["side"],
            "type": payload["type"],
            "time_in_force": payload["time_in_force"],
            "status": "accepted",
        }

    client = type(
        "FractionalClient",
        (),
        {
            "get_account": lambda _self: _session_account_model(),
            "get_asset": lambda _self, ticker: _session_asset_model(
                ticker, fractionable=True
            ),
        },
    )()
    session = broker.AlpacaBrokerSession(
        key="test-key", secret="test-secret", paper=True, client=client
    )
    monkeypatch.setattr(broker.AlpacaBrokerSession, "_http_post_json", fake_post)
    result = session.submit_market_order(
        "AAPL",
        "0.123456789",
        whole_shares_only=False,
        idempotency_key="fractional-client-id",
    )
    assert captured["payload"]["qty"] == "0.123456789"
    assert isinstance(captured["payload"]["qty"], str)
    assert result["shares_decimal"] == "0.123456789"


def test_fractional_order_refuses_a_nonfractionable_asset_before_http(monkeypatch):
    monkeypatch.setattr(broker, "verify_execution_authorization", lambda *_a, **_k: None)
    client = type(
        "NonfractionableClient",
        (),
        {
            "get_account": lambda _self: _session_account_model(),
            "get_asset": lambda _self, ticker: _session_asset_model(
                ticker, fractionable=False
            ),
        },
    )()
    session = broker.AlpacaBrokerSession(
        key="test-key", secret="test-secret", paper=True, client=client
    )
    monkeypatch.setattr(
        broker.AlpacaBrokerSession,
        "_http_post_json",
        lambda *_a, **_k: pytest.fail("nonfractionable order contacted HTTP"),
    )
    with pytest.raises(broker.BrokerPreflightError):
        session.submit_market_order(
            "NOFRAC",
            "0.5",
            whole_shares_only=False,
            idempotency_key="fractional-client-id",
        )


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



# --- Preflight and live-trading guards (mutation testing, 2026-07-29:
# every guard below survived deletion against the whole suite -- including
# the two TRADING_ASSISTANT_LIVE_ACCOUNT_ID checks, which are this repo's
# strongest protection against sending an order to the wrong REAL account).

def _account(status="ACTIVE", account_id="acct-1", **overrides):
    base = {
        "account_id": account_id, "status": status, "equity": 1000.0, "cash": 1000.0,
        "buying_power": 1000.0, "trading_blocked": False, "account_blocked": False,
        "trade_suspended_by_user": False, "transfers_blocked": False, "paper": True,
    }
    base.update(overrides)
    return base


def _with_fake_account(account, asset=None):
    """Patch get_account/get_asset and return a restore callable."""
    originals = (broker.get_account, broker.get_asset)
    broker.get_account = lambda: account
    broker.get_asset = lambda ticker: asset or {
        "ticker": ticker.upper(), "status": "active", "asset_class": "us_equity",
        "tradable": True, "fractionable": True,
    }

    def restore():
        broker.get_account, broker.get_asset = originals

    return restore


def test_preflight_rejects_a_non_active_account_status():
    restore = _with_fake_account(_account(status="ONBOARDING"))
    try:
        broker.assert_account_and_asset_ready("AAPL")
        assert False, "expected a non-ACTIVE account status to be refused"
    except broker.BrokerPreflightError as exc:
        assert "ACTIVE" in str(exc)
    finally:
        restore()


def test_preflight_rejects_a_blocked_account():
    restore = _with_fake_account(_account(trading_blocked=True))
    try:
        broker.assert_account_and_asset_ready("AAPL")
        assert False, "expected a trading-blocked account to be refused"
    except broker.BrokerPreflightError as exc:
        assert "trading_blocked" in str(exc)
    finally:
        restore()


def test_preflight_rejects_a_non_tradable_asset():
    restore = _with_fake_account(
        _account(),
        asset={"ticker": "AAPL", "status": "inactive", "asset_class": "us_equity",
               "tradable": False, "fractionable": True},
    )
    try:
        broker.assert_account_and_asset_ready("AAPL")
        assert False, "expected a non-tradable asset to be refused"
    except broker.BrokerPreflightError as exc:
        assert "not broker-tradable" in str(exc)
    finally:
        restore()


def test_live_preflight_requires_the_expected_account_id_env_var():
    os.environ.pop("TRADING_ASSISTANT_LIVE_ACCOUNT_ID", None)
    restore = _with_fake_account(_account())
    original_paper = broker.PAPER_TRADING
    broker.PAPER_TRADING = False
    try:
        broker.assert_account_and_asset_ready("AAPL")
        assert False, "live execution must require TRADING_ASSISTANT_LIVE_ACCOUNT_ID"
    except broker.LiveTradingNotConfirmed as exc:
        # Must be the MISSING-var message specifically, not the mismatch
        # one. Both mention the env var, so asserting only on the var name
        # let the missing-var guard be deleted without failing this test
        # (the mismatch branch below would then raise instead, since
        # None != the account id) -- caught by mutation testing.
        assert "requires TRADING_ASSISTANT_LIVE_ACCOUNT_ID" in str(exc)
        assert "does not match" not in str(exc)
    finally:
        broker.PAPER_TRADING = original_paper
        restore()


def test_live_preflight_rejects_a_mismatched_account_id():
    restore = _with_fake_account(_account(account_id="the-real-account"))
    original_paper = broker.PAPER_TRADING
    broker.PAPER_TRADING = False
    os.environ["TRADING_ASSISTANT_LIVE_ACCOUNT_ID"] = "some-other-account"
    try:
        broker.assert_account_and_asset_ready("AAPL")
        assert False, "a mismatched live account ID must be refused"
    except broker.LiveTradingNotConfirmed as exc:
        assert "does not match" in str(exc)
    finally:
        broker.PAPER_TRADING = original_paper
        os.environ.pop("TRADING_ASSISTANT_LIVE_ACCOUNT_ID", None)
        restore()


def test_live_preflight_accepts_the_matching_account_id():
    restore = _with_fake_account(_account(account_id="the-real-account"))
    original_paper = broker.PAPER_TRADING
    broker.PAPER_TRADING = False
    os.environ["TRADING_ASSISTANT_LIVE_ACCOUNT_ID"] = "the-real-account"
    try:
        result = broker.assert_account_and_asset_ready("AAPL")
        assert result["account"]["account_id"] == "the-real-account"
    finally:
        broker.PAPER_TRADING = original_paper
        os.environ.pop("TRADING_ASSISTANT_LIVE_ACCOUNT_ID", None)
        restore()


def test_submit_limit_order_refuses_live_without_confirmation():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    original_paper = broker.PAPER_TRADING
    broker.PAPER_TRADING = False
    try:
        broker.submit_limit_order("AAPL", 10, 150.0, idempotency_key="k")
        assert False, "expected LiveTradingNotConfirmed for a live limit order"
    except broker.LiveTradingNotConfirmed:
        pass
    finally:
        broker.PAPER_TRADING = original_paper
        _clear_alpaca_env()


def test_submit_orders_reject_an_invalid_side():
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    broker.PAPER_TRADING = True
    try:
        for call in (
            lambda: broker.submit_market_order("AAPL", 10, side="short", idempotency_key="k"),
            lambda: broker.submit_limit_order("AAPL", 10, 150.0, side="short", idempotency_key="k"),
        ):
            try:
                call()
                assert False, "expected an invalid side to be rejected"
            except ValueError as exc:
                assert "side must be" in str(exc)
    finally:
        _clear_alpaca_env()


def test_find_order_by_client_id_distinguishes_404_from_other_errors():
    # The documented contract: None means the broker CONFIRMED absence
    # (404). Any other failure must propagate, so "definitely not there"
    # is never confused with "couldn't check".
    _clear_alpaca_env()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"
    original_get_client = broker._get_client

    class _Err(Exception):
        def __init__(self, code):
            super().__init__(f"status {code}")
            self.status_code = code

    try:
        def client_raising(code):
            return type("FakeClient", (), {
                "get_order_by_client_id": staticmethod(lambda client_order_id: (_ for _ in ()).throw(_Err(code)))
            })()

        broker._get_client = lambda: client_raising(404)
        assert broker.find_order_by_client_id("idem-1") is None

        broker._get_client = lambda: client_raising(500)
        try:
            broker.find_order_by_client_id("idem-1")
            assert False, "a 500 must propagate, not be reported as confirmed absence"
        except _Err:
            pass
    finally:
        broker._get_client = original_get_client
        _clear_alpaca_env()



def test_functions_requiring_credentials_refuse_when_unconfigured():
    # The module's stated posture is "dormant by design" -- every network
    # entry point must refuse before constructing a client. Mutation
    # testing, 2026-07-29: these three guards were all deletable without
    # failing a test.
    _clear_alpaca_env()
    for call in (
        lambda: broker.get_latest_quote("AAPL"),
        lambda: broker.find_order_by_client_id("idem-1"),
        lambda: broker.run_trade_update_stream(lambda update: None),
    ):
        try:
            call()
            assert False, "expected AlpacaNotConfigured when credentials are absent"
        except broker.AlpacaNotConfigured:
            pass


def test_optional_float_passes_none_through_untouched():
    assert broker._optional_float(None) is None
    assert broker._optional_float("2.5") == 2.5
    assert broker._optional_float(float("nan")) is None
    assert broker._optional_float(float("inf")) is None


@pytest.mark.parametrize("bad", ["not-a-number", object(), True])
def test_optional_float_treats_malformed_broker_numbers_as_unusable(bad):
    assert broker._optional_float(bad) is None


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


def test_normalize_order_captures_the_replacement_chain():
    """Dropping replaced_by/replaces/replaced_at meant a replacement order
    could not be traced back to the proposal it superseded, so the replacement
    could fill while the proposal sat cancel-pending (GPT review, 2026-07-29)."""
    from types import SimpleNamespace

    from execution.alpaca_broker import _normalize_order

    order = SimpleNamespace(
        id="order-2",
        client_order_id="client-2",
        symbol="AAPL",
        qty=10,
        side="buy",
        type="limit",
        limit_price=100.0,
        notional=None,
        time_in_force="day",
        status="accepted",
        filled_qty=0,
        filled_avg_price=None,
        submitted_at=None,
        updated_at=None,
        filled_at=None,
        canceled_at=None,
        expired_at=None,
        failed_at=None,
        replaced_by=None,
        replaces="order-1",
        replaced_at=None,
    )
    normalized = _normalize_order(order)
    assert normalized["replaces"] == "order-1"
    assert normalized["replaced_by"] is None
    assert normalized["replaced_at"] is None


def test_normalize_order_tolerates_a_broker_object_without_chain_fields():
    """Older/partial order objects must not start raising AttributeError."""
    from types import SimpleNamespace

    from execution.alpaca_broker import _normalize_order

    minimal = SimpleNamespace(id="order-9", symbol="AAPL", qty=1, status="new")
    normalized = _normalize_order(minimal)
    assert normalized["replaces"] is None
    assert normalized["replaced_by"] is None


def test_normalize_order_never_turns_a_missing_id_into_literal_none():
    from types import SimpleNamespace

    normalized = broker._normalize_order(
        SimpleNamespace(id=None, symbol="AAPL", qty="1", status="new")
    )

    assert normalized["order_id"] is None


def test_normalize_trade_update_numbers_retain_exact_decimal_companions():
    assert broker._normalized_trade_update_numbers(
        fill_qty="0.123456789", fill_price="100.0001"
    ) == {
        "fill_qty": pytest.approx(0.123456789),
        "fill_qty_decimal": "0.123456789",
        "fill_price": pytest.approx(100.0001),
        "fill_price_decimal": "100.0001",
    }


# --------------------------------------------------------------------------
# FCS-005: a non-finite quote must refuse, not propagate.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), float("-inf"), None, "not a number"]
)
def test_a_non_finite_quote_component_refuses(bad):
    from execution.alpaca_broker import QuoteUnavailable, _required_decimal

    with pytest.raises(QuoteUnavailable):
        _required_decimal(bad, "bid price")


def test_a_usable_quote_component_converts_exactly():
    from decimal import Decimal

    from execution.alpaca_broker import _required_decimal

    # Through str(), so the human-visible value is preserved rather than the
    # float's binary expansion.
    assert _required_decimal(0.1, "bid price") == Decimal("0.1")
    assert _required_decimal("123.456", "ask price") == Decimal("123.456")


def test_the_decimal_nan_comparison_trap_is_what_this_guards():
    """Without the guard, `bid_decimal > 0` RAISES on a NaN bid.

    Not a hypothetical: that comparison is the next statement after the
    conversion in get_latest_quote, and InvalidOperation is an
    ArithmeticError, so it escapes `except ValueError` all the way out.
    """
    from decimal import Decimal, InvalidOperation

    unguarded = Decimal(str(float("nan")))  # what the code used to do
    with pytest.raises(InvalidOperation):
        unguarded > 0


# --- list_account_activities() (broker-activity ingestion, 2026-08-10) ---
# The pinned alpaca-py has no account-activities endpoint, so this is a
# direct REST read. Tests monkeypatch the single HTTP seam
# (_http_get_json) -- no network, no alpaca import.


def test_list_account_activities_raises_when_not_configured():
    _clear_alpaca_env()
    with pytest.raises(broker.AlpacaNotConfigured):
        broker.list_account_activities()


def _fake_pages(monkeypatch, pages):
    """Serve canned pages and capture each requested URL."""
    urls = []

    def fake_get(url):
        urls.append(url)
        return pages[len(urls) - 1]

    monkeypatch.setattr(broker, "_http_get_json", fake_get)
    return urls


def test_list_account_activities_paginates_with_the_last_row_id(monkeypatch):
    rows = [{"id": f"row-{i}", "activity_type": "FEE"} for i in range(5)]
    urls = _fake_pages(monkeypatch, [rows[0:2], rows[2:4], rows[4:5]])
    result = broker.list_account_activities(after="2026-08-01T00:00:00Z", page_size=2)
    assert result == rows
    assert len(urls) == 3
    assert "after=2026-08-01" in urls[0]
    assert "page_token" not in urls[0]
    assert "page_token=row-1" in urls[1]
    assert "page_token=row-3" in urls[2]


def test_list_account_activities_short_final_page_stops_cleanly(monkeypatch):
    urls = _fake_pages(monkeypatch, [[]])
    assert broker.list_account_activities(page_size=2) == []
    assert len(urls) == 1


def test_list_account_activities_refuses_a_stuck_cursor(monkeypatch):
    page = [{"id": "same"}, {"id": "same"}]
    _fake_pages(monkeypatch, [page, page, page])
    with pytest.raises(RuntimeError, match="did not advance"):
        broker.list_account_activities(page_size=2)


def test_list_account_activities_refuses_rows_without_ids(monkeypatch):
    _fake_pages(monkeypatch, [[{"activity_type": "FEE"}]])
    with pytest.raises(RuntimeError, match="missing its id"):
        broker.list_account_activities()


def test_list_account_activities_refuses_a_non_list_response(monkeypatch):
    _fake_pages(monkeypatch, [{"message": "forbidden"}])
    with pytest.raises(RuntimeError, match="unexpected account-activities response"):
        broker.list_account_activities()


def test_list_account_activities_rejects_out_of_range_page_size():
    with pytest.raises(ValueError, match="page_size"):
        broker.list_account_activities(page_size=0)
    with pytest.raises(ValueError, match="page_size"):
        broker.list_account_activities(page_size=101)


@pytest.mark.parametrize("page_size", [True, 1.5, "2"])
def test_list_account_activities_requires_a_real_integer_page_size(page_size):
    with pytest.raises((TypeError, ValueError), match="page_size"):
        broker.list_account_activities(page_size=page_size)
