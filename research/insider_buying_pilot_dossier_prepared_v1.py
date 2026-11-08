"""Bounded one-use pipes for independently prepared offline dossier workers.

Workers must be started before the parent installs its own native profile.
READY proves the worker reached its native/source/memory checks; it is not
activation or evidence completion. No data operation is implicit at EOF.
"""
from __future__ import annotations

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
import time

from research import insider_buying_pilot_stable_custody_v2 as stable

SCHEMA = "insider-pilot-storage-dossier-runner-v1"
ROOT, BRANCH = stable.LANE_ROOT, stable.LANE_BRANCH
ROLES = frozenset({"health", "dossier", "readback"})
MAX_READY, MAX_STDERR = 4096, 4096
MAX_ACTIVATION = MAX_OUTPUT = 1024 * 1024
READY_SECONDS, ACTIVE_SECONDS = 120, 240
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class PreparedError(ValueError):
    """Finite fixed refusal only; no command, private payload or stderr text."""


def need(ok, code):
    if not ok:
        raise PreparedError(code)


def raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise PreparedError("frame_refused") from None


def _identity(value):
    keys = {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
    need(type(value) is dict and set(value) == keys and value["root"] == str(ROOT)
         and value["branch"] == BRANCH and value["clean"] is True
         and type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["head"])
         and type(value["source_sha256"]) is dict and 0 < len(value["source_sha256"]) <= 1024,
         "identity_refused")
    for name, pin in value["source_sha256"].items():
        need(type(name) is str and len(name) <= 512 and re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py", name)
             and not Path(name).is_absolute() and ".." not in Path(name).parts
             and Path(name).as_posix() == name and Path(name).parts[0] != "artifacts"
             and type(pin) is str and _SHA.fullmatch(pin), "identity_refused")
    need(type(value["source_inventory_sha256"]) is str and value["source_inventory_sha256"]
         == hashlib.sha256(raw(value["source_sha256"])).hexdigest(), "identity_refused")
    encoded = raw(value)
    need(len(encoded) <= 256 * 1024, "identity_refused")
    return json.loads(encoded)


def ready_frame(role, identity):
    need(type(role) is str and role in ROLES, "role_refused")
    identity = _identity(identity)
    return {"schema": SCHEMA + "/ready", "role": role,
            "identity_sha256": hashlib.sha256(raw(identity)).hexdigest(),
            "ready": True, "data_operations": 0}


def activation_frame(role, identity, payload):
    ready = ready_frame(role, identity)
    need(type(payload) is dict, "activation_refused")
    frame = {"schema": SCHEMA + "/activate", "role": role,
             "identity_sha256": ready["identity_sha256"], "payload": payload}
    encoded = raw(frame) + b"\n"
    need(len(encoded) <= MAX_ACTIVATION, "activation_refused")
    return encoded


def validate_activation(encoded, role, identity):
    """Canonical one-document envelope; EOF is a refusal, never empty work."""
    need(type(encoded) is bytes and 0 < len(encoded) <= MAX_ACTIVATION
         and encoded.endswith(b"\n"), "activation_refused")
    def pairs(items):
        value = {}
        for key, child in items:
            need(key not in value, "activation_refused")
            value[key] = child
        return value
    def refuse(_value):
        raise PreparedError("activation_refused")
    try:
        value = json.loads(encoded[:-1], object_pairs_hook=pairs,
                           parse_float=refuse, parse_constant=refuse)
        need(type(value) is dict and set(value) == {"schema", "role", "identity_sha256", "payload"}
             and value["schema"] == SCHEMA + "/activate" and value["role"] == role
             and value["identity_sha256"] == ready_frame(role, identity)["identity_sha256"]
             and type(value["payload"]) is dict and raw(value) + b"\n" == encoded,
             "activation_refused")
        return json.loads(raw(value["payload"]))
    except PreparedError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PreparedError("activation_refused") from None


def _command(command, cwd):
    need(type(cwd) in {str, Path} or isinstance(cwd, Path), "command_refused")
    need(str(cwd) == str(ROOT) and isinstance(command, (tuple, list)) and len(command) == 11
         and all(type(part) is str and len(part) <= 256 * 1024 for part in command), "command_refused")
    need(tuple(command[:2]) == ("/usr/bin/sandbox-exec", "-p")
         and command[3] == sys.executable and tuple(command[4:8]) == ("-I", "-S", "-B", "-X")
         and command[8] == "pycache_prefix=" + stable.native.EMPTY_CACHE_PREFIX and command[9] == "-c"
         and bool(command[10]), "command_refused")
    need(command[2].startswith("(version 1)") and all(token in command[2] for token in
         ("(deny network*)", "(deny process-fork)", "(deny process-exec)", "(deny file-write*)")),
         "command_refused")
    return tuple(command)


def _remaining(deadline, code):
    remaining = deadline - time.monotonic()
    need(math.isfinite(remaining) and remaining > 0, code)
    return remaining


class Prepared:
    """A fixed native child, READY before one later explicit activation."""
    def __init__(self, role, identity, command, expected_ready, *, cwd):
        self.role, self.identity = role, _identity(identity)
        self.command = _command(command, cwd)
        expected = ready_frame(role, self.identity)
        need(type(expected_ready) is dict and raw(expected_ready) == raw(expected), "ready_refused")
        self.expected_ready = raw(expected) + b"\n"
        self.activated, self.closed, self.process = False, False, None
        try:
            self.process = subprocess.Popen(self.command, cwd=ROOT, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"})
            need(all(stream is not None for stream in (self.process.stdin, self.process.stdout, self.process.stderr)), "ready_refused")
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
            self._receive_ready()
        except BaseException as error:
            try:
                self.close()
            except BaseException:
                pass
            if isinstance(error, Exception) and type(error) is not PreparedError:
                raise PreparedError("ready_refused") from None
            raise

    def _receive_ready(self):
        poll, output = selectors.DefaultSelector(), bytearray()
        deadline = time.monotonic() + READY_SECONDS
        try:
            poll.register(self.process.stdout, selectors.EVENT_READ, "out")
            poll.register(self.process.stderr, selectors.EVENT_READ, "err")
            while b"\n" not in output:
                for key, _ in poll.select(min(.2, _remaining(deadline, "ready_refused"))):
                    try:
                        chunk = os.read(key.fileobj.fileno(), min(65536, MAX_READY + 1 - len(output)) if key.data == "out" else MAX_STDERR + 1)
                    except BlockingIOError:
                        continue
                    need(bool(chunk) and key.data == "out", "ready_refused")
                    output.extend(chunk)
                    need(len(output) <= MAX_READY, "ready_refused")
            need(bytes(output) == self.expected_ready and self.process.poll() is None, "ready_refused")
        finally:
            poll.close()

    def activate(self, payload):
        need(not self.closed and not self.activated and type(payload) is dict, "activation_refused")
        self.activated = True  # A failed write/framing consumes the invocation.
        poll = None
        try:
            encoded = activation_frame(self.role, self.identity, payload)
            poll = selectors.DefaultSelector()
            poll.register(self.process.stdin, selectors.EVENT_WRITE, "input")
            poll.register(self.process.stdout, selectors.EVENT_READ, "out")
            poll.register(self.process.stderr, selectors.EVENT_READ, "err")
            output, errors, offset = bytearray(), bytearray(), 0
            deadline = time.monotonic() + ACTIVE_SECONDS
            while poll.get_map():
                for key, _ in poll.select(min(.2, _remaining(deadline, "worker_refused"))):
                    if key.data == "input":
                        try:
                            count = os.write(key.fileobj.fileno(), memoryview(encoded)[offset:offset + 65536])
                        except BlockingIOError:
                            continue
                        need(type(count) is int and 0 < count <= min(65536, len(encoded) - offset), "worker_refused")
                        offset += count
                        if offset == len(encoded):
                            poll.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        target, cap = (output, MAX_OUTPUT) if key.data == "out" else (errors, MAX_STDERR)
                        try:
                            chunk = os.read(key.fileobj.fileno(), min(65536, cap + 1 - len(target)))
                        except BlockingIOError:
                            continue
                        if not chunk:
                            poll.unregister(key.fileobj)
                            continue
                        target.extend(chunk)
                        need(len(target) <= cap and not errors, "worker_refused")
            need(offset == len(encoded), "worker_refused")
            code = self.process.wait(timeout=_remaining(deadline, "worker_refused"))
            return stable.source._ipc_result(bytes(output), bytes(errors), code)
        except Exception:
            raise PreparedError("worker_refused") from None
        finally:
            primary = sys.exc_info()[0] is not None
            failed = False
            if poll is not None:
                try:
                    poll.close()
                except BaseException:
                    failed = True
            try:
                self.close()
            except Exception:
                if not primary:
                    raise
            need(primary or not failed, "cleanup_refused")

    def close(self):
        if self.closed:
            return
        self.closed, failed = True, False
        process = self.process
        if process is None:
            return
        try:
            running = process.poll() is None
        except BaseException:
            running, failed = True, True
        if running:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException:
                failed = True
        try:
            process.wait(timeout=5)
        except BaseException:
            failed = True
        for stream, cap in ((process.stdout, MAX_OUTPUT + 1), (process.stderr, MAX_STDERR + 1)):
            if stream is not None and not stream.closed:
                try:
                    while cap > 0:
                        chunk = os.read(stream.fileno(), min(65536, cap))
                        if not chunk:
                            break
                        cap -= len(chunk)
                except BlockingIOError:
                    pass
                except BaseException:
                    failed = True
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except BaseException:
                    failed = True
        need(not failed, "cleanup_refused")
