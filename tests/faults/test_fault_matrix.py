"""GR-3 fault-injection matrix (archived plan section 8.2, plus the two
isolation regressions GENERAL_READINESS_STATUS earmarked for GR-3).

Every test injects one adversity against a REAL SQLite store and the real
execution entry points, with only the broker scripted, and asserts BOTH
halves of the plan's contract: the required refusal/resolution AND that no
partial execution state persists afterwards. ``scripts/run_fault_drill.py``
runs this exact matrix and records the outcome as drill evidence; the test
names here are the drill inventory, so renaming a test without updating the
harness fails the drill run loudly.

Faults F1-F9 are the archived plan's table rows, in order. F10/F11 are the
2026-08-02 isolation incidents (pytest writing the operator database;
live broker calls during collection) recorded as standing drills.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import execution.alpaca_broker as real_broker_module
from assistant.execution_service import (
    ProposalExecutionError,
    execute_approved_paper_proposal,
    reconcile_submission,
    recover_stale_claim,
    recover_stale_reconciliation,
)
from assistant.order_reconciler import reconcile_nonterminal_orders
from assistant.storage import AssistantStore, configured_db_path
from fault_harness import (
    NOW_ET,
    ScriptedBroker,
    accepted_order,
    disk_full_on_statement,
    fresh_quote,
    held_position,
    make_proposal,
    observable_state,
    portfolio,
    ready_account,
    referential_integrity_holds,
    scripted_broker,
)


def _held_portfolio(*positions):
    return portfolio(positions=list(positions) or [held_position()])


def _age_proposal(store: AssistantStore, proposal_id: str, seconds: int) -> None:
    """Backdate updated_at so stale-guards see a genuinely old row."""
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with store._connect() as connection:
        connection.execute(
            "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
            (stamp, proposal_id),
        )


def _reserve(store: AssistantStore, proposal_id: str) -> None:
    store.reserve_execution_budget(
        proposal_id,
        trading_day="2026-08-03",
        notional="100.00",
        max_daily_notional="1000.00",
        max_daily_orders=5,
    )


def _sell_broker(**overrides) -> ScriptedBroker:
    behaviours = {
        "is_configured": True,
        "assert_account_and_asset_ready": ready_account(),
        "get_latest_quote": fresh_quote(),
        "submit_market_order": accepted_order(side="sell"),
        "find_order_by_client_id": None,
    }
    behaviours.update(overrides)
    return ScriptedBroker(**behaviours)


# --------------------------------------------------------------------------
# F1 — broker times out after submit, before ack
# --------------------------------------------------------------------------


def test_f1_submit_timeout_resolves_by_lookup_never_resubmits(store, policy):
    store.save_proposal(make_proposal("p-f1", side="sell"))
    broker = _sell_broker(
        submit_market_order=TimeoutError("gateway timed out after submit"),
        find_order_by_client_id=accepted_order("paper-f1", side="sell"),
    )

    with scripted_broker(broker):
        result = execute_approved_paper_proposal(
            "p-f1", "approve", _held_portfolio(), policy, store, now_et=NOW_ET,
            earnings_days_away=10,
        )

    # Resolution came from the idempotency-key lookup, not a blind retry.
    assert result["order_id"] == "paper-f1"
    assert broker.count("submit_market_order") == 1
    assert broker.call_names.index("find_order_by_client_id") > broker.call_names.index(
        "submit_market_order"
    )
    state = observable_state(store, "p-f1")
    assert state["proposal_status"] == "broker_accepted"
    assert [o["order_id"] for o in state["broker_orders"]] == ["paper-f1"]
    assert len(state["reservations"]) == 1  # budget stays accounted
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F2 — broker returns a duplicate order ID (crash-retry under the same
#      idempotency key must adopt, never create a second order)
# --------------------------------------------------------------------------


def test_f2_duplicate_order_id_is_idempotent_one_order_one_journal(store, policy):
    store.save_proposal(make_proposal("p-f2", side="sell"))
    broker = _sell_broker(submit_market_order=accepted_order("paper-f2", side="sell"))

    with scripted_broker(broker):
        execute_approved_paper_proposal(
            "p-f2", "approve", _held_portfolio(), policy, store, now_et=NOW_ET,
            earnings_days_away=10,
        )

    # Simulate the crash-retry: the proposal is forced back to the
    # unresolved state a dead process leaves behind, and reconciliation
    # re-encounters the SAME broker order id under the idempotency key.
    store.update_proposal_status_if_current(
        "p-f2", expected_statuses=("broker_accepted",), new_status="submission_unknown"
    )
    broker.set("find_order_by_client_id", accepted_order("paper-f2", side="sell"))
    with scripted_broker(broker):
        result = reconcile_submission("p-f2", store)

    assert result["order_id"] == "paper-f2"
    assert broker.count("submit_market_order") == 1  # never resubmitted
    state = observable_state(store, "p-f2")
    assert [o["order_id"] for o in state["broker_orders"]] == ["paper-f2"]
    with store._connect() as connection:
        order_rows = connection.execute(
            "SELECT COUNT(*) FROM broker_orders WHERE order_id = 'paper-f2'"
        ).fetchone()[0]
    assert order_rows == 1
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F3 — process killed mid-submission: restart recovery resolves the claim
# --------------------------------------------------------------------------


def test_f3_pre_broker_crash_recovers_claim_and_frees_the_slot(store):
    store.save_proposal(make_proposal("p-f3a", side="sell", status="validating"))
    _age_proposal(store, "p-f3a", seconds=3600)

    recovered = recover_stale_claim("p-f3a", store, stale_after_seconds=900)

    assert recovered["status"] == "validation_failed"
    state = observable_state(store, "p-f3a")
    assert state["proposal_status"] == "validation_failed"
    assert state["reservations"] == []  # pre-broker: nothing reserved, nothing leaked
    assert state["broker_orders"] == []
    assert referential_integrity_holds(store)


def test_f3_crash_mid_reconciliation_recovers_to_retryable(store):
    store.save_proposal(make_proposal("p-f3b", side="sell", status="reconciling"))
    _reserve(store, "p-f3b")
    _age_proposal(store, "p-f3b", seconds=3600)

    recovered = recover_stale_reconciliation("p-f3b", store, stale_after_seconds=300)

    assert recovered["status"] == "submission_unknown"
    state = observable_state(store, "p-f3b")
    assert state["proposal_status"] == "submission_unknown"
    assert len(state["reservations"]) == 1  # ambiguous: budget must stay held
    assert referential_integrity_holds(store)


def test_f3_restart_recovers_submitting_order_without_resubmit(store):
    store.save_proposal(make_proposal("p-f3c", side="sell", status="submitting"))
    _reserve(store, "p-f3c")
    broker = _sell_broker(
        find_order_by_client_id=accepted_order("paper-f3c", side="sell")
    )

    with scripted_broker(broker):
        result = reconcile_nonterminal_orders(store, now=NOW_ET)

    assert result["updated"] == 1
    assert broker.count("submit_market_order") == 0
    assert broker.count("find_order_by_client_id") == 1
    state = observable_state(store, "p-f3c")
    assert state["proposal_status"] == "broker_accepted"
    assert [order["order_id"] for order in state["broker_orders"]] == ["paper-f3c"]
    assert len(state["reservations"]) == 1
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F4 — broker reports an order the ledger does not expect (same-key
#      mismatch): critical halt, further submissions refused
# --------------------------------------------------------------------------


def test_f4_unexpected_order_halts_platform_and_blocks_new_submissions(store, policy):
    store.set_kill_switch(False, reason="drill reset")
    store.save_proposal(make_proposal("p-f4", side="sell", status="submission_unknown"))
    _reserve(store, "p-f4")
    broker = _sell_broker(
        # Same idempotency key, WRONG side: not our order.
        find_order_by_client_id=accepted_order("paper-f4", side="buy"),
    )

    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError) as caught:
            reconcile_submission("p-f4", store)

    assert "MISMATCHED" in str(caught.value)
    assert store.get_kill_switch()["active"] is True
    alerts = store.list_operational_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["category"] == "broker_reconciliation"
    assert alerts[0]["details"]["proposal_id"] == "p-f4"
    state = observable_state(store, "p-f4")
    assert state["proposal_status"] == "submission_unknown"  # never auto-resolved
    assert len(state["reservations"]) == 1

    # Further submissions are refused while the platform is halted.
    store.save_proposal(make_proposal("p-f4-next", side="sell"))
    broker_next = _sell_broker()
    with scripted_broker(broker_next):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "p-f4-next", "approve", _held_portfolio(), policy, store,
                now_et=NOW_ET, earnings_days_away=10,
            )
    assert broker_next.count("submit_market_order") == 0
    assert referential_integrity_holds(store)
    store.set_kill_switch(False, reason="drill cleanup")


# --------------------------------------------------------------------------
# F5 — ticker halted between approval and submit: per-ticker refusal,
#      risk-reducing sells elsewhere still permitted
# --------------------------------------------------------------------------


def test_f5_halted_ticker_refused_but_other_risk_reducing_sell_proceeds(store, policy):
    def preflight(ticker):
        if ticker == "HALTX":
            raise RuntimeError("asset HALTX is halted and not tradable")
        return ready_account(ticker)

    holdings = _held_portfolio(held_position("HALTX"), held_position("AAPL"))

    store.save_proposal(make_proposal("p-f5-halt", side="sell", ticker="HALTX"))
    broker = _sell_broker(assert_account_and_asset_ready=preflight)
    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-f5-halt", "approve", holdings, policy, store, now_et=NOW_ET,
                earnings_days_away=10,
            )
    assert "preflight failed" in str(caught.value)
    assert broker.count("submit_market_order") == 0
    # A per-ticker halt is not a platform halt.
    assert store.get_kill_switch()["active"] is False
    halted_state = observable_state(store, "p-f5-halt")
    assert halted_state["proposal_status"] == "blocked"
    assert halted_state["reservations"] == []
    assert halted_state["broker_orders"] == []

    # The OTHER holding's risk-reducing sell still executes.
    store.save_proposal(make_proposal("p-f5-sell", side="sell", ticker="AAPL"))
    broker_ok = _sell_broker(assert_account_and_asset_ready=preflight)
    with scripted_broker(broker_ok):
        result = execute_approved_paper_proposal(
            "p-f5-sell", "approve", holdings, policy, store, now_et=NOW_ET,
            earnings_days_away=10,
        )
    assert result["status"] == "accepted"
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F6 — corporate action between snapshot and submit: share-count mismatch
# --------------------------------------------------------------------------


def test_f6_share_count_mismatch_after_corporate_action_is_refused(store, policy):
    # The proposal predates a split: it sells 10 shares, but the fresh
    # snapshot shows only 5 exist.
    store.save_proposal(make_proposal("p-f6", side="sell", shares=10))
    post_split = _held_portfolio(held_position("AAPL", shares=5.0))
    broker = _sell_broker()

    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "p-f6", "approve", post_split, policy, store, now_et=NOW_ET,
                earnings_days_away=10,
            )

    assert broker.count("submit_market_order") == 0
    state = observable_state(store, "p-f6")
    assert state["proposal_status"] == "blocked"
    assert state["reservations"] == []
    assert state["broker_orders"] == []
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F7 — clock skew / stale snapshot: freshness refusals in both directions
# --------------------------------------------------------------------------


def test_f7_stale_quote_is_refused(store, policy):
    store.save_proposal(make_proposal("p-f7a", side="sell"))
    stale = fresh_quote(timestamp=NOW_ET - timedelta(minutes=30))
    broker = _sell_broker(get_latest_quote=stale)

    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "p-f7a", "approve", _held_portfolio(), policy, store, now_et=NOW_ET,
                earnings_days_away=10,
            )

    assert broker.count("submit_market_order") == 0
    state = observable_state(store, "p-f7a")
    assert state["proposal_status"] == "blocked"
    assert state["reservations"] == []
    assert state["broker_orders"] == []
    assert referential_integrity_holds(store)


def test_f7_future_quote_timestamp_clock_skew_is_refused(store, policy):
    store.save_proposal(make_proposal("p-f7b", side="sell"))
    skewed = fresh_quote(timestamp=NOW_ET + timedelta(minutes=10))
    broker = _sell_broker(get_latest_quote=skewed)

    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "p-f7b", "approve", _held_portfolio(), policy, store, now_et=NOW_ET,
                earnings_days_away=10,
            )

    assert broker.count("submit_market_order") == 0
    state = observable_state(store, "p-f7b")
    assert state["proposal_status"] == "blocked"
    assert state["reservations"] == []
    assert state["broker_orders"] == []
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F8 — disk full during the journal write: the atomic projection rolls
#      back whole, and an accepted order is never reported as failed
# --------------------------------------------------------------------------


def test_f8_disk_full_during_journal_rolls_back_and_keeps_the_truth(store, policy):
    store.save_proposal(make_proposal("p-f8", side="sell"))
    broker = _sell_broker(submit_market_order=accepted_order("paper-f8", side="sell"))

    with scripted_broker(broker):
        with disk_full_on_statement("INSERT INTO broker_order_events"):
            result = execute_approved_paper_proposal(
                "p-f8", "approve", _held_portfolio(), policy, store, now_et=NOW_ET,
                earnings_days_away=10,
            )

    # The broker DID accept: the caller gets the order, never a failure.
    assert result["order_id"] == "paper-f8"
    proposal = store.get_proposal("p-f8")
    assert "local recording failed" in (proposal.get("error") or "")
    state = observable_state(store, "p-f8")
    # The multi-row projection is atomic: the order row written earlier in
    # the same transaction was rolled back with the failed event insert --
    # no half-journal survives.
    assert state["broker_orders"] == []
    assert state["order_events"] == []
    assert len(state["reservations"]) == 1  # budget stays held for reconciliation
    assert referential_integrity_holds(store)

    # Once the disk recovers, normal journaling repairs the record.
    store.update_proposal_status_if_current(
        "p-f8", expected_statuses=(proposal["status"],), new_status="submission_unknown"
    )
    broker.set("find_order_by_client_id", accepted_order("paper-f8", side="sell"))
    with scripted_broker(broker):
        reconcile_submission("p-f8", store)
    after = observable_state(store, "p-f8")
    assert [o["order_id"] for o in after["broker_orders"]] == ["paper-f8"]
    assert referential_integrity_holds(store)


# --------------------------------------------------------------------------
# F9 — kill switch flips mid-flight: no new submissions, in-flight resolves
# --------------------------------------------------------------------------


def test_f9_kill_switch_mid_flight_blocks_new_but_inflight_resolves(store, policy):
    store.set_kill_switch(False, reason="drill reset")
    # An in-flight submission is already at the broker...
    store.save_proposal(make_proposal("p-f9-inflight", side="sell", status="submitting"))
    _reserve(store, "p-f9-inflight")
    # ...when the operator flips the kill switch.
    store.set_kill_switch(True, reason="drill: mid-flight halt")

    # No NEW submission may start.
    store.save_proposal(make_proposal("p-f9-new", side="sell"))
    broker_new = _sell_broker()
    with scripted_broker(broker_new):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "p-f9-new", "approve", _held_portfolio(), policy, store,
                now_et=NOW_ET, earnings_days_away=10,
            )
    assert broker_new.count("submit_market_order") == 0

    # The in-flight order still resolves cleanly: reconciliation is risk
    # reduction and must not be blocked by the halt.
    broker_inflight = _sell_broker(
        find_order_by_client_id=accepted_order("paper-f9", side="sell")
    )
    with scripted_broker(broker_inflight):
        result = reconcile_submission("p-f9-inflight", store)
    assert result["order_id"] == "paper-f9"
    state = observable_state(store, "p-f9-inflight")
    assert state["proposal_status"] == "broker_accepted"
    assert referential_integrity_holds(store)
    store.set_kill_switch(False, reason="drill cleanup")


# --------------------------------------------------------------------------
# F10/F11 — the 2026-08-02 isolation incidents, kept as standing drills
# --------------------------------------------------------------------------


def test_f10_tests_are_isolated_from_the_operator_database():
    configured = os.environ.get("TRADING_ASSISTANT_DB", "")
    assert configured, "test sessions must pin TRADING_ASSISTANT_DB away from the operator DB"
    repo_default = Path(__file__).resolve().parent.parent.parent / "data" / "trading_assistant.db"
    assert Path(configured).resolve() != repo_default.resolve()
    assert configured_db_path() == Path(configured)


def test_f11_no_live_broker_credentials_reach_the_suite():
    assert "APCA_API_KEY_ID" not in os.environ
    assert "APCA_API_SECRET_KEY" not in os.environ
    # The real, unpatched predicate: without credentials no code path can
    # open a live brokerage session during tests.
    assert real_broker_module.is_configured() is False


def test_f4_submit_time_unexpected_order_also_alerts_and_halts(store, policy):
    """The SUBMIT-TIME twin of the reconciliation mismatch: a raising
    submit whose idempotency-key lookup finds an order that does NOT match
    the intent must produce the same atomic critical alert + halt as the
    manual-reconciliation path -- an anomaly discovered thirty seconds
    earlier is not less critical."""
    store.set_kill_switch(False, reason="drill reset")
    store.save_proposal(make_proposal("p-f4-submit", side="sell"))
    broker = _sell_broker(
        submit_market_order=TimeoutError("gateway timed out after submit"),
        # Same key, wrong side: not our order.
        find_order_by_client_id=accepted_order("paper-f4s", side="buy"),
    )

    with scripted_broker(broker):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-f4-submit", "approve", _held_portfolio(), policy, store,
                now_et=NOW_ET, earnings_days_away=10,
            )

    assert "MISMATCHED" in str(caught.value)
    assert store.get_kill_switch()["active"] is True
    alerts = [
        a for a in store.list_operational_alerts()
        if a["category"] == "broker_reconciliation"
        and a["details"].get("proposal_id") == "p-f4-submit"
    ]
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    state = observable_state(store, "p-f4-submit")
    assert state["proposal_status"] == "submission_unknown"
    assert len(state["reservations"]) == 1
    assert referential_integrity_holds(store)
    store.set_kill_switch(False, reason="drill cleanup")
