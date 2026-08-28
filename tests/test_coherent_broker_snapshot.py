"""Account-scoped broker session and executable portfolio evidence barriers."""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import execution.alpaca_broker as broker
import assistant.dispatch_fence as dispatch_fence_module
from assistant.dispatch_fence import (
    execution_dispatch_fence,
    _mint_execution_service_dispatch_permit,
    record_runtime_dispatch_attempt,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_snapshot import (
    BrokerSnapshotCoherenceError,
    build_portfolio_snapshot_from_alpaca,
)
from execution.broker_contract import BrokerOrderIntegrityError
from risk.execution_gate import (
    ExecutionValidationContext,
    TradeIntent,
    authorize_trade_intent,
    validate_trade_intent,
    verify_execution_authorization,
)


def _open_test_session(
    client,
    *,
    key: str = "key",
    secret: str = "secret",
    paper: bool = True,
) -> broker.AlpacaBrokerSession:
    """Use the sealed production constructor with one identity-bearing fake."""
    client._api_key = key
    client._secret_key = secret
    client._sandbox = paper
    client._base_url = (
        broker._TRADING_PAPER_BASE_URL
        if paper
        else broker._TRADING_LIVE_BASE_URL
    )
    client._oauth_token = None
    client._use_basic_auth = False
    original_capture = broker._capture_connection_settings
    original_factory = broker._new_trading_client
    broker._capture_connection_settings = lambda: (key, secret, paper)
    broker._new_trading_client = lambda *_args, **_kwargs: client
    try:
        return broker.AlpacaBrokerSession()
    finally:
        broker._capture_connection_settings = original_capture
        broker._new_trading_client = original_factory


@pytest.fixture(autouse=True)
def _isolated_dispatch_runtime(tmp_path, monkeypatch):
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setattr(dispatch_fence_module, "_RUNTIME_FENCE_ROOT", runtime_root)
    monkeypatch.setattr(dispatch_fence_module, "_RUNTIME_STOP_LOCAL_FAILURE", None)
    with dispatch_fence_module._DISPATCH_PERMITS_GUARD:
        dispatch_fence_module._DISPATCH_PERMITS.clear()
    return tmp_path / "assistant.db"


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
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
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


def _paper_policy() -> TradingPolicy:
    policy = TradingPolicy(
        version="coherent-session-test-v1",
        name="Coherent session test policy",
        execution_mode="paper",
        max_position_pct=0.50,
        max_total_exposure_pct=0.90,
        max_basket_pct=0.90,
        max_leveraged_etf_pct=0.50,
        min_cash_reserve_pct=0.10,
        max_order_value=5_000.0,
        max_open_orders=5,
        allow_new_positions=True,
        whole_shares_only=True,
    )
    policy.validate()
    return policy


def _policy_gate_arguments(policy: TradingPolicy) -> dict:
    """Use the same policy-unit conversion as production validation."""
    return {
        "max_position_pct": policy.max_position_pct,
        "max_total_exposure_pct": policy.max_total_exposure_pct,
        "max_basket_pct": policy.max_basket_pct * 100,
        "max_leveraged_etf_pct": policy.max_leveraged_etf_pct * 100,
        "max_stale_price_minutes": policy.max_stale_price_minutes,
        "max_slippage_pct": policy.max_slippage_pct,
        "max_spread_pct": policy.max_spread_pct,
        "earnings_blackout_days": policy.earnings_blackout_days,
        "max_order_value": policy.max_order_value,
        "min_cash_reserve_pct": policy.min_cash_reserve_pct,
        "whole_shares_only": policy.whole_shares_only,
    }


def _bind_test_quote(
    session: broker.AlpacaBrokerSession,
    *,
    ticker: str,
    snapshot_id: str,
    reference_price: float,
) -> dict:
    quote_timestamp = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    exact_price = str(reference_price)

    class QuoteClient:
        _api_key = session._key
        _secret_key = session._secret
        _sandbox = False
        _base_url = broker._MARKET_DATA_BASE_URL
        _oauth_token = None
        _use_basic_auth = False

        def __init__(self):
            self.quotes = {}

        def get_stock_latest_quote(self, _request):
            return dict(self.quotes)

    original_data_factory = broker._new_stock_data_client
    quote_client = session._data_client
    if quote_client is None:
        quote_client = QuoteClient()
    quote_client.quotes[ticker.upper()] = SimpleNamespace(
        bid_price=exact_price,
        ask_price=exact_price,
        timestamp=quote_timestamp,
    )
    broker._new_stock_data_client = lambda *_args, **_kwargs: quote_client
    try:
        return session.get_execution_validation_quote(
            ticker,
            expected_snapshot_id=snapshot_id,
        )
    finally:
        broker._new_stock_data_client = original_data_factory


def _bound_authorization_for_session(
    session: broker.AlpacaBrokerSession,
    intent: TradeIntent,
    *,
    reference_price: float,
):
    """Capture, validate, and authorize through the real production contracts."""
    snapshot = session.capture_execution_portfolio_snapshot()
    policy = _paper_policy()
    context = ExecutionValidationContext(
        account_id=snapshot.account_id or "",
        account_mode=snapshot.account_mode,
        snapshot_id=snapshot.broker_snapshot_id or "",
        policy_fingerprint=compute_policy_fingerprint(policy),
    )
    quote = _bind_test_quote(
        session,
        ticker=intent.ticker,
        snapshot_id=context.snapshot_id,
        reference_price=reference_price,
    )
    validation = validate_trade_intent(
        intent,
        snapshot,
        reference_price=quote["price_decimal"],
        price_timestamp=quote["timestamp"],
        bid_price=quote["bid_decimal"],
        ask_price=quote["ask_decimal"],
        now=datetime(2026, 7, 27, 10, 0),
        execution_context=context,
        execution_policy=policy,
        **_policy_gate_arguments(policy),
    )
    assert validation.approved
    authorization = authorize_trade_intent(intent, validation)
    return authorization, snapshot, policy, context


def _dispatch_permit_for_session(
    session: broker.AlpacaBrokerSession,
    *,
    database: Path,
    context: ExecutionValidationContext,
    idempotency_key: str,
    proposal_id: str,
):
    attempted_at = datetime.now(timezone.utc).isoformat()
    with execution_dispatch_fence(database):
        record_runtime_dispatch_attempt(
            database,
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            attempted_at=attempted_at,
            account_id=context.account_id,
            account_mode=context.account_mode,
        )
        return _mint_execution_service_dispatch_permit(
            database,
            broker_session=session,
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            attempted_at=attempted_at,
            account_id=context.account_id,
            account_mode=context.account_mode,
            snapshot_id=context.snapshot_id,
            policy_fingerprint=context.policy_fingerprint,
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

    assert exc_info.value.code == "missing_exact_numeric"
    assert session.submit_count == 0


def test_session_freezes_credentials_mode_and_trading_client_through_lookup_and_submit(
    monkeypatch,
    _isolated_dispatch_runtime,
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
    position_model = SimpleNamespace(
        symbol="AAA",
        qty="2",
        avg_entry_price="45",
        current_price="50",
        market_value="100",
        unrealized_pl="10",
    )
    submitted_order = SimpleNamespace(
        id="submitted-1",
        client_order_id="stable-client-id",
        symbol="AAA",
        asset_class="us_equity",
        order_class="simple",
        extended_hours=False,
        legs=None,
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

        def get_orders(self, *, filter):
            assert filter is not None
            self.calls.append("orders")
            return []

        def get_all_positions(self):
            self.calls.append("positions")
            return [position_model]

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
        client._api_key = key
        client._secret_key = secret
        client._sandbox = paper
        client._base_url = (
            broker._TRADING_PAPER_BASE_URL
            if paper
            else broker._TRADING_LIVE_BASE_URL
        )
        client._oauth_token = None
        client._use_basic_auth = False
        return client

    monkeypatch.setenv("APCA_API_KEY_ID", "credential-a")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-a")
    monkeypatch.setattr(broker, "PAPER_TRADING", True)
    monkeypatch.setattr(broker, "_new_trading_client", fake_factory)
    session = broker.open_alpaca_broker_session()
    intent = TradeIntent(ticker="AAA", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session,
        intent,
        reference_price=50,
    )

    # Mutable global configuration rotates after the boundary is open.
    monkeypatch.setenv("APCA_API_KEY_ID", "credential-b")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-b")
    monkeypatch.setattr(broker, "PAPER_TRADING", False)
    dispatch_permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="stable-client-id",
        proposal_id="stable-proposal",
    )

    result = session.submit_market_order(
        "AAA",
        1,
        authorization=authorization,
        idempotency_key="stable-client-id",
        dispatch_permit=dispatch_permit,
        expected_snapshot_id=snapshot.broker_snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
    )
    lookup = session.find_order_by_client_id("stable-client-id")

    assert factory_calls == [("credential-a", "secret-a", True)]
    assert session.PAPER_TRADING is True
    assert session.account_mode == "paper"
    assert result["order_id"] == "submitted-1"
    assert lookup and lookup["order_id"] == "submitted-1"
    assert client.calls == [
        "account",
        "orders",
        "positions",
        "orders",
        "account",
        "account",
        "asset:AAA",
        # A final coherent recapture proves that no balance, position, or
        # active-order state changed between validation and broker contact.
        "account",
        "orders",
        "positions",
        "orders",
        "account",
        "submit",
        "lookup:stable-client-id",
    ]


def test_session_account_mismatch_refuses_without_consuming_bound_authorization(
    _isolated_dispatch_runtime,
):
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

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
        asset_class="us_equity",
        order_class="simple",
        extended_hours=False,
        legs=None,
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

        def get_orders(self, *, filter):
            assert filter is not None
            return []

        def get_all_positions(self):
            return []

        def submit_order(self, _request):
            self.submit_count += 1
            return accepted

    expected_client = AccountClient("paper-account-1")
    expected_session = _open_test_session(
        expected_client, key="key-a", secret="secret-a"
    )
    authorization, expected_snapshot, _policy, context = (
        _bound_authorization_for_session(
            expected_session,
            intent,
            reference_price=60,
        )
    )

    # A foreign session must capture and register its own genuine snapshot so
    # the test reaches account verification rather than failing at the earlier
    # session-capability check.
    foreign_client = AccountClient("foreign-paper-account")
    foreign_session = _open_test_session(
        foreign_client, key="key-a", secret="secret-a"
    )
    foreign_snapshot = foreign_session.capture_execution_portfolio_snapshot()
    foreign_context = ExecutionValidationContext(
        account_id=foreign_snapshot.account_id or "",
        account_mode=foreign_snapshot.account_mode,
        snapshot_id=foreign_snapshot.broker_snapshot_id or "",
        policy_fingerprint=context.policy_fingerprint,
    )
    _bind_test_quote(
        foreign_session,
        ticker="KO",
        snapshot_id=foreign_context.snapshot_id,
        reference_price=60,
    )
    foreign_permit = _dispatch_permit_for_session(
        foreign_session,
        database=_isolated_dispatch_runtime,
        context=foreign_context,
        idempotency_key="bound-client-id",
        proposal_id="foreign-proposal",
    )
    with pytest.raises(PermissionError, match="different broker account"):
        foreign_session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="bound-client-id",
            dispatch_permit=foreign_permit,
            expected_snapshot_id=foreign_snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert foreign_client.submit_count == 0

    # The mismatch check precedes token consumption: the exact same authority
    # still verifies once against the account it was signed for.  Do not mint a
    # second broker permit for the same client-order ID here: the runtime
    # attempt ledger correctly treats cross-account reuse of that ID as a
    # durable integrity conflict even though the short-lived authorization was
    # not consumed.
    verify_execution_authorization(
        intent,
        authorization,
        expected_account_id=expected_snapshot.account_id,
        expected_account_mode=expected_snapshot.account_mode,
        expected_snapshot_id=expected_snapshot.broker_snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
        require_bound=True,
    )
    assert expected_client.submit_count == 0


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


class _ExecutableClient:
    def __init__(self, *, account_id="paper-account-1"):
        self.account_id = account_id
        self.submit_count = 0
        self.account_reads = 0
        self.orders = []

    def get_account(self):
        self.account_reads += 1
        return _raw_account_model(self.account_id)

    def get_asset(self, ticker):
        return _raw_asset_model(ticker)

    def get_orders(self, *, filter):
        assert filter is not None
        return list(self.orders)

    def get_all_positions(self):
        return []

    def submit_order(self, request):
        self.submit_count += 1
        return SimpleNamespace(
            id=f"accepted-{self.submit_count}",
            client_order_id=getattr(request, "client_order_id", "client-id"),
            symbol=getattr(request, "symbol", "KO"),
            asset_class="us_equity",
            order_class="simple",
            extended_hours=False,
            legs=None,
            qty=str(getattr(request, "qty", 1)),
            side="buy",
            type="market",
            time_in_force="day",
            status="new",
            filled_qty="0",
            filled_avg_price=None,
            submitted_at="2026-08-26T15:00:00+00:00",
        )


@pytest.mark.parametrize(
    "mutation",
    ("price", "bid", "ask", "timestamp"),
)
def test_final_submit_refuses_any_bound_quote_drift_without_broker_contact(
    mutation,
    _isolated_dispatch_runtime,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session,
        intent,
        reference_price=60,
    )
    quote_client = session._data_client
    target_quote = quote_client.quotes["KO"]
    if mutation == "price":
        target_quote.bid_price = "61"
        target_quote.ask_price = "61"
    elif mutation == "bid":
        target_quote.bid_price = "59"
    elif mutation == "ask":
        target_quote.ask_price = "61"
    else:
        target_quote.timestamp = target_quote.timestamp.replace(second=1)
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key=f"quote-{mutation}",
        proposal_id=f"quote-{mutation}-proposal",
    )

    with pytest.raises(
        broker.BrokerPreflightError,
        match=r"(?i)quote.*changed",
    ):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key=f"quote-{mutation}",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.submit_count == 0


def test_final_submit_rechecks_a_pending_order_ticker_quote(
    _isolated_dispatch_runtime,
):
    from assistant.execution_kernel.revalidate import _pending_buy_value_by_ticker

    client = _ExecutableClient()
    submitted_at = datetime.now(timezone.utc)
    client.orders = [
        SimpleNamespace(
            id=UUID("22345678-1234-5678-1234-567812345678"),
            client_order_id="pending-client-id",
            symbol="PEND",
            asset_class="us_equity",
            order_class="simple",
            extended_hours=False,
            legs=None,
            qty="1",
            notional=None,
            side="buy",
            type="market",
            limit_price=None,
            time_in_force="day",
            status="new",
            replaced_by=None,
            replaces=None,
            replaced_at=None,
            filled_qty="0",
            filled_avg_price=None,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            filled_at=None,
            canceled_at=None,
            expired_at=None,
            failed_at=None,
        )
    ]
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    snapshot = session.capture_execution_portfolio_snapshot()
    policy = _paper_policy()
    context = ExecutionValidationContext(
        account_id=snapshot.account_id or "",
        account_mode=snapshot.account_mode,
        snapshot_id=snapshot.broker_snapshot_id or "",
        policy_fingerprint=compute_policy_fingerprint(policy),
    )
    target_quote = _bind_test_quote(
        session,
        ticker="KO",
        snapshot_id=context.snapshot_id,
        reference_price=60,
    )
    session._data_client.quotes["PEND"] = SimpleNamespace(
        bid_price="60",
        ask_price="60",
        timestamp=datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc),
    )
    pending_values = _pending_buy_value_by_ticker(
        snapshot.open_orders,
        SimpleNamespace(
            get_latest_quote=lambda ticker: session.get_execution_validation_quote(
                ticker,
                expected_snapshot_id=context.snapshot_id,
            )
        ),
    )
    assert pending_values == {"PEND": 60}
    validation = validate_trade_intent(
        intent,
        snapshot,
        reference_price=target_quote["price_decimal"],
        price_timestamp=target_quote["timestamp"],
        bid_price=target_quote["bid_decimal"],
        ask_price=target_quote["ask_decimal"],
        now=datetime(2026, 7, 27, 10, 0),
        pending_buy_value_by_ticker=pending_values,
        execution_context=context,
        execution_policy=policy,
        **_policy_gate_arguments(policy),
    )
    assert validation.approved
    authorization = authorize_trade_intent(intent, validation)
    session._data_client.quotes["PEND"].ask_price = "61"
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="pending-quote-drift",
        proposal_id="pending-quote-drift-proposal",
    )

    with pytest.raises(broker.BrokerPreflightError, match="PEND.*changed"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="pending-quote-drift",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.submit_count == 0


def _authorization_without_session_quote(
    session: broker.AlpacaBrokerSession,
    intent: TradeIntent,
):
    snapshot = session.capture_execution_portfolio_snapshot()
    policy = _paper_policy()
    context = ExecutionValidationContext(
        account_id=snapshot.account_id or "",
        account_mode=snapshot.account_mode,
        snapshot_id=snapshot.broker_snapshot_id or "",
        policy_fingerprint=compute_policy_fingerprint(policy),
    )
    validation = validate_trade_intent(
        intent,
        snapshot,
        reference_price=60,
        price_timestamp=datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc),
        bid_price=60,
        ask_price=60,
        now=datetime(2026, 7, 27, 10, 0),
        execution_context=context,
        execution_policy=policy,
        **_policy_gate_arguments(policy),
    )
    assert validation.approved
    return authorize_trade_intent(intent, validation), snapshot, context


def test_final_submit_refuses_missing_session_quote_binding(
    _isolated_dispatch_runtime,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, context = _authorization_without_session_quote(
        session, intent
    )
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="missing-quote",
        proposal_id="missing-quote-proposal",
    )

    with pytest.raises(PermissionError, match="no session-bound validation quote"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="missing-quote",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.submit_count == 0


def test_validation_quote_refuses_a_wrong_snapshot_before_quote_contact():
    client = _ExecutableClient()
    session = _open_test_session(client)
    snapshot = session.capture_execution_portfolio_snapshot()
    assert snapshot.broker_snapshot_id != "a" * 64

    with pytest.raises(PermissionError, match="not captured"):
        session.get_execution_validation_quote(
            "KO",
            expected_snapshot_id="a" * 64,
        )
    assert session._data_client is None
    assert client.submit_count == 0


def test_final_submit_refuses_quote_bound_to_wrong_ticker(
    _isolated_dispatch_runtime,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, context = _authorization_without_session_quote(
        session, intent
    )
    _bind_test_quote(
        session,
        ticker="AAA",
        snapshot_id=context.snapshot_id,
        reference_price=60,
    )
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="wrong-ticker",
        proposal_id="wrong-ticker-proposal",
    )

    with pytest.raises(PermissionError, match="different ticker"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="wrong-ticker",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.submit_count == 0


def test_direct_submit_refuses_missing_or_forged_dispatch_permit_before_reads(
    _isolated_dispatch_runtime,
):
    from assistant.dispatch_fence import ExecutionDispatchPermit

    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session, intent, reference_price=60
    )
    reads_before = client.account_reads

    for permit in (None, ExecutionDispatchPermit("0" * 64)):
        with pytest.raises(PermissionError, match="dispatch permit|Dispatch permit"):
            session.submit_market_order(
                "KO",
                1,
                authorization=authorization,
                idempotency_key="no-direct-adapter",
                dispatch_permit=permit,
                expected_snapshot_id=snapshot.broker_snapshot_id,
                expected_policy_fingerprint=context.policy_fingerprint,
            )
    assert client.account_reads == reads_before
    assert client.submit_count == 0


def test_dispatch_permit_is_single_use_and_direct_replay_cannot_contact_broker(
    _isolated_dispatch_runtime,
):
    from assistant.dispatch_fence import execution_dispatch_permit_fence

    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session, intent, reference_price=60
    )
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="single-use-permit",
        proposal_id="single-use-permit-proposal",
    )
    session.submit_market_order(
        "KO",
        1,
        authorization=authorization,
        idempotency_key="single-use-permit",
        dispatch_permit=permit,
        expected_snapshot_id=snapshot.broker_snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
    )
    assert client.submit_count == 1

    with pytest.raises(PermissionError, match="consumed|foreign|forged"):
        with execution_dispatch_permit_fence(
            permit,
            broker_session=session,
            idempotency_key="single-use-permit",
            expected_snapshot_id=context.snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
            expected_account_mode=context.account_mode,
        ):
            pytest.fail("a replayed permit entered the dispatch boundary")
    assert client.submit_count == 1


def test_dispatch_permit_is_bound_to_the_exact_broker_session(
    _isolated_dispatch_runtime,
):
    first_client = _ExecutableClient()
    first_session = _open_test_session(first_client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    _authorization, _snapshot, _policy, first_context = (
        _bound_authorization_for_session(
            first_session, intent, reference_price=60
        )
    )
    permit = _dispatch_permit_for_session(
        first_session,
        database=_isolated_dispatch_runtime,
        context=first_context,
        idempotency_key="foreign-permit",
        proposal_id="foreign-permit-proposal",
    )

    second_client = _ExecutableClient()
    second_session = _open_test_session(second_client)
    authorization, snapshot, _policy, second_context = (
        _bound_authorization_for_session(
            second_session, intent, reference_price=60
        )
    )
    reads_before = second_client.account_reads
    with pytest.raises(PermissionError, match="different broker session"):
        second_session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="foreign-permit",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=second_context.policy_fingerprint,
        )
    assert second_client.account_reads == reads_before
    assert second_client.submit_count == 0


@pytest.mark.parametrize("binding", ("idempotency", "policy", "snapshot"))
def test_dispatch_permit_refuses_foreign_call_bindings_before_broker_reads(
    binding,
    _isolated_dispatch_runtime,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session, intent, reference_price=60
    )
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="bound-permit",
        proposal_id="bound-permit-proposal",
    )
    call_idempotency = "foreign-permit" if binding == "idempotency" else "bound-permit"
    call_policy = "a" * 64 if binding == "policy" else context.policy_fingerprint
    call_snapshot = "a" * 64 if binding == "snapshot" else snapshot.broker_snapshot_id
    reads_before = client.account_reads

    with pytest.raises(PermissionError, match="binding|not captured"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key=call_idempotency,
            dispatch_permit=permit,
            expected_snapshot_id=call_snapshot,
            expected_policy_fingerprint=call_policy,
        )
    assert client.account_reads == reads_before
    assert client.submit_count == 0


def test_dispatch_permit_refuses_an_intervening_stop_generation_even_if_cleared(
    _isolated_dispatch_runtime,
):
    from assistant.dispatch_fence import (
        activate_runtime_emergency_stop,
        clear_runtime_emergency_stop,
    )

    client = _ExecutableClient()
    session = _open_test_session(client)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session, intent, reference_price=60
    )
    permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="stale-generation-permit",
        proposal_id="stale-generation-proposal",
    )
    stop = activate_runtime_emergency_stop(
        _isolated_dispatch_runtime,
        incident_id="test-intervening-stop",
        reason="test containment",
        changed_at=datetime.now(timezone.utc).isoformat(),
    )
    clear_runtime_emergency_stop(
        _isolated_dispatch_runtime,
        incident_id="test-intervening-stop",
        expected_generation=stop["generation"],
        reason="test stop cleared",
        changed_at=datetime.now(timezone.utc).isoformat(),
    )
    reads_before = client.account_reads

    with pytest.raises(PermissionError, match="generation changed"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="stale-generation-permit",
            dispatch_permit=permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.account_reads == reads_before
    assert client.submit_count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("_api_key", "rotated-key"),
        ("_secret_key", "rotated-secret"),
        ("_sandbox", False),
        ("_base_url", broker._TRADING_LIVE_BASE_URL),
        ("_oauth_token", "redirecting-oauth-token"),
        ("_use_basic_auth", True),
    ),
)
def test_session_refuses_sdk_identity_mutation_before_safety_read(field, value):
    client = _ExecutableClient()
    session = _open_test_session(client, key="captured-key", secret="captured-secret")
    setattr(client, field, value)

    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_account()
    assert client.account_reads == 0
    assert client.submit_count == 0


def test_session_refuses_market_data_endpoint_mutation_before_quote_read():
    client = _ExecutableClient()
    session = _open_test_session(client)
    _authorization, _snapshot, _policy, _context = (
        _bound_authorization_for_session(
            session,
            TradeIntent(ticker="KO", side="buy", shares=1),
            reference_price=60,
        )
    )
    session._data_client._base_url = "https://attacker.invalid"

    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_latest_quote("KO")
    assert client.submit_count == 0


def test_session_endpoint_identity_does_not_follow_mutated_module_constants(
    monkeypatch,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    monkeypatch.setattr(
        broker, "_TRADING_PAPER_BASE_URL", "https://attacker.invalid"
    )
    client._base_url = broker._TRADING_PAPER_BASE_URL

    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_account()
    assert client.account_reads == 0
    assert client.submit_count == 0


def test_session_data_endpoint_identity_does_not_follow_mutated_constant(
    monkeypatch,
):
    client = _ExecutableClient()
    session = _open_test_session(client)
    _authorization, _snapshot, _policy, _context = (
        _bound_authorization_for_session(
            session,
            TradeIntent(ticker="KO", side="buy", shares=1),
            reference_price=60,
        )
    )
    monkeypatch.setattr(
        broker, "_MARKET_DATA_BASE_URL", "https://attacker.invalid"
    )
    session._data_client._base_url = broker._MARKET_DATA_BASE_URL

    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_latest_quote("KO")
    assert client.submit_count == 0


def test_all_session_identity_slots_refuse_ordinary_reassignment():
    client = _ExecutableClient()
    session = _open_test_session(client)

    for name, value in (
        ("_key", "other"),
        ("_secret", "other"),
        ("_paper", False),
        ("_trading_base_url", "https://attacker.invalid"),
        ("_data_base_url", "https://attacker.invalid"),
        ("_owner_pid", -1),
        ("_client", object()),
        ("_data_client", object()),
        ("_account_id", "other-account"),
        ("_snapshot_guard", object()),
        ("_registered_execution_snapshots", {}),
    ):
        with pytest.raises(AttributeError, match="immutable"):
            setattr(session, name, value)


def test_snapshot_capability_registry_has_no_mutable_mapping_surface():
    session = _open_test_session(_ExecutableClient())
    snapshot = session.capture_execution_portfolio_snapshot()
    registrations = session._registered_execution_snapshots

    assert isinstance(registrations, tuple)
    assert registrations[0][0] == snapshot.broker_snapshot_id
    with pytest.raises(TypeError):
        registrations[0] = ("a" * 64, registrations[0][1])
    with pytest.raises(AttributeError):
        registrations.clear()


def test_public_constructor_cannot_pair_asserted_credentials_with_a_client():
    with pytest.raises(TypeError):
        broker.AlpacaBrokerSession(
            key="asserted-key",
            secret="asserted-secret",
            paper=True,
            client=object(),
        )


def test_session_refuses_reinitialization_copy_serialization_and_forgery():
    import copy
    import pickle

    session = _open_test_session(_ExecutableClient())
    with pytest.raises(TypeError, match="reinitialized"):
        session.__init__()
    with pytest.raises(TypeError, match="copied"):
        copy.copy(session)
    with pytest.raises(TypeError, match="copied"):
        copy.deepcopy(session)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(session)

    forged = object.__new__(broker.AlpacaBrokerSession)
    with pytest.raises(PermissionError, match="production constructor"):
        forged.get_account()


def test_emergency_raw_id_enumeration_isolates_a_malformed_sibling():
    valid_id = UUID("12345678-1234-5678-1234-567812345678")
    valid = SimpleNamespace(id=valid_id)

    class MalformedSibling:
        id = None

        @property
        def side(self):
            raise ValueError("malformed sibling side")

    class RawBookClient(_ExecutableClient):
        def get_orders(self, *, filter):
            assert filter is not None
            return [valid, MalformedSibling()]

    session = _open_test_session(RawBookClient())
    with pytest.raises(ValueError, match="malformed sibling"):
        session.get_open_orders()

    evidence = session.get_open_order_ids_for_emergency()
    assert evidence["order_ids"] == [str(valid_id)]
    assert evidence["complete"] is False
    assert len(evidence["errors"]) == 1
    assert evidence["errors"][0]["row_index"] == 1


@pytest.mark.parametrize(
    "bad_id",
    (" unknown ", "unknown", "bad\nidentity", "x" * 129, 7, True),
)
def test_emergency_raw_id_enumeration_refuses_noncanonical_identities(bad_id):
    valid_id = UUID("12345678-1234-5678-1234-567812345678")

    class RawBookClient(_ExecutableClient):
        def get_orders(self, *, filter):
            assert filter is not None
            return [SimpleNamespace(id=valid_id), SimpleNamespace(id=bad_id)]

    evidence = _open_test_session(
        RawBookClient()
    ).get_open_order_ids_for_emergency()
    assert evidence["order_ids"] == [str(valid_id)]
    assert evidence["complete"] is False
    assert evidence["errors"][0]["row_index"] == 1


def test_emergency_raw_id_enumeration_isolates_an_id_property_exception():
    valid_id = UUID("12345678-1234-5678-1234-567812345678")

    class BrokenIdentity:
        @property
        def id(self):
            raise RuntimeError("malformed identity property")

    class RawBookClient(_ExecutableClient):
        def get_orders(self, *, filter):
            assert filter is not None
            return [BrokenIdentity(), SimpleNamespace(id=valid_id)]

    evidence = _open_test_session(
        RawBookClient()
    ).get_open_order_ids_for_emergency()
    assert evidence["order_ids"] == [str(valid_id)]
    assert evidence["complete"] is False
    assert evidence["errors"][0]["row_index"] == 0
    assert "RuntimeError" in evidence["errors"][0]["error"]


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
    session = _open_test_session(client)

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
    session = _open_test_session(client)

    with pytest.raises(broker.BrokerPreflightError, match=message):
        session.assert_account_and_asset_ready("KO")


@pytest.mark.parametrize(
    ("bad_account_id", "message"),
    [
        (None, "usable account identity"),
        ("", "usable account identity"),
        ("unknown", "usable account identity"),
        (" null ", "surrounding whitespace"),
    ],
)
def test_session_refuses_unusable_account_identity(bad_account_id, message):
    client = SimpleNamespace(get_account=lambda: _raw_account_model(bad_account_id))
    session = _open_test_session(client)

    with pytest.raises(broker.BrokerPreflightError, match=message):
        session.get_account()


def test_session_refuses_account_identity_change_on_every_later_read():
    accounts = iter(
        [_raw_account_model("paper-account-1"), _raw_account_model("paper-account-2")]
    )
    client = SimpleNamespace(get_account=lambda: next(accounts))
    session = _open_test_session(client)

    assert session.get_account()["account_id"] == "paper-account-1"
    with pytest.raises(broker.BrokerPreflightError, match="identity changed"):
        session.get_account()


def test_session_refuses_broker_state_drift_before_contact_without_consuming_authority(
    _isolated_dispatch_runtime,
):
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    class MutableStateClient:
        def __init__(self):
            self.drift = False
            self.submit_count = 0

        def get_account(self):
            value = "9999" if self.drift else "10000"
            return _raw_account_model(equity=value, cash=value, buying_power=value)

        def get_asset(self, _ticker):
            return _raw_asset_model()

        def get_orders(self, *, filter):
            assert filter is not None
            return []

        def get_all_positions(self):
            return []

        def submit_order(self, _request):
            self.submit_count += 1
            return SimpleNamespace(
                id="accepted-state-1",
                client_order_id="state-id",
                symbol="KO",
                asset_class="us_equity",
                order_class="simple",
                extended_hours=False,
                legs=None,
                qty="1",
                side="buy",
                type="market",
                time_in_force="day",
                status="new",
                filled_qty="0",
                filled_avg_price=None,
                submitted_at="2026-08-26T15:00:00+00:00",
            )

    client = MutableStateClient()
    session = _open_test_session(client)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session,
        intent,
        reference_price=60,
    )
    dispatch_permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="state-id",
        proposal_id="state-proposal",
    )

    client.drift = True
    with pytest.raises(broker.BrokerPreflightError, match="changed after"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="state-id",
            dispatch_permit=dispatch_permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )
    assert client.submit_count == 0

    # The state check precedes both single-use consumptions.  If the broker
    # returns to the exact authorized state, this same capability can make its
    # one contact instead of being lost to a pre-contact integrity refusal.
    client.drift = False
    result = session.submit_market_order(
        "KO",
        1,
        authorization=authorization,
        idempotency_key="state-id",
        dispatch_permit=dispatch_permit,
        expected_snapshot_id=snapshot.broker_snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
    )
    assert result["order_id"] == "accepted-state-1"
    assert client.submit_count == 1


def test_final_recapture_refuses_policy_driving_market_valuation_movement(
    _isolated_dispatch_runtime,
):
    """A coherent market tick can still invalidate the signed risk decision."""
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    class MarketTickClient:
        def __init__(self):
            self.market_tick = False
            self.submit_count = 0

        def get_account(self):
            return _raw_account_model(
                equity="1101" if self.market_tick else "1100",
                cash="1000",
                buying_power="1000",
            )

        def get_asset(self, _ticker):
            return _raw_asset_model()

        def get_orders(self, *, filter):
            assert filter is not None
            return []

        def get_all_positions(self):
            return [
                SimpleNamespace(
                    symbol="AAA",
                    qty="2",
                    avg_entry_price="45",
                    current_price="50.5" if self.market_tick else "50",
                    market_value="101" if self.market_tick else "100",
                    unrealized_pl="11" if self.market_tick else "10",
                )
            ]

        def submit_order(self, _request):
            self.submit_count += 1
            return SimpleNamespace(
                id="accepted-market-tick-1",
                client_order_id="market-tick-id",
                symbol="KO",
                asset_class="us_equity",
                order_class="simple",
                extended_hours=False,
                legs=None,
                qty="1",
                side="buy",
                type="market",
                time_in_force="day",
                status="new",
                filled_qty="0",
                filled_avg_price=None,
                submitted_at="2026-08-26T15:00:00+00:00",
            )

    client = MarketTickClient()
    session = _open_test_session(client)
    authorization, snapshot, _policy, context = _bound_authorization_for_session(
        session,
        intent,
        reference_price=60,
    )
    dispatch_permit = _dispatch_permit_for_session(
        session,
        database=_isolated_dispatch_runtime,
        context=context,
        idempotency_key="market-tick-id",
        proposal_id="market-tick-proposal",
    )

    client.market_tick = True
    with pytest.raises(broker.BrokerPreflightError, match="changed after"):
        session.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="market-tick-id",
            dispatch_permit=dispatch_permit,
            expected_snapshot_id=snapshot.broker_snapshot_id,
            expected_policy_fingerprint=context.policy_fingerprint,
        )

    assert client.submit_count == 0


def test_live_session_mode_cannot_be_reassigned_to_paper_before_capture():
    """The retained live client can never acquire paper execution evidence."""

    class UntouchedLiveClient:
        def __init__(self):
            self.calls: list[str] = []
            self.submit_count = 0

        def get_account(self):
            self.calls.append("account")
            return _raw_account_model("live-account-1")

        def submit_order(self, _request):
            self.submit_count += 1
            raise AssertionError("a relabeled live client must never submit")

    client = UntouchedLiveClient()
    session = _open_test_session(
        client, key="live-key", secret="live-secret", paper=False
    )
    assert session.PAPER_TRADING is False
    assert session.account_mode == "live"

    with pytest.raises(AttributeError):
        session.PAPER_TRADING = True
    with pytest.raises(AttributeError, match="immutable"):
        session._paper = True

    assert session.PAPER_TRADING is False
    assert session.account_mode == "live"
    with pytest.raises(BrokerSnapshotCoherenceError, match="paper broker session"):
        session.capture_execution_portfolio_snapshot()
    assert client.calls == []
    assert client.submit_count == 0


def test_session_inherited_by_another_process_fails_before_broker_contact(monkeypatch):
    owner_pid = broker.os.getpid()
    calls = []
    session = _open_test_session(
        SimpleNamespace(get_account=lambda: calls.append("account"))
    )

    monkeypatch.setattr(broker.os, "getpid", lambda: owner_pid + 1)
    with pytest.raises(PermissionError, match="different process"):
        session.get_account()
    assert calls == []


def test_public_submit_facade_fails_closed_without_session_owned_snapshot(
    monkeypatch,
):
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    class SnapshotClient:
        def __init__(self):
            self.account_reads = 0
            self.submit_count = 0

        def get_account(self):
            self.account_reads += 1
            return _raw_account_model("paper-account-1")

        def get_orders(self, *, filter):
            assert filter is not None
            return []

        def get_all_positions(self):
            return []

        def submit_order(self, _request):
            self.submit_count += 1
            raise AssertionError("the compatibility facade must not submit")

    source_client = SnapshotClient()
    source_session = _open_test_session(
        source_client, key="source-key", secret="source-secret"
    )
    authorization, _snapshot, _policy, _context = (
        _bound_authorization_for_session(
            source_session,
            intent,
            reference_price=60,
        )
    )

    # The legacy module facade opens a different session and has no argument
    # through which it can supply a snapshot captured by that session.  It is
    # retained only as an explicitly fail-closed compatibility surface.
    facade_client = SnapshotClient()
    facade_session = _open_test_session(
        facade_client, key="facade-key", secret="facade-secret"
    )
    monkeypatch.setattr(broker, "PAPER_TRADING", True)
    monkeypatch.setattr(
        broker,
        "open_alpaca_broker_session",
        lambda: facade_session,
    )

    with pytest.raises(
        PermissionError,
        match="requires the exact account-scoped AlpacaBrokerSession",
    ):
        broker.submit_market_order(
            "KO",
            1,
            authorization=authorization,
            idempotency_key="facade-client-id",
            expected_policy_fingerprint=_context.policy_fingerprint,
        )

    assert facade_client.account_reads == 0
    assert facade_client.submit_count == 0


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


def test_non_strict_snapshot_marks_a_malformed_open_order_book_unavailable():
    """A successful broker call is transport success, not a usable book.

    The duplicate-order and pending-exposure checks silently skip a row that
    has no ticker, so reporting availability over such a book would present an
    incomplete order book as complete to every advisory and preflight caller.
    """
    from assistant.portfolio_snapshot import build_portfolio_snapshot_from_alpaca

    malformed = _order()
    malformed["ticker"] = None
    degraded = build_portfolio_snapshot_from_alpaca(
        broker_session=_ScriptedSession(
            accounts=[_account()], order_books=[[malformed]], positions=[[]]
        )
    )
    assert degraded.open_orders_available is False
    assert list(degraded.open_orders) == []

    # Positive control: the identical book without the defect stays available,
    # so the guard cannot pass by making every book unavailable.
    healthy = build_portfolio_snapshot_from_alpaca(
        broker_session=_ScriptedSession(
            accounts=[_account()], order_books=[[_order()]], positions=[[]]
        )
    )
    assert healthy.open_orders_available is True
    assert len(list(healthy.open_orders)) == 1
