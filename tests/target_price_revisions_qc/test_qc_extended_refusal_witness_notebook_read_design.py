"""Synthetic NEW-notebook wrapper; no actual research node/tool is constructed."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import extended_refusal_witness_notebook_read_design as d
from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_read_design as base

BEGIN = datetime(2026, 10, 22, 1, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs): raise AssertionError("actual provider/private/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def capsule():
    return {"schema": "tpr-ext26-new-notebook-context-v1", "operation_id": d.OPERATION,
        "tool_project_id": d.PROJECT, "notebook_filename": d.NOTEBOOK,
        "creation_metadata_sha256": "1"*64, "tool_context_identity_sha256": "2"*64,
        "project_identity_provenance": "genuine_mia_research_tool_metadata"}


def invoke(qb=None, context=None, **overrides):
    qb = NS(project_id=d.PROJECT, object_store=base.Store()) if qb is None else qb
    context = capsule() if context is None else context
    kwargs = dict(utc_now=lambda: BEGIN, monotonic_clock=lambda: 10,
        reference_equals=lambda left, right: left is right,
        started_utc=BEGIN, started_monotonic=10)
    kwargs.update(overrides)
    return d.read_new_notebook(qb, context, **kwargs)


def build(context=None, **overrides):
    raw = Path(d.__file__).read_bytes()
    kwargs = dict(expected_module_sha256=hashlib.sha256(raw).hexdigest(),
        reader_raw=Path(base.d.__file__).read_bytes(),
        witness_raw=(base.PUBLIC / "extended_refusal_witness_context_successor.py").read_bytes(),
        capsule=capsule() if context is None else context)
    kwargs.update(overrides)
    return d.build_notebook_cell(raw, **kwargs)


def test_only_exact_own_native_project_store_and_two_known_keys_are_read():
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    result = invoke(qb)
    assert result["status"] == "completed_diagnostic_only"
    assert result["native_internal_project_id_observed"] is True
    assert result["native_project_custody_proven"] is False
    assert result["cryptographic_project_attestation_proven"] is False
    assert result["external_capsule_authentication_proven"] is False
    assert result["sdk_hard_timeout_proven"] is False
    assert result["byte_bound_before_native_allocation_proven"] is False
    assert result["explicit_price_history_provider_requests"] == result["new_jobs"] == 0
    assert result["research_node_initialization_may_use_platform_infrastructure"] is True
    assert qb.object_store.calls == [(method, base.d.witness_key(kind)) for kind in base.d.KINDS
        for method in ("contains_key", "read_bytes")]


@pytest.mark.parametrize("field,value", [
    ("schema", "foreign"), ("operation_id", "foreign"), ("tool_project_id", 1),
    ("tool_project_id", True), ("notebook_filename", "mia.ipynb"),
    ("creation_metadata_sha256", "bad"), ("tool_context_identity_sha256", "bad"),
    ("project_identity_provenance", "configured-constant")])
def test_every_external_capsule_binding_refuses_before_store_reads(field, value):
    context = capsule(); context[field] = value
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    assert invoke(qb, context)["status"] == "failed_or_uncertain"
    assert qb.object_store.calls == []


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_capsule_schema_is_closed(change):
    context = capsule()
    if change == "missing": context.pop("creation_metadata_sha256")
    else: context["native_attestation"] = True
    with pytest.raises(ValueError): d.validate_capsule(context)


@pytest.mark.parametrize("project", [0, 1, True, "37650980", None])
def test_native_runtime_project_id_cannot_be_replaced_by_external_capsule(project):
    qb = NS(project_id=project, object_store=base.Store())
    assert invoke(qb)["status"] == "failed_or_uncertain" and qb.object_store.calls == []


@pytest.mark.parametrize("fault", ["utc_deadline", "utc_rollback", "elapsed_utc", "elapsed_monotonic",
    "monotonic_rollback", "monotonic_nan", "monotonic_bool", "naive", "reference_false", "reference_nonbool"])
def test_real_clock_and_store_guard_directions_refuse_before_reads(fault):
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    kwargs = {}
    if fault == "utc_deadline": kwargs["utc_now"] = lambda: datetime.fromisoformat(d.DEADLINE_UTC)
    elif fault == "utc_rollback": kwargs["utc_now"] = lambda: BEGIN-timedelta(seconds=1)
    elif fault == "elapsed_utc":
        kwargs.update(started_utc=BEGIN-timedelta(minutes=10), utc_now=lambda: BEGIN)
    elif fault == "elapsed_monotonic": kwargs["monotonic_clock"] = lambda: 610
    elif fault == "monotonic_rollback": kwargs["monotonic_clock"] = lambda: 9
    elif fault == "monotonic_nan": kwargs["monotonic_clock"] = lambda: float("nan")
    elif fault == "monotonic_bool": kwargs["monotonic_clock"] = lambda: True
    elif fault == "naive": kwargs["utc_now"] = lambda: BEGIN.replace(tzinfo=None)
    elif fault == "reference_false": kwargs["reference_equals"] = lambda *_: False
    else: kwargs["reference_equals"] = lambda *_: 1
    assert invoke(qb, **kwargs)["status"] == "failed_or_uncertain" and qb.object_store.calls == []


@pytest.mark.parametrize("fault", ["project", "store", "capsule"])
def test_guard_rechecks_identity_after_first_contains_before_any_read(fault):
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    original, context, checks = qb.object_store, capsule(), []
    def clock():
        checks.append(None)
        if len(checks) == 4:
            if fault == "project": qb.project_id = 1
            elif fault == "store": qb.object_store = base.Store()
            else: context["creation_metadata_sha256"] = "3"*64
        return BEGIN
    assert invoke(qb, context, utc_now=clock)["status"] == "failed_or_uncertain"
    assert original.calls == [("contains_key", base.d.witness_key("membership"))]


def test_genuine_cancellation_is_not_converted_into_continued_scope_spending():
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    def stop(_key): raise KeyboardInterrupt()
    qb.object_store.read_bytes = stop
    with pytest.raises(KeyboardInterrupt): invoke(qb)
    assert qb.object_store.calls == [("contains_key", base.d.witness_key("membership"))]


def test_single_cell_source_closure_pins_corrected_reader_and_real_native_guards():
    cell = build()
    assert cell == build(dict(reversed(list(capsule().items()))))
    tree = ast.parse(cell)
    constructors = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "_tpr_QuantBook"]
    assert len(constructors) == 1 and constructors[0].args == [] and constructors[0].keywords == []
    assert "reference_equals=_tpr_NativeObject.ReferenceEquals" in cell
    assert "monotonic_clock=_tpr_time.monotonic" in cell
    assert "utc_now=lambda:_tpr_datetime.now(_tpr_timezone.utc)" in cell
    assert d.DEADLINE_UTC in cell and d.NOTEBOOK in cell
    assert "STOP_FIXED_DEADLINE_EXPIRED" in cell and "STOP_NATIVE_CONTEXT_UNAVAILABLE_OR_REFUSED" in cell
    compile(cell, "<public-unexecuted-new-notebook-cell>", "exec")
    with pytest.raises(ValueError): build(expected_module_sha256="a"*64)
    with pytest.raises(ValueError): build(reader_raw=Path(base.d.__file__).read_bytes()+b" ")
    with pytest.raises(ValueError): build(witness_raw=b"foreign")


def test_fixed_deadline_cannot_be_implicitly_renewed_by_later_start():
    qb = NS(project_id=d.PROJECT, object_store=base.Store())
    after = datetime.fromisoformat(d.DEADLINE_UTC)+timedelta(seconds=1)
    assert invoke(qb, started_utc=after, utc_now=lambda: after)["status"] == "failed_or_uncertain"
    assert qb.object_store.calls == []


# TPR-CR28 regression: the wrapper source bound is enforced before the cell is built.


def test_oversized_wrapper_module_is_refused_even_with_a_matching_hash():
    raw = Path(d.__file__).read_bytes() + b"#" * (16385 - len(Path(d.__file__).read_bytes()) + 1) + b"\n"
    assert len(raw) > 16384
    with pytest.raises(ValueError):
        d.build_notebook_cell(raw, expected_module_sha256=hashlib.sha256(raw).hexdigest(),
            reader_raw=Path(base.d.__file__).read_bytes(),
            witness_raw=(base.PUBLIC / "extended_refusal_witness_context_successor.py").read_bytes(), capsule=capsule())
