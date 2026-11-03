"""Pure genuine toy factories, never old footprint or operational authority."""
import ast
import importlib.util
from pathlib import Path
import socket
import sys

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf import native_count_conservative_readmission as basis

spec = importlib.util.spec_from_file_location("conservative_basis_exposure_support",
    Path(__file__).with_name("test_short_interest_count_run13448_exposure.py"))
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


@pytest.fixture(autouse=True)
def isolated_pure_registries_and_network_denied(monkeypatch):
    for owner, pairs in ((basis, (("_MINTS", {}), ("_SCOPES", {}), ("_KEYS", {}),
            ("_ATTEMPTED", set()), ("_FAILED", set()), ("_CURRENT_SCOPE", None))),
        (basis.exposure, (("_MINTS", {}), ("_KEYS", set()), ("_FAILED", set()))),
        (basis.plans, (("_PLAN_MINTS", {}), ("_PLAN_KEYS", set()), ("_BUDGET_MINTS", {})))):
        for name, value in pairs: monkeypatch.setattr(owner, name, value)
    def denied(*args, **kwargs): raise AssertionError("pure basis forbids network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _toy_ledger(monkeypatch):
    """Named synthetic38-query profile; all three original factories execute.

    Production constants reject this toy. Only this explicit policy seam
    binds toy dimensions/hashes, never a caller payload or operational proof.
    """
    ledger = support.toy_ledger(monkeypatch, maximum_bytes=64 * 1024 ** 2)
    support.bind_toy_profile(monkeypatch, ledger)
    exposed = basis.exposure
    old = ledger.public_summary()
    for name, value in {"BASELINE_LEDGER_SHA256": ledger.sha256, "PRIOR_STARTS": old["START_debits"],
            "PRIOR_CHARGED_BYTES": old["charged_response_bytes"], "HISTORICAL_START_CEILING": 9,
            "MAXIMUM_CUMULATIVE_STARTS": exposed.MAXIMUM_STARTS,
            "MAXIMUM_CUMULATIVE_BYTES": exposed.MAXIMUM_BYTES, "MISSING_POSITIONS": exposed.MISSING_POSITIONS,
            "POSITIONS_PER_CHUNK": exposed.POSITIONS_PER_CHUNK, "MAXIMUM_CHUNKS": exposed.CHUNKS}.items():
        monkeypatch.setattr(basis.plans, name, value)
    monkeypatch.setattr(basis, "_EXPECTED_PROFILE", basis._profile())
    monkeypatch.setattr(basis, "POLICY_SHA256", hash_payload(basis.policy()))
    return ledger


@pytest.fixture
def ledger(monkeypatch): return _toy_ledger(monkeypatch)


def test_production_scope_has_exact_arithmetic_unknowns_and_no_source_authority():
    policy = basis.policy(); basis._registered()
    assert hash_payload(policy) == basis.POLICY_SHA256
    p = basis._profile()
    assert p[1] + p[11] == 14000 and p[2] + p[11] * p[12] == 40229897
    assert p[4] - 14000 == 70005 and p[5] - 40229897 == 4254737399
    assert p[13] + (p[8] - 1) * p[14] == 2120
    assert policy["owner_restart_statement"] == "The Mac was restarted"
    assert policy["historical_actuals"] == "UNKNOWN_not_zero"
    assert policy["qualified_coverage_contribution"] == policy["positive_closed_chunk_contribution"] == 0
    assert not policy["old_capability_recreated"] and not policy["old_footprint_or_mounted_epoch_reopened"]
    assert policy["maximum_process_bases"] == 1
    assert policy["authority"]["conservative_negative_basis_only"] is True
    assert all(value is False for name, value in policy["authority"].items()
        if type(value) is bool and name != "conservative_negative_basis_only")
    assert all(value == 0 and type(value) is int for value in policy["authority"].values() if type(value) is int)


def test_unmodified_new_profile_refuses_genuine_toy_before_any_allocation(monkeypatch):
    ledger = support.toy_ledger(monkeypatch, maximum_bytes=64 * 1024 ** 2)
    with pytest.raises((basis.ConservativeReadmissionRefusal, basis.exposure.Run13448ExposureRefusal)):
        basis.freeze_conservative_count_basis(ledger)
    assert not basis._ATTEMPTED and not basis._MINTS and not basis.exposure._MINTS and not basis.plans._PLAN_MINTS


def test_genuine_basis_retains_exact_original_scope_ledger_exposure_and_nine_part_plan(ledger):
    old_raw, old_sha = canonical_json(ledger.private_payload()), ledger.sha256
    value = basis.freeze_conservative_count_basis(ledger); row = basis.conservative_basis_binding(value)
    assert row is value._anchor is value._identity and row[0] is value and row[2] is ledger
    assert type(row[1]) is basis.SourceBasisScope and basis._scope_binding(row[1])[0] is row[1]
    allocated, plan = row[3:5]
    assert basis.exposure.exposure_binding(allocated)[1] is ledger
    assert len(plan._parts) == 9 and plan._parts[1] is ledger and plan._parts[8] is allocated
    report = value.public_summary()
    assert report["initial_START_upper_bound"] == ledger.public_summary()["START_debits"] + 8
    assert report["initial_byte_upper_bound"] == ledger.public_summary()["charged_response_bytes"] + 16777216
    assert report["permanent_unknown_START_upper_debits"] == 8 and report["permanent_unknown_byte_debits"] == 16777216
    assert report["qualified_coverage_contribution"] == report["positive_closed_chunk_contribution"] == 0
    assert report["old_process_exit"] is None and all(v is None for v in report["historical_actual_counts"].values())
    assert report["authority"] == basis.authority() and report["policy_sha256"] == basis.POLICY_SHA256
    assert value.sha256 == hash_payload(report)
    assert allocated.possible_reservation_positions() == tuple(range(5, 13))
    assert plan.chunk_extra_limit(1) == 8 and plan.chunk_extra_limit(2) == 16
    assert plan._parts[4][0] == tuple(allocated.lifetime_try_upper_bound(n) for n in range(1, 39))
    assert canonical_json(ledger.private_payload()) == old_raw and ledger.sha256 == old_sha
    assert not any(hasattr(value, name) for name in ("dispatch", "release", "refund", "retry", "iter_cells", "iter_records"))


def test_returned_report_is_copy_and_can_never_refund_or_certify_actuals(ledger):
    value = basis.freeze_conservative_count_basis(ledger); report = value.public_summary()
    report["permanent_unknown_START_upper_debits"] = report["permanent_unknown_byte_debits"] = 0
    report["historical_actual_counts"]["provider_GET_requests"] = 0
    report["authority"]["SourceAUTH_release"] = True
    original = value.public_summary()
    assert original["permanent_unknown_START_upper_debits"] == 8 and original["permanent_unknown_byte_debits"] == 16777216
    assert original["historical_actual_counts"]["provider_GET_requests"] is None
    assert original["authority"]["SourceAUTH_release"] is False


def test_duplicate_mint_latches_issued_basis_without_releasing_original_allocations(ledger):
    value = basis.freeze_conservative_count_basis(ledger); row = basis.conservative_basis_binding(value)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="already_attempted"):
        basis.freeze_conservative_count_basis(ledger)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()
    assert basis._MINTS[id(value)] is row and basis.exposure.exposure_binding(row[3])[1] is ledger
    assert row[4].budget_profile()["permanent_unknown_byte_debits"] == 16777216


def test_wrong_payload_hostile_and_unissued_types_cannot_enter_factory(ledger):
    class Hostile:
        def __getattribute__(self, name): pytest.fail("hostile property accessed")
        def __hash__(self): pytest.fail("hostile hash")
        def __eq__(self, other): pytest.fail("hostile equality")
    for supplied in (None, True, ledger.sha256, ledger.public_summary(), Hostile(), object.__new__(basis.historical.CountEpochLedger)):
        with pytest.raises((basis.ConservativeReadmissionRefusal, basis.historical.CountEpochLedgerRefusal)):
            basis.freeze_conservative_count_basis(supplied)
    assert not basis._MINTS and not basis._ATTEMPTED
    with pytest.raises(TypeError): basis.freeze_conservative_count_basis(ledger, complete=True)


@pytest.mark.parametrize("cls", [basis.SourceBasisScope, basis.ConservativeCountRecoveryBasis])
def test_scope_and_basis_cannot_be_publicly_constructed(cls):
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="factory_required"): cls()


def test_copied_anchor_reflection_and_original_mutation_restore_cannot_mint_or_revive(ledger):
    value = basis.freeze_conservative_count_basis(ledger); row = value._anchor
    copy = object.__new__(basis.ConservativeCountRecoveryBasis)
    object.__setattr__(copy, "_anchor", row); object.__setattr__(copy, "_identity", row)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="basis_changed"): basis.conservative_basis_binding(copy)
    replacement = tuple(list(row))
    object.__setattr__(value, "_anchor", replacement); object.__setattr__(value, "_identity", replacement)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="basis_changed"): value.public_summary()
    object.__setattr__(value, "_anchor", row); object.__setattr__(value, "_identity", row)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()


@pytest.mark.parametrize("target", ["scope", "exposure", "plan"])
def test_changed_original_component_restoration_never_revives_basis(ledger, target):
    value = basis.freeze_conservative_count_basis(ledger); row = value._anchor
    obj, attribute = (row[1], "_anchor") if target == "scope" else (row[3] if target == "exposure" else row[4], "_parts")
    original = getattr(obj, attribute)
    object.__setattr__(obj, attribute, tuple(list(original)))
    with pytest.raises((basis.ConservativeReadmissionRefusal, basis.exposure.Run13448ExposureRefusal,
            basis.plans.CountRecoveryBudgetRefusal)): value.public_summary()
    object.__setattr__(obj, attribute, original)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()


@pytest.mark.parametrize("field", ["POLICY_SHA256", "_EXPECTED_PROFILE", "_CURRENT_SCOPE"])
def test_policy_or_scope_change_then_restore_cannot_revive_issued_basis(ledger, monkeypatch, field):
    value = basis.freeze_conservative_count_basis(ledger); previous = getattr(basis, field)
    changed = "0" * 64 if field == "POLICY_SHA256" else (() if field == "_EXPECTED_PROFILE" else object())
    monkeypatch.setattr(basis, field, changed)
    with pytest.raises(basis.ConservativeReadmissionRefusal): value.public_summary()
    monkeypatch.setattr(basis, field, previous)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()


def test_factory_producer_substitution_refuses_without_mint_or_unknown_refund(ledger, monkeypatch):
    original = basis.exposure.freeze_run13448_exposure
    monkeypatch.setattr(basis.exposure, "freeze_run13448_exposure", lambda ledger: {"complete": True})
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="producer_changed"):
        basis.freeze_conservative_count_basis(ledger)
    assert not basis._MINTS and not basis._ATTEMPTED
    monkeypatch.setattr(basis.exposure, "freeze_run13448_exposure", original)


def test_partial_original_factory_failure_spends_attempt_and_cannot_be_guessed_again(ledger, monkeypatch):
    # Keep the original callable/code. Exhausting its original finite plan
    # registry makes the genuine factory fail AFTER genuine exposure issuance.
    monkeypatch.setattr(basis.plans, "_PLAN_MINTS", {n: object() for n in range(basis.plans.MAXIMUM_PLANS)})
    with pytest.raises(basis.plans.CountRecoveryBudgetRefusal, match="capacity_exhausted"):
        basis.freeze_conservative_count_basis(ledger)
    assert len(basis.exposure._MINTS) == len(basis._ATTEMPTED) == 1 and not basis._MINTS
    monkeypatch.setattr(basis.plans, "_PLAN_MINTS", {})
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="already_attempted"):
        basis.freeze_conservative_count_basis(ledger)
    assert len(basis.exposure._MINTS) == 1


def test_private_registry_failure_permanently_latches_even_after_restoration(ledger):
    value = basis.freeze_conservative_count_basis(ledger); row = value._anchor
    removed = basis._KEYS.pop(row[7])
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="basis_changed"): value.public_summary()
    basis._KEYS[row[7]] = removed
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()


def test_new_module_has_no_operational_old_resolver_main_or_filesystem_import():
    tree = ast.parse(Path(basis.__file__).read_text())
    imports = {a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"dataclasses", "json", "data.hashing",
        "research.short_interest_etf.native_count_epoch_ledger",
        "research.short_interest_etf.native_count_run13448_exposure",
        "research.short_interest_etf.native_count_recovery_budget"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "exec", "eval", "input"} for node in ast.walk(tree))
    assert "resolve_registered" not in Path(basis.__file__).read_text()
    assert not any(hasattr(basis, name) for name in ("resolve_registered", "Run13448Resolution", "CountSourceLease"))


def test_fixed_failure_summary_never_formats_or_compares_hostile_values():
    class Hostile:
        def __str__(self): pytest.fail("private exception formatting")
        def __eq__(self, other): pytest.fail("private exception equality")
    assert basis.failure_summary(basis.ConservativeReadmissionRefusal(Hostile()))["contract_code"] is None
    assert basis.failure_summary(RuntimeError("PRIVATE_FAKE_VALUE"))["category"] == "unknown_local_error"


def test_reflected_scope_never_substitutes_for_the_original_scope(ledger):
    value = basis.freeze_conservative_count_basis(ledger)
    original = basis.conservative_basis_binding(value)[1]
    reflected = object.__new__(basis.SourceBasisScope)
    object.__setattr__(reflected, "_anchor", original._anchor)
    object.__setattr__(reflected, "_identity", original._anchor)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="scope_changed"):
        basis._scope_binding(reflected)
    assert basis.conservative_basis_binding(value)[1] is original


def test_public_factory_scope_failure_latches_existing_basis_after_restoration(ledger, monkeypatch):
    value = basis.freeze_conservative_count_basis(ledger)
    original = basis.POLICY_SHA256
    monkeypatch.setattr(basis, "POLICY_SHA256", "0" * 64)
    with pytest.raises(basis.ConservativeReadmissionRefusal): basis.freeze_conservative_count_basis(ledger)
    monkeypatch.setattr(basis, "POLICY_SHA256", original)
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="permanently_stopped"): value.public_summary()


def test_wrong_registered_baseline_refuses_before_exposure_factory(ledger, monkeypatch):
    monkeypatch.setattr(basis.plans, "BASELINE_LEDGER_SHA256", "0" * 64)
    monkeypatch.setattr(basis, "_EXPECTED_PROFILE", basis._profile())
    monkeypatch.setattr(basis, "POLICY_SHA256", hash_payload(basis.policy()))
    with pytest.raises(basis.ConservativeReadmissionRefusal, match="baseline_changed"):
        basis.freeze_conservative_count_basis(ledger)
    assert not basis._ATTEMPTED and not basis.exposure._MINTS and not basis.plans._PLAN_MINTS
