"""Small genuine source/epoch factories; no operational source or dispatch."""
import importlib.util
from pathlib import Path
import socket
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_count_recovery_budget as budget
import research.short_interest_etf.native_count_epoch_ledger as historical

spec = importlib.util.spec_from_file_location("fabricated_budget_epoch_support",
    Path(__file__).with_name("test_short_interest_count_epoch_ledger.py"))
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("fabricated pure budget forbids network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def baseline(monkeypatch, maximum_bytes=None):
    """Eight genuine anchors, immutable old6-START debt,4 missing positions."""
    parallel, references = support.parallel, support.references
    page = parallel.MAXIMUM_RESPONSE_BYTES
    ceiling = 7 * page if maximum_bytes is None else maximum_bytes
    dates = ("2023-01-13", "2023-04-14", "2023-07-14", "2023-10-13",
        "2024-01-12", "2024-04-12", "2024-07-12", "2024-10-11")
    source = support.fabricated.plan(dates)
    for name, value in {"ORIGINAL_COUNT": 8, "MAXIMUM_CUMULATIVE_STARTS": 9,
        "MAXIMUM_CUMULATIVE_BYTES": ceiling, "PARENT_STARTED": 3, "PARENT_HTTP": 2,
        "PARENT_RAW": 2, "RECOVERY_STARTED": 3, "RECOVERY_HTTP": 3, "RECOVERY_RAW": 2,
        "FAILED_PARENT_POSITION": 2, "ANCHOR_PLAN_SHA256": source.sha256}.items():
        monkeypatch.setattr(historical, name, value)
    parent_plan = parallel.freeze_parallel_count_plan(source.query_plan, maximum_total_response_bytes=ceiling)
    parent = support._inventory(parent_plan, 3, 2, offset=0, failed_http=False)
    charged_parent = parent.to_payload()["charged_response_bytes"]
    monkeypatch.setattr(historical, "PARENT_CHARGED_BYTES", charged_parent)
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    queries = references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[position - 1] for position in (2, 4, 5, 6, 7, 8)))
    child_plan = parallel.freeze_parallel_count_plan(queries, maximum_total_response_bytes=ceiling - charged_parent)
    child = support._inventory(child_plan, 3, 3, offset=20, failed_http=True)
    monkeypatch.setattr(historical, "RECOVERY_CHARGED_BYTES", child.to_payload()["charged_response_bytes"])
    pins = tuple(tuple((label, None if value is None else hash_payload([index, label]))
        for label, value in row) for index, row in enumerate(historical._PROOF_PINS))
    monkeypatch.setattr(historical, "_PROOF_PINS", pins)
    proofs = tuple(tuple((label, value or "a" * 64) for label, value in row) for row in pins)
    ledger = historical.seal_registered_count_epoch_ledger(source,
        support.epochs_from((source, parent, child, proofs)))
    old = ledger.public_summary()
    for name, value in {"BASELINE_LEDGER_SHA256": ledger.sha256, "PRIOR_STARTS": old["START_debits"],
        "PRIOR_CHARGED_BYTES": old["charged_response_bytes"], "HISTORICAL_START_CEILING": 9,
        "MAXIMUM_CUMULATIVE_STARTS": 14, "MAXIMUM_CUMULATIVE_BYTES": ceiling,
        "MISSING_POSITIONS": 4, "POSITIONS_PER_CHUNK": 2, "MAXIMUM_CHUNKS": 2,
        "EXTRA_ATTEMPTS_PER_CHUNK": 2, "_PLAN_MINTS": {}, "_BUDGET_MINTS": {}, "_PLAN_KEYS": set()}.items():
        monkeypatch.setattr(budget, name, value)
    return ledger


@pytest.fixture
def ledger(monkeypatch): return baseline(monkeypatch)


def test_prospective_plan_derives_missing_positions_and_preserves_old_ledger(ledger):
    old_raw, old_hash = canonical_json(ledger.private_payload()), ledger.sha256
    plan = budget.freeze_count_recovery_plan(ledger)
    assert plan.chunk_positions(1) == (5, 6) and plan.chunk_positions(2) == (7, 8)
    selected = ledger._parts[1].query_plan.to_payload()["selected_query_ordinals"]
    assert plan.chunk_matrix_ordinals(1) == tuple(selected[position - 1] for position in (5, 6))
    value = plan.public_summary()
    assert value["missing_positions"] == 4 and value["chunks"] == value["full_chunks"] == 2
    assert value["maximum_new_slots"] == 8 and value["maximum_extra_slots"] == 4
    assert value["final_chunk_positions"] == 2 and value["final_chunk_maximum_slots"] == 4
    assert value["positive_closed_chunks"] == 0 and not value["historical_ledger_rewritten"]
    assert canonical_json(ledger.private_payload()) == old_raw and ledger.sha256 == old_hash
    assert historical.MAXIMUM_CUMULATIVE_STARTS == 9 and value["maximum_cumulative_STARTs"] == 14
    assert plan.sha256 == hash_bytes(canonical_json(value).encode())
    assert not hasattr(plan, "iter_cells") and not hasattr(plan, "iter_records")


def test_actual_policy_arithmetic_is_finite_and_does_not_raise_old_ceiling():
    assert budget.MISSING_POSITIONS == 67_885 and budget.POSITIONS_PER_CHUNK == 512
    assert divmod(budget.MISSING_POSITIONS, budget.POSITIONS_PER_CHUNK) == (132, 301)
    assert budget.MAXIMUM_CHUNKS * budget.EXTRA_ATTEMPTS_PER_CHUNK == 2_128
    assert budget.PRIOR_STARTS + budget.MISSING_POSITIONS + 2_128 == budget.MAXIMUM_CUMULATIVE_STARTS == 84_005
    assert 301 + budget.EXTRA_ATTEMPTS_PER_CHUNK == 317
    assert historical.MAXIMUM_CUMULATIVE_STARTS == budget.HISTORICAL_START_CEILING == 81_876
    assert budget.MAXIMUM_CUMULATIVE_BYTES == historical.MAXIMUM_CUMULATIVE_BYTES == 4 * 1024 ** 3
    assert 2_128 * budget.MAXIMUM_RESPONSE_BYTES > budget.MAXIMUM_CUMULATIVE_BYTES - budget.PRIOR_CHARGED_BYTES
    policy = budget.policy()
    assert policy["owner_authority"] == "SI-AUTH-20261025-01" and policy["owner_decision"] == "SI-DEC-20261025-06"
    assert not policy["reservation_releases_supported"] and policy["historical_attempts_count_toward_tries"]


def test_final_partial_chunk_uses_actual_descriptor_count_not_full_chunk_cap(ledger, monkeypatch):
    monkeypatch.setattr(budget, "POSITIONS_PER_CHUNK", 3)
    plan = budget.freeze_count_recovery_plan(ledger)
    assert plan.chunk_positions(1) == (5, 6, 7) and plan.chunk_positions(2) == (8,)
    report = plan.public_summary()
    assert report["full_chunks"] == 1 and report["final_chunk_positions"] == 1
    assert report["final_chunk_maximum_slots"] == 3 < 3 + budget.EXTRA_ATTEMPTS_PER_CHUNK
    assert report["maximum_new_slots"] == 8


def test_every_slot_keeps_its_full_page_and_returns_no_dispatch_authority(ledger):
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    first = value.reserve_start_slot(5)
    assert first == {"reservation_ordinal": 1, "chunk_number": 1, "try_number": 2,
        "bytes_reserved": budget.MAXIMUM_RESPONSE_BYTES, "dispatch_authority": False}
    second = value.reserve_start_slot(6)
    assert second["try_number"] == 1 and second["reservation_ordinal"] == 2
    report = value.public_summary()
    assert report["reserved_START_upper_bound"] == 2 and report["actual_STARTs_observed"] == 0
    assert report["full_page_bytes_reserved"] == 2 * budget.MAXIMUM_RESPONSE_BYTES
    assert not report["receipt_durability_adapter_present"]
    assert not any(hasattr(value, name) for name in ("release", "refund", "mark_durable", "complete", "dispatch"))
    assert report["authority"]["dispatch_authority"] is report["authority"]["ready_for_backtest"] is False
    report["full_page_bytes_reserved"] = 0
    assert value.public_summary()["full_page_bytes_reserved"] == 2 * budget.MAXIMUM_RESPONSE_BYTES


def test_full_inflight_reservations_refuse_before_overdraw_and_preserve_journal(ledger):
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    for position in (5, 6, 7, 8): value.reserve_start_slot(position)
    original = value._state
    assert budget.PRIOR_CHARGED_BYTES + 5 * budget.MAXIMUM_RESPONSE_BYTES > budget.MAXIMUM_CUMULATIVE_BYTES
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="full_page_byte_capacity"):
        value.reserve_start_slot(6)
    assert value._state is original and len(original) == 4
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="permanently_stopped"): value.public_summary()


def test_exact_byte_boundary_allows_the_last_whole_page(monkeypatch):
    page = support.parallel.MAXIMUM_RESPONSE_BYTES
    old = baseline(monkeypatch, maximum_bytes=6 * page + 4 * len(b"fabricated-two"))
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(old))
    for position in (5, 6, 7, 8): value.reserve_start_slot(position)
    assert value.public_summary()["cumulative_bytes_reserved_upper_bound"] == budget.MAXIMUM_CUMULATIVE_BYTES
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="full_page_byte_capacity"): value.reserve_start_slot(6)


@pytest.mark.parametrize("position", [True, 1.0, "5", None, 0, 1, 9])
def test_invalid_or_already_retained_position_latches_permanent_stop(ledger, position):
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="exact_missing_position"): value.reserve_start_slot(position)
    assert value._state == ()
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="permanently_stopped"): value.reserve_start_slot(5)


def test_historical_attempts_count_and_fresh_coordinator_cannot_reset(ledger):
    plan = budget.freeze_count_recovery_plan(ledger); value = budget.open_conservative_count_budget(plan)
    assert value.reserve_start_slot(5)["try_number"] == 2
    assert value.reserve_start_slot(5)["try_number"] == 3
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="total_try_allowance"): value.reserve_start_slot(5)
    assert len(value._state) == 2
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="plan_coordinator_already"): budget.open_conservative_count_budget(plan)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="baseline_plan_already"): budget.freeze_count_recovery_plan(ledger)


def test_second_extra_slot_refuses_even_when_try_and_byte_caps_fit(ledger, monkeypatch):
    monkeypatch.setattr(budget, "EXTRA_ATTEMPTS_PER_CHUNK", 1)
    monkeypatch.setattr(budget, "MAXIMUM_CUMULATIVE_STARTS", 12)
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    value.reserve_start_slot(6); value.reserve_start_slot(6)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="chunk_extra_allowance"): value.reserve_start_slot(6)
    assert len(value._state) == 2


def test_chunk_slots_and_historical_tries_are_independent_limits(ledger):
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    for position in (5, 5, 6, 6): value.reserve_start_slot(position)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="chunk_START_allowance"): value.reserve_start_slot(6)
    assert len(value._state) == 4


@pytest.mark.parametrize("chunk", [True, 0, -1, 3, 1.0, "1"])
def test_exact_chunk_number_required(ledger, chunk):
    plan = budget.freeze_count_recovery_plan(ledger)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="chunk_number"): plan.chunk_positions(chunk)


def test_fake_payload_copied_fields_or_reflected_states_do_not_mint_or_reset(ledger):
    for supplied in (ledger.public_summary(), True, object(), object.__new__(historical.CountEpochLedger)):
        with pytest.raises((budget.CountRecoveryBudgetRefusal, historical.CountEpochLedgerRefusal)):
            budget.freeze_count_recovery_plan(supplied)
    plan = budget.freeze_count_recovery_plan(ledger)
    fake = object.__new__(budget.CountRecoveryPlan)
    parts = (fake, *plan._parts[1:])
    object.__setattr__(fake, "_parts", parts); object.__setattr__(fake, "_identity", parts)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="sealed_plan"): fake.public_summary()
    value = budget.open_conservative_count_budget(plan); value.reserve_start_slot(5); original = value._state
    object.__setattr__(value, "_state", ())
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="sealed_coordinator"): value.reserve_start_slot(6)
    object.__setattr__(value, "_state", original)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="permanently_stopped"): value.public_summary()
    assert budget._BUDGET_MINTS[id(value)][2] is original


def test_constructors_uninitialized_and_copied_coordinator_fields_are_not_authority(ledger):
    for cls in (budget.CountRecoveryPlan, budget.ConservativeCountBudget):
        with pytest.raises(budget.CountRecoveryBudgetRefusal): cls()
        with pytest.raises(budget.CountRecoveryBudgetRefusal): object.__new__(cls).public_summary()
    value = budget.open_conservative_count_budget(budget.freeze_count_recovery_plan(ledger))
    forged = object.__new__(budget.ConservativeCountBudget)
    for name in ("_anchor", "_identity", "_state"): object.__setattr__(forged, name, getattr(value, name))
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="sealed_coordinator"): forged.reserve_start_slot(5)
    assert value.public_summary()["reserved_START_upper_bound"] == 0


def test_baseline_pin_and_false_authority_are_checked_before_factory(ledger, monkeypatch):
    monkeypatch.setattr(budget, "BASELINE_LEDGER_SHA256", "a" * 64)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="baseline_ledger_changed"):
        budget.freeze_count_recovery_plan(ledger)
    monkeypatch.setattr(budget, "BASELINE_LEDGER_SHA256", ledger.sha256)
    safe = budget.authority()
    monkeypatch.setattr(budget, "authority", lambda: {**safe, "dispatch_authority": True})
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="source_only_policy"):
        budget.freeze_count_recovery_plan(ledger)


def test_policy_scope_and_finite_capacity_are_checked(ledger, monkeypatch):
    monkeypatch.setattr(budget, "MAXIMUM_PLANS", 0)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="finite_plan_capacity"): budget.freeze_count_recovery_plan(ledger)
    monkeypatch.setattr(budget, "MAXIMUM_PLANS", 4)
    monkeypatch.setattr(budget, "MAXIMUM_COORDINATORS", 0)
    plan = budget.freeze_count_recovery_plan(ledger)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="finite_coordinator_capacity"):
        budget.open_conservative_count_budget(plan)
    monkeypatch.setattr(budget, "POSITIONS_PER_CHUNK", 3)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="scope"): plan.public_summary()


@pytest.mark.parametrize("name,value", [("POSITIONS_PER_CHUNK", 0), ("EXTRA_ATTEMPTS_PER_CHUNK", True),
    ("MAXIMUM_CUMULATIVE_BYTES", float("inf")), ("MAXIMUM_CHUNKS", -1),
    ("MAXIMUM_CUMULATIVE_STARTS", 84_006), ("EXTRA_ATTEMPTS_PER_CHUNK", 17),
    ("MAXIMUM_TOTAL_TRIES_PER_POSITION", 4), ("MAXIMUM_CUMULATIVE_BYTES", 4 * 1024 ** 3 + 1)])
def test_invalid_policy_numbers_refuse_without_mutating_old_ledger(ledger, monkeypatch, name, value):
    digest = ledger.sha256; monkeypatch.setattr(budget, name, value)
    with pytest.raises(budget.CountRecoveryBudgetRefusal, match="policy_bounds"): budget.freeze_count_recovery_plan(ledger)
    assert ledger.sha256 == digest


def test_safe_error_projection_has_no_formatting_or_dynamic_exception_content():
    class Hostile:
        def __str__(self): pytest.fail("hostile formatting")
        def __eq__(self, unused): pytest.fail("hostile comparison")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile attribute")
    for error in (budget.CountRecoveryBudgetRefusal(Hostile()), budget.CountRecoveryBudgetRefusal("REFUSED: SECRET"), Error()):
        assert budget.failure_summary(error)["contract_code"] is None
        assert "SECRET" not in canonical_json(budget.failure_summary(error))
    assert budget.failure_summary(budget.CountRecoveryBudgetRefusal("REFUSED: full_page_byte_capacity_exhausted"))["contract_code"] == "full_page_byte_capacity_exhausted"
