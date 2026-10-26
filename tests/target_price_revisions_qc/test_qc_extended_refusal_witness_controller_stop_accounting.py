"""Portable control-flow models, with no real filesystem/native custody claim.

Clone the real controller/helper definitions and replace public-source, program,
directory and OS collaborators with explicit synthetic seams. No source bytes
are normalized or executed as a program, and no private/operator path is read.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_controller_successor as m


PRIVATE = "SYNTHETIC-STOP-PAYLOAD-DO-NOT-RETAIN"
OPERATION = "TPR-EXT26-WITNESS-RUNTIME-SYNTHETIC-ONLY"
NOW = datetime(2026, 10, 24, 1, tzinfo=timezone.utc)
PROGRAM = b"synthetic control-flow program; never executed"


class SyntheticFatal(BaseException):
    def __bool__(self):
        raise AssertionError("stop priority must not inspect exception truthiness")


@pytest.fixture(autouse=True)
def deny_actual_effects(monkeypatch):
    """Retain the existing controller deny harness, plus socket/process denial."""
    import http.client
    import socket
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(ops.subprocess, "Popen", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(socket, "socket", deny)


def _clone(function, namespace):
    return FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)


def _runtime_result():
    result = {"schema": "tpr-ext26-witness-runtime-result-v1", "operation_id": OPERATION,
        "project_id": m.runtime.PROJECT, "job_id": m.runtime.JOB,
        "status": "completed_diagnostic_only", "contains_calls": 2, "read_calls": 0,
        "objects": [{"kind": kind, "present": False, "status": "absent_uninterpreted",
            "read_attempted": False, "gzip_bytes": None, "gzip_sha256": None,
            "plain_bytes": None, "plain_sha256": None} for kind in m.runtime.predecessor.KINDS],
        **dict.fromkeys(m.runtime._FALSE_KEYS, False), "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0}
    return m.runtime.validate_result(result)


def _controller(*, stage="complete", publication_error=OSError, close_error=None, native_error=None):
    """Model only control flow; validate real receipt/result contracts throughout."""
    sources = {name: b"synthetic public source" for name in m.SOURCE_PATHS}
    capsule = {"schema": "tpr-ext26-witness-runtime-context-v1", "operation_id": OPERATION,
        "tool_project_id": m.runtime.PROJECT, "job_id": m.runtime.JOB,
        "tool_context_sha256": "a" * 64, "project_identity_provenance": "genuine_mia_ephemeral_tool_metadata"}
    checked = {"operation_id": OPERATION, "git_head": "a" * 40,
        "receipt_directory": str(Path.cwd() / "synthetic-unused-directory"),
        "source_hashes": {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
        "program_sha256": hashlib.sha256(PROGRAM).hexdigest(), "capsule_sha256": "b" * 64,
        "permit": {"issued_utc": NOW.isoformat(), "expires_utc": (NOW + timedelta(seconds=60)).isoformat(),
            "max_elapsed_seconds": 60}}
    state = {"native_calls": 0, "publications": [], "saved": None, "close_calls": [], "fault_reached": False}
    info = SimpleNamespace(st_dev=1, st_ino=1)
    def fsync(fd):
        if stage == "lock" and fd == 101 and not state["fault_reached"]:
            state["fault_reached"] = True
            raise OSError(PRIVATE)
    def publish(_fd, name, raw):
        state["publications"].append(name)
        if stage in {"claim", "access"} and name.endswith("." + ("claim.spent.json" if stage == "claim" else "access.json")):
            state["fault_reached"] = True
            raise OSError(PRIVATE)
        if name.endswith(".result.json"):
            if publication_error is not None:
                raise publication_error(PRIVATE)
            state["saved"] = bytes(raw)
    def unlink(*_args, **_kwargs):
        if stage == "cleanup":
            state["fault_reached"] = True
            raise OSError(PRIVATE)
    def close(fd):
        state["close_calls"].append(fd)
        if fd == 100 and close_error is not None:
            raise close_error(PRIVATE)
    def native(*_args):
        state["native_calls"] += 1
        if native_error is not None:
            raise native_error(PRIVATE)
        return _runtime_result()
    fake_os = SimpleNamespace(open=lambda *_args, **_kwargs: 101, close=close, fsync=fsync,
        stat=lambda *_args, **_kwargs: info, fstat=lambda *_args: info, unlink=unlink,
        O_WRONLY=1, O_CREAT=2, O_EXCL=4, O_NOFOLLOW=8)
    runtime = SimpleNamespace(**vars(m.runtime))
    runtime.validate_permit = lambda value: m._canonical(value)
    namespace = {**m.execute_prepared_read.__globals__, "os": fake_os, "runtime": runtime,
        "NATIVE_ADAPTER_PERMITTED": True, "validate_plan": lambda *_args: deepcopy(checked),
        "_public_sources": lambda: dict(sources), "_program_bytes": lambda *_args: PROGRAM,
        "_open_directory": lambda *_args: 100, "_file_ok": lambda *_args: True, "_publish": publish}
    function = _clone(m.execute_prepared_read, namespace)
    def invoke():
        return function(checked, capsule, checked["receipt_directory"], program_raw=PROGRAM, native_read=native,
            repository_guard=lambda: {"physical_root": str(m.LANE), "git_toplevel": str(m.LANE),
                "branch": m.BRANCH, "git_head": checked["git_head"]},
            utc_now=lambda: NOW, monotonic_clock=lambda: 10)
    return invoke, state


def _assert_body_free(error, published):
    assert not isinstance(error, Exception) and PRIVATE not in str(error)
    assert error.receipt_published is published
    assert PRIVATE not in json.dumps(error.receipt)
    assert all(error.receipt[key] is False for key in m._FALSE_KEYS)
    assert m.NATIVE_ADAPTER_PERMITTED is False


@pytest.mark.parametrize("stage", ["lock", "claim", "access", "cleanup", "complete"])
@pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit, SyntheticFatal])
def test_unpublished_final_close_stop_updates_only_the_accounting_candidate(stage, stop):
    invoke, state = _controller(stage=stage, close_error=stop)
    with pytest.raises(BaseException) as caught:
        invoke()
    error = caught.value
    _assert_body_free(error, False)
    assert isinstance(error, m.ControllerCancelled if stop is KeyboardInterrupt else
        m.ControllerSystemExit if stop is SystemExit else m.ControllerEscaped)
    assert error.receipt["status"] == ("cancelled" if stop is KeyboardInterrupt else "failed_or_uncertain")
    assert error.receipt["failure_stage"] == ("post_read" if stage == "complete" else stage)
    assert state["fault_reached"] is (stage != "complete")
    assert state["native_calls"] == (1 if stage in {"cleanup", "complete"} else 0)
    assert state["saved"] is None and state["close_calls"][-1] == 100


@pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit, SyntheticFatal])
def test_published_final_close_receipt_stays_immutable(stop):
    invoke, state = _controller(publication_error=None, close_error=stop)
    with pytest.raises(BaseException) as caught:
        invoke()
    _assert_body_free(caught.value, True)
    assert caught.value.receipt == json.loads(state["saved"])
    assert caught.value.receipt["status"] == "completed_diagnostic_only"
    copy = caught.value.receipt
    copy["status"] = "cancelled"
    assert caught.value.receipt["status"] == "completed_diagnostic_only"
    assert state["native_calls"] == 1


@pytest.mark.parametrize("first,later", [(SystemExit, SyntheticFatal), (SyntheticFatal, SystemExit),
    (SystemExit, OSError), (SyntheticFatal, OSError), (SystemExit, KeyboardInterrupt),
    (SyntheticFatal, KeyboardInterrupt)])
def test_first_fatal_and_cancellation_priority_in_unpublished_final_close(first, later):
    invoke, state = _controller(native_error=first, close_error=later)
    with pytest.raises(BaseException) as caught:
        invoke()
    _assert_body_free(caught.value, False)
    assert isinstance(caught.value, m.ControllerCancelled if later is KeyboardInterrupt else
        m.ControllerSystemExit if first is SystemExit else m.ControllerEscaped)
    assert caught.value.receipt["status"] == ("cancelled" if later is KeyboardInterrupt else "failed_or_uncertain")
    assert caught.value.receipt["failure_stage"] == "native_read"
    assert state["native_calls"] == 1 and state["saved"] is None


@pytest.mark.parametrize("stage", ["lock", "claim", "access", "cleanup", "complete"])
@pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit, SyntheticFatal])
def test_publication_stop_keeps_the_reached_stage_over_an_ordinary_close_error(stage, stop):
    invoke, state = _controller(stage=stage, publication_error=stop, close_error=OSError)
    with pytest.raises(BaseException) as caught:
        invoke()
    _assert_body_free(caught.value, False)
    assert caught.value.receipt["status"] == ("cancelled" if stop is KeyboardInterrupt else "failed_or_uncertain")
    assert caught.value.receipt["failure_stage"] == ("post_read" if stage == "complete" else stage)
    assert state["saved"] is None


def test_ordinary_final_close_after_unpublished_result_reports_unavailable():
    invoke, state = _controller(close_error=OSError)
    with pytest.raises(m.ControllerReceiptUnavailable, match="receipt unavailable"):
        invoke()
    assert state["native_calls"] == 1 and state["saved"] is None
    assert state["close_calls"] == [101, 100]


def _publisher(*, first_at=None, first=None, cleanup_at=None, cleanup=None, existing=False, replaced_temporary=False):
    """Run the real publisher against a finite in-memory descriptor model."""
    state = {"events": [], "buffer": b"", "temporary": None, "published": b"original" if existing else None,
        "cleanup_started": False, "first_reached": False, "cleanup_reached": False}
    info = SimpleNamespace(st_dev=1, st_ino=2, st_mode=0o100600, st_nlink=1, st_uid=1)
    def effect(name):
        state["events"].append(name)
        if name == first_at:
            state["first_reached"] = True
            raise first
        if name == cleanup_at:
            state["cleanup_reached"] = True
            raise cleanup
    def opened(name, flags, mode, *, dir_fd):
        assert flags == 15 and mode == 0o600 and dir_fd == 100
        assert name.startswith(".pending-")
        state["temporary"] = name
        effect("open")
        return 101
    def write(fd, raw):
        assert fd == 101
        effect("write")
        state["buffer"] += raw
        return len(raw)
    def fsync(fd):
        effect("file_fsync" if fd == 101 else "cleanup_fsync" if state["cleanup_started"] else "directory_fsync")
    def linked(source, destination, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        assert source == state["temporary"] and destination == "synthetic.result.json"
        assert src_dir_fd == dst_dir_fd == 100 and follow_symlinks is False
        effect("link")
        if state["published"] is not None:
            raise FileExistsError("synthetic immutable destination")
        state["published"] = state["buffer"]
    def named(name, *, dir_fd, follow_symlinks):
        assert name == state["temporary"] and dir_fd == 100 and follow_symlinks is False
        state["cleanup_started"] = True
        effect("cleanup_stat")
        return SimpleNamespace(st_dev=1, st_ino=999) if replaced_temporary else info
    def unlink(name, *, dir_fd):
        assert name == state["temporary"] and dir_fd == 100
        effect("cleanup_unlink")
        state["temporary"] = None
    def close(fd):
        assert fd == 101
        effect("cleanup_close")
    fake_os = SimpleNamespace(open=opened, write=write, fsync=fsync, link=linked, stat=named,
        fstat=lambda _fd: info, unlink=unlink, close=close, getuid=lambda: 1,
        O_WRONLY=1, O_CREAT=2, O_EXCL=4, O_NOFOLLOW=8)
    namespace = {**m._publish.__globals__, "os": fake_os}
    namespace["_file_ok"] = _clone(m._file_ok, namespace)
    publish = _clone(m._publish, namespace)
    return lambda: publish(100, "synthetic.result.json", b"synthetic immutable receipt"), state


@pytest.mark.parametrize("first_at", ["write", "link", "directory_fsync"])
@pytest.mark.parametrize("cleanup_at", ["cleanup_stat", "cleanup_unlink", "cleanup_fsync", "cleanup_close"])
@pytest.mark.parametrize("first_type,cleanup_type", [
    (KeyboardInterrupt, OSError), (KeyboardInterrupt, SystemExit),
    (SystemExit, OSError), (SyntheticFatal, OSError),
    (SystemExit, SyntheticFatal), (SyntheticFatal, SystemExit),
    (SystemExit, KeyboardInterrupt), (SyntheticFatal, KeyboardInterrupt),
    (OSError, KeyboardInterrupt), (OSError, SystemExit), (OSError, SyntheticFatal)])
def test_publisher_cleanup_preserves_cancellation_else_the_first_fatal(
        first_at, cleanup_at, first_type, cleanup_type):
    first, cleanup = first_type(PRIVATE), cleanup_type(PRIVATE)
    invoke, state = _publisher(first_at=first_at, first=first, cleanup_at=cleanup_at, cleanup=cleanup)
    with pytest.raises(BaseException) as caught:
        invoke()
    expected = first if first_type is KeyboardInterrupt or cleanup_type is not KeyboardInterrupt and first_type is not OSError else cleanup
    assert caught.value is expected
    assert state["first_reached"] and state["cleanup_reached"]
    assert state["events"].count("cleanup_close") == 1
    assert state["events"].count("link") <= 1
    assert state["events"].count("write") <= 1


def test_publisher_success_removes_only_its_temporary_and_never_replaces_evidence():
    invoke, state = _publisher()
    assert invoke() is None
    assert state["published"] == b"synthetic immutable receipt" and state["temporary"] is None
    assert state["events"] == ["open", "write", "file_fsync", "link", "directory_fsync",
        "cleanup_stat", "cleanup_unlink", "cleanup_fsync", "cleanup_close"]
    invoke, state = _publisher(existing=True)
    with pytest.raises(FileExistsError):
        invoke()
    assert state["published"] == b"original" and state["temporary"] is None
    assert state["events"].count("link") == state["events"].count("cleanup_close") == 1


def test_publisher_preserves_a_replaced_temporary_inode_and_closes_once():
    invoke, state = _publisher(replaced_temporary=True)
    assert invoke() is None
    assert state["temporary"] is not None and state["published"] == b"synthetic immutable receipt"
    assert "cleanup_unlink" not in state["events"] and "cleanup_fsync" not in state["events"]
    assert state["events"].count("cleanup_close") == 1


def test_actual_effect_sentinels_are_installed_before_control_flow_models():
    import http.client
    import socket
    from research.target_price_revisions_qc import extended_operations as ops
    for effect in (ops.read_private, ops.credential, ops.Operations, ops.subprocess.run,
            ops.subprocess.Popen, http.client.HTTPSConnection, socket.socket):
        with pytest.raises(AssertionError, match="actual private/provider/credential/operator/cloud forbidden"):
            effect("synthetic sentinel")


@pytest.mark.parametrize("mutation", ["unpublished_accounting", "published_immutability", "stage",
    "publisher_priority", "publisher_close", "publisher_failure"])
def test_stop_accounting_mutants_are_killed_with_finally_restored_controls(monkeypatch, mutation):
    target = "execute_prepared_read"
    if mutation in {"unpublished_accounting", "published_immutability"}:
        before = "if not publication_confirmed:\n                    final = validate_receipt("
        after = ("if False:" if mutation == "unpublished_accounting" else "if True:") + "\n                    final = validate_receipt("
        check = (lambda: test_unpublished_final_close_stop_updates_only_the_accounting_candidate("complete", KeyboardInterrupt)) if mutation == "unpublished_accounting" else (lambda: test_published_final_close_receipt_stays_immutable(KeyboardInterrupt))
    elif mutation == "stage":
        target = "_stop_stage"
        before = 'return "post_read" if receipt["failure_stage"] == "complete" else receipt["failure_stage"]'
        after = 'return "post_read"'
        check = lambda: test_publication_stop_keeps_the_reached_stage_over_an_ordinary_close_error("lock", KeyboardInterrupt)
    else:
        target = "_publish"
        if mutation == "publisher_priority":
            before = ("if (failure is None or not isinstance(failure, KeyboardInterrupt)\n"
                "                and (isinstance(error, KeyboardInterrupt)\n"
                "                    or isinstance(failure, Exception) and not isinstance(error, Exception))):")
            after = "if True:"
        elif mutation == "publisher_close":
            before, after = "except BaseException as error:\n            retain(error)", "except BaseException:\n            raise"
        else:
            before, after = "if failure is not None:\n        raise failure", "if False:\n        raise failure"
        check = lambda: test_publisher_cleanup_preserves_cancellation_else_the_first_fatal(
            "write", "cleanup_close", KeyboardInterrupt, OSError)
    original = getattr(m, target)
    source = inspect.getsource(original)
    assert source.count(before) == 1
    namespace = dict(original.__globals__)
    exec(compile(source.replace(before, after, 1), "<synthetic-stop-accounting-mutant>", "exec"), namespace)
    check()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(m, target, namespace[target])
            with pytest.raises((AssertionError, OSError, pytest.fail.Exception)):
                check()
    finally:
        assert getattr(m, target) is original
    check()
    assert m.NATIVE_ADAPTER_PERMITTED is False
