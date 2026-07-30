"""
A proposal stranded before submission must not lock its ticker/side forever.

The cross-proposal duplicate guard (2026-07-30) made claim_proposal() hold a
ticker+side slot across IN_FLIGHT_INTENT_STATUSES, which includes "validating"
and "approved". That closed a real double-submit race -- but it also turned a
row stranded by a killed process into a PERMANENT block on every future
proposal for that ticker and side, with no way out:

  * recover_stale_reconciliation() only accepts "reconciling";
  * expiry sweeps only touch "proposed";
  * no CLI command reached it.

The only remedy was hand-editing SQLite. Found by reviewing the change that
caused it. Recovery is safe for exactly these two statuses because
submit_approved_proposal() writes "submitting" BEFORE it calls the broker, so a
row still in "validating"/"approved" provably has no order behind it.
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from assistant.execution_service import (
    PRE_BROKER_STRANDED_STATUSES,
    ProposalExecutionError,
    recover_stale_claim,
)
from assistant.proposal_status import (
    APPROVED,
    IN_FLIGHT_INTENT_STATUSES,
    SUBMITTING,
    VALIDATING,
    VALIDATION_FAILED,
)
from assistant.storage import AssistantStore, DuplicateIntentConflict


def _proposal(proposal_id: str, status: str = "proposed", ticker: str = "AAPL") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-30T14:00:00+00:00",
        "expires_at": "2099-12-31T00:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": ticker, "side": "buy", "shares": 10,
            "order_type": "market", "limit_price": None,
        },
    }


def _store(temp: str, *proposals: dict) -> AssistantStore:
    store = AssistantStore(Path(temp) / "assistant.db")
    for proposal in proposals:
        store.save_proposal(proposal)
    return store


def _backdate(store: AssistantStore, proposal_id: str, *, seconds: int) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    connection = sqlite3.connect(store.path)
    try:
        connection.execute(
            "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
            (stamp, proposal_id),
        )
        connection.commit()
    finally:
        connection.close()


def _claim_new(store: AssistantStore):
    return store.claim_proposal(
        "tp-new", expected_status="proposed", new_status=VALIDATING,
        conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
    )


@pytest.mark.parametrize("stranded_status", PRE_BROKER_STRANDED_STATUSES)
def test_a_stranded_pre_broker_claim_blocks_new_proposals_until_recovered(stranded_status):
    """THE regression, both halves: it blocks, and recovery unblocks it."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", stranded_status), _proposal("tp-new"))
        _backdate(store, "tp-stuck", seconds=7200)

        with pytest.raises(DuplicateIntentConflict):
            _claim_new(store)

        recovered = recover_stale_claim("tp-stuck", store)
        assert recovered["status"] == VALIDATION_FAILED
        assert _claim_new(store) is not None


def test_recovery_leaves_a_genuinely_in_flight_claim_alone():
    """A validation claimed moments ago is in flight, not stranded. Recovering
    it would resolve a proposal another worker is actively processing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", VALIDATING))

        with pytest.raises(ProposalExecutionError) as caught:
            recover_stale_claim("tp-stuck", store, stale_after_seconds=900)

        assert "in flight" in str(caught.value)
        assert store.get_proposal("tp-stuck")["status"] == VALIDATING


def test_post_submission_statuses_are_refused():
    """The whole safety argument is that these statuses precede any broker
    call. "submitting" does NOT -- an order may exist -- so this must refuse
    rather than declare it failed and release its slot."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-live", SUBMITTING))
        _backdate(store, "tp-live", seconds=7200)

        with pytest.raises(ProposalExecutionError) as caught:
            recover_stale_claim("tp-live", store)

        assert "not a stale pre-broker claim" in str(caught.value)
        assert store.get_proposal("tp-live")["status"] == SUBMITTING


def test_the_recoverable_set_is_exactly_the_pre_broker_statuses():
    """Pins the set itself. Adding a post-submission status here would make
    recovery unsafe, and no behavioral test would obviously fail."""
    assert PRE_BROKER_STRANDED_STATUSES == (VALIDATING, APPROVED)
    assert SUBMITTING not in PRE_BROKER_STRANDED_STATUSES
    for status in PRE_BROKER_STRANDED_STATUSES:
        assert status in IN_FLIGHT_INTENT_STATUSES, (
            "recovery only matters for statuses that hold the ticker/side slot"
        )


def test_recovery_records_why_it_was_safe():
    """The audit trail must say no broker order existed -- otherwise a later
    reader cannot tell this apart from abandoning a real order."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", VALIDATING))
        _backdate(store, "tp-stuck", seconds=7200)

        recovered = recover_stale_claim("tp-stuck", store)

        assert "No broker order exists" in recovered["error"]
        assert recovered["recovered_at"]


def test_an_unknown_proposal_raises_rather_than_reporting_success():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        with pytest.raises(ProposalExecutionError) as caught:
            recover_stale_claim("nope", store)
        assert "Unknown proposal" in str(caught.value)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "900"])
def test_a_bad_staleness_window_is_rejected(bad):
    """A zero/negative window makes every claim look stale immediately,
    defeating the guard -- the same trap already fixed on
    recover_stale_reconciliation()."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", VALIDATING))
        with pytest.raises(ValueError):
            recover_stale_claim("tp-stuck", store, stale_after_seconds=bad)
        assert store.get_proposal("tp-stuck")["status"] == VALIDATING


def test_recovery_does_not_touch_a_different_ticker():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-stuck", VALIDATING, ticker="AAPL"),
            _proposal("tp-other", VALIDATING, ticker="MSFT"),
        )
        _backdate(store, "tp-stuck", seconds=7200)
        _backdate(store, "tp-other", seconds=7200)

        recover_stale_claim("tp-stuck", store)

        assert store.get_proposal("tp-other")["status"] == VALIDATING



# --- readiness must SURFACE the block, not just offer a way out ---------
#
# Neither CRITICAL_UNRESOLVED_STATUSES nor ACTIVE_ORDER_STATUSES covers
# "validating"/"approved", so readiness reported ready=True while that
# ticker/side could not be claimed at all. "Readiness must match the enforcer"
# is a standing rule here; this is the same mismatch at a new status.

def _readiness(store, **kwargs):
    from assistant.policy import TradingPolicy
    from assistant.readiness import transaction_readiness

    policy = TradingPolicy(
        version="t", name="t", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
    )
    return transaction_readiness(store, policy, check_broker=False, **kwargs)


def _named(report, name):
    return next(c for c in report["checks"] if c["name"] == name)


@pytest.mark.parametrize("stranded_status", PRE_BROKER_STRANDED_STATUSES)
def test_readiness_reports_a_stranded_pre_broker_claim(stranded_status):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", stranded_status))
        _backdate(store, "tp-stuck", seconds=7200)

        check = _named(_readiness(store), "stranded_pre_broker_claims")
        assert check["ok"] is False
        assert "tp-stuck" in check["detail"]
        assert "recover-stale-claim" in check["detail"]


def test_readiness_ignores_a_claim_that_is_still_in_flight():
    """A proposal being validated right now must not fail readiness."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-live", VALIDATING))

        check = _named(_readiness(store), "stranded_pre_broker_claims")
        assert check["ok"] is True
        assert check["detail"] == "none"


def test_readiness_fails_closed_when_a_claim_age_is_unreadable():
    """A malformed timestamp must remain visible as an unresolved block.

    Silently dropping it reports readiness while the row still holds its
    ticker/side indefinitely, and recovery cannot prove that it is stale.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-corrupt", VALIDATING))
        connection = sqlite3.connect(store.path)
        try:
            connection.execute(
                "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
                ("not-a-timestamp", "tp-corrupt"),
            )
            connection.commit()
        finally:
            connection.close()

        report = _readiness(store)
        check = _named(report, "stranded_pre_broker_claims")
        assert check["ok"] is False
        assert "tp-corrupt" in check["detail"]
        assert "unreadable updated_at" in check["detail"]
        assert "repair" in check["detail"]
        assert report["ready"] is False


def test_readiness_is_clean_with_no_pre_broker_claims():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-fresh"))
        assert _named(_readiness(store), "stranded_pre_broker_claims")["ok"] is True


def test_a_stranded_claim_makes_the_overall_report_not_ready():
    """The check must actually gate `ready`, not just appear in the list."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-stuck", VALIDATING))
        _backdate(store, "tp-stuck", seconds=7200)
        assert _readiness(store)["ready"] is False


# --- verification follow-ups (reviewing the claim-fencing round) --------

def test_a_fenced_worker_raises_claim_lost_rather_than_a_generic_error():
    """The fencing helper itself: a revoked claim must refuse and not write.

    NOT a pin on `except _ProposalClaimLostError: raise` in
    execute_approved_paper_proposal(). Deleting that line was measured against
    the real execution path and is behaviorally UNOBSERVABLE -- the raised type
    and message are identical either way (without it, the generic
    ProposalExecutionError handler attempts its own fenced validating->blocked
    write, which raises the same error from inside the handler), and both paths
    send zero orders and hold zero reservations. It differs only in exception
    __context__ chaining. Pinning that would assert exception plumbing rather
    than behavior, so it is deliberately left unpinned and recorded here
    instead of implied by a test that does not actually cover it.
    """
    from assistant.execution_service import (
        _ProposalClaimLostError,
        _transition_pre_broker_claim,
    )

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-lost", VALIDATION_FAILED))

        with pytest.raises(_ProposalClaimLostError) as caught:
            _transition_pre_broker_claim(
                store, "tp-lost", expected_status=VALIDATING, new_status=APPROVED,
            )

        message = str(caught.value)
        assert "lost its execution claim" in message
        assert "Refusing to continue" in message
        assert store.get_proposal("tp-lost")["status"] == VALIDATION_FAILED


def test_an_unreadable_claim_timestamp_reports_the_real_reason():
    """readiness now BLOCKS on a corrupt updated_at, so recovery must not send
    the operator to wait out a staleness window that can never expire: the
    guard is a lexical SQL comparison, which a non-timestamp always loses.
    Recovery still refuses (staleness is unprovable, and assuming stale would
    revoke a possibly-live worker) -- but says so honestly."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-corrupt", VALIDATING))
        connection = sqlite3.connect(store.path)
        try:
            connection.execute(
                "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
                ("not-a-timestamp", "tp-corrupt"),
            )
            connection.commit()
        finally:
            connection.close()

        with pytest.raises(ProposalExecutionError) as caught:
            recover_stale_claim("tp-corrupt", store)

        message = str(caught.value)
        assert "not a readable timestamp" in message
        assert "data-integrity problem" in message
        assert "claimed less than" not in message, (
            "must not report a timing reason for a data-integrity failure"
        )
        assert store.get_proposal("tp-corrupt")["status"] == VALIDATING

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
