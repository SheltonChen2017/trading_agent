"""Synthetic local custody only: no genuine provider/native/QC capability."""
import ast
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_controller_successor as m
from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_runtime_successor as prior

PRIVATE = "SYNTHETIC-NATIVE-ERROR-DO-NOT-RETAIN"


@pytest.fixture(autouse=True)
def deny_actual_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def plan(directory):
    contract, capsule = prior.permit(), prior.capsule()
    result = {"schema": "tpr-ext26-witness-controller-contract-v1", "operation_id": contract["operation_id"],
        "mode": "offline-prepared-synthetic-only", "git_head": "a"*40, "physical_root": str(m.LANE),
        "branch": m.BRANCH, "source_hashes": m.source_hashes(), "owner_instruction_sha256": "b"*64,
        "receipt_directory": str(directory), "program_sha256": "c"*64,
        "permit": contract, "capsule_sha256": hashlib.sha256(m.runtime.validate_capsule(capsule,
            operation_id=contract["operation_id"])).hexdigest()}
    result["program_sha256"] = hashlib.sha256(m._program_bytes(result, capsule, m._public_sources())).hexdigest()
    return result


def repository_guard():
    return {"physical_root": str(m.LANE), "git_toplevel": str(m.LANE), "branch": m.BRANCH, "git_head": "a"*40}


def invoke(directory, *, contract=None, context=None, seam=None, **kwargs):
    checked = plan(directory) if contract is None else contract
    capsule = prior.capsule() if context is None else context
    # Deliberately malformed capsules are refused before program construction.
    if context is not None and context.get("tool_project_id") != m.runtime.PROJECT:
        m.validate_plan(checked, context)
    generated = m._program_bytes(checked, prior.capsule(), m._public_sources())
    adapter = (lambda program_raw, permit, capsule: prior.invoke(contract=permit, context=capsule)) if seam is None else seam
    # Explicit test-only policy override, not a callable's no-IO assertion.
    # The same finally-safe override applies to an in-memory mutant namespace.
    function = m.execute_prepared_read
    namespace = function.__globals__
    previous_policy = namespace["NATIVE_ADAPTER_PERMITTED"]
    namespace["NATIVE_ADAPTER_PERMITTED"] = True
    try:
        return function(checked, capsule, directory, program_raw=kwargs.pop("program_raw", generated),
            native_read=adapter,
            repository_guard=kwargs.pop("repository_guard", repository_guard),
            utc_now=kwargs.pop("utc_now", lambda: prior.NOW),
            monotonic_clock=kwargs.pop("monotonic_clock", lambda: 10), **kwargs)
    finally:
        namespace["NATIVE_ADAPTER_PERMITTED"] = previous_policy


def assert_saved(directory, result):
    assert m.validate_receipt(result) == result
    receipts = list(directory.glob("*.result.json"))
    selected = directory / (result["operation_id"] + ".attempt-" + result["invocation_id"] + ".result.json")
    assert selected in receipts and json.loads(selected.read_bytes()) == result
    assert PRIVATE not in selected.read_text()
    assert result["new_jobs"] == result["new_codex_attempts"] == result["new_looks"] == 0
    assert all(result[key] is False for key in m._FALSE_KEYS)


def test_completed_diagnostic_has_lock_before_claim_and_one_native_invocation(tmp_path):
    calls = []
    def native_read(program_raw, permit, capsule):
        assert hashlib.sha256(program_raw).hexdigest() == plan(tmp_path)["program_sha256"]
        assert (tmp_path / "controller.lock").is_file()
        assert len(list(tmp_path.glob("*.claim.spent.json"))) == 1
        assert len(list(tmp_path.glob("*.access.json"))) == 1
        calls.append(True)
        return prior.invoke(contract=permit, context=capsule)
    result = invoke(tmp_path, seam=native_read)
    assert result["status"] == "completed_diagnostic_only" and calls == [True]
    assert result["lock_acquired"] and result["lock_cleanup_complete"]
    assert result["contains_calls"] == result["read_calls"] == 2
    assert not (tmp_path / "controller.lock").exists()
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("cancel", [False, True])
def test_exact_controller_program_runtime_composition_is_synthetic_end_to_end(tmp_path, monkeypatch, cancel):
    from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_program_successor as generated
    qb = SimpleNamespace(project_id=m.runtime.PROJECT, object_store=prior.base.Store())
    if cancel:
        def interrupted_read(_key):
            raise KeyboardInterrupt(PRIVATE)
        qb.object_store.read_bytes = interrupted_read
    calls = []
    def synthetic_adapter(program_raw, permit, capsule):
        assert (tmp_path / "controller.lock").is_file()
        assert len(list(tmp_path.glob("*.claim.spent.json"))) == 1
        calls.append(hashlib.sha256(program_raw).hexdigest())
        params = generated.inputs()
        params["permit"], params["capsule"] = permit, capsule
        try:
            result, _, references = generated.execute(monkeypatch, params=params, qb=qb,
                utc=lambda: prior.NOW, program=program_raw.decode("utf-8"))
        except KeyboardInterrupt as error:
            # Standalone program has its own class identity. A future reviewed
            # transport must likewise retain/validate the closed cancellation
            # result; this adapter is SYNTHETIC and has no genuine capability.
            raise m.runtime.RuntimeReadCancelled(m.runtime.validate_result(error.result)) from None
        assert references
        return m.runtime.validate_result(result)
    if cancel:
        with pytest.raises(m.ControllerCancelled) as caught:
            invoke(tmp_path, seam=synthetic_adapter)
        result = caught.value.receipt
        assert result["status"] == "cancelled"
        assert result["contains_calls"] == result["read_calls"] == 1
        assert len(qb.object_store.calls) == 1
    else:
        result = invoke(tmp_path, seam=synthetic_adapter)
        assert result["status"] == "completed_diagnostic_only"
        assert result["contains_calls"] == result["read_calls"] == 2
        assert len(qb.object_store.calls) == 4
    assert len(calls) == result["native_read_invocations"] == 1
    assert_saved(tmp_path, result)


def test_lock_contention_never_claims_or_deletes_another_process_lock(tmp_path):
    lock = tmp_path / "controller.lock"
    lock.write_bytes(b"foreign lock must remain")
    result = invoke(tmp_path, seam=lambda *_: pytest.fail("must not read"))
    assert result["failure_stage"] == "lock" and not result["claim_written"]
    assert not list(tmp_path.glob("*.claim.spent.json"))
    assert lock.read_bytes() == b"foreign lock must remain"
    assert result["native_read_invocations"] == 0
    assert_saved(tmp_path, result)


def test_replay_adds_unique_refusal_receipt_without_overwriting_prior_evidence(tmp_path):
    original = invoke(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    replay = invoke(tmp_path, seam=lambda *_: pytest.fail("spent scope cannot read"))
    assert replay["failure_stage"] == "claim" and replay["status"] == "failed_or_uncertain"
    assert replay["invocation_id"] != original["invocation_id"]
    assert all((tmp_path / name).read_bytes() == raw for name, raw in before.items())
    assert len(list(tmp_path.glob("*.result.json"))) == 2
    assert_saved(tmp_path, replay)


def test_access_receipt_failure_is_durable_and_never_reads(tmp_path, monkeypatch):
    original = m._publish
    def fail_access(fd, name, raw):
        if name.endswith(".access.json"):
            raise OSError(PRIVATE)
        return original(fd, name, raw)
    monkeypatch.setattr(m, "_publish", fail_access)
    result = invoke(tmp_path, seam=lambda *_: pytest.fail("must not read"))
    assert result["failure_stage"] == "access" and result["claim_written"] and result["scope_spent"]
    assert result["native_read_invocations"] == 0
    assert_saved(tmp_path, result)


def test_uncertain_claim_publication_stays_spent_after_a_successful_link(tmp_path, monkeypatch):
    original = m._publish
    def ambiguous_claim(fd, name, raw):
        result = original(fd, name, raw)
        if name.endswith(".claim.spent.json"):
            raise OSError(PRIVATE)
        return result
    monkeypatch.setattr(m, "_publish", ambiguous_claim)
    result = invoke(tmp_path, seam=lambda *_: pytest.fail("must not read"))
    assert result["claim_attempted"] and result["scope_spent"] and not result["claim_written"]
    assert result["failure_stage"] == "claim" and result["native_read_invocations"] == 0
    assert len(list(tmp_path.glob("*.claim.spent.json"))) == 1
    assert_saved(tmp_path, result)


def test_interrupt_during_owned_lock_cleanup_is_durable_and_propagates(tmp_path, monkeypatch):
    original = os.stat
    state = {"interrupted": False}
    def interrupted_stat(path, *args, **kwargs):
        if path == "controller.lock" and not state["interrupted"]:
            state["interrupted"] = True
            raise KeyboardInterrupt(PRIVATE)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "stat", interrupted_stat)
    with pytest.raises(m.ControllerCancelled) as caught:
        invoke(tmp_path)
    result = caught.value.receipt
    assert result["failure_stage"] == "cleanup" and result["status"] == "cancelled"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("fault", ["raises", "oversized", "wrong_operation", "body", "foreign_project"])
def test_bad_native_results_leave_uncertain_counts_not_fabricated_zero(tmp_path, fault):
    def seam(program_raw, permit, capsule):
        if fault == "raises":
            raise RuntimeError(PRIVATE)
        result = prior.invoke(contract=permit, context=capsule)
        if fault == "oversized": result["objects"][0]["plain_sha256"] = PRIVATE*1000
        elif fault == "wrong_operation": result["operation_id"] = "TPR-EXT26-WITNESS-RUNTIME-OTHER"
        elif fault == "body": result["raw_body"] = PRIVATE
        else: result["project_id"] = 1
        return result
    result = invoke(tmp_path, seam=seam)
    assert result["status"] == "failed_or_uncertain" and result["native_read_invocations"] == 1
    assert result["contains_calls"] is None and result["read_calls"] is None and result["runtime_result"] is None
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("fault", ["expired", "head", "capsule", "sources", "monotonic", "utc_rollback"])
def test_post_read_scope_failure_preserves_returned_native_counts(tmp_path, fault):
    contract, capsule = plan(tmp_path), prior.capsule()
    state = {"now": prior.NOW, "tick": 10, "head": "a"*40}
    def seam(program_raw, permit, context):
        result = prior.invoke(contract=permit, context=context)
        if fault == "expired": state["now"] += timedelta(seconds=60)
        elif fault == "head": state["head"] = "c"*40
        elif fault == "capsule": capsule["tool_context_sha256"] = "c"*64
        elif fault == "sources": contract["source_hashes"][m.SOURCE_PATHS[0]] = "c"*64
        elif fault == "monotonic": state["tick"] += 60
        else: state["now"] -= timedelta(microseconds=1)
        return result
    def guard():
        value = repository_guard(); value["git_head"] = state["head"]; return value
    result = invoke(tmp_path, contract=contract, context=capsule, seam=seam,
        utc_now=lambda: state["now"], monotonic_clock=lambda: state["tick"], repository_guard=guard)
    assert result["status"] == "failed_or_uncertain" and result["failure_stage"] == "post_read"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("typed", [False, True])
def test_cancellation_is_durable_and_propagates_without_follow_on_read(tmp_path, typed):
    def seam(program_raw, permit, capsule):
        if typed:
            result = prior.invoke(contract=permit, context=capsule)
            result["status"] = "cancelled"
            raise m.runtime.RuntimeReadCancelled(result)
        raise KeyboardInterrupt(PRIVATE)
    with pytest.raises(m.ControllerCancelled) as caught:
        invoke(tmp_path, seam=seam)
    result = caught.value.receipt
    assert result["status"] == "cancelled" and result["native_read_invocations"] == 1
    assert result["contains_calls"] == (2 if typed else None)
    assert PRIVATE not in str(caught.value)
    assert_saved(tmp_path, result)
    result["operation_id"] = "tampered"
    assert caught.value.receipt["operation_id"] != "tampered"


def test_replaced_lock_is_preserved_and_receipt_reports_failed_custody(tmp_path):
    replacement = b"foreign replacement"
    def seam(program_raw, permit, capsule):
        (tmp_path / "controller.lock").unlink()
        (tmp_path / "controller.lock").write_bytes(replacement)
        return prior.invoke(contract=permit, context=capsule)
    result = invoke(tmp_path, seam=seam)
    assert result["status"] == "failed_or_uncertain" and result["failure_stage"] == "cleanup"
    assert not result["lock_cleanup_complete"] and (tmp_path / "controller.lock").read_bytes() == replacement
    assert_saved(tmp_path, result)


def test_unavailable_directory_and_failed_receipt_raise_explicit_body_free_error(tmp_path, monkeypatch):
    absent = tmp_path / "not-created"
    with pytest.raises(m.ControllerReceiptUnavailable, match="no read attempted"):
        invoke(absent, seam=lambda *_: pytest.fail("no read"))
    original = m._publish
    def refuse_result(fd, name, raw):
        if name.endswith(".result.json"): raise OSError(PRIVATE)
        return original(fd, name, raw)
    monkeypatch.setattr(m, "_publish", refuse_result)
    with pytest.raises(m.ControllerReceiptUnavailable, match="no automatic retry"):
        invoke(tmp_path)
    assert not list(tmp_path.glob("*.result.json"))


@pytest.mark.parametrize("fault", ["source", "root", "branch", "head", "deadline", "clock_nan", "clock_bool", "clock_rollback"])
def test_preflight_refuses_before_lock_claim_or_native_effect(tmp_path, fault):
    contract = plan(tmp_path); kwargs = {}
    if fault == "source": contract["source_hashes"][m.SOURCE_PATHS[0]] = "c"*64
    elif fault in {"root", "branch", "head"}:
        field = {"root": "physical_root", "branch": "branch", "head": "git_head"}[fault]
        def guard():
            value = repository_guard(); value[field] = "mismatch"; return value
        kwargs["repository_guard"] = guard
    elif fault == "deadline": kwargs["utc_now"] = lambda: prior.NOW+timedelta(seconds=60)
    elif fault == "clock_nan": kwargs["monotonic_clock"] = lambda: float("nan")
    elif fault == "clock_bool": kwargs["monotonic_clock"] = lambda: True
    else: kwargs["monotonic_clock"] = iter((10, 9)).__next__
    result = invoke(tmp_path, contract=contract, seam=lambda *_: pytest.fail("no read"), **kwargs)
    assert result["status"] == "failed_or_uncertain" and result["native_read_invocations"] == 0
    assert not result["claim_written"]
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("fault", ["production", "extra", "foreign_capsule", "bad_hash", "extra_source", "callable_default"])
def test_closed_plan_has_no_active_production_scope_or_implicit_adapter(tmp_path, fault):
    contract, capsule = plan(tmp_path), prior.capsule()
    if fault == "production": contract["mode"] = "production"
    elif fault == "extra": contract["authority_granted"] = True
    elif fault == "foreign_capsule": capsule["tool_project_id"] = 1
    elif fault == "bad_hash": contract["owner_instruction_sha256"] = PRIVATE
    elif fault == "extra_source": contract["source_hashes"]["extra.py"] = "c"*64
    else:
        with pytest.raises(TypeError): m.execute_prepared_read(contract, capsule, tmp_path)
        return
    with pytest.raises(m.ControllerRefusal): invoke(tmp_path, contract=contract, context=capsule)
    assert not list(tmp_path.iterdir())


def test_source_has_no_cli_credentials_network_clients_or_launch_imports():
    tree = ast.parse(Path(m.__file__).read_text())
    assert not any(isinstance(node, ast.FunctionDef) and node.name in {"main", "execute_plan"} for node in tree.body)
    prohibited = {"http", "requests", "socket", "subprocess", "QuantConnect", "clr", "argparse"}
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name.split(".")[0] in prohibited
        for alias in node.names) for node in ast.walk(tree))
    assert all(m.design()[key] is False for key in ("current_permit_registered", "native_adapter_constructed",
        "ready_for_dispatch", "authority_granted", "off_baseline_valid", "on_launch_authorized", "native_binding_proven"))


def test_self_pinned_arbitrary_program_is_not_the_exact_independently_built_program(tmp_path):
    contract = plan(tmp_path)
    arbitrary = b"raise RuntimeError('must never dispatch arbitrary text')\n"
    contract["program_sha256"] = hashlib.sha256(arbitrary).hexdigest()
    result = invoke(tmp_path, contract=contract, program_raw=arbitrary, seam=lambda *_: pytest.fail("no read"))
    assert result["failure_stage"] == "preflight" and not result["claim_attempted"]
    assert result["native_read_invocations"] == 0
    assert_saved(tmp_path, result)


@pytest.mark.parametrize("fault", ["hash", "text", "oversized", "directory"])
def test_program_and_directory_bindings_refuse_before_any_claim_or_native_effect(tmp_path, fault):
    contract = plan(tmp_path)
    program_raw = m._program_bytes(contract, prior.capsule(), m._public_sources())
    if fault == "hash": program_raw += b"\n"
    elif fault == "text": program_raw = program_raw.decode()
    elif fault == "oversized": program_raw = b"x"*(m.program.MAX_PROGRAM_BYTES+1)
    else: contract["receipt_directory"] = str(tmp_path / "other")
    with pytest.raises(m.ControllerRefusal):
        invoke(tmp_path, contract=contract, program_raw=program_raw, seam=lambda *_: pytest.fail("no read"))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field,value", [
    ("contains_calls", True), ("read_calls", True), ("scope_spent", False),
    ("native_read_invocations", True), ("on_launch_authorized", True), ("new_looks", 1),
    ("status", []), ("failure_stage", {}), ("runtime_result", {"raw": PRIVATE}),
    ("lock_cleanup_complete", False)])
def test_closed_receipt_rejects_false_accounting_and_arbitrary_native_bodies(tmp_path, field, value):
    receipt = invoke(tmp_path)
    receipt[field] = value
    with pytest.raises((m.ControllerRefusal, m.runtime.RuntimeReadRefusal)):
        m.validate_receipt(receipt)


@pytest.mark.parametrize("mutation", ["source", "post_read", "lock_before_claim", "unknown_counts", "owned_cleanup", "claim_uncertainty"])
def test_meaningful_controller_mutants_are_killed_and_real_definition_restored(tmp_path, monkeypatch, mutation):
    raw = Path(m.__file__).read_text()
    if mutation == "source":
        before, after = 'or {name: _sha(raw) for name, raw in sources.items()} != checked["source_hashes"]', 'or False'
        check = lambda path, patch: test_preflight_refuses_before_lock_claim_or_native_effect(path, "source")
    elif mutation == "post_read":
        before, after = 'receipt["failure_stage"] = "post_read"\n            check()', 'receipt["failure_stage"] = "post_read"'
        check = lambda path, patch: test_post_read_scope_failure_preserves_returned_native_counts(path, "expired")
    elif mutation == "lock_before_claim":
        before = 'receipt["failure_stage"] = "lock"\n            lock = os.open'
        after = 'receipt["failure_stage"] = "lock"\n            _publish(fd, checked["operation_id"] + ".claim.spent.json", frozen_plan)\n            lock = os.open'
        check = lambda path, patch: test_lock_contention_never_claims_or_deletes_another_process_lock(path)
    elif mutation == "unknown_counts":
        before, after = 'receipt["contains_calls"] = receipt["read_calls"] = None', 'receipt["contains_calls"] = receipt["read_calls"] = 0'
        check = lambda path, patch: test_bad_native_results_leave_uncertain_counts_not_fabricated_zero(path, "raises")
    elif mutation == "owned_cleanup":
        before, after = '(named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino):\n                        os.unlink("controller.lock"', 'True:\n                        os.unlink("controller.lock"'
        check = lambda path, patch: test_replaced_lock_is_preserved_and_receipt_reports_failed_custody(path)
    else:
        before, after = 'receipt["claim_attempted"] = receipt["scope_spent"] = True', 'receipt["claim_attempted"] = True'
        check = lambda path, patch: test_uncertain_claim_publication_stays_spent_after_a_successful_link(path, patch)
    assert raw.count(before) == 1
    namespace = {"__name__": m.__name__, "__file__": m.__file__}
    exec(compile(raw.replace(before, after, 1), "<synthetic-controller-mutant>", "exec"), namespace)
    original = m.execute_prepared_read
    control, mutant, restored = (tmp_path / name for name in ("control", "mutant", "restored"))
    for path in (control, mutant, restored):
        path.mkdir(mode=0o700)
    with monkeypatch.context() as patch:
        check(control, patch)
    # Each mutant executes only synthetic seams in this test's system temp root.
    with monkeypatch.context() as patched:
        patched.setattr(m, "execute_prepared_read", namespace["execute_prepared_read"])
        # Direct globals (publisher/clock/source seams) use the same synthetic controls.
        namespace["_publish"] = lambda *args, **kwargs: m._publish(*args, **kwargs)
        with pytest.raises((AssertionError, ValueError, pytest.fail.Exception, namespace["ControllerEscaped"])):
            check(mutant, patched)
    assert m.execute_prepared_read is original
    with monkeypatch.context() as patch:
        check(restored, patch)


# TPR-CR30 regressions: synthetic-only is enforced, the lane boundary is decided by
# identity, and every escape path still leaves a durable receipt.


def test_unmarked_native_adapter_is_refused_before_any_claim(tmp_path):
    checked = plan(tmp_path); capsule = prior.capsule()
    generated = m._program_bytes(checked, capsule, m._public_sources())
    with pytest.raises(m.ControllerRefusal):
        m.execute_prepared_read(checked, capsule, tmp_path, program_raw=generated,
            native_read=lambda *_: pytest.fail("unmarked adapter must never run"),
            repository_guard=repository_guard, utc_now=lambda: prior.NOW, monotonic_clock=lambda: 10)
    assert not list(tmp_path.iterdir()) and m.NATIVE_ADAPTER_PERMITTED is False


@pytest.mark.parametrize("inside", ["artifacts/synthetic-never-created", "research/synthetic-never-created"])
def test_receipt_directory_inside_the_lane_is_refused_by_identity(tmp_path, inside):
    checked = plan(tmp_path); checked["receipt_directory"] = str(m.LANE / inside)
    checked["program_sha256"] = hashlib.sha256(m._program_bytes(checked, prior.capsule(), m._public_sources())).hexdigest()
    with pytest.raises(m.ControllerRefusal) as refused:
        m.validate_plan(checked, prior.capsule())
    assert not isinstance(refused.value, m.ControllerReceiptUnavailable)
    alias = Path(str(m.LANE).upper())
    if alias.exists() and os.stat(alias).st_ino == os.stat(m.LANE).st_ino:
        assert m._lane_identity(alias / "synthetic-never-created", m.LANE) is True


def test_base_exception_from_the_native_read_still_writes_a_receipt(tmp_path):
    def exiting(*_):
        raise SystemExit(3)
    with pytest.raises(SystemExit):
        invoke(tmp_path, seam=exiting)
    receipt = json.loads(next(tmp_path.glob("*.result.json")).read_bytes())
    assert receipt["status"] == "failed_or_uncertain" and receipt["scope_spent"] and receipt["native_read_invocations"] == 1
    assert not (tmp_path / "controller.lock").exists()


def test_cleanup_failure_after_cancellation_keeps_the_cancelled_status(tmp_path, monkeypatch):
    def interrupted(*_):
        raise KeyboardInterrupt(PRIVATE)
    original = m.os.unlink
    def unlink(name, **kwargs):
        if name == "controller.lock": raise OSError(PRIVATE)
        return original(name, **kwargs)
    monkeypatch.setattr(m.os, "unlink", unlink)
    with pytest.raises(m.ControllerCancelled) as cancelled:
        invoke(tmp_path, seam=interrupted)
    receipt = cancelled.value.receipt
    assert receipt["status"] == "cancelled" and receipt["failure_stage"] == "cleanup"
    assert PRIVATE not in json.dumps(receipt)


def test_receipt_publish_failure_after_cancellation_still_propagates_the_cancellation(tmp_path, monkeypatch):
    def interrupted(*_):
        raise KeyboardInterrupt(PRIVATE)
    original = m._publish
    def publish(fd, name, raw):
        if name.endswith(".result.json"): raise OSError(PRIVATE)
        return original(fd, name, raw)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(m.ControllerCancelled):
        invoke(tmp_path, seam=interrupted)
    assert not list(tmp_path.glob("*.result.json"))


def test_self_declared_synthetic_marker_cannot_enable_the_public_dispatch_entrypoint(tmp_path):
    checked, capsule = plan(tmp_path), prior.capsule()
    generated = m._program_bytes(checked, capsule, m._public_sources())
    calls = []
    def declared_adapter(program_raw, permit, context):
        calls.append("safe sentinel reached; no actual IO")
        return prior.invoke(contract=permit, context=context)
    declared_adapter.tpr_synthetic_adapter = True
    with pytest.raises(m.ControllerRefusal):
        m.execute_prepared_read(checked, capsule, tmp_path, program_raw=generated,
            native_read=declared_adapter, repository_guard=repository_guard,
            utc_now=lambda: prior.NOW, monotonic_clock=lambda: 10)
    assert calls == [] and not list(tmp_path.iterdir())


def test_lane_parent_alias_is_refused_by_directory_identity_not_only_realpath_text(monkeypatch):
    lane, alias = Path("/synthetic/lane-parent/lane"), Path("/synthetic/parent-alias")
    identities = {lane: SimpleNamespace(st_dev=10, st_ino=100),
        lane.parent: SimpleNamespace(st_dev=10, st_ino=99),
        alias: SimpleNamespace(st_dev=10, st_ino=99)}
    def fake_stat(path, *args, **kwargs):
        if Path(path) in identities:
            return identities[Path(path)]
        raise FileNotFoundError("synthetic missing path")
    with monkeypatch.context() as patch:
        patch.setattr(m.os, "stat", fake_stat)
        assert m._lane_identity(alias, lane) is True


def test_system_exit_during_owned_lock_cleanup_has_a_closed_failure_receipt(tmp_path, monkeypatch):
    original = m.os.stat
    def exiting_stat(path, *args, **kwargs):
        if path == "controller.lock":
            raise SystemExit(PRIVATE)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(m.os, "stat", exiting_stat)
    with pytest.raises(SystemExit):
        invoke(tmp_path)
    receipts = list(tmp_path.glob("*.result.json"))
    assert len(receipts) == 1
    result = json.loads(receipts[0].read_bytes())
    assert result["status"] == "failed_or_uncertain" and result["failure_stage"] == "cleanup"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert PRIVATE not in receipts[0].read_text()


def test_unavailable_cancelled_receipt_is_explicitly_not_reported_as_durable(tmp_path, monkeypatch):
    original = m._publish
    def publish(fd, name, raw):
        if name.endswith(".result.json"):
            raise OSError(PRIVATE)
        return original(fd, name, raw)
    def interrupted(*_):
        raise KeyboardInterrupt(PRIVATE)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(m.ControllerCancelled) as caught:
        invoke(tmp_path, seam=interrupted)
    assert caught.value.receipt_published is False
    assert not list(tmp_path.glob("*.result.json"))


def test_unavailable_lane_identity_is_a_closed_boundary(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise PermissionError("synthetic stat unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(m.os, "stat", unavailable)
        assert m._lane_identity(Path("/synthetic/unknown-alias"), Path("/synthetic/lane")) is True


@pytest.mark.parametrize("generic", [False, True])
def test_fatal_native_payload_is_replaced_with_body_free_stop_and_saved_counts(tmp_path, generic):
    class SyntheticStop(BaseException):
        pass
    def stopped(*_):
        raise (SyntheticStop(PRIVATE) if generic else SystemExit(PRIVATE))
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path, seam=stopped)
    assert not isinstance(caught.value, Exception)
    if not generic:
        assert isinstance(caught.value, SystemExit)
    assert PRIVATE not in str(caught.value)
    assert caught.value.receipt_published is True
    result = caught.value.receipt
    assert result["native_read_invocations"] == 1 and result["contains_calls"] is None
    assert result["read_calls"] is None
    assert_saved(tmp_path, result)


def test_fatal_receipt_publication_failure_is_body_free_and_not_durable(tmp_path, monkeypatch):
    original = m._publish
    def publish(fd, name, raw):
        if name.endswith(".result.json"):
            raise SystemExit(PRIVATE)
        return original(fd, name, raw)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(SystemExit) as caught:
        invoke(tmp_path)
    assert PRIVATE not in str(caught.value)
    assert caught.value.receipt_published is False
    assert caught.value.receipt["contains_calls"] == 2
    assert not list(tmp_path.glob("*.result.json"))


@pytest.mark.parametrize("cancel", [False, True])
def test_directory_close_fatal_escape_is_body_free_and_cannot_replace_cancellation(tmp_path, monkeypatch, cancel):
    original_open, original_close = m._open_directory, m.os.close
    state = {"directory_fd": None, "raised": False}
    def opened(path):
        fd = original_open(path)
        state["directory_fd"] = fd
        return fd
    def close(fd):
        original_close(fd)
        if fd == state["directory_fd"] and not state["raised"]:
            state["raised"] = True
            raise SystemExit(PRIVATE)
    def interrupted(*_):
        raise KeyboardInterrupt(PRIVATE)
    monkeypatch.setattr(m, "_open_directory", opened)
    monkeypatch.setattr(m.os, "close", close)
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path, seam=interrupted if cancel else None)
    assert state["raised"] and PRIVATE not in str(caught.value)
    assert isinstance(caught.value, m.ControllerCancelled if cancel else SystemExit)
    assert caught.value.receipt_published is True
    assert_saved(tmp_path, caught.value.receipt)


@pytest.mark.parametrize("generic", [False, True])
def test_ordinary_directory_close_error_cannot_demote_a_fatal_native_stop(tmp_path, monkeypatch, generic):
    class SyntheticStop(BaseException):
        pass
    original_open, original_close = m._open_directory, m.os.close
    state = {"directory_fd": None, "raised": False}
    def opened(path):
        fd = original_open(path)
        state["directory_fd"] = fd
        return fd
    def close(fd):
        original_close(fd)
        if fd == state["directory_fd"] and not state["raised"]:
            state["raised"] = True
            raise OSError(PRIVATE)
    def stopped(*_):
        raise SyntheticStop(PRIVATE) if generic else SystemExit(PRIVATE)
    monkeypatch.setattr(m, "_open_directory", opened)
    monkeypatch.setattr(m.os, "close", close)
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path, seam=stopped)
    assert state["raised"] and not isinstance(caught.value, Exception)
    if not generic:
        assert isinstance(caught.value, SystemExit)
    assert PRIVATE not in str(caught.value) and caught.value.receipt_published is True
    assert_saved(tmp_path, caught.value.receipt)


@pytest.mark.parametrize("native_cancel,publish_error,close_error", [
    (True, SystemExit, False), (False, KeyboardInterrupt, True), (False, SystemExit, True)])
def test_publication_stop_state_survives_fatal_publish_and_ordinary_final_close(
        tmp_path, monkeypatch, native_cancel, publish_error, close_error):
    original_open, original_close, original_publish = m._open_directory, m.os.close, m._publish
    state = {"directory_fd": None, "close_error_raised": False, "publish_error_raised": False}
    def opened(path):
        fd = original_open(path)
        state["directory_fd"] = fd
        return fd
    def close(fd):
        original_close(fd)
        if close_error and fd == state["directory_fd"] and not state["close_error_raised"]:
            state["close_error_raised"] = True
            raise OSError(PRIVATE)
    def publish(fd, name, raw):
        if name.endswith(".result.json"):
            state["publish_error_raised"] = True
            raise publish_error(PRIVATE)
        return original_publish(fd, name, raw)
    def interrupted(*_):
        raise KeyboardInterrupt(PRIVATE)
    monkeypatch.setattr(m, "_open_directory", opened)
    monkeypatch.setattr(m.os, "close", close)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path, seam=interrupted if native_cancel else None)
    assert state["publish_error_raised"] and state["close_error_raised"] is close_error
    cancellation_expected = native_cancel or publish_error is KeyboardInterrupt
    assert isinstance(caught.value, m.ControllerCancelled if cancellation_expected else SystemExit)
    assert not isinstance(caught.value, Exception) and PRIVATE not in str(caught.value)
    assert caught.value.receipt_published is False
    receipt = caught.value.receipt
    assert receipt["status"] == ("cancelled" if cancellation_expected else "failed_or_uncertain")
    assert receipt["native_read_invocations"] == 1
    assert receipt["contains_calls"] == (None if native_cancel else 2)
    assert receipt["read_calls"] == (None if native_cancel else 2)
    assert not list(tmp_path.glob("*.result.json"))


@pytest.mark.parametrize("boundary", ["lock_cleanup", "publication"])
@pytest.mark.parametrize("first_system_exit", [False, True])
def test_first_fatal_stop_is_retained_over_a_later_fatal_stop(tmp_path, monkeypatch, boundary, first_system_exit):
    class SyntheticFatal(BaseException):
        pass
    first = SystemExit if first_system_exit else SyntheticFatal
    second = SyntheticFatal if first_system_exit else SystemExit
    original_stat, original_publish = m.os.stat, m._publish
    def stopped(*_):
        raise first(PRIVATE)
    def stat(path, *args, **kwargs):
        if boundary == "lock_cleanup" and path == "controller.lock":
            raise second(PRIVATE)
        return original_stat(path, *args, **kwargs)
    def publish(fd, name, raw):
        if boundary == "publication" and name.endswith(".result.json"):
            raise second(PRIVATE)
        return original_publish(fd, name, raw)
    monkeypatch.setattr(m.os, "stat", stat)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path, seam=stopped)
    assert not isinstance(caught.value, Exception)
    assert isinstance(caught.value, SystemExit) is first_system_exit
    assert PRIVATE not in str(caught.value)
    assert caught.value.receipt_published is (boundary == "lock_cleanup")
    assert caught.value.receipt["native_read_invocations"] == 1
    assert caught.value.receipt["contains_calls"] is None


@pytest.mark.parametrize("mutation", ["marker_gate", "identity_unavailable", "parent_alias",
    "cleanup_escape", "cancelled_durability", "fatal_payload"])
def test_counterreview_controller_mutants_are_killed_with_restored_controls(tmp_path, monkeypatch, mutation):
    raw = Path(m.__file__).read_text()
    target = "execute_prepared_read"
    if mutation == "marker_gate":
        before, after = 'if NATIVE_ADAPTER_PERMITTED is not True:', 'if False:'
        check = lambda path, patch: test_self_declared_synthetic_marker_cannot_enable_the_public_dispatch_entrypoint(path)
    elif mutation == "identity_unavailable":
        target = "_lane_identity"
        before = 'return True  # Unknown directory custody is not permission to proceed.'
        after = 'return False  # synthetic mutation: fail open'
        check = lambda path, patch: test_unavailable_lane_identity_is_a_closed_boundary(patch)
    elif mutation == "parent_alias":
        target = "_lane_identity"
        before, after = 'for ancestor in lane.parents:', 'for ancestor in ():'
        check = lambda path, patch: test_lane_parent_alias_is_refused_by_directory_identity_not_only_realpath_text(patch)
    elif mutation == "cleanup_escape":
        before = '                except BaseException as error:\n                    if escaped is None:'
        after = '                except RuntimeError as error:\n                    if escaped is None:'
        check = lambda path, patch: test_system_exit_during_owned_lock_cleanup_has_a_closed_failure_receipt(path, patch)
    elif mutation == "cancelled_durability":
        before = 'raise ControllerCancelled(final, receipt_published=False) from None'
        after = 'raise ControllerCancelled(final, receipt_published=True) from None'
        check = lambda path, patch: test_unavailable_cancelled_receipt_is_explicitly_not_reported_as_durable(path, patch)
    else:
        before = 'raise _body_free_escape(escaped, final, receipt_published=True) from None'
        after = 'raise escaped'
        check = lambda path, patch: test_fatal_native_payload_is_replaced_with_body_free_stop_and_saved_counts(path, False)
    assert raw.count(before) == (3 if mutation == "cancelled_durability" else 1)
    namespace = {"__name__": m.__name__, "__file__": m.__file__}
    exec(compile(raw.replace(before, after, 1), "<synthetic-counterreview-mutant>", "exec"), namespace)
    # Dynamic compilation creates another exception class identity. Keep the
    # regression's catch boundary identical; the mutated guard is unchanged.
    namespace["ControllerCancelled"] = m.ControllerCancelled
    original = getattr(m, target)
    control, mutant, restored = (tmp_path / name for name in ("control", "mutant", "restored"))
    for path in (control, mutant, restored):
        path.mkdir(mode=0o700)
    with monkeypatch.context() as patch:
        check(control, patch)
    with monkeypatch.context() as patch:
        patch.setattr(m, target, namespace[target])
        namespace["_publish"] = lambda *args, **kwargs: m._publish(*args, **kwargs)
        with pytest.raises((AssertionError, AttributeError, ValueError, pytest.fail.Exception, namespace["ControllerEscaped"])):
            check(mutant, patch)
    assert getattr(m, target) is original
    with monkeypatch.context() as patch:
        check(restored, patch)
    assert m.NATIVE_ADAPTER_PERMITTED is False


@pytest.mark.parametrize("earlier_stop,publish_error,expected_status,expected_stage", [
    ("lock", KeyboardInterrupt, "cancelled", "lock"),
    ("lock", SystemExit, "failed_or_uncertain", "lock"),
    (None, KeyboardInterrupt, "cancelled", "post_read"),
])
def test_publication_stop_keeps_the_stage_the_receipt_had_actually_reached(
        tmp_path, monkeypatch, earlier_stop, publish_error, expected_status, expected_stage):
    """TPR-CR31-001: an unpublished accounting candidate must not relabel an
    earlier lock/claim/cleanup stop as post_read; only a completed read is."""
    original_fsync, original_publish = m.os.fsync, m._publish
    state = {"fsync_failures": 0}
    def fsync(fd):
        if earlier_stop == "lock" and state["fsync_failures"] == 0:
            state["fsync_failures"] += 1
            raise OSError(PRIVATE)
        return original_fsync(fd)
    def publish(fd, name, raw):
        if name.endswith(".result.json"):
            raise publish_error(PRIVATE)
        return original_publish(fd, name, raw)
    monkeypatch.setattr(m.os, "fsync", fsync)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(BaseException) as caught:
        invoke(tmp_path)
    assert not isinstance(caught.value, Exception) and PRIVATE not in str(caught.value)
    assert isinstance(caught.value, m.ControllerCancelled if expected_status == "cancelled" else SystemExit)
    assert caught.value.receipt_published is False
    receipt = caught.value.receipt
    assert receipt["status"] == expected_status and receipt["failure_stage"] == expected_stage
    assert receipt["lock_acquired"] is True
    assert receipt["claim_attempted"] is (earlier_stop is None)
    assert receipt["native_read_invocations"] == (0 if earlier_stop else 1)
    assert receipt["lock_cleanup_complete"] is True
    assert not list(tmp_path.glob("*.result.json"))


def test_ordinary_final_close_error_after_failed_publication_reports_the_receipt_unavailable(tmp_path, monkeypatch):
    """TPR-CR31-002: when the receipt was never published, an ordinary error on the
    final directory close must still say receipt-unavailable, not generic cleanup."""
    original_open, original_close, original_publish = m._open_directory, m.os.close, m._publish
    state = {"directory_fd": None, "raised": False}
    def opened(path):
        fd = original_open(path)
        state["directory_fd"] = fd
        return fd
    def close(fd):
        original_close(fd)
        if fd == state["directory_fd"] and not state["raised"]:
            state["raised"] = True
            raise OSError(PRIVATE)
    def publish(fd, name, raw):
        if name.endswith(".result.json"):
            raise OSError(PRIVATE)
        return original_publish(fd, name, raw)
    monkeypatch.setattr(m, "_open_directory", opened)
    monkeypatch.setattr(m.os, "close", close)
    monkeypatch.setattr(m, "_publish", publish)
    with pytest.raises(m.ControllerReceiptUnavailable) as caught:
        invoke(tmp_path)
    assert state["raised"] and PRIVATE not in str(caught.value)
    assert not list(tmp_path.glob("*.result.json"))
