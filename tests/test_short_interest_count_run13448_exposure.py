"""Genuine small typed B3 factories with explicit toy-profile seams only.

No operational source/native/file/capture witness is fabricated or invoked.
The production profile rejects these toy ledgers before the named seam binds.
"""
import ast
import importlib.util
from pathlib import Path
import socket
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_run13448_exposure as exposure
from research.short_interest_etf import native_count_epoch_ledger as historical

spec = importlib.util.spec_from_file_location("run13448_exposure_epoch_support",
    Path(__file__).with_name("test_short_interest_count_epoch_ledger.py"))
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


@pytest.fixture(autouse=True)
def isolated_and_network_denied(monkeypatch):
    for name, value in (("_MINTS", {}), ("_KEYS", set()), ("_FAILED", set())):
        monkeypatch.setattr(exposure, name, value)
    def denied(*args, **kwargs): raise AssertionError("pure exposure forbids network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def toy_ledger(monkeypatch, *, repeated_unknown=False, maximum_bytes=None):
    """Genuine synthetic anchors and six debits, never operational evidence.

    Default:16 one-class anchors. The explicit larger-byte integration fixture
    uses38 two-class anchors so its genuine parallel plan can bind64MiB.
    """
    dates = ("2022-01-14", "2022-04-14", "2022-07-14", "2022-10-14",
        "2023-01-13", "2023-04-14", "2023-07-14", "2023-10-13",
        "2024-01-12", "2024-04-12", "2024-07-12", "2024-10-11",
        "2025-01-10", "2025-04-11", "2025-07-11", "2025-10-10")
    if maximum_bytes is None:
        source = support.fabricated.plan(dates)
        source_count = 16
    else:
        dates += ("2026-01-09", "2026-04-10", "2026-07-10")
        source = support.fabricated.plan(dates,
            reports=tuple(support.fabricated.identity(at, alt=True) for at in dates),
            cells=tuple((ticker, at) for at in dates for ticker in ("SYN", "ALT")))
        source_count = 38
    assert len(source.query_plan.to_payload()["selected_query_ordinals"]) == source_count
    # Fits both genuine small query plans and the permanent eight-page debt;
    # this is a pure allocation fixture, not an operational recovery budget.
    maximum_bytes = 24 * 1024 ** 2 if maximum_bytes is None else maximum_bytes
    for name, value in {"ORIGINAL_COUNT": source_count, "MAXIMUM_CUMULATIVE_STARTS": 9,
        "MAXIMUM_CUMULATIVE_BYTES": maximum_bytes, "PARENT_STARTED": 3, "PARENT_HTTP": 2,
        "PARENT_RAW": 2, "RECOVERY_STARTED": 3, "RECOVERY_HTTP": 3, "RECOVERY_RAW": 2,
        "FAILED_PARENT_POSITION": 2, "ANCHOR_PLAN_SHA256": source.sha256}.items():
        monkeypatch.setattr(historical, name, value)
    parent_plan = support.parallel.freeze_parallel_count_plan(source.query_plan,
        maximum_total_response_bytes=maximum_bytes)
    parent = support._inventory(parent_plan, 3, 2, offset=0, failed_http=False)
    charged_parent = parent.to_payload()["charged_response_bytes"]
    monkeypatch.setattr(historical, "PARENT_CHARGED_BYTES", charged_parent)
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    queries = support.references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[position - 1] for position in (2, *range(4, source_count + 1))))
    child_plan = support.parallel.freeze_parallel_count_plan(queries,
        maximum_total_response_bytes=maximum_bytes - charged_parent)
    child = support._inventory(child_plan, 3, 1 if repeated_unknown else 3, offset=20, failed_http=True)
    monkeypatch.setattr(historical, "RECOVERY_CHARGED_BYTES", child.to_payload()["charged_response_bytes"])
    pins = tuple(tuple((label, None if value is None else hash_payload([index, label]))
        for label, value in row) for index, row in enumerate(historical._PROOF_PINS))
    monkeypatch.setattr(historical, "_PROOF_PINS", pins)
    proofs = tuple(tuple((label, value or "a" * 64) for label, value in row) for row in pins)
    return historical.seal_registered_count_epoch_ledger(source,
        support.epochs_from((source, parent, child, proofs)))


def bind_toy_profile(monkeypatch, ledger):
    """Named profile/policy seam; unmodified production still rejects this B3."""
    old = ledger.public_summary()
    missing = old["missing_transport_observation_positions"]
    chunks = (missing + 7) // 8
    values = {"BASELINE_LEDGER_SHA256": ledger.sha256, "PRIOR_STARTS": old["START_debits"],
        "PRIOR_CHARGED_BYTES": old["charged_response_bytes"], "HISTORICAL_START_CEILING": 9,
        "MAXIMUM_STARTS": old["START_debits"] + 8 + missing + 8 + (chunks - 1) * 16,
        "MAXIMUM_BYTES": historical.MAXIMUM_CUMULATIVE_BYTES,
        "MISSING_POSITIONS": missing, "POSITIONS_PER_CHUNK": 8, "CHUNKS": chunks}
    for name, value in values.items(): monkeypatch.setattr(exposure, name, value)
    monkeypatch.setattr(exposure, "_EXPECTED_PROFILE", exposure._profile())
    monkeypatch.setattr(exposure, "POLICY_SHA256", hash_payload(exposure.policy()))


@pytest.fixture
def ledger(monkeypatch):
    value = toy_ledger(monkeypatch); bind_toy_profile(monkeypatch, value); return value


def test_production_arithmetic_and_false_authority_are_exact():
    policy = exposure.policy()
    assert exposure.registered_sha256() == hash_payload(policy)
    assert exposure.PRIOR_STARTS + exposure.EXPOSURE_SLOTS == 14000
    assert exposure.PRIOR_CHARGED_BYTES + exposure.EXPOSURE_SLOTS * exposure.PAGE_BYTES == 40229897
    assert exposure.MAXIMUM_STARTS - 14000 == 70005
    assert exposure.MAXIMUM_BYTES - 40229897 == 4254737399
    assert exposure.FIRST_CHUNK_FUTURE_EXTRAS + 132 * exposure.LATER_CHUNK_FUTURE_EXTRAS == 2120
    assert policy["owner_authority"] == "SI-AUTH-20261028-02"
    assert policy["owner_decision"] == "SI-DEC-20261028-01"
    assert policy["qualified_coverage_contribution"] == 0 and policy["forensic_witness_required_separately"]
    assert policy["historical_actual_counts"] == "UNKNOWN_not_zero"
    assert policy["allocation_release_or_settlement"] == "never" and not policy["old_ledger_rewritten"]
    for name, value in policy["authority"].items():
        assert value is (True if name == "negative_allocation_only" else False) if type(value) is bool else value == 0


def test_unmodified_production_profile_rejects_genuine_toy_ledger(monkeypatch):
    value = toy_ledger(monkeypatch)
    with pytest.raises(exposure.Run13448ExposureRefusal): exposure.freeze_run13448_exposure(value)
    assert not exposure._MINTS and not exposure._KEYS


def test_missing_mapping_possible_tries_and_permanent_debits_derive_from_genuine_ledger(ledger):
    before, digest = canonical_json(ledger.private_payload()), ledger.sha256
    value = exposure.freeze_run13448_exposure(ledger)
    parts = exposure.exposure_binding(value)
    assert parts is value._parts is value._identity and parts[0] is value and parts[1] is ledger
    assert parts[2] == tuple(range(5, 17)) and value.possible_reservation_positions() == tuple(range(5, 13))
    assert value.lifetime_try_upper_bound(5) == 2
    assert all(value.lifetime_try_upper_bound(position) == 1 for position in range(6, 13))
    assert all(value.lifetime_try_upper_bound(position) == 0 for position in range(13, 17))
    assert value.future_extra_allowance(1) == 8 and value.future_extra_allowance(2) == 16
    assert parts[5] == (8, 16) and parts[7] == exposure.registered_sha256()
    assert value.sha256 == hash_bytes(parts[6])
    report = value.public_summary()
    assert report["permanent_unknown_START_upper_debits"] == 8
    assert report["permanent_unknown_byte_debits"] == 16777216
    assert report["budget_counted_START_upper_bound"] == ledger.public_summary()["START_debits"] + 8
    assert report["budget_counted_byte_upper_bound"] == ledger.public_summary()["charged_response_bytes"] + 16777216
    assert report["maximum_future_extra_slots"] == 24
    assert report["qualified_coverage_contribution"] == report["positive_closed_chunk_contribution"] == 0
    assert all(item is None for item in report["historical_actual_counts"].values())
    assert not report["forensic_witness_authenticated"] and not report["allocation_is_operational_resolution"]
    assert canonical_json(ledger.private_payload()) == before and ledger.sha256 == digest
    assert not any(hasattr(value, name) for name in ("refund", "release", "settle", "dispatch", "iter_cells", "iter_records"))


def test_possible_try_must_leave_one_required_capture_try(monkeypatch):
    value = toy_ledger(monkeypatch, repeated_unknown=True); bind_toy_profile(monkeypatch, value)
    assert value._parts[2][0]._parts[5].count(2) == value._parts[2][1]._parts[5].count(2) == 1
    with pytest.raises(exposure.Run13448ExposureRefusal, match="required_future_try_unavailable"):
        exposure.freeze_run13448_exposure(value)
    assert not exposure._MINTS and not exposure._KEYS


def test_larger_integration_fixture_preserves_genuine_query_and_byte_bounds(monkeypatch):
    value = toy_ledger(monkeypatch, maximum_bytes=64 * 1024 ** 2)
    bind_toy_profile(monkeypatch, value)
    result = exposure.freeze_run13448_exposure(value)
    assert len(exposure.exposure_binding(result)[4]) == 38
    assert result.public_summary()["missing_positions"] == 34
    assert result.public_summary()["remaining_byte_capacity"] >= 8 * exposure.PAGE_BYTES
    assert result.possible_reservation_positions() == tuple(range(5, 13))


def test_caller_report_mutation_cannot_refund_or_certify_actuals(ledger):
    value = exposure.freeze_run13448_exposure(ledger); report = value.public_summary()
    report["permanent_unknown_byte_debits"] = 0
    report["historical_actual_counts"]["provider_GET_requests"] = 0
    report["authority"]["SourceAUTH_release"] = True
    again = value.public_summary()
    assert again["permanent_unknown_byte_debits"] == 16777216
    assert again["historical_actual_counts"]["provider_GET_requests"] is None
    assert not again["authority"]["SourceAUTH_release"]
    with pytest.raises(exposure.Run13448ExposureRefusal, match="already_minted"):
        exposure.freeze_run13448_exposure(ledger)


def test_payload_hash_complete_flag_or_hostile_object_is_not_a_genuine_ledger(ledger):
    class Hostile:
        def __getattribute__(self, unused): pytest.fail("hostile property accessed")
        def __str__(self): pytest.fail("hostile formatting")
        def __hash__(self): pytest.fail("hostile hash")
    for supplied in (ledger.public_summary(), ledger.sha256, True, Hostile(), object.__new__(historical.CountEpochLedger)):
        with pytest.raises((exposure.Run13448ExposureRefusal, historical.CountEpochLedgerRefusal)):
            exposure.freeze_run13448_exposure(supplied)
    with pytest.raises(TypeError): exposure.freeze_run13448_exposure(ledger, complete=True)
    assert not exposure._MINTS


def test_forged_copied_reflected_allocations_and_restored_mutations_remain_refused(ledger):
    with pytest.raises(exposure.Run13448ExposureRefusal, match="factory_required"): exposure.Run13448Exposure()
    value = exposure.freeze_run13448_exposure(ledger)
    forged = object.__new__(exposure.Run13448Exposure)
    object.__setattr__(forged, "_parts", value._parts); object.__setattr__(forged, "_identity", value._parts)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="allocation_changed"): forged.public_summary()
    original = value._parts
    changed = (*original[:3], (), *original[4:])
    object.__setattr__(value, "_parts", changed); object.__setattr__(value, "_identity", changed)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="allocation_changed"): value.public_summary()
    object.__setattr__(value, "_parts", original); object.__setattr__(value, "_identity", original)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="permanently_stopped"): value.public_summary()
    assert exposure._MINTS[id(value)] is original


@pytest.mark.parametrize("position", [True, 0, -1, 17, "5", 5.0])
def test_invalid_position_permanently_latches_without_releasing_allocations(ledger, position):
    value = exposure.freeze_run13448_exposure(ledger)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="exact_position_required"):
        value.lifetime_try_upper_bound(position)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="permanently_stopped"): value.public_summary()


@pytest.mark.parametrize("chunk", [True, 0, 3, "1", 1.0])
def test_invalid_chunk_permanently_latches(ledger, chunk):
    value = exposure.freeze_run13448_exposure(ledger)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="exact_chunk_required"): value.future_extra_allowance(chunk)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="permanently_stopped"): value.public_summary()


@pytest.mark.parametrize("name,bad", [("EXPOSURE_SLOTS", 0), ("EXPOSURE_SLOTS", True),
    ("EXPOSURE_SLOTS", 9), ("MAXIMUM_STARTS", 84006), ("MAXIMUM_BYTES", 4294967297),
    ("MAXIMUM_LIFETIME_TRIES", 4), ("FIRST_CHUNK_FUTURE_EXTRAS", 16)])
def test_scope_drift_refuses_before_mutating_ledger(ledger, monkeypatch, name, bad):
    before = ledger.sha256; monkeypatch.setattr(exposure, name, bad)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="profile_changed"):
        exposure.freeze_run13448_exposure(ledger)
    assert ledger.sha256 == before and not exposure._MINTS


def test_registered_policy_and_issued_scope_cannot_be_changed_then_restored(ledger, monkeypatch):
    value = exposure.freeze_run13448_exposure(ledger); original = exposure.POLICY_SHA256
    monkeypatch.setattr(exposure, "POLICY_SHA256", "0" * 64)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="policy_unregistered"): value.public_summary()
    monkeypatch.setattr(exposure, "POLICY_SHA256", original)
    with pytest.raises(exposure.Run13448ExposureRefusal, match="permanently_stopped"): value.public_summary()


def test_changed_authority_and_hostile_exception_values_are_not_accepted(ledger, monkeypatch):
    original = exposure.authority()
    monkeypatch.setattr(exposure, "authority", lambda: {**original, "SourceAUTH_release": True})
    with pytest.raises(exposure.Run13448ExposureRefusal, match="authority_changed"):
        exposure.freeze_run13448_exposure(ledger)
    class Hostile:
        def __str__(self): pytest.fail("secret formatting")
        def __eq__(self, unused): pytest.fail("secret comparison")
    assert exposure.failure_summary(exposure.Run13448ExposureRefusal(Hostile()))["contract_code"] is None
    assert exposure.failure_summary(RuntimeError("PRIVATE_SECRET"))["category"] == "unknown_local_error"


def test_pure_model_imports_no_scripts_filesystem_source_or_dispatch_module():
    tree = ast.parse(Path(exposure.__file__).read_text())
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"dataclasses", "json", "re", "data.hashing",
        "research.short_interest_etf.native_count_epoch_ledger"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "eval", "exec", "input"} for node in ast.walk(tree))
