"""Genuine small-domain plan factories, no source/provider or operational I/O."""
import importlib.util
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_durable_budget as budget

spec = importlib.util.spec_from_file_location("durable_count_budget_fabricated_support",
    Path(__file__).with_name("test_short_interest_count_recovery_budget.py"))
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


@pytest.fixture(autouse=True)
def isolated_registries_and_no_network(monkeypatch):
    for name, value in (("_BUDGETS", {}), ("_TICKETS", {}), ("_LOCKS", {}), ("_FAILED", set()), ("_CONSUMED", set()),
            ("_SETTLEMENT_MINTS", {}), ("_SETTLED_VIEWS", {}), ("_APPEND_ORIGINS", {})):
        monkeypatch.setattr(budget, name, value)
    def denied(*args, **kwargs): raise AssertionError("pure fabricated accounting forbids network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def genuine_plan(monkeypatch, *, maximum_bytes=None, chunk_size=2):
    ledger = support.baseline(monkeypatch, maximum_bytes=maximum_bytes)
    monkeypatch.setattr(budget.research_budget, "POSITIONS_PER_CHUNK", chunk_size)
    monkeypatch.setattr(budget, "_EXPECTED_SOURCE_PROFILE", budget._source_profile())
    return budget.research_budget.freeze_count_recovery_plan(ledger)


@pytest.fixture
def negative_plan(monkeypatch):
    value, exposed, plan = support.genuine_exposure_plan(monkeypatch)
    monkeypatch.setattr(budget, "_EXPECTED_SOURCE_PROFILE", budget._source_profile())
    return SimpleNamespace(ledger=value, exposure=exposed, plan=plan)


def test_permanent_negative_allocation_survives_successful_partial_settlement(negative_plan, fabricated_reader):
    h = negative_plan; value = budget.open_durable_count_budget(h.plan)
    before = value.public_summary(); page = budget.research_budget.MAXIMUM_RESPONSE_BYTES
    assert before["permanent_unknown_START_upper_debits"] == 8
    assert before["permanent_unknown_byte_debits"] == 8 * page
    assert before["cumulative_START_debits_upper_bound"] == h.ledger.public_summary()["START_debits"] + 8
    for position in h.plan.chunk_positions(1): value.reserve_start_slot(position)
    tickets = value.current_tickets()
    assert tickets[0].public_summary()["lifetime_try"] == 3
    assert all(ticket.public_summary()["lifetime_try"] == 2 for ticket in tickets[1:])
    charged = 8 * 17; value.settle_closed_chunk(fabricated_reader.mint(value))
    after = value.public_summary(); journal = budget.settled_chunk_accounting(value)
    assert value._state[4] == after["new_closed_charged_bytes"] == charged
    assert after["historical_charged_bytes"] == h.ledger.public_summary()["charged_response_bytes"]
    assert after["permanent_unknown_byte_debits"] == 8 * page and after["permanent_unknown_START_upper_debits"] == 8
    assert after["cumulative_charged_plus_reserved_bytes"] == before["cumulative_charged_plus_reserved_bytes"] + charged
    assert after["cumulative_START_debits_upper_bound"] == before["cumulative_START_debits_upper_bound"] + 8
    assert len(journal) == 4 and len(journal[3][0]) == 7 and len(budget.ticket_binding(tickets[0])) == 14
    assert len(budget._TICKETS) == 8 and value.reserve_start_slot(13).public_summary()["reservation_ordinal"] == 9
    assert value.public_summary()["permanent_unknown_byte_debits"] == 8 * page


def test_possible_prior_try_prevents_a_fourth_lifetime_attempt(negative_plan):
    value = budget.open_durable_count_budget(negative_plan.plan)
    assert value.reserve_start_slot(5).public_summary()["lifetime_try"] == 3
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="lifetime_try_cap"): value.reserve_start_slot(5)
    assert value._state is original and len(original[1]) == 1


def test_new_first_chunk_limit_rejects_old_sixteen_extra_allowance(monkeypatch):
    ledger, exposed, plan = support.genuine_exposure_plan(monkeypatch, maximum_bytes=72 * 1024 ** 2, chunk_size=16)
    monkeypatch.setattr(budget, "_EXPECTED_SOURCE_PROFILE", budget._source_profile())
    value = budget.open_durable_count_budget(plan)
    for position in (*range(5, 21), 13, 13, 14, 14, 15, 15, 16, 16): value.reserve_start_slot(position)
    assert plan.chunk_extra_limit(1) == 8 and len(value._state[2]) == 24
    # Position17 still has a legal lifetime try, but the ninth extra slot is
    # forbidden even though the obsolete global +16 rule would accept it.
    with pytest.raises(budget.DurableCountBudgetRefusal, match="current_chunk_START_cap"): value.reserve_start_slot(17)
    assert len(value._state[1]) == 24


def test_byte_capacity_counts_permanent_negative_pages_before_new_slot(monkeypatch):
    ledger, exposed, plan = support.genuine_exposure_plan(monkeypatch, maximum_bytes=24 * 1024 ** 2)
    monkeypatch.setattr(budget, "_EXPECTED_SOURCE_PROFILE", budget._source_profile())
    value = budget.open_durable_count_budget(plan)
    value.reserve_start_slot(5)
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="full_page_byte_capacity"): value.reserve_start_slot(6)
    assert value._state is original and len(original[1]) == 1
    assert plan.budget_profile()["initial_byte_upper_bound"] + 2 * budget.research_budget.MAXIMUM_RESPONSE_BYTES > 24 * 1024 ** 2


@pytest.fixture
def plan(monkeypatch): return genuine_plan(monkeypatch)


@pytest.fixture
def fabricated_reader(monkeypatch):
    """Explicit stand-in for an UNIMPLEMENTED operational-reader boundary.

    This proves the budget consumer contract only. It authenticates no actual
    body, receipt, filesystem, source, code, HTTP or outer-context closure.
    No such witness factory is exposed by the production budget module.
    """
    module = ModuleType("scripts.short_interest_closed_count_chunk")
    minted, calls = {}, []
    class ClosedCountChunk:
        __slots__ = ("_anchor", "_identity")
        def __init__(self): raise AssertionError("test registry factory required")
    def authenticate(value):
        calls.append(value)
        original = minted.get(value) if type(value) is ClosedCountChunk else None
        budget.require(original is not None and value._anchor is value._identity is original,
            "closed_chunk_binding_changed")
        for ticket in original[3]: budget.ticket_binding(ticket)
        return original
    def mint(value, *, outcomes=None, account_change=None):
        plan, state = value._guard()
        roster = state[2]
        if outcomes is None: outcomes = tuple(("durable", 17) for unused in roster)
        assert len(outcomes) == len(roster)
        charges = tuple(size if kind == "durable" else budget.research_budget.MAXIMUM_RESPONSE_BYTES
            for kind, size in outcomes)
        account = (value._anchor[3], plan, state[0], roster, charges, plan.chunk_positions(state[0]),
            hash_payload(["FABRICATED_READER_NOT_OPERATIONAL", len(minted), tuple(item.sha256 for item in roster)]))
        if account_change is not None: account = account_change(account)
        result = object.__new__(ClosedCountChunk)
        result._anchor = result._identity = account
        minted[result] = account
        return result
    module.ClosedCountChunk = ClosedCountChunk
    module.closed_count_chunk_accounting = authenticate
    monkeypatch.setitem(sys.modules, module.__name__, module)
    import scripts
    monkeypatch.setattr(scripts, "short_interest_closed_count_chunk", module, raising=False)
    return SimpleNamespace(module=module, mint=mint, minted=minted, calls=calls)


def test_actual_policy_keeps_old_debits_caps_and_no_dispatch_authority():
    value = budget.policy()
    assert (value["prior_STARTs"], value["prior_charged_bytes"]) == (13992, 23452681)
    assert value["maximum_cumulative_STARTs"] == 84005
    assert value["maximum_cumulative_bytes"] == 4 * 1024 ** 3
    assert value["whole_attempt_reservation_bytes"] == 2 * 1024 ** 2
    assert value["maximum_chunks"] == 133 and value["positions_per_chunk"] == 512
    assert value["extra_attempts_per_chunk"] == 16 and value["maximum_LIFETIME_tries_per_position"] == 3
    assert not value["individual_ticket_release"] and not value["actual_START_or_HTTP_observation"]
    assert not value["authority"]["dispatch_authority"] and not value["authority"]["ready_for_backtest"]
    assert not budget.research_budget.policy()["reservation_releases_supported"]


def test_exact_tickets_derive_original_source_request_and_preserve_prior_tries(plan):
    value = budget.open_durable_count_budget(plan)
    first = value.reserve_start_slot(5)
    second = value.reserve_start_slot(6)
    source_rows = tuple(plan._parts[1]._parts[1].query_plan.iter_queries())
    report = first.public_summary()
    assert report["request_sha256"] == source_rows[4].to_payload()["request_sha256"]
    assert report["lifetime_try"] == 2 and second.public_summary()["lifetime_try"] == 1
    assert report["source_position"] == 5 and report["matrix_query_ordinal"] == plan.chunk_matrix_ordinals(1)[0]
    assert first.sha256 == hash_bytes(canonical_json(report).encode())
    assert value.current_tickets() == (first, second)
    bound = budget.ticket_binding(first)
    assert bound[0] is first and bound[1] is value and bound[2] is plan
    assert bound[9] == first.sha256 and bound[11] == 2 * 1024 ** 2
    assert first.reservation_sha256 == first.sha256 and value.budget_identity is bound[12] and value.plan is plan
    assert all(token not in canonical_json(report) for token in ("https:", "ticker", "Bearer"))
    report["lifetime_try"] = 0
    assert first.public_summary()["lifetime_try"] == 2
    observed = value.public_summary()
    assert observed["new_START_reservations"] == 2 and observed["settled_tickets"] == 0
    assert observed["outstanding_full_page_bytes"] == 4 * 1024 ** 2
    assert observed["cumulative_charged_plus_reserved_bytes"] == budget.research_budget.PRIOR_CHARGED_BYTES + 4 * 1024 ** 2


@pytest.mark.parametrize("position", [True, 1.0, "5", None, 0, 1, 7, 8, 9])
def test_only_current_chunk_positions_are_permitted_and_refusal_is_permanent(plan, position):
    value = budget.open_durable_count_budget(plan)
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="exact_current_chunk_position"):
        value.reserve_start_slot(position)
    assert value._state is original and not budget._TICKETS
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.reserve_start_slot(5)


def test_historical_lifetime_try_cap_never_refunds_or_allows_a_fresh_coordinator(plan):
    value = budget.open_durable_count_budget(plan)
    value.reserve_start_slot(5); value.reserve_start_slot(5)
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="lifetime_try_cap"): value.reserve_start_slot(5)
    assert value._state is original and len(original[1]) == 2
    with pytest.raises(budget.DurableCountBudgetRefusal, match="already_opened"): budget.open_durable_count_budget(plan)
    assert not hasattr(value, "release") and not hasattr(value, "refund")


def test_chunk_limit_and_extra_limit_are_independent_of_lifetime_tries(plan):
    value = budget.open_durable_count_budget(plan)
    for position in (5, 5, 6, 6): value.reserve_start_slot(position)
    old = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="current_chunk_START_cap"): value.reserve_start_slot(6)
    assert value._state is old


def test_extra_attempt_limit_is_preserved(monkeypatch):
    ledger = support.baseline(monkeypatch)
    monkeypatch.setattr(budget.research_budget, "EXTRA_ATTEMPTS_PER_CHUNK", 1)
    monkeypatch.setattr(budget.research_budget, "MAXIMUM_CUMULATIVE_STARTS", 12)
    monkeypatch.setattr(budget, "_EXPECTED_SOURCE_PROFILE", budget._source_profile())
    plan = budget.research_budget.freeze_count_recovery_plan(ledger)
    value = budget.open_durable_count_budget(plan)
    value.reserve_start_slot(6); value.reserve_start_slot(6)
    # There is still a base descriptor unattempted, so the extra guard fires
    # before the overall three-slot chunk cap or the lifetime try ceiling.
    with pytest.raises(budget.DurableCountBudgetRefusal, match="current_chunk_extra_cap"): value.reserve_start_slot(6)
    assert len(value._state[1]) == 2


def test_byte_capacity_includes_all_full_pages_until_genuine_chunk_closure(monkeypatch):
    page = budget.research_budget.MAXIMUM_RESPONSE_BYTES
    plan = genuine_plan(monkeypatch, maximum_bytes=6 * page + 4 * len(b"fabricated-two"), chunk_size=3)
    value = budget.open_durable_count_budget(plan)
    for position in (5, 6, 7, 6): value.reserve_start_slot(position)
    assert value.public_summary()["cumulative_charged_plus_reserved_bytes"] == budget.research_budget.MAXIMUM_CUMULATIVE_BYTES
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="full_page_byte_capacity"): value.reserve_start_slot(7)
    assert value._state is original


def test_reflected_budget_and_ticket_copies_cannot_spend_or_reset(plan):
    value = budget.open_durable_count_budget(plan); ticket = value.reserve_start_slot(5)
    fake = object.__new__(budget.CountAttemptTicket)
    for name in ("_anchor", "_identity"): object.__setattr__(fake, name, getattr(ticket, name))
    with pytest.raises(budget.DurableCountBudgetRefusal, match="ticket_binding"): fake.public_summary()
    forged = object.__new__(budget.DurableCountBudget)
    for name in ("_anchor", "_identity", "_state"): object.__setattr__(forged, name, getattr(value, name))
    with pytest.raises(budget.DurableCountBudgetRefusal, match="budget_binding"): forged.reserve_start_slot(6)
    assert len(value.current_tickets()) == 1
    original = value._state
    object.__setattr__(value, "_state", (1, (), (), (), 0))
    with pytest.raises(budget.DurableCountBudgetRefusal, match="budget_binding"): value.public_summary()
    object.__setattr__(value, "_state", original)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()


def test_exact_original_ticket_binding_mutation_stops_owning_coordinator(plan):
    value = budget.open_durable_count_budget(plan); ticket = value.reserve_start_slot(5)
    original = ticket._anchor
    object.__setattr__(ticket, "_anchor", tuple(list(original)))
    with pytest.raises(budget.DurableCountBudgetRefusal, match="ticket_binding"): ticket.public_summary()
    object.__setattr__(ticket, "_anchor", original)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()


def test_only_original_owner_thread_can_touch_the_coordinator(plan):
    value = budget.open_durable_count_budget(plan); errors = []
    def other():
        try: value.reserve_start_slot(5)
        except BaseException as error: errors.append(error)
    thread = threading.Thread(target=other); thread.start(); thread.join()
    assert len(errors) == 1 and budget.failure_summary(errors[0])["contract_code"] == "durable_budget_owner_changed"
    assert value._state[1] == ()
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()


def test_workers_can_authenticate_immutable_tickets_without_coordinator_mutation(plan):
    value = budget.open_durable_count_budget(plan); ticket = value.reserve_start_slot(5)
    original = value._state; results = []
    thread = threading.Thread(target=lambda: results.append(budget.ticket_binding(ticket)))
    thread.start(); thread.join()
    assert len(results) == 1 and results[0][0] is ticket
    assert value._state is original and len(value.current_tickets()) == 1


def test_worker_cannot_observe_torn_reservation_append_even_at_registry_barrier(plan, monkeypatch):
    value = budget.open_durable_count_budget(plan)
    published, attempted, done = threading.Event(), threading.Event(), threading.Event()
    discovered, results, errors = [], [], []
    # Test-only registry write barrier at the genuine multiwrite transition.
    # Production registries are ordinary dictionaries and invoke no callback.
    class PausingTickets(dict):
        def __setitem__(self, key, parts):
            super().__setitem__(key, parts); discovered.append(key); published.set()
            assert attempted.wait(2)
            assert not done.wait(.05), "worker escaped lock during the uncommitted transition"
    monkeypatch.setattr(budget, "_TICKETS", PausingTickets())
    def worker():
        assert published.wait(2); attempted.set()
        try: results.append(budget.active_ticket_binding(discovered[0]))
        except BaseException as error: errors.append(error)
        finally: done.set()
    thread = threading.Thread(target=worker); thread.start()
    ticket = value.reserve_start_slot(5); thread.join(2)
    assert not thread.is_alive() and done.is_set() and not errors
    assert len(results) == 1 and results[0][0] is ticket
    assert value.current_tickets() == (ticket,)


def test_full_current_policy_changes_latch_without_spending(plan, monkeypatch):
    value = budget.open_durable_count_budget(plan)
    original = budget.authority()
    monkeypatch.setattr(budget, "authority", lambda: {**original, "dispatch_authority": True})
    with pytest.raises(budget.DurableCountBudgetRefusal, match="policy_changed"): value.reserve_start_slot(5)
    monkeypatch.setattr(budget, "authority", lambda: original)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()
    assert value._state[1] == ()


def test_genuine_exact_plan_and_finite_single_coordinator_are_required(plan):
    for value in (True, plan.public_summary(), object.__new__(budget.research_budget.CountRecoveryPlan)):
        with pytest.raises((budget.DurableCountBudgetRefusal, budget.research_budget.CountRecoveryBudgetRefusal)):
            budget.open_durable_count_budget(value)
    budget.open_durable_count_budget(plan)
    with pytest.raises(budget.DurableCountBudgetRefusal): budget.open_durable_count_budget(plan)
    for cls in (budget.DurableCountBudget, budget.CountAttemptTicket):
        with pytest.raises(budget.DurableCountBudgetRefusal): cls()


def test_failure_projection_never_formats_dynamic_values_or_types():
    class Hostile:
        def __str__(self): pytest.fail("secret formatting")
        def __repr__(self): pytest.fail("secret repr")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("secret property")
    for error in (Error(), budget.DurableCountBudgetRefusal(Hostile()),
        budget.DurableCountBudgetRefusal("REFUSED: SECRET")):
        assert budget.failure_summary(error)["contract_code"] is None
        assert "SECRET" not in canonical_json(budget.failure_summary(error))
    assert budget.failure_summary(budget.DurableCountBudgetRefusal("REFUSED: lifetime_try_cap"))["contract_code"] == "lifetime_try_cap"


def test_only_original_terminal_reader_witness_can_settle_and_advance(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan)
    first, second = value.reserve_start_slot(5), value.reserve_start_slot(6)
    original_STARTs = value.public_summary()["cumulative_START_debits_upper_bound"]
    witness = fabricated_reader.mint(value, outcomes=(("durable", 19), ("unknown", None)))
    assert value.public_summary()["outstanding_full_page_bytes"] == 2 * budget.research_budget.MAXIMUM_RESPONSE_BYTES
    settled = value.settle_closed_chunk(witness)
    assert settled == {"settled_chunk": 1, "settled_attempts": 2,
        "new_charged_bytes": 19 + budget.research_budget.MAXIMUM_RESPONSE_BYTES, "next_chunk": 2, "dispatch_authority": False}
    report = value.public_summary()
    assert report["cumulative_START_debits_upper_bound"] == original_STARTs
    assert report["outstanding_full_page_bytes"] == 0 and report["historical_charged_bytes"] == budget.research_budget.PRIOR_CHARGED_BYTES
    assert report["new_closed_charged_bytes"] == 19 + budget.research_budget.MAXIMUM_RESPONSE_BYTES
    assert budget.ticket_binding(first)[0] is first and budget.ticket_binding(second)[0] is second
    assert value.reserve_start_slot(7).public_summary()["reservation_ordinal"] == 3
    assert value.public_summary()["new_closed_charged_bytes"] == report["new_closed_charged_bytes"]


def test_settled_ticket_historical_auth_cannot_authorize_a_new_response(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan)
    ticket = value.reserve_start_slot(5); value.reserve_start_slot(6)
    value.settle_closed_chunk(fabricated_reader.mint(value))
    assert budget.ticket_binding(ticket)[0] is ticket
    with pytest.raises(budget.DurableCountBudgetRefusal, match="no_longer_active"): budget.active_ticket_binding(ticket)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()


@pytest.mark.parametrize("supplied", [True, {}, {"complete": True, "charged_bytes": 1}, b"closed", "a" * 64])
def test_pair_boolean_payload_hash_or_bytes_cannot_release_pages(plan, fabricated_reader, supplied):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5)
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="chunk_reader_required"): value.settle_closed_chunk(supplied)
    assert value._state is original and not budget._CONSUMED and not fabricated_reader.calls


@pytest.mark.parametrize("change", ["budget", "plan", "chunk", "roster", "order", "missing_coverage", "bool_coverage", "digest", "six_fields"])
def test_cross_identity_partial_or_wrong_coverage_refuses_without_release(plan, fabricated_reader, change):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    def mutation(account):
        values = list(account)
        if change == "budget": values[0] = object()
        elif change == "plan": values[1] = object()
        elif change == "chunk": values[2] = 2
        elif change == "roster": values[3] = values[3][:-1]
        elif change == "order": values[3] = tuple(reversed(values[3]))
        elif change == "missing_coverage": values[5] = values[5][:-1]
        elif change == "bool_coverage": values[5] = (True, 6)
        elif change == "digest": values[6] = "SECRET"
        elif change == "six_fields": return tuple(values[:5] + values[6:])
        return tuple(values)
    witness = fabricated_reader.mint(value, account_change=mutation); original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal): value.settle_closed_chunk(witness)
    assert value._state is original and not budget._CONSUMED


@pytest.mark.parametrize("charge", [True, 0, -1, 2 * 1024 ** 2 + 1, 1.0, "17", None])
def test_reader_charge_must_be_positive_bounded_exact_integer(plan, fabricated_reader, charge):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    witness = fabricated_reader.mint(value, account_change=lambda row: (*row[:4], (charge, 17), *row[5:]))
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="charge_changed"): value.settle_closed_chunk(witness)
    assert value._state is original and not budget._CONSUMED


def test_attempted_roster_must_cover_all_base_positions_independently_of_reader_claim(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5)
    witness = fabricated_reader.mint(value); original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="missing_base_position"): value.settle_closed_chunk(witness)
    assert value._state is original


def test_forged_or_reflected_reader_closure_cannot_release(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    original = fabricated_reader.mint(value)
    forged = object.__new__(fabricated_reader.module.ClosedCountChunk)
    forged._anchor = forged._identity = original._anchor
    before = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="binding_changed"): value.settle_closed_chunk(forged)
    assert value._state is before


def test_each_chunk_and_every_retry_ticket_is_consumed_exactly_once(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan)
    for position in (5, 6, 6): value.reserve_start_slot(position)
    first = fabricated_reader.mint(value); value.settle_closed_chunk(first)
    assert len(budget._CONSUMED) == 3 and value.public_summary()["new_START_reservations"] == 3
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal): value.settle_closed_chunk(first)
    assert value._state is original and len(budget._CONSUMED) == 3


def test_all_chunk_slots_keep_permanent_cumulative_START_debits_after_settlement(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan)
    for positions in ((5, 5, 6, 6), (7, 7, 8, 8)):
        before = value.public_summary()["new_START_reservations"]
        for position in positions: value.reserve_start_slot(position)
        total = value.public_summary()["cumulative_START_debits_upper_bound"]
        value.settle_closed_chunk(fabricated_reader.mint(value))
        report = value.public_summary()
        assert report["new_START_reservations"] == before + len(positions)
        assert report["cumulative_START_debits_upper_bound"] == total
    assert report["cumulative_START_debits_upper_bound"] == budget.research_budget.MAXIMUM_CUMULATIVE_STARTS == 14
    assert report["settled_tickets"] == len(budget._CONSUMED) == 8 and report["outstanding_full_page_bytes"] == 0
    original = value._state
    with pytest.raises(budget.DurableCountBudgetRefusal, match="current_chunk_required"): value.reserve_start_slot(7)
    assert value._state is original and len(original[1]) == 8


def test_reader_validation_cannot_hide_reentrant_reservation_or_discard_its_debit(plan, fabricated_reader, monkeypatch):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    witness = fabricated_reader.mint(value)
    original = fabricated_reader.module.closed_count_chunk_accounting
    def reentrant(closed):
        observed = original(closed)
        value.reserve_start_slot(6)
        return observed
    monkeypatch.setattr(fabricated_reader.module, "closed_count_chunk_accounting", reentrant)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="binding_changed"): value.settle_closed_chunk(witness)
    assert len(value._state[1]) == len(value._state[2]) == 3 and not budget._CONSUMED
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.public_summary()


def test_even_coherent_newer_reader_account_cannot_replace_prevalidation_state(plan, fabricated_reader, monkeypatch):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    witness = fabricated_reader.mint(value)
    original_authenticate = fabricated_reader.module.closed_count_chunk_accounting
    def newer(closed):
        original_authenticate(closed)
        value.reserve_start_slot(6)
        newer_witness = fabricated_reader.mint(value)
        return original_authenticate(newer_witness)
    monkeypatch.setattr(fabricated_reader.module, "closed_count_chunk_accounting", newer)
    with pytest.raises(budget.DurableCountBudgetRefusal, match="binding_changed"): value.settle_closed_chunk(witness)
    assert len(value._state[1]) == len(value._state[2]) == 3 and not budget._CONSUMED


def test_worker_cannot_settle_or_trigger_reader_validation(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    witness = fabricated_reader.mint(value); failures = []
    def worker():
        try: value.settle_closed_chunk(witness)
        except BaseException as error: failures.append(error)
    thread = threading.Thread(target=worker); thread.start(); thread.join()
    assert len(failures) == 1 and not fabricated_reader.calls and not budget._CONSUMED
    assert budget.failure_summary(failures[0])["contract_code"] == "durable_budget_owner_changed"


def test_workers_cannot_observe_torn_chunk_settlement(plan, fabricated_reader, monkeypatch):
    value = budget.open_durable_count_budget(plan)
    ticket = value.reserve_start_slot(5); value.reserve_start_slot(6)
    witness = fabricated_reader.mint(value)
    published, attempted, done = threading.Event(), threading.Event(), threading.Event()
    results, errors = [], []
    class PausingBudgets(dict):
        def __setitem__(self, key, row):
            if row[2][0] == 2:
                published.set(); assert attempted.wait(2)
                assert not done.wait(.05), "historical ticket auth escaped original settlement lock"
            super().__setitem__(key, row)
    monkeypatch.setattr(budget, "_BUDGETS", PausingBudgets(budget._BUDGETS))
    def worker():
        assert published.wait(2); attempted.set()
        try: results.append(budget.ticket_binding(ticket))
        except BaseException as error: errors.append(error)
        finally: done.set()
    thread = threading.Thread(target=worker); thread.start()
    value.settle_closed_chunk(witness); thread.join(2)
    assert not thread.is_alive() and done.is_set() and not errors and len(results) == 1
    assert results[0][0] is ticket and value.public_summary()["closed_chunks"] == 1


def test_settled_journal_returns_exact_original_account_without_old_reader_or_clock(plan, fabricated_reader, monkeypatch):
    value = budget.open_durable_count_budget(plan)
    empty = budget.settled_chunk_accounting(value)
    assert empty == (value, value.budget_identity, plan, ()) and budget.settled_chunk_accounting(value) is empty
    value.reserve_start_slot(5); value.reserve_start_slot(6)
    closed = fabricated_reader.mint(value); original_account = fabricated_reader.minted[closed]
    value.settle_closed_chunk(closed)
    journal = budget.settled_chunk_accounting(value)
    assert type(journal) is tuple and len(journal) == 4 and journal[0] is value and journal[1] is value.budget_identity
    assert journal[2] is plan and journal[3][0] is original_account
    record = value._state[3][0]
    assert len(record) == 5 and record[:4] == (closed, original_account[6], original_account[3], original_account[4])
    assert record[4] is original_account
    def expired(unused): raise AssertionError("historical accounting reopened an expired reader/source/clock")
    monkeypatch.setattr(fabricated_reader.module, "closed_count_chunk_accounting", expired)
    assert budget.settled_chunk_accounting(value) is journal
    assert journal[3][0] is original_account


def test_historical_accounting_survives_later_normal_failure_but_new_reserve_stops(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    value.settle_closed_chunk(fabricated_reader.mint(value)); history = budget.settled_chunk_accounting(value)
    value.reserve_start_slot(7)
    with pytest.raises(budget.DurableCountBudgetRefusal): value.reserve_start_slot(5)
    assert value in budget._FAILED and budget.settled_chunk_accounting(value) is history
    with pytest.raises(budget.DurableCountBudgetRefusal, match="permanently_stopped"): value.reserve_start_slot(8)
    assert len(history[3]) == 1 and len(value._state[2]) == 1


@pytest.mark.parametrize("change", ["record_copy", "account_copy", "view_copy", "reorder", "issuance_copy", "nonce"])
def test_copied_or_reordered_settled_records_cannot_reconstruct_issuance(plan, fabricated_reader, change):
    value = budget.open_durable_count_budget(plan)
    for positions in ((5, 6), (7, 8)):
        for position in positions: value.reserve_start_slot(position)
        value.settle_closed_chunk(fabricated_reader.mint(value))
    current = value._state
    if change == "view_copy":
        budget._SETTLED_VIEWS[value] = tuple(list(budget._SETTLED_VIEWS[value]))
    elif change in ("issuance_copy", "nonce"):
        bank = budget._SETTLEMENT_MINTS[value]; minted = list(bank[2])
        minted[0] = tuple(list(minted[0])) if change == "issuance_copy" else (*minted[0][:4], object())
        budget._SETTLEMENT_MINTS[value] = (*bank[:2], tuple(minted), bank[3])
    else:
        records = list(current[3])
        if change == "record_copy": records[0] = tuple(list(records[0]))
        elif change == "account_copy": records[0] = (*records[0][:4], tuple(list(records[0][4])))
        else: records.reverse()
        updated = (*current[:3], tuple(records), current[4])
        object.__setattr__(value, "_state", updated)
        budget._BUDGETS[value] = value, value._anchor, updated  # Even this copied public binding cannot mint history.
    with pytest.raises(budget.DurableCountBudgetRefusal, match="settled_accounting_changed"):
        budget.settled_chunk_accounting(value)


def test_historical_journal_is_worker_readonly_after_latch_and_no_caller_factory(plan, fabricated_reader):
    value = budget.open_durable_count_budget(plan); value.reserve_start_slot(5); value.reserve_start_slot(6)
    value.settle_closed_chunk(fabricated_reader.mint(value)); history = budget.settled_chunk_accounting(value)
    budget._FAILED.add(value); returned = []
    worker = threading.Thread(target=lambda: returned.append(budget.settled_chunk_accounting(value)))
    worker.start(); worker.join()
    assert returned == [history] and returned[0] is history and value in budget._FAILED
    for supplied in (True, history, object.__new__(budget.DurableCountBudget)):
        with pytest.raises(budget.DurableCountBudgetRefusal): budget.settled_chunk_accounting(supplied)


@pytest.mark.parametrize("kind", ["budget", "ticket"])
@pytest.mark.parametrize("method", ["__hash__", "__eq__"])
def test_changed_exact_class_hash_or_equality_never_executes_in_registry_lookup(plan, monkeypatch, kind, method):
    value = budget.open_durable_count_budget(plan); ticket = value.reserve_start_slot(5)
    calls = []
    def hostile(self, unused=None):
        calls.append(True)
        raise AssertionError("registry lookup invoked caller hash/equality")
    class LookupProbe(dict):
        def get(self, *args, **kwargs):
            calls.append("registry lookup before identity check")
            return super().get(*args, **kwargs)
    registry = "_LOCKS" if kind == "budget" else "_TICKETS"
    monkeypatch.setattr(budget, registry, LookupProbe(getattr(budget, registry)))
    cls = budget.DurableCountBudget if kind == "budget" else budget.CountAttemptTicket
    monkeypatch.setattr(cls, method, hostile)
    actions = (lambda: budget._lock(value), lambda: budget.settled_chunk_accounting(value),
        lambda: value._guard()) if kind == "budget" else (
        lambda: budget.ticket_binding(ticket), lambda: budget.active_ticket_binding(ticket),
        lambda: budget.settled_chunk_accounting(value), lambda: value.reserve_start_slot(6))
    for action in actions:
        with pytest.raises(budget.DurableCountBudgetRefusal): action()
    assert calls == []


def test_original_current_reader_issuance_is_retained_after_reader_expiry(monkeypatch, tmp_path, request):
    # Function-local genuine fixture builders avoid a reverse module-level
    # import cycle. Their external source/file/wire closures remain fake.
    import importlib
    operators = importlib.import_module("test_short_interest_count_durable_transport")
    readers = importlib.import_module("test_short_interest_closed_count_chunk")
    h = operators.operation.__wrapped__(monkeypatch, tmp_path, request)
    h = readers.chunk.__wrapped__(h, monkeypatch)
    from scripts import short_interest_closed_count_chunk as actual_reader
    closed = h.issue()
    original_account = actual_reader.closed_count_chunk_accounting(closed)
    h.budget.settle_closed_chunk(closed)
    original = budget.settled_chunk_accounting(h.budget)
    assert type(closed) is actual_reader.ClosedCountChunk and original[3][0] is original_account
    def expired(*unused): raise AssertionError("old operational reader/source lease expired")
    monkeypatch.setattr(h.coordinator, "terminal_chunk_binding", expired)
    h.tick += 7200
    with pytest.raises(AssertionError, match="expired"): actual_reader.closed_count_chunk_accounting(closed)
    assert budget.settled_chunk_accounting(h.budget) is original
    assert original[3][0] is original_account and original[3][0][4] == tuple(len(h.raw) for unused in h.tickets)
