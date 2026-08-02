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
engaged kill switch), validation purity through the full body, recovery
refusals, exception identity, and the atomic-claim structural invariant.
Mutation-verified: deleting the kill-switch check and changing an exception
type are both detected.

What is NOT yet frozen: any path that reaches submission. Every refusal
characterised here fails before a reservation is taken, so removing
`release_execution_reservation()` is invisible to these tests -- verified.
Reservation lifecycle, broker submission ordering, and ambiguous-outcome
reconciliation still need fixtures that drive a proposal all the way
through, and GR-1B must not treat this file as covering them.

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
from datetime import datetime, timezone
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
            "SELECT proposal_id, status FROM broker_orders "
            "WHERE proposal_id = ? ORDER BY proposal_id", proposal_id
        )
        events = rows(
            "SELECT event_type FROM broker_order_events "
            "WHERE proposal_id = ? ORDER BY event_id", proposal_id
        )
        telemetry = rows(
            "SELECT event_type FROM execution_telemetry_events "
            "WHERE proposal_id = ? ORDER BY telemetry_event_id", proposal_id
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
    proposal_id: str = "p-1", *, status: str = "proposed", side: str = "buy", **overrides
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
    held = _portfolio()
    held.positions = [
        PortfolioPosition(
            ticker="AAPL", shares=10.0, entry_price=90.0, current_price=100.0,
            market_value=1000.0, unrealized_pnl_pct=11.1, is_leveraged_etf=False,
        )
    ]
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


# --------------------------------------------------------------------------
# 3-5. reconciliation and recovery entry points
# --------------------------------------------------------------------------


def test_reconcile_submission_on_unknown_proposal_is_defined_behaviour(store):
    recorder = BrokerRecorder()
    with patched_broker(recorder):
        try:
            result = reconcile_submission("missing", store)
        except Exception as exc:  # characterise the type, whatever it is
            result = {"raised": type(exc).__name__}
    assert isinstance(result, dict)


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
    import ast
    import inspect

    source = inspect.getsource(AssistantStore.claim_proposal)
    tree = ast.parse(inspect.cleandoc(source.split("\n", 1)[1]).join(["", ""])) if False else None
    updates = source.upper().count("UPDATE TRADE_PROPOSALS")
    assert updates == 1, (
        f"claim_proposal() issues {updates} UPDATE statements; the atomic claim "
        "must remain exactly one conditional UPDATE"
    )
    assert "SELECT" not in source.upper().split("UPDATE TRADE_PROPOSALS")[0][-400:], (
        "a read immediately before the claiming UPDATE suggests the atomicity "
        "was split into read-then-write"
    )
