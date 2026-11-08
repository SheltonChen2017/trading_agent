"""Direct one-shot and role-entry coverage for section 383's test-only gap.

All profiles, native calls, guards, pipes and role workers are invented/mocked.
These tests never install a sandbox, launch a child or read retained DATA.
They cover existing activation guards, not a successor implementation.
"""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from research import insider_buying_pilot_storage_dossier_runner_v1 as m


def _bound():
    sources = {m.SELF: "a" * 64}
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": "b" * 40,
            "clean": True, "source_sha256": sources,
            "source_inventory_sha256": m.sha(m.raw(sources))}


def _fake_installer(monkeypatch, result):
    loads, calls = [], []

    class Init:
        def __call__(self, profile, flags, error_pointer):
            calls.append((profile, flags, error_pointer))
            return result

    init = Init()

    def load(path, **kwargs):
        loads.append((path, kwargs))
        return SimpleNamespace(sandbox_init=init)

    monkeypatch.setattr(m, "_PARENT_SANDBOX_APPLIED", False)
    monkeypatch.setattr(m.ctypes, "CDLL", load)
    return loads, calls


def test_parent_installer_is_one_shot_even_for_a_successful_fake_install(monkeypatch):
    loads, calls = _fake_installer(monkeypatch, 0)
    m.install_parent_policy("invented profile")
    assert m._PARENT_SANDBOX_APPLIED is True
    assert loads == [("/usr/lib/libsandbox.dylib", {"use_errno": True})]
    assert len(calls) == 1 and calls[0][:2] == (b"invented profile", 0)
    with pytest.raises(m.StorageDossierError, match="parent_isolation_refused"):
        m.install_parent_policy("another invented profile")
    assert len(loads) == len(calls) == 1


def test_failed_fake_install_stays_consumed_and_prevents_new_preparation(monkeypatch):
    loads, calls = _fake_installer(monkeypatch, -1)
    monkeypatch.setattr(m.prepared_io, "Prepared",
                        lambda *_a, **_k: pytest.fail("preparation after failed install"))
    monkeypatch.setattr(m.stable.source, "_launch",
                        lambda *_a, **_k: pytest.fail("launch after failed install"))
    with pytest.raises(m.StorageDossierError, match="parent_isolation_refused"):
        m.install_parent_policy("invented rejected profile")
    assert m._PARENT_SANDBOX_APPLIED is True
    with pytest.raises(m.StorageDossierError, match="parent_isolation_refused"):
        m.install_parent_policy("invented second attempt")
    with pytest.raises(m.StorageDossierError, match="worker_refused"):
        m.prepare_worker("health", _bound())
    with pytest.raises(m.StorageDossierError, match="worker_refused"):
        m.launch("discovery_worker", _bound())
    assert len(loads) == len(calls) == 1


def _entry(monkeypatch, role, payload=None, *, eof=False, envelope_role=None):
    bound, events, sent, guards, dispatched = _bound(), [], [], [], []
    frame = b"" if eof else m.prepared_io.activation_frame(
        envelope_role or role, bound, deepcopy(payload))
    output = io.BytesIO()
    text_output = io.TextIOWrapper(output, encoding="utf-8", write_through=True)
    monkeypatch.setattr(m.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frame)))
    monkeypatch.setattr(m.sys, "stdout", text_output)
    monkeypatch.setattr(m.stable.native, "_isolated", lambda: events.append("isolated"))
    monkeypatch.setattr(m.stable.native.source_runner, "_prove_isolation",
                        lambda: events.append("native-proof"))

    class Guard:
        def __init__(self):
            self.closed = False
            events.append("guard-created")
            guards.append(self)

        def check(self):
            assert not self.closed
            events.append("guard-check")

        def close(self):
            assert not self.closed
            self.closed = True
            events.append("guard-close")

    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", Guard)

    def source_check(value):
        assert value == m.compact(bound)
        events.append("source-check")

    monkeypatch.setattr(m.prior, "_source_current", source_check)

    def send(value, guard):
        assert guards and guard is guards[0] and not guard.closed
        guard.check()
        sent.append(deepcopy(value))

    monkeypatch.setattr(m, "_send", send)

    def inner(name):
        def invoke(*args):
            assert guards and not guards[0].closed
            events.append("dispatch-" + name)
            dispatched.append((name, deepcopy(args)))
            send({"completed": True, "role": name}, guards[0])
        return invoke

    monkeypatch.setattr(m, "health_worker", inner("health"))
    monkeypatch.setattr(m, "dossier_worker", inner("dossier"))
    monkeypatch.setattr(m, "readback_worker", inner("readback"))
    m.prepared_worker(role, bound)
    text_output.flush()
    ready_lines = output.getvalue().splitlines()
    assert len(ready_lines) == 1
    assert json.loads(ready_lines[0]) == m.prepared_io.ready_frame(role, bound)
    assert events[:4] == ["isolated", "native-proof", "guard-created", "source-check"]
    assert len(guards) == 1 and guards[0].closed
    assert events[-1] == "guard-close"
    return bound, events, sent, dispatched


@pytest.mark.parametrize("role,payload", (
    ("health", {}),
    ("dossier", {"discovered": {"invented": True}}),
    ("readback", {"complete_sha256": "c" * 64}),
))
def test_direct_prepared_entry_dispatches_only_its_canonical_role_payload(monkeypatch, role, payload):
    bound, events, sent, dispatched = _entry(monkeypatch, role, payload)
    expected = (bound,) if role == "health" else (
        bound, payload["discovered"] if role == "dossier" else payload["complete_sha256"])
    assert dispatched == [(role, expected)]
    assert sent == [{"completed": True, "role": role}]
    assert events.index("source-check") < events.index("dispatch-" + role)


@pytest.mark.parametrize("role,payload", (
    ("health", {"extra": True}),
    ("health", {"discovered": {}}),
    ("dossier", {}),
    ("dossier", {"discovered": {}, "extra": True}),
    ("dossier", {"complete_sha256": "c" * 64}),
    ("readback", {}),
    ("readback", {"complete_sha256": "c" * 63}),
    ("readback", {"complete_sha256": "g" * 64}),
    ("readback", {"complete_sha256": True}),
    ("readback", {"complete_sha256": "c" * 64, "extra": True}),
))
def test_direct_prepared_entry_refuses_role_payload_before_dispatch(monkeypatch, role, payload):
    _bound_value, _events, sent, dispatched = _entry(monkeypatch, role, payload)
    assert dispatched == []
    assert sent == [{"completed": False, "code": "activation_refused"}]


@pytest.mark.parametrize("role", ("health", "dossier", "readback"))
def test_direct_prepared_entry_eof_never_activates_a_role(monkeypatch, role):
    _bound_value, _events, sent, dispatched = _entry(monkeypatch, role, eof=True)
    assert dispatched == []
    assert sent == [{"completed": False, "code": "activation_refused"}]


@pytest.mark.parametrize("role,envelope_role", (
    ("health", "dossier"), ("dossier", "readback"), ("readback", "health"),
))
def test_direct_prepared_entry_refuses_another_canonical_role_envelope(monkeypatch, role, envelope_role):
    _bound_value, _events, sent, dispatched = _entry(
        monkeypatch, role, {}, envelope_role=envelope_role)
    assert dispatched == []
    assert sent == [{"completed": False, "code": "activation_refused"}]
