"""Pure public-source preparation and synthetic native-envelope boundaries."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from research.target_price_revisions_qc import extended_off_recovery_preparation as m
from research.target_price_revisions_qc import extended_refusal_witness_controller_successor as controller
from research.target_price_revisions_qc import extended_refusal_witness_runtime_successor as runtime

ROOT = Path(__file__).resolve().parents[2]
HEAD = "990e53672533cf27e466235bfe4184cec0bd32bb"
OWNER = b"Prepare offline only; no QC or Safari setup while another lane uses it."


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    import http.client
    import socket
    import subprocess
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/operator/provider/native effect forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def sources():
    return {path: (ROOT / path).read_bytes() for path in m.SOURCE_SHA256}


def observation():
    return {"physical_root": m.ROOT, "git_toplevel": m.ROOT, "branch": m.BRANCH,
        "git_head": HEAD, "status_short": ""}


def prepare(**kwargs):
    return m.prepare_off_recovery(kwargs.pop("public_sources", sources()),
        repository_observation=kwargs.pop("repository_observation", observation()),
        owner_instruction=kwargs.pop("owner_instruction", OWNER), **kwargs)


def bindings():
    return {"operation_id": "TPR-EXT26-WITNESS-RUNTIME-SYNTHETIC-ONLY",
        "invocation_id": "1" * 32, "git_head": HEAD, "plan_sha256": "2" * 64,
        "program_sha256": "3" * 64, "capsule_sha256": "4" * 64,
        "source_closure_sha256": m.source_closure_sha256()}


def result(*, status="completed_diagnostic_only", partial=False):
    value = runtime._new_result()
    value.update(operation_id=bindings()["operation_id"], status=status)
    if status == "completed_diagnostic_only":
        value["contains_calls"] = 2
        value["objects"] = [{"kind": kind, "present": False,
            "status": "absent_uninterpreted", "read_attempted": False,
            "gzip_bytes": None, "gzip_sha256": None, "plain_bytes": None, "plain_sha256": None}
            for kind in ("membership", "mark")]
    if partial:
        value["contains_calls"] = 1
        value["read_calls"] = 1
        value["objects"] = [{"kind": "membership", "present": True,
            "status": "failed_or_refused", "read_attempted": True,
            "gzip_bytes": None, "gzip_sha256": None, "plain_bytes": None, "plain_sha256": None}]
    return value


def envelope(*, delivery="returned", native=None):
    return {"schema": "tpr-ext26-off-native-envelope-v1", "bindings": bindings(),
        "delivery_status": delivery, "native_result": result() if native is None and delivery == "returned" else native}


def parse(value=None, **kwargs):
    return m.validate_native_envelope(canonical(envelope() if value is None else value),
        expected_bindings=kwargs.pop("expected_bindings", bindings()), **kwargs)


def test_manifest_composes_existing_source_validation_and_stays_inert(monkeypatch):
    calls = []
    original = m.program.validate_sources
    def track(**kwargs):
        calls.append(set(kwargs))
        return original(**kwargs)
    monkeypatch.setattr(m.program, "validate_sources", track)
    manifest = prepare()
    assert len(calls) == 1
    assert manifest["mode"] == "offline_prepared_native_setup_pending"
    assert set(manifest["source_hashes"]) == set(controller.SOURCE_PATHS)
    assert manifest["source_hashes"] == controller.source_hashes()
    assert manifest["retained_witness_contract"]["project_id"] == 37650980
    assert manifest["retained_witness_contract"]["job_id"] == runtime.JOB
    assert manifest["retained_witness_contract"]["keys"] == [runtime.predecessor.witness_key(kind) for kind in ("membership", "mark")]
    assert all(value is None for value in manifest["pending_native"].values())
    assert manifest["study"] == {"study_id": "TPR-CAP-TILT-EXT26-20261010-v1", "arm": "OFF",
        "start": "2021-01-04", "end": "2026-10-09", "warmup": "2020-09-01",
        "valuations": 1449, "decisions": 301, "sleeves": ["SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX"],
        "selection": "cap_only_top10_fixed60_stock_slots", "tpr_tilt": "0", "ar_enabled": False}
    assert controller.NATIVE_ADAPTER_PERMITTED is False
    assert manifest["source_units_accepted"] is manifest["diagnosis_sufficient"] is False
    assert manifest["old_scope_reuse_permitted"] is False
    assert len(manifest["pending_native_checklist"]) == 9
    assert manifest['resource_release'] == {'qc_safari_available': False,
        'availability_observed': False, 'monitor_rearm_authorized': False,
        'analyst_push_is_automatic_release': False,
        'next_boundary': 'fresh_owner_release_then_native_setup'}


def test_manifest_deterministic_owned_copies_and_digest():
    public, observed = sources(), observation()
    manifest = prepare(public_sources=public, repository_observation=observed)
    assert manifest == prepare()
    digest = manifest.pop("preparation_sha256")
    assert digest == hashlib.sha256(canonical(manifest)).hexdigest()
    observed["branch"] = "unrelated"
    public.clear()
    assert manifest["repository_observation"]["branch"] == m.BRANCH
    assert OWNER.decode() not in canonical(manifest).decode()
    manifest["source_hashes"].clear()
    assert prepare()["source_hashes"] == m.SOURCE_SHA256


@pytest.mark.parametrize("field", sorted(m.SOURCE_SHA256))
def test_each_independent_source_pin_refuses_changed_bytes(field):
    supplied = sources()
    supplied[field] += b"\n# changed public source\n"
    with pytest.raises(m.OffRecoveryRefusal, match="^offline OFF recovery preparation refused$"):
        prepare(public_sources=supplied)


@pytest.mark.parametrize("mutation", ["missing", "extra", "text", "bytearray", "oversized"])
def test_source_shape_and_byte_bounds(mutation):
    supplied = sources()
    key = next(iter(supplied))
    if mutation == "missing": del supplied[key]
    elif mutation == "extra": supplied["unknown.py"] = b""
    elif mutation == "text": supplied[key] = supplied[key].decode()
    elif mutation == "bytearray": supplied[key] = bytearray(supplied[key])
    else: supplied[key] = b"x" * (m.MAX_SOURCE_BYTES + 1)
    with pytest.raises(m.OffRecoveryRefusal): prepare(public_sources=supplied)


@pytest.mark.parametrize("field,value", [("physical_root", "/wrong"), ("git_toplevel", "/wrong"),
    ("branch", "main"), ("git_head", "a" * 39), ("git_head", True), ("status_short", "?? new.py"),
    ("status_short", None), ("branch", 1)])
def test_repository_observation_refuses_dirty_mismatch_and_bad_types(field, value):
    observed = observation(); observed[field] = value
    with pytest.raises(m.OffRecoveryRefusal): prepare(repository_observation=observed)


@pytest.mark.parametrize("value", [b"", b" \n", "not bytes", bytearray(b"text"), b"x" * (m.MAX_OWNER_BYTES + 1), None])
def test_owner_bytes_bound_no_text_retention(value):
    with pytest.raises(m.OffRecoveryRefusal): prepare(owner_instruction=value)


def test_boundary_owner_length_and_new_head_are_observations_not_authority():
    observed = observation(); observed["git_head"] = "f" * 40
    manifest = prepare(owner_instruction=b"x" * m.MAX_OWNER_BYTES, repository_observation=observed)
    assert manifest["repository_observation"]["git_head"] == "f" * 40
    for key in ("repository_observation_authenticated", "owner_instruction_authenticated", "authority_granted",
                "ready_for_dispatch", "native_binding_proven", "off_baseline_valid", "on_launch_authorized"):
        assert manifest[key] is False
    for key in ("new_jobs", "new_codex_attempts", "new_looks"): assert manifest[key] == 0


def test_factory_has_no_file_or_effect_access_after_public_inputs_supplied(monkeypatch):
    supplied, observed = sources(), observation()
    def deny(*_args, **_kwargs):
        raise AssertionError("the pure factory must not read any file or build active text")
    monkeypatch.setattr(Path, "read_bytes", deny)
    monkeypatch.setattr(Path, "read_text", deny)
    monkeypatch.setattr(m.program, "build_program", deny)
    manifest = m.prepare_off_recovery(supplied, repository_observation=observed, owner_instruction=OWNER)
    assert manifest["pending_native"]["permit"] is None
    assert manifest["retained_witness_contract"]["freeze_sha256"] == runtime.predecessor.witness.FREEZE_SHA256


def test_parser_binds_metadata_but_never_authenticates_native_or_accepts_strategy():
    output = parse()
    assert output["status"] == "completed_diagnostic_only"
    assert output["binding_shape_validated"] is True
    assert output["contains_calls"] == 2 and output["read_calls"] == 0
    for key in ("native_tool_authenticated", "native_binding_proven", "authority_granted", "ready_for_dispatch",
                "diagnosis_sufficient", "source_units_accepted", "off_baseline_valid", "on_launch_authorized"):
        assert output[key] is False
    assert output["native_result"] == result()


@pytest.mark.parametrize("field", sorted(m._BINDING_KEYS))
def test_each_expected_binding_mismatch_refuses(field):
    value = envelope()
    replacement = {"operation_id": "TPR-EXT26-WITNESS-RUNTIME-DIFFERENT", "invocation_id": "f" * 32,
        "git_head": "f" * 40, "plan_sha256": "f" * 64, "program_sha256": "f" * 64,
        "capsule_sha256": "f" * 64, "source_closure_sha256": "f" * 64}
    value["bindings"][field] = replacement[field]
    with pytest.raises(m.OffRecoveryRefusal): parse(value)


@pytest.mark.parametrize("field,value", [("operation_id", "arbitrary"), ("invocation_id", "x" * 32),
    ("git_head", "a" * 64), ("plan_sha256", True), ("program_sha256", "z" * 64),
    ("capsule_sha256", None), ("source_closure_sha256", "f" * 64)])
def test_expected_bindings_are_strict_not_caller_grants(field, value):
    expected = bindings(); expected[field] = value
    with pytest.raises(m.OffRecoveryRefusal): parse(expected_bindings=expected)


@pytest.mark.parametrize("delivery", ["failed_or_uncertain", "cancelled"])
def test_unreturned_transport_has_unknown_null_counts(delivery):
    output = parse(envelope(delivery=delivery))
    assert output["status"] == delivery
    assert output["native_result"] is None
    assert output["contains_calls"] is output["read_calls"] is None


def test_cancelled_return_preserves_known_partial_counts_and_stop_status():
    output = parse(envelope(delivery="cancelled", native=result(status="cancelled", partial=True)))
    assert output["status"] == "cancelled"
    assert output["contains_calls"] == output["read_calls"] == 1
    assert output["native_result"]["objects"][0]["status"] == "failed_or_refused"


def test_returned_failure_preserves_nonzero_spending_not_false_success():
    output = parse(envelope(native=result(status="failed_or_uncertain", partial=True)))
    assert output["status"] == "failed_or_uncertain"
    assert output["contains_calls"] == output["read_calls"] == 1
    assert output["off_baseline_valid"] is False


@pytest.mark.parametrize("delivery,status", [("cancelled", "completed_diagnostic_only"),
    ("cancelled", "failed_or_uncertain"), ("failed_or_uncertain", "cancelled")])
def test_transport_result_contradictions_refuse(delivery, status):
    with pytest.raises(m.OffRecoveryRefusal): parse(envelope(delivery=delivery, native=result(status=status)))


@pytest.mark.parametrize("mutation", ["schema", "unknown", "binding_unknown", "missing", "no_result", "bad_delivery", "result_operation", "result_unknown", "result_acceptance", "result_count"])
def test_closed_envelope_and_runtime_result_contract(mutation):
    value = envelope()
    if mutation == "schema": value["schema"] = "other"
    elif mutation == "unknown": value["secret"] = "PRIVATE-SENTINEL"
    elif mutation == "binding_unknown": value["bindings"]["authority_granted"] = True
    elif mutation == "missing": del value["bindings"]["program_sha256"]
    elif mutation == "no_result": value["native_result"] = None
    elif mutation == "bad_delivery": value["delivery_status"] = "Completed"
    elif mutation == "result_operation": value["native_result"]["operation_id"] = "TPR-EXT26-WITNESS-RUNTIME-OTHER"
    elif mutation == "result_unknown": value["native_result"]["payload"] = "PRIVATE-SENTINEL"
    elif mutation == "result_acceptance": value["native_result"]["off_baseline_valid"] = True
    else: value["native_result"]["read_calls"] = 1
    with pytest.raises(m.OffRecoveryRefusal) as error: parse(value)
    assert "PRIVATE-SENTINEL" not in str(error.value)


@pytest.mark.parametrize("raw", [b"", b"{", b"\xff", b"null", b"[]", b"{\"x\":NaN}",
    b"{\"x\":Infinity}", b"{\"x\":-Infinity}", b"{\"x\":1.5}", b"{\"x\":1e999}",
    b"{\"x\":1,\"x\":2}", b"{\"x\":{\"a\":1,\"a\":2}}", b"x" * (m.MAX_ENVELOPE_BYTES + 1)])
def test_malformed_duplicate_nonfinite_and_oversize_wire_refuses_bodyfree(raw):
    with pytest.raises(m.OffRecoveryRefusal, match="^offline OFF recovery preparation refused$"):
        m.validate_native_envelope(raw, expected_bindings=bindings())


def test_parser_suppresses_underlying_payload_error_context_in_traceback():
    import traceback
    raw = b'{"PRIVATE-NATIVE-WIRE":'
    with pytest.raises(m.OffRecoveryRefusal) as caught:
        m.validate_native_envelope(raw, expected_bindings=bindings())
    error = caught.value
    assert error.__suppress_context__ is True and error.__cause__ is None
    assert 'PRIVATE-NATIVE-WIRE' not in ''.join(traceback.format_exception(type(error), error, error.__traceback__))


@pytest.mark.parametrize("where", ["root", "bindings", "result", "nested"])
def test_duplicates_at_each_relevant_level_refuse(where):
    raw = canonical(envelope())
    if where == "root": raw = raw.replace(b'"delivery_status":"returned"', b'"delivery_status":"returned","delivery_status":"returned"')
    elif where == "bindings": raw = raw.replace(b'"invocation_id":"' + b"1" * 32 + b'"', b'"invocation_id":"' + b"1" * 32 + b'","invocation_id":"' + b"1" * 32 + b'"')
    elif where == "result": raw = raw.replace(b'"read_calls":0', b'"read_calls":0,"read_calls":0')
    else: raw = b'{"unexpected":{"duplicate":1,"duplicate":1}}'
    with pytest.raises(m.OffRecoveryRefusal): m.validate_native_envelope(raw, expected_bindings=bindings())


def test_limits_reject_depth_nodes_long_strings_and_nonbyte_wire():
    for raw in (b"[" * 14 + b"0" + b"]" * 14, canonical([0] * 257), canonical({"x": "x" * 1025}),
                canonical(envelope()).decode(), bytearray(canonical(envelope()))):
        with pytest.raises(m.OffRecoveryRefusal): m.validate_native_envelope(raw, expected_bindings=bindings())


def test_only_whitelisted_pure_dependency_calls_and_no_io_imports():
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
    assert imports == {"hashlib", "json", "re"}
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {"read_bytes", "read_text", "open", "run", "Popen", "connect", "build_program", "execute_prepared_read", "read_runtime_witnesses"}


def test_binding_guard_mutants_are_killed_without_editing_or_effects():
    source = Path(m.__file__).read_text()
    trials = [
        ("or _validate_bindings(envelope[\"bindings\"]) != expected", "or False", "binding_mismatch"),
        ("if key in result:", "if False:", "duplicate"),
        ("or delivery == \"cancelled\" and result[\"status\"] != \"cancelled\"", "or False", "cancellation"),
        ("if value[\"source_closure_sha256\"] != source_closure_sha256():", "if False:", "closure"),
    ]
    for before, after, case in trials:
        assert source.count(before) == 1
        mutant = ModuleType("research.target_price_revisions_qc._off_preparation_mutant")
        mutant.__package__ = m.__package__
        exec(compile(source.replace(before, after, 1), "<pure-off-preparation-mutant>", "exec"), mutant.__dict__)
        expected, value = bindings(), envelope()
        if case == "binding_mismatch": value["bindings"]["invocation_id"] = "f" * 32
        elif case == "duplicate":
            raw = canonical(value).replace(b'"delivery_status":"returned"', b'"delivery_status":"returned","delivery_status":"returned"')
        elif case == "cancellation": value = envelope(delivery="cancelled", native=result())
        else:
            expected["source_closure_sha256"] = value["bindings"]["source_closure_sha256"] = "f" * 64
        raw = raw if case == "duplicate" else canonical(value)
        # The real guard refuses; this narrow mutant accepts the exact same
        # synthetic packet. This demonstrates sensitivity without disk mutation.
        with pytest.raises(m.OffRecoveryRefusal): m.validate_native_envelope(raw, expected_bindings=expected)
        assert mutant.validate_native_envelope(raw, expected_bindings=expected)["native_tool_authenticated"] is False


def test_independent_controller_source_pin_mutant_detected_with_pure_public_bytes():
    source = Path(m.__file__).read_text()
    before = "or _sha(raw) != digest:"
    assert source.count(before) == 1
    mutant = ModuleType("research.target_price_revisions_qc._off_preparation_source_mutant")
    mutant.__package__ = m.__package__
    exec(compile(source.replace(before, "or False:", 1), "<pure-off-source-pin-mutant>", "exec"), mutant.__dict__)
    supplied = sources()
    supplied[m.PREFIX + "extended_refusal_witness_controller_successor.py"] += b"\n# synthetic public mutation\n"
    with pytest.raises(m.OffRecoveryRefusal): prepare(public_sources=supplied)
    output = mutant.prepare_off_recovery(supplied, repository_observation=observation(), owner_instruction=OWNER)
    assert output["ready_for_dispatch"] is False
