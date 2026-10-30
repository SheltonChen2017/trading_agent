"""Fabricated audit events/driver results only; never install a real audit hook."""
from copy import deepcopy
import errno
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
from scripts import run_short_interest_body_receipt_offline as harness

HEAD, REMOTE = "a" * 40, "b" * 40


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(harness, "_INVOKED", False)
    # Explicit fabricated terminal-factory seam: these cases test schema/audit
    # predicates only. Actual original-issued provenance is tested separately.
    monkeypatch.setattr(harness.proof, "validate_closed_result", lambda result: True)
    for name in ("_ORIGINAL", "_COUNTS", "_ACTIVE", "_FAILED", "_POLICY_ISSUED"):
        monkeypatch.setattr(harness, name, {}, raising=False)
    monkeypatch.setattr(harness, "HARNESS_SHA256", hash_payload(harness.policy()))


@pytest.fixture
def seams(): return harness.AuditSeams(HEAD)


def event_command(seams, command, executable=None, cwd=None):
    seams.handle("subprocess.Popen", (command[0] if executable is None else executable,
        command, seams.root if cwd is None else cwd, None))


def result(manifest):
    sample = {"fd_flags": 66, "name_flags": 66, "same_original_inode": True,
        "protections_match": True, "size_and_mtime_unchanged": True, "retained_fd_readonly": True}
    files = [{"role": "body", "name": harness.proof.custody.BODY_NAME, "bytes": 2097152,
        "raw_sha256": harness.proof.BODY_SHA256, "seal_stamp_sha256": "d" * 64},
        {"role": "receipt", "name": harness.proof.custody.RECEIPT_NAME, "bytes": 730,
        "raw_sha256": "f" * 64, "seal_stamp_sha256": "e" * 64}]
    restoration = {"tool_id": 4, "scope": harness.proof.monitor.SCOPE,
        "prior_tool_unused": True, "original_global_mask_zero": True, "original_target_local_masks_zero": True,
        "original_known_callbacks_absent": True, "owned_tool_released": True, "global_mask_restored": True,
        "target_local_masks_restored": True, "known_callback_slots_restored": True, "foreign_ownership_preserved": False}
    diagnostic = {"schema": "si-body-receipt-immutable-monitoring-diagnostic-v1", "observer_complete": True,
        "observer_failure": None, "native_call_count": 2, "distinct_original_inodes": True,
        "first_controlled_refusal": None, "controlled_refusals": [], "policy_sha256": hash_payload(harness.proof.monitor.policy()),
        "authority": harness.proof.monitor.authority(), "backend": harness.proof.monitor.BACKEND,
        "monitoring_context_closed": True, "resource_restoration": restoration,
        "files": [{**{key: row[key] for key in ("role", "name", "bytes", "raw_sha256")},
            "native_call_count": 1, "native_result": 0, "native_errno_name": None,
            "before_native": dict(sample, fd_flags=64, name_flags=64), "immediate_after_native": dict(sample),
            "after_callbacks": [dict(sample)], "classification": "required_flags_observed_without_recorded_loss"} for row in files]}
    return {"schema": "si-body-receipt-custody-proof-closed-v2", "status": "closed_offline_synthetic_maximum_body_receipt_only",
        "runtime_head": HEAD, "actual_remote": REMOTE, "code_identity_sha256": "e" * 64,
        "code_manifest_sha256": hash_payload(manifest), "protocol_sha256": harness.proof.PROTOCOL_SHA256,
        "started_at": "2026-10-27T07:00:00Z", "closed_at": "2026-10-27T07:00:10Z", "binding_sha256": "a" * 64,
        "files": files, "helper_closed_summary_sha256": "c" * 64, "isolated_storage_closed_summary_sha256": "9" * 64,
        "native_transition": {"diagnostic": diagnostic, "diagnostic_sha256": hash_payload(diagnostic)},
        "challenges": [{"role": row["role"], "name": row["name"], "challenges": [
            {"challenge": name, "result": "denied", "errno_name": "EPERM"}
            for name in ("write_open", "same_mode_fchmod", "fixed_fsetxattr")]} for row in files],
        "original_code_and_pair_contexts_closed": True, "authority": harness.proof.authority()}


def completed_seams(seams):
    state = {"image": seams.namespace / harness.proof.storage.IMAGE_NAME, "mount": seams.mount}
    for verb in ("create", "attach"): event_command(seams, harness.proof.storage._arguments(state, verb))
    for name in (harness.proof.custody.BODY_NAME, harness.proof.custody.RECEIPT_NAME):
        seams.handle("open", (name, None, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW))
        seams.handle("open", (name, None, os.O_WRONLY | os.O_NOFOLLOW))
    seams.handle("open", (".", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))


def test_fixed_creator_RDWR_and_real_WRONLY_challenge_with_implicit_cloexec(seams):
    original_open, capabilities = os.open, set(os.supports_dir_fd)
    extra = getattr(os, "O_CLOEXEC", 0)
    seams.handle("open", (harness.proof.custody.BODY_NAME, None, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | extra))
    seams.handle("open", (harness.proof.custody.BODY_NAME, None, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | extra))
    seams.handle("open", (harness.proof.custody.BODY_NAME, None, os.O_WRONLY | os.O_NOFOLLOW | extra))
    seams.handle("open", ("/dev/null", None, os.O_RDWR | extra))
    assert seams.permitted["body_create"] == seams.permitted["body_write_challenge"] == 1
    assert seams.permitted["null_stream"] == 1 and not seams.failed
    assert os.open is original_open and os.supports_dir_fd == capabilities


@pytest.mark.parametrize("extra", [0, getattr(os, "O_CLOEXEC", 0)])
def test_exact_original_directory_stream_flags_are_counted_without_read_authority(seams, extra):
    seams.handle("open", (".", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | extra))
    assert seams.summary()["permitted"]["directory_stream"] == 1
    assert all(value == 0 for value in seams.denied.values())


@pytest.mark.parametrize("path,mode,flags", [
    (".", None, os.O_RDONLY), (".", None, os.O_RDONLY | os.O_DIRECTORY),
    (".", None, os.O_RDONLY | os.O_NOFOLLOW),
    (".", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK),
    (".", None, os.O_RDWR | os.O_DIRECTORY | os.O_NOFOLLOW),
    (".", None, os.O_WRONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    (".", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_TRUNC),
    (".", "r", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    ("./", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    ("..", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    ("./old-source.raw", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    ("old-source.raw", None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    (Path("."), None, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)])
def test_dot_stream_exception_does_not_admit_alias_flags_files_or_writers(seams, path, mode, flags):
    with pytest.raises(harness.OfflineHarnessRefusal): seams.handle("open", (path, mode, flags))
    assert seams.summary()["failure_latched"] is True


def test_directory_stream_counter_has_a_finite_nonresettable_quota(seams):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    for unused in range(harness.MAXIMUM_DIRECTORY_STREAMS): seams.handle("open", (".", None, flags))
    assert seams.summary()["permitted"]["directory_stream"] == 4096
    with pytest.raises(harness.OfflineHarnessRefusal, match="read_open_denied"):
        seams.handle("open", (".", None, flags))
    assert seams.summary()["permitted"]["directory_stream"] == 4096
    assert seams.summary()["denied"]["read_open"] == 1 and seams.summary()["failure_latched"] is True


@pytest.mark.parametrize("change", ["counter", "dictionary"])
def test_directory_stream_counter_reset_or_dictionary_copy_cannot_authorize_an_open(seams, change):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    seams.handle("open", (".", None, flags))
    if change == "counter": seams.permitted["directory_stream"] = 0
    else: seams.permitted = dict(seams.permitted)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (".", None, flags))
    assert seams.summary()["permitted"]["directory_stream"] == 1
    assert seams.summary()["failure_latched"] is True


def test_directory_stream_policy_declares_exact_original_flags_and_finite_counter():
    value = harness.policy()
    assert value["maximum_directory_streams"] == 4096
    assert value["inventory_directory_stream"] == (
        "literal_dot_mode_None_exact_RDONLY_DIRECTORY_NOFOLLOW_only_implicit_CLOEXEC_removed_original_FD_owner_mode_stamp_checks_unchanged")


def test_fresh_child_original_inventory_uses_real_hook_then_denies_unrelated_read():
    # Only a new empty temporary OwnedOutput is prepared before the hook.
    # This child never invokes a capture, image, setter, proof or credential.
    code = r'''
import json
import os
from pathlib import Path
import sys
import tempfile
from scripts import run_short_interest_body_receipt_offline as harness
cache = harness.proof.base.previous.count.old.cache
OwnedOutput = harness.proof.base.previous.prior._OwnedOutput
with tempfile.TemporaryDirectory(prefix="si-inventory-hook-unit-") as parent:
    target = Path(parent).resolve() / "owned"
    target.mkdir(mode=0o700)
    owned = OwnedOutput(target, lambda: None)
    harness.HARNESS_SHA256 = harness.hash_payload(harness.policy())
    seams = harness.AuditSeams("a" * 40)
    sys.addaudithook(seams.handle)
    try:
        names = cache._inventory_names(owned._anchor[2], boundary=owned.check)
        assert names == ()
        denied = False
        try:
            fd = os.open("old-source.raw", os.O_RDONLY)
        except harness.OfflineHarnessRefusal:
            denied = True
        else:
            os.close(fd)
        summary = seams.summary()
    finally:
        harness._deactivate(seams)
        owned.close()
    print(json.dumps({"empty_original_inventory": names == (), "unrelated_read_denied": denied,
        "directory_stream": summary["permitted"]["directory_stream"],
        "denied_read_open": summary["denied"]["read_open"], "failure_latched": summary["failure_latched"],
        "other_denials": sum(value for name, value in summary["denied"].items() if name != "read_open"),
        "body_create": summary["permitted"]["body_create"], "receipt_create": summary["permitted"]["receipt_create"]}))
'''
    completed = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ".:tests", "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"empty_original_inventory": True, "unrelated_read_denied": True,
        "directory_stream": 1, "denied_read_open": 1, "failure_latched": True, "other_denials": 0,
        "body_create": 0, "receipt_create": 0}


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
    seams.handle("open", (harness.proof.custody.BODY_NAME, None, flags))
    with pytest.raises(harness.OfflineHarnessRefusal): seams.handle("open", (harness.proof.custody.BODY_NAME, None, flags))
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (str(seams.parent / "old-spent-source" / "row.raw"), "r", os.O_RDONLY))
    fresh = harness.AuditSeams(HEAD)
    with pytest.raises(harness.OfflineHarnessRefusal, match="read_open_denied"):
        fresh.handle("open", (str(fresh.parent / "old-spent-source" / "row.raw"), "r", os.O_RDONLY))


def test_exact_new_artifact_and_committed_code_read_names_only(seams):
    for name in (str(seams.parent), str(seams.namespace), str(seams.probe), harness.proof.custody.BODY_NAME,
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
        seams.handle("open", (harness.proof.custody.BODY_NAME, None, os.O_RDONLY))
    seams.permitted = original; seams.failed = False
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("open", (harness.proof.custody.BODY_NAME, None, os.O_RDONLY))
    assert seams.summary()["permitted"]["body_create"] == 0 and seams.summary()["failure_latched"] is True


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
    for unused in range(harness.MAXIMUM_INFO_COMMANDS): event_command(seams, harness.proof.storage._arguments(state, "info"))
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


@pytest.mark.parametrize("kind", ["extra", "authority", "observer", "native_count", "flags", "refusal", "challenge", "counter", "resource", "backend"])
def test_completed_shape_or_summary_never_bypasses_real_closure_contract(seams, kind):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    value = result(manifest); completed_seams(seams)
    diagnostic = value["native_transition"]["diagnostic"]
    if kind == "extra": value["PRIVATE"] = "SECRET"
    elif kind == "authority": value["authority"]["source_admitted"] = True
    elif kind == "observer": diagnostic["observer_complete"] = False
    elif kind == "native_count": diagnostic["native_call_count"] = True
    elif kind == "flags": diagnostic["files"][0]["after_callbacks"][0]["fd_flags"] = 64
    elif kind == "refusal": diagnostic["controlled_refusals"] = [{"PRIVATE": "SECRET"}]
    elif kind == "challenge": value["challenges"][0]["errno_name"] = "EACCES"
    elif kind == "resource": diagnostic["resource_restoration"]["owned_tool_released"] = False
    elif kind == "backend": diagnostic["schema"] = "si-immutable-transition-diagnostic-v1"
    else: seams.denied["source"] = 1
    value["native_transition"]["diagnostic_sha256"] = hash_payload(diagnostic)
    with pytest.raises(harness.OfflineHarnessRefusal): harness._validate_result(value, seams, HEAD, REMOTE, manifest)


def test_exact_body_and_receipt_have_separate_nonresettable_create_challenge_quotas(seams):
    for name in (harness.proof.custody.BODY_NAME, harness.proof.custody.RECEIPT_NAME):
        seams.handle("open", (name, None, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW))
        seams.handle("open", (name, None, os.O_WRONLY | os.O_NOFOLLOW))
    assert all(seams.permitted[key] == 1 for key in ("body_create", "body_write_challenge",
        "receipt_create", "receipt_write_challenge"))
    with pytest.raises(harness.OfflineHarnessRefusal, match="write_open_denied"):
        seams.handle("open", (harness.proof.custody.RECEIPT_NAME, None, os.O_WRONLY | os.O_NOFOLLOW))


def test_receipt_create_cannot_precede_original_body_create(seams):
    with pytest.raises(harness.OfflineHarnessRefusal, match="write_open_denied"):
        seams.handle("open", (harness.proof.custody.RECEIPT_NAME, None,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW))
    assert seams.summary()["permitted"]["receipt_create"] == 0


@pytest.mark.parametrize("kind", ["duplicate_role", "wrong_size", "second_native_missing", "inodes", "cleanup"])
def test_two_total_calls_do_not_replace_exact_two_original_roles_and_cleanup(seams, kind):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    completed_seams(seams); value = result(manifest)
    diagnostic = value["native_transition"]["diagnostic"]
    if kind == "duplicate_role": diagnostic["files"][1]["role"] = "body"
    elif kind == "wrong_size": diagnostic["files"][0]["bytes"] = True
    elif kind == "second_native_missing": diagnostic["files"][1]["native_call_count"] = 0
    elif kind == "inodes": diagnostic["distinct_original_inodes"] = False
    else: diagnostic["resource_restoration"]["owned_tool_released"] = False
    value["native_transition"]["diagnostic_sha256"] = hash_payload(diagnostic)
    with pytest.raises(harness.OfflineHarnessRefusal, match="result_refused"):
        harness._validate_result(value, seams, HEAD, REMOTE, manifest)


def test_matching_schema_hashes_do_not_bypass_original_factory_validator(seams, monkeypatch):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    completed_seams(seams)
    def refuse(value): raise harness.proof.BodyReceiptProofRefusal("REFUSED: body_receipt_proof_not_original_closed")
    monkeypatch.setattr(harness.proof, "validate_closed_result", refuse)
    with pytest.raises(harness.proof.BodyReceiptProofRefusal):
        harness._validate_result(result(manifest), seams, HEAD, REMOTE, manifest)


def test_hot_complete_policy_never_rebuilds_or_hashes_two_megabyte_body(seams, monkeypatch):
    def refuse(): raise AssertionError("hot body generation is forbidden")
    monkeypatch.setattr(harness.proof, "synthetic_body", refuse)
    seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is False


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


@pytest.mark.parametrize("number,name", [(errno.ENOSPC, "ENOSPC"), (errno.EIO, "EIO")])
def test_run_once_preserves_allowlisted_os_errno_without_exception_values(monkeypatch, number, name):
    handlers = []
    monkeypatch.setattr(harness.sys, "addaudithook", handlers.append)
    monkeypatch.setattr(harness, "_registered_arguments", lambda *args: None)
    monkeypatch.setattr(harness.proof, "_LAST_TRANSITION", None)
    monkeypatch.setattr(harness.proof.storage, "association_diagnostic", lambda: {"status": "not_observed"})
    def refused(*args, **kwargs): raise OSError(number, "PRIVATE MESSAGE SECRET", "/PRIVATE/FILENAME")
    monkeypatch.setattr(harness.proof, "run_registered", refused)
    value = harness.run_once(HEAD, REMOTE, {path: "f" * 64 for path in harness.proof.code_paths()})
    assert value["status"] == "refused" and handlers[0].__self__.active is False
    assert value["failure"]["category"] == "local_os_error" and value["failure"]["errno_name"] == name
    assert "PRIVATE" not in json.dumps(value) and "SECRET" not in json.dumps(value)


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


def test_own_harness_refusal_retains_original_safe_storage_projection(monkeypatch):
    observation = {"status": "original_association_observed", "mismatching_fields": ["volume-kind"]}
    monkeypatch.setattr(harness.proof.storage, "association_diagnostic", lambda: dict(observation), raising=False)
    result_value = harness._failure(harness.OfflineHarnessRefusal("REFUSED: harness_native_denied"))
    assert result_value["storage_association"] == observation
    assert result_value["contract_code"] == "harness_native_denied"


def test_registered_policy_disclaims_audit_mode_dirfd_and_persistent_storage():
    value = harness.policy()
    assert "mode_and_dir_fd" in value["relative_open_audit_limitation"]
    assert value["maximum_hdiutil_create"] == value["maximum_hdiutil_attach"] == 1
    assert value["maximum_hdiutil_info"] == 16
    assert value["authority"]["source_STARTs"] == value["authority"]["source_bytes"] == 0
    assert value["authority"]["persistent_storage_qualified"] is False


def test_real_bounded_child_audit_hook_handles_one_NOOP_without_nested_id_events():
    # This exercises only the ORIGINAL audit handler on one benign event, not
    # run_once, Git, an image, native calls, source replay or a credential seam.
    # The outer observer's depth cap makes the historical reentrancy finite.
    code = r'''
import json
import sys
from scripts import run_short_interest_body_receipt_offline as harness
# Explicit fabricated registration only; this child never enters run_once.
harness.HARNESS_SHA256 = harness.hash_payload(harness.policy())
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


def test_complete_current_policy_is_evaluated_every_check_without_hot_canonical_hash(seams, monkeypatch):
    original_policy, original_hash = harness.policy, harness.hash_payload
    evaluations, hashes = [], []
    def current_policy():
        evaluations.append(True)
        return original_policy()
    def counted_hash(value):
        hashes.append(True)
        return original_hash(value)
    monkeypatch.setattr(harness, "policy", current_policy)
    monkeypatch.setattr(harness, "hash_payload", counted_hash)
    for unused in range(7): seams.handle("offline.synthetic_no_operation", ())
    assert len(evaluations) == 7 and hashes == []


def test_original_same_policy_value_is_canonically_registered_before_hook(monkeypatch):
    monkeypatch.setattr(harness, "HARNESS_SHA256", "0" * 64)
    with pytest.raises(harness.OfflineHarnessRefusal, match="registration_changed"):
        harness.AuditSeams(HEAD)


@pytest.mark.parametrize("kind", ["dict_subclass", "list_subclass", "str_subclass", "int_subclass", "key_subclass", "tuple", "bool_int"])
def test_strict_current_policy_shapes_refuse_normalization_aliases(seams, monkeypatch, kind):
    value = deepcopy(harness.policy())
    if kind == "dict_subclass": value = type("OtherDict", (dict,), {})(value)
    elif kind == "list_subclass": value["code_paths"] = type("OtherList", (list,), {})(value["code_paths"])
    elif kind == "str_subclass": value["schema"] = type("OtherStr", (str,), {})(value["schema"])
    elif kind == "int_subclass": value["maximum_hdiutil_create"] = type("OtherInt", (int,), {})(1)
    elif kind == "key_subclass": value = {(type("OtherStr", (str,), {})(key) if key == "schema" else key): item
        for key, item in value.items()}
    elif kind == "tuple": value["code_paths"] = tuple(value["code_paths"])
    else: value["maximum_hdiutil_create"] = True
    monkeypatch.setattr(harness, "policy", lambda: value)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is True


def test_equal_fresh_policy_and_dict_order_are_allowed_but_all_leaf_changes_refuse():
    original = harness.policy()
    frozen = harness._freeze_policy(original)
    reordered = dict(reversed(list(deepcopy(original).items())))
    assert harness._matches_policy(frozen, reordered)
    def leaves(value, path=()):
        if type(value) is dict:
            for key, item in value.items(): yield from leaves(item, (*path, key))
        elif type(value) is list:
            for index, item in enumerate(value): yield from leaves(item, (*path, index))
        else: yield path, value
    original_hash = hash_payload(original)
    for path, item in leaves(original):
        value = deepcopy(original)
        parent = value
        for part in path[:-1]: parent = parent[part]
        parent[path[-1]] = (not item if type(item) is bool else item + 1
            if type(item) is int else item + " changed" if type(item) is str else "changed")
        assert hash_payload(value) != original_hash
        assert not harness._matches_policy(frozen, value)


@pytest.mark.parametrize("kind", ["extra", "missing", "path_order", "authority", "cycle", "nan", "inf", "unknown"])
def test_complete_current_policy_structural_changes_are_fixed_permanent_refusals(seams, monkeypatch, kind):
    value = deepcopy(harness.policy())
    if kind == "extra": value["unexpected"] = False
    elif kind == "missing": del value["branch"]
    elif kind == "path_order": value["code_paths"].reverse()
    elif kind == "authority": value["authority"]["source_admitted"] = True
    elif kind == "cycle": value["code_paths"][0] = value
    elif kind == "nan": value["maximum_hdiutil_create"] = float("nan")
    elif kind == "inf": value["maximum_hdiutil_create"] = float("inf")
    else:
        class Unknown:
            def __str__(self): raise AssertionError("unknown value was formatted")
            def __eq__(self, other): raise AssertionError("unknown value was compared")
        value["schema"] = Unknown()
    monkeypatch.setattr(harness, "policy", lambda: value)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is True


@pytest.mark.parametrize("kind", ["equal_copy", "nonce", "tree", "hash"])
def test_policy_witness_cannot_be_forged_or_replaced_by_equal_values(seams, kind):
    original = harness._POLICY_ISSUED[seams]
    replacement = list(original)
    if kind == "nonce": replacement[2] = object()
    elif kind == "tree": replacement[3] = harness._freeze_policy(harness.policy())
    elif kind == "hash": replacement[4] = "0" * 64
    harness._POLICY_ISSUED[seams] = tuple(replacement)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    harness._POLICY_ISSUED[seams] = original
    seams.failed = False
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is True


def test_positive_terminal_recomputes_original_policy_canonical_hash(seams, monkeypatch):
    manifest = {name: "f" * 64 for name in harness.proof.code_paths()}
    completed_seams(seams)
    value = result(manifest)
    original_hash = harness.hash_payload
    schema = harness.policy()["schema"]
    def changed_digest(payload):
        if type(payload) is dict and payload.get("schema") == schema: return "0" * 64
        return original_hash(payload)
    monkeypatch.setattr(harness, "hash_payload", changed_digest)
    seams.handle("offline.synthetic_no_operation", ())  # Full current values still match.
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        harness._validate_result(value, seams, HEAD, REMOTE, manifest)
    assert seams.summary()["failure_latched"] is True


def test_issued_tree_is_immutable_and_primitive_types_are_exact():
    value = {"none": None, "bool": False, "int": 0, "str": "", "list": [1, True]}
    frozen = harness._freeze_policy(value)
    def immutable_only(item):
        assert type(item) in (tuple, str, int, bool, type(None))
        if type(item) is tuple:
            for child in item: immutable_only(child)
    immutable_only(frozen)
    assert harness._matches_policy(frozen, deepcopy(value))
    for key, replacement in (("none", False), ("bool", 0), ("int", False), ("str", [])):
        changed = deepcopy(value); changed[key] = replacement
        assert not harness._matches_policy(frozen, changed)


def test_unknown_mint_value_or_cycle_refuses_without_formatting_or_equality():
    class HostileMeta(type):
        def __eq__(self, other): raise AssertionError("unknown metaclass was compared")
    class Unknown(metaclass=HostileMeta):
        def __str__(self): raise AssertionError("unknown value was formatted")
        def __eq__(self, other): raise AssertionError("unknown value was compared")
    cycle = []; cycle.append(cycle)
    for value in (Unknown(), cycle, float("nan"), float("inf")):
        with pytest.raises(harness.OfflineHarnessRefusal, match="registration_changed"):
            harness._freeze_policy(value)


def test_policy_construction_exception_permanently_latches_even_after_restoration(seams, monkeypatch):
    original = harness.policy
    def refused(): raise RuntimeError("PRIVATE_EXCEPTION_PATH")
    monkeypatch.setattr(harness, "policy", refused)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    monkeypatch.setattr(harness, "policy", original)
    seams.failed = False
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is True


def test_original_mutable_construction_value_does_not_change_issued_tree(monkeypatch):
    original = harness.policy()
    mutable = deepcopy(original)
    monkeypatch.setattr(harness, "policy", lambda: mutable)
    seams = harness.AuditSeams(HEAD)
    witness = harness._POLICY_ISSUED[seams]
    mutable["code_paths"].reverse()
    assert harness._matches_policy(witness[3], deepcopy(original))
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert seams.summary()["failure_latched"] is True


def test_unissued_hostile_tree_is_rejected_before_any_tag_comparison(seams):
    called = []
    class HostileTag:
        def __eq__(self, other):
            called.append(True)
            raise AssertionError("unissued policy tag was compared")
    original = harness._POLICY_ISSUED[seams]
    replacement = list(original)
    replacement[3] = HostileTag(), None
    harness._POLICY_ISSUED[seams] = tuple(replacement)
    with pytest.raises(harness.OfflineHarnessRefusal, match="counter_failed"):
        seams.handle("offline.synthetic_no_operation", ())
    assert called == []
    assert seams.summary()["failure_latched"] is True
