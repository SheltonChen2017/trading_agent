from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import inspect
import os
import select
import signal
import threading
import types

import pytest

from research.analyst_revisions_v2.production_scoring import (
    BINARY_COLUMNS,
    CONTINUOUS_COLUMNS,
)
from research.analyst_revisions_v2_qc import formal_evaluation_bridge as module
from research.analyst_revisions_v2_qc import (
    formal_submission_adapter as submission_adapter,
)
from research.analyst_revisions_v2_qc.formal_evaluation import (
    BINARY_CONTROL_NAMES,
    CONTINUOUS_CONTROL_NAMES,
    ECONOMIC_EXECUTION_DEFINITION_SHA256,
)
from research.analyst_revisions_v2_qc.formal_report_contract import (
    COMPARATOR_LEDGER_IDS,
    FORMAL_FOLD_IDS,
    REPORT_FAMILY_IDS,
    SOURCE_VIEW_IDS,
    build_formal_report_contract,
    formal_report_contract_record,
)


def test_scoring_and_evaluator_control_contracts_are_exactly_aligned():
    assert tuple(CONTINUOUS_COLUMNS) == CONTINUOUS_CONTROL_NAMES
    assert tuple(BINARY_COLUMNS) == BINARY_CONTROL_NAMES
    assert len(CONTINUOUS_COLUMNS) == 19
    assert len(BINARY_COLUMNS) == 6


def test_public_bridge_requires_complete_process_authenticated_read_chain():
    signature = inspect.signature(module.build_formal_aggregate_evaluation_receipt)
    assert tuple(signature.parameters) == (
        "result_read_receipt",
        "result_authority",
        "terminal",
        "launch",
        "submission_bridge",
        "expected_bindings",
    )
    assert "outcome_payload" not in signature.parameters
    assert "summary_pairs" not in signature.parameters


def test_aggregate_receipt_cannot_be_caller_minted():
    forged = object.__new__(module.FormalAggregateEvaluationReceipt)
    with pytest.raises(module.FormalEvaluationBridgeError, match="builder-authenticated"):
        module.require_formal_aggregate_evaluation_receipt(
            forged,
            result_authority=None,  # type: ignore[arg-type]
            terminal=None,  # type: ignore[arg-type]
            launch=None,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "name",
    (
        "_make_evaluation_receipt_authority_vault",
        "_evaluation_receipt_authority_register",
        "_evaluation_receipt_authority_current",
        "_build_formal_aggregate_evaluation_receipt_impl",
        "_require_formal_aggregate_evaluation_receipt_impl",
        "_render_formal_aggregate_evaluation_bytes_impl",
        "_bind_evaluation_receipt_authority",
    ),
)
def test_aggregate_receipt_authority_primitives_are_not_module_addressable(name):
    assert not hasattr(module, name)


def _extracted_aggregate_receipt_register():
    builder = module.build_formal_aggregate_evaluation_receipt
    assert builder.__closure__ is not None
    cells = dict(
        zip(builder.__code__.co_freevars, builder.__closure__, strict=True)
    )
    return cells["authority_register"].cell_contents


def _closure_cell(value):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name, value):
    assert function.__closure__ is not None
    cells = dict(zip(
        function.__code__.co_freevars, function.__closure__, strict=True
    ))
    assert name in cells
    rebound = types.FunctionType(
        function.__code__, function.__globals__, function.__name__,
        function.__defaults__,
        tuple(
            _closure_cell(value) if freevar == name else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _install_test_aggregate_receipt_authority(monkeypatch):
    """Keep synthetic aggregate receipts out of the production vault."""

    private = {}

    def forget(identity, reference):
        entry = private.get(identity)
        if entry is not None and entry[0] is reference:
            private.pop(identity, None)
        if module._RECEIPTS.get(identity) is entry:
            module._RECEIPTS.pop(identity, None)

    def register(value, entry_tail):
        identity = id(value)
        reference = module.weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        entry = (reference, *entry_tail, os.getpid())
        if identity in private or identity in module._RECEIPTS:
            raise module.FormalEvaluationBridgeError(
                "test aggregate receipt authority identity was reused"
            )
        private[identity] = entry
        module._RECEIPTS[identity] = entry
        return value

    def current(value):
        identity = id(value)
        entry = private.get(identity)
        if (
            entry is None
            or module._RECEIPTS.get(identity) is not entry
            or entry[0]() is not value
            or entry[-1] != os.getpid()
        ):
            private.pop(identity, None)
            module._RECEIPTS.pop(identity, None)
            return None
        return entry

    def reset_after_fork():
        private.clear()
        module._RECEIPTS = {}
        module._RECEIPTS_LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    production_builder = module.build_formal_aggregate_evaluation_receipt
    production_requirer = module.require_formal_aggregate_evaluation_receipt
    local_requirer = _with_closure_value(
        production_requirer, "authority_current", current
    )
    local_builder = _with_closure_value(
        production_builder, "authority_register", register
    )
    local_builder = _with_closure_value(
        local_builder,
        "require_formal_aggregate_evaluation_receipt",
        local_requirer,
    )
    return production_builder, local_builder, local_requirer


def _build_test_aggregate_receipt(monkeypatch):
    """Traverse the genuine public builder with all external parents offline."""

    bindings = module.FormalCloudEvaluationBindings(
        input_manifest_sha256="1" * 64,
        production_scoring_census_sha256="2" * 64,
        evaluation_input_bundle_id="fixture-bundle",
        evaluation_input_bundle_sha256="3" * 64,
        terminal_disposition_package_sha256="4" * 64,
        shared_market_panel_sha256="5" * 64,
        shared_market_panel_observation_count=1,
        formal_evaluator_source_sha256="6" * 64,
        evaluator_source_closure_sha256="7" * 64,
        execution_plan_sha256="8" * 64,
        capacity_plan_sha256="9" * 64,
    )
    private_names = {
        "_aggregate_bytes",
        "_result_read_receipt",
        "_bindings",
        "_submission_bridge",
    }
    record = {}
    for field in module.dataclasses.fields(module.FormalAggregateEvaluationReceipt):
        if field.name in {"receipt_id", "receipt_sha256", *private_names}:
            continue
        if field.name.endswith("_count"):
            record[field.name] = 1
        elif field.name.endswith("_authority"):
            record[field.name] = False
        elif field.name in {"process_authenticated_qc_read", "content_authenticated"}:
            record[field.name] = True
        else:
            record[field.name] = "fixture-" + field.name
    read_receipt = object()
    result_authority = object()
    terminal = object()
    launch = object()
    submitted = object()
    aggregate = b'{"fixture":"aggregate"}\n'
    production_builder, local_builder, local_requirer = (
        _install_test_aggregate_receipt_authority(monkeypatch)
    )
    monkeypatch.setattr(
        module,
        "require_streamed_formal_submission_adapter_bridge",
        lambda _value: submitted,
    )
    monkeypatch.setattr(module, "_require_submission_derived_bindings", lambda **_kw: None)
    monkeypatch.setattr(
        module,
        "require_formal_qc_summary_result_read_receipt",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        module,
        "_reconstruct_aggregate",
        lambda *_args, **_kwargs: (aggregate, {}, 14, "a" * 64),
    )
    monkeypatch.setattr(module, "_receipt_record", lambda **_kwargs: dict(record))
    builder_kwargs = {
        "result_read_receipt": read_receipt,
        "result_authority": result_authority,
        "terminal": terminal,
        "launch": launch,
        "submission_bridge": submitted,
        "expected_bindings": bindings,
    }
    prior_receipts = dict(module._RECEIPTS)
    with pytest.raises(
        module.FormalEvaluationBridgeError,
        match="register caller changed",
    ):
        production_builder(**builder_kwargs)
    assert module._RECEIPTS == prior_receipts
    monkeypatch.setattr(
        module, "build_formal_aggregate_evaluation_receipt", local_builder
    )
    monkeypatch.setattr(
        module, "require_formal_aggregate_evaluation_receipt", local_requirer
    )
    value = local_builder(
        **builder_kwargs,
    )
    return value


def test_reflected_aggregate_receipt_register_cannot_self_mint():
    register = _extracted_aggregate_receipt_register()
    value = object.__new__(module.FormalAggregateEvaluationReceipt)
    with pytest.raises(module.FormalEvaluationBridgeError, match="caller changed"):
        register(value, tuple(object() for _index in range(7)))


def test_reflected_aggregate_private_registry_is_immutable():
    register = _extracted_aggregate_receipt_register()
    cells = dict(
        zip(register.__code__.co_freevars, register.__closure__, strict=True)
    )
    private_entry = cells["private_entry"].cell_contents
    inner = dict(
        zip(
            private_entry.__code__.co_freevars,
            private_entry.__closure__,
            strict=True,
        )
    )
    state = inner["private_receipts"].cell_contents
    assert type(state) is tuple
    assert not hasattr(state, "append")


def test_aggregate_receipt_public_mirror_cannot_reseal_private_authority(monkeypatch):
    value = _build_test_aggregate_receipt(monkeypatch)
    with module._RECEIPTS_LOCK:
        entry = module._RECEIPTS[id(value)]
        replacement = tuple(list(entry))
        assert replacement is not entry
        module._RECEIPTS[id(value)] = replacement
    with pytest.raises(module.FormalEvaluationBridgeError, match="builder-authenticated"):
        module.require_formal_aggregate_evaluation_receipt(
            value,
            result_authority=None,  # type: ignore[arg-type]
            terminal=None,  # type: ignore[arg-type]
            launch=None,  # type: ignore[arg-type]
        )
    assert id(value) not in module._RECEIPTS
    with module._RECEIPTS_LOCK:
        module._RECEIPTS[id(value)] = entry
    with pytest.raises(module.FormalEvaluationBridgeError, match="builder-authenticated"):
        module.require_formal_aggregate_evaluation_receipt(
            value,
            result_authority=None,  # type: ignore[arg-type]
            terminal=None,  # type: ignore[arg-type]
            launch=None,  # type: ignore[arg-type]
        )
    assert id(value) not in module._RECEIPTS


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_aggregate_receipt_authority_registry_is_cleared_after_fork(monkeypatch):
    value = _build_test_aggregate_receipt(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def hold_inherited_lock():
        with module._RECEIPTS_LOCK:
            entered.set()
            release.wait(15)

    holder = threading.Thread(target=hold_inherited_lock)
    holder.start()
    assert entered.wait(5)
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - assertion is reported through the pipe
        os.close(read_descriptor)
        try:
            try:
                module.require_formal_aggregate_evaluation_receipt(
                    value,
                    result_authority=None,  # type: ignore[arg-type]
                    terminal=None,  # type: ignore[arg-type]
                    launch=None,  # type: ignore[arg-type]
                )
            except module.FormalEvaluationBridgeError as exc:
                if "builder-authenticated" not in str(exc):
                    raise
            else:
                raise AssertionError("inherited evaluation receipt survived fork")
            with module._RECEIPTS_LOCK:
                pass
            if module._RECEIPTS:
                raise AssertionError("inherited evaluation registry survived fork")
            payload = b"ok"
        except BaseException as exc:
            payload = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:1000]
        try:
            os.write(write_descriptor, payload)
        finally:
            os.close(write_descriptor)
            os._exit(0)
    os.close(write_descriptor)
    ready, _writable, _exceptional = select.select(
        [read_descriptor], [], [], 10
    )
    if ready:
        outcome = os.read(read_descriptor, 1000)
    else:
        outcome = b"child-timeout"
        os.kill(child, signal.SIGKILL)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    release.set()
    holder.join(timeout=5)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"ok"
    assert not holder.is_alive()
    assert id(value) in module._RECEIPTS


def test_bridge_only_releases_aggregate_not_rows_or_action_authority():
    fields = {
        item.name
        for item in module.dataclasses.fields(module.FormalAggregateEvaluationReceipt)
    }
    assert "_aggregate_bytes" in fields
    assert "decision_outcomes" not in fields
    assert {
        "production_scoring_census_sha256",
        "evaluation_input_bundle_id",
        "evaluation_input_bundle_sha256",
        "terminal_disposition_package_sha256",
        "formal_evaluator_source_sha256",
        "execution_plan_sha256",
        "capacity_plan_sha256",
        "formal_contract_sha256",
        "economic_h20_terminal_liquidation_session",
        "secondary_hypothesis_registry_sha256",
        "deflated_sharpe_trial_registry_sha256",
        "stock_bootstrap_seed_sha256",
        "preoutcome_global_comparator_coverage_record_count",
        "preoutcome_global_comparator_coverages_sha256",
        "result_disposition_authority",
        "deployment_authority",
        "orders_authority",
        "trading_authority",
    }.issubset(fields)
    assert "build_runtime_outcome_authority" not in module.__all__


def test_result_gate_accepts_only_deterministic_bounded_gzip():
    raw = b'{"schema":"fixture"}\n'
    compressed_buffer = bytearray(gzip.compress(raw, compresslevel=9, mtime=0))
    compressed_buffer[9] = 255
    compressed = bytes(compressed_buffer)
    assert module._bounded_gzip(compressed, len(raw)) == raw
    changed = bytearray(compressed)
    changed[4] = 1  # nonzero mtime remains valid gzip but is not canonical
    with pytest.raises(module.FormalEvaluationBridgeError, match="header"):
        module._bounded_gzip(bytes(changed), len(raw))
    platform_variant = bytearray(compressed)
    platform_variant[9] = 19  # Python 3.12/zlib may emit this before normalization.
    with pytest.raises(module.FormalEvaluationBridgeError, match="header"):
        module._bounded_gzip(bytes(platform_variant), len(raw))
    platform_variant[9] = 255  # The projected publisher owns this normalization.
    assert module._bounded_gzip(bytes(platform_variant), len(raw)) == raw
    with pytest.raises(module.FormalEvaluationBridgeError):
        module._bounded_gzip(compressed + compressed, len(raw) * 2)
    with pytest.raises(module.FormalEvaluationBridgeError):
        module._bounded_gzip(compressed + b"trailing", len(raw))


def test_bridge_reconstructs_the_multipart_root_metadata_contract(monkeypatch):
    """The post-QC bridge accepts the root/26-object contract, not v1 names."""

    assert len(module._SUMMARY_META_FIELDS) == 26
    assert module._SUMMARY_META_FIELDS == (
        submission_adapter._SUMMARY_RESULT_META_FIELDS
    )
    root = b'{"formal":"multipart-root"}\n'
    compressed_buffer = bytearray(gzip.compress(root, compresslevel=9, mtime=0))
    compressed_buffer[9] = 255
    compressed = bytes(compressed_buffer)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    input_manifest_sha256 = "1" * 64
    evaluator_sha256 = "2" * 64
    project_id = 123
    descriptors = []
    payloads = []
    for ordinal in range(module.FORMAL_RESULT_FAMILY_OBJECT_COUNT):
        payload = f"family-{ordinal:02d}".encode("ascii")
        compressed_sha256 = hashlib.sha256(payload).hexdigest()
        suffix = (
            module.REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
            + input_manifest_sha256
            + f"/{ordinal:02d}-{compressed_sha256}-json.gz"
        )
        record = {
            "ordinal": ordinal,
            "object_store_key_suffix": suffix,
            "uncompressed_byte_count": len(payload) + 1,
            "compressed_byte_count": len(payload),
        }
        descriptors.append(
            types.SimpleNamespace(
                **record,
                to_record=(lambda value=record: dict(value)),
            )
        )
        payloads.append((suffix, payload))
    descriptors = tuple(descriptors)
    payloads = tuple(payloads)
    descriptor_records = [item.to_record() for item in descriptors]
    chunk_name = module.SUMMARY_CHUNK_PREFIX + "000"
    meta = {
        "schema": module.SUMMARY_RECEIPT_SCHEMA,
        "evaluation_id": module.EVALUATION_ID,
        "input_manifest_sha256": input_manifest_sha256,
        "cloud_evaluator_sha256": evaluator_sha256,
        "root_manifest_schema": module.AGGREGATE_RESULT_SCHEMA,
        "root_manifest_sha256": hashlib.sha256(root).hexdigest(),
        "root_manifest_byte_count": len(root),
        "compressed_root_sha256": hashlib.sha256(compressed).hexdigest(),
        "compressed_root_byte_count": len(compressed),
        "encoding": (
            "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
        ),
        "chunk_count": 1,
        "chunks": [{
            "name": chunk_name,
            "ordinal": 0,
            "character_count": len(encoded),
            "sha256": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
        }],
        "report_family_object_reference_schema": (
            module.REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        ),
        "report_family_object_count": len(descriptors),
        "report_family_object_inventory_sha256": hashlib.sha256(
            module._canonical_bytes(descriptor_records)
        ).hexdigest(),
        "report_family_object_total_uncompressed_byte_count": sum(
            item.uncompressed_byte_count for item in descriptors
        ),
        "report_family_object_total_compressed_byte_count": sum(
            item.compressed_byte_count for item in descriptors
        ),
        "report_family_object_full_key_prefix": (
            f"{project_id}/{module.REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX}"
        ),
        "object_store_write_once_existing_identical_bytes_only": True,
        "object_store_save_then_reopen_and_rehash_complete": True,
        "object_store_reopened_object_count": len(descriptors),
        "raw_report_family_rows_in_summary": False,
        "fold_horizon_axis_count": 24,
        "source_view_fold_horizon_axis_count": 48,
        "failed_arm_omission_count": 0,
        "orders_placed": 0,
    }
    meta_text = base64.urlsafe_b64encode(
        module._canonical_bytes(meta)
    ).decode("ascii")
    pairs = ((chunk_name, encoded), (module.SUMMARY_META_NAME, meta_text))
    bindings = module.FormalCloudEvaluationBindings(
        input_manifest_sha256=input_manifest_sha256,
        production_scoring_census_sha256="3" * 64,
        evaluation_input_bundle_id="fixture-bundle",
        evaluation_input_bundle_sha256="4" * 64,
        terminal_disposition_package_sha256="5" * 64,
        shared_market_panel_sha256="6" * 64,
        shared_market_panel_observation_count=1,
        formal_evaluator_source_sha256="7" * 64,
        evaluator_source_closure_sha256=evaluator_sha256,
        execution_plan_sha256="8" * 64,
        capacity_plan_sha256="9" * 64,
    )
    receipt = types.SimpleNamespace(
        summary_pairs=pairs,
        project_id=project_id,
        _formal_result_root_manifest=root,
        _formal_result_bindings=bindings,
        _formal_result_family_descriptors=descriptors,
        _formal_result_family_payloads=payloads,
    )
    document = {"validated": True}
    monkeypatch.setattr(
        module._cloud_evaluator,
        "formal_cloud_evaluation_family_object_read_plan",
        lambda payload, *, expected_bindings: descriptors,
    )
    monkeypatch.setattr(
        module,
        "require_formal_cloud_evaluation_aggregate_bytes",
        lambda payload, *, expected_bindings, report_family_object_payloads: document,
    )
    monkeypatch.setattr(
        module,
        "_require_exact_preoutcome_coverage_output",
        lambda **_kwargs: (14, "3" * 64),
    )

    assert module._reconstruct_aggregate(
        receipt, bindings, types.SimpleNamespace()
    ) == (root, document, 14, "3" * 64)

    legacy_meta = dict(meta)
    legacy_meta["aggregate_result_sha256"] = legacy_meta.pop(
        "root_manifest_sha256"
    )
    legacy_pairs = (
        (chunk_name, encoded),
        (
            module.SUMMARY_META_NAME,
            base64.urlsafe_b64encode(
                module._canonical_bytes(legacy_meta)
            ).decode("ascii"),
        ),
    )
    receipt.summary_pairs = legacy_pairs
    with pytest.raises(module.FormalEvaluationBridgeError, match="fields changed"):
        module._reconstruct_aggregate(
            receipt, bindings, types.SimpleNamespace()
        )


def _coverage_record(view: str, folds: list[str]) -> dict[str, object]:
    return {
        "source_view_id": view,
        "fold_ids": folds,
        "ledgers": [
            {
                "ledger_id": ledger_id,
                "numerator": 19,
                "denominator": 20,
                "passes": True,
                "disposition": "PASS",
                "reasons": [],
            }
            for ledger_id in COMPARATOR_LEDGER_IDS
        ],
        "endpoint_status_counts": [["mapped", 20]],
        "endpoint_pair_status_counts": [["mapped", 10]],
        "direction_status_counts": [["expected_sign", 10]],
        "date_diagnostic_counts": [["preoutcome_candidate_dates", 20]],
        "raw_form_collision_counts": [
            ["canonical_keys_with_multiple_raw_forms", 0]
        ],
    }


def _coverage_boundary_fixture(contract: dict[str, object]):
    report = formal_report_contract_record(build_formal_report_contract(
        economic_execution_definition_sha256=(
            ECONOMIC_EXECUTION_DEFINITION_SHA256
        )
    ))
    contract["formal_report_contract"] = report
    schema = report["report_schemas"][4]
    coverages = tuple(
        (*contract["global_comparator_fold_coverages"],
         *contract["global_comparator_pooled_coverages"])
    )
    chunks = []
    fields = (
        *schema["ordered_key_fields"],
        *schema["ordered_value_fields"],
    )
    for view in SOURCE_VIEW_IDS:
        rows = module._expected_preoutcome_coverage_rows(
            coverages, source_view_id=view
        )
        aligned = [[row[name] for name in fields] for row in rows]
        seed = {
            "schema": "arv2-formal-report-family-output-v1",
            "formal_report_contract_sha256": report["contract_sha256"],
            "source_view_id": view,
            "family_schema": schema,
            "row_count": len(aligned),
            "rows": aligned,
            "raw_security_event_or_market_rows_exported": False,
        }
        digest = hashlib.sha256(module._canonical_bytes(seed)).hexdigest()
        family = {
            **seed,
            "family_output_id": (
                "arv2-formal-report-family-output-" + digest[:24]
            ),
            "family_output_sha256": digest,
        }
        chunks.append(module._cloud_evaluator._report_family_chunk(family))
    manifest = module._canonical_bytes({
        "streamed_formal_input_lineage": {
            "formal_contract_sha256": hashlib.sha256(
                module._canonical_bytes(contract)
            ).hexdigest()
        }
    })
    streamed_input = object()
    submission = types.SimpleNamespace(runtime_bridge=types.SimpleNamespace(
        input_manifest_payload=manifest,
        resource_candidate=types.SimpleNamespace(streamed_input=streamed_input),
    ))
    return submission, {"report_family_chunks": chunks}, streamed_input


def _coverage_contract() -> dict[str, object]:
    return {
        "global_comparator_fold_coverages": [
            _coverage_record(view, [fold])
            for fold in FORMAL_FOLD_IDS
            for view in SOURCE_VIEW_IDS
        ],
        "global_comparator_pooled_coverages": [
            _coverage_record(view, list(FORMAL_FOLD_IDS))
            for view in SOURCE_VIEW_IDS
        ],
    }


def test_family4_coverage_rows_equal_all_14_authenticated_input_records(
    monkeypatch,
):
    contract = _coverage_contract()
    submission, document, streamed_input = _coverage_boundary_fixture(contract)
    monkeypatch.setattr(
        module,
        "streamed_formal_contract_record",
        lambda value: contract if value is streamed_input else None,
    )
    count, digest = module._require_exact_preoutcome_coverage_output(
        document=document,
        submission_bridge=submission,
    )
    assert count == 14
    assert digest == hashlib.sha256(module._canonical_bytes({
        "global_comparator_fold_coverages": (
            contract["global_comparator_fold_coverages"]
        ),
        "global_comparator_pooled_coverages": (
            contract["global_comparator_pooled_coverages"]
        ),
    })).hexdigest()


@pytest.mark.parametrize("coverage_index", range(14))
def test_each_authenticated_coverage_parent_must_match_family4_output(
    monkeypatch,
    coverage_index,
):
    original = _coverage_contract()
    _original_submission, document, _original_input = (
        _coverage_boundary_fixture(original)
    )
    changed = copy.deepcopy(original)
    changed_records = (
        *changed["global_comparator_fold_coverages"],
        *changed["global_comparator_pooled_coverages"],
    )
    changed_records[coverage_index]["ledgers"][0]["numerator"] = 20
    submission, _unused_document, streamed_input = (
        _coverage_boundary_fixture(changed)
    )
    monkeypatch.setattr(
        module,
        "streamed_formal_contract_record",
        lambda value: changed if value is streamed_input else None,
    )
    with pytest.raises(
        module.FormalEvaluationBridgeError,
        match="differs from authenticated input records",
    ):
        module._require_exact_preoutcome_coverage_output(
            document=document,
            submission_bridge=submission,
        )
