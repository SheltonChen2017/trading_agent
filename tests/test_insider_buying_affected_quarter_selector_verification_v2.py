"""Invented-only successor verification; no real archive, account or receipt I/O."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from research import insider_buying_affected_quarter_selector_verification_v2 as module


def _load_fixture_module():
    name = "selector_verification_v2_invented_front_fixtures"
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name("test_insider_buying_affected_quarter_selector_runner.py")
    )
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


fixtures = _load_fixture_module()


@pytest.fixture
def supplied(tmp_path):
    return fixtures.supplied.__wrapped__(tmp_path)


def _registered_result(supplied, monkeypatch):
    context, body, encoded = fixtures._result(supplied, monkeypatch)
    context["operation_registration"] = module._registration()
    context["operation_registration_sha256"] = module.REGISTRATION_SHA256
    body["schema"] = module.SCHEMA + "/worker-result"
    body["audit_id"] = module.AUDIT_ID
    body["operation_registration_sha256"] = module.REGISTRATION_SHA256
    expected_execution = copy.deepcopy(body["source_execution"])
    monkeypatch.setattr(module, "_source_context", lambda *_: copy.deepcopy(expected_execution))
    return context, body, encoded


def _invented_predecessor(tmp_path, monkeypatch):
    root = tmp_path / "invented-predecessor"
    root.mkdir(mode=0o700)
    pins = {}
    sizes = {}
    for name in sorted(module._FILES):
        raw = module._raw({"fixture_only": True, "old_failed_leaf": name})
        target = root / name
        target.write_bytes(raw)
        target.chmod(0o600)
        pins[name] = module._sha(raw)
        sizes[name] = len(raw)
    held = module.previous._HeldPublication(root, pins, fixture_only=True)
    monkeypatch.setattr(module, "PREDECESSOR_PINS", pins)
    monkeypatch.setattr(module, "PREDECESSOR_BYTES", sizes)
    return root, held


def test_fixed_registration_is_immutable_fresh_and_not_a_new_authority():
    assert module.AUDIT_ID == "ib-affected-quarter-selector-ctime-verified-v2-20261021-once"
    assert module.OUTPUT_PARTS == (
        "artifacts", "insider_buying", "affected_quarter_selector_verification_v2"
    )
    assert module.PREDECESSOR_AUDIT_ID == "ib-affected-quarter-selector-all6-retained-v1-20261014-once"
    registration = module._registration()
    assert module._raw(registration) == module.REGISTRATION_RAW
    assert module._sha(module.REGISTRATION_RAW) == module.REGISTRATION_SHA256
    assert module.AUDIT_ID.encode() in module.REGISTRATION_RAW
    assert module.PREDECESSOR_AUDIT_ID.encode() in module.REGISTRATION_RAW
    assert b"parent_final_output_check" in module.REGISTRATION_RAW
    assert all(not value for value in module._authority().values())
    registration.clear()
    assert module._raw(module._registration()) == module.REGISTRATION_RAW


def test_predecessor_is_bound_to_the_exact_failed_three_leaf_images():
    assert module.PREDECESSOR_PARTS == (
        "artifacts", "insider_buying", "affected_quarter_selector_v1"
    )
    assert module.PREDECESSOR_PINS == {
        "reservation.json": "08a11e4dea01408970ad5ab6df12a31b411ae12472fdf9a712195b01515fe8d8",
        "selection.json": "d1dd4e093d5505fac6373562bb24198c7ad6fc61ef7745912a40bff84528aaef",
        "complete.json": "ca0fb475cbb102505cc07bf33e7a67568919ecfc4687bee7b9475162c3045e57",
    }
    assert module.PREDECESSOR_BYTES == {
        "reservation.json": 27812, "selection.json": 91237, "complete.json": 39794,
    }


@pytest.mark.parametrize("value", [
    module.PREDECESSOR_AUDIT_ID,
    "ib-affected-quarter-selector-ctime-verified-v2-20261021-twice",
    "ib-affected-quarter-selector-ctime-verified-v2-20261021-once/child",
    "ib-affected-quarter-selector-invented", None, True,
])
def test_only_the_single_registered_identifier_can_reach_any_reader_or_writer(value, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unregistered operation reached source, input or output callback")
    for name in ("_fixed_source_identity", "_HeldIntake", "_HeldPredecessorPublication", "_output_directory"):
        monkeypatch.setattr(module, name, forbidden)
    with pytest.raises(ValueError):
        module.run_observed_verification(value, expected_head="a" * 40)


def test_direct_output_constructor_refuses_unregistered_id_before_directory_callback(monkeypatch):
    monkeypatch.setattr(module.original.capture.custody, "_Directory",
        lambda *_args, **_kwargs: pytest.fail("directory callback reached"))
    with pytest.raises(ValueError):
        module._output_directory(module.PREDECESSOR_AUDIT_ID)


@pytest.mark.parametrize("kind", [
    "missing_registration", "wrong_registration_pin", "positive_authority", "one_derivation",
    "disabled_network", "disabled_fork", "disabled_allwrite", "wrong_audit", "extra_field",
])
def test_registered_worker_result_cannot_substitute_source_scope_or_denials(supplied, monkeypatch, kind):
    context, body, _ = _registered_result(supplied, monkeypatch)
    if kind == "missing_registration":
        del body["operation_registration_sha256"]
    elif kind == "wrong_registration_pin":
        body["operation_registration_sha256"] = "f" * 64
    elif kind == "positive_authority":
        body["authority"]["backtesting_ready"] = True
    elif kind == "one_derivation":
        body["full_input_rederivations"] = 1
    elif kind.startswith("disabled_"):
        key = {"disabled_network": "effective_process_tree_network_denial",
               "disabled_fork": "effective_process_fork_denial",
               "disabled_allwrite": "effective_all_write_denial"}[kind]
        body[key] = False
    elif kind == "wrong_audit":
        body["audit_id"] = module.PREDECESSOR_AUDIT_ID
    else:
        body["private_financial_data"] = {"count": 42}
    with pytest.raises(ValueError):
        module._validate_worker_result(body, audit_id=module.AUDIT_ID, context=context)


def test_registered_worker_result_has_a_genuine_twice_derived_control(supplied, monkeypatch):
    context, body, encoded = _registered_result(supplied, monkeypatch)
    assert module._validate_worker_result(body, audit_id=module.AUDIT_ID, context=context) == encoded
    assert body["full_input_rederivations"] == 2
    assert json.loads(encoded)["affected_periods"] == ["2006Q1", "2020Q4"]


@pytest.mark.parametrize("kind", ["registration_body", "registration_pin"])
def test_parent_context_registration_cannot_be_substituted_while_worker_pin_stays_valid(
        supplied, monkeypatch, kind):
    context, body, _ = _registered_result(supplied, monkeypatch)
    if kind == "registration_body":
        context["operation_registration"]["backtesting_readiness_granted"] = True
    elif kind == "registration_pin":
        context["operation_registration_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        module._validate_worker_result(body, audit_id=module.AUDIT_ID, context=context)


def test_captured_worker_rejects_additional_context_before_any_current_source_or_input_read(
        supplied, monkeypatch):
    context, _, _ = _registered_result(supplied, monkeypatch)
    context["hidden_scope"] = "forbidden"
    events = []
    monkeypatch.setattr(module, "_prove_allwrite_denial", lambda *_: events.append("native_control"))
    monkeypatch.setattr(module.sys, "addaudithook", lambda *_: events.append("hook_control"))
    monkeypatch.setattr(module.original, "_current_bytes", lambda *_: pytest.fail("current reader reached"))
    monkeypatch.setattr(module, "_HeldIntake", lambda: pytest.fail("input reader reached"))
    with pytest.raises(ValueError):
        module._worker(module.AUDIT_ID, expected_head="a" * 40, context=context,
                       executed_sources=[], bootstrap_source={})
    assert events == ["native_control", "hook_control"]


def _held_publication(tmp_path):
    root = tmp_path / "invented-v2-output"
    root.mkdir(mode=0o700)
    pins = {}
    for name in sorted(module._FILES):
        raw = module._raw({"fixture_only": True, "v2_leaf": name})
        target = root / name
        target.write_bytes(raw)
        target.chmod(0o600)
        pins[name] = module._sha(raw)
    return root, module._HeldPublication(root, pins, fixture_only=True)


def test_only_the_fresh_publication_hold_tolerates_ctime_only_drift(tmp_path, supplied):
    root, held = _held_publication(tmp_path)
    intake = module._HeldIntake(**supplied[2])
    try:
        target = root / "complete.json"
        before = target.stat()
        target.chmod(0o600)
        after = target.stat()
        assert before.st_ctime_ns != after.st_ctime_ns
        assert before.st_mtime_ns == after.st_mtime_ns
        held.recheck()
        intake_target = supplied[2]["root"] / "2006q1_form345.zip"
        intake_target.chmod(0o600)
        with pytest.raises(ValueError):
            intake.recheck()
    finally:
        held.close()
        intake.close()


@pytest.mark.parametrize("kind", ["same_size_content_restored_mtime", "mode", "replace", "link", "extra_leaf"])
def test_settled_ctime_output_hold_keeps_content_and_all_other_custody_guards(tmp_path, kind):
    root, held = _held_publication(tmp_path)
    try:
        target = root / "selection.json"
        if kind == "same_size_content_restored_mtime":
            info = target.stat()
            raw = target.read_bytes()
            changed = raw.replace(b"true", b"fals", 1)
            assert changed != raw and len(changed) == len(raw)
            target.write_bytes(changed)
            os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))
        elif kind == "mode":
            target.chmod(0o640)
        elif kind == "replace":
            raw = target.read_bytes()
            target.rename(tmp_path / "preserved-old-selection")
            target.write_bytes(raw)
            target.chmod(0o600)
        elif kind == "link":
            os.link(target, tmp_path / "invented-linked-selection")
        else:
            (root / "unexpected.json").write_bytes(b"{}")
        with pytest.raises(ValueError):
            held.recheck()
    finally:
        held.close()


@pytest.mark.parametrize("root", [
    module.original.capture.bootstrap.custody.LANE_ROOT,
    module.original.capture.bootstrap.custody.LANE_ROOT.parent,
    Path("/"),
])
def test_fixture_publication_fence_refuses_before_any_real_reader(root, monkeypatch):
    monkeypatch.setattr(module.held_io, "_HeldCapture", lambda *_args, **_kwargs: pytest.fail("reader reached"))
    with pytest.raises(ValueError):
        module._HeldPublication(root, dict.fromkeys(module._FILES, "a" * 64), fixture_only=True)


def test_private_cli_image_refuses_before_real_inputs_or_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(module, "__file__", str(tmp_path / "inactive-front.py"))
    for name in ("_HeldIntake", "_HeldPredecessorPublication", "_output_directory"):
        monkeypatch.setattr(module, name, lambda *_args, **_kwargs: pytest.fail("real callback reached"))
    assert module.main(["--audit-id", module.AUDIT_ID, "--expected-head", "a" * 40]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["disposition"] == module._DISPOSITION
    assert result["failure_phase"] == "parent_preflight"
    assert set(result) == {"disposition", "failure_phase", "failure_class", "os_errno"}


def test_worker_proves_native_denial_before_any_actual_reader_or_python_hook(monkeypatch):
    monkeypatch.setattr(module, "__file__", str(module.original.capture.bootstrap.custody.LANE_ROOT / module.SELF_PATH))
    events = []
    def refuse(_):
        events.append("native")
        raise ValueError("invented missing native denial")
    monkeypatch.setattr(module, "_prove_allwrite_denial", refuse)
    monkeypatch.setattr(module, "_HeldIntake", lambda: pytest.fail("actual reader reached"))
    monkeypatch.setattr(module.sys, "addaudithook", lambda *_: pytest.fail("hook preceded native proof"))
    with pytest.raises(ValueError) as caught:
        module._worker(module.AUDIT_ID, expected_head="a" * 40,
                       context={}, executed_sources=[], bootstrap_source={})
    assert events == ["native"]
    assert module._failure_diagnostic(caught.value)["failure_phase"] == "worker_native_denial"


def _temporary_registered_parent(tmp_path, supplied, monkeypatch, *, fault=None):
    """Real intake/output custody with invented source identity and native transport.

    The input bytes genuinely traverse the qualified fixture factory twice.
    Only Git/source identity and subprocess transport are replaced; no production
    input or receipt path can be opened after the private lane-root redirect.
    """
    context, body, encoded = _registered_result(supplied, monkeypatch)
    root = (tmp_path / "invented-lane").resolve()
    root.mkdir(mode=0o700)
    monkeypatch.setattr(module.original.capture.bootstrap.custody, "LANE_ROOT", root)
    predecessor_path = root.joinpath(*module.PREDECESSOR_PARTS, module.PREDECESSOR_AUDIT_ID)
    predecessor_path.mkdir(parents=True, mode=0o700)
    predecessor_images = {
        name: module._raw({"fixture_only": True, "preserved_failed_predecessor": name})
        for name in module._FILES
    }
    for name, raw in predecessor_images.items():
        target = predecessor_path / name
        target.write_bytes(raw)
        target.chmod(0o600)
    monkeypatch.setattr(module, "PREDECESSOR_PINS", {
        name: module._sha(raw) for name, raw in predecessor_images.items()
    })
    monkeypatch.setattr(module, "PREDECESSOR_BYTES", {
        name: len(raw) for name, raw in predecessor_images.items()
    })
    intake_class = module._HeldIntake
    predecessor_class = module._HeldPredecessorPublication
    publication_class = module._HeldPublication
    held = intake_class(**supplied[2])
    held.context = copy.deepcopy(context["intake_context"])
    predecessor = predecessor_class()
    streams = [stream for _, stream, _, _ in held.tree.handles]
    streams += [stream for _, stream, _, _ in predecessor.held.tree.handles]
    calls = {"identity": 0, "inputs": 0, "predecessor": 0, "launch": 0}
    initial_input_recheck = held.recheck
    initial_predecessor_recheck = predecessor.recheck
    def recheck_inputs():
        calls["inputs"] += 1
        if fault == "inputs" and calls["inputs"] == 3:
            raise ValueError("PRIVATE INPUT SENTINEL")
        initial_input_recheck()
    def recheck_predecessor():
        calls["predecessor"] += 1
        if fault == "predecessor" and calls["predecessor"] == 3:
            raise ValueError("PRIVATE PREDECESSOR SENTINEL")
        initial_predecessor_recheck()
    held.recheck = recheck_inputs
    predecessor.recheck = recheck_predecessor
    def identity(_):
        calls["identity"] += 1
        if fault == "source" and calls["identity"] == 4:
            return {"changed": True}, {}
        return context["identity"], context["frozen_sources"]
    def publication(*args, **kwargs):
        if fault == "hold":
            raise ValueError("PRIVATE OUTPUT HOLD SENTINEL")
        value = publication_class(*args, **kwargs)
        streams.extend(stream for _, stream, _, _ in value.tree.handles)
        if fault == "output":
            def refuse():
                raise ValueError("PRIVATE OUTPUT SENTINEL")
            value.recheck = refuse
        return value
    def launch(command, **kwargs):
        calls["launch"] += 1
        policy = command[command.index("-p") + 1]
        assert "(deny network*)" in policy and "(deny process-fork)" in policy
        assert "(deny file-write*)" in policy and "(allow file-write*" not in policy
        envelope = json.loads(kwargs["input"])
        assert envelope["audit_id"] == module.AUDIT_ID
        assert envelope["context"] == context
        assert envelope["sources"] == []
        assert command[-1] == module.SOURCE_ONLY_BOOTSTRAP
        return SimpleNamespace(returncode=0, stderr=b"", stdout=module._raw(body) + b"\n")
    monkeypatch.setattr(module, "_fixed_source_identity", identity)
    monkeypatch.setattr(module, "_HeldIntake", lambda: held)
    monkeypatch.setattr(module, "_HeldPredecessorPublication", lambda: predecessor)
    monkeypatch.setattr(module, "_HeldPublication", publication)
    monkeypatch.setattr(module.subprocess, "run", launch)
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 0)
    return SimpleNamespace(
        context=context, body=body, encoded=encoded, root=root,
        output_path=root.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID),
        predecessor_path=predecessor_path, predecessor_images=predecessor_images,
        calls=calls, streams=streams, intake_class=intake_class,
        predecessor_class=predecessor_class, supplied=supplied,
    )


def _fresh_readback_factories(state, monkeypatch, *, cleanup_fault=False):
    """Every post-completion verifier gets new real descriptors, not closed holds."""
    verifier_streams = []
    def intake():
        held = state.intake_class(**state.supplied[2])
        held.context = copy.deepcopy(state.context["intake_context"])
        verifier_streams.extend(stream for _, stream, _, _ in held.tree.handles)
        if cleanup_fault:
            original_close = held.close
            def refuse_after_closing():
                original_close()
                raise ValueError("PRIVATE CLEANUP SENTINEL")
            held.close = refuse_after_closing
        return held
    predecessor_class = state.predecessor_class
    def predecessor():
        held = predecessor_class()
        verifier_streams.extend(stream for _, stream, _, _ in held.held.tree.handles)
        return held
    capture_class = module.held_io._HeldCapture
    captures = []
    def capture(path, **kwargs):
        value = capture_class(path, **kwargs)
        if path == state.output_path:
            captures.append(value)
        return value
    monkeypatch.setattr(module, "_HeldIntake", intake)
    monkeypatch.setattr(module, "_HeldPredecessorPublication", predecessor)
    monkeypatch.setattr(module.held_io, "_HeldCapture", capture)
    def no_semantic_replay(*_args, **_kwargs):
        pytest.fail("read-only receipt verifier attempted semantic replay or worker launch")
    monkeypatch.setattr(module, "_derive_twice", no_semantic_replay)
    monkeypatch.setattr(module.pure, "select_affected_quarters", no_semantic_replay)
    monkeypatch.setattr(module.subprocess, "run", no_semantic_replay)
    return verifier_streams, captures


@pytest.mark.parametrize("fault, phase", [
    (None, None), ("hold", "parent_final_output_hold"),
    ("inputs", "parent_final_inputs"), ("source", "parent_final_sources"),
    ("output", "parent_final_output_check"), ("predecessor", "parent_predecessor_recheck"),
])
def test_full_real_temporary_parent_lifecycle_requires_every_final_check_before_cli_zero(
        tmp_path, supplied, monkeypatch, capsys, fault, phase):
    state = _temporary_registered_parent(tmp_path, supplied, monkeypatch, fault=fault)
    result = module.main(["--audit-id", module.AUDIT_ID, "--expected-head", "a" * 40])
    payload = json.loads(capsys.readouterr().out)
    assert result == (0 if fault is None else 2)
    if fault is None:
        assert payload["selection_sha256"] == module._sha(state.encoded)
        assert payload["predecessor_status"] == "FAILED_preserved_not_promoted"
        assert state.calls == {"identity": 4, "inputs": 3, "predecessor": 3, "launch": 1}
    else:
        assert payload["failure_phase"] == phase
        assert "PRIVATE" not in module._raw(payload).decode()
    assert set(os.listdir(state.output_path)) == module._FILES
    assert (state.output_path / "selection.json").read_bytes() == state.encoded
    assert all(stream.closed for stream in state.streams)
    assert {name: (state.predecessor_path / name).read_bytes() for name in module._FILES} == state.predecessor_images


def test_parent_cleanup_failure_does_not_mask_primary_late_refusal_or_skip_other_handles(
        tmp_path, supplied, monkeypatch, capsys):
    state = _temporary_registered_parent(tmp_path, supplied, monkeypatch, fault="output")
    publication_factory = module._HeldPublication
    def publication(*args, **kwargs):
        held = publication_factory(*args, **kwargs)
        original_close = held.close
        def failed_cleanup():
            original_close()
            raise OSError("PRIVATE SECONDARY CLEANUP SENTINEL")
        held.close = failed_cleanup
        return held
    monkeypatch.setattr(module, "_HeldPublication", publication)
    assert module.main(["--audit-id", module.AUDIT_ID, "--expected-head", "a" * 40]) == 2
    body = json.loads(capsys.readouterr().out)
    assert body["failure_phase"] == "parent_final_output_check"
    assert body["failure_class"] == "ValueError"
    assert "PRIVATE" not in module._raw(body).decode()
    assert all(stream.closed for stream in state.streams)


def _complete_temporary_parent(tmp_path, supplied, monkeypatch):
    state = _temporary_registered_parent(tmp_path, supplied, monkeypatch)
    state.result = module.run_observed_verification(module.AUDIT_ID, expected_head="a" * 40)
    assert all(stream.closed for stream in state.streams)
    return state


def _verify(state, **changes):
    arguments = {"expected_head": "a" * 40,
                 "expected_selection_sha256": state.result["selection_sha256"],
                 "expected_complete_sha256": state.result["complete_sha256"],
                 "observed_cli_success": True}
    arguments.update(changes)
    return module.verify_observed_completion(**arguments)


@pytest.mark.parametrize("kind", ["size_pin", "hash_pin", "extra_leaf", "changed_bytes", "renamed_leaf"])
def test_real_temporary_predecessor_constructor_requires_exact_failed_receipt_custody(
        tmp_path, supplied, monkeypatch, kind):
    state = _complete_temporary_parent(tmp_path, supplied, monkeypatch)
    monkeypatch.setattr(module, "_HeldPredecessorPublication", state.predecessor_class)
    if kind == "size_pin":
        monkeypatch.setattr(module, "PREDECESSOR_BYTES", {**module.PREDECESSOR_BYTES,
            "selection.json": module.PREDECESSOR_BYTES["selection.json"] + 1})
    elif kind == "hash_pin":
        monkeypatch.setattr(module, "PREDECESSOR_PINS", {**module.PREDECESSOR_PINS,
            "selection.json": "f" * 64})
    elif kind == "extra_leaf":
        (state.predecessor_path / "unexpected.json").write_bytes(b"{}")
    elif kind == "changed_bytes":
        target = state.predecessor_path / "selection.json"
        target.write_bytes(target.read_bytes() + b" ")
    else:
        target = state.predecessor_path / "selection.json"
        target.rename(target.with_name("not-selection.json"))
    with pytest.raises(ValueError):
        module._HeldPredecessorPublication()


def test_readonly_receipt_verification_is_not_semantic_replay_or_cli_authentication(tmp_path, supplied, monkeypatch):
    state = _complete_temporary_parent(tmp_path, supplied, monkeypatch)
    before = {name: (state.output_path / name).read_bytes() for name in module._FILES}
    streams, captures = _fresh_readback_factories(state, monkeypatch)
    result = _verify(state)
    assert result["metadata_only"] is True
    assert result["semantic_rederivations_performed_here"] == 0
    assert result["terminal_cli_status_authenticated_here"] is False
    assert result["external_cli_success_hint_supplied"] is True
    assert result["predecessor_status"] == "FAILED_preserved_not_promoted"
    assert result["operation_registration_sha256"] == module.REGISTRATION_SHA256
    assert result["selection_sha256"] == state.result["selection_sha256"]
    assert result["complete_sha256"] == state.result["complete_sha256"]
    assert all(not value for value in result["authority"].values())
    assert all(stream.closed for stream in streams)
    assert len(captures) == 1 and captures[0].handles == [] and captures[0].chain.fds == []
    assert before == {name: (state.output_path / name).read_bytes() for name in module._FILES}


def test_successful_readback_cleanup_fault_still_drains_all_output_handles(tmp_path, supplied, monkeypatch):
    state = _complete_temporary_parent(tmp_path, supplied, monkeypatch)
    streams, captures = _fresh_readback_factories(state, monkeypatch, cleanup_fault=True)
    with pytest.raises(ValueError) as caught:
        _verify(state)
    assert module._failure_diagnostic(caught.value)["failure_phase"] == "parent_cleanup"
    assert all(stream.closed for stream in streams)
    assert len(captures) == 1 and captures[0].handles == [] and captures[0].chain.fds == []


@pytest.mark.parametrize("hint", [False, None, 0, 1, "true"])
def test_receipt_verifier_refuses_missing_or_nonboolean_cli_hint_before_any_io(hint, monkeypatch):
    monkeypatch.setattr(module, "_fixed_source_identity", lambda *_: pytest.fail("reader reached"))
    with pytest.raises(ValueError):
        module.verify_observed_completion(expected_head="a" * 40,
            expected_selection_sha256="b" * 64, expected_complete_sha256="c" * 64,
            observed_cli_success=hint)


@pytest.mark.parametrize("kind", [
    "external_selection", "external_complete", "unknown_complete_field", "positive_authority",
    "registration_pin", "registration_scope", "worker_result_pin", "bootstrap_pin",
    "one_derivation", "denial_false", "naive_clock", "noncanonical_clock", "reservation_changed",
    "unknown_selection_field", "extra_output_leaf",
])
def test_hash_coherent_receipt_tampering_still_refuses_semantic_or_custody_substitution(
        tmp_path, supplied, monkeypatch, kind):
    state = _complete_temporary_parent(tmp_path, supplied, monkeypatch)
    arguments = {}
    if kind == "external_selection":
        arguments["expected_selection_sha256"] = "f" * 64
    elif kind == "external_complete":
        arguments["expected_complete_sha256"] = "f" * 64
    elif kind == "extra_output_leaf":
        (state.output_path / "extra.json").write_bytes(b"{}")
    elif kind == "reservation_changed":
        path = state.output_path / "reservation.json"
        body = json.loads(path.read_bytes())
        body["fixture_only"] = True
        path.write_bytes(module._raw(body))
    elif kind == "unknown_selection_field":
        path = state.output_path / "selection.json"
        body = json.loads(path.read_bytes())
        body["private_financial_data"] = {"count": 42}
        raw = module._raw(body)
        path.write_bytes(raw)
        arguments["expected_selection_sha256"] = module._sha(raw)
    else:
        path = state.output_path / "complete.json"
        body = json.loads(path.read_bytes())
        if kind == "unknown_complete_field": body["private_financial_data"] = {"count": 42}
        elif kind == "positive_authority": body["authority"]["backtesting_ready"] = True
        elif kind == "registration_pin": body["operation_registration_sha256"] = "f" * 64
        elif kind == "registration_scope": body["operation_registration"]["predecessor_promoted_or_rewritten"] = True
        elif kind == "worker_result_pin": body["worker_result_sha256"] = "f" * 64
        elif kind == "bootstrap_pin": body["source_only_bootstrap_sha256"] = "f" * 64
        elif kind == "one_derivation": body["full_input_rederivations"] = 1
        elif kind == "denial_false": body["effective_all_write_denial"] = False
        elif kind == "naive_clock": body["observed_at_utc"] = "2026-10-21T00:00:00"
        else: body["observed_at_utc"] = "2026-10-21T00:00:00Z"
        raw = module._raw(body)
        path.write_bytes(raw)
        arguments["expected_complete_sha256"] = module._sha(raw)
    streams, captures = _fresh_readback_factories(state, monkeypatch)
    with pytest.raises(ValueError):
        _verify(state, **arguments)
    assert all(stream.closed for stream in streams)
    assert len(captures) == 1 and captures[0].handles == [] and captures[0].chain.fds == []


# Claude review section 201: in-memory mutants that each of the following
# guards survived. Each test fails if its guard is removed.

def test_parent_recomputes_executed_sources_and_binds_the_reported_selection_hash(supplied, monkeypatch):
    # _registered_result stubs _source_context to echo the reported value, so
    # the comparison itself needs a recomputation that differs.
    context, body, _ = _registered_result(supplied, monkeypatch)
    recomputed = copy.deepcopy(body["source_execution"])
    recomputed["executed_source_inventory_sha256"] = "e" * 64
    monkeypatch.setattr(module, "_source_context", lambda *_: copy.deepcopy(recomputed))
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="worker_executed_source_context_differs"):
        module._validate_worker_result(body, audit_id=module.AUDIT_ID, context=context)
    context, body, _ = _registered_result(supplied, monkeypatch)
    body["selection_sha256"] = "e" * 64
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="worker_selection_bytes_binding_differs"):
        module._validate_worker_result(body, audit_id=module.AUDIT_ID, context=context)


def test_two_derivations_that_differ_refuse(monkeypatch):
    results = iter([SimpleNamespace(canonical_bytes=lambda: b"first"),
                    SimpleNamespace(canonical_bytes=lambda: b"second")])
    monkeypatch.setattr(module.pure, "select_affected_quarters", lambda **_: next(results))
    held = SimpleNamespace(source_arguments=dict, recheck=lambda: None)
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="independent_full_selector_rederivation_differs"):
        module._derive_twice(held)


def _worker_failure():
    return {"disposition": module._DISPOSITION, "failure_phase": "worker_execution",
            "failure_class": "ValueError", "os_errno": None}


def test_child_result_requires_empty_stderr_and_canonical_framing():
    canonical = module._raw(_worker_failure()) + b"\n"
    with pytest.raises(module.ReportedSelectorWorkerError):
        module._child_result(subprocess.CompletedProcess(["invented"], 2, canonical, b""), context={})
    for stdout, stderr, code in ((canonical, b"x", "selector_child_refused_outputs_preserved"),
            (json.dumps(_worker_failure(), indent=1).encode() + b"\n", b"", "strict_selector_child_framing_required")):
        with pytest.raises(module.AffectedQuarterSelectorRunnerError) as caught:
            module._child_result(subprocess.CompletedProcess(["invented"], 2, stdout, stderr), context={})
        assert type(caught.value) is module.AffectedQuarterSelectorRunnerError and str(caught.value) == code


def test_control_json_refuses_duplicate_keys():
    # The hook's own duplicate code is re-labelled by the outer ValueError
    # catch; the refusal itself is what this pins (IBSELECT-V2-OBS01).
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="malformed_control_json_refused"):
        module._opaque_json(b'{"counts":1,"counts":2}')
    assert module._opaque_json(b'{"counts":1}') == {"counts": "1"}


def test_inside_write_that_succeeds_is_not_accepted_as_denial(tmp_path, monkeypatch):
    monkeypatch.setattr(module.original, "_prove_worker_isolation", lambda *_: None)
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="effective_inside_write_denial_not_observed"):
        module._prove_allwrite_denial(tmp_path)


@pytest.mark.parametrize("kind", ["fixture_intake", "other_head"])
def test_worker_refuses_fixture_intake_or_another_head_before_identity_or_inputs(supplied, monkeypatch, kind):
    context, _, _ = _registered_result(supplied, monkeypatch)
    context = {key: context[key] for key in ("identity", "frozen_sources", "intake_context",
        "operation_registration", "operation_registration_sha256")}
    head = context["identity"]["head"]
    if kind == "fixture_intake":
        context["intake_context"] = {**context["intake_context"], "fixture_only": True}
    else:
        head = "f" * 40 if head != "f" * 40 else "e" * 40
    monkeypatch.setattr(module, "_prove_allwrite_denial", lambda *_: None)
    monkeypatch.setattr(module.sys, "addaudithook", lambda *_: None)
    monkeypatch.setattr(module.original.capture.bootstrap, "_required_identity", lambda *_: pytest.fail("identity reached"))
    monkeypatch.setattr(module, "_HeldIntake", lambda: pytest.fail("input reader reached"))
    with pytest.raises(module.AffectedQuarterSelectorRunnerError, match="strict_actual_worker_context_required"):
        module._worker(module.AUDIT_ID, expected_head=head, context=context,
                       executed_sources=[], bootstrap_source={})
