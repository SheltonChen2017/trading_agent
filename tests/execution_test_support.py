"""Security-faithful broker-contact boundary for execution test doubles.

Production submits consume two process-local, single-use capabilities while
holding the dispatch/runtime fence. A fake broker that merely records the
call leaves both capabilities live and can make later tests depend on suite
order. Test sessions use this context manager immediately before their
scripted contact so they preserve the same authorization semantics without
weakening or special-casing production code.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from assistant.dispatch_fence import (
    consume_execution_dispatch_permit,
    execution_dispatch_permit_fence,
)
from risk.execution_gate import TradeIntent, verify_execution_authorization


class ScriptedBrokerSession(Protocol):
    """Minimum account-scoped surface required by a scripted submission."""

    account_mode: str

    def assert_account_and_asset_ready(
        self, ticker: str
    ) -> Mapping[str, Any]: ...


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PermissionError(f"Scripted broker contact requires {name}.")
    return value


@contextmanager
def scripted_broker_contact_boundary(
    *,
    broker_session: ScriptedBrokerSession,
    snapshot_id_reader: Callable[[], str | None],
    consume_snapshot: Callable[[], None],
    ticker: str,
    shares: object,
    side: str,
    order_type: str,
    limit_price: object | None,
    authorization: object,
    idempotency_key: str,
    dispatch_permit: object,
    expected_snapshot_id: str,
    expected_policy_fingerprint: str,
) -> Iterator[None]:
    """Consume the real one-use capabilities around one scripted contact."""
    idempotency_key = _required_text(
        idempotency_key, name="a non-empty idempotency key"
    )
    expected_snapshot_id = _required_text(
        expected_snapshot_id, name="an execution snapshot id"
    )
    expected_policy_fingerprint = _required_text(
        expected_policy_fingerprint, name="a policy fingerprint"
    )
    if expected_snapshot_id != snapshot_id_reader():
        raise PermissionError(
            "Broker submission requires this session's current execution snapshot."
        )
    intent = TradeIntent(
        ticker=ticker,
        shares=shares,
        side=side,
        order_type=order_type,
        limit_price=limit_price,
    )
    account_mode = broker_session.account_mode
    with execution_dispatch_permit_fence(
        dispatch_permit,
        broker_session=broker_session,
        idempotency_key=idempotency_key,
        expected_snapshot_id=expected_snapshot_id,
        expected_policy_fingerprint=expected_policy_fingerprint,
        expected_account_mode=account_mode,
    ):
        # Re-read after the real dispatch fence is held.  A copied scalar
        # checked before fence acquisition can go stale while another path
        # replaces or consumes the session snapshot.
        if expected_snapshot_id != snapshot_id_reader():
            raise PermissionError(
                "Broker submission requires this session's current execution snapshot."
            )
        readiness = broker_session.assert_account_and_asset_ready(ticker)
        account_id = readiness["account"]["account_id"]
        verify_execution_authorization(
            intent,
            authorization,
            expected_account_id=account_id,
            expected_account_mode=account_mode,
            expected_snapshot_id=expected_snapshot_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
            require_bound=True,
        )
        consume_execution_dispatch_permit(
            dispatch_permit,
            broker_session=broker_session,
            idempotency_key=idempotency_key,
            expected_account_id=account_id,
            expected_account_mode=account_mode,
            expected_snapshot_id=expected_snapshot_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
        )
        # Consume the session snapshot before yielding to the scripted
        # network result, including a timeout.  A callback keeps the read and
        # mutation attached to the same session state and under the fence.
        consume_snapshot()
        if snapshot_id_reader() is not None:
            raise AssertionError("scripted broker snapshot was not consumed")
        yield
