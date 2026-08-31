from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from execution import alpaca_broker as broker


class _LyingText(str):
    """Different text whose equality claims every string is identical."""

    def __eq__(self, _other):
        return True

    def __ne__(self, _other):
        return False

    __hash__ = str.__hash__


class _RedirectingBaseURL:
    """Claims the expected `.value` but concatenates against the live URL."""

    value = broker._TRADING_PAPER_BASE_URL

    def __add__(self, suffix):
        return broker._TRADING_LIVE_BASE_URL + suffix


class _EmergencyRawClient:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.bulk_cancel_calls = 0
        self.single_cancel_calls: list[str] = []

    def get_orders(self, *, filter):
        assert filter is not None
        return list(self.rows)

    def cancel_orders(self):
        self.bulk_cancel_calls += 1
        return [{"status": 207}]

    def cancel_order_by_id(self, order_id):
        self.single_cancel_calls.append(str(order_id))


def _add_observable_identity(client, *, raw_data: bool = True):
    client._api_key = "captured-key"
    client._secret_key = "captured-secret"
    client._sandbox = True
    client._base_url = broker._TRADING_PAPER_BASE_URL
    client._oauth_token = None
    client._use_basic_auth = False
    client._use_raw_data = raw_data
    return client


def _open_session(
    monkeypatch,
    *,
    primary_client,
    emergency_client: _EmergencyRawClient,
):
    emergency_factory_calls: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(
        broker,
        "_capture_connection_settings",
        lambda: ("captured-key", "captured-secret", True),
    )
    monkeypatch.setattr(
        broker,
        "_new_trading_client",
        lambda *_args, **_kwargs: primary_client,
    )

    def emergency_factory(key, secret, *, paper, client_factory=None):
        assert client_factory is not None
        emergency_factory_calls.append((key, secret, paper))
        return emergency_client

    monkeypatch.setattr(
        broker,
        "_new_emergency_trading_client",
        emergency_factory,
    )
    return broker.AlpacaBrokerSession(), emergency_factory_calls


def test_optional_sdk_account_and_position_numbers_remain_explicit_unknown():
    account = SimpleNamespace(
        id="paper-account-1",
        status="ACTIVE",
        equity=None,
        cash=float("nan"),
        buying_power="not-a-number",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        transfers_blocked=False,
    )
    normalized_account = broker._normalize_account(account, paper=True)

    for field in ("equity", "cash", "buying_power"):
        assert normalized_account[field] is None
        assert normalized_account[f"{field}_decimal"] is None

    position = SimpleNamespace(
        symbol="AAPL",
        qty="1.25",
        avg_entry_price="100.00",
        current_price=None,
        unrealized_pl="NaN",
        market_value=None,
    )
    normalized_position = broker._normalize_position(position)

    assert normalized_position["current_price"] is None
    assert normalized_position["current_price_decimal"] is None
    assert normalized_position["unrealized_pl"] is None
    assert "market_value" not in normalized_position


def test_optional_sdk_number_normalization_contains_integer_overflow():
    assert broker._optional_float(10**10_000) is None


@pytest.mark.parametrize(
    "market_value",
    ("NaN", "Infinity", "not-a-number", True),
)
def test_optional_position_market_value_never_publishes_nonfinite_or_junk(
    market_value,
):
    position = SimpleNamespace(
        symbol="AAPL",
        qty="1.25",
        avg_entry_price="100.00",
        current_price="101.00",
        unrealized_pl="1.25",
        market_value=market_value,
    )

    normalized = broker._normalize_position(position)

    assert "market_value" not in normalized
    assert "market_value_decimal" not in normalized


@pytest.mark.parametrize(
    ("field", "mismatched_value"),
    (
        ("_api_key", "redirected-key"),
        ("_secret_key", "redirected-secret"),
        ("_sandbox", False),
        ("_base_url", broker._TRADING_LIVE_BASE_URL),
        ("_oauth_token", "redirected-oauth-token"),
        ("_use_basic_auth", True),
        ("_use_raw_data", False),
    ),
)
def test_allow_unverifiable_identity_still_rejects_each_present_mismatch(
    field,
    mismatched_value,
):
    partial = SimpleNamespace(**{field: mismatched_value})

    with pytest.raises(
        broker.BrokerPreflightError,
        match=rf"mismatched fields: {field}",
    ):
        broker._assert_sdk_client_identity(
            partial,
            key="captured-key",
            secret="captured-secret",
            expected_sandbox=True,
            expected_base_url=broker._TRADING_PAPER_BASE_URL,
            label="partial SDK client",
            allow_unverifiable=True,
            expected_raw_data=True,
        )


def test_allow_unverifiable_identity_allows_only_absent_fields():
    partial = SimpleNamespace(_api_key="captured-key")

    assert broker._assert_sdk_client_identity(
        partial,
        key="captured-key",
        secret="captured-secret",
        expected_sandbox=True,
        expected_base_url=broker._TRADING_PAPER_BASE_URL,
        label="partial SDK client",
        allow_unverifiable=True,
        expected_raw_data=True,
    ) is False


def test_strict_identity_rejects_the_same_partial_sdk_surface():
    partial = SimpleNamespace(_api_key="captured-key")

    with pytest.raises(
        broker.BrokerPreflightError,
        match=r"missing fields: _secret_key, _sandbox, _base_url, _oauth_token, "
        r"_use_basic_auth, _use_raw_data",
    ):
        broker._assert_sdk_client_identity(
            partial,
            key="captured-key",
            secret="captured-secret",
            expected_sandbox=True,
            expected_base_url=broker._TRADING_PAPER_BASE_URL,
            label="partial SDK client",
            allow_unverifiable=False,
            expected_raw_data=True,
        )


@pytest.mark.parametrize(
    ("key", "secret"),
    (
        (_LyingText("captured-key"), "captured-secret"),
        ("captured-key", _LyingText("captured-secret")),
    ),
)
def test_session_constructor_refuses_noncanonical_credential_subclasses(
    monkeypatch,
    key,
    secret,
):
    factory_calls: list[object] = []
    monkeypatch.setattr(
        broker,
        "_capture_connection_settings",
        lambda: (key, secret, True),
    )
    monkeypatch.setattr(
        broker,
        "_new_trading_client",
        lambda *_args, **_kwargs: factory_calls.append(object()),
    )

    with pytest.raises(broker.AlpacaNotConfigured, match="non-empty string"):
        broker.AlpacaBrokerSession()
    assert factory_calls == []


def test_emergency_factory_requests_the_public_raw_data_sdk_surface(monkeypatch):
    calls: list[tuple[str, str, bool, bool]] = []
    sentinel = object()

    class FakeTradingClient:
        def __new__(cls, key, secret, *, paper, raw_data):
            calls.append((key, secret, paper, raw_data))
            return sentinel

    from alpaca.trading import client as alpaca_client

    monkeypatch.setattr(alpaca_client, "TradingClient", FakeTradingClient)

    result = broker._new_emergency_trading_client(
        "captured-key",
        "captured-secret",
        paper=True,
    )

    assert result is sentinel
    assert calls == [("captured-key", "captured-secret", True, True)]


def test_emergency_paths_survive_unavailable_sdk_private_identity(monkeypatch):
    valid_id = UUID("12345678-1234-5678-1234-567812345678")

    class SdkAfterPrivateRename:
        # Intentionally no _api_key/_secret_key/_sandbox/_base_url/
        # _oauth_token/_use_basic_auth attributes.
        account_reads = 0

        def get_account(self):
            self.account_reads += 1
            raise AssertionError("strict read reached unverifiable SDK client")

        def get_orders(self, *, filter):
            raise AssertionError("modeled order path must not serve emergency IDs")

    primary = SdkAfterPrivateRename()
    emergency = _EmergencyRawClient(
        rows=[
            {"id": str(valid_id)},
            {"id": {"malformed": "sibling"}},
        ]
    )
    session, factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )

    # Captured mode is available without touching SDK-private state so the
    # cancellation orchestrator can continue into its contained path.
    assert session.PAPER_TRADING is True
    assert session.account_mode == "paper"
    with pytest.raises(
        broker.BrokerPreflightError,
        match="does not expose verifiable SDK connection identity",
    ):
        session.get_account()
    assert primary.account_reads == 0

    evidence = session.get_open_order_ids_for_emergency()
    assert evidence["order_ids"] == [str(valid_id)]
    assert evidence["complete"] is False
    assert evidence["errors"][0]["row_index"] == 1

    assert session.cancel_all_orders() == [{"status": 207}]
    assert session.cancel_order(str(valid_id)) == {
        "order_id": str(valid_id),
        "status": "pending_cancel",
    }
    assert emergency.bulk_cancel_calls == 1
    assert emergency.single_cancel_calls == [str(valid_id)]
    assert factory_calls == [("captured-key", "captured-secret", True)]


@pytest.mark.parametrize(
    ("slot", "value"),
    (
        ("_key", "redirected-key"),
        ("_secret", "redirected-secret"),
        ("_paper", False),
        ("_trading_base_url", "https://attacker.invalid"),
        ("_client", object()),
        ("_owner_pid", -1),
    ),
)
def test_emergency_client_refuses_mutated_session_connection_tuple(
    monkeypatch,
    slot,
    value,
):
    primary = SimpleNamespace(
        _api_key="captured-key",
        _secret_key="captured-secret",
        _sandbox=True,
        _base_url=broker._TRADING_PAPER_BASE_URL,
        _oauth_token=None,
        _use_basic_auth=False,
        _use_raw_data=False,
    )
    emergency = _EmergencyRawClient()
    session, factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )
    object.__setattr__(session, slot, value)

    with pytest.raises(PermissionError, match="registered connection identity changed"):
        session.cancel_all_orders()

    assert factory_calls == []
    assert emergency.bulk_cancel_calls == 0


def test_cached_emergency_client_refuses_observable_identity_mutation(
    monkeypatch,
):
    primary = SimpleNamespace(
        _api_key="captured-key",
        _secret_key="captured-secret",
        _sandbox=True,
        _base_url=broker._TRADING_PAPER_BASE_URL,
        _oauth_token=None,
        _use_basic_auth=False,
        _use_raw_data=False,
    )
    emergency = _add_observable_identity(_EmergencyRawClient())
    session, factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )
    assert session.get_open_order_ids_for_emergency()["complete"] is True
    assert factory_calls == [("captured-key", "captured-secret", True)]

    emergency._api_key = "redirected-key"
    emergency._base_url = broker._TRADING_LIVE_BASE_URL

    with pytest.raises(
        broker.BrokerPreflightError,
        match="Emergency TradingClient credential, endpoint",
    ):
        session.cancel_all_orders()
    assert emergency.bulk_cancel_calls == 0


@pytest.mark.parametrize(
    ("field", "redirected_value"),
    (
        ("_api_key", _LyingText("redirected-key")),
        ("_secret_key", _LyingText("redirected-secret")),
        ("_base_url", _LyingText(broker._TRADING_LIVE_BASE_URL)),
        ("_base_url", _RedirectingBaseURL()),
    ),
)
def test_cached_emergency_client_refuses_equality_trap_identity_mutation(
    monkeypatch,
    field,
    redirected_value,
):
    primary = SimpleNamespace(
        _api_key="captured-key",
        _secret_key="captured-secret",
        _sandbox=True,
        _base_url=broker._TRADING_PAPER_BASE_URL,
        _oauth_token=None,
        _use_basic_auth=False,
        _use_raw_data=False,
    )
    emergency = _add_observable_identity(_EmergencyRawClient())
    session, _factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )
    assert session.get_open_order_ids_for_emergency()["complete"] is True
    setattr(emergency, field, redirected_value)

    with pytest.raises(
        broker.BrokerPreflightError,
        match=rf"mismatched fields: {field}",
    ):
        session.cancel_all_orders()
    assert emergency.bulk_cancel_calls == 0


@pytest.mark.parametrize(
    ("field", "redirected_value"),
    (
        ("_api_key", _LyingText("redirected-key")),
        ("_secret_key", _LyingText("redirected-secret")),
        ("_base_url", _LyingText(broker._TRADING_LIVE_BASE_URL)),
        ("_base_url", _RedirectingBaseURL()),
    ),
)
def test_primary_client_refuses_equality_trap_before_account_contact(
    monkeypatch,
    field,
    redirected_value,
):
    class PrimaryClient:
        def __init__(self):
            self.account_reads = 0

        def get_account(self):
            self.account_reads += 1
            raise AssertionError("identity trap reached the account endpoint")

    primary = _add_observable_identity(PrimaryClient(), raw_data=False)
    session, _factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=_add_observable_identity(_EmergencyRawClient()),
    )
    setattr(primary, field, redirected_value)

    with pytest.raises(
        broker.BrokerPreflightError,
        match=rf"mismatched fields: {field}",
    ):
        session.get_account()
    assert primary.account_reads == 0


def test_registered_session_refuses_equality_trap_slot_before_cancellation(
    monkeypatch,
):
    primary = _add_observable_identity(SimpleNamespace(), raw_data=False)
    emergency = _add_observable_identity(_EmergencyRawClient())
    session, factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )
    object.__setattr__(session, "_key", _LyingText("redirected-key"))

    with pytest.raises(PermissionError, match="registered connection identity changed"):
        session.cancel_all_orders()
    assert factory_calls == []
    assert emergency.bulk_cancel_calls == 0


def test_emergency_client_refuses_observable_non_raw_mode(monkeypatch):
    primary = SimpleNamespace(
        _api_key="captured-key",
        _secret_key="captured-secret",
        _sandbox=True,
        _base_url=broker._TRADING_PAPER_BASE_URL,
        _oauth_token=None,
        _use_basic_auth=False,
        _use_raw_data=False,
    )
    emergency = _add_observable_identity(
        _EmergencyRawClient(), raw_data=False
    )
    session, _factory_calls = _open_session(
        monkeypatch,
        primary_client=primary,
        emergency_client=emergency,
    )

    with pytest.raises(
        broker.BrokerPreflightError,
        match=r"mismatched fields: _use_raw_data",
    ):
        session.cancel_all_orders()
    assert emergency.bulk_cancel_calls == 0


def test_emergency_methods_reject_a_forged_session_before_opening_a_client(
    monkeypatch,
):
    factory_calls: list[object] = []
    monkeypatch.setattr(
        broker,
        "_new_emergency_trading_client",
        lambda *_args, **_kwargs: factory_calls.append(object()),
    )
    forged = object.__new__(broker.AlpacaBrokerSession)

    with pytest.raises(PermissionError, match="production constructor"):
        forged.cancel_all_orders()

    assert factory_calls == []
