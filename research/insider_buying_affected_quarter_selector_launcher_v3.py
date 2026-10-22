"""One-shot trusted hash/control publisher for the unchanged selector-v2 front.

The owner explicitly approved an UNSANDBOXED trusted parent on 2026-10-21.
Its Python audit guard is defense in depth, not native isolation. Only the
unchanged front's captured-source semantic worker receives one native sandbox;
that worker still proves network, fork and all-write denial before intake.
No raw rows, credentials, acquisition, outcomes or backtest authority arise.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time


LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
SELF_PATH = "research/insider_buying_affected_quarter_selector_launcher_v3.py"
SCHEMA = "insider-affected-quarter-selector-trusted-publisher-v3"
AUDIT_ID = "ib-selector-trusted-publisher-v3-20261021-once"
OUTPUT_PARTS = ("artifacts", "insider_buying", "selector_trusted_publisher_v3")
SEMANTIC_ID = "ib-affected-quarter-selector-ctime-verified-v2-20261021-once"
SEMANTIC_PARTS = ("artifacts", "insider_buying", "affected_quarter_selector_verification_v2")
PRIOR_OBSERVER_PARTS = ("artifacts", "insider_buying", "selector_verification_v2_observer", SEMANTIC_ID)
PRIOR_OBSERVER_PINS = {
    "reservation.json": (1845, "6309966fea99f54bf293b30d096c778de56b929f6b79ea29d05212996dd9360b"),
    "terminal.json": (522, "734d734f93887a288ee59b4148ebd3d115c2f22d1fec5fb80163b70f2de16929"),
}
MAX_CHILD_BYTES = 2 * 1024 * 1024
MAX_JOURNAL_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
REGISTRATION_RAW = json.dumps({
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "observer_namespace": "/".join(OUTPUT_PARTS), "semantic_audit_id": SEMANTIC_ID,
    "semantic_namespace": "/".join(SEMANTIC_PARTS),
    "unchanged_v2_front_sha256": "e5d3839ab630e1df3c1b3d1c0e23b0191a4105fa887b400bd49700cdae48daf3",
    "semantic_registration_sha256": "bb6f2d720ecc86abeddf863b75c3d9eb823a9cf3ef695c47f5474a9ccdd916ee",
    "prior_observer_namespace": "/".join(PRIOR_OBSERVER_PARTS),
    "prior_observer_pins": {name: {"bytes": pin[0], "sha256": pin[1]}
        for name, pin in sorted(PRIOR_OBSERVER_PINS.items())},
    "prior_launch_exit": 71, "prior_semantic_executions": 0,
    "new_semantic_invocations_permitted": 1,
    "parent_isolation": "trusted_unsandboxed_python_audit_guard_not_native_denial",
    "semantic_worker_isolation": "unchanged_single_native_network_fork_all_write_denial",
    "old_failed_v1_promoted_or_rewritten": False,
    "new_source_acquisition_or_qc_or_outcome_access": False,
    "backtest_readiness_granted": False,
}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
REGISTRATION_SHA256 = hashlib.sha256(REGISTRATION_RAW).hexdigest()


class TrustedSelectorLauncherError(ValueError):
    """Fixed control refusal, never source/provider/credential/error text."""


def _need(value, code="trusted_selector_control_refused"):
    if not value:
        raise TrustedSelectorLauncherError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _decode(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            _need(name not in result, "repeated_control_key_refused")
            result[name] = value
        return result
    body = json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: _need(False, "nonfinite_control_refused"))
    _need(_raw(body) + b"\n" == raw, "canonical_child_control_required")
    return body


def _front():
    # Role entry installs its audit hook before this first lane import.
    from research import insider_buying_affected_quarter_selector_verification_v2 as front
    _need(front.AUDIT_ID == SEMANTIC_ID and front.REGISTRATION_SHA256
        == json.loads(REGISTRATION_RAW)["semantic_registration_sha256"], "unchanged_semantic_registration_required")
    return front


def _fd_path(fd):
    _need(type(fd) is int and fd >= 0, "audit_directory_descriptor_required")
    # Darwin F_GETPATH resolves the descriptor, not a caller-controlled lexical
    # relative path. Linux support here is for invented tests, not a lane port.
    if sys.platform == "darwin":
        value = fcntl.fcntl(fd, 50, bytes(1024)).split(b"\0", 1)[0]
        return Path(os.fsdecode(value))
    return Path(os.readlink("/proc/self/fd/" + str(fd)))


class ParentAuditGuard:
    """Cooperative process-level protection, explicitly NOT an OS sandbox."""
    def __init__(self, role, *, head, commands=()):
        _need(role in {"observer", "preflight", "semantic", "readback"})
        _need(type(head) is str and _HEAD.fullmatch(head))
        self.role, self.head = role, head
        self.commands = tuple(tuple(command) for command in commands)
        self.used_commands = set()
        self.worker_launches = 0
        self.front = None

    def _path(self, value, directory_fd=-1):
        if type(value) is int:
            return _fd_path(value)
        _need(type(value) in {str, bytes} or isinstance(value, os.PathLike), "audit_path_required")
        path = Path(os.fsdecode(value))
        if not path.is_absolute():
            parent = Path.cwd() if directory_fd in {-1, None} else _fd_path(directory_fd)
            path = parent / path
        return Path(os.path.realpath(path))

    def _write(self, path, *, mkdir=False):
        if self.role == "observer":
            root = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)
            leaves = {"reservation.json", "terminal.json", "readback.json", "final.json"}
        elif self.role == "semantic":
            root = LANE_ROOT.joinpath(*SEMANTIC_PARTS, SEMANTIC_ID)
            leaves = {"reservation.json", "selection.json", "complete.json"}
        else:
            raise PermissionError("trusted_parent_write_refused")
        permitted = ((mkdir and path in {root.parent, root})
            or (not mkdir and path.parent == root and path.name in leaves))
        if not permitted:
            raise PermissionError("trusted_parent_write_refused")

    def _open_write_path(self, value):
        if type(value) is int or Path(os.fsdecode(value)).is_absolute():
            return self._path(value)
        # CPython's ``open`` audit event omits openat's dir_fd. Only the exact
        # byte-bound custody publisher may resolve that otherwise ambiguous
        # relative name, from its held descriptor. Unknown writers refuse.
        _need(self.front is not None, "audit_known_publisher_required")
        publisher = self.front.original.capture.custody._Directory
        frame = sys._getframe(2)
        owner = frame.f_locals.get("self")
        _need(frame.f_code is publisher.publish.__code__ and type(owner) is publisher
            and frame.f_locals.get("name") == value, "audit_relative_open_publisher_required")
        return self._path(value, owner.fd)

    def _git(self, executable, command, cwd, env):
        if executable != "/usr/bin/git" or type(command) not in {list, tuple}:
            return False
        if not command or command[0] != executable or not self._lane_cwd(cwd):
            return False
        args = tuple(command[1:])
        if args in {("rev-parse", "--show-toplevel"), ("rev-parse", "HEAD"),
                ("branch", "--show-current"), ("status", "--porcelain=v1", "--untracked-files=all")}:
            return type(env) is dict and env == {"PATH": "/usr/bin:/bin"}
        if len(args) == 2 and args[0] == "show" and type(args[1]) is str:
            commit, separator, relative = args[1].partition(":")
            path = Path(relative)
            valid = (separator and commit in {self.head, "aa0d635d00b64825bf8003289e0a60279bd52e73"}
                and not path.is_absolute() and ".." not in path.parts
                and (relative.endswith(".py") or relative == "artifacts/sec_insider/raw/.gitattributes"))
            return bool(valid and type(env) is dict and env == {"PATH": "/usr/bin:/bin"})
        return False

    @staticmethod
    def _lane_cwd(value):
        return (type(value) is str or isinstance(value, os.PathLike)) and Path(value) == LANE_ROOT

    def __call__(self, event, args):
        if (event.startswith(("socket.", "http.client.", "urllib."))
                or event in {"os.system", "os.fork", "os.forkpty", "os.exec", "os.posix_spawn",
                    "os.spawn", "os.startfile", "os.startfile/2", "pty.spawn"}):
            raise PermissionError("trusted_parent_network_or_unknown_process_refused")
        if event == "subprocess.Popen":
            executable, command, cwd, env = args
            if self._git(executable, command, cwd, env):
                return
            if self.role == "observer":
                candidate = tuple(command) if type(command) in {list, tuple} else ()
                if (candidate not in self.commands or candidate in self.used_commands
                        or not self._lane_cwd(cwd) or executable != sys.executable
                        or env != {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}):
                    raise PermissionError("trusted_observer_child_refused")
                self.used_commands.add(candidate)
                return
            if self.role == "semantic" and self.front is not None:
                front = self.front
                expected = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                    "/usr/bin/sandbox-exec", "-p", front.original.isolation._worker_policy(
                        LANE_ROOT.joinpath(*SEMANTIC_PARTS, SEMANTIC_ID), readonly=True),
                    sys.executable, "-I", "-S", "-B", "-c", front.SOURCE_ONLY_BOOTSTRAP)
                if (executable == "/usr/bin/env" and tuple(command) == expected
                        and self._lane_cwd(cwd) and env is None and self.worker_launches == 0):
                    self.worker_launches += 1
                    return
            raise PermissionError("trusted_parent_unknown_subprocess_refused")
        if event.startswith("subprocess."):
            raise PermissionError("trusted_parent_unknown_subprocess_refused")
        if event == "open":
            path, mode, flags = args
            writable = (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writable or (type(mode) is str and any(letter in mode for letter in "wax+")):
                self._write(self._open_write_path(path))
        elif event == "os.mkdir":
            path, _mode, directory_fd = args
            self._write(self._path(path, directory_fd), mkdir=True)
        elif event in {"os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.chmod", "os.chown", "os.truncate", "os.utime"}:
            raise PermissionError("trusted_parent_mutation_refused")


def run_child(command, *, cwd, env, timeout, cap=MAX_CHILD_BYTES):
    """Bound BOTH pipes; timeout/interrupt/overflow kills and reaps the group."""
    _need(type(timeout) in {int, float} and math.isfinite(timeout) and timeout > 0
        and type(cap) is int and cap > 0)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    output, error = bytearray(), bytearray()
    monitor = selectors.DefaultSelector()
    deadline = time.monotonic() + timeout
    try:
        for stream, target in ((process.stdout, output), (process.stderr, error)):
            os.set_blocking(stream.fileno(), False)
            monitor.register(stream, selectors.EVENT_READ, target)
        while monitor.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout, bytes(output), bytes(error))
            for key, _ in monitor.select(min(remaining, 0.2)):
                chunk = os.read(key.fileobj.fileno(), min(65536, cap + 1 - len(key.data)))
                if chunk:
                    key.data.extend(chunk)
                    _need(len(key.data) <= cap, "bounded_child_pipe_refused")
                else:
                    monitor.unregister(key.fileobj)
        status = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, status, bytes(output), bytes(error))
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        monitor.close()
        process.stdout.close()
        process.stderr.close()


def _identity(front, head):
    identity, frozen = front._fixed_source_identity(head)
    _need(identity["head"] == head and identity["root"] == str(LANE_ROOT)
        and identity["branch"] == LANE_BRANCH and identity["clean"] is True
        and SELF_PATH in identity["source_sha256"]
        and identity["source_inventory_sha256"] == _sha(_raw(identity["source_sha256"]))
        and identity["source_sha256"][front.SELF_PATH]
            == json.loads(REGISTRATION_RAW)["unchanged_v2_front_sha256"], "clean_registered_source_identity_required")
    return {"identity": identity, "frozen": frozen}


def role_main(role, head, selection_sha=None, complete_sha=None):
    _need(role in {"preflight", "semantic", "readback"} and _HEAD.fullmatch(head))
    guard = ParentAuditGuard(role, head=head)
    sys.addaudithook(guard)
    front = _front()
    guard.front = front
    if role == "preflight":
        body = _identity(front, head)
    elif role == "semantic":
        status = front.main(["--audit-id", SEMANTIC_ID, "--expected-head", head])
        return status
    else:
        _need(type(selection_sha) is str and _SHA.fullmatch(selection_sha)
            and type(complete_sha) is str and _SHA.fullmatch(complete_sha))
        body = front.verify_observed_completion(expected_head=head,
            expected_selection_sha256=selection_sha, expected_complete_sha256=complete_sha,
            observed_cli_success=True)
    print(_raw(body).decode(), flush=True)
    return 0


def _role_command(role, head, prefix, *pins):
    code = ("import sys;from research import insider_buying_affected_quarter_selector_launcher_v3 as l;"
        "raise SystemExit(l.role_main(*sys.argv[1:]))")
    return [sys.executable, "-B", "-X", "pycache_prefix=" + str(prefix), "-c", code, role, head, *pins]


class _HeldPriorObserver:
    def __init__(self, front):
        self.front = front
        self.tree = None
        try:
            self.tree = front.held_io._HeldCapture(LANE_ROOT.joinpath(*PRIOR_OBSERVER_PARTS))
            _need(self.tree.names == frozenset(PRIOR_OBSERVER_PINS), "exact_failed_observer_inventory_required")
            for name, (size, digest) in sorted(PRIOR_OBSERVER_PINS.items()):
                stream = self.tree.open(name, MAX_JOURNAL_BYTES)
                _need(front.held_io._hash_stream(stream, MAX_JOURNAL_BYTES) == (digest, size),
                    "failed_observer_pin_changed")
            self.tree.check()
        except BaseException:
            self.close()
            raise

    def recheck(self, front):
        self.tree.check()
        for name, stream, _, cap in self.tree.handles:
            size, digest = PRIOR_OBSERVER_PINS[name]
            _need(front.held_io._hash_stream(stream, cap) == (digest, size), "held_failed_observer_pin_changed")
        self.tree.check()

    def close(self):
        if self.tree is not None:
            tree = self.tree
            self.tree = None
            self.front._close_tree(tree, phase="parent_cleanup")


def _semantic_success(front, child):
    _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= 8192,
        "actual_semantic_exit0_and_empty_stderr_required")
    body = _decode(child.stdout)
    _need(type(body) is dict and set(body) == {"audit_id", "fixture_only", "selection_sha256",
        "complete_sha256", "counts", "authority", "operation_registration_sha256", "predecessor_status"})
    expected = {"audit_id": SEMANTIC_ID, "fixture_only": False,
        "selection_sha256": front.pure._digest(body["selection_sha256"]),
        "complete_sha256": front.pure._digest(body["complete_sha256"]),
        "counts": front.pure.EXPECTED_ACTUAL_COUNTS, "authority": front._authority(),
        "operation_registration_sha256": front.REGISTRATION_SHA256,
        "predecessor_status": "FAILED_preserved_not_promoted"}
    _need(front._raw(front._known_context(front._opaque_json(child.stdout.removesuffix(b"\n")), expected))
        + b"\n" == child.stdout, "exact_canonical_semantic_success_required")
    return expected


def _terminal(child, started, kind):
    return {"schema": SCHEMA + "/" + kind, "audit_id": AUDIT_ID,
        "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": child.returncode,
        "timed_out": False, "stdout_bytes": len(child.stdout), "stdout_sha256": _sha(child.stdout),
        "stderr_bytes": len(child.stderr), "stderr_sha256": _sha(child.stderr)}


def _readback_control(front, child, success):
    _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= 8192,
        "actual_readback_exit0_and_empty_stderr_required")
    body = _decode(child.stdout)
    expected = {"schema": front.SCHEMA + "/read-only-verification", "audit_id": SEMANTIC_ID,
        "fixture_only": False, "metadata_only": True, "semantic_rederivations_performed_here": 0,
        "terminal_cli_status_authenticated_here": False, "external_cli_success_hint_supplied": True,
        "operation_registration_sha256": front.REGISTRATION_SHA256,
        "selection_sha256": success["selection_sha256"], "complete_sha256": success["complete_sha256"],
        "reservation_sha256": front.pure._digest(body["reservation_sha256"]),
        "counts": front.pure.EXPECTED_ACTUAL_COUNTS,
        "predecessor_status": "FAILED_preserved_not_promoted", "authority": front._authority()}
    opaque = front._opaque_json(child.stdout.removesuffix(b"\n"))
    _need(front._raw(front._known_context(opaque, expected)) + b"\n" == child.stdout,
        "strict_metadata_readback_control_required")
    return expected


def _verify_journal(front, journal, pins):
    # Fresh publisher leaves can receive delayed macOS ctime-only metadata.
    # As for corrected v2 outputs, retain identity/custody/mtime and rehash all
    # bytes; do not reinterpret that metadata transition as content stability.
    journal.check()
    held = front.held_io._HeldCapture(journal.path, settle_ctime=True)
    try:
        _need(held.names == set(pins), "exact_launcher_journal_inventory_required")
        for name, digest in sorted(pins.items()):
            stream = held.open(name, MAX_JOURNAL_BYTES)
            actual, size = front.held_io._hash_stream(stream, MAX_JOURNAL_BYTES)
            _need(actual == digest and 0 < size <= MAX_JOURNAL_BYTES, "launcher_journal_bytes_changed")
        held.check()
        for name, stream, _, cap in held.handles:
            _need(front.held_io._hash_stream(stream, cap)[0] == pins[name], "held_launcher_journal_bytes_changed")
        held.check()
        journal.check()
    finally:
        front._close_tree(held, phase="parent_cleanup")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    _need(args.audit_id == AUDIT_ID and _HEAD.fullmatch(args.expected_head), "fixed_unused_launcher_scope_required")
    _need(Path.cwd() == LANE_ROOT and Path(__file__).resolve() == LANE_ROOT / SELF_PATH,
        "designated_tracked_launcher_required")
    os.umask(0o077)
    # Prefix is created before the observer's write fence and never used for
    # writing bytecode. All role interpreters compile exact committed sources.
    prefix = Path(tempfile.mkdtemp(prefix="ib-selector-trusted-v3-", dir="/private/tmp")) / "unused-cache"
    head = args.expected_head
    preflight = _role_command("preflight", head, prefix)
    semantic = _role_command("semantic", head, prefix)
    # Readback pins are unknown until actual success. Only the trusted observer
    # then extends its exact allowlist with that one hash-bound command.
    observer_guard = ParentAuditGuard("observer", head=head, commands=(preflight, semantic))
    sys.addaudithook(observer_guard)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    source = run_child(preflight, cwd=LANE_ROOT, env=env, timeout=180)
    _need(source.returncode == 0 and source.stderr == b"" and 0 < len(source.stdout) < MAX_CHILD_BYTES,
        "clean_child_source_preflight_required")
    source_context = _decode(source.stdout)
    _need(type(source_context) is dict and set(source_context) == {"identity", "frozen"})
    front = _front()
    observer_guard.front = front
    _need(_identity(front, head) == source_context, "observer_and_role_source_identity_differ")
    semantic_root = LANE_ROOT.joinpath(*SEMANTIC_PARTS, SEMANTIC_ID)
    _need(not os.path.lexists(semantic_root), "semantic_namespace_already_consumed")
    prior = _HeldPriorObserver(front)
    journal = None
    published = {}
    try:
        base = LANE_ROOT.joinpath(*OUTPUT_PARTS)
        parent = front.original.capture.custody._Directory(base, create=True)
        try:
            _need(not parent.exists(AUDIT_ID), "launcher_namespace_already_consumed")
            os.mkdir(AUDIT_ID, 0o700, dir_fd=parent.fd)
            os.fsync(parent.fd)
        finally:
            parent.close()
        journal = front.original.capture.custody._Directory(base / AUDIT_ID)
        reservation = {"schema": SCHEMA + "/reservation", "audit_id": AUDIT_ID,
            "execution_head": head, "registration": json.loads(REGISTRATION_RAW),
            "registration_sha256": REGISTRATION_SHA256, "source_context": source_context,
            "launcher_source_sha256": source_context["identity"]["source_sha256"][SELF_PATH],
            "python": sys.version, "environment_keys": sorted(env), "authority": front._authority()}
        published["reservation.json"] = journal.publish("reservation.json", _raw(reservation), cap=MAX_JOURNAL_BYTES)
        started = time.monotonic()
        try:
            child = run_child(semantic, cwd=LANE_ROOT, env=env, timeout=1900)
        except (subprocess.TimeoutExpired, TrustedSelectorLauncherError) as exc:
            terminal = {"schema": SCHEMA + "/semantic-terminal", "audit_id": AUDIT_ID,
                "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": None,
                "timed_out": isinstance(exc, subprocess.TimeoutExpired), "terminal_success_observed": False,
                "control_refusal": "timeout_or_bounded_pipe_refusal_preserved_no_retry"}
            published["terminal.json"] = journal.publish("terminal.json", _raw(terminal), cap=MAX_JOURNAL_BYTES)
            print(_raw(terminal).decode(), flush=True)
            return 2
        terminal = _terminal(child, started, "semantic-terminal")
        terminal["terminal_success_observed"] = False
        success = None
        try:
            success = _semantic_success(front, child)
            terminal.update(terminal_success_observed=True, success_summary=success)
        except (ValueError, TypeError, KeyError):
            if child.returncode == 2 and child.stderr == b"" and 0 < len(child.stdout) <= 8192:
                try:
                    terminal["fixed_diagnostic"] = front._strict_failure(front._opaque_json(child.stdout.removesuffix(b"\n")))
                except (ValueError, TypeError, KeyError):
                    terminal["diagnostic_schema_accepted"] = False
        published["terminal.json"] = journal.publish("terminal.json", _raw(terminal), cap=MAX_JOURNAL_BYTES)
        print(_raw(terminal).decode(), flush=True)
        prior.recheck(front)
        if success is None:
            return 2
        command = _role_command("readback", head, prefix, success["selection_sha256"], success["complete_sha256"])
        observer_guard.commands += (tuple(command),)
        started = time.monotonic()
        try:
            child = run_child(command, cwd=LANE_ROOT, env=env, timeout=180)
        except (subprocess.TimeoutExpired, TrustedSelectorLauncherError) as exc:
            observed = {"schema": SCHEMA + "/readback-terminal", "audit_id": AUDIT_ID,
                "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": None,
                "timed_out": isinstance(exc, subprocess.TimeoutExpired), "readback_accepted": False,
                "semantic_invocations_performed_here": 0}
            published["readback.json"] = journal.publish("readback.json", _raw(observed), cap=MAX_JOURNAL_BYTES)
            print(_raw(observed).decode(), flush=True)
            return 2
        observed = _terminal(child, started, "readback-terminal")
        observed.update(readback_accepted=False, semantic_invocations_performed_here=0)
        try:
            observed.update(readback=_readback_control(front, child, success), readback_accepted=True)
        except (ValueError, TypeError, KeyError):
            observed["stdout_schema_accepted"] = False
        published["readback.json"] = journal.publish("readback.json", _raw(observed), cap=MAX_JOURNAL_BYTES)
        print(_raw(observed).decode(), flush=True)
        prior.recheck(front)
        _need(_identity(front, head) == source_context, "final_source_identity_changed")
        _verify_journal(front, journal, published)
        _need(observed["readback_accepted"], "actual_readback_not_accepted")
        final = {"schema": SCHEMA + "/final", "audit_id": AUDIT_ID,
            "execution_head": head, "registration_sha256": REGISTRATION_SHA256,
            "semantic_exit0_observed": True, "strict_readback_accepted": True,
            "parent_isolation": "trusted_unsandboxed_python_audit_guard_not_native_denial",
            "semantic_invocations_performed": 1, "preceding_failed_observer_preserved": True,
            "old_failed_v1_promoted_or_rewritten": False, "journal_leaf_sha256": published,
            "selection_sha256": success["selection_sha256"], "complete_sha256": success["complete_sha256"],
            "authority": front._authority()}
        final_sha = journal.publish("final.json", _raw(final), cap=MAX_JOURNAL_BYTES)
        prior.recheck(front)
        _verify_journal(front, journal, {**published, "final.json": final_sha})
        print(_raw(final).decode(), flush=True)
        return 0
    finally:
        front._close_all((journal, prior), phase="parent_cleanup")


if __name__ == "__main__":
    try:
        status = main()
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
        print(_raw({"schema": SCHEMA + "/refusal", "audit_id": AUDIT_ID,
            "disposition": "trusted_launcher_refused_preserved_no_retry",
            "backtest_readiness_granted": False}).decode(), flush=True)
        status = 2
    raise SystemExit(status)
