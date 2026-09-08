from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import pickle
import signal
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest

import research.analyst_revisions_v2.power_calibration_receipt as receipt_module
import research.analyst_revisions_v2.stock_power_successor as module
import tests.analyst_revisions_v2.test_power_calibration_receipt as receipt_helpers
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    load_global_benchmark_contract,
)
from research.analyst_revisions_v2.power_calibration_protocol import (
    TEST_SESSION_CAPACITY,
    ProvisionalPowerDisposition,
)


SPEC_ROOT = receipt_helpers.SPEC_ROOT
PARENT_FILENAMES = receipt_helpers.b2_helpers.PARENT_FILENAMES

ACCEPTED_ANCESTOR_FILENAMES = (
    PARENT_FILENAMES["base"],
    PARENT_FILENAMES["plan"],
    PARENT_FILENAMES["stock"],
    PARENT_FILENAMES["folds"],
    PARENT_FILENAMES["map"],
    PARENT_FILENAMES["matched"],
    PARENT_FILENAMES["successor"],
    PARENT_FILENAMES["protocol"],
    PARENT_FILENAMES["overlay"],
    PARENT_FILENAMES["look_authority"],
    PARENT_FILENAMES["schema"],
    receipt_helpers.b2_helpers.ADMISSION_FILENAME,
    receipt_helpers.CONTENT_CONTRACT_FILENAME,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _render(value: object) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _rehash_successor(raw: dict[str, object]) -> None:
    raw["spec_id"] = None
    raw["spec_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["spec_hash"] = digest
    raw["spec_id"] = module.ID_PREFIX + digest[:16]


def _rehash_power_amendment(raw: dict[str, object]) -> None:
    _rehash_successor(raw)


def _load_stock_contract() -> GlobalBenchmarkContract:
    names = PARENT_FILENAMES
    return load_global_benchmark_contract(
        map_path=SPEC_ROOT / names["map"],
        matched_contract_path=SPEC_ROOT / names["matched"],
        successor_spec_path=SPEC_ROOT / names["successor"],
        parent_stock_spec_path=SPEC_ROOT / names["stock"],
        fold_manifest_path=SPEC_ROOT / names["folds"],
        qc_first_plan_path=SPEC_ROOT / names["plan"],
    )


@dataclass(frozen=True)
class _Parents:
    receipt_parents: object
    stock_contract: GlobalBenchmarkContract


@dataclass(frozen=True)
class _PersistedReceipt:
    inputs: object
    path: Path
    value: receipt_module.PowerCalibrationReceipt


@dataclass(frozen=True)
class _LoadedSuccessor:
    receipt: _PersistedReceipt
    path: Path
    value: module.StockPowerSuccessor


@pytest.fixture(scope="module")
def parents() -> _Parents:
    return _Parents(
        receipt_parents=receipt_helpers.parents.__wrapped__(),
        stock_contract=_load_stock_contract(),
    )


def _persisted_receipt(
    root: Path,
    parents: _Parents,
    *,
    beta_document: dict[str, object] | None = None,
    component_document: dict[str, object] | None = None,
) -> _PersistedReceipt:
    inputs = receipt_helpers._write_authorized_inputs(
        root,
        parents.receipt_parents,
        beta_document=beta_document,
        component_document=component_document,
    )
    computed = receipt_helpers._compute(parents.receipt_parents, inputs)
    path = receipt_module.persist_power_calibration_receipt(
        computed,
        root / receipt_module.power_calibration_receipt_filename(computed),
    )
    return _PersistedReceipt(inputs=inputs, path=path, value=computed)


def _render_successor(parents: _Parents, receipt: _PersistedReceipt) -> str:
    source = parents.receipt_parents
    return module.render_stock_power_successor(
        stock_contract=parents.stock_contract,
        power_protocol=source.protocol,
        multiplicity_overlay=source.overlay,
        power_receipt=receipt.value,
    )


def _load_successor(
    path: Path, parents: _Parents, receipt: _PersistedReceipt
) -> module.StockPowerSuccessor:
    source = parents.receipt_parents
    return module.load_stock_power_successor(
        path,
        stock_contract=parents.stock_contract,
        power_protocol=source.protocol,
        multiplicity_overlay=source.overlay,
        power_receipt=receipt.value,
    )


def _loaded_successor(root: Path, parents: _Parents) -> _LoadedSuccessor:
    receipt = _persisted_receipt(root, parents)
    path = root / "stock-power-successor-v3.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    value = _load_successor(path, parents, receipt)
    return _LoadedSuccessor(receipt=receipt, path=path, value=value)


def test_feasible_successor_binds_only_exact_power_amendment_and_stays_inert(
    tmp_path: Path, parents: _Parents
):
    loaded = _loaded_successor(tmp_path, parents)
    successor = loaded.value
    receipt = loaded.receipt.value
    raw = json.loads(loaded.path.read_bytes())
    amendment = raw["power_amendment"]

    assert set(amendment) == set(module._POWER_AMENDMENT_FIELDS)
    assert amendment == {
        "calibration_input_manifest_sha256": receipt.manifest_artifact_sha256,
        "numeric_power_receipt_sha256": hashlib.sha256(
            loaded.receipt.path.read_bytes()
        ).hexdigest(),
        "power_plan_sha256": receipt.receipt_hash,
        "required_valid_dates": receipt.required_valid_dates,
        "required_connected_components": receipt.required_connected_components,
        "fixed_capacity_disposition": receipt.disposition.value,
    }
    assert successor.power_plan_sha256 == receipt.receipt_hash
    assert successor.numeric_power_receipt_id == receipt.receipt_id
    assert successor.numeric_power_receipt_content_sha256 == receipt.receipt_hash
    assert successor.numeric_power_receipt_sha256 == hashlib.sha256(
        loaded.receipt.path.read_bytes()
    ).hexdigest()
    assert (
        successor.calibration_input_manifest_sha256
        == receipt.manifest_artifact_sha256
    )
    assert successor.power_plan_bound is True
    assert successor.status == module.FEASIBLE_STATUS
    assert successor.fixed_design_feasible is True
    assert successor.hard_no_launch is False
    assert set(successor.capabilities) == set(module._CAPABILITIES)
    assert all(value is False for value in successor.capabilities.values())
    assert successor.source_access_available is False
    assert successor.outcome_access_available is False
    assert successor.qc_action_available is False
    assert successor.result_access_available is False
    assert successor.result_disposition_available is False
    assert successor.deployment_available is False
    assert successor.orders_available is False
    assert successor.trading_available is False
    assert successor.launch_authorized is False
    assert module.require_loaded_stock_power_successor(successor) is successor


def test_successor_content_identity_and_render_are_deterministic(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    first = _render_successor(parents, receipt).encode("utf-8")
    second = _render_successor(parents, receipt).encode("utf-8")
    raw = json.loads(first)
    declared_id = raw["spec_id"]
    declared_hash = raw["spec_hash"]
    raw["spec_id"] = None
    raw["spec_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()

    assert first == second
    assert first == _render(json.loads(first))
    assert declared_hash == digest
    assert declared_id == module.ID_PREFIX + digest[:16]


def test_exact_bindings_and_deliberately_incomplete_direct_parent_projection(
    tmp_path: Path, parents: _Parents
):
    loaded = _loaded_successor(tmp_path, parents)
    raw = json.loads(loaded.path.read_bytes())
    bindings = raw["direct_parent_bindings"]
    projection = loaded.value.direct_parent_projection
    expected_roles = (
        "stock_successor_v2",
        "power_calibration_protocol",
        "four_family_multiplicity_overlay",
        "numeric_power_receipt",
    )

    assert bindings["stock_successor_v2"] == {
        "artifact_id": parents.stock_contract.successor_spec_id,
        "content_sha256": parents.stock_contract.successor_spec_hash,
        "artifact_sha256": hashlib.sha256(
            (SPEC_ROOT / PARENT_FILENAMES["successor"]).read_bytes()
        ).hexdigest(),
    }
    assert bindings["power_calibration_protocol"] == {
        "artifact_id": parents.receipt_parents.protocol.protocol_id,
        "content_sha256": parents.receipt_parents.protocol.protocol_hash,
        "artifact_sha256": hashlib.sha256(
            (SPEC_ROOT / PARENT_FILENAMES["protocol"]).read_bytes()
        ).hexdigest(),
    }
    assert bindings["four_family_multiplicity_overlay"] == {
        "artifact_id": parents.receipt_parents.overlay.overlay_id,
        "content_sha256": parents.receipt_parents.overlay.overlay_hash,
        "artifact_sha256": hashlib.sha256(
            (SPEC_ROOT / PARENT_FILENAMES["overlay"]).read_bytes()
        ).hexdigest(),
    }
    assert bindings["numeric_power_receipt"] == {
        "artifact_id": loaded.receipt.value.receipt_id,
        "content_sha256": loaded.receipt.value.receipt_hash,
        "artifact_sha256": hashlib.sha256(
            loaded.receipt.path.read_bytes()
        ).hexdigest(),
    }
    assert set(bindings) == set(expected_roles)
    assert projection == {"stock_successor_v3": expected_roles}
    declared = raw["direct_parent_projection"]
    assert declared["projection_scope"] == (
        "stock_successor_v3_direct_edges_only_not_complete_ancestry"
    )
    assert declared["complete_ancestry_graph"] is False
    assert declared["ordered_direct_parent_nodes"] == list(expected_roles)
    assert declared["ordered_direct_edges"] == [
        {"child": "stock_successor_v3", "parent": parent}
        for parent in expected_roles
    ]
    assert declared["parent_subgraphs"] == (
        "authenticated_by_each_parent_loader_and_deliberately_not_redeclared"
    )


def test_direct_parent_edge_contract_has_no_mutable_nested_state():
    expected = tuple(
        ("stock_successor_v3", parent)
        for parent in module._DIRECT_PARENT_ROLES
    )

    assert module._DIRECT_PARENT_EDGES == expected
    assert all(type(edge) is tuple for edge in module._DIRECT_PARENT_EDGES)


def test_compute_only_receipt_cannot_supply_a_persisted_artifact_binding(
    tmp_path: Path, parents: _Parents
):
    inputs = receipt_helpers._write_authorized_inputs(
        tmp_path, parents.receipt_parents
    )
    computed = receipt_helpers._compute(parents.receipt_parents, inputs)
    with pytest.raises(module.StockPowerSuccessorError, match="direct-parent"):
        module.render_stock_power_successor(
            stock_contract=parents.stock_contract,
            power_protocol=parents.receipt_parents.protocol,
            multiplicity_overlay=parents.receipt_parents.overlay,
            power_receipt=computed,
        )


@pytest.mark.parametrize(
    "parent_name",
    ("stock_contract", "power_protocol", "multiplicity_overlay", "power_receipt"),
)
def test_copied_direct_parent_substitution_is_refused(
    tmp_path: Path, parents: _Parents, parent_name: str
):
    receipt = _persisted_receipt(tmp_path, parents)
    arguments = {
        "stock_contract": parents.stock_contract,
        "power_protocol": parents.receipt_parents.protocol,
        "multiplicity_overlay": parents.receipt_parents.overlay,
        "power_receipt": receipt.value,
    }
    arguments[parent_name] = copy.copy(arguments[parent_name])
    with pytest.raises(module.StockPowerSuccessorError, match="direct-parent"):
        module.render_stock_power_successor(**arguments)


def test_valid_but_different_receipt_cannot_substitute_for_bound_receipt(
    tmp_path: Path, parents: _Parents
):
    first = _persisted_receipt(tmp_path / "first", parents)
    component = receipt_helpers._baseline_component_document(
        parents.receipt_parents.admission.calibration_session_axis,
        zero_count=25,
    )
    second = _persisted_receipt(
        tmp_path / "second", parents, component_document=component
    )
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, first).encode("utf-8"))

    assert first.value.receipt_id != second.value.receipt_id
    with pytest.raises(module.StockPowerSuccessorError, match="content changed"):
        _load_successor(path, parents, second)


@pytest.mark.parametrize(
    "field",
    (
        "calibration_input_manifest_sha256",
        "numeric_power_receipt_sha256",
        "power_plan_sha256",
        "required_valid_dates",
        "required_connected_components",
        "fixed_capacity_disposition",
    ),
)
def test_each_power_amendment_value_is_exact_not_caller_selected(
    tmp_path: Path, parents: _Parents, field: str
):
    receipt = _persisted_receipt(tmp_path, parents)
    raw = json.loads(_render_successor(parents, receipt))
    amendment = raw["power_amendment"]
    if field in {"required_valid_dates", "required_connected_components"}:
        amendment[field] += 1
    else:
        amendment[field] = "0" * 64 if field.endswith("sha256") else "substitute"
    _rehash_power_amendment(raw)
    path = tmp_path / "mutated.json"
    path.write_bytes(_render(raw))

    with pytest.raises(module.StockPowerSuccessorError, match="content changed"):
        _load_successor(path, parents, receipt)


def test_power_plan_semantic_hash_must_equal_receipt_content_hash(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    raw = json.loads(_render_successor(parents, receipt))
    raw["power_amendment"]["power_plan_sha256"] = "0" * 64
    _rehash_successor(raw)
    path = tmp_path / "bad-power-hash.json"
    path.write_bytes(_render(raw))

    with pytest.raises(module.StockPowerSuccessorError, match="content changed"):
        _load_successor(path, parents, receipt)


def test_direct_parent_projection_cannot_masquerade_as_complete_ancestry(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    raw = json.loads(_render_successor(parents, receipt))
    raw["direct_parent_projection"]["complete_ancestry_graph"] = True
    _rehash_successor(raw)
    path = tmp_path / "false-complete-lineage.json"
    path.write_bytes(_render(raw))

    with pytest.raises(module.StockPowerSuccessorError, match="projection"):
        _load_successor(path, parents, receipt)


@pytest.mark.parametrize(
    "payload",
    (
        b"{}\n",
        b'{"x":1.5}\n',
        b'{"x":NaN}\n',
        b'{"x":1,"x":1}\n',
        b"[]\n",
        b"\xff",
    ),
)
def test_malformed_noncanonical_float_and_duplicate_json_refuse(
    tmp_path: Path, parents: _Parents, payload: bytes
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "invalid.json"
    path.write_bytes(payload)
    with pytest.raises(module.StockPowerSuccessorError):
        _load_successor(path, parents, receipt)


@pytest.mark.parametrize(
    "token",
    (b"987654321.123456789", b"NaN"),
)
def test_rejected_numeric_token_is_not_disclosed(
    tmp_path: Path, parents: _Parents, token: bytes
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "sensitive-invalid.json"
    path.write_bytes(b'{"value":' + token + b"}\n")

    with pytest.raises(module.StockPowerSuccessorError) as caught:
        _load_successor(path, parents, receipt)

    assert token.decode("ascii") not in str(caught.value)


def test_rejected_duplicate_key_is_not_disclosed(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    token = "sensitive-beta-987654321"
    path = tmp_path / "sensitive-duplicate.json"
    path.write_bytes(
        ('{"' + token + '":1,"' + token + '":2}\n').encode("utf-8")
    )

    with pytest.raises(module.StockPowerSuccessorError) as caught:
        _load_successor(path, parents, receipt)

    assert token not in str(caught.value)


def test_unknown_root_field_refuses_even_with_recomputed_identity(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    raw = json.loads(_render_successor(parents, receipt))
    raw["extra"] = False
    _rehash_successor(raw)
    path = tmp_path / "extra.json"
    path.write_bytes(_render(raw))
    with pytest.raises(module.StockPowerSuccessorError, match="fields changed"):
        _load_successor(path, parents, receipt)


@pytest.mark.parametrize(
    ("raw_dates", "expected_disposition", "expected_status", "hard_no_launch"),
    (
        (
            TEST_SESSION_CAPACITY,
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT,
            module.FEASIBLE_STATUS,
            False,
        ),
        (
            TEST_SESSION_CAPACITY + 1,
            ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH,
            module.UNDERPOWERED_STATUS,
            True,
        ),
    ),
)
def test_fixed_capacity_boundary_maps_to_exact_successor_disposition(
    tmp_path: Path,
    parents: _Parents,
    raw_dates: int,
    expected_disposition: ProvisionalPowerDisposition,
    expected_status: str,
    hard_no_launch: bool,
):
    beta = receipt_helpers._beta_document_for_raw_date_requirement(
        parents.receipt_parents.admission.calibration_session_axis, raw_dates
    )
    receipt = _persisted_receipt(tmp_path, parents, beta_document=beta)
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    successor = _load_successor(path, parents, receipt)

    assert successor.required_valid_dates == raw_dates
    assert successor.disposition is expected_disposition
    assert successor.status == expected_status
    assert successor.hard_no_launch is hard_no_launch
    assert successor.fixed_design_feasible is (not hard_no_launch)
    assert successor.launch_authorized is False
    assert json.loads(path.read_bytes())["disposition_gate"]["current_effect"] == (
        "hard_no_launch"
        if hard_no_launch
        else "candidate_pending_review_and_separate_ARV2_4_authority"
    )


@pytest.mark.parametrize(
    ("checker_name", "parent_getter"),
    (
        ("require_loaded_global_benchmark_contract", lambda value: value.stock_contract),
        (
            "require_loaded_power_calibration_protocol",
            lambda value: value.receipt_parents.protocol,
        ),
        (
            "require_loaded_four_family_multiplicity_overlay",
            lambda value: value.receipt_parents.overlay,
        ),
        ("require_persisted_power_calibration_receipt", None),
    ),
)
def test_render_and_load_reauthenticate_each_direct_parent_before_and_after(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
    checker_name: str,
    parent_getter,
):
    receipt = _persisted_receipt(tmp_path, parents)
    expected = receipt.value if parent_getter is None else parent_getter(parents)
    checker_module = receipt_module if parent_getter is None else module
    original = getattr(checker_module, checker_name)
    expected_calls = 4 if parent_getter is None else 2
    calls: list[object] = []

    def counted(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(checker_module, checker_name, counted)
    rendered = _render_successor(parents, receipt)
    assert calls == [expected] * expected_calls
    path = tmp_path / "successor.json"
    path.write_bytes(rendered.encode("utf-8"))
    calls.clear()
    _load_successor(path, parents, receipt)
    assert calls == [expected] * expected_calls


@pytest.mark.parametrize(
    "checker_name",
    (
        "require_persisted_power_calibration_receipt",
        "power_calibration_receipt_artifact_sha256",
    ),
)
def test_receipt_helper_never_exports_a_restricted_object_or_failure_frame(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
    checker_name: str,
) -> None:
    class FixtureFatal(BaseException):
        pass

    def fail_closed(_value):
        raise FixtureFatal("fixture-only restricted-parent failure")

    receipt = _persisted_receipt(tmp_path, parents)
    monkeypatch.setattr(
        receipt_module,
        checker_name,
        fail_closed,
    )
    assert module._authenticate_receipt_parent(receipt.value) is None
    assert not hasattr(module, "require_persisted_power_calibration_receipt")
    assert not hasattr(module, "power_calibration_receipt_artifact_sha256")
    assert not hasattr(module, "PowerCalibrationReceiptError")


def test_receipt_parent_refusal_traceback_contains_no_restricted_facade_local(
    parents: _Parents,
) -> None:
    source = parents.receipt_parents
    with pytest.raises(module.StockPowerSuccessorError) as captured:
        module._authenticate_parents(
            parents.stock_contract,
            source.protocol,
            source.overlay,
            object(),
        )

    assert captured.value.__cause__ is None
    forbidden_locals = {
        "power_calibration_receipt_artifact_sha256",
        "require_persisted_power_calibration_receipt",
    }
    traceback_cursor = captured.value.__traceback__
    while traceback_cursor is not None:
        assert forbidden_locals.isdisjoint(traceback_cursor.tb_frame.f_locals)
        traceback_cursor = traceback_cursor.tb_next


def test_render_uses_one_complete_snapshot_during_transient_parent_mutation(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    receipt = _persisted_receipt(tmp_path, parents)
    expected_evaluation_id = parents.stock_contract.evaluation_id
    expected_dates = receipt.value.required_valid_dates
    original = module._document_from_snapshot

    def transient(snapshot):
        object.__setattr__(
            parents.stock_contract, "evaluation_id", "transient-wrong-evaluation"
        )
        object.__setattr__(receipt.value, "required_valid_dates", expected_dates + 7)
        try:
            return original(snapshot)
        finally:
            object.__setattr__(
                parents.stock_contract, "evaluation_id", expected_evaluation_id
            )
            object.__setattr__(
                receipt.value, "required_valid_dates", expected_dates
            )

    monkeypatch.setattr(module, "_document_from_snapshot", transient)
    raw = json.loads(_render_successor(parents, receipt))

    assert raw["evaluation_id"] == expected_evaluation_id
    assert raw["power_amendment"]["required_valid_dates"] == expected_dates


def test_loaded_fields_use_authenticated_raw_after_final_parent_authentication(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    expected = receipt.value.disposition
    transient = (
        ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH
        if expected
        is ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
        else ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    )
    original_revalidate = module._revalidate
    original_freeze = module._freeze
    successor_revalidations = 0
    restore_pending = False

    def mutate_after_final_revalidation(*args):
        nonlocal successor_revalidations, restore_pending
        result = original_revalidate(*args)
        if args[2] == "stock-v3 successor":
            successor_revalidations += 1
            if successor_revalidations == 2:
                object.__setattr__(receipt.value, "disposition", transient)
                restore_pending = True
        return result

    def restore_before_freezing(value):
        nonlocal restore_pending
        if restore_pending:
            object.__setattr__(receipt.value, "disposition", expected)
            restore_pending = False
        return original_freeze(value)

    monkeypatch.setattr(module, "_revalidate", mutate_after_final_revalidation)
    monkeypatch.setattr(module, "_freeze", restore_before_freezing)
    successor = _load_successor(path, parents, receipt)

    assert successor.disposition is expected
    assert module.require_loaded_stock_power_successor(successor) is successor


def test_successor_downstream_authentication_never_reopens_calibration_inputs(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    receipt = _persisted_receipt(tmp_path, parents)
    original = receipt_module._reauthenticate_artifact_identity
    opened_sensitive: list[str] = []

    def guard(artifact, name):
        if name in {"date-beta input", "component-count input"}:
            opened_sensitive.append(name)
            raise AssertionError(f"successor reopened {name}")
        return original(artifact, name)

    monkeypatch.setattr(receipt_module, "_reauthenticate_artifact_identity", guard)
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    successor = _load_successor(path, parents, receipt)
    assert module.require_loaded_stock_power_successor(successor) is successor
    assert opened_sensitive == []


def test_post_load_successor_or_receipt_byte_change_revokes_authority(
    tmp_path: Path, parents: _Parents
):
    first = _loaded_successor(tmp_path / "successor-change", parents)
    first.path.write_bytes(first.path.read_bytes() + b"\n")
    with pytest.raises(module.StockPowerSuccessorError, match="changed"):
        module.require_loaded_stock_power_successor(first.value)

    second = _loaded_successor(tmp_path / "receipt-change", parents)
    second.receipt.path.write_bytes(second.receipt.path.read_bytes() + b"\n")
    with pytest.raises(module.StockPowerSuccessorError, match="direct-parent"):
        module.require_loaded_stock_power_successor(second.value)


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="POSIX process-local successor authority reset check",
)
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_successor_authority_lock_and_registry_fail_closed_after_fork(
    tmp_path: Path,
    parents: _Parents,
) -> None:
    loaded = _loaded_successor(tmp_path, parents)
    successor = loaded.value
    lock_held = threading.Event()
    release_holder = threading.Event()

    def hold_successor_authority_lock() -> None:
        with module._STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK:
            lock_held.set()
            assert release_holder.wait(timeout=8)

    holder = threading.Thread(target=hold_successor_authority_lock)
    holder.start()
    assert lock_held.wait(timeout=5)
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions run in the child
        signal.alarm(4)
        inherited = (
            module._INHERITED_STOCK_POWER_SUCCESSOR_AUTHORITY_QUARANTINE[-1]
        )
        if (
            id(successor) not in inherited
            or module._STOCK_POWER_SUCCESSOR_AUTHORITIES
        ):
            os._exit(4)
        try:
            module.require_loaded_stock_power_successor(successor)
        except module.StockPowerSuccessorError:
            exit_code = 0
        except BaseException:
            exit_code = 2
        else:
            exit_code = 3
        os._exit(exit_code)

    try:
        child_status = receipt_helpers._wait_child_bounded(child_pid)
    finally:
        release_holder.set()
        holder.join(timeout=5)

    assert not holder.is_alive()
    assert os.waitstatus_to_exitcode(child_status) == 0
    assert module.require_loaded_stock_power_successor(successor) is successor


def test_parent_change_during_load_is_detected(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    original = module._authenticate_parents
    calls = 0

    def mutate_after_first(*args):
        nonlocal calls
        calls += 1
        result = original(*args)
        if calls == 1:
            receipt.path.write_bytes(receipt.path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(module, "_authenticate_parents", mutate_after_first)
    with pytest.raises(module.StockPowerSuccessorError, match="direct-parent"):
        _load_successor(path, parents, receipt)


def test_successor_file_change_during_load_is_detected_at_final_revalidation(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "successor.json"
    path.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    original = module._authenticate_parents
    calls = 0

    def mutate_after_second_parent_authentication(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 2:
            path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(
        module,
        "_authenticate_parents",
        mutate_after_second_parent_authentication,
    )
    with pytest.raises(module.StockPowerSuccessorError, match="changed"):
        _load_successor(path, parents, receipt)


def test_copy_reconstruction_pickle_replace_and_mutation_never_create_authority(
    tmp_path: Path, parents: _Parents
):
    successor = _loaded_successor(tmp_path, parents).value
    with pytest.raises(TypeError):
        dataclasses.replace(successor)

    copied = copy.copy(successor)
    with pytest.raises(module.StockPowerSuccessorError):
        module.require_loaded_stock_power_successor(copied)
    with pytest.raises(module.StockPowerSuccessorError):
        _ = copied.power_plan_bound

    forged = object.__new__(module.StockPowerSuccessor)
    for field in dataclasses.fields(module.StockPowerSuccessor):
        object.__setattr__(forged, field.name, getattr(successor, field.name))
    with pytest.raises(module.StockPowerSuccessorError):
        module.require_loaded_stock_power_successor(forged)

    try:
        restored = pickle.loads(pickle.dumps(successor))
    except (TypeError, pickle.PickleError):
        restored = None
    if restored is not None:
        with pytest.raises(module.StockPowerSuccessorError):
            module.require_loaded_stock_power_successor(restored)

    object.__setattr__(successor, "required_valid_dates", 1)
    with pytest.raises(module.StockPowerSuccessorError, match="changed after"):
        module.require_loaded_stock_power_successor(successor)


def test_deep_low_level_object_mutation_is_a_normalized_domain_error(
    tmp_path: Path, parents: _Parents
):
    successor = _loaded_successor(tmp_path, parents).value
    deeply_nested: object = ()
    for _ in range(2_000):
        deeply_nested = (deeply_nested,)
    object.__setattr__(
        successor,
        "definition",
        MappingProxyType({"deep": deeply_nested}),
    )
    with pytest.raises(
        module.StockPowerSuccessorError, match="too deeply nested"
    ):
        module.require_loaded_stock_power_successor(successor)


def test_nested_definition_and_capabilities_are_recursively_immutable(
    tmp_path: Path, parents: _Parents
):
    successor = _loaded_successor(tmp_path, parents).value
    with pytest.raises(TypeError):
        successor.capabilities["outcome_access"] = True
    with pytest.raises(TypeError):
        successor.definition["power_amendment"]["required_valid_dates"] = 1


def test_no_forbidden_receipt_intermediate_is_copied_into_successor(
    tmp_path: Path, parents: _Parents
):
    raw = json.loads(
        _render_successor(parents, _persisted_receipt(tmp_path, parents))
    )
    amendment = raw["power_amendment"]
    forbidden = {
        "valid_beta_date_count",
        "lag_pair_counts_0_through_20",
        "long_run_variance",
        "component_count_census_sha256",
        "component_count_census_session_count",
        "q05_components_per_date",
        "raw_required_valid_dates",
        "date_level_beta_values",
        "returns",
        "p_value",
        "gate_result",
    }
    assert forbidden.isdisjoint(amendment)


def test_successor_construction_never_changes_accepted_ancestor_bytes(
    tmp_path: Path, parents: _Parents
):
    before = {
        name: hashlib.sha256((SPEC_ROOT / name).read_bytes()).hexdigest()
        for name in ACCEPTED_ANCESTOR_FILENAMES
    }
    loaded = _loaded_successor(tmp_path, parents)
    module.require_loaded_stock_power_successor(loaded.value)
    after = {
        name: hashlib.sha256((SPEC_ROOT / name).read_bytes()).hexdigest()
        for name in ACCEPTED_ANCESTOR_FILENAMES
    }

    assert after == before
    assert not (SPEC_ROOT / "arv2_stock_historical_power_successor_v3.json").exists()


def test_successor_leaf_symlink_refuses(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path / "inputs", parents)
    real = tmp_path / "real-successor.json"
    real.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    linked = tmp_path / "linked-successor.json"
    try:
        linked.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"host cannot create a test symlink: {exc}")
    with pytest.raises(module.StockPowerSuccessorError, match="link"):
        _load_successor(linked, parents, receipt)


def test_successor_ancestor_directory_symlink_refuses(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path / "inputs", parents)
    real_directory = tmp_path / "real-directory"
    real_directory.mkdir()
    real = real_directory / "successor.json"
    real.write_bytes(_render_successor(parents, receipt).encode("utf-8"))
    linked_directory = tmp_path / "linked-directory"
    try:
        linked_directory.symlink_to(real_directory, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create a test directory symlink: {exc}")
    with pytest.raises(module.StockPowerSuccessorError, match="link"):
        _load_successor(linked_directory / "successor.json", parents, receipt)


def test_oversized_successor_refuses_before_json_parse(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "oversized.json"
    path.write_bytes(b"x" * (module.MAX_AUTHENTICATED_ARTIFACT_BYTES + 1))
    with pytest.raises(module.StockPowerSuccessorError, match="size limit"):
        _load_successor(path, parents, receipt)


def test_python_integer_digit_limit_is_normalized_to_domain_error(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    path = tmp_path / "huge-integer.json"
    path.write_bytes(b'{"value":' + b"1" * 10_000 + b"}\n")
    with pytest.raises(module.StockPowerSuccessorError, match="strict JSON"):
        _load_successor(path, parents, receipt)


def test_deep_json_chain_is_normalized_without_recursive_projection_walk(
    tmp_path: Path, parents: _Parents
):
    receipt = _persisted_receipt(tmp_path, parents)
    nested: object = 0
    for _ in range(900):
        nested = [nested]
    previous_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(10_000)
        payload = _render({"value": nested})
    finally:
        sys.setrecursionlimit(previous_limit)
    path = tmp_path / "deep-chain.json"
    path.write_bytes(payload)
    with pytest.raises(module.StockPowerSuccessorError):
        _load_successor(path, parents, receipt)


def test_authority_bearing_successor_cannot_be_directly_constructed():
    with pytest.raises(TypeError):
        module.StockPowerSuccessor()
