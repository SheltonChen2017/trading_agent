"""Invented pipe state only; no child, retained input, provider or QC operation."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace
import subprocess
import sys

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX native custody")
from research import insider_buying_pilot_dossier_prepared_v1 as m


def identity():
    sources = {"research/invented.py": "1" * 64}
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": "2" * 40, "clean": True,
            "source_sha256": sources, "source_inventory_sha256": hashlib.sha256(m.raw(sources)).hexdigest()}


def command():
    policy = "(version 1)(allow default)(deny network*)(deny process-fork)(deny process-exec)(deny file-write*)"
    return ("/usr/bin/sandbox-exec", "-p", policy, sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=" + m.stable.native.EMPTY_CACHE_PREFIX, "-c", "pass")


@pytest.mark.parametrize("role", ("health", "dossier", "readback"))
def test_canonical_ready_and_activation_are_role_and_full_identity_bound(role):
    bound = identity(); ready = m.ready_frame(role, bound)
    payload = {"invented": [1, None, False]}
    frame = m.activation_frame(role, bound, payload)
    assert ready["ready"] is True and ready["data_operations"] == 0
    assert ready["identity_sha256"] == hashlib.sha256(m.raw(bound)).hexdigest()
    assert m.validate_activation(frame, role, bound) == payload
    payload["invented"].append("changed")
    assert m.validate_activation(frame, role, bound) == {"invented": [1, None, False]}


@pytest.mark.parametrize("fault", ("eof", "newline", "whitespace", "duplicate", "float", "nan", "role", "identity", "extra", "oversize"))
def test_activation_refuses_ambiguous_unbound_or_noncanonical_frames(fault):
    bound = identity(); encoded = m.activation_frame("dossier", bound, {})
    value = {"schema": m.SCHEMA + "/activate", "role": "dossier",
             "identity_sha256": m.ready_frame("dossier", bound)["identity_sha256"], "payload": {}}
    if fault == "eof": encoded = b""
    elif fault == "newline": encoded = encoded[:-1]
    elif fault == "whitespace": encoded = b" " + encoded
    elif fault == "duplicate": encoded = encoded.replace(b'"payload":{}', b'"payload":{},"payload":{}')
    elif fault == "float": value["payload"] = {"value": 1.5}; encoded = m.raw(value) + b"\n"
    elif fault == "nan": encoded = encoded.replace(b'"payload":{}', b'"payload":{"value":NaN}')
    elif fault == "role": value["role"] = "readback"; encoded = m.raw(value) + b"\n"
    elif fault == "identity": value["identity_sha256"] = "0" * 64; encoded = m.raw(value) + b"\n"
    elif fault == "extra": value["extra"] = True; encoded = m.raw(value) + b"\n"
    else: encoded = b"X" * (m.MAX_ACTIVATION + 1) + b"\n"
    with pytest.raises(m.PreparedError): m.validate_activation(encoded, "dossier", bound)


@pytest.mark.parametrize("fault", ("root", "branch", "clean", "inventory", "absolute", "traversal", "extra"))
def test_ready_refuses_a_rebound_or_unqualified_source_identity(fault):
    bound = identity()
    if fault in {"root", "branch"}: bound[fault] = "invented-other"
    elif fault == "clean": bound["clean"] = 1
    elif fault == "inventory": bound["source_inventory_sha256"] = "0" * 64
    elif fault == "absolute": bound["source_sha256"] = {"/private/invented.py": "1" * 64}
    elif fault == "traversal": bound["source_sha256"] = {"research/../invented.py": "1" * 64}
    else: bound["extra"] = True
    with pytest.raises(m.PreparedError): m.ready_frame("health", bound)


@pytest.mark.parametrize("fault", ("cwd", "program", "python", "isolated", "site", "bytecode", "cache", "profile", "extra"))
def test_native_command_and_cwd_are_fixed_before_popen(fault):
    args, cwd = list(command()), m.ROOT
    if fault == "cwd": cwd = m.ROOT.parent
    elif fault == "program": args[0] = "/usr/bin/env"
    elif fault == "python": args[3] = "/invented/python"
    elif fault == "isolated": args[4] = "-B"
    elif fault == "site": args[5] = "-B"
    elif fault == "bytecode": args[6] = "-S"
    elif fault == "cache": args[8] = "pycache_prefix=/private/tmp"
    elif fault == "profile": args[2] = "(version 1)(allow default)"
    else: args.append("extra")
    with pytest.raises(m.PreparedError): m._command(args, cwd)


class Stream:
    def __init__(self, fd, events, *, close_error=False):
        self.fd, self.events, self.closed, self.close_error = fd, events, False, close_error
    def fileno(self): return self.fd
    def close(self):
        self.closed = True; self.events.append(("close", self.fd))
        if self.close_error: raise OSError("PRIVATE CLOSE")


def pipes(monkeypatch, *, ready=None, output=None, ready_error=b"", stderr=b"", write_error=False,
          write_zero=False, ready_timeout=False, activation_timeout=False, cleanup_failure=False):
    bound = identity(); expected = m.ready_frame("dossier", bound)
    ready = m.raw(expected) + b"\n" if ready is None else ready
    output = m.raw({"ok": True, "value": {"completed": True, "invented": 1}}) + b"\n" if output is None else output
    events, written, calls = [], bytearray(), []
    class Process:
        pid = 123456789
        def __init__(self):
            self.stdin = Stream(10, events); self.stdout = Stream(11, events)
            self.stderr = Stream(12, events, close_error=cleanup_failure); self.returncode = None
        def poll(self): return self.returncode
        def wait(self, timeout):
            events.append(("wait", timeout)); self.returncode = 0; return 0
    process = Process()
    def popen(cmd, **kwargs): calls.append((cmd, kwargs)); return process
    monkeypatch.setattr(m.subprocess, "Popen", popen)
    monkeypatch.setattr(m.os, "set_blocking", lambda fd, value: events.append(("blocking", fd, value)))
    monkeypatch.setattr(m.os, "killpg", lambda pid, sig: events.append(("kill", pid, sig)))
    phase = {"stage": 0, "ready": bytearray(ready), "readyerr": bytearray(ready_error),
             "output": bytearray(output), "stderr": bytearray(stderr)}
    class Poll:
        def __init__(self): self.map = {}; self.stage = phase["stage"]; phase["stage"] += 1
        def register(self, stream, _events, data): self.map[stream.fd] = SimpleNamespace(fileobj=stream, data=data)
        def unregister(self, stream): self.map.pop(stream.fd)
        def get_map(self): return self.map
        def select(self, timeout):
            if self.stage == 0:
                if ready_timeout: raise m.PreparedError("ready_refused")
                selected = [self.map[11]]
                if ready_error: selected.append(self.map[12])
                return [(key, 1) for key in selected]
            if activation_timeout: raise m.PreparedError("worker_refused")
            return [(key, 1) for key in list(self.map.values())]
        def close(self): events.append(("poll-close", self.stage))
    monkeypatch.setattr(m.selectors, "DefaultSelector", Poll)
    def read(fd, cap):
        if phase["stage"] == 1:
            buffer = phase["ready"] if fd == 11 else phase["readyerr"]
        else:
            buffer = phase["output"] if fd == 11 else phase["stderr"]
        result = bytes(buffer[:cap]); del buffer[:cap]; return result
    monkeypatch.setattr(m.os, "read", read)
    def write(_fd, payload):
        if write_error: raise BrokenPipeError("PRIVATE PIPE")
        if write_zero: return 0
        count = min(37, len(payload)); written.extend(payload[:count]); return count
    monkeypatch.setattr(m.os, "write", write)
    prepared = lambda: m.Prepared("dossier", bound, command(), expected, cwd=m.ROOT)
    return prepared, process, written, events, calls


def test_prepared_child_is_ready_before_one_bounded_activation_and_cleaned(monkeypatch):
    factory, process, written, events, calls = pipes(monkeypatch)
    child = factory()
    assert not child.activated and not written
    result = child.activate({"invented": "payload"})
    assert result == {"completed": True, "invented": 1}
    assert m.validate_activation(bytes(written), "dossier", identity()) == {"invented": "payload"}
    assert child.activated and child.closed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    assert calls[0][1]["start_new_session"] is True and calls[0][1]["cwd"] == m.ROOT
    assert set(calls[0][1]["env"]) == {"PATH", "LANG"}
    with pytest.raises(m.PreparedError): child.activate({})
    before = list(events); child.close(); assert events == before


@pytest.mark.parametrize("fault", ("eof", "wrong", "extra-line", "oversize", "stderr", "deadline"))
def test_ready_failure_never_activates_and_cleans_the_process_group(monkeypatch, fault):
    ready = m.raw(m.ready_frame("dossier", identity())) + b"\n"
    options = {}
    if fault == "eof": options["ready"] = b""
    elif fault == "wrong": options["ready"] = b"{}\n"
    elif fault == "extra-line": options["ready"] = ready + b"{}\n"
    elif fault == "oversize": options["ready"] = b"X" * (m.MAX_READY + 1)
    elif fault == "stderr": options["ready_error"] = b"PRIVATE SOURCE"
    else: options["ready_timeout"] = True
    factory, process, written, events, _calls = pipes(monkeypatch, **options)
    with pytest.raises(m.PreparedError) as caught: factory()
    assert "PRIVATE" not in str(caught.value) and not written
    assert any(event[0] == "kill" for event in events)
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


@pytest.mark.parametrize("fault", ("broken-pipe", "zero-write", "extra-ready", "stderr", "oversize", "deadline", "cleanup"))
def test_activation_is_consumed_before_failure_and_never_returns_success(monkeypatch, fault):
    options = {}
    if fault == "broken-pipe": options["write_error"] = True
    elif fault == "zero-write": options["write_zero"] = True
    elif fault == "extra-ready": options["output"] = m.raw(m.ready_frame("dossier", identity())) + b"\n" + m.raw({"ok": True, "value": {"completed": True}}) + b"\n"
    elif fault == "stderr": options["stderr"] = b"PRIVATE STDERR"
    elif fault == "oversize": options["output"] = b"X" * (m.MAX_OUTPUT + 1)
    elif fault == "deadline": options["activation_timeout"] = True
    else: options["cleanup_failure"] = True
    factory, process, _written, _events, _calls = pipes(monkeypatch, **options)
    child = factory()
    with pytest.raises(m.PreparedError) as caught: child.activate({})
    assert "PRIVATE" not in str(caught.value) and child.activated and child.closed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    with pytest.raises(m.PreparedError): child.activate({})


def test_invalid_activation_frame_consumes_the_prepared_invocation_before_write(monkeypatch):
    factory, _process, written, _events, _calls = pipes(monkeypatch)
    child = factory()
    with pytest.raises(m.PreparedError): child.activate({"oversized": "X" * m.MAX_ACTIVATION})
    assert child.activated and child.closed and not written


def test_constructor_refuses_nonmatching_expected_ready_before_spawning(monkeypatch):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *_a, **_k: pytest.fail("spawned before ready binding"))
    ready = m.ready_frame("health", identity()); ready["data_operations"] = 1
    with pytest.raises(m.PreparedError): m.Prepared("health", identity(), command(), ready, cwd=m.ROOT)
