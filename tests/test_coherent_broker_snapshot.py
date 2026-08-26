"""Account-scoped broker session and executable portfolio evidence barriers."""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

import execution.alpaca_broker as broker
from assistant.portfolio_snapshot import (
    BrokerSnapshotCoherenceError,
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
)
from execution.broker_contract import BrokerOrderIntegrityError
from risk.execution_gate import (
    TradeIntent,
    authorize_trade_intent,
    validate_trade_intent,
)


def _account(
    *,
    account_id: str = "paper-account-1",
    equity: str = "1100.00",
    cash: str = "1000.00",
    buying_power: str = "1000.00",
    paper: bool = True,
) -> dict:
    return {
        "account_id": account_id,
        "status": "ACTIVE",
        "equity": float(equity),
        "equity_decimal": equity,
        "cash": float(cash),
        "cash_decimal": cash,
        "buying_power": float(buying_power),
        "buying_power_decimal": buying_power,
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
        "paper": paper,
    }


def _position(*, shares: str = "2", market_value: str = "100.00") -> dict:
    return {
        "ticker": "AAA",
        "shares": float(shares),
        "shares_decimal": shares,
        "avg_entry_price": 45.0,
        "avg_entry_price_decimal": "45.00",
        "current_price": 50.0,
        "current_price_decimal": "50.00",
        "market_value": float(market_value),
        "market_value_decimal": market_value,
        "unrealized_pl": 10.0,
    }


def _order(
    *,
    status: str = "new",
    filled_qty: str = "0",
    filled_avg_price: str | None = None,
) -> dict:
    return {
        "order_id": "order-1",
        "client_order_id": "client-1",
        "ticker": "BBB",
        "shares": 2.0,
        "shares_decimal": "2",
        "notional": None,
        "notional_decimal": None,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "limit_price_decimal": None,
        "time_in_force": "day",
        "status": status,
        "filled_qty": float(filled_qty),
        "filled_qty_decimal": filled_qty,
        "filled_avg_price": (
            None if filled_avg_price is None else float(filled_avg_price)
        ),
        "filled_avg_price_decimal": filled_avg_price,
        "submitted_at": "2026-08-26T15:00:00+00:00",
        "updated_at": "2026-08-26T15:00:01+00:00",
        "filled_at": None,
        "canceled_at": None,
        "expired_at": None,
        "failed_at": None,
        "replaced_at": None,
        "replaces": None,
        "replaced_by": None,
    }


class _ScriptedSession:
    PAPER_TRADING = True
    account_mode = "paper"

    def __init__(
        self,
        *,
        accounts: list[dict],
        order_books: list[list[dict]],
        positions: list[list[dict]],
    ) -> None:
        self._accounts = iter(deepcopy(accounts))
        self._order_books = iter(deepcopy(order_books))
        self._positions = iter(deepcopy(positions))
        self.calls: list[str] = []
        self.submit_count = 0

    def get_account(self) -> dict:
        self.calls.append("account")
        return next(self._accounts)

    def get_open_orders(self) -> list[dict]:
        self.calls.append("orders")
        return next(self._order_books)

    def get_open_positions(self) -> list[dict]:
        self.calls.append("positions")
        return next(self._positions)

    def submit_market_order(self, *_args, **_kwargs):
        self.submit_count += 1
        raise AssertionError("snapshot acquisition must never submit")


def _one_attempt_session(
    *,
    account_a: dict | None = None,
    account_b: dict | None = None,
    orders_a: list[dict] | None = None,
    orders_b: list[dict] | None = None,
    positions: list[dict] | None = None,
) -> _ScriptedSession:
    return _ScriptedSession(
        accounts=[account_a or _account(), account_b or _account()],
        order_books=[
            orders_a if orders_a is not None else [_order()],
            orders_b if orders_b is not None else [_order()],
        ],
        positions=[positions if positions is not None else [_position()]],
    )


def test_strict_capture_returns_account_bound_sha256_evidence_in_exact_sequence():
    session = _one_attempt_session()

    snapshot = build_portfolio_snapshot_from_alpaca(
        broker_session=session,
        require_execution_coherence=True,
        expected_account_id="paper-account-1",
    )

    assert session.calls == ["account", "orders", "positions", "orders", "account"]
    assert session.submit_count == 0
    assert snapshot.source == "alpaca"
    assert snapshot.account_mode == "paper"
    assert snapshot.account_id == "paper-account-1"
    assert snapshot.total_equity_exact == "1100"
    assert snapshot.component_equity_exact == "1100"
    assert snapshot.component_equity_delta_exact == "0"
    assert snapshot.open_orders_available is True
    assert snapshot.positions[0].market_value_exact == "100"
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot.broker_snapshot_id or "")
    captured = datetime.fromisoformat(snapshot.captured_at or "")
    assert captured.tzinfo is not None
    assert captured.utcoffset() is not None


def test_fill_mutation_retries_then_returns_only_the_stable_order_book():
    partially_filled = _order(
        status="partially_filled", filled_qty="1", filled_avg_price="50"
    )
    session = _ScriptedSession(
        accounts=[_account(), _account(), _account(), _account()],
        order_books=[[_order()], [partially_filled], [_order()], [_order()]],
        positions=[[_position()], [_position()]],
    )

    snapshot = build_portfolio_snapshot_from_alpaca(
        broker_session=session,
        require_execution_coherence=True,
        max_coherence_attempts=2,
    )

    assert session.calls == [
        "account",
        "orders",
        "positions",
        "orders",
        "account",
    ] * 2
    assert snapshot.open_orders[0]["status"] == "new"


def test_fill_mutation_refuses_after_bounded_attempts():
    partially_filled = _order(
        status="partially_filled", filled_qty="1", filled_avg_price="50"
    )
    session = _ScriptedSession(
        accounts=[_account(), _account(), _account(), _account()],
        order_books=[
            [_order()],
            [partially_filled],
            [_order()],
            [partially_filled],
        ],
        positions=[[_position()], [_position()]],
    )

    with pytest.raises(BrokerSnapshotCoherenceError, match="did not stabilize"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
            max_coherence_attempts=2,
        )

    assert session.submit_count == 0
    assert len(session.calls) == 10


def test_account_balance_mutation_retries_and_then_refuses():
    session = _ScriptedSession(
        accounts=[
            _account(equity="1100"),
            _account(equity="1101"),
            _account(equity="1100"),
            _account(equity="1101"),
        ],
        order_books=[[_order()], [_order()], [_order()], [_order()]],
        positions=[[_position()], [_position()]],
    )

    with pytest.raises(BrokerSnapshotCoherenceError, match="did not stabilize"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
            max_coherence_attempts=2,
        )

    assert session.submit_count == 0


def test_position_component_mutation_retries_before_accepting_consistent_values():
    session = _ScriptedSession(
        accounts=[_account(), _account(), _account(), _account()],
        order_books=[[_order()], [_order()], [_order()], [_order()]],
        positions=[[_position(market_value="101")], [_position(market_value="100")]],
    )

    snapshot = build_portfolio_snapshot_from_alpaca(
        broker_session=session,
        require_execution_coherence=True,
        max_coherence_attempts=2,
    )

    assert len(session.calls) == 10
    assert snapshot.component_equity_delta_exact == "0"


def test_component_disagreement_refuses_instead_of_overwriting_broker_equity():
    session = _ScriptedSession(
        accounts=[_account(), _account(), _account(), _account()],
        order_books=[[_order()], [_order()], [_order()], [_order()]],
        positions=[[_position(market_value="101")], [_position(market_value="101")]],
    )

    with pytest.raises(BrokerSnapshotCoherenceError, match="did not stabilize"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
            max_coherence_attempts=2,
        )

    assert session.submit_count == 0


@pytest.mark.parametrize(
    ("paper", "mode"),
    [(False, "live"), (True, "manual")],
)
def test_live_or_manual_session_is_rejected_before_any_broker_read(paper, mode):
    session = _one_attempt_session()
    session.PAPER_TRADING = paper
    session.account_mode = mode

    with pytest.raises(BrokerSnapshotCoherenceError, match="paper broker session"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session, require_execution_coherence=True
        )

    assert session.calls == []
    assert session.submit_count == 0


def test_foreign_account_is_rejected_and_never_submitted():
    session = _one_attempt_session()

    with pytest.raises(BrokerSnapshotCoherenceError, match="expected account"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
            expected_account_id="another-paper-account",
        )

    assert session.calls == ["account", "orders", "positions", "orders", "account"]
    assert session.submit_count == 0


def test_account_identity_rotation_retries_then_refuses():
    session = _ScriptedSession(
        accounts=[
            _account(account_id="account-a"),
            _account(account_id="account-b"),
            _account(account_id="account-a"),
            _account(account_id="account-b"),
        ],
        order_books=[[_order()], [_order()], [_order()], [_order()]],
        positions=[[_position()], [_position()]],
    )

    with pytest.raises(BrokerSnapshotCoherenceError, match="did not stabilize"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
            max_coherence_attempts=2,
        )

    assert session.submit_count == 0


def test_malformed_active_order_fails_through_strict_order_contract():
    malformed = _order()
    malformed["submitted_at"] = None
    session = _one_attempt_session(orders_a=[malformed], orders_b=[malformed])

    with pytest.raises(BrokerOrderIntegrityError) as exc_info:
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
        )

    assert exc_info.value.code == "invalid_submitted_at"
    assert session.submit_count == 0


def test_rounded_only_active_order_numeric_is_not_exact_execution_evidence():
    rounded_only = _order()
    rounded_only["shares_decimal"] = None
    session = _one_attempt_session(
        orders_a=[rounded_only], orders_b=[rounded_only]
    )

    with pytest.raises(BrokerOrderIntegrityError) as exc_info:
        build_portfolio_snapshot_from_alpaca(
            broker_session=session,
            require_execution_coherence=True,
        )

    assert exc_info.value.code == "missing_exact_order_numeric"
    assert session.submit_count == 0


def test_session_freezes_credentials_mode_and_trading_client_through_lookup_and_submit(
    monkeypatch,
):
    account_model = SimpleNamespace(
        id="paper-account-1",
        status="ACTIVE",
        equity="1100",
        cash="1000",
        buying_power="1000",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        transfers_blocked=False,
    )
    asset_model = SimpleNamespace(
        symbol="AAA",
        status="active",
        asset_class="us_equity",
        tradable=True,
        fractionable=True,
    )
    submitted_order = SimpleNamespace(
        id="submitted-1",
        client_order_id="stable-client-id",
        symbol="AAA",
        qty="1",
        side="buy",
        type="market",
        time_in_force="day",
        status="new",
        filled_qty="0",
        filled_avg_price=None,
        submitted_at="2026-08-26T15:00:00+00:00",
    )

    class FakeTradingClient:
        def __init__(self):
            self.calls: list[str] = []

        def get_account(self):
            self.calls.append("account")
            return account_model

        def get_asset(self, ticker):
            self.calls.append(f"asset:{ticker}")
            return asset_model

        def submit_order(self, _request):
            self.calls.append("submit")
            return submitted_order

        def get_order_by_client_id(self, client_order_id):
            self.calls.append(f"lookup:{client_order_id}")
            return submitted_order

    client = FakeTradingClient()
    factory_calls = []

    def fake_factory(key, secret, *, paper):
        factory_calls.append((key, secret, paper))
        return client

    monkeypatch.setenv("APCA_API_KEY_ID", "credential-a")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-a")
    monkeypatch.setattr(broker, "PAPER_TRADING", True)
    monkeypatch.setattr(broker, "_new_trading_client", fake_factory)
    monkeypatch.setattr(broker, "verify_execution_authorization", lambda *_a, **_k: None)
    session = broker.open_alpaca_broker_session()

    # Mutable global configuration rotates after the boundary is open.
    monkeypatch.setenv("APCA_API_KEY_ID", "credential-b")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-b")
    monkeypatch.setattr(broker, "PAPER_TRADING", False)

    result = session.submit_market_order(
        "AAA", 1, idempotency_key="stable-client-id"
    )
    lookup = session.find_order_by_client_id("stable-client-id")

    assert factory_calls == [("credential-a", "secret-a", True)]
    assert session.PAPER_TRADING is True
    assert session.account_mode == "paper"
    assert result["order_id"] == "submitted-1"
    assert lookup and lookup["order_id"] == "submitted-1"
    assert client.calls == [
        "account",
        "asset:AAA",
        "submit",
        "lookup:stable-client-id",
    ]


def test_session_account_mismatch_refuses_without_consuming_bound_authorization():
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    validation = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash=10_000),
        reference_price=60,
        now=datetime(2026, 7, 27, 10, 0),
    )
    assert validation.approved
    authorization = authorize_trade_intent(
        intent,
        validation,
        account_id="paper-account-1",
        account_mode="paper",
        snapshot_id=hashlib.sha256(b"snapshot").hexdigest(),
        policy_fingerprint=hashlib.sha256(b"policy").hexdigest(),
    )

    def account_model(account_id):
        return SimpleNamespace(
            id=account_id,
            status="ACTIVE",
            equity="10000",
            cash="10000",
            buying_power="10000",
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            transfers_blocked=False,
        )

    asset = SimpleNamespace(
        symbol="KO",
        status="active",
        asset_class="us_equity",
        tradable=True,
        fractionable=True,
    )
    accepted = SimpleNamespace(
        id="accepted-1",
        client_order_id="bound-client-id",
        symbol="KO",
        qty="1",
        side="buy",
        type="market",
        time_in_force="day",
        status="new",
        filled_qty="0",
        filled_avg_price=None,
        submitted_at="2026-08-26T15:00:00+00:00",
    )

    class AccountClient:
        def __init__(self, account_id):
            self.account_id = account_id
            self.submit_count = 0

        def get_account(self):
            return account_model(self.account_id)

        def get_asset(self, _ticker):
            return asset

        def submit_order(self, _request):
            self.submit_count += 1
            return accepted

    foreign_client = AccountClient("foreign-paper-account")
    foreign_session = broker.AlpacaBrokerSession(
        key="key-a", secret="secret-a", paper=True, client=foreign_client
    )
    with pytest.raises(PermissionError, match="different broker account"):
        foreign_session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="bound-client-id",
        )
    assert foreign_client.submit_count == 0

    # The mismatch check precedes token consumption: the exact same authority
    # remains usable once against the account it was signed for.
    expected_client = AccountClient("paper-account-1")
    expected_session = broker.AlpacaBrokerSession(
        key="key-a", secret="secret-a", paper=True, client=expected_client
    )
    result = expected_session.submit_market_order(
        "KO",
        1,
        authorization=authorization,
        idempotency_key="bound-client-id",
    )
    assert result["order_id"] == "accepted-1"
    assert expected_client.submit_count == 1


def _raw_account_model(account_id="paper-account-1", **overrides):
    values = {
        "id": account_id,
        "status": "ACTIVE",
        "equity": "10000",
        "cash": "10000",
        "buying_power": "10000",
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _raw_asset_model(symbol="KO", **overrides):
    values = {
        "symbol": symbol,
        "status": "active",
        "asset_class": "us_equity",
        "tradable": True,
        "fractionable": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "missing_flag",
    ["trading_blocked", "account_blocked", "trade_suspended_by_user"],
)
def test_session_refuses_missing_account_safety_flags(missing_flag):
    raw_account = _raw_account_model()
    delattr(raw_account, missing_flag)
    client = SimpleNamespace(
        get_account=lambda: raw_account,
        get_asset=lambda _ticker: _raw_asset_model(),
    )
    session = broker.AlpacaBrokerSession(
        key="key", secret="secret", paper=True, client=client
    )

    with pytest.raises(broker.BrokerPreflightError, match="malformed"):
        session.assert_account_and_asset_ready("KO")


@pytest.mark.parametrize(
    ("asset", "message"),
    [
        (_raw_asset_model(tradable="false"), "malformed tradable"),
        (_raw_asset_model(fractionable="false"), "malformed fractionable"),
        (_raw_asset_model(symbol="MSFT"), "while 'KO' was requested"),
    ],
)
def test_session_refuses_malformed_or_wrong_asset_evidence(asset, message):
    client = SimpleNamespace(
        get_account=lambda: _raw_account_model(),
        get_asset=lambda _ticker: asset,
    )
    session = broker.AlpacaBrokerSession(
        key="key", secret="secret", paper=True, client=client
    )

    with pytest.raises(broker.BrokerPreflightError, match=message):
        session.assert_account_and_asset_ready("KO")


@pytest.mark.parametrize("bad_account_id", [None, "", "unknown", " null "])
def test_session_refuses_unusable_account_identity(bad_account_id):
    client = SimpleNamespace(get_account=lambda: _raw_account_model(bad_account_id))
    session = broker.AlpacaBrokerSession(
        key="key", secret="secret", paper=True, client=client
    )

    with pytest.raises(broker.BrokerPreflightError, match="usable account identity"):
        session.get_account()


def test_session_refuses_account_identity_change_on_every_later_read():
    accounts = iter(
        [_raw_account_model("paper-account-1"), _raw_account_model("paper-account-2")]
    )
    client = SimpleNamespace(get_account=lambda: next(accounts))
    session = broker.AlpacaBrokerSession(
        key="key", secret="secret", paper=True, client=client
    )

    assert session.get_account()["account_id"] == "paper-account-1"
    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_account()


def test_public_submit_facade_cannot_rotate_to_a_second_client(monkeypatch):
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    validation = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash=10_000),
        reference_price=60,
        now=datetime(2026, 7, 27, 10, 0),
    )
    authorization = authorize_trade_intent(
        intent,
        validation,
        account_id="paper-account-1",
        account_mode="paper",
        snapshot_id=hashlib.sha256(b"facade-snapshot").hexdigest(),
        policy_fingerprint=hashlib.sha256(b"facade-policy").hexdigest(),
    )
    accepted = SimpleNamespace(
        id="accepted-facade-1",
        client_order_id="facade-client-id",
        symbol="KO",
        qty="1",
        side="buy",
        type="market",
        time_in_force="day",
        status="new",
        filled_qty="0",
        filled_avg_price=None,
        submitted_at="2026-08-26T15:00:00+00:00",
    )

    class RotatingEnvironmentClient:
        def __init__(self):
            self.submit_count = 0

        def get_account(self):
            return _raw_account_model("paper-account-1")

        def get_asset(self, _ticker):
            # Rotation after readiness begins cannot replace the already-open
            # session/client or alter its captured paper mode.
            monkeypatch.setenv("APCA_API_KEY_ID", "credential-b")
            monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-b")
            broker.PAPER_TRADING = False
            return _raw_asset_model("KO")

        def submit_order(self, _request):
            self.submit_count += 1
            return accepted

    client = RotatingEnvironmentClient()
    factory_calls = []

    def client_factory(key, secret, *, paper):
        factory_calls.append((key, secret, paper))
        return client

    monkeypatch.setenv("APCA_API_KEY_ID", "credential-a")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-a")
    monkeypatch.setattr(broker, "PAPER_TRADING", True)
    monkeypatch.setattr(broker, "_new_trading_client", client_factory)

    result = broker.submit_market_order(
        "KO",
        1,
        authorization=authorization,
        idempotency_key="facade-client-id",
    )

    assert result["order_id"] == "accepted-facade-1"
    assert factory_calls == [("credential-a", "secret-a", True)]
    assert client.submit_count == 1


def test_legacy_read_only_session_path_keeps_incomplete_order_availability_honest():
    class LegacySession:
        def get_account(self):
            return {
                "account_id": "paper-account-1",
                "equity": 1100.0,
                "cash": 1000.0,
                "buying_power": 1000.0,
                "paper": True,
            }

        def get_open_orders(self):
            raise RuntimeError("temporary order endpoint outage")

        def get_open_positions(self):
            return [
                {
                    "ticker": "AAA",
                    "shares": 2.0,
                    "avg_entry_price": 45.0,
                    "current_price": 50.0,
                }
            ]

    snapshot = build_portfolio_snapshot_from_alpaca(
        broker_session=LegacySession(), require_execution_coherence=False
    )

    assert snapshot.open_orders_available is False
    assert snapshot.broker_snapshot_id is None
    assert snapshot.captured_at is None
    assert snapshot.total_equity == 1100.0


@pytest.mark.parametrize("bad_attempts", [True, 0, 6, 1.5])
def test_coherence_retry_bound_rejects_ambiguous_values(bad_attempts):
    with pytest.raises(ValueError, match="max_coherence_attempts"):
        build_portfolio_snapshot_from_alpaca(
            broker_session=_one_attempt_session(),
            require_execution_coherence=True,
            max_coherence_attempts=bad_attempts,
        )
