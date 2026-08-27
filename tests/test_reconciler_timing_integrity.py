"""Fail-closed temporal input boundaries for reconciliation and readiness."""
from __future__ import annotations

from datetime import datetime

import pytest

from assistant.execution_service import (
    recover_stale_claim,
    recover_stale_reconciliation,
)
from assistant.order_reconciler import (
    cancel_all_open_orders,
    cancel_assistant_order,
    monitor_orders,
    reconcile_nonterminal_orders,
)
from assistant.readiness import transaction_readiness
from assistant.temporal_integrity import MAX_RECOVERY_WINDOW_SECONDS


class _NoContact:
    """Explode on any database, policy, broker, or event access."""

    def __init__(self, label: str):
        self.label = label
        self.contacts: list[str] = []

    def __getattr__(self, name: str):
        self.contacts.append(name)
        raise AssertionError(f"{self.label} was contacted through {name}")


_NONFINITE_OR_NEGATIVE = (-1.0, float("nan"), float("inf"), float("-inf"))


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [
        *(("max_order_age_minutes", value) for value in _NONFINITE_OR_NEGATIVE),
        ("max_order_age_minutes", 0.0),
        ("max_order_age_minutes", True),
        ("max_order_age_minutes", 10**1000),
        ("max_order_age_minutes", 31.0 * 24.0 * 60.0 + 0.001),
        *(("min_absence_age_seconds", value) for value in _NONFINITE_OR_NEGATIVE),
        ("min_absence_age_seconds", True),
        ("min_absence_age_seconds", 10**1000),
        ("min_absence_age_seconds", 7.0 * 24.0 * 60.0 * 60.0 + 0.001),
    ],
)
def test_reconcile_rejects_bad_timing_before_store_or_broker_contact(
    argument, bad_value
):
    store = _NoContact("store")
    broker = _NoContact("broker")

    with pytest.raises(ValueError):
        reconcile_nonterminal_orders(
            store,
            broker_module=broker,
            **{argument: bad_value},
        )

    assert store.contacts == []
    assert broker.contacts == []


@pytest.mark.parametrize("bad_now", [datetime(2026, 8, 26, 16, 0), "2026-08-26Z"])
def test_reconcile_requires_aware_now_before_store_or_broker_contact(bad_now):
    store = _NoContact("store")
    broker = _NoContact("broker")

    with pytest.raises(ValueError, match="timezone-aware"):
        reconcile_nonterminal_orders(store, broker_module=broker, now=bad_now)

    assert store.contacts == []
    assert broker.contacts == []


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [
        *(("max_order_age_minutes", value) for value in _NONFINITE_OR_NEGATIVE),
        ("max_order_age_minutes", 0.0),
        ("max_order_age_minutes", True),
        ("max_order_age_minutes", 10**1000),
        ("max_order_age_minutes", 31.0 * 24.0 * 60.0 + 0.001),
        *(("min_absence_age_seconds", value) for value in _NONFINITE_OR_NEGATIVE),
        ("min_absence_age_seconds", True),
        ("min_absence_age_seconds", 10**1000),
        ("min_absence_age_seconds", 7.0 * 24.0 * 60.0 * 60.0 + 0.001),
        *(("poll_interval_seconds", value) for value in _NONFINITE_OR_NEGATIVE),
        ("poll_interval_seconds", 0.0),
        ("poll_interval_seconds", True),
        ("poll_interval_seconds", 10**1000),
        ("poll_interval_seconds", 3600.001),
        *(("reconnect_delay_seconds", value) for value in _NONFINITE_OR_NEGATIVE),
        ("reconnect_delay_seconds", 0.0),
        ("reconnect_delay_seconds", True),
        ("reconnect_delay_seconds", 10**1000),
        ("reconnect_delay_seconds", 3600.001),
    ],
)
def test_monitor_rejects_bad_timing_before_store_broker_or_thread_contact(
    argument, bad_value
):
    store = _NoContact("store")
    broker = _NoContact("broker")

    with pytest.raises(ValueError):
        monitor_orders(store, broker_module=broker, **{argument: bad_value})

    assert store.contacts == []
    assert broker.contacts == []


@pytest.mark.parametrize("cancel_stale", [0, 1, "false", None])
@pytest.mark.parametrize("entrypoint", [reconcile_nonterminal_orders, monitor_orders])
def test_reconciler_requires_an_actual_boolean_before_contact(
    entrypoint, cancel_stale
):
    store = _NoContact("store")
    broker = _NoContact("broker")

    with pytest.raises(ValueError, match="actual bool"):
        entrypoint(store, broker_module=broker, cancel_stale=cancel_stale)

    assert store.contacts == []
    assert broker.contacts == []


@pytest.mark.parametrize("bad_now", [datetime(2026, 8, 26, 16, 0), "bad-now"])
@pytest.mark.parametrize("entrypoint", [cancel_assistant_order, cancel_all_open_orders])
def test_cancel_entrypoints_require_aware_now_before_state_or_broker_contact(
    entrypoint, bad_now
):
    store = _NoContact("store")
    broker = _NoContact("broker")
    kwargs = {"broker_module": broker, "now": bad_now}
    if entrypoint is cancel_assistant_order:
        args = (store, "tp-1")
    else:
        args = (store,)
        kwargs["reason"] = "timing validation test"

    with pytest.raises(ValueError, match="timezone-aware"):
        entrypoint(*args, **kwargs)

    assert store.contacts == []
    assert broker.contacts == []


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [
        *(("max_reconciliation_age_minutes", value) for value in _NONFINITE_OR_NEGATIVE),
        ("max_reconciliation_age_minutes", 0.0),
        ("max_reconciliation_age_minutes", True),
        ("max_reconciliation_age_minutes", 10**1000),
        ("max_reconciliation_age_minutes", 7.0 * 24.0 * 60.0 + 0.001),
        *(("stale_claim_seconds", value) for value in _NONFINITE_OR_NEGATIVE),
        ("stale_claim_seconds", 0.0),
        ("stale_claim_seconds", True),
        ("stale_claim_seconds", 10**1000),
        ("stale_claim_seconds", 7.0 * 24.0 * 60.0 * 60.0 + 0.001),
    ],
)
def test_readiness_rejects_bad_windows_before_policy_or_store_contact(
    argument, bad_value
):
    store = _NoContact("store")
    policy = _NoContact("policy")

    with pytest.raises(ValueError):
        transaction_readiness(
            store,
            policy,
            check_broker=False,
            **{argument: bad_value},
        )

    assert store.contacts == []
    assert policy.contacts == []


@pytest.mark.parametrize("bad_now", [datetime(2026, 8, 26, 16, 0), "bad-now"])
def test_readiness_requires_aware_now_before_policy_or_store_contact(bad_now):
    store = _NoContact("store")
    policy = _NoContact("policy")

    with pytest.raises(ValueError, match="timezone-aware"):
        transaction_readiness(
            store, policy, check_broker=False, now=bad_now
        )

    assert store.contacts == []
    assert policy.contacts == []


@pytest.mark.parametrize("check_broker", [0, 1, "false", None])
def test_readiness_requires_actual_boolean_before_policy_or_store_contact(
    check_broker
):
    store = _NoContact("store")
    policy = _NoContact("policy")

    with pytest.raises(ValueError, match="actual bool"):
        transaction_readiness(store, policy, check_broker=check_broker)

    assert store.contacts == []
    assert policy.contacts == []


@pytest.mark.parametrize(
    "entrypoint", [recover_stale_claim, recover_stale_reconciliation]
)
@pytest.mark.parametrize(
    "bad_window",
    [0, -1, True, 1.5, float("nan"), 10**1000, int(MAX_RECOVERY_WINDOW_SECONDS) + 1],
)
def test_recovery_windows_fail_before_store_contact(entrypoint, bad_window):
    store = _NoContact("store")

    with pytest.raises(ValueError):
        entrypoint("tp-1", store, stale_after_seconds=bad_window)

    assert store.contacts == []
