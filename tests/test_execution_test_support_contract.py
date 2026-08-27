"""Contracts for security-faithful execution test doubles."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

import tests.execution_test_support as support


class _Session:
    account_mode = "paper"

    def __init__(self) -> None:
        self.preflight_calls = 0

    def assert_account_and_asset_ready(self, ticker: str) -> dict:
        self.preflight_calls += 1
        return {"account": {"account_id": "paper-account-1"}}


def test_snapshot_is_reread_under_the_dispatch_fence_before_preflight(
    monkeypatch,
) -> None:
    expected = "a" * 64
    observed = iter((expected, "b" * 64))
    session = _Session()

    @contextmanager
    def fake_fence(*args, **kwargs):
        yield

    monkeypatch.setattr(support, "execution_dispatch_permit_fence", fake_fence)

    with pytest.raises(PermissionError, match="current execution snapshot"):
        with support.scripted_broker_contact_boundary(
            broker_session=session,
            snapshot_id_reader=lambda: next(observed),
            consume_snapshot=lambda: pytest.fail(
                "a changed snapshot must not be consumed"
            ),
            ticker="AAPL",
            shares=1,
            side="buy",
            order_type="market",
            limit_price=None,
            authorization=object(),
            idempotency_key="idem-race",
            dispatch_permit=object(),
            expected_snapshot_id=expected,
            expected_policy_fingerprint="c" * 64,
        ):
            pytest.fail("a changed snapshot reached scripted broker contact")

    assert session.preflight_calls == 0
