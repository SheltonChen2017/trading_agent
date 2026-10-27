"""ONE offline synthetic custody invocation with fixed, counted external seams.

The audit event cannot independently see open's mode or dir_fd. Exact original
creator/OwnedOutput checks and the committed 64-file composition bind those;
this harness does not replace os.open, its capability set, or a native call.
"""
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import re
import socket
import sys

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_isolated_immutable_metadata as proof

DRIVER = "scripts/run_short_interest_isolated_custody_offline.py"
HARNESS_SHA256 = "48536fb87e405e6a1c43edd07b6e37dee336559122b1e31e1ca73c94cc0b6fae"
MAXIMUM_GIT_COMMANDS, MAXIMUM_INFO_COMMANDS = 20000, 12
_INVOKED = False
_ORIGINAL, _COUNTS, _ACTIVE, _FAILED = {}, {}, {}, {}
_CODES = frozenset("""harness_registration_changed harness_arguments_refused harness_manifest_refused
harness_already_invoked harness_network_denied harness_credentials_denied harness_source_denied
harness_subprocess_denied harness_write_open_denied harness_read_open_denied harness_mutation_denied
harness_native_denied harness_other_denied harness_counter_failed harness_result_refused
harness_root_changed""".split())
DENIED = ("network", "credentials", "source", "subprocess", "write_open", "read_open",
          "mutation", "native", "other")


class OfflineHarnessRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise OfflineHarnessRefusal("REFUSED: " + code)


def policy():
    require((MAXIMUM_GIT_COMMANDS, MAXIMUM_INFO_COMMANDS) == (20000, 12),
        "harness_registration_changed")
    return {"schema": "si-isolated-custody-offline-harness-v2", "driver": DRIVER,
        "root": str(proof.base.previous.lane.ROOT), "branch": "codex/strategy-short-interest",
        "ref": "refs/heads/codex/strategy-short-interest", "code_paths": list(proof.code_paths()),
        "proof_protocol_sha256": proof.PROTOCOL_SHA256,
        "allowed_subprocesses": "exact_lane_Git_and_frozen_new_hdiutil_create_attach_info_only",
        "maximum_Git_commands": MAXIMUM_GIT_COMMANDS, "maximum_hdiutil_info": MAXIMUM_INFO_COMMANDS,
        "maximum_hdiutil_create": 1, "maximum_hdiutil_attach": 1,
        "Python_write_open": "one_original_O_EXCL0600_186byte_inode_and_its_real_WRONLY_challenge",
        "relative_open_audit_limitation": "mode_and_dir_fd_enforced_by_unchanged_original_authenticated_creator",
        "null_stream": "exact_dev_null_RDWR_for_hdiutil_stdin_stderr_only_not_evidence",
        "native_library": proof.base.immutable.LIBRARY,
        "native_symbols": ["fstatfs64", "fchflags", "fsetxattr"],
        "source_replay_credentials_network_publication": "denied_counted_permanent_failure",
        "artifact_file_opens": "new_fixed_namespace_exact_parent_directory_exact64code_files_basenames_and_their_readonly_parent_directories",
        "metadata_audit_limit": "stat_and_directory_metadata_not_independently_sandboxed_original_authenticated_code_and_FD_checks_remain",
        "audit_state": "original_identity_counter_tuples_and_permanent_failure_latch_no_public_reset_or_active_toggle",
        "registry_keys": "original_objects_retained_with_default_object_identity_hash_no_audited_builtin_id",
        "refusal_projection": "after_failed_driver_contexts_unwind_deactivate_hook_only_preserve_all_denials_then_fixed_projection",
        "destructive_operations": "denied_no_cleanup_detach_unlock_or_adoption",
        "denied_counter_names": list(DENIED), "authority": proof.authority()}


class AuditSeams:
    """Directly testable policy handler; constructing it installs no real hook."""
    __slots__ = ("root", "head", "namespace", "parent", "mount", "target", "probe", "code",
        "code_parents", "code_basenames", "denied", "permitted", "failed", "active",
        "last_hdiutil", "_identity")
    def __init__(self, runtime_head):
        require(type(self) is AuditSeams and AuditSeams.__hash__ is object.__hash__
            and AuditSeams.__eq__ is object.__eq__, "harness_counter_failed")
        self.root = proof.base.previous.lane.ROOT
        self.head = runtime_head
        self.namespace = self.root / proof.storage.PARENT / proof.storage.NAMESPACE
        self.parent = self.root / proof.storage.PARENT
        self.mount = self.namespace / proof.storage.MOUNT_NAME
        self.target = self.mount / proof.INNER_DIRECTORY
        self.probe = self.target / proof.NAME
        self.code = frozenset(str(self.root / name) for name in proof.code_paths())
        self.code_parents = frozenset(str((self.root / name).parent) for name in proof.code_paths())
        self.code_basenames = frozenset(Path(name).name for name in proof.code_paths())
        self.denied = {name: 0 for name in DENIED}
        self.permitted = {"Git": 0, "create": 0, "attach": 0, "info": 0,
            "probe_create": 0, "probe_write_challenge": 0, "null_stream": 0}
        self.failed, self.active, self.last_hdiutil = False, True, "none"
        self._identity = object()
        bindings = tuple(getattr(self, name) for name in (
            "root", "head", "namespace", "parent", "mount", "target", "probe", "code",
            "code_parents", "code_basenames"))
        _ORIGINAL[self] = (self, self._identity, (bindings, hash_payload(policy())),
            self.denied, self.permitted, tuple(self.denied), tuple(self.permitted))
        _COUNTS[self] = self, tuple(self.denied.values()), tuple(self.permitted.values()), "none"
        _ACTIVE[self] = self, True

    def _check(self, *, allow_failed=False):
        require(type(self) is AuditSeams and AuditSeams.__hash__ is object.__hash__
            and AuditSeams.__eq__ is object.__eq__, "harness_counter_failed")
        entry, counts, active = _ORIGINAL.get(self), _COUNTS.get(self), _ACTIVE.get(self)
        bindings = tuple(getattr(self, name) for name in (
            "root", "head", "namespace", "parent", "mount", "target", "probe", "code",
            "code_parents", "code_basenames"))
        good = (type(self) is AuditSeams and type(entry) is tuple and len(entry) == 7
            and entry[0] is self and entry[1] is self._identity and entry[2] == (bindings, hash_payload(policy()))
            and self.denied is entry[3] and self.permitted is entry[4]
            and type(counts) is tuple and len(counts) == 4 and counts[0] is self
            and set(self.denied) == set(entry[5]) and set(self.permitted) == set(entry[6])
            and tuple(self.denied[name] for name in entry[5]) == counts[1]
            and tuple(self.permitted[name] for name in entry[6]) == counts[2]
            and self.last_hdiutil == counts[3]
            and type(active) is tuple and active[0] is self and type(self.active) is bool
            and self.active is active[1] and type(self.failed) is bool
            and self.failed is (_FAILED.get(self) is self))
        if not good:
            _FAILED[self] = self; self.failed = True
            raise OfflineHarnessRefusal("REFUSED: harness_counter_failed")
        require(allow_failed or _FAILED.get(self) is not self, "harness_counter_failed")
        return entry, counts

    def _allow(self, name, *, verb=None):
        entry, counts = self._check()
        values = list(counts[2]); index = entry[6].index(name); values[index] += 1
        self.permitted[name] = values[index]
        if verb is not None: self.last_hdiutil = verb
        _COUNTS[self] = self, counts[1], tuple(values), self.last_hdiutil

    def deny(self, category):
        entry, counts = self._check(allow_failed=True)
        if category not in entry[5]: category = "other"
        values = list(counts[1]); index = entry[5].index(category); values[index] += 1
        self.denied[category] = values[index]; self.failed = True; _FAILED[self] = self
        _COUNTS[self] = self, tuple(values), counts[2], counts[3]
        raise OfflineHarnessRefusal("REFUSED: harness_" + category + "_denied")

    @staticmethod
    def _path(value):
        if type(value) is str: return value
        if isinstance(value, Path): return str(value)
        return None

    def _artifact_read(self, name, flags):
        if name in self.code or name == str(self.parent) or name == "/dev/null": return True
        if name in self.code_parents and flags & os.O_DIRECTORY: return True
        if name in self.code_basenames: return True
        if name == str(self.namespace) or name.startswith(str(self.namespace) + "/"):
            return ".." not in Path(name).parts
        return name in {proof.NAME, proof.INNER_DIRECTORY, proof.storage.NAMESPACE,
            proof.storage.IMAGE_NAME, proof.storage.MOUNT_NAME}

    def _open(self, args):
        if type(args) is not tuple or len(args) != 3: self.deny("other")
        path, unused_mode, flags = args
        if type(flags) is not int: self.deny("other")
        flags &= ~getattr(os, "O_CLOEXEC", 0)  # CPython's implicit PEP446 flag only.
        if type(path) is int:
            if flags & os.O_ACCMODE != os.O_RDONLY: self.deny("write_open")
            return  # Original subprocess PIPE readers; no artifact FD is supplied by a caller.
        name = self._path(path)
        if name is None: self.deny("read_open")
        writing = flags & os.O_ACCMODE != os.O_RDONLY or flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if not writing:
            if not self._artifact_read(name, flags): self.deny("read_open")
            return
        if name == "/dev/null" and flags & os.O_ACCMODE == os.O_RDWR and not flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            self._allow("null_stream"); return
        if name != proof.NAME: self.deny("write_open")
        create = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        challenge = os.O_WRONLY | os.O_NOFOLLOW
        if flags == create and self.permitted["probe_create"] == 0:
            self._allow("probe_create"); return
        if flags == challenge and self.permitted["probe_create"] == 1 and self.permitted["probe_write_challenge"] == 0:
            self._allow("probe_write_challenge"); return
        self.deny("write_open")

    def _subprocess(self, args):
        if type(args) is not tuple or len(args) != 4: self.deny("subprocess")
        executable, command, cwd, unused_environment = args
        if (type(command) not in (list, tuple) or not all(type(item) is str for item in command)
                or self._path(cwd) != str(self.root)): self.deny("subprocess")
        command = list(command)
        if executable == "git" and command and command[0] == "git":
            simple = (["git", "rev-parse", "--show-toplevel"],
                ["git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"],
                ["git", "ls-remote", "--exit-code", "origin", "refs/heads/codex/strategy-short-interest"],
                ["git", "check-ignore", str(self.target)])
            show = len(command) == 3 and command[:2] == ["git", "show"]
            show = show and command[2] in {self.head + ":" + name for name in proof.code_paths()}
            if command not in simple and not show: self.deny("subprocess")
            if self.permitted["Git"] >= MAXIMUM_GIT_COMMANDS: self.deny("subprocess")
            self._allow("Git")
            return
        if executable == proof.storage.HDIUTIL:
            state = {"image": self.namespace / proof.storage.IMAGE_NAME, "mount": self.mount}
            verb = next((verb for verb in ("create", "attach", "info")
                if command == proof.storage._arguments(state, verb)), None)
            if verb is None: self.deny("subprocess")
            maximum = MAXIMUM_INFO_COMMANDS if verb == "info" else 1
            if self.permitted[verb] >= maximum: self.deny("subprocess")
            if verb == "attach" and self.permitted["create"] != 1: self.deny("subprocess")
            self._allow(verb, verb=verb); return
        self.deny("subprocess")

    def _chmod(self, args):
        if type(args) is not tuple or len(args) != 3: self.deny("mutation")
        value, mode, unused_dirfd = args
        if type(value) is not int or mode not in (0o600, 0o700): self.deny("mutation")
        original = os.fstat(value)
        names = (self.namespace, self.mount) if mode == 0o700 else (
            self.namespace / proof.storage.IMAGE_NAME, self.probe)
        for path in names:
            try: named = path.lstat()
            except FileNotFoundError: continue
            if (named.st_dev, named.st_ino) == (original.st_dev, original.st_ino): return
        self.deny("mutation")

    def handle(self, event, args):
        active = _ACTIVE.get(self)
        if type(active) is tuple and active[0] is self and active[1] is False:
            if self.active is False: return  # Only trusted run_once finally sets this original record.
        self._check()
        if event == "open": return self._open(args)
        if event == "subprocess.Popen": return self._subprocess(args)
        if event.startswith("socket."): self.deny("network")
        if event == "ctypes.dlopen":
            if args != (proof.base.immutable.LIBRARY,): self.deny("native")
        elif event == "ctypes.dlsym":
            if len(args) != 2 or args[1] not in {"fstatfs64", "fchflags", "fsetxattr"}: self.deny("native")
            try: name = object.__getattribute__(args[0], "_name")
            except (AttributeError, TypeError): self.deny("native")
            if name != proof.base.immutable.LIBRARY: self.deny("native")
        elif event.startswith("ctypes.dlsym/"): self.deny("native")
        elif event == "os.mkdir":
            if len(args) != 3 or args[1] != 0o700: self.deny("mutation")
            name = self._path(args[0])
            if name not in {proof.storage.NAMESPACE, proof.storage.MOUNT_NAME,
                    str(self.namespace), str(self.mount), str(self.target)}: self.deny("mutation")
        elif event == "os.chmod": return self._chmod(args)
        elif event in {"os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.truncate",
                "os.chflags", "os.lchflags", "os.chown", "os.lchown", "os.setxattr", "os.removexattr",
                "os.utime", "os.chdir", "os.fchdir", "os.chroot", "os.mknod", "os.mkfifo",
                "os.system", "os.posix_spawn", "os.exec", "os.fork", "os.forkpty"}: self.deny("mutation")

    def summary(self):
        try: self._check(allow_failed=True)
        except OfflineHarnessRefusal: pass  # Project ORIGINAL retained counts even after public tampering.
        entry, counts = _ORIGINAL[self], _COUNTS[self]
        return {"denied": dict(zip(entry[5], counts[1])), "permitted": dict(zip(entry[6], counts[2])),
            "failure_latched": _FAILED.get(self) is self, "last_permitted_hdiutil_verb": counts[3]}


def _deactivate(seams):
    """Trusted terminal cleanup only; never clear a denial or reset its counters."""
    try: seams._check(allow_failed=True)
    except OfflineHarnessRefusal: pass
    _ACTIVE[seams] = seams, False
    seams.active = False


@contextmanager
def _denied_entries(seams):
    changes = []
    def replace(owner, name, category):
        if not hasattr(owner, name): return
        original = getattr(owner, name)
        def refused(*args, **kwargs): seams.deny(category)
        changes.append((owner, name, original)); setattr(owner, name, refused)
    count = proof.base.previous.count
    cache = count.old.cache
    for owner, names, category in (
        (count, ("run_registered", "capture_chunk"), "source"),
        (count.old, ("run_registered",), "source"),
        (proof.base, ("run_registered",), "source"),
        (proof.base.previous, ("run_registered",), "source"),
        (proof.base.previous.prior, ("run_registered",), "source"),
        (cache, ("load_registered_cache", "write_cache", "capture_counts"), "source"),
        (cache.source_preflight, ("preflight",), "source"),
        (count, ("read_named_keychain",), "credentials"),
        (count.old, ("read_named_keychain",), "credentials"),
        (count.transport, ("http",), "network"),
        (proof.base.previous.prior._OwnedOutput, ("publish",), "source"),
        (socket, ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"), "network")):
        for name in names: replace(owner, name, category)
    key_module = sys.modules.get("scripts.short_interest_keychain")
    if key_module is not None: replace(key_module, "read_named_keychain", "credentials")
    try: yield
    finally:
        for owner, name, original in reversed(changes): setattr(owner, name, original)


def _registered_arguments(runtime_head, actual_remote, manifest):
    root = proof.base.previous.lane.ROOT
    require(root == Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
        and root.resolve() == root and Path.cwd().resolve() == root, "harness_root_changed")
    require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
        for value in (runtime_head, actual_remote)), "harness_arguments_refused")
    require(len(proof.code_paths()) == len(set(proof.code_paths())) == 64 and DRIVER in proof.code_paths(),
        "harness_registration_changed")
    if manifest is not None:
        require(type(manifest) is dict and set(manifest) == set(proof.code_paths())
            and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in manifest.values()), "harness_manifest_refused")
    require(HARNESS_SHA256 == hash_payload(policy()), "harness_registration_changed")


def _validate_result(result, seams, head, remote, manifest):
    seams._check()
    require(seams.active is True, "harness_counter_failed")
    require(not seams.failed and all(value == 0 for value in seams.denied.values()), "harness_counter_failed")
    fields = {"schema", "status", "runtime_head", "actual_remote", "code_identity_sha256",
        "code_manifest_sha256", "protocol_sha256", "started_at", "metadata_raw_sha256",
        "seal_stamp_sha256", "helper_closed_summary_sha256", "native_transition", "challenges",
        "original_code_and_metadata_contexts_closed", "authority", "closed_at",
        "isolated_storage_closed_summary_sha256"}
    require(type(result) is dict and set(result) == fields
        and result.get("schema") == "si-isolated-kernel-immutable-proof-closed-v2"
        and result.get("status") == "closed_offline_isolated_new_inode_only"
        and result.get("runtime_head") == head and result.get("actual_remote") == remote
        and result.get("code_manifest_sha256") == hash_payload(manifest)
        and result.get("protocol_sha256") == proof.PROTOCOL_SHA256
        and result.get("authority") == proof.authority()
        and result.get("original_code_and_metadata_contexts_closed") is True, "harness_result_refused")
    for name in ("code_identity_sha256", "metadata_raw_sha256", "seal_stamp_sha256",
            "helper_closed_summary_sha256", "isolated_storage_closed_summary_sha256"):
        require(type(result[name]) is str and re.fullmatch(r"[0-9a-f]{64}", result[name]), "harness_result_refused")
    require(result["metadata_raw_sha256"] == hash_bytes(proof.base.previous.metadata_bytes())
        and proof.base.previous.count.old.parallel.clock(result["closed_at"])
            >= proof.base.previous.count.old.parallel.clock(result["started_at"]), "harness_result_refused")
    transition = result.get("native_transition")
    require(type(transition) is dict and set(transition) == {"diagnostic", "diagnostic_sha256"}
        and type(transition["diagnostic"]) is dict
        and transition["diagnostic_sha256"] == hash_payload(transition["diagnostic"])
        and transition["diagnostic"].get("observer_complete") is True
        and type(transition["diagnostic"].get("native_call_count")) is int
        and transition["diagnostic"].get("native_call_count") == 1
        and type(transition["diagnostic"].get("native_result")) is int
        and transition["diagnostic"].get("native_result") == 0, "harness_result_refused")
    diagnostic = transition["diagnostic"]
    require(set(diagnostic) == {"schema", "observer_complete", "observer_failure", "native_call_count",
        "native_result", "native_errno_name", "before_native", "immediate_after_native",
        "after_callbacks", "classification", "first_controlled_refusal", "controlled_refusals",
        "policy_sha256", "authority"}
        and diagnostic["schema"] == "si-immutable-transition-diagnostic-v1"
        and diagnostic["observer_failure"] is diagnostic["native_errno_name"]
            is diagnostic["first_controlled_refusal"] is None
        and diagnostic["controlled_refusals"] == []
        and diagnostic["policy_sha256"] == hash_payload(proof.base.transition.policy())
        and diagnostic["authority"] == proof.base.transition.authority()
        and diagnostic["classification"] == "required_flags_observed_without_recorded_loss",
        "harness_result_refused")
    before, immediate, after = (diagnostic[name] for name in
        ("before_native", "immediate_after_native", "after_callbacks"))
    require(type(before) is dict and type(immediate) is dict and type(after) is list
        and 1 <= len(after) <= proof.base.transition.MAXIMUM_REFUSALS, "harness_result_refused")
    sample_fields = {"fd_flags", "name_flags", "same_original_inode", "protections_match",
        "size_and_mtime_unchanged", "retained_fd_readonly"}
    for sample in (before, immediate, *after):
        require(type(sample) is dict and set(sample) == sample_fields
            and all(sample[name] is True for name in sample_fields - {"fd_flags", "name_flags"})
            and type(sample["fd_flags"]) is int and type(sample["name_flags"]) is int
            and sample["fd_flags"] == sample["name_flags"], "harness_result_refused")
    require(before["fd_flags"] in (0, 64)
        and all(sample["fd_flags"] == before["fd_flags"] | 2 for sample in (immediate, *after)),
        "harness_result_refused")
    require(result.get("challenges") == [{"challenge": name, "result": "denied", "errno_name": "EPERM"}
        for name in ("write_open", "same_mode_fchmod", "fixed_fsetxattr")], "harness_result_refused")
    require(seams.permitted["create"] == seams.permitted["attach"] == seams.permitted["probe_create"]
        == seams.permitted["probe_write_challenge"] == 1, "harness_result_refused")


def _failure(error):
    if type(error) is OfflineHarnessRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = next((value for value in _CODES if args == ("REFUSED: " + value,)), None)
        return {"category": "offline_harness_refusal", "contract_code": code, "errno_name": None}
    return proof.failure_summary(error)


def run_once(runtime_head, actual_remote, complete_code_manifest=None):
    global _INVOKED
    require(not _INVOKED, "harness_already_invoked"); _INVOKED = True
    _registered_arguments(runtime_head, actual_remote, complete_code_manifest)
    seams = AuditSeams(runtime_head)
    sys.addaudithook(seams.handle)
    try:
        with _denied_entries(seams):
            manifest = complete_code_manifest
            if manifest is None:
                root = proof.base.previous.lane.ROOT
                manifest = {name: hash_bytes((root / name).read_bytes()) for name in proof.code_paths()}
            result = proof.run_registered(proof.base.previous.lane.ROOT, runtime_head=runtime_head,
                actual_remote=actual_remote, complete_code_manifest=manifest)
            _validate_result(result, seams, runtime_head, actual_remote, manifest)
            return {"status": "completed", "proof": result, "proof_sha256": hash_payload(result),
                "harness_policy_sha256": HARNESS_SHA256, "seams": seams.summary()}
    except BaseException as error:
        # All original driver/context exits have unwound as a refusal. Stop
        # the failed audit callback before pure traceback/error projection;
        # never clear its permanent failure/counters or admit another run.
        _deactivate(seams)
        return {"status": "refused", "failure": _failure(error),
            "harness_policy_sha256": HARNESS_SHA256, "seams": seams.summary()}
    finally: _deactivate(seams)


def main(argv=None):
    values = sys.argv[1:] if argv is None else argv
    if type(values) not in (list, tuple) or len(values) != 2:
        print(canonical_json({"status": "refused", "failure": {"contract_code": "harness_arguments_refused"}}), flush=True)
        return 2
    print(canonical_json({"status": "starting", "schema": "si-isolated-custody-offline-harness-v2"}), flush=True)
    try: result = run_once(values[0], values[1])
    except BaseException as error:
        result = {"status": "refused", "failure": _failure(error)}
    print(canonical_json(result), flush=True)
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__": raise SystemExit(main())
