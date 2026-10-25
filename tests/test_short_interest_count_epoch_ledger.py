"""Fabricated genuine typed plans/inventories, never source observations."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_epoch_ledger as ledger
from research.short_interest_etf import native_dated_class_reference as references
from research.short_interest_etf import native_parallel_count_contract as parallel

spec = importlib.util.spec_from_file_location("epoch_ledger_fabricated_source_factory",
    Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
fabricated = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fabricated
spec.loader.exec_module(fabricated)


def at(seconds):
    return (datetime(2026, 10, 25, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _inventory(plan, count, failed, *, offset, failed_http):
    receipts = []
    for number, query in enumerate(plan._queries.iter_queries(), 1):
        if number > count: break
        body = number != failed
        raw = b"fabricated-two" if body else None
        receipts.append({"query_ordinal": number, "request_sha256": query.to_payload()["request_sha256"],
            "started_at": at(offset + number * 2), "received_at": at(offset + number * 2 + 1),
            "http_attempted": True if body else failed_http, "http_status": 200 if body else None,
            "body_observed": body, "raw_path": f"query-{number:08d}.raw" if body else None,
            "raw_sha256": hash_bytes(raw) if body else None, "raw_bytes": len(raw) if body else None,
            "content_type": "application/json" if body else None,
            "code": "received" if body else "material_request_refused"})
    return parallel.seal_parallel_inventory(plan, tuple(receipts), started_at=at(offset),
        completed_at=at(offset + count * 2 + 2), halted=True)


def fabricated_epoch_inputs(monkeypatch):
    """Small-domain complete typed fixture; no reflective source fabrication."""
    dates = ("2023-01-13", "2023-04-14", "2023-07-14", "2023-10-13", "2024-01-12", "2024-04-12")
    source = fabricated.plan(dates)
    assert len(source.query_plan.to_payload()["selected_query_ordinals"]) == 6
    for name, value in {"ORIGINAL_COUNT": 6, "MAXIMUM_CUMULATIVE_STARTS": 7,
        "MAXIMUM_CUMULATIVE_BYTES": 4 * parallel.MAXIMUM_RESPONSE_BYTES,
        "PARENT_STARTED": 3, "PARENT_HTTP": 2, "PARENT_RAW": 2,
        "RECOVERY_STARTED": 3, "RECOVERY_HTTP": 3, "RECOVERY_RAW": 2,
        "FAILED_PARENT_POSITION": 2, "ANCHOR_PLAN_SHA256": source.sha256}.items():
        monkeypatch.setattr(ledger, name, value)
    parent_plan = parallel.freeze_parallel_count_plan(source.query_plan,
        maximum_total_response_bytes=ledger.MAXIMUM_CUMULATIVE_BYTES)
    parent = _inventory(parent_plan, 3, 2, offset=0, failed_http=False)
    monkeypatch.setattr(ledger, "PARENT_CHARGED_BYTES", parent.to_payload()["charged_response_bytes"])
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    recovery_queries = references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[position - 1] for position in (2, 4, 5, 6)))
    recovery_plan = parallel.freeze_parallel_count_plan(recovery_queries,
        maximum_total_response_bytes=ledger.MAXIMUM_CUMULATIVE_BYTES - ledger.PARENT_CHARGED_BYTES)
    recovery = _inventory(recovery_plan, 3, 3, offset=20, failed_http=True)
    monkeypatch.setattr(ledger, "RECOVERY_CHARGED_BYTES", recovery.to_payload()["charged_response_bytes"])
    pins = tuple(tuple((label, None if expected is None else hash_payload([index, label]))
        for label, expected in row) for index, row in enumerate(ledger._PROOF_PINS))
    monkeypatch.setattr(ledger, "_PROOF_PINS", pins)
    proofs = tuple(tuple((label, value or hash_payload([index, label, "opaque-authenticated-code"]))
        for label, value in row) for index, row in enumerate(pins))
    return source, parent, recovery, proofs


@pytest.fixture
def inputs(monkeypatch): return fabricated_epoch_inputs(monkeypatch)


def epochs_from(inputs):
    source, parent, recovery, proofs = inputs
    return tuple(ledger._seal_registered_epoch_inventory(source, inventory, epoch_id=name, proof_lineage=proof)
        for name, inventory, proof in zip(ledger.EPOCH_IDS, (parent, recovery, None, None), proofs))


def test_every_debit_and_failed_receipt_is_preserved_while_coverage_is_only_transport(inputs):
    source, parent, recovery, unused = inputs
    epochs = epochs_from(inputs)
    result = ledger.seal_registered_count_epoch_ledger(source, epochs)
    value = result.public_summary()
    assert value["START_debits"] == 6 and value["known_HTTP_invocations"] == 5
    assert value["START_based_HTTP_upper_bound"] == 6 and value["recorded_HTTP_flags_complete"]
    assert not value["HTTP_upper_bound_is_observation"] and not value["actual_wire_HTTP_count_established"]
    assert value["recorded_not_invoked_STARTs"] == 1 and value["unknown_body_full_page_START_debits"] == 2
    assert value["unknown_body_full_page_charged_bytes"] == 2 * parallel.MAXIMUM_RESPONSE_BYTES
    assert value["charged_response_bytes"] == parent.to_payload()["charged_response_bytes"] + recovery.to_payload()["charged_response_bytes"]
    assert value["retained_transport_observation_positions"] == 4
    assert value["missing_transport_observation_positions"] == 2 and value["available_historical_STARTs"] == 1
    assert value["minimum_additional_START_allowance_lower_bound"] == 1
    assert value["distinct_started_positions"] == 5 and value["repeated_position_START_debits"] == 1
    assert value["positive_closed_chunk_count"] == 0 and value["registered_spent_epochs"] == 4
    assert not value["original_source_complete"] and not value["any_count_source_qualified"]
    assert all(not value["authority"][name] for name in ("source_admitted", "denominator_admitted",
        "actual_input_execution_admitted", "ready_for_backtest", "trading_authority"))
    assert value["authority"]["outcome_looks"] == value["authority"]["qc_attempts"] == 0
    assert "epochs" not in value and result.sha256 == hash_bytes(canonical_json(result.private_payload()).encode())
    assert not hasattr(result, "iter_cells") and not hasattr(result, "iter_records") and not hasattr(result, "_plan")
    assert all(epoch.private_payload()["epoch_status"] == "authenticated_refused_spent_never_promoted" for epoch in epochs)


def test_positions_are_derived_from_typed_source_query_mapping_not_receipt_numbers(inputs):
    epochs = epochs_from(inputs)
    assert epochs[0]._parts[5] == (1, 2, 3) and epochs[0]._parts[6] == (1, 3)
    assert epochs[1]._parts[5] == (2, 4, 5) and epochs[1]._parts[6] == (2, 4)
    assert epochs[1].private_payload()["retained_position_provenance_sha256"] == hash_payload([2, 4])
    assert "original_positions" not in canonical_json(epochs[1].private_payload())


def test_claim_maximums_are_not_actual_debits_and_zero_spent_epochs_never_refund(inputs):
    source, parent, recovery, unused = inputs
    assert parent._plan.to_payload()["maximum_attempts"] == 6 > 3
    assert recovery._plan.to_payload()["maximum_attempts"] == 4 > 3
    epochs = epochs_from(inputs)
    for epoch in epochs[2:]:
        value = epoch.private_payload()
        assert value["START_debits"] == value["known_HTTP_invocations"] == value["charged_response_bytes"] == 0
        assert value["positive_closed_chunk_count"] == 0 and not value["authority"]["source_admitted"]
    value = ledger.seal_registered_count_epoch_ledger(source, epochs).public_summary()
    assert value["available_historical_STARTs"] == 7 - 6


@pytest.mark.parametrize("mutation", ["hash", "label", "bool", "extra", "list"])
def test_proof_lineage_exact_types_and_registered_roots(inputs, mutation):
    source, parent, unused, proofs = inputs
    proof = list(proofs[0])
    if mutation == "hash": proof[0] = (proof[0][0], "a" * 64)
    elif mutation == "label": proof[0] = ("complete", proof[0][1])
    elif mutation == "bool": proof[0] = (proof[0][0], True)
    elif mutation == "extra": proof.append(("source_admitted", "a" * 64))
    else: proof[0] = list(proof[0])
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="proof_lineage"):
        ledger._seal_registered_epoch_inventory(source, parent, epoch_id="original48", proof_lineage=tuple(proof))


@pytest.mark.parametrize("epoch_id", ["closed-positive-chunk", "new-retry-epoch", True, 1, None])
def test_no_new_epoch_or_positive_chunk_can_be_registered_by_caller(inputs, epoch_id):
    source, parent, unused, proofs = inputs
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="unregistered_epoch"):
        ledger._seal_registered_epoch_inventory(source, parent, epoch_id=epoch_id, proof_lineage=proofs[0])


def test_zero_epoch_cannot_adopt_nonzero_inventory_or_boolean_payload(inputs):
    source, parent, unused, proofs = inputs
    for value in (parent, {"START_debits": 0, "complete": True}, True):
        with pytest.raises(ledger.CountEpochLedgerRefusal):
            ledger._seal_registered_epoch_inventory(source, value, epoch_id="v2zero", proof_lineage=proofs[2])


def test_missing_duplicate_reordered_roster_and_cross_epoch_overlap_fail(inputs):
    source, unused, unused2, unused3 = inputs
    epochs = epochs_from(inputs)
    for supplied in (epochs[:3], (*epochs, epochs[-1]), (epochs[1], epochs[0], *epochs[2:]),
        (epochs[0], epochs[0], *epochs[2:])):
        with pytest.raises(ledger.CountEpochLedgerRefusal): ledger.seal_registered_count_epoch_ledger(source, supplied)
    # The private tuple remains immutable; reflected alteration is not proof.
    original = epochs[1]._parts
    object.__setattr__(epochs[1], "_parts", (*original[:6], (1, 4), *original[7:]))
    with pytest.raises(ledger.CountEpochLedgerRefusal): ledger.seal_registered_count_epoch_ledger(source, epochs)


def test_sealed_factory_forgery_copied_reflection_and_old_registry_casts_fail(inputs):
    source, parent, unused, proofs = inputs
    for cls in (ledger.CountEpochInventory, ledger.CountEpochLedger):
        with pytest.raises(ledger.CountEpochLedgerRefusal): cls()
        empty = object.__new__(cls)
        with pytest.raises(ledger.CountEpochLedgerRefusal): empty.public_summary()
    epochs = epochs_from(inputs)
    forged = object.__new__(ledger.CountEpochInventory)
    object.__setattr__(forged, "_parts", epochs[0]._parts)
    object.__setattr__(forged, "_identity", epochs[0]._identity)
    with pytest.raises(ledger.CountEpochLedgerRefusal): forged.public_summary()
    # Even reanchoring both reflected slots onto the forgery cannot mint it.
    reanchored = (forged, *epochs[0]._parts[1:])
    object.__setattr__(forged, "_parts", reanchored)
    object.__setattr__(forged, "_identity", reanchored)
    with pytest.raises(ledger.CountEpochLedgerRefusal): forged.public_summary()
    for supplied in (parent.to_payload(), {"complete": True}, object()):
        with pytest.raises(ledger.CountEpochLedgerRefusal):
            ledger._seal_registered_epoch_inventory(source, supplied, epoch_id="original48", proof_lineage=proofs[0])


def test_both_reflected_slots_cannot_replace_factory_provenance_or_raw(inputs):
    source = inputs[0]
    epochs = epochs_from(inputs)
    for index, replacement in ((5, (2, 3, 4)), (6, (2, 3)), (7, b"{}")):
        original = epochs[0]._parts
        changed = (*original[:index], replacement, *original[index + 1:])
        object.__setattr__(epochs[0], "_parts", changed)
        object.__setattr__(epochs[0], "_identity", changed)
        with pytest.raises(ledger.CountEpochLedgerRefusal): epochs[0].public_summary()
        object.__setattr__(epochs[0], "_parts", original)
        object.__setattr__(epochs[0], "_identity", original)
    result = ledger.seal_registered_count_epoch_ledger(source, epochs)
    forged = object.__new__(ledger.CountEpochLedger)
    fake_parts = (forged, *result._parts[1:])
    object.__setattr__(forged, "_parts", fake_parts)
    object.__setattr__(forged, "_identity", fake_parts)
    with pytest.raises(ledger.CountEpochLedgerRefusal): forged.public_summary()


def test_disjoint_guard_rejects_genuine_overlapping_retained_contributions(inputs):
    source, parent, recovery, proofs = inputs
    # Alternate fabricated history keeps the exact debit/cardinality totals,
    # but parent position2 is now retained and child contributes position2 too.
    # Both inventories are genuinely sealed; no reflected payload is used.
    overlapping_parent = _inventory(parent._plan, 3, 1, offset=0, failed_http=False)
    epochs = epochs_from((source, overlapping_parent, recovery, proofs))
    assert epochs[0]._parts[6] == (2, 3) and epochs[1]._parts[6] == (2, 4)
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="overlapping_retained"):
        ledger.seal_registered_count_epoch_ledger(source, epochs)


@pytest.mark.parametrize("field,value", [("attempts_started", True), ("http_invocations", True),
    ("charged_response_bytes", True), ("retained_raw_bytes", True), ("halted", False),
    ("complete_frozen_request_sequence", True), ("charged_response_bytes", 0)])
def test_header_flags_bool_counters_or_refunded_debits_are_not_accepted(inputs, monkeypatch, field, value):
    source, parent, unused, proofs = inputs
    original = parallel.ParallelCountInventory.to_payload
    def changed(inventory):
        payload = original(inventory)
        if inventory is parent: payload[field] = value
        return payload
    monkeypatch.setattr(parallel.ParallelCountInventory, "to_payload", changed)
    with pytest.raises(ledger.CountEpochLedgerRefusal):
        ledger._seal_registered_epoch_inventory(source, parent, epoch_id="original48", proof_lineage=proofs[0])


@pytest.mark.parametrize("change", ["drop_failed", "bool_ordinal", "bool_body", "request", "bool_raw_size"])
def test_independent_all_start_replay_rejects_missing_or_changed_receipts(inputs, monkeypatch, change):
    source, parent, unused, proofs = inputs
    original = parallel.ParallelCountInventory.iter_receipts
    def changed(inventory):
        rows = list(original(inventory))
        if inventory is parent:
            if change == "drop_failed": rows.pop(1)
            elif change == "bool_ordinal": rows[0]["query_ordinal"] = True
            elif change == "bool_body": rows[0]["body_observed"] = 1
            elif change == "request": rows[0]["request_sha256"] = "a" * 64
            else: rows[0]["raw_bytes"] = True
        yield from rows
    monkeypatch.setattr(parallel.ParallelCountInventory, "iter_receipts", changed)
    with pytest.raises(ledger.CountEpochLedgerRefusal):
        ledger._seal_registered_epoch_inventory(source, parent, epoch_id="original48", proof_lineage=proofs[0])


def test_start_ceiling_never_increases_for_spent_zero_epochs(inputs, monkeypatch):
    source = inputs[0]
    monkeypatch.setattr(ledger, "MAXIMUM_CUMULATIVE_STARTS", 5)
    epochs = epochs_from(inputs)
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="cumulative_ceiling"):
        ledger.seal_registered_count_epoch_ledger(source, epochs)


def test_authority_profile_is_scope_bound_before_factory(inputs, monkeypatch):
    source, parent, unused, proofs = inputs
    safe = ledger.authority()
    monkeypatch.setattr(ledger, "authority", lambda: {**safe, "source_admitted": True})
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="source_only_authority"):
        ledger._seal_registered_epoch_inventory(source, parent, epoch_id="original48", proof_lineage=proofs[0])


def test_scope_changes_refuse_and_reports_are_detached(inputs, monkeypatch):
    source = inputs[0]
    epochs = epochs_from(inputs)
    result = ledger.seal_registered_count_epoch_ledger(source, epochs)
    raw = result.private_payload(); raw["epochs"][0]["START_debits"] = 0
    assert result.private_payload()["START_debits"] == 6
    monkeypatch.setattr(ledger, "MAXIMUM_CUMULATIVE_STARTS", 8)
    with pytest.raises(ledger.CountEpochLedgerRefusal, match="scope"): result.public_summary()


def test_known_actual_scope_lower_bound_arithmetic_without_source_or_provider_facts():
    assert ledger.MAXIMUM_CUMULATIVE_STARTS == 81_876 and ledger.MAXIMUM_CUMULATIVE_BYTES == 4 * 1024 ** 3
    starts = ledger.PARENT_STARTED + ledger.RECOVERY_STARTED
    retained = ledger.PARENT_RAW + ledger.RECOVERY_RAW
    assert starts == 13_992 and retained == 13_990
    assert ledger.ORIGINAL_COUNT - retained == 67_885
    assert ledger.MAXIMUM_CUMULATIVE_STARTS - starts == 67_884
    assert (ledger.ORIGINAL_COUNT - retained) - (ledger.MAXIMUM_CUMULATIVE_STARTS - starts) == 1
    assert ledger.MAXIMUM_CUMULATIVE_BYTES - ledger.PARENT_CHARGED_BYTES - ledger.RECOVERY_CHARGED_BYTES == 4_271_514_615
    assert all(value is None or ledger._digest(value) for proof in ledger._PROOF_PINS for unused, value in proof)


def test_pure_error_projection_has_no_dynamic_type_messages_or_script_imports():
    class Hostile:
        def __str__(self): pytest.fail("hostile formatting")
        def __eq__(self, unused): pytest.fail("hostile comparison")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile property")
    for error in (ledger.CountEpochLedgerRefusal(Hostile()), ledger.CountEpochLedgerRefusal("REFUSED: SECRET"), Error()):
        assert ledger.failure_summary(error)["contract_code"] is None
        assert "SECRET" not in canonical_json(ledger.failure_summary(error))
    assert ledger.failure_summary(ledger.CountEpochLedgerRefusal("REFUSED: unregistered_epoch_refused"))["contract_code"] == "unregistered_epoch_refused"
    import ast
    tree = ast.parse(Path(ledger.__file__).read_bytes())
    assert all(not (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scripts"))
        for node in ast.walk(tree))
