"""Generated text executes ONLY with synthetic clocks, context and store."""
import ast
import builtins
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_program_successor as m
from research.target_price_revisions_qc import extended_refusal_witness_runtime_successor as runtime
from tests.target_price_revisions_qc.test_qc_extended_refusal_witness_read_design import Store, PRIVATE_ID, PRIVATE_NUMBER

ROOT = Path(__file__).resolve().parents[2] / "research/target_price_revisions_qc"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def inputs():
    builder_raw = Path(m.__file__).read_bytes()
    return {"builder_raw": builder_raw, "expected_builder_sha256": hashlib.sha256(builder_raw).hexdigest(),
        "runtime_raw": (ROOT / "extended_refusal_witness_runtime_successor.py").read_bytes(),
        "reader_raw": (ROOT / "extended_refusal_witness_read_design.py").read_bytes(),
        "witness_raw": (ROOT / "extended_refusal_witness_context_successor.py").read_bytes(),
        "permit": {"schema": "tpr-ext26-witness-runtime-contract-v1",
            "operation_id": "TPR-EXT26-WITNESS-RUNTIME-SYNTHETIC-ONLY",
            "project_id": runtime.PROJECT, "job_id": runtime.JOB,
            "issued_utc": NOW.isoformat(), "expires_utc": (NOW + timedelta(seconds=60)).isoformat(),
            "max_elapsed_seconds": 60, "max_contains_calls": 2, "max_read_calls": 2,
            "max_bytes_each": 4096, "effects_authorized": False},
        "capsule": {"schema": "tpr-ext26-witness-runtime-context-v1",
            "operation_id": "TPR-EXT26-WITNESS-RUNTIME-SYNTHETIC-ONLY",
            "tool_project_id": runtime.PROJECT, "job_id": runtime.JOB, "tool_context_sha256": "a" * 64,
            "project_identity_provenance": "genuine_mia_ephemeral_tool_metadata"}}


def execute(monkeypatch, *, params=None, qb=None, context=True, utc=None, tick=None, system=True, program=None, ambient=None):
    params = inputs() if params is None else params
    program = m.build_program(**params) if program is None else program
    namespace = {} if ambient is None else dict(ambient)
    system_imports = []
    namespace["_fixture_system_imports"] = system_imports
    if qb is not None:
        namespace["qb"] = qb
    if context is True:
        namespace["TPR_EPHEMERAL_CONTEXT"] = deepcopy(params["capsule"])
    elif context is not False:
        namespace["TPR_EPHEMERAL_CONTEXT"] = context
    real_datetime_module = sys.modules["datetime"]
    fake_datetime_module = ModuleType("datetime")
    fake_datetime_module.__dict__.update(real_datetime_module.__dict__)
    class FixtureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            value = NOW if utc is None else utc()
            return cls.fromisoformat(value.isoformat())
    fake_datetime_module.datetime = FixtureDateTime
    fake_system = ModuleType("System")
    references = []
    class FixtureObject:
        @staticmethod
        def ReferenceEquals(left, right):
            references.append((left, right))
            return left is right
    fake_system.Object = FixtureObject
    stdout = io.StringIO()
    original_import = builtins.__import__
    def counted_import(name, *args, **kwargs):
        if name == "System": system_imports.append(name)
        return original_import(name, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "datetime", fake_datetime_module)
        patch.setattr(__import__("time"), "monotonic", (lambda: 10) if tick is None else tick)
        if system:
            patch.setitem(sys.modules, "System", fake_system)
        else:
            patch.setitem(sys.modules, "System", None)
        patch.setattr(builtins, "__import__", counted_import)
        with redirect_stdout(stdout):
            exec(compile(program, "<synthetic-generated-witness-program>", "exec"), namespace)
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert runtime.validate_result(result) == result
    assert PRIVATE_ID not in lines[0] and PRIVATE_NUMBER not in lines[0]
    return result, namespace, references


def test_closed_dependency_projection_and_actual_callbacks_are_generated_not_external():
    params = inputs(); original = deepcopy(params)
    text = m.build_program(**params)
    assert params == original
    assert len(text.encode()) <= m.MAX_PROGRAM_BYTES
    tree = ast.parse(text)
    definitions = {node.targets[0].id: node.value for node in tree.body
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    bindings = ast.literal_eval(definitions["_tpr_bindings"])
    assert set(bindings) == set(m.SOURCE_SHA256)
    for name, binding in bindings.items():
        assert hashlib.sha256(binding["raw"].encode()).hexdigest() == m.SOURCE_SHA256[name]
    assert "_tpr_datetime.now(_tpr_timezone.utc)" in text
    assert "monotonic_clock=_tpr_time.monotonic" in text
    assert "reference_equals=_tpr_Object.ReferenceEquals" in text
    assert text.index("_tpr_issued <= _tpr_now < _tpr_expiry") < text.index("from System import Object")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(isinstance(node.func, ast.Name) and node.func.id in {"QuantBook", "open", "eval"} for node in calls)
    assert "SCOPE_CHECK" not in {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_generated_two_key_success_does_not_embed_or_call_old_unsafe_reader(monkeypatch):
    qb = NS(project_id=runtime.PROJECT, object_store=Store())
    result, namespace, references = execute(monkeypatch, qb=qb)
    assert result["status"] == "completed_diagnostic_only"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert len(qb.object_store.calls) == 4 and references
    projection = namespace["_tpr_payloads"]["projection"]["raw"]
    names = {node.name for node in ast.parse(projection).body if isinstance(node, ast.FunctionDef)}
    assert not {"read_native_witnesses", "build_native_program", "_check_scope", "design"} & names
    assert {"project_witness", "_native_bytes", "witness_key"} <= names
    assert result["actual_clock_proven"] is result["native_project_custody_proven"] is False


@pytest.mark.parametrize("name", ["builder", "runtime", "reader", "witness"])
def test_corrupt_source_refuses_before_program_or_any_effect(name):
    params = inputs(); params[name + "_raw"] += b"\n# synthetic source drift\n"
    with pytest.raises(m.ProgramBuildRefusal, match="^prospective witness program build refused$"):
        m.build_program(**params)


@pytest.mark.parametrize("fault", ["bad_builder_digest", "builder_notbytes", "oversize_builder",
    "widened_permit", "extra_capsule", "wrong_project", "active_authority", "nonfinite"])
def test_invalid_prospective_inputs_refuse(fault):
    params = inputs()
    if fault == "bad_builder_digest": params["expected_builder_sha256"] = "x" * 64
    elif fault == "builder_notbytes": params["builder_raw"] = "source"
    elif fault == "oversize_builder": params["builder_raw"] = b"x" * (m.MAX_SOURCE_BYTES + 1)
    elif fault == "widened_permit": params["permit"]["max_read_calls"] = 3
    elif fault == "extra_capsule": params["capsule"]["extra"] = PRIVATE_ID
    elif fault == "wrong_project": params["capsule"]["tool_project_id"] = 1
    elif fault == "active_authority": params["permit"]["effects_authorized"] = True
    else: params["permit"]["max_elapsed_seconds"] = float("nan")
    with pytest.raises(m.ProgramBuildRefusal): m.build_program(**params)


class ForbiddenGetters:
    def __init__(self): self.getters = []
    @property
    def project_id(self):
        self.getters.append("project_id")
        raise AssertionError("native getter must not run")
    @property
    def object_store(self):
        self.getters.append("object_store")
        raise AssertionError("native getter must not run")


@pytest.mark.parametrize("fault", ["missing_qb", "missing_context", "wrong_context", "expired", "future", "missing_system"])
def test_initial_refusals_precede_every_native_getter_and_store(monkeypatch, fault):
    qb = ForbiddenGetters()
    context, utc, system = True, None, True
    if fault == "missing_context": context = False
    elif fault == "wrong_context": context = {"private": PRIVATE_ID}
    elif fault == "expired": utc = lambda: NOW + timedelta(seconds=60)
    elif fault == "future": utc = lambda: NOW - timedelta(microseconds=1)
    elif fault == "missing_system": system = False
    result, namespace, references = execute(monkeypatch, qb=None if fault == "missing_qb" else qb,
        context=context, utc=utc, system=system)
    assert result["status"] == "failed_or_uncertain" and result["contains_calls"] == result["read_calls"] == 0
    assert qb.getters == [] and references == []
    assert namespace["_fixture_system_imports"] == (["System"] if fault == "missing_system" else [])


@pytest.mark.parametrize("moment", ["contains_key", "read_bytes"])
@pytest.mark.parametrize("fault", ["expired", "project", "store", "context", "monotonic"])
def test_generated_intrinsic_post_call_checks_stop_before_second_key(monkeypatch, moment, fault):
    params = inputs(); context = deepcopy(params["capsule"])
    qb = NS(project_id=runtime.PROJECT, object_store=Store())
    store = qb.object_store
    state = {"now": NOW, "tick": 10}
    original = getattr(store, moment)
    def changed(key):
        value = original(key)
        if fault == "expired": state["now"] = NOW + timedelta(seconds=60)
        elif fault == "monotonic": state["tick"] = 70
        elif fault == "project": qb.project_id = 1
        elif fault == "store": qb.object_store = Store()
        else: context["tool_context_sha256"] = "b" * 64
        return value
    setattr(store, moment, changed)
    result, _, _ = execute(monkeypatch, params=params, qb=qb, context=context,
        utc=lambda: state["now"], tick=lambda: state["tick"])
    assert result["status"] == "failed_or_uncertain"
    assert result["contains_calls"] == 1 and result["read_calls"] == (moment == "read_bytes")
    assert len(store.calls) == 1 + (moment == "read_bytes")


def test_generated_missing_witnesses_do_not_mean_missing_baseline_data(monkeypatch):
    qb = NS(project_id=runtime.PROJECT, object_store=Store({}))
    result, _, _ = execute(monkeypatch, qb=qb)
    assert result["status"] == "completed_diagnostic_only" and result["read_calls"] == 0
    assert all(row["status"] == "absent_uninterpreted" for row in result["objects"])
    assert result["off_baseline_valid"] is result["on_launch_authorized"] is False


def test_generated_cancellation_propagates_closed_spent_counts_without_second_key(monkeypatch):
    qb = NS(project_id=runtime.PROJECT, object_store=Store())
    def cancelled(_key): raise KeyboardInterrupt(PRIVATE_ID)
    qb.object_store.read_bytes = cancelled
    try:
        execute(monkeypatch, qb=qb)
    except KeyboardInterrupt as exc:
        result = exc.result
        assert result["status"] == "cancelled" and result["contains_calls"] == result["read_calls"] == 1
        assert runtime.validate_result(result) == result
        assert PRIVATE_ID not in str(exc)
    else:
        pytest.fail("cancellation was swallowed")
    assert len(qb.object_store.calls) == 1


@pytest.mark.parametrize("name", ["runtime", "reader", "witness"])
def test_standalone_source_drift_refuses_before_native_getter(monkeypatch, name):
    text = m.build_program(**inputs())
    target = "'sha256': '" + m.SOURCE_SHA256[name] + "'"
    assert text.count(target) == 1
    changed = text.replace(target, "'sha256': '" + "f" * 64 + "'", 1)
    qb = ForbiddenGetters()
    result, namespace, references = execute(monkeypatch, qb=qb, program=changed)
    assert result == runtime._new_result()
    assert qb.getters == [] and namespace["_fixture_system_imports"] == [] and references == []


@pytest.mark.parametrize("name", ["projection", "runtime"])
def test_compiled_payload_drift_is_detected_even_with_original_sources_unchanged(monkeypatch, name):
    tree = ast.parse(m.build_program(**inputs()))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_tpr_payloads")
    payloads = ast.literal_eval(assignment.value)
    payloads[name]["raw"] += "\nraise AssertionError('synthetic payload drift executed')\n"
    assignment.value = ast.parse(repr(payloads), mode="eval").body
    changed = ast.unparse(ast.fix_missing_locations(tree))
    qb = ForbiddenGetters()
    result, namespace, references = execute(monkeypatch, qb=qb, program=changed)
    assert result == runtime._new_result() and qb.getters == []
    assert namespace["_fixture_system_imports"] == [] and references == []


@pytest.mark.parametrize("name", ["globals", "exec", "compile", "any", "print", "Exception", "KeyboardInterrupt",
    "UTC_NOW", "MONOTONIC_CLOCK", "REFERENCE_EQUALS", "SCOPE_CHECK", "OBSERVED_PROJECT_ID"])
def test_ambient_names_cannot_replace_intrinsic_builtins_callbacks_or_actual_context(monkeypatch, name):
    calls = []
    def poison(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("ambient override executed")
    qb = NS(project_id=runtime.PROJECT, object_store=Store())
    result, _, _ = execute(monkeypatch, qb=qb, ambient={name: poison})
    assert result["status"] == "completed_diagnostic_only" and len(qb.object_store.calls) == 4
    assert calls == []


def test_poisoned_globals_cannot_mask_missing_actual_context(monkeypatch):
    qb = ForbiddenGetters()
    result, namespace, _ = execute(monkeypatch, qb=qb, context=False,
        ambient={"globals": lambda: {"TPR_EPHEMERAL_CONTEXT": inputs()["capsule"]}})
    assert result["status"] == "failed_or_uncertain" and qb.getters == []
    assert namespace["_fixture_system_imports"] == []


@pytest.mark.parametrize("mutation", ["ambient_globals", "initial_expiry", "payload_binding", "original_binding",
    "cancellation", "ambient_print"])
def test_matching_in_memory_mutations_are_killed_after_clean_control(monkeypatch, mutation):
    original = m.build_program(**inputs())
    if mutation == "ambient_globals":
        before, after = "_tpr_namespace = _tpr_builtins.globals()", "_tpr_namespace = globals()"
        def check(program):
            qb = ForbiddenGetters()
            result, namespace, _ = execute(monkeypatch, qb=qb, context=False, program=program,
                ambient={"globals": lambda: {"qb": qb, "TPR_EPHEMERAL_CONTEXT": inputs()["capsule"]}})
            assert result["status"] == "failed_or_uncertain" and qb.getters == []
            assert namespace["_fixture_system_imports"] == []
    elif mutation == "initial_expiry":
        before = "if not _tpr_issued <= _tpr_now < _tpr_expiry or 'qb' not in _tpr_namespace:"
        after = "if 'qb' not in _tpr_namespace:"
        def check(program):
            qb = ForbiddenGetters()
            result, namespace, _ = execute(monkeypatch, qb=qb, program=program,
                utc=lambda: NOW + timedelta(seconds=60))
            assert result["status"] == "failed_or_uncertain" and qb.getters == []
            assert namespace["_fixture_system_imports"] == []
    elif mutation in {"payload_binding", "original_binding"}:
        before = "for _tpr_group in (_tpr_bindings, _tpr_payloads) for v in _tpr_group.values()"
        after = "for _tpr_group in (" + ("_tpr_bindings" if mutation == "payload_binding" else "_tpr_payloads") + ",) for v in _tpr_group.values()"
        def check(program):
            qb = ForbiddenGetters()
            pin = (hashlib.sha256(m._projection_source(inputs()["reader_raw"].decode(),
                m._contract(inputs()["witness_raw"].decode())).encode()).hexdigest()
                if mutation == "payload_binding" else m.SOURCE_SHA256["reader"])
            target = "'sha256': '" + pin + "'"
            assert program.count(target) == 1
            tampered = program.replace(target, "'sha256': '" + "f" * 64 + "'", 1)
            result, namespace, _ = execute(monkeypatch, qb=qb, program=tampered)
            assert result == runtime._new_result() and qb.getters == []
            assert namespace["_fixture_system_imports"] == []
    elif mutation == "cancellation":
        before = "except _tpr_runtime.RuntimeReadCancelled:\n        raise"
        after = "except _tpr_runtime.RuntimeReadCancelled:\n        pass"
        def check(program):
            qb = NS(project_id=runtime.PROJECT, object_store=Store())
            def cancelled(_key): raise KeyboardInterrupt(PRIVATE_ID)
            qb.object_store.read_bytes = cancelled
            try:
                execute(monkeypatch, qb=qb, program=program)
            except KeyboardInterrupt as exc:
                assert exc.result["contains_calls"] == exc.result["read_calls"] == 1
            else:
                raise AssertionError("mutant swallowed cancellation")
    else:
        before, after = "_tpr_builtins.print(_tpr_json.dumps", "print(_tpr_json.dumps"
        def check(program):
            def poison(*args, **kwargs): raise AssertionError("ambient output override")
            result, _, _ = execute(monkeypatch, qb=NS(project_id=runtime.PROJECT, object_store=Store()),
                program=program, ambient={"print": poison})
            assert result["status"] == "completed_diagnostic_only"
    assert original.count(before) == 1
    check(original)
    with pytest.raises(AssertionError): check(original.replace(before, after, 1))
    check(original)


def test_build_and_design_never_create_active_contract_or_effect_entrypoint():
    design = m.design()
    for key in ("authority_granted", "permit_registered", "ready_for_dispatch", "native_project_custody_proven",
                "sdk_hard_timeout_proven", "byte_bound_before_native_allocation_proven", "off_baseline_valid", "on_launch_authorized"):
        assert design[key] is False
    assert design["new_jobs"] == design["new_codex_attempts"] == design["new_looks"] == 0
    tree = ast.parse(Path(m.__file__).read_text())
    assert not any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "exec", "eval", "QuantBook"} for node in ast.walk(tree))
