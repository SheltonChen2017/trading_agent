"""Claude section 383 review: the PIT audit workers' isolation and final checks.

Both workers must prove native isolation and current source bytes before they
open any retained leaf, recheck every held leaf and the source bytes at the end,
and take the storage-qualification pin from the provider receipt. The earlier
tests replace those calls with silent no-ops, so removing any of them passed.
Invented values only; no retained input, git, sandbox launch or provider access.
"""
import json
import os

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_pit_retained_audit_runner_v1 as m


IDENTITY = {"head": "1" * 40, "sources": {}, "source_inventory_sha256": "2" * 64}
STORAGE_PIN = {"bytes": 2, "sha256": "4" * 64}
CONTROLS_PIN = {"bytes": 3, "sha256": "5" * 64}


def _storage():
    physical = {"schema": m.stable.SCHEMA + "/storage-identity", "root_kind": "fixed_user_application_support",
                "device": 1, "inode": 2, "mode": 0o700, "owner": os.geteuid(), "group": 20}
    proof = {"passed": True, "fixture_only": False, "storage_identity": dict(physical)}
    qualification = {**proof, "storage_identity": dict(physical), "receipt_sha256": m.PINS["proof_complete"]["sha256"]}
    return physical, proof, qualification


def _install(monkeypatch, events, values, *, physical):
    """Record every isolation, source, read and recheck call in one ordered log."""
    bodies = {}

    class Guard:
        def __init__(self):
            events.append("guard")
        def check(self):
            pass
        def close(self):
            pass

    class Held:
        def __init__(self, root):
            events.append(("open", root))
            self.root, self.leaves = root, {}
        def read(self, name, pin, *, check):
            check(); events.append(("read", self.root, name, pin)); self.leaves[name] = pin
            data = str(len(bodies)).encode(); bodies[data] = values[self.root, name]
            return data
        def check(self, *, check):
            check(); events.append(("check", self.root))
        def close(self):
            pass

    class Chain:
        def __init__(self, *_):
            pass
        def close(self):
            pass

    monkeypatch.setattr(m.stable.native, "_isolated", lambda: events.append("isolated"))
    monkeypatch.setattr(m.stable.native.batch.campaign.base, "_prove_isolation", lambda: events.append("prove"))
    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", Guard)
    monkeypatch.setattr(m, "_source_current", lambda _identity: events.append("source"))
    monkeypatch.setattr(m, "Held", Held)
    monkeypatch.setattr(m, "decode", lambda body, _pin: bodies[body])
    monkeypatch.setattr(m.stable, "_HeldChain", Chain)
    monkeypatch.setattr(m.stable, "_managed", lambda _held: None)
    monkeypatch.setattr(m.stable, "_storage_identity", lambda *_a, **_k: physical)


def _before_first_open(events):
    first = next(i for i, event in enumerate(events) if type(event) is tuple)
    return events[:first]


@pytest.mark.parametrize("entry", ("worker", "storage_diagnostic_worker"))
def test_isolation_and_source_proofs_precede_the_first_retained_open(monkeypatch, capsysbinary, entry):
    events = []
    physical, _proof, _qualification = _storage()
    _install(monkeypatch, events, {}, physical=physical)

    def refuse(root):
        events.append(("open", root))
        raise OSError(13, "invented refusal")
    monkeypatch.setattr(m, "Held", refuse)
    getattr(m, entry)(IDENTITY)
    value = json.loads(capsysbinary.readouterr().out)["value"]
    assert value["completed"] is False and value["phase"] == "open_provider"
    assert _before_first_open(events) == ["isolated", "prove", "guard", "source"]
    assert events[-1] == ("open", m.PROVIDER)


def test_diagnostic_rechecks_every_leaf_and_the_source_after_reading(monkeypatch, capsysbinary):
    events = []
    physical, proof, qualification = _storage()
    complete = {"published_leaf_pins": {"storage-qualification.json": STORAGE_PIN}}
    values = {(m.PROVIDER, "complete.json"): complete, (m.PROOF, "complete.json"): proof,
              (m.PROVIDER, "storage-qualification.json"): qualification}
    _install(monkeypatch, events, values, physical=physical)
    m.storage_diagnostic_worker(IDENTITY)
    value = json.loads(capsysbinary.readouterr().out)["value"]
    assert value["completed"] is True and value["binding_passed"] is True
    reads = [event for event in events if type(event) is tuple and event[0] == "read"]
    assert reads[-1] == ("read", m.PROVIDER, "storage-qualification.json", STORAGE_PIN)
    last_read = events.index(reads[-1])
    tail = events[last_read + 1:]
    assert tail == [("check", m.PROVIDER), ("check", m.PROOF), "source"]


def test_audit_worker_rechecks_every_leaf_and_the_source_after_deriving(monkeypatch, capsysbinary):
    events = []
    physical, proof, qualification = _storage()
    complete = {"published_leaf_pins": {"controls.json": CONTROLS_PIN, "storage-qualification.json": STORAGE_PIN}}
    receipt = {"capture_manifest_sha256": m.MANIFEST,
               "tickers_projection_sha256": m.PINS["tickers_projection"]["sha256"],
               "actions_projection_sha256": m.PINS["actions_projection"]["sha256"],
               "fixture_only": False, "financial_values_interpreted": False}
    values = {(m.PROVIDER, "complete.json"): complete, (m.PROOF, "complete.json"): proof,
              (m.PROVIDER, "controls.json"): {"fixture_only": False, "cases": list(range(12))},
              (m.PROVIDER, "storage-qualification.json"): qualification,
              (m.SHARADAR, "complete.json"): receipt}
    _install(monkeypatch, events, values, physical=physical)
    monkeypatch.setattr(m, "projection", lambda *_a, **_k: events.append("projection") or [])
    monkeypatch.setattr(m.audit, "build_audit", lambda *_a, **_k: events.append("derive") or {})
    monkeypatch.setattr(m.audit, "public_summary", lambda _value: {"schema": "invented-summary"})
    m.worker(IDENTITY)
    value = json.loads(capsysbinary.readouterr().out)["value"]
    assert value["completed"] is True and value["schema"] == "invented-summary"
    reads = [event for event in events if type(event) is tuple and event[0] == "read"]
    assert ("read", m.PROVIDER, "controls.json", CONTROLS_PIN) in reads
    assert ("read", m.PROVIDER, "storage-qualification.json", STORAGE_PIN) in reads
    tail = events[events.index("derive") + 1:]
    assert tail == [("check", m.PROVIDER), ("check", m.PROOF), ("check", m.SHARADAR), "source"]
