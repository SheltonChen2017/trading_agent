"""GR-1A: freeze the execution service's OBSERVABLE behaviour before splitting it.

`assistant/execution_service.py` is 2,040 lines and GR-1 splits it into
`assistant/execution_kernel/`. A refactor is only behaviour-preserving if
you can prove it, and a returned dictionary proves very little: the things
that matter on this path are the state transitions committed, the broker
calls actually issued and their ORDER, the reservations taken and released,
the telemetry appended, and the exact exception type raised.

So these tests characterise effects rather than return values. They are
deliberately assertion-heavy and deliberately not "clean" -- a
characterisation test's job is to be sensitive, not elegant. If the split
changes any of this, one of these fails and the change was not a refactor.

COVERAGE NOTE -- read before relying on this suite during GR-1B.

What is frozen: refusal paths (confirmation phrase, unknown proposal,
engaged kill switch), validation purity through the full body, ordinary
submission call ordering and persisted evidence, reservation release after a
pre-submit telemetry failure, timeout reconciliation without resubmission,
manual reconciliation, successful and refused recovery, exception identity,
and the atomic-claim structural invariant. Mutation-verified: deleting the
kill-switch check and changing an exception type are both detected.

What is NOT frozen exhaustively: every broker-error/mismatch/replacement-chain
branch, override review, local journal failure, and every concurrent race.
The existing execution suite still owns those cases. This file freezes the
representative cross-seam paths most likely to change during GR-1 extraction;
it must not be treated as proof that uncharacterised branches are safe.

Frozen against `assistant/execution_service.py` at GR-1A. The five public
entry points:

    validate_proposal_for_execution
    execute_approved_paper_proposal
    reconcile_submission
    recover_stale_reconciliation
    recover_stale_claim
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import execution.alpaca_broker as broker_module
from assistant import execution_service
from assistant.execution_service import (
    ProposalExecutionError,
    execute_approved_paper_proposal,
    reconcile_submission,
    recover_stale_claim,
    recover_stale_reconciliation,
    validate_proposal_for_execution,
)
from assistant.policy import compute_policy_fingerprint, load_policy
from assistant.proposal_status import (
    BROKER_ABSENCE_GRACE_SECONDS,
    SUBMISSION_FAILED,
    SUBMISSION_UNKNOWN,
)
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore

NOW_ET = datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# recorders
# --------------------------------------------------------------------------


class BrokerRecorder:
    """Records every broker call, in order, with its arguments."""

    def __init__(self, **behaviours: Any) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._behaviours = behaviours

    def _record(self, name: str):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            behaviour = self._behaviours.get(name)
            if isinstance(behaviour, Exception):
                raise behaviour
            if callable(behaviour):
                return behaviour(*args, **kwargs)
            return behaviour

        return call

    @property
    def call_names(self) -> tuple[str, ...]:
        return tuple(name for name, _, _ in self.calls)


_PATCHED = (
    "is_configured",
    "assert_account_and_asset_ready",
    "get_latest_quote",
    "submit_market_order",
    "submit_limit_order",
    "find_order_by_client_id",
    "get_order_by_id",
)


@contextlib.contextmanager
def patched_broker(recorder: BrokerRecorder):
    """The service does `import execution.alpaca_broker as broker` INSIDE the
    function, so the module attributes are what must be replaced."""
    originals = {
        name: getattr(broker_module, name, None)
        for name in _PATCHED
        if hasattr(broker_module, name)
    }
    try:
        for name in originals:
            setattr(broker_module, name, recorder._record(name))
        yield recorder
    finally:
        for name, original in originals.items():
            setattr(broker_module, name, original)


def observable_state(store: AssistantStore, proposal_id: str) -> dict[str, Any]:
    """Everything a caller or operator could see afterwards."""
    proposal = store.get_proposal(proposal_id)
    with store._connect() as connection:
        def rows(sql, *params):
            return [dict(r) for r in connection.execute(sql, params).fetchall()]

        # No status column: a reservation row EXISTS or it has been
        # released by deletion. That is the invariant worth freezing.
        reservations = rows(
            "SELECT proposal_id, trading_day, reserved_notional_text "
            "FROM execution_reservations WHERE proposal_id = ? "
            "ORDER BY trading_day", proposal_id
        )
        orders = rows(
            "SELECT order_id, proposal_id, status FROM broker_orders "
            "WHERE proposal_id = ? ORDER BY order_id", proposal_id
        )
        events = rows(
            "SELECT event_type FROM broker_order_events "
            "WHERE proposal_id = ? ORDER BY event_at, rowid", proposal_id
        )
        telemetry = rows(
            "SELECT event_type FROM execution_telemetry_events "
            "WHERE proposal_id = ? ORDER BY event_at, rowid", proposal_id
        )
    with store._connect() as connection:
        stamp = connection.execute(
            "SELECT updated_at FROM trade_proposals WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
    return {
        "proposal_status": None if proposal is None else proposal.get("status"),
        # Without updated_at, a write that rewrites the same status is
        # invisible and a purity regression passes unnoticed.
        "proposal_updated_at": None if stamp is None else stamp["updated_at"],
        "reservations": reservations,
        "broker_orders": orders,
        "order_events": [e["event_type"] for e in events],
        "telemetry": [t["event_type"] for t in telemetry],
    }


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _proposal(
    proposal_id: str = "p-1",
    *,
    status: str = "proposed",
    side: str = "buy",
    intent_overrides: dict | None = None,
    **overrides,
) -> dict:
    payload = {
        "proposal_id": proposal_id,
        "created_at": "2026-08-03T13:00:00+00:00",
        "expires_at": "2099-12-31T00:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "policy_version": load_policy().version,
        "policy_fingerprint": compute_policy_fingerprint(load_policy()),
        "intent": {
            "ticker": "AAPL",
            "side": side,
            "shares": 1,
            "order_type": "market",
            "limit_price": None,
        },
    }
    payload.update(overrides)
    if intent_overrides:
        payload["intent"] = {**payload["intent"], **intent_overrides}
    return payload


def _portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        positions=[],
        cash=100_000.0,
        total_equity=100_000.0,
        as_of="2026-08-03",
        buying_power=100_000.0,
        source="alpaca",
        account_mode="paper",
        account_id="paper-account-1",
        open_orders=[],
        open_orders_available=True,
    )


def _held_portfolio() -> PortfolioSnapshot:
    portfolio = _portfolio()
    portfolio.positions = [
        PortfolioPosition(
            ticker="AAPL",
            shares=10.0,
            entry_price=90.0,
            current_price=100.0,
            market_value=1000.0,
            unrealized_pnl_pct=11.1,
            is_leveraged_etf=False,
        )
    ]
    return portfolio


def _submission_recorder(*, submit: Any, lookup: Any = None) -> BrokerRecorder:
    return BrokerRecorder(
        is_configured=True,
        assert_account_and_asset_ready={
            "account": {
                "account_id": "paper-account-1",
                "paper": True,
                "status": "ACTIVE",
            },
            "asset": {"symbol": "AAPL", "status": "active", "tradable": True},
        },
        get_latest_quote={
            "ticker": "AAPL",
            "price": 100.0,
            "price_decimal": "100.00",
            "bid": 99.99,
            "ask": 100.01,
            "bid_decimal": "99.99",
            "ask_decimal": "100.01",
            "timestamp": NOW_ET,
        },
        submit_market_order=submit,
        find_order_by_client_id=lookup,
    )


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "characterize.db")


# --------------------------------------------------------------------------
# 1. validate_proposal_for_execution
# --------------------------------------------------------------------------


def test_validate_unknown_proposal_touches_no_broker_and_writes_nothing(store):
    recorder = BrokerRecorder()
    before = observable_state(store, "missing")
    with patched_broker(recorder):
        outcome = validate_proposal_for_execution(
            "missing", _portfolio(), load_policy(), store, now_et=NOW_ET
        )
    assert outcome.error is not None
    assert outcome.approved is False
    # A proposal that does not exist must not cause a broker round trip.
    assert recorder.call_names == ()
    assert observable_state(store, "missing") == before


def test_validate_is_side_effect_free_on_a_real_proposal(store):
    # A SELL of a held position, because the active policy refuses to open
    # new positions -- a buy returns early at that check and never exercises
    # the body this test claims to characterise. (Found by instrumenting the
    # return path after a purity mutation went undetected three times.)
    store.save_proposal(_proposal(side="sell"))
    recorder = BrokerRecorder(
        # Without is_configured=True the call stops at the credentials check
        # and never reaches the body this test claims to characterise.
        is_configured=True,
        assert_account_and_asset_ready={"account": {}, "asset": {}},
        get_latest_quote={
            "price": 100.0, "price_decimal": "100.00",
            "bid": 99.99, "ask": 100.01,
            "bid_decimal": "99.99", "ask_decimal": "100.01",
            "timestamp": NOW_ET,  # broker returns a datetime, not a string
        },
    )
    held = _held_portfolio()
    before = observable_state(store, "p-1")
    with patched_broker(recorder):
        outcome = validate_proposal_for_execution(
            "p-1", held, load_policy(), store, now_et=NOW_ET
        )
    # Freeze that it reached the body rather than an early refusal -- an
    # early return makes a purity claim vacuous.
    assert outcome.validation is not None, (
        f"validation returned early ({outcome.error}); this test would then "
        "prove nothing about the body's purity"
    )
    # Validation is documented as pure. Freeze that: no status change, no
    # reservation, no telemetry, no order rows.
    assert observable_state(store, "p-1") == before


# --------------------------------------------------------------------------
# 2. execute_approved_paper_proposal
# --------------------------------------------------------------------------


def test_wrong_confirmation_phrase_raises_before_any_broker_contact(store):
    store.save_proposal(_proposal(status="approved"))
    recorder = BrokerRecorder()
    before = observable_state(store, "p-1")
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "yes please", _portfolio(), load_policy(), store, now_et=NOW_ET
            )
    # Exception IDENTITY, not just message -- callers branch on the type.
    assert type(caught.value) is ProposalExecutionError
    assert recorder.call_names == ()
    assert observable_state(store, "p-1") == before


def test_unknown_proposal_execution_raises_and_writes_nothing(store):
    recorder = BrokerRecorder()
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError):
            execute_approved_paper_proposal(
                "nope", "approve", _portfolio(), load_policy(), store, now_et=NOW_ET
            )
    assert recorder.call_names == ()


def test_kill_switch_blocks_execution_without_reaching_the_broker(store):
    # Must be a CLAIMABLE status. With status="approved" the call fails at
    # "could not be claimed" and never reaches the kill-switch check at all,
    # so the test would pass while the check was deleted (caught by mutation
    # testing this file against a disabled kill switch).
    store.save_proposal(_proposal(status="proposed"))
    # is_configured must be True or the call stops at "credentials are not
    # configured" -- the suite clears real credentials (tests/conftest.py).
    recorder = BrokerRecorder(is_configured=True)
    before = observable_state(store, "p-1")
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "approve", _portfolio(), load_policy(), store,
                now_et=NOW_ET, kill_switch_active=True,
            )
    assert "kill switch" in str(caught.value).lower(), (
        f"blocked for the wrong reason: {caught.value}"
    )
    assert "submit_market_order" not in recorder.call_names
    assert observable_state(store, "p-1")["broker_orders"] == before["broker_orders"]


def test_early_refusals_never_create_a_reservation(store):
    """These refusals happen BEFORE any budget is reserved.

    Named for what it actually proves. It does NOT prove that a reservation
    taken later is released -- that path is not yet characterised; see this
    module's coverage note.
    """
    for confirmation, kill in (("wrong", False), ("approve", True)):
        store.save_proposal(_proposal(f"p-{confirmation}-{kill}", status="approved"))
        recorder = BrokerRecorder()
        with patched_broker(recorder):
            with pytest.raises(ProposalExecutionError):
                execute_approved_paper_proposal(
                    f"p-{confirmation}-{kill}", confirmation, _portfolio(),
                    load_policy(), store, now_et=NOW_ET, kill_switch_active=kill,
                )
        state = observable_state(store, f"p-{confirmation}-{kill}")
        assert state["reservations"] == [], (
            f"{confirmation}/{kill} left a reservation row behind; a refused "
            "execution must not hold budget"
        )


def test_successful_submission_freezes_call_order_state_and_evidence(store):
    """Characterise the ordinary path all four GR-1 seams participate in."""
    store.save_proposal(_proposal(side="sell"))
    accepted = {
        "order_id": "paper-success-1",
        "ticker": "AAPL",
        "shares": 1,
        "side": "sell",
        "type": "market",
        "status": "accepted",
    }
    recorder = _submission_recorder(submit=accepted)

    with patched_broker(recorder):
        result = execute_approved_paper_proposal(
            "p-1",
            "approve",
            _held_portfolio(),
            load_policy(),
            store,
            now_et=NOW_ET,
            earnings_days_away=10,
        )

    assert result == accepted
    assert recorder.call_names == (
        "is_configured",
        "assert_account_and_asset_ready",
        "get_latest_quote",
        "submit_market_order",
    )
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "broker_accepted"
    assert len(state["reservations"]) == 1
    assert state["broker_orders"] == [
        {
            "order_id": "paper-success-1",
            "proposal_id": "p-1",
            "status": "accepted",
        }
    ]
    assert state["order_events"] == ["submission_response"]
    assert state["telemetry"] == ["validation_approved", "submission_started"]


def test_pre_submit_telemetry_failure_releases_budget_without_broker_contact(
    store, monkeypatch
):
    """Freeze the after-reservation failure path GR-1 is most likely to lose."""
    store.save_proposal(_proposal(side="sell"))
    recorder = _submission_recorder(
        submit={
            "order_id": "must-not-submit",
            "ticker": "AAPL",
            "shares": 1,
            "side": "sell",
            "type": "market",
            "status": "accepted",
        }
    )

    def fail_submission_telemetry(*args, **kwargs):
        raise RuntimeError("characterized telemetry failure")

    monkeypatch.setattr(
        execution_service, "record_submission_started", fail_submission_telemetry
    )
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1",
                "approve",
                _held_portfolio(),
                load_policy(),
                store,
                now_et=NOW_ET,
                earnings_days_away=10,
            )

    assert "telemetry failed before broker submission" in str(caught.value).lower()
    assert "submit_market_order" not in recorder.call_names
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "submission_failed"
    assert state["reservations"] == []
    assert state["broker_orders"] == []
    assert state["order_events"] == []
    assert state["telemetry"] == ["validation_approved"]


def test_timeout_reconciles_by_idempotency_key_without_resubmitting(store):
    """An ambiguous submit must query the broker and never issue a blind retry."""
    store.save_proposal(_proposal(side="sell"))
    reconciled = {
        "order_id": "paper-reconciled-1",
        "ticker": "AAPL",
        "shares": 1,
        "side": "sell",
        "type": "market",
        "limit_price": None,
        "status": "accepted",
    }
    recorder = _submission_recorder(
        submit=TimeoutError("response lost after submission"),
        lookup=reconciled,
    )

    with patched_broker(recorder):
        result = execute_approved_paper_proposal(
            "p-1",
            "approve",
            _held_portfolio(),
            load_policy(),
            store,
            now_et=NOW_ET,
            earnings_days_away=10,
        )

    assert result == reconciled
    assert recorder.call_names == (
        "is_configured",
        "assert_account_and_asset_ready",
        "get_latest_quote",
        "submit_market_order",
        "find_order_by_client_id",
    )
    assert recorder.call_names.count("submit_market_order") == 1
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "broker_accepted"
    assert len(state["reservations"]) == 1
    assert state["order_events"] == ["submission_reconciled"]
    assert state["telemetry"] == ["validation_approved", "submission_started"]


# --------------------------------------------------------------------------
# 3-5. reconciliation and recovery entry points
# --------------------------------------------------------------------------


def test_reconcile_submission_on_unknown_proposal_is_defined_behaviour(store):
    recorder = BrokerRecorder()
    before = observable_state(store, "missing")
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            reconcile_submission("missing", store)
    assert type(caught.value) is ProposalExecutionError
    assert str(caught.value) == "Unknown proposal: missing"
    assert observable_state(store, "missing") == before
    assert recorder.call_names == ()


def test_manual_reconciliation_freezes_lookup_state_and_held_reservation(store):
    store.save_proposal(_proposal(status="submission_unknown", side="sell"))
    store.reserve_execution_budget(
        "p-1",
        trading_day="2026-08-03",
        notional="100.00",
        max_daily_notional="1000.00",
        max_daily_orders=5,
    )
    accepted = {
        "order_id": "paper-manual-reconcile-1",
        "ticker": "AAPL",
        "shares": 1,
        "side": "sell",
        "type": "market",
        "limit_price": None,
        "status": "accepted",
    }
    recorder = BrokerRecorder(find_order_by_client_id=accepted)

    with patched_broker(recorder):
        result = reconcile_submission("p-1", store)

    assert result == accepted
    assert recorder.call_names == ("find_order_by_client_id",)
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "broker_accepted"
    assert len(state["reservations"]) == 1
    assert state["order_events"] == ["manual_reconciliation"]
    assert state["telemetry"] == []


def test_recovery_refuses_a_proposal_that_is_not_actually_stranded(store):
    """Recovery must not "recover" something that was never stuck.

    Both entry points raise rather than returning a report when the
    proposal is in the wrong status or was claimed too recently. Freezing
    the refusal matters more than freezing a return shape: a recovery path
    that quietly acted on a healthy in-flight proposal could release a
    reservation or reset a status underneath a live submission.
    """
    store.save_proposal(_proposal(status="approved"))
    recorder = BrokerRecorder(find_order_by_client_id=None)
    before = observable_state(store, "p-1")

    with patched_broker(recorder):
        for entry in (recover_stale_reconciliation, recover_stale_claim):
            with pytest.raises(ProposalExecutionError) as caught:
                entry("p-1", store)
            assert type(caught.value) is ProposalExecutionError, entry.__name__

    after = observable_state(store, "p-1")
    # Refusing must be completely inert.
    assert after == before
    assert recorder.call_names == ()


def test_recovery_on_an_unknown_proposal_also_refuses(store):
    recorder = BrokerRecorder()
    with patched_broker(recorder):
        for entry in (recover_stale_reconciliation, recover_stale_claim):
            with pytest.raises(ProposalExecutionError):
                entry("no-such-proposal", store)
    assert recorder.call_names == ()


def _make_proposal_stale(store: AssistantStore, proposal_id: str) -> None:
    with store._connect() as connection:
        connection.execute(
            "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
            ("2000-01-01T00:00:00+00:00", proposal_id),
        )


def test_stale_pre_broker_claim_recovery_is_atomic_and_never_contacts_broker(store):
    store.save_proposal(_proposal(status="validating"))
    _make_proposal_stale(store, "p-1")
    recorder = BrokerRecorder()

    with patched_broker(recorder):
        recovered = recover_stale_claim("p-1", store, stale_after_seconds=1)

    assert recovered["status"] == "validation_failed"
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "validation_failed"
    assert state["reservations"] == []
    assert state["broker_orders"] == []
    assert state["order_events"] == []
    assert state["telemetry"] == []
    assert recorder.call_names == ()


def test_stale_reconciliation_recovery_preserves_ambiguous_budget_hold(store):
    store.save_proposal(_proposal(status="reconciling", side="sell"))
    store.reserve_execution_budget(
        "p-1",
        trading_day="2026-08-03",
        notional="100.00",
        max_daily_notional="1000.00",
        max_daily_orders=5,
    )
    _make_proposal_stale(store, "p-1")
    recorder = BrokerRecorder()

    with patched_broker(recorder):
        recovered = recover_stale_reconciliation(
            "p-1", store, stale_after_seconds=1
        )

    assert recovered["status"] == "submission_unknown"
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "submission_unknown"
    # A crashed local reconciler proves nothing about broker acceptance.
    # Keep the budget held until an actual broker lookup resolves it.
    assert len(state["reservations"]) == 1
    assert state["broker_orders"] == []
    assert state["order_events"] == []
    assert state["telemetry"] == []
    assert recorder.call_names == ()


# --------------------------------------------------------------------------
# structural facts GR-1 must preserve
# --------------------------------------------------------------------------


def test_the_five_public_entry_points_remain_importable_from_execution_service():
    """GR-1's facade requirement: 21 test files import these by this path."""
    for name in (
        "validate_proposal_for_execution",
        "execute_approved_paper_proposal",
        "reconcile_submission",
        "recover_stale_reconciliation",
        "recover_stale_claim",
    ):
        assert callable(getattr(execution_service, name)), name


def test_the_atomic_claim_is_still_a_single_conditional_update():
    """GR-1 section 6.2 hard requirement.

    Splitting the claim into read-then-write across a module boundary would
    reintroduce the race claim_proposal() exists to close. The claim lives in
    AssistantStore and must stay there; a kernel module may orchestrate the
    claim phase but must not reimplement the update.
    """
    import inspect

    source = inspect.getsource(AssistantStore.claim_proposal)
    updates = source.count("UPDATE trade_proposals SET status")
    assert updates == 1, (
        f"claim_proposal() issues {updates} UPDATE statements; the atomic claim "
        "must remain exactly one conditional UPDATE"
    )
    assert (
        "WHERE proposal_id = ? AND status IN ({placeholders})" in source
    ), "the claiming UPDATE must retain both identity and expected-status guards"
    assert 'query += " AND expires_at >= ?"' in source
    assert "self.get_proposal(" not in source, (
        "claim_proposal() must not perform an out-of-transaction application-level read"
    )
    begin = source.index('connection.execute("BEGIN IMMEDIATE")')
    update = source.index("cursor = connection.execute(query, params)")
    commit = source.index("connection.commit()")
    assert begin < update < commit, (
        "the conditional UPDATE must execute after BEGIN IMMEDIATE and before commit"
    )


# --------------------------------------------------------------------------
# gaps found by mutation-testing the suite itself (2026-08-02)
# --------------------------------------------------------------------------


def test_submission_carries_the_proposals_exact_idempotency_key(store):
    """Nothing asserted the key's VALUE, only that submission happened.

    Verified by mutation: replacing `idempotency_key=proposal[...]` with
    `idempotency_key=None` at the submit call left the whole suite green.
    That key is the only thing preventing a retry from becoming a second
    real order, so its value -- not merely its presence -- must be frozen.
    """
    store.save_proposal(_proposal(side="sell"))
    recorder = _submission_recorder(
        submit={
            "order_id": "order-1",
            "ticker": "AAPL",
            "shares": 1,
            "side": "sell",
            "type": "market",
            "status": "accepted",
        }
    )
    with patched_broker(recorder):
        execute_approved_paper_proposal(
            "p-1", "approve", _held_portfolio(), load_policy(), store,
            now_et=NOW_ET, earnings_days_away=10,
        )

    submits = [call for call in recorder.calls if call[0] == "submit_market_order"]
    assert len(submits) == 1, recorder.call_names
    _, args, kwargs = submits[0]
    assert kwargs.get("idempotency_key") == "idem-p-1", (
        f"submission did not carry the proposal's idempotency key: {kwargs}"
    )


def test_an_unsupported_order_type_blocks_and_releases_its_reservation(store):
    """The 2026-07-29 fail-closed branch, previously uncharacterised.

    execution_gate.validate_trade_intent() approves order_type="stop"; it is
    a lower layer with no view of policy. The dispatch refuses rather than
    silently downgrading a stop to a MARKET order -- an unbounded-price
    order where a bounded one was intended -- and must release the budget it
    had already reserved. Verified by mutation: deleting that
    release_execution_reservation() call left the suite green before this
    test existed.

    Reaching the branch requires a policy that permits "stop", which
    TradingPolicy.__post_init__ rejects. Constructing it through
    object.__setattr__ is deliberate: it reproduces exactly the layer
    disagreement the branch was added to survive.
    """
    policy = load_policy()
    object.__setattr__(
        policy, "allowed_order_types", tuple(policy.allowed_order_types) + ("stop",)
    )
    # The proposal must carry the MUTATED policy's fingerprint, or the call
    # stops at the fingerprint check and never reaches the dispatch.
    store.save_proposal(
        _proposal(
            side="sell",
            intent_overrides={"order_type": "stop"},
            policy_fingerprint=compute_policy_fingerprint(policy),
        )
    )
    recorder = _submission_recorder(submit={"order_id": "must-not-exist"})

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "approve", _held_portfolio(), policy, store,
                now_et=NOW_ET, earnings_days_away=10,
            )

    assert "order_type" in str(caught.value)
    state = observable_state(store, "p-1")
    assert state["reservations"] == [], (
        "an unsupported order type left budget reserved with no order to release it"
    )
    assert "submit_market_order" not in recorder.call_names
    assert "submit_limit_order" not in recorder.call_names


# --------------------------------------------------------------------------
# the third release path: reconcile_submission's confirmed-absence branch
# --------------------------------------------------------------------------


def _unresolved_with_reservation(store, *, updated_at: str) -> None:
    """A proposal stuck in submission_unknown, holding reserved budget.

    `updated_at` is what claim_proposal() hands to
    _broker_absence_is_old_enough() as `_claimed_from_updated_at`, so it is
    the only thing deciding whether a 404 is trusted.
    """
    store.save_proposal(_proposal(side="sell", status=SUBMISSION_UNKNOWN))
    store.reserve_execution_budget(
        "p-1",
        trading_day="2026-08-03",
        notional="100.00",
        max_daily_notional="1000000.00",
        max_daily_orders=100,
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
            (updated_at, "p-1"),
        )


def test_a_confirmed_absent_order_releases_budget_only_after_the_grace_period(store):
    """The third release path -- `mark_submission_failed_and_release`.

    A 404 from the broker is not proof the order never existed: the broker
    may simply not have indexed it yet. Only once BROKER_ABSENCE_GRACE_SECONDS
    has elapsed is absence trusted, and only then is the reserved budget
    released. Freezing both halves, because releasing too early frees capital
    against an order that may still be live.
    """
    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=BROKER_ABSENCE_GRACE_SECONDS + 60)).isoformat()
    _unresolved_with_reservation(store, updated_at=old)
    recorder = BrokerRecorder(is_configured=True, find_order_by_client_id=None)

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            reconcile_submission("p-1", store)

    assert "never accepted" in str(caught.value)
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == SUBMISSION_FAILED
    assert state["reservations"] == [], (
        "confirmed absence past the grace period must release the reservation"
    )


def test_a_fresh_absent_order_keeps_the_budget_held(store):
    """The safety half: a recent 404 must NOT be trusted as absence."""
    recent = datetime.now(timezone.utc).isoformat()
    _unresolved_with_reservation(store, updated_at=recent)
    recorder = BrokerRecorder(is_configured=True, find_order_by_client_id=None)

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            reconcile_submission("p-1", store)

    assert "grace period has not elapsed" in str(caught.value)
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == SUBMISSION_UNKNOWN
    assert state["reservations"] != [], (
        "a 404 inside the grace period must keep the budget held; releasing it "
        "would free capital against an order that may still be live"
    )
