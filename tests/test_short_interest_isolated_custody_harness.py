"""Fabricated audit events/driver results only; never install a real audit hook."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("resource", reason="original protected runtime imports POSIX resource")
pytest.importorskip("fcntl", reason="original metadata runtime imports POSIX fcntl")

from data.hashing import hash_bytes, hash_payload
from scripts import run_short_interest_isolated_custody_offline as harness

HEAD, REMOTE = "a" * 40, "b" * 40


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(harness, "_INVOKED", False)
    for name in ("_ORIGINAL", "_COUNTS", "_ACTIVE", "_FAILED"):
        monkeypatch.setattr(harness, name, {})
    monkeypatch.setattr(harness, "HARNESS_SHA256", hash_payload(harness.policy()))


@pytest.fixture
def seams(): return harness.AuditSeams(HEAD)


def event_command(seams, command, executable=None, cwd=None):
    seams.handle("subprocess.Popen", (command[0] if executable is None else executable,
        command, seams.root if cwd is None else cwd, None))


def result(manifest):
    sample = {"fd_flags": 66, "name_flags": 66, "same_original_inode": True,
        "protections_match": True, "size_and_mtime_unchanged": True, "retained_fd_readonly": True}
    diagnostic = {"schema": "si-immutable-transition-diagnostic-v1", "observer_complete": True,
        "observer_failure": None, "native_call_count": 1, "native_result": 0, "native_errno_name": None,
        "before_native": dict(sample, fd_flags=64, name_flags=64), "immediate_after_native": dict(sample),
        "after_callbacks": [dict(sample)], "classification": "required_flags_observed_without_recorded_loss",
        "first_controlled_refusal": None, "controlled_refusals": [],
        "policy_sha256": hash_payload(harness.proof.base.transition.policy()),
        "authority": harness.proof.base.transition.authority()}
    return {"schema": "si-isolated-kernel-immutable-proof-closed-v2",
        "status": "closed_offline_isolated_new_inode_only", "runtime_head": HEAD, "actual_remote": REMOTE,
        "code_identity_sha256": "e" * 64, "code_manifest_sha256": hash_payload(manifest),
        "protocol_sha256": harness.proof.PROTOCOL_SHA256,
        "started_at": "2026-10-27T07:00:00Z", "closed_at": "2026-10-27T07:00:10Z",
        "metadata_raw_sha256": hash_bytes(harness.proof.base.previous.metadata_bytes()),
        "seal_stamp_sha256": "d" * 64, "helper_closed_summary_sha256": "c" * 64,
        "isolated_storage_closed_summary_sha256": "9" * 64,
        "native_transition": {"diagnostic": diagnostic, "diagnostic_sha256": hash_payload(diagnostic)},
        "challenges": [{"challenge": name, "result": "denied", "errno_name": "EPERM"}
            for name in ("write_open", "same_mode_fchmod", "fixed_fsetxattr")],
        "original_code_and_metadata_contexts_closed": True, "authority": harness.proof.authority()}


def completed_seams(seams):
    state = {"image": seams.namespace / harness.proof.storage.IMAGE_NAME, "mount": seams.mount}
    for verb in ("create", "attach"): event_command(seams, harness.proof.storage._arguments(state, verb))
    seams.handle("open", (harness.proof.NAME, None, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW))
    seams.handle("open", (harness.proof.NAME, None, os.O_WRONLY | os.O_NOFOLLOW))


def test_fixed_creator_RDWR_and_real_WRONLY_challenge_with_implicit_cloexec(seams):
    original_open, capabilities = os.open, set(os.supports_dir_fd)
    extra = getattr(os, "O_CLOEXEC", 0)
    seams.handle("open", (harness.proof.NAME, None, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | extra))
    seams.handle("open", (harness.proof.NAME, None, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | extra))
    seams.handle("open", (harness.proof.NAME, None, os.O_WRONLY | os.O_NOFOLLOW | extra))
    seams.handle("open", ("/dev/null", None, os.O_RDWR | extra))
    assert seams.permitted["probe_create"] == seams.permitted["probe_write_challenge"] == 1
    assert seams.permitted["null_stream"] == 1 and not seams.failed
    assert os.open is original_open and os.supports_dir_fd == capabilities


@pytest.mark.parametrize("name,flags", [("old.spent.json", os.O_RDWR | os.O_CREAT | os.O_EXCL),
    ("one-safe-nonclaim.private.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW),
    ("one-safe-nonclaim.private.json", os.O_RDWR | os.O_TRUNC),
    ("/dev/null", os.O_RDWR | os.O_TRUNC)])
def test_all_other_write_opens_refuse_without_original_syscall(seams, name, flags):
    with pytest.raises(harness.OfflineHarnessRefusal, match="write_open_denied"):
        seams.handle("open", (name, None, flags))
    assert seams.failed and seams.denied["write_open"] == 1


def test_duplicate_creation_and_old_private_read_fail_closed(seams):
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    seams.handle("open", (harness.proof.NAME, None, flags))
    with pytest.raises(harness.OfflineHarnessRefusal): seams.handle("open", (harness.proof.NAME, None, flags))
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (str(seams.parent / "old-spent-source" / "row.raw"), "r", os.O_RDONLY))
    fresh = harness.AuditSeams(HEAD)
    with pytest.raises(harness.OfflineHarnessRefusal, match="read_open_denied"):
        fresh.handle("open", (str(fresh.parent / "old-spent-source" / "row.raw"), "r", os.O_RDONLY))


def test_exact_new_artifact_and_committed_code_read_names_only(seams):
    for name in (str(seams.parent), str(seams.namespace), str(seams.probe), harness.proof.NAME,
            str(seams.root / harness.DRIVER), harness.proof.storage.IMAGE_NAME):
        seams.handle("open", (name, "r", os.O_RDONLY))
    assert all(value == 0 for value in seams.denied.values())


def test_exact_committed_code_parent_directories_are_readable_not_arbitrary_subtrees(seams):
    parents = {str((seams.root / name).parent) for name in harness.proof.code_paths()}
    for parent in parents:
        seams.handle("open", (parent, None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))


def test_original_HeldFiles_relative_code_basenames_are_readable(seams):
    for name in harness.proof.code_paths():
        seams.handle("open", (Path(name).name, None, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK))


def test_caught_denial_cannot_be_reset_into_clean_validator_state(seams):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    completed_seams(seams)
    with pytest.raises(harness.OfflineHarnessRefusal):
        seams.handle("open", ("old-source.raw", None, os.O_WRONLY | os.O_TRUNC))
    seams.failed = False; seams.denied["write_open"] = 0
    with pytest.raises(harness.OfflineHarnessRefusal):
        harness._validate_result(result(manifest), seams, HEAD, REMOTE, manifest)
    assert seams.summary()["denied"]["write_open"] == 1
    assert seams.summary()["failure_latched"] is True


def test_public_quota_reset_cannot_authorize_second_image_create(seams):
    state = {"image": seams.namespace / harness.proof.storage.IMAGE_NAME, "mount": seams.mount}
    command = harness.proof.storage._arguments(state, "create")
    event_command(seams, command)
    seams.permitted["create"] = 0
    with pytest.raises(harness.OfflineHarnessRefusal): event_command(seams, command)


def test_public_active_false_cannot_disable_hot_denials(seams):
    seams.active = False
    with pytest.raises(harness.OfflineHarnessRefusal):
        seams.handle("open", ("old-source.raw", None, os.O_WRONLY | os.O_TRUNC))


def test_replacing_public_counter_dictionary_cannot_forge_original_observation(seams):
    original = seams.permitted
    seams.permitted = dict(original)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (harness.proof.NAME, None, os.O_RDONLY))
    seams.permitted = original; seams.failed = False
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (harness.proof.NAME, None, os.O_RDONLY))
    assert seams.summary()["permitted"]["probe_create"] == 0 and seams.summary()["failure_latched"] is True


def test_trusted_terminal_deactivation_never_erases_prior_failure_or_admits_reuse(seams):
    with pytest.raises(harness.OfflineHarnessRefusal): seams.deny("credentials")
    harness._deactivate(seams)
    seams.handle("open", ("ignored_after_terminal_cleanup", None, os.O_WRONLY))
    assert seams.active is False and seams.summary()["denied"]["credentials"] == 1
    assert seams.summary()["failure_latched"] is True
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    with pytest.raises(harness.OfflineHarnessRefusal):
        harness._validate_result(result(manifest), seams, HEAD, REMOTE, manifest)


def test_exact_matching_git_and_hdiutil_arrays_have_finite_quotas(seams):
    event_command(seams, ["git", "rev-parse", "--show-toplevel"])
    event_command(seams, ["git", "ls-remote", "--exit-code", "origin", "refs/heads/codex/strategy-short-interest"])
    event_command(seams, ["git", "show", HEAD + ":" + harness.DRIVER])
    state = {"image": seams.namespace / harness.proof.storage.IMAGE_NAME, "mount": seams.mount}
    event_command(seams, harness.proof.storage._arguments(state, "create"))
    event_command(seams, harness.proof.storage._arguments(state, "attach"))
    for unused in range(12): event_command(seams, harness.proof.storage._arguments(state, "info"))
    with pytest.raises(harness.OfflineHarnessRefusal, match="subprocess_denied"):
        event_command(seams, harness.proof.storage._arguments(state, "info"))
    assert seams.last_hdiutil == "info" and seams.permitted["Git"] == 3


@pytest.mark.parametrize("command", [["git", "fetch", "origin"], ["git", "show", REMOTE + ":" + harness.DRIVER],
    ["git", "ls-remote", "origin"], ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
    ["/usr/bin/hdiutil", "detach", "/dev/disk999"], ["/usr/bin/security", "find-generic-password"]])
def test_no_other_branch_source_shell_secret_or_device_command(seams, command):
    with pytest.raises(harness.OfflineHarnessRefusal, match="subprocess_denied"): event_command(seams, command)


@pytest.mark.parametrize("event,args,category", [("socket.getaddrinfo", ("PRIVATE",), "network"),
    ("os.remove", ("PRIVATE", -1), "mutation"), ("os.rename", ("PRIVATE", "OTHER", -1, -1), "mutation"),
    ("os.utime", ("PRIVATE", None, None, -1), "mutation"),
    ("ctypes.dlopen", ("PRIVATE",), "native"), ("ctypes.dlsym", (None, "system"), "native")])
def test_denied_events_project_only_fixed_codes(seams, event, args, category):
    with pytest.raises(harness.OfflineHarnessRefusal) as caught: seams.handle(event, args)
    assert seams.denied[category] == 1 and "PRIVATE" not in json.dumps(harness._failure(caught.value))


def test_exact_original_native_symbols_are_not_replaced_or_fake_denied(seams):
    library = SimpleNamespace(_name=harness.proof.base.immutable.LIBRARY)
    seams.handle("ctypes.dlopen", (library._name,))
    for name in ("fstatfs64", "fchflags", "fsetxattr"): seams.handle("ctypes.dlsym", (library, name))
    assert not seams.failed


def test_chmod_only_exact_new_named_inode_and_mode(seams, monkeypatch):
    monkeypatch.setattr(os, "fstat", lambda unused: SimpleNamespace(st_dev=1, st_ino=2))
    monkeypatch.setattr(Path, "lstat", lambda path: SimpleNamespace(st_dev=1, st_ino=2))
    seams.handle("os.chmod", (99, 0o600, -1))
    with pytest.raises(harness.OfflineHarnessRefusal, match="mutation_denied"):
        seams.handle("os.chmod", (99, 0o644, -1))


@pytest.mark.parametrize("kind", ["extra", "authority", "observer", "native_count", "flags", "refusal", "challenge", "counter"])
def test_completed_shape_or_summary_never_bypasses_real_closure_contract(seams, kind):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    value = result(manifest); completed_seams(seams)
    diagnostic = value["native_transition"]["diagnostic"]
    if kind == "extra": value["PRIVATE"] = "SECRET"
    elif kind == "authority": value["authority"]["source_admitted"] = True
    elif kind == "observer": diagnostic["observer_complete"] = False
    elif kind == "native_count": diagnostic["native_call_count"] = True
    elif kind == "flags": diagnostic["after_callbacks"][0]["fd_flags"] = 64
    elif kind == "refusal": diagnostic["controlled_refusals"] = [{"PRIVATE": "SECRET"}]
    elif kind == "challenge": value["challenges"][0]["errno_name"] = "EACCES"
    else: seams.denied["source"] = 1
    value["native_transition"]["diagnostic_sha256"] = hash_payload(diagnostic)
    with pytest.raises(harness.OfflineHarnessRefusal): harness._validate_result(value, seams, HEAD, REMOTE, manifest)


def test_run_once_uses_explicit_fake_hook_and_driver_seams_without_real_operations(monkeypatch):
    handlers = []
    monkeypatch.setattr(harness.sys, "addaudithook", handlers.append)
    monkeypatch.setattr(harness, "_registered_arguments", lambda *args: None)  # Explicit fabricated registration seam.
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    def closed(root, **kwargs):
        assert kwargs == {"runtime_head": HEAD, "actual_remote": REMOTE, "complete_code_manifest": manifest}
        completed_seams(handlers[0].__self__)
        return result(manifest)
    monkeypatch.setattr(harness.proof, "run_registered", closed)
    old_open = os.open; old_capabilities = set(os.supports_dir_fd)
    value = harness.run_once(HEAD, REMOTE, manifest)
    assert value["status"] == "completed" and len(handlers) == 1
    assert handlers[0].__self__.active is False
    assert os.open is old_open and os.supports_dir_fd == old_capabilities
    with pytest.raises(harness.OfflineHarnessRefusal, match="already_invoked"): harness.run_once(HEAD, REMOTE, manifest)


def test_failure_projection_only_after_unwound_hook_deactivation_preserves_original_denial(monkeypatch):
    handlers = []
    monkeypatch.setattr(harness.sys, "addaudithook", handlers.append)
    monkeypatch.setattr(harness, "_registered_arguments", lambda *args: None)
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    def refused(*args, **kwargs): handlers[0].__self__.deny("source")
    def safe_projection(error):
        seams = handlers[0].__self__
        assert seams.active is False
        assert harness._ACTIVE[seams] == (seams, False)
        return {"category": "fixed_test_projection", "contract_code": "harness_source_denied", "errno_name": None}
    monkeypatch.setattr(harness.proof, "run_registered", refused)
    monkeypatch.setattr(harness, "_failure", safe_projection)
    result_value = harness.run_once(HEAD, REMOTE, manifest)
    assert result_value["status"] == "refused"
    assert result_value["seams"]["denied"]["source"] == 1
    assert result_value["seams"]["failure_latched"] is True


def test_memory_denials_restore_original_entries_and_never_read_a_key(seams):
    count = harness.proof.base.previous.count
    original = count.read_named_keychain
    with harness._denied_entries(seams):
        with pytest.raises(harness.OfflineHarnessRefusal, match="credentials_denied"): count.read_named_keychain()
    assert count.read_named_keychain is original and seams.denied["credentials"] == 1


def test_main_invalid_argument_and_unknown_exception_never_echo_values(monkeypatch, capsys):
    assert harness.main(["PRIVATE"]) == 2
    assert "PRIVATE" not in capsys.readouterr().out
    def refused(*args): raise RuntimeError("PRIVATE SECRET PATH")
    monkeypatch.setattr(harness, "run_once", refused)
    assert harness.main([HEAD, REMOTE]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE" not in output and "SECRET" not in output and '"status":"refused"' in output


def test_registered_policy_disclaims_audit_mode_dirfd_and_persistent_storage():
    value = harness.policy()
    assert "mode_and_dir_fd" in value["relative_open_audit_limitation"]
    assert value["maximum_hdiutil_create"] == value["maximum_hdiutil_attach"] == 1
    assert value["maximum_hdiutil_info"] == 12
    assert value["authority"]["source_STARTs"] == value["authority"]["source_bytes"] == 0
    assert value["authority"]["persistent_storage_qualified"] is False


def test_real_bounded_child_audit_hook_handles_one_NOOP_without_nested_id_events():
    # This exercises only the ORIGINAL audit handler on one benign event, not
    # run_once, Git, an image, native calls, source replay or a credential seam.
    # The outer observer's depth cap makes the historical reentrancy finite.
    code = r'''
import json
import sys
from scripts import run_short_interest_isolated_custody_offline as harness
seams = harness.AuditSeams("a" * 40)
assert type(seams).__hash__ is object.__hash__
assert type(seams).__eq__ is object.__eq__
enabled, depth, maximum, nested_ids = True, 0, 0, 0
def observe(event, args):
    global depth, maximum, nested_ids
    if not enabled:
        return
    depth += 1
    maximum = max(maximum, depth)
    if event == "builtins.id":
        nested_ids += 1
    try:
        if depth > 8:
            raise RuntimeError("fixed_bounded_observer_depth")
        seams.handle(event, args)
    finally:
        depth -= 1
sys.addaudithook(observe)
raised = False
try:
    sys.audit("offline.synthetic_no_operation")
except BaseException:
    raised = True
enabled = False
print(json.dumps({"raised": raised, "nested_id_events": nested_ids, "maximum_depth": maximum}))
'''
    completed = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ".:tests", "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"raised": False, "nested_id_events": 0, "maximum_depth": 1}
