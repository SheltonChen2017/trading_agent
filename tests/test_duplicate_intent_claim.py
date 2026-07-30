"""
The duplicate-order rule must be serialized, not read from a snapshot.

claim_proposal() has always serialized a single proposal_id. But the
duplicate rule is about ticker+side, and that was evaluated from a plain read
(recent_executed_intents() plus the broker's open orders) nowhere near a
lock. Two DIFFERENT proposals to buy the same ticker, approved concurrently
before either order became visible at the broker, could both observe "no
duplicate" and both submit -- and because they carry distinct idempotency
keys, the broker sees two genuinely separate real orders (independent
review, 2026-07-30).

test_concurrent_claims_for_the_same_ticker_and_side_do_not_both_win is the
one that actually reproduces the race; the rest pin the rule's edges.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

from assistant.proposal_status import (
    BROKER_ACCEPTED,
    FILLED,
    SUBMISSION_FAILED,
    IN_FLIGHT_INTENT_STATUSES,
    SUBMITTING,
)
from assistant.storage import AssistantStore, DuplicateIntentConflict


def _proposal(proposal_id: str, *, ticker="AAPL", side="buy", status="proposed") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-30T14:00:00+00:00",
        "expires_at": "2099-12-31T00:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": ticker, "side": side, "shares": 10,
            "order_type": "market", "limit_price": None,
        },
    }


def _store(temp: str, *proposals: dict) -> AssistantStore:
    store = AssistantStore(Path(temp) / "assistant.db")
    for proposal in proposals:
        store.save_proposal(proposal)
    return store


def _claim(store: AssistantStore, proposal_id: str):
    return store.claim_proposal(
        proposal_id,
        expected_status="proposed",
        new_status="validating",
        conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
    )


@pytest.mark.parametrize("live_status", IN_FLIGHT_INTENT_STATUSES)
def test_a_live_sibling_blocks_the_claim(live_status):
    """Every status where a broker order may exist must block a second claim
    for the same ticker/side -- parametrized so adding a status to the tuple
    without meaning it cannot pass silently."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-live", status=live_status),
            _proposal("tp-second"),
        )
        with pytest.raises(DuplicateIntentConflict) as caught:
            _claim(store, "tp-second")
        assert "tp-live" in str(caught.value)
        assert store.get_proposal("tp-second")["status"] == "proposed"


def test_a_terminal_sibling_does_not_block_the_claim():
    """The guard must not become a permanent lock: once the earlier order is
    resolved, the ticker/side is free again."""
    for terminal in (FILLED, SUBMISSION_FAILED, "canceled", "expired"):
        # A fresh database per case: a shared one would leave the PREVIOUS
        # iteration's proposal sitting in "validating", which legitimately
        # blocks the next claim and would make this test pass for the wrong
        # reason.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = _store(
                temp,
                _proposal("tp-done", status=terminal),
                _proposal("tp-next"),
            )
            assert _claim(store, "tp-next") is not None, (
                f"a sibling in terminal status {terminal} must not block a claim"
            )


def test_a_different_ticker_does_not_block_the_claim():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-live", ticker="MSFT", status=SUBMITTING),
            _proposal("tp-second", ticker="AAPL"),
        )
        assert _claim(store, "tp-second") is not None


def test_the_opposite_side_does_not_block_the_claim():
    """Identity is ticker+side: a live BUY must not block a risk-reducing
    SELL of the same ticker."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-live", side="buy", status=SUBMITTING),
            _proposal("tp-second", side="sell"),
        )
        assert _claim(store, "tp-second") is not None


def test_ticker_and_side_comparison_is_case_insensitive():
    """A lowercase stored ticker must not slip past the guard."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-live", ticker="aapl", side="BUY", status=BROKER_ACCEPTED),
            _proposal("tp-second", ticker="AAPL", side="buy"),
        )
        with pytest.raises(DuplicateIntentConflict):
            _claim(store, "tp-second")


def test_an_unreadable_sibling_intent_blocks_the_claim():
    """Being unable to rule out a live order is not evidence there isn't one."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        broken = _proposal("tp-broken", status=SUBMITTING)
        broken["intent"] = {"side": "buy"}  # no ticker
        store = _store(temp, broken, _proposal("tp-second"))
        with pytest.raises(DuplicateIntentConflict) as caught:
            _claim(store, "tp-second")
        assert "tp-broken" in str(caught.value)


def test_the_guard_is_off_by_default():
    """Callers that transition a proposal for other reasons (expiry,
    reconciliation) must keep their existing behavior."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(
            temp,
            _proposal("tp-live", status=SUBMITTING),
            _proposal("tp-second"),
        )
        assert store.claim_proposal(
            "tp-second", expected_status="proposed", new_status="validating",
        ) is not None


def test_concurrent_claims_for_the_same_ticker_and_side_do_not_both_win():
    """THE race. Two threads claim two DIFFERENT proposals for the same
    ticker/side at the same moment. A snapshot-based check lets both through;
    a check inside the claim's own BEGIN IMMEDIATE transaction cannot.

    The barrier makes both threads arrive together, so this exercises the
    overlap rather than a sequential pair.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp, _proposal("tp-a"), _proposal("tp-b"))
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def attempt(proposal_id: str) -> None:
            barrier.wait(timeout=10)
            try:
                claimed = _claim(store, proposal_id)
                verdict = "claimed" if claimed is not None else "not_claimed"
            except DuplicateIntentConflict:
                verdict = "blocked"
            with lock:
                outcomes.append(verdict)

        threads = [threading.Thread(target=attempt, args=(pid,)) for pid in ("tp-a", "tp-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()

        assert outcomes.count("claimed") == 1, (
            f"exactly one claim must win, got {outcomes}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
