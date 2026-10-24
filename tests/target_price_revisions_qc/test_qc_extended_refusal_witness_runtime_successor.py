"""Synthetic-only runtime successor checks; no QC/native/provider access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ast
import hashlib
import http.client
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_runtime_successor as m
from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_read_design as base

NOW = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)
PRIVATE = "SYNTHETIC-NATIVE-BODY-DO-NOT-DISCLOSE"


@pytest.fixture(autouse=True)
def deny_actual_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def permit():
    return {"schema": "tpr-ext26-witness-runtime-contract-v1",
        "operation_id": "TPR-EXT26-WITNESS-RUNTIME-SYNTHETIC-ONLY",
        "project_id": m.PROJECT, "job_id": m.JOB,
        "issued_utc": NOW.isoformat(), "expires_utc": (NOW + timedelta(seconds=60)).isoformat(),
        "max_elapsed_seconds": 60, "max_contains_calls": 2, "max_read_calls": 2,
        "max_bytes_each": base.d.MAX_BYTES, "effects_authorized": False}


def capsule():
    return {"schema": "tpr-ext26-witness-runtime-context-v1",
        "operation_id": permit()["operation_id"], "tool_project_id": m.PROJECT,
        "job_id": m.JOB, "tool_context_sha256": "a" * 64,
        "project_identity_provenance": "genuine_mia_ephemeral_tool_metadata"}


def invoke(qb=None, contract=None, context=None, **kwargs):
    if qb is None:
        qb = NS(project_id=m.PROJECT, object_store=base.Store())
    return m.read_runtime_witnesses(qb, permit() if contract is None else contract,
        capsule() if context is None else context, utc_now=kwargs.pop("utc_now", lambda: NOW),
        monotonic_clock=kwargs.pop("monotonic_clock", lambda: 10),
        reference_equals=kwargs.pop("reference_equals", lambda left, right: left is right), **kwargs)


def assert_safe(result):
    assert m.validate_result(result) == result
    wire = json.dumps(result)
    assert PRIVATE not in wire and base.PRIVATE_ID not in wire and base.PRIVATE_NUMBER not in wire
    for key in ("authority_granted", "controller_implemented", "ready_for_dispatch",
                "native_project_custody_proven", "actual_clock_proven", "off_baseline_valid",
                "on_launch_authorized", "external_capsule_authentication_proven",
                "sdk_hard_timeout_proven", "byte_bound_before_native_allocation_proven"):
        assert result[key] is False
    assert result["new_jobs"] == result["new_codex_attempts"] == result["new_looks"] == 0


def test_exact_two_known_keys_and_body_free_metadata_only():
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    result = invoke(qb)
    assert result["status"] == "completed_diagnostic_only"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert [row["kind"] for row in result["objects"]] == ["membership", "mark"]
    assert qb.object_store.calls == [(method, base.d.witness_key(kind))
        for kind in base.d.KINDS for method in ("contains_key", "read_bytes")]
    for row in result["objects"]:
        assert row["status"] == "validated_diagnostic"
        raw = qb.object_store.values[base.d.witness_key(row["kind"])]
        assert row["gzip_bytes"] == len(raw) and row["gzip_sha256"] == hashlib.sha256(raw).hexdigest()
    assert_safe(result)


def test_missing_witnesses_remain_uninterpreted_and_never_mean_valid_baseline():
    qb = NS(project_id=m.PROJECT, object_store=base.Store({}))
    result = invoke(qb)
    assert result["status"] == "completed_diagnostic_only" and result["read_calls"] == 0
    assert all(row["status"] == "absent_uninterpreted" and row["present"] is False for row in result["objects"])
    assert_safe(result)


@pytest.mark.parametrize("field,value", [
    ("schema", "foreign"), ("operation_id", "TPR-EXT26-MIA-WITNESS-READONLY-20261022-002"),
    ("project_id", True), ("project_id", 1), ("job_id", "foreign"),
    ("issued_utc", "2026-10-24T01:00:00"), ("issued_utc", "2026-10-24T02:00:00+01:00"),
    ("expires_utc", NOW.isoformat()), ("expires_utc", (NOW+timedelta(seconds=601)).isoformat()),
    ("max_elapsed_seconds", True), ("max_elapsed_seconds", 0), ("max_elapsed_seconds", 601),
    ("max_contains_calls", 3), ("max_read_calls", 3), ("max_bytes_each", 8192),
    ("effects_authorized", True)])
def test_bad_or_widened_contract_refuses_before_any_store_operation(field, value):
    contract = permit(); contract[field] = value
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    result = invoke(qb, contract=contract)
    assert result["status"] == "failed_or_uncertain" and qb.object_store.calls == []
    assert_safe(result)


@pytest.mark.parametrize("which", ["permit", "capsule"])
@pytest.mark.parametrize("change", ["extra", "missing", "list"])
def test_contract_and_context_are_closed(which, change):
    contract, context = permit(), capsule()
    target = contract if which == "permit" else context
    if change == "extra": target["private_body"] = PRIVATE
    elif change == "missing": target.pop("schema")
    elif which == "permit": contract = []
    else: context = []
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    assert invoke(qb, contract, context)["status"] == "failed_or_uncertain"
    assert qb.object_store.calls == []


@pytest.mark.parametrize("field,value", [("schema", "foreign"), ("operation_id", "foreign"),
    ("tool_project_id", True), ("tool_project_id", 1), ("job_id", "foreign"),
    ("tool_context_sha256", PRIVATE), ("project_identity_provenance", "caller_claim")])
def test_external_metadata_does_not_override_actual_runtime_binding(field, value):
    context = capsule(); context[field] = value
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    result = invoke(qb, context=context)
    assert result["status"] == "failed_or_uncertain" and qb.object_store.calls == []
    assert_safe(result)


@pytest.mark.parametrize("project", [1, True, "37650980", None])
def test_actual_project_id_is_not_a_capsule_assertion(project):
    qb = NS(project_id=project, object_store=base.Store())
    assert invoke(qb)["status"] == "failed_or_uncertain" and qb.object_store.calls == []


@pytest.mark.parametrize("fault", ["future_permit", "expires_at_start", "utc_naive", "utc_offset",
    "utc_rollback", "monotonic_rollback", "monotonic_nan", "monotonic_bool", "elapsed_monotonic",
    "elapsed_utc", "false_reference", "nonbool_reference", "uncallable_clock"])
def test_intrinsic_clock_and_native_reference_checks_refuse_before_store(fault):
    contract = permit(); kwargs = {}
    if fault == "future_permit": kwargs["utc_now"] = lambda: NOW-timedelta(seconds=1)
    elif fault == "expires_at_start": kwargs["utc_now"] = lambda: NOW+timedelta(seconds=60)
    elif fault == "utc_naive": kwargs["utc_now"] = lambda: NOW.replace(tzinfo=None)
    elif fault == "utc_offset": kwargs["utc_now"] = lambda: NOW.astimezone(timezone(timedelta(hours=1)))
    elif fault == "utc_rollback": kwargs["utc_now"] = iter((NOW, NOW-timedelta(microseconds=1))).__next__
    elif fault == "monotonic_rollback": kwargs["monotonic_clock"] = iter((10, 9)).__next__
    elif fault == "monotonic_nan": kwargs["monotonic_clock"] = lambda: float("nan")
    elif fault == "monotonic_bool": kwargs["monotonic_clock"] = lambda: True
    elif fault == "elapsed_monotonic": kwargs["monotonic_clock"] = iter((10, 70)).__next__
    elif fault == "elapsed_utc": kwargs["utc_now"] = iter((NOW, NOW+timedelta(seconds=60))).__next__
    elif fault == "false_reference": kwargs["reference_equals"] = lambda *_: False
    elif fault == "nonbool_reference": kwargs["reference_equals"] = lambda *_: 1
    elif fault == "uncallable_clock": kwargs["utc_now"] = None
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    result = invoke(qb, contract=contract, **kwargs)
    assert result["status"] == "failed_or_uncertain" and qb.object_store.calls == []
    assert_safe(result)


@pytest.mark.parametrize("moment", ["contains", "read"])
@pytest.mark.parametrize("fault", ["expired", "project", "store", "capsule", "permit", "clock_backwards"])
def test_every_post_operation_guard_stops_before_spending_the_second_key(moment, fault):
    contract, context = permit(), capsule()
    state = {"now": NOW}
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    original_store = qb.object_store
    name = "contains_key" if moment == "contains" else "read_bytes"
    original = getattr(original_store, name)
    def changed(key):
        returned = original(key)
        if fault == "expired": state["now"] = NOW+timedelta(seconds=60)
        elif fault == "project": qb.project_id = 1
        elif fault == "store": qb.object_store = base.Store()
        elif fault == "capsule": context["tool_context_sha256"] = "b"*64
        elif fault == "permit": contract["operation_id"] = "TPR-EXT26-WITNESS-RUNTIME-REPLACED"
        elif fault == "clock_backwards": state["now"] = NOW-timedelta(microseconds=1)
        return returned
    setattr(original_store, name, changed)
    result = invoke(qb, contract, context, utc_now=lambda: state["now"])
    assert result["status"] == "failed_or_uncertain"
    assert result["contains_calls"] == 1 and result["read_calls"] == (moment == "read")
    assert original_store.calls == [("contains_key", base.d.witness_key("membership"))] + (
        [("read_bytes", base.d.witness_key("membership"))] if moment == "read" else [])
    assert_safe(result)


def test_clock_rollback_after_an_advance_is_not_hidden_by_start_clock():
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    times = iter((NOW, NOW+timedelta(seconds=2), NOW+timedelta(seconds=1)))
    assert invoke(qb, utc_now=times.__next__)["status"] == "failed_or_uncertain"
    assert qb.object_store.calls == []


@pytest.mark.parametrize("fault", ["read_error", "contains_nonbool", "malformed", "oversize", "arbitrary_iterable"])
def test_native_errors_and_malformed_witnesses_are_body_free_and_stop(fault):
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    if fault == "read_error":
        def refuse(_key): raise RuntimeError(PRIVATE)
        qb.object_store.read_bytes = refuse
    elif fault == "contains_nonbool": qb.object_store.contains_key = lambda _: 1
    else:
        qb.object_store.values[base.d.witness_key("membership")] = (
            PRIVATE.encode() if fault == "malformed" else b"x"*4097 if fault == "oversize" else [1, 2, 3])
    result = invoke(qb)
    assert result["status"] == "failed_or_uncertain" and result["contains_calls"] == 1
    assert result["objects"][0]["status"] == "failed_or_refused"
    assert_safe(result)


def test_cancellation_propagates_without_second_key_and_carries_closed_counts():
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    def cancelled(_key): raise KeyboardInterrupt(PRIVATE)
    qb.object_store.read_bytes = cancelled
    with pytest.raises(m.RuntimeReadCancelled) as caught:
        invoke(qb)
    assert PRIVATE not in str(caught.value)
    result = caught.value.result
    assert result["status"] == "cancelled" and result["contains_calls"] == result["read_calls"] == 1
    result["objects"][0]["kind"] = "tampered"
    assert caught.value.result["objects"][0]["kind"] == "membership"
    assert_safe(caught.value.result)


@pytest.mark.parametrize("field,value", [("plain_bytes", True), ("plain_bytes", 4097),
    ("plain_sha256", PRIVATE), ("plain_sha256", PRIVATE*1000)],
    ids=["bool_size", "over_limit_size", "invalid_hash", "oversized_hash"])
def test_bad_projection_metadata_is_refused_without_erasing_spent_counts(monkeypatch, field, value):
    original = base.d.project_witness
    def bad(*args, **kwargs):
        projected = original(*args, **kwargs)
        projected[field] = value
        return projected
    monkeypatch.setattr(base.d, "project_witness", bad)
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    result = invoke(qb)
    assert result["status"] == "failed_or_uncertain"
    assert result["contains_calls"] == result["read_calls"] == 1
    assert result["objects"][0]["status"] == "failed_or_refused"
    assert_safe(result)


def test_cancellation_during_projection_preserves_spent_counts_and_withholds_partial_body(monkeypatch):
    def interrupted(_encoded, *, kind):
        partial = {"plain_sha256": PRIVATE*1000, "plain_bytes": True, "kind": kind}
        raise KeyboardInterrupt(str(partial))
    monkeypatch.setattr(base.d, "project_witness", interrupted)
    qb = NS(project_id=m.PROJECT, object_store=base.Store())
    with pytest.raises(m.RuntimeReadCancelled) as caught:
        invoke(qb)
    assert caught.value.result["contains_calls"] == caught.value.result["read_calls"] == 1
    assert caught.value.result["objects"][0]["status"] == "failed_or_refused"
    assert PRIVATE not in str(caught.value)
    assert len(qb.object_store.calls) == 2
    assert_safe(caught.value.result)


@pytest.mark.parametrize("fault", ["extra", "bool_count", "reset_count", "authority", "unknown_status",
    "body", "unbounded_hash", "reordered", "bad_size", "fake_completed"])
def test_output_schema_cannot_accept_arbitrary_dictionaries_or_false_counts(fault):
    result = invoke()
    if fault == "extra": result["extra"] = PRIVATE
    elif fault == "bool_count": result["read_calls"] = True
    elif fault == "reset_count": result["read_calls"] = 0
    elif fault == "authority": result["authority_granted"] = True
    elif fault == "unknown_status": result["status"] = PRIVATE
    elif fault == "body": result["objects"][0]["raw"] = PRIVATE
    elif fault == "unbounded_hash": result["objects"][0]["plain_sha256"] = PRIVATE*1000
    elif fault == "reordered": result["objects"].reverse()
    elif fault == "bad_size": result["objects"][0]["gzip_bytes"] = 4097
    elif fault == "fake_completed": result["objects"] = []; result["contains_calls"] = result["read_calls"] = 0
    with pytest.raises(m.RuntimeReadRefusal): m.validate_result(result)


@pytest.mark.parametrize("kind", ["list", "dict", "string_subclass"])
def test_result_status_wrong_types_raise_fixed_body_free_refusal(kind):
    class DerivedString(str):
        pass
    result = invoke()
    result["status"] = [] if kind == "list" else {} if kind == "dict" else DerivedString("completed_diagnostic_only")
    with pytest.raises(m.RuntimeReadRefusal, match="^offline witness runtime contract refused$"):
        m.validate_result(result)


def test_contract_validation_copies_and_does_not_create_a_permit_or_dispatch_path():
    contract, context = permit(), capsule()
    before = deepcopy((contract, context))
    assert json.loads(m.validate_permit(contract)) == contract
    assert json.loads(m.validate_capsule(context, operation_id=contract["operation_id"])) == context
    assert (contract, context) == before
    design = m.design()
    assert design["intrinsic_utc_monotonic_project_store_checks"] is True
    assert all(design[key] is False for key in ("controller_implemented", "program_built", "permit_registered",
        "ready_for_dispatch", "authority_granted", "off_baseline_valid", "on_launch_authorized"))
    raw = Path(m.__file__).read_text()
    tree = ast.parse(raw)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval", "compile", "QuantBook", "open"} for node in ast.walk(tree))
    assert not any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom))
        and any(alias.name.split(".")[0] in {"requests", "http", "socket", "QuantConnect", "subprocess", "os"}
            for alias in node.names) for node in tree.body)


@pytest.mark.parametrize("mutation", ["actual_project", "store_reference", "capsule_binding", "permit_binding"])
def test_intrinsic_guard_mutants_are_killed_by_the_matching_behavioral_regression(monkeypatch, mutation):
    raw = Path(m.__file__).read_text()
    if mutation == "actual_project":
        before = "if type(qb.project_id) is not int or qb.project_id != PROJECT:"
        after = "if False:"
        check = lambda: test_actual_project_id_is_not_a_capsule_assertion(1)
    elif mutation == "store_reference":
        before = "if store is not None and reference_equals(store, qb.object_store) is not True:"
        after = "if False:"
        check = lambda: test_intrinsic_clock_and_native_reference_checks_refuse_before_store("false_reference")
    elif mutation == "capsule_binding":
        before = "or validate_capsule(capsule, operation_id=result[\"operation_id\"]) != frozen_capsule"
        after = "or False"
        check = lambda: test_every_post_operation_guard_stops_before_spending_the_second_key("contains", "capsule")
    else:
        before = "or validate_permit(permit) != frozen_permit"
        after = "or False"
        check = lambda: test_every_post_operation_guard_stops_before_spending_the_second_key("contains", "permit")
    assert raw.count(before) == 1
    namespace = {"__name__": m.__name__}
    exec(compile(raw.replace(before, after, 1), "<synthetic-runtime-guard-mutant>", "exec"), namespace)
    original = m.read_runtime_witnesses
    with monkeypatch.context() as patch:
        patch.setattr(m, "read_runtime_witnesses", namespace["read_runtime_witnesses"])
        with pytest.raises(AssertionError):
            check()
    assert m.read_runtime_witnesses is original
    check()
