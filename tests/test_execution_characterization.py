"""GR-1A: freeze the execution service's OBSERVABLE behaviour before splitting it.

`assistant/execution_service.py` was 2,040 lines at the GR-1A freeze and
GR-1 splits it into
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
engaged kill switch), validation read-only behavior (reads state and
queries the broker, writes nothing) through the full body, ordinary
submission call ordering and persisted evidence, reservation release after a
pre-submit telemetry failure, timeout reconciliation without resubmission,
manual reconciliation, successful and refused recovery, exception identity,
the atomic-claim structural invariant, and simultaneous claim contention.
Mutation-verified: deleting the kill-switch check and changing an exception
type are both detected.

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
import dataclasses
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
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
    BLOCKED,
    BROKER_ABSENCE_GRACE_SECONDS,
    SUBMISSION_FAILED,
    SUBMISSION_UNKNOWN,
)
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent

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


def test_validate_is_read_only_on_a_real_proposal(store):
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
    # early return makes a read-only-state claim vacuous.
    assert outcome.validation is not None, (
        f"validation returned early ({outcome.error}); this test would then "
        "prove nothing about the body's read-only state contract"
    )
    # Validation may perform store and broker reads. Freeze the actual
    # contract: no status change, reservation, telemetry, or order rows.
    assert observable_state(store, "p-1") == before


def _validation_recorder() -> BrokerRecorder:
    """Broker behaviours that let validation reach validate_trade_intent."""
    return BrokerRecorder(
        is_configured=True,
        assert_account_and_asset_ready={"account": {}, "asset": {}},
        get_latest_quote={
            "price": 100.0, "price_decimal": "100.00",
            "bid": 99.99, "ask": 100.01,
            "bid_decimal": "99.99", "ask_decimal": "100.01",
            "timestamp": NOW_ET,
        },
    )


def test_gr1c_patching_validate_trade_intent_on_the_facade_reaches_the_kernel(
    store, monkeypatch
):
    """THE seam that kept validation on the facade through GR-1B.

    tests/test_personal_assistant.py patches
    ``execution_service.validate_trade_intent`` to simulate an unexpected
    gate failure. GR-1C moved the orchestration into
    assistant/execution_kernel/validate.py behind explicit dependency
    injection, and this test freezes the contract that made the move safe:
    the facade builds the deps AT CALL TIME from its own namespace, so a
    patch on the facade name must still be the callable the kernel invokes.
    A future edit that resolves validate_trade_intent inside the kernel, or
    hoists the deps construction to import time, fails here.
    """
    from risk.execution_gate import ValidationResult

    store.save_proposal(_proposal(side="sell"))
    seen: list = []

    def sentinel_gate(intent, portfolio, reference_price, **kwargs):
        seen.append(intent)
        return ValidationResult(
            approved=False,
            violations=("SENTINEL: the patched gate ran",),
            violation_codes=("sentinel",),
        )

    monkeypatch.setattr(execution_service, "validate_trade_intent", sentinel_gate)
    with patched_broker(_validation_recorder()):
        outcome = validate_proposal_for_execution(
            "p-1", _held_portfolio(), load_policy(), store, now_et=NOW_ET
        )
    assert outcome.error is None, outcome.error
    assert outcome.validation.violations == ("SENTINEL: the patched gate ran",), (
        "the kernel consulted a validate_trade_intent other than the one "
        "patched onto the facade -- the injection seam is broken"
    )
    assert seen and seen[0].ticker == "AAPL"


def test_gr1c_every_injected_seam_resolves_from_the_facade_at_call_time(
    store, monkeypatch
):
    """Each remaining ProposalValidationDeps field, frozen one at a time.

    For every injected seam: patch the facade name, call the unchanged
    public entry point, and require the seam-specific observable that only
    the PATCHED callable can produce. Any kernel-side import of one of
    these names (or an import-time deps cache) breaks exactly one context
    below, naming the regressed seam.
    """
    from risk.execution_gate import ValidationResult

    # env_kill_switch_active -- checked after broker configuration, so the
    # broker recorder must let validation get that far.
    store.save_proposal(_proposal("p-env", side="sell"))
    with monkeypatch.context() as patch:
        patch.setattr(execution_service, "env_kill_switch_active", lambda: True)
        with patched_broker(_validation_recorder()):
            outcome = validate_proposal_for_execution(
                "p-env", _held_portfolio(), load_policy(), store, now_et=NOW_ET
            )
        assert "kill switch is active" in str(outcome.error), outcome.error

    # compute_policy_fingerprint -- checked before the broker import.
    store.save_proposal(_proposal("p-fp", side="sell"))
    with monkeypatch.context() as patch:
        patch.setattr(
            execution_service, "compute_policy_fingerprint", lambda policy: "0" * 64
        )
        outcome = validate_proposal_for_execution(
            "p-fp", _held_portfolio(), load_policy(), store, now_et=NOW_ET
        )
        assert "policy fingerprint does not match" in str(outcome.error), outcome.error

    # _validate_proposal_context -- feature-specific durable bindings are
    # checked after the universal policy fingerprint and before broker I/O.
    store.save_proposal(_proposal("p-context", side="sell"))
    with monkeypatch.context() as patch:
        patch.setattr(
            execution_service,
            "_validate_proposal_context",
            lambda proposal: "SENTINEL-context",
        )
        outcome = validate_proposal_for_execution(
            "p-context", _held_portfolio(), load_policy(), store, now_et=NOW_ET
        )
        assert outcome.error == "SENTINEL-context"
        assert outcome.failure_class == execution_service.FAILURE_DATA_INTEGRITY

    # _intent_from_dict -- parses the stored intent after the broker checks.
    store.save_proposal(_proposal("p-intent", side="sell"))
    with monkeypatch.context() as patch:
        def broken_intent(raw):
            raise ValueError("SENTINEL-intent")

        patch.setattr(execution_service, "_intent_from_dict", broken_intent)
        with patched_broker(_validation_recorder()):
            outcome = validate_proposal_for_execution(
                "p-intent", _held_portfolio(), load_policy(), store, now_et=NOW_ET
            )
        assert "Malformed stored intent: SENTINEL-intent" in str(outcome.error)

    # detect_split_like_share_mismatch -- a newly added corporate-action
    # refusal must retain GR-1C's call-time facade seam like every other
    # runtime collaborator in the moved validation body.
    split_proposal = _proposal("p-split-seam", side="sell")
    split_proposal["expected_impact"] = {"position_shares_before": "10"}
    store.save_proposal(split_proposal)
    with monkeypatch.context() as patch:
        patch.setattr(
            execution_service,
            "detect_split_like_share_mismatch",
            lambda recorded, current: {
                "ratio": "SENTINEL",
                "direction": "forward",
            },
        )
        with patched_broker(_validation_recorder()):
            outcome = validate_proposal_for_execution(
                "p-split-seam",
                _held_portfolio(),
                load_policy(),
                store,
                now_et=NOW_ET,
            )
        assert "suspected SENTINEL forward split" in str(outcome.error)

    # _pending_buy_value_by_ticker -- consulted only for buys; AAPL is held,
    # so the no-new-positions policy does not return early.
    store.save_proposal(_proposal("p-pending", side="buy"))
    with monkeypatch.context() as patch:
        def broken_pending(open_orders, broker):
            raise RuntimeError("SENTINEL-pending")

        patch.setattr(
            execution_service, "_pending_buy_value_by_ticker", broken_pending
        )
        with patched_broker(_validation_recorder()):
            outcome = validate_proposal_for_execution(
                "p-pending", _held_portfolio(), load_policy(), store, now_et=NOW_ET
            )
        assert "SENTINEL-pending" in str(outcome.error), outcome.error

    # _resolve_earnings_days_away -- its return value must be the one the
    # (also patched) gate receives, proving the resolver consulted is the
    # facade's, not one the kernel found in its own namespace.
    store.save_proposal(_proposal("p-earn", side="sell"))
    with monkeypatch.context() as patch:
        received: dict = {}

        def recording_gate(intent, portfolio, reference_price, **kwargs):
            received.update(kwargs)
            return ValidationResult(
                approved=False, violations=("stop",), violation_codes=("sentinel",)
            )

        patch.setattr(
            execution_service,
            "_resolve_earnings_days_away",
            lambda ticker, override: 77,
        )
        patch.setattr(execution_service, "validate_trade_intent", recording_gate)
        with patched_broker(_validation_recorder()):
            validate_proposal_for_execution(
                "p-earn", _held_portfolio(), load_policy(), store, now_et=NOW_ET
            )
        assert received.get("earnings_days_away") == 77, received

    # _import_execution_broker -- the deferred broker import is itself
    # injected, so a facade-level replacement must be what the kernel sees.
    store.save_proposal(_proposal("p-broker", side="sell"))
    with monkeypatch.context() as patch:
        class StubBroker:
            PAPER_TRADING = False

        patch.setattr(
            execution_service, "_import_execution_broker", lambda: StubBroker
        )
        outcome = validate_proposal_for_execution(
            "p-broker", _held_portfolio(), load_policy(), store, now_et=NOW_ET
        )
        assert "PAPER_TRADING must remain True" in str(outcome.error), outcome.error


def test_gr1c_runtime_constructors_resolve_from_the_facade_at_call_time(
    store, monkeypatch
):
    """The moved body used these public facade names at runtime too.

    Injecting only the named helper functions is not enough: open-order
    normalization constructed ``TradeIntent`` directly, and cumulative batch
    exposure called ``to_decimal`` directly. Moving those resolutions into
    the kernel would silently defeat the same facade monkeypatch contract that
    motivated GR-1C's dependency bundle.
    """
    from assistant.money import to_decimal as real_to_decimal
    from risk.execution_gate import TradeIntent as RealTradeIntent

    store.save_proposal(_proposal("p-runtime", side="buy"))
    portfolio = _held_portfolio()
    portfolio.open_orders = [
        {"ticker": "MSFT", "side": "sell", "shares": 1, "type": "market"}
    ]
    constructed: list[dict] = []
    converted: list[tuple] = []

    def recording_trade_intent(*args, **kwargs):
        constructed.append(dict(kwargs))
        return RealTradeIntent(*args, **kwargs)

    def recording_to_decimal(value, **kwargs):
        converted.append((value, dict(kwargs)))
        return real_to_decimal(value, **kwargs)

    monkeypatch.setattr(execution_service, "TradeIntent", recording_trade_intent)
    monkeypatch.setattr(execution_service, "to_decimal", recording_to_decimal)
    with patched_broker(_validation_recorder()):
        outcome = validate_proposal_for_execution(
            "p-runtime",
            portfolio,
            load_policy(),
            store,
            now_et=NOW_ET,
            earnings_days_away=10,
            extra_pending_buy_value_by_ticker={"AAPL": 25.0},
        )

    assert outcome.validation is not None, outcome.error
    assert constructed and constructed[0]["ticker"] == "MSFT"
    assert converted and converted[0][0] == 25.0


def test_gr1c_validation_clock_still_resolves_from_the_facade(store, monkeypatch):
    """Callers could replace the facade clock before the body moved.

    Both expiration and the captured quote-receipt timestamp used that same
    name, so the dependency must cover every runtime clock read rather than
    only the first one encountered in the function.
    """
    real_datetime = datetime

    class FutureDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2099, 1, 1, tzinfo=timezone.utc)

        @classmethod
        def fromisoformat(cls, value):
            return real_datetime.fromisoformat(value)

    store.save_proposal(
        _proposal("p-clock", side="sell", expires_at="2090-01-01T00:00:00+00:00")
    )
    monkeypatch.setattr(execution_service, "datetime", FutureDateTime)

    outcome = validate_proposal_for_execution(
        "p-clock", _held_portfolio(), load_policy(), store, now_et=NOW_ET
    )

    assert outcome.error == "Proposal has expired."

    store.save_proposal(
        _proposal(
            "p-clock-quote",
            side="sell",
            expires_at="2100-01-01T00:00:00+00:00",
        )
    )
    with patched_broker(_validation_recorder()):
        outcome = validate_proposal_for_execution(
            "p-clock-quote",
            _held_portfolio(),
            load_policy(),
            store,
            now_et=NOW_ET,
            earnings_days_away=10,
        )

    assert outcome.validation is not None, outcome.error
    assert str(outcome.quote_received_at).startswith("2099-01-01T00:00:00")


def test_gr1c_outcome_construction_still_resolves_from_the_facade(
    store, monkeypatch
):
    """Moving the body must not bypass the facade's return-type seam."""
    from assistant import execution_service

    sentinel = object()
    constructions: list[dict] = []

    def recording_outcome(**kwargs):
        constructions.append(dict(kwargs))
        return sentinel

    monkeypatch.setattr(
        execution_service, "ProposalValidationOutcome", recording_outcome
    )

    outcome = execution_service.validate_proposal_for_execution(
        "missing-proposal",
        _held_portfolio(),
        load_policy(),
        store,
        now_et=NOW_ET,
    )

    assert outcome is sentinel
    assert constructions == [
        {
            "proposal": None,
            "intent": None,
            "validation": None,
            "error": "Unknown proposal: missing-proposal",
            "failure_class": execution_service.FAILURE_DATA_INTEGRITY,
        }
    ]


def test_gr1c_utc_source_still_resolves_from_the_facade(store, monkeypatch):
    """The moved body historically read both datetime and timezone there."""
    from assistant import execution_service

    real_datetime = datetime
    facade_utc = object()
    clock_arguments: list[object] = []

    class FacadeTimezone:
        utc = facade_utc

    class RecordingDateTime:
        @classmethod
        def now(cls, tz=None):
            clock_arguments.append(tz)
            return real_datetime(2099, 1, 1, tzinfo=timezone.utc)

        @classmethod
        def fromisoformat(cls, value):
            return real_datetime.fromisoformat(value)

    store.save_proposal(
        _proposal(
            "p-facade-utc",
            side="sell",
            expires_at="2090-01-01T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(execution_service, "datetime", RecordingDateTime)
    monkeypatch.setattr(execution_service, "timezone", FacadeTimezone)

    outcome = execution_service.validate_proposal_for_execution(
        "p-facade-utc",
        _held_portfolio(),
        load_policy(),
        store,
        now_et=NOW_ET,
    )

    assert outcome.error == "Proposal has expired."
    assert clock_arguments == [facade_utc]


def test_gr1c_failure_constants_still_resolve_from_the_facade(store, monkeypatch):
    """Failure classifications are behavioral collaborators, not decoration."""
    from assistant import execution_service

    facade_data_failure = "facade-data-integrity"
    facade_infrastructure_failure = "facade-infrastructure"
    monkeypatch.setattr(
        execution_service,
        "FAILURE_DATA_INTEGRITY",
        facade_data_failure,
    )
    monkeypatch.setattr(
        execution_service,
        "FAILURE_INFRASTRUCTURE",
        facade_infrastructure_failure,
    )

    outcome = execution_service.validate_proposal_for_execution(
        "missing-proposal",
        _held_portfolio(),
        load_policy(),
        store,
        now_et=NOW_ET,
    )
    assert outcome.failure_class == facade_data_failure

    store.save_proposal(
        _proposal(
            "p-facade-failure",
            side="sell",
            expires_at="2100-01-01T00:00:00+00:00",
        )
    )
    with patched_broker(BrokerRecorder(is_configured=False)):
        outcome = execution_service.validate_proposal_for_execution(
            "p-facade-failure",
            _held_portfolio(),
            load_policy(),
            store,
            now_et=NOW_ET,
        )

    assert outcome.failure_class == facade_infrastructure_failure


def test_gr1c_the_kernel_body_reads_no_module_globals():
    """Structural guard behind the whole GR-1C seam family.

    The behavioural tests above each freeze one seam. This pins the boundary
    itself: run_proposal_validation() may not read any module-scope runtime
    name; every collaborator must arrive through ProposalValidationDeps. A
    symbol-table test is used because it follows Python's actual lexical
    scopes (including comprehensions and nested blocks) and still detects a
    module global that shadows a builtin. Runtime behavior cannot observe the
    distinction when the kernel and facade imports happen to point at the
    same object.
    """
    import builtins
    from pathlib import Path
    import symtable

    source_path = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "execution_kernel" / "validate.py"
    )
    source = source_path.read_text(encoding="utf-8")
    module_table = symtable.symtable(source, str(source_path), "exec")
    function_table = next(
        table
        for table in module_table.get_children()
        if table.get_name() == "run_proposal_validation"
    )

    module_bindings = {
        symbol.get_name()
        for symbol in module_table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }

    def runtime_module_reads(table) -> set[str]:
        reads = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_global()
            and symbol.is_referenced()
            and (
                symbol.get_name() in module_bindings
                or not hasattr(builtins, symbol.get_name())
            )
        }
        for child in table.get_children():
            reads.update(runtime_module_reads(child))
        return reads

    module_reads = runtime_module_reads(function_table)
    assert not module_reads, (
        "run_proposal_validation() reads module-scope runtime names instead "
        f"of ProposalValidationDeps: {sorted(module_reads)}"
    )


def test_gr1c_resolved_failure_class_fallbacks_are_class_resolved(monkeypatch):
    """Pins the one deliberate residual of the injection boundary.

    ProposalValidationOutcome.resolved_failure_class resolves its
    FAILURE_NONE / FAILURE_DETERMINISTIC_POLICY fallbacks from the KERNEL's
    namespace at property-access time. Pre-GR-1C the class lived on the
    facade, so patching either facade constant changed this property's
    output; post-extraction it does not. That IS a facade-seam difference,
    accepted deliberately: injecting the fallbacks would change the frozen
    dataclass's public field set (a larger compatibility break), and
    resolving them from the facade would invert the kernel->facade
    dependency direction GR-1 forbids. This test makes the boundary an
    explicit decision -- if it starts failing, someone moved the boundary
    and must update the ProposalValidationDeps/property docstrings to match.
    """
    from assistant import execution_service
    from assistant.execution_kernel import validate as kernel_validate
    from assistant.execution_telemetry import (
        FAILURE_DETERMINISTIC_POLICY,
        FAILURE_NONE,
    )

    errored = execution_service.ProposalValidationOutcome(
        proposal=None, intent=None, validation=None, error="boom"
    )
    clean = execution_service.ProposalValidationOutcome(
        proposal=None, intent=None, validation=None, error=None
    )

    # A facade-level patch of either constant must NOT reach the property...
    monkeypatch.setattr(
        execution_service, "FAILURE_DETERMINISTIC_POLICY", "facade-patched-dp"
    )
    monkeypatch.setattr(execution_service, "FAILURE_NONE", "facade-patched-none")
    assert errored.resolved_failure_class == FAILURE_DETERMINISTIC_POLICY
    assert clean.resolved_failure_class == FAILURE_NONE

    # ...because the property resolves from the kernel module, where a patch
    # DOES reach. (This direction proves the test observes real resolution
    # rather than passing vacuously against constants that equal each other.)
    monkeypatch.setattr(
        kernel_validate, "FAILURE_DETERMINISTIC_POLICY", "kernel-patched-dp"
    )
    monkeypatch.setattr(kernel_validate, "FAILURE_NONE", "kernel-patched-none")
    assert errored.resolved_failure_class == "kernel-patched-dp"
    assert clean.resolved_failure_class == "kernel-patched-none"


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


def test_a_neutered_release_helper_still_never_submits_to_the_broker(
    store, monkeypatch
):
    """The fail-closed guard behind the telemetry-failure path.

    ``release_after_telemetry_failure`` is ``NoReturn``, but submission safety
    must not depend solely on that helper contract. The old call site said
    nothing equivalent to "if this returns, stop anyway." This test neuters
    the helper into a plain return and proves the facade STILL refuses to
    submit an order, because a bare ``raise`` guard re-raises the telemetry
    failure.

    GR-1B self-audit finding, 2026-08-02: without the guard, this exact
    scenario fell through to the broker submit. Mutation-verified by deleting
    the guard and watching this test observe a submitted order.
    """
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
    # The dangerous future edit, simulated: the helper gains a return path.
    monkeypatch.setattr(
        execution_service,
        "release_after_telemetry_failure",
        lambda *args, **kwargs: None,
    )

    with patched_broker(recorder):
        with pytest.raises(RuntimeError) as caught:
            execute_approved_paper_proposal(
                "p-1",
                "approve",
                _held_portfolio(),
                load_policy(),
                store,
                now_et=NOW_ET,
                earnings_days_away=10,
            )

    assert "characterized telemetry failure" in str(caught.value)
    assert "submit_market_order" not in recorder.call_names, (
        "a telemetry failure must never fall through to a live order "
        "submission, even if the release helper stops raising"
    )
    assert observable_state(store, "p-1")["broker_orders"] == []


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


def test_simultaneous_claim_attempts_have_exactly_one_winner(store):
    """Exercise the storage guarantee under real writer contention.

    Older tests described two back-to-back calls as "concurrent". Those prove
    the status guard, but they cannot detect a refactor that stops acquiring
    the SQLite write lock before its claim checks. A barrier makes four worker
    threads enter the claim together; every call opens its own connection.
    """
    store.save_proposal(_proposal())
    contender_count = 4
    start = Barrier(contender_count)

    def claim(_: int):
        start.wait(timeout=10)
        return store.claim_proposal("p-1")

    with ThreadPoolExecutor(max_workers=contender_count) as executor:
        results = list(executor.map(claim, range(contender_count)))

    winners = [result for result in results if result is not None]
    assert len(winners) == 1, (
        f"expected exactly one claim winner under contention, got {len(winners)}"
    )
    assert winners[0]["status"] == "validating"
    assert store.get_proposal("p-1")["status"] == "validating"


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


def test_a_failed_lookup_is_never_treated_as_confirmed_absence(store):
    """The three-state contract `_lookup_order_outcome` exists to protect.

    "The broker says no such order" and "we could not ask the broker" are
    different answers. Collapsing them means a network failure is read as
    durable proof the order never existed -- releasing reserved budget and
    marking submission_failed for an order that may be live at the broker.

    Found by mutation: returning None instead of LOOKUP_UNCONFIRMED left the
    whole suite green, including the grace-period tests, because those only
    exercise the confirmed-absence branch.
    """
    old = (
        datetime.now(timezone.utc)
        - timedelta(seconds=BROKER_ABSENCE_GRACE_SECONDS + 60)
    ).isoformat()
    _unresolved_with_reservation(store, updated_at=old)

    # The lookup itself fails -- not a 404.
    recorder = BrokerRecorder(
        is_configured=True,
        find_order_by_client_id=ConnectionError("broker unreachable"),
    )
    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            reconcile_submission("p-1", store)

    assert "lookup" in str(caught.value).lower(), caught.value
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == SUBMISSION_UNKNOWN, (
        "a failed lookup must leave the proposal unresolved, not failed"
    )
    assert state["reservations"] != [], (
        "a failed lookup must keep the budget held -- releasing it would free "
        "capital against an order that may still exist at the broker"
    )


def test_the_override_review_digest_binds_to_the_exact_reviewed_violations():
    """The control that stops an override becoming blanket permission.

    `override_policy_violations=True` is only honoured when the CURRENT
    violations match a previously stored reviewed-override record, and
    `_review_digest` is what "match" means. A digest that ignores its inputs
    makes any override-eligible condition match any prior review -- exactly
    the vulnerability the 2026-07-30 review closed, where an override could
    accept whatever conditions happened to exist at the later execution
    instant rather than the ones a human actually saw.

    Found by mutation while extracting the kernel: returning a constant from
    `_review_digest` left the entire suite green.
    """
    from assistant.execution_service import _review_digest

    intent = TradeIntent(ticker="AAPL", side="sell", shares=1, order_type="market")
    base = _review_digest(intent, ("max_position_pct",), ("AAPL is 30% of the book.",))

    # Same inputs, any ordering -> same digest (no spurious mismatch).
    assert base == _review_digest(
        intent, ("max_position_pct",), ("AAPL is 30% of the book.",)
    )
    # A DIFFERENT violation code must not reuse a prior review.
    assert base != _review_digest(
        intent, ("earnings_blackout",), ("AAPL is 30% of the book.",)
    )
    # Same code, materially different severity in the message, must differ --
    # "slightly over the cap" is not the reviewed risk of "dramatically over".
    assert base != _review_digest(
        intent, ("max_position_pct",), ("AAPL is 80% of the book.",)
    )
    # An additional violation the human never saw must not match.
    assert base != _review_digest(
        intent,
        ("max_position_pct", "earnings_blackout"),
        ("AAPL is 30% of the book.", "Earnings in 2 days."),
    )
    # A different trade entirely must not match.
    assert base != _review_digest(
        TradeIntent(ticker="MSFT", side="sell", shares=1, order_type="market"),
        ("max_position_pct",),
        ("AAPL is 30% of the book.",),
    )


def test_a_budget_refusal_fences_the_proposal_out_of_submitting(store):
    """A refused reservation must not leave the row looking submitted.

    `submitting` means "this may have reached the broker" -- it is the
    status recovery treats as ambiguous and reconciles rather than
    retries. A proposal refused by the daily budget provably never
    contacted the broker, so leaving it in `submitting` would manufacture
    a false ambiguity: reconciliation would go looking for an order that
    cannot exist, and the ticker/side slot would stay occupied.

    The transition is fenced (conditional on still owning the claim)
    rather than a plain write, so stale-claim recovery cannot be clobbered
    by a worker that was merely paused.

    Mutation result, GR-1B: dropping the fenced transition and raising
    directly left the execution suite green -- the raise still happened,
    only the status was wrong. Uncovered until this test.
    """
    # A policy that permits zero orders today: the reservation is refused
    # by the persistent daily cap, after the SUBMITTING fence is written.
    # The proposal must be bound to THIS policy's fingerprint, or execution
    # refuses at the policy-binding gate long before the budget is touched.
    exhausted = dataclasses.replace(load_policy(), max_daily_order_count=0)
    store.save_proposal(
        _proposal(
            side="sell",
            policy_version=exhausted.version,
            policy_fingerprint=compute_policy_fingerprint(exhausted),
        )
    )
    recorder = _submission_recorder(submit={"order_id": "must-not-submit"})

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "approve", _held_portfolio(), exhausted, store,
                now_et=NOW_ET, earnings_days_away=10,
            )

    assert "budget" in str(caught.value).lower(), caught.value
    assert "submit_market_order" not in recorder.call_names, (
        "a budget refusal happens before the broker is contacted"
    )
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == BLOCKED, (
        "left in a status that would make recovery hunt for an order that "
        "was never sent"
    )
    assert state["reservations"] == []
    assert state["broker_orders"] == []


def test_the_persistent_kill_switch_blocks_execution_on_its_own(store):
    """The switch an OPERATOR actually engages, with no caller cooperation.

    test_kill_switch_blocks_execution_without_reaching_the_broker passes
    `kill_switch_active=True`, so it only proves the caller's own flag is
    honoured. The persistent switch lives in the store and is what an
    operator flips to stop the platform -- including the one this service
    sets itself on a mismatched order. A caller that passes nothing, or
    passes False, must still be stopped.

    Mutation result, GR-1B. The switch is resolved at TWO sites: the
    pre-claim gate in execution_kernel/claim.py and, authoritatively,
    inside validate_proposal_for_execution(). Reducing either one alone to
    `return caller_flag` is survivable BY DESIGN -- the other still
    refuses -- so a single-site mutation proves nothing here. Removing the
    persistent and environment switches from BOTH sites was undetected by
    this suite until this test existed; it is what fails now.
    """
    store.save_proposal(_proposal(status="proposed"))
    store.set_kill_switch(True, reason="operator halted the platform")
    recorder = BrokerRecorder(is_configured=True)

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "approve", _portfolio(), load_policy(), store,
                now_et=NOW_ET,
                # Deliberately False: the caller is NOT cooperating.
                kill_switch_active=False,
            )

    assert "kill switch" in str(caught.value).lower(), (
        f"blocked for the wrong reason: {caught.value}"
    )
    assert "submit_market_order" not in recorder.call_names
    assert "submit_limit_order" not in recorder.call_names
    assert observable_state(store, "p-1")["broker_orders"] == []


def test_a_proposal_bound_to_a_different_policy_content_is_refused(store):
    """Version equality is not enough; the fingerprint covers content.

    Two policy files can share a version string yet carry materially
    different limits -- a personal copy edited without a version bump is
    the realistic case. The fingerprint covers every behaviour-affecting
    field, so it changes when the version does not, and a proposal whose
    stored fingerprint no longer matches must be regenerated rather than
    executed against limits nobody approved it under.

    Mutation result, GR-1B. Like the kill switch, this is checked at two
    sites -- the pre-claim gate and validate_proposal_for_execution() --
    so disabling either alone is survivable by design. Disabling BOTH was
    undetected by this suite until this test existed.
    """
    proposal = _proposal(side="sell")
    proposal["policy_fingerprint"] = "0" * 64  # a policy that is not this one
    store.save_proposal(proposal)
    recorder = _submission_recorder(submit={"order_id": "must-not-submit"})

    with patched_broker(recorder):
        with pytest.raises(ProposalExecutionError) as caught:
            execute_approved_paper_proposal(
                "p-1", "approve", _held_portfolio(), load_policy(), store,
                now_et=NOW_ET, earnings_days_away=10,
            )

    assert "fingerprint" in str(caught.value).lower(), caught.value
    assert recorder.call_names == (), (
        "a policy-binding failure must be refused before any broker contact"
    )
    state = observable_state(store, "p-1")
    assert state["reservations"] == []
    assert state["broker_orders"] == []


def test_an_expired_proposal_is_refused_and_never_reaches_the_broker(store):
    """Expiry is enforced INSIDE the atomic claim, and that must be proved.

    An expired proposal was priced, sized, and approved against a market
    view that no longer holds. Submitting it sends an order the human
    approved under conditions that have since changed.

    Mutation result, GR-1B, stated precisely. Deleting `not_expired_after`
    from the atomic claim left the ENTIRE suite green (2395 passed). It
    does NOT let an expired order reach the broker -- validation still
    refuses, measured -- but the proposal is CLAIMED first and ends in
    `blocked` rather than `expired`. So what was uncovered is not the
    refusal, it is that expiry belongs INSIDE the conditional claim.

    That location is the point. The claim is the serialization boundary:
    deciding expiry after it means an expired proposal briefly holds a
    claim and occupies its ticker/side duplicate slot, blocking a live
    proposal for the same trade. Pinning the resulting status is how this
    test tells the two arrangements apart.
    """
    store.save_proposal(
        _proposal(side="sell", expires_at="2020-01-01T00:00:00+00:00")
    )
    recorder = _submission_recorder(submit={"order_id": "must-not-submit"})

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

    assert "expired" in str(caught.value).lower(), caught.value
    assert recorder.call_names == (), (
        "an expired proposal must be refused before any broker contact"
    )
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "expired"
    assert state["reservations"] == [], "an expired proposal must reserve nothing"
    assert state["broker_orders"] == []


def test_a_mismatched_order_under_our_key_halts_the_platform(store):
    """The only execution path that ENGAGES the persistent kill switch.

    Submission raised, and a lookup by our exact idempotency key found an
    order that is NOT what we submitted. That means either the broker
    reused our key or something we do not understand happened to an order
    carrying our identity -- precisely the anomaly duplicate-order
    protection exists to catch. It must never auto-resolve: the proposal
    stays unresolved, the reservation stays held, no order is journaled as
    ours, and the whole platform stops until a human looks.

    GR-1B gap analysis, 2026-08-02: grepping this branch's error strings
    across tests/ returned nothing, so a path that halts the entire
    platform was moving into the kernel with zero coverage. Frozen here
    before the orchestration split, not after.
    """
    store.save_proposal(_proposal(side="sell"))
    # Same ticker/side/type under our key, but 100 shares where we sent 1.
    mismatched = {
        "order_id": "paper-not-ours-1",
        "ticker": "AAPL",
        "shares": 100,
        "side": "sell",
        "type": "market",
        "limit_price": None,
        "status": "accepted",
    }
    recorder = _submission_recorder(
        submit=TimeoutError("response lost after submission"),
        lookup=mismatched,
    )

    assert store.get_kill_switch().get("active") is not True

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

    message = str(caught.value)
    assert "MISMATCHED" in message, message
    # The audit trail must name WHICH field disagreed, not just that one did.
    assert "shares" in message, message

    assert recorder.call_names.count("submit_market_order") == 1, (
        "a mismatch must never be retried -- that is how a duplicate real "
        "order gets sent"
    )
    assert recorder.call_names[-1] == "find_order_by_client_id"

    kill_switch = store.get_kill_switch()
    assert kill_switch.get("active") is True, (
        "an order carrying our idempotency key that is not our order is an "
        "unexplained broker-state anomaly; the platform must stop"
    )
    assert "MISMATCH" in str(kill_switch.get("reason", "")).upper() or "match" in str(
        kill_switch.get("reason", "")
    ), kill_switch

    state = observable_state(store, "p-1")
    assert state["proposal_status"] == SUBMISSION_UNKNOWN, (
        "never auto-resolved to failed or accepted -- we do not know what "
        "happened, and a terminal status would claim we do"
    )
    assert state["reservations"] != [], (
        "the budget stays held: an order may be live at the broker"
    )
    assert state["broker_orders"] == [], (
        "the mismatched order must NOT be journaled as this proposal's order"
    )


def test_the_legacy_facade_reexports_the_exact_kernel_exception_objects():
    """GR-1 moves definitions without changing caller-visible identities."""
    from assistant import execution_service
    from assistant.execution_kernel import errors

    assert execution_service.ProposalExecutionError is errors.ProposalExecutionError
    assert (
        execution_service.PolicyOverridableBlockError
        is errors.PolicyOverridableBlockError
    )
    assert errors.ProposalClaimLostError is errors._ProposalClaimLostError
    assert (
        execution_service._ProposalClaimLostError
        is errors.ProposalClaimLostError
    )


def test_gr1b_preserves_the_legacy_duplicate_conflict_facade_export():
    """The facade cannot silently lose names merely because GR-1 moved code."""
    from assistant import execution_service
    from assistant.storage import DuplicateIntentConflict

    assert execution_service.DuplicateIntentConflict is DuplicateIntentConflict


def test_gr1c_the_outcome_class_is_the_exact_kernel_object():
    """Same class object, not a copy: isinstance checks and constructions
    through either import path must be interchangeable."""
    from assistant import execution_service
    from assistant.execution_kernel import validate as validate_kernel

    assert (
        execution_service.ProposalValidationOutcome
        is validate_kernel.ProposalValidationOutcome
    )
    assert (
        execution_service.ProposalValidationDeps
        is validate_kernel.ProposalValidationDeps
    )
    assert (
        execution_service.run_proposal_validation
        is validate_kernel.run_proposal_validation
    )


def test_gr1c_preserves_the_facades_export_only_names():
    """The facade's pre-GR-1C importable surface stays importable, by identity.

    The facade's importable surface is a compatibility contract -- the
    GR-1B review rejected dropping DuplicateIntentConflict on exactly this
    ground even with zero in-repo consumers. Losing any of these names from
    ``assistant.execution_service`` is an API change, not a cleanup. Naming
    precision (third round): not all of these are export-ONLY -- Decimal,
    to_decimal, TradeIntent, FAILURE_DATA_INTEGRITY, and
    FAILURE_INFRASTRUCTURE are live facade call sites (the deps wiring);
    only MoneyInput, ValidationResult, intent_fingerprint, dataclasses,
    FAILURE_DETERMINISTIC_POLICY, and FAILURE_NONE remain import-only.
    Either way the pin is the same: identity, not mere importability.
    """
    import dataclasses as stdlib_dataclasses
    from decimal import Decimal

    from assistant import execution_service
    from assistant.execution_telemetry import (
        FAILURE_DATA_INTEGRITY,
        FAILURE_DETERMINISTIC_POLICY,
        FAILURE_INFRASTRUCTURE,
        FAILURE_NONE,
    )
    from assistant.money import MoneyInput, to_decimal
    from risk.execution_gate import (
        TradeIntent,
        ValidationResult,
        intent_fingerprint,
    )

    assert execution_service.FAILURE_DATA_INTEGRITY is FAILURE_DATA_INTEGRITY
    assert (
        execution_service.FAILURE_DETERMINISTIC_POLICY
        is FAILURE_DETERMINISTIC_POLICY
    )
    assert execution_service.FAILURE_INFRASTRUCTURE is FAILURE_INFRASTRUCTURE
    assert execution_service.FAILURE_NONE is FAILURE_NONE
    assert execution_service.MoneyInput is MoneyInput
    assert execution_service.to_decimal is to_decimal
    assert execution_service.TradeIntent is TradeIntent
    assert execution_service.ValidationResult is ValidationResult
    assert execution_service.intent_fingerprint is intent_fingerprint
    assert execution_service.dataclasses is stdlib_dataclasses
    assert execution_service.Decimal is Decimal


# --------------------------------------------------------------------------
# GR-1D: manual-reconciliation seam freeze
#
# reconcile_submission() historically resolved twelve runtime names from
# this facade's module namespace (symtable-enumerated before the move):
# ProposalExecutionError, SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING,
# _intent_from_dict, _lookup_order_outcome, _order_matches_intent,
# _authoritative_order_for, _broker_absence_is_old_enough,
# journal_broker_order_update, datetime, timezone -- plus the deferred
# `import execution.alpaca_broker` (frozen separately by the sys.modules
# patching tests in test_replacement_chain_round3.py). Each test below pins
# one seam: replacing the FACADE name must keep changing reconciliation
# behaviour, exactly as it did before GR-1D moved the body into the kernel.
# --------------------------------------------------------------------------


def _unknown_proposal(store, proposal_id: str = "p-1") -> None:
    store.save_proposal(_proposal(proposal_id, status="submission_unknown"))
    store.reserve_execution_budget(
        proposal_id,
        trading_day="2026-08-03",
        notional="100.00",
        max_daily_notional="1000.00",
        max_daily_orders=5,
    )


def test_gr1d_patching_lookup_and_absence_guard_on_the_facade_is_honoured(
    store, monkeypatch
):
    _unknown_proposal(store)
    lookup_calls = []
    absence_calls = []

    def facade_lookup(broker, idempotency_key):
        lookup_calls.append(idempotency_key)
        return None

    def facade_absence_guard(claimed, *, now):
        absence_calls.append(now)
        return False

    monkeypatch.setattr(execution_service, "_lookup_order_outcome", facade_lookup)
    monkeypatch.setattr(
        execution_service, "_broker_absence_is_old_enough", facade_absence_guard
    )

    with pytest.raises(ProposalExecutionError) as caught:
        reconcile_submission("p-1", store)

    assert "grace period has not elapsed" in str(caught.value)
    assert lookup_calls == ["idem-p-1"]
    assert len(absence_calls) == 1
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "submission_unknown"
    assert len(state["reservations"]) == 1  # reservation retained


def test_gr1d_patching_order_match_on_the_facade_drives_the_mismatch_path(
    store, monkeypatch
):
    _unknown_proposal(store)
    monkeypatch.setattr(
        execution_service,
        "_lookup_order_outcome",
        lambda broker, key: {"order_id": "o-1", "status": "accepted"},
    )
    monkeypatch.setattr(
        execution_service,
        "_order_matches_intent",
        lambda outcome, intent: (False, "gr1d-sentinel-mismatch"),
    )

    with pytest.raises(ProposalExecutionError) as caught:
        reconcile_submission("p-1", store)

    assert "gr1d-sentinel-mismatch" in str(caught.value)
    assert store.get_kill_switch()["active"] is True
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "submission_unknown"
    assert len(state["reservations"]) == 1
    store.set_kill_switch(False, reason="test cleanup")


def test_gr1d_patching_chain_resolution_on_the_facade_is_honoured(
    store, monkeypatch
):
    _unknown_proposal(store)
    monkeypatch.setattr(
        execution_service,
        "_lookup_order_outcome",
        lambda broker, key: {"order_id": "o-1", "status": "accepted"},
    )
    monkeypatch.setattr(
        execution_service, "_order_matches_intent", lambda outcome, intent: (True, None)
    )
    monkeypatch.setattr(
        execution_service,
        "_authoritative_order_for",
        lambda broker, outcome, intent: (None, "gr1d-chain-error", False, ()),
    )

    with pytest.raises(ProposalExecutionError) as caught:
        reconcile_submission("p-1", store)

    assert "gr1d-chain-error" in str(caught.value)
    assert "Left retryable" in str(caught.value)
    assert store.get_kill_switch()["active"] is False
    assert observable_state(store, "p-1")["proposal_status"] == "submission_unknown"


def test_gr1d_patching_journal_on_the_facade_receives_the_authoritative_order(
    store, monkeypatch
):
    _unknown_proposal(store)
    authoritative = {"order_id": "o-replacement", "status": "filled"}
    journal_calls = []

    def facade_journal(store_arg, proposal_id, order, **kwargs):
        journal_calls.append((proposal_id, order, kwargs))

    monkeypatch.setattr(
        execution_service,
        "_lookup_order_outcome",
        lambda broker, key: {"order_id": "o-1", "status": "accepted"},
    )
    monkeypatch.setattr(
        execution_service, "_order_matches_intent", lambda outcome, intent: (True, None)
    )
    monkeypatch.setattr(
        execution_service,
        "_authoritative_order_for",
        lambda broker, outcome, intent: (
            authoritative,
            None,
            False,
            ("o-1", "o-replacement"),
        ),
    )
    monkeypatch.setattr(
        execution_service, "journal_broker_order_update", facade_journal
    )

    result = reconcile_submission("p-1", store)

    assert result is authoritative
    assert len(journal_calls) == 1
    proposal_id, order, kwargs = journal_calls[0]
    assert proposal_id == "p-1"
    assert order is authoritative
    assert kwargs["event_type"] == "manual_reconciliation"
    assert kwargs["clear_error"] is True
    assert kwargs["raw_event"] == {"replacement_chain": ["o-1", "o-replacement"]}
    assert "reconciled_at" in kwargs["extra_updates"]


def test_gr1d_patching_intent_parsing_on_the_facade_is_honoured(store, monkeypatch):
    _unknown_proposal(store)

    def broken_intent(payload):
        raise ValueError("gr1d-intent-sentinel")

    monkeypatch.setattr(execution_service, "_intent_from_dict", broken_intent)

    with pytest.raises(ProposalExecutionError) as caught:
        reconcile_submission("p-1", store)

    assert "gr1d-intent-sentinel" in str(caught.value)
    state = observable_state(store, "p-1")
    assert state["proposal_status"] == "submission_unknown"
    proposal = store.get_proposal("p-1")
    assert "gr1d-intent-sentinel" in (proposal.get("error") or "")


def test_gr1d_the_reconciliation_clock_and_timezone_resolve_from_the_facade(
    store, monkeypatch
):
    _unknown_proposal(store)
    fixed = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    class FacadeTimezone:
        utc = object()

    seen_tz = []

    class RecordingDateTime:
        @classmethod
        def now(cls, tz=None):
            seen_tz.append(tz)
            return fixed

    journal_calls = []
    monkeypatch.setattr(
        execution_service,
        "_lookup_order_outcome",
        lambda broker, key: {"order_id": "o-1", "status": "accepted"},
    )
    monkeypatch.setattr(
        execution_service, "_order_matches_intent", lambda outcome, intent: (True, None)
    )
    monkeypatch.setattr(
        execution_service,
        "_authoritative_order_for",
        lambda broker, outcome, intent: (
            {"order_id": "o-1", "status": "accepted"},
            None,
            False,
            (),
        ),
    )
    monkeypatch.setattr(
        execution_service,
        "journal_broker_order_update",
        lambda store_arg, proposal_id, order, **kwargs: journal_calls.append(kwargs),
    )
    monkeypatch.setattr(execution_service, "datetime", RecordingDateTime)
    monkeypatch.setattr(execution_service, "timezone", FacadeTimezone)

    reconcile_submission("p-1", store)

    assert journal_calls[0]["event_at"] == fixed.isoformat()
    assert journal_calls[0]["extra_updates"]["reconciled_at"] == fixed.isoformat()
    assert seen_tz == [FacadeTimezone.utc]


def test_gr1d_patching_the_exception_class_on_the_facade_controls_raise_identity(
    store, monkeypatch
):
    class SentinelError(Exception):
        pass

    monkeypatch.setattr(execution_service, "ProposalExecutionError", SentinelError)

    with pytest.raises(SentinelError) as caught:
        reconcile_submission("missing", store)

    assert type(caught.value) is SentinelError
    assert str(caught.value) == "Unknown proposal: missing"


def test_gr1d_status_constants_resolve_from_the_facade(store, monkeypatch):
    store.save_proposal(_proposal(status="gr1d-unknown"))
    monkeypatch.setattr(execution_service, "SUBMISSION_UNKNOWN", "gr1d-unknown")
    monkeypatch.setattr(execution_service, "RECONCILING", "gr1d-reconciling")
    monkeypatch.setattr(
        execution_service, "_lookup_order_outcome", lambda broker, key: object()
    )

    with pytest.raises(ProposalExecutionError) as caught:
        reconcile_submission("p-1", store)

    # The claim accepted the patched claimable status, transitioned through
    # the patched RECONCILING, and the unconfirmed-lookup branch wrote the
    # patched SUBMISSION_UNKNOWN back.
    assert "could not confirm the broker's outcome" in str(caught.value)
    assert observable_state(store, "p-1")["proposal_status"] == "gr1d-unknown"


def test_gr1d_facade_exports_the_exact_kernel_reconciliation_objects():
    from assistant.execution_kernel import reconcile as reconcile_kernel

    assert execution_service.ReconciliationDeps is reconcile_kernel.ReconciliationDeps
    assert (
        execution_service.run_submission_reconciliation
        is reconcile_kernel.run_submission_reconciliation
    )


def test_gr1d_the_kernel_body_reads_no_module_globals():
    """Structural guard behind the whole GR-1D seam family.

    The behavioural tests above each freeze one seam. This pins the boundary
    itself: run_submission_reconciliation() may not read any module-scope
    runtime name; every collaborator must arrive through ReconciliationDeps.
    A symbol-table test is used because it follows Python's actual lexical
    scopes (including comprehensions and nested blocks) and still detects a
    module global that shadows a builtin. Runtime behavior cannot observe the
    distinction when the kernel and facade imports happen to point at the
    same object.
    """
    import builtins
    from pathlib import Path
    import symtable

    source_path = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "execution_kernel" / "reconcile.py"
    )
    source = source_path.read_text(encoding="utf-8")
    module_table = symtable.symtable(source, str(source_path), "exec")
    function_table = next(
        table
        for table in module_table.get_children()
        if table.get_name() == "run_submission_reconciliation"
    )

    module_bindings = {
        symbol.get_name()
        for symbol in module_table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }

    def runtime_module_reads(table) -> set[str]:
        reads = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_global()
            and symbol.is_referenced()
            and (
                symbol.get_name() in module_bindings
                or not hasattr(builtins, symbol.get_name())
            )
        }
        for child in table.get_children():
            reads.update(runtime_module_reads(child))
        return reads

    module_reads = runtime_module_reads(function_table)
    assert not module_reads, (
        "run_submission_reconciliation() reads module-scope runtime names "
        f"instead of ReconciliationDeps: {sorted(module_reads)}"
    )
