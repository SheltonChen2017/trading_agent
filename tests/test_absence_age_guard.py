"""
Reconciliation must not believe "the broker has no such order" while a
submission is still in flight.

submit_approved_proposal() writes "submitting" and reserves daily budget
BEFORE it calls the broker. A poller running in that window used to treat a
404 as a CONFIRMED failure: it marked the proposal submission_failed and
released the daily reservation, so the order that then succeeded no longer
counted against max_daily_submitted_notional / max_daily_order_count and
briefly left the duplicate-risk set (independent review, 2026-07-30).

These tests pin the age guard that closes that window. `now` is always
computed RELATIVE to the row's own updated_at rather than wall clock, so a
failure means the guard broke, not that the machine was slow.
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from assistant.order_reconciler import (
    MIN_ABSENCE_AGE_SECONDS,
    reconcile_nonterminal_orders,
)
from assistant.proposal_status import SUBMISSION_FAILED, SUBMISSION_UNKNOWN, SUBMITTING
from assistant.storage import AssistantStore

RESERVED_NOTIONAL = 1_000.0


def _proposal(status: str = SUBMITTING, proposal_id: str = "tp-inflight") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-30T14:00:00+00:00",
        "expires_at": "2026-07-31T14:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "order_type": "market",
            "limit_price": None,
        },
    }


class _AbsentBroker:
    """Every lookup finds nothing -- exactly what a real broker returns in the
    window between our "submitting" write and the order being indexed."""

    @staticmethod
    def find_order_by_client_id(client_order_id):
        return None

    @staticmethod
    def cancel_order(order_id):
        raise AssertionError("no cancellation expected in these tests")


def _store_with_reservation(temp: str, *, status: str = SUBMITTING) -> AssistantStore:
    store = AssistantStore(Path(temp) / "assistant.db")
    store.save_proposal(_proposal(status=status))
    store.reserve_execution_budget(
        "tp-inflight",
        trading_day="2026-07-30",
        notional=RESERVED_NOTIONAL,
        max_daily_notional=100_000.0,
        max_daily_orders=10,
    )
    return store


def _updated_at(store: AssistantStore, status: str = SUBMITTING) -> datetime:
    rows = store.list_proposals_by_statuses((status,))
    assert rows, f"expected a proposal in {status}"
    raw = rows[0]["updated_at"]
    assert raw, "list_proposals_by_statuses must expose the row's updated_at"
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _reserved_notional(store: AssistantStore) -> float:
    return store.get_execution_budget_usage("2026-07-30")["submitted_notional"]


def test_absence_during_the_submit_window_does_not_fail_the_proposal():
    """THE regression: a 404 five seconds after entering "submitting" is the
    in-flight window, not proof of absence."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        now = _updated_at(store) + timedelta(seconds=5)

        result = reconcile_nonterminal_orders(store, broker_module=_AbsentBroker, now=now)

        assert store.get_proposal("tp-inflight")["status"] == SUBMITTING
        assert result["confirmed_absent"] == 0
        assert result["skipped_too_recent"] == 1


def test_absence_during_the_submit_window_keeps_the_budget_reservation():
    """The reservation is the part that actually costs money: releasing it
    lets a second order slip past the daily cap."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        now = _updated_at(store) + timedelta(seconds=5)

        reconcile_nonterminal_orders(store, broker_module=_AbsentBroker, now=now)

        assert _reserved_notional(store) == RESERVED_NOTIONAL


def test_absence_is_believed_once_the_proposal_is_genuinely_stranded():
    """The guard must not disable reconciliation -- only delay it. A proposal
    stuck in "submitting" for an hour is stranded and must still be resolved."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        now = _updated_at(store) + timedelta(hours=1)

        result = reconcile_nonterminal_orders(store, broker_module=_AbsentBroker, now=now)

        assert store.get_proposal("tp-inflight")["status"] == SUBMISSION_FAILED
        assert result["confirmed_absent"] == 1
        assert result["skipped_too_recent"] == 0
        assert _reserved_notional(store) == 0.0


def test_the_boundary_is_the_documented_grace_period():
    """Just under the threshold is skipped; just over it resolves. Pins the
    comparison itself, so a flipped inequality or a wrong unit is caught."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        entered_at = _updated_at(store)

        just_under = reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=entered_at + timedelta(seconds=MIN_ABSENCE_AGE_SECONDS - 1),
        )
        assert just_under["skipped_too_recent"] == 1
        assert store.get_proposal("tp-inflight")["status"] == SUBMITTING

        just_over = reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=entered_at + timedelta(seconds=MIN_ABSENCE_AGE_SECONDS + 1),
        )
        assert just_over["confirmed_absent"] == 1
        assert store.get_proposal("tp-inflight")["status"] == SUBMISSION_FAILED


def test_an_unparseable_updated_at_fails_closed():
    """Declining to act costs one poll cycle; acting wrongly drops a live
    order's reservation. Corrupt metadata must take the cheap side."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        connection = sqlite3.connect(store.path)
        try:
            connection.execute(
                "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
                ("not-a-timestamp", "tp-inflight"),
            )
            connection.commit()
        finally:
            connection.close()

        result = reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=datetime.fromisoformat("2030-01-01T00:00:00+00:00"),
        )

        assert store.get_proposal("tp-inflight")["status"] == SUBMITTING
        assert result["confirmed_absent"] == 0
        assert _reserved_notional(store) == RESERVED_NOTIONAL


def test_a_nonfinite_grace_period_is_rejected_before_any_broker_call():
    """A NaN/negative value would silently disable the guard rather than fail
    -- the exact failure direction the guard exists to prevent."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        for bad in (float("nan"), -1.0, float("inf"), True, "60"):
            with pytest.raises(ValueError):
                reconcile_nonterminal_orders(
                    store, broker_module=_AbsentBroker, min_absence_age_seconds=bad,
                )
        assert store.get_proposal("tp-inflight")["status"] == SUBMITTING


def test_age_is_rechecked_atomically_before_releasing_the_reservation():
    """A stale list snapshot must not authorize release after another worker
    refreshes the row while the broker lookup is in flight."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store_with_reservation(temp)
        old = (
            datetime.now(timezone.utc)
            - timedelta(seconds=MIN_ABSENCE_AGE_SECONDS + 30)
        ).isoformat()
        with sqlite3.connect(store.path) as connection:
            connection.execute(
                "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
                (old, "tp-inflight"),
            )

        class _RefreshDuringLookup(_AbsentBroker):
            @staticmethod
            def find_order_by_client_id(client_order_id):
                claimed = store.claim_proposal(
                    "tp-inflight",
                    expected_status=SUBMITTING,
                    new_status="reconciling",
                )
                assert claimed is not None
                return None

        result = reconcile_nonterminal_orders(
            store,
            broker_module=_RefreshDuringLookup,
            now=datetime.now(timezone.utc),
        )

        assert result["confirmed_absent"] == 0
        assert store.get_proposal("tp-inflight")["status"] == "reconciling"
        assert _reserved_notional(store) == RESERVED_NOTIONAL


def test_a_blocked_reconcile_attempt_does_not_restart_the_grace_clock():
    """Found while reviewing the reconciliation-hardening round (2026-07-30).

    reconcile_submission() bounces a too-recent 404 back to
    "submission_unknown". That write used to stamp updated_at = now -- but the
    grace period is measured FROM updated_at, so every attempt pushed its own
    deadline out. A user re-clicking Reconcile inside the window could never
    let the proposal age enough to resolve, and because the background poller
    reads the same column, the impatient clicking starved that too. The bounce
    must preserve the original timestamp: it made no progress, so it is not a
    transition.
    """
    from assistant.execution_service import reconcile_submission
    import execution.alpaca_broker as broker_module

    original_lookup = broker_module.find_order_by_client_id
    broker_module.find_order_by_client_id = lambda client_order_id: None
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = _store_with_reservation(temp, status=SUBMISSION_UNKNOWN)
            before = _updated_at(store, SUBMISSION_UNKNOWN)

            for _ in range(3):
                with pytest.raises(Exception):
                    reconcile_submission("tp-inflight", store)

            after = _updated_at(store, SUBMISSION_UNKNOWN)
            assert after == before, (
                "a no-progress bounce must not refresh updated_at -- doing so "
                "restarts the very grace period the caller is waiting on"
            )
            assert _reserved_notional(store) == RESERVED_NOTIONAL
    finally:
        broker_module.find_order_by_client_id = original_lookup


def test_absence_age_helper_fails_closed_without_claim_metadata():
    """Pins a fail-closed default that is unreachable today.

    claim_proposal() always supplies _claimed_from_updated_at (updated_at is
    NOT NULL), so this branch is defensive dead code -- and a mutation flipping
    it to fail OPEN survived the whole suite. Asserted directly so the safe
    direction is pinned rather than merely intended.
    """
    from assistant.execution_service import _broker_absence_is_old_enough

    now = datetime.now(timezone.utc)
    assert _broker_absence_is_old_enough({}, now=now) is False
    assert _broker_absence_is_old_enough({"_claimed_from_updated_at": None}, now=now) is False
    assert _broker_absence_is_old_enough(
        {"_claimed_from_updated_at": "not-a-timestamp"}, now=now,
    ) is False



# --- L6: a legacy "executed" row must not be corrupted by an absent lookup ---
#
# proposal_status_for_order() never returns EXECUTED; it only exists on rows
# written before fill-aware lifecycle tracking, i.e. OLD trades. Brokers age
# orders out of their lookup window, so "not found" is the EXPECTED answer for
# one of these. Flipping it to submission_unknown became actively harmful once
# IN_FLIGHT_INTENT_STATUSES started holding a ticker/side slot: a long-completed
# trade would silently block every new proposal for that ticker/side and fail
# readiness, on the strength of a lookup miss that proves nothing.

def test_an_absent_legacy_executed_order_is_left_alone():
    from assistant.proposal_status import EXECUTED

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status=EXECUTED, proposal_id="tp-legacy"))

        result = reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        assert store.get_proposal("tp-legacy")["status"] == EXECUTED
        assert result["legacy_unverifiable"] == 1
        assert result["confirmed_absent"] == 0


def test_an_absent_legacy_executed_order_remains_fail_closed_under_real_status():
    """Absence preserves the legacy status but cannot prove it is terminal."""
    from assistant.proposal_status import EXECUTED, IN_FLIGHT_INTENT_STATUSES
    from assistant.storage import DuplicateIntentConflict

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status=EXECUTED, proposal_id="tp-legacy"))
        fresh = _proposal(proposal_id="tp-new")
        fresh["status"] = "proposed"
        store.save_proposal(fresh)

        reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # EXECUTED is itself in IN_FLIGHT_INTENT_STATUSES (a legacy row may be
        # an accepted-but-unfilled order), so this claim remains blocked under
        # the truthful legacy status. The old test used try/except without an
        # assertion when no exception was raised, so it passed in both the
        # blocking and non-blocking cases.
        assert store.get_proposal("tp-legacy")["status"] == EXECUTED
        with pytest.raises(DuplicateIntentConflict, match="executed"):
            store.claim_proposal(
                "tp-new", expected_status="proposed", new_status="validating",
                conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
            )


def test_an_absent_active_order_is_still_treated_as_anomalous():
    """The narrowing must not weaken the genuine case: a BROKER_ACCEPTED order
    vanishing IS anomalous and must still be surfaced.

    Measured note: putting EXECUTED back into the else-branch's
    expected_statuses tuple survives this file, because the `elif` above
    short-circuits first and the else can never receive an EXECUTED row. Dead
    list membership, not a behavioural property -- removed for clarity, and
    left unpinned rather than asserted on source text.
    """
    from assistant.proposal_status import BROKER_ACCEPTED, SUBMISSION_UNKNOWN

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status=BROKER_ACCEPTED, proposal_id="tp-active"))

        result = reconcile_nonterminal_orders(
            store, broker_module=_AbsentBroker,
            now=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        assert store.get_proposal("tp-active")["status"] == SUBMISSION_UNKNOWN
        assert result["legacy_unverifiable"] == 0

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
