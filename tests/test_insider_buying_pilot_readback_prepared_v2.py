"""Invented pipe and argv state only; caller provides native DATA isolation."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace
import sys

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX offline custody")
from research import insider_buying_pilot_readback_prepared_v2 as m


def identity():
    sources = {"research/invented.py": "1" * 64}
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": "2" * 40, "clean": True,
            "source_sha256": sources, "source_inventory_sha256": hashlib.sha256(m.raw(sources)).hexdigest()}


def command(role="readback"):
    profile = "(version 1)(allow default)(deny network*)(deny process-exec)(deny file-write*)"
    profile += "(deny process-fork)" if role == "readback" else '(allow process-exec (literal "' + m.GIT_IMAGE + '"))'
    return ("/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=" + m.stable.native.EMPTY_CACHE_PREFIX, "-c", "pass")


def bindings(role="readback"):
    cmd = command(role)
    return hashlib.sha256(cmd[2].encode()).hexdigest(), m.command_binding(cmd)


@pytest.mark.parametrize("role", ("source", "readback"))
def test_ready_and_activation_bind_role_source_policy_and_exact_command(role):
    bound, (profile, launch) = identity(), bindings(role)
    ready = m.ready_frame(role, bound, profile, launch)
    payload = {"invented": [1, None, False]}
    frame = m.activation_frame(role, bound, profile, launch, payload)
    assert ready["ready"] is True and ready["data_operations"] == 0
    assert ready["identity_sha256"] == hashlib.sha256(m.raw(bound)).hexdigest()
    assert (ready["profile_sha256"], ready["command_sha256"]) == (profile, launch)
    assert m.validate_activation(frame, role, bound, profile, launch) == payload
    payload["invented"].append("changed")
    assert m.validate_activation(frame, role, bound, profile, launch) == {"invented": [1, None, False]}


def test_running_python_binding_matches_parent_without_duplicating_full_policy(monkeypatch):
    cmd = command()
    profile, launch = bindings()
    monkeypatch.setattr(m.sys, "orig_argv", list(cmd[3:]))
    assert m.running_command_binding(profile) == launch
    changed = list(cmd); changed[10] = "different source"
    assert m.command_binding(changed) != launch
    changed = list(cmd); changed[2] += '(deny file-read-data (literal "/invented"))'
    assert m.command_binding(changed) != launch
    assert m.running_command_binding("0" * 64) != launch


def test_known_fingerprinted_macos_framework_relaunch_preserves_launch_binding(monkeypatch):
    from research import insider_buying_pilot_readback_isolation_v2 as isolation
    profile, launch = bindings()
    actual = list(command()[3:])
    image = isolation.SUPPORTED_BASE / "Resources/Python.app/Contents/MacOS/Python"
    actual[0] = str(image)
    monkeypatch.setattr(m.sys, "orig_argv", actual)
    monkeypatch.setattr(isolation, "runtime_layout", lambda: ((), (image,), ()))
    assert m.running_command_binding(profile) == launch


@pytest.mark.parametrize("image", ("/Volumes/untrusted/Python", "/tmp/Python", "/usr/bin/python3"))
def test_framework_normalization_cannot_accept_an_arbitrary_python_image(monkeypatch, image):
    profile, _launch = bindings()
    actual = list(command()[3:]); actual[0] = image
    monkeypatch.setattr(m.sys, "orig_argv", actual)
    with pytest.raises(m.PreparedError, match="command_refused"):
        m.running_command_binding(profile)


@pytest.mark.parametrize("fault", ("eof", "newline", "whitespace", "duplicate", "float", "nan",
    "role", "identity", "profile", "command", "extra", "oversize"))
def test_activation_refuses_ambiguous_or_rebound_frames(fault):
    bound, (profile, launch) = identity(), bindings()
    encoded = m.activation_frame("readback", bound, profile, launch, {})
    value = {"schema": m.SCHEMA + "/activate", "role": "readback", "payload": {},
        "identity_sha256": m.ready_frame("readback", bound, profile, launch)["identity_sha256"],
        "profile_sha256": profile, "command_sha256": launch}
    if fault == "eof": encoded = b""
    elif fault == "newline": encoded = encoded[:-1]
    elif fault == "whitespace": encoded = b" " + encoded
    elif fault == "duplicate": encoded = encoded.replace(b'"payload":{}', b'"payload":{},"payload":{}')
    elif fault == "float": value["payload"] = {"value": 1.5}; encoded = m.raw(value) + b"\n"
    elif fault == "nan": encoded = encoded.replace(b'"payload":{}', b'"payload":{"value":NaN}')
    elif fault == "role": value["role"] = "source"; encoded = m.raw(value) + b"\n"
    elif fault in {"identity", "profile", "command"}:
        value[fault + "_sha256"] = "0" * 64; encoded = m.raw(value) + b"\n"
    elif fault == "extra": value["extra"] = True; encoded = m.raw(value) + b"\n"
    else: encoded = b"X" * (m.MAX_ACTIVATION + 1) + b"\n"
    with pytest.raises(m.PreparedError): m.validate_activation(encoded, "readback", bound, profile, launch)


@pytest.mark.parametrize("fault", ("root", "branch", "clean", "inventory", "absolute", "traversal", "dot", "artifact", "extra"))
def test_ready_refuses_rebound_or_noncanonical_identity(fault):
    bound, (profile, launch) = identity(), bindings()
    if fault in {"root", "branch"}: bound[fault] = "invented-other"
    elif fault == "clean": bound["clean"] = 1
    elif fault == "inventory": bound["source_inventory_sha256"] = "0" * 64
    elif fault in {"absolute", "traversal", "dot", "artifact"}:
        names = {"absolute": "/private/invented.py", "traversal": "research/../invented.py",
                 "dot": "./artifacts/private.py", "artifact": "artifacts/private.py"}
        bound["source_sha256"] = {names[fault]: "1" * 64}
        bound["source_inventory_sha256"] = hashlib.sha256(m.raw(bound["source_sha256"])).hexdigest()
    else: bound["extra"] = True
    with pytest.raises(m.PreparedError): m.ready_frame("readback", bound, profile, launch)


@pytest.mark.parametrize("fault", ("cwd", "program", "python", "isolated", "site", "bytecode", "cache", "profile", "extra", "oversize"))
def test_command_and_cwd_are_checked_before_spawning(fault):
    cmd, cwd = list(command()), m.ROOT
    if fault == "cwd": cwd = m.ROOT.parent
    elif fault == "program": cmd[0] = "/usr/bin/env"
    elif fault == "python": cmd[3] = "/invented/python"
    elif fault == "isolated": cmd[4] = "-B"
    elif fault == "site": cmd[5] = "-B"
    elif fault == "bytecode": cmd[6] = "-S"
    elif fault == "cache": cmd[8] = "pycache_prefix=/private/tmp"
    elif fault == "profile": cmd[2] = "(version 1)(allow default)"
    elif fault == "oversize": cmd[10] = "X" * m.MAX_COMMAND
    else: cmd.append("extra")
    with pytest.raises(m.PreparedError): m._command(cmd, cwd, "readback")


def test_source_and_readback_launch_shapes_cannot_be_interchanged():
    assert m._command(command("source"), m.ROOT, "source")
    assert m._command(command("readback"), m.ROOT, "readback")
    with pytest.raises(m.PreparedError): m._command(command("source"), m.ROOT, "readback")
    with pytest.raises(m.PreparedError): m._command(command("readback"), m.ROOT, "source")


class Stream:
    def __init__(self, fd, events, *, close_error=False):
        self.fd, self.events, self.closed, self.close_error = fd, events, False, close_error
    def fileno(self): return self.fd
    def close(self):
        self.closed = True; self.events.append(("close", self.fd))
        if self.close_error: raise OSError("PRIVATE CLOSE")


def pipes(monkeypatch, *, role="readback", ready=None, output=None, ready_error=b"", stderr=b"",
          write_error=False, write_zero=False, ready_timeout=False, activation_timeout=False,
          cleanup_failure=False, exit_code=0):
    bound, (profile, launch) = identity(), bindings(role)
    expected = m.ready_frame(role, bound, profile, launch)
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
            events.append(("wait", timeout)); self.returncode = exit_code; return exit_code

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
    factory = lambda: m.Prepared(role, bound, command(role), cwd=m.ROOT)
    return factory, process, written, events, calls


@pytest.mark.parametrize("role", ("source", "readback"))
def test_readiness_precedes_one_bound_activation_and_cleanup(monkeypatch, role):
    factory, process, written, events, calls = pipes(monkeypatch, role=role)
    child = factory()
    assert not child.activated and not written
    result = child.activate({"invented": "payload"})
    assert result == {"completed": True, "invented": 1}
    profile, launch = bindings(role)
    assert m.validate_activation(bytes(written), role, identity(), profile, launch) == {"invented": "payload"}
    assert child.activated and child.closed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    assert calls[0][0] == command(role)
    assert calls[0][1]["start_new_session"] is True and calls[0][1]["cwd"] == m.ROOT
    assert set(calls[0][1]["env"]) == {"PATH", "LANG"}
    with pytest.raises(m.PreparedError): child.activate({})
    before = list(events); child.close(); assert events == before


@pytest.mark.parametrize("fault", ("eof", "wrong", "profile", "command", "extra-line", "oversize", "stderr", "deadline"))
def test_bad_ready_never_activates_and_cleans_group(monkeypatch, fault):
    profile, launch = bindings()
    value = m.ready_frame("readback", identity(), profile, launch)
    ready = m.raw(value) + b"\n"
    options = {}
    if fault == "eof": options["ready"] = b""
    elif fault == "wrong": options["ready"] = b"{}\n"
    elif fault in {"profile", "command"}:
        value[fault + "_sha256"] = "0" * 64; options["ready"] = m.raw(value) + b"\n"
    elif fault == "extra-line": options["ready"] = ready + b"{}\n"
    elif fault == "oversize": options["ready"] = b"X" * (m.MAX_READY + 1)
    elif fault == "stderr": options["ready_error"] = b"PRIVATE SOURCE"
    else: options["ready_timeout"] = True
    factory, process, written, events, _calls = pipes(monkeypatch, **options)
    with pytest.raises(m.PreparedError) as caught: factory()
    assert "PRIVATE" not in str(caught.value) and not written
    assert any(event[0] == "kill" for event in events)
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


@pytest.mark.parametrize("fault", ("broken-pipe", "zero-write", "extra-output", "stderr", "oversize", "deadline", "cleanup", "exit"))
def test_activation_failure_is_consumed_and_cannot_return_success(monkeypatch, fault):
    options = {}
    if fault == "broken-pipe": options["write_error"] = True
    elif fault == "zero-write": options["write_zero"] = True
    elif fault == "extra-output": options["output"] = b'{}\n{}\n'
    elif fault == "stderr": options["stderr"] = b"PRIVATE STDERR"
    elif fault == "oversize": options["output"] = b"X" * (m.MAX_OUTPUT + 1)
    elif fault == "deadline": options["activation_timeout"] = True
    elif fault == "exit": options["exit_code"] = 2
    else: options["cleanup_failure"] = True
    factory, process, _written, _events, _calls = pipes(monkeypatch, **options)
    child = factory()
    with pytest.raises(m.PreparedError) as caught: child.activate({})
    assert "PRIVATE" not in str(caught.value) and child.activated and child.closed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    with pytest.raises(m.PreparedError): child.activate({})


def test_oversized_activation_consumes_invocation_before_any_write(monkeypatch):
    factory, _process, written, _events, _calls = pipes(monkeypatch)
    child = factory()
    with pytest.raises(m.PreparedError): child.activate({"oversized": "X" * m.MAX_ACTIVATION})
    assert child.activated and child.closed and not written


def test_exited_source_leader_still_retires_its_owned_descendant_group(monkeypatch):
    factory, process, _written, events, _calls = pipes(monkeypatch, role="source")
    child = factory()
    process.returncode = 2
    child.close()
    assert ("kill", process.pid, m.signal.SIGKILL) in events
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


def test_popen_failure_is_sanitized(monkeypatch):
    def fail(*_args, **_kwargs): raise OSError("PRIVATE COMMAND")
    monkeypatch.setattr(m.subprocess, "Popen", fail)
    with pytest.raises(m.PreparedError, match="^ready_refused$"):
        m.Prepared("readback", identity(), command(), cwd=m.ROOT)
