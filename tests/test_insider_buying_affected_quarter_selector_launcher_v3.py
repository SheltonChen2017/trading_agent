"""Invented-only trusted-parent controls; no retained archive or account access.

The one opt-in topology test is intentionally launched outside an inherited
native sandbox. Its trusted synthetic parent has Python process guards; its
single native worker proves network/fork/all-write denial before any input.
This is not a claim of native isolation for the trusted parent.
"""
from __future__ import annotations

import copy
import errno
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from research import insider_buying_affected_quarter_selector_launcher_v3 as module
from research import insider_buying_affected_quarter_selector_verification_v2 as front


HEAD = "1" * 40
SELECTION = "2" * 64
COMPLETE = "3" * 64
RESERVATION = "4" * 64
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


def _child(body=None, *, code=0, stderr=b"", stdout=None):
    if stdout is None:
        stdout = module._raw(body) + b"\n"
    return subprocess.CompletedProcess(["invented-control"], code, stdout, stderr)


def _success():
    return {"audit_id": module.SEMANTIC_ID, "fixture_only": False,
        "selection_sha256": SELECTION, "complete_sha256": COMPLETE,
        "counts": copy.deepcopy(front.pure.EXPECTED_ACTUAL_COUNTS),
        "authority": front._authority(), "operation_registration_sha256": front.REGISTRATION_SHA256,
        "predecessor_status": "FAILED_preserved_not_promoted"}


def _readback():
    return {"schema": front.SCHEMA + "/read-only-verification", "audit_id": module.SEMANTIC_ID,
        "fixture_only": False, "metadata_only": True, "semantic_rederivations_performed_here": 0,
        "terminal_cli_status_authenticated_here": False, "external_cli_success_hint_supplied": True,
        "operation_registration_sha256": front.REGISTRATION_SHA256,
        "selection_sha256": SELECTION, "complete_sha256": COMPLETE,
        "reservation_sha256": RESERVATION, "counts": copy.deepcopy(front.pure.EXPECTED_ACTUAL_COUNTS),
        "predecessor_status": "FAILED_preserved_not_promoted", "authority": front._authority()}


def test_fixed_registration_retains_blocked_observer_and_honest_parent_boundary():
    value = json.loads(module.REGISTRATION_RAW)
    assert module.AUDIT_ID == "ib-selector-trusted-publisher-v3-20261021-once"
    assert module.OUTPUT_PARTS == ("artifacts", "insider_buying", "selector_trusted_publisher_v3")
    assert module.SEMANTIC_ID == front.AUDIT_ID
    assert module.SEMANTIC_PARTS == front.OUTPUT_PARTS
    assert value["new_semantic_invocations_permitted"] == 1
    assert value["prior_semantic_executions"] == 0
    assert value["prior_launch_exit"] == 71
    assert value["parent_isolation"] == "trusted_unsandboxed_python_audit_guard_not_native_denial"
    assert value["semantic_worker_isolation"] == "unchanged_single_native_network_fork_all_write_denial"
    assert value["unchanged_v2_front_sha256"] == "e5d3839ab630e1df3c1b3d1c0e23b0191a4105fa887b400bd49700cdae48daf3"
    assert value["semantic_registration_sha256"] == front.REGISTRATION_SHA256
    assert value["prior_observer_pins"] == {
        "reservation.json": {"bytes": 1845, "sha256": "6309966fea99f54bf293b30d096c778de56b929f6b79ea29d05212996dd9360b"},
        "terminal.json": {"bytes": 522, "sha256": "734d734f93887a288ee59b4148ebd3d115c2f22d1fec5fb80163b70f2de16929"},
    }
    assert module._sha(module.REGISTRATION_RAW) == module.REGISTRATION_SHA256
    assert module._raw(value) == module.REGISTRATION_RAW
    assert value["backtest_readiness_granted"] is False
    assert value["new_source_acquisition_or_qc_or_outcome_access"] is False
    assert value["old_failed_v1_promoted_or_rewritten"] is False


@pytest.mark.parametrize("raw", [b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{"a":Infinity}\n',
    b'{"a": 1}\n', b'{"a":1}', b'{"a":1}\n\n'])
def test_control_decoder_refuses_duplicates_nonfinite_or_noncanonical_bytes(raw):
    with pytest.raises((ValueError, TypeError)):
        module._decode(raw)


def test_semantic_and_metadata_receipts_are_separate_observations():
    success = module._semantic_success(front, _child(_success()))
    checked = module._readback_control(front, _child(_readback()), success)
    assert success == _success()
    assert checked == _readback()
    assert checked["terminal_cli_status_authenticated_here"] is False
    assert checked["external_cli_success_hint_supplied"] is True
    assert checked["semantic_rederivations_performed_here"] == 0


@pytest.mark.parametrize("code,stderr,stdout", [(2, b"", None), (71, b"", None),
    (0, b"PRIVATE ERROR SENTINEL", None), (0, b"", b""), (0, b"", b"x" * 8193)])
def test_terminal_control_never_authenticates_failed_cli_from_a_receipt(code, stderr, stdout):
    with pytest.raises((ValueError, TypeError)):
        module._semantic_success(front, _child(_success(), code=code, stderr=stderr, stdout=stdout))


@pytest.mark.parametrize("key,value", [("fixture_only", 0), ("audit_id", module.AUDIT_ID),
    ("selection_sha256", "2" * 63), ("complete_sha256", "F" * 64),
    ("operation_registration_sha256", "9" * 64), ("predecessor_status", "ACCEPTED"),
    ("extra", False)])
def test_semantic_summary_exact_context_refuses_forged_fields(key, value):
    body = _success()
    body[key] = value
    with pytest.raises((ValueError, TypeError, KeyError)):
        module._semantic_success(front, _child(body))


@pytest.mark.parametrize("key,value", [("metadata_only", 1), ("fixture_only", 0),
    ("semantic_rederivations_performed_here", False), ("terminal_cli_status_authenticated_here", 0),
    ("external_cli_success_hint_supplied", 1), ("selection_sha256", "9" * 64),
    ("operation_registration_sha256", "9" * 64), ("predecessor_status", "ACCEPTED"), ("extra", False)])
def test_readback_control_rejects_type_coercion_and_forged_pins(key, value):
    body = _readback()
    body[key] = value
    with pytest.raises((ValueError, TypeError, KeyError)):
        module._readback_control(front, _child(body), _success())


@pytest.mark.parametrize("event", ["socket.__new__", "socket.connect", "http.client.connect",
    "urllib.Request", "os.system", "os.fork", "os.forkpty", "os.exec", "os.posix_spawn", "pty.spawn"])
def test_parent_process_hook_refuses_network_unknown_processes_and_keychain_exec(event):
    guard = module.ParentAuditGuard("semantic", head=HEAD)
    with pytest.raises(PermissionError):
        guard(event, ())
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", ("/usr/bin/security", ["/usr/bin/security", "find-generic-password"], module.LANE_ROOT, ENV))


@pytest.mark.parametrize("role", ["preflight", "readback", "semantic", "observer"])
@pytest.mark.parametrize("target", ["artifacts/sec_insider/raw/input.zip", "research/source.py",
    "tests/test_source.py", "docs/record.md", "artifacts/insider_buying/selector_verification_v2_observer/old.json"])
def test_all_parent_roles_refuse_writes_to_intake_sources_and_predecessors(role, target):
    guard = module.ParentAuditGuard(role, head=HEAD)
    path = module.LANE_ROOT / target
    with pytest.raises(PermissionError):
        guard("open", (str(path), "w", os.O_WRONLY | os.O_CREAT))
    with pytest.raises(PermissionError):
        guard("open", (str(path), "r+", os.O_RDWR))


@pytest.mark.parametrize("event", ["os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink",
    "os.chmod", "os.chown", "os.truncate", "os.utime"])
def test_parent_process_hook_refuses_mutations_even_in_its_allowed_namespace(event):
    guard = module.ParentAuditGuard("observer", head=HEAD)
    with pytest.raises(PermissionError):
        guard(event, (str(module.LANE_ROOT.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID, "reservation.json")),))


def test_parent_roles_have_only_their_exact_publication_leaves():
    observer = module.ParentAuditGuard("observer", head=HEAD)
    semantic = module.ParentAuditGuard("semantic", head=HEAD)
    observer_root = module.LANE_ROOT.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID)
    semantic_root = module.LANE_ROOT.joinpath(*module.SEMANTIC_PARTS, module.SEMANTIC_ID)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    observer("open", (str(observer_root / "reservation.json"), "w", flags))
    semantic("open", (str(semantic_root / "selection.json"), "w", flags))
    observer("os.mkdir", (str(observer_root), 0o700, -1))
    semantic("os.mkdir", (str(semantic_root), 0o700, -1))
    for guard, path in [(observer, semantic_root / "selection.json"),
                        (semantic, observer_root / "terminal.json"),
                        (observer, observer_root / "extra.json"),
                        (semantic, semantic_root / "extra.json")]:
        with pytest.raises(PermissionError):
            guard("open", (str(path), None, flags))
    for role in ("preflight", "readback"):
        with pytest.raises(PermissionError):
            module.ParentAuditGuard(role, head=HEAD)("open", (str(semantic_root / "complete.json"), None, flags))


def test_descriptor_relative_and_symlink_paths_cannot_escape_publication_fence(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "LANE_ROOT", tmp_path)
    output = tmp_path.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID)
    output.mkdir(parents=True)
    forbidden = tmp_path / "intake"
    forbidden.mkdir()
    (output / "reservation.json").symlink_to(forbidden / "victim")
    guard = module.ParentAuditGuard("observer", head=HEAD)
    with pytest.raises(PermissionError):
        guard("open", (str(output / "reservation.json"), "w", os.O_WRONLY))
    descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(PermissionError):
            guard("os.mkdir", ("../../escape", 0o700, descriptor))
    finally:
        os.close(descriptor)


def test_exact_git_controls_allow_only_clean_identity_and_current_or_historical_sources():
    guard = module.ParentAuditGuard("readback", head=HEAD)
    environment = {"PATH": "/usr/bin:/bin"}
    for args in [["rev-parse", "HEAD"], ["branch", "--show-current"],
                 ["status", "--porcelain=v1", "--untracked-files=all"],
                 ["show", HEAD + ":research/example.py"]]:
        command = ["/usr/bin/git", *args]
        guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, environment))
    for args in [["fetch", "origin"], ["reset", "--hard"], ["show", "9" * 40 + ":research/example.py"],
                 ["show", HEAD + ":../private.py"], ["show", HEAD + ":/private.py"],
                 ["show", HEAD + ":artifacts/private.json"]]:
        command = ["/usr/bin/git", *args]
        with pytest.raises(PermissionError):
            guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, environment))


def test_observer_allows_each_exact_role_command_once_and_refuses_dirty_environment(tmp_path):
    command = module._role_command("semantic", HEAD, tmp_path / "unused")
    guard = module.ParentAuditGuard("observer", head=HEAD, commands=[command])
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", (sys.executable, command, module.LANE_ROOT, {**ENV, "PYTHONPATH": "PRIVATE SENTINEL"}))
    guard("subprocess.Popen", (sys.executable, command, module.LANE_ROOT, ENV))
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", (sys.executable, command, module.LANE_ROOT, ENV))
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", (sys.executable, command[:-1] + ["other-head"], module.LANE_ROOT, ENV))


def test_semantic_role_allows_exactly_one_unchanged_native_worker_and_never_a_plain_python_worker():
    guard = module.ParentAuditGuard("semantic", head=HEAD)
    guard.front = front
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p",
        front.original.isolation._worker_policy(module.LANE_ROOT.joinpath(*module.SEMANTIC_PARTS, module.SEMANTIC_ID), readonly=True),
        sys.executable, "-I", "-S", "-B", "-c", front.SOURCE_ONLY_BOOTSTRAP]
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", (sys.executable, [sys.executable, "-c", front.SOURCE_ONLY_BOOTSTRAP], module.LANE_ROOT, None))
    guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, None))
    assert guard.worker_launches == 1
    with pytest.raises(PermissionError):
        guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, None))


def test_role_hook_is_installed_before_front_import_and_readback_never_calls_semantics(monkeypatch, capsys):
    hooks, events = [], []
    monkeypatch.setattr(module.sys, "addaudithook", lambda hook: (hooks.append(hook), events.append("hook")))
    def supplied_front():
        assert events == ["hook"]
        events.append("front")
        return SimpleNamespace(verify_observed_completion=lambda **kwargs: {"metadata_only": True, **kwargs})
    monkeypatch.setattr(module, "_front", supplied_front)
    assert module.role_main("readback", HEAD, SELECTION, COMPLETE) == 0
    assert events == ["hook", "front"]
    assert len(hooks) == 1 and hooks[0].role == "readback"
    assert json.loads(capsys.readouterr().out)["observed_cli_success"] is True


def _prior_observer(tmp_path, monkeypatch):
    root = (tmp_path / "invented-prior-lane").resolve()
    monkeypatch.setattr(module, "LANE_ROOT", root)
    prior = root.joinpath(*module.PRIOR_OBSERVER_PARTS)
    prior.mkdir(parents=True, mode=0o700)
    images = {"reservation.json": b'{"invented":"reservation"}', "terminal.json": b'{"invented":"failed"}'}
    for name, raw in images.items():
        path = prior / name
        path.write_bytes(raw)
        path.chmod(0o600)
    monkeypatch.setattr(module, "PRIOR_OBSERVER_PINS", {
        name: (len(raw), module._sha(raw)) for name, raw in images.items()
    })
    return prior, images


def test_prior_failed_observer_is_held_rehashed_and_closed_without_promoting_or_rewriting(tmp_path, monkeypatch):
    prior, images = _prior_observer(tmp_path, monkeypatch)
    held = module._HeldPriorObserver(front)
    streams = [stream for _, stream, _, _ in held.tree.handles]
    held.recheck(front)
    assert {path.name: path.read_bytes() for path in prior.iterdir()} == images
    held.close()
    assert held.tree is None and all(stream.closed for stream in streams)
    held.close()


@pytest.mark.parametrize("fault", ["extra", "content", "mode", "hardlink", "symlink"])
def test_prior_observer_rejects_any_nonexact_leaf_or_custody_before_new_semantic_work(tmp_path, monkeypatch, fault):
    prior, images = _prior_observer(tmp_path, monkeypatch)
    target = prior / "terminal.json"
    if fault == "extra":
        (prior / "extra.json").write_bytes(b"{}")
    elif fault == "content":
        target.write_bytes(b"x" * len(images["terminal.json"]))
    elif fault == "mode":
        target.chmod(0o644)
    elif fault == "hardlink":
        os.link(target, tmp_path / "invented-link")
    else:
        target.unlink()
        target.symlink_to(prior / "reservation.json")
    with pytest.raises((ValueError, OSError)):
        module._HeldPriorObserver(front)


def test_prior_observer_final_recheck_catches_same_size_content_change(tmp_path, monkeypatch):
    prior, images = _prior_observer(tmp_path, monkeypatch)
    held = module._HeldPriorObserver(front)
    try:
        original = (prior / "terminal.json").stat()
        (prior / "terminal.json").write_bytes(b"x" * len(images["terminal.json"]))
        os.utime(prior / "terminal.json", ns=(original.st_atime_ns, original.st_mtime_ns))
        with pytest.raises((ValueError, OSError)):
            held.recheck(front)
    finally:
        held.close()


@pytest.mark.parametrize("fault", [None, "extra", "content", "mode", "hardlink"])
def test_fresh_observer_journal_requires_exact_private_rehashed_leaves(tmp_path, fault):
    root = (tmp_path / "invented-fresh-journal").resolve()
    root.mkdir(mode=0o700)
    directory = front.original.capture.custody._Directory(root)
    try:
        pins = {name: directory.publish(name, module._raw({"invented_leaf": name}), cap=1024)
            for name in ("reservation.json", "terminal.json", "readback.json")}
        module._verify_journal(front, directory, pins)
        target = root / "terminal.json"
        if fault == "extra":
            directory.publish("extra.json", b"{}", cap=1024)
        elif fault == "content":
            previous = target.stat()
            target.write_bytes(b"x" * previous.st_size)
            os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        elif fault == "mode":
            target.chmod(0o644)
        elif fault == "hardlink":
            os.link(target, tmp_path / "invented-extra-link")
        if fault is None:
            module._verify_journal(front, directory, pins)
        else:
            with pytest.raises((ValueError, OSError)):
                module._verify_journal(front, directory, pins)
    finally:
        directory.close()


def _faulty_owned_tree(tmp_path):
    """Invented owned handles: first reversed close raises, others must drain."""
    states = {"bad_closed": False}
    class BadStream(io.BytesIO):
        def close(self):
            super().close()
            states["bad_closed"] = True
            raise OSError("INVENTED OWNED CLOSE FAULT")
    good, bad = io.BytesIO(b"invented-good"), BadStream(b"invented-bad")
    fds = [os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _ in range(2)]
    class Tree:
        names = frozenset({"invented-unexpected.json"})
        handles = [("good", good, None, 100), ("bad", bad, None, 100)]
        chain = SimpleNamespace(fds=list(fds))
        def close(self):
            # Faithful old shared convenience behavior, intentionally weak.
            for _, stream, _, _ in reversed(self.handles):
                stream.close()
            for descriptor in reversed(self.chain.fds):
                os.close(descriptor)
    tree = Tree()
    def check_drained():
        assert states["bad_closed"] and good.closed and bad.closed
        assert tree.handles == [] and tree.chain.fds == []
        for descriptor in fds:
            with pytest.raises(OSError) as caught:
                os.fstat(descriptor)
            assert caught.value.errno == errno.EBADF
    def rescue():
        good.close()
        try:
            bad.close()
        except OSError:
            pass
        for descriptor in fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
    supplied_front = SimpleNamespace(
        held_io=SimpleNamespace(_HeldCapture=lambda *args, **kwargs: tree),
        _close_tree=front._close_tree,
    )
    return tree, supplied_front, check_drained, rescue


def test_prior_constructor_preserves_primary_inventory_refusal_while_draining_every_owned_handle(tmp_path):
    tree, supplied_front, check_drained, rescue = _faulty_owned_tree(tmp_path)
    try:
        with pytest.raises(module.TrustedSelectorLauncherError, match="exact_failed_observer_inventory"):
            module._HeldPriorObserver(supplied_front)
        check_drained()
    finally:
        rescue()


def test_prior_close_detaches_tree_and_drains_siblings_before_raising_cleanup_fault(tmp_path):
    tree, supplied_front, check_drained, rescue = _faulty_owned_tree(tmp_path)
    held = object.__new__(module._HeldPriorObserver)
    held.tree, held.front = tree, supplied_front
    try:
        with pytest.raises(OSError, match="INVENTED OWNED CLOSE FAULT"):
            held.close()
        assert held.tree is None
        check_drained()
        held.close()
    finally:
        rescue()


def test_journal_cleanup_preserves_primary_inventory_refusal_and_drains_every_owned_handle(tmp_path):
    tree, supplied_front, check_drained, rescue = _faulty_owned_tree(tmp_path)
    journal = SimpleNamespace(path=tmp_path, check=lambda: None)
    try:
        with pytest.raises(module.TrustedSelectorLauncherError, match="exact_launcher_journal_inventory"):
            module._verify_journal(supplied_front, journal, {"reservation.json": "1" * 64})
        check_drained()
    finally:
        rescue()


@pytest.mark.parametrize("audit_id", [module.SEMANTIC_ID, module.AUDIT_ID + "-retry", "../" + module.AUDIT_ID])
def test_scope_refusal_precedes_import_or_any_namespace_creation(audit_id, monkeypatch):
    monkeypatch.setattr(module, "_front", lambda: pytest.fail("front imported before fixed scope rejection"))
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **_: pytest.fail("namespace created before scope rejection"))
    with pytest.raises(module.TrustedSelectorLauncherError):
        module.main(["--audit-id", audit_id, "--expected-head", HEAD])


def test_real_directory_publication_crosses_audit_guard_only_for_known_custody_frame(tmp_path):
    root = (tmp_path / "invented-real-hook-lane").resolve()
    output = root.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID)
    output.mkdir(parents=True, mode=0o700)
    protected = root / "artifacts/sec_insider/raw"
    protected.mkdir(parents=True)
    script = """import json,os,sys
from pathlib import Path
from research import insider_buying_affected_quarter_selector_launcher_v3 as m
m.LANE_ROOT=Path(sys.argv[1]);guard=m.ParentAuditGuard('observer',head='1'*40)
sys.addaudithook(guard)
front=m._front();guard.front=front
root=m.LANE_ROOT.joinpath(*m.OUTPUT_PARTS,m.AUDIT_ID)
directory=front.original.capture.custody._Directory(root)
proof={}
try:
 proof['published_sha256']=directory.publish('reservation.json',b'{"invented":true}',cap=100)
 proof['bytes']=len(directory.read('reservation.json',cap=100))
 try: directory.publish('reservation.json',b'{"different":true}',cap=100)
 except FileExistsError: proof['exclusive']=True
 try: directory.publish('extra.json',b'{}',cap=100)
 except PermissionError: proof['extra_refused']=True
 try: os.open('terminal.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=directory.fd)
 except (PermissionError,m.TrustedSelectorLauncherError): proof['unknown_fd_relative_writer_refused']=True
 try: os.open(m.LANE_ROOT/'artifacts/sec_insider/raw/forbidden',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except PermissionError: proof['intake_write_refused']=True
finally: directory.close()
print(json.dumps(proof,sort_keys=True,separators=(',',':')))
"""
    child = module.run_child([sys.executable, "-B", "-c", script, str(root)],
        cwd=module.LANE_ROOT, env=ENV, timeout=30)
    assert child.returncode == 0 and child.stderr == b""
    assert json.loads(child.stdout) == {"published_sha256": module._sha(b'{"invented":true}'),
        "bytes": 17, "exclusive": True, "extra_refused": True,
        "unknown_fd_relative_writer_refused": True, "intake_write_refused": True}
    assert {path.name for path in output.iterdir()} == {"reservation.json"}
    assert (output / "reservation.json").stat().st_mode & 0o777 == 0o600
    assert list(protected.iterdir()) == []


def test_installed_observer_guard_allows_real_bounded_child_transport_but_not_arbitrary_devnull_writes(tmp_path):
    root = (tmp_path / "invented-observer-transport-lane").resolve()
    root.mkdir(mode=0o700)
    script = """import json,os,sys
from pathlib import Path
from research import insider_buying_affected_quarter_selector_launcher_v3 as m
m.LANE_ROOT=Path(sys.argv[1])
command=[sys.executable,'-I','-S','-B','-c',"print('invented-child-control')"]
environment={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
guard=m.ParentAuditGuard('observer',head='1'*40,commands=[command])
sys.addaudithook(guard)
proof={}
try: descriptor=os.open('/dev/null',os.O_RDWR)
except PermissionError: proof['arbitrary_devnull_write_refused']=True
else: os.close(descriptor);proof['arbitrary_devnull_write_refused']=False
try: m.run_child(command[:-1]+["print('unknown-command')"],cwd=m.LANE_ROOT,env=environment,timeout=10,cap=100)
except PermissionError: proof['unknown_child_devnull_refused']=True
child=m.run_child(command,cwd=m.LANE_ROOT,env=environment,timeout=10,cap=100)
proof.update(exit_code=child.returncode,stdout_sha256=m._sha(child.stdout),stderr_bytes=len(child.stderr),
             exact_role_command_consumed=tuple(command) in guard.used_commands)
print(json.dumps(proof,sort_keys=True,separators=(',',':')))
"""
    child = module.run_child([sys.executable, "-B", "-c", script, str(root)],
        cwd=module.LANE_ROOT, env=ENV, timeout=30)
    assert child.returncode == 0 and child.stderr == b""
    assert json.loads(child.stdout) == {"arbitrary_devnull_write_refused": True,
        "unknown_child_devnull_refused": True,
        "exit_code": 0, "stdout_sha256": module._sha(b"invented-child-control\n"),
        "stderr_bytes": 0, "exact_role_command_consumed": True}
    assert list(root.iterdir()) == []


def test_installed_semantic_guard_crosses_real_stdin_pipe_wrapper_before_a_stubbed_exec_only(tmp_path):
    """No inner launch: stub only _execute_child, after real CPython pipe setup."""
    root = tmp_path.resolve()
    script = """import json,os,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from research import insider_buying_affected_quarter_selector_launcher_v3 as m
m.LANE_ROOT=Path(sys.argv[1]);policy='(version 1)(allow default)(deny network*)(deny file-write*)(deny process-fork)'
worker="print('invented-preexec-only')"
fixture=SimpleNamespace(SOURCE_ONLY_BOOTSTRAP=worker,
 original=SimpleNamespace(isolation=SimpleNamespace(_worker_policy=lambda *_args,**_kwargs:policy)))
command=['/usr/bin/env','-i','PATH=/usr/bin:/bin:/usr/sbin:/sbin','/usr/bin/sandbox-exec','-p',policy,
 sys.executable,'-I','-S','-B','-c',worker]
read_fd,write_fd=os.pipe()
class InventedPreexecReached(OSError):pass
def no_child_execution(*_args,**_kwargs):raise InventedPreexecReached('invented-no-execution')
subprocess.Popen._execute_child=no_child_execution
guard=m.ParentAuditGuard('semantic',head='1'*40);guard.front=fixture
sys.addaudithook(guard)
proof={}
try:
 try:os.fdopen(write_fd,'wb',closefd=False)
 except (PermissionError,ValueError,OSError):proof['unknown_pipe_wrapper_refused']=True
 try:subprocess.run(command,cwd=m.LANE_ROOT,input=b'invented-only',capture_output=True,check=False,timeout=10)
 except InventedPreexecReached:proof['genuine_stdin_pipe_wrapper_reached_stubbed_exec']=True
finally:os.close(read_fd);os.close(write_fd)
proof['inner_child_executions']=0
print(json.dumps(proof,sort_keys=True,separators=(',',':')))
"""
    child = module.run_child([sys.executable, "-B", "-c", script, str(root)],
        cwd=module.LANE_ROOT, env=ENV, timeout=30)
    assert child.returncode == 0 and child.stderr == b""
    assert json.loads(child.stdout) == {"unknown_pipe_wrapper_refused": True,
        "genuine_stdin_pipe_wrapper_reached_stubbed_exec": True, "inner_child_executions": 0}
    assert list(root.iterdir()) == []


def _orchestration(tmp_path, monkeypatch, *, fault=None):
    root = (tmp_path / "invented-lane").resolve()
    root.mkdir(mode=0o700)
    monkeypatch.setattr(module, "LANE_ROOT", root)
    monkeypatch.setattr(module, "__file__", str(root / module.SELF_PATH))
    monkeypatch.chdir(root)
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **_: str(tmp_path / "prefix"))
    hooks = []
    monkeypatch.setattr(module.sys, "addaudithook", hooks.append)
    identity = {"head": HEAD, "source_sha256": {module.SELF_PATH: "5" * 64}}
    context = {"identity": identity, "frozen": {"invented": True}}
    monkeypatch.setattr(module, "_front", lambda: front)
    monkeypatch.setattr(module, "_identity", lambda *_: copy.deepcopy(context))
    state = {"prior_closed": False, "rechecks": 0, "roles": []}
    class Prior:
        def __init__(self, _):
            pass
        def recheck(self, _):
            state["rechecks"] += 1
            if fault == "prior":
                raise ValueError("PRIVATE PRIOR SENTINEL")
        def close(self):
            state["prior_closed"] = True
    monkeypatch.setattr(module, "_HeldPriorObserver", Prior)
    def run(command, **kwargs):
        role = next(name for name in ("preflight", "semantic", "readback") if name in command)
        state["roles"].append(role)
        assert kwargs["cwd"] == root and kwargs["env"] == ENV
        if role == "preflight":
            return _child(context)
        if role == "semantic":
            if fault == "timeout":
                raise subprocess.TimeoutExpired(command, 1900, b"PRIVATE STDOUT SENTINEL", b"PRIVATE STDERR SENTINEL")
            if fault == "failure":
                return _child(stdout=b"PRIVATE SEMANTIC SENTINEL", code=2)
            return _child(_success())
        assert role == "readback"
        if fault == "readback":
            return _child(stdout=b"PRIVATE READBACK SENTINEL", code=2)
        return _child(_readback())
    monkeypatch.setattr(module, "run_child", run)
    return root, state, hooks


def test_invented_observer_publishes_private_exclusive_journal_only_after_real_terminal_and_readback_controls(tmp_path, monkeypatch, capsys):
    root, state, hooks = _orchestration(tmp_path, monkeypatch)
    assert module.main(["--audit-id", module.AUDIT_ID, "--expected-head", HEAD]) == 0
    journal = root.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID)
    assert {path.name for path in journal.iterdir()} == {"reservation.json", "terminal.json", "readback.json", "final.json"}
    final = json.loads((journal / "final.json").read_bytes())
    assert final["semantic_exit0_observed"] is True and final["strict_readback_accepted"] is True
    assert final["parent_isolation"] == "trusted_unsandboxed_python_audit_guard_not_native_denial"
    assert final["semantic_invocations_performed"] == 1
    assert final["old_failed_v1_promoted_or_rewritten"] is False
    assert final["authority"] == front._authority()
    assert not any(final["authority"].values())
    assert state["roles"] == ["preflight", "semantic", "readback"]
    assert state["prior_closed"] is True
    assert (journal.stat().st_mode & 0o777) == 0o700
    assert all((path.stat().st_mode & 0o777) == 0o600 and path.stat().st_nlink == 1 for path in journal.iterdir())
    assert hooks and hooks[0].role == "observer"
    images = {path.name: path.read_bytes() for path in journal.iterdir()}
    with pytest.raises(module.TrustedSelectorLauncherError, match="consumed"):
        module.main(["--audit-id", module.AUDIT_ID, "--expected-head", HEAD])
    assert {path.name: path.read_bytes() for path in journal.iterdir()} == images
    assert state["roles"].count("semantic") == 1
    assert "PRIVATE" not in capsys.readouterr().out


@pytest.mark.parametrize("fault,leaves,roles", [
    ("timeout", {"reservation.json", "terminal.json"}, ["preflight", "semantic"]),
    ("failure", {"reservation.json", "terminal.json"}, ["preflight", "semantic"]),
    ("readback", {"reservation.json", "terminal.json", "readback.json"}, ["preflight", "semantic", "readback"]),
    ("prior", {"reservation.json", "terminal.json"}, ["preflight", "semantic"]),
])
def test_failed_terminal_or_custody_never_creates_final_or_retries_and_closes_holds(tmp_path, monkeypatch, capsys, fault, leaves, roles):
    root, state, _ = _orchestration(tmp_path, monkeypatch, fault=fault)
    try:
        result = module.main(["--audit-id", module.AUDIT_ID, "--expected-head", HEAD])
        assert result == 2
    except (ValueError, module.TrustedSelectorLauncherError):
        assert fault in {"prior", "readback"}
    journal = root.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID)
    assert {path.name for path in journal.iterdir()} == leaves
    assert state["roles"] == roles
    assert state["prior_closed"] is True
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    terminal = json.loads((journal / "terminal.json").read_bytes())
    if fault in {"timeout", "failure"}:
        assert terminal["terminal_success_observed"] is False


def test_main_cleanup_keeps_primary_custody_failure_when_journal_close_also_fails(tmp_path, monkeypatch, capsys):
    root, state, _ = _orchestration(tmp_path, monkeypatch, fault="prior")
    directory_type = front.original.capture.custody._Directory
    def directory(path, **kwargs):
        held = directory_type(path, **kwargs)
        if Path(path).name == module.AUDIT_ID:
            close = held.close
            def failing_close():
                close()
                raise OSError("INVENTED JOURNAL CLOSE FAULT")
            held.close = failing_close
        return held
    monkeypatch.setattr(front.original.capture.custody, "_Directory", directory)
    with pytest.raises(ValueError, match="PRIVATE PRIOR SENTINEL"):
        module.main(["--audit-id", module.AUDIT_ID, "--expected-head", HEAD])
    assert state["prior_closed"] is True
    assert state["roles"] == ["preflight", "semantic"]
    assert {path.name for path in root.joinpath(*module.OUTPUT_PARTS, module.AUDIT_ID).iterdir()} == {
        "reservation.json", "terminal.json"}
    assert "PRIVATE" not in capsys.readouterr().out


def test_child_transport_bounds_both_pipes_and_reaps_group_after_timeout(tmp_path):
    child = module.run_child([sys.executable, "-I", "-S", "-B", "-c", "import sys;print('invented');sys.stderr.write('control')"],
        cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=5)
    assert child.returncode == 0 and child.stdout == b"invented\n" and child.stderr == b"control"
    for pipe in ("stdout", "stderr"):
        code = "import sys;sys." + pipe + ".write('x'*65);sys." + pipe + ".flush()"
        with pytest.raises(module.TrustedSelectorLauncherError, match="bounded_child_pipe"):
            module.run_child([sys.executable, "-I", "-S", "-B", "-c", code],
                cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=5, cap=64)
    code = "import os,time;print(os.getpid(),flush=True);time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        module.run_child([sys.executable, "-I", "-S", "-B", "-c", code],
            cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=0.15)
    pid = int(caught.value.stdout.strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("timeout,cap", [(0, 100), (-1, 100), (True, 100), (float("nan"), 100),
    (float("inf"), 100), (1, 0), (1, True)])
def test_child_transport_refuses_invalid_bounds_before_process_creation(monkeypatch, timeout, cap):
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: pytest.fail("invalid transport bounds launched process"))
    with pytest.raises(module.TrustedSelectorLauncherError):
        module.run_child(["invented"], cwd=module.LANE_ROOT, env=ENV, timeout=timeout, cap=cap)


@pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("IB_SELECTOR_V3_NATIVE_TOPOLOGY") != "1",
    reason="single-profile topology requires separately selected trusted unsandboxed synthetic harness")
def test_trusted_parent_launches_one_native_worker_with_before_input_denial_proofs(tmp_path):
    """Native loopback-connect denial, not just an allowed socket allocation."""
    inside, outside = tmp_path / "invented-output", tmp_path / "invented-outside"
    inside.mkdir()
    outside.mkdir()
    policy = front.original.isolation._worker_policy(inside.resolve(), readonly=True)
    worker = """import errno,json,os,socket,sys
proof={}
try:
 s=socket.socket();s.settimeout(0.2);s.connect(('127.0.0.1',9));s.close();proof['network']=0
except OSError as exc: proof['network']=exc.errno
try:
 p=os.fork()
 if p==0: os._exit(0)
 os.waitpid(p,0);proof['fork']=0
except OSError as exc: proof['fork']=exc.errno
for label,path in [('inside',sys.argv[1]),('outside',sys.argv[2])]:
 try:
  f=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(f);proof[label]=0
 except OSError as exc: proof[label]=exc.errno
proof['before_input']=True
proof['source_rows_read']=0
print(json.dumps(proof,sort_keys=True,separators=(',',':')))
"""
    command = ["/usr/bin/sandbox-exec", "-p", policy, sys.executable, "-I", "-S", "-B", "-c", worker,
        str(inside / "probe"), str(outside / "probe")]
    # The trusted test parent deliberately has no native profile, so the one
    # native child can install the worker's complete policy without nesting.
    # A separate Python guard blocks network/credential/other subprocess use;
    # it is not relabeled native parent isolation.
    hook = """import json,os,subprocess,sys
command=json.loads(sys.argv[1]);root=sys.argv[2]
def guard(event,args):
 if event.startswith(('socket.','http.client.','urllib.')) or event in {'os.system','os.fork','os.exec','os.posix_spawn'}:
  raise PermissionError('invented_trusted_parent_refused')
 if event=='subprocess.Popen' and tuple(args[1])!=tuple(command):
  raise PermissionError('invented_trusted_parent_unknown_child')
sys.addaudithook(guard)
child=subprocess.run(command,cwd=root,env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=10)
sys.stdout.buffer.write(child.stdout);sys.stderr.buffer.write(child.stderr)
raise SystemExit(child.returncode)
"""
    child = module.run_child([sys.executable, "-I", "-S", "-B", "-c", hook, json.dumps(command), str(tmp_path)],
        cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=15)
    assert child.returncode == 0 and child.stderr == b""
    proof = json.loads(child.stdout)
    assert proof == {"network": errno.EPERM, "fork": errno.EPERM, "inside": errno.EPERM,
        "outside": errno.EPERM, "before_input": True, "source_rows_read": 0}
    assert list(inside.iterdir()) == [] and list(outside.iterdir()) == []


@pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("IB_SELECTOR_V3_NATIVE_TOPOLOGY") != "1",
    reason="input-PIPE topology requires separately selected trusted unsandboxed synthetic harness")
def test_installed_semantic_guard_allows_real_input_pipe_but_not_unknown_regular_descriptor_writes(tmp_path):
    """Use the exact production command shape, but only invented stdin bytes."""
    root = tmp_path.resolve()
    regular = root / "invented-regular-file"
    regular.write_bytes(b"preserved-invented-regular-file")
    output = root / "invented-worker-output"
    output.mkdir()
    policy = front.original.isolation._worker_policy(output, readonly=True)
    worker = "import hashlib,json,sys;body=sys.stdin.buffer.read(64);print(json.dumps({'input_bytes':len(body),'input_sha256':hashlib.sha256(body).hexdigest()},sort_keys=True,separators=(',',':')))"
    script = """import json,os,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from research import insider_buying_affected_quarter_selector_launcher_v3 as m
m.LANE_ROOT=Path(sys.argv[2]);policy=sys.argv[3];worker=sys.argv[4]
regular_fd=os.open(sys.argv[5],os.O_RDWR)
unknown_pipe_read,unknown_pipe_write=os.pipe()
fixture=SimpleNamespace(SOURCE_ONLY_BOOTSTRAP=worker,
 original=SimpleNamespace(isolation=SimpleNamespace(_worker_policy=lambda *_args,**_kwargs:policy)))
guard=m.ParentAuditGuard('semantic',head='1'*40);guard.front=fixture
sys.addaudithook(guard)
proof={}
try:
 try: os.fdopen(regular_fd,'wb',closefd=False)
 except (PermissionError,ValueError,OSError): proof['unknown_regular_fd_write_refused']=True
 try: os.fdopen(unknown_pipe_write,'wb',closefd=False)
 except (PermissionError,ValueError,OSError): proof['unknown_pipe_write_refused']=True
 command=['/usr/bin/env','-i','PATH=/usr/bin:/bin:/usr/sbin:/sbin','/usr/bin/sandbox-exec','-p',policy,
  sys.executable,'-I','-S','-B','-c',worker]
 child=subprocess.run(command,cwd=m.LANE_ROOT,input=b'invented-input-only',capture_output=True,check=False,timeout=10)
 proof.update(exit_code=child.returncode,stderr_bytes=len(child.stderr),worker_launches=guard.worker_launches)
 if child.returncode==0:proof['child_control']=json.loads(child.stdout)
finally:os.close(regular_fd);os.close(unknown_pipe_read);os.close(unknown_pipe_write)
print(json.dumps(proof,sort_keys=True,separators=(',',':')))
"""
    child = module.run_child([sys.executable, "-I", "-S", "-B", "-c", script,
        str(module.LANE_ROOT), str(root), policy, worker, str(regular)],
        cwd=root, env={"PATH": "/usr/bin:/bin"}, timeout=30)
    assert child.returncode == 0 and child.stderr == b""
    assert json.loads(child.stdout) == {"unknown_regular_fd_write_refused": True, "unknown_pipe_write_refused": True,
        "exit_code": 0, "stderr_bytes": 0, "worker_launches": 1,
        "child_control": {"input_bytes": 19, "input_sha256": module._sha(b"invented-input-only")}}
    assert regular.read_bytes() == b"preserved-invented-regular-file"
    assert list(output.iterdir()) == []


# Claude review section 201: in-memory mutants that each of the following
# guards survived. Each test fails if its guard is removed.

def test_child_transport_timeout_kills_the_whole_session_not_only_the_direct_child(tmp_path):
    code = ("import subprocess,sys,time;"
            "g=subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time;time.sleep(30)']);"
            "print(g.pid,flush=True);time.sleep(30)")
    grandchild = None
    try:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            module.run_child([sys.executable, "-I", "-S", "-B", "-c", code],
                cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=2)
        grandchild = int(caught.value.stdout.strip())
        deadline = time.monotonic() + 5
        while True:
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break
            assert time.monotonic() < deadline, "descendant survived the timeout kill"
            time.sleep(0.05)
    finally:
        if grandchild is not None:
            try:
                os.kill(grandchild, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_git_and_observer_admission_require_minimal_environment_and_the_lane_cwd(tmp_path):
    guard = module.ParentAuditGuard("readback", head=HEAD)
    command = ["/usr/bin/git", "rev-parse", "HEAD"]
    guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, {"PATH": "/usr/bin:/bin"}))
    for environment in ({"PATH": "/usr/bin:/bin", "GIT_DIR": "/invented"}, None, {"PATH": "/invented"}):
        with pytest.raises(PermissionError):
            guard("subprocess.Popen", (command[0], command, module.LANE_ROOT, environment))
    role = module._role_command("semantic", HEAD, tmp_path / "unused")
    observer = module.ParentAuditGuard("observer", head=HEAD, commands=[role])
    with pytest.raises(PermissionError):
        observer("subprocess.Popen", (sys.executable, role, tmp_path, ENV))
    observer("subprocess.Popen", (sys.executable, role, module.LANE_ROOT, ENV))


def test_consumed_semantic_namespace_refuses_before_the_observer_scope_is_spent(tmp_path, monkeypatch):
    root, state, _ = _orchestration(tmp_path, monkeypatch)
    root.joinpath(*module.SEMANTIC_PARTS, module.SEMANTIC_ID).mkdir(parents=True, mode=0o700)
    with pytest.raises(module.TrustedSelectorLauncherError, match="semantic_namespace_already_consumed"):
        module.main(["--audit-id", module.AUDIT_ID, "--expected-head", HEAD])
    assert state["roles"] == ["preflight"]
    assert not root.joinpath(*module.OUTPUT_PARTS).exists()


def test_launcher_journal_hold_settles_only_ctime_and_still_rehashes_content(tmp_path, monkeypatch):
    root = tmp_path / "invented-journal"
    root.mkdir(mode=0o700)
    pins = {}
    for name in ("reservation.json", "terminal.json"):
        raw = module._raw({"invented": name})
        (root / name).write_bytes(raw)
        (root / name).chmod(0o600)
        pins[name] = module._sha(raw)
    journal = front.original.capture.custody._Directory(root)
    real, drifted = front.held_io._hash_stream, []
    def drifting(stream, cap):
        # A ctime-only metadata transition on the first leaf, already held.
        if not drifted:
            before = (root / "reservation.json").stat()
            (root / "reservation.json").chmod(0o600)
            after = (root / "reservation.json").stat()
            assert before.st_ctime_ns != after.st_ctime_ns and before.st_mtime_ns == after.st_mtime_ns
            drifted.append(True)
        return real(stream, cap)
    monkeypatch.setattr(front.held_io, "_hash_stream", drifting)
    try:
        module._verify_journal(front, journal, pins)
        assert drifted == [True]
        with pytest.raises(ValueError):
            module._verify_journal(front, journal, {**pins, "terminal.json": "0" * 64})
    finally:
        journal.close()
