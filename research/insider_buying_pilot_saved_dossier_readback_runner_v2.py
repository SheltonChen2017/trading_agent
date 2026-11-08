"""Additive native read-only verification of the saved five-leaf dossier.

Source/Git checks and saved-byte checks are separate. No original input,
provider, credential, namespace creation, receipt rewrite or QC operation.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

from research import insider_buying_pilot_readback_isolation_v2 as isolation
from research import insider_buying_pilot_readback_prepared_v2 as transport
from research import insider_buying_pilot_saved_dossier_readback_v2 as receipt

prior = receipt.prior
stable, native, custody = prior.stable, prior.stable.native, prior.stable.custody
ROOT, BRANCH = isolation.ROOT, isolation.BRANCH
SCHEMA = "insider-pilot-saved-dossier-readback-runner-v2"
SELF = "research/insider_buying_pilot_saved_dossier_readback_runner_v2.py"
OWN = (SELF, "tests/test_insider_buying_pilot_saved_dossier_readback_runner_v2.py",
       "research/insider_buying_pilot_readback_isolation_v2.py",
       "tests/test_insider_buying_pilot_readback_isolation_v2.py",
       "research/insider_buying_pilot_readback_prepared_v2.py",
       "tests/test_insider_buying_pilot_readback_prepared_v2.py",
       "research/insider_buying_pilot_saved_dossier_readback_v2.py",
       "tests/test_insider_buying_pilot_saved_dossier_readback_v2.py")
MAX_IPC = 1024 * 1024
PARENT_INSTALLED = False
PHASES = frozenset({"entry", "current", "activation", "source-verify", "saved-open",
                    "saved-identity", "saved-validate", "final"})
REASONS = frozenset({"worker_error", "arguments_refused", "custody_refused", "identity_refused",
    "output_changed", "native_refused", "cleanup_refused", "saved_payload_refused",
    "saved_pin_refused", "saved_complete_anchor_refused", "saved_original_anchor_refused",
    "saved_identity_refused", "saved_source_overlap_refused", "saved_storage_refused",
    "saved_authority_refused", "saved_arguments_refused", "saved_summary_refused", "saved_readback_refused"})


class ReadbackError(ValueError):
    """Finite refusals only; never source config, saved fields or exception text."""


class WorkerRefusal(ReadbackError):
    def __init__(self, phase, reason):
        need(phase in PHASES and reason in REASONS, "refusal_frame_refused")
        self.phase, self.reason = phase, reason
        super().__init__("saved_readback_refused")


def refusal_frame(phase, error):
    reason = "worker_error"
    if isinstance(error, receipt.SavedReadbackError) and str(error) in REASONS:
        reason = str(error)
    elif isinstance(error, stable.CustodyError) and error.code in REASONS:
        reason = error.code
    return {"schema": SCHEMA + "/refusal", "completed": False,
            "phase": phase if phase in PHASES else "entry", "reason": reason}


def refuse_worker_result(value):
    if type(value) is dict and value.get("schema") == SCHEMA + "/refusal":
        need(set(value) == {"schema", "completed", "phase", "reason"} and value["completed"] is False
             and type(value["phase"]) is str and value["phase"] in PHASES
             and type(value["reason"]) is str and value["reason"] in REASONS, "refusal_frame_refused")
        raise WorkerRefusal(value["phase"], value["reason"])


def need(ok, code="readback_refused"):
    if not ok:
        raise ReadbackError(code)


def raw(value):
    return isolation.raw(value)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def version(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, "st_flags", 0)]


def code_bytes(name):
    isolation.validate_source_names((name,))
    path = ROOT / name
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
             and before.st_nlink == 1 and not stat.S_IMODE(before.st_mode) & 0o022
             and 0 <= before.st_size <= 4 * 1024 * 1024, "source_refused")
        body = os.pread(descriptor, 4 * 1024 * 1024 + 1, 0)
        need(len(body) == before.st_size and version(before) == version(os.fstat(descriptor))
             == version(path.stat(follow_symlinks=False)), "source_changed")
        return body, version(before)
    finally:
        os.close(descriptor)


def source_names():
    """Conservative internal closure plus string-named verifier/test images."""
    found = set(custody._internal_source_paths(ROOT)) | set(OWN) | set(prior.OWN)
    def collect(value, depth=0):
        if type(value) is str:
            if re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.py", value) and not value.startswith("artifacts/"):
                if (ROOT / value).is_file():
                    found.add(value)
        elif depth < 4 and isinstance(value, (tuple, list, set, frozenset, dict)) and len(value) <= 2048:
            for child in value:
                collect(child, depth + 1)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if type(filename) is str and Path(filename).is_relative_to(ROOT):
            for key, value in tuple(vars(module).items()):
                if key.isupper():
                    collect(value)
    return tuple(sorted(isolation.validate_source_names(sorted(found))))


def git(arguments, admin, *, limit=4 * 1024 * 1024):
    need(type(limit) is int and 0 < limit <= 4 * 1024 * 1024, "git_refused")
    need(os.getpgrp() == os.getpid(), "source_process_group_refused")
    process = subprocess.Popen(isolation.git_command(tuple(arguments), admin), cwd=ROOT,
        env=isolation.git_environment(admin), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=False)
    poll, output, errors = selectors.DefaultSelector(), bytearray(), bytearray()
    deadline = time.monotonic() + 15
    primary = False
    try:
        for stream, role in ((process.stdout, "out"), (process.stderr, "err")):
            os.set_blocking(stream.fileno(), False); poll.register(stream, selectors.EVENT_READ, role)
        while poll.get_map():
            remaining = deadline - time.monotonic(); need(remaining > 0, "git_refused")
            for key, _ in poll.select(min(.2, remaining)):
                target, cap = (output, limit) if key.data == "out" else (errors, 4096)
                try: chunk = os.read(key.fileobj.fileno(), min(65536, cap + 1 - len(target)))
                except BlockingIOError: continue
                if not chunk:
                    poll.unregister(key.fileobj); continue
                target.extend(chunk)
                need(len(target) <= cap and not errors, "git_refused")
        remaining = deadline - time.monotonic(); need(remaining > 0, "git_refused")
        need(process.wait(timeout=remaining) == 0 and not errors, "git_refused")
        return bytes(output)
    except BaseException:
        primary = True
        # The source worker owns this session. Terminal Git refusal kills
        # its WHOLE group; no detached descendants outlive a timed-out read.
        os.killpg(os.getpgrp(), signal.SIGKILL)
        raise
    finally:
        failed = False
        try: poll.close()
        except Exception: failed = True
        if process.poll() is None:
            try: process.kill()
            except ProcessLookupError: pass
            except Exception: failed = True
        try: process.wait(timeout=5)
        except Exception: failed = True
        for stream in (process.stdout, process.stderr):
            try: stream.close()
            except Exception: failed = True
        need(primary or not failed, "git_cleanup_refused")


def git_position(head, admin, *, clean):
    need(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head)
         and Path.cwd() == ROOT, "source_refused")
    need(git(("rev-parse", "--show-toplevel"), admin).decode().strip() == str(ROOT)
         and git(("rev-parse", "HEAD"), admin).decode().strip() == head
         and git(("rev-parse", "--abbrev-ref", "HEAD"), admin).decode().strip() == BRANCH,
         "source_refused")
    if clean:
        need(git(("status", "--porcelain=v1", "--untracked-files=all"), admin) == b"", "source_dirty")


def native_proof(*, source):
    native._isolated()
    custody._effective_denial(require_fork=not source)
    try:
        os.execve("/usr/bin/security", ["security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as error:
        need(error.errno in {errno.EACCES, errno.EPERM}, "native_refused")
    else:
        raise ReadbackError("native_refused")
    for path in (ROOT / "README.md", isolation.USER / "Library/Keychains"):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except OSError as error:
            need(error.errno in {errno.EACCES, errno.EPERM}, "data_fence_refused")
        else:
            os.close(descriptor)
            raise ReadbackError("data_fence_refused")
    try:
        descriptor = os.open("/private/tmp/ib386-forbidden-output", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as error:
        need(error.errno in {errno.EACCES, errno.EPERM}, "native_refused")
    else:
        os.close(descriptor)
        raise ReadbackError("native_refused")


def send(value, guard):
    wire = raw({"ok": True, "value": value}) + b"\n"
    need(len(wire) <= MAX_IPC, "ipc_refused")
    sys.stdout.buffer.write(wire); sys.stdout.buffer.flush(); guard.check()


def tree_plan(head, admin):
    git_position(head, admin, clean=False)
    directory_rows = git(("ls-tree", "-r", "-d", "--name-only", head), admin).decode().splitlines()
    files = git(("ls-tree", "-r", "--name-only", head), admin).decode().splitlines()
    def relative(name):
        need(type(name) is str and name and not Path(name).is_absolute()
             and Path(name).as_posix() == name and all(p not in {".", ".."} for p in name.split("/")), "tree_refused")
        return str(ROOT / name)
    need(len(directory_rows) <= 4096 and len(files) <= 20000
         and all(len(p) <= 1024 for p in (*directory_rows, *files)), "tree_refused")
    # Git must enumerate this existing untracked directory to establish a
    # clean status. Grant its DIRECTORY literal only, never file bodies or a
    # subtree. Any other unexpected directory stays denied/fail-closed.
    optional = [str(ROOT / name) for name in ("tmp", "tmp/pdfs") if (ROOT / name).is_dir()]
    return {"directories": list(dict.fromkeys([str(ROOT), *(relative(p) for p in directory_rows), *optional])),
            "ignores": [relative(p) for p in files if Path(p).name == ".gitignore"]}


def tree_worker(head, names, admin):
    guard = None
    try:
        native_proof(source=True); guard = native._WorkerMemoryGuard()
        isolation.check_admin(admin)
        for name in names:
            code_bytes(name)
        tree = tree_plan(head, admin)
        isolation.check_admin(admin); guard.check()
        send({"schema": SCHEMA + "/tree", "completed": True, "head": head, "tree": tree}, guard)
    finally:
        if guard is not None: guard.close()


def runtime_pins():
    _directories, images, _libraries = isolation.runtime_layout()
    pins = {}
    for path in (*images, isolation.GIT_IMAGE):
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 128 * 1024 * 1024,
                 "runtime_refused")
            data = os.pread(descriptor, before.st_size + 1, 0)
            need(len(data) == before.st_size and version(before) == version(os.fstat(descriptor))
                 == version(Path(path).stat()), "runtime_changed")
            pins[str(path)] = {"bytes": len(data), "sha256": sha(data)}
        finally: os.close(descriptor)
    return pins


def ignore_pins(tree, *, head, admin):
    result = {}
    for name in tree["ignores"]:
        body, pin = isolation._read_admin(Path(name))
        need(body == git(("show", head + ":" + Path(name).relative_to(ROOT).as_posix()), admin),
             "ignore_changed")
        result[name] = pin
    return result


def snapshot(head, names, admin, tree):
    isolation.check_admin(admin); git_position(head, admin, clean=True)
    old_files = set(git(("ls-tree", "-r", "--name-only", receipt.ORIGINAL_HEAD), admin).decode().splitlines())
    sources, versions = {}, {}
    for name in names:
        data, versions[name] = code_bytes(name)
        need(data == git(("show", head + ":" + name), admin), "source_refused")
        if name in old_files:
            need(data == git(("show", receipt.ORIGINAL_HEAD + ":" + name), admin), "bound_source_changed")
        sources[name] = sha(data)
    identity = {"root": str(ROOT), "branch": BRANCH, "head": head, "clean": True,
                "source_sha256": sources, "source_inventory_sha256": sha(raw(sources))}
    receipt.source_identity(identity)
    need(tree_plan(head, admin) == tree, "tree_changed")
    isolation.check_admin(admin); git_position(head, admin, clean=True)
    return {"identity": identity, "versions": versions, "admin": admin,
            "tree": tree, "runtime_pins": runtime_pins(),
            "ignore_pins": ignore_pins(tree, head=head, admin=admin)}


def source_worker(head, names, admin, tree):
    guard = None
    try:
        native_proof(source=True); guard = native._WorkerMemoryGuard()
        value = snapshot(head, names, admin, tree)
        send({"schema": SCHEMA + "/source", "completed": True, "manifest": value}, guard)
    finally:
        if guard is not None: guard.close()


def source_current(manifest):
    validate_manifest(manifest)
    identity = receipt.source_identity(manifest["identity"])
    need(set(manifest["versions"]) == set(identity["source_sha256"]), "source_refused")
    for name, digest in identity["source_sha256"].items():
        data, observed = code_bytes(name)
        need(sha(data) == digest and observed == manifest["versions"][name], "source_changed")
    need(runtime_pins() == manifest["runtime_pins"], "runtime_changed")


def validate_manifest(manifest):
    need(type(manifest) is dict and set(manifest) == {"identity", "versions", "admin", "tree", "runtime_pins", "ignore_pins"},
         "source_refused")
    identity = receipt.source_identity(manifest["identity"])
    need(type(manifest["versions"]) is dict and set(manifest["versions"]) == set(identity["source_sha256"]), "source_refused")
    for observed in manifest["versions"].values():
        need(type(observed) is list and len(observed) == 10
             and all(type(field) is int and field >= 0 for field in observed)
             and stat.S_ISREG(observed[2]) and observed[3] == 1 and 0 <= observed[6] <= 4 * 1024 * 1024,
             "source_refused")
    isolation._layout(manifest["admin"])
    tree = manifest["tree"]
    need(type(tree) is dict and set(tree) == {"directories", "ignores"}
         and type(tree["directories"]) is list and 0 < len(tree["directories"]) <= 4099
         and type(tree["ignores"]) is list and len(tree["ignores"]) <= 256, "tree_refused")
    isolation._source_directories(tree["directories"]); isolation._ignore_leaves(tree["ignores"])
    pins = manifest["runtime_pins"]
    _dirs, images, _libraries = isolation.runtime_layout()
    need(type(pins) is dict and set(pins) == {str(path) for path in (*images, isolation.GIT_IMAGE)}, "runtime_refused")
    for pin in pins.values():
        need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
             and type(pin["bytes"]) is int and 0 < pin["bytes"] <= 128 * 1024 * 1024
             and type(pin["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]), "runtime_refused")
    need(type(manifest["ignore_pins"]) is dict and set(manifest["ignore_pins"]) == set(tree["ignores"]), "ignore_refused")
    for pin in manifest["ignore_pins"].values():
        need(type(pin) is dict and set(pin) == {"present", "bytes", "sha256", "version"}
             and pin["present"] is True and type(pin["bytes"]) is int and 0 <= pin["bytes"] <= isolation.MAX_ADMIN
             and type(pin["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
             and type(pin["version"]) is list and len(pin["version"]) == 10
             and all(type(field) is int and field >= 0 for field in pin["version"])
             and pin["version"][6] == pin["bytes"], "ignore_refused")
    return manifest


def verify_sources(manifest, original):
    source_current(manifest)
    bound, admin, tree = manifest["identity"], manifest["admin"], manifest["tree"]
    isolation.check_admin(admin); git_position(bound["head"], admin, clean=True)
    need(ignore_pins(tree, head=bound["head"], admin=admin) == manifest["ignore_pins"], "ignore_changed")
    if original is not None:
        original = receipt.source_identity(original)
        need(original["head"] == receipt.ORIGINAL_HEAD
             and original["source_inventory_sha256"] == receipt.ORIGINAL_INVENTORY
             and len(original["source_sha256"]) == receipt.ORIGINAL_SOURCE_COUNT,
             "original_source_refused")
        for name, digest in original["source_sha256"].items():
            need(bound["source_sha256"].get(name) == digest
                 and sha(git(("show", original["head"] + ":" + name), admin)) == digest,
                 "original_source_refused")
    for name, digest in bound["source_sha256"].items():
        need(sha(git(("show", bound["head"] + ":" + name), admin)) == digest, "source_refused")
    need(tree_plan(bound["head"], admin) == tree, "tree_changed")
    need(ignore_pins(tree, head=bound["head"], admin=admin) == manifest["ignore_pins"], "ignore_changed")
    isolation.check_admin(admin); git_position(bound["head"], admin, clean=True)
    source_current(manifest)
    return {"schema": SCHEMA + "/verified-sources", "completed": True,
            "reader_head": bound["head"], "reader_inventory": bound["source_inventory_sha256"],
            "reader_source_images_verified": len(bound["source_sha256"]),
            "original_inventory": original["source_inventory_sha256"] if original is not None else None,
            "original_source_images_verified": len(original["source_sha256"]) if original is not None else 0,
            "admin_sha256": sha(raw(admin)), "runtime_sha256": sha(raw(manifest["runtime_pins"])),
            "ignore_sha256": sha(raw(manifest["ignore_pins"]))}


def prepared_worker(role, manifest, profile_hash, mode):
    guard, phase = None, "entry"
    try:
        need(role in {"source", "readback"} and mode in {"health", "readback"}, "arguments_refused")
        native_proof(source=role == "source"); guard = native._WorkerMemoryGuard()
        phase = "current"; source_current(manifest)
        if role == "source":
            isolation.check_admin(manifest["admin"])
            git_position(manifest["identity"]["head"], manifest["admin"], clean=True)
            need(ignore_pins(manifest["tree"], head=manifest["identity"]["head"],
                 admin=manifest["admin"]) == manifest["ignore_pins"], "ignore_changed")
        binding = transport.running_command_binding(profile_hash)
        ready = transport.ready_frame(role, manifest["identity"], profile_hash, binding)
        sys.stdout.buffer.write(raw(ready) + b"\n"); sys.stdout.buffer.flush(); guard.check()
        phase = "activation"
        encoded = sys.stdin.buffer.read(transport.MAX_ACTIVATION + 1)
        payload = transport.validate_activation(encoded, role, manifest["identity"], profile_hash, binding)
        if role == "source":
            need(type(payload) is dict and set(payload) == {"original_identity"}
                 and (mode == "readback" and type(payload["original_identity"]) is dict
                      or mode == "health" and payload["original_identity"] is None), "activation_refused")
            phase = "source-verify"; result = verify_sources(manifest, payload["original_identity"])
        else:
            need(payload == {} and type(payload) is dict, "activation_refused")
            if mode == "health":
                result = {"schema": SCHEMA + "/health", "completed": True, "data_leaves": 0,
                          "reader_inventory": manifest["identity"]["source_inventory_sha256"]}
            else:
                phase = "saved-open"
                value = stable.read_epoch_controls(prior.AUDIT_ID, receipt.OUTPUT_NAMES,
                    {"complete.json": {"bytes": None, "sha256": receipt.COMPLETE_SHA256}}, memory=guard)
                phase = "saved-identity"; original = receipt.extract_original_identity(value)
                phase = "saved-validate"
                result = {"schema": SCHEMA + "/saved", "completed": True,
                          "original_identity": original,
                          "summary": receipt.validate_saved(value, original_identity=original,
                                                            reader_identity=manifest["identity"])}
        phase = "final"; source_current(manifest); send(result, guard)
    except Exception as error:
        if guard is not None: send(refusal_frame(phase, error), guard)
        else: raise
    finally:
        if guard is not None: guard.close()


def command(function, args, profile):
    code = "import sys;sys.path.insert(0," + repr(str(ROOT)) + ");from research import insider_buying_pilot_saved_dossier_readback_runner_v2 as m;m." + function + "(" + ",".join(repr(arg) for arg in args) + ")"
    return ("/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=" + native.EMPTY_CACHE_PREFIX, "-c", code)


def source_profile(names, admin, tree=None):
    return isolation.policy(sources=names, admin=admin, git=True,
        source_directories=() if tree is None else tree["directories"],
        gitignore_leaves=() if tree is None else tree["ignores"])


def launch_source(argv, *, timeout):
    # Keep the frozen bounded transport intact. SIP-protected env clears the
    # inherited environment BEFORE sandbox-exec/interpreter bootstrap; neither
    # a shell nor a caller-controlled executable or environment entry is used.
    prefix = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=en_US.UTF-8")
    return stable.source._launch((*prefix, *argv), timeout=timeout)


def source_preflight(head):
    need(PARENT_INSTALLED is False, "parent_refused")
    names, admin = source_names(), isolation.discover_admin()
    result = launch_source(command("tree_worker", (head, names, admin), source_profile(names, admin)), timeout=120)
    need(type(result) is dict and set(result) == {"schema", "completed", "head", "tree"}
         and result["schema"] == SCHEMA + "/tree" and result["completed"] is True
         and result["head"] == head, "tree_refused")
    tree = result["tree"]
    result = launch_source(command("source_worker", (head, names, admin, tree), source_profile(names, admin, tree)), timeout=180)
    need(type(result) is dict and set(result) == {"schema", "completed", "manifest"}
         and result["schema"] == SCHEMA + "/source" and result["completed"] is True, "source_refused")
    manifest = result["manifest"]
    validate_manifest(manifest)
    need(type(manifest) is dict and set(manifest) == {"identity", "versions", "admin", "tree", "runtime_pins", "ignore_pins"}
         and receipt.source_identity(manifest["identity"])["head"] == head
         and set(manifest["identity"]["source_sha256"]) == set(names)
         and raw(manifest["admin"]) == raw(admin) and raw(manifest["tree"]) == raw(tree), "source_refused")
    source_current(manifest)
    return manifest


def prepare(role, manifest, mode):
    need(PARENT_INSTALLED is False, "parent_refused")
    if role == "source":
        profile = source_profile(manifest["identity"]["source_sha256"], manifest["admin"], manifest["tree"])
    else:
        profile = isolation.policy(sources=manifest["identity"]["source_sha256"],
            data_leaves=tuple(prior.OUTPUT / name for name in receipt.OUTPUT_NAMES) if mode == "readback" else ())
    argv = command("prepared_worker", (role, manifest, sha(profile.encode()), mode), profile)
    return transport.Prepared(role, manifest["identity"], argv, cwd=ROOT)


def install_parent(profile):
    global PARENT_INSTALLED
    need(PARENT_INSTALLED is False, "parent_refused"); PARENT_INSTALLED = True
    library = ctypes.CDLL("/usr/lib/libsandbox.dylib", use_errno=True)
    call = library.sandbox_init
    call.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
    call.restype = ctypes.c_int; error = ctypes.c_char_p()
    need(call(profile.encode(), 0, ctypes.byref(error)) == 0, "parent_refused")


def validate_source_result(value, manifest, original):
    expected = {"schema": SCHEMA + "/verified-sources", "completed": True,
        "reader_head": manifest["identity"]["head"],
        "reader_inventory": manifest["identity"]["source_inventory_sha256"],
        "reader_source_images_verified": len(manifest["identity"]["source_sha256"]),
        "original_inventory": original["source_inventory_sha256"] if original is not None else None,
        "original_source_images_verified": len(original["source_sha256"]) if original is not None else 0,
        "admin_sha256": sha(raw(manifest["admin"])), "runtime_sha256": sha(raw(manifest["runtime_pins"])),
        "ignore_sha256": sha(raw(manifest["ignore_pins"]))}
    need(raw(value) == raw(expected), "source_result_refused")
    return value


def run(head, *, mode):
    need(mode in {"health", "readback"}, "arguments_refused")
    guard, workers = native._WorkerMemoryGuard(), []
    try:
        manifest = source_preflight(head)
        reader = prepare("readback", manifest, mode); workers.append(reader)
        verifier = prepare("source", manifest, mode); workers.append(verifier)
        profile = isolation.policy(sources=manifest["identity"]["source_sha256"], controller=True)
        install_parent(profile); native_proof(source=False); source_current(manifest); guard.check()
        value = reader.activate({})
        refuse_worker_result(value)
        if mode == "health":
            need(raw(value) == raw({"schema": SCHEMA + "/health", "completed": True,
                "data_leaves": 0, "reader_inventory": manifest["identity"]["source_inventory_sha256"]}), "health_result_refused")
            original, summary = None, value
        else:
            need(type(value) is dict and set(value) == {"schema", "completed", "original_identity", "summary"}
                 and value["schema"] == SCHEMA + "/saved" and value["completed"] is True, "saved_result_refused")
            original = receipt.source_identity(value["original_identity"])
            summary = receipt.validate_summary(value["summary"], original_identity=original,
                                               reader_identity=manifest["identity"])
        verified = verifier.activate({"original_identity": original})
        refuse_worker_result(verified)
        verified = validate_source_result(verified, manifest, original)
        source_current(manifest); guard.check()
        return {"schema": SCHEMA + "/complete", "completed": True, "mode": mode,
                "reader_execution_head": head,
                "source_verification": verified, "receipt": summary,
                "controller_profile_sha256": sha(profile.encode()),
                "native_policy_bindings": {role: {"profile_sha256": worker.profile_sha256,
                    "command_sha256": worker.command_sha256} for role, worker in
                    (("readback", reader), ("source", verifier))},
                "original_input_leaves_replayed": 0, "files_written": 0,
                "authority": prior.transition.authority()}
    finally:
        failed = False
        for worker in reversed(workers):
            try: worker.close()
            except Exception: failed = True
        try: guard.close()
        except Exception: failed = True
        need(not failed, "cleanup_refused")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--health", action="store_true")
    choice.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.expected_head, mode="health" if args.health else "readback")
        print(raw(result).decode())
    except WorkerRefusal as error:
        print(raw({"completed": False, "code": "saved_readback_refused",
                   "phase": error.phase, "reason": error.reason}).decode())
        raise SystemExit(2) from None
    except Exception:
        print('{"completed":false,"code":"saved_readback_refused"}')
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
