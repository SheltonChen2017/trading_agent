"""Claude review section 375: retained PIT audit runner guards without a pin.

Invented values only; no retained input, git operation, sandbox launch, provider
or account access. The caller supplies native process-tree network denial.
"""
import json
import os

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_pit_retained_audit_runner_v1 as m


IDENTITY = {"head": "1" * 40, "sources": {}, "source_inventory_sha256": "2" * 64}


@pytest.mark.parametrize("attribute", ("base_prefix", "executable"))
@pytest.mark.parametrize("covering", ("lane-root", "lane-parent", "custody-parent"))
def test_interpreter_prefix_cannot_grant_the_lane_or_custody_roots(monkeypatch, attribute, covering):
    prefix = {"lane-root": m.ROOT, "lane-parent": m.ROOT.parent,
              "custody-parent": m.stable.PRIVATE_CUSTODY_ROOT.parent}[covering]
    # sys.executable is two levels below the directory the policy grants.
    value = prefix / "bin" / "python" if attribute == "executable" else prefix
    monkeypatch.setattr(m.sys, attribute, str(value))
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m.policy(sources=m.OWN)


def test_unrelated_interpreter_prefix_keeps_the_native_denials(monkeypatch):
    monkeypatch.setattr(m.sys, "base_prefix", "/opt/invented-python")
    monkeypatch.setattr(m.sys, "executable", "/opt/invented-python/bin/python")
    policy = m.policy(sources=m.OWN)
    assert "(deny file-read-data)" in policy and "(deny network*)" in policy


def _launched(monkeypatch, value, *, identities=(IDENTITY, IDENTITY)):
    remaining = iter(identities)
    monkeypatch.setattr(m, "_identity", lambda *_: next(remaining))
    monkeypatch.setattr(m, "policy", lambda **_: "invented-policy")
    monkeypatch.setattr(m.stable.source, "_launch", lambda *_a, **_k: value)


def test_parent_returns_a_completed_worker_result(monkeypatch):
    value = {"completed": True, "read_only": True}
    _launched(monkeypatch, value)
    assert m.run_actual("1" * 40) is value


@pytest.mark.parametrize("value", ({}, {"completed": None}, {"completed": 1}, {"completed": "true"}))
def test_parent_refuses_a_worker_result_without_exact_completion(monkeypatch, value):
    _launched(monkeypatch, value)
    with pytest.raises(m.AuditRunnerError, match="retained_identity_audit_refused"):
        m.run_actual("1" * 40)


def test_parent_refuses_when_the_source_identity_moved_during_the_worker(monkeypatch):
    moved = {**IDENTITY, "source_inventory_sha256": "3" * 64}
    _launched(monkeypatch, {"completed": True}, identities=(IDENTITY, moved))
    with pytest.raises(m.AuditRunnerError, match="retained_identity_audit_refused"):
        m.run_actual("1" * 40)


class _Guard:
    def check(self):
        pass

    def close(self):
        pass


def test_worker_failure_wire_has_only_finite_fields_and_the_parent_reads_it_as_a_refusal(monkeypatch, capsysbinary):
    monkeypatch.setattr(m.stable.native, "_isolated", lambda: None)
    monkeypatch.setattr(m.stable.native.batch.campaign.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", _Guard)
    monkeypatch.setattr(m, "_source_current", lambda _identity: None)
    def held(*_a, **_k):
        raise OSError(13, "PRIVATE ACCOUNT BODY", "/private/PRIVATE-TOKEN")
    monkeypatch.setattr(m, "Held", held)
    m.worker(IDENTITY)
    wire = capsysbinary.readouterr().out
    assert b"PRIVATE" not in wire
    expected = {"completed": False, "read_only": True, "phase": "open_provider",
                "failure_class": "os_error", "os_errno": 13, "refusal_code": "unknown"}
    assert json.loads(wire) == {"ok": True, "value": expected}
    assert m.stable.source._ipc_result(wire, b"", 0) == expected
    assert m.ReportedAuditRefusal(expected).diagnostic == expected


def test_a_failure_after_the_success_wire_cannot_reach_the_parent_as_success():
    # The worker writes its success line, then runs one more guard check. A
    # failure there appends a diagnostic line, so stdout holds two documents.
    success = m.raw({"ok": True, "value": {"completed": True}}) + b"\n"
    late = m.raw({"ok": True, "value": m.failure_info("serialization", RuntimeError())}) + b"\n"
    assert m.stable.source._ipc_result(success, b"", 0) == {"completed": True}
    with pytest.raises(m.stable.source.FirstRateQualificationError):
        m.stable.source._ipc_result(success + late, b"", 0)


def _storage():
    physical = {"schema": m.stable.SCHEMA + "/storage-identity", "root_kind": "fixed_user_application_support",
                "device": 1, "inode": 2, "mode": 0o700, "owner": os.geteuid(), "group": 20}
    proof = {"passed": True, "fixture_only": False, "storage_identity": dict(physical)}
    return physical, proof, {**proof, "storage_identity": dict(physical), "receipt_sha256": m.PINS["proof_complete"]["sha256"]}


@pytest.mark.parametrize(("field", "value"), (("schema", "invented"), ("root_kind", "fixture"), ("mode", 0o755),
    ("owner", os.geteuid() + 1 if hasattr(os, "geteuid") else 1), ("inode", 0), ("device", -1), ("group", "20")))
def test_current_storage_identity_fields_are_each_required(field, value):
    physical, proof, qualification = _storage()
    changed = {**physical, field: value}
    # The stored proofs agree with the changed value, so only the field rule can refuse it.
    proof["storage_identity"] = dict(changed)
    qualification["storage_identity"] = dict(changed)
    with pytest.raises(m.AuditRunnerError, match="storage_identity_refused"):
        m.storage_binding(changed, proof, qualification)


def test_unexpected_failure_code_is_reported_as_unknown():
    assert m.failure_info("derive", m.AuditRunnerError("PRIVATE VALUE"))["refusal_code"] == "unknown"
    assert m.failure_info("derive", m.audit.PitRetainedAuditError("row_limit_refused"))["refusal_code"] == "row_limit_refused"
    assert m.failure_info("derive", OSError(999, "PRIVATE"))["os_errno"] is None
    # A foreign exception whose text happens to equal a safe code is still not an own refusal.
    assert m.failure_info("derive", ValueError("row_limit_refused"))["refusal_code"] == "unknown"
